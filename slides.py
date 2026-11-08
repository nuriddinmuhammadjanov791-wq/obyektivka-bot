"""Taqdimot (.pptx): shablonlar, rasmlar, reja, rahmat sahifasi (reklama bilan)."""
import datetime
import io
import math
import os

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Inches, Pt

BOT_TAG = os.getenv("BOT_TAG", "@cylooerai")
W_IN, H_IN = 13.333, 7.5

LABELS = {
    "uz": {"agenda": "Reja", "thanks": "E’tiboringiz uchun rahmat!", "q": "Savollaringiz bormi?"},
    "ru": {"agenda": "План", "thanks": "Спасибо за внимание!", "q": "Есть вопросы?"},
    "en": {"agenda": "Agenda", "thanks": "Thank you for your attention!", "q": "Any questions?"},
}


def C(h):
    return RGBColor.from_string(h)


# ---------------- past darajadagi yordamchilar ----------------
def I(v):
    return Inches(v)


def shape(s, kind, x, y, w, h, fill=None, line=None, lw=1.0):
    sh = s.shapes.add_shape(kind, I(x), I(y), I(w), I(h))
    if fill:
        sh.fill.solid()
        sh.fill.fore_color.rgb = C(fill)
    else:
        sh.fill.background()
    if line:
        sh.line.color.rgb = C(line)
        sh.line.width = Pt(lw)
    else:
        sh.line.fill.background()
    sh.shadow.inherit = False
    return sh


def rect(s, x, y, w, h, fill=None, line=None, lw=1.0):
    return shape(s, MSO_SHAPE.RECTANGLE, x, y, w, h, fill, line, lw)


def text(s, x, y, w, h, t, size, color, bold=False, font="Calibri", align=PP_ALIGN.LEFT,
         anchor=MSO_ANCHOR.TOP, italic=False):
    tb = s.shapes.add_textbox(I(x), I(y), I(w), I(h))
    tf = tb.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = anchor
    p = tf.paragraphs[0]
    p.alignment = align
    r = p.add_run()
    r.text = t
    f = r.font
    f.size, f.bold, f.italic, f.name = Pt(size), bold, italic, font
    f.color.rgb = C(color)
    return tb


def row_of(s, kind, x, y, n, size, gap, fill):
    for k in range(n):
        shape(s, kind, x + k * (size + gap), y, size, size, fill)


# ---------------- shablonlar ----------------
def decor_klassik(s, kind, i, th):
    if kind == "title":
        rect(s, 0, 0, W_IN, H_IN, th["dark"])
        rect(s, 0.8, 2.2, 0.12, 2.6, th["accent"])
    else:
        rect(s, 0, 0, W_IN, H_IN, th["bg"])
        rect(s, 0, 0, 0.35, H_IN, th["dark"])
        rect(s, 0.35, 0, 0.08, H_IN, th["accent"])


def decor_milliy(s, kind, i, th):
    if kind == "title":
        rect(s, 0, 0, W_IN, H_IN, th["dark"])
        shape(s, MSO_SHAPE.MOON, 0.9, 0.6, 0.8, 1.2, "FFFFFF")
        for x, y in [(2.1, 0.7), (2.5, 1.1), (2.9, 0.7), (3.3, 1.1), (3.7, 0.7), (4.1, 1.1)]:
            shape(s, MSO_SHAPE.STAR_5_POINT, x, y, 0.26, 0.26, "FFFFFF")
        row_of(s, MSO_SHAPE.DIAMOND, 0.4, 6.05, 28, 0.22, 0.2, "FFFFFF")
        rect(s, 0, 6.55, W_IN, 0.1, "FFFFFF")
        rect(s, 0, 6.65, W_IN, 0.16, "1EB53A")
        rect(s, 0, 6.81, W_IN, 0.06, "CE1126")
        rect(s, 0, 6.87, W_IN, 0.63, "1EB53A")
    else:
        rect(s, 0, 0, W_IN, H_IN, "FFFFFF")
        rect(s, 0, 0, W_IN, 0.34, th["dark"])
        row_of(s, MSO_SHAPE.DIAMOND, 0.3, 0.09, 40, 0.16, 0.16, "FFFFFF")
        rect(s, 0, 0.34, W_IN, 0.07, "1EB53A")
        rect(s, 0, 0.41, W_IN, 0.04, "CE1126")


