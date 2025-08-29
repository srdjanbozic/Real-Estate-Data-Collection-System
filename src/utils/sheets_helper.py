from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import logging
from datetime import datetime
import time
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

class GoogleSheetsHelper:
    def __init__(self, credentials_path: str, spreadsheet_id: str):
        """
        Initialize Google Sheets helper with credentials and spreadsheet ID.
        
        Args:
            credentials_path (str): Path to service account credentials JSON file
            spreadsheet_id (str): Google Sheets spreadsheet ID
        """
        self.spreadsheet_id = spreadsheet_id
        self.scope = ['https://www.googleapis.com/auth/spreadsheets']
        
        try:
            # Initialize credentials
            self.creds = service_account.Credentials.from_service_account_file(
                credentials_path,
                scopes=self.scope
            )
            
            # Build service
            self.service = build('sheets', 'v4', credentials=self.creds)
            logger.info("Google Sheets service initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize Google Sheets: {e}")
            raise

    def format_row(self, listing_data: Dict[str, Any]) -> List[str]:
        """
        Format listing data into a row for Google Sheets.
        
        Args:
            listing_data (dict): Dictionary containing listing information
            
        Returns:
            list: Formatted row of data
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
                str(listing_data.get('url', '')),
                str(listing_data.get('description', '')),  # Optional description
                str(listing_data.get('posted_date', datetime.now()).strftime("%Y-%m-%d %H:%M:%S"))  # Posted date
            ]
        except Exception as e:
            logger.error(f"Error formatting row: {e}")
            return []

    def append_listing(self, listing_data: Dict[str, Any], max_retries: int = 3) -> bool:
        """
        Append a listing to the Google Sheet.
        
        Args:
            listing_data (dict): Dictionary containing listing information
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
                
                # Execute the append request
                result = self.service.spreadsheets().values().append(
                    spreadsheetId=self.spreadsheet_id,
                    range='Listings!A:J',  # Updated to include description and posted_date
                    valueInputOption='USER_ENTERED',
                    insertDataOption='INSERT_ROWS',
                    body=body
                ).execute()
                
                logger.info(f"Successfully appended listing: {listing_data.get('url', '')}")
                return True
                
            except HttpError as e:
                if e.resp.status in [429, 500, 503]:  # Rate limit or server error
                    if attempt < max_retries - 1:
                        delay = min(2 ** attempt, 60)  # Exponential backoff, max 60 seconds
                        logger.warning(f"Sheets API error {e.resp.status}, retrying in {delay}s")
                        time.sleep(delay)
                        continue
                logger.error(f"Sheets API error: {e}")
                return False
                
            except Exception as e:
                if attempt < max_retries - 1:
                    logger.warning(f"Error appending listing, attempt {attempt + 1} of {max_retries}: {e}")
                    time.sleep(2 ** attempt)
                    continue
                logger.error(f"Failed to append listing to sheets: {e}")
                return False
        
        return False

    def clear_sheet(self) -> bool:
        """
        Clear all data from the sheet except the header row.
        
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            self.service.spreadsheets().values().clear(
                spreadsheetId=self.spreadsheet_id,
                range='Listings!A2:J',  # Clear from row 2 onwards
                body={}
            ).execute()
            logger.info("Successfully cleared sheet")
            return True
        except Exception as e:
            logger.error(f"Failed to clear sheet: {e}")
            return False

    def get_all_listings(self) -> Optional[List[List[str]]]:
        """
        Get all listings from the sheet.
        
        Returns:
            Optional[List[List[str]]]: List of rows or None if failed
        """
        try:
            result = self.service.spreadsheets().values().get(
                spreadsheetId=self.spreadsheet_id,
                range='Listings!A:J'
            ).execute()
            return result.get('values', [])
        except Exception as e:
            logger.error(f"Failed to get listings: {e}")
            return None