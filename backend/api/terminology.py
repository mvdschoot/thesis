"""Terminology search client backed by OMOPHub semantic search.

OMOPHub (https://omophub.com) is a hosted OHDSI/ATHENA vocabulary search API.
The semantic search endpoint (``/v1/concepts/semantic-search``) uses
LLM-generated embeddings to find concepts by natural language — e.g.
"heart attack" → "Myocardial infarction". Results come pre-ranked by cosine
similarity so no client-side re-ranking is needed.

We map ``vocabulary_id`` → FHIR system URI and expose a flat
``[{system, code, display}]`` shape so the frontend doesn't need to know
about OMOP.

Auth: bearer token from the ``OMOPHUB_API_KEY`` env var.
Docs: https://docs.omophub.com
"""
from __future__ import annotations

import json
import logging
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Literal, Protocol

logger = logging.getLogger(__name__)

BASE_URL = "https://api.omophub.com/v1"
SEMANTIC_SEARCH_PATH = "/concepts/semantic-search"

TermSystem = Literal["loinc", "ucum", "snomed", "rxnorm", "icd10", "cpt"]

# Frontend-facing system name → OMOPHub vocabulary_id filter.
_VOCAB_FILTER: dict[str, str] = {
    "loinc": "LOINC",
    "ucum": "UCUM",
    "snomed": "SNOMED",
    "rxnorm": "RxNorm",
    "icd10": "ICD10CM",
    "cpt": "CPT4",
}

_EXCLUDED_CONCEPT_CLASSES: frozenset[str] = frozenset({
    "LOINC Hierarchy",
    "LOINC Component",
    "LOINC System",
    "LOINC Method",
    "LOINC Property",
    "LOINC Time Aspect",
    "LOINC Scale",
})

# OMOPHub vocabulary_id → FHIR system URI. We only map systems we actively
# surface; unknown vocabularies fall back to ``urn:oid:omophub:<vocab>`` so the
# code is still round-trippable.
_FHIR_SYSTEM: dict[str, str] = {
    "LOINC": "http://loinc.org",
    "UCUM": "http://unitsofmeasure.org",
    "SNOMED": "http://snomed.info/sct",
    "RxNorm": "http://www.nlm.nih.gov/research/umls/rxnorm",
    "ICD10CM": "http://hl7.org/fhir/sid/icd-10-cm",
    "ICD10": "http://hl7.org/fhir/sid/icd-10",
    "ICD9CM": "http://hl7.org/fhir/sid/icd-9-cm",
    "HCPCS": "https://www.cms.gov/Medicare/Coding/MedHCPCSGenInfo",
    "CPT4": "http://www.ama-assn.org/go/cpt",
    "ATC": "http://www.whocc.no/atc",
}


class TerminologyError(RuntimeError):
    """Raised when the upstream terminology service fails."""


class TerminologyClient(Protocol):
    def search(self, system: TermSystem, query: str, max_results: int = 20) -> list[dict[str, str]]:
        ...


