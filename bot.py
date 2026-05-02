import asyncio
import json
import os
import re
from contextlib import asynccontextmanager
from pathlib import Path

import google.generativeai as genai
from fastapi import FastAPI, Request
from telegram import (
    Update,
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    InputMediaPhoto,
)
from telegram.constants import ChatMemberStatus
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    ConversationHandler,
    filters,
)

TOKEN = os.getenv("TOKEN")
RENDER_EXTERNAL_URL = os.getenv("RENDER_EXTERNAL_URL")
ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID")
CARD_NUMBER = os.getenv("CARD_NUMBER")
CARD_HOLDER = os.getenv("CARD_HOLDER")
PRODUCT_CHANNEL_USERNAME = os.getenv("PRODUCT_CHANNEL_USERNAME")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if not TOKEN:
    raise RuntimeError("TOKEN topilmadi")
if not ADMIN_CHAT_ID:
    raise RuntimeError("ADMIN_CHAT_ID topilmadi")
if not CARD_NUMBER or not CARD_HOLDER:
    raise RuntimeError("CARD_NUMBER yoki CARD_HOLDER topilmadi")
if not PRODUCT_CHANNEL_USERNAME:
    raise RuntimeError("PRODUCT_CHANNEL_USERNAME topilmadi")

ADMIN_CHAT_ID = int(ADMIN_CHAT_ID)

if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
    ai_model = genai.GenerativeModel("gemini-1.5-flash")
else:
    ai_model = None

REQUIRED_CHANNELS = [
    ("Bizning kanal", "@pijamas_optom", "https://t.me/pijamas_optom"),
]

DATA_DIR = Path(".")
ORDERS_FILE = DATA_DIR / "orders.json"
USERS_FILE = DATA_DIR / "users.json"
PRODUCTS_FILE = DATA_DIR / "products.json"

ASK_REGION, ASK_NAME, ASK_PHONE, ASK_SIZE, ASK_COLOR, ASK_PAYMENT, ASK_RECEIPT = range(7)

ALLOWED_REGIONS = [
    "📍 Toshkent",
    "📍 Andijon",
    "📍 Farg‘ona",
    "📍 Namangan",
    "📍 Samarqand",
    "📍 Buxoro",
    "📍 Xorazm",
    "📍 Qashqadaryo",
    "📍 Surxondaryo",
    "📍 Jizzax",
    "📍 Sirdaryo",
    "📍 Navoiy",
]

STATUS_LABELS = {
    "new": "Yangi",
    "accepted": "Qabul qilindi ✅",
    "preparing": "Tayyorlanmoqda 🧵",
    "shipped": "Yuborildi 🚚",
    "delivered": "Yetkazildi 📦",
    "rejected": "Bekor qilindi ❌",
    "paid": "To‘lov tekshirilmoqda ⏳",
    "receipt_ok": "To‘lov tushdi ✅",
    "receipt_bad": "To‘lov topilmadi ❌",
}

main_markup = ReplyKeyboardMarkup(
    [["🛍 Mahsulotlar", "📞 Aloqa"], ["ℹ️ Haqimizda", "📢 Kanal"]],
    resize_keyboard=True,
)

product_markup = ReplyKeyboardMarkup(
    [["👗 Pijama", "🥻 Pinuar"], ["🌸 Parfumeriya"], ["⬅️ Orqaga"]],
    resize_keyboard=True,
)

city_markup = ReplyKeyboardMarkup(
    [["📍 Toshkent", "📍 Qo‘qon"], ["⬅️ Orqaga"]],
    resize_keyboard=True,
)

contact_detail_markup = ReplyKeyboardMarkup(
    [["📱 Qo‘ng‘iroq", "💬 Telegram"], ["📍 Manzil"], ["⬅️ Orqaga"]],
    resize_keyboard=True,
)

order_markup = ReplyKeyboardMarkup(
    [["🛒 Buyurtma berish"], ["⬅️ Orqaga"]],
    resize_keyboard=True,
)

phone_markup = ReplyKeyboardMarkup(
    [[KeyboardButton("📲 Raqamni yuborish", request_contact=True)]],
    resize_keyboard=True,
    one_time_keyboard=True,
)

