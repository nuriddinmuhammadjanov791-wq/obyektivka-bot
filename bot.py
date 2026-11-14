"""
Obyektivka (ma'lumotnoma) Telegram boti.
Savollarni birin-ketin so'raydi, oxirida hammasini ko'rsatib, tahrirlash imkonini beradi
va tayyor Word (.docx) fayl yuboradi.
"""
import asyncio
import collections
import datetime
import html
import io
import logging
import os
import random
import re
import tempfile
import time
import zipfile

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
from store import store
from telegram.error import BadRequest, Forbidden, RetryAfter
from docgen import build_docx
import crossword
import paper
import images
from slides import BOT_TAG, IMG_RATIO, THEME_OPTIONS, build_pptx

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

def _kb(*rows):
    return InlineKeyboardMarkup([[InlineKeyboardButton(t, callback_data=d) for t, d in row] for row in rows])


MENU_KB = _kb(
    [("📄 Obyektivka tayyorlash", "m:obyektivka")],
    [("📊 Slayd tayyorlash", "m:slayd")],
    [("📝 Mustaqil ish / Referat", "m:mustaqil")],
    [("📚 Boshqa hujjatlar", "m:docs"), ("🧰 O‘quv materiallari", "m:edu")],
    [("🖼 Rasmni PDF qilish", "m:pdf"), ("🗜 ZIP qilish", "m:zip")],
    [("🤖 AI yordamchi (savol-javob)", "m:ai")],
    [("👤 Profilim", "m:profil"), ("📖 Qo‘llanma", "m:help")],
    [("📞 Admin bilan bog‘lanish", "m:contact")],
)
AI_KB = _kb([("🧹 Yangi suhbat", "ai:new"), ("🏠 Menyu", "m:menu")])
CHAT_LIMIT = int(os.getenv("CHAT_LIMIT", "20"))
DOCS_KB = _kb(
    [("🎓 Kurs ishi", "m:kurs"), ("✍️ Insho", "m:insho")],
    [("📰 Ilmiy maqola", "m:maqola"), ("📄 Tezis", "m:tezis")],
    [("💼 Keys (case study)", "m:keys")],
    [("🏠 Menyu", "m:menu")],
)
EDU_KB = _kb(
    [("📝 Test yaratish", "m:test"), ("📖 Glossariy", "m:glossariy")],
    [("🧩 Krossvord", "m:krossvord")],
    [("🏠 Menyu", "m:menu")],
)
def rate_kb(form):
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("👍 Yoqdi", callback_data=f"rate:{form}:up"),
          InlineKeyboardButton("👎 Yoqmadi", callback_data=f"rate:{form}:down")]] + list(MENU_KB.inline_keyboard))


PDF_KB = _kb([("✅ PDF qilish", "pdf:make"), ("🗑 Tozalash", "pdf:clear")], [("🏠 Menyu", "m:menu")])
ZIP_KB = _kb([("✅ ZIP qilish", "zip:make"), ("🗑 Tozalash", "zip:clear")], [("🏠 Menyu", "m:menu")])
MAX_PDF = 20
MAX_ZIP_FILES, MAX_ZIP_BYTES = 30, 45 * 1024 * 1024
MENU_BTN = InlineKeyboardButton("🏠 Menyu", callback_data="m:menu")
MENU_TEXT = "Assalomu alaykum! 👋 Nimani tayyorlab beray?"

LANGS = [("🇺🇿 O‘zbekcha", "uz"), ("🇷🇺 Русский", "ru"), ("🇬🇧 English", "en")]
# forma: (kalit, savol, variantlar yoki None)
def _nums(*vals):
    return [(str(v), str(v)) for v in vals]


