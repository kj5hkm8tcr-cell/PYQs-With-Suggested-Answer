"""Find the MCQs and their answers in ICAI RTPs, MTPs and Model Test Papers.

These papers are laid out differently from the suggested answers (segment.py):

    QUESTIONS                              Mock Test Paper (questions PDF)
    1. If 2n-1 + 2n+1 = 320 ...            1. Mr. Suraj aged 38 ... (facts (a)..(j))
       (a) 6   (b) 8 ...                      (i) Which of the following ...
    ...                                           (a) ... (b) ... (c) ... (d) ...
    Case Scenario                             (ii) ...
    <facts> ... Questions 1 to 5 below     2. ...  (a) ... (d)
    1. ...  (a) ... (d)
    SUGGESTED ANSWERS                      Answers PDF / answers section:
    1. (d) 2. (a) 3. (d) ...               1. (i) (b)     2. (c)
    1. Option (c) ` 12                         (ii) (c)   3. (c)

segment_practice(questions_pdf, answers_pdf=None) returns a list of MCQs in paper order:

    {"key": "1.ii", "label": "1(ii)", "question": spans, "context": spans, "context_id": "c3",
     "answer": "(B)", "options": "letter"}

"options" is "roman" when the options are printed (i)-(iv); answers are always given as
A-D, i.e. (i) = A ... (iv) = D.

An MCQ is a numbered item (or a roman sub-item of one) followed by options (a)-(d).
Numbered items without options are descriptive questions: they end a block of MCQs.
Answers are read only for keys that are MCQs, block by block, so the numbering may
restart (e.g. Income-tax and GST sections) without answers getting mixed up.
"""

import re

import pdfplumber

from segment import RE_HEADER, RE_PAGE_NO, RE_SCENARIO, _cut_above, _ink, _lines as _segment_lines, _range_in, _spans

RE_ROMAN_UNIT = re.compile(r"^\(\s*(i|ii|iii|iv|v|vi|vii|viii|ix|x)\s*\)\s")
RE_NUM = re.compile(r"^(\d{1,3})\s*\.\s*(?=\S)")
RE_OPTION = re.compile(r"^\(\s*([a-dA-D])\s*\)")
ROMANS = ["i", "ii", "iii", "iv", "v", "vi", "vii", "viii", "ix", "x"]
# where the answers start in a paper that carries its own answers
RE_ANSWERS_START = re.compile(r"^(SUGGESTED\s+ANSWERS|ANSWERS?(\s*KEY)?|SOLUTIONS?|Answer\s*Key|HINTS?)\b.{0,30}$"
                              r"|^Answers?\s+to\s+(Case|Multiple|MCQ|the\s+MCQ|Part)", re.I)
# inside answers: where MCQ answers begin and where descriptive answers begin
RE_ANS_BLOCK = re.compile(r"Answer\s*Key|Multiple\s+Choice|MCQ|Case\s+Scenario|Division\s*A\b|"
                          r"^(SUGGESTED\s+ANSWERS|ANSWERS?|SOLUTIONS?|HINTS?)\b", re.I)
RE_DESC_HEAD = re.compile(r"Division\s*B\b|Descriptive\s+Questions|PART\s*[–-]?\s*II\b", re.I)
RE_MCQ_HEAD = re.compile(r"Division\s*A\b|Multiple\s+Choice|Case\s+Scenario|MCQs?\b|^SECTION\b", re.I)
RE_ANS_END = re.compile(r"Division\s*B\b|Descriptive|PART\s*[–-]?\s*(II|B)\b", re.I)


