from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import Updater, MessageHandler, Filters, CallbackContext, CommandHandler
import os
import json
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import base64
from collections import defaultdict

# --- Категорії ---
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
    "прихід": [],
    "розваги": [],
    "відпустка": [],
    "ремонт": []
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

# --- Команда /start ---
def start_handler(update: Update, context: CallbackContext):
    update.message.reply_text("👋 Привіт! Надішли суму витрат, і я допоможу її зафіксувати.")

# --- Команда /report ---
def report_handler(update: Update, context: CallbackContext):
    user_id = update.message.from_user.id
    report_state[user_id] = "waiting_for_period"
    keyboard = [["з початку місяця"], ["від ЗП"], ["від 2025-04-01"]]
    update.message.reply_text("За який період зробити звіт?", reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True))

# --- Формування звіту ---
def send_report(update, start, end):
    rows = sheet.get_all_values()[1:]
    data = []
    for row in rows:
        try:
            dt = datetime.strptime(row[0], "%Y-%m-%d %H:%M")
            if not (start <= dt <= end): continue
            user, amount, cat, subcat = row[1], float(row[2]), row[3], row[4] if len(row) > 4 else ""
            data.append((user, amount, cat, subcat))
        except: continue

    if not data:
        update.message.reply_text("❌ За цей період немає даних.", reply_markup=ReplyKeyboardRemove())
        return

    income = sum(d[1] for d in data if d[1] > 0)
    expenses = [d for d in data if d[1] < 0]

    grouped = defaultdict(lambda: defaultdict(float))
    for _, amount, cat, subcat in expenses:
        grouped[cat][subcat] += amount

    lines = [f"💰 Прихід: *{income:.2f} грн*\n"]
    total_exp = 0
    for cat, subcats in sorted(grouped.items(), key=lambda x: sum(x[1].values())):
        cat_total = sum(subcats.values())
        total_exp += cat_total
        lines.append(f"\n*{cat}*: *{-cat_total:.2f} грн*")
        for subcat, amt in subcats.items():
            if subcat:
                lines.append(f"  - {subcat}: {-amt:.2f} грн")

    balance = income + total_exp
    lines.append(f"\n📊 Підсумок: *{balance:.2f} грн*")

    update.message.reply_text("\n".join(lines), parse_mode="Markdown", reply_markup=ReplyKeyboardRemove())

# --- Повідомлення з сумою ---
def handle_message(update: Update, context: CallbackContext):
    user_id = update.message.from_user.id
    user_name = update.message.from_user.first_name
    text = update.message.text.strip().lower()

    if report_state.get(user_id) == "waiting_for_period":
        del report_state[user_id]
        if text == "з початку місяця":
            start = datetime.now().replace(day=1)
            end = datetime.now()
            return send_report(update, start, end)
        elif text == "від зп":
            update.message.reply_text("🔜 Команда додавання приходу в розробці")
            return
        elif text.startswith("від"):
            try:
                date_str = text.replace("від", "").strip()
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
            update.message.reply_text("Вибери категорію:", reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True))
            return
        if CATEGORY_MAP[category]:
            pending_state[user_id] = {"step": "await_subcategory", "amount": state["amount"], "category": category}
            subcat_keyboard = [[s] for s in CATEGORY_MAP[category]]
            update.message.reply_text("Обери підкатегорію:", reply_markup=ReplyKeyboardMarkup(subcat_keyboard, one_time_keyboard=True, resize_keyboard=True))
            return
        amount = float(state["amount"])
        if category != "прихід":
            amount *= -1
        sheet.append_row([datetime.now().strftime("%Y-%m-%d %H:%M"), user_name, amount, category, ""])
        update.message.reply_text(f"💾 Записав {abs(amount)} грн у {category}", reply_markup=ReplyKeyboardRemove())
        pending_state.pop(user_id)
        return

    if state.get("step") == "await_subcategory":
        amount = float(state["amount"])
        if state["category"] != "прихід":
            amount *= -1
        sheet.append_row([datetime.now().strftime("%Y-%m-%d %H:%M"), user_name, amount, state["category"], text])
        update.message.reply_text(f"💾 Записав {abs(amount)} грн у {state['category']} > {text}", reply_markup=ReplyKeyboardRemove())
        pending_state.pop(user_id)
        return

    if text.replace(".", "", 1).isdigit():
        pending_state[user_id] = {"step": "await_category", "amount": text}
        keyboard = [[c] for c in CATEGORY_MAP.keys()]
        update.message.reply_text("Окей, обери категорію:", reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True))
        return

    update.message.reply_text("🧠 Надішли суму у форматі: 100 або 250.5")

# --- Запуск ---
updater = Updater(os.environ["BOT_TOKEN"], use_context=True)
dp = updater.dispatcher
dp.add_handler(CommandHandler("start", start_handler))
dp.add_handler(CommandHandler("report", report_handler))
dp.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_message))

updater.start_polling()
print("✅ Бот працює")
updater.idle()
