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
part_id is "1", "1a", "1a.ii" or "4c-or" (the alternative after an "OR"), or "m5"
for MCQ 5 (see segment_mcq), and spans are (page_index, top, bottom) in pdfplumber
coordinates (y grows down).
"""

import re

import pdfplumber

LETTERS = "abcdefgh"
ROMANS = ["i", "ii", "iii", "iv", "v", "vi", "vii", "viii", "ix", "x", "xi", "xii", "xiii", "xiv", "xv",
          "xvi", "xvii", "xviii", "xix", "xx", "xxi", "xxii", "xxiii", "xxiv", "xxv"]

# ICAI PDFs sometimes split words ("Answ er"), so allow stray spaces inside the keywords
RE_QUESTION = re.compile(r"^Q\s?u\s?e\s?s\s?t\s?i\s?o\s?n\s?s?\s*(?:No\.?\s*)?(\d{1,2})\b\.?\s*$", re.I)
RE_ANSWER = re.compile(r"^A\s?n\s?s\s?w\s?e\s?r\s?s?\s*:?\s*$", re.I)
RE_LETTER = re.compile(r"^\(([a-h])\)")
RE_ROMAN = re.compile(r"^(?:\([a-h]\)\s*)?(?:\((?P<r>x{0,2}(?:ix|iv|v?i{0,3}))\)|(?P<d>x{0,2}(?:ix|iv|v?i{1,3}|v))\.\s)")
RE_NUMBERED = re.compile(r"^(?:\([a-h]\)\s*)?(\d{1,2})\.\s")
RE_OR = re.compile(r"^OR$", re.I)
RE_PAGE_NO = re.compile(r"^(\d{1,3}|©.*)$")
# Headings and exam instructions between two questions, e.g. "SECTION B – BUSINESS
# CORRESPONDENCE AND REPORTING" / "Attempt any four questions ...". Headings must be
# centred so that answer lines like "Section 135 of the Companies Act" are never matched.
RE_SECTION_HEAD = re.compile(r"^(SECTION|PART)\b|^(Section|Part)\s*[-–:]?\s*(?:[A-D]|I{1,3}|IV|V|VI)\b(?!\s*of\b)")
RE_INSTRUCTION = re.compile(r"^Questions?\s*No\.?\s*1\s*is\s*compulsory|^(Answer|Attempt)\s+any\b"
                            r"|^Working\s+notes?\s+should|^All\s+questions\b|^Candidates\s+are\b"
                            r"|^In\s+case,?\s*any\s+candidate|^Wherever\s+necessary"
                            r"|^\(i\)\s*Question\s+paper\s+comprises", re.I)
RE_HEADER = re.compile(r"SUGGESTED\s*ANSW|EXAMINATION|^PAPER|^[A-Z ,&:\-]+$")


def _lines(pdf):
    """Yield (page_index, line dict) for body lines, plus per-page body bounds."""
    bounds, out = [], []
    for pi, page in enumerate(pdf.pages):
        h = float(page.height)
        lines = page.extract_text_lines(strip=True)
        head = [l for l in lines if l["top"] < 0.16 * h and RE_HEADER.search(l["text"].strip())]
        # the page number is the lowest numeric line near the foot (a low "16" in a
        # fraction near the bottom of the text is not the page number)
        nums = [l for l in lines if l["top"] > 0.80 * h and RE_PAGE_NO.match(l["text"].strip())]
        foot = [max(nums, key=lambda l: l["top"])] if nums else []
        top = max((l["bottom"] for l in head), default=0.11 * h) + 2
        bottom = min((l["top"] for l in foot), default=0.86 * h) - 2
        body = [l for l in lines if l["top"] >= top - 1 and l["bottom"] <= bottom + 1]
        if body:  # tighten to the text so header rules / page-number boxes stay out
            top = max(top, min(l["top"] for l in body) - 5)
            last = max(l["bottom"] for l in body)
            # stop above decorations (e.g. ICAI's page-number badge) that start just
            # below the text and reach far down; thin rules right under the text stay in
            deco = [o["top"] for o in page.lines + page.curves + page.rects
                    if last - 0.5 < o["top"] < last + 6 and o["bottom"] > last + 12]
            bottom = min(bottom, last + 6, min(deco, default=bottom) - 0.5)
        bounds.append((top, bottom))
        out.extend((pi, l) for l in body)
    return out, bounds


def _ink(pdf):
    """Vertical extent (top, bottom) of everything printed on each page: characters and
    drawn lines/curves such as fraction bars and square-root signs."""
    ink = []
    for page in pdf.pages:
        objs = [(c["top"], c["bottom"]) for c in page.chars if c["text"].strip()]
        objs += [(o["top"], o["bottom"]) for o in page.lines + page.curves + page.rects
                 if o["bottom"] - o["top"] < 60]
        ink.append(sorted(objs))
    return ink


def _cut_above(ink, bounds, pi, line):
    """Where to cut so that a question starting at `line` keeps everything printed on its
    first row: numerators of fractions and square-root signs rise above the text line."""
    t, b = line["top"], line["bottom"]
    top = t
    while True:  # grow upwards over anything touching the row (root bars sit on the root sign)
        new = min([o_t for o_t, o_b in ink[pi] if o_t < b - 1 and o_b >= top - 0.5 and o_t >= t - 25] + [top])
        if new >= top:
            break
        top = new
    above = [o_b for o_t, o_b in ink[pi] if o_b < top - 0.5 and o_b > top - 40]
    prev = max(above, default=top - 6)
    cut = (prev + top) / 2 if top - prev < 6 else top - 3
    return (pi, max(cut, bounds[pi][0]))


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
        bot = y1 if p == p1 else bounds[p][1]  # y1 is already a cut in blank space (_cut_above)
        if bot - top > 4:
            spans.append((p, top, bot))
    return spans


def segment(path):
    with pdfplumber.open(path) as pdf:
        lines, bounds = _lines(pdf)
        ink = _ink(pdf)
    margin = _margin(lines)
    at_margin = lambda l: abs(l["x0"] - margin) < 4
    end_pos = (len(bounds) - 1, bounds[-1][1])

    # 1. "Question N" and "Answer" lines split the paper into regions.
    heads = []  # (kind, qno, index into lines)
    for i, (pi, l) in enumerate(lines):
        if at_margin(l) and RE_QUESTION.match(l["text"]):
            heads.append(("Q", int(RE_QUESTION.match(l["text"]).group(1)), i))
        elif at_margin(l) and RE_ANSWER.match(l["text"]) and heads and heads[-1][0] == "Q":
            heads.append(("A", heads[-1][1], i))
    pos_of = lambda i: _cut_above(ink, bounds, *lines[i]) if i < len(lines) else end_pos

    # 2. Inside each region, pick the (a), (b), (c) ... lines that start parts.
    def letters_in(lo, hi, allowed_indented=(), dup_is_next=False):
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
            if dup_is_next and val == cur and not pending_or and nxt < len(LETTERS):
                val = LETTERS[nxt]  # ICAI typo: the same letter printed twice
            if pending_or and val == cur:
                found.append((val, True, i))
            elif val in LETTERS[nxt:nxt + 2]:  # allow one skipped letter (ICAI typos)
                found.append((val, False, i))
                cur = val
            else:
                continue
            pending_or = False
        return found

    def trim_end(s_i, e_i):
        """Drop section headings and exam instructions that sit between this block and
        the next question ("SECTION B – BUSINESS CORRESPONDENCE", "Attempt any four ...")."""
        for k in range(max(s_i + 1, e_i - 12), e_i):
            l = lines[k][1]
            if (RE_SECTION_HEAD.match(l["text"]) and l["x0"] > margin + 30 or RE_INSTRUCTION.match(l["text"])) \
                    and not any(at_margin(lines[j][1]) and RE_LETTER.match(lines[j][1]["text"]) for j in range(k, e_i)):
                return k
        return e_i

    blocks = []  # (qno, side, letter, alt, start index, end index)
    for k, (kind, qno, i) in enumerate(heads):
        if kind != "Q":
            continue
        a = heads[k + 1][2] if k + 1 < len(heads) and heads[k + 1][0] == "A" else None
        nxt = next((h[2] for h in heads[k + 1:] if h[0] == "Q"), len(lines))
        if a is None:
            continue
        q_l, a_l = letters_in(i, a), letters_in(a, nxt)
        if not q_l or not a_l:  # "(a), (b)" on one side only are clauses or table rows, not parts
            q_l = a_l = []
        key = lambda found: [(v, alt) for v, alt, _ in found]
        if key(q_l) != key(a_l):
            # part (a) answered straight after "Answer" with no "(a)" label
            if key(q_l)[1:] == key(a_l) and key(q_l)[0] == ("a", False):
                a_l = [("a", False, a + 1)] + a_l
            elif key(a_l)[1:] == key(q_l) and key(a_l)[0] == ("a", False):
                q_l = [("a", False, i + 1)] + q_l
        if key(q_l) != key(a_l):
            qs, as_ = {v for v, _, _ in q_l}, {v for v, _, _ in a_l}
            # a part indented on one side only: accept it if the other side has it
            if as_ - qs:
                q_l = letters_in(i, a, as_ - qs)
            if qs - as_:
                a_l = letters_in(a, nxt, qs - as_)
            # the same letter printed twice on one side
            if len(q_l) < len(a_l):
                q_l = letters_in(i, a, dup_is_next=True)
            elif len(a_l) < len(q_l):
                a_l = letters_in(a, nxt, dup_is_next=True)
        if key(q_l) != key(a_l):
            if len(q_l) == len(a_l):
                # same number of parts, labelled differently (e.g. question "(d)" = answer "(c) OR"):
                # pair by order and use the question's labels
                a_l = [(qv, qalt, ai) for (qv, qalt, _), (_, _, ai) in zip(q_l, a_l)]
            else:
                # an "OR" alternative on one side only belongs to the part before it
                q_alts = {v for v, alt, _ in q_l if alt}
                a_alts = {v for v, alt, _ in a_l if alt}
                q_l = [x for x in q_l if not x[1] or x[0] in a_alts]
                a_l = [x for x in a_l if not x[1] or x[0] in q_alts]
                if len(q_l) == len(a_l):
                    a_l = [(qv, qalt, ai) for (qv, qalt, _), (_, _, ai) in zip(q_l, a_l)]
                else:
                    # can't pair the parts reliably: keep the whole question as one unit
                    q_l = a_l = []
        for side, lo, hi, found in (("question", i + 1, a, q_l), ("answer", a + 1, nxt, a_l)):
            cuts = [(lo, "", False)] + [(idx, v, alt) for v, alt, idx in found] + [(hi, None, None)]
            for (s_i, let, alt), (e_i, _, _) in zip(cuts, cuts[1:]):
                blocks.append((qno, side, let, alt, pos_of(s_i), pos_of(trim_end(s_i, e_i))))

    # Roman items (i), (ii) ... for splitting True/False bundles into separate items.
    romans = []
    for b_qno, b_side, b_let, b_alt, b_start, b_end in blocks:
        for pi, l in lines:
            pos = _cut_above(ink, bounds, pi, l)
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
    # Parts other than (a) get the stem separately as "stem", so a part filed in another
    # chapter still shows the shared introduction of its question.
    parts = {}
    stems = {}
    for qno, side, let, alt, start, end in blocks:
        if not let:
            stems[(qno, side)] = (start, end)
            pid = str(qno)
        else:
            pid = f"{qno}{let}" + ("-or" if alt else "")
        stem = stems.get((qno, side))
        if let == "a" and not alt and stem:
            start = stem[0]
        parts.setdefault(pid, {"question": [], "answer": []})[side] = _spans(start, end, bounds)
        parts[pid].setdefault("_range", {})[side] = (start, end)
        if let and side == "question" and not (let == "a" and not alt) and stem:
            stem_spans = _spans(*stem, bounds)
            if sum(b - t for _, t, b in stem_spans) > 12:  # at least one line of text
                parts[pid]["stem"] = stem_spans

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
                    if rom.startswith("n") and int(rom[1:]) == len(seq) + 1 and len(seq) < len(ROMANS):
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
                item = parts.setdefault(f"{pid}.{rom}", {"question": [], "answer": [], "own": []})
                if side == "question":
                    item["own"] = spans  # the item without the shared stem
                    if stem_end > start:
                        spans = _spans(start, stem_end, bounds) + spans
                item[side] = spans
        # items are only usable when question and answer have the same ones
        items = [k for k in parts if k.startswith(pid + ".")]
        if any(not parts[k]["question"] or not parts[k]["answer"] for k in items):
            for k in items:
                del parts[k]

    for p in parts.values():
        p.pop("_range", None)
        p.pop("_romans", None)
    parts.update(segment_mcq(path))
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


# ---------------------------------------------------------------------------
# MCQs (Part I of Inter/Final papers; all of Foundation Papers 3 and 4)
#
#   Case Scenario - I            <- shared context for the MCQs it introduces
#   ... answer Question Nos. 1 to 3
#   1. ...  (A) ... (D) ...
#   2. ...
#   Answer Key                   <- table "1. (B)  2. (C) ..." after the MCQs
#
# segment_mcq() returns {"m1": {"question": spans, "answer": [], "mcq_answer": "(B)",
#                               "context": spans, "context_id": "cs1"}, ...}

RE_SCENARIO = re.compile(r"^(?:Integrated\s+)?(?:Case\s*(?:Scenario|Study)\b|Scenario\s*[-–:]?\s*[IVX\d]+\b)", re.I)
RE_SHARED = re.compile(r"^(Use|Based on|Read|Refer|Consider|Study|On the basis of|From the|With the help of|Answer)\b"
                       r".*\b(following|given|below|above)\b", re.I)
RE_MCQ = re.compile(r"^(\d{1,3})\s*(?:\.+|\s(?=[A-Z]))\s*\S")  # "18 Calculate": ICAI sometimes drops the dot
RE_KEY_HEAD = re.compile(r"^(?:Answers?\s*Key|ANSWERS?|Answers? to (?:MCQs?|Part).*|ANSWER TO PART.*MCQS?"
                         r"|MCQ\.?\s*No\.?\s*(?:Correct|Answer).*)\s*:?\s*$", re.I)
RE_DESCRIPTIVE = re.compile(r"PART\s*[–-]?\s*(?:II|2)\b|Descriptive\s+Questions", re.I)
RE_KEY_CELL = re.compile(r"(\d{1,3})\s*\.{0,2}\s+((?:\(\s*[A-Da-d]?\s*\)|No correct option|None of the)[^()\d]*?(?:\(\s*[A-Da-d]\s*\))?\s*[*∗]?)(?=\s+\d{1,3}\s*\.|\s*$)")


def _range_in(text):
    m = re.search(r"Q(?:uestion)?s?\.?\s*(?:No\.?|Nos\.?)?\s*(\d{1,3})\s*(?:to|and|-|–|&)\s*"
                  r"(?:Q(?:uestion)?\.?\s*(?:No\.?|Nos\.?)?\s*)?(\d{1,3})", text, re.I)
    return (int(m.group(1)), int(m.group(2))) if m else None


RE_KEY_NUM = re.compile(r"^(\d{1,3})\.{0,2}$")
RE_CELL_START = re.compile(r"^(\(|[A-Da-d]$|[A-Da-d][.,):]|No$|None|Either|Option|All|Both)")


def _read_key(path, lines, bounds, key, end, expected=()):
    """Parse the answer key between line indexes key..end into {mcq no: answer text}.

    Handles "1. (B)", "1. B", "1. Option (D): text", grids with several answers per
    row, and answers that wrap onto the next line (matched to their column by x).
    """
    p0, y0 = lines[key][0], lines[key][1]["bottom"]
    p1, y1 = (lines[end][0], lines[end][1]["top"]) if end < len(lines) else (len(bounds) - 1, bounds[-1][1])
    rows = []
    with pdfplumber.open(path) as pdf:
        for pi in range(p0, p1 + 1):
            lo = y0 if pi == p0 else bounds[pi][0]
            hi = y1 if pi == p1 else bounds[pi][1]
            words = [w for w in pdf.pages[pi].extract_words() if lo < w["top"] < hi]
            for w in sorted(words, key=lambda w: w["top"]):
                if rows and rows[-1][0] == pi and w["top"] - rows[-1][1] < 4:
                    rows[-1][2].append(w)
                else:
                    rows.append((pi, w["top"], [w]))
    answers, notes, last = {}, [], []  # last: [(x, n)] cells of the previous numbered row
    prev = None
    for pi, top, words in rows:
        words.sort(key=lambda w: w["x0"])
        text = " ".join(w["text"] for w in words)
        # the key is over once every MCQ has an answer and the layout breaks off
        if expected and all(n in answers for n in expected) and prev and \
                (pi != prev[0] or top - prev[1] > 30) and not text.lstrip().startswith(("*", "∗")):
            break
        prev = (pi, top)
        if text.lstrip().startswith(("*", "∗")):
            notes.append(text.strip())
            continue
        cells = []
        for k, w in enumerate(words):
            m = RE_KEY_NUM.match(w["text"])
            nxt = words[k + 1]["text"] if k + 1 < len(words) else ""
            if m and (w["text"].endswith(".") or RE_CELL_START.match(nxt)) and 0 < int(m.group(1)) <= 200:
                cells.append([w["x0"], int(m.group(1)), []])
            elif cells:
                cells[-1][2].append(w["text"])
            elif last:  # continuation line: belongs to the column it sits under
                x, n = max(((x, n) for x, n in last if x <= w["x0"] + 5), default=last[0])
                answers[n] = answers.get(n, "") + " " + w["text"]
        for x, n, ws in cells:
            answers[n] = " ".join(ws)
        if cells:
            last = [(x, n) for x, n, _ in cells]
    answers = {n: re.sub(r"\s+", " ", a).strip() for n, a in answers.items() if a.strip()}
    return answers, notes


def segment_mcq(path):
    with pdfplumber.open(path) as pdf:
        lines, bounds = _lines(pdf)
        ink = _ink(pdf)
    if not lines:
        return {}
    margin = _margin(lines) if any(RE_QUESTION.match(l["text"]) for _, l in lines) else \
        min((round(l["x0"]) for _, l in lines if RE_MCQ.match(l["text"])), default=108)
    near = lambda l: abs(l["x0"] - margin) < 8

    # MCQ section ends at the descriptive part ("Question 1" / "PART II").
    end = next((i for i, (_, l) in enumerate(lines)
                if RE_QUESTION.match(l["text"]) and near(l) or RE_DESCRIPTIVE.search(l["text"])), len(lines))
    keys = [i for i in range(end) if RE_KEY_HEAD.match(lines[i][1]["text"])]
    if not keys:
        return {}
    pos = lambda i: _cut_above(ink, bounds, *lines[i]) if i < len(lines) else (len(bounds) - 1, bounds[-1][1])
    RE_SECTION = re.compile(r"^(SECTION|PART)\b", re.I)

    # A paper can have several MCQ blocks (e.g. Income Tax and GST), each ending in
    # its own answer key; numbering continues across blocks.
    starts, scen, answers, notes = [], [], {}, []
    expect, lo, block_ends = 1, 0, []
    for key in keys:
        if key < lo:
            continue  # a second heading line of the same key ("Answer Key" + "MCQ No. ...")
        block = []
        last_was_mcq = True  # whether the latest marker seen is an MCQ (not a scenario)
        blocked_until = -1   # numbered notes inside a scenario are not MCQs
        for i in range(lo, key):
            l = lines[i][1]
            if near(l) and RE_SCENARIO.match(l["text"]):
                scen.append(i)
                last_was_mcq = False
                # MCQs start after the line naming them ("answer Question Nos. 4 to 9")
                nxt_s = next((j for j in range(i + 1, key) if near(lines[j][1])
                              and RE_SCENARIO.match(lines[j][1]["text"])), key)
                blocked_until = next((j for j in range(i + 1, nxt_s) if _range_in(
                    " ".join(lines[k][1]["text"] for k in range(max(i + 1, j - 1), j + 1)))), -1)
                continue
            if i <= blocked_until:
                continue
            m = RE_MCQ.match(l["text"])
            if m and near(l) and int(m.group(1)) == expect:
                block.append((expect, i))
                expect += 1
                last_was_mcq = True
            elif last_was_mcq and RE_SHARED.match(l["text"]) and l["x0"] < margin + 30 and _range_in(
                    " ".join(lines[j][1]["text"] for j in range(i, min(i + 2, key)))):
                # "Use the following data to answer questions 26 and 27": data shared by
                # several MCQs, treated like a small case scenario
                scen.append(i)
                last_was_mcq = False
        # the key runs until the next block starts
        key_end = next((i for i in range(key + 1, end)
                        if (near(lines[i][1]) and RE_SCENARIO.match(lines[i][1]["text"]))
                        or RE_SECTION.match(lines[i][1]["text"])
                        or (RE_MCQ.match(lines[i][1]["text"]) and near(lines[i][1])
                            and int(RE_MCQ.match(lines[i][1]["text"]).group(1)) == expect
                            and not RE_KEY_CELL.search(lines[i][1]["text"]))), end)
        a, nt = _read_key(path, lines, bounds, key, key_end, expected=[n for n, _ in block])
        answers.update({n: v for n, v in a.items() if any(n == b for b, _ in block)})
        notes += nt
        starts += block
        block_ends.append(key)
        lo = key_end
    if not starts:
        return {}
    key = block_ends[-1]

    # Each scenario covers its heading up to its first MCQ; the MCQs it applies to
    # are those named in "Question Nos. x to y", else all until the next scenario.
    contexts = []
    for k, si in enumerate(scen):
        first = next((n for n, i in starts if i > si), None)
        if first is None:
            continue
        first_i = dict(starts)[first]
        text = " ".join(lines[j][1]["text"] for j in range(si, first_i))
        nxt = min([j for j in scen[k + 1:]] + [b for b in block_ends if b > si] + [len(lines)])
        rng = _range_in(text) or (first, max([n for n, i in starts if i < nxt], default=first))
        contexts.append((f"cs{k + 1}", _spans(pos(si), pos(first_i), bounds), rng))

    stops = sorted([i for _, i in starts] + scen + block_ends)
    out = {}
    for n, i in starts:
        nxt = next(s for s in stops if s > i)
        ctx = next(((cid, sp) for cid, sp, (a, b) in contexts if a <= n <= b), (None, []))
        ans = answers.get(n, "")
        note = " ".join(notes) if "*" in ans or "∗" in ans or "()" in ans.replace(" ", "") else ""
        out[f"m{n}"] = {"question": _spans(pos(i), pos(nxt), bounds), "answer": [],
                        "mcq_answer": (ans + (" " + note if note else "")).strip(),
                        "context": ctx[1], "context_id": ctx[0]}
    return out
