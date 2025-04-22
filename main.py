
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import Updater, MessageHandler, Filters, CallbackContext, CommandHandler
import os
import json
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime, timedelta
import base64

CATEGORY_MAP = {
    "продукти": [],
    "господарські товари": [],
    "ресторани": [],
    "кіно": [],
    "кав'ярня": [],
    "авто": ["заправка", "техобслуговування", "мийка", "стоянка", "паркування", "кредит", "страхування"],
    "косметика": [],
    "краса": [],
    "одяг та взуття": [],
    "комуналка, мобільний, інтернет": [],
    "дні народження, свята": [],
    "здоров'я": ["бади", "лікарі", "ліки", "психолог", "масаж"],
    "стрільба": ["патрони", "внески", "запчастини"],
    "навчання": ["школа", "англійська", "інститут", "інше"],
    "таксі": [],
    "донати": [],
    "квіти": [],
    "батькам": [],
    "техніка": [],
    "прихід": []
}

scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
google_creds_raw = base64.b64decode(os.environ["GOOGLE_CREDS_B64"]).decode("utf-8")
google_creds = json.loads(google_creds_raw)
creds = ServiceAccountCredentials.from_json_keyfile_dict(google_creds, scope)
client = gspread.authorize(creds)
sheet = client.open_by_key(os.environ["SPREADSHEET_ID"]).sheet1
limits_sheet = client.open_by_key(os.environ["SPREADSHEET_ID"]).worksheet("Ліміти")

pending_state = {}
report_state = {}

def get_spent_in_category_this_month(category):
    rows = sheet.get_all_values()[1:]
    total = 0
    for row in rows:
        if len(row) < 4 or row[3] != category:
            continue
        try:
            dt = datetime.strptime(row[0], "%Y-%m-%d %H:%M")
            if dt < datetime.now().replace(day=1):
                continue
            val = float(row[2])
            if val < 0:
                total += abs(val)
        except:
            continue
    return total

def handle_message(update: Update, context: CallbackContext):
    user_id = update.message.from_user.id
    user_name = update.message.from_user.first_name
    text = update.message.text.strip().lower()

    state = pending_state.get(user_id, {})

    if text.replace(".", "", 1).isdigit():
        pending_state[user_id] = {"step": "await_category", "amount": text}
        keyboard = [[c] for c in CATEGORY_MAP.keys()]
        update.message.reply_text("Окей, тепер обери категорію:", reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True))
        return

    if state.get("step") == "await_category":
        category = text
        if category not in CATEGORY_MAP:
            keyboard = [[c] for c in CATEGORY_MAP.keys()]
            update.message.reply_text("Вибери категорію з кнопок:", reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True))
            return

        if CATEGORY_MAP[category]:
            pending_state[user_id] = {"step": "await_subcategory", "amount": state["amount"], "category": category}
            subcat_keyboard = [[s] for s in CATEGORY_MAP[category]]
            update.message.reply_text(f"'{category}' має підкатегорії. Обери одну:", reply_markup=ReplyKeyboardMarkup(subcat_keyboard, one_time_keyboard=True, resize_keyboard=True))
            return

        amount = float(state["amount"])
        if category != "прихід":
            amount *= -1

        limits_raw = limits_sheet.get_all_values()
        limits = {row[0]: float(row[1]) for row in limits_raw if len(row) >= 2}
        spent = get_spent_in_category_this_month(category)
        limit = limits.get(category)
        limit_msg = ""
        if limit and (spent + abs(amount)) > limit:
            limit_msg = f"⚠️ Перевищено ліміт {limit} грн у категорії '{category}' (вже витрачено: {spent + abs(amount):.2f} грн)"
            closing = "😬 Будь уважним(-ою) з витратами!"
        else:
            closing = "💪 Гарна робота!"

        sheet.append_row([datetime.now().strftime("%Y-%m-%d %H:%M"), user_name, amount, category, ""])
        update.message.reply_text(f"{limit_msg}\n💸 Зафіксував {abs(amount)} грн у *{category}*. {closing}", parse_mode="Markdown")
        pending_state.pop(user_id)
        return

    if state.get("step") == "await_subcategory":
        amount = float(state["amount"])
        if state["category"] != "прихід":
            amount *= -1

        limits_raw = limits_sheet.get_all_values()
        limits = {row[0]: float(row[1]) for row in limits_raw if len(row) >= 2}
        spent = get_spent_in_category_this_month(state["category"])
        limit = limits.get(state["category"])
        limit_msg = ""
        if limit and (spent + abs(amount)) > limit:
            limit_msg = f"⚠️ Перевищено ліміт {limit} грн у категорії '{state['category']}' (вже витрачено: {spent + abs(amount):.2f} грн)"
            closing = "😬 Будь уважним(-ою) з витратами!"
        else:
            closing = "💪 Гарна робота!"

        sheet.append_row([datetime.now().strftime("%Y-%m-%d %H:%M"), user_name, amount, state["category"], text])
        update.message.reply_text(f"{limit_msg}\n💸 Записав {abs(amount)} грн у *{state['category']} > {text}*. {closing}", parse_mode="Markdown")
        pending_state.pop(user_id)
        return

    update.message.reply_text("🧠 Напиши суму, наприклад '1000'")

def start(update: Update, context: CallbackContext):
    update.message.reply_text("👋 Привіт! Напиши суму, наприклад '1000'")

updater = Updater(os.environ["BOT_TOKEN"], use_context=True)
dp = updater.dispatcher
dp.add_handler(CommandHandler("start", start))
dp.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_message))
updater.start_polling()
print("✅ Бот працює")
updater.idle()
