from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from .adapters.registry import AdapterRegistry
from .connectors.base import BaseConnector
from .heuristics.base import HeuristicChain
from .models.canonical import CanonicalEvent

logger = logging.getLogger(__name__)


class Pipeline:
    """Orchestrates the ingestion pipeline: connector -> adapter -> heuristics.

    Reads data via a connector, looks up the appropriate adapter for each
    record, transforms to canonical events, and applies heuristics.
    """

    def __init__(
        self,
        connector: BaseConnector,
        registry: AdapterRegistry,
        heuristics: HeuristicChain | None = None,
    ) -> None:
        self.connector = connector
        self.registry = registry
        self.heuristics = heuristics or HeuristicChain()

    def run(self, path: str | Path) -> list[CanonicalEvent]:
        """Run the pipeline on the given input path.

        Returns all canonical events produced.
        """
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

            events = adapter.transform(metadata, record)
            # events = self.heuristics.apply_all(events)
            all_events.extend(events)

        logger.info(
            "Pipeline complete: %d events produced, %d records skipped",
            len(all_events),
            skipped,
        )
        return all_events
