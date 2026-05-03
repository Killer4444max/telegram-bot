import asyncio
import json
import os
import re
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton, InputMediaPhoto
from telegram.constants import ChatMemberStatus
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, ConversationHandler, filters

TOKEN = os.getenv('TOKEN')
RENDER_EXTERNAL_URL = os.getenv('RENDER_EXTERNAL_URL')
ADMIN_CHAT_ID = os.getenv('ADMIN_CHAT_ID')
CARD_NUMBER = os.getenv('CARD_NUMBER')
CARD_HOLDER = os.getenv('CARD_HOLDER')
PRODUCT_CHANNEL_USERNAME = os.getenv('PRODUCT_CHANNEL_USERNAME', '@pijamas_optom')

if not TOKEN:
    raise RuntimeError('TOKEN topilmadi')
if not ADMIN_CHAT_ID:
    raise RuntimeError('ADMIN_CHAT_ID topilmadi')
if not CARD_NUMBER or not CARD_HOLDER:
    raise RuntimeError('CARD_NUMBER yoki CARD_HOLDER topilmadi')

ADMIN_CHAT_ID = int(ADMIN_CHAT_ID)

REQUIRED_CHANNELS = [('Bizning kanal', '@pijamas_optom', 'https://t.me/pijamas_optom')]

ORDERS_FILE = Path('orders.json')
USERS_FILE = Path('users.json')
PRODUCTS_FILE = Path('products.json')

ASK_REGION, ASK_NAME, ASK_PHONE, ASK_SIZE, ASK_COLOR, ASK_QUANTITY, ASK_PAYMENT, ASK_RECEIPT = range(8)

ALLOWED_REGIONS = ['📍 Toshkent', '📍 Andijon', '📍 Farg‘ona', '📍 Namangan', '📍 Samarqand', '📍 Buxoro', '📍 Xorazm', '📍 Qashqadaryo', '📍 Surxondaryo', '📍 Jizzax', '📍 Sirdaryo', '📍 Navoiy']
STATUS_LABELS = {'new': 'Yangi', 'accepted': 'Qabul qilindi ✅', 'preparing': 'Tayyorlanmoqda 🧵', 'shipped': 'Yuborildi 🚚', 'delivered': 'Yetkazildi 📦', 'rejected': 'Bekor qilindi ❌', 'paid': 'To‘lov tekshirilmoqda ⏳', 'receipt_ok': 'To‘lov tushdi ✅', 'receipt_bad': 'To‘lov topilmadi ❌'}

main_markup = ReplyKeyboardMarkup([['🛍 Mahsulotlar', '📞 Aloqa'], ['ℹ️ Haqimizda', '📢 Kanal']], resize_keyboard=True)
product_markup = ReplyKeyboardMarkup([['👗 Pijama', '🥻 Pinuar'], ['🌸 Parfumeriya'], ['⬅️ Orqaga']], resize_keyboard=True)
city_markup = ReplyKeyboardMarkup([['📍 Toshkent', '📍 Qo‘qon'], ['⬅️ Orqaga']], resize_keyboard=True)
contact_detail_markup = ReplyKeyboardMarkup([['📱 Qo‘ng‘iroq', '💬 Telegram'], ['📍 Manzil'], ['⬅️ Orqaga']], resize_keyboard=True)
phone_markup = ReplyKeyboardMarkup([[KeyboardButton('📲 Raqamni yuborish', request_contact=True)]], resize_keyboard=True, one_time_keyboard=True)
size_markup = ReplyKeyboardMarkup([['46', '48', '50'], ['52', '54', '56'], ['⬅️ Orqaga']], resize_keyboard=True, one_time_keyboard=True)
color_markup = ReplyKeyboardMarkup([['⚪ Oq', '🌸 Pushti'], ['⚫ Qora', '🔴 Qizil'], ['🔵 Ko‘k'], ['⬅️ Orqaga']], resize_keyboard=True, one_time_keyboard=True)
quantity_markup = ReplyKeyboardMarkup([['1', '2', '3'], ['4', '5', '10'], ['⬅️ Orqaga']], resize_keyboard=True, one_time_keyboard=True)
region_markup = ReplyKeyboardMarkup([['📍 Toshkent', '📍 Andijon'], ['📍 Farg‘ona', '📍 Namangan'], ['📍 Samarqand', '📍 Buxoro'], ['📍 Xorazm', '📍 Qashqadaryo'], ['📍 Surxondaryo', '📍 Jizzax'], ['📍 Sirdaryo', '📍 Navoiy'], ['⬅️ Orqaga']], resize_keyboard=True, one_time_keyboard=True)
payment_markup = ReplyKeyboardMarkup([['💵 Naqd', '💳 Karta'], ['📲 Click', '📲 Payme'], ['⬅️ Orqaga']], resize_keyboard=True, one_time_keyboard=True)
ALLOWED_PAYMENTS = ['💵 Naqd', '💳 Karta', '📲 Click', '📲 Payme']


