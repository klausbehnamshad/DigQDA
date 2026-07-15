#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
QDA-UTIL-QUOTE-LOCATOR-VALIDATION  (v0.2, DRAFT)

Externer, deterministischer Validator fuer die VERBA reference utilities.
Leitsatz: Das Modell schlaegt vor, der Code verifiziert.

Prueft mechanische Treue, NICHT analytische Guete:
- source_quote ZEICHENGETREU in der BEHAUPTETEN Einheit (Binding!), nicht nur
  irgendwo in der Datei;
- Locator existiert (SRT-Cue bzw. TXT-Zeilen-/Zeichen-Range).

v0.2 behebt zwei Review-Befunde:
- Binding: ein Zitat aus einer anderen Einheit gilt jetzt als WRONG_UNIT, nicht
  faelschlich als EXACT/PASS.
- Verdikt: nur wenn ALLE Zitate EXACT sind, gilt PASS; FUZZY/WRONG_UNIT/NOT_FOUND
  -> REVIEW_REQUIRED (zeichengetreu-Vertrag).
- Hash: SHA256 der ORIGINAL-Dateibytes (identisch zu qda_segment.py).

Abhaengigkeit: rapidfuzz

Exit-Code: 0 nur bei PASS, sonst 1 (pipeline-tauglich, fail-closed).
"""

import argparse
import hashlib
import json
import re
import sys
import unicodedata
from datetime import datetime, timezone

try:
    from rapidfuzz import fuzz
except ImportError:
    sys.stderr.write("FEHLER: rapidfuzz fehlt. -> pip install rapidfuzz\n")
    sys.exit(2)

VALIDATOR_VERSION = "0.2"

QUOTE_KEY_HINT = "quote"
LOCATOR_KEYS = {"source_range", "source_range_unverified", "quote_locator",
                "locator", "timecode", "range"}
UNIT_RANGE_KEYS = ("source_range", "source_range_unverified")
PLACEHOLDERS = {
    "", "not stated", "unclear", "none", "n/a", "na", "not applicable",
    "not requested", "none warranted", "locator unavailable",
    "speaker not identified", "keine", "nicht genannt", "unklar",
}
TIMECODE_RE = re.compile(r"(\d{2}):(\d{2}):(\d{2})[,\.](\d{3})")


def normalize(text):
    text = unicodedata.normalize("NFC", text or "")
    text = text.replace(" ", " ")
    return re.sub(r"\s+", " ", text).strip()


def is_placeholder(value):
    return (not isinstance(value, str)) or (value.strip().lower() in PLACEHOLDERS)


def tc_to_ms(h, m, s, ms):
    return ((int(h) * 60 + int(m)) * 60 + int(s)) * 1000 + int(ms)


def parse_srt(raw):
    cues = []
    for block in re.split(r"\n\s*\n", raw.strip()):
        lines = [l for l in block.splitlines() if l.strip() != ""]
        if not lines:
            continue
        for i, line in enumerate(lines):
            tcs = TIMECODE_RE.findall(line)
            if len(tcs) >= 2 and "-->" in line:
                idx = int(lines[0].strip()) if lines[0].strip().isdigit() else len(cues) + 1
                cues.append({"index": idx, "start_ms": tc_to_ms(*tcs[0]),
                             "end_ms": tc_to_ms(*tcs[1]),
                             "text": " ".join(lines[i + 1:]).strip()})
                break
    return cues, len(cues) > 0


# --------------------------------------------------------------------------- #
# Einheits-Haystack: der Text GENAU der behaupteten Einheit (Binding)
# --------------------------------------------------------------------------- #
def unit_haystack(source_range, src):
    """Text der durch source_range bezeichneten Einheit; None wenn unbestimmbar."""
    if not isinstance(source_range, str) or is_placeholder(source_range):
        return None
    if src["is_srt"]:
        tcs = TIMECODE_RE.findall(source_range)
        if len(tcs) < 2:
            return None
        lo, hi = tc_to_ms(*tcs[0]), tc_to_ms(*tcs[1])
        texts = [c["text"] for c in src["cues"]
                 if c["start_ms"] >= lo - 1 and c["end_ms"] <= hi + 1]
        if not texts:  # Fallback: ueberlappende Cues
            texts = [c["text"] for c in src["cues"]
                     if c["start_ms"] <= hi and c["end_ms"] >= lo]
        return normalize(" ".join(texts)) if texts else None
    m = re.search(r"[Ll]\s*(\d+)\s*[-–]\s*[Ll]?\s*(\d+)", source_range) or \
        re.search(r"[Ll]\s*(\d+)", source_range)
    if m:
        a = int(m.group(1)); b = int(m.group(2)) if m.lastindex >= 2 else a
        lines = src["lines"]
        if 1 <= a <= b <= len(lines):
            return normalize(" ".join(lines[a - 1:b]))
    return None


def check_quote(quote, unit_hay, doc_hay, threshold):
    q = normalize(quote)
    if q == "":
        return {"result": "SKIPPED", "reason": "leeres Zitat"}
    hay = unit_hay if unit_hay is not None else doc_hay
    scope = "unit" if unit_hay is not None else "document"
    # 1. zeichengetreu in der behaupteten Einheit?
    if q in hay:
        return {"result": "EXACT", "score": 100.0, "scope": scope}
    # 2. nah (nicht zeichengetreu) in der Einheit?
    al = fuzz.partial_ratio_alignment(q, hay)
    score = round(al.score, 1) if al is not None else 0.0
    closest = hay[al.dest_start:al.dest_end].strip() if al is not None else ""
    if score >= threshold:
        out = {"result": "FUZZY", "score": score, "scope": scope}
        if closest:
            out["closest_source"] = closest[:240]
        return out
    # 3. nicht in der Einheit -> steht es woanders in der Datei? (Binding-Bruch)
    if unit_hay is not None:
        if q in doc_hay:
            return {"result": "WRONG_UNIT", "score": 100.0,
                    "reason": "zeichengetreu, aber nicht in der behaupteten Einheit"}
        ald = fuzz.partial_ratio_alignment(q, doc_hay)
        ds = round(ald.score, 1) if ald is not None else 0.0
        if ds >= threshold:
            out = {"result": "WRONG_UNIT", "score": ds,
                   "reason": "nah an anderer Stelle der Datei, nicht in der Einheit"}
            if ald is not None:
                out["closest_source"] = doc_hay[ald.dest_start:ald.dest_end].strip()[:240]
            return out
    out = {"result": "NOT_FOUND", "score": score, "scope": scope}
    if closest:
        out["closest_source"] = closest[:240]
    return out


def check_locator(loc, src):
    if is_placeholder(loc):
        return {"result": "SKIPPED", "reason": "kein Locator angegeben"}
    if not src["is_srt"]:
        m = re.search(r"[Ll]\s*(\d+)\s*[-–]\s*[Ll]?\s*(\d+)", loc) or \
            re.search(r"[Ll]\s*(\d+)", loc)
        if m:
            a = int(m.group(1)); b = int(m.group(2)) if m.lastindex >= 2 else a
            if 1 <= a <= b <= src["n_lines"]:
                return {"result": "PRESENT", "match": "line_range"}
            return {"result": "NOT_FOUND", "reason": f"Zeilen {a}-{b} ausserhalb 1-{src['n_lines']}"}
        mc = re.search(r"[Cc]\s*(\d+)\s*[-–]\s*[Cc]?\s*(\d+)", loc)
        if mc:
            a, b = int(mc.group(1)), int(mc.group(2))
            if 0 <= a <= b <= src["n_chars"]:
                return {"result": "PRESENT", "match": "char_range"}
            return {"result": "NOT_FOUND", "reason": f"Zeichen {a}-{b} ausserhalb 0-{src['n_chars']}"}
        return {"result": "N/A", "reason": "kein pruefbarer TXT-Locator"}
    tcs = TIMECODE_RE.findall(loc)
    cues = src["cues"]
    if not tcs:
        m = re.search(r"\d+", loc)
        if m and any(c["index"] == int(m.group()) for c in cues):
            return {"result": "PRESENT", "match": "cue_index"}
        return {"result": "NOT_FOUND", "reason": "kein Timecode/Index erkannt"}
    times = [tc_to_ms(*t) for t in tcs]
    lo, hi = min(times), max(times)
    for c in cues:
        if c["start_ms"] == lo and c["end_ms"] == hi:
            return {"result": "EXACT", "cue_index": c["index"]}
    for c in cues:
        if lo >= c["start_ms"] and hi <= c["end_ms"]:
            return {"result": "WITHIN", "cue_index": c["index"]}
    for c in cues:
        if lo <= c["end_ms"] and hi >= c["start_ms"]:
            return {"result": "OVERLAP", "cue_index": c["index"]}
    return {"result": "NOT_FOUND", "reason": "kein Cue deckt diesen Timecode"}


def walk(node, ctx, findings, src, threshold):
    if isinstance(node, dict):
        seg = node.get("segment_id") or node.get("unit_id") or ctx.get("segment_id")
        code = node.get("code_label", ctx.get("code_label"))
        # Einheits-Kontext aktualisieren, wenn dieser dict einen source_range traegt
        unit_hay = ctx.get("unit_hay")
        for rk in UNIT_RANGE_KEYS:
            if isinstance(node.get(rk), str):
                uh = unit_haystack(node[rk], src)
                if uh is not None:
                    unit_hay = uh
                break
        local = {"segment_id": seg, "code_label": code, "unit_hay": unit_hay}
        for key in list(node.keys()):
            val = node.get(key)
            if QUOTE_KEY_HINT in key.lower() and isinstance(val, str) \
                    and "locator" not in key.lower():
                if is_placeholder(val):
                    res = {"result": "SKIPPED", "reason": "Platzhalter"}
                else:
                    res = check_quote(val, unit_hay, src["doc_hay"], threshold)
                node[key + "_match"] = res
                if res["result"] in ("EXACT", "FUZZY", "WRONG_UNIT", "NOT_FOUND"):
                    findings["quotes"].append({"segment_id": seg, "code_label": code,
                                               "field": key, "value": val, **res})
            if key in LOCATOR_KEYS and isinstance(val, str):
                res = check_locator(val, src)
                node[key + "_match"] = res
                if res["result"] in ("EXACT", "WITHIN", "OVERLAP", "PRESENT", "NOT_FOUND"):
                    findings["locators"].append({"segment_id": seg, "field": key,
                                                 "value": val, **res})
        for v in node.values():
            walk(v, local, findings, src, threshold)
    elif isinstance(node, list):
        for item in node:
            walk(item, ctx, findings, src, threshold)


def build_report(findings, meta):
    q = findings["quotes"]
    n = len(q)
    counts = {k: sum(1 for x in q if x["result"] == k)
              for k in ("EXACT", "FUZZY", "WRONG_UNIT", "NOT_FOUND")}
    loc = findings["locators"]
    loc_bad = [x for x in loc if x["result"] == "NOT_FOUND"]

    def pct(x):
        return f"{(100.0 * x / n):.0f}%" if n else "–"

    L = ["# QDA Quote-/Locator-Validierung\n",
         "> Deterministischer Vergleich mit der Originalquelle. Geprueft wird",
         "> mechanische Treue (Zitat zeichengetreu IN der behaupteten Einheit?",
         "> Locator vorhanden?), NICHT analytische Guete.\n",
         f"- Quelle: `{meta['source_name']}` (SRT: {meta['is_srt']}, Cues: {meta['n_cues']})",
         f"- Quelle-SHA256 (Originalbytes): `{meta['source_sha256'][:16]}…`",
         f"- Modell-JSON: `{meta['json_name']}`",
         f"- Validator: v{VALIDATOR_VERSION} · {meta['timestamp']} · Fuzzy-Schwelle {meta['threshold']}\n",
         "## Zitate\n",
         "| Ergebnis | Anzahl | Anteil |", "|---|---|---|",
         f"| EXACT (zeichengetreu in der Einheit) | {counts['EXACT']} | {pct(counts['EXACT'])} |",
         f"| FUZZY (nah, nicht zeichengetreu) | {counts['FUZZY']} | {pct(counts['FUZZY'])} |",
         f"| WRONG_UNIT (in der Datei, falsche Einheit) | {counts['WRONG_UNIT']} | {pct(counts['WRONG_UNIT'])} |",
         f"| NOT_FOUND (nirgends) | {counts['NOT_FOUND']} | {pct(counts['NOT_FOUND'])} |",
         f"| **gesamt** | **{n}** | |\n"]

    flagged = [x for x in q if x["result"] != "EXACT"]
    if flagged:
        L.append("## Zu pruefen (nicht EXACT)\n")
        for x in flagged:
            L.append(f"- **{x['result']}** (score {x.get('score','?')}) · "
                     f"Einheit {x.get('segment_id','?')}"
                     f"{' · Code: ' + x['code_label'] if x.get('code_label') else ''}")
            L.append(f"  - Modell: „{x['value']}\"")
            if x.get("closest_source"):
                L.append(f"  - Quelle: „{x['closest_source']}\"")
        L.append("")

    L.append("## Locatoren\n")
    if not loc:
        L.append("_Keine Locatoren im JSON._\n")
    else:
        L.append(f"- geprueft: {len(loc)} · vorhanden: {len(loc) - len(loc_bad)} · "
                 f"NICHT gefunden: {len(loc_bad)}")
        for x in loc_bad:
            L.append(f"  - NOT_FOUND · Einheit {x.get('segment_id','?')} · `{x['value']}`")
    L.append("")

    all_exact = (counts["FUZZY"] == 0 and counts["WRONG_UNIT"] == 0
                 and counts["NOT_FOUND"] == 0)
    verdict = "PASS" if (all_exact and not loc_bad) else "REVIEW_REQUIRED"
    L.append(f"## Validator-Ergebnis: **{verdict}**\n")
    L.append("PASS nur, wenn JEDES Zitat zeichengetreu IN seiner Einheit belegt ist "
             "und jeder Locator existiert. FUZZY, WRONG_UNIT und NOT_FOUND sind "
             "Paraphrasen, Fehlbindungen oder Halluzinationen und muessen von der "
             "Forscherin gegen die Quelle geprueft werden.\n")
    return "\n".join(L), {
        "verdict": verdict, "quotes_total": n,
        "quotes_exact": counts["EXACT"], "quotes_fuzzy": counts["FUZZY"],
        "quotes_wrong_unit": counts["WRONG_UNIT"], "quotes_not_found": counts["NOT_FOUND"],
        "locators_total": len(loc), "locators_not_found": len(loc_bad),
    }


def main():
    ap = argparse.ArgumentParser(description="QDA Quote-/Locator-Validator (fail-closed).")
    ap.add_argument("--source", required=True, help="Originalquelle (.srt oder .txt)")
    ap.add_argument("--json", required=True, help="Modell-/gebundene Ausgabe als JSON")
    ap.add_argument("--out", help="Ziel fuer augmentiertes JSON")
    ap.add_argument("--report", help="Ziel fuer Validierungsreport (Markdown)")
    ap.add_argument("--fuzzy-threshold", type=float, default=90.0)
    ap.add_argument(
        "--quiet", action="store_true",
        help="Keine Zitate/Reports nach stdout; nur maschinenlesbares Manifest ausgeben.",
    )
    args = ap.parse_args()

    # Hash der ORIGINAL-Dateibytes (identisch zu qda_segment.py).
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

    findings = {"quotes": [], "locators": []}
    walk(data, {}, findings, src, args.fuzzy_threshold)

    meta = {"source_name": args.source.split("/")[-1], "json_name": args.json.split("/")[-1],
            "source_sha256": source_sha, "is_srt": is_srt, "n_cues": len(cues),
            "threshold": args.fuzzy_threshold,
            "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")}
    report_md, summary = build_report(findings, meta)

    manifest = {"validator_id": "QDA-UTIL-QUOTE-LOCATOR-VALIDATION",
                "validator_version": VALIDATOR_VERSION, "source_sha256": source_sha,
                "timestamp": meta["timestamp"], "result": summary}

    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump({"_qda_validation": manifest, "data": data}, f,
                      ensure_ascii=False, indent=2)
    if args.report:
        with open(args.report, "w", encoding="utf-8") as f:
            f.write(report_md)

    if args.quiet:
        print(json.dumps({"_qda_validation": manifest}, ensure_ascii=False, indent=2))
    else:
        print(report_md)
        print("\n--- Manifest-Fragment ---")
        print(json.dumps(manifest, ensure_ascii=False, indent=2))
    sys.exit(0 if summary["verdict"] == "PASS" else 1)


if __name__ == "__main__":
    main()
