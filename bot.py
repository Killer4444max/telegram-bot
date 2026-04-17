import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

TOKEN = os.getenv("TOKEN")
RENDER_EXTERNAL_URL = os.getenv("RENDER_EXTERNAL_URL")

if not TOKEN:
    raise RuntimeError("TOKEN topilmadi")


main_keyboard = [
    ["🛍 Mahsulotlar", "📞 Aloqa"],
    ["ℹ️ Haqimizda", "📢 Kanal"],
]
main_markup = ReplyKeyboardMarkup(main_keyboard, resize_keyboard=True)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Salom Odilbek! Bot ishlayapti 🚀",
        reply_markup=main_markup
    )


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text

    if text == "🛍 Mahsulotlar":
        await update.message.reply_text("Mahsulotlar bo‘limi ochildi ✅")
    elif text == "📞 Aloqa":
        await update.message.reply_text(
            "Aloqa uchun:\n"
            "📱 +998773005353\n"
            "📍 Qo‘qon"
        )
    elif text == "ℹ️ Haqimizda":
        await update.message.reply_text("Bizning do‘konimizga xush kelibsiz ✅")
    elif text == "📢 Kanal":
        await update.message.reply_text("Kanal linkini shu yerga yozasan")
    else:
        await update.message.reply_text("Tugmalardan birini bosing.")


telegram_app = Application.builder().token(TOKEN).build()
telegram_app.add_handler(CommandHandler("start", start))
telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))


@asynccontextmanager
async def lifespan(app: FastAPI):
    await telegram_app.initialize()
    await telegram_app.start()

    if RENDER_EXTERNAL_URL:
        webhook_url = RENDER_EXTERNAL_URL.rstrip("/") + "/webhook"
        await telegram_app.bot.set_webhook(webhook_url)
        print("Webhook o‘rnatildi:", webhook_url)

    yield

    await telegram_app.stop()
    await telegram_app.shutdown()


app = FastAPI(lifespan=lifespan)


@app.get("/")
async def home():
    return {"status": "ok"}


@app.post("/webhook")
async def webhook(req: Request):
    data = await req.json()
    update = Update.de_json(data, telegram_app.bot)
    await telegram_app.process_update(update)
    return {"ok": True}
