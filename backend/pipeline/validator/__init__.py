"""Validator stage: events stage=CLEANED → stage=VALIDATED."""
from __future__ import annotations

import logging

from domain.models import CanonicalEvent
from domain.rules import load_rules

from .base import BaseValidator
from .config import ValidateConfig
from .runner import ValidationRunner

__all__ = ["BaseValidator", "ValidateConfig", "ValidationRunner", "run"]

logger = logging.getLogger("pipeline.validator")


def run(
    events: list[CanonicalEvent],
    *,
    config: ValidateConfig | None = None,
) -> list[CanonicalEvent]:
    runner = ValidationRunner.from_config(load_rules(), config)
    validated = runner.apply_all(events)
    logger.info("validator processed %d events", len(validated))
    return validated