def decor_sharqona(s, kind, i, th):
    if kind == "title":
        rect(s, 0, 0, W_IN, H_IN, th["dark"])
        shape(s, MSO_SHAPE.STAR_8_POINT, 8.4, 0.8, 5.6, 5.6, "138793")
        shape(s, MSO_SHAPE.STAR_8_POINT, 9.3, 1.7, 3.8, 3.8, None, th["accent"], 3)
        shape(s, MSO_SHAPE.STAR_8_POINT, 10.2, 2.6, 2.0, 2.0, th["accent"])
        rect(s, 0, 6.7, W_IN, 0.05, th["accent"])
        row_of(s, MSO_SHAPE.DIAMOND, 0.4, 6.95, 30, 0.2, 0.2, th["accent"])
    else:
        rect(s, 0, 0, W_IN, H_IN, th["bg"])
        rect(s, 0, 0, W_IN, 0.5, th["dark"])
        row_of(s, MSO_SHAPE.DIAMOND, 0.3, 0.15, 36, 0.2, 0.16, th["accent"])
        rect(s, 0, 0.5, W_IN, 0.05, th["accent"])
        shape(s, MSO_SHAPE.STAR_8_POINT, -0.5, 6.5, 1.5, 1.5, "EAD9A8")


PAL = ["7B2FF7", "FF3D81", "FF9F1C", "2EC4B6", "FFC914"]


def decor_rang(s, kind, i, th):
    if kind == "title":
        rect(s, 0, 0, W_IN, H_IN, th["dark"])
        shape(s, MSO_SHAPE.OVAL, -1.2, -1.4, 4.2, 4.2, "FF3D81")
        shape(s, MSO_SHAPE.OVAL, 10.3, 4.4, 4.6, 4.6, "FF9F1C")
        shape(s, MSO_SHAPE.OVAL, 9.6, -1.6, 3.6, 3.6, "2EC4B6")
        shape(s, MSO_SHAPE.OVAL, 0.4, 5.7, 1.6, 1.6, "FFC914")
        shape(s, MSO_SHAPE.OVAL, 11.6, 3.2, 0.8, 0.8, "7B2FF7")
    else:
        rect(s, 0, 0, W_IN, H_IN, th["bg"])
        shape(s, MSO_SHAPE.OVAL, -0.7, -0.7, 1.9, 1.9, PAL[i % 5])
        shape(s, MSO_SHAPE.OVAL, 12.0, -0.6, 1.7, 1.7, PAL[(i + 2) % 5])
        shape(s, MSO_SHAPE.OVAL, 12.4, 6.3, 1.5, 1.5, PAL[(i + 4) % 5])
        for k in range(4):
            rect(s, 0.9 + k * 0.45, 1.8, 0.4, 0.09, PAL[(i + k) % 5])


def decor_it(s, kind, i, th):
    rect(s, 0, 0, W_IN, H_IN, th["bg"])
    rect(s, 0, 0, W_IN, 0.5, "161B22")
    for k, col in enumerate(["FF5F56", "FFBD2E", "27C93F"]):
        shape(s, MSO_SHAPE.OVAL, 0.25 + k * 0.3, 0.15, 0.2, 0.2, col)
    text(s, 1.4, 0.08, 8, 0.35, f"~/{BOT_TAG.lstrip('@')} $ python slides.py", 12, "8B949E", font="Consolas")
    if kind == "title":
        text(s, 8.6, 1.4, 4.7, 3.4, "</>", 130, "12303B", True, "Consolas", PP_ALIGN.CENTER, MSO_ANCHOR.MIDDLE)
        rect(s, 0.8, 1.9, 0.1, 2.9, th["accent"])
        rect(s, 0, 7.3, W_IN, 0.2, "00E5FF")
    else:
        rect(s, 0, 0.5, 0.12, H_IN - 0.5, th["accent"])


