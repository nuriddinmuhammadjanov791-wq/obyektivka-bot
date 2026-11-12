"""Hujjatlarni rasmiylashtirish (oliy ta'lim ilmiy-uslubiy talablari):
A4; Times New Roman 14; qator oralig'i 1,5; abzats 1,25 sm; matn kenglik bo'yicha tekislangan;
chekkalar: chap 30 mm, o'ng 15 mm, yuqori/past 20 mm (maqola va tezis: har tomondan 20 mm);
sahifa raqami pastda o'rtada (titul varag'ida ko'rsatilmaydi);
adabiyotlar ro'yxati O'zDSt 7.1 (GOST 7.1) bibliografik tavsif uslubida.
"""
import datetime
import re

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt

FONT = "Times New Roman"
MINISTRY = "O‘ZBEKISTON RESPUBLIKASI OLIY TA’LIM, FAN VA INNOVATSIYALAR VAZIRLIGI"
C, L, R, J = (WD_ALIGN_PARAGRAPH.CENTER, WD_ALIGN_PARAGRAPH.LEFT, WD_ALIGN_PARAGRAPH.RIGHT,
              WD_ALIGN_PARAGRAPH.JUSTIFY)


# ---------------- asosiy yordamchilar ----------------
def _fmt(run, size=14, bold=False, italic=False):
    run.font.name = FONT
    run._element.rPr.rFonts.set(qn("w:eastAsia"), FONT)
    run.font.size = Pt(size)
    run.bold = bold
    run.italic = italic


def _par(doc, text="", size=14, bold=False, align=None, indent=False, spacing=1.5, after=0, before=0,
         italic=False, keep=False, page_break=False, left=None):
    p = doc.add_paragraph()
    pf = p.paragraph_format
    pf.line_spacing, pf.space_after, pf.space_before = spacing, Pt(after), Pt(before)
    if indent:
        pf.first_line_indent = Cm(1.25)
    if left is not None:
        pf.left_indent = Cm(left)
    if keep:
        pf.keep_with_next = True
    if page_break:
        pf.page_break_before = True
    if align is not None:
        p.alignment = align
    if text:
        _fmt(p.add_run(text), size, bold, italic)
    return p


def _page_number(section, hide_first=True):
    section.different_first_page_header_footer = hide_first
    p = section.footer.paragraphs[0]
    p.alignment = C
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


def new_doc(left=3.0, right=1.5, top=2.0, bottom=2.0, numbers=True):
    doc = Document()
    sec = doc.sections[0]
    sec.page_width, sec.page_height = Cm(21), Cm(29.7)
    sec.left_margin, sec.right_margin = Cm(left), Cm(right)
    sec.top_margin, sec.bottom_margin = Cm(top), Cm(bottom)
    doc.styles["Normal"].font.name = FONT
    doc.styles["Normal"].font.size = Pt(14)
    if numbers:
        _page_number(sec, hide_first=True)
    return doc


def _clean(t):
    t = re.sub(r"\*\*|__|`", "", t)
    return re.sub(r"(?<!\w)\*(?!\s)|(?<!\s)\*(?!\w)", "", t).strip()


def parse_body(text):
    """# / ## sarlavhalar, bo'sh qator bilan ajratilgan abzaclar, '- ' ro'yxat, '1. ' adabiyotlar."""
    items, buf = [], []

    def flush():
        if buf:
            items.append(("p", _clean(" ".join(buf))))
            buf.clear()

    for line in text.replace("\r", "").split("\n"):
        s = line.strip()
        if not s:
            flush()
        elif s.startswith("## "):
            flush(); items.append(("h2", _clean(s[3:]).rstrip(".")))
        elif s.startswith("# "):
            flush(); items.append(("h1", _clean(s[2:]).rstrip(".")))
        elif s.startswith("- ") or s.startswith("• "):
            flush(); items.append(("li", _clean(s[2:])))
        elif re.match(r"^\d+[.)]\s", s):
            flush(); items.append(("ref", _clean(s)))
        else:
            buf.append(s)
    flush()
    return [i for i in items if i[1]]


