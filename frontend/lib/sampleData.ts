// Module-level sample data for the prototype's first paint. Replaces the
// `window.SAMPLE_*` globals from the design's data.js. The Connector panel
// shows these as picker options; once the user runs the pipeline, real
// backend output supersedes the simulated events below.

import type { AdapterConfig, CanonicalEvent, QualityFlag, SampleDataset } from "./types";

export const SAMPLE_DATASETS: Record<string, SampleDataset> = {
  "fitbit-heart-rate": {
    label: "Fitbit · Heart Rate",
    source: "fitbit",
    file: "fitbit_2025-01-12.json",
    record: {
      userId: "u-08431",
      measurementType: "heart-rate-intraday",
      measurementDateTime: "2025-01-12T00:00:00.000Z",
      measurementValue: {
        "activities-heart": [
          {
            dateTime: "2025-01-12",
            value: {
              restingHeartRate: 62,
              heartRateZones: [
                { name: "Out of Range", min: 30, max: 99, minutes: 1124, caloriesOut: 1532.4 },
                { name: "Fat Burn", min: 99, max: 138, minutes: 248, caloriesOut: 1180.8 },
                { name: "Cardio", min: 138, max: 168, minutes: 51, caloriesOut: 412.0 },
                { name: "Peak", min: 168, max: 220, minutes: 17, caloriesOut: 184.6 },
              ],
            },
          },
        ],
        "activities-heart-intraday": {
          dataset: [
            { time: "06:00:00", value: 58 },
            { time: "06:01:00", value: 60 },
            { time: "06:02:00", value: 61 },
            { time: "06:03:00", value: 63 },
            { time: "06:04:00", value: 244 },
            { time: "06:05:00", value: 64 },
          ],
          datasetInterval: 1,
          datasetType: "minute",
        },
      },
    },
  },
  "withings-body-scale": {
    label: "Withings · Body Scale",
    source: "withings",
    file: "withings_2025-01-12.json",
    record: {
      userId: "u-08431",
      measurementDateTime: "2025-01-12T07:14:22.000Z",
      measurementValue: 74.6,
      measurementType: { typeValue: 1, typeDescription: "Weight" },
      attrib: 0,
      createdDateTime: "2025-01-12T07:14:25.000Z",
    },
  },
  "linguistic-games": {
    label: "Linguistic Games",
    source: "linguistic-games",
    file: "linguistic_games_results.json",
    record: {
      username: "u-08431",
      email: "anon@example.org",
      results: [
        { game: "word-recall", level: 1, score: 82, avg_score: 78, avg_errors: 2, times_played: 14, state: "stable" },
        { game: "word-recall", level: 2, score: 64, avg_score: 60, avg_errors: 4, times_played: 9, state: "improving" },
        { game: "anagram", level: 1, score: 90, avg_score: 88, avg_errors: 1, times_played: 22, state: "-" },
      ],
    },
  },
};