def decor_tabiat(s, kind, i, th):
    if kind == "title":
        rect(s, 0, 0, W_IN, H_IN, th["dark"])
        shape(s, MSO_SHAPE.OVAL, -1.8, 4.2, 6.5, 5.2, "2E7D32")
        shape(s, MSO_SHAPE.OVAL, 8.8, -2.2, 6.4, 5.2, "388E3C")
        shape(s, MSO_SHAPE.OVAL, 7.4, 4.8, 4.4, 4.2, "66BB6A")
        shape(s, MSO_SHAPE.OVAL, 11.4, 2.6, 1.2, 1.2, "A5D6A7")
    else:
        rect(s, 0, 0, W_IN, H_IN, th["bg"])
        shape(s, MSO_SHAPE.OVAL, 11.0, -1.0, 3.0, 2.5, "A5D6A7")
        shape(s, MSO_SHAPE.OVAL, 12.1, -0.4, 1.9, 1.6, "66BB6A")
        shape(s, MSO_SHAPE.OVAL, -0.9, 6.6, 2.6, 1.8, "A5D6A7")
        rect(s, 0, 0, 0.14, H_IN, th["dark"])


def decor_elegant(s, kind, i, th):
    rect(s, 0, 0, W_IN, H_IN, th["bg"] if kind != "title" else th["dark"])
    rect(s, 0.3, 0.3, W_IN - 0.6, H_IN - 0.6, None, th["accent"], 2)
    rect(s, 0.4, 0.4, W_IN - 0.8, H_IN - 0.8, None, "7A6A2A", 0.75)


THEMES = {
    "klassik": dict(label="📘 Klassik", decor=decor_klassik, bg="F4F7FB", dark="142B4D", accent="1F8FD6",
                    title="142B4D", text="222B38", muted="8A97A8", banner="142B4D", banner_text="FFFFFF",
                    on_dark="FFFFFF", sub="BFD9F2", on_accent="FFFFFF", ft="Calibri", fb="Calibri"),
    "milliy": dict(label="🇺🇿 Milliy", decor=decor_milliy, bg="FFFFFF", dark="0F4C9A", accent="1EB53A",
                   title="0F4C9A", text="1F2A37", muted="7B8794", banner="0F4C9A", banner_text="FFFFFF",
                   on_dark="FFFFFF", sub="CFE0F7", on_accent="FFFFFF", ft="Georgia", fb="Calibri"),
    "sharqona": dict(label="🕌 Sharqona", decor=decor_sharqona, bg="FBF4E2", dark="0E6E78", accent="C9A227",
                     title="0E6E78", text="2B2A24", muted="8C7B3C", banner="0E6E78", banner_text="FFF8E1",
                     on_dark="FFF8E1", sub="F0DDA0", on_accent="3A2F00", ft="Georgia", fb="Calibri"),
    "rang": dict(label="🌈 Rang-barang", decor=decor_rang, bg="FFF9F2", dark="2B1055", accent="7B2FF7",
                 title="2B1055", text="2A2A3A", muted="9A8FB0", banner="2B1055", banner_text="FFFFFF",
                 on_dark="FFFFFF", sub="FFD6E8", on_accent="FFFFFF", ft="Calibri", fb="Calibri"),
    "it": dict(label="💻 IT", decor=decor_it, bg="0D1117", dark="0D1117", accent="00E5FF",
               title="FFFFFF", text="E6EDF3", muted="6E7681", banner="0B2A33", banner_text="00E5FF",
               on_dark="FFFFFF", sub="39FF14", on_accent="002A33", ft="Consolas", fb="Calibri", bullet=">"),
    "tabiat": dict(label="🌿 Tabiat", decor=decor_tabiat, bg="F1F8F1", dark="1B5E20", accent="43A047",
                   title="1B5E20", text="22302A", muted="7C9A80", banner="1B5E20", banner_text="FFFFFF",
                   on_dark="FFFFFF", sub="C8E6C9", on_accent="FFFFFF", ft="Georgia", fb="Calibri"),
    "elegant": dict(label="✨ Elegant", decor=decor_elegant, bg="151515", dark="111111", accent="D4AF37",
                    title="D4AF37", text="EEEEEE", muted="8A7A3A", banner="2A2410", banner_text="F3D77A",
                    on_dark="FFFFFF", sub="D4AF37", on_accent="1A1500", ft="Georgia", fb="Calibri",
                    center=True),
}
THEME_OPTIONS = [(t["label"], k) for k, t in THEMES.items()]

