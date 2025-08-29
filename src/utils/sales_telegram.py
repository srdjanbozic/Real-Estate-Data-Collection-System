from io import BytesIO
from typing import Dict, Optional
from utils.telegram import TelegramNotifier


class SalesTelegramNotifier(TelegramNotifier):
    def __init__(self, bot_token: str, chat_id: str):
        super().__init__(bot_token, chat_id)
    
    def send_photo(self, 
                  photo: BytesIO, 
                  caption: str, 
                  reply_markup: Optional[Dict] = None) -> Dict:
        """Send photo with sales-specific formatting"""
        # Customize caption for sales listings
        if caption.startswith("<b>📋"):
            # Replace the emoji and add "PRODAJA" prefix
            caption = caption.replace("<b>📋", "<b>🏡 PRODAJA:")
        
        return super().send_photo(photo, caption, reply_markup)

    def send_message(self, 
                    text: str, 
                    reply_markup: Optional[Dict] = None) -> Dict:
        """Send text message with sales-specific formatting"""
        # Customize text for sales listings
        if text.startswith("<b>📋"):
            # Replace the emoji and add "PRODAJA" prefix
            text = text.replace("<b>📋", "<b>🏡 PRODAJA:")
        
        return super().send_message(text, reply_markup)