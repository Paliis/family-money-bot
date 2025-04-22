from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import Updater, MessageHandler, Filters, CallbackContext, CommandHandler
import os
import json
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime, timedelta
import base64

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

# Google Sheets
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
google_creds_raw = base64.b64decode(os.environ["GOOGLE_CREDS_B64"]).decode("utf-8")
google_creds = json.loads(google_creds_raw)
creds = ServiceAccountCredentials.from_json_keyfile_dict(google_creds, scope)
client = gspread.authorize(creds)
sheet = client.open_by_key(os.environ["SPREADSHEET_ID"]).sheet1
limits_sheet = client.open_by_key(os.environ["SPREADSHEET_ID"]).worksheet("Ліміти")

pending_state = {}  # user_id: {step, amount, category}
report_state = {}   # user_id: waiting_for_report_range

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

def send_report(update, start, end):
    rows = sheet.get_all_values()[1:]
    totals = {}
    incoming = 0
    for row in rows:
        try:
            dt = datetime.strptime(row[0], "%Y-%m-%d %H:%M")
            if not (start <= dt <= end):
                continue
            amount = float(row[2])
            category = row[3]
            subcat = row[4] if len(row) > 4 else ""

            if category == "прихід":
                incoming += amount
                continue

            key = (category, subcat)
            totals[key] = totals.get(key, 0) + amount
        except:
            continue

    result = f"📊 Звіт з {start.strftime('%Y-%m-%d')} по {end.strftime('%Y-%m-%d')}\n"
    result += f"\n💰 Прихід: *{incoming:.2f} грн*\n"
    categories = {}
    for (cat, subcat), amount in totals.items():
        categories.setdefault(cat, []).append((subcat, amount))

    for cat, items in sorted(categories.items(), key=lambda i: sum(x[1] for x in i[1]), reverse=True):
        total = sum(x[1] for x in items)
        result += f"\n*{cat}*: {abs(total):.2f} грн\n"
        for subcat, amount in items:
            if subcat:
                result += f"  - {subcat}: {abs(amount):.2f} грн\n"

    result += f"\n📉 Баланс: *{incoming + sum(sum(x[1] for x in v) for v in categories.values()):.2f} грн*"
    update.message.reply_text(result, parse_mode="Markdown")

def handle_message(update: Update, context: CallbackContext):
    user_id = update.message.from_user.id
    user_name = update.message.from_user.first_name
    text = update.message.text.strip().lower()

    if report_state.get(user_id) == "waiting_for_period":
        del report_state[user_id]
        if text == "з початку місяця":
            start = datetime.now().replace(day=1)
            return send_report(update, start, datetime.now())
        elif text == "від зп":
            update.message.reply_text("🔜 Команда додавання приходу в розробці")
            return
        elif text.startswith("від "):
            try:
                start = datetime.strptime(text.replace("від ", ""), "%Y-%m-%d")
                return send_report(update, start, datetime.now())
            except:
                update.message.reply_text("📅 Невірна дата. Формат: від 2025-04-01")
                return

    state = pending_state.get(user_id, {})

    if state.get("step") == "await_category":
        category = text
        if category not in CATEGORY_MAP:
            keyboard = [[c] for c in CATEGORY_MAP]
            update.message.reply_text("Вибери категорію з кнопок:", reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True))
            return
        if CATEGORY_MAP[category]:
            pending_state[user_id] = {"step": "await_subcategory", "amount": state["amount"], "category": category}
            subcats = [[s] for s in CATEGORY_MAP[category]]
            update.message.reply_text(f"'{category}' має підкатегорії. Обери одну:", reply_markup=ReplyKeyboardMarkup(subcats, one_time_keyboard=True, resize_keyboard=True))
            return

        amount = float(state["amount"])
        if category != "прихід":
            amount *= -1

        spent = get_spent_in_category_this_month(category)
        limits = {row[0]: float(row[1]) for row in limits_sheet.get_all_values() if len(row) > 1}
        limit = limits.get(category)
        if limit and (spent + abs(amount)) > limit:
            limit_msg = f"⚠️ Перевищено ліміт {limit} грн у категорії '{category}' (вже витрачено: {spent + abs(amount):.2f} грн)\n"
            closing = "😬 Будь уважним(-ою) з витратами!"
        else:
            limit_msg = ""
            closing = "💪 Гарна робота!"

        sheet.append_row([datetime.now().strftime("%Y-%m-%d %H:%M"), user_name, amount, category, ""])
        update.message.reply_text(f"{limit_msg}💸 Зафіксував {abs(amount)} грн у *{category}*. {closing}", parse_mode="Markdown")
        pending_state.pop(user_id)
        return

    if state.get("step") == "await_subcategory":
        amount = float(state["amount"])
        if state["category"] != "прихід":
            amount *= -1
        spent = get_spent_in_category_this_month(state["category"])
        limits = {row[0]: float(row[1]) for row in limits_sheet.get_all_values() if len(row) > 1}
        limit = limits.get(state["category"])
        if limit and (spent + abs(amount)) > limit:
            limit_msg = f"⚠️ Перевищено ліміт {limit} грн у категорії '{state['category']}' (вже витрачено: {spent + abs(amount):.2f} грн)\n"
            closing = "😬 Будь уважним(-ою) з витратами!"
        else:
            limit_msg = ""
            closing = "💪 Все за планом!"

        sheet.append_row([datetime.now().strftime("%Y-%m-%d %H:%M"), user_name, amount, state["category"], text])
        update.message.reply_text(f"{limit_msg}💸 Зафіксував {abs(amount)} грн у *{state['category']} > {text}*. {closing}", parse_mode="Markdown")
        pending_state.pop(user_id)
        return

    if text.replace(".", "", 1).isdigit():
        pending_state[user_id] = {"step": "await_category", "amount": text}
        keyboard = [[c] for c in CATEGORY_MAP]
        update.message.reply_text("Окей, тепер обери категорію:", reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True))
        return

    update.message.reply_text("🧠 Напиши суму, наприклад '1000'")

def report_command(update: Update, context: CallbackContext):
    user_id = update.message.from_user.id
    report_state[user_id] = "waiting_for_period"
    now = datetime.now()
    keyboard = [
        ["з початку місяця"],
        ["від ЗП"],
        [f"від {now.strftime('%Y-%m-%d')}"]
    ]
    update.message.reply_text("За який період зробити звіт?", reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True))

def start(update: Update, context: CallbackContext):
    update.message.reply_text("👋 Привіт! Напиши суму, наприклад '1000' або натисни /report")

def ping(update: Update, context: CallbackContext):
    update.message.reply_text("✅ Я на зв'язку!")

def main():
    updater = Updater(os.environ["BOT_TOKEN"], use_context=True)
    dp = updater.dispatcher
    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("report", report_command))
    dp.add_handler(CommandHandler("ping", ping))
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_message))
    updater.start_polling()
    updater.idle()

if __name__ == "__main__":
    main()
