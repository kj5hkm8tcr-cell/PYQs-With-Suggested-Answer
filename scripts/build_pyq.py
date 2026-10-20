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


def order_key(pid):
    """Paper order: MCQs first by number, then Question 1(a), 1(a) OR, 1(a)(ii), 1(b) ..."""
    if pid.startswith("m"):
        return (0, int(pid[1:]), "", 0, 0)
    m = re.match(r"(\d+)([a-h]?)(-or)?(?:\.([ivx]+))?$", pid)
    q, letter, alt, rom = m.groups()
    romans = ["i", "ii", "iii", "iv", "v", "vi", "vii", "viii", "ix", "x", "xi", "xii", "xiii", "xiv", "xv",
              "xvi", "xvii", "xviii", "xix", "xx", "xxi", "xxii", "xxiii", "xxiv", "xxv"]
    return (1, int(q), letter, 1 if alt else 0, romans.index(rom) + 1 if rom else 0)


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
    if key == "CS":
        return value, None
    # file names must work on Windows/Drive: no : " / \\ ? * < > |
    name = re.sub(r"\s*:\s*", " - ", name)
    name = re.sub(r'["/\\?*<>|]', "", name)
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

    # "CS" collects case scenarios whose MCQs span several chapters; they get their own
    # file after the last chapter so the scenario stays together with all its MCQs
    numbers = [int(m.group(1)) for k in chapters for m in [re.search(r"(\d+)$", k)] if m]
    flat = all(k.isdigit() for k in chapters)
    chapters = dict(chapters, CS=f"Chapter {max(numbers, default=0) + 1:02d} - Case Scenario MCQs (Multiple Chapters)"
                    if flat else "Case Scenario MCQs (Multiple Chapters)")
    by_chapter = {c: [] for c in chapters}  # chapter -> [(attempt, label, src, part)]
    attempts = sorted(spec["attempts"], key=lambda a: a["attempt"], reverse=True)
    ok = True
    for a in attempts:
        srcs = sources(a)
        for si, s in enumerate(srcs):
            src = fetch(s["url"], CACHE / level / paper / Path(s["url"]).name)
            parts = segment(str(src))
            tag = f" ({s['note'].split(':')[0]})" if s.get("note") else ""
            if not check_coverage(parts, s["map"], f"{paper} {a['attempt']} {Path(s['url']).name}"):
                ok = False
                continue
            for pid, ch in s["map"].items():
                for c in ch if isinstance(ch, list) else [ch]:
                    if c == "X":
                        continue
                    if str(c) not in by_chapter:
                        print(f"  ! {paper} {a['attempt']}: '{pid}' is mapped to unknown chapter '{c}'")
                        ok = False
                    else:
                        by_chapter[str(c)].append((a["attempt"], (si, order_key(pid)), part_label(pid) + tag,
                                                   str(src), parts[pid]))
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
        # paper order within each attempt: MCQs (Part I) first, then Question 1, 2, 3 ...
        items.sort(key=lambda it: (-int(it[0].replace("-", "")), it[1]))
        used = sorted({it[0] for it in items}, reverse=True)
        doc = Composer(f"{level} - {paper} - {title}")
        doc.cover([title, f"{level}  |  {paper}",
                   f"Past year questions with ICAI suggested answers",
                   f"{len(items)} questions from {len(used)} attempts: "
                   f"{attempt_name(used[0])} to {attempt_name(used[-1])}"])
        current, shown_context = None, None
        for k, (attempt, _, label, src, part) in enumerate(items):
            name = attempt_name(attempt)
            if attempt != current:
                current, shown_context = attempt, None
                doc.heading(f"{name} Examination", outline_level=0, size=14)
            ctx = (src, part.get("context_id")) if part.get("context") else None
            if ctx and ctx != shown_context:
                # the complete case comes first, then each of its MCQs with its answer
                shown_context = ctx
                group = [it[2] for it in items[k:] if it[0] == attempt and it[3] == src
                         and it[4].get("context_id") == part["context_id"]]
                span = group[0] if len(group) == 1 else f"{group[0]} to {group[-1].replace('MCQ ', '')}"
                doc.heading(f"{name}  -  Case Scenario: {span}", outline_level=1, size=12)
                for region in part["context"]:
                    doc.region(src, *region)
            elif not ctx:
                shown_context = None
            if "mcq_answer" in part:
                doc.keep_together(part["question"], extra=70)
                doc.heading(f"{name}  -  {label}", outline_level=1, size=11)
                for region in part["question"]:
                    doc.region(src, *region)
                doc.answer_box(part["mcq_answer"])
                continue
            doc.heading(f"{name}  -  {label}", outline_level=1, size=11)
            doc.label("QUESTION")
            for region in part.get("stem", []) + part["question"]:
                doc.region(src, *region)
            doc.label("SUGGESTED ANSWER", highlight=True)
            for region in part["answer"]:
                doc.region(src, *region)
        path = out_dir / f"{title}.pdf"
        doc.save(path)
        print(f"  wrote {path.relative_to(ROOT)} ({len(items)} questions)")


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    files = args or sorted(str(p) for p in (ROOT / "data").rglob("*.json"))
    if "--download-only" in sys.argv:
        for f in files:
            spec = json.loads(Path(f).read_text())
            for a in spec["attempts"]:
                for s in sources(a):
                    fetch(s["url"], CACHE / spec["level"] / spec["paper"] / Path(s["url"]).name)
        return
    # papers are independent, so build them in parallel
    from concurrent.futures import ProcessPoolExecutor
    with ProcessPoolExecutor() as pool:
        list(pool.map(build, files))


if __name__ == "__main__":
    main()
