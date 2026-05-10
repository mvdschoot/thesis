"""Validator stage: events stage=CLEANED → stage=VALIDATED."""
from __future__ import annotations

import logging

from domain.models import CanonicalEvent
from domain.rules import load_rules

from .base import BaseValidator
from .runner import ValidationRunner

__all__ = ["BaseValidator", "ValidationRunner", "run"]

logger = logging.getLogger("pipeline.validator")

_RULES = load_rules()
_RUNNER = ValidationRunner(rules=_RULES)


def run(events: list[CanonicalEvent]) -> list[CanonicalEvent]:
    validated = _RUNNER.apply_all(events)
    logger.info("validator processed %d events", len(validated))
    return validated
