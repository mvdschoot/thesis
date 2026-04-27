from __future__ import annotations

from collections import defaultdict
from statistics import median

from shared.models import CanonicalEvent, QualityFlag, Severity

_HAMPEL_THRESHOLD = 3.5  # number of MADs from the median
_MIN_GROUP_SIZE = 5


def _numeric(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def detect_outliers(events: list[CanonicalEvent]) -> None:
    """Hampel test per (subject_id, category) group on payload.value.

    Skips groups with fewer than _MIN_GROUP_SIZE numeric values; emits
    OUTLIER_INSUFFICIENT_DATA (info) on the first event of such groups.
    """
    groups: dict[tuple[str, str], list[tuple[CanonicalEvent, float]]] = defaultdict(list)
    for event in events:
        v = _numeric(event.payload.value)
        if v is None:
            continue
        groups[(event.subject_id, event.category)].append((event, v))

    for key, members in groups.items():
        if len(members) < _MIN_GROUP_SIZE:
            members[0][0].quality.flags.append(
                QualityFlag(
                    code="OUTLIER_INSUFFICIENT_DATA",
                    severity=Severity.INFO,
                    stage="qualified",
                    message=f"Group ({key[0]}, {key[1]}) has {len(members)} numeric points; Hampel skipped",
                )
            )
            continue

        values = [v for _, v in members]
        med = median(values)
        abs_dev = [abs(v - med) for v in values]
        mad = median(abs_dev)
        if mad == 0:
            continue

        for event, v in members:
            score = abs(v - med) / mad
            if score > _HAMPEL_THRESHOLD:
                event.quality.flags.append(
                    QualityFlag(
                        code="OUTLIER_HAMPEL",
                        severity=Severity.WARNING,
                        stage="qualified",
                        message=f"|x-median|/MAD = {score:.2f} > {_HAMPEL_THRESHOLD} (median={med}, MAD={mad})",
                    )
                )