def load_json(path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return default


def save_json(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')

ORDERS = load_json(ORDERS_FILE, {})
USERS = load_json(USERS_FILE, [])
PRODUCTS = load_json(PRODUCTS_FILE, {})
ALBUMS = {}


def add_user(user_id):
    if user_id not in USERS:
        USERS.append(user_id)
        save_json(USERS_FILE, USERS)


def next_order_id():
    return '1' if not ORDERS else str(max(int(k) for k in ORDERS.keys()) + 1)


def order_text(order_id, order):
    return ('🛒 BUYURTMA\n\n'
            f'🆔 Buyurtma ID: {order_id}\n'
            f'🛍 Mahsulot: {order["product"]}\n'
            f'🆔 Mahsulot kodi: {order.get("product_code", "-")}\n'
            f'📍 Viloyat: {order["region"]}\n'
            f'👤 Ism: {order["name"]}\n'
            f'📱 Telefon: {order["phone"]}\n'
            f'📏 Razmer: {order["size"]}\n'
            f'🎨 Rang: {order["color"]}\n'
            f'🔢 Soni: {order.get("quantity", 1)} ta\n'
            f'💳 To‘lov turi: {order["payment"]}\n'
            f'💵 1 dona narxi: {order["product_price"]:,} so‘m\n'
            f'💰 Jami: {order["total_price"]:,} so‘m\n'
            f'📌 Holat: {order["status"]}')


def admin_order_keyboard(order_id):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton('✅ To‘lov tushdi', callback_data=f'status:{order_id}:receipt_ok'), InlineKeyboardButton('❌ To‘lov tushmadi', callback_data=f'status:{order_id}:receipt_bad')],
        [InlineKeyboardButton('✅ Qabul', callback_data=f'status:{order_id}:accepted'), InlineKeyboardButton('🧵 Tayyor', callback_data=f'status:{order_id}:preparing')],
        [InlineKeyboardButton('🚚 Yuborildi', callback_data=f'status:{order_id}:shipped'), InlineKeyboardButton('📦 Yetkazildi', callback_data=f'status:{order_id}:delivered')],
        [InlineKeyboardButton('❌ Bekor', callback_data=f'status:{order_id}:rejected')],
    ])


def product_order_keyboard(code):
    return InlineKeyboardMarkup([[InlineKeyboardButton(f'🛒 {code} ni buyurtma qilish', callback_data=f'buy:{code}')]])


def subscription_keyboard():
    rows = [[InlineKeyboardButton(f'🔔 {title}', url=url)] for title, _, url in REQUIRED_CHANNELS]
    rows.append([InlineKeyboardButton('✅ Tekshirish', callback_data='check_sub')])
    return InlineKeyboardMarkup(rows)


def parse_product_caption(caption):
    if not caption:
        return None
    name_match = re.search(r'(?im)^NOM:\s*(.+)$', caption)
    price_match = re.search(r'(?im)^NARX:\s*([\d\s]+)$', caption)
    code_match = re.search(r'(?im)^KOD:\s*(.+)$', caption)
    color_match = re.search(r'(?im)^RANG:\s*(.+)$', caption)
    if not name_match or not price_match or not code_match:
        return None
    raw_price = price_match.group(1).replace(' ', '').strip()
    if not raw_price.isdigit():
        return None
    return {'name': name_match.group(1).strip(), 'price': int(raw_price), 'code': code_match.group(1).strip(), 'color': color_match.group(1).strip() if color_match else ''}


def get_products_by_name(name):
    return [(code, product) for code, product in PRODUCTS.items() if product.get('name', '').lower() == name.lower()]


