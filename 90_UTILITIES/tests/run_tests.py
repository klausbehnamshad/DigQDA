#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Reproduzierbare Tests. Deckt die Senior-Review-P0 ab, jeweils rot-zuerst-fähig:
zero evidence (P0-01), unbound (P0-02), mode-SM (P0-03), claim nicht überschreibbar
(P0-04), overlap-Locator (P0-05), malformed SRT fail-closed (P0-06).

Aufruf: python3 run_tests.py    (Deps: rapidfuzz, jsonschema)
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


def validate(jsonf, *extra):
    r = run([os.path.join(UTIL, "qda_validate.py"), "--source", os.path.join(FIX, "interview.srt"),
             "--json", os.path.join(FIX, jsonf)] + list(extra))
    res = json.loads(r.stdout.split("--- Manifest-Fragment ---")[-1])["result"]
    return res, r.returncode


srt = os.path.join(FIX, "interview.srt")
txt = os.path.join(FIX, "interview.txt")

print("T1  P0-Segmenter SRT")
d = seg(srt, "--max-gap-ms", "50")
check("SRT split -> 3 units", d["meta"]["n_units"] == 3, d["meta"])
check("unit_ids S01..S03", [u["unit_id"] for u in d["source_units"]] == ["S01", "S02", "S03"])
d1 = seg(srt)
check("Default merged -> 1 unit", d1["meta"]["n_units"] == 1)

print("T2  P0-Segmenter TXT")
t = seg(txt)
check("TXT -> 4 units", t["meta"]["n_units"] == 4)
check("S02 Sprecher B", t["source_units"][1]["explicit_speaker"] == "B")

print("T3  Validator bound_srt")
res, rc = validate("bound_srt.json")
check("1 EXACT / 1 FUZZY / 1 NOT_FOUND",
      (res["quotes_exact"], res["quotes_fuzzy"], res["quotes_not_found"]) == (1, 1, 1), res)
check("Verdict REVIEW_REQUIRED", res["verdict"] == "REVIEW_REQUIRED")
check("Exit 1", rc == 1)

print("T4  Schema-Vertrag")
from jsonschema import Draft202012Validator
schema = json.load(open(os.path.join(GEN, "p1_schema.json"), encoding="utf-8"))
v = Draft202012Validator(schema)
val = lambda fn: not list(v.iter_errors(json.load(open(os.path.join(FIX, fn), encoding="utf-8"))))
check("gutes Beispiel valide", val("p1_good.json"))
check("Extra-Feld abgelehnt", not val("p1_bad_extra.json"))
check("fehlendes required abgelehnt", not val("p1_bad_missing.json"))
check("unbekannter Enum abgelehnt", not val("p1_bad_enum.json"))
check("CODES_ASSIGNED + leere Liste abgelehnt", not val("p1_bad_empty_codes.json"))
check("NOTHING_CODABLE + Codes abgelehnt", not val("p1_bad_nothing_with_codes.json"))
check("leere source_quote abgelehnt", not val("p1_bad_emptystr.json"))

print("T5  Runner --dry-run OK + Provenance")
import qda_run_p1 as R
units_file = os.path.join(HERE, "_tmp_units.json")
json.dump(d1, open(units_file, "w", encoding="utf-8"), ensure_ascii=False)
schema_file = os.path.join(GEN, "p1_schema.json")


def run_p1(*extra):
    r = run([os.path.join(UTIL, "qda_run_p1.py"), "--units", units_file,
             "--schema", schema_file, "--dry-run"] + list(extra))
    return (json.loads(r.stdout)["_qda_run"] if r.stdout.strip() else None), r.returncode


m, rc = run_p1("--num-ctx", "8192")
check("DRY_RUN_OK", m["statuses"][0]["status"] == "DRY_RUN_OK")
check("Exit 0", rc == 0)
check("Manifest: contract/schema/prompt/library/claim + Hashes",
      all(k in m for k in ("contract_version", "contract_sha256", "schema_sha256",
                           "prompt_sha256", "library_version", "allowed_method_claim")))

print("T6  Runner fail-closed bei Budget")
m2, rc2 = run_p1("--num-ctx", "300", "--reserve-output-tokens", "100")
check("SKIPPED_OVER_BUDGET", m2["statuses"][0]["status"] == "SKIPPED_OVER_BUDGET")
check("Exit 1", rc2 == 1)