AUTHOR_Q = "Muallif (ism-familiya va guruh)?\nMasalan: Ali Valiyev, 101-guruh"
FORMS = {
    "slayd": [
        ("topic", "Taqdimot mavzusi nima?", None),
        ("subject", "Fan nomi? (sarlavha slaydida chiqadi; kerak bo‘lmasa «-» yozing)", None),
        ("lang", "Qaysi tilda bo‘lsin?", LANGS),
        ("count", "Jami nechta slayd kerak? (sarlavha, reja va yakuniy sahifa ham kiradi)", _nums(8, 10, 12, 15, 20)),
        ("theme", "Slayd uslubini (shablonini) tanlang:", THEME_OPTIONS),
        ("author", AUTHOR_Q, None),
    ],
    "mustaqil": [
        ("subject", "Fan nomi?", None),
        ("topic", "Mavzu?", None),
        ("doc", "Hujjat turi?", [("📘 Referat", "referat"), ("📝 Mustaqil ish", "mustaqil")]),
        ("lang", "Qaysi tilda bo‘lsin?", LANGS),
        ("pages", "Taxminan necha bet kerak?", _nums(5, 8, 10, 15, 20)),
        ("author", AUTHOR_Q, None),
        ("univ", "Universitet nomi? (titul varag‘ida chiqadi)", None),
        ("faculty", "Fakultet va yo‘nalish? Kerak bo‘lmasa «-» yozing", None),
        ("teacher", "Qabul qiluvchi o‘qituvchi (F.I.Sh.)? Kerak bo‘lmasa «-» yozing", None),
        ("city", "Shahar? (titulda «Toshkent – 2026» ko‘rinishida chiqadi; kerak bo‘lmasa «-»)", None),
    ],
    "kurs": [
        ("subject", "Fan nomi?", None),
        ("topic", "Kurs ishi mavzusi?", None),
        ("lang", "Qaysi tilda bo‘lsin?", LANGS),
        ("pages", "Taxminan necha bet kerak?", _nums(20, 25, 30, 40)),
        ("author", AUTHOR_Q, None),
        ("univ", "Universitet nomi?", None),
        ("faculty", "Fakultet va yo‘nalish? Kerak bo‘lmasa «-» yozing", None),
        ("teacher", "Ilmiy rahbar (F.I.Sh.)? Kerak bo‘lmasa «-» yozing", None),
        ("city", "Shahar? (kerak bo‘lmasa «-»)", None),
    ],
    "insho": [
        ("topic", "Insho mavzusi?", None),
        ("lang", "Qaysi tilda bo‘lsin?", LANGS),
        ("words", "Necha so‘z atrofida bo‘lsin?", _nums(300, 500, 800, 1000)),
        ("style", "Uslub?", [("🎓 Ilmiy-rasmiy", "formal"), ("🎨 Erkin", "free")]),
        ("author", "Muallif (F.I.Sh.)? Kerak bo‘lmasa «-» yozing", None),
    ],
    "maqola": [
        ("topic", "Maqola mavzusi?", None),
        ("field", "Ilmiy soha? (masalan: ekologiya, iqtisodiyot, pedagogika)", None),
        ("lang", "Qaysi tilda bo‘lsin?", LANGS),
        ("pages", "Necha bet?", _nums(3, 4, 5, 6)),
        ("author", "Muallif (F.I.Sh.)?", None),
        ("workplace", "Ish yoki o‘qish joyi (masalan: TDTU, 2-kurs talabasi)?", None),
    ],
    "tezis": [
        ("topic", "Tezis mavzusi?", None),
        ("field", "Ilmiy soha?", None),
        ("lang", "Qaysi tilda bo‘lsin?", LANGS),
        ("author", "Muallif (F.I.Sh.)?", None),
        ("workplace", "Ish yoki o‘qish joyi (masalan: TDTU, 2-kurs talabasi)?", None),
    ],
    "keys": [
        ("subject", "Fan nomi?", None),
        ("topic", "Keys mavzusi?", None),
        ("lang", "Qaysi tilda bo‘lsin?", LANGS),
        ("author", "Tayyorlovchi (F.I.Sh.)? Kerak bo‘lmasa «-» yozing", None),
    ],
    "test": [
        ("subject", "Fan nomi?", None),
        ("topic", "Test mavzusi?", None),
        ("lang", "Qaysi tilda bo‘lsin?", LANGS),
        ("count", "Nechta savol?", _nums(10, 20, 30, 50)),
        ("level", "Murakkablik darajasi?", [("🟢 Oson", "easy"), ("🟡 O‘rta", "mid"), ("🔴 Murakkab", "hard")]),
    ],
    "glossariy": [
        ("subject", "Fan nomi?", None),
        ("topic", "Mavzu?", None),
        ("lang", "Qaysi tilda bo‘lsin?", LANGS),
        ("count", "Nechta atama?", _nums(15, 25, 40)),
    ],
    "krossvord": [
        ("topic", "Krossvord mavzusi?", None),
        ("lang", "Qaysi tilda bo‘lsin?", LANGS),
        ("count", "Nechta so‘z?", _nums(10, 15, 20)),
    ],
}
FORMS["profil"] = [
    ("author", "Muallif (ism-familiya va guruh)?\nMasalan: Ali Valiyev, 101-guruh", None),
    ("univ", "Universitet nomi?", None),
    ("faculty", "Fakultet va yo‘nalish? Kerak bo‘lmasa «-» yozing", None),
    ("city", "Shahar? Kerak bo‘lmasa «-» yozing", None),
]
FORM_TITLES = {
    "profil": "👤 Profil",
    "slayd": "📊 Slayd", "mustaqil": "📝 Mustaqil ish / Referat", "kurs": "🎓 Kurs ishi", "insho": "✍️ Insho",
    "maqola": "📰 Ilmiy maqola", "tezis": "📄 Tezis", "keys": "💼 Keys", "test": "📝 Test",
    "glossariy": "📖 Glossariy", "krossvord": "🧩 Krossvord",
}
DAILY_LIMIT = int(os.getenv("DAILY_LIMIT", "3"))


def is_admin(uid):
    return str(uid) == str(os.getenv("ADMIN_ID", ""))


_hits = {}
_warned = {}
RATE = {"msg": (8, 10), "media": (30, 10)}  # (nechta, necha soniyada)
PROFILE_KEYS = {
    "slayd": ["author"], "insho": ["author"], "keys": ["author"],
    "mustaqil": ["author", "univ", "faculty", "city"], "kurs": ["author", "univ", "faculty", "city"],
}
PROFILE_LABELS = {"author": "Muallif", "univ": "Universitet", "faculty": "Fakultet/yo‘nalish", "city": "Shahar"}
HELP_TEXT = (
    "📖 Qo‘llanma\n\n"
    "📄 Obyektivka — savollarga javob bering, tayyor Word fayl olasiz.\n"
    "📊 Slayd — mavzu, til, shablon tanlang; rasmli taqdimot (.pptx).\n"
    "📝 Mustaqil ish / Referat, 🎓 Kurs ishi, 📰 Maqola, 📄 Tezis, ✍️ Insho, 💼 Keys — davlat talablariga "
    "(A4, TNR 14, 1,5 interval, chekkalar) mos Word fayl.\n"
    "🧰 Test, Glossariy, Krossvord — o‘quv materiallari.\n"
    "🖼 Rasmni PDF, 🗜 ZIP — fayllarni o‘zgartirish (AI kerak emas).\n"
    "🤖 AI yordamchi — istalgan savolga javob.\n\n"
    f"Limit: kuniga {DAILY_LIMIT} ta hujjat va {CHAT_LIMIT} ta AI xabar.\n"
    "👤 Profilim — ism, universitet bir marta saqlanadi, qayta so‘ralmaydi.\n\n"
    "Buyruqlar: /menu — bosh menyu, /orqaga — bir qadam orqaga, /profil, /yordam, /cancel.\n"
    "Muhim: AI yozgan matnni albatta o‘qib chiqib, faktlarni tekshiring va o‘zingizga moslang."
)


