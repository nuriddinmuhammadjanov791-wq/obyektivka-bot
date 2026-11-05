"""Ma'lumotnoma (obyektivka) Word faylini yaratadi."""
from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt

FONT = "Times New Roman"


def _run(par, text, bold=False, size=12):
    r = par.add_run(text)
    r.bold = bold
    r.font.name = FONT
    r._element.rPr.rFonts.set(qn("w:eastAsia"), FONT)
    r.font.size = Pt(size)
    return r


def _par(doc_or_cell, text="", bold=False, size=12, align=None, after=4):
    p = doc_or_cell.add_paragraph()
    p.paragraph_format.space_after = Pt(after)
    p.paragraph_format.space_before = Pt(0)
    if align:
        p.alignment = align
    if text:
        _run(p, text, bold, size)
    return p


def _label_value(doc, label, value):
    p = _par(doc)
    _run(p, label + " ", bold=True)
    _run(p, value)


def _two_cols(doc, l_label, l_val, r_label, r_val):
    t = doc.add_table(rows=1, cols=2)
    t.autofit = False
    for i, (lab, val) in enumerate(((l_label, l_val), (r_label, r_val))):
        c = t.rows[0].cells[i]
        c.width = Cm(8.5)
        p = c.paragraphs[0]
        p.paragraph_format.space_after = Pt(0)
        _run(p, lab, bold=True)
        p2 = c.add_paragraph()
        p2.paragraph_format.space_after = Pt(4)
        _run(p2, val)
    return t


def build_docx(data: dict, out_path: str, photo_path: str | None = None):
    doc = Document()
    sec = doc.sections[0]
    sec.page_width, sec.page_height = Cm(21), Cm(29.7)
    sec.left_margin = sec.right_margin = Cm(2)
    sec.top_margin = sec.bottom_margin = Cm(1.5)
    st = doc.styles["Normal"]
    st.font.name = FONT
    st.font.size = Pt(12)

    d = data
    study = (
        f"{d['enroll']}dan buyon: {d['univ']} {d['faculty']} talabasi"
    )

    # --- sarlavha + rasm ---
    head = doc.add_table(rows=1, cols=2)
    head.autofit = False
    left, right = head.rows[0].cells
    left.width, right.width = Cm(13.5), Cm(3.5)
    p = left.paragraphs[0]
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _run(p, "MA’LUMOTNOMA", bold=True, size=16)
    _par(left, d["fio"], bold=True, size=14, align=WD_ALIGN_PARAGRAPH.CENTER)
    _par(left, study, align=WD_ALIGN_PARAGRAPH.CENTER)
    rp = right.paragraphs[0]
    rp.alignment = WD_ALIGN_PARAGRAPH.CENTER
    if photo_path:
        rp.add_run().add_picture(photo_path, width=Cm(3), height=Cm(4))
    else:
        _run(rp, "RASM 3x4")
    _par(doc, "", after=2)

    # --- shaxsiy ma'lumotlar ---
    _two_cols(doc, "Tug‘ilgan yili:", d["birth_date"], "Tug‘ilgan joyi:", d["birth_place"])
    _two_cols(doc, "Millati:", d["nationality"], "Partiyaviyligi:", d["party"])
    _two_cols(doc, "Ma’lumoti:", d["education"], "Tamomlagan:", d["graduated"])
    _label_value(doc, "Ma’lumoti bo‘yicha mutaxassisligi:", d["specialty"])
    _two_cols(doc, "Ilmiy darajasi:", d["degree"], "Ilmiy unvoni:", d["rank"])
    _label_value(doc, "Qaysi chet tillarini biladi:", d["languages"])
    _label_value(doc, "Davlat mukofotlari bilan taqdirlanganmi (qanaqa):", d["awards"])
    _label_value(
        doc,
        "Xalq deputatlari respublika, viloyat, shahar va tuman Kengashi deputatimi "
        "yoki boshqa saylanadigan organlarning a’zosimi (to‘liq ko‘rsatilishi lozim):",
        d["deputy"],
    )

    # --- mehnat faoliyati ---
    _par(doc, "MEHNAT FAOLIYATI", bold=True, align=WD_ALIGN_PARAGRAPH.CENTER, after=6)
    for line in d["work"]:
        _par(doc, line, after=4)
    _par(doc, f"{d['enroll']}dan h.v. – {d['univ']} {d['faculty']} talabasi", after=8)

    # --- qarindoshlar ---
    _par(doc, f"{d['fio']}ning yaqin qarindoshlari haqida", bold=True,
         align=WD_ALIGN_PARAGRAPH.CENTER, after=0)
    _par(doc, "MA’LUMOT", bold=True, align=WD_ALIGN_PARAGRAPH.CENTER, after=6)

    heads = ["Qanday qarindosh", "Familyasi, ismi va otasining ismi",
             "Tug‘ilgan yili va joyi", "Ish joyi va lavozimi", "Turar joyi"]
    widths = [Cm(2.3), Cm(3.6), Cm(3.6), Cm(3.8), Cm(3.7)]
    t = doc.add_table(rows=1, cols=5)
    t.style = "Table Grid"
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    t.autofit = False
    for i, h in enumerate(heads):
        c = t.rows[0].cells[i]
        c.width = widths[i]
        c.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER
        _run(c.paragraphs[0], h, bold=True, size=11)
    for rel in d["relatives"]:
        row = t.add_row().cells
        vals = [rel["kind"], rel["fio"], rel["birth"], rel["work"], rel["home"]]
        for i, v in enumerate(vals):
            row[i].width = widths[i]
            _run(row[i].paragraphs[0], v, bold=(i == 0), size=11)

    p = _par(doc, "", align=WD_ALIGN_PARAGRAPH.RIGHT, after=0)
    p.paragraph_format.space_before = Pt(12)
    _run(p, f"Тel: {d['phone']}", bold=True)

    doc.save(out_path)
    return out_path
