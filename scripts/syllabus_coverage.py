#!/usr/bin/env python3
"""How much of each paper's syllabus the last N attempts cover, chapter-wise.

A chapter counts as covered by an attempt when at least one question (descriptive part
or MCQ) of that attempt is on it. Case-scenario MCQs filed under "CS" are resolved to
their own chapters with analysis/cs-chapters/<level>-<paper>.json. "X" (out of
syllabus) parts are ignored.

Attempts come from the paper's data file (ICAI suggested answers) plus
analysis/question-papers/<level>-<paper>.json for attempts whose question paper is out
but whose suggested answers are not yet. Only the newest LAST attempts are counted.

Writes analysis/syllabus-coverage.json, analysis/syllabus-coverage-by-attempt.csv
(period-wise cumulative coverage) and analysis/syllabus-coverage-chapters.csv.
Pass level names (e.g. `foundation`) to run only those levels; the files then get a suffix.
"""

import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from build_pyq import attempt_name, sources  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "analysis"
LAST = 10  # attempts counted, newest first
DEPTH = 3  # questions per chapter that count as "practised", not just "seen once"


def chapters_asked(paper_file, spec):
    """{attempt: {chapter key: number of questions}} for the newest LAST attempts, newest first."""
    name = f"{paper_file.parent.name}-{paper_file.stem}.json"
    cs_file = OUT / "cs-chapters" / name
    cs = json.loads(cs_file.read_text()) if cs_file.exists() else {}
    qp_file = OUT / "question-papers" / name
    maps = {}  # attempt -> [(map, source)]
    for a in spec["attempts"]:
        maps[a["attempt"]] = [(s["map"], "suggested answers") for s in sources(a)]
    if qp_file.exists():
        for attempt, qp in json.loads(qp_file.read_text()).items():
            if attempt not in maps:  # suggested answers, once out, take over
                maps[attempt] = [(qp["map"], "question paper")]
    asked, kind = {}, {}
    for attempt in sorted(maps, reverse=True)[:LAST]:
        if not any(m for m, _ in maps[attempt]):
            raise SystemExit(f"{paper_file.name} {attempt}: map is empty")
        counts = asked.setdefault(attempt, {})
        kind[attempt] = maps[attempt][0][1]
        for m, _ in maps[attempt]:
            for pid, ch in m.items():
                if ch == "CS":
                    ch = cs.get(attempt, {}).get(pid)
                    if ch is None:
                        raise SystemExit(f"{paper_file.name} {attempt} {pid}: case-scenario MCQ has no chapter")
                for c in map(str, ch if isinstance(ch, list) else [ch]):
                    if c in spec["chapters"]:
                        counts[c] = counts.get(c, 0) + 1
    return asked, kind


def recommended(cumulative, depth, total):
    """Fewest attempts that show every chapter ever asked and give 3+ questions on at
    least 90% of the chapters (or as many as the attempts available ever do)."""
    target = min(0.9 * total, depth[-1])
    return next(i + 1 for i in range(len(cumulative))
                if cumulative[i] == cumulative[-1] and depth[i] >= target)


def main():
    levels = sys.argv[1:]  # e.g. "foundation": only those levels, written to *-foundation files
    suffix = "".join(f"-{lv}" for lv in levels)
    papers, rows, period_rows = [], [], []
    for paper_file in sorted((ROOT / "data").glob("*/*.json")):
        if levels and paper_file.parent.name not in levels:
            continue
        spec = json.loads(paper_file.read_text())
        if not spec.get("chapters"):
            continue  # Final Paper 6 (IBS): case studies, no chapters
        asked, kind = chapters_asked(paper_file, spec)
        attempts = list(asked)
        names = {str(k): (v if isinstance(v, str) else v["name"]) for k, v in spec["chapters"].items()}
        total = len(names)
        seen, cumulative, depth, running, periods = set(), [], [], {}, []
        for i, a in enumerate(attempts):
            new = [c for c in names if c in asked[a] and c not in seen]
            seen |= set(asked[a])
            cumulative.append(len(seen))
            for c, n in asked[a].items():
                running[c] = running.get(c, 0) + n
            depth.append(sum(1 for n in running.values() if n >= DEPTH))
            periods.append({"n": i + 1, "attempt": a, "label": attempt_name(a), "source": kind[a],
                            "chapters_in_attempt": len(asked[a]), "cumulative_seen": cumulative[-1],
                            "cumulative_practised": depth[-1], "new_chapters": new})
            period_rows.append([spec["level"], spec["paper"], i + 1, attempt_name(a), kind[a], total,
                                len(asked[a]), round(100 * len(asked[a]) / total),
                                cumulative[-1], round(100 * cumulative[-1] / total),
                                depth[-1], round(100 * depth[-1] / total),
                                "; ".join(f"{c} {names[c]}" for c in new)])
        chapters = []
        for key, name in names.items():
            hits = [a for a in attempts if key in asked[a]]
            chapters.append({
                "key": key, "name": name,
                "asked_in": len(hits),
                "questions": sum(asked[a].get(key, 0) for a in attempts),
                "first_attempt_needed": attempts.index(hits[0]) + 1 if hits else None,
                "attempts": hits,
            })
            rows.append([spec["level"], spec["paper"], key, name, len(hits), len(attempts),
                         chapters[-1]["questions"], chapters[-1]["first_attempt_needed"] or "",
                         ", ".join(attempt_name(a) for a in hits)])
        papers.append({
            "level": spec["level"], "paper": spec["paper"], "chapters_total": total,
            "attempts": attempts, "periods": periods, "cumulative_covered": cumulative,
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
    (OUT / f"syllabus-coverage{suffix}.json").write_text(json.dumps(papers, indent=1))
    with open(OUT / f"syllabus-coverage-by-attempt{suffix}.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["level", "paper", "attempts_solved", "attempt", "source", "chapters_total",
                    "chapters_in_this_attempt", "pct_in_this_attempt", "cumulative_chapters_seen",
                    "cumulative_seen_pct", "cumulative_chapters_practised_3plus", "cumulative_practised_pct",
                    "new_chapters_this_attempt"])
        w.writerows(period_rows)
    with open(OUT / f"syllabus-coverage-chapters{suffix}.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["level", "paper", "chapter_key", "chapter", "attempts_asked", "attempts_checked",
                    "questions", "covered_from_attempt_n", "asked_in"])
        w.writerows(rows)


if __name__ == "__main__":
    main()