def allowed(uid, kind="msg"):
    if is_admin(uid):
        return True
    n, per = RATE[kind]
    now = time.monotonic()
    dq = _hits.setdefault((uid, kind), collections.deque())
    while dq and now - dq[0] > per:
        dq.popleft()
    if len(dq) >= n:
        return False
    dq.append(now)
    return True


async def guard(user, msg, kind="msg"):
    """Foydalanuvchini hisobga oladi va juda tez yozayotganini to'xtatadi."""
    await store.seen(user)
    if allowed(user.id, kind):
        return True
    now = time.monotonic()
    last = _warned.get(user.id)
    if last is None or now - last > 10:
        _warned[user.id] = now
        try:
            await msg.reply_text("⏳ Juda tez yubordingiz. Biroz sekinroq 🙂")
        except Exception:
            pass
    return False


async def notify_admin(ctx, text):
    admin = os.getenv("ADMIN_ID")
    if admin:
        try:
            await ctx.bot.send_message(int(admin), text[:3500])
        except Exception:
            pass


def quota_left(uid):
    return 999 if is_admin(uid) else DAILY_LIMIT - store.used(uid, "doc")


def quota_use(uid):
    store.add_used(uid, "doc")


PROMO = (f"✨ {BOT_TAG} — slayd, mustaqil ish va obyektivkani bir daqiqada tayyorlaydigan bot. "
         "Do‘stlaringizga ham ulashing!")
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
    if not await guard(update.effective_user, update.message):
        return
    await send_menu(update.message, ctx.user_data)


async def profil_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await guard(update.effective_user, update.message):
        return
    ctx.user_data.clear()
    await show_profile(update.message, update.effective_user.id)


async def help_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await guard(update.effective_user, update.message):
        return
    await update.message.reply_text(HELP_TEXT, reply_markup=MENU_KB)


BG_TASKS = set()


async def elon_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    if not await guard(u, update.message):
        return
    now_off = not store.is_optout(u.id)
    store.set_optout(u.id, now_off)
    await update.message.reply_text("🔕 E’lonlar o‘chirildi." if now_off else "🔔 E’lonlar yoqildi.")


async def bc_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    if not is_admin(u.id):
        return  # oddiy foydalanuvchiga hech narsa bildirmaymiz
    logging.info("ADMIN uid=%s cmd=/xabar", u.id)
    ctx.user_data.clear()
    ctx.user_data["step"] = "bc_wait"
    n = len(await store.broadcast_ids())
    await update.message.reply_text(
        f"📢 E’lon: hozir {n} ta foydalanuvchiga yuboriladi.\n\n"
        "E’lon xabarini yuboring (matn, rasm yoki video + izoh). Oxiriga «E’lonlarni o‘chirish: /elon» "
        "qo‘shsangiz, odamlar bloklamaydi. Bekor qilish: /cancel")


async def bc_capture(update, ctx):
    """Admin e'lon matnini yuborganda: ko'rinishini tasdiqlashga qo'yadi."""
    ud, u, m = ctx.user_data, update.effective_user, update.message
    if ud.get("step") != "bc_wait" or not is_admin(u.id):
        return False
    ud["bc"] = (m.chat_id, m.message_id)
    ud["step"] = "bc_confirm"
    n = len(await store.broadcast_ids())
    await m.reply_text(f"👆 Shu xabar {n} ta foydalanuvchiga yuboriladi. Tasdiqlaysizmi?",
                       reply_markup=_kb([("✅ Yuborish", "bc:go"), ("❌ Bekor", "bc:no")]))
    return True


async def run_broadcast(bot, admin_id, chat_id, mid, ids):
    ok = blocked = failed = 0
    for i, uid in enumerate(ids, 1):
        try:
            try:
                await bot.copy_message(chat_id=uid, from_chat_id=chat_id, message_id=mid)
            except RetryAfter as e:
                ra = e.retry_after
                await asyncio.sleep((ra.total_seconds() if hasattr(ra, "total_seconds") else float(ra)) + 1)
                await bot.copy_message(chat_id=uid, from_chat_id=chat_id, message_id=mid)
            ok += 1
        except Forbidden:
            store.mark_blocked(uid)
            blocked += 1
        except BadRequest as e:
            if "chat not found" in str(e).lower():
                store.mark_blocked(uid)
                blocked += 1
            else:
                failed += 1
        except Exception:
            failed += 1
        await asyncio.sleep(0.05)  # soniyasiga ~20 ta: Telegram limitidan (30) past
        if i % 200 == 0:
            try:
                await bot.send_message(admin_id, f"… {i}/{len(ids)} yuborildi")
            except Exception:
                pass
    try:
        await bot.send_message(admin_id, f"✅ E’lon tugadi.\nYuborildi: {ok}\nBotni bloklagan: {blocked}\nXato: {failed}")
    except Exception:
        pass


async def stat_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    if not is_admin(u.id):
        return  # oddiy foydalanuvchiga hech narsa bildirmaymiz
    logging.info("ADMIN uid=%s cmd=/stat", u.id)
    await update.message.reply_text(await store.stats_text())


async def on_error(update, ctx: ContextTypes.DEFAULT_TYPE):
    logging.error("Handler xatosi", exc_info=ctx.error)
    await notify_admin(ctx, f"⚠️ Bot xatosi: {type(ctx.error).__name__}: {ctx.error}")
    m = getattr(update, "effective_message", None)
    if m is not None:
        try:
            await m.reply_text("⚠️ Kutilmagan xato chiqdi. Bosh menyuga qaytish: /menu")
        except Exception:
            pass


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
        btns = [InlineKeyboardButton(lab, callback_data=f"opt:{val}") for lab, val in opts]
        rows += [btns[i:i + 3] for i in range(0, len(btns), 3)]
    rows.append([BACK_BTN] if ud["fi"] > 0 else [MENU_BTN])
    await ask(msg, ud, prefix + text, InlineKeyboardMarkup(rows))


