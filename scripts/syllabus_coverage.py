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
DEPTH = 3  # questions per chapter that count as "practised", not just "seen once"


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
                for c in map(str, ch if isinstance(ch, list) else [ch]):
                    if c in spec["chapters"]:
                        counts[c] = counts.get(c, 0) + 1
    return asked


def recommended(cumulative, depth, total):
    """Fewest attempts that show every chapter ever asked and give 3+ questions on at
    least 90% of the chapters (or as many as the attempts available ever do)."""
    target = min(0.9 * total, depth[-1])
    return next(i + 1 for i in range(len(cumulative))
                if cumulative[i] == cumulative[-1] and depth[i] >= target)


def main():
    papers, rows = [], []
    for paper_file in sorted((ROOT / "data").glob("*/*.json")):
        spec = json.loads(paper_file.read_text())
        if not spec.get("chapters"):
            continue  # Final Paper 6 (IBS): case studies, no chapters
        asked = chapters_asked(paper_file, spec)
        attempts = list(asked)
        total = len(spec["chapters"])
        seen, cumulative, depth, running = set(), [], [], {}
        for a in attempts:
            seen |= set(asked[a])
            cumulative.append(len(seen))
            for c, n in asked[a].items():
                running[c] = running.get(c, 0) + n
            depth.append(sum(1 for n in running.values() if n >= DEPTH))
        chapters = []
        for key, info in spec["chapters"].items():
            info = info if isinstance(info, dict) else {"name": info}
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
            "cumulative_with_depth": depth, "depth": DEPTH,
            "per_attempt_covered": [len(asked[a]) for a in attempts],
            "attempts_for_full": next((i + 1 for i, n in enumerate(cumulative) if n == total), None),
            "attempts_for_depth": next((i + 1 for i, n in enumerate(depth) if n == len(seen)), None),
            "recommended_attempts": recommended(cumulative, depth, total),
            "chapters": chapters,
        })
        print(f"{spec['level']:16} {spec['paper'][:40]:40} "
              + " ".join(f"{100 * n / total:4.0f}" for n in cumulative)
              + "  | depth " + " ".join(f"{100 * n / total:4.0f}" for n in depth))
    (OUT / "syllabus-coverage.json").write_text(json.dumps(papers, indent=1))
    with open(OUT / "syllabus-coverage-chapters.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["level", "paper", "chapter_key", "chapter", "attempts_asked", "attempts_checked",
                    "questions", "covered_from_attempt_n"])
        w.writerows(rows)


if __name__ == "__main__":
    main()
