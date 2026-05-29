"""OMOP CDM v5.4 table dataclasses.

Minimal subset covering the tables relevant for patient-generated
health data (wearables, scales, surveys, games).  Each dataclass
mirrors the required + key optional columns from the CDM spec.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass
class OmopPerson:
    person_id: int
    person_source_value: str
    gender_concept_id: int = 0
    year_of_birth: int = 0
    race_concept_id: int = 0
    ethnicity_concept_id: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class OmopMeasurement:
    measurement_id: int
    person_id: int
    measurement_concept_id: int
    measurement_date: str
    measurement_datetime: str | None = None
    measurement_type_concept_id: int = 0
    value_as_number: float | None = None
    value_as_concept_id: int = 0
    unit_concept_id: int = 0
    unit_source_value: str | None = None
    measurement_source_value: str | None = None
    measurement_source_concept_id: int = 0
    provider_id: int | None = None
    visit_occurrence_id: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class OmopObservation:
    observation_id: int
    person_id: int
    observation_concept_id: int
    observation_date: str
    observation_datetime: str | None = None
    observation_type_concept_id: int = 0
    value_as_number: float | None = None
    value_as_string: str | None = None
    value_as_concept_id: int = 0
    unit_concept_id: int = 0
    unit_source_value: str | None = None
    observation_source_value: str | None = None
    observation_source_concept_id: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class OmopDeviceExposure:
    device_exposure_id: int
    person_id: int
    device_concept_id: int = 0
    device_exposure_start_date: str = ""
    device_exposure_end_date: str = ""
    device_type_concept_id: int = 0
    device_source_value: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class OmopObservationPeriod:
    observation_period_id: int
    person_id: int
    observation_period_start_date: str
    observation_period_end_date: str
    period_type_concept_id: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class OmopConcept:
    """A custom ("2-billionaire") CONCEPT row for a source code with no
    standard OMOP mapping.  Per OHDSI guidance custom concepts use
    concept_id > 2,000,000,000, are always non-standard, and are referenced
    only from ``*_source_concept_id`` columns.
    """
    concept_id: int
    concept_name: str
    domain_id: str
    vocabulary_id: str
    concept_code: str
    concept_class_id: str = "Undefined"
    standard_concept: str | None = None
    valid_start_date: str = "1970-01-01"
    valid_end_date: str = "2099-12-31"
    invalid_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