print("T7  Reales Built-in-Beispiel schema-valide & quellentreu")
ex_open, ex_cb = json.loads(R.EXAMPLE_OPEN), json.loads(R.EXAMPLE_CODEBOOK)
check("EXAMPLE_OPEN valide", not list(v.iter_errors(ex_open)))
check("EXAMPLE_CODEBOOK valide", not list(v.iter_errors(ex_cb)))
tmp_ex = os.path.join(HERE, "_tmp_example.json")
json.dump(ex_open, open(tmp_ex, "w", encoding="utf-8"), ensure_ascii=False)
rr = run([os.path.join(UTIL, "qda_validate.py"), "--source", srt, "--json", tmp_ex, "--document-mode"])
res7 = json.loads(rr.stdout.split("--- Manifest-Fragment ---")[-1])["result"]
check("beide Beispiel-Zitate EXACT (document-mode)", res7["quotes_exact"] == 2, res7)
os.remove(tmp_ex)

print("T8  Binding: Fehlbindung -> WRONG_UNIT (P0-02-Kern)")
res8, rc8 = validate("mis_attribution.json")
check("WRONG_UNIT erkannt", res8["quotes_wrong_unit"] == 1, res8)
check("kein faelschliches EXACT / nicht PASS", res8["quotes_exact"] == 0 and res8["verdict"] != "PASS")
check("Exit 1", rc8 == 1)

print("T9  FUZZY-only -> REVIEW")
res9, rc9 = validate("fuzzy_only.json")
check("Verdict REVIEW_REQUIRED", res9["verdict"] == "REVIEW_REQUIRED")
check("Exit 1", rc9 == 1)

print("T10  validate_mode (P0-03 volle Statemachine)")
allowed = {"Familienbindung"}
CD = "CODES_ASSIGNED"
ind = {"coding_decision": CD, "descriptive_codes": [{"code_label": "frei", "status": "INDUCTIVE_CANDIDATE"}]}
cb = {"coding_decision": CD, "descriptive_codes": [{"code_label": "Familienbindung", "status": "CODEBOOK_APPLIED"}]}
fremd = {"coding_decision": CD, "descriptive_codes": [{"code_label": "X", "status": "CODEBOOK_APPLIED"}]}
ncf = {"coding_decision": "NO_CODE_FITS", "descriptive_codes": []}
mix = {"coding_decision": CD, "descriptive_codes": [
    {"code_label": "Familienbindung", "status": "CODEBOOK_APPLIED"},
    {"code_label": "neu", "status": "INDUCTIVE_CANDIDATE"}]}
two_ind = {"coding_decision": CD, "descriptive_codes": [
    {"code_label": "a", "status": "INDUCTIVE_CANDIDATE"}, {"code_label": "b", "status": "INDUCTIVE_CANDIDATE"}]}
check("STRICT lehnt induktiv ab", R.validate_mode(ind, "STRICT_CODEBOOK", allowed) is not None)
check("STRICT akzeptiert Codebuch-Code", R.validate_mode(cb, "STRICT_CODEBOOK", allowed) is None)
check("STRICT lehnt Nicht-Codebuch-Label ab", R.validate_mode(fremd, "STRICT_CODEBOOK", allowed) is not None)
check("OPEN lehnt Codebuch-Status ab", R.validate_mode(cb, "OPEN_DESCRIPTIVE", None) is not None)
check("OPEN lehnt NO_CODE_FITS ab", R.validate_mode(ncf, "OPEN_DESCRIPTIVE", None) is not None)
check("CONSTRAINED lehnt Mischen ab", R.validate_mode(mix, "CONSTRAINED_EXTENSION", allowed) is not None)
check("CONSTRAINED lehnt >1 induktiv ab", R.validate_mode(two_ind, "CONSTRAINED_EXTENSION", allowed) is not None)

print("T11  grammar_schema fuer Ollama")
g = R.grammar_schema(schema); gs = json.dumps(g)
check("kein allOf/if/then", not any(k in g for k in ("allOf", "if", "then")))
check("kein minLength/minItems", "minLength" not in gs and "minItems" not in gs)
check("enum/additionalProperties bleiben", '"enum"' in gs and "additionalProperties" in gs)

print("T12  Hash-Konsistenz")
_, _ = validate("bound_srt.json")
rman = run([os.path.join(UTIL, "qda_validate.py"), "--source", srt, "--json", os.path.join(FIX, "bound_srt.json")])
man = json.loads(rman.stdout.split("--- Manifest-Fragment ---")[-1])
check("Segmenter- = Validator-Hash", seg(srt)["meta"]["source_sha256"] == man["source_sha256"])

