#!/usr/bin/env python3
"""Merge per-attempt PYQ PDFs into one PDF per chapter.

Input layout (what you upload to the repo):

    source/<Level>/<Subject>/<Chapter>/<Attempt>.pdf
    e.g. source/CA Foundation/Paper 1 - Accounting/Chapter 01 - Theoretical Framework/May 2026.pdf

Output layout (what gets uploaded to Google Drive):

    dist/<Level>/<Subject>/<Chapter>.pdf

Each chapter PDF contains the latest N attempts (default 10), newest first,
with a divider page and a bookmark for every attempt.

A ready-made chapter PDF placed directly inside a subject folder
(source/<Level>/<Subject>/<Chapter>.pdf) is copied to dist/ unchanged.
"""

import argparse
import io
import re
import shutil
import sys
from pathlib import Path

from pypdf import PdfReader, PdfWriter
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}
MONTH_NAMES = ["", "January", "February", "March", "April", "May", "June",
               "July", "August", "September", "October", "November", "December"]


def parse_attempt(stem):
    """Return (year, month) from names like 'May 2026', 'Jan-26', 'Sept 2025', '2026-05'."""
    s = stem.lower()
    m = re.search(r"(20\d{2})[-_ .](\d{1,2})\b", s)
    if m and 1 <= int(m.group(2)) <= 12:
        return int(m.group(1)), int(m.group(2))
    m = re.search(r"([a-z]{3,9})[-_ .']*(\d{4}|\d{2})\b", s)
    if m and m.group(1)[:3] in MONTHS:
        year = int(m.group(2))
        if year < 100:
            year += 2000
        return year, MONTHS[m.group(1)[:3]]
    return None


def divider_page(title, subtitle):
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4, invariant=1)  # no timestamps, so rebuilds are byte-identical
    w, h = A4
    c.setFont("Helvetica-Bold", 28)
    c.drawCentredString(w / 2, h / 2 + 20, title)
    c.setFont("Helvetica", 14)
    c.drawCentredString(w / 2, h / 2 - 15, subtitle)
    c.showPage()
    c.save()
    buf.seek(0)
    return PdfReader(buf).pages[0]


def build_chapter(chapter_dir, out_file, max_attempts):
    attempts = []
    for pdf in chapter_dir.glob("*.pdf"):
        when = parse_attempt(pdf.stem)
        if when is None:
            print(f"  ! skipping {pdf} (can't read attempt month/year from file name)")
            continue
        attempts.append((when, pdf))
    if not attempts:
        return False

    attempts.sort(reverse=True)
    attempts = attempts[:max_attempts]

    writer = PdfWriter()
    for (year, month), pdf in attempts:
        label = f"{MONTH_NAMES[month]} {year}"
        start = len(writer.pages)
        writer.add_page(divider_page(f"{label} Attempt", "Questions with Suggested Answers"))
        for page in PdfReader(pdf).pages:
            writer.add_page(page)
        writer.add_outline_item(label, start)

    writer.add_metadata({"/Title": f"{chapter_dir.parent.name} - {chapter_dir.name} - Last {len(attempts)} Attempts PYQ"})
    out_file.parent.mkdir(parents=True, exist_ok=True)
    with open(out_file, "wb") as f:
        writer.write(f)
    print(f"  built {out_file} ({len(attempts)} attempts)")
    return True


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source", default="source")
    ap.add_argument("--out", default="dist")
    ap.add_argument("--max-attempts", type=int, default=10)
    args = ap.parse_args()

    src, out = Path(args.source), Path(args.out)
    if out.exists():
        shutil.rmtree(out)

    count = 0
    for level in sorted(p for p in src.iterdir() if p.is_dir()):
        for subject in sorted(p for p in level.iterdir() if p.is_dir()):
            for item in sorted(subject.iterdir()):
                dest = out / level.name / subject.name
                if item.is_dir():
                    count += build_chapter(item, dest / f"{item.name}.pdf", args.max_attempts)
                elif item.suffix.lower() == ".pdf":
                    dest.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(item, dest / item.name)
                    print(f"  copied {dest / item.name}")
                    count += 1
    print(f"Done: {count} chapter PDF(s) in {out}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