def advance(ud):
    form = FORMS[ud["form"]]
    ud["fi"] += 1
    while ud["fi"] < len(form) and form[ud["fi"]][0] in ud.get("prefill", {}):
        ud["fi"] += 1


async def begin_form(msg, ud, name, uid=None):
    ud.clear()
    prof = store.profile(uid) if uid else {}
    prefill = {k: prof[k] for k in PROFILE_KEYS.get(name, []) if prof.get(k)}
    ud.update(step="form", form=name, fi=-1, fdata=dict(prefill), prefill=prefill, busy=False)
    advance(ud)
    await msg.reply_text(f"{FORM_TITLES[name]} tayyorlaymiz. Bir necha savol beraman. "
                         "(Orqaga: /orqaga, menyu: /menu)")
    if prefill:
        names = ", ".join(PROFILE_LABELS[k] for k in prefill)
        await msg.reply_text(f"💾 Profilingizdan olindi: {names}. O‘zgartirish uchun «⬅️ Orqaga» yoki 👤 Profilim.")
    await ask_field(msg, ud)


async def show_profile(msg, uid):
    prof = store.profile(uid)
    if prof:
        body = "\n".join(f"• {PROFILE_LABELS.get(k, k)}: {v}" for k, v in prof.items())
        text = "👤 Profilingiz:\n" + body + "\n\nBu ma’lumotlar keyingi hujjatlarda qayta so‘ralmaydi."
    else:
        text = ("👤 Profilingiz hali bo‘sh. Birinchi hujjatni tayyorlaganingizda ism va universitet "
                "avtomatik saqlanadi, yoki hozir o‘zingiz kiriting.")
    opt = ("🔔 E’lonlarni yoqish", "prof:optin") if store.is_optout(uid) else ("🔕 E’lonlarni o‘chirish", "prof:optout")
    await msg.reply_text(text, reply_markup=_kb(
        [("✏️ O‘zgartirish", "m:profedit"), ("🗑 O‘chirish", "prof:del")], [opt], [("🏠 Menyu", "m:menu")]))


async def begin_pdf(msg, ud):
    ud.clear()
    ud.update(step="pdf", pics=[], busy=False, last_group=None)
    await ask(msg, ud,
              f"🖼 Rasmlarni yuboring (bir yoki bir nechta, ko‘pi bilan {MAX_PDF} ta). Hujjat yoki konspekt "
              "bo‘lsa, 📎 → Fayl orqali yuborsangiz sifati yaxshi bo‘ladi. Hammasi yuborilgach «PDF qilish» ni bosing. "
              "Sahifalar yuborilgan tartibda joylashadi.",
              InlineKeyboardMarkup([[MENU_BTN]]))


def _alive(ud, step, key):
    """Yuklab olish davomida sessiya tugamaganini tekshiradi."""
    return ud.get("step") == step and key in ud


async def add_pdf_image(msg, ud, tg_file, group):
    if not _alive(ud, "pdf", "pics"):
        return
    first = group is None or ud.get("last_group") != group
    ud["last_group"] = group
    if len(ud["pics"]) >= MAX_PDF:
        if first:
            await msg.reply_text(f"Ko‘pi bilan {MAX_PDF} ta rasm. «PDF qilish» ni bosing.", reply_markup=PDF_KB)
        return
    ud["pending"] = ud.get("pending", 0) + 1
    try:
        raw = await tg_file.download_as_bytearray()
        data = images.shrink(bytes(raw))
    finally:
        ud["pending"] = max(0, ud.get("pending", 1) - 1)
    if not _alive(ud, "pdf", "pics"):
        return  # PDF allaqachon tayyorlangan yoki sessiya tugagan
    if data is None:
        await msg.reply_text("Bu rasmni ochib bo‘lmadi (JPG yoki PNG yuboring).")
        return
    ud["pics"].append((msg.message_id, data))
    if not first:
        return  # albom: har bir rasm uchun alohida javob bermaymiz
    await drop_kb(ud)
    await ask(msg, ud, "📷 Qabul qilindi. Yana yuboring yoki PDF qiling "
                       "(albom yuborgan bo‘lsangiz, hammasi qo‘shiladi):", PDF_KB)


def md_to_html(t):
    """Gemini'ning markdown javobini Telegram HTML'ga aylantiradi."""
    t = html.escape(t, quote=False)
    t = re.sub(r"```(?:\w+)?\n?(.*?)```", lambda m: "<pre>" + m.group(1) + "</pre>", t, flags=re.S)
    t = re.sub(r"`([^`\n]+)`", r"<code>\1</code>", t)
    t = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", t, flags=re.S)
    t = re.sub(r"(?m)^#{1,6}\s*(.+)$", r"<b>\1</b>", t)
    t = re.sub(r"(?m)^\s*[\*\-]\s+", "• ", t)
    return t


def split_text(t, size=3800):
    parts = []
    while len(t) > size:
        cut = t.rfind("\n\n", 0, size)
        if cut < size // 2:
            cut = t.rfind("\n", 0, size)
        if cut < size // 2:
            cut = size
        parts.append(t[:cut].strip())
        t = t[cut:].strip()
    if t:
        parts.append(t)
    return parts


def chat_left(uid):
    return 999 if is_admin(uid) else CHAT_LIMIT - store.used(uid, "chat")


def chat_use(uid):
    store.add_used(uid, "chat")


