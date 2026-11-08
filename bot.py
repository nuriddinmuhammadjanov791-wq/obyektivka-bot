"""
Obyektivka (ma'lumotnoma) Telegram boti.
Savollarni birin-ketin so'raydi, oxirida hammasini ko'rsatib, tahrirlash imkonini beradi
va tayyor Word (.docx) fayl yuboradi.
"""
import datetime
import logging
import os
import re
import tempfile

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

import ai
from docgen import build_docx
from paper import build_paper
from slides import build_pptx

logging.basicConfig(level=logging.INFO)

# (kalit, qisqa nom, savol)
PERSONAL = [
    ("fio", "F.I.Sh.", "Familiyangiz, ismingiz va otangizning ismini yozing.\nMasalan: Nursoatova Feruza Muxiddin qizi"),
    ("birth_date", "Tug‘ilgan sana", "Tug‘ilgan sanangiz (kun.oy.yil)?\nMasalan: 19.10.2008"),
    ("birth_place", "Tug‘ilgan joy", "Tug‘ilgan joyingiz (viloyat, tuman)?"),
    ("nationality", "Millati", "Millatingiz?"),
    ("party", "Partiyaviyligi", "Partiyaviyligingiz? (a’zo bo‘lmasangiz «yo‘q» deb yozing)"),
    ("education", "Ma’lumoti", "Ma’lumotingiz?\nMasalan: o‘rta, tugallanmagan oliy"),
    ("graduated", "Tamomlagan", "Qachon va qaysi maktab/kollejni tugatgansiz?\nMasalan: 2026 yil, Dehqonobod tumani 92-sonli o‘rta maktab"),
    ("specialty", "Mutaxassisligi", "Ma’lumoti bo‘yicha mutaxassisligingiz? (yo‘q bo‘lsa «yo‘q»)"),
    ("degree", "Ilmiy darajasi", "Ilmiy darajangiz? (yo‘q bo‘lsa «yo‘q»)"),
    ("rank", "Ilmiy unvoni", "Ilmiy unvoningiz? (yo‘q bo‘lsa «yo‘q»)"),
    ("languages", "Chet tillari", "Qaysi chet tillarini bilasiz?\nMasalan: rus tili, ingliz tili"),
    ("awards", "Mukofotlari", "Davlat mukofotlari bilan taqdirlanganmisiz? (yo‘q bo‘lsa «yo‘q»)"),
    ("deputy", "Deputatligi", "Xalq deputatlari Kengashi deputati yoki boshqa saylanadigan organ a’zosimisiz? (yo‘q bo‘lsa «yo‘q»)"),
    ("univ", "Universiteti", "Hozir o‘qiyotgan universitetingiz nomi?"),
    ("faculty", "Fakultet/yo‘nalish", "Fakultet va yo‘nalishingiz?\nMasalan: Kechki va Sirtqi ta’lim fakulteti (Ingliz tili) yo‘nalishi"),
    ("enroll", "Kirgan sanasi", "Universitetga qachon kirgansiz?\nMasalan: 2026 yil 7 sentabr"),
    ("phone", "Telefon", "Telefon raqamingiz?"),
]

RELATIVE = [
    ("kind", "Qarindoshligi? (otasi, onasi, akasi, ukasi, opasi, singlisi...)"),
    ("fio", "Uning familiyasi, ismi va otasining ismi?"),
    ("birth", "Tug‘ilgan yili va joyi?\nMasalan: 1983 yil, Qashqadaryo viloyati, Dehqonobod tumani"),
    ("work", "Ish joyi va lavozimi? (o‘quvchi / bog‘cha yoshida / nafaqada bo‘lsa shuni yozing)"),
    ("home", "Turar joyi? (viloyat, tuman, mahalla yoki shaharcha)"),
]

WORK_HELP = (
    "Endi mehnat faoliyatingizni yozing (maktab o‘quvchiligi ham kiradi).\n"
    "Har bir qatorni alohida xabar qilib yuboring.\n\n"
    "Masalan:\n2015 y – 2026 y. – Dehqonobod tumani 92-sonli maktab o‘quvchisi\n\n"
    "Hozirgi o‘qishingiz o‘zi avtomatik qo‘shiladi."
)

