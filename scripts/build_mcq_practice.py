#!/usr/bin/env python3
"""Build the data for the MCQ practice site (mcq-practice/index.html).

For every paper in data/ that has MCQs, each MCQ is cut out of ICAI's PDF as an image
(so formulas, tables and the ₹ sign look exactly as ICAI printed them), together with
its case scenario and the correct option from ICAI's answer key:

    mcq-practice/data/index.js          <- list of papers, chapters and question sets
    mcq-practice/data/<paper>.js        <- that paper's MCQs, loaded when it is opened
    mcq-practice/data/img/<paper>/...   <- question and case scenario images

Sets come from the PYQ attempts already in data/<level>/<paper>.json (chapter-wise via
their "map") and from an optional "practice" list in the same file for RTPs and MTPs:

    "practice": [
      {"type": "RTP", "name": "September 2026", "url": "https://.../rtp.pdf"},
      {"type": "MTP", "name": "September 2026 - Series I", "url": "https://.../mtp-q.pdf",
       "answers_url": "https://.../mtp-a.pdf"}
    ]

RTP/MTP sets are paper-wise only; add a "map" (same format as attempts) to file them
under chapters too. "answers_url" is for MTPs whose answer key is a separate PDF.

The output contains ICAI's copyrighted text and is git-ignored (see README).

Usage:
    python scripts/build_mcq_practice.py                 # every paper
    python scripts/build_mcq_practice.py data/foundation/paper-3-quantitative-aptitude.json
"""

import json
import re
import sys
from pathlib import Path

import pdfplumber
import pypdfium2
from PIL import Image

sys.path.insert(0, str(Path(__file__).parent))
from build_pyq import CACHE, ROOT, attempt_name, fetch, sources  # noqa: E402
from segment import _lines, segment_mcq  # noqa: E402

OUT = ROOT / "mcq-practice" / "data"
SCALE = 2.0  # render at 144 dpi: sharp on phones, small enough as 16-grey PNGs
LEVELS = ["CA Foundation", "CA Intermediate", "CA Final"]


def slug(text):
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def parse_answer(raw):
    """ICAI key text -> (correct letters, note). "No correct option" -> ([], note)."""
    text = raw.strip()
    if re.match(r"No correct option|None\b", text, re.I):
        note = re.sub(r"^[^*∗]*[*∗]+\s*", "", text) if re.search(r"[*∗]", text) else text
        return [], note.strip("*∗ ") or "ICAI: no option is correct."
    # "(B)", "B", "Option (D): ...", "(A & B)", "(B/C)", "(A) or (C)"
    m = re.match(r"(?:Either\s*)?(?:Option\s*)?\(?\s*([A-Da-d](?:\s*\)?\s*(?:&|/|,|or|and)\s*\(?\s*[A-Da-d])*)\s*(?:\)|$|[\s.,:*∗])",
                 text, re.I)
    letters = re.findall(r"[A-Da-d]", re.sub(r"(?i)\b(?:or|and)\b", "", m.group(1))) if m else []
    letters = sorted({c.upper() for c in letters})
    note = ""
    if re.search(r"[*∗]", text):
        note = re.sub(r"^[^*∗]*[*∗]+\s*", "", text).strip("*∗ ")
    elif len(letters) > 1:
        note = "ICAI accepts any of these options."
    return letters, note


class Renderer:
    """Cuts (page, top, bottom) spans out of one PDF and saves them as one image."""

    def __init__(self, path):
        self.pdf = pypdfium2.PdfDocument(path)
        self.pages = {}
        with pdfplumber.open(path) as plumb:
            # left/right edges of the text on each page, so images carry no wide margins
            self.xs = []
            for page in plumb.pages:
                chars = [c for c in page.chars if c["text"].strip()]
                w = float(page.width)
                x0 = min((c["x0"] for c in chars), default=0.08 * w)
                x1 = max((c["x1"] for c in chars), default=0.92 * w)
                self.xs.append((max(0, x0 - 6), min(w, x1 + 6)))

    def page(self, pi):
        if pi not in self.pages:
            self.pages[pi] = self.pdf[pi].render(scale=SCALE, grayscale=True).to_pil().convert("L")
        return self.pages[pi]

    def save(self, spans, dest):
        if not spans:
            return None
        crops = []
        for pi, top, bot in spans:
            img = self.page(pi)
            x0, x1 = self.xs[pi]
            crops.append(img.crop((int(x0 * SCALE), int(top * SCALE), int(x1 * SCALE), int(bot * SCALE))))
        width = max(c.width for c in crops)
        out = Image.new("L", (width, sum(c.height for c in crops)), 255)
        y = 0
        for c in crops:
            out.paste(c, (0, y))
            y += c.height
        dest.parent.mkdir(parents=True, exist_ok=True)
        out.quantize(16).save(dest, optimize=True)
        return dest


def answer_key_only(path):
    """Answers from a separate MTP answer PDF: lines like "1. (B)" or a key table."""
    answers = {}
    with pdfplumber.open(path) as pdf:
        lines, _ = _lines(pdf)
    text = "\n".join(l["text"] for _, l in lines)
    for n, a in re.findall(r"(?m)(?:^|\s)(\d{1,3})\s*\.?\s*\(\s*([A-Da-d])\s*\)", text):
        answers.setdefault(int(n), f"({a.upper()})")
    return answers