async def is_user_subscribed(context, user_id):
    try:
        for _, username, _ in REQUIRED_CHANNELS:
            member = await context.bot.get_chat_member(chat_id=username, user_id=user_id)
            if member.status in [ChatMemberStatus.LEFT, ChatMemberStatus.BANNED]:
                return False
        return True
    except Exception as e:
        print('Subscription check error:', e)
        return False


async def ensure_subscription(update, context):
    ok = await is_user_subscribed(context, update.effective_user.id)
    if ok:
        return True
    await update.effective_message.reply_text('❗ Botdan foydalanish uchun avval kanalga a’zo bo‘ling.\n\nA’zo bo‘lgach, ✅ Tekshirish tugmasini bosing.', reply_markup=subscription_keyboard())
    return False


async def save_album_later(media_group_id):
    await asyncio.sleep(2)
    album = ALBUMS.pop(media_group_id, None)
    if not album or not album.get('parsed') or not album.get('photos'):
        return
    parsed = album['parsed']
    code = parsed['code']
    PRODUCTS[code] = {'name': parsed['name'], 'price': parsed['price'], 'code': code, 'color': parsed['color'], 'photo_file_ids': album['photos']}
    save_json(PRODUCTS_FILE, PRODUCTS)
    print(f'Album mahsulot saqlandi: {code} - {parsed["name"]} | rasmlar: {len(album["photos"])}')


async def handle_channel_post(update, context):
    msg = update.channel_post or update.message
    if not msg:
        return
    chat_username = f'@{msg.chat.username.lower()}' if msg.chat.username else ''
    if chat_username != PRODUCT_CHANNEL_USERNAME.lower():
        return
    photo_file_id = None
    if msg.photo:
        photo_file_id = msg.photo[-1].file_id
    elif msg.document and msg.document.mime_type and msg.document.mime_type.startswith('image/'):
        photo_file_id = msg.document.file_id
    if not photo_file_id:
        return
    if msg.media_group_id:
        group_id = str(msg.media_group_id)
        if group_id not in ALBUMS:
            ALBUMS[group_id] = {'photos': [], 'parsed': None, 'task_started': False}
        ALBUMS[group_id]['photos'].append(photo_file_id)
        parsed = parse_product_caption(msg.caption or '')
        if parsed:
            ALBUMS[group_id]['parsed'] = parsed
        if not ALBUMS[group_id]['task_started']:
            ALBUMS[group_id]['task_started'] = True
            asyncio.create_task(save_album_later(group_id))
        return
    parsed = parse_product_caption(msg.caption or '')
    if not parsed:
        return
    code = parsed['code']
    PRODUCTS[code] = {'name': parsed['name'], 'price': parsed['price'], 'code': code, 'color': parsed['color'], 'photo_file_ids': [photo_file_id]}
    save_json(PRODUCTS_FILE, PRODUCTS)
    print(f'Mahsulot saqlandi: {code} - {parsed["name"]}')


async def start(update, context):
    add_user(update.effective_user.id)
    if not await ensure_subscription(update, context):
        return
    context.user_data['section'] = 'main'
    await update.message.reply_text('Assalomu alaykum!\nBotga xush kelibsiz 🚀\n\nQuyidagi menyudan birini tanlang:', reply_markup=main_markup)


async def menu(update, context):
    if not await ensure_subscription(update, context):
        return
    context.user_data['section'] = 'main'
    await update.message.reply_text('Asosiy menu ✅', reply_markup=main_markup)


async def products(update, context):
    context.user_data['section'] = 'products'
    await update.message.reply_text('Mahsulot bo‘limini tanlang:', reply_markup=product_markup)


async def contact(update, context):
    context.user_data['section'] = 'contact_city'
    await update.message.reply_text('📞 Qaysi shahar bo‘yicha aloqa kerak?', reply_markup=city_markup)


async def about(update, context):
    await update.message.reply_text('Biz online shopmiz. Sifatli mahsulotlarni taklif qilamiz.')


async def channel(update, context):
    await update.message.reply_text('📢 Bizning kanal:\n\nhttps://t.me/pijamas_optom')


