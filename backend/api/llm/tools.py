"""LangChain tool wrappers for the concept-suggestion agentic loop.

Each tool is a thin shim over an existing client so the LLM can call it via
function calling.  Tool docstrings are critical — they ARE the tool description
the model sees.
"""
from __future__ import annotations

import json

from langchain_core.tools import tool

from api.terminology import TerminologyError, get_client, VOCAB_FILTER


@tool
def search_terminology(searches: list[dict[str, str]]) -> str:
    """Search medical terminology databases for standard codes.

    Submit ALL lookups in a SINGLE call — do not call this tool once per term.
    Up to 25 searches per call.

    Args:
        searches: list of search objects. Each has:
            - query: natural-language terms or a known code (e.g. "heart rate", "8867-4", "beats per minute")
            - system: vocabulary to search. One of:
                "loinc"  — observation/measurement codes
                "ucum"   — measurement units
                "snomed" — clinical concepts (fallback when LOINC has no match)
                "rxnorm" — medication codes
                "icd10"  — diagnosis codes
                "cpt"    — procedure codes

    Returns:
        JSON list in the same order as the input. Each element has
        ``query``, ``system``, and ``results`` (array of {system, code, display}).
        Empty results array if nothing matched.
    """
    valid_systems = set(VOCAB_FILTER.keys())
    for s in searches:
        sys = s.get("system", "")
        if sys not in valid_systems:
            return json.dumps({"error": f"Unknown system {sys!r}. Use one of: {', '.join(sorted(valid_systems))}"})

    bulk_searches = []
    for i, s in enumerate(searches):
        q = (s.get("query") or "").strip()
        if not q:
            continue
        if len(q) < 3:
            q = q + " "
        bulk_searches.append({
            "search_id": str(i),
            "query": q,
            "vocabulary_ids": [VOCAB_FILTER[s["system"]]],
            "page_size": 10,
        })

    if not bulk_searches:
        return json.dumps([{"query": s.get("query", ""), "system": s.get("system", ""), "results": []} for s in searches])

    try:
        results_map = get_client().bulk_search(
            bulk_searches,
            defaults={"threshold": 0.3},
        )
    except TerminologyError as exc:
        return json.dumps({"error": f"Terminology search failed: {exc}"})

    output = []
    for i, s in enumerate(searches):
        concepts = results_map.get(str(i), [])
        output.append({
            "query": s.get("query", ""),
            "system": s.get("system", ""),
            "results": concepts,
        })
    return json.dumps(output)
