# CA PYQs with Suggested Answers: chapter-wise

Past year questions from the last 10 attempts of CA Foundation, Intermediate and Final,
each with ICAI's suggested answer, arranged **Level → Subject → Chapter**:

```
Google Drive Upload/
  00 - Start Here.pdf                        <- how to use + list of every chapter
  CA Foundation/
    Paper 1 - Accounting/
      Chapter 01 - Theoretical Framework.pdf <- every question on this chapter, newest attempt first
      ...
  CA Intermediate/
    Paper 3 - Taxation/
      Section A - Income-tax Law/Chapter 01 - Basic Concepts.pdf
      Section B - Goods and Services Tax/...
      Case Scenario MCQs (Multiple Chapters).pdf
  CA Final/
    ...
    Paper 6 - Integrated Business Solutions/  <- one file per attempt (case studies span all subjects)
```

Inside each chapter PDF, bookmarks jump to an attempt or a question. Pages are cut directly
from ICAI's suggested-answer PDFs, so tables and formatting are exactly as ICAI published them.
For MCQs, the question is cut from ICAI's PDF and the correct option from ICAI's answer key is
printed under it. A case scenario whose MCQs all belong to one chapter goes to that chapter;
one whose MCQs span several chapters goes, whole, to "Case Scenario MCQs (Multiple Chapters)"
after the last chapter.

## Coverage

Attempts with ICAI suggested answers published as of October 2026 (September 2026 answers not out yet):

| Level | Attempts |
| --- | --- |
| Foundation (Papers 1, 2) | May 2026, Jan 2026, Sep 2025, May 2025, Jan 2025, Sep 2024, Jun 2024, Dec 2023, Jun 2023, Nov 2022 |
| Foundation (Papers 3, 4 – MCQ papers) | May 2026, Jan 2026, Sep 2025, May 2025 (ICAI did not publish earlier ones) |
| Intermediate | May 2026, Jan 2026, Sep 2025, May 2025, Jan 2025, Sep 2024, May 2024, Nov 2023, May 2023, Nov 2022 |
| Final | May 2026, Jan 2026, Sep 2025, May 2025, Nov 2024, May 2024, Nov 2023, May 2023, Nov 2022, May 2022 |

- Attempts before the 2024 syllabus change come from the old-scheme papers, matched to the
  current subjects (e.g. old Inter Paper 4 Taxation → current Paper 3). Questions on topics no longer
  in the syllabus (e.g. Contract/NI Act in Inter Law, Hire Purchase, Economics for Finance, EIS,
  Business Correspondence) are left out.
- ICAI's May 2024 Inter/Final suggested answers contain no MCQs, so that attempt has descriptive
  questions only.
- Chapter lists follow ICAI's current study material (May 2026 exams onwards).

## MCQ practice site

`mcq-practice/index.html` is a practice page for students: pick **Foundation / Intermediate / Final**,
the paper, then practise **chapter-wise** (every past-paper MCQ on a chapter, plus
"Case Scenario MCQs (multiple chapters)") or **paper-wise** (a whole PYQ attempt, RTP or MTP).
Tap A-D to see if you were right and ICAI's answer; a bubble grid shows progress, answers are saved in
the browser, and wrong ones can be retried. Light/dark switch and A-/A+ text size are in the top bar.

Each MCQ is shown as an image cut from ICAI's PDF, so formulas, tables and the ₹ sign look as printed.
Build the data, then open the page in a browser (works straight from disk, or host the folder):

```bash
python scripts/build_mcq_practice.py      # writes mcq-practice/data/ (git-ignored, ICAI copyright)
```

RTPs and MTPs: add them to the paper's JSON as a `"practice"` list (format in the script's docstring).
They show up under paper-wise; until then those buttons read "not added yet".

## Copyright

ICAI's copyright policy (<https://www.icai.org/post/16585>) allows its material to be reproduced
**only with prior written permission from ICAI**, with the source acknowledged. So the built PDFs
are **not committed** (see `.gitignore`) and should not be shared publicly until permission is
granted. Every page carries a "Source: ICAI Suggested Answers" line. Once permission is granted,
remove `Google Drive Upload/` from `.gitignore` (or build locally) and upload the folder to Drive.

What is committed: the build code, ICAI's download links, and the question → chapter mapping.

## How it works

- `data/<level>/<paper>.json`: chapter list, ICAI PDF link(s) for each attempt, and a `map` from
  each question part (`"1a"`, `"1a.ii"`, `"2b-or"`, MCQ `"m5"`) to a chapter key, `"CS"`
  (multi-chapter case scenario), `"X"` (out of syllabus) or a list of chapters.
- `scripts/segment.py`: finds every question part, MCQ, case scenario and answer in an ICAI PDF.
- `scripts/compose.py`: lays the cut-out regions onto new A4 pages.
- `scripts/build_pyq.py`: downloads the PDFs, checks every part is mapped and has its answer, writes the chapter PDFs.
- `scripts/build_index.py`: writes `00 - Start Here.pdf`.
- `scripts/dump_parts.py`: lists each part's question text, used when assigning chapters.

## Building

```bash
pip install -r requirements.txt
python scripts/build_pyq.py      # all papers (or pass one data file)
python scripts/build_index.py
```

### Adding a new attempt

Add the attempt with its ICAI suggested-answer link to the paper's JSON file, run
`python scripts/dump_parts.py data/<level>/<paper>.json` to see its questions, fill in its `map`,
and rebuild. Remove the oldest attempt to keep it to the last 10.
