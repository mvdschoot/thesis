from __future__ import annotations

from typing import Any

from ..models.canonical import CanonicalEvent

# Default expected fields when no per-category schema is declared.
_DEFAULT_EXPECTED = ["subject_id", "timestamp", "payload.value"]


def _is_present(event: CanonicalEvent, path: str) -> bool:
    """Resolve a dotted field path against a CanonicalEvent and check non-empty."""
    parts = path.split(".")
    obj: Any = event
    for part in parts:
        if isinstance(obj, dict):
            obj = obj.get(part)
        else:
            obj = getattr(obj, part, None)
        if obj is None:
            return False
    if isinstance(obj, str) and obj == "":
        return False
    if isinstance(obj, (list, tuple)) and len(obj) == 0:
        return False
    return True


def compute_completeness(
    event: CanonicalEvent, category_rules: dict[str, Any]
) -> tuple[float, int, int]:
    """Returns (ratio, present_count, expected_count)."""
    expected = category_rules.get("expected_fields") or _DEFAULT_EXPECTED
    if not expected:
        return 1.0, 0, 0
    present = sum(1 for f in expected if _is_present(event, f))
    total = len(expected)
    ratio = present / total if total else 1.0
    return ratio, present, total
