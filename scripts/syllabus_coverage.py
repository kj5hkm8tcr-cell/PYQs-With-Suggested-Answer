#!/usr/bin/env python3
"""How much of each paper's syllabus the last N attempts cover, chapter-wise.

A chapter counts as covered by an attempt when at least one question (descriptive part
or MCQ) of that attempt is on it. Case-scenario MCQs filed under "CS" are resolved to
their own chapters with analysis/cs-chapters/<level>-<paper>.json. "X" (out of
syllabus) parts are ignored.

Writes analysis/syllabus-coverage.json and analysis/syllabus-coverage-chapters.csv.
"""

import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "analysis"


def chapters_asked(paper_file, spec):
    """{attempt: {chapter key: number of questions}}, newest attempt first."""
    cs_file = OUT / "cs-chapters" / f"{paper_file.parent.name}-{paper_file.stem}.json"
    cs = json.loads(cs_file.read_text()) if cs_file.exists() else {}
    asked = {}
    for a in sorted(spec["attempts"], key=lambda a: a["attempt"], reverse=True):
        counts = asked.setdefault(a["attempt"], {})
        for s in a.get("sources") or [a]:
            for pid, ch in s["map"].items():
                if ch == "CS":
                    ch = cs.get(a["attempt"], {}).get(pid)
                    if ch is None:
                        raise SystemExit(f"{paper_file.name} {a['attempt']} {pid}: case-scenario MCQ has no chapter")
                for c in ch if isinstance(ch, list) else [ch]:
                    if c in spec["chapters"]:
                        counts[c] = counts.get(c, 0) + 1
    return asked


def main():
    papers, rows = [], []
    for paper_file in sorted((ROOT / "data").glob("*/*.json")):
        spec = json.loads(paper_file.read_text())
        if not spec.get("chapters"):
            continue  # Final Paper 6 (IBS): case studies, no chapters
        asked = chapters_asked(paper_file, spec)
        attempts = list(asked)
        total = len(spec["chapters"])
        seen, cumulative = set(), []
        for a in attempts:
            seen |= set(asked[a])
            cumulative.append(len(seen))
        chapters = []
        for key, info in spec["chapters"].items():
            hits = [a for a in attempts if key in asked[a]]
            chapters.append({
                "key": key, "name": info["name"], "folder": info.get("folder"),
                "asked_in": len(hits),
                "questions": sum(asked[a].get(key, 0) for a in attempts),
                "first_attempt_needed": attempts.index(hits[0]) + 1 if hits else None,
                "attempts": hits,
            })
            rows.append([spec["level"], spec["paper"], key, info["name"], len(hits), len(attempts),
                         chapters[-1]["questions"], chapters[-1]["first_attempt_needed"] or ""])
        papers.append({
            "level": spec["level"], "paper": spec["paper"], "chapters_total": total,
            "attempts": attempts, "cumulative_covered": cumulative,
            "per_attempt_covered": [len(asked[a]) for a in attempts],
            "attempts_for_full": next((i + 1 for i, n in enumerate(cumulative) if n == total), None),
            "chapters": chapters,
        })
        print(f"{spec['level']:16} {spec['paper'][:40]:40} "
              + " ".join(f"{100 * n / total:4.0f}" for n in cumulative))
    (OUT / "syllabus-coverage.json").write_text(json.dumps(papers, indent=1))
    with open(OUT / "syllabus-coverage-chapters.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["level", "paper", "chapter_key", "chapter", "attempts_asked", "attempts_checked",
                    "questions", "covered_from_attempt_n"])
        w.writerows(rows)


if __name__ == "__main__":
    main()
