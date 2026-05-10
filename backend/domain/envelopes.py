"""Per-topic message envelope shapes (JSON-over-Kafka).

Each stage consumes envelopes from one topic and produces to the next.
`request_id` is the Kafka key; the rest is the message body.
"""
from __future__ import annotations

from typing import Any, Literal, NotRequired, TypedDict


# Topic names — single source of truth.
TOPIC_REQUESTS = "transform-requests"
TOPIC_CONNECTOR_OUT = "connector-out"
TOPIC_ADAPTER_OUT = "adapter-out"
TOPIC_CLEANER_OUT = "cleaner-out"
TOPIC_VALIDATOR_OUT = "validator-out"
TOPIC_RESULTS = "transform-results"

# Consumer-group ids per service (multiple replicas of the same service share).
GROUP_CONNECTOR = "harmonia-connector"
GROUP_ADAPTER = "harmonia-adapter"
GROUP_CLEANER = "harmonia-cleaner"
GROUP_VALIDATOR = "harmonia-validator"
GROUP_QUALIFIER = "harmonia-qualifier"
GROUP_GATEWAY = "harmonia-gateway"


class MetadataEnv(TypedDict):
    source_name: str
    format: Literal["json", "csv"]
    device: str | None
    modality: NotRequired[str]


class ErrorEnv(TypedDict):
    stage: str
    message: str


class TransformRequestEnv(TypedDict):
    request_id: str
    yaml: str
    data: Any  # JSON object/array OR raw CSV text
    format: Literal["json", "csv"]
    source: str | None
    device: str | None


class ConnectorOutEnv(TypedDict):
    request_id: str
    yaml: str
    metadata: MetadataEnv
    records: list[dict[str, Any]]


class StageEventsEnv(TypedDict, total=False):
    """Generic events envelope used between adapter/cleaner/validator/qualifier."""

    request_id: str
    yaml: str
    metadata: MetadataEnv
    events: list[dict[str, Any]]
    stats: dict[str, Any]
    error: ErrorEnv