class OmopHubClient:
    """OMOPHub-backed terminology search.

    Reads the API key from ``OMOPHUB_API_KEY`` at call time so the env can be
    set after process start (uvicorn --reload picks it up cleanly). Uses
    stdlib ``urllib`` — one upstream endpoint isn't worth an httpx dep.
    """

    _MIN_REQUEST_INTERVAL = 0.5

    def __init__(self, *, timeout: float = 5.0) -> None:
        self._timeout = timeout
        self._last_request: float = 0.0

    @staticmethod
    def _require_key() -> str:
        key = os.environ.get("OMOPHUB_API_KEY", "").strip()
        if not key:
            raise TerminologyError(
                "OMOPHUB_API_KEY is not set. Get a key from https://dashboard.omophub.com "
                "and add it to backend/.env or your shell environment."
            )
        return key

    def search(
        self,
        system: TermSystem,
        query: str,
        max_results: int = 20,
    ) -> list[dict[str, str]]:
        vocab = _VOCAB_FILTER.get(system)
        if vocab is None:
            raise TerminologyError(f"Unsupported terminology system: {system}")

        q = (query or "").strip()
        if not q:
            return []
        if len(q) < 3:
            q = q + " "  # OmopHub requires >= 3 chars

        max_n = max(1, min(int(max_results or 20), 100))
        params = {
            "query": q,
            "vocabulary_ids": vocab,
            "page_size": str(max_n),
            "threshold": "0.3",
        }
        url = f"{BASE_URL}{SEMANTIC_SEARCH_PATH}?{urllib.parse.urlencode(params)}"
        req = urllib.request.Request(
            url,
            headers={
                "Authorization": f"Bearer {self._require_key()}",
                "Accept": "application/json",
            },
        )

        elapsed = time.monotonic() - self._last_request
        if elapsed < self._MIN_REQUEST_INTERVAL:
            time.sleep(self._MIN_REQUEST_INTERVAL - elapsed)

        max_retries = 3
        for attempt in range(max_retries):
            try:
                with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                    raw = resp.read()
                self._last_request = time.monotonic()
                break
            except urllib.error.HTTPError as e:
                if e.code == 429 and attempt < max_retries - 1:
                    retry_after = float(e.headers.get("Retry-After", 1 + attempt))
                    logger.warning("omophub rate-limited (%s), retrying in %.1fs", system, retry_after)
                    time.sleep(retry_after)
                    continue
                body = e.read().decode("utf-8", errors="replace")[:200] if e.fp else ""
                logger.warning("omophub fetch failed (%s): %s %s", system, e.code, body)
                raise TerminologyError(f"omophub upstream {e.code}: {body or e.reason}") from e
            except urllib.error.URLError as e:
                logger.warning("omophub fetch failed (%s): %s", system, e)
                raise TerminologyError(f"upstream fetch failed: {e}") from e

        try:
            data = json.loads(raw)
        except json.JSONDecodeError as e:
            raise TerminologyError(f"upstream returned invalid JSON: {e}") from e

        results = _parse_response(data)
        return results[:max_n]


def _extract_results(data: Any) -> list[dict[str, Any]]:
    """Pull the result list out of OMOPHub's response shape.

    OMOPHub's docs aren't explicit about the envelope. Common API patterns it
    might use: top-level array, ``{"data": [...]}``, ``{"results": [...]}``,
    or ``{"data": {"concepts": [...]}}``. Try the obvious shapes and fall
    through. Each result dict must carry ``concept_code`` + ``concept_name`` +
    ``vocabulary_id`` per the documented field names.
    """
    if isinstance(data, list):
        return data
    if not isinstance(data, dict):
        return []
    for key in ("data", "results", "concepts", "items"):
        v = data.get(key)
        if isinstance(v, list):
            return v
        if isinstance(v, dict):
            for sub_key in ("concepts", "results", "items"):
                sv = v.get(sub_key)
                if isinstance(sv, list):
                    return sv
    return []


def _parse_response(data: Any) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for item in _extract_results(data):
        if not isinstance(item, dict):
            continue
        code = item.get("concept_code")
        name = item.get("concept_name")
        vocab = item.get("vocabulary_id")
        if not code or not vocab:
            continue
        concept_class = str(item.get("concept_class_id", ""))
        if concept_class in _EXCLUDED_CONCEPT_CLASSES:
            continue
        system_uri = _FHIR_SYSTEM.get(str(vocab)) or f"urn:omophub:vocab:{vocab}"
        out.append({
            "system": system_uri,
            "code": str(code),
            "display": str(name) if name else str(code),
        })
    return out


_singleton: OmopHubClient | None = None


def get_client() -> OmopHubClient:
    global _singleton
    if _singleton is None:
        _singleton = OmopHubClient()
    return _singleton
