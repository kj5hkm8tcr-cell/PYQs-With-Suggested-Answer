"""Lay out cropped question/answer regions from ICAI PDFs onto new A4 pages.

Regions are copied as vector content (no re-typing, no image conversion), so
tables, symbols and formatting look exactly like ICAI's original.
"""

import pikepdf
from pikepdf import Array, Dictionary, Name

A4_W, A4_H = 595.28, 841.89
TOP, BOTTOM = 56, 48
CROP_X0, CROP_X1 = 92, 503  # horizontal band of ICAI pages that holds the text
DEST_X = (A4_W - (CROP_X1 - CROP_X0)) / 2
GAP = 6


def _esc(text):
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)").encode("cp1252", "replace").decode("latin-1")


class Composer:
    def __init__(self, title):
        self.pdf = pikepdf.new()
        self.pdf.docinfo["/Title"] = title
        self.fonts = Dictionary(
            F1=Dictionary(Type=Name.Font, Subtype=Name.Type1, BaseFont=Name.Helvetica, Encoding=Name.WinAnsiEncoding),
            F2=Dictionary(Type=Name("/Font"), Subtype=Name.Type1, BaseFont=Name("/Helvetica-Bold"), Encoding=Name.WinAnsiEncoding),
        )
        self.sources = {}
        self.forms = {}
        self.page = None
        self.y = 0
        self.outline = []  # (title, page index, level)

    # -- pages -------------------------------------------------------------
    def _new_page(self):
        self._flush()
        self.ops, self.xobjs = [], Dictionary()
        self.page = True
        self.y = A4_H - TOP
        self._footer()

    def _flush(self):
        if not self.page:
            return
        content = self.pdf.make_stream("\n".join(self.ops).encode("latin-1"))
        page = pikepdf.Page(Dictionary(
            Type=Name.Page,
            MediaBox=Array([0, 0, A4_W, A4_H]),
            Resources=Dictionary(Font=self.fonts, XObject=self.xobjs),
            Contents=content,
        ))
        self.pdf.pages.append(page)
        self.page = None

    def _need(self, h):
        if self.page is None or self.y - h < BOTTOM:
            self._new_page()

    def _text(self, x, y, text, size=10, bold=False, gray=0):
        self.ops.append(f"BT {gray} g /{'F2' if bold else 'F1'} {size} Tf {x:.2f} {y:.2f} Td ({_esc(text)}) Tj ET")

    def _footer(self):
        self._text(DEST_X, 26, "Source: ICAI Suggested Answers (www.icai.org)", size=7, gray=0.45)

    @property
    def page_index(self):
        return len(self.pdf.pages)

    # -- content -----------------------------------------------------------
    def cover(self, lines):
        self._new_page()
        y = A4_H / 2 + 40
        for i, line in enumerate(lines):
            size = 22 if i == 0 else 13
            width = len(line) * size * 0.5
            self._text(max(40, (A4_W - width) / 2), y, line, size=size, bold=(i == 0))
            y -= size + 14
        self.page = True
        self.y = 0  # force next content onto a new page

    def heading(self, text, outline_level=None, size=12):
        self._need(size + 160)  # keep the heading with the start of its question
        self.y -= size
        if outline_level is not None:
            self.outline.append((text, self.page_index, outline_level))
        self._text(DEST_X, self.y, text, size=size, bold=True)
        self.ops.append(f"0.6 G 0.5 w {DEST_X:.2f} {self.y - 5:.2f} m {A4_W - DEST_X:.2f} {self.y - 5:.2f} l S")
        self.y -= 5 + GAP * 2

    def label(self, text):
        self._need(90)  # keep the label with the start of what follows
        self.y -= 10
        self._text(DEST_X, self.y, text, size=9, bold=True, gray=0.35)
        self.y -= GAP

    def note(self, text, size=10, bold_prefix=None):
        """Wrapped plain text, e.g. an MCQ's correct option read from ICAI's answer key."""
        text = text.replace("`", "Rs.")
        words, lines, cur = text.split(), [], ""
        for w in words:
            limit = 72 - (len(bold_prefix or "") if not lines else 0)
            if len(cur) + len(w) + 1 > limit:
                lines.append(cur)
                cur = w
            else:
                cur = f"{cur} {w}".strip()
        lines.append(cur)
        self._need(len(lines) * (size + 4) + 6)
        for k, line in enumerate(lines):
            self.y -= size + 2
            if k == 0 and bold_prefix:
                self._text(DEST_X + 18, self.y, bold_prefix, size=size, bold=True)
                self._text(DEST_X + 18 + len(bold_prefix) * size * 0.56, self.y, line, size=size)
            else:
                self._text(DEST_X + 18, self.y, line, size=size)
            self.y -= 2
        self.y -= GAP

    def keep_together(self, spans, extra=0):
        """Start a new page now unless spans (+ extra points) fit on this one."""
        h = sum(b - t + 2 for _, t, b in spans) + extra
        if h < A4_H - TOP - BOTTOM:
            self._need(h)

    def region(self, src_path, page_index, top, bottom):
        """Copy part of a source page (pdfplumber coordinates) into the output."""
        src = self.sources.get(src_path)
        if src is None:
            src = self.sources[src_path] = pikepdf.open(src_path)
        key = (src_path, page_index)
        if key not in self.forms:
            self.forms[key] = self.pdf.copy_foreign(src.pages[page_index].as_form_xobject())
        mb = [float(v) for v in src.pages[page_index].mediabox]
        y_top, y_bot = mb[3] - top, mb[3] - bottom
        h = y_top - y_bot
        self._need(h)
        # A tiny wrapper form whose BBox clips the shared full-page form to the region.
        form = self.pdf.make_stream(b"/P Do", Dictionary(
            Type=Name.XObject, Subtype=Name.Form,
            BBox=Array([CROP_X0 + mb[0], y_bot, CROP_X1 + mb[0], y_top]),
            Resources=Dictionary(XObject=Dictionary(P=self.forms[key]))))
        name = f"/X{len(self.xobjs)}"
        self.xobjs[name] = form
        tx, ty = DEST_X - CROP_X0 - mb[0], (self.y - h) - y_bot
        self.ops.append(f"q 1 0 0 1 {tx:.2f} {ty:.2f} cm {name} Do Q")
        self.y -= h + 2

    def save(self, path):
        self._flush()
        with self.pdf.open_outline() as outline:
            stack = []
            for title, page, level in self.outline:
                item = pikepdf.OutlineItem(title, page)
                del stack[level:]
                (stack[-1].children if stack else outline.root).append(item)
                stack.append(item)
        self.pdf.save(path, deterministic_id=True)
        for s in self.sources.values():
            s.close()
