from datetime import datetime
import time
from typing import Any, Dict, List, Optional
from venv import logger
from utils.sheets_helper import GoogleSheetsHelper
import logging
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

class SalesGoogleSheetsHelper(GoogleSheetsHelper):
    def __init__(self, credentials_path: str, spreadsheet_id: str):
        super().__init__(credentials_path, spreadsheet_id)
    
    def format_row(self, listing_data: Dict[str, Any]) -> List[str]:
        """
        Format sales listing data into a row for Google Sheets.
        
        Args:
            listing_data (dict): Dictionary containing sales listing information
            
        Returns:
            list: Formatted row of data with sales-specific fields
        """
        try:
            return [
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                str(listing_data.get('source', '')),
                str(listing_data.get('title', '')),
                f"{float(listing_data.get('price', 0)):.2f}",
                str(listing_data.get('square_meters', '')),
                str(listing_data.get('rooms', '')),
                str(listing_data.get('location', '')),
                str(listing_data.get('building_condition', '')),  # Sales-specific
                str(listing_data.get('floor_level', '')),         # Sales-specific
                str(listing_data.get('url', '')),
                str(listing_data.get('description', '')),
                str(listing_data.get('posted_date', datetime.now()).strftime("%Y-%m-%d %H:%M:%S")),
                'prodaja'  # Type marker
            ]
        except Exception as e:
            logger.error(f"Error formatting row: {e}")
            return []

    def append_listing(self, listing_data: Dict[str, Any], max_retries: int = 3) -> bool:
        """
        Append a sales listing to the Google Sheet.
        
        Args:
            listing_data (dict): Dictionary containing sales listing information
            max_retries (int): Maximum number of retry attempts
            
        Returns:
            bool: True if successful, False otherwise
        """
        for attempt in range(max_retries):
            try:
                # Format the row data
                row = self.format_row(listing_data)
                if not row:
                    return False

                body = {
                    'values': [row],
                    'majorDimension': 'ROWS'
                }
                
                # Execute the append request - note different sheet name
                result = self.service.spreadsheets().values().append(
                    spreadsheetId=self.spreadsheet_id,
                    range='Prodaja!A:M',  # Use 'Prodaja' tab with extended column range for sales data
                    valueInputOption='USER_ENTERED',
                    insertDataOption='INSERT_ROWS',
                    body=body
                ).execute()
                
                logger.info(f"Successfully appended sales listing: {listing_data.get('url', '')}")
                return True
                
            except HttpError as e:
                # Same error handling as parent class
                if e.resp.status in [429, 500, 503]:
                    if attempt < max_retries - 1:
                        delay = min(2 ** attempt, 60)
                        logger.warning(f"Sheets API error {e.resp.status}, retrying in {delay}s")
                        time.sleep(delay)
                        continue
                logger.error(f"Sheets API error: {e}")
                return False
                
            except Exception as e:
                if attempt < max_retries - 1:
                    logger.warning(f"Error appending sales listing, attempt {attempt + 1} of {max_retries}: {e}")
                    time.sleep(2 ** attempt)
                    continue
                logger.error(f"Failed to append sales listing to sheets: {e}")
                return False
        
        return False

    def get_all_listings(self) -> Optional[List[List[str]]]:
        """
        Get all sales listings from the sheet.
        
        Returns:
            Optional[List[List[str]]]: List of rows or None if failed
        """
        try:
            result = self.service.spreadsheets().values().get(
                spreadsheetId=self.spreadsheet_id,
                range='Prodaja!A:M'  # Use 'Prodaja' tab
            ).execute()
            return result.get('values', [])
        except Exception as e:
            logger.error(f"Failed to get sales listings: {e}")
            return None