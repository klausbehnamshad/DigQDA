#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
QDA-UTIL-QUOTE-LOCATOR-VALIDATION  (v0.3, DRAFT)

Externer, deterministischer Validator. Leitsatz: Modell schlaegt vor, Code verifiziert.
Prueft mechanische Treue (Zitat zeichengetreu IN der behaupteten Einheit? Locator gueltig?),
nicht analytische Guete.

v0.3 schliesst Fail-closed-Luecken (Senior-Review P0-01/02/05):
- Verdikte getrennt: PASS | REVIEW_REQUIRED | NO_EVIDENCE | INVALID_INPUT.
- Null Evidenz ist nur bei EXPLIZIT gebundenem NOTHING_CODABLE/NO_CODE_FITS zulaessig
  (-> NO_EVIDENCE, nicht PASS); sonst INVALID_INPUT.
- Fehlende/ungueltige Einheitsbindung faellt NICHT mehr still auf Dokumentebene
  zurueck: -> UNBOUND, kein PASS. Dokumentweite Pruefung nur mit --document-mode.
- Blosse Timecode-UEBERLAPPUNG ist kein gueltiger Locator mehr (OVERLAP -> REVIEW).
- Exit: PASS=0, REVIEW_REQUIRED/NO_EVIDENCE=1, INVALID_INPUT=2.

