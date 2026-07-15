# VERBA

**Verifiable Evidence-bound Repertoire for Bounded Analysis**

VERBA is an independent, versioned method-contract toolkit for evidence-bound
qualitative analysis with local language models. It is upstream research
software: governed applications may consume its contracts, prompts, schemas and
reference validators, but VERBA has no dependency on any consuming system.

> Status: pre-release (`0.2-draft`). VERBA is not itself a research
> infrastructure and does not claim to implement a complete named qualitative
> methodology.

## What VERBA provides

- versioned method contracts and allowed-method-claim boundaries;
- source-near coding prompts with machine-readable JSON schemas;
- deterministic source-unit segmentation and quote/locator validation;
- a local Ollama reference runner with fail-closed conformance checks;
- a consumer-neutral integration contract and conformance suite.

## Boundary

VERBA publishes software and contains no research data. When executed on a
transcript, however, it **does process that input and its derived quotations**.
The consuming application therefore remains responsible for authorization,
data access, storage, logging, retention and release. Outputs must be treated as
potentially sensitive.

The normative edge is defined in
[`contracts/VERBA-INTEGRATION-CONTRACT_v0.1.md`](contracts/VERBA-INTEGRATION-CONTRACT_v0.1.md).

```text
governed consumer
  authorizes and selects one bounded source unit
            |
            v
VERBA method contract + reference implementation
  returns a proposal and validation manifest
            |
            v
governed consumer
  binds protected provenance, stores, reviews and releases
```

A permissible production run requires both conditions:

```text
governance authorization AND valid method contract
```

## Quick start

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements.txt
python3 90_UTILITIES/tests/run_tests.py
```

The Ollama dependency is required only for real model calls. Dry runs and most
contract checks do not require a running model service.

## Repository map

- `contracts/` — normative consumer boundary;
- `00_CORE/` — reliability design and method-independent principles;
- `10_GENERIC/` — generic coding prompts and schemas;
- `90_UTILITIES/` — reference CLIs and conformance tests;
- `docs/METHOD_CATALOG.md` — broader method-family catalog inherited from the
  prototype and retained as design context;
- `GOVERNANCE.md` — lightweight method governance and release policy.

## Independence

VERBA must not import consumer code, name consumer-specific entities in its
contracts, or decide whether a data subject, project or source is authorized.
Consumers integrate through adapters and pin the exact contract, schema and
VERBA versions they have validated.

## Publication status

This repository is not yet ready for a public release. A public `v0.1.0` is
blocked until maintainers confirm the final project name, choose a license,
confirm authorship/ORCID metadata, add `CITATION.cff`, and archive a versioned
release. See [`docs/RELEASE_CHECKLIST.md`](docs/RELEASE_CHECKLIST.md).
