# src/config/settings.py
import os
from dotenv import load_dotenv

load_dotenv()

# Telegram settings
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
TELEGRAM_SALE_CHAT_ID = os.getenv('TELEGRAM_SALE_CHAT_ID') 
# Google Sheets settings
GOOGLE_SHEETS_CREDS = '/app/credentials/google-credentials.json'  # Docker path
GOOGLE_SHEETS_ID = os.getenv('GOOGLE_SHEETS_ID')

# Scraping Configuration
MAX_RETRIES = int(os.getenv('MAX_RETRIES', '3'))
WAIT_TIME = int(os.getenv('WAIT_TIME', '300'))
MAX_PAGES = int(os.getenv('MAX_PAGES', '2'))