// Editor-shape sample configs used as a fallback when the backend list is
// empty or unreachable. Mirrors lib/types.ts MatchPredicate `{op, value}`.
export const SAMPLE_CONFIGS: Record<string, AdapterConfig> = {
  "fitbit-heart-rate-v1": {
    adapter: {
      id: "fitbit-heart-rate-v1",
      version: "1.0.0",
      description: "Fitbit heart rate intraday and daily summary",
    },
    match: {
      source: "fitbit",
      record: [
        { field: "measurementType", op: "equals", value: "heart-rate-intraday" },
        { field: "userId", op: "exists", value: true },
        { field: "measurementDateTime", op: "exists", value: true },
        { field: "measurementValue.activities-heart[0].value", op: "type", value: "object" },
        { field: "measurementValue.activities-heart-intraday.dataset", op: "type", value: "array" },
      ],
    },
    defaults: {
      subject_id: { path: "userId" },
      context: {
        source: "fitbit",
        modality: "wearable",
        device: null,
        source_measurement_type: { path: "measurementType" },
      },
      stage: "structured",
    },
    emit: [
      {
        id: "daily-resting-hr",
        description: "Daily resting heart rate",
        type: "summary",
        category: "heart-rate",
        granularity: "daily",
        timestamp: {
          start: { path: "measurementDateTime", transform: "start_of_day" },
          end: { path: "measurementDateTime", transform: "end_of_day" },
          duration_seconds: 86400,
        },
        payload: {
          value: { path: "measurementValue.activities-heart[0].value.restingHeartRate" },
          raw_value: { path: "measurementValue.activities-heart[0].value.restingHeartRate" },
          unit: "bpm",
          label: "Resting Heart Rate",
          components: [],
        },
        quality: { flags: [] },
      },
      {
        id: "hr-zones",
        description: "Heart rate zone breakdown",
        type: "summary",
        category: "heart-rate-zone",
        granularity: "daily",
        parent: "daily-resting-hr",
        iterate: "measurementValue.activities-heart[0].value.heartRateZones",
        timestamp: {
          start: { path: "measurementDateTime", transform: "start_of_day" },
          end: { path: "measurementDateTime", transform: "end_of_day" },
          duration_seconds: 86400,
        },
        payload: {
          value: { path: "@item.minutes" },
          raw_value: { path: "@item" },
          unit: "min",
          label: { path: "@item.name" },
          components: [
            { name: "min", value: { path: "@item.min" }, unit: "bpm" },
            { name: "max", value: { path: "@item.max" }, unit: "bpm" },
            { name: "minutes", value: { path: "@item.minutes" }, unit: "min" },
            { name: "caloriesOut", value: { path: "@item.caloriesOut" }, unit: "kcal" },
          ],
        },
        quality: { flags: [] },
      },
      {
        id: "hr-intraday",
        description: "Per-interval heart rate measurements",
        type: "measurement",
        category: "heart-rate",
        granularity: "interval",
        parent: "daily-resting-hr",
        iterate: "measurementValue.activities-heart-intraday.dataset",
        timestamp: {
          start: { date_from: { path: "measurementDateTime" }, time_from: { path: "@item.time" } },
          duration_seconds: {
            multiply: [
              { path: "measurementValue.activities-heart-intraday.datasetInterval" },
              60,
            ],
          },
        },
        payload: {
          value: { path: "@item.value" },
          raw_value: { path: "@item.value" },
          unit: "bpm",
          label: "Heart Rate",
          components: [],
        },
        quality: { flags: [] },
      },
    ],
    clean: {
      heuristics: [
        "whitespace",
        "timestamp_normalizer",
        "type_coercer",
        "unit_inferrer",
      ],
    },
    validate: {
      enabled: ["required_fields", "timestamp_window", "payload_shape", "unit_whitelist", "range"],
    },
    qualify: {
      enabled: ["completeness", "duplicates", "outliers", "conformance", "plausibility"],
      outliers: { hampel_k: 3.5, min_group_size: 5 },
      duplicates: {
        fields: ["subject_id", "category", "timestamp", "payload.value"],
        value_round_digits: 3,
      },
      plausibility: { warning_count_for_review: 1 },
    },
  },
};