size_markup = ReplyKeyboardMarkup(
    [["46", "48", "50"], ["52", "54", "56"], ["⬅️ Orqaga"]],
    resize_keyboard=True,
    one_time_keyboard=True,
)

color_markup = ReplyKeyboardMarkup(
    [["⚪ Oq", "🌸 Pushti"], ["⚫ Qora", "🔴 Qizil"], ["🔵 Ko‘k"], ["⬅️ Orqaga"]],
    resize_keyboard=True,
    one_time_keyboard=True,
)

region_markup = ReplyKeyboardMarkup(
    [
        ["📍 Toshkent", "📍 Andijon"],
        ["📍 Farg‘ona", "📍 Namangan"],
        ["📍 Samarqand", "📍 Buxoro"],
        ["📍 Xorazm", "📍 Qashqadaryo"],
        ["📍 Surxondaryo", "📍 Jizzax"],
        ["📍 Sirdaryo", "📍 Navoiy"],
        ["⬅️ Orqaga"],
    ],
    resize_keyboard=True,
    one_time_keyboard=True,
)

payment_markup = ReplyKeyboardMarkup(
    [["💵 Naqd", "💳 Karta"], ["📲 Click", "📲 Payme"], ["⬅️ Orqaga"]],
    resize_keyboard=True,
    one_time_keyboard=True,
)

ALLOWED_PAYMENTS = ["💵 Naqd", "💳 Karta", "📲 Click", "📲 Payme"]


def load_json(path: Path, default):
    if not path.exists():
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def save_json(path: Path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


ORDERS = load_json(ORDERS_FILE, {})
USERS = load_json(USERS_FILE, [])
PRODUCTS = load_json(PRODUCTS_FILE, {})
ALBUMS = {}


def add_user(user_id: int):
    if user_id not in USERS:
        USERS.append(user_id)
        save_json(USERS_FILE, USERS)


def next_order_id() -> str:
    if not ORDERS:
        return "1"
    return str(max(int(k) for k in ORDERS.keys()) + 1)


def order_text(order_id: str, order: dict) -> str:
    return (
        "🛒 BUYURTMA\n\n"
        f"🆔 Buyurtma ID: {order_id}\n"
        f"🛍 Mahsulot: {order['product']}\n"
        f"📍 Viloyat: {order['region']}\n"
        f"👤 Ism: {order['name']}\n"
        f"📱 Telefon: {order['phone']}\n"
        f"📏 Razmer: {order['size']}\n"
        f"🎨 Rang: {order['color']}\n"
        f"💳 To‘lov turi: {order['payment']}\n"
        f"💵 Mahsulot narxi: {order['product_price']:,} so‘m\n"
        f"💰 Jami: {order['total_price']:,} so‘m\n"
        f"📌 Holat: {order['status']}"
    )


def admin_order_keyboard(order_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("✅ To‘lov tushdi", callback_data=f"status:{order_id}:receipt_ok"),
                InlineKeyboardButton("❌ To‘lov tushmadi", callback_data=f"status:{order_id}:receipt_bad"),
            ],
            [
                InlineKeyboardButton("✅ Qabul", callback_data=f"status:{order_id}:accepted"),
                InlineKeyboardButton("🧵 Tayyor", callback_data=f"status:{order_id}:preparing"),
            ],
            [
                InlineKeyboardButton("🚚 Yuborildi", callback_data=f"status:{order_id}:shipped"),
                InlineKeyboardButton("📦 Yetkazildi", callback_data=f"status:{order_id}:delivered"),
            ],
            [InlineKeyboardButton("❌ Bekor", callback_data=f"status:{order_id}:rejected")],
        ]
    )


def subscription_keyboard() -> InlineKeyboardMarkup:
    rows = []
    for title, _, url in REQUIRED_CHANNELS:
        rows.append([InlineKeyboardButton(f"🔔 {title}", url=url)])
    rows.append([InlineKeyboardButton("✅ Tekshirish", callback_data="check_sub")])
    return InlineKeyboardMarkup(rows)