async def show_product(update, context, product_name, emoji_title):
    products_list = get_products_by_name(product_name)
    if not products_list:
        await update.message.reply_text(f'{emoji_title} bo‘limi uchun hali mahsulot joylanmagan.\n\nPost formati:\nNOM: Pijama\nNARX: 120000\nKOD: PJ01\nRANG: oq, qora')
        return
    context.user_data['section'] = 'products'
    for code, product in products_list:
        caption = f'{emoji_title}\n\n🛍 Nomi: {product["name"]}\n🆔 Kodi: {product["code"]}\n💵 Narxi: {product["price"]:,} so‘m\n🎨 Rang: {product.get("color", "-")}\n\nBuyurtma qilish uchun pastdagi tugmani bosing.'
        photo_ids = product.get('photo_file_ids') or [product.get('photo_file_id')]
        if len(photo_ids) == 1:
            await context.bot.send_photo(chat_id=update.effective_chat.id, photo=photo_ids[0], caption=caption, reply_markup=product_order_keyboard(code))
        else:
            media = [InputMediaPhoto(media=p, caption=caption if i == 0 else None) for i, p in enumerate(photo_ids)]
            await context.bot.send_media_group(chat_id=update.effective_chat.id, media=media)
            await update.message.reply_text(f'🛒 {code} mahsulotini buyurtma qilish:', reply_markup=product_order_keyboard(code))


async def order_entry_callback(update, context):
    query = update.callback_query
    await query.answer()
    if not await ensure_subscription(update, context):
        return ConversationHandler.END
    code = query.data.split(':', 1)[1]
    product = PRODUCTS.get(code)
    if not product:
        await query.message.reply_text('Bu mahsulot topilmadi. Qaytadan tanlang.')
        return ConversationHandler.END
    context.user_data['product'] = product['name']
    context.user_data['product_code'] = code
    context.user_data['product_price'] = int(product['price'])
    await query.message.reply_text(f'Buyurtma boshlandi ✅\n\n🛍 Mahsulot: {product["name"]}\n🆔 Kod: {code}\n💵 Narx: {int(product["price"]):,} so‘m\n\nEndi viloyatni tanlang:', reply_markup=region_markup)
    return ASK_REGION


async def ask_region(update, context):
    text = update.message.text
    if text == '⬅️ Orqaga':
        context.user_data.clear()
        context.user_data['section'] = 'main'
        await update.message.reply_text('Buyurtma bekor qilindi.', reply_markup=main_markup)
        return ConversationHandler.END
    if text not in ALLOWED_REGIONS:
        await update.message.reply_text('Viloyatni tugmadan tanlang:', reply_markup=region_markup)
        return ASK_REGION
    context.user_data['order_region'] = text
    await update.message.reply_text(f'Tanlangan viloyat: {text}\n\nIsmingizni yozing:')
    return ASK_NAME


async def ask_name(update, context):
    context.user_data['name'] = update.message.text
    await update.message.reply_text('Telefon raqamingizni yuboring:', reply_markup=phone_markup)
    return ASK_PHONE


async def ask_phone(update, context):
    if update.message.contact:
        context.user_data['phone'] = update.message.contact.phone_number
        await update.message.reply_text('Razmerni tanlang:', reply_markup=size_markup)
        return ASK_SIZE
    await update.message.reply_text('Pastdagi 📲 Raqamni yuborish tugmasini bosing.')
    return ASK_PHONE


async def ask_size(update, context):
    text = update.message.text
    if text == '⬅️ Orqaga':
        await update.message.reply_text('Telefon raqamingizni yuboring:', reply_markup=phone_markup)
        return ASK_PHONE
    if text not in ['46', '48', '50', '52', '54', '56']:
        await update.message.reply_text('Razmerni tugmadan tanlang:', reply_markup=size_markup)
        return ASK_SIZE
    context.user_data['size'] = text
    await update.message.reply_text('Rangni tanlang:', reply_markup=color_markup)
    return ASK_COLOR


async def ask_color(update, context):
    text = update.message.text
    if text == '⬅️ Orqaga':
        await update.message.reply_text('Razmerni tanlang:', reply_markup=size_markup)
        return ASK_SIZE
    if text not in ['⚪ Oq', '🌸 Pushti', '⚫ Qora', '🔴 Qizil', '🔵 Ko‘k']:
        await update.message.reply_text('Rangni tugmadan tanlang:', reply_markup=color_markup)
        return ASK_COLOR
    context.user_data['color'] = text
    await update.message.reply_text('Nechta olasiz?', reply_markup=quantity_markup)
    return ASK_QUANTITY


