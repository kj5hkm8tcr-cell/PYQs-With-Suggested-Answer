#!/usr/bin/env python3
"""Build chapter-wise PYQ PDFs from ICAI suggested answers.

For every data/<level>/<paper>.json file:
  1. download each attempt's ICAI suggested-answers PDF into cache/,
  2. cut out every question part with its answer (scripts/segment.py),
  3. file each part under the chapter given in the JSON "map",
  4. write one PDF per chapter, newest attempt first:

     Google Drive Upload/<Level>/<Paper>/Chapter NN - <Name>.pdf

Usage:
    python scripts/build_pyq.py                     # everything
    python scripts/build_pyq.py data/foundation/paper-1-accounting.json
"""

import json
import re
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from compose import Composer  # noqa: E402
from segment import segment  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "cache"
OUT = ROOT / "Google Drive Upload"
MONTHS = ["", "January", "February", "March", "April", "May", "June", "July",
          "August", "September", "October", "November", "December"]


def attempt_name(a):
    y, m = a.split("-")
    return f"{MONTHS[int(m)]} {y}"


def part_label(pid):
    """'1a.ii' -> 'Question 1(a)(ii)', '3c-or' -> 'Question 3(c) (OR)'."""
    m = re.match(r"(\d+)([a-h]?)(-or)?(?:\.([ivx]+))?$", pid)
    q, letter, alt, rom = m.groups()
    s = f"Question {q}" + (f"({letter})" if letter else "") + (f"({rom})" if rom else "")
    return s + (" (OR)" if alt else "")


def fetch(url, dest):
    if not dest.exists():
        dest.parent.mkdir(parents=True, exist_ok=True)
        print(f"  downloading {url}")
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=120) as r:
            dest.write_bytes(r.read())
    return dest


def check_coverage(parts, mapping, where):
    """Every mapped key must exist, and every part must be mapped (directly or via its items)."""
    ok = True
    for key in mapping:
        if key not in parts:
            print(f"  ! {where}: '{key}' is in the map but was not found in the PDF")
            ok = False
        elif not parts[key]["question"] or not parts[key]["answer"]:
            print(f"  ! {where}: '{key}' is missing its question or answer text")
            ok = False
    for pid in parts:
        if "." in pid:
            continue
        if pid not in mapping and not any(k.startswith(pid + ".") for k in mapping):
            print(f"  ! {where}: part '{pid}' has no chapter in the map")
            ok = False
    return ok


def build(data_file):
    spec = json.loads(Path(data_file).read_text())
    level, paper, chapters = spec["level"], spec["paper"], spec["chapters"]
    print(f"{level} / {paper}")

    by_chapter = {c: [] for c in chapters}  # chapter -> [(attempt, pid, src, part)]
    attempts = sorted(spec["attempts"], key=lambda a: a["attempt"], reverse=True)
    for a in attempts:
        src = fetch(a["url"], CACHE / level / paper / f"{a['attempt']}.pdf")
        parts = segment(str(src))
        if not check_coverage(parts, a["map"], f"{paper} {a['attempt']}"):
            sys.exit(1)
        for pid, ch in a["map"].items():
            for c in ch if isinstance(ch, list) else [ch]:
                if c != "X":
                    by_chapter[str(c)].append((a["attempt"], pid, str(src), parts[pid]))

    out_dir = OUT / level / paper
    out_dir.mkdir(parents=True, exist_ok=True)
    for c, name in chapters.items():
        items = by_chapter[c]
        if not items:
            print(f"  (no questions for chapter {c})")
            continue
        title = f"Chapter {int(c):02d} - {name}"
        used = sorted({a for a, *_ in items}, reverse=True)
        doc = Composer(f"{level} - {paper} - {title}")
        doc.cover([title, f"{level}  |  {paper}",
                   f"Past year questions with ICAI suggested answers",
                   f"{len(items)} questions from {len(used)} attempts: "
                   f"{attempt_name(used[0])} to {attempt_name(used[-1])}"])
        current = None
        for attempt, pid, src, part in items:
            if attempt != current:
                current = attempt
                doc.heading(f"{attempt_name(attempt)} Examination", outline_level=0, size=14)
            doc.heading(f"{attempt_name(attempt)}  -  {part_label(pid)}", outline_level=1, size=11)
            doc.label("QUESTION")
            for span in part["question"]:
                doc.region(src, *span)
            doc.label("SUGGESTED ANSWER")
            for span in part["answer"]:
                doc.region(src, *span)
        path = out_dir / f"{title}.pdf"
        doc.save(path)
        print(f"  wrote {path.relative_to(ROOT)} ({len(items)} questions)")


def main():
    files = sys.argv[1:] or sorted(str(p) for p in (ROOT / "data").rglob("*.json"))
    for f in files:
        build(f)


if __name__ == "__main__":
    main()
