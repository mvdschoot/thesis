"""FHIR R4 Bundle builder.

Each ``CodeableConcept`` carries ``text`` plus, when a user has bound a
concept in the MAPPED stage, a ``coding[]`` array. Bindings live on
``event.mapping`` (headline ``Observation.code``) or
``event.extensions["_concept_codings"]`` (unit / component / category).
The builder never strips ``text`` — it stays as the human-readable fallback.

Resource-type mapping by ``event.type``:

* ``measurement`` / ``observation`` / ``event`` / ``session`` / ``summary``
  → :class:`Observation`
* ``survey`` → :class:`QuestionnaireResponse` (added in a later step)
"""
from __future__ import annotations

from typing import Any

from domain.models import CanonicalEvent, Component, EventType

from .config import FhirConfig
from .refs import device_uuid, observation_uuid, provenance_uuid, questionnaire_uuid, subject_uuid


# Coarse mapping from canonical category → FHIR Observation.category.text.
# The FHIR R4 spec accepts text-only CodeableConcepts; codings (vital-signs
# value set, US Core profiles, etc.) are bound by the future MAPPED stage.
_VITAL_SIGN_CATEGORIES: frozenset[str] = frozenset({
    "weight", "height", "body-mass-index", "bmi",
    "heart-rate", "blood-pressure",
    "respiratory-rate", "body-temperature",
    "oxygen-saturation", "spo2",
})

_ACTIVITY_CATEGORIES: frozenset[str] = frozenset({
    "steps", "distance", "calories", "intensity",
    "active-minutes", "exercise", "workout", "session",
    "sleep", "sleep-stage",
})

# LOINC codes the R4 base spec ties to the vital-signs profile family; any
# Observation bearing one MUST carry a category coding of `vital-signs`.
_VITAL_SIGN_LOINC: frozenset[str] = frozenset({
    "85353-1",  # vital signs panel
    "9279-1",   # respiratory rate
    "8867-4",   # heart rate
    "2708-6", "59408-5",  # oxygen saturation
    "8310-5",   # body temperature
    "8302-2",   # body height
    "8306-3",   # body height lying
    "8287-5",   # head circumference
    "29463-7",  # body weight
    "39156-5",  # BMI
    "85354-9",  # blood pressure panel
    "8480-6",   # systolic BP
    "8462-4",   # diastolic BP
})
_OBS_CATEGORY_SYSTEM = "http://terminology.hl7.org/CodeSystem/observation-category"
_QUALITY_FLAG_URL = "https://harmonia.thesis/fhir/StructureDefinition/quality-flag"


def _has_value(value: Any) -> bool:
    """True when a payload value is present (not None / not blank string)."""
    return value is not None and not (isinstance(value, str) and not value.strip())


def _flag_texts(event: CanonicalEvent) -> list[str]:
    """Render quality flags as ``[severity/code] message`` text lines."""
    return [
        f"[{f.severity.value}/{f.code}] {f.message or ''}".strip()
        for f in event.quality.flags
    ]


def _category_text_for_event(event: CanonicalEvent) -> str:
    """Pick a coarse FHIR Observation.category text bucket."""
    if event.type == EventType.SURVEY:
        return "survey"
    if event.type == EventType.OBSERVATION:
        return "exam"
    if event.type in (EventType.EVENT, EventType.SESSION):
        return "activity"
    cat = event.category.lower() if event.category else ""
    if cat in _VITAL_SIGN_CATEGORIES:
        return "vital-signs"
    if cat in _ACTIVITY_CATEGORIES:
        return "activity"
    return "exam"


def _status_for_event(event: CanonicalEvent) -> str:
    """Map plausibility to FHIR Observation.status.

    plausibility=exclude → entered-in-error
    plausibility=review  → amended
    everything else      → final
    """
    p = event.quality.plausibility
    if p == "exclude":
        return "entered-in-error"
    if p == "review":
        return "amended"
    return "final"