async def ask_quantity(update, context):
    text = update.message.text
    if text == '⬅️ Orqaga':
        await update.message.reply_text('Rangni tanlang:', reply_markup=color_markup)
        return ASK_COLOR
    if not text.isdigit() or int(text) <= 0:
        await update.message.reply_text('Soni faqat raqam bo‘lsin. Masalan: 1, 2, 3')
        return ASK_QUANTITY
    context.user_data['quantity'] = int(text)
    await update.message.reply_text('To‘lov turini tanlang:', reply_markup=payment_markup)
    return ASK_PAYMENT


async def ask_payment(update, context):
    text = update.message.text
    if text == '⬅️ Orqaga':
        await update.message.reply_text('Nechta olasiz?', reply_markup=quantity_markup)
        return ASK_QUANTITY
    if text not in ALLOWED_PAYMENTS:
        await update.message.reply_text('To‘lov turini tugmadan tanlang:', reply_markup=payment_markup)
        return ASK_PAYMENT
    context.user_data['payment'] = text
    product_price = int(context.user_data.get('product_price', 0))
    quantity = int(context.user_data.get('quantity', 1))
    total_price = product_price * quantity
    if text in ['💳 Karta', '📲 Click', '📲 Payme']:
        context.user_data['pending_total'] = total_price
        context.user_data['pending_product_price'] = product_price
        await update.message.reply_text(f'💳 To‘lov uchun karta:\n\n👤 Karta egasi: {CARD_HOLDER}\n💳 Karta raqami: {CARD_NUMBER}\n\n💵 1 dona narxi: {product_price:,} so‘m\n🔢 Soni: {quantity} ta\n💰 To‘lanadigan summa: {total_price:,} so‘m\n\nTo‘lov qilganingizdan keyin chek rasmini yuboring.')
        return ASK_RECEIPT
    await create_order_and_notify(update, context, STATUS_LABELS['new'])
    return ConversationHandler.END


async def create_order_and_notify(update, context, status):
    product_price = int(context.user_data.get('pending_product_price', context.user_data.get('product_price', 0)))
    quantity = int(context.user_data.get('quantity', 1))
    total_price = int(context.user_data.get('pending_total', product_price * quantity))
    order_id = next_order_id()
    ORDERS[order_id] = {'user_id': update.effective_chat.id, 'product': context.user_data.get('product', ''), 'product_code': context.user_data.get('product_code', ''), 'region': context.user_data.get('order_region', ''), 'name': context.user_data.get('name', ''), 'phone': context.user_data.get('phone', ''), 'size': context.user_data.get('size', ''), 'color': context.user_data.get('color', ''), 'quantity': quantity, 'payment': context.user_data.get('payment', ''), 'product_price': product_price, 'total_price': total_price, 'status': status}
    save_json(ORDERS_FILE, ORDERS)
    await update.message.reply_text(f'✅ Buyurtmangiz qabul qilindi!\n\n🆔 Buyurtma ID: {order_id}\n🛍 Mahsulot: {ORDERS[order_id]["product"]}\n🆔 Kod: {ORDERS[order_id]["product_code"]}\n📍 Viloyat: {ORDERS[order_id]["region"]}\n👤 Ism: {ORDERS[order_id]["name"]}\n📱 Telefon: {ORDERS[order_id]["phone"]}\n📏 Razmer: {ORDERS[order_id]["size"]}\n🎨 Rang: {ORDERS[order_id]["color"]}\n🔢 Soni: {quantity} ta\n💳 To‘lov turi: {ORDERS[order_id]["payment"]}\n💵 1 dona narxi: {product_price:,} so‘m\n💰 Jami: {total_price:,} so‘m', reply_markup=main_markup)
    try:
        await context.bot.send_message(chat_id=ADMIN_CHAT_ID, text=order_text(order_id, ORDERS[order_id]), reply_markup=admin_order_keyboard(order_id))
    except Exception as e:
        print('Adminga yuborishda xato:', e)
    context.user_data.clear()
    context.user_data['section'] = 'main'


async def ask_receipt(update, context):
    if not update.message.photo and not update.message.document:
        await update.message.reply_text('Chek rasmini yuboring.')
        return ASK_RECEIPT
    await update.message.reply_text('✅ Chekingiz qabul qilindi. Admin tekshiradi.', reply_markup=main_markup)
    await create_order_and_notify(update, context, STATUS_LABELS['paid'])
    return ConversationHandler.END


