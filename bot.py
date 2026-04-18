import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from openai import OpenAI
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    ConversationHandler,
    filters,
)

TOKEN = os.getenv("TOKEN")
RENDER_EXTERNAL_URL = os.getenv("RENDER_EXTERNAL_URL")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
ADMIN_CHAT_ID = 7450937325

if not TOKEN:
    raise RuntimeError("TOKEN topilmadi")

client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None

ASK_NAME, ASK_PHONE, ASK_SIZE, ASK_COLOR = range(4)

# Asosiy menu
main_keyboard = [
    ["🛍 Mahsulotlar", "📞 Aloqa"],
    ["ℹ️ Haqimizda", "📢 Kanal"],
]
main_markup = ReplyKeyboardMarkup(main_keyboard, resize_keyboard=True)

# Mahsulotlar menu
product_keyboard = [
    ["👗 Pijama", "🥻 Pinuar"],
    ["🌸 Parfumeriya"],
    ["⬅️ Orqaga"],
]
product_markup = ReplyKeyboardMarkup(product_keyboard, resize_keyboard=True)

# 12 ta viloyat
region_keyboard = [
    ["📍 Toshkent", "📍 Andijon"],
    ["📍 Farg‘ona", "📍 Namangan"],
    ["📍 Samarqand", "📍 Buxoro"],
    ["📍 Xorazm", "📍 Qashqadaryo"],
    ["📍 Surxondaryo", "📍 Jizzax"],
    ["📍 Sirdaryo", "📍 Navoiy"],
    ["⬅️ Orqaga"],
]
region_markup = ReplyKeyboardMarkup(region_keyboard, resize_keyboard=True)

# Aloqa ichki menu
contact_detail_keyboard = [
    ["📱 Qo‘ng‘iroq", "💬 Telegram"],
    ["📍 Manzil"],
    ["⬅️ Orqaga"],
]
contact_detail_markup = ReplyKeyboardMarkup(contact_detail_keyboard, resize_keyboard=True)

# Buyurtma tugmasi
order_keyboard = [
    ["🛒 Buyurtma berish"],
    ["⬅️ Orqaga"],
]
order_markup = ReplyKeyboardMarkup(order_keyboard, resize_keyboard=True)

# Telefon yuborish tugmasi
phone_markup = ReplyKeyboardMarkup(
    [[KeyboardButton("📲 Raqamni yuborish", request_contact=True)]],
    resize_keyboard=True,
    one_time_keyboard=True
)

# Razmer tugmalari
size_keyboard = [
    ["46", "48", "50"],
    ["52", "54", "56"],
    ["⬅️ Orqaga"],
]
size_markup = ReplyKeyboardMarkup(size_keyboard, resize_keyboard=True, one_time_keyboard=True)

# Rang tugmalari
color_keyboard = [
    ["⚪ Oq", "🌸 Pushti"],
    ["⚫ Qora", "🔴 Qizil"],
    ["🔵 Ko‘k"],
    ["⬅️ Orqaga"],
]
color_markup = ReplyKeyboardMarkup(color_keyboard, resize_keyboard=True, one_time_keyboard=True)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["section"] = "main"
    await update.message.reply_text(
        "Assalomu alaykum!\n"
        "Botga xush kelibsiz 🚀\n\n"
        "Quyidagi menyudan birini tanlang:",
        reply_markup=main_markup
    )


async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["section"] = "main"
    await update.message.reply_text("Asosiy menu ✅", reply_markup=main_markup)


