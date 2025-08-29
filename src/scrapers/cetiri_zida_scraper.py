from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from selenium.common.exceptions import NoSuchElementException, TimeoutException
from io import BytesIO
import requests
import time
from datetime import datetime
from typing import Set
import logging
from concurrent.futures import ThreadPoolExecutor
from .base_scraper import DB_CONNECTION_ERRORS, LISTINGS_PROCESSED, LISTINGS_SKIPPED, SCRAPING_ERRORS, BaseScraper, ProcessedLink
from utils.telegram import TelegramNotifier
from database.session import get_db_session, SessionFactory  
from html import escape
from typing import Tuple, Optional
from sqlalchemy import or_, and_
from database.models import Listing


logger = logging.getLogger(__name__)

class CetiriZidaScraper(BaseScraper):
    def __init__(self, bot_token: str, chat_id: str):
        super().__init__(
            bot_token=bot_token,
            chat_id=chat_id,
            processed_links_path='data/processed_links/4zida_links.json'
        )
        self.telegram = TelegramNotifier(bot_token, chat_id)
        logger.info("CetiriZidaScraper initialized successfully")
        
    def load_processed_links(self):
        """Load processed links with error handling"""
        try:
            return super().load_processed_links()
        except Exception as e:
            logger.warning(f"Error loading links, starting fresh: {e}")
            return set()
        
    def get_page_url(self, page: int) -> str:
        if page == 1:
            return "https://4zida.rs/izdavanje-stanova/gradske-lokacije-novi-sad/vlasnik?sortiranje=najnoviji"
        return f"https://4zida.rs/izdavanje-stanova/gradske-lokacije-novi-sad/vlasnik?sortiranje=najnoviji&strana={page}"

    def scroll_and_load_content(self):
        """Scroll through page to trigger lazy loading"""
        try:
            logger.info("Starting scroll to trigger lazy loading...")
            
            # Initial wait for page to load
            time.sleep(3)
            
            # Get initial page height
            last_height = self.driver.execute_script("return document.body.scrollHeight")
            
            scroll_attempts = 0
            max_scroll_attempts = 5
            
            while scroll_attempts < max_scroll_attempts:
                logger.info(f"Scroll attempt {scroll_attempts + 1}/{max_scroll_attempts}")
                
                # Scroll down in increments
                self.driver.execute_script("window.scrollTo(0, 1000);")
                time.sleep(2)
                self.driver.execute_script("window.scrollTo(0, 2000);")
                time.sleep(2)
                self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(3)
                
                # Check if new content loaded
                new_height = self.driver.execute_script("return document.body.scrollHeight")
                if new_height == last_height:
                    logger.info("No new content loaded, stopping scroll")
                    break
                    
                last_height = new_height
                scroll_attempts += 1
                
            logger.info("Scroll complete, checking for listings...")
            return True
            
        except Exception as e:
            logger.error(f"Error during scrolling: {e}")
            return False

    def get_page_listings(self):
        """Get listings after triggering lazy loading"""
        try:
            # First scroll to load content
            if not self.scroll_and_load_content():
                logger.warning("Failed to load content through scrolling")
                return []
            
            # Try multiple selectors for 4zida listings
            possible_selectors = [
                '[test-data="ad-search-card"]',      # Original
                '[data-testid="ad-search-card"]',    # Alternative
                '.search-results .card',             # Generic card
                '.listing-card',                     # Generic listing
                '.property-card',                    # Property card
                'div[class*="card"]',                # Any div with "card"
                'article',                           # Semantic article
                '.ad-item',                          # Ad item
                '[class*="listing"]',                # Any class with "listing"
                '[class*="property"]'                # Any class with "property"
            ]
            
            for selector in possible_selectors:
                try:
                    elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                    if elements and len(elements) > 2:  # Need at least a few elements
                        logger.info(f"✅ Found {len(elements)} listings with selector: {selector}")
                        
                        # Quick validation - check if elements contain property-like content
                        sample_element = elements[0]
                        sample_text = sample_element.text.lower() if sample_element.text else ""
                        
                        # Look for property indicators
                        property_indicators = ['€', 'din', 'eur', 'm²', 'm2', 'soban', 'stan', 'garsonjera']
                        if any(indicator in sample_text for indicator in property_indicators):
                            logger.info(f"✅ Elements contain property data, using selector: {selector}")
                            return elements
                        else:
                            logger.debug(f"Elements don't contain property data: {sample_text[:100]}")
                            
                except Exception as e:
                    logger.debug(f"Selector {selector} failed: {e}")
                    continue
            
            # If no good selectors found, log debug info
            logger.warning("No listings found with any selector")
            self.debug_page_content()
            return []
            
        except Exception as e:
            logger.error(f"Error in get_page_listings: {e}")
            return []

    def debug_page_content(self):
        """Debug page content when listings not found"""
        try:
            logger.info("=== 4ZIDA PAGE DEBUG ===")
            logger.info(f"URL: {self.driver.current_url}")
            logger.info(f"Title: {self.driver.title}")
            logger.info(f"Page source length: {len(self.driver.page_source)}")
            
            # Check for common elements
            body_text = self.driver.find_element(By.TAG_NAME, "body").text[:200] if self.driver.find_elements(By.TAG_NAME, "body") else "No body"
            logger.info(f"Body text start: {body_text}")
            
            # Look for any divs that might be listings
            all_divs = self.driver.find_elements(By.TAG_NAME, "div")
            logger.info(f"Total divs on page: {len(all_divs)}")
            
            # Check for potential listing containers
            potential_containers = []
            for div in all_divs[:50]:  # Check first 50 divs
                try:
                    class_attr = div.get_attribute("class") or ""
                    if any(word in class_attr.lower() for word in ['card', 'listing', 'property', 'ad']):
                        potential_containers.append(class_attr)
                except:
                    pass
                    
            if potential_containers:
                logger.info(f"Potential listing containers found: {potential_containers[:5]}")
            else:
                logger.warning("No potential listing containers found")
                
        except Exception as e:
            logger.error(f"Debug error: {e}")
        
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
                        Listing.source == '4zida.rs',
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
                SessionFactory.remove()
            except Exception as e:
                logger.error(f"Error cleaning up database session: {e}")

    def extract_text_or_empty(self, element, selector, attribute=None):
        try:
            found = element.find_element(By.CSS_SELECTOR, selector)
            return found.get_attribute(attribute) if attribute else found.text.strip()
        except NoSuchElementException:
            return ""
        except Exception as e:
            logger.warning(f"Error extracting text: {e}")
            return ""

    def parse_details(self, details_text: str) -> tuple:
        square_meters = 0
        rooms = ''
        
        if details_text:
            details_parts = details_text.split('•')
            for part in details_parts:
                part = part.strip()
                if 'm²' in part:
                    try:
                        square_meters = int(part.replace('m²', '').strip())
                    except ValueError:
                        pass
                elif any(x in part.lower() for x in ['soban', 'garsonjera']):
                    rooms = part

        return square_meters, rooms

    def extract_price(self, price_text: str) -> float:
        try:
            return float(''.join(filter(str.isdigit, price_text)))
        except (ValueError, TypeError) as e:
            logger.error(f"Price conversion error: {e}")
            return 0.0

    def process_listing(self, listing, processed_links: Set[ProcessedLink]) -> bool:
        db = get_db_session()
        try:
            logger.debug("Processing listing...")
            
            # Extract link with flexible selectors
            link_elem = None
            link_selectors = [
                'a[href*="/izdavanje-stanova/"]',
                'a[href*="4zida.rs"]',
                'a[href*="/ad/"]',
                'a[href]'
            ]
            
            for selector in link_selectors:
                try:
                    link_elem = listing.find_element(By.CSS_SELECTOR, selector)
                    break
                except NoSuchElementException:
                    continue
                    
            if not link_elem:
                logger.warning("No link found in listing")
                return False
                
            link = self.normalize_url(link_elem.get_attribute('href'))
            external_id = link.split('/')[-1] if link else 'unknown'
            
            logger.debug(f"Processing: {link}")
            
            # Check duplicates
            is_duplicate, existing = self.check_listing_exists(link, external_id)
            if is_duplicate or link in [pl.url for pl in processed_links]:
                LISTINGS_SKIPPED.inc()
                logger.info(f"Skipping duplicate: {link}")
                return True

            # Extract data with flexible selectors
            title = self.extract_listing_text(listing, [
                'p.truncate.font-medium',
                '.title',
                'h3',
                '[class*="title"]'
            ]) or "Bez naslova"
            
            price_text = self.extract_listing_text(listing, [
                'p.rounded-tl.bg-spotlight',
                '.price',
                '[class*="price"]'
            ]) or "0"
            
            location = self.extract_listing_text(listing, [
                'p.line-clamp-2',
                '.location',
                '[class*="location"]'
            ]) or "Nepoznata lokacija"
            
            details = self.extract_listing_text(listing, [
                'a.px-3.text-sm',
                '.details',
                '[class*="details"]'
            ]) or ""
            
            info = self.extract_listing_text(listing, [
                'div.flex-1.text-2xs',
                '.info',
                '.description'
            ]) or ""

            price = self.extract_price(price_text)
            square_meters, rooms = self.parse_details(details)

            # Handle image
            img_url = self.extract_image_url(listing)
            listing_photo = None
            if img_url:
                try:
                    response = self.make_request(img_url)
                    if response:
                        listing_photo = BytesIO(response.content)
                        listing_photo.name = 'image.jpg'
                except Exception as e:
                    logger.warning(f"Image error: {e}")

            # Prepare data
            owner_data = {
                'name': "4zida Owner",
                'phone': '',
                'source': '4zida.rs',
                'external_id': external_id
            }

            listing_data = {
                'source': '4zida.rs',
                'external_id': external_id,
                'title': title,
                'price': price,
                'square_meters': square_meters,
                'rooms': rooms,
                'description': info,
                'location': location,
                'posted_date': datetime.now(),
                'processed_date': datetime.now(),
                'url': link,
                'status': 'active',
                'image_url': img_url
            }

            # Prepare Telegram message
            caption = (
                f"<b>📋 {title}</b>\n\n"
                f"💰 Cena: {price} EUR\n"
                f"🏠 Detalji: {details}\n"
                f"📍 Lokacija: {location}\n"
                f"ℹ️ {info}"
            )
            
            keyboard_markup = {
                'inline_keyboard': [[{
                'text': '🔗 Pogledaj oglas',
                'url': link
            }]]
            }

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
                DB_CONNECTION_ERRORS.inc() 
                logger.error(f"Error cleaning up database session: {e}")

    def extract_listing_text(self, listing, selectors):
        """Try multiple selectors to extract text"""
        for selector in selectors:
            try:
                element = listing.find_element(By.CSS_SELECTOR, selector)
                text = element.text.strip()
                if text:
                    return escape(text)
            except:
                continue
        return None

    def extract_image_url(self, listing):
        """Extract image URL with multiple selectors"""
        img_selectors = [
            'img[alt*="4zida.rs"]',
            'img[src*="4zida"]',
            'img',
            '.image img'
        ]
        
        for selector in img_selectors:
            try:
                img = listing.find_element(By.CSS_SELECTOR, selector)
                img_url = img.get_attribute('src')
                if img_url:
                    return img_url.split('#')[0]
            except:
                continue
        return None
    
    def run(self):
        processed_links = self.load_processed_links()
        self.processed_links = processed_links
        
        while True:
            try:
                with self.setup_driver() as driver:
                    self.driver = driver
                    logger.info(f"Starting scan cycle for {self.__class__.__name__}")
                    
                    for page in range(1, 3):  # Test first 2 pages
                        page_url = self.get_page_url(page)
                        logger.info(f"Processing page {page}: {page_url}")
                        
                        try:
                            self.driver.get(page_url)
                            logger.info(f"Page loaded, starting content discovery...")
                            
                            listings = self.get_page_listings()
                            if not listings:
                                logger.warning(f"No listings found on page {page}")
                                break
                                
                            logger.info(f"Found {len(listings)} listings on page {page}")
                                
                            # Process listings
                            new_listings_count = 0
                            for i, listing in enumerate(listings):
                                logger.info(f"Processing listing {i+1}/{len(listings)}")
                                try:
                                    is_duplicate = self.process_listing(listing, self.processed_links)
                                    if not is_duplicate:
                                        new_listings_count += 1
                                except Exception as e:
                                    logger.error(f"Error processing listing {i+1}: {e}")
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