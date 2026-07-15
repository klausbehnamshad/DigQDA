#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Reproduzierbare Tests fuer die QDA-Utilities.
Deckt die Review-Befunde ab: Binding (Befund 2), FUZZY->REVIEW (Befund 3),
STRICT-Erzwingung (Befund 1), fail-closed Exit (Befund 4), Schema-Haertung,
Hash-Konsistenz, echtes Prompt-Beispiel.

Aufruf:  python3 run_tests.py    (Deps: rapidfuzz, jsonschema)
Exit 0 = alle gruen.
"""

import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
UTIL = os.path.dirname(HERE)
GEN = os.path.join(os.path.dirname(UTIL), "10_GENERIC")
FIX = os.path.join(HERE, "fixtures")
PY = sys.executable
sys.path.insert(0, UTIL)

PASS = FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1; print(f"  PASS  {name}")
    else:
        FAIL += 1; print(f"  FAIL  {name}  {detail}")


def run(cmd):
    return subprocess.run([PY] + cmd, capture_output=True, text=True)


def seg(*extra):
    return json.loads(run([os.path.join(UTIL, "qda_segment.py"), "--source"] + list(extra)).stdout)


def validate(src, jsonf):
    r = run([os.path.join(UTIL, "qda_validate.py"), "--source", os.path.join(FIX, src),
             "--json", os.path.join(FIX, jsonf)])
    res = json.loads(r.stdout.split("--- Manifest-Fragment ---")[-1])["result"]
    return res, r.returncode, json.loads(r.stdout.split("--- Manifest-Fragment ---")[-1])


srt = os.path.join(FIX, "interview.srt")
txt = os.path.join(FIX, "interview.txt")

# --- T1 P0 SRT ---
print("T1  P0-Segmenter SRT")
d = seg(srt, "--max-gap-ms", "50")
check("SRT split -> 3 units", d["meta"]["n_units"] == 3, d["meta"])
check("unit_ids S01..S03", [u["unit_id"] for u in d["source_units"]] == ["S01", "S02", "S03"])
check("S01 range exakt", d["source_units"][0]["source_range"] == "00:00:01,000 --> 00:00:04,500")
d1 = seg(srt)
check("Default merged -> 1 unit", d1["meta"]["n_units"] == 1)

# --- T2 P0 TXT ---
print("T2  P0-Segmenter TXT")
t = seg(txt)
check("TXT -> 4 units", t["meta"]["n_units"] == 4)
check("S01 Sprecher I", t["source_units"][0]["explicit_speaker"] == "I")
check("S02 Sprecher B", t["source_units"][1]["explicit_speaker"] == "B")

# --- T3 Validator (bound) ---
print("T3  Validator bound_srt")
res, rc, _ = validate("interview.srt", "bound_srt.json")
check("1 EXACT", res["quotes_exact"] == 1, res)
check("1 FUZZY", res["quotes_fuzzy"] == 1, res)
check("1 NOT_FOUND", res["quotes_not_found"] == 1, res)
check("Verdict REVIEW_REQUIRED", res["verdict"] == "REVIEW_REQUIRED")
check("Exit 1", rc == 1)

# --- T4 Schema-Haertung ---
print("T4  Schema-Vertrag")
from jsonschema import Draft202012Validator
schema = json.load(open(os.path.join(GEN, "p1_schema.json"), encoding="utf-8"))
v = Draft202012Validator(schema)


def valid(fn):
    return not list(v.iter_errors(json.load(open(os.path.join(FIX, fn), encoding="utf-8"))))


check("gutes Beispiel valide", valid("p1_good.json"))
check("Extra-Feld abgelehnt", not valid("p1_bad_extra.json"))
check("fehlendes required abgelehnt", not valid("p1_bad_missing.json"))
check("unbekannter Enum abgelehnt", not valid("p1_bad_enum.json"))
check("CODES_ASSIGNED + leere Liste abgelehnt", not valid("p1_bad_empty_codes.json"))
check("NOTHING_CODABLE + Codes abgelehnt", not valid("p1_bad_nothing_with_codes.json"))
check("leere source_quote abgelehnt", not valid("p1_bad_emptystr.json"))

# --- T5/T6 Runner dry-run + fail-closed ---
print("T5  Runner --dry-run OK")
units_file = os.path.join(HERE, "_tmp_units.json")
json.dump(d1, open(units_file, "w", encoding="utf-8"), ensure_ascii=False)
schema_file = os.path.join(GEN, "p1_schema.json")


def run_p1(*extra):
    r = run([os.path.join(UTIL, "qda_run_p1.py"), "--units", units_file,
             "--schema", schema_file, "--dry-run"] + list(extra))
    return json.loads(r.stdout)["_qda_run"], r.returncode


m, rc = run_p1("--num-ctx", "8192")
check("Unit im Budget -> DRY_RUN_OK", m["statuses"][0]["status"] == "DRY_RUN_OK")
check("dry-run all_ok -> Exit 0", rc == 0)
check("Manifest traegt contract/schema/library-Version",
      all(k in m for k in ("contract_version", "schema_sha256", "library_version",
                           "prompt_version", "allowed_method_claim")))

print("T6  Runner fail-closed bei Budget-Ueberschreitung")
m2, rc2 = run_p1("--num-ctx", "300", "--reserve-output-tokens", "100")
check("winziges num_ctx -> SKIPPED_OVER_BUDGET", m2["statuses"][0]["status"] == "SKIPPED_OVER_BUDGET")
check("Nicht-Ergebnis -> Exit 1 (fail-closed)", rc2 == 1)

os.remove(units_file)

# --- T7 echtes Prompt-Beispiel (nicht nur die Fixture) ---
print("T7  Reales Built-in-Beispiel ist schema-valide & quellentreu")
import qda_run_p1 as R
ex_open = json.loads(R.EXAMPLE_OPEN)
ex_cb = json.loads(R.EXAMPLE_CODEBOOK)
check("EXAMPLE_OPEN schema-valide", not list(v.iter_errors(ex_open)))
check("EXAMPLE_CODEBOOK schema-valide", not list(v.iter_errors(ex_cb)))
tmp_ex = os.path.join(HERE, "_tmp_example.json")
json.dump(ex_open, open(tmp_ex, "w", encoding="utf-8"), ensure_ascii=False)
rr = run([os.path.join(UTIL, "qda_validate.py"), "--source", srt, "--json", tmp_ex])
res7 = json.loads(rr.stdout.split("--- Manifest-Fragment ---")[-1])["result"]
check("beide Beispiel-Zitate EXACT", res7["quotes_exact"] == 2, res7)
os.remove(tmp_ex)

# --- T8 Binding / Fehlbindung (Befund 2) ---
print("T8  Binding: Zitat aus falscher Einheit -> WRONG_UNIT")
res8, rc8, _ = validate("interview.srt", "mis_attribution.json")
check("WRONG_UNIT erkannt", res8["quotes_wrong_unit"] == 1, res8)
check("kein faelschliches EXACT", res8["quotes_exact"] == 0, res8)
check("Verdict NICHT PASS", res8["verdict"] == "REVIEW_REQUIRED")
check("Exit 1", rc8 == 1)

# --- T9 FUZZY-only -> REVIEW (Befund 3) ---
print("T9  FUZZY-only fuehrt NICHT zu PASS")
res9, rc9, _ = validate("interview.srt", "fuzzy_only.json")
check("1 EXACT / 1 FUZZY / 0 NOT_FOUND", res9["quotes_exact"] == 1 and res9["quotes_fuzzy"] == 1
      and res9["quotes_not_found"] == 0, res9)
check("Verdict REVIEW_REQUIRED (nicht PASS)", res9["verdict"] == "REVIEW_REQUIRED")
check("Exit 1", rc9 == 1)

# --- T10 STRICT-Modus maschinell erzwungen (Befund 1) ---
print("T10  enforce_mode")
allowed = {"Familienbindung"}
induktiv = {"descriptive_codes": [{"code_label": "frei", "status": "INDUCTIVE_CANDIDATE"}]}
codebuch = {"descriptive_codes": [{"code_label": "Familienbindung", "status": "CODEBOOK_APPLIED"}]}
fremd = {"descriptive_codes": [{"code_label": "Unbekannt", "status": "CODEBOOK_APPLIED"}]}
check("STRICT lehnt induktiven Code ab", R.enforce_mode(induktiv, "STRICT_CODEBOOK", allowed) is not None)
check("STRICT akzeptiert Codebuch-Code", R.enforce_mode(codebuch, "STRICT_CODEBOOK", allowed) is None)
check("STRICT lehnt Nicht-Codebuch-Label ab", R.enforce_mode(fremd, "STRICT_CODEBOOK", allowed) is not None)
check("OPEN lehnt Codebuch-Status ab", R.enforce_mode(codebuch, "OPEN_DESCRIPTIVE", None) is not None)

# --- T11 grammar_schema strippt Nicht-Grammatik-Keywords ---
print("T11  grammar_schema fuer Ollama")
g = R.grammar_schema(schema)
gs = json.dumps(g)
check("kein allOf/if/then in Grammar", not any(k in g for k in ("allOf", "if", "then")))
check("kein minLength/minItems in Grammar", "minLength" not in gs and "minItems" not in gs)
check("enum/additionalProperties bleiben", '"enum"' in gs and "additionalProperties" in gs)

# --- T12 Hash-Konsistenz Segmenter <-> Validator ---
print("T12  Hash-Konsistenz (Originalbytes)")
seg_hash = seg(srt)["meta"]["source_sha256"]
_, _, man = validate("interview.srt", "bound_srt.json")
check("Segmenter- und Validator-Hash identisch", seg_hash == man["source_sha256"],
      f"{seg_hash[:12]} vs {man['source_sha256'][:12]}")

# --- T13 Quiet mode: keine Zitate in ambient stdout ---
print("T13  Validator --quiet redigiert stdout")
rq = run([os.path.join(UTIL, "qda_validate.py"), "--source", srt,
          "--json", os.path.join(FIX, "mis_attribution.json"), "--quiet"])
quiet_payload = json.loads(rq.stdout)
check("quiet stdout enthaelt nur Manifest", set(quiet_payload) == {"_qda_validation"})
check("quiet stdout enthaelt kein Rohzitat", "Meine Familie" not in rq.stdout)

print(f"\n{'='*48}\n  {PASS} PASS  /  {FAIL} FAIL\n{'='*48}")
sys.exit(0 if FAIL == 0 else 1)
