from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import Updater, MessageHandler, Filters, CallbackContext, CommandHandler
import os
import json
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime, timedelta
import base64
from collections import defaultdict

# --- Категорії та підкатегорії ---
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

# --- Google Sheets ---
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
google_creds_raw = base64.b64decode(os.environ["GOOGLE_CREDS_B64"]).decode("utf-8")
google_creds = json.loads(google_creds_raw)
creds = ServiceAccountCredentials.from_json_keyfile_dict(google_creds, scope)
client = gspread.authorize(creds)
sheet = client.open_by_key(os.environ["SPREADSHEET_ID"]).sheet1

pending_state = {}  # user_id: {step, amount, category}
report_state = {}   # user_id: waiting_for_report_range

# --- Обробник витрат ---
def handle_message(update: Update, context: CallbackContext):
    user_id = update.message.from_user.id
    user_name = update.message.from_user.first_name
    text = update.message.text.strip().lower()

    # --- Обробка вибору звіту ---
    if report_state.get(user_id) == "waiting_for_period":
        del report_state[user_id]
        if text == "з початку місяця":
            start = datetime.now().replace(day=1)
            end = datetime.now()
            return send_report(update, start, end)
        elif text == "від зп":
            update.message.reply_text("🔜 Команда додавання приходу в розробці")
            return
        elif text.startswith("від "):
            try:
                date_str = text.replace("від ", "")
                start = datetime.strptime(date_str, "%Y-%m-%d")
                end = datetime.now()
                return send_report(update, start, end)
            except:
                update.message.reply_text("📅 Невірна дата. Формат: від 2025-04-01")
                return

    state = pending_state.get(user_id, {})

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
            amount *= -1  # витрата

        sheet.append_row([datetime.now().strftime("%Y-%m-%d %H:%M"), user_name, amount, category, ""])
        update.message.reply_text(f"📂 {abs(amount)} грн записано в '{category}'")
        pending_state.pop(user_id)
        return

    if state.get("step") == "await_subcategory":
        amount = float(state["amount"])
        if state["category"] != "прихід":
            amount *= -1

        sheet.append_row([datetime.now().strftime("%Y-%m-%d %H:%M"), user_name, amount, state["category"], text])
        update.message.reply_text(f"📂 {abs(amount)} грн записано в '{state['category']} > {text}'")
        pending_state.pop(user_id)
        return

    # Якщо повідомлення тільки число — чекаємо категорію
    if text.replace(".", "", 1).isdigit():
        pending_state[user_id] = {"step": "await_category", "amount": text}
        keyboard = [[c] for c in CATEGORY_MAP.keys()]
        update.message.reply_text("Окей, тепер обери категорію:", reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True))
        return

    update.message.reply_text("🧠 Напиши суму, наприклад '1000'")

# --- Команда /report ---
def report_command(update: Update, context: CallbackContext):
    user_id = update.message.from_user.id
    report_state[user_id] = "waiting_for_period"
    keyboard = [["З початку місяця"], ["Від ЗП"], ["Від 2025-04-01"]]
    update.message.reply_text("📅 Обери період звіту:", reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True))

# --- Надсилання звіту ---
def send_report(update, start_date, end_date):
    rows = sheet.get_all_values()[1:]  # Пропускаємо заголовок
    summary = defaultdict(float)
    total = 0

    for row in rows:
        if len(row) < 5:
            continue
        try:
            timestamp = datetime.strptime(row[0], "%Y-%m-%d %H:%M")
        except ValueError:
            continue

        if not (start_date <= timestamp <= end_date):
            continue

        user, amount, category, subcat = row[1], row[2], row[3], row[4]
        try:
            amount_val = float(amount)
        except ValueError:
            continue

        key = f"{category} > {subcat}" if subcat else category
        summary[key] += amount_val
        total += amount_val

    if not summary:
        update.message.reply_text("За обраний період не знайдено витрат", reply_markup=ReplyKeyboardRemove())
        return

    lines = [f"📊 Звіт з {start_date.strftime('%Y-%m-%d')} по {end_date.strftime('%Y-%m-%d')}", f"Загалом: {total:.2f} грн"]
    for cat, amt in sorted(summary.items(), key=lambda x: -x[1]):
        lines.append(f"• {cat}: {amt:.2f} грн")

    update.message.reply_text("\n".join(lines), reply_markup=ReplyKeyboardRemove())

# --- Запуск ---
updater = Updater(os.environ["BOT_TOKEN"], use_context=True)
dp = updater.dispatcher
dp.add_handler(CommandHandler("report", report_command))
dp.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_message))
updater.start_polling()
print("✅ FamilyMoneyBot працює")
updater.idle()
