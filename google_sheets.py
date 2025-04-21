
import gspread
from oauth2client.service_account import ServiceAccountCredentials

def get_sheet(spreadsheet_id: str, credentials_path: str = "credentials.json"):
    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/drive"
    ]
    creds = ServiceAccountCredentials.from_json_keyfile_name(credentials_path, scope)
    client = gspread.authorize(creds)
    sheet = client.open_by_key(spreadsheet_id).sheet1
    return sheet

def append_expense(sheet, user: str, amount: str, category: str):
    sheet.append_row([user, amount, category])
