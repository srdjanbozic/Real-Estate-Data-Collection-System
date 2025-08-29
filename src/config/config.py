# src/config/config.py
import os
from dotenv import load_dotenv

load_dotenv()

# For Docker, use absolute path from container root
GOOGLE_SHEETS_CREDS = '/app/credentials/google-credentials.json'
GOOGLE_SHEETS_ID = os.getenv('GOOGLE_SHEETS_ID', 'your-sheet-id-here')