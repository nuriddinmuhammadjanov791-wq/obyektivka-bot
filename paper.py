"""Mustaqil ish (.docx) yaratish."""
import datetime
import re

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt

FONT = "Times New Roman"


def _fmt(run, size=14, bold=False):
    run.font.name = FONT
    run._element.rPr.rFonts.set(qn("w:eastAsia"), FONT)
    run.font.size = Pt(size)
    run.bold = bold


def _par(doc, text="", size=14, bold=False, align=None, indent=False, spacing=1.5, after=0, before=0):
    p = doc.add_paragraph()
    pf = p.paragraph_format
    pf.line_spacing = spacing
    pf.space_after = Pt(after)
    pf.space_before = Pt(before)
    if indent:
        pf.first_line_indent = Cm(1.25)
    if align is not None:
        p.alignment = align
    if text:
        _fmt(p.add_run(text), size, bold)
    return p


def _page_number(section):
    p = section.footer.paragraphs[0]
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run()
    _fmt(run, 12)
    for tag, txt in (("begin", None), (None, "PAGE"), ("end", None)):
        if tag:
            el = OxmlElement("w:fldChar")
            el.set(qn("w:fldCharType"), tag)
        else:
            el = OxmlElement("w:instrText")
            el.set(qn("xml:space"), "preserve")
            el.text = txt
        run._r.append(el)


def _clean(t):
    t = re.sub(r"\*\*|__|`", "", t)
    return re.sub(r"(?<!\w)\*(?!\s)|(?<!\s)\*(?!\w)", "", t).strip()


def parse_body(text):
    """# / ## sarlavhalar, bo'sh qator bilan ajratilgan abzaclar, '- ' ro'yxat."""
    items = []
    buf = []

    def flush():
        if buf:
            items.append(("p", _clean(" ".join(buf))))
            buf.clear()

    for line in text.replace("\r", "").split("\n"):
        s = line.strip()
        if not s:
            flush()
        elif s.startswith("## "):
            flush(); items.append(("h2", _clean(s[3:])))
        elif s.startswith("# "):
            flush(); items.append(("h1", _clean(s[2:])))
        elif s.startswith("- ") or s.startswith("• "):
            flush(); items.append(("li", _clean(s[2:])))
        elif re.match(r"^\d+[.)]\s", s):
            flush(); items.append(("ref", _clean(s)))
        else:
            buf.append(s)
    flush()
    return [i for i in items if i[1]]


def build_paper(meta: dict, body_text: str, out_path: str):
    doc = Document()
    sec = doc.sections[0]
    sec.page_width, sec.page_height = Cm(21), Cm(29.7)
    sec.left_margin, sec.right_margin = Cm(3), Cm(1.5)
    sec.top_margin = sec.bottom_margin = Cm(2)
    doc.styles["Normal"].font.name = FONT
    doc.styles["Normal"].font.size = Pt(14)
    _page_number(sec)

    C = WD_ALIGN_PARAGRAPH.CENTER
    # --- titul varag'i ---
    _par(doc, meta["univ"].upper(), 14, True, C, spacing=1.15, after=6)
    for _ in range(5):
        _par(doc, "", spacing=1.15)
    _par(doc, "MUSTAQIL ISH", 24, True, C, spacing=1.15, after=18)
    _par(doc, f"Fan: {meta['subject']}", 16, False, C, spacing=1.15, after=6)
    _par(doc, f"Mavzu: {meta['topic']}", 16, True, C, spacing=1.15, after=6)
    for _ in range(6):
        _par(doc, "", spacing=1.15)
    _par(doc, f"Bajardi: {meta['author']}", 14, False, WD_ALIGN_PARAGRAPH.RIGHT, spacing=1.15, after=6)
    if meta.get("teacher") and meta["teacher"] != "-":
        _par(doc, f"Qabul qildi: {meta['teacher']}", 14, False, WD_ALIGN_PARAGRAPH.RIGHT, spacing=1.15)
    for _ in range(4):
        _par(doc, "", spacing=1.15)
    _par(doc, str(datetime.date.today().year), 14, False, C, spacing=1.15)
    doc.add_paragraph().add_run().add_break(WD_BREAK.PAGE)

    items = parse_body(body_text)

    # --- reja ---
    _par(doc, "REJA", 14, True, C, after=6)
    for kind, t in items:
        if kind == "h1":
            _par(doc, t, 14, False, spacing=1.5)
    doc.add_paragraph().add_run().add_break(WD_BREAK.PAGE)

    # --- asosiy matn ---
    for kind, t in items:
        if kind == "h1":
            _par(doc, t.upper() if len(t) < 60 else t, 14, True, C, spacing=1.5, before=6, after=6)
        elif kind == "h2":
            _par(doc, t, 14, True, WD_ALIGN_PARAGRAPH.LEFT, spacing=1.5, before=4, after=2)
        elif kind == "li":
            p = _par(doc, "", 14, align=WD_ALIGN_PARAGRAPH.JUSTIFY, spacing=1.5)
            p.paragraph_format.left_indent = Cm(1.25)
            _fmt(p.add_run("•  " + t))
        elif kind == "ref":
            _par(doc, t, 14, False, WD_ALIGN_PARAGRAPH.JUSTIFY, spacing=1.5)
        else:
            _par(doc, t, 14, False, WD_ALIGN_PARAGRAPH.JUSTIFY, indent=True, spacing=1.5)
    doc.save(out_path)
    return out_path