def _body(doc, items, chapters_on_new_page=False):
    first = True
    for kind, t in items:
        if kind == "h1":
            _par(doc, t.upper() if len(t) < 70 else t, 14, True, C, spacing=1.5, before=6, after=6, keep=True,
                 page_break=chapters_on_new_page and not first)
            first = False
        elif kind == "h2":
            _par(doc, t, 14, True, L, indent=True, spacing=1.5, before=4, after=2, keep=True)
        elif kind == "li":
            _par(doc, "•  " + t, 14, False, J, spacing=1.5, left=1.25)
        elif kind == "ref":
            _par(doc, t, 14, False, J, indent=True, spacing=1.5)
        else:
            _par(doc, t, 14, False, J, indent=True, spacing=1.5)


def _page_break(doc):
    doc.add_paragraph().add_run().add_break(WD_BREAK.PAGE)


def _skip(v):
    return not v or v.strip() in ("-", "—")


# ---------------- Referat / Mustaqil ish / Kurs ishi ----------------
LABEL = {"mustaqil": "MUSTAQIL ISH", "referat": "REFERAT", "kurs": "KURS ISHI"}


def build_paper(meta, body_text, out_path, kind="mustaqil"):
    doc = new_doc()
    _par(doc, MINISTRY, 14, True, C, spacing=1.15, after=10)
    _par(doc, meta["univ"].upper(), 14, True, C, spacing=1.15, after=6)
    if not _skip(meta.get("faculty")):
        _par(doc, meta["faculty"], 14, False, C, spacing=1.15, after=6)
    for _ in range(5):
        _par(doc, "", spacing=1.15)
    _par(doc, LABEL[kind], 26, True, C, spacing=1.15, after=18)
    _par(doc, f"Fan: {meta['subject']}", 16, False, C, spacing=1.15, after=8)
    _par(doc, f"Mavzu: {meta['topic']}", 16, True, C, spacing=1.15, after=8)
    for _ in range(5):
        _par(doc, "", spacing=1.15)
    _par(doc, f"Bajardi: {meta['author']}", 14, False, R, spacing=1.15, after=8)
    if not _skip(meta.get("teacher")):
        who = "Tekshirdi" if kind == "kurs" else "Qabul qildi"
        _par(doc, f"{who}: {meta['teacher']}", 14, False, R, spacing=1.15)
    for _ in range(3):
        _par(doc, "", spacing=1.15)
    city = meta.get("city")
    place = f"{city} – {datetime.date.today().year}" if not _skip(city) else str(datetime.date.today().year)
    _par(doc, place, 14, False, C, spacing=1.15)
    _page_break(doc)

    items = parse_body(body_text)
    _par(doc, "MUNDARIJA" if kind == "kurs" else "REJA", 14, True, C, after=6)
    for kd, t in items:
        if kd == "h1":
            _par(doc, t, 14, False, L, spacing=1.5)
        elif kd == "h2":
            _par(doc, t, 14, False, L, spacing=1.5, left=1.0)
    _page_break(doc)
    _body(doc, items, chapters_on_new_page=(kind == "kurs"))
    doc.save(out_path)
    return out_path


# ---------------- Ilmiy maqola va tezis ----------------
def _author_block(doc, meta):
    _par(doc, meta["author"], 14, True, R, spacing=1.15)
    if not _skip(meta.get("workplace")):
        _par(doc, meta["workplace"], 14, False, R, spacing=1.15)
    _par(doc, "", spacing=1.15)
    _par(doc, meta["topic"].upper(), 14, True, C, spacing=1.15, after=10)