def parse_product_caption(caption: str) -> dict | None:
    if not caption:
        return None

    name_match = re.search(r"(?im)^NOM:\s*(.+)$", caption)
    price_match = re.search(r"(?im)^NARX:\s*([\d\s]+)$", caption)
    code_match = re.search(r"(?im)^KOD:\s*(.+)$", caption)
    color_match = re.search(r"(?im)^RANG:\s*(.+)$", caption)

    if not name_match or not price_match or not code_match:
        return None

    raw_price = price_match.group(1).replace(" ", "").strip()
    if not raw_price.isdigit():
        return None

    return {
        "name": name_match.group(1).strip(),
        "price": int(raw_price),
        "code": code_match.group(1).strip(),
        "color": color_match.group(1).strip() if color_match else "",
    }


def get_products_by_name(name: str) -> list[tuple[str, dict]]:
    result = []
    for code, product in PRODUCTS.items():
        if product.get("name", "").lower() == name.lower():
            result.append((code, product))
    return result


async def is_user_subscribed(context: ContextTypes.DEFAULT_TYPE, user_id: int) -> bool:
    try:
        for _, username, _ in REQUIRED_CHANNELS:
            member = await context.bot.get_chat_member(chat_id=username, user_id=user_id)
            if member.status in [ChatMemberStatus.LEFT, ChatMemberStatus.BANNED]:
                return False
        return True
    except Exception as e:
        print("Subscription check error:", e)
        return False