def _effective(event: CanonicalEvent) -> dict[str, Any]:
    """Build the FHIR ``effective[x]`` slice from event timestamps.

    Returns ``effectivePeriod`` if the event has both start and end,
    otherwise ``effectiveDateTime``. Empty timestamps are omitted (the
    validator should already have caught that earlier).
    """
    start = event.timestamp or None
    end = event.timestamp_end or None
    if start and end:
        return {"effectivePeriod": {"start": start, "end": end}}
    if start:
        return {"effectiveDateTime": start}
    if end:
        return {"effectiveDateTime": end}
    return {}


def _value_block(
    value: Any,
    unit: str | None,
    unit_coding: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Render a payload value as the appropriate FHIR ``value[x]`` slice.

    Numeric → ``valueQuantity`` with UCUM ``system``/``code`` when the MAPPED
    stage has bound a unit. Boolean → ``valueBoolean``. Anything else, when
    present, falls through to ``valueString``. A None / blank-string value
    yields no element (an empty ``value[x]`` would violate FHIR ele-1).
    """
    if not _has_value(value):
        return {}
    if isinstance(value, bool):
        return {"valueBoolean": value}
    if isinstance(value, (int, float)):
        q: dict[str, Any] = {"value": value}
        if unit:
            q["unit"] = unit
        if unit_coding:
            sys_ = unit_coding.get("system")
            code = unit_coding.get("code")
            if sys_:
                q["system"] = sys_
            if code:
                q["code"] = code
        return {"valueQuantity": q}
    return {"valueString": str(value)}


def _coding_from_mapping(mapping: Any) -> dict[str, str] | None:
    """Build one FHIR Coding from a ``CanonicalEvent.mapping`` if populated."""
    if not mapping or not mapping.standard_code or not mapping.standard_system:
        return None
    c: dict[str, str] = {
        "system": mapping.standard_system,
        "code": mapping.standard_code,
    }
    if mapping.standard_display:
        c["display"] = mapping.standard_display
    return c


def _coding_from_dict(d: dict[str, str] | None) -> dict[str, str] | None:
    """Normalise a ``{system, code, display}`` dict into a FHIR Coding."""
    if not d:
        return None
    sys_ = d.get("system")
    code = d.get("code")
    if not sys_ or not code:
        return None
    out: dict[str, str] = {"system": sys_, "code": code}
    disp = d.get("display")
    if disp:
        out["display"] = disp
    return out


def _concept_codings(event: CanonicalEvent) -> dict[str, Any]:
    """Read the private ``_concept_codings`` extension. Empty dict when unset."""
    if not event.extensions:
        return {}
    bag = event.extensions.get("_concept_codings")
    return bag if isinstance(bag, dict) else {}


def _questionnaire_item_type(value: Any) -> str:
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "decimal"
    return "string"


def _build_questionnaire(
    category: str,
    components: list[Component],
) -> dict[str, Any]:
    q_id = questionnaire_uuid(category)
    items: list[dict[str, Any]] = []
    seen_link_ids: set[str] = set()
    for c in components:
        if c.name in seen_link_ids:
            continue
        seen_link_ids.add(c.name)
        items.append({
            "linkId": c.name,
            "text": c.name,
            "type": _questionnaire_item_type(c.value),
        })
    return {
        "resourceType": "Questionnaire",
        "id": q_id,
        "status": "active",
        "title": category,
        "item": items,
    }


def _build_patient(subject_id: str) -> dict[str, Any]:
    """Synthesized Patient — id and identifier only, no PII fields."""
    patient_id = subject_uuid(subject_id)
    return {
        "resourceType": "Patient",
        "id": patient_id,
        "identifier": [
            {
                "system": "urn:harmonia:subject",
                "value": subject_id,
            }
        ],
    }


def _build_device(source: str, device: str) -> dict[str, Any]:
    """Synthesized Device — manufacturer = source, deviceName.text = device."""
    dev_id = device_uuid(source, device)
    return {
        "resourceType": "Device",
        "id": dev_id,
        "identifier": [
            {
                "system": "urn:harmonia:device",
                "value": f"{source}|{device}",
            }
        ],
        "manufacturer": source,
        "deviceName": [{"name": device, "type": "user-friendly-name"}],
    }


def _build_provenance(
    *,
    target_full_urls: list[str],
    adapter_id: str,
    adapter_version: str,
    recorded_at: str,
) -> dict[str, Any]:
    """One Provenance resource pointing at every observation in the bundle."""
    prov_seed = f"{adapter_id}|{adapter_version}|{recorded_at}"
    return {
        "resourceType": "Provenance",
        "id": provenance_uuid(prov_seed),
        "recorded": recorded_at,
        "target": [{"reference": ref} for ref in target_full_urls],
        "agent": [
            {
                "type": {"text": "assembler"},
                "who": {
                    "display": f"harmonia adapter {adapter_id}@{adapter_version}",
                },
            }
        ],
    }


def _build_observation(
    event: CanonicalEvent,
    *,
    patient_uuid: str,
    device_uuid_value: str | None = None,
) -> dict[str, Any]:
    codings = _concept_codings(event)

    cat_text = _category_text_for_event(event)
    category_cc: dict[str, Any] = {"text": cat_text}
    cat_coding = _coding_from_dict(codings.get("category"))
    if cat_coding:
        category_cc["coding"] = [cat_coding]

    # Any Observation coded with a vital-sign LOINC must carry the `vital-signs`
    # category slice required by the R4 base profile (open slicing — the coarse
    # category above stays). Keyed on the bound LOINC code, not the canonical
    # category string, since the spec triggers on the code.
    categories: list[dict[str, Any]] = [category_cc]
    m = event.mapping
    if (m and m.standard_code in _VITAL_SIGN_LOINC
            and m.standard_system and "loinc" in m.standard_system.lower()):
        categories.append({
            "coding": [{
                "system": _OBS_CATEGORY_SYSTEM,
                "code": "vital-signs",
                "display": "Vital Signs",
            }],
        })

    code_cc: dict[str, Any] = {"text": event.payload.label or event.category}
    code_coding = _coding_from_mapping(event.mapping)
    if code_coding:
        code_cc["coding"] = [code_coding]

    obs: dict[str, Any] = {
        "resourceType": "Observation",
        "id": event.event_id,
        "status": _status_for_event(event),
        "category": categories,
        "code": code_cc,
        "subject": {"reference": f"urn:uuid:{patient_uuid}"},
    }
    obs.update(_effective(event))

    if event.payload.value is not None:
        obs.update(_value_block(
            event.payload.value,
            event.payload.unit,
            unit_coding=_coding_from_dict(codings.get("unit")),
        ))

    if event.payload.components:
        component_codings = codings.get("component") or {}
        component_unit_codings = codings.get("component_unit") or {}
        comp_list: list[dict[str, Any]] = []
        for c in event.payload.components:
            comp_code: dict[str, Any] = {"text": c.name}
            cc = _coding_from_dict(component_codings.get(c.name))
            if cc:
                comp_code["coding"] = [cc]
            comp_list.append({
                "code": comp_code,
                **_value_block(
                    c.value,
                    c.unit,
                    unit_coding=_coding_from_dict(component_unit_codings.get(c.name)),
                ),
            })
        obs["component"] = comp_list

    if event.quality.flags:
        obs["note"] = [{"text": t} for t in _flag_texts(event)]

    if device_uuid_value:
        obs["device"] = {"reference": f"urn:uuid:{device_uuid_value}"}

    if event.type == EventType.SUMMARY and event.provenance.parent_event_id:
        obs["derivedFrom"] = [
            {"reference": f"urn:uuid:{observation_uuid(event.provenance.parent_event_id)}"}
        ]

    return obs


def _build_questionnaire_response(
    event: CanonicalEvent,
    *,
    patient_uuid: str,
    questionnaire_ref: str | None = None,
) -> dict[str, Any]:
    """Build a QuestionnaireResponse from a survey event.

    Each ``payload.components[]`` entry becomes one ``item[]`` linkId/answer
    pair; if the event has no components, a single item is built from
    ``payload.value``.
    """
    qr: dict[str, Any] = {
        "resourceType": "QuestionnaireResponse",
        "id": event.event_id,
        "status": _qr_status_for_event(event),
        "subject": {"reference": f"urn:uuid:{patient_uuid}"},
    }
    if questionnaire_ref:
        qr["questionnaire"] = questionnaire_ref
    if event.timestamp:
        qr["authored"] = event.timestamp

    codings = _concept_codings(event)
    items: list[dict[str, Any]] = []
    if event.payload.components:
        component_unit_codings = codings.get("component_unit") or {}
        for c in event.payload.components:
            item: dict[str, Any] = {"linkId": c.name, "text": c.name}
            # An answer with no value[x] would violate ele-1; emit a value-less
            # item (linkId/text only, valid in R4) when the value is blank.
            if _has_value(c.value):
                item["answer"] = [_qr_answer(
                    c.value,
                    c.unit,
                    unit_coding=_coding_from_dict(component_unit_codings.get(c.name)),
                )]
            items.append(item)
    elif _has_value(event.payload.value):
        items.append({
            "linkId": event.payload.label or event.category,
            "text": event.payload.label or event.category,
            "answer": [_qr_answer(
                event.payload.value,
                event.payload.unit,
                unit_coding=_coding_from_dict(codings.get("unit")),
            )],
        })
    if items:
        qr["item"] = items

    # QuestionnaireResponse has no `note` element in R4; carry the quality/
    # provenance trail as a repeated DomainResource extension instead.
    if event.quality.flags:
        qr["extension"] = [
            {"url": _QUALITY_FLAG_URL, "valueString": t}
            for t in _flag_texts(event)
        ]
    return qr


def _qr_status_for_event(event: CanonicalEvent) -> str:
    """QuestionnaireResponse.status uses a different value set than Observation."""
    p = event.quality.plausibility
    if p == "exclude":
        return "entered-in-error"
    if p == "review":
        return "amended"
    return "completed"


def _qr_answer(
    value: Any,
    unit: str | None,
    unit_coding: dict[str, str] | None = None,
) -> dict[str, Any]:
    if not _has_value(value):
        return {}
    if isinstance(value, bool):
        return {"valueBoolean": value}
    if isinstance(value, (int, float)):
        q: dict[str, Any] = {"value": value}
        if unit:
            q["unit"] = unit
        if unit_coding:
            sys_ = unit_coding.get("system")
            code = unit_coding.get("code")
            if sys_:
                q["system"] = sys_
            if code:
                q["code"] = code
        return {"valueQuantity": q}
    return {"valueString": str(value)}


def _entry(full_url: str, resource: dict[str, Any], *, bundle_type: str) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "fullUrl": f"urn:uuid:{full_url}",
        "resource": resource,
    }
    if bundle_type == "transaction":
        method = "PUT" if resource["resourceType"] == "Patient" else "POST"
        url = (
            f"{resource['resourceType']}/{resource['id']}"
            if method == "PUT"
            else resource["resourceType"]
        )
        entry["request"] = {"method": method, "url": url}
    return entry


def _verify_references(bundle: dict[str, Any]) -> list[str]:
    """Walk the bundle and return any references that don't resolve to a
    ``fullUrl`` in the same bundle.

    Only checks ``urn:uuid:`` references — relative references (``Patient/123``)
    are valid in transaction bundles when resolved server-side and we don't
    re-implement that here.
    """
    full_urls: set[str] = {
        e.get("fullUrl") for e in bundle.get("entry", []) if e.get("fullUrl")
    }
    dangling: list[str] = []

    def _walk(node: Any) -> None:
        if isinstance(node, dict):
            ref = node.get("reference")
            if isinstance(ref, str) and ref.startswith("urn:uuid:") and ref not in full_urls:
                dangling.append(ref)
            for v in node.values():
                _walk(v)
        elif isinstance(node, list):
            for item in node:
                _walk(item)

    _walk(bundle)
    return dangling


def build_bundle(
    events: list[CanonicalEvent], *, config: FhirConfig
) -> dict[str, Any]:
    """Build a FHIR R4 Bundle from a list of qualified events."""
    entries: list[dict[str, Any]] = []
    include = set(config.include)
    obs_full_urls: list[str] = []  # populated when Provenance is included

    # Unique Patient resources (one per subject_id).
    seen_patients: set[str] = set()
    if "Patient" in include:
        for ev in events:
            sid = ev.subject_id or ""
            if not sid or sid in seen_patients:
                continue
            seen_patients.add(sid)
            patient = _build_patient(sid)
            entries.append(_entry(patient["id"], patient, bundle_type=config.bundle_type))

    # Unique Device resources (one per (source, device) pair) — emitted before
    # observations so device.reference inside an Observation always resolves.
    seen_devices: set[tuple[str, str]] = set()
    if "Device" in include:
        for ev in events:
            src = ev.context.source or ""
            dev = ev.context.device or ""
            if not src or not dev:
                continue
            key = (src, dev)
            if key in seen_devices:
                continue
            seen_devices.add(key)
            device = _build_device(src, dev)
            entries.append(_entry(device["id"], device, bundle_type=config.bundle_type))

    # Questionnaire definitions — one per unique survey category. Items come
    # from each survey event's components when present; otherwise the event is
    # itself one answered question (value + label), so we synthesize a single
    # item from its label/value. Without this fallback, per-item survey configs
    # (one event per question, no components) would emit zero Questionnaires.
    seen_questionnaires: dict[str, list[Component]] = {}
    if "Questionnaire" in include:
        for ev in events:
            if ev.type != EventType.SURVEY:
                continue
            if ev.payload.components:
                items = ev.payload.components
            elif ev.payload.value is not None:
                items = [Component(
                    name=ev.payload.label or ev.category,
                    value=ev.payload.value,
                    unit=ev.payload.unit,
                )]
            else:
                continue
            seen_questionnaires.setdefault(ev.category, []).extend(items)
        for cat, components in seen_questionnaires.items():
            q = _build_questionnaire(cat, components)
            q_uuid = questionnaire_uuid(cat)
            entries.append(_entry(q_uuid, q, bundle_type=config.bundle_type))

    # Observations / QuestionnaireResponses — one resource per event.
    if "Observation" in include:
        for ev in events:
            patient_id = subject_uuid(ev.subject_id or "")
            dev_uuid = (
                device_uuid(ev.context.source, ev.context.device)
                if "Device" in include and ev.context.source and ev.context.device
                else None
            )
            if ev.type in (
                EventType.MEASUREMENT,
                EventType.OBSERVATION,
                EventType.EVENT,
                EventType.SESSION,
                EventType.SUMMARY,
            ):
                obs = _build_observation(
                    ev, patient_uuid=patient_id, device_uuid_value=dev_uuid
                )
                obs_uuid = observation_uuid(ev.event_id)
                entries.append(_entry(obs_uuid, obs, bundle_type=config.bundle_type))
                obs_full_urls.append(f"urn:uuid:{obs_uuid}")
            elif ev.type == EventType.SURVEY:
                q_ref = (
                    f"urn:uuid:{questionnaire_uuid(ev.category)}"
                    if ev.category in seen_questionnaires
                    else None
                )
                qr = _build_questionnaire_response(
                    ev, patient_uuid=patient_id, questionnaire_ref=q_ref,
                )
                qr_uuid = observation_uuid(ev.event_id)
                entries.append(_entry(qr_uuid, qr, bundle_type=config.bundle_type))
                obs_full_urls.append(f"urn:uuid:{qr_uuid}")

    # Single Provenance resource pointing at every observation we emitted.
    if "Provenance" in include and obs_full_urls:
        # Pick the first event with adapter info; fall back to "harmonia"/"unknown".
        first = next(
            (e for e in events if e.provenance.adapter), events[0] if events else None
        )
        adapter_id = first.provenance.adapter if first and first.provenance.adapter else "harmonia"
        adapter_version = (
            first.provenance.adapter_version
            if first and first.provenance.adapter_version
            else "unknown"
        )
        recorded_at = (
            first.provenance.ingested_at
            if first and first.provenance.ingested_at
            else CanonicalEvent.now_iso()
        )
        prov = _build_provenance(
            target_full_urls=obs_full_urls,
            adapter_id=adapter_id,
            adapter_version=adapter_version,
            recorded_at=recorded_at,
        )
        entries.append(_entry(prov["id"], prov, bundle_type=config.bundle_type))

    bundle = {
        "resourceType": "Bundle",
        "type": config.bundle_type,
        "entry": entries,
    }
    bundle["__dangling_refs"] = _verify_references(bundle)
    return bundle