def _lines(pdf):
    """Body lines as in segment.py, plus lines it trims above the body on pages without a
    running header (Model Test Paper booklets): there the first question of a page sits
    higher than the usual header band."""
    lines, bounds = _segment_lines(pdf)
    have = {(pi, round(l["top"])) for pi, l in lines}
    extra = []
    for pi, page in enumerate(pdf.pages):
        h = float(page.height)
        top = bounds[pi][0]
        add = [l for l in page.extract_text_lines(strip=True)
               if l["bottom"] <= top + 1 and l["top"] > 0.03 * h and (pi, round(l["top"])) not in have
               and not RE_HEADER.search(l["text"].strip()) and not RE_PAGE_NO.match(l["text"].strip())]
        if add:
            extra += [(pi, l) for l in add]
            bounds[pi] = (min(l["top"] for l in add) - 3, bounds[pi][1])
    if extra:
        lines = sorted(lines + extra, key=lambda x: (x[0], x[1]["top"]))
    return lines, bounds


def _is_mcq_options(lines, kind="any"):
    """Options among these lines: (a)..(d) at line starts or several on one line, or
    (i)..(iv) when the sub-questions themselves are lettered (a), (b) ...
    A part (e) / (v) means parts of a descriptive question, not options."""
    letters, romans = set(), set()
    for _, l in lines:
        t = l["text"]
        if RE_OPTION.match(t):
            letters.update(c.lower() for c in re.findall(r"\(\s*([a-dA-D])\s*\)", t))
        m = re.match(r"^\(\s*(i|ii|iii|iv)\s*\)", t)
        if m:
            romans.add(m.group(1))
        if re.match(r"^\(\s*[e-hE-H]\s*\)", t):
            letters.add("e")
        if re.match(r"^\(\s*(v|vi)\s*\)", t):
            romans.add("v")
    ok_letters = len(letters & set("abcd")) >= 3 and "e" not in letters
    ok_romans = len(romans & {"i", "ii", "iii", "iv"}) >= 3 and "v" not in romans
    return {"letter": ok_letters, "roman": ok_romans}.get(kind, ok_letters or ok_romans)


# sub-questions inside a case scenario, and which kind of options each kind uses
SUB_KINDS = [
    (re.compile(r"^\(\s*(i|ii|iii|iv|v|vi|vii|viii|ix|x)\s*\)\s*"), "letter"),
    (re.compile(r"^(I|II|III|IV|V|VI|VII|VIII|IX|X|i|ii|iii|iv|v|vi|vii|viii|ix|x)\s*\.\s"), "letter"),
    (re.compile(r"^\(\s*([a-h])\s*\)\s*"), "roman"),
]


def _questions(lines, upto, rtp=False):
    """Units (numbered items) and scenario headings before line index `upto`.

    RTPs open with amendments; their questions start at the "QUESTIONS" heading.
    In "Division B" / "Descriptive" parts numbered items are never MCQs.
    """
    start = 0
    if rtp:
        start = min([i for i in range(upto) if re.match(r"^QUESTIONS?$", lines[i][1]["text"].strip())], default=0)
    # question numbers sit at the left margin: the first "1." after the start
    first = next((l for _, l in lines[start:upto] if re.match(r"^1\s*\.", l["text"])), None)
    if not first:
        return [], [], 0, set(), []
    margin = round(first["x0"])
    units, heads, last, descriptive = [], [], 0, set()
    runits, rlast = [], -1
    desc = False
    for i in range(start, upto):
        l = lines[i][1]
        if RE_DESC_HEAD.search(l["text"]) and len(l["text"]) < 90:
            desc = True
        elif RE_MCQ_HEAD.search(l["text"]) and len(l["text"]) < 120:
            desc = False
        if desc:
            descriptive.add(i)
        if abs(l["x0"] - margin) > 5:
            continue
        m = RE_NUM.match(l["text"])
        r = RE_ROMAN_UNIT.match(l["text"])
        if m:
            n = int(m.group(1))
            if n == last + 1 or (n == 1 and last > 0):
                units.append((n, i))
                last = n
        elif r and ROMANS.index(r.group(1)) in (rlast + 1, 0):
            # MCQs numbered (i), (ii) ... at the margin under one case scenario
            runits.append((r.group(1), i))
            rlast = ROMANS.index(r.group(1))
        elif RE_SCENARIO.match(l["text"]) or re.match(r"^General\s+MCQs?|^Multiple\s+Choice\s+Questions", l["text"], re.I):
            heads.append(i)
    return units, heads, margin, descriptive, runits