def build_article(meta, ann, body_text, out_path):
    """Maqola: har tomondan 20 mm; muallif o'ngda, sarlavha o'rtada; 3 tilda annotatsiya."""
    doc = new_doc(2, 2, 2, 2, numbers=False)
    _author_block(doc, meta)
    labels = {"uz": ("Annotatsiya.", "Kalit so‘zlar:"), "ru": ("Аннотация.", "Ключевые слова:"),
              "en": ("Abstract.", "Keywords:")}
    order = [meta["lang"]] + [x for x in ("uz", "ru", "en") if x != meta["lang"]]
    for lg in order:
        a = ann.get(lg, {})
        if not a:
            continue
        p = _par(doc, "", 12, align=J, spacing=1.15, after=2, indent=True)
        _fmt(p.add_run(labels[lg][0] + " "), 12, True, True)
        _fmt(p.add_run(a.get("annotation", "")), 12, False, True)
        p = _par(doc, "", 12, align=J, spacing=1.15, after=8, indent=True)
        _fmt(p.add_run(labels[lg][1] + " "), 12, True, True)
        _fmt(p.add_run(a.get("keywords", "")), 12, False, True)
    _body(doc, parse_body(body_text))
    doc.save(out_path)
    return out_path


def build_tezis(meta, ann, body_text, out_path):
    doc = new_doc(2, 2, 2, 2, numbers=False)
    _author_block(doc, meta)
    _body(doc, parse_body(body_text))
    doc.save(out_path)
    return out_path


# ---------------- Insho ----------------
def build_insho(meta, text, out_path):
    doc = new_doc()
    _par(doc, meta["topic"].upper(), 14, True, C, spacing=1.5, after=6)
    for para in [p.strip() for p in text.split("\n\n") if p.strip()]:
        _par(doc, _clean(para), 14, False, J, indent=True)
    if not _skip(meta.get("author")):
        _par(doc, f"Muallif: {meta['author']}", 14, False, R, before=12)
    doc.save(out_path)
    return out_path


# ---------------- Keys ----------------
def build_keys(meta, text, out_path):
    doc = new_doc()
    _par(doc, "KEYS (CASE STUDY)", 16, True, C, spacing=1.5, after=4)
    _par(doc, f"Fan: {meta['subject']}", 14, False, C, spacing=1.15)
    _par(doc, f"Mavzu: {meta['topic']}", 14, True, C, spacing=1.15, after=10)
    _body(doc, parse_body(text))
    if not _skip(meta.get("author")):
        _par(doc, f"Tayyorladi: {meta['author']}", 14, False, R, before=12)
    doc.save(out_path)
    return out_path


# ---------------- Test ----------------
def _cell_borders(cell, show=True):
    tcPr = cell._tc.get_or_add_tcPr()
    b = OxmlElement("w:tcBorders")
    for edge in ("top", "left", "bottom", "right"):
        el = OxmlElement(f"w:{edge}")
        el.set(qn("w:val"), "single" if show else "nil")
        el.set(qn("w:sz"), "8")
        el.set(qn("w:color"), "000000")
        b.append(el)
    tcPr.append(b)


