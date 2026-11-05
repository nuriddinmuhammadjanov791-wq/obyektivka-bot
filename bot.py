"""
Obyektivka (ma'lumotnoma) Telegram boti.
Savollarni birin-ketin so'raydi va oxirida tayyor Word (.docx) fayl yuboradi.

Ishga tushirish:
    pip install -r requirements.txt
    export BOT_TOKEN="BotFather bergan token"
    export ADMIN_ID="123456789"      # (ixtiyoriy) tayyor fayllar nusxasi sizga ham keladi
    python bot.py
"""
import logging
import os
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

from docgen import build_docx

logging.basicConfig(level=logging.INFO)

# (kalit, savol) — shu tartibda so'raladi
PERSONAL = [
    ("fio", "Familiyangiz, ismingiz va otangizning ismini yozing.\nMasalan: Nursoatova Feruza Muxiddin qizi"),
    ("birth_date", "Tug‘ilgan sanangiz (kun.oy.yil)?\nMasalan: 19.10.2008"),
    ("birth_place", "Tug‘ilgan joyingiz (viloyat, tuman)?"),
    ("nationality", "Millatingiz?"),
    ("party", "Partiyaviyligingiz? (a’zo bo‘lmasangiz «yo‘q» deb yozing)"),
    ("education", "Ma’lumotingiz?\nMasalan: o‘rta, tugallanmagan oliy"),
    ("graduated", "Qachon va qaysi maktab/kollejni tugatgansiz?\nMasalan: 2026 yil, Dehqonobod tumani 92-sonli o‘rta maktab"),
    ("specialty", "Ma’lumoti bo‘yicha mutaxassisligingiz? (yo‘q bo‘lsa «yo‘q»)"),
    ("degree", "Ilmiy darajangiz? (yo‘q bo‘lsa «yo‘q»)"),
    ("rank", "Ilmiy unvoningiz? (yo‘q bo‘lsa «yo‘q»)"),
    ("languages", "Qaysi chet tillarini bilasiz?\nMasalan: rus tili, ingliz tili"),
    ("awards", "Davlat mukofotlari bilan taqdirlanganmisiz? (yo‘q bo‘lsa «yo‘q»)"),
    ("deputy", "Xalq deputatlari Kengashi deputati yoki boshqa saylanadigan organ a’zosimisiz? (yo‘q bo‘lsa «yo‘q»)"),
    ("univ", "Hozir o‘qiyotgan universitetingiz nomi?"),
    ("faculty", "Fakultet va yo‘nalishingiz?\nMasalan: Kechki va Sirtqi ta’lim fakulteti (Ingliz tili) yo‘nalishi"),
    ("enroll", "Universitetga qachon kirgansiz?\nMasalan: 2026 yil 7 sentabr"),
    ("phone", "Telefon raqamingiz?"),
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

BTN_DONE_WORK = InlineKeyboardMarkup([[InlineKeyboardButton("✅ Tayyor", callback_data="work_done")]])
BTN_REL = InlineKeyboardMarkup([[
    InlineKeyboardButton("➕ Yana qarindosh", callback_data="rel_more"),
    InlineKeyboardButton("✅ Tugatish", callback_data="rel_done"),
]])


def fresh(ctx):
    ctx.user_data.clear()
    ctx.user_data.update(step="personal", i=0, data={"work": [], "relatives": []},
                         photo=None, rel={}, ri=0)


async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    fresh(ctx)
    await update.message.reply_text(
        "Assalomu alaykum! Men ma’lumotnoma (obyektivka) tayyorlab beraman.\n"
        "Savollarga birin-ketin javob bering, oxirida tayyor Word fayl olasiz.\n"
        "Bekor qilish: /cancel, qaytadan boshlash: /start"
    )
    await update.message.reply_text(PERSONAL[0][1])


async def cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data.clear()
    await update.message.reply_text("Bekor qilindi. Qaytadan boshlash uchun /start.")


async def ask_photo(msg):
    await msg.reply_text(
        "3x4 rasmingizni yuboring (oddiy foto sifatida, fayl emas).\n"
        "Rasm kerak bo‘lmasa «yo‘q» deb yozing."
    )


async def on_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ud = ctx.user_data
    msg = update.message
    text = (msg.text or "").strip()
    step = ud.get("step")
    if not step:
        await msg.reply_text("Boshlash uchun /start bosing.")
        return

    if step == "personal":
        key = PERSONAL[ud["i"]][0]
        ud["data"][key] = text
        ud["i"] += 1
        if ud["i"] < len(PERSONAL):
            await msg.reply_text(PERSONAL[ud["i"]][1])
        else:
            ud["step"] = "photo"
            await ask_photo(msg)

    elif step == "photo":
        ud["photo"] = None
        ud["step"] = "work"
        await msg.reply_text(WORK_HELP)

    elif step == "work":
        ud["data"]["work"].append(text)
        await msg.reply_text("Qo‘shildi. Yana yozing yoki tugating:", reply_markup=BTN_DONE_WORK)

    elif step == "relative":
        key = RELATIVE[ud["ri"]][0]
        ud["rel"][key] = text
        ud["ri"] += 1
        if ud["ri"] < len(RELATIVE):
            await msg.reply_text(RELATIVE[ud["ri"]][1])
        else:
            ud["data"]["relatives"].append(dict(ud["rel"]))
            ud["rel"], ud["ri"] = {}, 0
            ud["step"] = "relative_menu"
            n = len(ud["data"]["relatives"])
            await msg.reply_text(f"{n}-qarindosh qo‘shildi. Yana qo‘shamizmi?", reply_markup=BTN_REL)

    else:
        await msg.reply_text("Iltimos, pastdagi tugmalardan birini bosing.")


async def on_photo(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ud = ctx.user_data
    if ud.get("step") != "photo":
        return
    f = await update.message.photo[-1].get_file()
    path = os.path.join(tempfile.gettempdir(), f"photo_{update.effective_user.id}.jpg")
    await f.download_to_drive(path)
    ud["photo"] = path
    ud["step"] = "work"
    await update.message.reply_text("Rasm qabul qilindi ✅")
    await update.message.reply_text(WORK_HELP)


async def on_button(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    ud = ctx.user_data
    if not ud.get("step"):
        return

    if q.data == "work_done" and ud["step"] == "work":
        if not ud["data"]["work"]:
            await q.message.reply_text("Hech bo‘lmasa bitta qator yozing (masalan, maktab o‘quvchisi).")
            return
        ud["step"] = "relative"
        await q.message.reply_text(
            "Endi yaqin qarindoshlaringiz: ota, ona, aka-uka, opa-singillar.\n"
            "Har biri uchun alohida so‘rayman."
        )
        await q.message.reply_text(RELATIVE[0][1])

    elif q.data == "rel_more" and ud["step"] == "relative_menu":
        ud["step"] = "relative"
        await q.message.reply_text(RELATIVE[0][1])

    elif q.data == "rel_done" and ud["step"] == "relative_menu":
        await q.message.reply_text("Fayl tayyorlanmoqda…")
        out = os.path.join(tempfile.gettempdir(), f"Obyektivka_{q.from_user.id}.docx")
        build_docx(ud["data"], out, ud.get("photo"))
        name = ud["data"]["fio"].split()[0]
        with open(out, "rb") as fh:
            await q.message.reply_document(fh, filename=f"Obyektivka_{name}.docx",
                                           caption="Tayyor! Tekshirib ko‘ring. Xato bo‘lsa /start bilan qaytadan kiriting.")
        admin = os.getenv("ADMIN_ID")
        if admin:
            with open(out, "rb") as fh:
                await ctx.bot.send_document(int(admin), fh, filename=f"Obyektivka_{name}.docx",
                                            caption=f"Yangi obyektivka: {ud['data']['fio']}")
        ud.clear()


def main():
    token = os.environ["BOT_TOKEN"]
    app = ApplicationBuilder().token(token).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("cancel", cancel))
    app.add_handler(CallbackQueryHandler(on_button))
    app.add_handler(MessageHandler(filters.PHOTO, on_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))

    # Render (bulut) da RENDER_EXTERNAL_URL avtomatik beriladi -> webhook rejimi.
    # Kompyuterda bo'lsa shu o'zgaruvchi yo'q -> oddiy polling.
    base_url = os.getenv("RENDER_EXTERNAL_URL")
    if base_url:
        app.run_webhook(
            listen="0.0.0.0",
            port=int(os.getenv("PORT", "10000")),
            url_path=token,
            webhook_url=f"{base_url}/{token}",
            drop_pending_updates=False,
        )
    else:
        app.run_polling()


if __name__ == "__main__":
    main()
