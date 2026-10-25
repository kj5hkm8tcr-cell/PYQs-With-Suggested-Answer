#!/usr/bin/env python3
"""Find ICAI's RTPs, MTPs and Model Test Papers and list them in data/<level>/<paper>.json.

Sources (every PDF is downloaded from ICAI's own servers):
  - RTPs: ICAI BoS Knowledge Portal, https://boslive.icai.org/education_content_rtp.php
  - Model Test Papers: https://boslive.icai.org/education_content_modelTestPapers.php
    (one booklet per level/group; each test is found by its "MODEL TEST PAPER n" title page)
  - MTPs: ICAI hosts them at boslive.icai.org/mock_test_paper/..., but lists them only behind
    the student login. The links are taken from public pages that list them (VSI Jaipur), and
    each PDF is identified from its own first page (series, month, level, paper).

Each paper's JSON gets a "practice" list used by build_mcq_practice.py:

    {"type": "RTP", "name": "September 2026", "url": "..."}
    {"type": "MTP", "name": "Series II - August 2025", "url": "...questions.pdf", "answers_url": "...answers.pdf"}
    {"type": "Model", "name": "Model Test Paper 3", "url": "...booklet.pdf", "pages": [172, 190],
     "answer_pages": [800, 803]}

Only papers of the current scheme are kept (Foundation from June 2024, Intermediate and Final
from May 2024). Run again before each attempt to pick up new papers.

Usage:  python scripts/find_rtp_mtp.py
"""

import difflib
import html
import json
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

import pdfplumber

sys.path.insert(0, str(Path(__file__).parent))
from build_pyq import CACHE, ROOT, fetch, sources  # noqa: E402

BOS = "https://boslive.icai.org/"
LEVELS = {"Foundation": "CA Foundation", "Intermediate": "CA Intermediate", "Final": "CA Final"}
MTP_INDEX_PAGES = [
    "https://www.vsijaipur.com/icai-ca-foundation-question-papers/",
    "https://www.vsijaipur.com/icai-ca-intermediate-papers/",
    "https://www.vsijaipur.com/ca-final-papers/",
]
MONTHS = ["january", "february", "march", "april", "may", "june", "july", "august", "september",
          "october", "november", "december"]
FIRST_ATTEMPT = {"CA Foundation": (2024, 6), "CA Intermediate": (2024, 5), "CA Final": (2024, 5)}


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) Chrome/120"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return r.read().decode("utf-8", "replace")


def clean(s):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", s))).strip()


def table_rows(page):
    """(first cell text, pdf link) for every table row with a link."""
    for row in re.findall(r"<tr[^>]*>(.*?)</tr>", page, re.S):
        links = re.findall(r'href="([^"]+\.pdf)"', row, re.I)
        cells = [clean(c) for c in re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)]
        if links and cells:
            yield cells[0], links[0]


def attempt_of(text):
    """'September, 2026' -> (2026, 9)."""
    m = re.search(r"(" + "|".join(MONTHS) + r"|sept?)\w*[,.]?\s*(\d{4})", text, re.I)
    if not m:
        return None
    word = m.group(1).lower()
    month = 9 if word.startswith("sep") else MONTHS.index(word) + 1
    return int(m.group(2)), month


