
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext
import os
import json
import gspread
import base64
from datetime import datetime
from oauth2client.service_account import ServiceAccountCredentials

# Категорії
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

# Підключення до Google Sheets
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
google_creds_raw = base64.b64decode(os.environ["GOOGLE_CREDS_B64"]).decode("utf-8")
google_creds = json.loads(google_creds_raw)
creds = ServiceAccountCredentials.from_json_keyfile_dict(google_creds, scope)
client = gspread.authorize(creds)
sheet = client.open_by_key(os.environ["SPREADSHEET_ID"]).sheet1
limits_sheet = client.open_by_key(os.environ["SPREADSHEET_ID"]).worksheet("Ліміти")

pending_state = {}  # user_id: {step, amount, category}
report_state = {}
last_salary_date = {}

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
            amount = float(row[2])
            if amount < 0:
                total += abs(amount)
        except:
            continue
    return total

def send_report(update, start, end):
    rows = sheet.get_all_values()[1:]
    income = 0
    expenses = {}
    for row in rows:
        try:
            dt = datetime.strptime(row[0], "%Y-%m-%d %H:%M")
            if not (start <= dt <= end): continue
            amount = float(row[2])
            category = row[3]
            subcat = row[4] if len(row) > 4 else ""
            if category == "прихід":
                income += amount
            else:
                expenses.setdefault(category, {}).setdefault(subcat, 0)
                expenses[category][subcat] += amount
        except:
            continue

    result = f"📊 Звіт з {start.strftime('%Y-%m-%d')} по {end.strftime('%Y-%m-%d')}

"
    result += f"💰 Прихід: *{income:.2f} грн*

"
    total_exp = 0
    for cat, subcats in sorted(expenses.items(), key=lambda x: sum(x[1].values()), reverse=True):
        cat_total = sum(subcats.values())
        total_exp += abs(cat_total)
        result += f"*{cat}*: {abs(cat_total):.2f} грн
"
        for sub, val in subcats.items():
            if sub:
                result += f"  └ {sub}: {abs(val):.2f} грн
"
        result += "
"
    balance = income + sum(sum(v.values()) for v in expenses.values())
    result += f"📉 Баланс: *{balance:.2f} грн*"
    update.message.reply_text(result, parse_mode="Markdown")

def handle_message(update: Update, context: CallbackContext):
    user_id = update.message.from_user.id
    name = update.message.from_user.first_name
    text = update.message.text.lower().strip()

    if report_state.get(user_id) == "waiting_for_period":
        del report_state[user_id]
        now = datetime.now()
        if text == "з початку місяця":
            return send_report(update, now.replace(day=1), now)
        elif text == "від зп":
            if user_id in last_salary_date:
                return send_report(update, last_salary_date[user_id], now)
            update.message.reply_text("❌ Дата останньої ЗП невідома. Скористайся /salary")
            return
        elif text.startswith("від "):
            try:
                dt = datetime.strptime(text.replace("від ", ""), "%Y-%m-%d")
                return send_report(update, dt, now)
            except:
                update.message.reply_text("📅 Формат дати: від 2025-04-01")
                return

    state = pending_state.get(user_id, {})
    if state.get("step") == "await_category":
        cat = text
        if cat not in CATEGORY_MAP:
            keyboard = [[c] for c in CATEGORY_MAP.keys()]
            update.message.reply_text("Обери категорію:", reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True))
            return
        if CATEGORY_MAP[cat]:
            pending_state[user_id] = {"step": "await_subcategory", "amount": state["amount"], "category": cat}
            subs = [[s] for s in CATEGORY_MAP[cat]]
            update.message.reply_text(f"'{cat}' має підкатегорії. Обери:", reply_markup=ReplyKeyboardMarkup(subs, resize_keyboard=True, one_time_keyboard=True))
            return
        return save_transaction(update, name, float(state["amount"]), cat, "", user_id)

    if state.get("step") == "await_subcategory":
        return save_transaction(update, name, float(state["amount"]), state["category"], text, user_id)

    if text.replace(".", "", 1).isdigit():
        pending_state[user_id] = {"step": "await_category", "amount": text}
        keyboard = [[c] for c in CATEGORY_MAP.keys()]
        update.message.reply_text("Окей, тепер обери категорію:", reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True))
        return

    update.message.reply_text("🧠 Напиши суму або використай команду")

def save_transaction(update, user_name, amount, category, subcat, user_id):
    is_income = category == "прихід"
    value = amount if is_income else -amount
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    spent = get_spent_in_category_this_month(category)
    limits = {row[0]: float(row[1]) for row in limits_sheet.get_all_values() if len(row) >= 2}
    limit = limits.get(category)
    limit_msg, closing = "", "💪 Гарна робота!"

    if limit and not is_income and (spent + abs(value)) > limit:
        limit_msg = f"⚠️ Перевищено ліміт {limit} грн у категорії '{category}' (вже витрачено: {spent + abs(value):.2f} грн)
"
        closing = "😬 Будь уважним(-ою) з витратами!"

    sheet.append_row([now, user_name, value, category, subcat])
    pending_state.pop(user_id, None)

    if is_income:
        last_salary_date[user_id] = datetime.now()

    suffix = f"*{category}*" if not subcat else f"*{category} > {subcat}*"
    update.message.reply_text(f"{limit_msg}💸 Зафіксував {abs(value)} грн у {suffix}. {closing}", parse_mode="Markdown")

def report(update: Update, context: CallbackContext):
    user_id = update.message.from_user.id
    report_state[user_id] = "waiting_for_period"
    now = datetime.now().strftime("%Y-%m-%d")
    keyboard = [["з початку місяця"], ["від ЗП"], [f"від {now}"]]
    update.message.reply_text("За який період зробити звіт?", reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True))

def start(update: Update, context: CallbackContext):
    update.message.reply_text("👋 Привіт! Напиши суму, наприклад '1000' або натисни /report")

def ping(update: Update, context: CallbackContext):
    update.message.reply_text("✅ Я на зв'язку!")

def salary(update: Update, context: CallbackContext):
    user_id = update.message.from_user.id
    pending_state[user_id] = {"step": "await_category", "amount": "0"}
    update.message.reply_text("💼 Введи суму ЗП (запишемо як прихід):")

def setlimit(update: Update, context: CallbackContext):
    try:
        parts = update.message.text.split(" ", 2)
        category, value = parts[1], float(parts[2])
        limits_sheet.append_row([category, value])
        update.message.reply_text(f"✅ Ліміт {value} грн встановлено для категорії '{category}'")
    except:
        update.message.reply_text("⚠️ Формат: /setlimit <категорія> <сума>")

def main():
    updater = Updater(os.environ["BOT_TOKEN"], use_context=True)
    dp = updater.dispatcher
    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("ping", ping))
    dp.add_handler(CommandHandler("report", report))
    dp.add_handler(CommandHandler("salary", salary))
    dp.add_handler(CommandHandler("setlimit", setlimit))
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_message))
    updater.start_polling()
    updater.idle()

if __name__ == "__main__":
    main()
