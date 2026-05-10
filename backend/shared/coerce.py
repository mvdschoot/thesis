from __future__ import annotations


def try_coerce_numeric(value: object) -> tuple[object, bool]:
    if not isinstance(value, str):
        return value, False
    s = value.strip()
    if not s:
        return value, False
    try:
        if "." in s or "e" in s or "E" in s:
            return float(s), True
        return int(s), True
    except ValueError:
        try:
            return float(s), True
        except ValueError:
            return value, False