print("T13  P0-01 zero evidence")
res_e, rc_e = validate("p1_bad_empty_codes.json")
check("CODES_ASSIGNED+leer -> INVALID_INPUT", res_e["verdict"] == "INVALID_INPUT", res_e)
check("Exit 2", rc_e == 2)
res_n, rc_n = validate("nothing_codable.json")
check("gebundenes NOTHING_CODABLE -> NO_EVIDENCE (nicht PASS)", res_n["verdict"] == "NO_EVIDENCE", res_n)
check("Exit 1 (kein Schein-PASS)", rc_n == 1)

print("T14  P0-02 unbound evidence")
res_u, rc_u = validate("unbound.json")
check("Zitat UNBOUND (Range unaufloesbar)", res_u["quotes_unbound"] == 1, res_u)
check("Verdict REVIEW (kein PASS)", res_u["verdict"] == "REVIEW_REQUIRED")
check("Exit 1", rc_u == 1)
res_pg, rc_pg = validate("p1_good.json")
check("ungebundenes Modelloutput ohne source_range -> INVALID_INPUT", res_pg["verdict"] == "INVALID_INPUT", res_pg)
check("Exit 2", rc_pg == 2)

print("T18  Gap1 fremde Payload (fake_quote) erreicht NICHT PASS")
res_f, rc_f = validate("foreign_payload.json")
check("fremde Struktur -> INVALID_INPUT", res_f["verdict"] == "INVALID_INPUT", res_f)
check("Exit 2", rc_f == 2)

print("T19  Gap2 Platzhalter-Evidenz ist fail-closed")
res_p, rc_p = validate("placeholder_evidence.json")
check("'not stated' -> MISSING_EVIDENCE", res_p["quotes_missing_evidence"] == 1, res_p)
check("trotz eines EXACT kein PASS", res_p["verdict"] == "REVIEW_REQUIRED")
check("Exit 1", rc_p == 1)

print("T20  Gap4 Mehr-Cue-Fenster ist gueltige SPAN -> PASS")
res_s, rc_s = validate("span_window.json")
check("Verdict PASS", res_s["verdict"] == "PASS", res_s)
check("keine ungueltigen Locatoren", res_s["locators_invalid"] == 0, res_s)
check("Exit 0", rc_s == 0)

print("T21  Gap3 .srt mit kaputtem Pfeil -> fail-closed (kein TXT-Fallback)")
r_ba = run([os.path.join(UTIL, "qda_segment.py"), "--source", os.path.join(FIX, "bad_arrow.srt")])
check("Exit != 0", r_ba.returncode != 0, f"rc={r_ba.returncode}")
check("kein Output-JSON", r_ba.stdout.strip() == "")

print("T22  unbound NOTHING_CODABLE -> INVALID_INPUT (nicht NO_EVIDENCE)")
res_un, rc_un = validate("unbound_nothing_codable.json")
check("Verdict INVALID_INPUT", res_un["verdict"] == "INVALID_INPUT", res_un)
check("Exit 2", rc_un == 2)

print("T15  P0-05 blosse Overlap ist ungueltig")
res_o, rc_o = validate("overlap_locator.json")
check("Locator ungueltig gezaehlt", res_o["locators_invalid"] >= 1, res_o)
check("Verdict REVIEW (kein PASS trotz EXACT-Zitat)", res_o["verdict"] == "REVIEW_REQUIRED")
check("Exit 1", rc_o == 1)

print("T16  P0-04 Methodenclaim nicht ueberschreibbar")
check("Claim = Contract-Konstante", m["allowed_method_claim"] == "GENERIC_SOURCE_NEAR_CONTROLLED_QDA_CODING")
r_claim = run([os.path.join(UTIL, "qda_run_p1.py"), "--units", units_file, "--schema", schema_file,
               "--dry-run", "--method-claim", "GROUNDED_THEORY_METHOD_CLAIM"])
check("--method-claim wird abgewiesen (kein Override)", r_claim.returncode != 0)

print("T17  P0-06 malformed SRT fail-closed")
r_bad = run([os.path.join(UTIL, "qda_segment.py"), "--source", os.path.join(FIX, "malformed.srt")])
check("Abbruch mit Exit != 0", r_bad.returncode != 0, f"rc={r_bad.returncode}")
check("kein Output-JSON auf stdout", r_bad.stdout.strip() == "")

os.remove(units_file)
print(f"\n{'='*48}\n  {PASS} PASS  /  {FAIL} FAIL\n{'='*48}")
sys.exit(0 if FAIL == 0 else 1)