MENU_KB = InlineKeyboardMarkup([
    [InlineKeyboardButton("📄 Obyektivka tayyorlash", callback_data="m:obyektivka")],
    [InlineKeyboardButton("📊 Slayd tayyorlash", callback_data="m:slayd")],
    [InlineKeyboardButton("📝 Mustaqil ish tayyorlash", callback_data="m:mustaqil")],
    [InlineKeyboardButton("📞 Admin bilan bog‘lanish", callback_data="m:contact")],
])
MENU_BTN = InlineKeyboardButton("🏠 Menyu", callback_data="m:menu")
MENU_TEXT = "Assalomu alaykum! 👋 Nimani tayyorlab beray?"

LANGS = [("🇺🇿 O‘zbekcha", "uz"), ("🇷🇺 Русский", "ru"), ("🇬🇧 English", "en")]
# forma: (kalit, savol, variantlar yoki None)
FORMS = {
    "slayd": [
        ("topic", "Taqdimot mavzusi nima?", None),
        ("subject", "Fan nomi? (sarlavha slaydida chiqadi; kerak bo‘lmasa «-» yozing)", None),
        ("lang", "Qaysi tilda bo‘lsin?", LANGS),
        ("count", "Jami nechta slayd kerak?", [(str(n), str(n)) for n in (6, 8, 10, 12, 15)]),
        ("author", "Muallif (ism-familiya va guruh)?\nMasalan: Ali Valiyev, 101-guruh", None),
    ],
    "mustaqil": [
        ("subject", "Fan nomi?", None),
        ("topic", "Mustaqil ish mavzusi?", None),
        ("lang", "Qaysi tilda bo‘lsin?", LANGS),
        ("pages", "Taxminan necha bet kerak?", [(str(n), str(n)) for n in (5, 8, 10, 15, 20)]),
        ("author", "Muallif (ism-familiya va guruh)?\nMasalan: Ali Valiyev, 101-guruh", None),
        ("univ", "Universitet nomi? (titul varag‘ida chiqadi)", None),
        ("teacher", "Qabul qiluvchi o‘qituvchi (F.I.Sh.)? Kerak bo‘lmasa «-» yozing", None),
    ],
}
DAILY_LIMIT = int(os.getenv("DAILY_LIMIT", "3"))
USAGE = {}  # user_id -> (sana, soni)


def is_admin(uid):
    return str(uid) == str(os.getenv("ADMIN_ID", ""))


def quota_left(uid):
    if is_admin(uid):
        return 999
    day = datetime.date.today().isoformat()
    d, n = USAGE.get(uid, (day, 0))
    return DAILY_LIMIT - (n if d == day else 0)


def quota_use(uid):
    day = datetime.date.today().isoformat()
    d, n = USAGE.get(uid, (day, 0))
    USAGE[uid] = (day, (n if d == day else 0) + 1)


BACK_BTN = InlineKeyboardButton("⬅️ Bir qadam orqaga", callback_data="back")
BACK_KB = InlineKeyboardMarkup([[BACK_BTN]])
THANKS = (
    "Botdan foydalanganingiz uchun rahmat! 🙏\n\n"
    "Rahmatni ikki xil aytsangiz bo‘ladi 😁\n"
    "💳 <code>5614688708547111</code> N.M orqali 😅\n"
    "✍️ yoki @nuriddin26 ga samimiy yozib qo‘yish orqali 😊"
)

BTN_DONE_WORK = InlineKeyboardMarkup([[InlineKeyboardButton("✅ Tayyor", callback_data="work_done")]])
BTN_REL = InlineKeyboardMarkup([[
    InlineKeyboardButton("➕ Yana qarindosh", callback_data="rel_more"),
    InlineKeyboardButton("✅ Tugatish", callback_data="rel_done"),
]])