async def begin_ai(msg, ud):
    ud.clear()
    ud.update(step="ai", hist=[], busy=False)
    await ask(msg, ud,
              "🤖 Men AI yordamchiman. Istalgan savolingizni yozing: dars mavzusini tushuntirish, tarjima, "
              f"g‘oya, maslahat. Har kuni {CHAT_LIMIT} tagacha xabar. Mavzuni almashtirmoqchi bo‘lsangiz, "
              "«🧹 Yangi suhbat» ni bosing.", AI_KB)


async def ai_answer(msg, ctx, ud, user, text):
    if chat_left(user.id) <= 0:
        await msg.reply_text(f"Bugungi limit ({CHAT_LIMIT} ta xabar) tugadi. Ertaga davom etamiz 🙂", reply_markup=MENU_KB)
        ud.clear()
        return
    ud["busy"] = True
    try:
        try:
            await ctx.bot.send_chat_action(msg.chat_id, "typing")
        except Exception:
            pass
        answer = await ai.chat(ud["hist"], text)
        chat_use(user.id)
        ud["hist"] += [{"role": "user", "text": text}, {"role": "model", "text": answer}]
        ud["hist"] = ud["hist"][-12:]
        chunks = split_text(answer)
        sent = None
        for i, ch in enumerate(chunks):
            kb = AI_KB if i == len(chunks) - 1 else None
            try:
                sent = await msg.reply_text(md_to_html(ch), parse_mode="HTML", reply_markup=kb)
            except Exception:
                sent = await msg.reply_text(ch, reply_markup=kb)
        ud["last_q"] = sent
    except ai.AIError as e:
        logging.warning("AI chat xato: %s", e)
        txt = ("Hozir juda ko‘p so‘rov bor, 1 daqiqadan keyin qayta yozing."
               if str(e) == "busy" else "Javob olishda xato chiqdi. Qayta urinib ko‘ring.")
        await msg.reply_text(txt, reply_markup=AI_KB)
    except Exception:
        logging.exception("AI chat xatosi")
        await msg.reply_text("Kutilmagan xato. Qayta urinib ko‘ring.", reply_markup=AI_KB)
    finally:
        ud["busy"] = False


async def begin_zip(msg, ud):
    ud.clear()
    ud.update(step="zip", files=[], size=0, busy=False, last_group=None)
    await ask(msg, ud,
              f"🗜 Fayllarni yuboring (hujjat, rasm, video — ko‘pi bilan {MAX_ZIP_FILES} ta, jami 45 MB gacha; "
              "Telegram har bir faylni 20 MB gacha yuklab olishga ruxsat beradi). "
              "Hammasi yuborilgach «ZIP qilish» ni bosing.",
              InlineKeyboardMarkup([[MENU_BTN]]))


async def add_zip_file(msg, ud, tg_file, name, group):
    if not _alive(ud, "zip", "files"):
        return
    first = group is None or ud.get("last_group") != group
    ud["last_group"] = group
    if len(ud["files"]) >= MAX_ZIP_FILES or ud["size"] >= MAX_ZIP_BYTES:
        if first:
            await msg.reply_text("Limitga yetdi. «ZIP qilish» ni bosing.", reply_markup=ZIP_KB)
        return
    ud["pending"] = ud.get("pending", 0) + 1
    try:
        raw = bytes(await tg_file.download_as_bytearray())
    except Exception:
        await msg.reply_text("Bu faylni yuklab bo‘lmadi (20 MB dan katta bo‘lishi mumkin).")
        return
    finally:
        ud["pending"] = max(0, ud.get("pending", 1) - 1)
    if not _alive(ud, "zip", "files"):
        return
    if ud["size"] + len(raw) > MAX_ZIP_BYTES:
        await msg.reply_text("Jami hajm 45 MB dan oshib ketadi, bu fayl qo‘shilmadi.", reply_markup=ZIP_KB)
        return
    used = {n for n, _ in ud["files"]}
    base, dot, ext = name.rpartition(".")
    if not dot:
        base, ext = name, ""
    k, final = 1, name
    while final in used:
        k += 1
        final = f"{base} ({k}).{ext}" if ext else f"{base} ({k})"
    ud["files"].append((final, raw))
    ud["size"] += len(raw)
    if not first:
        return
    await drop_kb(ud)
    await ask(msg, ud, "📎 Qabul qilindi. Yana yuboring yoki ZIP qiling "
                       "(bir nechta fayl yuborgan bo‘lsangiz, hammasi qo‘shiladi):", ZIP_KB)


async def wait_uploads(ud):
    """Albomning hamma rasmi yuklab bo'linishini (ko'pi bilan ~9 soniya) kutadi."""
    for _ in range(30):
        if not ud.get("pending"):
            break
        await asyncio.sleep(0.3)


async def begin_contact(msg, ud):
    ud.clear()
    ud["step"] = "contact"
    await ask(msg, ud, "📞 Xabaringizni yozing, adminga yetkazaman. Admin javobi shu yerga keladi.",
              InlineKeyboardMarkup([[MENU_BTN]]))


WAIT_TEXT = {
    "slayd": "2-3 daqiqa (matn va rasmlar tayyorlanmoqda)",
    "mustaqil": "3-5 daqiqa (uzun ish bo‘limma-bo‘lim yoziladi)",
    "kurs": "5-8 daqiqa (kurs ishi bo‘limma-bo‘lim yoziladi)",
    "maqola": "2-3 daqiqa", "tezis": "1-2 daqiqa", "insho": "1-2 daqiqa", "keys": "1-2 daqiqa",
    "test": "1-3 daqiqa", "glossariy": "1-2 daqiqa", "krossvord": "1-2 daqiqa",
}
AI_NOTE = ("Matn sun’iy intellekt yordamida yozilgan: faktlar, havolalar va adabiyotlar ro‘yxatini albatta "
           "tekshirib, o‘zingizga moslab tahrirlang.")


