#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
QDA P1 RUNNER (v0.2, DRAFT) -- Referenzimplementierung der P1-Kante.

Belastbarer Orchestrator fuer den deskriptiven Kodierpass (P1) auf lokalem Ollama.
Diese CLI ist die unabhaengige Referenzimplementierung des Dependency-Vertrags;
ein governed consumer nutzt einen eigenen Adapter, nicht diese CLI direkt.

v0.2 behebt Review-Befunde:
- STRICT_CODEBOOK / CONSTRAINED_EXTENSION / OPEN_DESCRIPTIVE werden MASCHINELL
  erzwungen (Status + Codebuch-Mitgliedschaft), nicht nur im Prompt behauptet.
- Vertragsverletzung/Fehler sind fail-closed: Exit != 0, kein Schein-Erfolg.
- Manifest traegt contract/schema/library/model/backend-Version + Methodenclaim.
- Ans Ollama-format geht ein grammatiktaugliches Schema (ohne if/then/minLength);
  validiert wird die Antwort gegen das VOLLE Schema (jsonschema).
- Beispiel im Prompt ist modusgerecht (kein induktives Beispiel im STRICT-Modus).

Deps (Zielmaschine): pip install ollama jsonschema
--dry-run baut Prompts + prueft Budget/Modusbeispiel OHNE Ollama.
"""

import argparse
import copy
import hashlib
import json
import math
import sys
from datetime import datetime, timezone

LIBRARY_VERSION = "0.2"      # Paketversion
CONTRACT_VERSION = "0.1"     # Dependency-/Kanten-Vertragsversion (getrennt!)
PROMPT_ID = "QDA-GEN-DESCRIPTIVE-CODING"
PROMPT_VERSION = "1.1"
DEFAULT_METHOD_CLAIM = "GENERIC_SOURCE_NEAR_CONTROLLED_QDA_CODING"

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

# Modusgerechtes Beispiel: Codebuch-Code angewandt, KEIN induktiver Code.
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
2. Führe nichts Verstecktes ein: keine latente Bedeutung, keine Psyche, keine Identität/Resilienz/Trauma/Macht, außer der Text benennt es ausdrücklich.
3. Ein code_label paraphrasiert knapp; es darf keinen Ort, keine Kategorie, keinen Begriff einführen, der nicht im Text steht (aus "Damaskus" wird NICHT "Herkunftsland").
4. Kopiere pro Code eine kurze source_quote ZEICHENGETREU aus der Einheit.
5. Ton, Pause, Ironie, Emotion, Prosodie NICHT erschließen.
6. Lieber KEIN Code als ein vager, abstrakter oder doppelter.
7. Nur diese Einheit. Keine Aussage über das ganze Interview.
8. coding_decision: CODES_ASSIGNED (>=1 Code) | NO_CODE_FITS (nur STRICT_CODEBOOK, kein Codebuch-Code passt, codes []) | NOTHING_CODABLE (kein relevanter manifester Inhalt, codes []).
9. uncertainty ist eine Liste kurzer Punkte; sonst [].

MODUS-DETAILS
- STRICT_CODEBOOK: NUR Codes aus dem Codebuch, status "CODEBOOK_APPLIED" (klar) oder "CODEBOOK_AMBIGUOUS" (Grenze unklar). Passt keiner: descriptive_codes [], coding_decision "NO_CODE_FITS". NIE einen neuen Code erfinden, NIE status "INDUCTIVE_CANDIDATE".
- CONSTRAINED_EXTENSION: erst Codebuch (status CODEBOOK_APPLIED/AMBIGUOUS, Label AUS dem Codebuch). Nur wenn nichts passt, EIN neuer status "INDUCTIVE_CANDIDATE".
- OPEN_DESCRIPTIVE: kein Codebuch; alle Codes status "INDUCTIVE_CANDIDATE".

AUSGABE
Gib AUSSCHLIESSLICH ein einziges JSON-Objekt nach dem Schema zurück. Kein Text davor/danach, \
kein Markdown. Erzeuge NICHT unit_id, source_range, explicit_speaker, quote_locator.

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


def codebook_block(allowed_labels, defs):
    if not allowed_labels:
        return "keins"
    return "; ".join(f"{lbl} = {defs.get(lbl, '')}".strip(" =") for lbl in allowed_labels)


def build_prompt(rq, mode, allowed_labels, defs, unit):
    example = EXAMPLE_OPEN if mode == "OPEN_DESCRIPTIVE" else EXAMPLE_CODEBOOK
    return (BUILT_IN_PROMPT
            .replace("[[RESEARCH_QUESTION]]", rq or "explorative Analyse")
            .replace("[[CODING_MODE]]", mode)
            .replace("[[CODEBOOK]]", codebook_block(allowed_labels, defs))
            .replace("[[EXAMPLE]]", example)
            .replace("[[UNIT_ID]]", str(unit.get("unit_id", "?")))
            .replace("[[UNIT_TEXT]]", unit.get("source_text", "")))


def approx_tokens(text, ratio):
    return math.ceil(len(text) / ratio)


def semantic_check(obj):
    dec = obj.get("coding_decision")
    n = len(obj.get("descriptive_codes", []))
    if dec == "CODES_ASSIGNED" and n == 0:
        return "CODES_ASSIGNED aber keine Codes"
    if dec in ("NO_CODE_FITS", "NOTHING_CODABLE") and n > 0:
        return f"{dec} aber {n} Codes"
    return None


def enforce_mode(obj, mode, allowed_labels):
    """Maschinelle Modus-Erzwingung. Gibt Verletzungsgrund zurueck oder None."""
    for c in obj.get("descriptive_codes", []):
        st, lbl = c.get("status"), c.get("code_label")
        if mode == "STRICT_CODEBOOK":
            if st == "INDUCTIVE_CANDIDATE":
                return f"STRICT: induktiver Code '{lbl}' unzulaessig"
            if allowed_labels is not None and lbl not in allowed_labels:
                return f"STRICT: Code '{lbl}' nicht im Codebuch"
        elif mode == "CONSTRAINED_EXTENSION":
            if st in ("CODEBOOK_APPLIED", "CODEBOOK_AMBIGUOUS") \
                    and allowed_labels is not None and lbl not in allowed_labels:
                return f"CONSTRAINED: Codebuch-Code '{lbl}' nicht im Codebuch"
        elif mode == "OPEN_DESCRIPTIVE":
            if st in ("CODEBOOK_APPLIED", "CODEBOOK_AMBIGUOUS"):
                return f"OPEN: Codebuch-Status '{st}' ohne Codebuch unzulaessig"
    return None


def grammar_schema(schema):
    """Schema fuer Ollamas format: Constraints entfernen, die die Grammatik nicht
    zuverlaessig unterstuetzt (Validierung passiert danach gegen das VOLLE Schema)."""
    drop = {"minLength", "maxLength", "minItems", "maxItems",
            "allOf", "if", "then", "else", "$schema", "title"}
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
    """JSON-Codebuch -> (allowed_labels:set, defs:dict). Nur JSON, damit
    Mitgliedschaft maschinell pruefbar ist."""
    with open(path, encoding="utf-8") as f:
        cb = json.load(f)
    labels, defs = [], {}
    for item in cb:
        if isinstance(item, str):
            labels.append(item)
        elif isinstance(item, dict) and "code_label" in item:
            labels.append(item["code_label"])
            defs[item["code_label"]] = item.get("definition", "")
    return set(labels), defs


def main():
    ap = argparse.ArgumentParser(description="QDA P1 Runner (fail-closed, Modus erzwungen).")
    ap.add_argument("--units", required=True)
    ap.add_argument("--schema", required=True)
    ap.add_argument("--model", default="gemma3n:e4b")
    ap.add_argument("--mode", default="OPEN_DESCRIPTIVE",
                    choices=["OPEN_DESCRIPTIVE", "CONSTRAINED_EXTENSION", "STRICT_CODEBOOK"])
    ap.add_argument("--research-question", default="")
    ap.add_argument("--codebook", help="JSON-Codebuch (Liste von Labels oder {code_label,definition})")
    ap.add_argument("--method-claim", default=DEFAULT_METHOD_CLAIM)
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

    with open(args.units, encoding="utf-8") as f:
        p0 = json.load(f)
    units = p0.get("source_units", p0 if isinstance(p0, list) else [])
    with open(args.schema, encoding="utf-8") as f:
        full_schema = json.load(f)
    grammar = grammar_schema(full_schema)

    allowed_labels, defs = None, {}
    if args.codebook:
        raw = open(args.codebook, encoding="utf-8").read()
        if len(raw) > args.max_codebook_chars:
            sys.stderr.write(f"ABBRUCH: Codebuch {len(raw)}>{args.max_codebook_chars} Zeichen.\n")
            sys.exit(2)
        try:
            allowed_labels, defs = load_codebook(args.codebook)
        except (json.JSONDecodeError, TypeError):
            sys.stderr.write("ABBRUCH: --codebook muss JSON sein (Label-Liste), "
                             "damit Mitgliedschaft maschinell pruefbar ist.\n")
            sys.exit(2)
    if args.mode in ("STRICT_CODEBOOK", "CONSTRAINED_EXTENSION") and not allowed_labels:
        sys.stderr.write(f"ABBRUCH: Modus {args.mode} braucht ein JSON-Codebuch (--codebook).\n")
        sys.exit(2)

    budget = args.num_ctx - args.reserve_output_tokens
    results, statuses = [], []
    validator = chat = None
    model_digest = None
    if not args.dry_run:
        try:
            from jsonschema import Draft202012Validator
            validator = Draft202012Validator(full_schema)
        except ImportError:
            sys.stderr.write("FEHLER: jsonschema fehlt -> pip install jsonschema\n"); sys.exit(2)
        try:
            import ollama
            chat = ollama.chat
            try:
                model_digest = ollama.show(args.model).get("details", {}).get("quantization_level")
            except Exception:  # noqa: BLE001
                model_digest = None
        except ImportError:
            sys.stderr.write("FEHLER: ollama fehlt -> pip install ollama\n"); sys.exit(2)

    for unit in units:
        prompt = build_prompt(args.research_question, args.mode, allowed_labels, defs, unit)
        tok = approx_tokens(prompt, args.token_ratio)
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
            sem = semantic_check(obj)
            if sem:
                st.update(status="SEMANTIC_INVALID", reason=sem); statuses.append(st); continue
            mv = enforce_mode(obj, args.mode, allowed_labels)
            if mv:
                st.update(status="MODE_VIOLATION", reason=mv); statuses.append(st); continue
            results.append(bind_p0_fields(unit, obj))
            st["status"] = "OK"; statuses.append(st)
        except json.JSONDecodeError as e:
            st.update(status="NOT_JSON", reason=str(e)); statuses.append(st)
        except Exception as e:  # noqa: BLE001
            st.update(status="ERROR", reason=str(e)); statuses.append(st)

    ok_states = {"OK", "DRY_RUN_OK"}
    n_ok = sum(1 for s in statuses if s.get("status") in ok_states)
    all_ok = bool(units) and all(s.get("status") in ok_states for s in statuses)

    manifest = {
        "runner_id": "QDA-P1-RUNNER", "library_version": LIBRARY_VERSION,
        "contract_version": CONTRACT_VERSION, "prompt_id": PROMPT_ID,
        "prompt_version": PROMPT_VERSION, "allowed_method_claim": args.method_claim,
        "model": args.model, "model_quantization": model_digest, "backend": "ollama",
        "mode": args.mode, "codebook_size": (len(allowed_labels) if allowed_labels else 0),
        "runtime": {"temperature": args.temperature, "top_p": args.top_p,
                    "num_ctx": args.num_ctx, "seed": args.seed},
        "schema_sha256": hashlib.sha256(json.dumps(full_schema, sort_keys=True).encode()).hexdigest(),
        "source_sha256": p0.get("meta", {}).get("source_sha256"),
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "n_units": len(units), "n_ok": n_ok, "statuses": statuses,
        "note": "seed+temp0 verbessern die Wiederholbarkeit, garantieren sie nicht.",
    }
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump({"_qda_run": manifest, "results": results}, f, ensure_ascii=False, indent=2)
    sys.stderr.write(f"units={len(units)} ok={n_ok} all_ok={all_ok}\n")
    if args.dry_run or not args.out:
        print(json.dumps({"_qda_run": manifest}, ensure_ascii=False, indent=2))
    # fail-closed: nur bei durchgaengigem Erfolg Exit 0.
    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
