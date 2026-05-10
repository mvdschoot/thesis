"""Quality-rules loader, used by the validator and qualifier services.

The path defaults to /app/configs/quality_rules.yaml inside containers; can
be overridden with the QUALITY_RULES_PATH env var.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

_DEFAULT_PATH = Path("/app/configs/quality_rules.yaml")


def quality_rules_path() -> Path:
    return Path(os.environ.get("QUALITY_RULES_PATH", str(_DEFAULT_PATH)))


def load_rules() -> dict[str, Any]:
    path = quality_rules_path()
    try:
        with path.open("r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except FileNotFoundError:
        logger.warning("quality_rules.yaml not found at %s; using empty rules", path)
        return {}
