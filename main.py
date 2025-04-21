from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import Updater, MessageHandler, Filters, CallbackContext
import os
import json
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import base64

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
google_creds_raw = base64.b64decode(os.environ["GOOGLE_CREDS_B64"]).decode("utf-8")
google_creds = json.loads(google_creds_raw)
creds = ServiceAccountCredentials.from_json_keyfile_dict(google_creds, scope)
client = gspread.authorize(creds)
sheet = client.open_by_key(os.environ["SPREADSHEET_ID"]).sheet1

pending_state = {}  # chat_id: {step, amount, category}

# --- Обробник ---
def handle_message(update: Update, context: CallbackContext):
    chat_id = update.message.chat_id
    user = update.message.from_user.first_name
    text = update.message.text.strip().lower()

    state = pending_state.get(chat_id, {})

    if state.get("step") == "await_category":
        category = text
        if category not in CATEGORY_MAP:
            keyboard = [[c] for c in CATEGORY_MAP.keys()]
            update.message.reply_text("Вибери категорію з кнопок:", reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True))
            return
        if CATEGORY_MAP[category]:
            pending_state[chat_id] = {"step": "await_subcategory", "amount": state["amount"], "category": category}
            subcat_keyboard = [[s] for s in CATEGORY_MAP[category]]
            update.message.reply_text(f"'{category}' має підкатегорії. Обери одну:", reply_markup=ReplyKeyboardMarkup(subcat_keyboard, one_time_keyboard=True, resize_keyboard=True))
            return
        sheet.append_row([datetime.now().isoformat(), user, state["amount"], category, ""])
        update.message.reply_text(f"📂 {state['amount']} грн записано в '{category}'")
        pending_state.pop(chat_id)
        return

    if state.get("step") == "await_subcategory":
        sheet.append_row([datetime.now().isoformat(), user, state["amount"], state["category"], text])
        update.message.reply_text(f"📂 {state['amount']} грн записано в '{state['category']} > {text}'")
        pending_state.pop(chat_id)
        return

    # Якщо повідомлення тільки число — чекаємо категорію
    if text.replace(".", "", 1).isdigit():
        pending_state[chat_id] = {"step": "await_category", "amount": text}
        keyboard = [[c] for c in CATEGORY_MAP.keys()]
        update.message.reply_text("Окей, тепер обери категорію:", reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True))
        return

    update.message.reply_text("🤖 Напиши суму, наприклад '1000'")

# --- Запуск ---
updater = Updater(os.environ["BOT_TOKEN"], use_context=True)
dp = updater.dispatcher
dp.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_message))
updater.start_polling()
print("✅ FamilyMoneyBot працює")
updater.idle()
