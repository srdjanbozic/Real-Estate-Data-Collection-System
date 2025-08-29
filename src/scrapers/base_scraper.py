from abc import ABC, abstractmethod
import json
import time
from datetime import datetime, timedelta
import threading
from concurrent.futures import ThreadPoolExecutor
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException
from typing import Set, Optional
from pathlib import Path
import shutil
import os
import sys
import logging
from webdriver_manager.chrome import ChromeDriverManager
from database.session import get_db_session
from database.models import Listing, Owner, ListingHistory
from sqlalchemy import or_, and_
from utils.sheets_helper import GoogleSheetsHelper
from config import GOOGLE_SHEETS_CREDS, GOOGLE_SHEETS_ID
import requests
import ssl
from typing import Optional
from prometheus_client import Counter, Gauge, generate_latest, CONTENT_TYPE_LATEST
from http.server import HTTPServer, BaseHTTPRequestHandler

# Create necessary directories
os.makedirs('data/logs', exist_ok=True)
os.makedirs('data/processed_links', exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('data/logs/scraper.log', encoding='utf-8'),
        logging.StreamHandler(sys.stdout)  
    ]
)
logger = logging.getLogger(__name__)

# Metrics
LISTINGS_PROCESSED = Counter('listings_processed_total', 'Number of listings processed')
LISTINGS_SKIPPED = Counter('listings_skipped_total', 'Number of duplicate listings skipped')
DB_CONNECTION_ERRORS = Counter('db_connection_errors_total', 'Number of database connection errors')
CONNECTION_POOL_FULL = Counter('connection_pool_full_total', 'Number of times connection pool was full')
SCRAPING_ERRORS = Counter('scraping_errors_total', 'Number of scraping errors')
ACTIVE_SCRAPERS = Gauge('active_scrapers', 'Number of active scrapers')


class MetricsHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/metrics':
            self.send_response(200)
            self.send_header('Content-Type', CONTENT_TYPE_LATEST)
            self.end_headers()
            self.wfile.write(generate_latest())
        elif self.path == '/health':
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(b'{"status": "healthy"}')
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        # Suppress HTTP server logs
        pass


class ProcessedLink:
    def __init__(self, url: str, timestamp: datetime = None):
        self.url = url
        self.timestamp = timestamp or datetime.now()

    def to_dict(self):
        return {
            'url': self.url,
            'timestamp': self.timestamp.isoformat()
        }

    @staticmethod
    def from_dict(data):
        return ProcessedLink(
            data['url'],
            datetime.fromisoformat(data['timestamp'])
        )

    def __eq__(self, other):
        return self.url == other.url if isinstance(other, ProcessedLink) else self.url == other

    def __hash__(self):
        return hash(self.url)

