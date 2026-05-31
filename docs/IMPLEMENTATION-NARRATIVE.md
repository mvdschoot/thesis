# Harmonia — Implementation Narrative (thesis-ready prose)

> **Companion to `IMPLEMENTATION.md`.** That file is the exhaustive technical
> reference — every endpoint, flag code, constant, and verbatim artifact. *This*
> file is written as flowing academic prose intended to be lightly edited into the
> implementation chapter of the thesis. It foregrounds the *why* behind each design
> choice and keeps code to a minimum; when a precise identifier, value-spec form,
> flag code, or constant is needed, it points to the matching section of the
> reference document (cited as “Reference §N”). Framework citations (Kahn et al.
> 2016; Tanaka et al. 2001) are placed where they already apply so they can be
> carried straight into the chapter's bibliography.

---

## 1. Overview and motivation

The implementation accompanying this thesis is a working proof of concept named
*Harmonia*: a web application that ingests heterogeneous health and behavioural
data — consumer wearables, smart scales, mobile-app usage logs, serious-game and
virtual-reality telemetry, clinical pilot exports and questionnaires — and
harmonises it into a single canonical representation, from which it derives two of
the most widely adopted health-data standards, HL7 FHIR R4 and the OHDSI OMOP
Common Data Model v5.4.

The problem that motivates the system is well known in health informatics:
every data source speaks its own dialect, and the conventional response is to write
bespoke extract-transform-load code for each one. That approach scales poorly,
buries domain knowledge in imperative code, and produces opaque pipelines whose
decisions are difficult to audit. Harmonia takes a different position. Rather than
writing transformation *code* per source, it expresses each transformation as a
declarative configuration — a YAML *adapter config* — that is interpreted by a
single generic engine. Because the transformation is data rather than code, it can
be authored, repaired and edited by a large language model under human supervision,
and it can be inspected, version-controlled and reasoned about as a first-class
artifact.

The thesis contribution is not merely that the mapping is declarative, but that the
harmonisation is *progressive* and *observable*. Each record advances through a
fixed sequence of named stages, and at every stage the system records what it
checked, inferred, normalised or found suspect. The result is a pipeline whose
intermediate states are all visible and whose every quality judgement is
attributable to a specific stage.

## 2. The principle of progressive harmonization

Harmonia models harmonisation as a ladder of seven explicit stages — *raw,
structured, cleaned, validated, qualified, mapped,* and *standardized* — through
which every record passes in order. The stage of a record is part of its data, not
an implicit property of where it happens to be in the code, so it is always
possible to ask of any event exactly how far it has been harmonised.

Three invariants give the principle teeth, and they recur throughout the
implementation. The first is *tag, don't drop*: no stage ever removes a record.
A record that fails validation is not discarded; it is retained and annotated with
error-severity quality flags, and a later stage records a verdict on whether it
should be used downstream. This preserves the chain of custody and lets each
consumer decide its own tolerance, rather than having the pipeline silently impose
one. The second is the *trail of evidence*: the original, untransformed value is
preserved on every event for the life of the pipeline, and the list of quality
flags is append-only — a flag, once raised, is never erased. The third is
*statelessness*: each HTTP request runs the whole pipeline in process with no
database and no shared state, which keeps the system simple to reason about and to
debug, at the documented cost that cross-record analyses see only the current
request (Reference §1, §10).

A consequence of statelessness deserves emphasis because it shapes several later
choices: to make outputs reproducible without an external identity registry,
Harmonia derives all identifiers deterministically by hashing. FHIR resource
references are UUID5 values minted from stable seeds; OMOP person identifiers are
derived from a SHA-256 of the subject identifier; and unmapped OMOP concepts are
assigned hash-derived identifiers in the OHDSI custom-concept range. Identical input
therefore always yields identical output, which in turn makes the FHIR bundle safe
to submit idempotently and the OMOP rows reproducible across runs (Reference §13,
§14).

## 3. Architecture

The system is deliberately small in its moving parts. The backend is a single
FastAPI process organised into three flat tiers: an HTTP layer, the pipeline
itself, and a tier of pure domain value objects with no input/output. There is no
message broker, no task queue and no worker fabric; the seven stages are ordinary
Python functions called in sequence, which means a developer can place a breakpoint
in any stage and have it fire on the next request. This architectural austerity is
a feature for a proof of concept: it keeps the conceptual surface area small enough
that the harmonisation logic, rather than the plumbing, is what the reader studies.

For deployment the system is packaged as four cooperating services — the API, the
single-page frontend, a persistent HAPI FHIR server, and that server's Postgres
database. A noteworthy architectural decision is that the browser communicates with
the FHIR server *directly*, both to export generated bundles and to drive a live
dashboard that queries the server; the backend is not in that path. This cleanly
separates the concern of *producing* standards-conformant output from the concern
of *hosting* it, and it lets the thesis demonstrate that the exported bundles are
genuine, queryable FHIR rather than merely well-formed JSON (Reference §2, §19).

