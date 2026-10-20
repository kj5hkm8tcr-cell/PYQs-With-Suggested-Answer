#!/usr/bin/env python3
"""Write "00 - Start Here.pdf" at the top of Google Drive Upload/.

It explains how the folder is organised and lists every level, paper and chapter
file with its number of questions, so students can find what they need at a glance.
Run after build_pyq.py.
"""

import sys
from pathlib import Path

import pikepdf

sys.path.insert(0, str(Path(__file__).parent))
from build_pyq import OUT  # noqa: E402
from compose import Composer  # noqa: E402

LEVELS = ["CA Foundation", "CA Intermediate", "CA Final"]


def count_questions(pdf_path):
    """Questions = second-level bookmarks (first level is the attempt)."""
    with pikepdf.open(pdf_path) as pdf, pdf.open_outline() as outline:
        return sum(1 for item in outline.root for q in item.children if "Case Scenario:" not in q.title)


def main():
    doc = Composer("CA Past Year Questions - Start Here")
    doc.cover(["CA Past Year Questions", "Chapter-wise, with ICAI Suggested Answers",
               "Foundation  |  Intermediate  |  Final", "Last 10 attempts up to May 2026"])
    doc.heading("How to use this folder", size=14)
    for line in [
        "1. Open your level: CA Foundation, CA Intermediate or CA Final.",
        "2. Open your subject (paper).",
        "3. Open the chapter. Every question asked on that chapter in the last 10 attempts is "
        "inside, newest attempt first, each followed by ICAI's suggested answer.",
        "4. Use the PDF bookmarks to jump to an attempt or a question.",
        "Case scenario MCQs that cover several chapters are in the last file of each subject, "
        "\"Case Scenario MCQs (Multiple Chapters)\". Final Paper 6 (IBS) has one file per attempt, "
        "because its case studies cover several subjects at once.",
        "Answers reflect the law and standards that applied in that attempt; check later amendments.",
    ]:
        doc.note(line)
    for level in LEVELS:
        level_dir = OUT / level
        if not level_dir.is_dir():
            continue
        doc.heading(level, outline_level=0, size=16)
        for paper_dir in sorted(p for p in level_dir.iterdir() if p.is_dir()):
            doc.heading(paper_dir.name, outline_level=1, size=12)
            for f in sorted(paper_dir.rglob("*.pdf")):
                rel = " > ".join(f.relative_to(paper_dir).with_suffix("").parts)
                n = count_questions(f)
                doc.note(f"{rel}" + (f"  ({n} questions)" if n else ""))
    path = OUT / "00 - Start Here.pdf"
    doc.save(path)
    print(f"wrote {path}")


if __name__ == "__main__":
    main()