# ---------------- slayd qismlari ----------------
IMG_W, IMG_H = 4.7, 3.7  # rasm o'lchami (dyuym)
IMG_RATIO = IMG_W / IMG_H


def fit_size(items, width_in, height_pt, sizes=(24, 22, 20, 19, 18, 17, 16, 15, 14)):
    wpt = width_in * 72 - 30
    for sz in sizes:
        cpl = max(10, wpt / (sz * 0.49))
        lines = sum(math.ceil(len(b) / cpl) for b in items)
        if lines * sz * 1.2 + len(items) * 11 <= height_pt:
            return sz
    return sizes[-1]


def footer(s, n, th):
    text(s, 0.9, 7.05, 4, 0.3, BOT_TAG, 11, th["muted"], font=th["fb"])
    if n:
        text(s, 11.8, 7.0, 1.0, 0.35, str(n), 13, th["muted"], font=th["fb"], align=PP_ALIGN.RIGHT)


def title_slide(prs, th, topic, subject, author):
    s = prs.slides.add_slide(prs.slide_layouts[6])
    th["decor"](s, "title", 0, th)
    center = th.get("center")
    al = PP_ALIGN.CENTER if center else PP_ALIGN.LEFT
    narrow = th["decor"] in (decor_sharqona, decor_it, decor_rang, decor_tabiat)
    x, w = (1.2, W_IN - 2.4) if center else (1.2, 7.6 if narrow else 10.8)
    size = 44 if len(topic) < 45 else 36 if len(topic) < 80 else 30
    text(s, x, 1.6, w, 2.9, topic, size, th["on_dark"], True, th["ft"], al, MSO_ANCHOR.MIDDLE)
    y = 4.7
    if subject and subject != "-":
        text(s, x, y, w, 0.6, subject, 22, th["sub"], font=th["fb"], align=al)
        y += 0.7
    text(s, x, y, w, 0.5, author, 18, th["on_dark"], font=th["fb"], align=al)
    text(s, x, y + 0.5, w, 0.4, str(datetime.date.today().year), 16, th["sub"], font=th["fb"], align=al)
    return s


def agenda_slide(prs, th, lang, titles, n):
    s = prs.slides.add_slide(prs.slide_layouts[6])
    th["decor"](s, "content", n, th)
    text(s, 0.9, 0.7, 11.6, 1.05, LABELS[lang]["agenda"], 34, th["title"], True, th["ft"],
         anchor=MSO_ANCHOR.MIDDLE)
    rect(s, 0.9, 1.9, 1.6, 0.06, th["accent"])
    titles = titles[:14]
    per = 7 if len(titles) > 7 else len(titles)
    for k, t in enumerate(titles):
        col, row = divmod(k, per)
        x, y = 0.9 + col * 6.0, 2.25 + row * 0.66
        shape(s, MSO_SHAPE.OVAL, x, y, 0.5, 0.5, th["accent"])
        text(s, x, y + 0.02, 0.5, 0.46, str(k + 1), 16, th["on_accent"], True, th["fb"], PP_ALIGN.CENTER,
             MSO_ANCHOR.MIDDLE)
        text(s, x + 0.65, y, 5.2, 0.5, t, 19 if len(t) < 38 else 16, th["text"], font=th["fb"],
             anchor=MSO_ANCHOR.MIDDLE)
    footer(s, n, th)
    return s