async def build_output(form, d, uid):
    """Tanlangan imkoniyat bo'yicha fayl yaratadi. (yo'l, fayl nomi, izoh) qaytaradi."""
    tmp = tempfile.gettempdir()
    if form == "slayd":
        n = int(d["count"])
        slides = await ai.make_slides(d["topic"], d["subject"], d["lang"], n - 3)
        pics = await images.fetch_all([x.get("image_query", "") for x in slides], IMG_RATIO)
        for x, p in zip(slides, pics):
            x["img"] = p
        out = os.path.join(tmp, f"slayd_{uid}.pptx")
        build_pptx(d["topic"], d["subject"], d["author"], slides, out, d["theme"], d["lang"])
        return out, "Taqdimot.pptx", ("Tayyor! ✅ Har bir slaydning izohi (notes) ham bor. Matnni o‘qib chiqing, "
                                      "kerak bo‘lsa PowerPoint’da tahrirlang.")
    if form in ("mustaqil", "kurs"):
        kind = "kurs" if form == "kurs" else d["doc"]
        text = await ai.write_document(kind, d["subject"], d["topic"], d["lang"], int(d["pages"]))
        out = os.path.join(tmp, f"ish_{uid}.docx")
        paper.build_paper(d, text, out, kind)
        names = {"mustaqil": "Mustaqil_ish.docx", "referat": "Referat.docx", "kurs": "Kurs_ishi.docx"}
        return out, names[kind], "Tayyor! ✅ Talab: A4, Times New Roman 14, 1,5 interval, chap 30/o‘ng 15/yuqori-past 20 mm. " + AI_NOTE
    if form == "maqola":
        text, ann = await asyncio.gather(
            ai.write_document("maqola", d["field"], d["topic"], d["lang"], int(d["pages"])),
            ai.make_annotations(d["topic"], d["field"], d["lang"]))
        out = os.path.join(tmp, f"maqola_{uid}.docx")
        paper.build_article(d, ann, text, out)
        return out, "Ilmiy_maqola.docx", ("Tayyor! ✅ Muallif o‘ngda, sarlavha o‘rtada, 3 tilda annotatsiya, "
                                          "har tomondan 20 mm. UO‘K indeksini o‘zingiz qo‘shing. " + AI_NOTE)
    if form == "tezis":
        text = await ai.make_tezis(d["topic"], d["field"], d["lang"])
        out = os.path.join(tmp, f"tezis_{uid}.docx")
        paper.build_tezis(d, None, text, out)
        return out, "Tezis.docx", "Tayyor! ✅ " + AI_NOTE
    if form == "insho":
        text = await ai.make_insho(d["topic"], d["lang"], int(d["words"]), d["style"])
        out = os.path.join(tmp, f"insho_{uid}.docx")
        paper.build_insho(d, text, out)
        return out, "Insho.docx", "Tayyor! ✅ O‘qib chiqib, o‘z uslubingizga moslang."
    if form == "keys":
        text = await ai.make_keys(d["subject"], d["topic"], d["lang"])
        out = os.path.join(tmp, f"keys_{uid}.docx")
        paper.build_keys(d, text, out)
        return out, "Keys.docx", "Tayyor! ✅ " + AI_NOTE
    if form == "test":
        qs = await ai.make_test(d["subject"], d["topic"], d["lang"], int(d["count"]), d["level"])
        items = []
        for q in qs:
            opts = [q["correct"]] + q["wrong"]
            random.shuffle(opts)
            items.append({"q": q["q"], "options": opts, "answer": "ABCD"[opts.index(q["correct"])]})
        out = os.path.join(tmp, f"test_{uid}.docx")
        paper.build_test(d, items, out)
        return out, "Test.docx", f"Tayyor! ✅ {len(items)} ta savol, oxirida javoblar kaliti. Savollarni tekshirib chiqing."
    if form == "glossariy":
        terms = await ai.make_glossary(d["subject"], d["topic"], d["lang"], int(d["count"]))
        out = os.path.join(tmp, f"glos_{uid}.docx")
        paper.build_glossary(d, terms, out)
        return out, "Glossariy.docx", f"Tayyor! ✅ {len(terms)} ta atama, alifbo tartibida."
    if form == "krossvord":
        items = await ai.make_crossword_words(d["topic"], d["lang"], int(d["count"]))
        g = crossword.build_grid(items, int(d["count"]))
        out = os.path.join(tmp, f"kross_{uid}.docx")
        paper.build_crossword(d, g, out)
        return out, "Krossvord.docx", f"Tayyor! ✅ {g['count']} ta so‘z joylashdi. 2-sahifada javoblar bor."
    raise ValueError(form)


