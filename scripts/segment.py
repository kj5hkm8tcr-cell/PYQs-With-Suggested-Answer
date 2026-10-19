"""Find every question part and its answer inside an ICAI suggested-answers PDF.

ICAI suggested answers repeat each question and then give the answer:

    Question 1
    (a) ...            <- sub-parts start at the left margin
        (i) ...        <- items are indented
    (b) ...
    Answer
    (a) (i) ...
    (b) ...

segment() returns a dict {part_id: {"question": spans, "answer": spans}} where
part_id is "1", "1a", "1a.ii" or "4c-or" (the alternative after an "OR"), and
spans are (page_index, top, bottom) in pdfplumber coordinates (y grows down).
"""

import re

import pdfplumber

LETTERS = "abcdefgh"
ROMANS = ["i", "ii", "iii", "iv", "v", "vi", "vii", "viii", "ix", "x", "xi", "xii"]

RE_QUESTION = re.compile(r"^Questions?\s*(?:No\.?\s*)?(\d{1,2})\b\.?\s*$", re.I)
RE_ANSWER = re.compile(r"^Answers?\b\s*:?\s*$", re.I)
RE_LETTER = re.compile(r"^\(([a-h])\)")
RE_ROMAN = re.compile(r"^(?:\([a-h]\)\s*)?(?:\((?P<r>x|ix|iv|v?i{0,3})\)|(?P<d>x|ix|iv|v?i{1,3}|v)\.\s)")
RE_NUMBERED = re.compile(r"^(?:\([a-h]\)\s*)?(\d{1,2})\.\s")
RE_OR = re.compile(r"^OR$", re.I)
RE_PAGE_NO = re.compile(r"^(\d{1,3}|©.*)$")
RE_HEADER = re.compile(r"SUGGESTED\s*ANSW|EXAMINATION|^PAPER|^[A-Z ,&:\-]+$")


def _lines(pdf):
    """Yield (page_index, line dict) for body lines, plus per-page body bounds."""
    bounds, out = [], []
    for pi, page in enumerate(pdf.pages):
        h = float(page.height)
        lines = page.extract_text_lines(strip=True)
        head = [l for l in lines if l["top"] < 0.16 * h and RE_HEADER.search(l["text"].strip())]
        foot = [l for l in lines if l["top"] > 0.80 * h and RE_PAGE_NO.match(l["text"].strip())]
        top = max((l["bottom"] for l in head), default=0.11 * h) + 2
        bottom = min((l["top"] for l in foot), default=0.86 * h) - 2
        body = [l for l in lines if l["top"] >= top - 1 and l["bottom"] <= bottom + 1]
        if body:  # tighten to the text so header rules / page-number boxes stay out
            top = max(top, min(l["top"] for l in body) - 5)
            bottom = min(bottom, max(l["bottom"] for l in body) + 6)
        bounds.append((top, bottom))
        out.extend((pi, l) for l in body)
    return out, bounds


def _margin(lines):
    """Left margin = most common x0 of 'Question N' / '(a)' lines."""
    xs = [round(l["x0"]) for _, l in lines if RE_QUESTION.match(l["text"]) or RE_LETTER.match(l["text"])]
    return min(xs, key=lambda x: (-xs.count(x), x)) if xs else 108


def _spans(start, end, bounds):
    """Region between two positions (page, top) → list of per-page spans."""
    (p0, y0), (p1, y1) = start, end
    spans = []
    for p in range(p0, p1 + 1):
        top = y0 if p == p0 else bounds[p][0]
        bot = y1 - 2 if p == p1 else bounds[p][1]  # -2: brackets on the next line reach above its "top"
        if bot - top > 4:
            spans.append((p, top, bot))
    return spans


