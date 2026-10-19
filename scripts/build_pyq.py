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
import shutil
import sys
import time
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
    if pid.startswith("m"):
        return f"MCQ {pid[1:]}"
    m = re.match(r"(\d+)([a-h]?)(-or)?(?:\.([ivx]+))?$", pid)
    q, letter, alt, rom = m.groups()
    s = f"Question {q}" + (f"({letter})" if letter else "") + (f"({rom})" if rom else "")
    return s + (" (OR)" if alt else "")


def fetch(url, dest):
    if not dest.exists():
        dest.parent.mkdir(parents=True, exist_ok=True)
        print(f"  downloading {url}")
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        for attempt in range(5):
            try:
                with urllib.request.urlopen(req, timeout=120) as r:
                    data = r.read()
                break
            except OSError:
                if attempt == 4:
                    raise
                time.sleep(2 ** (attempt + 1))
        if not data.startswith(b"%PDF"):
            sys.exit(f"  ! {url} did not return a PDF")
        dest.write_bytes(data)
    return dest


def sources(attempt):
    """An attempt has one ICAI PDF ("url" + "map") or several ("sources": [...])."""
    if "sources" in attempt:
        return attempt["sources"]
    return [{"url": attempt["url"], "map": attempt["map"]}]


def chapter_info(key, value):
    """Chapter spec is a name, or {"name": ..., "folder": ...} to group chapters in a subfolder."""
    name, folder = (value, None) if isinstance(value, str) else (value["name"], value.get("folder"))
    # keys like "A-3" keep ICAI's own numbering when it restarts per part (e.g. Income-tax / GST)
    num = re.search(r"(\d+)$", key)
    title = f"Chapter {int(num.group(1)):02d} - {name}" if num else name
    return title, folder


def check_coverage(parts, mapping, where):
    """Every mapped key must exist, and every part must be mapped (directly or via its items)."""
    ok = True
    for key in mapping:
        if key not in parts:
            print(f"  ! {where}: '{key}' is in the map but was not found in the PDF")
            ok = False
        elif not parts[key]["question"] or not (parts[key]["answer"] or parts[key].get("mcq_answer")):
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

    if spec.get("whole_paper"):
        # e.g. Integrated Business Solutions: case studies span all subjects, so each
        # attempt's suggested answers are kept whole instead of being split by chapter
        out_dir = OUT / level / paper
        out_dir.mkdir(parents=True, exist_ok=True)
        for a in spec["attempts"]:
            for s in sources(a):
                src = fetch(s["url"], CACHE / level / paper / Path(s["url"]).name)
                path = out_dir / f"{a['attempt']} - {attempt_name(a['attempt'])} - Case Studies.pdf"
                shutil.copyfile(src, path)
                print(f"  wrote {path.relative_to(ROOT)}")
        return

    by_chapter = {c: [] for c in chapters}  # chapter -> [(attempt, label, src, part)]
    attempts = sorted(spec["attempts"], key=lambda a: a["attempt"], reverse=True)
    ok = True
    for a in attempts:
        srcs = sources(a)
        for s in srcs:
            src = fetch(s["url"], CACHE / level / paper / Path(s["url"]).name)
            parts = segment(str(src))
            tag = f" ({s['note'].split(':')[0]})" if s.get("note") else ""
            if not check_coverage(parts, s["map"], f"{paper} {a['attempt']} {Path(s['url']).name}"):
                ok = False
                continue
            for pid, ch in s["map"].items():
                for c in ch if isinstance(ch, list) else [ch]:
                    if c != "X":
                        by_chapter[str(c)].append((a["attempt"], part_label(pid) + tag, str(src), parts[pid]))
    if not ok:
        sys.exit(1)

    for c, value in chapters.items():
        items = by_chapter[c]
        title, folder = chapter_info(c, value)
        if not items:
            print(f"  (no questions for {title})")
            continue
        out_dir = OUT / level / paper / folder if folder else OUT / level / paper
        out_dir.mkdir(parents=True, exist_ok=True)
        used = sorted({a for a, *_ in items}, reverse=True)
        doc = Composer(f"{level} - {paper} - {title}")
        doc.cover([title, f"{level}  |  {paper}",
                   f"Past year questions with ICAI suggested answers",
                   f"{len(items)} questions from {len(used)} attempts: "
                   f"{attempt_name(used[0])} to {attempt_name(used[-1])}"])
        current, shown_context = None, None
        for attempt, pid, src, part in items:
            if attempt != current:
                current = attempt
                doc.heading(f"{attempt_name(attempt)} Examination", outline_level=0, size=14)
            doc.heading(f"{attempt_name(attempt)}  -  {pid}", outline_level=1, size=11)
            if part.get("context") and shown_context != (src, part["context_id"]):
                # a case scenario is printed once, before the first of its MCQs in this chapter
                shown_context = (src, part["context_id"])
                doc.label("CASE SCENARIO")
                for span in part["context"]:
                    doc.region(src, *span)
            if "mcq_answer" in part:
                doc.keep_together(part["question"], extra=60)
            doc.label("QUESTION")
            for span in part["question"]:
                doc.region(src, *span)
            if "mcq_answer" in part:
                doc.note(part["mcq_answer"], bold_prefix="Correct answer: ")
                continue
            doc.label("SUGGESTED ANSWER")
            for span in part["answer"]:
                doc.region(src, *span)
        path = out_dir / f"{title}.pdf"
        doc.save(path)
        print(f"  wrote {path.relative_to(ROOT)} ({len(items)} questions)")


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    files = args or sorted(str(p) for p in (ROOT / "data").rglob("*.json"))
    for f in files:
        if "--download-only" in sys.argv:
            spec = json.loads(Path(f).read_text())
            for a in spec["attempts"]:
                for s in sources(a):
                    fetch(s["url"], CACHE / spec["level"] / spec["paper"] / Path(s["url"]).name)
        else:
            build(f)


if __name__ == "__main__":
    main()
