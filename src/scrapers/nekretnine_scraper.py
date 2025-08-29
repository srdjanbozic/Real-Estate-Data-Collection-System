from selenium.webdriver.common.by import By
from selenium.common.exceptions import NoSuchElementException
from io import BytesIO
import requests
import time
from datetime import datetime
from typing import Set
import logging
from .base_scraper import BaseScraper, ProcessedLink, LISTINGS_PROCESSED, LISTINGS_SKIPPED, SCRAPING_ERRORS
from utils.telegram import TelegramNotifier
from database.session import get_db_session, SessionFactory
from html import escape

logger = logging.getLogger(__name__)

class NekretnineRSScraper(BaseScraper):
    def __init__(self, bot_token: str, chat_id: str):
        super().__init__(
            bot_token=bot_token,
            chat_id=chat_id,
            processed_links_path='data/processed_links/nekretnine_links.json'
        )
        self.telegram = TelegramNotifier(bot_token, chat_id)
        logger.info("NekretnineRSScraper initialized successfully")
        
    def get_page_url(self, page: int) -> str:
        if page == 1:
            return "https://www.nekretnine.rs/stambeni-objekti/stanovi/izdavanje-prodaja/izdavanje/grad/novi-sad/vlasnik/lista/po-stranici/10/?order=2"
        return f"https://www.nekretnine.rs/stambeni-objekti/stanovi/izdavanje-prodaja/izdavanje/grad/novi-sad/vlasnik/lista/po-stranici/10/stranica/{page}/?order=2"

    def get_page_listings(self):
        try:
            listings = self.driver.find_elements(By.CSS_SELECTOR, ".row.offer")
            logger.info(f"Found {len(listings)} listings")
            return listings
        except Exception as e:
            logger.error(f"Error finding listings: {e}")
            return []

    def extract_text_or_empty(self, element, selector, attribute=None):
        try:
            found = element.find_element(By.CSS_SELECTOR, selector)
            return found.get_attribute(attribute) if attribute else found.text.strip()
        except NoSuchElementException:
            return ""
        except Exception as e:
            logger.warning(f"Error extracting text: {e}")
            return ""

    def parse_price(self, price_text: str) -> float:
        try:
            # Extract numbers from price text
            cleaned_price = ''.join(filter(str.isdigit, price_text))
            return float(cleaned_price) if cleaned_price else 0.0
        except (ValueError, TypeError):
            return 0.0

    def extract_square_meters(self, details_text: str) -> int:
        try:
            if 'm²' in details_text or 'm2' in details_text:
                numbers = ''.join(filter(str.isdigit, details_text))
                return int(numbers) if numbers else 0
        except:
            pass
        return 0

    def process_listing(self, listing, processed_links: Set[ProcessedLink]) -> bool:
        db = get_db_session()
        try:
            # Extract title and link
            title_elem = listing.find_element(By.CSS_SELECTOR, '.offer-title a')
            title = escape(title_elem.text.strip())
            link = self.normalize_url(title_elem.get_attribute('href'))
            external_id = link.split('/')[-1] if link else 'unknown'
            
            # Check duplicates
            is_duplicate, existing = self.check_listing_exists(link, external_id)
            if is_duplicate or link in [pl.url for pl in processed_links]:
                LISTINGS_SKIPPED.inc()
                logger.info(f"Skipping duplicate: {link}")
                return True

            # Extract price
            price_text = self.extract_text_or_empty(listing, '.offer-price span') or "Cena nije navedena"
            price_display = f"💰 {price_text}"
            price = self.parse_price(price_text)

            # Extract location and meta info
            location = self.extract_text_or_empty(listing, '.offer-location')
            meta_info = self.extract_text_or_empty(listing, '.offer-meta-info')

            # Extract square meters
            meters_text = self.extract_text_or_empty(listing, '.offer-price--invert span')
            square_meters = self.extract_square_meters(meters_text)
            details = f"Kvadratura: {meters_text}" if meters_text else ""

            # Try to extract rooms info from title or details
            rooms = ''
            if any(x in title.lower() for x in ['jednosoban', 'dvosoban', 'trosoban', 'četvorosoban', 'garsonjera']):
                if 'jednosoban' in title.lower():
                    rooms = '1.0 soban'
                elif 'dvosoban' in title.lower():
                    rooms = '2.0 soban'
                elif 'trosoban' in title.lower():
                    rooms = '3.0 soban'
                elif 'četvorosoban' in title.lower():
                    rooms = '4.0 soban'
                elif 'garsonjera' in title.lower():
                    rooms = 'Garsonjera'

            # Extract image
            img_url = None
            listing_photo = None
            try:
                img = listing.find_element(By.CSS_SELECTOR, '.img-fluid')
                img_url = img.get_attribute('src')
                if img_url:
                    response = self.make_request(img_url)
                    if response and response.ok:
                        listing_photo = BytesIO(response.content)
                        listing_photo.name = 'image.jpg'
            except Exception as e:
                logger.warning(f"Image error: {e}")

            # Create owner data
            owner_data = {
                'name': "Nekretnine.rs Owner",
                'phone': '',
                'source': 'nekretnine.rs',
                'external_id': external_id
            }

            # Create listing data
            listing_data = {
                'source': 'nekretnine.rs',
                'external_id': external_id,
                'title': title,
                'price': price,
                'square_meters': square_meters,
                'rooms': rooms,
                'description': details,
                'location': location,
                'posted_date': datetime.now(),
                'processed_date': datetime.now(),
                'url': link,
                'status': 'active',
                'image_url': img_url
            }

            # Create Telegram message
            keyboard_markup = {
                'inline_keyboard': [[{
                    'text': '🔗 Pogledaj oglas',
                    'url': link
                }]]
            }

            caption = (
                f"<b>📋 {title}</b>\n\n"
                f"{price_display}\n"
                f"📍 {location}\n"
                f"📅 {meta_info}\n"
                f"🏠 {details}"
            )

            # Send to Telegram
            try:
                if listing_photo:
                    self.telegram.send_photo(listing_photo, caption, reply_markup=keyboard_markup)
                else:
                    self.telegram.send_message(caption, reply_markup=keyboard_markup)
                logger.info(f"Sent to Telegram: {title}")
            except Exception as e:
                logger.error(f"Telegram failed: {e}")

            # Save to database
            self.save_listing(listing_data, owner_data)
            
            # Update processed links
            processed_links.add(ProcessedLink(link))
            self.save_processed_links(processed_links)
            LISTINGS_PROCESSED.inc()
            logger.info(f"Successfully processed: {title}")
            return False
                
        except Exception as e:
            SCRAPING_ERRORS.inc()
            logger.error(f"Processing error: {e}")
            return False
        finally:
            try:
                db.close()
                SessionFactory.remove()
            except Exception as e:
                logger.error(f"Error cleaning up database session: {e}")

    def run(self):
        processed_links = self.load_processed_links()
        
        while True:
            try:
                with self.setup_driver() as driver:
                    self.driver = driver
                    logger.info(f"Starting scan cycle for {self.__class__.__name__}")
                    
                    for page in range(1, 3):
                        page_url = self.get_page_url(page)
                        logger.info(f"Processing page {page}: {page_url}")
                        
                        try:
                            self.driver.get(page_url)
                            if not self.verify_page_loaded():
                                break
                            
                            listings = self.get_page_listings()
                            if not listings:
                                break
                                
                            new_listings_count = 0
                            for listing in listings:
                                try:
                                    is_duplicate = self.process_listing(listing, processed_links)
                                    if not is_duplicate:
                                        new_listings_count += 1
                                    time.sleep(2)  # Rate limiting
                                except Exception as e:
                                    logger.error(f"Error processing listing: {e}")
                                    continue
                                
                            logger.info(f"Page {page}: {new_listings_count} new listings processed")
                            
                        except Exception as e:
                            logger.error(f"Page {page} error: {e}")
                            break

                    logger.info(f"Cycle complete. Waiting {self.wait_time}s")
                    time.sleep(self.wait_time)

            except Exception as e:
                logger.error(f"Critical error: {e}")
                time.sleep(60)