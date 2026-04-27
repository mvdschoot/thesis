from __future__ import annotations

from ..models.canonical import CanonicalEvent, QualityFlag, Severity


def _fingerprint(event: CanonicalEvent) -> tuple:
    val = event.payload.value
    if isinstance(val, float):
        val = round(val, 3)
    return (event.subject_id, event.category, event.timestamp, val)


def detect_duplicates(events: list[CanonicalEvent]) -> None:
    """Tag every event after the first with the same (subject, category, ts, value)."""
    seen: set[tuple] = set()
    for event in events:
        fp = _fingerprint(event)
        if fp in seen:
            event.quality.flags.append(
                QualityFlag(
                    code="DUPLICATE_EVENT",
                    severity=Severity.WARNING,
                    stage="qualified",
                    message="Duplicate of an earlier event with the same (subject, category, timestamp, value)",
                )
            )
        else:
            seen.add(fp)