## 4. The canonical event model

At the centre of the design sits a single data structure, the *canonical event*,
which is the contract every stage reads and writes. Each event records who it
concerns, when it occurred, what kind of record it is, and the measured payload,
together with four supporting facets: provenance (which source record and which
adapter produced it), context (source, device, modality), a terminology mapping,
and a quality assessment. The payload distinguishes a single headline value from a
list of components, which lets multi-axis measurements such as blood pressure, or a
heart-rate zone's several derived figures, be represented faithfully without
flattening them prematurely.

The quality facet is modelled directly on the harmonised data-quality terminology
of **Kahn et al. (2016)**, recording *conformance*, *completeness* and
*plausibility* alongside the append-only list of flags. Adopting an established
vocabulary rather than inventing one lets the thesis situate its quality machinery
within the existing literature and lets readers interpret the verdicts without a
bespoke glossary. A small but important implementation detail is that the public
serialisation of an event strips any internal book-keeping fields (those whose keys
begin with an underscore), so the cross-stage plumbing the engine relies on never
leaks into the API responses the frontend consumes (Reference §3).

## 5. The adapter DSL and the engine that runs it

The declarative language is the technical heart of the contribution. A single YAML
document specifies, for one family of source records, how to recognise those
records, how to turn them into canonical events, and how to configure the
downstream stages — cleaning, validation, qualification and the two output
projections. The language is compact but expressive: it offers a small expression
sub-language for pulling values out of nested records (dotted paths with array
indexing, references to the current iteration element and back to the enclosing
record, fallbacks, templates, lookups, simple arithmetic, and explicit timestamp
parsing), and it offers iteration constructs for the common shapes of health data,
including iterating a nested array and expanding an object's keys — the latter being
the natural way to handle wide questionnaire exports with one column per question
(Reference §5).

Two aspects of the language reflect deliberate methodological positions. The first
is its insistence on a *rigid match block*. Rather than letting a configuration
attempt to transform any record that merely shares a source name, the language
requires that the match block assert the existence and shape of every field the
rules will read and pin any discriminator value. The rationale is that a permissive
match block is a latent bug: a false positive silently produces unusable events,
whereas a false negative surfaces cleanly in the interface as "no configuration
matches", which a user can then choose to widen. Strictness, in other words, makes
failure visible. The second is its explicit *payload triage*: every meaningful
field of a record must be assigned to exactly one role — the headline value, a
component, or an extension — with a hard rule that a value may never also appear as
a component. This discipline ensures that no analytically relevant field is lost
and that none is duplicated when the event is later projected into FHIR and OMOP
(Reference §5, §6).

The engine that interprets the language carries no source-specific code whatsoever;
it is a single generic interpreter that resolves value specifications, evaluates
match predicates, iterates as instructed, and assembles canonical events. It is
careful to be total rather than partial: when a value cannot be resolved or a
timestamp cannot be parsed, it does not raise but records the original value and
defers judgement to the validation stage, in keeping with the tag-don't-drop
principle. It also enforces the value-versus-component rule at load time, quietly
discarding any component that merely restates the headline value and recording that
it did so for the diagnostics surface (Reference §6).

## 6. Diagnostics: making silent failure loud

Because the configurations are machine-generated, a particular failure mode is
endemic: a configuration that is syntactically valid but produces no events,
because a path does not resolve, an iteration target is the wrong type, or the match
predicates exclude every record. A naive engine would fail silently here. Harmonia
instead instruments the adapter stage with a diagnostics collector that records,
per rule and per record, precisely why an event was or was not produced, down to
the specific match clause that excluded a record and the actual value it found. The
diagnostics are bounded so a broken configuration over a large dataset cannot
overwhelm the response, and they are surfaced to the user and fed back to the
language model for automated repair. This turns the brittleness of generated
configurations into a tractable, observable, fixable condition rather than a dead
end (Reference §7, §16).

## 7. Cleaning, validation and qualification

The three middle stages embody the quality machinery. Cleaning applies a short,
ordered chain of heuristics that normalise rather than judge: trimming whitespace,
normalising timestamps to a single ISO 8601 convention in UTC, coercing numeric
strings to numbers, and inferring missing units from a small knowledge base keyed
on source and category. Each heuristic that changes a value records an
informational flag, so even benign normalisation leaves a trace (Reference §8).

Validation, by contrast, only asserts; it never mutates. Five checks examine
required fields, timestamp parseability and recency, the minimum payload appropriate
to the event type, unit membership in a per-category whitelist, and numeric range.
Each failure becomes a quality flag of the appropriate severity, and — crucially —
the offending event remains in the stream. The validation thresholds are not
hard-coded into the validators; they are read from a central, per-category quality
rules file, which an adapter configuration may narrow either globally or per emit
rule. This separates the *policy* of what counts as acceptable from the *mechanism*
of checking it (Reference §9, §11).

