from io import BytesIO
import requests
import json
import time
import logging
from typing import Dict, Optional, Union

logger = logging.getLogger(__name__)

class TelegramNotifier:
    def __init__(self, bot_token: str, chat_id: str):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.base_url = f"https://api.telegram.org/bot{self.bot_token}"
        self.max_retries = 3
        self.timeout = 30

    def _make_request(self, 
                     endpoint: str, 
                     payload: Dict, 
                     files: Optional[Dict] = None) -> Dict:
        """Make request to Telegram API with retry logic"""
        url = f"{self.base_url}/{endpoint}"

        for attempt in range(self.max_retries):
            try:
                if files:
                    response = requests.post(url, 
                                          data=payload, 
                                          files=files, 
                                          timeout=self.timeout)
                else:
                    response = requests.post(url, 
                                          json=payload, 
                                          timeout=self.timeout)
                
                response.raise_for_status()
                return response.json()

            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 429:  # Too many requests
                    retry_after = int(e.response.headers.get('Retry-After', 10))
                    logger.warning(f"Rate limited. Retrying after {retry_after} seconds...")
                    time.sleep(retry_after)
                    continue
                logger.error(f"HTTP error during {endpoint}: {e}")
                return {"ok": False, "error": str(e)}

            except Exception as e:
                logger.error(f"Error during {endpoint}: {e}")
                if attempt < self.max_retries - 1:
                    time.sleep(2 ** attempt)  # Exponential backoff
                    continue
                return {"ok": False, "error": str(e)}

        return {"ok": False, "error": "Max retries exceeded"}

    def send_photo(self, 
                  photo: BytesIO, 
                  caption: str, 
                  reply_markup: Optional[Dict] = None) -> Dict:
        """Send photo with caption and optional inline keyboard"""
        payload = {
            'chat_id': self.chat_id,
            'caption': caption,
            'parse_mode': 'HTML'
        }

        if reply_markup:
            payload['reply_markup'] = json.dumps(reply_markup)

        files = {'photo': photo}
        return self._make_request('sendPhoto', payload, files)

    def send_message(self, 
                    text: str, 
                    reply_markup: Optional[Dict] = None) -> Dict:
        """Send text message with optional inline keyboard"""
        payload = {
            'chat_id': self.chat_id,
            'text': text,
            'parse_mode': 'HTML'
        }
        
        if reply_markup:
            payload['reply_markup'] = json.dumps(reply_markup)
        
        return self._make_request('sendMessage', payload)