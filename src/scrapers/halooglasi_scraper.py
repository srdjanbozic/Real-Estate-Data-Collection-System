from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import NoSuchElementException, TimeoutException
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

class HaloOglasiScraper(BaseScraper):
    def __init__(self, bot_token: str, chat_id: str):
        super().__init__(
            bot_token=bot_token,
            chat_id=chat_id,
            processed_links_path='data/processed_links/halo_links.json'
        )
        self.telegram = TelegramNotifier(bot_token, chat_id)
        logger.info("HaloOglasiScraper initialized successfully")
        
    def get_page_url(self, page: int) -> str:
        if page == 1:
            return "https://www.halooglasi.com/nekretnine/izdavanje-stanova/novi-sad?oglasivac_nekretnine_id_l=387237"
        return f"https://www.halooglasi.com/nekretnine/izdavanje-stanova/novi-sad?oglasivac_nekretnine_id_l=387237&page={page}"

    def get_page_listings(self):
        try:
            self.wait.until(EC.presence_of_element_located(
                (By.CSS_SELECTOR, '.product-item')
            ))
            listings = self.driver.find_elements(By.CSS_SELECTOR, '.product-item')
            logger.info(f"Found {len(listings)} listings")
            return listings
        except TimeoutException:
            logger.warning("No listings found within timeout")
            return []
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

    def process_listing(self, listing, processed_links: Set[ProcessedLink]) -> bool:
        db = get_db_session()
        try:
            # Extract title and link
            title_elem = listing.find_element(By.CSS_SELECTOR, 'h3.product-title a')
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
            price_text = self.extract_text_or_empty(listing, 'div.central-feature span') or "Cena nije navedena"
            price_display = f"💰 {price_text}"
            
            # Parse price to float
            try:
                cleaned_price = ''.join(filter(str.isdigit, price_text))
                price = float(cleaned_price) if cleaned_price else 0.0
            except ValueError:
                price = 0.0

            # Extract location
            locations = listing.find_elements(By.CSS_SELECTOR, 'ul.subtitle-places li')
            location = ' » '.join([loc.text.strip() for loc in locations if loc.text.strip()])

            # Extract features
            features = listing.find_elements(By.CSS_SELECTOR, 'ul.product-features li')
            feature_texts = []
            square_meters = 0
            rooms = ''
            
            for feature in features:
                try:
                    value = feature.find_element(By.CSS_SELECTOR, '.value-wrapper').text
                    feature_texts.append(value.replace('\n', ' '))
                    
                    # Parse square meters and rooms
                    if 'm²' in value or 'm2' in value:
                        try:
                            square_meters = int(''.join(filter(str.isdigit, value)))
                        except:
                            pass
                    elif any(x in value.lower() for x in ['soban', 'garsonjera', 'jednosoban', 'dvosoban']):
                        rooms = value
                except:
                    continue
                    
            features_text = ' • '.join(feature_texts)

            # Extract description
            description = self.extract_text_or_empty(listing, 'p.text-description-list') or "Opis nije dostupan"

            # Extract posting date and owner info
            date_text = self.extract_text_or_empty(listing, 'span.publish-date')
            owner_type = self.extract_text_or_empty(listing, 'span.basic-info')

            # Extract image
            img_url = None
            listing_photo = None
            try:
                img = listing.find_element(By.CSS_SELECTOR, 'figure.pi-img-wrapper img')
                img_url = img.get_attribute('src')
                if img_url and 'no-image' not in img_url:
                    response = self.make_request(img_url)
                    if response and response.ok:
                        listing_photo = BytesIO(response.content)
                        listing_photo.name = 'image.jpg'
            except Exception as e:
                logger.warning(f"Image error: {e}")

            # Create owner data
            owner_data = {
                'name': owner_type or "HaloOglasi Owner",
                'phone': '',
                'source': 'halooglasi.rs',
                'external_id': external_id
            }

            # Create listing data
            listing_data = {
                'source': 'halooglasi.rs',
                'external_id': external_id,
                'title': title,
                'price': price,
                'square_meters': square_meters,
                'rooms': rooms,
                'description': description,
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
                f"🏠 {features_text}\n"
                f"📝 {description}\n\n"
                f"📅 {date_text}\n"
                f"👤 {owner_type}"
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