async def ensure_subscription(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    ok = await is_user_subscribed(context, update.effective_user.id)
    if ok:
        return True

    text = (
        "❗ Botdan foydalanish uchun avval kanalga a’zo bo‘ling.\n\n"
        "A’zo bo‘lgach, ✅ Tekshirish tugmasini bosing."
    )

    if update.callback_query:
        await update.callback_query.message.reply_text(text, reply_markup=subscription_keyboard())
    else:
        await update.effective_message.reply_text(text, reply_markup=subscription_keyboard())
    return False


async def save_album_later(media_group_id: str):
    await asyncio.sleep(2)

    album = ALBUMS.pop(media_group_id, None)
    if not album:
        return

    parsed = album.get("parsed")
    photos = album.get("photos", [])

    if not parsed or not photos:
        return

    code = parsed["code"]
    PRODUCTS[code] = {
        "name": parsed["name"],
        "price": parsed["price"],
        "code": code,
        "color": parsed["color"],
        "photo_file_ids": photos,
    }

    save_json(PRODUCTS_FILE, PRODUCTS)
    print(f"Album mahsulot saqlandi: {code} - {parsed['name']} | rasmlar: {len(photos)}")


async def handle_channel_post(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.channel_post or update.message
    if not msg:
        return

    chat_username = f"@{msg.chat.username.lower()}" if msg.chat.username else ""

    if chat_username != PRODUCT_CHANNEL_USERNAME.lower():
        return

    photo_file_id = None
    if msg.photo:
        photo_file_id = msg.photo[-1].file_id
    elif msg.document and msg.document.mime_type and msg.document.mime_type.startswith("image/"):
        photo_file_id = msg.document.file_id

    if not photo_file_id:
        return

    if msg.media_group_id:
        group_id = str(msg.media_group_id)

        if group_id not in ALBUMS:
            ALBUMS[group_id] = {"photos": [], "parsed": None, "task_started": False}

        ALBUMS[group_id]["photos"].append(photo_file_id)

        parsed = parse_product_caption(msg.caption or "")
        if parsed:
            ALBUMS[group_id]["parsed"] = parsed

        if not ALBUMS[group_id]["task_started"]:
            ALBUMS[group_id]["task_started"] = True
            asyncio.create_task(save_album_later(group_id))

        return

    parsed = parse_product_caption(msg.caption or "")
    if not parsed:
        return

    code = parsed["code"]
    PRODUCTS[code] = {
        "name": parsed["name"],
        "price": parsed["price"],
        "code": code,
        "color": parsed["color"],
        "photo_file_ids": [photo_file_id],
    }

    save_json(PRODUCTS_FILE, PRODUCTS)
    print(f"Mahsulot saqlandi: {code} - {parsed['name']}")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    add_user(update.effective_user.id)
    if not await ensure_subscription(update, context):
        return

    context.user_data["section"] = "main"
    await update.message.reply_text(
        "Assalomu alaykum!\nBotga xush kelibsiz 🚀\n\nQuyidagi menyudan birini tanlang:",
        reply_markup=main_markup,
    )


async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await ensure_subscription(update, context):
        return
    context.user_data["section"] = "main"
    await update.message.reply_text("Asosiy menu ✅", reply_markup=main_markup)


async def products(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["section"] = "products"
    await update.message.reply_text("Mahsulot bo‘limini tanlang:", reply_markup=product_markup)


async def contact(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["section"] = "contact_city"
    await update.message.reply_text(
        "📞 Qaysi shahar bo‘yicha aloqa kerak?\n\nQuyidan tanlang:",
        reply_markup=city_markup,
    )


async def about(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Biz online shopmiz.\nSifatli mahsulotlarni taklif qilamiz.")


async def channel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📢 Bizning kanal:\n\nhttps://t.me/pijamas_optom")


async def show_product(update: Update, context: ContextTypes.DEFAULT_TYPE, product_name: str, emoji_title: str):
    products_list = get_products_by_name(product_name)

    if not products_list:
        await update.message.reply_text(
            f"{emoji_title} bo‘limi uchun hali kanalga yoki guruhga mahsulot joylanmagan.\n\n"
            "Post formati:\n"
            "NOM: Pijama\n"
            "NARX: 120000\n"
            "KOD: PJ01\n"
            "RANG: oq, qora"
        )
        return

    context.user_data["section"] = "product_detail"

    for code, product in products_list:
        context.user_data["product"] = product["name"]
        context.user_data["product_code"] = code

        caption = (
            f"{emoji_title}\n\n"
            f"🛍 Nomi: {product['name']}\n"
            f"🆔 Kodi: {product['code']}\n"
            f"💵 Narxi: {product['price']:,} so‘m\n"
            f"🎨 Rang: {product.get('color', '-')}"
        )

        photo_ids = product.get("photo_file_ids") or [product.get("photo_file_id")]

        if len(photo_ids) == 1:
            await context.bot.send_photo(
                chat_id=update.effective_chat.id,
                photo=photo_ids[0],
                caption=caption,
            )
        else:
            media = []
            for i, photo_id in enumerate(photo_ids):
                if i == 0:
                    media.append(InputMediaPhoto(media=photo_id, caption=caption))
                else:
                    media.append(InputMediaPhoto(media=photo_id))

            await context.bot.send_media_group(
                chat_id=update.effective_chat.id,
                media=media,
            )

    await update.message.reply_text(
        "Buyurtma berish uchun tugmani bosing:",
        reply_markup=order_markup
    )


async def order_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    product = context.user_data.get("product")
    if not product:
        await update.message.reply_text("Avval mahsulotni tanlang.")
        return ConversationHandler.END

    await update.message.reply_text(
        f"Buyurtma boshlandi ✅\n\nMahsulot: {product}\n\nEndi buyurtma qilinadigan viloyatni tanlang:",
        reply_markup=region_markup,
    )
    return ASK_REGION


async def ask_region(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text

    if text == "⬅️ Orqaga":
        context.user_data["section"] = "main"
        await update.message.reply_text("Buyurtma bekor qilindi.", reply_markup=main_markup)
        return ConversationHandler.END

    if text not in ALLOWED_REGIONS:
        await update.message.reply_text("Viloyatni tugmadan tanlang:", reply_markup=region_markup)
        return ASK_REGION

    context.user_data["order_region"] = text
    await update.message.reply_text(f"Tanlangan viloyat: {text}\n\nIsmingizni yozing:")
    return ASK_NAME


async def ask_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["name"] = update.message.text
    await update.message.reply_text("Telefon raqamingizni yuboring:", reply_markup=phone_markup)
    return ASK_PHONE


async def ask_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.contact:
        context.user_data["phone"] = update.message.contact.phone_number
        await update.message.reply_text("Razmerni tanlang:", reply_markup=size_markup)
        return ASK_SIZE

    await update.message.reply_text("Pastdagi 📲 Raqamni yuborish tugmasini bosing.")
    return ASK_PHONE


async def ask_size(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    allowed_sizes = ["46", "48", "50", "52", "54", "56"]

    if text == "⬅️ Orqaga":
        await update.message.reply_text("Telefon raqamingizni yuboring:", reply_markup=phone_markup)
        return ASK_PHONE

    if text not in allowed_sizes:
        await update.message.reply_text("Razmerni tugmadan tanlang:", reply_markup=size_markup)
        return ASK_SIZE

    context.user_data["size"] = text
    await update.message.reply_text("Rangni tanlang:", reply_markup=color_markup)
    return ASK_COLOR


async def ask_color(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    allowed_colors = ["⚪ Oq", "🌸 Pushti", "⚫ Qora", "🔴 Qizil", "🔵 Ko‘k"]

    if text == "⬅️ Orqaga":
        await update.message.reply_text("Razmerni tanlang:", reply_markup=size_markup)
        return ASK_SIZE

    if text not in allowed_colors:
        await update.message.reply_text("Rangni tugmadan tanlang:", reply_markup=color_markup)
        return ASK_COLOR

    context.user_data["color"] = text
    await update.message.reply_text("To‘lov turini tanlang:", reply_markup=payment_markup)
    return ASK_PAYMENT


async def ask_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text

    if text == "⬅️ Orqaga":
        await update.message.reply_text("Rangni tanlang:", reply_markup=color_markup)
        return ASK_COLOR

    if text not in ALLOWED_PAYMENTS:
        await update.message.reply_text("To‘lov turini tugmadan tanlang:", reply_markup=payment_markup)
        return ASK_PAYMENT

    context.user_data["payment"] = text

    product_name = context.user_data.get("product", "")
    product_code = context.user_data.get("product_code", "")
    product_price = 0

    if product_code and product_code in PRODUCTS:
        product_price = PRODUCTS[product_code].get("price", 0)
        product_name = PRODUCTS[product_code].get("name", product_name)

    region = context.user_data.get("order_region", "")
    total_price = product_price

    if text in ["💳 Karta", "📲 Click", "📲 Payme"]:
        context.user_data["pending_total"] = total_price
        context.user_data["pending_product_price"] = product_price

        await update.message.reply_text(
            "💳 To‘lov uchun karta:\n\n"
            f"👤 Karta egasi: {CARD_HOLDER}\n"
            f"💳 Karta raqami: {CARD_NUMBER}\n\n"
            f"💰 To‘lanadigan summa: {total_price:,} so‘m\n\n"
            "To‘lov qilganingizdan keyin chek rasmini yuboring."
        )
        return ASK_RECEIPT

    name = context.user_data.get("name", "")
    phone = context.user_data.get("phone", "")
    size = context.user_data.get("size", "")
    color = context.user_data.get("color", "")
    payment = context.user_data.get("payment", "")

    order_id = next_order_id()
    ORDERS[order_id] = {
        "user_id": update.effective_chat.id,
        "product": product_name,
        "region": region,
        "name": name,
        "phone": phone,
        "size": size,
        "color": color,
        "payment": payment,
        "product_price": product_price,
        "total_price": total_price,
        "status": STATUS_LABELS["new"],
    }
    save_json(ORDERS_FILE, ORDERS)

    await update.message.reply_text(
        "✅ Buyurtmangiz qabul qilindi!\n\n"
        f"🆔 Buyurtma ID: {order_id}\n"
        f"🛍 Mahsulot: {product_name}\n"
        f"📍 Viloyat: {region}\n"
        f"👤 Ism: {name}\n"
        f"📱 Telefon: {phone}\n"
        f"📏 Razmer: {size}\n"
        f"🎨 Rang: {color}\n"
        f"💳 To‘lov turi: {payment}\n"
        f"💵 Mahsulot narxi: {product_price:,} so‘m\n"
        f"💰 Jami: {total_price:,} so‘m",
        reply_markup=main_markup,
    )

    try:
        await context.bot.send_message(
            chat_id=ADMIN_CHAT_ID,
            text=order_text(order_id, ORDERS[order_id]),
            reply_markup=admin_order_keyboard(order_id),
        )
    except Exception:
        await update.message.reply_text("Buyurtma saqlandi, lekin adminga yuborilmadi.")

    context.user_data.clear()
    context.user_data["section"] = "main"
    return ConversationHandler.END


async def ask_receipt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.photo and not update.message.document:
        await update.message.reply_text("Chek rasmini yuboring.")
        return ASK_RECEIPT

    product = context.user_data.get("product", "")
    region = context.user_data.get("order_region", "")
    name = context.user_data.get("name", "")
    phone = context.user_data.get("phone", "")
    size = context.user_data.get("size", "")
    color = context.user_data.get("color", "")
    payment = context.user_data.get("payment", "")
    product_price = context.user_data.get("pending_product_price", 0)
    total_price = context.user_data.get("pending_total", 0)

    order_id = next_order_id()
    ORDERS[order_id] = {
        "user_id": update.effective_chat.id,
        "product": product,
        "region": region,
        "name": name,
        "phone": phone,
        "size": size,
        "color": color,
        "payment": payment,
        "product_price": product_price,
        "total_price": total_price,
        "status": STATUS_LABELS["paid"],
    }
    save_json(ORDERS_FILE, ORDERS)

    await update.message.reply_text(
        "✅ Chekingiz qabul qilindi.\nAdmin tekshiradi.\n\n"
        f"🆔 Buyurtma ID: {order_id}",
        reply_markup=main_markup,
    )

    admin_text = (
        "🧾 YANGI TO‘LOV CHEKI\n\n"
        f"🆔 Buyurtma ID: {order_id}\n"
        f"🛍 Mahsulot: {product}\n"
        f"📍 Viloyat: {region}\n"
        f"👤 Ism: {name}\n"
        f"📱 Telefon: {phone}\n"
        f"📏 Razmer: {size}\n"
        f"🎨 Rang: {color}\n"
        f"💳 To‘lov turi: {payment}\n"
        f"💵 Mahsulot narxi: {product_price:,} so‘m\n"
        f"💰 Jami: {total_price:,} so‘m\n"
        f"📌 Holat: {STATUS_LABELS['paid']}"
    )

    try:
        if update.message.photo:
            file_id = update.message.photo[-1].file_id
            await context.bot.send_photo(
                chat_id=ADMIN_CHAT_ID,
                photo=file_id,
                caption=admin_text,
                reply_markup=admin_order_keyboard(order_id),
            )
        else:
            file_id = update.message.document.file_id
            await context.bot.send_document(
                chat_id=ADMIN_CHAT_ID,
                document=file_id,
                caption=admin_text,
                reply_markup=admin_order_keyboard(order_id),
            )
    except Exception:
        await update.message.reply_text("Chek adminga yuborilmadi.")

    context.user_data.clear()
    context.user_data["section"] = "main"
    return ConversationHandler.END


async def cancel_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    context.user_data["section"] = "main"
    await update.message.reply_text("Buyurtma bekor qilindi.", reply_markup=main_markup)
    return ConversationHandler.END


async def admin_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.from_user.id != ADMIN_CHAT_ID:
        await query.answer("Siz admin emassiz.", show_alert=True)
        return

    _, order_id, status_key = query.data.split(":")
    order = ORDERS.get(order_id)

    if not order:
        if query.message.photo or query.message.document:
            await query.edit_message_caption(caption="Buyurtma topilmadi.")
        else:
            await query.edit_message_text("Buyurtma topilmadi.")
        return

    order["status"] = STATUS_LABELS[status_key]
    save_json(ORDERS_FILE, ORDERS)

    new_text = order_text(order_id, order)

    try:
        if query.message.photo or query.message.document:
            await query.edit_message_caption(
                caption=new_text,
                reply_markup=admin_order_keyboard(order_id),
            )
        else:
            await query.edit_message_text(
                text=new_text,
                reply_markup=admin_order_keyboard(order_id),
            )
    except Exception as e:
        print("Admin action error:", e)

    try:
        await context.bot.send_message(
            chat_id=order["user_id"],
            text=f"🆔 Buyurtma ID: {order_id}\n📌 Buyurtmangiz holati yangilandi:\n{order['status']}",
        )
    except Exception as e:
        print("Userga status yuborishda xato:", e)


async def list_orders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_CHAT_ID:
        await update.message.reply_text("Bu buyruq faqat admin uchun.")
        return

    if not ORDERS:
        await update.message.reply_text("Hozircha buyurtmalar yo‘q.")
        return

    lines = ["📦 Buyurtmalar ro‘yxati:\n"]
    for order_id, order in ORDERS.items():
        lines.append(f"🆔 {order_id} | {order['product']} | {order['region']} | {order['status']}")

    await update.message.reply_text("\n".join(lines))


async def reklamastart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_CHAT_ID:
        await update.message.reply_text("Bu buyruq faqat admin uchun.")
        return

    context.user_data["broadcast_mode"] = True
    await update.message.reply_text(
        "📢 Reklama rejimi yoqildi.\n"
        "Endi yuborgan keyingi text, rasm, video yoki post hamma userlarga boradi.\n\n"
        "Bekor qilish: /cancel_reklama"
    )


async def cancel_reklama(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_CHAT_ID:
        return

    context.user_data["broadcast_mode"] = False
    await update.message.reply_text("Reklama rejimi bekor qilindi.")


async def handle_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_CHAT_ID:
        return
    if not context.user_data.get("broadcast_mode"):
        return

    sent = 0
    failed = 0
    admin_id = update.effective_chat.id
    msg = update.effective_message

    for user_id in USERS:
        try:
            if int(user_id) == int(admin_id):
                continue
            await context.bot.copy_message(
                chat_id=user_id,
                from_chat_id=admin_id,
                message_id=msg.message_id,
            )
            sent += 1
        except Exception:
            failed += 1

    context.user_data["broadcast_mode"] = False
    await update.message.reply_text(f"✅ Reklama yuborildi.\n\nYuborildi: {sent}\nXato: {failed}")


async def check_subscription_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    ok = await is_user_subscribed(context, query.from_user.id)
    if ok:
        try:
            await query.message.delete()
        except Exception:
            pass
        await query.message.reply_text("✅ Obuna tasdiqlandi.\nAsosiy menu:", reply_markup=main_markup)
    else:
        await query.answer("Hali kanalga a’zo bo‘lmagansiz.", show_alert=True)


async def ai_reply(update: Update, text: str):
    if not ai_model:
        await update.message.reply_text("Kerakli tugmani tanlang.")
        return

    try:
        response = ai_model.generate_content(
            "Sen Shodashop kiyim do‘koni uchun sotuvchi-yordamchi botsan. "
            "Qisqa, chiroyli va foydali javob ber. "
            "User Uzbek tilida yozsa Uzbek tilida javob ber. "
            "Mahsulotlar: pijama, pinuar, parfumeriya. "
            "Buyurtma berish uchun userga mahsulot tanlashni ayt.\n\n"
            f"User savoli: {text}"
        )
        await update.message.reply_text(response.text)
    except Exception as e:
        print("Gemini AI error:", e)
        await update.message.reply_text("AI vaqtincha ishlamayapti.")


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    add_user(update.effective_user.id)

    if not await ensure_subscription(update, context):
        return

    if update.effective_user.id == ADMIN_CHAT_ID and context.user_data.get("broadcast_mode"):
        await handle_broadcast(update, context)
        return

    text = update.message.text
    section = context.user_data.get("section", "main")
    selected_city = context.user_data.get("selected_city", "")

    if text == "🛍 Mahsulotlar":
        await products(update, context)

    elif text == "👗 Pijama":
        await show_product(update, context, "Pijama", "👗 Pijama")

    elif text == "🥻 Pinuar":
        await show_product(update, context, "Pinuar", "🥻 Pinuar")

    elif text == "🌸 Parfumeriya":
        await show_product(update, context, "Parfumeriya", "🌸 Parfumeriya")

    elif text == "📞 Aloqa":
        await contact(update, context)

    elif text == "📍 Toshkent":
        context.user_data["selected_city"] = "Toshkent"
        context.user_data["section"] = "contact_detail"
        await update.message.reply_text("📍 Toshkent bo‘yicha bo‘limni tanlang:", reply_markup=contact_detail_markup)

    elif text == "📍 Qo‘qon":
        context.user_data["selected_city"] = "Qo‘qon"
        context.user_data["section"] = "contact_detail"
        await update.message.reply_text("📍 Qo‘qon bo‘yicha bo‘limni tanlang:", reply_markup=contact_detail_markup)

    elif text == "📱 Qo‘ng‘iroq":
        if selected_city == "Toshkent":
            await update.message.reply_text("📱 Toshkent telefon raqamlari:\n\n1) +998 90 827 88 25\n2) +998 90 827 88 96")
        elif selected_city == "Qo‘qon":
            await update.message.reply_text("📱 Qo‘qon telefon raqamlari:\n\n1) +998 95 007 95 66\n2) +998 90 550 70 45")
        else:
            await update.message.reply_text("Avval shaharni tanlang.")

    elif text == "💬 Telegram":
        if selected_city == "Toshkent":
            await update.message.reply_text("💬 Toshkent Telegram:\n@shodashop_toshkent")
        elif selected_city == "Qo‘qon":
            await update.message.reply_text("💬 Qo‘qon Telegram:\n@shodashop")
        else:
            await update.message.reply_text("Avval shaharni tanlang.")

    elif text == "📍 Manzil":
        if selected_city == "Toshkent":
            await context.bot.send_location(chat_id=update.effective_chat.id, latitude=41.257681, longitude=69.153924)
            await update.message.reply_text("📍 Toshkent manzili")
        elif selected_city == "Qo‘qon":
            await context.bot.send_location(chat_id=update.effective_chat.id, latitude=40.554953, longitude=70.963713)
            await update.message.reply_text("📍 Qo‘qon manzili")
        else:
            await update.message.reply_text("Avval shaharni tanlang.")

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
            await update.message.reply_text("Mahsulot bo‘limini tanlang:", reply_markup=product_markup)
        elif section == "contact_city":
            context.user_data["section"] = "main"
            await update.message.reply_text("Asosiy menu", reply_markup=main_markup)
        elif section == "contact_detail":
            context.user_data["section"] = "contact_city"
            await update.message.reply_text("📞 Qaysi shahar bo‘yicha aloqa kerak?", reply_markup=city_markup)
        else:
            context.user_data["section"] = "main"
            await update.message.reply_text("Asosiy menu", reply_markup=main_markup)

    else:
        await ai_reply(update, text)


telegram_app = Application.builder().token(TOKEN).build()

order_handler = ConversationHandler(
    entry_points=[MessageHandler(filters.Regex("^🛒 Buyurtma berish$"), order_entry)],
    states={
        ASK_REGION: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_region)],
        ASK_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_name)],
        ASK_PHONE: [
            MessageHandler(filters.CONTACT, ask_phone),
            MessageHandler(filters.TEXT & ~filters.COMMAND, ask_phone),
        ],
        ASK_SIZE: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_size)],
        ASK_COLOR: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_color)],
        ASK_PAYMENT: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_payment)],
        ASK_RECEIPT: [
            MessageHandler(filters.PHOTO | filters.Document.IMAGE, ask_receipt),
            MessageHandler(filters.TEXT & ~filters.COMMAND, ask_receipt),
        ],
    },
    fallbacks=[CommandHandler("cancel", cancel_order)],
)

telegram_app.add_handler(CommandHandler("start", start))
telegram_app.add_handler(CommandHandler("menu", menu))
telegram_app.add_handler(CommandHandler("orders", list_orders))
telegram_app.add_handler(CommandHandler("reklama", reklamastart))
telegram_app.add_handler(CommandHandler("cancel_reklama", cancel_reklama))
telegram_app.add_handler(order_handler)
telegram_app.add_handler(CallbackQueryHandler(check_subscription_callback, pattern="^check_sub$"))
telegram_app.add_handler(CallbackQueryHandler(admin_action, pattern="^status:"))
telegram_app.add_handler(
    MessageHandler(
        (filters.ChatType.CHANNEL | filters.ChatType.GROUPS) & (filters.PHOTO | filters.Document.IMAGE),
        handle_channel_post,
    )
)
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
