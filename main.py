from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import Updater, MessageHandler, Filters, CallbackContext
import os
import json
import gspread
import base64
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime

# --- Категорії та підкатегорії ---
CATEGORY_MAP = {
    "продукти": [],
    "хозтовари": [],
    "ресторани": [],
    "кино": [],
    "кофейня": [],
    "авто": ["заправка", "техобслуживание", "мойка", "стоянка", "парковка", "кредит", "страховка"],
    "косметіка": [],
    "красота": [],
    "одежда, обувь": [],
    "комуналка, мобільний, інтернет": [],
    "дни рождения, праздники": [],
    "здоровье": ["бадЫ", "врачи", "лекарства", "психолог", "масаж"],
    "стрельба": ["патрони", "взноси", "запчасти"],
    "учеба": ["школа", "ангийский", "институт", "другое"],
    "такси": [],
    "донати": [],
    "квіти": [],
    "родителям": [],
    "техніка": []
}

# --- Google Sheets ---
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
google_creds_b64 = os.environ["GOOGLE_CREDS_B64"]
google_creds_raw = base64.b64decode(google_creds_b64).decode("utf-8")
google_creds = json.loads(google_creds_raw)
creds = ServiceAccountCredentials.from_json_keyfile_dict(google_creds, scope)
client = gspread.authorize(creds)
sheet = client.open_by_key(os.environ["SPREADSHEET_ID"]).sheet1

pending_categories = {}  # chat_id: (amount, category)

# --- Обробник ---
def handle_message(update: Update, context: CallbackContext):
    chat_id = update.message.chat_id
    user = update.message.from_user.first_name
    text = update.message.text.strip().lower()

    if chat_id in pending_categories:
        amount, main_category = pending_categories.pop(chat_id)
        subcat = text
        sheet.append_row([datetime.now().isoformat(), user, amount, main_category, subcat])
        update.message.reply_text(f"📂 {amount} грн записано в '{main_category} > {subcat}'")
        return

    parts = text.split(" ", 1)
    if len(parts) != 2 or not parts[0].replace(".", "", 1).isdigit():
        update.message.reply_text("🤖 Формат має бути типу '100 продукти'")
        return

    amount, category = parts[0], parts[1]

    # Пошук категорії (точне або часткове співпадіння)
    found_category = None
    for cat in CATEGORY_MAP:
        if category == cat or category.startswith(cat):
            found_category = cat
            break

    if not found_category:
        keyboard = [[c] for c in CATEGORY_MAP.keys()]
        update.message.reply_text(
            f"Не знаю категорію '{category}'. Обери з меню:",
            reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
        )
        return

    if CATEGORY_MAP[found_category]:
        pending_categories[chat_id] = (amount, found_category)
        subcat_keyboard = [[s] for s in CATEGORY_MAP[found_category]]
        update.message.reply_text(
            f"'{found_category}' має підкатегорії. Обери одну:",
            reply_markup=ReplyKeyboardMarkup(subcat_keyboard, one_time_keyboard=True, resize_keyboard=True)
        )
    else:
        sheet.append_row([datetime.now().isoformat(), user, amount, found_category, ""])
        update.message.reply_text(f"📂 {amount} грн записано в '{found_category}'")

# --- Запуск ---
updater = Updater(os.environ["BOT_TOKEN"], use_context=True)
dp = updater.dispatcher
dp.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_message))
updater.start_polling()
print("✅ FamilyMoneyBot працює")
updater.idle()
