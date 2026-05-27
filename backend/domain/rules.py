"""Quality-rules loader, used by the validator and qualifier stages.

Resolves to backend/configs/quality_rules.yaml relative to this file.
Override with QUALITY_RULES_PATH for tests or non-default deployments.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

# domain/rules.py → backend/configs/quality_rules.yaml
_DEFAULT_PATH = Path(__file__).resolve().parent.parent / "configs" / "quality_rules.yaml"

_cached_rules: dict[str, Any] | None = None
_cached_path: Path | None = None


def quality_rules_path() -> Path:
    return Path(os.environ.get("QUALITY_RULES_PATH", str(_DEFAULT_PATH)))


def load_rules() -> dict[str, Any]:
    global _cached_rules, _cached_path
    path = quality_rules_path()
    if _cached_rules is not None and _cached_path == path:
        return _cached_rules
    try:
        with path.open("r", encoding="utf-8") as f:
            _cached_rules = yaml.safe_load(f) or {}
    except FileNotFoundError:
        logger.warning("quality_rules.yaml not found at %s; using empty rules", path)
        _cached_rules = {}
    _cached_path = path
    return _cached_rules
