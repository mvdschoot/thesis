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