async def cancel_order(update, context):
    context.user_data.clear()
    context.user_data['section'] = 'main'
    await update.message.reply_text('Buyurtma bekor qilindi.', reply_markup=main_markup)
    return ConversationHandler.END


async def admin_action(update, context):
    query = update.callback_query
    await query.answer()
    if query.from_user.id != ADMIN_CHAT_ID:
        await query.answer('Siz admin emassiz.', show_alert=True)
        return
    _, order_id, status_key = query.data.split(':')
    order = ORDERS.get(order_id)
    if not order:
        await query.message.reply_text('Buyurtma topilmadi.')
        return
    order['status'] = STATUS_LABELS[status_key]
    save_json(ORDERS_FILE, ORDERS)
    try:
        await query.edit_message_text(text=order_text(order_id, order), reply_markup=admin_order_keyboard(order_id))
    except Exception as e:
        print('Admin action edit error:', e)
    try:
        await context.bot.send_message(chat_id=order['user_id'], text=f'🆔 Buyurtma ID: {order_id}\n📌 Buyurtmangiz holati:\n{order["status"]}')
    except Exception as e:
        print('Userga status yuborishda xato:', e)


async def list_orders(update, context):
    if update.effective_user.id != ADMIN_CHAT_ID:
        await update.message.reply_text('Bu buyruq faqat admin uchun.')
        return
    if not ORDERS:
        await update.message.reply_text('Hozircha buyurtmalar yo‘q.')
        return
    lines = ['📦 Buyurtmalar ro‘yxati:\n']
    for order_id, order in ORDERS.items():
        lines.append(f'🆔 {order_id} | {order["product"]} | {order.get("product_code", "-")} | {order["status"]}')
    await update.message.reply_text('\n'.join(lines))


async def reklamastart(update, context):
    if update.effective_user.id != ADMIN_CHAT_ID:
        await update.message.reply_text('Bu buyruq faqat admin uchun.')
        return
    context.user_data['broadcast_mode'] = True
    await update.message.reply_text('📢 Reklama rejimi yoqildi. Keyingi xabar hamma userlarga boradi.')


async def cancel_reklama(update, context):
    if update.effective_user.id != ADMIN_CHAT_ID:
        return
    context.user_data['broadcast_mode'] = False
    await update.message.reply_text('Reklama rejimi bekor qilindi.')


async def handle_broadcast(update, context):
    if update.effective_user.id != ADMIN_CHAT_ID or not context.user_data.get('broadcast_mode'):
        return
    sent = failed = 0
    for user_id in USERS:
        try:
            if int(user_id) == int(update.effective_chat.id):
                continue
            await context.bot.copy_message(chat_id=user_id, from_chat_id=update.effective_chat.id, message_id=update.effective_message.message_id)
            sent += 1
        except Exception:
            failed += 1
    context.user_data['broadcast_mode'] = False
    await update.message.reply_text(f'✅ Reklama yuborildi.\nYuborildi: {sent}\nXato: {failed}')


async def check_subscription_callback(update, context):
    query = update.callback_query
    await query.answer()
    ok = await is_user_subscribed(context, query.from_user.id)
    if ok:
        try:
            await query.message.delete()
        except Exception:
            pass
        await query.message.reply_text('✅ Obuna tasdiqlandi.\nAsosiy menu:', reply_markup=main_markup)
    else:
        await query.answer('Hali kanalga a’zo bo‘lmagansiz.', show_alert=True)


