#!/usr/bin/env python3
"""Check a paper's chapter map without building PDFs.

    python scripts/check_maps.py data/intermediate/paper-3-taxation.json [attempt]

For each attempt (or just the one given): every part in the ICAI PDF is mapped, every
mapped key exists, every chapter key is known, and every "CS" MCQ has its chapter in
analysis/cs-chapters/<level>-<paper>.json.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from build_pyq import CACHE, check_coverage, fetch, sources  # noqa: E402
from segment import segment  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def main():
    paper_file = Path(sys.argv[1])
    only = sys.argv[2] if len(sys.argv) > 2 else None
    spec = json.loads(paper_file.read_text())
    cs_file = ROOT / "analysis" / "cs-chapters" / f"{paper_file.parent.name}-{paper_file.stem}.json"
    cs = json.loads(cs_file.read_text()) if cs_file.exists() else {}
    chapters = {str(k) for k in spec["chapters"]}
    ok = True
    for a in spec["attempts"]:
        if only and a["attempt"] != only:
            continue
        for s in sources(a):
            src = fetch(s["url"], CACHE / spec["level"] / spec["paper"] / Path(s["url"]).name)
            where = f"{a['attempt']} {Path(s['url']).name}"
            ok &= check_coverage(segment(str(src)), s["map"], where)
            for pid, ch in s["map"].items():
                for c in map(str, ch if isinstance(ch, list) else [ch]):
                    if c == "CS":
                        cc = cs.get(a["attempt"], {}).get(pid)
                        for x in map(str, cc if isinstance(cc, list) else [cc]):
                            if x not in chapters:
                                print(f"  ! {where}: CS MCQ '{pid}' has chapter {cc!r} in {cs_file.name}")
                                ok = False
                    elif c != "X" and c not in chapters:
                        print(f"  ! {where}: '{pid}' is mapped to unknown chapter '{c}'")
                        ok = False
    print("OK" if ok else "PROBLEMS FOUND")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
