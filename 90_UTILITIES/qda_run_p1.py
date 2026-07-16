#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
QDA P1 RUNNER (v0.3, DRAFT) -- Referenzimplementierung der P1-Kante.

v0.3 schliesst Senior-Review-P0:
- P0-03: vollstaendige Modus-Statemachine (validate_mode): coding_decision-Legalitaet,
  Status/Label-Mitgliedschaft, kein Mischen von Codebuch+induktiv, Kardinalitaet.
- P0-04: Methodenclaim ist NICHT mehr per CLI ueberschreibbar; er wird aus einem
  Prompt->Claim-Contract-Mapping abgeleitet und mit Prompt+Schema zu contract_sha256 gehasht.
- Listen-Input-Guard (kein AttributeError bei Listen-P0).
- Atomare Writes.

Deps: pip install ollama jsonschema   ·   --dry-run baut/prueft ohne Ollama.
"""

import argparse
import copy
import hashlib
import json
import math
import os
import sys
import tempfile
from datetime import datetime, timezone

LIBRARY_VERSION = "0.3"
CONTRACT_VERSION = "0.1"
PROMPT_ID = "QDA-GEN-DESCRIPTIVE-CODING"
PROMPT_VERSION = "1.1"
# Der Claim ist an den Prompt/Contract gebunden, NICHT frei setzbar (P0-04).
ALLOWED_METHOD_CLAIM = {
    "QDA-GEN-DESCRIPTIVE-CODING": "GENERIC_SOURCE_NEAR_CONTROLLED_QDA_CODING",
}

EXAMPLE_OPEN = """{
  "concise_description": "Familie ist noch in Damaskus; eine Belastung wird ausdrücklich benannt.",
  "narrative_function": "EVALUATION",
  "coding_decision": "CODES_ASSIGNED",
  "descriptive_codes": [
    {"code_label": "Familie in Damaskus", "definition": "Familie wird als weiterhin in Damaskus befindlich beschrieben", "status": "INDUCTIVE_CANDIDATE", "source_quote": "Meine Familie ist noch in Damaskus"},
    {"code_label": "benannte Belastung", "definition": "eine Belastung wird ausdrücklich benannt", "status": "INDUCTIVE_CANDIDATE", "source_quote": "das belastet mich sehr"}
  ],
  "uncertainty": []
}"""

EXAMPLE_CODEBOOK = """{
  "concise_description": "Familie ist noch in Damaskus; eine Belastung wird ausdrücklich benannt.",
  "narrative_function": "EVALUATION",
  "coding_decision": "CODES_ASSIGNED",
  "descriptive_codes": [
    {"code_label": "Familienbindung", "definition": "im Codebuch: Bezug auf Angehörige", "status": "CODEBOOK_APPLIED", "source_quote": "Meine Familie ist noch in Damaskus"}
  ],
  "uncertainty": []
}"""

BUILT_IN_PROMPT = """Du bist eine sorgfältige qualitative Forscherin. Kodiere GENAU EINE Quelleinheit \
(source unit) quellennah auf Ebene 1 (Beschreibung). Nutze nur den Text der Einheit.

WICHTIGSTE REGEL (gilt vor allen anderen):
Kodiere ausschließlich manifest belegte Sachverhalte. Nur die source_quote muss \
zeichengetreu kopiert werden. code_label und definition dürfen knapp paraphrasieren, \
aber KEINE zusätzliche Information und KEINE latente Bedeutung einführen.

EINSTELLUNGEN
- Forschungsfrage: [[RESEARCH_QUESTION]]
- Coding-Modus: [[CODING_MODE]]
- Codebuch (nur diese Codes sind erlaubt, falls nicht "keins"): [[CODEBOOK]]
- Ausgabesprache: Deutsch (Zitate immer in Originalsprache belassen)

REGELN
1. Bleib am manifesten Inhalt (beschrieben, getan, erlebt, berichtet, verglichen, bewertet, erinnert).
2. Führe nichts Verstecktes ein: keine latente Bedeutung, keine Psyche, keine Identität/Resilienz/Trauma/Macht.
3. Ein code_label paraphrasiert knapp; kein Ort/keine Kategorie/kein Begriff, der nicht im Text steht (aus "Damaskus" wird NICHT "Herkunftsland").
4. Kopiere pro Code eine kurze source_quote ZEICHENGETREU aus der Einheit.
5. Ton, Pause, Ironie, Emotion, Prosodie NICHT erschließen.
6. Lieber KEIN Code als ein vager, abstrakter oder doppelter.
7. Nur diese Einheit. Keine Aussage über das ganze Interview.
8. coding_decision: CODES_ASSIGNED (>=1 Code) | NO_CODE_FITS (nur STRICT_CODEBOOK, codes []) | NOTHING_CODABLE (kein relevanter Inhalt, codes []).
9. uncertainty ist eine Liste kurzer Punkte; sonst [].