async def finish_form(msg, ctx, ud, user):
    uid = user.id
    if ud["form"] != "profil" and quota_left(uid) <= 0:
        await msg.reply_text(
            f"Bugungi limit ({DAILY_LIMIT} ta) tugadi. Ertaga yana urinib ko‘ring yoki admin bilan bog‘laning.",
            reply_markup=MENU_KB)
        ud.clear()
        return
    d, form = ud["fdata"], ud["form"]
    if form == "profil":
        store.set_profile(uid, **{k: v for k, v in d.items() if v and v not in ("-", "—")})
        await msg.reply_text("✅ Profil saqlandi.", reply_markup=MENU_KB)
        ud.clear()
        return
    ud["busy"] = True
    await msg.reply_text(f"⏳ Tayyorlanmoqda, {WAIT_TEXT.get(form, '1-3 daqiqa')} kuting…")
    try:
        out, fname, caption = await build_output(form, d, uid)
        with open(out, "rb") as fh:
            await msg.reply_document(fh, filename=fname, caption=caption + "\n\n" + PROMO)
        quota_use(uid)
        store.count(form)
        changed = store.save_from_form(uid, PROFILE_KEYS.get(form, []), d)
        await msg.reply_text(THANKS, parse_mode="HTML")
        if changed:
            await msg.reply_text("💾 Ma’lumotlaringiz profilga saqlandi, keyingi safar qayta so‘ralmaydi "
                                 "(o‘zgartirish: 👤 Profilim).")
        await msg.reply_text("Natija yoqdimi? Yana nima kerak?", reply_markup=rate_kb(form))
    except ai.AIError as e:
        logging.warning("AI xato: %s", e)
        if str(e) != "busy":
            await notify_admin(ctx, f"⚠️ {form} xatosi (user {uid}): {e}")
        if str(e) == "busy":
            txt = "Hozir juda ko‘p so‘rov bor. 1-2 daqiqadan keyin qayta urinib ko‘ring."
        elif str(e) == "no_key":
            txt = "Sun’iy intellekt hali ulanmagan. Admin bilan bog‘laning."
        else:
            txt = "Tayyorlashda xato chiqdi. Birozdan keyin qayta urinib ko‘ring."
        await msg.reply_text(txt, reply_markup=MENU_KB)
    except Exception as e:
        logging.exception("Generatsiya xatosi")
        await notify_admin(ctx, f"⚠️ {form} kutilmagan xato (user {uid}): {type(e).__name__}: {e}")
        await msg.reply_text("Kutilmagan xato. Qayta urinib ko‘ring.", reply_markup=MENU_KB)
    ud.clear()


async def form_answer(msg, ctx, ud, user, value):
    ud["fdata"][FORMS[ud["form"]][ud["fi"]][0]] = value
    advance(ud)
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
    if not await guard(user, msg):
        return
    if await bc_capture(update, ctx):
        return

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

    if step == "ai":
        await ai_answer(msg, ctx, ud, user, text)
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
    msg = update.message
    if not await guard(update.effective_user, msg, "media"):
        return
    if await bc_capture(update, ctx):
        return
    if not ud.get("step"):  # menyuda turib rasm yuborsa — PDF rejimini o'zi boshlaymiz
        await begin_pdf(msg, ud)
    step = ud.get("step")
    if step == "pdf":
        f = await msg.photo[-1].get_file()
        await add_pdf_image(msg, ud, f, msg.media_group_id)
        return
    if step == "zip":
        f = await msg.photo[-1].get_file()
        await add_zip_file(msg, ud, f, f"rasm_{msg.message_id}.jpg", msg.media_group_id)
        return
    if step != "photo":
        return
    await drop_kb(ud)
    f = await msg.photo[-1].get_file()
    path = os.path.join(tempfile.gettempdir(), f"photo_{update.effective_user.id}.jpg")
    await f.download_to_drive(path)
    ud["photo"] = path
    await msg.reply_text("Rasm qabul qilindi ✅")
    if ud["from_review"]:
        await show_review(msg, ud)
    else:
        ud["step"] = "work"
        await ask(msg, ud, WORK_HELP)