def _marker(tok):
    """"(b)", "(iii)", "II", "iv." -> "b", "iii", "ii", "iv"; anything else -> None."""
    m = re.fullmatch(r"\(\s*([a-hA-H]|[ivxIVX]+)\s*\)|([IVX]+|[ivx]+)\.?", tok)
    if not m:
        return None
    v = (m.group(1) or m.group(2)).lower()
    return v if v in ROMANS or re.fullmatch(r"[a-h]", v) else None


def _answer_letter(mk):
    """Option as printed -> A-D: "(b)" -> "B", "(iii)" -> "C" (options numbered (i)-(iv))."""
    if mk in ("a", "b", "c", "d"):
        return mk.upper()
    return {"i": "A", "ii": "B", "iii": "C", "iv": "D"}.get(mk)


def _answer_tokens(pdf, page_from=0, y_from=0.0):
    """Answer tokens in reading order, split into blocks at headings.

    Returns a list of blocks; each block is a list of (num, roman, letters) found in it.
    Grids with several answers per row and sub-part tables are read column by column.
    """
    lines, bounds = _lines(pdf)
    blocks, cur, on = [], [], True
    started = False
    for pi in range(page_from, len(pdf.pages)):
        top, bot = bounds[pi]
        if pi == page_from:
            top = max(top, y_from)
        words = [w for w in pdf.pages[pi].extract_words(keep_blank_chars=False)
                 if top - 1 <= w["top"] <= bot + 1]
        rows = []
        for w in sorted(words, key=lambda w: w["top"]):
            if rows and w["top"] - rows[-1][0] < 7:  # "`" and "1." sit a little off the line
                rows[-1][1].append(w)
            else:
                rows.append([w["top"], [w]])
        cols = []  # [x, num, roman, last token kind]
        for _, ws in rows:
            ws.sort(key=lambda w: w["x0"])
            text = " ".join(w["text"] for w in ws)
            if RE_ANS_END.search(text) and len(text) < 90:
                on = False
                continue
            if RE_ANS_BLOCK.search(text) and len(text) < 90 and not RE_NUM.match(text):
                if cur:
                    blocks.append(cur)
                cur, on, started, cols = [], True, True, []
                continue
            if not on:
                continue
            # split words into tokens: "1.", "(ii)", "(b)", "Option", "C"
            toks = []
            for w in ws:
                for m in re.finditer(r"\d{1,3}\.?(?=\(|$)|\(\s*(?:[a-hA-H]|[ivxIVX]+)\s*\)|[^\s(]+|\(", w["text"]):
                    toks.append((w["x0"] + m.start() * 4, m.group(0)))
            for k, (x, tok) in enumerate(toks):
                col = max((c for c in cols if c[0] <= x + 4), key=lambda c: c[0], default=None)
                nxt = toks[k + 1][1] if k + 1 < len(toks) else ""
                if re.fullmatch(r"\d{1,3}\.?", tok):
                    if not (_marker(nxt) or re.fullmatch(r"Option|[A-Da-d]", nxt, re.I)):
                        if col:
                            col[3] = "text"
                        continue
                    near = [c for c in cols if abs(c[0] - x) < 20]
                    if near:
                        col = near[0]
                        col[1:] = [int(tok.rstrip(".")), None, "num"]
                    else:
                        col = [x, int(tok.rstrip(".")), None, "num"]
                        cols.append(col)
                    continue
                if col is None and k == 0 and _marker(tok) and _marker(nxt):
                    # "(i) (b)" with the question number left out (only one case scenario)
                    col = [x, None, None, "ans"]
                    cols.append(col)
                if col is None:
                    continue
                if re.fullmatch(r"Option", tok, re.I) and col[3] in ("num", "sub"):
                    continue
                mk = _marker(tok) or (re.fullmatch(r"[A-Da-d]", tok) and col[3] == "num" and tok.lower())
                if mk and (col[3] in ("num", "ans") or (k == 0 and col[1] is None)) and _marker(nxt):
                    col[2], col[3] = mk, "sub"  # "1. (i) (b)", "1. I (b)", "(a) (iii)"
                    continue
                if mk and col[3] in ("num", "sub") and _answer_letter(mk):
                    cur.append((col[1], col[2], _answer_letter(mk)))
                    col[3] = "ans"
                    continue
                if mk and col[3] == "ans" and k > 0 and toks[k - 1][1].lower() in ("or", "/", "&", "and") \
                        and _answer_letter(mk):
                    n, r, a = cur[-1]  # "(b) or (c)": either is accepted
                    cur[-1] = (n, r, a + _answer_letter(mk))
                    continue
                if col[3] == "ans" and tok.lower() in ("or", "/", "&", "and"):
                    continue
                col[3] = "text"
    if cur:
        blocks.append(cur)
    return blocks


