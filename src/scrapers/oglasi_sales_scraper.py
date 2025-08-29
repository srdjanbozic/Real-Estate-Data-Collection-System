import certifi
import requests
from selenium.webdriver.common.by import By
from selenium.common.exceptions import NoSuchElementException
from typing import Set
import logging
from datetime import datetime
from io import BytesIO

import urllib3

from config.config import GOOGLE_SHEETS_CREDS, GOOGLE_SHEETS_ID
from utils.sales_sheets_helper import SalesGoogleSheetsHelper
from utils.sales_telegram import SalesTelegramNotifier
from .oglasi_scraper import OglasiScraper, ProcessedLink, LISTINGS_PROCESSED, LISTINGS_SKIPPED, SCRAPING_ERRORS, DB_CONNECTION_ERRORS

logger = logging.getLogger(__name__)

class OglasiSalesScraper(OglasiScraper):
    def __init__(self, bot_token: str, chat_id: str):
        super().__init__(
            bot_token=bot_token,
            chat_id=chat_id
        )
        # Override the processed_links_path to use a different file for sales
        self.processed_links_path = 'data/processed_links/oglasi_sales_links.json'
        self.telegram = SalesTelegramNotifier(bot_token, chat_id)
        self.sheets_helper = SalesGoogleSheetsHelper(GOOGLE_SHEETS_CREDS, GOOGLE_SHEETS_ID)
        self.processed_links = set()
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        self.session = requests.Session()
        self.session.verify = certifi.where()
        
    def get_page_url(self, page: int) -> str:
        """Override to use sales URLs instead of rentals"""
        if page == 1:
            return "https://www.oglasi.rs/nekretnine/prodaja-stanova/novi-sad?s=d&rt=vlasnik"
        return f"https://www.oglasi.rs/nekretnine/prodaja-stanova/novi-sad?s=d&rt=vlasnik&p={page}"

    def extract_building_condition(self, listing) -> str:
        """Extract the condition of the building (stanje objekta)"""
        try:
            condition_element = listing.find_element(By.CSS_SELECTOR, 'div.col-sm-6:nth-of-type(3) strong')
            return condition_element.text.strip()
        except Exception as e:
            logger.warning(f"Error extracting building condition: {e}")
            return ""

    def extract_floor_level(self, listing) -> str:
        """Extract the floor level (nivo u zgradi)"""
        try:
            level_element = listing.find_element(By.CSS_SELECTOR, 'div.col-sm-6:nth-of-type(4) strong')
            return level_element.text.strip()
        except Exception as e:
            logger.warning(f"Error extracting floor level: {e}")
            return ""

    def process_listing(self, listing, processed_links: Set[ProcessedLink]) -> bool:
        """Process a sales listing"""
        db = self.get_db_session()
        try:
            title_elem = listing.find_element(By.CSS_SELECTOR, '.fpogl-list-title')
            title = self.extract_text_or_empty(title_elem, 'h2')
            link = self.normalize_url(title_elem.get_attribute('href'))
            external_id = link.split('/')[-2]

            # Check if we've already processed this listing
            is_duplicate, existing = self.check_listing_exists(link, external_id)
            if is_duplicate:
                LISTINGS_SKIPPED.inc()
                logger.info(f"Skipping duplicate: {link}")
                return True

            # Extract the same data as for rentals
            price_text = self.extract_price(listing)
            price_display = f"💰 {price_text}"

            # Parse price - same logic as rentals
            try:
                if "EUR" in price_text:
                    cleaned_price = price_text.replace("EUR", "").replace(".", "").replace(",", ".").strip()
                    logger.debug(f"Original price: {price_text}, Cleaned: {cleaned_price}")
                    price = float(cleaned_price)
                else:
                    price = 0.0
            except ValueError as e:
                logger.warning(f"Price conversion error: {e} for text '{price_text}'")
                price = 0.0

            # Extract general details
            details = []
            detail_elements = listing.find_elements(By.CSS_SELECTOR, '.row .col-sm-6 strong')
            for detail in detail_elements:
                if detail.text.strip():
                    details.append(detail.text.strip())

            # Extract specific details for sales listings
            building_condition = self.extract_building_condition(listing)
            floor_level = self.extract_floor_level(listing)

            # Extract common details
            square_meters = 0
            rooms = ''
            for detail in details:
                if 'm2' in detail:
                    try:
                        square_meters = int(detail.replace('m2', '').strip())
                    except:
                        pass
                if 'soban' in detail or 'garsonjera' in detail:
                    rooms = detail

            location = self.extract_location_from_breadcrumbs(listing)
            description = self.extract_text_or_empty(listing, 'p[itemprop="description"]')
            posted_date = self.extract_posting_date(listing, visit_detail=False)

            # Extract image
            img_url = None
            listing_photo = None
            try:
                img_selectors = [
                    'img[itemprop="image"]',
                    'img.img-responsive',
                    '.carousel-item img',
                    '.listing-image img'
                ]
                
                for selector in img_selectors:
                    try:
                        img = listing.find_element(By.CSS_SELECTOR, selector)
                        img_url = img.get_attribute('src')
                        if img_url and 'no-image' not in img_url:
                            response = self.session.get(img_url, verify=certifi.where())
                            if response.ok:
                                listing_photo = BytesIO(response.content)
                                listing_photo.name = 'image.jpg'
                                break
                    except NoSuchElementException:
                        continue
            except Exception as e:
                logger.warning(f"Image error: {e}")

            # Create owner data
            owner_data = {
                'name': self.extract_text_or_empty(listing, 'cite') or "Unknown",
                'phone': '',
                'source': 'oglasi.rs',
                'external_id': external_id
            }

            # Create listing data for sales
            listing_data = {
                'source': 'oglasi.rs',
                'external_id': external_id,
                'title': title,
                'price': price,
                'square_meters': square_meters,
                'rooms': rooms,
                'description': description,
                'location': location,
                'posted_date': posted_date,
                'processed_date': datetime.now(),
                'url': link,
                'status': 'active',
                'image_url': img_url,
                'listing_type': 'sale',  # Mark as sale
                'building_condition': building_condition,  # Sale-specific field
                'floor_level': floor_level  # Sale-specific field
            }

            # Create Telegram message for sales listing
            keyboard_markup = {
                'inline_keyboard': [[{
                    'text': '🔗 Pogledaj oglas',
                    'url': link
                }]]
            }

            # Format with sales-specific details
            caption = (
                f"<b>🏡 PRODAJA: {title}</b>\n\n"
                f"{price_display}\n"
                f"🏠 Detalji: {' • '.join(details)}\n"
                f"📏 Površina: {square_meters} m²\n"
                f"🛏 Struktura: {rooms}\n"
                f"🏢 Stanje objekta: {building_condition}\n"  # Sale-specific
                f"🔝 Sprat: {floor_level}\n\n"  # Sale-specific
                f"📍 Lokacija: {location}\n"
                f"⏰ Objavljeno: {posted_date.strftime('%d.%m.%Y.')}"
            )

            # Send to Telegram
            try:
                if listing_photo:
                    self.telegram.send_photo(listing_photo, caption, reply_markup=keyboard_markup)
                else:
                    self.telegram.send_message(caption, reply_markup=keyboard_markup)
            except Exception as e:
                logger.error(f"Telegram failed: {e}")

            # Save to database
            self.save_listing(listing_data, owner_data)
            
            # Mark as processed
            processed_links.add(ProcessedLink(link))
            self.save_processed_links(processed_links)
            
            LISTINGS_PROCESSED.inc()
            return False

        except Exception as e:
            SCRAPING_ERRORS.inc()
            logger.error(f"Processing error: {e}")
            return False
        finally:
            try:
                db.close()
                from database.session import SessionFactory
                SessionFactory.remove()
            except Exception as e:
                DB_CONNECTION_ERRORS.inc()
                logger.error(f"Error cleaning up database session: {e}")