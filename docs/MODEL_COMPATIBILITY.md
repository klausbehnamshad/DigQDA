# Tested model/backend compatibility

This file records observed DigQDA conformance runs. It is not a general model
quality ranking and does not establish suitability for a research project.
Every production use still requires human review and the consuming system's
data-protection and authorization controls.

## Local synthetic smoke — 2026-07-16

| Field | Observed value |
|---|---|
| Host | Apple M3, 11.8 GiB Metal memory available to Ollama |
| Python | 3.13.9 |
| Ollama server | 0.24.0, localhost |
| Python client | 0.6.2 |
| Model | `gemma3:4b` |
| Quantization | `Q4_K_M` |
| Model digest | `a2af6cc3eb7fa8be8504abaf9b04e88f17a119ec3f04a3addf55f92841195f5a` |
| Runtime | temperature 0.0, top_p 0.9, num_ctx 8192, seed 42 |
| Source | bundled synthetic SRT, SHA-256 `16bea23fb7d0562d96efc4933cb145d907c5a6efe48bb9b4b4c8a2a1b9baf8fc` |
| Prompt SHA-256 | `357727b6ab7b5c8e53d6012a9db0193061e9846259f75c5606a57b2ab121ff12` |
| Schema SHA-256 | `c09ddafc7b9db9ff8c8b4b76c62f29324e8c3aacd5ffe53c70bbb1229520ff84` |
| Contract SHA-256 | `f14ef8d98cf1e7528350e04aab3f4ce06b8802f69c301bfad2ad9baa5866e820` |

### Results

| Mode | Runner | Validator | Evidence | Locators | Effective grammar SHA-256 |
|---|---|---|---|---|---|
| `OPEN_DESCRIPTIVE` | 4/4 `OK` | `PASS` | 8 exact, 0 fuzzy/not-found | 0 invalid / 12 | `de3ca60621ed5d3410c6fe1b9bc2bdbf51103aae078e1984b1b0a21d3f398eae` |
| `STRICT_CODEBOOK` | 4/4 `OK` | `PASS` | 5 exact, 0 fuzzy/not-found | 0 invalid / 9 | `c16a2315948753a3b515c0badcafa4e6c2a1ce48deb11b30c0806611026e417a` |

The STRICT run used the bundled two-entry synthetic codebook with SHA-256
`d2f79b2f0b49c594f0108311d1346cb5451f8cc26b09420310c364d2a9f465360d2cf`.
No invalid response remained in quarantine.

### Reproduction

```bash
ollama serve
MODEL=gemma3:4b bash 90_UTILITIES/smoke/run_smoke.sh
```

Only the bundled synthetic fixtures are authorized for this harness. A passing
smoke result proves local contract plumbing, structured-output compliance and
technical evidence binding for this exact model digest. It does not prove
semantic coding quality on unseen or protected data.
