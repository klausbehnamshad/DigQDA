# Changelog

All notable changes will be documented here.

## Unreleased — DigQDA extraction

- established DigQDA as an independent upstream method-contract toolkit;
- added Integration Contract v0.1 and lightweight method governance;
- separated the public software artifact from consumer data-governance duties;
- added quiet validator output for governed adapters;
- retained the hardened QDA prototype as the initial reference implementation.
- closed adversarial trust-boundary gaps for foreign payloads, missing evidence,
  malformed SRT input and valid multi-cue spans;
- made the versioned P0 object envelope mandatory and fail-closed against its
  required JSON Schema, including basic cross-field consistency checks;
- moved the complete P1 prompt template and both mode examples into one
  canonical, fully hashed prompt bundle with no embedded fallback.
- completed run provenance with unique run IDs, canonical unit-input and
  rendered-prompt hashes, research-question/codebook hashes, deterministic
  codebook rendering and mandatory model-digest binding for real runs;
- added opt-in, path-confined raw-response quarantine artifacts with hashed
  filenames and integrity references; the repository-local `quarantine/`
  directory is ignored to prevent accidental staging of sensitive outputs;
- added a fail-closed synthetic smoke harness spanning P0 SRT/TXT, real P1 OPEN
  and STRICT calls, external validation, diagnostic quarantine and aggregate
  exit semantics without stale-output reuse;
- made repo-wide Ruff linting and the model-free end-to-end smoke path CI gates,
  and removed the legacy lint violations;
- specialized the Ollama output grammar by coding mode, including an exact
  STRICT code-label enum derived from the bound codebook, and recorded the
  effective `grammar_sha256` in run provenance;
- recorded a fully passing synthetic OPEN+STRICT compatibility run for local
  `gemma3:4b` (`Q4_K_M`) via Ollama.