class Papers:
    """The data/<level>/*.json files that have MCQs, matched by paper number and name."""

    def __init__(self):
        self.files = {}
        for f in sorted((ROOT / "data").rglob("*.json")):
            spec = json.loads(f.read_text())
            if spec.get("whole_paper"):
                continue
            if not any(k.startswith("m") for a in spec["attempts"] for s in sources(a) for k in s["map"]):
                continue  # no MCQs in this paper (Foundation Papers 1 and 2)
            num = int(re.search(r"Paper (\d+)", spec["paper"]).group(1))
            name = re.sub(r"^Paper \d+\s*-\s*", "", spec["paper"])
            self.files[(spec["level"], num)] = (f, name)

    def match(self, level, title):
        """Paper title as printed ('PAPER – 3: TAXATION', 'Paper 6A: FM') -> json file."""
        cands = {k: v for k, v in self.files.items() if k[0] == level}
        name = re.sub(r"^.*?PAPER\s*[-–]?\s*\d+\s*[A-B]?\s*[:\-–]?\s*", "", title, flags=re.I).lower()
        ratio = lambda kv: difflib.SequenceMatcher(None, name, kv[1][1].lower()).ratio()
        best = max(cands.items(), key=ratio, default=None)
        if best and ratio(best) > 0.9:  # the name wins over a misprinted paper number
            return best[1][0]
        m = re.search(r"PAPER\s*[-–]?\s*(\d+)", title, re.I)
        if m:  # papers without MCQs (Foundation 1 and 2) are not in cands
            return cands[(level, int(m.group(1)))][0] if (level, int(m.group(1))) in cands else None
        return best[1][0] if best and ratio(best) > 0.6 else None


def rtps(papers):
    out = []
    for c, level in LEVELS.items():
        page = get(f"{BOS}education_content_rtp.php?c={c}")
        for link in sorted(set(re.findall(r'href="([^"]*education_content_rtp_list\.php[^"]*)"', page))):
            year = urllib.parse.unquote(html.unescape(link).split("content_year=")[-1])
            when = attempt_of(year)
            if "hindi" in year.lower() or not when or when < FIRST_ATTEMPT[level]:
                continue
            listing = get(urllib.parse.urljoin(BOS, html.unescape(link).replace(" ", "%20")))
            for title, url in table_rows(listing):
                if not re.search(r"paper", title, re.I):
                    continue  # e.g. whole-group files that repeat the papers
                f = papers.match(level, title)
                if f:
                    part = re.search(r"PAPER\s*[-–]?\s*\d+\s*([AB])\b", title, re.I)
                    name = f"{MONTHS[when[1] - 1].title()} {when[0]}" + (f" - Paper {part.group(0)[-2:].strip()}" if part else "")
                    out.append((f, {"type": "RTP", "name": name, "url": url, "_when": when}))
    return out


def pdf_header(path, lines=12):
    with pdfplumber.open(path) as pdf:
        text = pdf.pages[0].extract_text() or ""
    return [l.strip() for l in text.splitlines()[:lines]]


def mtps(papers):
    links = set()
    for page in MTP_INDEX_PAGES:
        try:
            links |= set(re.findall(r"https://boslive\.icai\.org/mock_test_paper/[A-Za-z0-9_]+\.pdf", get(page)))
        except OSError as e:
            print(f"  ! could not read {page}: {e}")
    pairs = {}
    for url in links:
        m = re.search(r"MTP_(\d+)_(\d+)_(QUESTIONS|ANSWERS)_", url)
        if m:
            pairs.setdefault((m.group(1), m.group(2)), {})[m.group(3)] = url
    out = []
    for (series, paper), p in sorted(pairs.items()):
        if "QUESTIONS" not in p or "ANSWERS" not in p:
            continue
        q = fetch(p["QUESTIONS"], CACHE / "MTP" / Path(p["QUESTIONS"]).name)
        head = " | ".join(pdf_header(q))
        level = next((v for k, v in LEVELS.items() if re.search(k, head, re.I)), None)
        s = re.search(r"Series\s*[-–]?\s*(I{1,3}|\d)\s*[:,]?\s*(\w+)?,?\s*(\d{4})?", head, re.I)
        title = next((t for t in pdf_header(q) if re.search(r"PAPER\s*[-–]?\s*\d", t, re.I)), "")
        f = papers.match(level, title) if level else None
        if not f or not s:
            print(f"  ! MTP {series}_{paper}: could not identify ({head[:120]})")
            continue
        when = attempt_of(f"{s.group(2)} {s.group(3)}") if s.group(3) else None
        part = re.search(r"PAPER\s*[-–]?\s*\d+\s*([AB])\b", title, re.I)
        name = f"Series {s.group(1).upper()}" + (f" - {MONTHS[when[1] - 1].title()} {when[0]}" if when else "") + \
            (f" - Paper {title[part.start(1) - 1:part.end(1)].strip()}" if part else "")
        out.append((f, {"type": "MTP", "name": name, "url": p["QUESTIONS"], "answers_url": p["ANSWERS"],
                         "_when": when or (0, 0)}))
    return out


