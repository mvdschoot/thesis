"""Cleaner stage: events stage=STRUCTURED → stage=CLEANED."""
from __future__ import annotations

import logging

from domain.models import CanonicalEvent

from .base import BaseHeuristic, HeuristicChain
from .cleaner import Cleaner
from .coercion import TypeCoercer
from .timestamp import TimestampNormalizer
from .units import UnitInferrer
from .whitespace import WhitespaceStripper

__all__ = [
    "BaseHeuristic",
    "HeuristicChain",
    "Cleaner",
    "TypeCoercer",
    "TimestampNormalizer",
    "UnitInferrer",
    "WhitespaceStripper",
    "run",
]

logger = logging.getLogger("pipeline.cleaner")

_CLEANER = Cleaner()


def run(events: list[CanonicalEvent]) -> list[CanonicalEvent]:
    cleaned = _CLEANER.apply_all(events)
    logger.info("cleaner processed %d events", len(cleaned))
    return cleaned
