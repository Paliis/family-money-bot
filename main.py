from telegram.ext import Updater, MessageHandler, Filters
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import os
import json
import datetime
import random
import base64

# Завантажуємо змінні
bot_token = os.environ["BOT_TOKEN"]
spreadsheet_id = os.environ["SPREADSHEET_ID"]
google_creds_b64 = os.environ["GOOGLE_CREDS_B64"]

# Декодуємо base64 → JSON
google_creds_raw = base64.b64decode(google_creds_b64).decode("utf-8")
google_creds = json.loads(google_creds_raw)

# Google Sheets
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_dict(google_creds, scope)
client = gspread.authorize(creds)
sheet = client.open_by_key(spreadsheet_id).sheet1

# Довідник категорій
category_tree = {
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
    "здоровье": ["бады", "врачи, лекарства", "психолог", "масаж"],
    "стрельба": ["патрони", "взноси", "запчасти"],
    "учеба": ["школа", "английский", "институт", "другое"],
    "такси": [],
    "донати": [],
    "квіти": [],
    "родителям": [],
    "техніка": []
}

# Плоский список усіх категорій і підкатегорій
all_terms = {}
for cat, subs in category_tree.items():
    all_terms[cat] = cat
    for sub in subs:
        all_terms[sub] = cat

# Обробник
def handle_message(update, context):
    text = update.message.text.strip().lower()
    user = update.message.from_user.first_name
    date = datetime.datetime.now().strftime("%d.%m.%Y %H:%M")

    # Знаходимо суму
    words = text.split()
    amount = None
    for word in words:
        if word.replace('.', '', 1).isdigit():
            amount = word
            break
    if not amount:
        update.message.reply_text("Не бачу суму. Напиши '100 продукти' або 'кофе 80'")
        return

    # Отримуємо категорію/підкатегорію
    category_words = [w for w in words if w != amount]
    found_category = None
    found_subcategory = None

    for word in category_words:
        if word in all_terms:
            found_category = all_terms[word]
            if word != found_category:
                found_subcategory = word
            break

    if not found_category:
        categories_list = ", ".join(category_tree.keys())
        update.message.reply_text(f"Не знаю категорію '{' '.join(category_words)}'. Напиши точніше або вибери з: {categories_list}")
        return

    # Запис у таблицю
    sheet.append_row([date, user, amount, found_category, found_subcategory or "—"])

    # Мемна відповідь
    reply_options = [
        f"💾 Заніс {amount} грн в '{found_category}'" + (f" / {found_subcategory}" if found_subcategory else ""),
        f"🧾 {amount} на '{found_category}' → збережено!",
        f"📌 Розбито по категоріях: {found_category}" + (f" → {found_subcategory}" if found_subcategory else ""),
        f"👛 {amount} грн — бюджет плаче, але все записано в '{found_category}'"
    ]
    update.message.reply_text(random.choice(reply_options))

# Запуск бота
updater = Updater(bot_token, use_context=True)
dp = updater.dispatcher
dp.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_message))
updater.start_polling()
print("✅ Бот працює")
updater.idle()