MODUS-DETAILS
- STRICT_CODEBOOK: NUR Codebuch-Codes (CODEBOOK_APPLIED/AMBIGUOUS). Kein neuer Code, kein INDUCTIVE_CANDIDATE. Passt keiner: codes [], coding_decision NO_CODE_FITS.
- CONSTRAINED_EXTENSION: entweder Codebuch-Codes (Label aus dem Codebuch) ODER, wenn keiner passt, EIN INDUCTIVE_CANDIDATE. Nicht beides in einer Einheit. Kein NO_CODE_FITS.
- OPEN_DESCRIPTIVE: kein Codebuch; alle Codes INDUCTIVE_CANDIDATE. Kein NO_CODE_FITS.

AUSGABE
Gib AUSSCHLIESSLICH ein einziges JSON-Objekt nach dem Schema zurück. Kein Text davor/danach, kein Markdown. \
Erzeuge NICHT unit_id, source_range, explicit_speaker, quote_locator.

BEISPIEL (für den gewählten Modus)
Quelleinheit: unit_id: S03, text: "Meine Familie ist noch in Damaskus, das belastet mich sehr."
Ausgabe:
[[EXAMPLE]]

ZUR ERINNERUNG: nur die source_quote zeichengetreu, nichts Neues einführen, genau ein JSON-Objekt.

