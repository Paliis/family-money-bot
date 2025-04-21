
from telegram.ext import Updater, MessageHandler, Filters
import yaml
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# Завантажуємо конфіг
import os
config = {
    "bot_token": os.environ["BOT_TOKEN"],
    "spreadsheet_id": os.environ["SPREADSHEET_ID"]
}

bot_token = config["bot_token"]
spreadsheet_id = config["spreadsheet_id"]

# Підключення до Google Sheets
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
import json

google_creds = json.loads(os.environ["GOOGLE_CREDS_JSON"].replace("\\n", "\n"))
creds = ServiceAccountCredentials.from_json_keyfile_dict(google_creds, scope)
client = gspread.authorize(creds)
sheet = client.open_by_key(spreadsheet_id).sheet1

# Обробник повідомлень
def handle_message(update, context):
    text = update.message.text
    chat_id = update.message.chat_id
    user = update.message.from_user.first_name

    if text.replace(" ", "").isdigit():
        update.message.reply_text("Схоже, ти просто надіслав цифри 🤔 Спробуй '1000 продукти'")
        return

    try:
        amount, category = text.split(" ", 1)
        sheet.append_row([user, amount, category])
        update.message.reply_text(f"💾 Записав {amount} грн у категорію '{category}'")
    except:
        update.message.reply_text("Не зміг розпізнати. Спробуй у форматі '1000 продукти'")

# Запуск бота
updater = Updater(bot_token, use_context=True)
dp = updater.dispatcher
dp.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_message))
updater.start_polling()
print("✅ Бот працює")
updater.idle()
