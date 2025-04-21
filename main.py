from telegram.ext import Updater, MessageHandler, Filters
import yaml
import gspread
import os
import json
import base64
from oauth2client.service_account import ServiceAccountCredentials

# Завантажуємо конфіг
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
    text = update.message.text
    user = update.message.from_user.first_name

    if text.replace(" ", "").isdigit():
        update.message.reply_text("Схоже, ти просто надіслав цифри 🤔 Спробуй '1000 продукти'")
        return

    try:
        amount, category = text.split(" ", 1)
        sheet.append_row([user, amount, category])
        update.message.reply_text(f"💾 Записав {amount} грн у категорію '{category}'_
