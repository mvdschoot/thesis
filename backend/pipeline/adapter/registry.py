from __future__ import annotations

import logging
from typing import Any

from domain.models import SourceMetadata

from .base import BaseAdapter
from .diagnostics import SkippedReason, top_level_keys

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

    def explain_no_match(
        self,
        metadata: SourceMetadata,
        record: dict[str, Any],
        record_index: int,
    ) -> list[SkippedReason]:
        """Why did no adapter match this record? One reason per registered
        adapter, naming the first failing match clause (or noting that no
        adapters are registered at all).

        Used by `adapter.run` to populate `AdapterDiagnostics.predicate_failures`
        when `get_adapter` returns None.
        """
        if not self._adapters:
            return [
                SkippedReason(
                    code="no_adapter_registered",
                    record_index=record_index,
                    detail="No adapter is registered; transform() will produce 0 events.",
                    record_keys=top_level_keys(record),
                )
            ]

        reasons: list[SkippedReason] = []
        for adapter in self._adapters:
            explain = getattr(adapter, "explain_no_match", None)
            if callable(explain):
                reason = explain(metadata, record, record_index)
                if reason is not None:
                    reasons.append(reason)
            else:
                reasons.append(
                    SkippedReason(
                        code="predicate_mismatch",
                        rule_id=None,
                        record_index=record_index,
                        detail=(
                            f"Adapter '{adapter.adapter_id}' rejected the record; "
                            "no per-clause detail available."
                        ),
                        record_keys=top_level_keys(record),
                    )
                )
        return reasons

    @property
    def registered_adapters(self) -> list[BaseAdapter]:
        """List all registered adapters."""
        return list(self._adapters)
