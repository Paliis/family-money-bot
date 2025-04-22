from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import Updater, MessageHandler, Filters, CallbackContext, CommandHandler
import os
import json
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime, timedelta
import base64

# ========== КАТЕГОРІЇ ==========
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

# ========== GOOGLE SHEETS ==========
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
google_creds_raw = base64.b64decode(os.environ["GOOGLE_CREDS_B64"]).decode("utf-8")
google_creds = json.loads(google_creds_raw)
creds = ServiceAccountCredentials.from_json_keyfile_dict(google_creds, scope)
client = gspread.authorize(creds)
sheet = client.open_by_key(os.environ["SPREADSHEET_ID"]).sheet1
limits_sheet = client.open_by_key(os.environ["SPREADSHEET_ID"]).worksheet("Ліміти")

# ========== СТАНИ ==========
pending_state = {}  # user_id: {step, amount, category}
report_state = {}   # user_id: waiting_for_report_range
salary_dates = {}   # user_id: datetime of last salary

# ========== ДОПОМОЖНІ ==========
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

    sorted_cats = sorted(categories.items(), key=lambda i: sum(x[1] for x in i[1]), reverse=True)
    for cat, items in sorted_cats:
        total = sum(x[1] for x in items)
        result += f"\n*{cat}*: {abs(total):.2f} грн\n"
        for subcat, amount in items:
            if subcat:
                result += f"  - {subcat}: {abs(amount):.2f} грн\n"

    net = incoming + sum(sum(x[1] for x in v) for v in categories.values())
    result += f"\n📉 Баланс: *{net:.2f} грн*"
    update.message.reply_text(result, parse_mode="Markdown")

# ========== ХЕНДЛЕРИ ==========
def handle_message(update: Update, context: CallbackContext):
    user_id = update.message.from_user.id
    user_name = update.message.from_user.first_name
    text = update.message.text.strip().lower()

    if report_state.get(user_id) == "waiting_for_period":
        del report_state[user_id]
        if text == "з початку місяця":
            return send_report(update, datetime.now().replace(day=1), datetime.now())
        elif text == "від зп":
            if user_id in salary_dates:
                return send_report(update, salary_dates[user_id], datetime.now())
            else:
                update.message.reply_text("🔔 Дата останньої ЗП не вказана. Використай /salary")
                return
        elif text.startswith("від "):
            try:
                start = datetime.strptime(text.replace("від ", ""), "%Y-%m-%d")
                return send_report(update, start, datetime.now())
            except:
                update.message.reply_text("📅 Формат: від 2025-04-01")
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

        return save_expense(update, user_name, user_id, float(state["amount"]), category, "")

    if state.get("step") == "await_subcategory":
        return save_expense(update, user_name, user_id, float(state["amount"]), state["category"], text)

    if text.replace(".", "", 1).isdigit():
        pending_state[user_id] = {"step": "await_category", "amount": text}
        keyboard = [[c] for c in CATEGORY_MAP]
        update.message.reply_text("Окей, тепер обери категорію:", reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True))
        return

    update.message.reply_text("🧠 Напиши суму, наприклад '1000'")

def save_expense(update, user_name, user_id, amount, category, subcat):
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

    sheet.append_row([datetime.now().strftime("%Y-%m-%d %H:%M"), user_name, amount, category, subcat])
    sub_info = f" > {subcat}" if subcat else ""
    update.message.reply_text(f"{limit_msg}💸 Зафіксував {abs(amount)} грн у *{category}{sub_info}*. {closing}", parse_mode="Markdown")
    pending_state.pop(user_id)

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

def salary_command(update: Update, context: CallbackContext):
    user_id = update.message.from_user.id
    user_name = update.message.from_user.first_name
    now = datetime.now()
    sheet.append_row([now.strftime("%Y-%m-%d %H:%M"), user_name, 0.01, "прихід", "зарплата"])
    salary_dates[user_id] = now
    update.message.reply_text("✅ ЗП збережена як прихід. Тепер можеш генерувати звіти від ЗП!")

def setlimit_command(update: Update, context: CallbackContext):
    text = update.message.text.replace("/setlimit", "").strip()
    try:
        category, value = text.split()
        value = float(value)
        limits_sheet.append_row([category, value])
        update.message.reply_text(f"📌 Ліміт {value:.0f} грн встановлено для '{category}'")
    except:
        update.message.reply_text("📌 Формат: /setlimit категорія сума\nПриклад: /setlimit продукти 7000")

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
    dp.add_handler(CommandHandler("salary", salary_command))
    dp.add_handler(CommandHandler("setlimit", setlimit_command))
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_message))
    updater.start_polling()
    updater.idle()

if __name__ == "__main__":
    main()
