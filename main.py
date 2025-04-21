from telegram.ext import Updater, MessageHandler, Filters
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import os
import json
import datetime
import random
import base64

# Завантажуємо змінні з оточення
bot_token = os.environ["BOT_TOKEN"]
spreadsheet_id = os.environ["SPREADSHEET_ID"]
google_creds_b64 = os.environ["GOOGLE_CREDS_B64"]

# Декодуємо base64 → JSON
google_creds_raw = base64.b64decode(google_creds_b64).decode("utf-8")
google_creds = json.loads(google_creds_raw)

# Підключення до Google Sheets
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_dict(google_creds, scope)
client = gspread.authorize(creds)
sheet = client.open_by_key(spreadsheet_id).sheet1

# Обробник повідомлень
def handle_message(update, context):
    text = update.message.text.strip()
    user = update.message.from_user.first_name
    date = datetime.datetime.now().strftime("%d.%m.%Y %H:%M")

    # Знаходимо суму (перше число в тексті)
    words = text.split()
    amount = None
    for word in words:
        if word.replace('.', '', 1).isdigit():
            amount = word
            break

    if not amount:
        update.message.reply_text("Не бачу суму. Напиши щось типу '100 продукти' або 'продукти 100'")
        return

    # Видаляємо суму і залишаємо категорію
    category_words = [w for w in words if w != amount]
    category = " ".join(category_words).strip().lower()

    if not category:
        update.message.reply_text("Не бачу категорію. Напиши щось типу '100 кава' або 'продукти 50'")
        return

    # Запис у таблицю
    sheet.append_row([date, user, amount, category])

    # Мемна відповідь
    reply_options = [
        f"💾 Записав {amount} грн у категорію '{category}'",
        f"Та легко! {amount} грн пішло в '{category}'",
        f"Гроші летять! {amount} грн → '{category}'",
        f"Фіксанув: {amount} на '{category}'. Тримайся, бюджет!",
        f"Це ти потратив {amount} на '{category}'? Бюджет не одобрює, але записав.",
        f"Бухгалтер спить, бот працює. {amount} грн на '{category}'"
    ]
    update.message.reply_text(random.choice(reply_options))

# Запуск бота
updater = Updater(bot_token, use_context=True)
dp = updater.dispatcher
dp.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_message))
updater.start_polling()
print("✅ Бот працює")
updater.idle()