// A representative event stream used to populate the Results panel before
// the user has run the real pipeline.
export const SIMULATED_EVENTS: CanonicalEvent[] = [
  {
    event_id: "ev-01",
    subject_id: "u-08431",
    timestamp: "2025-01-12T00:00:00.000Z",
    timestamp_end: "2025-01-12T23:59:59.999Z",
    duration_seconds: 86400,
    type: "summary",
    category: "heart-rate",
    granularity: "daily",
    payload: { value: 62, raw_value: 62, unit: "bpm", label: "Resting Heart Rate", components: null },
    context: { source: "fitbit", modality: "wearable", device: null, source_measurement_type: "heart-rate-intraday" },
    provenance: {
      source_record_id: null,
      ingested_at: "2026-04-27T10:00:00.000Z",
      group_id: null,
      parent_event_id: null,
      adapter: "fitbit-heart-rate-v1",
      adapter_version: "1.0.0",
    },
    mapping: {
      standard_code: null,
      standard_system: null,
      standard_display: null,
      confidence: null,
      method: null,
    },
    quality: {
      flags: [],
      conformance: "ok",
      completeness: 1.0,
      plausibility: "ok",
      expected_field_count: 4,
      present_field_count: 4,
    },
    stage: "qualified",
    extensions: null,
    emit_id: "daily-resting-hr",
  },
  ...["Out of Range", "Fat Burn", "Cardio", "Peak"].map((zone, i): CanonicalEvent => {
    const minutes = [1124, 248, 51, 17][i];
    const cals = [1532.4, 1180.8, 412.0, 184.6][i];
    const ranges: Array<[number, number]> = [
      [30, 99],
      [99, 138],
      [138, 168],
      [168, 220],
    ];
    return {
      event_id: `ev-zone-${i}`,
      subject_id: "u-08431",
      timestamp: "2025-01-12T00:00:00.000Z",
      timestamp_end: "2025-01-12T23:59:59.999Z",
      duration_seconds: 86400,
      type: "summary",
      category: "heart-rate-zone",
      granularity: "daily",
      payload: {
        value: minutes,
        raw_value: { name: zone, min: ranges[i][0], max: ranges[i][1], minutes, caloriesOut: cals },
        unit: "min",
        label: zone,
        components: [
          { name: "min", value: ranges[i][0], unit: "bpm" },
          { name: "max", value: ranges[i][1], unit: "bpm" },
          { name: "minutes", value: minutes, unit: "min" },
          { name: "caloriesOut", value: cals, unit: "kcal" },
        ],
      },
      context: {
        source: "fitbit",
        modality: "wearable",
        device: null,
        source_measurement_type: "heart-rate-intraday",
      },
      provenance: {
        source_record_id: null,
        ingested_at: "2026-04-27T10:00:00.000Z",
        group_id: null,
        parent_event_id: "ev-01",
        adapter: "fitbit-heart-rate-v1",
        adapter_version: "1.0.0",
      },
      mapping: {
        standard_code: null,
        standard_system: null,
        standard_display: null,
        confidence: null,
        method: null,
      },
      quality: {
        flags: [],
        conformance: "ok",
        completeness: 1.0,
        plausibility: "ok",
        expected_field_count: 5,
        present_field_count: 5,
      },
      stage: "qualified",
      extensions: null,
      emit_id: "hr-zones",
    };
  }),
  ...(
    [
      { time: "06:00:00", value: 58, flags: [] as QualityFlag[] },
      { time: "06:01:00", value: 60, flags: [] as QualityFlag[] },
      { time: "06:02:00", value: 61, flags: [] as QualityFlag[] },
      { time: "06:03:00", value: 63, flags: [] as QualityFlag[] },
      {
        time: "06:04:00",
        value: 244,
        flags: [
          {
            code: "HR_OUT_OF_RANGE",
            severity: "warning",
            stage: "validated",
            message: "value 244 outside [25, 230] for heart-rate",
          },
          {
            code: "HAMPEL_OUTLIER",
            severity: "warning",
            stage: "qualified",
            message: "Hampel: |x - median| > 3.5·MAD for (u-08431, heart-rate)",
          },
        ] as QualityFlag[],
      },
      { time: "06:05:00", value: 64, flags: [] as QualityFlag[] },
    ]
  ).map((d, i): CanonicalEvent => ({
    event_id: `ev-intra-${i}`,
    subject_id: "u-08431",
    timestamp: `2025-01-12T${d.time}.000Z`,
    timestamp_end: `2025-01-12T${d.time}.000Z`,
    duration_seconds: 60,
    type: "measurement",
    category: "heart-rate",
    granularity: "interval",
    payload: { value: d.value, raw_value: d.value, unit: "bpm", label: "Heart Rate", components: null },
    context: {
      source: "fitbit",
      modality: "wearable",
      device: null,
      source_measurement_type: "heart-rate-intraday",
    },
    provenance: {
      source_record_id: null,
      ingested_at: "2026-04-27T10:00:00.000Z",
      group_id: null,
      parent_event_id: "ev-01",
      adapter: "fitbit-heart-rate-v1",
      adapter_version: "1.0.0",
    },
    mapping: {
      standard_code: null,
      standard_system: null,
      standard_display: null,
      confidence: null,
      method: null,
    },
    quality: {
      flags: [...d.flags],
      conformance: d.flags.some((f) => f.severity === "error") ? "issues" : "ok",
      completeness: 1.0,
      plausibility: d.flags.length === 0 ? "ok" : "review",
      expected_field_count: 4,
      present_field_count: 4,
    },
    stage: "qualified",
    extensions: null,
    emit_id: "hr-intraday",
  })),
];