async def on_doc(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Fayl sifatida yuborilgan hujjat/rasm."""
    ud = ctx.user_data
    msg = update.message
    if not await guard(update.effective_user, msg, "media"):
        return
    if await bc_capture(update, ctx):
        return
    doc = msg.document
    is_img = (doc.mime_type or "").startswith("image/")
    if not ud.get("step"):
        if is_img:
            await begin_pdf(msg, ud)
        else:
            await msg.reply_text("Faylni ZIP qilmoqchimisiz? Menyudan «🗜 ZIP qilish» ni tanlang.", reply_markup=MENU_KB)
            return
    step = ud.get("step")
    if step == "pdf":
        if not is_img:
            await msg.reply_text("PDF uchun faqat rasm yuboring (JPG/PNG).")
            return
        await add_pdf_image(msg, ud, await doc.get_file(), msg.media_group_id)
    elif step == "zip":
        await add_zip_file(msg, ud, await doc.get_file(), doc.file_name or f"fayl_{msg.message_id}",
                           msg.media_group_id)


async def on_media(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Video/audio — faqat ZIP rejimida."""
    ud = ctx.user_data
    msg = update.message
    if not await guard(update.effective_user, msg, "media"):
        return
    if await bc_capture(update, ctx):
        return
    if ud.get("step") != "zip":
        return
    m = msg.video or msg.audio
    name = getattr(m, "file_name", None) or f"{'video' if msg.video else 'audio'}_{msg.message_id}"
    await add_zip_file(msg, ud, await m.get_file(), name, msg.media_group_id)


# ---------- Tugmalar ----------
async def on_button(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    ud = ctx.user_data
    msg = q.message
    step = ud.get("step")
    data = q.data
    if not await guard(q.from_user, msg):
        return

    if data.startswith("rate:"):
        _, form, val = data.split(":")
        store.rate(form, val == "up")
        try:
            await msg.edit_reply_markup(reply_markup=MENU_KB)
        except Exception:
            pass
        await msg.reply_text("Rahmat! 🙏" if val == "up" else
                             "Rahmat! Nima yoqmaganini «📞 Admin bilan bog‘lanish» orqali yozsangiz, tuzatamiz.")
        return
    if data in ("prof:optout", "prof:optin"):
        store.set_optout(q.from_user.id, data == "prof:optout")
        await msg.reply_text("🔕 E’lonlar o‘chirildi." if data == "prof:optout" else "🔔 E’lonlar yoqildi.",
                             reply_markup=MENU_KB)
        return
    if data.startswith("bc:"):
        if not is_admin(q.from_user.id):
            return
        if data == "bc:no":
            ud.clear()
            await msg.reply_text("Bekor qilindi.")
        elif data == "bc:go" and ud.get("bc"):
            chat_id, mid = ud["bc"]
            ud.clear()
            ids = await store.broadcast_ids()
            logging.info("ADMIN uid=%s cmd=broadcast n=%s", q.from_user.id, len(ids))
            await msg.reply_text(f"🚀 Yuborish boshlandi: {len(ids)} ta. Tugagach hisobot beraman.")
            t = asyncio.get_running_loop().create_task(run_broadcast(ctx.bot, q.from_user.id, chat_id, mid, ids))
            BG_TASKS.add(t)
            t.add_done_callback(BG_TASKS.discard)
        return
    if data == "prof:del":
        store.clear_profile(q.from_user.id)
        await msg.reply_text("🗑 Profil o‘chirildi.", reply_markup=MENU_KB)
        return

    if data.startswith("m:"):
        await drop_kb(ud)
        what = data[2:]
        if what == "obyektivka":
            await begin_obyektivka(msg, ctx)
        elif what == "profil":
            ud.clear()
            await show_profile(msg, q.from_user.id)
        elif what == "profedit":
            await begin_form(msg, ud, "profil", q.from_user.id)
        elif what == "help":
            ud.clear()
            await msg.reply_text(HELP_TEXT, reply_markup=MENU_KB)
        elif what in FORMS:
            await begin_form(msg, ud, what, q.from_user.id)
        elif what == "docs":
            ud.clear()
            await msg.reply_text("📚 Qaysi hujjatni tayyorlaymiz?", reply_markup=DOCS_KB)
        elif what == "edu":
            ud.clear()
            await msg.reply_text("🧰 Qaysi o‘quv materialini tayyorlaymiz?", reply_markup=EDU_KB)
        elif what == "pdf":
            await begin_pdf(msg, ud)
        elif what == "zip":
            await begin_zip(msg, ud)
        elif what == "ai":
            await begin_ai(msg, ud)
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

    elif step == "ai":
        if data == "ai:new":
            ud["hist"] = []
            await ask(msg, ud, "Yangi suhbat boshlandi. Savolingizni yozing.", AI_KB)

    elif step == "zip":
        if data == "zip:clear":
            ud["files"], ud["size"], ud["last_group"] = [], 0, None
            await ask(msg, ud, "Tozalandi. Yangi fayllarni yuboring.", InlineKeyboardMarkup([[MENU_BTN]]))
        elif data == "zip:make":
            await wait_uploads(ud)
            if not ud.get("files"):
                await msg.reply_text("Avval fayl yuboring.")
                return
            ud["busy"] = True
            await msg.reply_text("⏳ ZIP tayyorlanmoqda…")
            try:
                buf = io.BytesIO()
                with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
                    for name, raw in ud["files"]:
                        zf.writestr(name, raw)
                await msg.reply_document(buf.getvalue(), filename="Fayllar.zip",
                                         caption=f"Tayyor! ✅ {len(ud['files'])} ta fayl.\n\n" + PROMO)
                await msg.reply_text("Yana nima kerak?", reply_markup=MENU_KB)
            except Exception:
                logging.exception("ZIP xatosi")
                await msg.reply_text("ZIP tayyorlashda xato chiqdi.", reply_markup=MENU_KB)
            ud.clear()

    elif step == "pdf":
        if data == "pdf:clear":
            ud["pics"], ud["last_group"] = [], None
            await ask(msg, ud, "Tozalandi. Yangi rasmlarni yuboring.", InlineKeyboardMarkup([[MENU_BTN]]))
        elif data == "pdf:make":
            await wait_uploads(ud)
            if not ud.get("pics"):
                await msg.reply_text("Avval rasm yuboring.")
                return
            ud["busy"] = True
            await msg.reply_text("⏳ PDF tayyorlanmoqda…")
            try:
                pics = [b for _, b in sorted(ud["pics"], key=lambda x: x[0])]
                out = os.path.join(tempfile.gettempdir(), f"rasm_{q.from_user.id}.pdf")
                images.make_pdf(pics, out)
                with open(out, "rb") as fh:
                    await msg.reply_document(fh, filename="Rasmlar.pdf",
                                             caption=f"Tayyor! ✅ {len(pics)} sahifa.\n\n" + PROMO)
                await msg.reply_text("Yana nima kerak?", reply_markup=MENU_KB)
            except Exception:
                logging.exception("PDF xatosi")
                await msg.reply_text("PDF tayyorlashda xato chiqdi. Qayta urinib ko‘ring.", reply_markup=MENU_KB)
            ud.clear()

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
                    caption="Tayyor! Tekshirib ko‘ring. Yana o‘zgartirish kerak bo‘lsa /menu bosing.\n\n" + PROMO)
            store.count("obyektivka")
            await msg.reply_text(THANKS, parse_mode="HTML")
            await msg.reply_text("Natija yoqdimi? Yana nima kerak?", reply_markup=rate_kb("obyektivka"))
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
    app.add_handler(CommandHandler("profil", profil_cmd))
    app.add_handler(CommandHandler("yordam", help_cmd))
    app.add_handler(CommandHandler("stat", stat_cmd))
    app.add_handler(CommandHandler("xabar", bc_start))
    app.add_handler(CommandHandler("elon", elon_cmd))
    app.add_error_handler(on_error)
    app.add_handler(CommandHandler("cancel", cancel))
    app.add_handler(CommandHandler("orqaga", back))
    app.add_handler(CallbackQueryHandler(on_button))
    app.add_handler(MessageHandler(filters.PHOTO, on_photo))
    app.add_handler(MessageHandler(filters.Document.ALL, on_doc))
    app.add_handler(MessageHandler(filters.VIDEO | filters.AUDIO, on_media))
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
