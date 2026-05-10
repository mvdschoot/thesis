from __future__ import annotations

import logging
from typing import Any

from domain.models import SourceMetadata

from .base import BaseAdapter

logger = logging.getLogger(__name__)


class AdapterRegistry:
    """Registry that maps source data to the appropriate adapter.

    Adapters are registered by instance. When looking up an adapter for a
    record, the registry asks each registered adapter whether it can handle
    the record (via `can_handle`). The first match wins.
    """

    def __init__(self) -> None:
        self._adapters: list[BaseAdapter] = []

    def register(self, adapter: BaseAdapter) -> None:
        """Register an adapter instance."""
        logger.info(
            "Registered adapter %s (v%s) for source type '%s'",
            adapter.adapter_id,
            adapter.version,
            adapter.source_type,
        )
        self._adapters.append(adapter)

    def get_adapter(
        self, metadata: SourceMetadata, record: dict[str, Any]
    ) -> BaseAdapter | None:
        """Find the first adapter that can handle the given record.

        Returns None if no adapter matches.
        """
        for adapter in self._adapters:
            if adapter.can_handle(metadata, record):
                return adapter
        return None

    @property
    def registered_adapters(self) -> list[BaseAdapter]:
        """List all registered adapters."""
        return list(self._adapters)