Qualification is the only stage that reasons across events. It computes a
completeness ratio against the fields expected for each category, detects duplicates
by fingerprinting configurable fields, and identifies outliers using the Hampel
identifier — the median plus or minus a multiple of the median absolute deviation,
computed within each subject-and-category group. The Hampel test is chosen because
it is robust to the heavy tails and occasional gross errors characteristic of
consumer-wearable data, where a mean-and-standard-deviation rule would be distorted
by the very anomalies it is meant to catch; a minimum group size guards against the
degenerate case in which the deviation collapses to zero on sparse data and would
otherwise flag everything. From the accumulated flags the stage derives the three
Kahn verdicts: an event with any error is marked for exclusion, an event with enough
warnings is marked for review, and the rest are judged plausible. The physiological
bounds used in range checking are drawn from the literature where applicable — for
example, the heart-rate ceiling reflects maximum-heart-rate norms in the spirit of
**Tanaka et al. (2001)** (Reference §10, §11).

## 8. Terminology binding

Between qualification and the output projections, the mapper stage binds standard
terminology codes to events. It does so through a *slot* abstraction motivated by a
practical reality of patient-generated data: such data is enormously repetitive, so
that a single day of heart-rate sampling can contain tens of thousands of events
that all require the same code. Rather than coding each event, the mapper groups
events that share a coding target into slots, lets the user bind a code once per
slot, and applies that binding to every member. The candidate codes are retrieved
from a hosted OHDSI vocabulary service through semantic search, and they may be
proposed automatically by a language model. Because automatic proposal risks
fabricated codes, the suggestion path is guarded: the system records every code the
search tool actually returned and discards any model-proposed code that was not
among them. This is a concrete, defensible safeguard against hallucination and is
worth presenting as such (Reference §12, §15, §16).

## 9. Two projections of one model

The final stages project the mapped events into FHIR R4 and OMOP CDM. The two
standards serve different masters, and the contrast between the projections is
itself an argument the thesis can make. FHIR is an *exchange* standard: it
represents each clinical fact as a self-describing resource connected by references
and packaged in a bundle, it tolerates human-readable codings without machine codes,
and it represents multi-axis measurements as nested components and surveys as a
dedicated questionnaire-response resource. OMOP is an *analytics* standard: it
normalises every fact into a row in a person-centric relational schema, it requires
a standard concept identifier for every row, it has no notion of a nested component
so each must become its own row, and it has no survey-specific table so survey
answers become ordinary observation rows.

These differences force genuinely different decisions. The requirement that every
OMOP row carry a concept identifier makes vocabulary coverage the binding
constraint for the analytics projection, in a way it never is for FHIR; consumer
metrics with no standard equivalent are emitted with the OHDSI "no matching concept"
sentinel and recorded in an audit list, or assigned a deterministic custom concept
identifier, rather than being dropped. The treatment of implausible data also
diverges: FHIR retains excluded events flagged as entered-in-error, faithful to
tag-don't-drop, whereas the OMOP projection omits them — the single deliberate
exception to that principle, justified by the fact that including implausible rows
would contaminate cohort queries, and mitigated by the fact that the same events
remain available through the canonical model and the FHIR bundle (Reference §13,
§14).

## 10. Human-in-the-loop authoring

The language model is woven through the authoring experience rather than bolted on.
It generates a first draft of a configuration from a data sample and a description;
it repairs a configuration that produced no events, given the diagnostics and a
sample record; it applies natural-language edits to a working configuration; and it
proposes terminology bindings. In every case the output is previewed and editable
before it takes effect — generated and repaired configurations are shown for review,
edits are presented as a side-by-side difference, and concept suggestions populate a
binding interface the user can override. The same authoritative description of the
language is supplied to the model in every flow, so that the specification the model
is taught and the specification the engine enforces are literally the same artifact.
The design stance is that the model accelerates authoring while the human retains
judgement, and that the system's strict matching and loud diagnostics keep the
model's mistakes visible rather than silent (Reference §16, §17, §19).

## 11. Limitations and future work

The proof of concept is honest about its boundaries. Statelessness, which buys
simplicity and reproducibility, also means the qualifier cannot draw on
cross-request baselines; a persistence layer would unlock longitudinal outlier
detection and global identifiers. The system relies on an external vocabulary
service for OMOP concept resolution, so analytics coverage degrades gracefully to
the unmapped sentinel when that service is unavailable or when a metric has no
standard concept. Terminology binding into FHIR remains user-mediated rather than
fully automatic. And verification has so far been by exercise against representative
fixtures rather than by a formal test suite. None of these undercut the central
claim; each marks a clear direction for the work to mature (Reference §10, §14,
§22).

---

*For exact endpoint signatures, value-spec forms, flag codes, constants, the full
DSL specification as taught to the model, and verbatim example configurations, see
the companion reference `IMPLEMENTATION.md`.*