def build_test(meta, questions, out_path):
    """questions: [{'q','options':[4], 'answer':'A'}]"""
    doc = new_doc(3, 1.5, 2, 2, numbers=True)
    _par(doc, "TEST SAVOLLARI", 16, True, C, spacing=1.15, after=4)
    _par(doc, f"Fan: {meta['subject']}", 14, False, C, spacing=1.15)
    _par(doc, f"Mavzu: {meta['topic']}", 14, True, C, spacing=1.15, after=12)
    for i, q in enumerate(questions, 1):
        _par(doc, f"{i}. {q['q']}", 14, True, J, spacing=1.15, after=2, keep=True)
        for letter, opt in zip("ABCD", q["options"]):
            _par(doc, f"{letter}) {opt}", 14, False, L, spacing=1.15, left=0.8, after=0)
        _par(doc, "", spacing=1.0, after=4)
    _page_break(doc)
    _par(doc, "JAVOBLAR KALITI", 16, True, C, spacing=1.15, after=10)
    cols = 5
    rows = (len(questions) + cols - 1) // cols
    t = doc.add_table(rows=rows, cols=cols)
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    for k, q in enumerate(questions):
        cell = t.rows[k % rows].cells[k // rows]
        cell.paragraphs[0].alignment = C
        _fmt(cell.paragraphs[0].add_run(f"{k + 1} — {q['answer']}"), 14, True)
        _cell_borders(cell, True)
    doc.save(out_path)
    return out_path


# ---------------- Glossariy ----------------
def build_glossary(meta, terms, out_path):
    doc = new_doc(3, 1.5, 2, 2, numbers=True)
    _par(doc, "GLOSSARIY", 16, True, C, spacing=1.15, after=4)
    _par(doc, f"Fan: {meta['subject']}", 14, False, C, spacing=1.15)
    _par(doc, f"Mavzu: {meta['topic']}", 14, True, C, spacing=1.15, after=12)
    terms = sorted(terms, key=lambda x: x["term"].lower())
    t = doc.add_table(rows=1, cols=3)
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    widths = (Cm(1.2), Cm(4.5), Cm(10.3))
    for i, h in enumerate(("T/r", "Atama", "Ta’rifi")):
        c = t.rows[0].cells[i]
        c.width = widths[i]
        c.paragraphs[0].alignment = C
        _fmt(c.paragraphs[0].add_run(h), 13, True)
        _cell_borders(c)
    for n, it in enumerate(terms, 1):
        row = t.add_row().cells
        for i, v in enumerate((str(n), it["term"], it["definition"])):
            row[i].width = widths[i]
            p = row[i].paragraphs[0]
            p.alignment = C if i == 0 else L
            p.paragraph_format.line_spacing = 1.15
            _fmt(p.add_run(v), 13, bold=(i == 1))
            _cell_borders(row[i])
    doc.save(out_path)
    return out_path


# ---------------- Krossvord ----------------
def _grid_table(doc, g, answers):
    t = doc.add_table(rows=g["rows"], cols=g["cols"])
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    t.autofit = False
    for r in range(g["rows"]):
        t.rows[r].height = Cm(0.85)
        for c in range(g["cols"]):
            cell = t.rows[r].cells[c]
            cell.width = Cm(0.85)
            p = cell.paragraphs[0]
            p.paragraph_format.space_after = Pt(0)
            p.paragraph_format.line_spacing = 1.0
            has = (r, c) in g["cells"]
            _cell_borders(cell, has)
            if has:
                p.alignment = C
                if (r, c) in g["nums"]:
                    _fmt(p.add_run(str(g["nums"][(r, c)])), 7)
                if answers:
                    _fmt(p.add_run(g["cells"][(r, c)]), 13, True)
    return t


def build_crossword(meta, g, out_path):
    doc = new_doc(2, 2, 2, 2, numbers=False)
    _par(doc, "KROSSVORD", 18, True, C, spacing=1.15, after=2)
    _par(doc, f"Mavzu: {meta['topic']}", 14, False, C, spacing=1.15, after=10)
    _grid_table(doc, g, answers=False)
    _par(doc, "", spacing=1.0, after=6)
    _par(doc, "Gorizontal →", 14, True, L, spacing=1.15, after=2)
    for n, clue, _w in g["across"]:
        _par(doc, f"{n}. {clue}", 13, False, L, spacing=1.15)
    _par(doc, "Vertikal ↓", 14, True, L, spacing=1.15, before=8, after=2)
    for n, clue, _w in g["down"]:
        _par(doc, f"{n}. {clue}", 13, False, L, spacing=1.15)
    _page_break(doc)
    _par(doc, "JAVOBLAR", 16, True, C, spacing=1.15, after=8)
    _grid_table(doc, g, answers=True)
    _par(doc, "", spacing=1.0, after=6)
    _par(doc, "Gorizontal: " + "; ".join(f"{n}. {w}" for n, _c, w in g["across"]), 13, False, L, spacing=1.15)
    _par(doc, "Vertikal: " + "; ".join(f"{n}. {w}" for n, _c, w in g["down"]), 13, False, L, spacing=1.15)
    doc.save(out_path)
    return out_path
