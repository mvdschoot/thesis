mHealth

**Withings**

**Payload Format**

JSON array of measurement records.

**Fields**

| **Field**           | **Type** | **Description**                                                                  |
| ------------------- | -------- | -------------------------------------------------------------------------------- |
| userId              | uuid     | Keycloak user identifier representing the user to whom this measurement belongs. |
| measurementType     | object   | Contains metadata about the measurement type.                                    |
| └─ typeValue        | integer  | Numeric code for the measurement type (1 for Weight, 2 for Mass).                |
| └─ typeDescription  | string   | Human-readable description of the measurement type.                              |
| attrib              | integer  | Indicates how the measurement was attributed to the user. See table below.       |
| measurementDateTime | string   | Date/time the measurement was taken (ISO 8601 format).                           |
| createdDateTime     | string   | Date/time the record was created (ISO 8601 format).                              |
| modifiedDateTime    | string   | Date/time the record was last modified (ISO 8601 format).                        |
| measurementValue    | number   | The actual measurement value (e.g., weight in kilograms).                        |

**Attrib Field Values**

| **Value** | **Description**                                                                                      |
| --------- | ---------------------------------------------------------------------------------------------------- |
| 0         | Captured by a device and confidently attributed to this user.                                        |
| 1         | Captured by a device, but ambiguous - may belong to other users as well.                             |
| 2         | Entered manually by the user.                                                                        |
| 4         | Entered manually during user creation (may not be accurate).                                         |
| 5         | Auto measurement (Blood Pressure Monitor only); best value computed from multiple readings.          |
| 7         | Confirmed measurement (e.g., user-confirmed detected activity).                                      |
| 8         | Same as 0 - confidently attributed to this user.                                                     |
| 15        | Performed under guided conditions (e.g., Nerve Health Score).                                        |
| 17        | Performed under guided conditions for Nerve Health Score and Electrochemical Skin Conductance tests. |

**Fitbit**

**Payload Format**

JSON array of measurement records.

**Fields**

| **Field**           | **Type**      | **Description**                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                      |
| ------------------- | ------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| userId              | uuid          | Keycloak user identifier representing the user to whom this measurement belongs.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     |
| measurementType     | string        | Type of measurement (e.g., heart-rate-intraday, sleep-log).                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                          |
| measurementDateTime | string        | Timestamp of the measurement (ISO 8601 format).                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                      |
| measurementValue    | string (JSON) | A JSON-encoded string containing the actual measurement details. <br>**Note:** For heart-rate-intraday, refer to the JSON schema at [AZM Intraday](https://dev.fitbit.com/build/reference/web-api/intraday/get-azm-intraday-by-interval/#Response). For sleep-log, refer to the JSON schema at [Sleep log](https://dev.fitbit.com/build/reference/web-api/sleep/get-sleep-log-by-date-range/#Response). For activity (steps, distance, calories, floors, elevation) refer to [Get Activity Time Series by Date](https://dev.fitbit.com/build/reference/web-api/activity-timeseries/get-activity-timeseries-by-date/) |