async def products(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["section"] = "products"
    await update.message.reply_text(
        "Mahsulot bo‘limini tanlang:",
        reply_markup=product_markup
    )


async def contact(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["section"] = "contact_region"
    await update.message.reply_text(
        "📞 Qaysi viloyat bo‘yicha aloqa kerak?\n\nQuyidan tanlang:",
        reply_markup=region_markup
    )


async def about(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Biz online shopmiz.\n"
        "Sifatli mahsulotlarni taklif qilamiz."
    )


async def channel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📢 Bizning kanallarimiz:\n\n"
        "1️⃣ https://t.me/shoda11Y\n"
        "2️⃣ https://t.me/bilyonejni"
    )


async def order_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    product = context.user_data.get("product")

    if not product:
        await update.message.reply_text("Avval mahsulotni tanlang.")
        return ConversationHandler.END

    await update.message.reply_text(
        f"Buyurtma boshlandi ✅\n\nMahsulot: {product}\n\nIsmingizni yozing:"
    )
    return ASK_NAME


async def ask_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["name"] = update.message.text
    await update.message.reply_text(
        "Telefon raqamingizni yuboring:",
        reply_markup=phone_markup
    )
    return ASK_PHONE


async def ask_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.contact:
        context.user_data["phone"] = update.message.contact.phone_number
        await update.message.reply_text(
            "Razmerni tanlang:",
            reply_markup=size_markup
        )
        return ASK_SIZE
    else:
        await update.message.reply_text(
            "Pastdagi 📲 Raqamni yuborish tugmasini bosing."
        )
        return ASK_PHONE


async def ask_size(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    allowed_sizes = ["46", "48", "50", "52", "54", "56"]

    if text == "⬅️ Orqaga":
        await update.message.reply_text(
            "Telefon raqamingizni yuboring:",
            reply_markup=phone_markup
        )
        return ASK_PHONE

    if text not in allowed_sizes:
        await update.message.reply_text(
            "Razmerni tugmadan tanlang:",
            reply_markup=size_markup
        )
        return ASK_SIZE

    context.user_data["size"] = text
    await update.message.reply_text(
        "Rangni tanlang:",
        reply_markup=color_markup
    )
    return ASK_COLOR


async def ask_color(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    allowed_colors = ["⚪ Oq", "🌸 Pushti", "⚫ Qora", "🔴 Qizil", "🔵 Ko‘k"]

    if text == "⬅️ Orqaga":
        await update.message.reply_text(
            "Razmerni tanlang:",
            reply_markup=size_markup
        )
        return ASK_SIZE

    if text not in allowed_colors:
        await update.message.reply_text(
            "Rangni tugmadan tanlang:",
            reply_markup=color_markup
        )
        return ASK_COLOR

    context.user_data["color"] = text

    product = context.user_data.get("product", "")
    name = context.user_data.get("name", "")
    phone = context.user_data.get("phone", "")
    size = context.user_data.get("size", "")
    color = context.user_data.get("color", "")

    user_text = (
        "✅ Buyurtmangiz qabul qilindi!\n\n"
        f"🛍 Mahsulot: {product}\n"
        f"👤 Ism: {name}\n"
        f"📱 Telefon: {phone}\n"
        f"📏 Razmer: {size}\n"
        f"🎨 Rang: {color}"
    )

    admin_text = (
        "🛒 YANGI BUYURTMA\n\n"
        f"🛍 Mahsulot: {product}\n"
        f"👤 Ism: {name}\n"
        f"📱 Telefon: {phone}\n"
        f"📏 Razmer: {size}\n"
        f"🎨 Rang: {color}"
    )

    await update.message.reply_text(user_text, reply_markup=main_markup)

    try:
        await context.bot.send_message(chat_id=ADMIN_CHAT_ID, text=admin_text)
    except Exception:
        await update.message.reply_text(
            "Buyurtma saqlandi, lekin adminga yuborilmadi. ADMIN_CHAT_ID ni tekshiring."
        )

    context.user_data.clear()
    context.user_data["section"] = "main"
    return ConversationHandler.END


async def cancel_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    context.user_data["section"] = "main"
    await update.message.reply_text(
        "Buyurtma bekor qilindi.",
        reply_markup=main_markup
    )
    return ConversationHandler.END


async def ask_ai(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not client:
        await update.message.reply_text(
            "OPENAI_API_KEY qo‘shilmagan. Render Environment ga key qo‘ying."
        )
        return

    question = update.message.text

    try:
        response = client.responses.create(
            model="gpt-4o-mini",
            input=[
                {
                    "role": "system",
                    "content": [
                        {
                            "type": "input_text",
                            "text": "Sen foydali yordamchi botsan. Uzbek tilida sodda va tushunarli javob ber."
                        }
                    ],
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": question
                        }
                    ],
                },
            ],
        )
        answer = response.output_text or "Javob topilmadi."
        await update.message.reply_text(answer)
    except Exception as e:
        await update.message.reply_text(f"AI xato berdi: {e}")


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    section = context.user_data.get("section", "main")
    selected_region = context.user_data.get("selected_region", "")

    if text == "🛍 Mahsulotlar":
        await products(update, context)

    elif text == "👗 Pijama":
        context.user_data["product"] = "Pijama"
        context.user_data["section"] = "product_detail"
        await update.message.reply_text(
            "👗 Pijama bo‘limi\n\n"
            "Narxi: 120 000 so‘m\n"
            "Razmer: 46-56\n"
            "Rang: oq, pushti, qora, qizil, ko‘k\n\n"
            "Buyurtma uchun tugmani bosing:",
            reply_markup=order_markup
        )

    elif text == "🥻 Pinuar":
        context.user_data["product"] = "Pinuar"
        context.user_data["section"] = "product_detail"
        await update.message.reply_text(
            "🥻 Pinuar bo‘limi\n\n"
            "Narxi: 150 000 so‘m\n"
            "Razmer: 46-56\n"
            "Rang: oq, pushti, qora, qizil, ko‘k\n\n"
            "Buyurtma uchun tugmani bosing:",
            reply_markup=order_markup
        )

    elif text == "🌸 Parfumeriya":
        context.user_data["section"] = "product_detail"
        await update.message.reply_text(
            "🌸 Parfumeriya bo‘limi\n\n"
            "Bu bo‘limga keyin atirlar qo‘shamiz.",
            reply_markup=order_markup
        )

    elif text == "📞 Aloqa":
        await contact(update, context)

    # 12 viloyat tanlash
    elif text in [
        "📍 Toshkent", "📍 Andijon", "📍 Farg‘ona", "📍 Namangan",
        "📍 Samarqand", "📍 Buxoro", "📍 Xorazm", "📍 Qashqadaryo",
        "📍 Surxondaryo", "📍 Jizzax", "📍 Sirdaryo", "📍 Navoiy"
    ]:
        context.user_data["selected_region"] = text
        context.user_data["section"] = "contact_detail"
        await update.message.reply_text(
            f"{text} bo‘yicha bo‘limni tanlang:",
            reply_markup=contact_detail_markup
        )

    elif text == "📱 Qo‘ng‘iroq":
        if selected_region == "📍 Toshkent":
            await update.message.reply_text(
                "📱 Toshkent telefon raqamlari:\n\n"
                "1) +998 90 827 88 25\n"
                "2) +998 90 827 88 96"
            )
        elif selected_region == "📍 Farg‘ona":
            await update.message.reply_text(
                "📱 Farg‘ona telefon raqamlari:\n\n"
                "1) +998 95 007 95 66\n"
                "2) +998 90 550 70 45"
            )
        else:
            await update.message.reply_text(
                f"{selected_region} uchun telefon raqamlari tez orada qo‘shiladi."
            )

    elif text == "💬 Telegram":
        if selected_region == "📍 Toshkent":
            await update.message.reply_text("💬 Toshkent Telegram:\n@shodashop_toshkent")
        elif selected_region == "📍 Farg‘ona":
            await update.message.reply_text("💬 Farg‘ona Telegram:\n@shodashop")
        else:
            await update.message.reply_text(
                f"{selected_region} uchun Telegram manzili tez orada qo‘shiladi."
            )

    elif text == "📍 Manzil":
        if selected_region == "📍 Toshkent":
            await context.bot.send_location(
                chat_id=update.effective_chat.id,
                latitude=41.257681,
                longitude=69.153924
            )
            await update.message.reply_text("📍 Toshkent manzili")
        elif selected_region == "📍 Farg‘ona":
            await context.bot.send_location(
                chat_id=update.effective_chat.id,
                latitude=40.554953,
                longitude=70.963713
            )
            await update.message.reply_text("📍 Farg‘ona manzili")
        else:
            await update.message.reply_text(
                f"{selected_region} uchun manzil tez orada qo‘shiladi."
            )

    elif text == "ℹ️ Haqimizda":
        await about(update, context)

    elif text == "📢 Kanal":
        await channel(update, context)

    elif text == "⬅️ Orqaga":
        if section == "products":
            context.user_data["section"] = "main"
            await update.message.reply_text("Asosiy menu", reply_markup=main_markup)

        elif section == "product_detail":
            context.user_data["section"] = "products"
            await update.message.reply_text(
                "Mahsulot bo‘limini tanlang:",
                reply_markup=product_markup
            )

        elif section == "contact_region":
            context.user_data["section"] = "main"
            await update.message.reply_text("Asosiy menu", reply_markup=main_markup)

        elif section == "contact_detail":
            context.user_data["section"] = "contact_region"
            await update.message.reply_text(
                "📞 Qaysi viloyat bo‘yicha aloqa kerak?",
                reply_markup=region_markup
            )

        else:
            context.user_data["section"] = "main"
            await update.message.reply_text("Asosiy menu", reply_markup=main_markup)

    else:
        await ask_ai(update, context)


telegram_app = Application.builder().token(TOKEN).build()

order_handler = ConversationHandler(
    entry_points=[
        MessageHandler(filters.Regex("^🛒 Buyurtma berish$"), order_entry),
    ],
    states={
        ASK_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_name)],
        ASK_PHONE: [
            MessageHandler(filters.CONTACT, ask_phone),
            MessageHandler(filters.TEXT & ~filters.COMMAND, ask_phone),
        ],
        ASK_SIZE: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_size)],
        ASK_COLOR: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_color)],
    },
    fallbacks=[CommandHandler("cancel", cancel_order)],
)

telegram_app.add_handler(CommandHandler("start", start))
telegram_app.add_handler(CommandHandler("menu", menu))
telegram_app.add_handler(order_handler)
telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))


@asynccontextmanager
async def lifespan(app: FastAPI):
    await telegram_app.initialize()
    await telegram_app.start()

    if RENDER_EXTERNAL_URL:
        webhook_url = RENDER_EXTERNAL_URL.rstrip("/") + "/webhook"
        await telegram_app.bot.set_webhook(webhook_url)

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