RE_MODEL = re.compile(r"^(ANSWERS?\s+(?:(?:OF|TO)\s+)?)?MODEL\s+TEST\s+PAPER\s*[-–]?\s*(\d+)?\s*$", re.I)
RE_PAPER_TITLE = re.compile(r"(?<!TEST )PAPER\s*[-–]?\s*\d", re.I)


def models(papers):
    out = []
    for c, level in LEVELS.items():
        page = get(f"{BOS}education_content_modelTestPapers.php?c={c}")
        for title, url in table_rows(page):
            book = fetch(url, CACHE / "Model Test Papers" / Path(url).name)
            print(f"  reading {Path(url).name} ({title})")
            sections = []  # (page, kind, test no, paper title)
            with pdfplumber.open(book) as pdf:
                for pi, pg in enumerate(pdf.pages):
                    head = [l.strip() for l in (pg.extract_text() or "").splitlines()[:8]]
                    k = next((k for k, l in enumerate(head) if RE_MODEL.match(l)), None)
                    if k is None:
                        continue
                    hit = RE_MODEL.match(head[k])
                    # "ANSWERS OF MODEL TEST PAPER" with the number on the next line
                    no = hit.group(2) or (re.match(r"\d+", head[k + 1]).group(0)
                                          if k + 1 < len(head) and re.match(r"\d+", head[k + 1]) else None)
                    ptitle = next((l for l in head if RE_PAPER_TITLE.search(l) and not RE_MODEL.match(l)), "")
                    if no:
                        sections.append((pi, "A" if hit.group(1) else "Q", int(no), ptitle))
                n = len(pdf.pages)
            ranges = {}
            for k, (pi, kind, no, ptitle) in enumerate(sections):
                end = sections[k + 1][0] - 1 if k + 1 < len(sections) else n - 1
                f = papers.match(level, ptitle)
                if f:
                    ranges.setdefault((f, no), {})[kind] = [pi, end]
            for (f, no), r in sorted(ranges.items(), key=lambda kv: (str(kv[0][0]), kv[0][1])):
                if "Q" in r and "A" in r:
                    tag = f" ({title})" if re.search(r"3-?A|6-?A", title) else ""
                    out.append((f, {"type": "Model", "name": f"Model Test Paper {no}{tag}", "url": url,
                                    "pages": r["Q"], "answer_pages": r["A"], "_when": (0, no)}))
    return out


def main():
    papers = Papers()
    found = []
    for kind, fn in (("RTPs", rtps), ("MTPs", mtps), ("Model Test Papers", models)):
        print(f"Finding {kind} ...")
        found += fn(papers)
    by_file = {}
    for f, entry in found:
        by_file.setdefault(f, []).append(entry)
    order = {"RTP": 0, "MTP": 1, "Model": 2}
    for f, entries in by_file.items():
        entries.sort(key=lambda e: (order[e["type"]], tuple(-x for x in e["_when"]), e["name"]))
        seen, practice = set(), []
        for e in entries:
            key = (e["type"], e["url"], tuple(e.get("pages", [])))
            if key in seen:
                continue
            seen.add(key)
            practice.append({k: v for k, v in e.items() if not k.startswith("_")})
        spec = json.loads(f.read_text())
        spec["practice"] = practice
        f.write_text(json.dumps(spec, indent=2, ensure_ascii=False) + "\n")
        counts = {t: sum(1 for e in practice if e["type"] == t) for t in order}
        print(f"  {f.relative_to(ROOT)}: " + ", ".join(f"{v} {k}" for k, v in counts.items() if v))


if __name__ == "__main__":
    main()
