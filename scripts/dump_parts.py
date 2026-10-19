#!/usr/bin/env python3
"""Print the question text of every part in a paper's ICAI PDFs, for assigning chapters.

    python scripts/dump_parts.py data/intermediate/paper-2-corporate-and-other-laws.json

For each attempt and source PDF it lists the keys that the JSON "map" must cover:
  - descriptive parts: "1a", "2b-or", "5" ...; items inside a part ("1a.ii") are listed
    under it and may be mapped instead of the part when they belong to different chapters
  - MCQs: "m1" ... with the case scenario they belong to ("cs2")
"""

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from build_pyq import CACHE, fetch, sources  # noqa: E402
from segment import segment, text_of  # noqa: E402


def main():
    spec = json.loads(Path(sys.argv[1]).read_text())
    width = int(sys.argv[2]) if len(sys.argv) > 2 else 350
    for a in sorted(spec["attempts"], key=lambda a: a["attempt"], reverse=True):
        for i, s in enumerate(sources(a)):
            src = fetch(s["url"], CACHE / spec["level"] / spec["paper"] / Path(s["url"]).name)
            parts = segment(str(src))
            texts = text_of(str(src), parts, width)
            own = text_of(str(src), {k: {"question": v["own"]} for k, v in parts.items() if v.get("own")}, 220)
            ctx_texts = text_of(str(src), {k: {"question": v["context"]} for k, v in parts.items()
                                           if v.get("context")}, 250)
            print(f"\n##### attempt {a['attempt']}  source[{i}] {Path(s['url']).name}  {s.get('note', '')}")
            shown = set()
            for pid, p in parts.items():
                if "." in pid:
                    continue
                if p.get("context_id") and p["context_id"] not in shown:
                    shown.add(p["context_id"])
                    print(f"  [{p['context_id']} case scenario] {ctx_texts.get(pid, '')}")
                print(f"{pid}: {texts[pid]}" + (f"   [answer: {p['mcq_answer'][:60]}]" if p.get("mcq_answer") else ""))
                for sub in [k for k in parts if k.startswith(pid + ".")]:
                    print(f"    {sub}: {own.get(sub, texts[sub])}")


if __name__ == "__main__":
    main()
