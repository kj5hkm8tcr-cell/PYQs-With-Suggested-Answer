"""Rank source pages (study material, RTP, MTP, past papers) for each exam question.

    python3 -I match.py <manifest.json> <questions dir> <out dir>

Score = shared distinctive numbers (IDF-weighted) + shared word 4-grams (IDF-weighted).
Numbers are what make a cost problem recognisable: the same data reused gives many hits.
"""
import json
import math
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

NUM = re.compile(r"(?<![\w.])(\d{1,3}(?:,\d{2,3})+|\d+(?:\.\d+)?)(?![\w])")
WORD = re.compile(r"[a-z]+")
STOP = set("the of and to a in for is be by on as at or an are with from that this which per its it any".split())


def numbers(text):
    out = set()
    for m in NUM.finditer(text):
        s = m.group(1).replace(",", "")
        try:
            v = float(s)
        except ValueError:
            continue
        # skip page/question numbers, years and tiny integers: they match everywhere
        if v < 10 and "." not in s:
            continue
        if 1990 <= v <= 2035 and "." not in s:
            continue
        out.add(s.rstrip("0").rstrip(".") if "." in s else s)
    return out


def grams(text, n=4):
    w = [x for x in WORD.findall(text.lower()) if x not in STOP]
    return {" ".join(w[i:i + n]) for i in range(len(w) - n + 1)}


def pages(txt):
    parts = re.split(r"=== PAGE (\d+) ===", txt)
    if len(parts) < 3:
        return [(1, txt)]
    return [(int(parts[i]), parts[i + 1]) for i in range(1, len(parts), 2)]


def main():
    manifest, qdir, out = json.load(open(sys.argv[1])), Path(sys.argv[2]), Path(sys.argv[3])
    out.mkdir(parents=True, exist_ok=True)
    units = []  # (source idx, page, text, nums, grams)
    for si, src in enumerate(manifest):
        if not src.get("txt") or not Path(src["txt"]).exists():
            continue
        txt = Path(src["txt"]).read_text(errors="ignore")
        pg = pages(txt)
        for i, (p, t) in enumerate(pg):
            # a problem can run over a page break: score each page with the next one
            t2 = t + "\n" + (pg[i + 1][1] if i + 1 < len(pg) else "")
            units.append((si, p, t2, numbers(t2), grams(t2)))
    df_n, df_g = Counter(), Counter()
    for _, _, _, ns, gs in units:
        df_n.update(ns)
        df_g.update(gs)
    N = len(units)
    idf = lambda df, k: math.log(N / (1 + df[k]))
    for qf in sorted(qdir.glob("*.json")):
        attempt = qf.stem
        res = {}
        for key, q in json.load(open(qf)).items():
            text = (q.get("context") or "") + "\n" + q["question"]
            qn, qg = numbers(text), grams(text)
            scored = []
            for si, p, t, ns, gs in units:
                src = manifest[si]
                sa = src.get("attempt") or ""
                # only sources published before the exam: earlier papers; RTP/MTP of that attempt or earlier
                if src["type"] == "pyq" and sa >= attempt:
                    continue
                if src["type"] in ("rtp", "mtp") and sa > attempt:
                    continue
                hn, hg = qn & ns, qg & gs
                if not hn and not hg:
                    continue
                s = sum(idf(df_n, k) for k in hn) + 0.5 * sum(idf(df_g, k) for k in hg)
                scored.append((s, si, p, len(hn), len(qn), len(hg), len(qg)))
            scored.sort(reverse=True)
            best, seen = [], set()
            for s, si, p, hn, nq, hg, ng in scored:
                if (si, p) in seen:
                    continue
                seen.add((si, p))
                src = manifest[si]
                best.append({"score": round(s, 1), "label": src["label"], "part": src.get("part"),
                             "type": src["type"], "page": p, "txt": src["txt"],
                             "numbers_shared": f"{hn}/{nq}", "phrases_shared": f"{hg}/{ng}"})
                if len(best) == 8:
                    break
            res[key] = {"chapter": q.get("chapter"), "question": text[:600], "candidates": best}
        (out / f"{attempt}.json").write_text(json.dumps(res, indent=1, ensure_ascii=False))
        print(attempt, len(res))


if __name__ == "__main__":
    main()