async def handle_text(update, context):
    add_user(update.effective_user.id)
    if not await ensure_subscription(update, context):
        return
    if update.effective_user.id == ADMIN_CHAT_ID and context.user_data.get('broadcast_mode'):
        await handle_broadcast(update, context)
        return
    text = update.message.text
    section = context.user_data.get('section', 'main')
    selected_city = context.user_data.get('selected_city', '')
    if text == '🛍 Mahsulotlar':
        await products(update, context)
    elif text == '👗 Pijama':
        await show_product(update, context, 'Pijama', '👗 Pijama')
    elif text == '🥻 Pinuar':
        await show_product(update, context, 'Pinuar', '🥻 Pinuar')
    elif text == '🌸 Parfumeriya':
        await show_product(update, context, 'Parfumeriya', '🌸 Parfumeriya')
    elif text == '📞 Aloqa':
        await contact(update, context)
    elif text == '📍 Toshkent':
        context.user_data['selected_city'] = 'Toshkent'; context.user_data['section'] = 'contact_detail'
        await update.message.reply_text('📍 Toshkent bo‘yicha bo‘limni tanlang:', reply_markup=contact_detail_markup)
    elif text == '📍 Qo‘qon':
        context.user_data['selected_city'] = 'Qo‘qon'; context.user_data['section'] = 'contact_detail'
        await update.message.reply_text('📍 Qo‘qon bo‘yicha bo‘limni tanlang:', reply_markup=contact_detail_markup)
    elif text == '📱 Qo‘ng‘iroq':
        await update.message.reply_text('📱 Telefon:\n+998 95 007 95 66\n+998 90 550 70 45')
    elif text == '💬 Telegram':
        await update.message.reply_text('💬 Telegram:\n@shodashop')
    elif text == '📍 Manzil':
        await update.message.reply_text('📍 Manzil tez orada qo‘shiladi.')
    elif text == 'ℹ️ Haqimizda':
        await about(update, context)
    elif text == '📢 Kanal':
        await channel(update, context)
    elif text == '⬅️ Orqaga':
        if section == 'products':
            context.user_data['section'] = 'main'; await update.message.reply_text('Asosiy menu', reply_markup=main_markup)
        elif section == 'contact_city':
            context.user_data['section'] = 'main'; await update.message.reply_text('Asosiy menu', reply_markup=main_markup)
        elif section == 'contact_detail':
            context.user_data['section'] = 'contact_city'; await update.message.reply_text('📞 Qaysi shahar bo‘yicha aloqa kerak?', reply_markup=city_markup)
        else:
            context.user_data['section'] = 'main'; await update.message.reply_text('Asosiy menu', reply_markup=main_markup)
    else:
        await update.message.reply_text('Kerakli tugmani tanlang.')


async def error_handler(update, context):
    print('ERROR:', context.error)


telegram_app = Application.builder().token(TOKEN).build()
order_handler = ConversationHandler(
    entry_points=[CallbackQueryHandler(order_entry_callback, pattern='^buy:')],
    states={
        ASK_REGION: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_region)],
        ASK_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_name)],
        ASK_PHONE: [MessageHandler(filters.CONTACT, ask_phone), MessageHandler(filters.TEXT & ~filters.COMMAND, ask_phone)],
        ASK_SIZE: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_size)],
        ASK_COLOR: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_color)],
        ASK_QUANTITY: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_quantity)],
        ASK_PAYMENT: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_payment)],
        ASK_RECEIPT: [MessageHandler(filters.PHOTO | filters.Document.IMAGE, ask_receipt), MessageHandler(filters.TEXT & ~filters.COMMAND, ask_receipt)],
    },
    fallbacks=[CommandHandler('cancel', cancel_order)],
)

telegram_app.add_handler(CommandHandler('start', start))
telegram_app.add_handler(CommandHandler('menu', menu))
telegram_app.add_handler(CommandHandler('orders', list_orders))
telegram_app.add_handler(CommandHandler('reklama', reklamastart))
telegram_app.add_handler(CommandHandler('cancel_reklama', cancel_reklama))
telegram_app.add_handler(order_handler)
telegram_app.add_handler(CallbackQueryHandler(check_subscription_callback, pattern='^check_sub$'))
telegram_app.add_handler(CallbackQueryHandler(admin_action, pattern='^status:'))
telegram_app.add_handler(MessageHandler((filters.ChatType.CHANNEL | filters.ChatType.GROUPS) & (filters.PHOTO | filters.Document.IMAGE), handle_channel_post))
telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
telegram_app.add_error_handler(error_handler)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await telegram_app.initialize()
    await telegram_app.start()
    if RENDER_EXTERNAL_URL:
        webhook_url = RENDER_EXTERNAL_URL.rstrip('/') + '/webhook'
        await telegram_app.bot.set_webhook(webhook_url)
        print('Webhook set:', webhook_url)
    yield
    await telegram_app.stop()
    await telegram_app.shutdown()

app = FastAPI(lifespan=lifespan)

@app.get('/')
async def home():
    return {'status': 'ok'}

@app.post('/webhook')
async def webhook(req: Request):
    data = await req.json()
    update = Update.de_json(data, telegram_app.bot)
    await telegram_app.process_update(update)
    return {'ok': True}