def content_slide(prs, th, item, n, idx):
    s = prs.slides.add_slide(prs.slide_layouts[6])
    th["decor"](s, "content", idx, th)
    acc = PAL[idx % 5] if th["decor"] is decor_rang else th["accent"]
    t = item["title"]
    text(s, 0.9, 0.7, 11.6, 1.05, t, 32 if len(t) <= 42 else 27, th["title"], True, th["ft"],
         anchor=MSO_ANCHOR.MIDDLE)
    if th["decor"] is not decor_rang:
        rect(s, 0.9, 1.8, 1.6, 0.06, acc)

    has_banner = bool(item.get("key_point"))
    body_bottom = 6.0 if has_banner else 6.85
    body_h = body_bottom - 2.05
    img = item.get("img")
    if img:
        right = idx % 2 == 0
        img_x = 12.43 - IMG_W if right else 0.9
        txt_x = 0.9 if right else 0.9 + IMG_W + 0.45
        txt_w = 11.53 - IMG_W - 0.45
        img_y = 2.05 + max(0, (body_h - IMG_H) / 2)
        shape(s, MSO_SHAPE.RECTANGLE, img_x + 0.1, img_y + 0.1, IMG_W, IMG_H, acc)
        s.shapes.add_picture(io.BytesIO(img), I(img_x), I(img_y), I(IMG_W), I(IMG_H))
    else:
        txt_x, txt_w = 0.9, 11.5

    size = fit_size(item["bullets"], txt_w, body_h * 72)
    tb = s.shapes.add_textbox(I(txt_x), I(2.05), I(txt_w), I(body_h))
    tf = tb.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE if img else MSO_ANCHOR.TOP
    mark = th.get("bullet", "■")
    for k, b in enumerate(item["bullets"]):
        p = tf.paragraphs[0] if k == 0 else tf.add_paragraph()
        p.space_after = Pt(10)
        r1 = p.add_run()
        r1.text = mark + "  "
        r1.font.size = Pt(max(10, size - 6))
        r1.font.name = th["fb"]
        r1.font.bold = True
        r1.font.color.rgb = C(acc)
        r2 = p.add_run()
        r2.text = b
        r2.font.size = Pt(size)
        r2.font.name = th["fb"]
        r2.font.color.rgb = C(th["text"])

    if has_banner:
        rect(s, 0.9, 6.1, 11.53, 0.78, th["banner"])
        rect(s, 0.9, 6.1, 0.12, 0.78, acc)
        kp = item["key_point"]
        text(s, 1.2, 6.1, 11.1, 0.78, kp, 18 if len(kp) < 90 else 15, th["banner_text"], True, th["fb"],
             anchor=MSO_ANCHOR.MIDDLE, italic=True)
    footer(s, n, th)
    if item.get("notes"):
        s.notes_slide.notes_text_frame.text = item["notes"]
    return s


def thanks_slide(prs, th, lang):
    s = prs.slides.add_slide(prs.slide_layouts[6])
    th["decor"](s, "title", 1, th)
    lab = LABELS[lang]
    text(s, 0.9, 1.5, 11.5, 1.3, lab["thanks"], 44, th["on_dark"], True, th["ft"], PP_ALIGN.CENTER,
         MSO_ANCHOR.MIDDLE)
    text(s, 0.9, 2.9, 11.5, 0.7, lab["q"], 26, th["sub"], font=th["fb"], align=PP_ALIGN.CENTER)
    shape(s, MSO_SHAPE.ROUNDED_RECTANGLE, 1.6, 3.95, 10.1, 1.8, th["accent"])
    text(s, 1.8, 4.0, 9.7, 0.8, f"★  Bu taqdimot {BOT_TAG} boti yordamida tayyorlandi", 24, th["on_accent"],
         True, th["fb"], PP_ALIGN.CENTER, MSO_ANCHOR.MIDDLE)
    text(s, 1.8, 4.8, 9.7, 0.8,
         f"Slayd, mustaqil ish va obyektivkani 1 daqiqada tayyorlang — Telegram’da {BOT_TAG}", 18,
         th["on_accent"], False, th["fb"], PP_ALIGN.CENTER, MSO_ANCHOR.MIDDLE)
    return s


def build_pptx(topic, subject, author, slides, out_path, theme="klassik", lang="uz"):
    th = THEMES.get(theme, THEMES["klassik"])
    prs = Presentation()
    prs.slide_width, prs.slide_height = Inches(W_IN), Inches(H_IN)

    title_slide(prs, th, topic, subject, author)
    agenda_titles = [x["title"] for x in slides[:-1]] or [x["title"] for x in slides]
    agenda_slide(prs, th, lang, agenda_titles, 2)
    for k, item in enumerate(slides):
        content_slide(prs, th, item, k + 3, k)
    thanks_slide(prs, th, lang)
    prs.save(out_path)
    return out_path