class BaseScraper(ABC):
    _instance_lock = threading.Lock()
    _active_instances = set()
    _metrics_started = False

    def __init__(self, 
                 bot_token: str,
                 chat_id: str,
                 processed_links_path: str = 'data/processed_links',
                 wait_time: int = 300):
        self.bot_token = bot_token
        self.chat_id = chat_id
        logger.debug(f"Converting processed_links_path: {processed_links_path} (type: {type(processed_links_path)})")
        self.processed_links_path = Path(processed_links_path)
        logger.debug(f"After conversion: {self.processed_links_path} (type: {type(self.processed_links_path)})")
        self.wait_time = wait_time
        self.driver = None
        self.wait = None
        self.instance_id = id(self)
        self.sheets_helper = GoogleSheetsHelper(GOOGLE_SHEETS_CREDS, GOOGLE_SHEETS_ID)
        
        # Start metrics server only once
        with self._instance_lock:
            if not BaseScraper._metrics_started:
                try:
                    server = HTTPServer(('0.0.0.0', 8000), MetricsHandler)
                    thread = threading.Thread(target=server.serve_forever, daemon=True)
                    thread.start()
                    BaseScraper._metrics_started = True
                    logger.info("Prometheus metrics server with health endpoint started on port 8000")
                except Exception as e:
                    logger.error(f"Failed to start metrics server: {e}")
            self._active_instances.add(self.instance_id)
            ACTIVE_SCRAPERS.inc()  # Increment active scrapers count
        
        self.processed_links_path.parent.mkdir(parents=True, exist_ok=True)
        self._file_lock = threading.Lock()

        self.http_session = requests.Session()
        from requests.adapters import HTTPAdapter
        adapter = HTTPAdapter(pool_connections=10, pool_maxsize=20, max_retries=3)
        self.http_session.mount('http://', adapter)
        self.http_session.mount('https://', adapter)

    def __enter__(self):
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        try:
            if self.driver:
                self.driver.quit()
        except Exception as e:
            logger.error(f"Cleanup error: {e}")
        finally:
            with self._instance_lock:
                self._active_instances.discard(self.instance_id)

    def make_request(self, url: str, timeout: int = 10) -> Optional[requests.Response]:
        try:
            # Create a custom SSL context
            ssl_context = ssl.create_default_context()
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE
            
            # Use the custom context in requests
            response = self.http_session.get(
                url, 
                timeout=timeout,
                verify=False,  # Disable SSL verification
                stream=True
            )
            response.raise_for_status()
            return response
        except requests.exceptions.SSLError:
            logger.warning(f"SSL Error for URL: {url}")
            return None
        except Exception as e:
            logger.error(f"Request error: {e}")
            return None

    def clean_chromedriver(self):
        try:
            chrome_driver_path = os.path.join(os.path.expanduser('~'), '.wdm', 'drivers', 'chromedriver')
            if os.path.exists(chrome_driver_path):
                shutil.rmtree(chrome_driver_path, ignore_errors=True)
        except Exception as e:
            logger.warning(f"Could not clean ChromeDriver directory: {e}")

    def setup_driver(self) -> webdriver.Chrome:
        try:
            options = webdriver.ChromeOptions()
            
            # Headless and security settings
            options.add_argument('--headless=new')
            options.add_argument('--no-sandbox')
            options.add_argument('--disable-dev-shm-usage')
            options.add_argument('--disable-blink-features=AutomationControlled')
            options.add_experimental_option("excludeSwitches", ["enable-automation"])
            options.add_experimental_option('useAutomationExtension', False)
            
            # SSL handling
            options.add_argument('--ignore-certificate-errors')
            options.add_argument('--ignore-ssl-errors')
            options.add_argument('--allow-insecure-localhost')
            options.add_argument('--ssl-version-max=tls1.2')
            options.add_argument('--ssl-version-min=tls1')
            options.add_argument('--allow-running-insecure-content')
            options.add_argument('--disable-web-security')
            options.add_argument('--disable-aia-fetch')
            
            # Performance and detection avoidance
            options.add_argument('--disable-gpu')
            options.add_argument('--enable-unsafe-swiftshader')
            options.add_argument('--disable-notifications')
            options.add_argument('--disable-popup-blocking')
            options.add_argument('--start-maximized')
            options.add_argument('--disable-extensions')
            options.add_argument('--window-size=1920,1080')
            options.add_argument(f'--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
            
            service = Service(ChromeDriverManager().install())
            self.driver = webdriver.Chrome(service=service, options=options)
            
            # Evasion techniques
            self.driver.execute_cdp_cmd('Network.setUserAgentOverride', {
                "userAgent": 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            })
            
            self.driver.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {
                'source': '''
                    Object.defineProperty(navigator, 'webdriver', {
                        get: () => undefined
                    })
                '''
            })
            
            # Timeout configurations
            self.driver.set_page_load_timeout(30)
            self.driver.implicitly_wait(10)
            self.wait = WebDriverWait(self.driver, 15)
            
            return self.driver
            
        except WebDriverException as e:
            logger.error(f"Error setting up Chrome driver: {e}")
            raise

    def verify_page_loaded(self):
        try:
            self.wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, 'body')))
            body_text = self.driver.find_element(By.CSS_SELECTOR, 'body').text
            
            if not body_text:
                logger.warning("Page loaded but no content found")
                logger.debug(f"Page source: {self.driver.page_source[:500]}...")
                return False
                
            return True
        except Exception as e:
            logger.error(f"Error verifying page load: {e}")
            return False

    def normalize_url(self, url: str) -> str:
        return url.split('?')[0] if '?' in url else url

    def check_listing_exists(self, url: str, external_id: str) -> tuple[bool, Optional[Listing]]:
        db = get_db_session()
        try:
            existing = db.query(Listing).filter(
                or_(
                    Listing.url == url,
                    and_(
                        Listing.source == self.__class__.__name__.replace('Scraper', '').lower(),
                        Listing.external_id == external_id,
                        Listing.processed_date >= datetime.now() - timedelta(hours=24)
                    )
                )
            ).first()
            return bool(existing), existing
        except Exception as e:
            logger.error(f"Database check error: {e}")
            return False, None
        finally:
            db.close()

    def get_db_session(self):
        return get_db_session()

    def save_listing(self, listing_data: dict, owner_data: dict):
        db = get_db_session()
        try:
            # Check for existing listing
            is_duplicate, existing_listing = self.check_listing_exists(
                listing_data['url'], 
                listing_data['external_id']
            )

            if existing_listing:
                # Update existing listing if price changed
                if existing_listing.price != listing_data['price']:
                    history = ListingHistory(
                        listing_id=existing_listing.id,
                        price=existing_listing.price,
                        changed_date=datetime.now(),
                        change_type='price_change'
                    )
                    db.add(history)
                    for key, value in listing_data.items():
                        setattr(existing_listing, key, value)
                db.commit()
                logger.info(f"Updated listing: {listing_data['url']}")
                return

            # Handle owner
            owner = db.query(Owner).filter(
                Owner.source == owner_data['source'],
                Owner.external_id == owner_data['external_id']
            ).first()

            if not owner:
                owner = Owner(**owner_data)
                db.add(owner)
                db.flush()

            # Create new listing
            listing_data['owner_id'] = owner.id
            listing = Listing(**listing_data)
            db.add(listing)
            db.commit()
            
            # Google Sheets integration
            try:
                self.sheets_helper.append_listing(listing_data)
            except Exception as sheets_error:
                logger.error(f"Google Sheets error: {sheets_error}")

        except Exception as e:
            db.rollback()
            logger.error(f"Database error: {e}")
        finally:
            db.close()

    def load_processed_links(self) -> Set[ProcessedLink]:
        with self._file_lock:
            try:
                if not self.processed_links_path.exists():
                    return set()

                with open(self.processed_links_path, 'r') as f:
                    data = json.load(f)
                    links = {ProcessedLink.from_dict(item) for item in data}
                    cutoff = datetime.now() - timedelta(hours=24)
                    return {link for link in links if link.timestamp >= cutoff}
            except Exception as e:
                logger.error(f"Error loading links: {e}")
                return set()

    def save_processed_links(self, links: Set[ProcessedLink]) -> None:
        with self._file_lock:
            try:
                temp_path = self.processed_links_path.with_suffix('.tmp')
                with open(temp_path, 'w') as f:
                    json.dump([link.to_dict() for link in links], f)
                temp_path.replace(self.processed_links_path)
            except Exception as e:
                logger.error(f"Error saving links: {e}")

    @abstractmethod
    def get_page_url(self, page: int) -> str:
        pass

    @abstractmethod
    def get_page_listings(self):
        pass

    @abstractmethod
    def process_listing(self, listing, processed_links: Set[ProcessedLink]) -> bool:
        pass

    def run(self):
        processed_links = self.load_processed_links()
        
        while True:
            driver = None
            try:
                driver = self.setup_driver()
                self.driver = driver
                logger.info(f"Starting scan cycle for {self.__class__.__name__}")
                
                for page in range(1, 3):  # Limit to 3 pages for testing
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
                                lambda l: self.process_listing(l, processed_links),
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
            finally:
                if driver:
                    try:
                        driver.quit()
                    except:
                        pass