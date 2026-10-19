# CA PYQs with Suggested Answers: chapter-wise

Last 10 attempts' past year questions with ICAI's suggested answers, split
**question by question** and arranged **Level → Paper → Chapter**:

```
Google Drive Upload/
  CA Foundation/
    Paper 1 - Accounting/
      Chapter 01 - Theoretical Framework.pdf
      Chapter 02 - Accounting Process.pdf
      ...
```

Each chapter PDF contains every question from that chapter in the last 10 attempts,
newest attempt first, each followed by ICAI's suggested answer. Bookmarks let students
jump to an attempt or a question. Pages are cut directly from ICAI's PDFs, so tables
and formatting are exactly as ICAI published them.

## Status

| Level | Paper | Attempts | Status |
| --- | --- | --- | --- |
| Foundation | Paper 1 - Accounting | May 2026 – Nov 2022 | Done (199 questions) |
| Foundation | Papers 2–4 | | To do |
| Intermediate | Papers 1–6 | | To do |
| Final | Papers 1–6 | | To do |

## Copyright

ICAI's copyright policy (<https://www.icai.org/post/16585>) allows its material to be
reproduced **only with prior written permission from ICAI**, with the source acknowledged.
So the built PDFs are **not committed** to this repo (see `.gitignore`), and should not be
shared publicly until permission is granted. Every page carries a "Source: ICAI Suggested
Answers" line.

What is committed is only: the build code, ICAI's download links, and the
question → chapter mapping.

## How it works

- `data/<level>/<paper>.json`: ICAI's chapter list, the PDF link for each attempt, and a
  `map` that assigns every question part to a chapter, e.g.
  `"1a.ii": 10` (Q1(a)(ii) → Chapter 10). True/False bundles and "either (i) or (ii)" choices
  are split so each item goes to its own chapter. `"X"` marks a topic that is no longer in
  the current syllabus (left out). A list (`[6, 4]`) puts the part in several chapters.
- `scripts/segment.py`: finds every question part and its answer inside an ICAI PDF.
- `scripts/compose.py`: lays the cut-out regions onto new A4 pages.
- `scripts/build_pyq.py`: downloads the PDFs, checks that every part is mapped and has
  both question and answer, and writes the chapter PDFs.

## Building

```bash
pip install -r requirements.txt
python scripts/build_pyq.py
```

The output appears in `Google Drive Upload/`. Drag its level folders into Google Drive.

### Adding a new attempt

Add an entry to the paper's JSON file with ICAI's suggested-answer link and the chapter
of each question, then rebuild. To keep it to the last 10 attempts, remove the oldest entry.