Abhaengigkeit: rapidfuzz
"""

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
import unicodedata
from datetime import datetime, timezone

try:
    from rapidfuzz import fuzz
except ImportError:
    sys.stderr.write("FEHLER: rapidfuzz fehlt. -> pip install rapidfuzz\n")
    sys.exit(2)

VALIDATOR_VERSION = "0.3"

QUOTE_KEY_HINT = "quote"
LOCATOR_KEYS = {"quote_locator", "locator", "timecode"}
UNIT_RANGE_KEYS = ("source_range", "source_range_unverified")
EMPTY_DECISIONS = {"NOTHING_CODABLE", "NO_CODE_FITS"}
VALID_LOC = {"EXACT", "WITHIN", "PRESENT"}
PLACEHOLDERS = {"", "not stated", "unclear", "none", "n/a", "na", "not applicable",
                "not requested", "none warranted", "locator unavailable",
                "speaker not identified", "keine", "nicht genannt", "unklar"}
TIMECODE_RE = re.compile(r"(\d{2}):(\d{2}):(\d{2})[,\.](\d{3})")


def normalize(text):
    text = unicodedata.normalize("NFC", text or "")
    text = text.replace(" ", " ")
    return re.sub(r"\s+", " ", text).strip()


def is_placeholder(v):
    return (not isinstance(v, str)) or (v.strip().lower() in PLACEHOLDERS)


def atomic_write(path, text):
    d = os.path.dirname(os.path.abspath(path))
    fd, tmp = tempfile.mkstemp(dir=d, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def tc(h, m, s, ms):
    return ((int(h) * 60 + int(m)) * 60 + int(s)) * 1000 + int(ms)


def parse_srt(raw):
    cues = []
    for block in re.split(r"\n\s*\n", raw.strip()):
        lines = [l for l in block.splitlines() if l.strip() != ""]
        if not lines:
            continue
        for i, line in enumerate(lines):
            t = TIMECODE_RE.findall(line)
            if len(t) >= 2 and "-->" in line:
                idx = int(lines[0].strip()) if lines[0].strip().isdigit() else len(cues) + 1
                cues.append({"index": idx, "start_ms": tc(*t[0]), "end_ms": tc(*t[1]),
                             "text": " ".join(lines[i + 1:]).strip()})
                break
    return cues, len(cues) > 0


def unit_haystack(source_range, src):
    if not isinstance(source_range, str) or is_placeholder(source_range):
        return None
    if src["is_srt"]:
        t = TIMECODE_RE.findall(source_range)
        if len(t) < 2:
            return None
        lo, hi = tc(*t[0]), tc(*t[1])
        texts = [c["text"] for c in src["cues"]
                 if c["start_ms"] >= lo - 1 and c["end_ms"] <= hi + 1]
        return normalize(" ".join(texts)) if texts else None
    m = re.search(r"[Ll]\s*(\d+)\s*[-–]\s*[Ll]?\s*(\d+)", source_range) or \
        re.search(r"[Ll]\s*(\d+)", source_range)
    if m:
        a = int(m.group(1)); b = int(m.group(2)) if m.lastindex >= 2 else a
        lines = src["lines"]
        if 1 <= a <= b <= len(lines):
            return normalize(" ".join(lines[a - 1:b]))
    return None


def check_quote(quote, unit_hay, doc_hay, threshold, document_mode):
    q = normalize(quote)
    if q == "":
        return {"result": "SKIPPED", "reason": "leeres Zitat"}
    if unit_hay is None:
        if not document_mode:
            return {"result": "UNBOUND", "reason": "keine gueltige Einheitsbindung"}
        hay = doc_hay
    else:
        hay = unit_hay
    if q in hay:
        return {"result": "EXACT", "score": 100.0}
    al = fuzz.partial_ratio_alignment(q, hay)
    score = round(al.score, 1) if al is not None else 0.0
    closest = hay[al.dest_start:al.dest_end].strip() if al is not None else ""
    if score >= threshold:
        return {"result": "FUZZY", "score": score, "closest_source": closest[:240]}
    if unit_hay is not None:
        if q in doc_hay:
            return {"result": "WRONG_UNIT", "score": 100.0,
                    "reason": "zeichengetreu, aber nicht in der behaupteten Einheit"}
        ald = fuzz.partial_ratio_alignment(q, doc_hay)
        if ald is not None and round(ald.score, 1) >= threshold:
            return {"result": "WRONG_UNIT", "score": round(ald.score, 1),
                    "closest_source": doc_hay[ald.dest_start:ald.dest_end].strip()[:240]}
    return {"result": "NOT_FOUND", "score": score, "closest_source": closest[:240]}


def check_locator(loc, src):
    if is_placeholder(loc):
        return {"result": "SKIPPED"}
    if not src["is_srt"]:
        m = re.search(r"[Ll]\s*(\d+)\s*[-–]\s*[Ll]?\s*(\d+)", loc) or re.search(r"[Ll]\s*(\d+)", loc)
        if m:
            a = int(m.group(1)); b = int(m.group(2)) if m.lastindex >= 2 else a
            if 1 <= a <= b <= src["n_lines"]:
                return {"result": "PRESENT"}
            return {"result": "NOT_FOUND", "reason": f"Zeilen {a}-{b} ausserhalb"}
        return {"result": "NOT_FOUND", "reason": "kein pruefbarer TXT-Locator"}
    t = TIMECODE_RE.findall(loc)
    cues = src["cues"]
    if not t:
        m = re.search(r"\d+", loc)
        if m and any(c["index"] == int(m.group()) for c in cues):
            return {"result": "PRESENT", "match": "cue_index"}
        return {"result": "NOT_FOUND"}
    times = [tc(*x) for x in t]
    lo, hi = min(times), max(times)
    for c in cues:
        if c["start_ms"] == lo and c["end_ms"] == hi:
            return {"result": "EXACT", "cue_index": c["index"]}
    for c in cues:
        if lo >= c["start_ms"] and hi <= c["end_ms"]:
            return {"result": "WITHIN", "cue_index": c["index"]}
    for c in cues:  # blosse Ueberlappung ist KEIN gueltiger Locator (P0-05)
        if lo <= c["end_ms"] and hi >= c["start_ms"]:
            return {"result": "OVERLAP", "cue_index": c["index"],
                    "reason": "Range nicht vollstaendig von einem Cue gedeckt"}
    return {"result": "NOT_FOUND"}


def extract_units(data):
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for k in ("results", "source_units", "data", "units"):
            if isinstance(data.get(k), list):
                return data[k]
        if any(key in data for key in ("descriptive_codes", "coding_decision", "unit_id")):
            return [data]
    return None


def collect_from_unit(unit, unit_hay, src, threshold, document_mode, findings):
    """Sucht Zitat-/Locatorfelder in genau EINER Einheit; nutzt deren unit_hay."""
    seg = unit.get("unit_id") or unit.get("segment_id")

    def rec(node, code):
        if isinstance(node, dict):
            code = node.get("code_label", code)
            for key, val in list(node.items()):
                if QUOTE_KEY_HINT in key.lower() and isinstance(val, str) and "locator" not in key.lower():
                    res = ({"result": "SKIPPED"} if is_placeholder(val)
                           else check_quote(val, unit_hay, src["doc_hay"], threshold, document_mode))
                    node[key + "_match"] = res
                    if res["result"] in ("EXACT", "FUZZY", "WRONG_UNIT", "NOT_FOUND", "UNBOUND"):
                        findings["quotes"].append({"segment_id": seg, "code_label": code,
                                                   "value": val, **res})
                if key in LOCATOR_KEYS and isinstance(val, str):
                    res = check_locator(val, src)
                    node[key + "_match"] = res
                    if res["result"] in ("EXACT", "WITHIN", "OVERLAP", "PRESENT", "NOT_FOUND"):
                        findings["locators"].append({"segment_id": seg, "value": val, **res})
            for v in node.values():
                rec(v, code)
        elif isinstance(node, list):
            for it in node:
                rec(it, code)

    # Unit-Range separat als Locator pruefen
    for rk in UNIT_RANGE_KEYS:
        if isinstance(unit.get(rk), str) and not is_placeholder(unit[rk]):
            res = check_locator(unit[rk], src)
            unit[rk + "_match"] = res
            if res["result"] in ("EXACT", "WITHIN", "OVERLAP", "PRESENT", "NOT_FOUND"):
                findings["locators"].append({"segment_id": seg, "value": unit[rk], **res})
            break
    rec({k: v for k, v in unit.items() if k not in UNIT_RANGE_KEYS}, None)


def build_report(findings, meta, verdict, reason):
    q = findings["quotes"]
    n = len(q)
    counts = {k: sum(1 for x in q if x["result"] == k)
              for k in ("EXACT", "FUZZY", "WRONG_UNIT", "NOT_FOUND", "UNBOUND")}
    loc = findings["locators"]
    loc_bad = [x for x in loc if x["result"] not in VALID_LOC and x["result"] != "SKIPPED"]
    L = [f"# QDA Quote-/Locator-Validierung — **{verdict}**\n",
         f"> {reason}\n",
         f"- Quelle: `{meta['source_name']}` (SRT: {meta['is_srt']}, Cues: {meta['n_cues']})",
         f"- Quelle-SHA256 (Originalbytes): `{meta['source_sha256'][:16]}…`",
         f"- Validator v{VALIDATOR_VERSION} · {meta['timestamp']} · Fuzzy {meta['threshold']}"
         f"{' · document-mode' if meta['document_mode'] else ''}\n",
         "## Zitate\n", "| Ergebnis | Anzahl |", "|---|---|"]
    for k in ("EXACT", "FUZZY", "WRONG_UNIT", "NOT_FOUND", "UNBOUND"):
        L.append(f"| {k} | {counts[k]} |")
    L.append(f"| **gesamt** | **{n}** |\n")
    flagged = [x for x in q if x["result"] != "EXACT"]
    if flagged:
        L.append("## Zu pruefen (nicht EXACT)\n")
        for x in flagged:
            L.append(f"- **{x['result']}** · Einheit {x.get('segment_id','?')}"
                     f"{' · ' + x['code_label'] if x.get('code_label') else ''}: „{x['value']}\"")
    L.append("\n## Locatoren\n")
    L.append(f"- geprueft: {len(loc)} · ungueltig (inkl. OVERLAP): {len(loc_bad)}")
    for x in loc_bad:
        L.append(f"  - {x['result']} · Einheit {x.get('segment_id','?')} · `{x['value']}`")
    return "\n".join(L), {
        "verdict": verdict, "reason": reason, "quotes_total": n,
        "quotes_exact": counts["EXACT"], "quotes_fuzzy": counts["FUZZY"],
        "quotes_wrong_unit": counts["WRONG_UNIT"], "quotes_not_found": counts["NOT_FOUND"],
        "quotes_unbound": counts["UNBOUND"],
        "locators_total": len(loc), "locators_invalid": len(loc_bad)}


def main():
    ap = argparse.ArgumentParser(description="QDA Quote-/Locator-Validator (fail-closed).")
    ap.add_argument("--source", required=True)
    ap.add_argument("--json", required=True)
    ap.add_argument("--out")
    ap.add_argument("--report")
    ap.add_argument("--fuzzy-threshold", type=float, default=90.0)
    ap.add_argument("--document-mode", action="store_true",
                    help="Erlaubt (explizit!) dokumentweite Pruefung ohne Einheitsbindung.")
    args = ap.parse_args()

    with open(args.source, "rb") as f:
        raw_bytes = f.read()
    source_sha = hashlib.sha256(raw_bytes).hexdigest()
    source_raw = raw_bytes.decode("utf-8")
    with open(args.json, encoding="utf-8") as f:
        data = json.load(f)

    cues, is_srt = parse_srt(source_raw)
    lines = source_raw.splitlines()
    doc_hay = normalize(" ".join(c["text"] for c in cues)) if is_srt else normalize(source_raw)
    src = {"cues": cues, "is_srt": is_srt, "lines": lines, "doc_hay": doc_hay,
           "n_lines": len(lines), "n_chars": len(source_raw)}
    meta = {"source_name": args.source.split("/")[-1], "source_sha256": source_sha,
            "is_srt": is_srt, "n_cues": len(cues), "threshold": args.fuzzy_threshold,
            "document_mode": args.document_mode,
            "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")}

    units = extract_units(data)
    findings = {"quotes": [], "locators": []}
    verdict = reason = None

    if units is None or not all(isinstance(u, dict) for u in units) or len(units) == 0:
        verdict, reason = "INVALID_INPUT", "Kein erkennbares gebundenes P1-Ergebnis (Liste von Einheiten)."
    else:
        for unit in units:
            uh = None
            for rk in UNIT_RANGE_KEYS:
                if isinstance(unit.get(rk), str):
                    uh = unit_haystack(unit[rk], src)
                    break
            collect_from_unit(unit, uh, src, args.fuzzy_threshold, args.document_mode, findings)

        q = findings["quotes"]
        loc_bad = [x for x in findings["locators"]
                   if x["result"] not in VALID_LOC and x["result"] != "SKIPPED"]
        if len(q) == 0:
            legit_empty = all(u.get("coding_decision") in EMPTY_DECISIONS
                              and not u.get("descriptive_codes") for u in units)
            if legit_empty and not args.document_mode:
                verdict, reason = "NO_EVIDENCE", "Gebundenes leeres Ergebnis (NOTHING_CODABLE/NO_CODE_FITS); nichts zu verifizieren, menschliche Bestaetigung noetig."
            else:
                verdict, reason = "INVALID_INPUT", "Null Zitate, aber kein explizit gebundenes leeres Ergebnis."
        else:
            all_exact = all(x["result"] == "EXACT" for x in q)
            verdict = "PASS" if (all_exact and not loc_bad) else "REVIEW_REQUIRED"
            reason = ("Jedes Zitat zeichengetreu in seiner Einheit belegt, Locatoren gueltig."
                      if verdict == "PASS" else
                      "Mind. ein Zitat ist FUZZY/WRONG_UNIT/NOT_FOUND/UNBOUND oder ein Locator ungueltig (inkl. OVERLAP).")

    report_md, summary = build_report(findings, meta, verdict, reason)
    manifest = {"validator_id": "QDA-UTIL-QUOTE-LOCATOR-VALIDATION",
                "validator_version": VALIDATOR_VERSION, "source_sha256": source_sha,
                "document_mode": args.document_mode, "timestamp": meta["timestamp"],
                "result": summary}
    if args.out:
        atomic_write(args.out, json.dumps({"_qda_validation": manifest, "data": data},
                                          ensure_ascii=False, indent=2))
    if args.report:
        atomic_write(args.report, report_md)
    print(report_md)
    print("\n--- Manifest-Fragment ---")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    sys.exit({"PASS": 0, "REVIEW_REQUIRED": 1, "NO_EVIDENCE": 1, "INVALID_INPUT": 2}[verdict])


if __name__ == "__main__":
    main()
