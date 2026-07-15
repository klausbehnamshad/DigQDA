#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
QDA P0 — SEGMENTIERUNG (v0.1, DRAFT)

Deterministische Vor-Segmentierung fuer die VERBA reference utilities.
KEIN Modell. P0 trifft KEINE analytischen Entscheidungen — es zerlegt die
Quelle nur an *beobachtbaren* Grenzen (Cue-Pausen bzw. Leerzeilen) in
handhabbare Kodierfenster mit exakt uebernommenen Locatoren. Die eigentliche
analytische Segmentierung (Zusammenfassen zu bedeutungsvollen Einheiten) bleibt
Sache von P1 / der Forscherin.

Unterstuetzte Quellen:
  .srt  -> Fenster aus aufeinanderfolgenden Cues (Timecode-Range je Fenster)
  .txt  -> Absaetze (durch Leerzeilen getrennt); Locator = Zeilen-/Zeichen-Range

Aufruf:
  python3 qda_segment.py --source interview.srt --out segments.json
  python3 qda_segment.py --source interview.txt --out segments.json
  python3 qda_segment.py --source i.srt --mode cue           # 1 Segment je Cue
  python3 qda_segment.py --source i.srt --max-gap-ms 1500 --max-chars 1000

Jedes Segment ist so gebaut, dass es einzeln in den P1-Prompt gepastet werden
kann. Die Locatoren sind spaeter mit qda_validate.py pruefbar.
"""

import argparse
import hashlib
import json
import re
import sys
import unicodedata

TIMECODE_RE = re.compile(r"(\d{2}):(\d{2}):(\d{2})[,\.](\d{3})")
# Sprecherlabel am Zeilenanfang, z.B. "B:", "I:", "IP2:", "Interviewer:".
SPEAKER_RE = re.compile(r"^\s*([A-Za-z0-9ÄÖÜäöüß_.\-]{1,15}):\s")


def detect_speaker(text):
    m = SPEAKER_RE.match(text or "")
    return m.group(1) if m else None


def resolve_speakers(texts):
    """Deterministische, nicht erschlossene Sprecherbindung.

    Nur Labels, die WÖRTLICH am Zeilenanfang stehen, werden übernommen.
    Kein Label -> 'not stated'. Uneinheitliche Labels -> 'multiple'.
    """
    found = [s for s in (detect_speaker(t) for t in texts) if s]
    uniq = sorted(set(found))
    if not uniq:
        return "not stated"
    if len(uniq) == 1:
        return uniq[0]
    return "multiple"


def tc_to_ms(h, m, s, ms):
    return ((int(h) * 60 + int(m)) * 60 + int(s)) * 1000 + int(ms)


def ms_to_tc(ms):
    h = ms // 3_600_000
    ms -= h * 3_600_000
    m = ms // 60_000
    ms -= m * 60_000
    s = ms // 1000
    ms -= s * 1000
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


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
                cues.append({
                    "index": idx,
                    "start_ms": tc_to_ms(*tcs[0]),
                    "end_ms": tc_to_ms(*tcs[1]),
                    "text": " ".join(lines[i + 1:]).strip(),
                })
                break
    return cues


def segment_srt(cues, mode, max_gap_ms, max_chars):
    segments = []
    if not cues:
        return segments

    def flush(group):
        if not group:
            return
        uid = f"S{len(segments) + 1:02d}"
        text = " ".join(c["text"] for c in group).strip()
        segments.append({
            "unit_id": uid,
            "source_type": "srt",
            "source_range": f"{ms_to_tc(group[0]['start_ms'])} --> {ms_to_tc(group[-1]['end_ms'])}",
            "explicit_speaker": resolve_speakers([c["text"] for c in group]),
            "cue_indices": [c["index"] for c in group],
            "n_cues": len(group),
            "source_text": text,
        })

    if mode == "cue":
        for c in cues:
            flush([c])
        return segments

    # mode == "window": Grenze bei Pause > max_gap_ms ODER Zeichenbudget ueberschritten
    group = []
    for c in cues:
        if group:
            gap = c["start_ms"] - group[-1]["end_ms"]
            cur_len = sum(len(x["text"]) + 1 for x in group)
            if gap > max_gap_ms or cur_len + len(c["text"]) > max_chars:
                flush(group)
                group = []
        group.append(c)
    flush(group)
    return segments


def segment_txt(raw, max_chars):
    """Absatzweise (Leerzeilen-getrennt); Locator = Zeilen- und Zeichen-Range."""
    segments = []
    lines = raw.splitlines()
    # Char-Offset je Zeilenanfang (1-indexierte Zeilen).
    line_start_char = []
    pos = 0
    for ln in lines:
        line_start_char.append(pos)
        pos += len(ln) + 1  # +1 fuer den Zeilenumbruch

    # Absaetze als Bloecke nicht-leerer Zeilen.
    i = 0
    n = len(lines)
    while i < n:
        if lines[i].strip() == "":
            i += 1
            continue
        j = i
        while j < n and lines[j].strip() != "":
            j += 1
        block_lines = lines[i:j]
        text = " ".join(l.strip() for l in block_lines).strip()
        char_start = line_start_char[i]
        char_end = line_start_char[j - 1] + len(lines[j - 1])
        uid = f"S{len(segments) + 1:02d}"
        seg = {
            "unit_id": uid,
            "source_type": "txt",
            "source_range": f"L{i + 1}-L{j}",
            "explicit_speaker": resolve_speakers(block_lines),
            "line_start": i + 1,
            "line_end": j,
            "char_start": char_start,
            "char_end": char_end,
            "source_text": text,
        }
        if len(text) > max_chars:
            seg["warning"] = (f"Absatz laenger als max_chars ({len(text)}>{max_chars}); "
                              f"ggf. manuell teilen oder num_ctx erhoehen.")
        segments.append(seg)
        i = j
    return segments


def main():
    ap = argparse.ArgumentParser(description="QDA P0 — deterministische Segmentierung (SRT/TXT).")
    ap.add_argument("--source", required=True, help=".srt oder .txt")
    ap.add_argument("--out", help="Ziel-JSON (sonst stdout)")
    ap.add_argument("--mode", choices=["window", "cue"], default="window",
                    help="SRT: window (Cues zu Fenstern) oder cue (1 Segment/Cue). Default window.")
    ap.add_argument("--max-gap-ms", type=int, default=2000,
                    help="SRT: Pause > diesem Wert beendet ein Fenster (Default 2000).")
    ap.add_argument("--max-chars", type=int, default=1200,
                    help="Weiches Zeichenbudget je Fenster/Absatz (Default 1200).")
    args = ap.parse_args()

    # Hash der ORIGINAL-Dateibytes (identisch zu qda_validate.py), erst DANACH
    # fuer die Verarbeitung normalisieren.
    with open(args.source, "rb") as f:
        raw_bytes = f.read()
    sha = hashlib.sha256(raw_bytes).hexdigest()
    raw = unicodedata.normalize("NFC", raw_bytes.decode("utf-8"))

    cues = parse_srt(raw)
    if cues:
        source_type = "srt"
        segments = segment_srt(cues, args.mode, args.max_gap_ms, args.max_chars)
    else:
        source_type = "txt"
        segments = segment_txt(raw, args.max_chars)

    out = {
        "meta": {
            "source": args.source.split("/")[-1],
            "source_type": source_type,
            "source_sha256": sha,
            "mode": args.mode if source_type == "srt" else "paragraph",
            "params": {"max_gap_ms": args.max_gap_ms, "max_chars": args.max_chars},
            "n_units": len(segments),
            "note": "source_units sind mechanische Verarbeitungseinheiten, keine "
                    "analytischen Segmente. Analytische Segmentierung bleibt P1/Mensch.",
        },
        "source_units": segments,
    }
    text = json.dumps(out, ensure_ascii=False, indent=2)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(text)
        sys.stderr.write(f"{len(segments)} source_units ({source_type}) -> {args.out}\n")
    else:
        print(text)


if __name__ == "__main__":
    main()
