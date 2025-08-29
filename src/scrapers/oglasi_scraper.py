from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import NoSuchElementException, TimeoutException
from io import BytesIO
import requests
import time
from datetime import datetime, timedelta
from typing import Set, Optional, Tuple
import logging
from concurrent.futures import ThreadPoolExecutor
from .base_scraper import DB_CONNECTION_ERRORS, LISTINGS_PROCESSED, LISTINGS_SKIPPED, SCRAPING_ERRORS, BaseScraper, ProcessedLink
from utils.telegram import TelegramNotifier
from database.models import Listing, Owner
from database.session import get_db_session, SessionFactory  
from sqlalchemy import or_, and_
from html import escape
import random
import certifi
import urllib3

logger = logging.getLogger(__name__)

class OglasiScraper(BaseScraper):
    def __init__(self, bot_token: str, chat_id: str):
        super().__init__(
            bot_token=bot_token,
            chat_id=chat_id,
            processed_links_path='data/processed_links/oglasi_links.json'
        )
        self.telegram = TelegramNotifier(bot_token, chat_id)
        self.processed_links = set()

    def get_page_url(self, page: int) -> str:
        if page == 1:
            return "https://www.oglasi.rs/nekretnine/izdavanje-stanova/novi-sad?s=d&rt=vlasnik"
        return f"https://www.oglasi.rs/nekretnine/izdavanje-stanova/novi-sad?s=d&rt=vlasnik&p={page}"

    def check_listing_exists(self, link: str, external_id: str) -> Tuple[bool, Optional[Listing]]:
        if link in [pl.url for pl in self.processed_links]:
            logger.debug(f"Found in memory: {link}")
            return True, None

        db = get_db_session()
        try:
            existing = db.query(Listing).filter(
                or_(
                    Listing.url == link,
                    and_(
                        Listing.source == 'oglasi.rs',
                        Listing.external_id == external_id
                    )
                )
            ).first()
            
            if existing:
                logger.debug(f"Found in database: {link}")
                return True, existing
                
            return False, None
                
        except Exception as e:
            logger.error(f"Database check error: {e}")
            return False, None
        finally:
            try:
                db.close()
                SessionFactory.remove()  # Add this line
            except Exception as e:
                logger.error(f"Error cleaning up database session: {e}")

    def get_page_listings(self):
        try:
            self.wait.until(EC.presence_of_element_located(
                (By.CSS_SELECTOR, '.fpogl-holder, .single-item')
            ))
            listings = self.driver.find_elements(
                By.CSS_SELECTOR, '.fpogl-holder, .single-item'
            )
            logger.info(f"Found {len(listings)} listings")
            return listings
        except TimeoutException:
            logger.warning("No listings found within timeout")
            return []
        except Exception as e:
            logger.error(f"Error finding listings: {e}")
            return []

    def extract_price(self, listing) -> str:
        try:
            spans = listing.find_elements(By.CSS_SELECTOR, 'span.text-price strong')
            if spans:
                price_texts = [span.text for span in spans if span.text.strip()]
                if price_texts:
                    return price_texts[0]
                else:
                    return "Cena nije navedena"
            else:
                return "Cena nije navedena"
        except Exception as e:
            logger.warning(f"Error extracting price: {e}")
            return "Cena nije navedena"

    def extract_text_or_empty(self, element, selector, attribute=None):
        try:
            found = element.find_element(By.CSS_SELECTOR, selector)
            return found.get_attribute(attribute) if attribute else found.text.strip()
        except NoSuchElementException:
            return ""
        except Exception as e:
            logger.warning(f"Error extracting text: {e}")
            return ""

    def extract_posting_date(self, listing, visit_detail: bool = False) -> datetime:
        selectors = ['.visible-sm.time', '.date-published', '.listing-date', '.publish-date']
        for selector in selectors:
            try:
                date_element = listing.find_element(By.CSS_SELECTOR, selector)
                if date_element:
                    date_text = date_element.text.strip()
                    logger.debug(f"Found date text: {date_text}")
                    date_part = date_text.split('.')[0:3]
                    date_str = '.'.join(date_part)
                    return datetime.strptime(date_str, '%d.%m.%Y')
            except Exception as e:
                logger.debug(f"Selector {selector} failed: {e}")
                continue  # Probaj sledeći selector umesto return
        
        logger.warning("Could not extract posting date with any selector")
        return datetime.now()  # Samo ako svi selectors ne uspeju

    def extract_location_from_breadcrumbs(self, listing) -> str:
        try:
            breadcrumbs = listing.find_elements(By.CSS_SELECTOR, 'a[itemprop="category"]')
            if len(breadcrumbs) >= 4:
                return breadcrumbs[3].text.strip()
            return ""
        except Exception as e:
            logger.warning(f"Error extracting location: {e}")
            return ""

    def sync_processed_links(self):
        file_links = self.load_processed_links()
        self.processed_links.update(file_links)
        self.save_processed_links(self.processed_links)

    def process_listing(self, listing, processed_links: Set[ProcessedLink]) -> bool:
        db = get_db_session()
        try:
            title_elem = listing.find_element(By.CSS_SELECTOR, '.fpogl-list-title')
            title = escape(title_elem.find_element(By.CSS_SELECTOR, 'h2').text.strip())
            link = self.normalize_url(title_elem.get_attribute('href'))
            external_id = link.split('/')[-2]

            is_duplicate, existing = self.check_listing_exists(link, external_id)
            if is_duplicate:
                LISTINGS_SKIPPED.inc()
                logger.info(f"Skipping duplicate: {link}")
                return True

            price_text = self.extract_price(listing)
            price_display = f"💰 {price_text}"

            try:
                if "EUR" in price_text:
                    # Remove EUR, spaces, and replace comma with dot
                    cleaned_price = price_text.replace("EUR", "").replace(".", "").replace(",", ".").strip()
                    # Additional check for debugging
                    print(f"Original price: {price_text}, Cleaned: {cleaned_price}")
                    price = float(cleaned_price)
                else:
                    price = 0.0
            except ValueError as e:
                logger.warning(f"Price conversion error: {e} for text '{price_text}'")
                price = 0.0

            details = []
            detail_elements = listing.find_elements(By.CSS_SELECTOR, '.row .col-sm-6 strong')
            for detail in detail_elements:
                if detail.text.strip():
                    details.append(detail.text.strip())

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
                            response = self.make_request(img_url)
                            if response.ok:
                                listing_photo = BytesIO(response.content)
                                listing_photo.name = 'image.jpg'
                                break
                    except NoSuchElementException:
                        continue
            except Exception as e:
                logger.warning(f"Image error: {e}")

            owner_data = {
                'name': self.extract_text_or_empty(listing, 'cite') or "Unknown",
                'phone': '',
                'source': 'oglasi.rs',
                'external_id': external_id
            }

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
                'image_url': img_url
            }

            keyboard_markup = {
                'inline_keyboard': [[{
                    'text': '🔗 Pogledaj oglas',
                    'url': link
                }]]
            }

            caption = (
                f"<b>📋 {title}</b>\n\n"
                f"{price_display}\n"
                f"🏠 Detalji: {' • '.join(details)}\n"
                f"📏 Površina: {square_meters} m²\n"
                f"🛏 Struktura: {rooms}\n\n"
                f"📍 Lokacija: {location}\n"
                f"⏰ Objavljeno: {posted_date.strftime('%d.%m.%Y.')}"
            )

            try:
                if listing_photo:
                    self.telegram.send_photo(listing_photo, caption, reply_markup=keyboard_markup)
                else:
                    self.telegram.send_message(caption, reply_markup=keyboard_markup)
            except Exception as e:
                logger.error(f"Telegram failed: {e}")

            self.save_listing(listing_data, owner_data)
            
            processed_links.add(ProcessedLink(link))
            self.save_processed_links(processed_links)
            
            time.sleep(random.uniform(1, 3))
            LISTINGS_PROCESSED.inc()
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
                DB_CONNECTION_ERRORS.inc()
                logger.error(f"Error cleaning up database session: {e}")
    def run(self):
        processed_links = self.load_processed_links()
        self.processed_links = processed_links
        
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
                                
                            with ThreadPoolExecutor(max_workers=3) as executor:
                                results = list(executor.map(
                                    lambda l: self.process_listing(l, self.processed_links),
                                    listings
                                ))
                                
                            new_count = len([r for r in results if not r])
                            logger.info(f"Page {page}: {new_count} new listings")
                            
                        except Exception as e:
                            logger.error(f"Page {page} error: {e}")
                            break

                    logger.info(f"Cycle complete. Waiting {self.wait_time}s")
                    time.sleep(self.wait_time)

            except Exception as e:
                logger.error(f"Critical error: {e}")
                time.sleep(60)