def fresh(ctx):
    ctx.user_data.clear()
    ctx.user_data.update(step="personal", i=0, data={"work": [], "relatives": []},
                         photo=None, rel={}, ri=0, from_review=False, edit_rel=None, edit_i=None)


async def drop_kb(ud):
    """Oldingi savoldagi «Orqaga» tugmasini olib tashlaydi (eski tugmalar adashtirmasin)."""
    prev = ud.pop("last_q", None)
    if prev is not None:
        try:
            await prev.edit_reply_markup(reply_markup=None)
        except Exception:
            pass


async def ask(msg, ud, text, kb=BACK_KB):
    ud["last_q"] = await msg.reply_text(text, reply_markup=kb)


async def ask_personal(msg, ud, i, prefix=""):
    await ask(msg, ud, prefix + PERSONAL[i][2], BACK_KB if i > 0 else None)


async def ask_photo(msg, ud):
    await ask(msg, ud, "3x4 rasmingizni yuboring (oddiy foto sifatida, fayl emas).\n"
                       "Rasm kerak bo‘lmasa «yo‘q» deb yozing.")


# ---------- Tekshiruv (tahrirlash) ekrani ----------
def review_text(ud):
    d = ud["data"]
    lines = ["📋 Barcha javoblaringiz:\n"]
    for n, (k, label, _) in enumerate(PERSONAL, 1):
        lines.append(f"{n}. {label}: {d[k]}")
    lines.append(f"\n📷 Rasm: {'bor' if ud.get('photo') else 'yo‘q'}")
    lines.append("\n💼 Mehnat faoliyati:")
    lines += [f"• {w}" for w in d["work"]] or ["—"]
    lines.append("\n👪 Qarindoshlar:")
    lines += [f"{n}. {r['kind']} — {r['fio']}" for n, r in enumerate(d["relatives"], 1)] or ["—"]
    lines.append("\nXato bo‘lsa, shu raqamni bosing (tahrirlash). Hammasi to‘g‘ri bo‘lsa — «Faylni olish».")
    return "\n".join(lines)


def review_kb(ud):
    d = ud["data"]
    nums = [InlineKeyboardButton(str(n), callback_data=f"e:{n-1}") for n in range(1, len(PERSONAL) + 1)]
    rows = [nums[i:i + 6] for i in range(0, len(nums), 6)]
    rows.append([InlineKeyboardButton("📷 Rasmni o‘zgartirish", callback_data="ephoto")])
    rows.append([InlineKeyboardButton("💼 Mehnat faoliyatini qayta yozish", callback_data="ework")])
    for n, r in enumerate(d["relatives"]):
        rows.append([
            InlineKeyboardButton(f"✏️ {r['kind'][:18]}", callback_data=f"erel:{n}"),
            InlineKeyboardButton("🗑 O‘chirish", callback_data=f"drel:{n}"),
        ])
    rows.append([InlineKeyboardButton("➕ Qarindosh qo‘shish", callback_data="addrel")])
    rows.append([InlineKeyboardButton("✅ Faylni olish", callback_data="finish")])
    return InlineKeyboardMarkup(rows)


async def show_review(msg, ud):
    ud["step"] = "review"
    ud["from_review"] = False
    ud["edit_rel"] = None
    await msg.reply_text(review_text(ud), reply_markup=review_kb(ud))


# ---------- Buyruqlar ----------
async def send_menu(msg, ud=None):
    if ud is not None:
        ud.clear()
    await msg.reply_text(MENU_TEXT, reply_markup=MENU_KB)


async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await send_menu(update.message, ctx.user_data)


async def begin_obyektivka(msg, ctx):
    fresh(ctx)
    ud = ctx.user_data
    await msg.reply_text(
        "📄 Obyektivka tayyorlaymiz. Savollarga birin-ketin javob bering. Oxirida hammasini "
        "ko‘rsataman — xato bo‘lsa, faqat o‘sha joyni tuzatasiz.\n\n"
        "Bir qadam orqaga: /orqaga yoki tugma. Menyu: /menu"
    )
    await ask(msg, ud, PERSONAL[0][2], InlineKeyboardMarkup([[MENU_BTN]]))


