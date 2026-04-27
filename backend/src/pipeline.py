from __future__ import annotations

import logging
from pathlib import Path

from .adapters.registry import AdapterRegistry
from .cleaning.cleaner import Cleaner
from .connectors.base import BaseConnector
from .models.canonical import CanonicalEvent
from .qualification.qualifier import Qualifier
from .validation.runner import ValidationRunner

logger = logging.getLogger(__name__)


class Pipeline:
    """Orchestrates the ingestion pipeline:
    connector -> adapter -> cleaner -> validator -> qualifier.

    Each post-adapter stage advances the event's `stage` field, leaving an
    audit trail of QualityFlags. Failed-validation events are kept and tagged
    (`quality.plausibility="exclude"`) so consumers choose their own filter.
    """

    def __init__(
        self,
        connector: BaseConnector,
        registry: AdapterRegistry,
        cleaner: Cleaner | None = None,
        validator: ValidationRunner | None = None,
        qualifier: Qualifier | None = None,
    ) -> None:
        self.connector = connector
        self.registry = registry
        self.cleaner = cleaner or Cleaner()
        self.validator = validator or ValidationRunner()
        self.qualifier = qualifier or Qualifier()

    def run(self, path: str | Path) -> list[CanonicalEvent]:
        path = Path(path)
        all_events: list[CanonicalEvent] = []
        skipped = 0

        for metadata, record in self.connector.read(path):
            adapter = self.registry.get_adapter(metadata, record)
            if adapter is None:
                logger.warning(
                    "No adapter found for record from source '%s', skipping",
                    metadata.source_name,
                )
                skipped += 1
                continue

            all_events.extend(adapter.transform(metadata, record))

        all_events = self.cleaner.apply_all(all_events)
        all_events = self.validator.apply_all(all_events)
        all_events = self.qualifier.apply_all(all_events)

        logger.info(
            "Pipeline complete: %d events produced, %d records skipped",
            len(all_events),
            skipped,
        )
        return all_events
