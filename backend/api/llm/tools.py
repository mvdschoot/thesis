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
            - "loinc"  — observation/measurement codes (heart rate, blood pressure, BMI, …)
            - "ucum"   — measurement units (bpm, kg, mmHg, mg/dL, …)
            - "snomed" — clinical concepts (fallback when LOINC has no match)
            - "rxnorm" — medication codes
            - "icd10"  — diagnosis codes (ICD-10-CM)
            - "cpt"    — procedure codes (CPT-4)
        query: Search terms. You can search by:
            - Natural language: "heart rate", "body mass index", "beats per minute"
            - Code number: "8867-4" to look up a specific code you know

    Returns:
        JSON array of up to 10 matching concepts, each with ``system`` (URI),
        ``code``, and ``display``.  Empty array if nothing matched.
        Results are ranked by relevance to your query.
    """
    if system not in ("loinc", "ucum", "snomed", "rxnorm", "icd10", "cpt"):
        return json.dumps({"error": f"Unknown system {system!r}. Use loinc, ucum, snomed, rxnorm, icd10, or cpt."})
    try:
        results = get_client().search(system, query, max_results=10)  # type: ignore[arg-type]
        return json.dumps(results)
    except TerminologyError as exc:
        return json.dumps({"error": f"Terminology search failed: {exc}"})
