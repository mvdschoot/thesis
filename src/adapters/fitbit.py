from __future__ import annotations

from typing import Any

from ..connectors.base import SourceMetadata
from ..models.canonical import (
    CanonicalEvent,
    Component,
    Context,
    EventType,
    Granularity,
    Mapping,
    Modality,
    Payload,
    Provenance,
    Quality,
    QualityFlag,
    Severity,
    Stage,
)
from .base import BaseAdapter

# Implicit units for Fitbit measurement categories
FITBIT_UNITS: dict[str, str] = {
    "steps": "count",
    "distance": "km",
    "calories": "kcal",
    "floors": "count",
    "elevation": "m",
    "heart-rate": "bpm",
    "heart-rate-zone": "min",
}


class FitbitAdapter(BaseAdapter):
    """Adapter for Fitbit Charge data.

    Handles measurement types: steps, distance, calories, floors, elevation,
    heart-rate-intraday, sleep-log, activity-summary.

    Each source record is decomposed into one or more canonical events
    (daily summary + intraday intervals).
    """

    @property
    def source_type(self) -> str:
        return "fitbit"

    @property
    def adapter_id(self) -> str:
        return "fitbit-v1"

    @property
    def version(self) -> str:
        return "1.0.0"

    def can_handle(self, metadata: SourceMetadata, record: dict[str, Any]) -> bool:
        return (
            metadata.source_name == "fitbit"
            and "measurementType" in record
            and "measurementValue" in record
        )

    def transform(
        self, metadata: SourceMetadata, record: dict[str, Any]
    ) -> list[CanonicalEvent]:
        measurement_type = record["measurementType"]
        dispatch = {
            "steps": self._transform_intraday_metric,
            "distance": self._transform_intraday_metric,
            "calories": self._transform_calories,
            "floors": self._transform_intraday_metric,
            "elevation": self._transform_intraday_metric,
            "heart-rate-intraday": self._transform_heart_rate,
            "sleep-log": self._transform_sleep,
            "activity-summary": self._transform_activity_summary,
        }

        handler = dispatch.get(measurement_type)
        if handler is None:
            return self._transform_unknown(metadata, record)

        return handler(metadata, record)

    # -- Shared helpers --

    def _make_context(
        self, metadata: SourceMetadata, measurement_type: str
    ) -> Context:
        return Context(
            source="fitbit",
            modality=Modality.WEARABLE,
            device=metadata.device,
            source_measurement_type=measurement_type,
        )

    def _make_provenance(
        self, record: dict[str, Any], group_id: str, parent_id: str | None = None
    ) -> Provenance:
        user_id = record["userId"]
        m_type = record["measurementType"]
        m_dt = record["measurementDateTime"]
        return Provenance(
            source_record_id=f"fitbit:{user_id}:{m_type}:{m_dt}",
            ingested_at=CanonicalEvent.now_iso(),
            group_id=group_id,
            parent_event_id=parent_id,
            adapter=self.adapter_id,
            adapter_version=self.version,
        )

    def _empty_mapping(self) -> Mapping:
        return Mapping()

    def _base_date(self, record: dict[str, Any]) -> str:
        """Extract the date portion from measurementDateTime (YYYY-MM-DD)."""
        return record["measurementDateTime"][:10]

    # -- Generic intraday metric (steps, distance, floors, elevation) --

    def _transform_intraday_metric(
        self, metadata: SourceMetadata, record: dict[str, Any]
    ) -> list[CanonicalEvent]:
        events: list[CanonicalEvent] = []
        m_type = record["measurementType"]
        mv = record["measurementValue"]
        base_date = self._base_date(record)
        group_id = CanonicalEvent.new_id()
        category = m_type  # "steps", "distance", etc.
        unit = FITBIT_UNITS.get(category)

        # Find the daily summary key (e.g., "activities-steps")
        summary_key = f"activities-{m_type}"
        intraday_key = f"{summary_key}-intraday"

        # Daily summary event
        summary_id = CanonicalEvent.new_id()
        daily_data = mv.get(summary_key, [])
        daily_value_raw = daily_data[0]["value"] if daily_data else None
        flags = []

        # Fitbit daily values come as strings -- coerce to number
        daily_value: float | int | None = None
        if daily_value_raw is not None:
            try:
                daily_value = (
                    int(daily_value_raw)
                    if "." not in str(daily_value_raw)
                    else float(daily_value_raw)
                )
                if str(daily_value_raw) != str(daily_value):
                    flags.append(
                        QualityFlag(
                            code="TYPE_COERCED",
                            severity=Severity.INFO,
                            stage="structured",
                            message=f"Coerced from string '{daily_value_raw}' to {daily_value}",
                        )
                    )
            except (ValueError, TypeError):
                daily_value = None

        events.append(
            CanonicalEvent(
                event_id=summary_id,
                subject_id=record["userId"],
                timestamp=f"{base_date}T00:00:00.000Z",
                timestamp_end=f"{base_date}T23:59:59.999Z",
                duration_seconds=86400,
                type=EventType.SUMMARY,
                category=category,
                granularity=Granularity.DAILY,
                payload=Payload(
                    value=daily_value,
                    raw_value=daily_value_raw,
                    unit=unit,
                    label=f"Daily {category.title()} Total",
                ),
                context=self._make_context(metadata, m_type),
                provenance=self._make_provenance(record, group_id),
                mapping=self._empty_mapping(),
                quality=Quality(flags=flags),
                stage=Stage.STRUCTURED,
            )
        )

        # Intraday interval events
        intraday = mv.get(intraday_key, {})
        dataset = intraday.get("dataset", [])
        interval = intraday.get("datasetInterval", 15)
        extensions = {
            "fitbit.datasetInterval": interval,
            "fitbit.datasetType": intraday.get("datasetType", "minute"),
        }

        for point in dataset:
            time_str = point["time"]
            val = point["value"]
            events.append(
                CanonicalEvent(
                    event_id=CanonicalEvent.new_id(),
                    subject_id=record["userId"],
                    timestamp=f"{base_date}T{time_str}Z",
                    timestamp_end=None,
                    duration_seconds=interval * 60,
                    type=EventType.MEASUREMENT,
                    category=category,
                    granularity=Granularity.INTERVAL,
                    payload=Payload(
                        value=val if isinstance(val, (int, float)) else None,
                        raw_value=val,
                        unit=unit,
                        label=f"Intraday {category.title()}",
                    ),
                    context=self._make_context(metadata, m_type),
                    provenance=self._make_provenance(record, group_id, summary_id),
                    mapping=self._empty_mapping(),
                    quality=Quality(),
                    stage=Stage.STRUCTURED,
                    extensions=extensions,
                )
            )

        return events

    # -- Calories (same as intraday metric but with mets/level components) --

    def _transform_calories(
        self, metadata: SourceMetadata, record: dict[str, Any]
    ) -> list[CanonicalEvent]:
        events: list[CanonicalEvent] = []
        mv = record["measurementValue"]
        base_date = self._base_date(record)
        group_id = CanonicalEvent.new_id()

        # Daily summary
        summary_id = CanonicalEvent.new_id()
        daily_data = mv.get("activities-calories", [])
        daily_value_raw = daily_data[0]["value"] if daily_data else None
        flags = []
        daily_value: int | float | None = None
        if daily_value_raw is not None:
            try:
                daily_value = (
                    int(daily_value_raw)
                    if "." not in str(daily_value_raw)
                    else float(daily_value_raw)
                )
                if str(daily_value_raw) != str(daily_value):
                    flags.append(
                        QualityFlag(
                            code="TYPE_COERCED",
                            severity=Severity.INFO,
                            stage="structured",
                            message=f"Coerced from string '{daily_value_raw}' to {daily_value}",
                        )
                    )
            except (ValueError, TypeError):
                daily_value = None

        events.append(
            CanonicalEvent(
                event_id=summary_id,
                subject_id=record["userId"],
                timestamp=f"{base_date}T00:00:00.000Z",
                timestamp_end=f"{base_date}T23:59:59.999Z",
                duration_seconds=86400,
                type=EventType.SUMMARY,
                category="calories",
                granularity=Granularity.DAILY,
                payload=Payload(
                    value=daily_value,
                    raw_value=daily_value_raw,
                    unit="kcal",
                    label="Daily Calories Total",
                ),
                context=self._make_context(metadata, "calories"),
                provenance=self._make_provenance(record, group_id),
                mapping=self._empty_mapping(),
                quality=Quality(flags=flags),
                stage=Stage.STRUCTURED,
            )
        )

        # Intraday with mets/level components
        intraday = mv.get("activities-calories-intraday", {})
        dataset = intraday.get("dataset", [])
        interval = intraday.get("datasetInterval", 15)
        extensions = {
            "fitbit.datasetInterval": interval,
            "fitbit.datasetType": intraday.get("datasetType", "minute"),
        }

        for point in dataset:
            components = []
            if "mets" in point:
                components.append(Component(name="mets", value=point["mets"]))
            if "level" in point:
                components.append(
                    Component(name="activity_level", value=point["level"])
                )

            events.append(
                CanonicalEvent(
                    event_id=CanonicalEvent.new_id(),
                    subject_id=record["userId"],
                    timestamp=f"{base_date}T{point['time']}Z",
                    duration_seconds=interval * 60,
                    type=EventType.MEASUREMENT,
                    category="calories",
                    granularity=Granularity.INTERVAL,
                    payload=Payload(
                        value=point["value"],
                        raw_value=point["value"],
                        unit="kcal",
                        label="Intraday Calories",
                        components=components if components else None,
                    ),
                    context=self._make_context(metadata, "calories"),
                    provenance=self._make_provenance(record, group_id, summary_id),
                    mapping=self._empty_mapping(),
                    quality=Quality(),
                    stage=Stage.STRUCTURED,
                    extensions=extensions,
                )
            )

        return events

    # -- Heart rate --

    def _transform_heart_rate(
        self, metadata: SourceMetadata, record: dict[str, Any]
    ) -> list[CanonicalEvent]:
        events: list[CanonicalEvent] = []
        mv = record["measurementValue"]
        base_date = self._base_date(record)
        group_id = CanonicalEvent.new_id()

        activities_heart = mv.get("activities-heart", [])
        heart_data = activities_heart[0] if activities_heart else {}
        heart_value = heart_data.get("value", {})

        # Daily resting heart rate summary
        summary_id = CanonicalEvent.new_id()
        resting_hr = heart_value.get("restingHeartRate")
        events.append(
            CanonicalEvent(
                event_id=summary_id,
                subject_id=record["userId"],
                timestamp=f"{base_date}T00:00:00.000Z",
                timestamp_end=f"{base_date}T23:59:59.999Z",
                duration_seconds=86400,
                type=EventType.SUMMARY,
                category="heart-rate",
                granularity=Granularity.DAILY,
                payload=Payload(
                    value=resting_hr,
                    raw_value=resting_hr,
                    unit="bpm",
                    label="Resting Heart Rate",
                ),
                context=self._make_context(metadata, "heart-rate-intraday"),
                provenance=self._make_provenance(record, group_id),
                mapping=self._empty_mapping(),
                quality=Quality(),
                stage=Stage.STRUCTURED,
            )
        )

        # Heart rate zones
        for zone in heart_value.get("heartRateZones", []):
            components = [
                Component(name="min", value=zone.get("min"), unit="bpm"),
                Component(name="max", value=zone.get("max"), unit="bpm"),
                Component(name="minutes", value=zone.get("minutes"), unit="min"),
                Component(
                    name="caloriesOut", value=zone.get("caloriesOut"), unit="kcal"
                ),
            ]
            events.append(
                CanonicalEvent(
                    event_id=CanonicalEvent.new_id(),
                    subject_id=record["userId"],
                    timestamp=f"{base_date}T00:00:00.000Z",
                    timestamp_end=f"{base_date}T23:59:59.999Z",
                    duration_seconds=86400,
                    type=EventType.SUMMARY,
                    category="heart-rate-zone",
                    granularity=Granularity.DAILY,
                    payload=Payload(
                        value=zone.get("minutes"),
                        raw_value=zone,
                        unit="min",
                        label=zone.get("name", "Unknown Zone"),
                        components=components,
                    ),
                    context=self._make_context(metadata, "heart-rate-intraday"),
                    provenance=self._make_provenance(record, group_id, summary_id),
                    mapping=self._empty_mapping(),
                    quality=Quality(),
                    stage=Stage.STRUCTURED,
                )
            )

        # Intraday heart rate readings
        intraday = mv.get("activities-heart-intraday", {})
        dataset = intraday.get("dataset", [])
        interval = intraday.get("datasetInterval", 15)

        for point in dataset:
            events.append(
                CanonicalEvent(
                    event_id=CanonicalEvent.new_id(),
                    subject_id=record["userId"],
                    timestamp=f"{base_date}T{point['time']}Z",
                    duration_seconds=interval * 60,
                    type=EventType.MEASUREMENT,
                    category="heart-rate",
                    granularity=Granularity.INTERVAL,
                    payload=Payload(
                        value=point["value"],
                        raw_value=point["value"],
                        unit="bpm",
                        label="Intraday Heart Rate",
                    ),
                    context=self._make_context(metadata, "heart-rate-intraday"),
                    provenance=self._make_provenance(record, group_id, summary_id),
                    mapping=self._empty_mapping(),
                    quality=Quality(),
                    stage=Stage.STRUCTURED,
                    extensions={
                        "fitbit.datasetInterval": interval,
                        "fitbit.datasetType": intraday.get("datasetType", "minute"),
                    },
                )
            )

        return events

    # -- Sleep --

    def _transform_sleep(
        self, metadata: SourceMetadata, record: dict[str, Any]
    ) -> list[CanonicalEvent]:
        events: list[CanonicalEvent] = []
        mv = record["measurementValue"]
        base_date = self._base_date(record)
        group_id = CanonicalEvent.new_id()

        # Daily sleep summary
        summary_id = CanonicalEvent.new_id()
        summary = mv.get("summary", {})
        components = []
        for key in ("totalTimeInBed", "totalMinutesAsleep", "totalSleepRecords"):
            if key in summary:
                components.append(
                    Component(name=key, value=summary[key], unit="min" if "Time" in key or "Minutes" in key else None)
                )
        stages = summary.get("stages", {})
        for stage_name, minutes in stages.items():
            components.append(
                Component(name=f"stage_{stage_name}", value=minutes, unit="min")
            )

        events.append(
            CanonicalEvent(
                event_id=summary_id,
                subject_id=record["userId"],
                timestamp=f"{base_date}T00:00:00.000Z",
                timestamp_end=f"{base_date}T23:59:59.999Z",
                duration_seconds=86400,
                type=EventType.SUMMARY,
                category="sleep",
                granularity=Granularity.DAILY,
                payload=Payload(
                    value=summary.get("totalMinutesAsleep"),
                    raw_value=summary,
                    unit="min",
                    label="Daily Sleep Summary",
                    components=components if components else None,
                ),
                context=self._make_context(metadata, "sleep-log"),
                provenance=self._make_provenance(record, group_id),
                mapping=self._empty_mapping(),
                quality=Quality(
                    flags=[
                        QualityFlag(
                            code="EMPTY_DATASET",
                            severity=Severity.WARNING,
                            stage="structured",
                            message="No sleep sessions recorded",
                        )
                    ]
                    if not mv.get("sleep")
                    else []
                ),
                stage=Stage.STRUCTURED,
            )
        )

        # Individual sleep sessions
        for session in mv.get("sleep", []):
            session_id = CanonicalEvent.new_id()
            session_components = []
            for key in (
                "minutesAsleep",
                "minutesAwake",
                "minutesToFallAsleep",
                "timeInBed",
            ):
                if key in session:
                    session_components.append(
                        Component(name=key, value=session[key], unit="min")
                    )

            start_time = session.get("startTime", f"{base_date}T00:00:00.000")
            end_time = session.get("endTime")
            duration_ms = session.get("duration")
            duration_s = duration_ms / 1000 if duration_ms else None

            events.append(
                CanonicalEvent(
                    event_id=session_id,
                    subject_id=record["userId"],
                    timestamp=start_time if "Z" in start_time else start_time + "Z",
                    timestamp_end=end_time + "Z" if end_time and "Z" not in end_time else end_time,
                    duration_seconds=duration_s,
                    type=EventType.SESSION,
                    category="sleep",
                    granularity=Granularity.SESSION,
                    payload=Payload(
                        value=session.get("efficiency"),
                        raw_value=session.get("efficiency"),
                        unit=None,
                        label="Sleep Session",
                        components=session_components if session_components else None,
                    ),
                    context=self._make_context(metadata, "sleep-log"),
                    provenance=self._make_provenance(record, group_id, summary_id),
                    mapping=self._empty_mapping(),
                    quality=Quality(
                        flags=[
                            QualityFlag(
                                code="TIMEZONE_AMBIGUOUS",
                                severity=Severity.WARNING,
                                stage="structured",
                                message="Sleep timestamps are local time without timezone info",
                            )
                        ]
                    ),
                    stage=Stage.STRUCTURED,
                    extensions={
                        "fitbit.logId": str(session.get("logId", "")),
                        "fitbit.isMainSleep": session.get("isMainSleep"),
                        "fitbit.type": session.get("type"),
                    },
                )
            )

            # Sleep stage transitions
            levels = session.get("levels", {})
            for level_entry in levels.get("data", []):
                events.append(
                    self._make_sleep_stage_event(
                        record, metadata, base_date, group_id, session_id, level_entry
                    )
                )
            for level_entry in levels.get("shortData", []):
                events.append(
                    self._make_sleep_stage_event(
                        record, metadata, base_date, group_id, session_id, level_entry
                    )
                )

        return events

    def _make_sleep_stage_event(
        self,
        record: dict[str, Any],
        metadata: SourceMetadata,
        base_date: str,
        group_id: str,
        session_id: str,
        level_entry: dict[str, Any],
    ) -> CanonicalEvent:
        dt = level_entry.get("dateTime", "")
        if dt and "Z" not in dt:
            dt = dt + "Z"
        return CanonicalEvent(
            event_id=CanonicalEvent.new_id(),
            subject_id=record["userId"],
            timestamp=dt,
            duration_seconds=level_entry.get("seconds"),
            type=EventType.OBSERVATION,
            category="sleep-stage",
            granularity=Granularity.INTERVAL,
            payload=Payload(
                value=level_entry.get("level"),
                raw_value=level_entry,
                unit=None,
                label=f"Sleep Stage: {level_entry.get('level', 'unknown')}",
            ),
            context=self._make_context(metadata, "sleep-log"),
            provenance=self._make_provenance(record, group_id, session_id),
            mapping=self._empty_mapping(),
            quality=Quality(),
            stage=Stage.STRUCTURED,
        )

    # -- Activity summary --

    def _transform_activity_summary(
        self, metadata: SourceMetadata, record: dict[str, Any]
    ) -> list[CanonicalEvent]:
        events: list[CanonicalEvent] = []
        mv = record["measurementValue"]
        base_date = self._base_date(record)
        group_id = CanonicalEvent.new_id()
        activity = mv.get("activity", {})

        # Activity summary
        summary_data = activity.get("summary", {})
        components = []
        for key, unit in [
            ("steps", "count"),
            ("caloriesOut", "kcal"),
            ("sedentaryMinutes", "min"),
            ("lightlyActiveMinutes", "min"),
            ("fairlyActiveMinutes", "min"),
            ("veryActiveMinutes", "min"),
            ("restingHeartRate", "bpm"),
        ]:
            if key in summary_data:
                components.append(
                    Component(name=key, value=summary_data[key], unit=unit)
                )

        summary_id = CanonicalEvent.new_id()
        events.append(
            CanonicalEvent(
                event_id=summary_id,
                subject_id=record["userId"],
                timestamp=f"{base_date}T00:00:00.000Z",
                timestamp_end=f"{base_date}T23:59:59.999Z",
                duration_seconds=86400,
                type=EventType.SUMMARY,
                category="activity-summary",
                granularity=Granularity.DAILY,
                payload=Payload(
                    value=None,
                    raw_value=summary_data,
                    unit=None,
                    label="Daily Activity Summary",
                    components=components if components else None,
                ),
                context=self._make_context(metadata, "activity-summary"),
                provenance=self._make_provenance(record, group_id),
                mapping=self._empty_mapping(),
                quality=Quality(),
                stage=Stage.STRUCTURED,
            )
        )

        # Goals
        goals = activity.get("goals", {})
        if goals:
            goal_components = [
                Component(name=k, value=v)
                for k, v in goals.items()
            ]
            events.append(
                CanonicalEvent(
                    event_id=CanonicalEvent.new_id(),
                    subject_id=record["userId"],
                    timestamp=f"{base_date}T00:00:00.000Z",
                    type=EventType.OBSERVATION,
                    category="activity-goals",
                    granularity=Granularity.DAILY,
                    payload=Payload(
                        value=None,
                        raw_value=goals,
                        unit=None,
                        label="Activity Goals",
                        components=goal_components,
                    ),
                    context=self._make_context(metadata, "activity-summary"),
                    provenance=self._make_provenance(record, group_id, summary_id),
                    mapping=self._empty_mapping(),
                    quality=Quality(),
                    stage=Stage.STRUCTURED,
                )
            )

        return events

    # -- Unknown measurement type fallback --

    def _transform_unknown(
        self, metadata: SourceMetadata, record: dict[str, Any]
    ) -> list[CanonicalEvent]:
        m_type = record["measurementType"]
        return [
            CanonicalEvent(
                event_id=CanonicalEvent.new_id(),
                subject_id=record["userId"],
                timestamp=record["measurementDateTime"],
                type=EventType.OBSERVATION,
                category=m_type,
                granularity=Granularity.UNKNOWN,
                payload=Payload(
                    value=None,
                    raw_value=record["measurementValue"],
                    unit=None,
                    label=f"Unknown Fitbit type: {m_type}",
                ),
                context=self._make_context(metadata, m_type),
                provenance=self._make_provenance(record, CanonicalEvent.new_id()),
                mapping=self._empty_mapping(),
                quality=Quality(
                    flags=[
                        QualityFlag(
                            code="UNKNOWN_TYPE",
                            severity=Severity.WARNING,
                            stage="structured",
                            message=f"No handler for measurement type '{m_type}'",
                        )
                    ]
                ),
                stage=Stage.STRUCTURED,
            )
        ]
