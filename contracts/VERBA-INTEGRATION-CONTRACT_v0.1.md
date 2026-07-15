# VERBA Integration Contract v0.1

```text
CONTRACT_ID: VERBA-INTEGRATION-CONTRACT
CONTRACT_VERSION: 0.1
STATUS: DRAFT
DIRECTION: VERBA -> consumer
CHANGE_POLICY: breaking edge changes require a new contract version
```

## 1. Purpose

This contract defines the only supported edge between VERBA and a governed
consumer. It separates two assurance responsibilities:

1. the consumer decides whether a run is authorized and controls the data;
2. VERBA constrains the analytic operation and validates its output contract.

Neither responsibility substitutes for the other.

## 2. Dependency rule

- A consumer may depend on a released VERBA contract.
- VERBA must never depend on consumer code, configuration, entities or policy.
- Integration happens through a consumer-owned adapter, not by importing a
  consumer pipeline into this repository.
- The adapter pins `contract_version`, `schema_sha256`, `library_version` and
  `prompt_version`.

## 3. Consumer responsibilities

Before invocation, the consumer MUST:

- establish the legal, ethical and organizational authorization for the run;
- select exactly one bounded source unit per analytic call;
- minimize identifiers and use an opaque `unit_id` at the VERBA edge;
- keep mappings from opaque IDs to protected provenance outside VERBA;
- configure a local or otherwise approved model backend;
- define logging, retention, review and release controls;
- treat model outputs, quotations, reports and validation artifacts as
  potentially sensitive;
- reject the result if VERBA exits non-zero or reports a contract violation.

## 4. VERBA responsibilities

VERBA MUST:

- perform only the declared analytic operation;
- accept no hidden project context or consumer governance state;
- produce only output allowed by the selected schema and method claim;
- enforce coding-mode constraints mechanically where they are machine-testable;
- bind each evidence quote to the supplied source unit;
- fail closed on schema, mode, budget, backend or validation failure;
- expose contract, schema, prompt, library, model and backend provenance;
- avoid implicit persistence and avoid emitting source quotations when invoked
  in quiet integration mode.

VERBA MUST NOT:

- decide consent, access, disclosure, publication or retention;
- infer that local execution makes processing non-personal;
- claim a named method not permitted by the selected prompt header;
- silently broaden a unit-level result to an interview- or corpus-level claim.

## 5. Edge envelope

The current reference CLI consumes P0 JSON. A consumer adapter should construct
the smallest equivalent envelope:

```json
{
  "contract_version": "0.1",
  "operation_id": "DESCRIPTIVE_CODING_SINGLE_SOURCE_UNIT",
  "source_unit": {
    "unit_id": "opaque-local-id",
    "source_text": "bounded source text",
    "source_type": "srt-or-txt",
    "source_range": "optional local locator"
  },
  "settings": {
    "coding_mode": "OPEN_DESCRIPTIVE",
    "research_question": "...",
    "codebook_ref": null
  }
}
```

`source_text`, `source_range` and every derived quotation can be personal data.
The envelope must remain inside the consumer's approved processing boundary.
VERBA does not require participant names, project names, consent records,
storage paths or global catalog identifiers.

## 6. Result acceptance

A consumer may accept a result only when all of the following hold:

- the process exits with code `0`;
- every unit status is `OK` (or `DRY_RUN_OK` for a dry run);
- full-schema and mode validation pass;
- required quote binding validation returns `PASS`;
- the manifest versions match the adapter's pinned versions;
- a human performs every decision declared in `HUMAN_DECISIONS_REQUIRED`.

Anything else is a non-result, not a degraded success.

## 7. Output and logging

- CLIs write artifacts only when an explicit output path is supplied.
- Integrations use quiet/redacted output and capture the manifest separately.
- Raw or fuzzy quotations must not enter ambient application logs.
- The consumer owns encryption, access control, retention and deletion.
- Hashes support integrity; they do not anonymize the source.

## 8. Compatibility

Patch changes may clarify implementation without changing the edge. A new
contract version is required when required inputs, acceptance semantics,
security-relevant output behavior or responsibility allocation changes.