def segment_practice(path, answers_path=None, rtp=False):
    with pdfplumber.open(path) as pdf:
        lines, bounds = _lines(pdf)
        ink = _ink(pdf)
        # answers inside the same paper start at a heading after the questions
        upto = len(lines)
        if not answers_path:
            for i, (pi, l) in enumerate(lines):
                if i > 5 and RE_ANSWERS_START.match(l["text"].strip()):
                    upto = i
                    break
            ans_pdf, ans_page, ans_y = pdf, lines[upto][0] if upto < len(lines) else 0, \
                lines[upto][1]["top"] if upto < len(lines) else 0
            ans_blocks = _answer_tokens(pdf, ans_page, ans_y) if upto < len(lines) else []
    if answers_path:
        with pdfplumber.open(answers_path) as apdf:
            ans_blocks = _answer_tokens(apdf)

    units, heads, margin, descriptive, runits = _questions(lines, upto, rtp)
    if len(runits) < 2:
        runits = []
    pos = lambda i: _cut_above(ink, bounds, *lines[i]) if i < len(lines) else (len(bounds) - 1, bounds[-1][1])
    stops = sorted([i for _, i in units] + [i for _, i in runits] + heads + [upto])

    # 1. classify units and find roman sub-items that are MCQs
    mcqs, block, prev_mcq, contexts = [], 0, False, {}
    for k, (n, i) in enumerate(units):
        if i in descriptive:
            prev_mcq = False
            continue
        end = next((s for s in stops if s > i), upto)
        body = lines[i:end]
        sub_mcqs = []
        for rx, opt_kind in SUB_KINDS:
            subs = []
            for j in range(i + 1, end):
                l = lines[j][1]
                m = rx.match(l["text"])
                if m and l["x0"] > margin + 10:
                    subs.append((m.group(1).lower(), j, l["x0"]))
            found = []
            for s_, (sub, j, x) in enumerate(subs):
                nxt = subs[s_ + 1][1] if s_ + 1 < len(subs) else end
                opts = [ln for ln in lines[j + 1:nxt] if ln[1]["x0"] > x + 8]
                if _is_mcq_options(opts, opt_kind) and not _is_mcq_options([lines[j]]):
                    found.append((sub, j, nxt, opt_kind))
            if len(found) > len(sub_mcqs):
                sub_mcqs = found
        if len(sub_mcqs) >= 2:
            first = sub_mcqs[0][1]
            if not prev_mcq:
                block += 1
            cid = f"c{len(contexts) + 1}"
            contexts[cid] = _spans(pos(i), pos(first), bounds)
            for sub, j, nxt, opt_kind in sub_mcqs:
                mcqs.append({"block": block, "key": f"{n}.{sub}", "label": f"{n}({sub})", "options": opt_kind,
                             "question": _spans(pos(j), pos(nxt), bounds), "context_id": cid, "line": j})
            prev_mcq = True
        elif _is_mcq_options(body):
            if not prev_mcq or (n == 1 and mcqs and mcqs[-1]["block"] == block):
                block += 1
            mcqs.append({"block": block, "key": str(n), "label": str(n),
                         "options": "letter" if _is_mcq_options(body, "letter") else "roman",
                         "question": _spans(pos(i), pos(end), bounds), "context_id": None, "line": i})
            prev_mcq = True
        else:
            prev_mcq = False

    # roman-numbered MCQs: the case scenario runs from the "Case Scenario based MCQs"
    # heading (or the previous item) down to the first of them
    run_start = None
    for k, (rom, i) in enumerate(runits):
        end = next((s_ for s_ in stops if s_ > i), upto)
        if i in descriptive or not _is_mcq_options(lines[i:end], "letter"):
            run_start = None
            continue
        if run_start is None or rom == "i":
            block += 1
            prev_heads = [j for j in range(max(0, i - 120), i) if RE_MCQ_HEAD.search(lines[j][1]["text"])
                          and len(lines[j][1]["text"]) < 120]
            start = prev_heads[-1] + 1 if prev_heads else max([s_ for s_ in stops if s_ < i], default=0)
            cid = f"c{len(contexts) + 1}"
            contexts[cid] = _spans(pos(start), pos(i), bounds) if start < i else []
            run_start = i
        mcqs.append({"block": block, "key": f"r.{rom}", "label": f"({rom})", "options": "letter",
                     "question": _spans(pos(i), pos(end), bounds),
                     "context_id": cid if contexts.get(cid) else None, "line": i})
    mcqs.sort(key=lambda q: q["line"])

    # 2. scenario headings ("Case Scenario ... Questions 1 to 5") give context to the MCQs after them
    for h in heads:
        after = [q for q in mcqs if q["line"] > h and not q["context_id"]]
        if not after:
            continue
        first = after[0]
        if not RE_SCENARIO.match(lines[h][1]["text"]):
            continue
        text = " ".join(lines[j][1]["text"] for j in range(h, first["line"]))
        rng = _range_in(text)
        nxt_head = min([x for x in heads if x > h] + [upto])
        cid = f"c{len(contexts) + 1}"
        contexts[cid] = _spans(pos(h), pos(first["line"]), bounds)
        for q in after:
            n = int(q["key"].split(".")[0])
            if (rng and rng[0] <= n <= rng[1]) or (not rng and q["line"] < nxt_head):
                if q["block"] == first["block"]:
                    q["context_id"] = cid

    # 3. answers: pair each block of MCQs with the answer block that covers it best
    q_blocks = sorted({q["block"] for q in mcqs})
    ans_dicts = []
    for b in ans_blocks:
        d = {}
        for n, r, a in b:
            d.setdefault(f"{n}.{r}" if r else str(n), a)
        ans_dicts.append(d)
    # answers listed as "(i) (b)" without their question number belong to the one
    # case scenario of a block whose sub-questions they match
    for d in ans_dicts:
        loose = {k[5:]: v for k, v in d.items() if k.startswith("None.")}
        if not loose:
            continue
        for sub, v in loose.items():
            d.setdefault(f"r.{sub}", v)
        for qb in q_blocks:
            nums = {q["key"].split(".")[0] for q in mcqs if q["block"] == qb and "." in q["key"]}
            if len(nums) == 1:
                n = nums.pop()
                if all(f"{n}.{sub}" in [q["key"] for q in mcqs] for sub in loose):
                    for sub, v in loose.items():
                        d.setdefault(f"{n}.{sub}", v)
    used = set()
    for qb in q_blocks:
        keys = [q["key"] for q in mcqs if q["block"] == qb]
        best, score = None, 0
        for k, d in enumerate(ans_dicts):
            if k in used:
                continue
            s = sum(1 for key in keys if key in d)
            if s > score:
                best, score = k, s
        if best is None:
            continue
        used.add(best)
        for q in mcqs:
            if q["block"] == qb:
                a = ans_dicts[best].get(q["key"])
                q["answer"] = "(" + ") or (".join(a) + ")" if a else ""
    for q in mcqs:
        q.setdefault("answer", "")
        q["context"] = contexts.get(q["context_id"], [])
        q.pop("line", None)
    return mcqs