async def ask_field(msg, ud, prefix=""):
    key, text, opts = FORMS[ud["form"]][ud["fi"]]
    rows = []
    if opts:
        rows.append([InlineKeyboardButton(lab, callback_data=f"opt:{val}") for lab, val in opts])
    rows.append([BACK_BTN] if ud["fi"] > 0 else [MENU_BTN])
    await ask(msg, ud, prefix + text, InlineKeyboardMarkup(rows))


async def begin_form(msg, ud, name):
    ud.clear()
    ud.update(step="form", form=name, fi=0, fdata={}, busy=False)
    title = "📊 Slayd" if name == "slayd" else "📝 Mustaqil ish"
    await msg.reply_text(f"{title} tayyorlaymiz. Bir necha savol beraman. (Orqaga: /orqaga, menyu: /menu)")
    await ask_field(msg, ud)


async def begin_contact(msg, ud):
    ud.clear()
    ud["step"] = "contact"
    await ask(msg, ud, "📞 Xabaringizni yozing, adminga yetkazaman. Admin javobi shu yerga keladi.",
              InlineKeyboardMarkup([[MENU_BTN]]))


async def finish_form(msg, ctx, ud, user):
    uid = user.id
    if quota_left(uid) <= 0:
        await msg.reply_text(
            f"Bugungi limit ({DAILY_LIMIT} ta) tugadi. Ertaga yana urinib ko‘ring yoki admin bilan bog‘laning.",
            reply_markup=MENU_KB)
        ud.clear()
        return
    d = ud["fdata"]
    form = ud["form"]
    ud["busy"] = True
    await msg.reply_text("⏳ Tayyorlanmoqda, 1-2 daqiqa kuting…")
    try:
        if form == "slayd":
            n = int(d["count"])
            slides = await ai.make_slides(d["topic"], d["subject"], d["lang"], n - 1)
            out = os.path.join(tempfile.gettempdir(), f"slayd_{uid}.pptx")
            build_pptx(d["topic"], d["subject"], d["author"], slides, out)
            fname = "Taqdimot.pptx"
            caption = "Tayyor! ✅ Matnni o‘qib chiqing, kerak bo‘lsa PowerPoint’da tahrirlang."
        else:
            text = await ai.make_paper(d["subject"], d["topic"], d["lang"], int(d["pages"]))
            out = os.path.join(tempfile.gettempdir(), f"ish_{uid}.docx")
            build_paper(d, text, out)
            fname = "Mustaqil_ish.docx"
            caption = ("Tayyor! ✅ Matn sun’iy intellekt yordamida yozilgan: faktlar va adabiyotlar "
                       "ro‘yxatini albatta tekshirib, o‘zingizga moslab tahrirlang.")
        with open(out, "rb") as fh:
            await msg.reply_document(fh, filename=fname, caption=caption)
        quota_use(uid)
        await msg.reply_text(THANKS, parse_mode="HTML")
        await msg.reply_text("Yana nima kerak?", reply_markup=MENU_KB)
    except ai.AIError as e:
        logging.warning("AI xato: %s", e)
        if str(e) == "busy":
            txt = "Hozir juda ko‘p so‘rov bor. 1-2 daqiqadan keyin qayta urinib ko‘ring."
        elif str(e) == "no_key":
            txt = "Sun’iy intellekt hali ulanmagan. Admin bilan bog‘laning."
        else:
            txt = "Tayyorlashda xato chiqdi. Birozdan keyin qayta urinib ko‘ring."
        await msg.reply_text(txt, reply_markup=MENU_KB)
    except Exception:
        logging.exception("Generatsiya xatosi")
        await msg.reply_text("Kutilmagan xato. Qayta urinib ko‘ring.", reply_markup=MENU_KB)
    ud.clear()


async def form_answer(msg, ctx, ud, user, value):
    ud["fdata"][FORMS[ud["form"]][ud["fi"]][0]] = value
    ud["fi"] += 1
    if ud["fi"] < len(FORMS[ud["form"]]):
        await ask_field(msg, ud)
    else:
        await finish_form(msg, ctx, ud, user)


