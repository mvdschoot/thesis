"""Deterministic UUID5 minting for FHIR Bundle references.

Centralizing every ``urn:uuid:`` we emit lets the final reference-integrity
pass walk the bundle and confirm every reference resolves to a ``fullUrl``
in the same bundle. The namespace is fixed; identical inputs produce
identical UUIDs across runs, which is what FHIR consumers expect for
PUT-based upserts.
"""
from __future__ import annotations

import uuid

# Stable namespace for harmonia-minted UUIDs. Generated once via uuid4 and
# pinned here forever — changing it invalidates every previously-emitted
# reference.
_NS = uuid.UUID("a3f1c4e8-7d61-4f2c-9a3b-3e8d5b1c0f10")


def subject_uuid(subject_id: str) -> str:
    return str(uuid.uuid5(_NS, f"subject:{subject_id}"))


def device_uuid(source: str, device: str) -> str:
    return str(uuid.uuid5(_NS, f"device:{source}|{device}"))


def observation_uuid(event_id: str) -> str:
    return str(uuid.uuid5(_NS, f"observation:{event_id}"))


def provenance_uuid(group_id: str) -> str:
    return str(uuid.uuid5(_NS, f"provenance:{group_id}"))


def questionnaire_uuid(category: str) -> str:
    return str(uuid.uuid5(_NS, f"questionnaire:{category}"))
