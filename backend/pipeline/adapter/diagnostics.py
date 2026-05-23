"""Adapter-stage diagnostics.

When an LLM-generated YAML config emits zero events for the input data, the
adapter would otherwise drop silently — paths resolve to None, iterate targets
turn out to be the wrong type, match predicates exclude the record. This module
records *why* the adapter ended up where it did, so the API can surface
per-rule diagnostics to the user without changing the event-emission contract.

Two failure surfaces are tracked:

1. **Predicate failures** — when `AdapterRegistry.get_adapter()` returns None,
   the registry reports which `match.record` clause excluded the record.
2. **Rule-execution skips** — inside `ConfigAdapter._execute_rule`, every
   silent skip (iterate path None, iterate target not a list, iterate_object
   source not a dict, condition unmet, …) appends a `SkippedReason`.

The collector is optional everywhere — adapter callers that don't pass one
behave exactly as before.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# Per-rule cap so a malformed config processing 10k records doesn't blow up the
# payload. The first few reasons are usually enough to diagnose.
MAX_REASONS_PER_RULE = 3
MAX_PREDICATE_FAILURES = 5


@dataclass
class SkippedReason:
    """One reason a record (or part of a record) failed to produce an event."""

    code: str
    """Stable identifier — see CODES below."""

    record_index: int
    """0-based index into the original record list."""

    detail: str
    """One-line human-readable description."""

    rule_id: str | None = None
    path: str | None = None
    """The YAML path that failed to resolve (or the discriminator field for
    predicate failures)."""

    expected: Any = None
    actual: Any = None
    """For predicate failures: what the match clause required vs. what the
    record actually had."""

    record_keys: list[str] | None = None
    """Top-level keys present in the record — orients the user when a path
    didn't resolve."""

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "record_index": self.record_index,
            "detail": self.detail,
            "rule_id": self.rule_id,
            "path": self.path,
            "expected": self.expected,
            "actual": self.actual,
            "record_keys": self.record_keys,
        }


@dataclass
class RuleDiagnostic:
    rule_id: str
    records_seen: int = 0
    events_emitted: int = 0
    skipped_reasons: list[SkippedReason] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "records_seen": self.records_seen,
            "events_emitted": self.events_emitted,
            "skipped_reasons": [r.to_dict() for r in self.skipped_reasons],
        }


@dataclass
class AdapterDiagnostics:
    records_total: int = 0
    records_matched: int = 0
    records_unmatched: int = 0
    events_emitted: int = 0
    rules: list[RuleDiagnostic] = field(default_factory=list)
    predicate_failures: list[SkippedReason] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "records_total": self.records_total,
            "records_matched": self.records_matched,
            "records_unmatched": self.records_unmatched,
            "events_emitted": self.events_emitted,
            "rules": [r.to_dict() for r in self.rules],
            "predicate_failures": [r.to_dict() for r in self.predicate_failures],
        }


class DiagnosticsCollector:
    """Accumulates diagnostics across the adapter run.

    Threaded through `adapter.run` and into `ConfigAdapter.transform`. The
    collector is record-aware (current record index) and rule-aware (current
    rule id is set by `start_rule` / `end_rule`).
    """

    def __init__(self) -> None:
        self._diag = AdapterDiagnostics()
        self._rules_by_id: dict[str, RuleDiagnostic] = {}
        self._current_record_index: int = -1
        self._current_rule_id: str | None = None

    # ── record scoping ─────────────────────────────────────────────────────

    def start_record(self, index: int) -> None:
        self._current_record_index = index
        self._diag.records_total = max(self._diag.records_total, index + 1)

    def record_matched(self) -> None:
        self._diag.records_matched += 1

    def record_unmatched(self, reasons: list[SkippedReason]) -> None:
        self._diag.records_unmatched += 1
        remaining = MAX_PREDICATE_FAILURES - len(self._diag.predicate_failures)
        if remaining > 0:
            self._diag.predicate_failures.extend(reasons[:remaining])

    # ── rule scoping ───────────────────────────────────────────────────────

    def start_rule(self, rule_id: str) -> None:
        self._current_rule_id = rule_id
        rd = self._rules_by_id.get(rule_id)
        if rd is None:
            rd = RuleDiagnostic(rule_id=rule_id)
            self._rules_by_id[rule_id] = rd
            self._diag.rules.append(rd)
        rd.records_seen += 1

    def end_rule(self, rule_id: str, events_emitted: int) -> None:
        rd = self._rules_by_id.get(rule_id)
        if rd is not None:
            rd.events_emitted += events_emitted
        self._current_rule_id = None

    # ── skip recording ─────────────────────────────────────────────────────

    def record_skip(
        self,
        code: str,
        detail: str,
        *,
        path: str | None = None,
        record_keys: list[str] | None = None,
        expected: Any = None,
        actual: Any = None,
    ) -> None:
        rule_id = self._current_rule_id
        if rule_id is None:
            return
        rd = self._rules_by_id.get(rule_id)
        if rd is None:
            return
        if len(rd.skipped_reasons) >= MAX_REASONS_PER_RULE:
            return
        rd.skipped_reasons.append(
            SkippedReason(
                code=code,
                rule_id=rule_id,
                record_index=self._current_record_index,
                path=path,
                detail=detail,
                expected=expected,
                actual=actual,
                record_keys=record_keys,
            )
        )

    # ── finalize ───────────────────────────────────────────────────────────

    def finalize(self, events_emitted: int) -> AdapterDiagnostics:
        self._diag.events_emitted = events_emitted
        return self._diag


def top_level_keys(record: Any) -> list[str] | None:
    """Best-effort listing of a record's top-level keys for the user. Returns
    None for non-dict records (lets the UI render a generic message)."""
    if isinstance(record, dict):
        return list(record.keys())
    return None