async def cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data.clear()
    await update.message.reply_text("Bekor qilindi.", reply_markup=MENU_KB)


async def do_back(msg, ud):
    step = ud.get("step")
    if not step:
        await send_menu(msg, ud)
        return
    if step == "edit_field":
        await show_review(msg, ud)
    elif step == "form":
        if ud["fi"] > 0:
            ud["fi"] -= 1
            await ask_field(msg, ud, "⬅️ Orqaga qaytdik.\n\n")
        else:
            await msg.reply_text("Bu birinchi savol. Menyuga qaytish: /menu")
    elif step == "contact":
        await send_menu(msg, ud)
    elif step == "personal":
        if ud["i"] > 0:
            ud["i"] -= 1
            await ask_personal(msg, ud, ud["i"], "⬅️ Orqaga qaytdik.\n\n")
        else:
            await msg.reply_text("Bu birinchi savol, orqaga qaytib bo‘lmaydi.")
    elif step == "photo":
        if ud["from_review"]:
            await show_review(msg, ud)
        else:
            ud["step"], ud["i"] = "personal", len(PERSONAL) - 1
            await ask_personal(msg, ud, ud["i"], "⬅️ Orqaga qaytdik.\n\n")
    elif step == "work":
        if ud["from_review"]:
            await show_review(msg, ud)
        else:
            ud["data"]["work"] = []
            ud["step"] = "photo"
            await ask_photo(msg, ud)
    elif step == "relative":
        if ud["ri"] > 0:
            ud["ri"] -= 1
            await ask(msg, ud, "⬅️ Orqaga qaytdik.\n\n" + RELATIVE[ud["ri"]][1])
        elif ud["from_review"]:
            ud["rel"] = {}
            await show_review(msg, ud)
        elif ud["data"]["relatives"]:
            ud["step"], ud["rel"] = "relative_menu", {}
            await msg.reply_text("Yana qarindosh qo‘shamizmi?", reply_markup=BTN_REL)
        else:
            ud["step"], ud["rel"] = "work", {}
            ud["data"]["work"] = []
            await ask(msg, ud, WORK_HELP)
    else:
        await msg.reply_text("Pastdagi tugmalardan foydalaning.")


