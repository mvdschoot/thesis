"""OMOPHub FHIR Resolver: batch-resolve FHIR codings to OMOP concepts.

Uses ``POST /v1/fhir/resolve/batch`` via stdlib ``urllib``.  Falls back
to per-coding ``POST /v1/fhir/resolve`` when the batch call is rejected
(some codes like UCUM ``%`` trigger server-side validation errors).
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
import urllib.error
import urllib.request
from typing import Any

logger = logging.getLogger("pipeline.omop.resolver")

_CACHE_TTL = 600  # 10 minutes
_cache_lock = threading.Lock()
_resolution_cache: dict[tuple[str, str, str], tuple[float, dict[str, Any]]] = {}

_BASE_URL = "https://api.omophub.com/v1"

_EMPTY_RESOLUTION: dict[str, Any] = {
    "source_concept": {"concept_id": 0},
    "standard_concept": {"concept_id": 0, "domain_id": ""},
    "target_table": "",
    "mapping_type": "unmapped",
}


def _get_api_key() -> str | None:
    key = os.environ.get("OMOPHUB_API_KEY", "").strip()
    if not key:
        logger.warning(
            "OMOPHUB_API_KEY not set — OMOP CDM concept resolution "
            "will return concept_id=0 for all codings"
        )
        return None
    return key


def _http_post(path: str, body: dict[str, Any], api_key: str) -> dict[str, Any]:
    payload = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        f"{_BASE_URL}{path}",
        data=payload,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())


def _resolve_single(
    coding: dict[str, str],
    api_key: str,
    resource_type: str,
) -> dict[str, Any]:
    """Resolve one coding via POST /v1/fhir/resolve."""
    body: dict[str, Any] = {
        "system": coding["system"],
        "code": coding["code"],
        "on_unmapped": "sentinel",
    }
    if resource_type:
        body["resource_type"] = resource_type
    try:
        data = _http_post("/fhir/resolve", body, api_key)
        resolution = data.get("resolution") or data.get("data", {}).get("resolution")
        if resolution and isinstance(resolution, dict):
            return resolution
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="replace")[:300] if e.fp else ""
        logger.warning(
            "omophub resolve %s|%s → %d: %s",
            coding["system"], coding["code"], e.code, err_body,
        )
    except Exception as exc:
        logger.warning("omophub resolve %s|%s failed: %s", coding["system"], coding["code"], exc)
    return dict(_EMPTY_RESOLUTION)


def batch_resolve(
    codings: list[dict[str, str]],
    *,
    resource_type: str = "Observation",
) -> dict[tuple[str, str], dict[str, Any]]:
    """Resolve a list of FHIR codings to OMOP concepts.

    Returns a dict mapping ``(system, code)`` → resolution from the API.
    Unresolved codings get :data:`_EMPTY_RESOLUTION`.  Results are cached
    in-process for ``_CACHE_TTL`` seconds so repeated batch-transform
    requests with the same codings don't re-hit the external API.
    """
    if not codings:
        return {}

    api_key = _get_api_key()
    if api_key is None:
        return {
            (c["system"], c["code"]): dict(_EMPTY_RESOLUTION)
            for c in codings
        }

    now = time.monotonic()
    result: dict[tuple[str, str], dict[str, Any]] = {}
    uncached: list[dict[str, str]] = []

    with _cache_lock:
        for c in codings:
            cache_key = (c["system"], c["code"], resource_type)
            entry = _resolution_cache.get(cache_key)
            if entry and (now - entry[0]) < _CACHE_TTL:
                result[(c["system"], c["code"])] = dict(entry[1])
            else:
                uncached.append(c)

    if not uncached:
        logger.info("omophub batch resolve: all %d codings served from cache", len(codings))
        return result

    logger.info(
        "omophub batch resolve: %d cached, %d to fetch",
        len(codings) - len(uncached), len(uncached),
    )

    for i in range(0, len(uncached), 100):
        chunk = uncached[i : i + 100]
        try:
            data = _http_post("/fhir/resolve/batch", {
                "codings": chunk,
                "resource_type": resource_type,
                "on_unmapped": "sentinel",
            }, api_key)
            results_list = data.get("results", [])
            if not results_list and isinstance(data.get("data"), dict):
                results_list = data["data"].get("results", [])
            logger.info(
                "omophub batch resolved chunk=%d → %d results",
                i, len(results_list),
            )
            for item in results_list:
                if not isinstance(item, dict):
                    continue
                inp = item.get("input", {})
                sys = inp.get("system", "")
                code = inp.get("code", "")
                if not sys or not code:
                    continue
                resolution = item.get("resolution")
                if resolution and isinstance(resolution, dict):
                    result[(sys, code)] = resolution
                else:
                    result[(sys, code)] = dict(_EMPTY_RESOLUTION)
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="replace")[:300] if e.fp else ""
            logger.warning(
                "omophub batch rejected (chunk %d, %d codings): %d %s — falling back to single resolve",
                i, len(chunk), e.code, err_body,
            )
            for c in chunk:
                key = (c["system"], c["code"])
                if key not in result:
                    result[key] = _resolve_single(c, api_key, resource_type)
        except Exception as exc:
            logger.error("omophub batch resolve failed for chunk %d: %s", i, exc)
            for c in chunk:
                key = (c["system"], c["code"])
                if key not in result:
                    result[key] = dict(_EMPTY_RESOLUTION)

    for c in uncached:
        key = (c["system"], c["code"])
        if key not in result:
            result[key] = dict(_EMPTY_RESOLUTION)

    with _cache_lock:
        for c in uncached:
            key = (c["system"], c["code"])
            if key in result:
                _resolution_cache[(key[0], key[1], resource_type)] = (now, result[key])

    return result
