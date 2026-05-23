"""LangChain tool wrappers for the concept-suggestion agentic loop.

Each tool is a thin shim over an existing client so the LLM can call it via
function calling.  Tool docstrings are critical — they ARE the tool description
the model sees.
"""
from __future__ import annotations

import json

from langchain_core.tools import tool

from api.terminology import TerminologyError, get_client


@tool
def search_terminology(system: str, query: str) -> str:
    """Search medical terminology databases for standard codes.

    Use this tool to look up FHIR-compatible codes in official vocabularies.

    Args:
        system: The terminology to search. One of:
            - "loinc"  — observation codes (heart rate, blood pressure, BMI, …)
            - "ucum"   — measurement units (bpm, kg, mmHg, mg/dL, …)
            - "snomed" — clinical concepts (fallback when LOINC has no match)
        query: Natural-language search terms, e.g. "heart rate", "body mass index",
               "beats per minute". Keep queries short and specific.

    Returns:
        JSON array of up to 5 matching concepts, each with ``system`` (URI),
        ``code``, and ``display``.  Empty array if nothing matched.
    """
    if system not in ("loinc", "ucum", "snomed"):
        return json.dumps({"error": f"Unknown system {system!r}. Use loinc, ucum, or snomed."})
    try:
        results = get_client().search(system, query, max_results=5)  # type: ignore[arg-type]
        return json.dumps(results)
    except TerminologyError as exc:
        return json.dumps({"error": f"Terminology search failed: {exc}"})
