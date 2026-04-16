import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# TOKEN Render Environment'dan olinadi
TOKEN = os.getenv("TOKEN")

if not TOKEN:
    raise RuntimeError("TOKEN topilmadi!")

# /start komandasi
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Salom Odilbek! Bot ishlayapti 🚀")

# Telegram bot application
telegram_app = Application.builder().token(TOKEN).build()
telegram_app.add_handler(CommandHandler("start", start))


# FastAPI lifecycle (webhook set qilish)
@asynccontextmanager
async def lifespan(app: FastAPI):
    await telegram_app.initialize()

    # Render avtomatik URL beradi
    url = os.getenv("RENDER_EXTERNAL_URL")

    if url:
        webhook_url = url + "/webhook"
        await telegram_app.bot.set_webhook(webhook_url)
        print("Webhook o‘rnatildi:", webhook_url)

    yield

    await telegram_app.shutdown()


# FastAPI app
app = FastAPI(lifespan=lifespan)


# test route
@app.get("/")
async def home():
    return {"status": "Bot ishlayapti"}


# Telegram webhook endpoint
@app.post("/webhook")
async def webhook(req: Request):
    data = await req.json()
    update = Update.de_json(data, telegram_app.bot)
    await telegram_app.process_update(update)
    return {"ok": True}
