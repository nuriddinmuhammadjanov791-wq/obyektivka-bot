"""Taqdimot (.pptx) yaratish."""
import datetime

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Emu, Inches, Pt

NAVY = RGBColor(0x14, 0x2B, 0x4D)
ACCENT = RGBColor(0x1F, 0x8F, 0xD6)
LIGHT = RGBColor(0xF4, 0xF7, 0xFB)
TEXT = RGBColor(0x22, 0x2B, 0x38)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
FONT = "Calibri"


def _rect(slide, x, y, w, h, color):
    s = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, x, y, w, h)
    s.fill.solid()
    s.fill.fore_color.rgb = color
    s.line.fill.background()
    return s


def _text(slide, x, y, w, h, text, size, color, bold=False, align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP):
    tb = slide.shapes.add_textbox(x, y, w, h)
    tf = tb.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = anchor
    p = tf.paragraphs[0]
    p.alignment = align
    r = p.add_run()
    r.text = text
    r.font.size = Pt(size)
    r.font.bold = bold
    r.font.name = FONT
    r.font.color.rgb = color
    return tb


def build_pptx(topic, subject, author, slides, out_path):
    prs = Presentation()
    prs.slide_width, prs.slide_height = Inches(13.333), Inches(7.5)
    W, H = prs.slide_width, prs.slide_height
    blank = prs.slide_layouts[6]

    # --- sarlavha slaydi ---
    s = prs.slides.add_slide(blank)
    _rect(s, 0, 0, W, H, NAVY)
    _rect(s, Inches(0.8), Inches(2.2), Inches(0.12), Inches(2.6), ACCENT)
    tsize = 44 if len(topic) < 60 else 34
    _text(s, Inches(1.2), Inches(2.0), Inches(11), Inches(2.4), topic, tsize, WHITE, bold=True,
          anchor=MSO_ANCHOR.MIDDLE)
    if subject and subject != "-":
        _text(s, Inches(1.2), Inches(4.4), Inches(11), Inches(0.6), subject, 22, RGBColor(0xBF, 0xD9, 0xF2))
    _text(s, Inches(1.2), Inches(6.2), Inches(8), Inches(0.5), author, 18, WHITE)
    _text(s, Inches(10.3), Inches(6.2), Inches(2.5), Inches(0.5), str(datetime.date.today().year), 18,
          RGBColor(0xBF, 0xD9, 0xF2), align=PP_ALIGN.RIGHT)

    # --- mazmun slaydlari ---
    for n, item in enumerate(slides, 2):
        s = prs.slides.add_slide(blank)
        _rect(s, 0, 0, W, H, LIGHT)
        _rect(s, 0, 0, Inches(0.35), H, NAVY)
        _rect(s, Inches(0.35), 0, Inches(0.08), H, ACCENT)
        _text(s, Inches(1.0), Inches(0.5), Inches(11.6), Inches(1.2), item["title"], 34, NAVY, bold=True,
              anchor=MSO_ANCHOR.MIDDLE)
        _rect(s, Inches(1.0), Inches(1.75), Inches(1.6), Inches(0.06), ACCENT)

        total = sum(len(b) for b in item["bullets"])
        size = 26 if total < 280 else 22 if total < 420 else 19
        tb = s.shapes.add_textbox(Inches(1.0), Inches(2.1), Inches(11.4), Inches(4.7))
        tf = tb.text_frame
        tf.word_wrap = True
        for i, b in enumerate(item["bullets"]):
            p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
            p.space_after = Pt(12)
            r1 = p.add_run()
            r1.text = "■  "
            r1.font.size = Pt(size - 8)
            r1.font.color.rgb = ACCENT
            r1.font.name = FONT
            r2 = p.add_run()
            r2.text = b
            r2.font.size = Pt(size)
            r2.font.color.rgb = TEXT
            r2.font.name = FONT
        _text(s, Inches(11.8), Inches(6.9), Inches(1.2), Inches(0.4), str(n), 14, NAVY, align=PP_ALIGN.RIGHT)

    prs.save(out_path)
    return out_path