def build_set(spec_dir, set_id, src_path, mapping, answers_path=None):
    """One attempt / RTP / MTP -> (questions, contexts) with images written to disk."""
    parts = segment_mcq(str(src_path))
    if answers_path:
        extra = answer_key_only(str(answers_path))
        for pid, p in parts.items():
            if not p["mcq_answer"] and int(pid[1:]) in extra:
                p["mcq_answer"] = extra[int(pid[1:])]
    render = Renderer(str(src_path))
    img_dir = OUT / "img" / spec_dir
    questions, contexts, problems = [], {}, []
    for pid in sorted(parts, key=lambda k: int(k[1:])):
        p = parts[pid]
        ch = mapping.get(pid) if mapping else None
        if ch == "X" or re.match(r"Out of syllabus", p["mcq_answer"], re.I):
            continue  # out of the current syllabus
        if mapping and ch is None:
            problems.append(f"{pid} has no chapter in the map")
        letters, note = parse_answer(p["mcq_answer"])
        if not letters and not note:
            problems.append(f"{pid} has no answer in ICAI's key ({p['mcq_answer']!r})")
            continue
        ctx = None
        if p.get("context"):
            ctx = f"{set_id}-{p['context_id']}"
            if ctx not in contexts:
                render.save(p["context"], img_dir / f"{ctx}.png")
                contexts[ctx] = f"img/{spec_dir}/{ctx}.png"
        render.save(p["question"], img_dir / f"{set_id}-{pid}.png")
        questions.append({
            "id": f"{set_id}-{pid}",
            "no": int(pid[1:]),
            "img": f"img/{spec_dir}/{set_id}-{pid}.png",
            "ctx": ctx,
            "ans": letters,
            "note": note,
            "ch": [] if ch is None else [str(c) for c in (ch if isinstance(ch, list) else [ch])],
        })
    return questions, contexts, problems


def build(data_file):
    spec = json.loads(Path(data_file).read_text())
    level, paper = spec["level"], spec["paper"]
    if spec.get("whole_paper"):
        return None  # case studies spanning all subjects, kept as whole PDFs
    key = slug(f"{level} {paper}")
    print(f"{level} / {paper}")
    sets, contexts = [], {}

    jobs = []
    for a in sorted(spec["attempts"], key=lambda a: a["attempt"], reverse=True):
        srcs = sources(a)
        for si, s in enumerate(srcs):
            # e.g. Inter Taxation May 2025 was two PDFs (Income-tax / GST): one set each
            part = f" - {s['note'].split(':')[0]}" if s.get("note") and len(srcs) > 1 else ""
            jobs.append(("PYQ", f"{attempt_name(a['attempt'])}{part}", f"pyq-{a['attempt']}-{si}",
                         s["url"], s.get("map", {}), None))
    for k, s in enumerate(spec.get("practice", [])):
        jobs.append((s["type"].upper(), s["name"], f"{s['type'].lower()}-{k}", s["url"], s.get("map"),
                     s.get("answers_url")))

    for kind, name, set_id, url, mapping, answers_url in jobs:
        src = fetch(url, CACHE / level / paper / Path(url).name)
        ans = fetch(answers_url, CACHE / level / paper / Path(answers_url).name) if answers_url else None
        qs, cs, problems = build_set(key, set_id, src, mapping, ans)
        for msg in problems:
            print(f"  ! {paper} {kind} {name}: {msg}")
        if not qs:
            continue
        sets.append({"id": set_id, "type": kind, "name": name, "questions": qs})
        contexts.update(cs)
        print(f"  {kind} {name}: {len(qs)} MCQs")
    if not sets:
        print("  (no MCQs)")
        return None

    chapters = []
    for ck, v in spec["chapters"].items():
        name, folder = (v, None) if isinstance(v, str) else (v["name"], v.get("folder"))
        num = re.search(r"(\d+)$", ck)
        chapters.append({"key": ck, "name": f"Chapter {int(num.group(1))} - {name}" if num else name,
                         "group": folder})
    used = {c for s in sets for q in s["questions"] for c in q["ch"]}
    chapters = [c for c in chapters if c["key"] in used]

    paper_data = {"key": key, "contexts": contexts, "sets": sets}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{key}.js").write_text(
        f"MCQ.loaded({json.dumps(paper_data, ensure_ascii=False, separators=(',', ':'))});\n")
    return {
        "key": key, "level": level, "paper": paper, "chapters": chapters,
        "hasCaseScenario": "CS" in used,
        "sets": [{"id": s["id"], "type": s["type"], "name": s["name"], "count": len(s["questions"])}
                 for s in sets],
        "count": sum(len(s["questions"]) for s in sets),
    }


def main():
    files = sys.argv[1:] or sorted(str(p) for p in (ROOT / "data").rglob("*.json"))
    from concurrent.futures import ProcessPoolExecutor
    with ProcessPoolExecutor() as pool:
        built = [p for p in pool.map(build, files) if p]
    index_file = OUT / "index.js"
    # building one paper keeps the others already in the index
    old = []
    if index_file.exists() and sys.argv[1:]:
        old = json.loads(re.search(r"MCQ\.index\((.*)\);", index_file.read_text(), re.S).group(1))
    papers = {p["key"]: p for p in old}
    papers.update({p["key"]: p for p in built})
    order = lambda p: (LEVELS.index(p["level"]), int(re.search(r"Paper (\d+)", p["paper"]).group(1)))
    papers = sorted(papers.values(), key=order)
    index_file.write_text(f"MCQ.index({json.dumps(papers, ensure_ascii=False, indent=1)});\n")
    print(f"wrote {index_file.relative_to(ROOT)}: {sum(p['count'] for p in papers)} MCQs "
          f"in {len(papers)} papers")


if __name__ == "__main__":
    main()