async def back(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await drop_kb(ctx.user_data)
    await do_back(update.message, ctx.user_data)


# ---------- Matn / rasm ----------
async def on_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ud = ctx.user_data
    msg = update.message
    text = (msg.text or "").strip()
    user = update.effective_user

    # admin foydalanuvchi xabariga javob yozsa — foydalanuvchiga yuboriladi
    if is_admin(user.id) and msg.reply_to_message and msg.reply_to_message.text:
        m = re.search(r"ID:\s*(\d+)", msg.reply_to_message.text)
        if m:
            try:
                await ctx.bot.send_message(
                    int(m.group(1)), f"👨‍💻 Admin javobi:\n\n{text}",
                    reply_markup=InlineKeyboardMarkup(
                        [[InlineKeyboardButton("✍️ Javob yozish", callback_data="m:contact")]]))
                await msg.reply_text("Yuborildi ✅")
            except Exception:
                await msg.reply_text("Yuborib bo‘lmadi (foydalanuvchi botni to‘xtatgan bo‘lishi mumkin).")
            return

    step = ud.get("step")
    if not step:
        await send_menu(msg, ud)
        return
    if ud.get("busy"):
        await msg.reply_text("⏳ Hozir tayyorlanmoqda, biroz kuting…")
        return
    await drop_kb(ud)

    if step == "contact":
        admin = os.getenv("ADMIN_ID")
        if not admin:
            await msg.reply_text("Admin hozircha ulanmagan.", reply_markup=MENU_KB)
        else:
            name = user.full_name + (f" (@{user.username})" if user.username else "")
            await ctx.bot.send_message(int(admin), f"📩 Yangi xabar\n👤 {name}\nID: {user.id}\n\n{text}")
            await msg.reply_text("Xabaringiz adminga yuborildi ✅ Javob shu yerga keladi.", reply_markup=MENU_KB)
        ud.clear()
        return

    if step == "form":
        opts = FORMS[ud["form"]][ud["fi"]][2]
        if opts:
            hit = next((v for lab, v in opts if text.lower() in (v.lower(), lab.lower())), None)
            if hit is None:
                await msg.reply_text("Iltimos, yuqoridagi tugmalardan birini tanlang.")
                return
            text = hit
        await form_answer(msg, ctx, ud, user, text)
        return

    if step == "personal":
        ud["data"][PERSONAL[ud["i"]][0]] = text
        ud["i"] += 1
        if ud["i"] < len(PERSONAL):
            await ask_personal(msg, ud, ud["i"])
        else:
            ud["step"] = "photo"
            await ask_photo(msg, ud)

    elif step == "edit_field":
        ud["data"][PERSONAL[ud["edit_i"]][0]] = text
        await show_review(msg, ud)

    elif step == "photo":
        ud["photo"] = None
        if ud["from_review"]:
            await show_review(msg, ud)
        else:
            ud["step"] = "work"
            await ask(msg, ud, WORK_HELP)

    elif step == "work":
        ud["data"]["work"].append(text)
        await msg.reply_text("Qo‘shildi. Yana yozing yoki tugating:", reply_markup=BTN_DONE_WORK)

    elif step == "relative":
        ud["rel"][RELATIVE[ud["ri"]][0]] = text
        ud["ri"] += 1
        if ud["ri"] < len(RELATIVE):
            await ask(msg, ud, RELATIVE[ud["ri"]][1])
            return
        rel, idx = dict(ud["rel"]), ud["edit_rel"]
        ud["rel"], ud["ri"] = {}, 0
        if ud["from_review"]:
            if idx is None:
                ud["data"]["relatives"].append(rel)
            else:
                ud["data"]["relatives"][idx] = rel
            await show_review(msg, ud)
        else:
            ud["data"]["relatives"].append(rel)
            ud["step"] = "relative_menu"
            n = len(ud["data"]["relatives"])
            await msg.reply_text(f"{n}-qarindosh qo‘shildi. Yana qo‘shamizmi?", reply_markup=BTN_REL)
    else:
        await msg.reply_text("Iltimos, pastdagi tugmalardan birini bosing.")


async def on_photo(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ud = ctx.user_data
    if ud.get("step") != "photo":
        return
    await drop_kb(ud)
    f = await update.message.photo[-1].get_file()
    path = os.path.join(tempfile.gettempdir(), f"photo_{update.effective_user.id}.jpg")
    await f.download_to_drive(path)
    ud["photo"] = path
    await update.message.reply_text("Rasm qabul qilindi ✅")
    if ud["from_review"]:
        await show_review(update.message, ud)
    else:
        ud["step"] = "work"
        await ask(update.message, ud, WORK_HELP)


# ---------- Tugmalar ----------
async def on_button(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    ud = ctx.user_data
    msg = q.message
    step = ud.get("step")
    data = q.data

    if data.startswith("m:"):
        await drop_kb(ud)
        what = data[2:]
        if what == "obyektivka":
            await begin_obyektivka(msg, ctx)
        elif what in ("slayd", "mustaqil"):
            await begin_form(msg, ud, what)
        elif what == "contact":
            await begin_contact(msg, ud)
        else:
            await send_menu(msg, ud)
        return

    if not step:
        await msg.reply_text("Sessiya tugagan. Menyuga qaytamiz:", reply_markup=MENU_KB)
        return
    if ud.get("busy"):
        return
    await drop_kb(ud)

    if data.startswith("opt:") and step == "form":
        await form_answer(msg, ctx, ud, q.from_user, data[4:])
        return

    if data == "back":
        await do_back(msg, ud)

    elif data == "work_done" and step == "work":
        if not ud["data"]["work"]:
            await msg.reply_text("Hech bo‘lmasa bitta qator yozing (masalan, maktab o‘quvchisi).")
            return
        if ud["from_review"]:
            await show_review(msg, ud)
            return
        ud["step"] = "relative"
        await msg.reply_text(
            "Endi yaqin qarindoshlaringiz: ota, ona, aka-uka, opa-singillar.\n"
            "Har biri uchun alohida so‘rayman.\n(Xato qilsangiz: /orqaga)"
        )
        ud["rel"], ud["ri"] = {}, 0
        await ask(msg, ud, RELATIVE[0][1])

    elif data == "rel_more" and step == "relative_menu":
        ud["step"] = "relative"
        await ask(msg, ud, RELATIVE[0][1])

    elif data == "rel_done" and step == "relative_menu":
        await show_review(msg, ud)

    elif step == "review":
        if data.startswith("e:"):
            i = int(data[2:])
            ud["step"], ud["edit_i"] = "edit_field", i
            cur = ud["data"][PERSONAL[i][0]]
            await ask(msg, ud, f"Hozirgi javob: {cur}\n\nYangisini yozing:\n{PERSONAL[i][2]}")
        elif data == "ephoto":
            ud["step"], ud["from_review"] = "photo", True
            await ask(msg, ud, "Yangi 3x4 rasmni yuboring (yoki rasmni olib tashlash uchun «yo‘q» deb yozing).")
        elif data == "ework":
            ud["step"], ud["from_review"] = "work", True
            ud["data"]["work"] = []
            await ask(msg, ud, WORK_HELP + "\n\n(Eski yozuvlar o‘chirildi, hammasini qaytadan yozing.)")
        elif data.startswith("erel:"):
            n = int(data[5:])
            ud.update(step="relative", from_review=True, edit_rel=n, rel={}, ri=0)
            await ask(msg, ud, f"{n+1}-qarindoshni qaytadan kiritamiz.\n\n" + RELATIVE[0][1])
        elif data.startswith("drel:"):
            n = int(data[5:])
            if n < len(ud["data"]["relatives"]):
                ud["data"]["relatives"].pop(n)
            await show_review(msg, ud)
        elif data == "addrel":
            ud.update(step="relative", from_review=True, edit_rel=None, rel={}, ri=0)
            await ask(msg, ud, RELATIVE[0][1])
        elif data == "finish":
            await msg.reply_text("Fayl tayyorlanmoqda…")
            out = os.path.join(tempfile.gettempdir(), f"Obyektivka_{q.from_user.id}.docx")
            build_docx(ud["data"], out, ud.get("photo"))
            name = ud["data"]["fio"].split()[0]
            with open(out, "rb") as fh:
                await msg.reply_document(
                    fh, filename=f"Obyektivka_{name}.docx",
                    caption="Tayyor! Tekshirib ko‘ring. Yana o‘zgartirish kerak bo‘lsa /start bosing.")
            await msg.reply_text(THANKS, parse_mode="HTML")
            await msg.reply_text("Yana nima kerak?", reply_markup=MENU_KB)
            admin = os.getenv("ADMIN_ID")
            if admin:
                with open(out, "rb") as fh:
                    await ctx.bot.send_document(int(admin), fh, filename=f"Obyektivka_{name}.docx",
                                                caption=f"Yangi obyektivka: {ud['data']['fio']}")
            ud.clear()


def main():
    token = os.environ["BOT_TOKEN"]
    app = ApplicationBuilder().token(token).concurrent_updates(True).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("menu", start))
    app.add_handler(CommandHandler("cancel", cancel))
    app.add_handler(CommandHandler("orqaga", back))
    app.add_handler(CallbackQueryHandler(on_button))
    app.add_handler(MessageHandler(filters.PHOTO, on_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))

    base_url = os.getenv("RENDER_EXTERNAL_URL")
    if base_url:
        app.run_webhook(
            listen="0.0.0.0",
            port=int(os.getenv("PORT", "10000")),
            url_path=token,
            webhook_url=f"{base_url}/{token}",
        )
    else:
        app.run_polling()


if __name__ == "__main__":
    main()