def segment(path):
    with pdfplumber.open(path) as pdf:
        lines, bounds = _lines(pdf)
    margin = _margin(lines)
    at_margin = lambda l: abs(l["x0"] - margin) < 6
    end_pos = (len(bounds) - 1, bounds[-1][1])

    # 1. "Question N" and "Answer" lines split the paper into regions.
    heads = []  # (kind, qno, index into lines)
    for i, (pi, l) in enumerate(lines):
        if at_margin(l) and RE_QUESTION.match(l["text"]):
            heads.append(("Q", int(RE_QUESTION.match(l["text"]).group(1)), i))
        elif at_margin(l) and RE_ANSWER.match(l["text"]) and heads and heads[-1][0] == "Q":
            heads.append(("A", heads[-1][1], i))
    pos_of = lambda i: (lines[i][0], lines[i][1]["top"] - 3) if i < len(lines) else end_pos

    # 2. Inside each region, pick the (a), (b), (c) ... lines that start parts.
    def letters_in(lo, hi, allowed_indented=()):
        found, cur, pending_or = [], "", False
        for i in range(lo, hi):
            l = lines[i][1]
            t = l["text"]
            if RE_OR.match(t) and l["x0"] > margin + 40:
                pending_or = True
                continue
            m = RE_LETTER.match(t)
            if not m:
                continue
            val = m.group(1)
            indented = not at_margin(l)
            if indented and (val not in allowed_indented or l["x0"] > margin + 30):
                continue
            nxt = LETTERS.index(cur) + 1 if cur else 0
            if pending_or and val == cur:
                found.append((val, True, i))
            elif val in LETTERS[nxt:nxt + 2]:  # allow one skipped letter (ICAI typos)
                found.append((val, False, i))
                cur = val
            else:
                continue
            pending_or = False
        return found

    blocks = []  # (qno, side, letter, alt, start index, end index)
    for k, (kind, qno, i) in enumerate(heads):
        if kind != "Q":
            continue
        a = heads[k + 1][2] if k + 1 < len(heads) and heads[k + 1][0] == "A" else None
        nxt = next((h[2] for h in heads[k + 1:] if h[0] == "Q"), len(lines))
        if a is None:
            continue
        q_l, a_l = letters_in(i, a), letters_in(a, nxt)
        qs, as_ = {v for v, _, _ in q_l}, {v for v, _, _ in a_l}
        if qs != as_:  # a part indented on one side only: accept it if the other side has it
            q_l = letters_in(i, a, as_ - qs) if as_ - qs else q_l
            a_l = letters_in(a, nxt, qs - as_) if qs - as_ else a_l
        if not q_l or not a_l:  # "(a), (b)" on one side only are clauses, not parts
            q_l = a_l = []
        # an "OR" alternative on one side only belongs to the part before it
        q_alts = {v for v, alt, _ in q_l if alt}
        a_alts = {v for v, alt, _ in a_l if alt}
        q_l = [x for x in q_l if not x[1] or x[0] in a_alts]
        a_l = [x for x in a_l if not x[1] or x[0] in q_alts]
        # different letters but same count (e.g. question says (c), answer says (b)): pair by order
        if [v for v, _, _ in q_l] != [v for v, _, _ in a_l] and len(q_l) == len(a_l):
            a_l = [(qv, qalt, ai) for (qv, qalt, _), (_, _, ai) in zip(q_l, a_l)]
        # lo skips the "Question N" / "Answer" line itself
        for side, lo, hi, found in (("question", i + 1, a, q_l), ("answer", a + 1, nxt, a_l)):
            cuts = [(lo, "", False)] + [(idx, v, alt) for v, alt, idx in found] + [(hi, None, None)]
            for (s_i, let, alt), (e_i, _, _) in zip(cuts, cuts[1:]):
                blocks.append((qno, side, let, alt, pos_of(s_i), pos_of(e_i)))

    # Roman items (i), (ii) ... for splitting True/False bundles into separate items.
    romans = []
    for b_qno, b_side, b_let, b_alt, b_start, b_end in blocks:
        for pi, l in lines:
            pos = (pi, l["top"] - 3)
            if not (b_start <= pos < b_end):
                continue
            if RE_OR.match(l["text"]) and l["x0"] > margin + 40:
                romans.append(((b_qno, b_side, b_let, b_alt), "OR", pos))
                continue
            if l["x0"] >= margin + 30:
                continue
            m = RE_ROMAN.match(l["text"])
            rom = m and (m.group("r") or m.group("d"))
            if rom in ROMANS:
                romans.append(((b_qno, b_side, b_let, b_alt), rom, pos))
            m = RE_NUMBERED.match(l["text"])
            if m:
                romans.append(((b_qno, b_side, b_let, b_alt), "n" + m.group(1), pos))

    # 3. Turn blocks into parts. A block before the first (a) of a question is
    # the shared stem ("Question 1" line / "Answer" line) and is folded into (a).
    parts = {}
    stems = {}
    for qno, side, let, alt, start, end in blocks:
        if not let:
            stems[(qno, side)] = start
            pid = str(qno)
        else:
            pid = f"{qno}{let}" + ("-or" if alt else "")
        start = stems.get((qno, side), start) if let == "a" and not alt else start
        parts.setdefault(pid, {"question": [], "answer": []})[side] = _spans(start, end, bounds)
        parts[pid].setdefault("_range", {})[side] = (start, end)

    # Drop the bare-number entry when the question has lettered parts.
    for pid in [p for p in parts if p.isdigit()]:
        if any(k.startswith(pid) and not k.isdigit() and k[len(pid)].isalpha() for k in parts):
            del parts[pid]

    # 4. Roman items inside each part, e.g. "1a.ii", for splitting True/False bundles.
    for (qno, side, let, alt), rom, pos in romans:
        pid = (f"{qno}{let}" + ("-or" if alt else "")) if let else str(qno)
        if pid not in parts or side not in parts[pid]["_range"]:
            continue
        parts[pid].setdefault("_romans", {}).setdefault(side, []).append((rom, pos))

    for pid, p in list(parts.items()):
        for side in ("question", "answer"):
            items = p.get("_romans", {}).get(side, [])
            # keep the first run of (i), (ii), (iii) ... in order; ICAI sometimes
            # numbers answers 1., 2., 3. instead, so fall back to that.
            seq = []
            for rom, pos in items:
                if rom != "OR" and not rom.startswith("n") and ROMANS.index(rom) == len(seq):
                    seq.append((rom, pos))
            if len(seq) < 2:
                seq = []
                for rom, pos in items:
                    if rom.startswith("n") and int(rom[1:]) == len(seq) + 1:
                        seq.append((ROMANS[len(seq)], pos))
            ors = [pos for rom, pos in items if rom == "OR"]
            if len(seq) < 2 and side == "answer" and len(ors) == 1 and f"{pid}.ii" in parts \
                    and f"{pid}.iii" not in parts:
                # "either (i) OR (ii)" answered without labels, just split by an "OR" line
                seq = [("i", p["_range"][side][0]), ("ii", ors[0])]
            if len(seq) < 2:
                continue
            start, end = p["_range"][side]
            stem_end = seq[0][1]
            for k, (rom, pos) in enumerate(seq):
                nxt = seq[k + 1][1] if k + 1 < len(seq) else end
                spans = _spans(pos, nxt, bounds)
                if side == "question" and stem_end > start:
                    spans = _spans(start, stem_end, bounds) + spans
                parts.setdefault(f"{pid}.{rom}", {"question": [], "answer": []})[side] = spans

    for p in parts.values():
        p.pop("_range", None)
        p.pop("_romans", None)
    return parts


def text_of(path, spans_by_part, max_chars=600):
    """Plain text of each part's question (for deciding its chapter)."""
    out = {}
    with pdfplumber.open(path) as pdf:
        for pid, p in spans_by_part.items():
            chunks = []
            for pi, top, bot in p["question"]:
                page = pdf.pages[pi]
                crop = page.crop((0, max(top, 0), float(page.width), min(bot, float(page.height))))
                chunks.append(crop.extract_text() or "")
            out[pid] = re.sub(r"\s+", " ", " ".join(chunks)).strip()[:max_chars]
    return out