QUELLEINHEIT
unit_id: [[UNIT_ID]]
text:
[[UNIT_TEXT]]
"""


def atomic_write(path, text):
    d = os.path.dirname(os.path.abspath(path))
    fd, tmp = tempfile.mkstemp(dir=d, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text); f.flush(); os.fsync(f.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def codebook_block(allowed_labels, defs):
    if not allowed_labels:
        return "keins"
    return "; ".join(f"{l} = {defs.get(l, '')}".strip(" =") for l in allowed_labels)


def build_prompt(rq, mode, allowed_labels, defs, unit):
    example = EXAMPLE_OPEN if mode == "OPEN_DESCRIPTIVE" else EXAMPLE_CODEBOOK
    return (BUILT_IN_PROMPT
            .replace("[[RESEARCH_QUESTION]]", rq or "explorative Analyse")
            .replace("[[CODING_MODE]]", mode)
            .replace("[[CODEBOOK]]", codebook_block(allowed_labels, defs))
            .replace("[[EXAMPLE]]", example)
            .replace("[[UNIT_ID]]", str(unit.get("unit_id", "?")))
            .replace("[[UNIT_TEXT]]", unit.get("source_text", "")))


def validate_mode(obj, mode, allowed_labels):
    """Vollstaendige Modus-Statemachine (P0-03). Gibt Verletzungsgrund oder None."""
    dec = obj.get("coding_decision")
    codes = obj.get("descriptive_codes", [])
    statuses = [c.get("status") for c in codes]
    labels = [c.get("code_label") for c in codes]
    n_ind = statuses.count("INDUCTIVE_CANDIDATE")
    n_cb = sum(1 for s in statuses if s in ("CODEBOOK_APPLIED", "CODEBOOK_AMBIGUOUS"))
    if dec == "CODES_ASSIGNED" and not codes:
        return "CODES_ASSIGNED aber keine Codes"
    if dec in ("NO_CODE_FITS", "NOTHING_CODABLE") and codes:
        return f"{dec} aber Codes vorhanden"
    if mode == "OPEN_DESCRIPTIVE":
        if dec == "NO_CODE_FITS":
            return "OPEN: NO_CODE_FITS ist ein Codebuch-Konzept, hier unzulaessig"
        for s in statuses:
            if s != "INDUCTIVE_CANDIDATE":
                return f"OPEN: Status '{s}' ohne Codebuch unzulaessig"
    elif mode == "STRICT_CODEBOOK":
        for s, l in zip(statuses, labels):
            if s == "INDUCTIVE_CANDIDATE":
                return f"STRICT: induktiver Code '{l}' unzulaessig"
            if allowed_labels is not None and l not in allowed_labels:
                return f"STRICT: Code '{l}' nicht im Codebuch"
    elif mode == "CONSTRAINED_EXTENSION":
        if dec == "NO_CODE_FITS":
            return "CONSTRAINED: statt NO_CODE_FITS einen INDUCTIVE_CANDIDATE bilden"
        for s, l in zip(statuses, labels):
            if s in ("CODEBOOK_APPLIED", "CODEBOOK_AMBIGUOUS") \
                    and allowed_labels is not None and l not in allowed_labels:
                return f"CONSTRAINED: Codebuch-Code '{l}' nicht im Codebuch"
        if n_cb > 0 and n_ind > 0:
            return "CONSTRAINED: kein Mischen von Codebuch-Code und induktivem Code in einer Einheit"
        if n_ind > 1:
            return f"CONSTRAINED: mehr als ein induktiver Code ({n_ind})"
    return None


def grammar_schema(schema):
    drop = {"minLength", "maxLength", "minItems", "maxItems", "allOf", "if",
            "then", "else", "$schema", "title"}
    if isinstance(schema, dict):
        return {k: grammar_schema(v) for k, v in schema.items() if k not in drop}
    if isinstance(schema, list):
        return [grammar_schema(x) for x in schema]
    return schema


def bind_p0_fields(unit, model_obj):
    src_range = unit.get("source_range", "locator unavailable")
    codes = [{**c, "quote_locator": src_range} for c in model_obj.get("descriptive_codes", [])]
    return {"unit_id": unit.get("unit_id"), "source_type": unit.get("source_type"),
            "source_range": src_range, "explicit_speaker": unit.get("explicit_speaker", "not stated"),
            "concise_description": model_obj.get("concise_description"),
            "narrative_function": model_obj.get("narrative_function"),
            "coding_decision": model_obj.get("coding_decision"),
            "descriptive_codes": codes, "uncertainty": model_obj.get("uncertainty", [])}


def load_codebook(path):
    with open(path, encoding="utf-8") as f:
        cb = json.load(f)
    labels, defs = [], {}
    for item in cb:
        if isinstance(item, str):
            labels.append(item)
        elif isinstance(item, dict) and "code_label" in item:
            labels.append(item["code_label"]); defs[item["code_label"]] = item.get("definition", "")
    return set(labels), defs


def main():
    ap = argparse.ArgumentParser(description="QDA P1 Runner (fail-closed, Modus + Claim erzwungen).")
    ap.add_argument("--units", required=True)
    ap.add_argument("--schema", required=True)
    ap.add_argument("--model", default="gemma3n:e4b")
    ap.add_argument("--mode", default="OPEN_DESCRIPTIVE",
                    choices=["OPEN_DESCRIPTIVE", "CONSTRAINED_EXTENSION", "STRICT_CODEBOOK"])
    ap.add_argument("--research-question", default="")
    ap.add_argument("--codebook")
    ap.add_argument("--num-ctx", type=int, default=8192)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--temperature", type=float, default=0.0)
    ap.add_argument("--top-p", type=float, default=0.9)
    ap.add_argument("--out")
    ap.add_argument("--max-codebook-chars", type=int, default=4000)
    ap.add_argument("--token-ratio", type=float, default=3.2)
    ap.add_argument("--reserve-output-tokens", type=int, default=768)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    # KEIN --method-claim: der Claim ist vertraglich gebunden (P0-04).

    claim = ALLOWED_METHOD_CLAIM[PROMPT_ID]

    with open(args.units, encoding="utf-8") as f:
        p0 = json.load(f)
    if isinstance(p0, list):
        units, p0_meta = p0, {}
    elif isinstance(p0, dict):
        units, p0_meta = p0.get("source_units", []), p0.get("meta", {})
    else:
        sys.stderr.write("ABBRUCH: P0-Input ist weder Liste noch Objekt.\n"); sys.exit(2)
    if not units or not all(isinstance(u, dict) and u.get("source_text") for u in units):
        sys.stderr.write("ABBRUCH: P0-Units fehlen oder haben keinen source_text.\n"); sys.exit(2)

    with open(args.schema, encoding="utf-8") as f:
        full_schema = json.load(f)
    grammar = grammar_schema(full_schema)

    allowed_labels, defs = None, {}
    if args.codebook:
        raw = open(args.codebook, encoding="utf-8").read()
        if len(raw) > args.max_codebook_chars:
            sys.stderr.write(f"ABBRUCH: Codebuch zu gross ({len(raw)}).\n"); sys.exit(2)
        try:
            allowed_labels, defs = load_codebook(args.codebook)
        except (json.JSONDecodeError, TypeError):
            sys.stderr.write("ABBRUCH: --codebook muss JSON sein.\n"); sys.exit(2)
    if args.mode in ("STRICT_CODEBOOK", "CONSTRAINED_EXTENSION") and not allowed_labels:
        sys.stderr.write(f"ABBRUCH: Modus {args.mode} braucht --codebook (JSON).\n"); sys.exit(2)

    schema_sha = hashlib.sha256(json.dumps(full_schema, sort_keys=True).encode()).hexdigest()
    prompt_sha = hashlib.sha256(BUILT_IN_PROMPT.encode()).hexdigest()
    contract_sha = hashlib.sha256(json.dumps(
        {"prompt_id": PROMPT_ID, "prompt_version": PROMPT_VERSION,
         "schema_sha256": schema_sha, "prompt_sha256": prompt_sha,
         "method_claim": claim}, sort_keys=True).encode()).hexdigest()

    budget = args.num_ctx - args.reserve_output_tokens
    results, statuses = [], []
    validator = chat = None
    model_quant = None
    if not args.dry_run:
        try:
            from jsonschema import Draft202012Validator
            validator = Draft202012Validator(full_schema)
        except ImportError:
            sys.stderr.write("FEHLER: jsonschema fehlt.\n"); sys.exit(2)
        try:
            import ollama
            chat = ollama.chat
            try:
                model_quant = ollama.show(args.model).get("details", {}).get("quantization_level")
            except Exception:  # noqa: BLE001
                model_quant = None
        except ImportError:
            sys.stderr.write("FEHLER: ollama fehlt.\n"); sys.exit(2)

    for unit in units:
        prompt = build_prompt(args.research_question, args.mode, allowed_labels, defs, unit)
        tok = math.ceil(len(prompt) / args.token_ratio)
        st = {"unit_id": unit.get("unit_id"), "approx_prompt_tokens": tok, "budget": budget}
        if tok > budget:
            st["status"] = "SKIPPED_OVER_BUDGET"; statuses.append(st); continue
        if args.dry_run:
            st["status"] = "DRY_RUN_OK"; statuses.append(st); continue
        try:
            resp = chat(model=args.model, messages=[{"role": "user", "content": prompt}],
                        format=grammar,
                        options={"temperature": args.temperature, "top_p": args.top_p,
                                 "num_ctx": args.num_ctx, "seed": args.seed})
            obj = json.loads(resp["message"]["content"])
            errs = sorted(validator.iter_errors(obj), key=lambda e: list(e.path))
            if errs:
                st.update(status="SCHEMA_INVALID", errors=[e.message for e in errs[:5]])
                statuses.append(st); continue
            mv = validate_mode(obj, args.mode, allowed_labels)
            if mv:
                st.update(status="MODE_VIOLATION", reason=mv); statuses.append(st); continue
            results.append(bind_p0_fields(unit, obj))
            st["status"] = "OK"; statuses.append(st)
        except json.JSONDecodeError as e:
            st.update(status="NOT_JSON", reason=str(e)); statuses.append(st)
        except Exception as e:  # noqa: BLE001
            st.update(status="ERROR", reason=str(e)); statuses.append(st)

    ok = {"OK", "DRY_RUN_OK"}
    n_ok = sum(1 for s in statuses if s.get("status") in ok)
    all_ok = bool(units) and all(s.get("status") in ok for s in statuses)
    manifest = {
        "runner_id": "QDA-P1-RUNNER", "library_version": LIBRARY_VERSION,
        "contract_version": CONTRACT_VERSION, "contract_sha256": contract_sha,
        "prompt_id": PROMPT_ID, "prompt_version": PROMPT_VERSION, "prompt_sha256": prompt_sha,
        "schema_sha256": schema_sha, "allowed_method_claim": claim,
        "model": args.model, "model_quantization": model_quant, "backend": "ollama",
        "mode": args.mode, "codebook_size": (len(allowed_labels) if allowed_labels else 0),
        "runtime": {"temperature": args.temperature, "top_p": args.top_p,
                    "num_ctx": args.num_ctx, "seed": args.seed},
        "source_sha256": p0_meta.get("source_sha256"),
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "n_units": len(units), "n_ok": n_ok, "statuses": statuses,
        "note": "seed+temp0 verbessern die Wiederholbarkeit, garantieren sie nicht.",
    }
    if args.out:
        atomic_write(args.out, json.dumps({"_qda_run": manifest, "results": results},
                                          ensure_ascii=False, indent=2))
    sys.stderr.write(f"units={len(units)} ok={n_ok} all_ok={all_ok}\n")
    if args.dry_run or not args.out:
        print(json.dumps({"_qda_run": manifest}, ensure_ascii=False, indent=2))
    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
