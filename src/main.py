import sys
from pathlib import Path
import signal
import time
import logging
from concurrent.futures import ThreadPoolExecutor
import os
import threading
from scrapers.base_scraper import ACTIVE_SCRAPERS

# Add the src directory to the Python path
src_path = str(Path(__file__).parent)
if src_path not in sys.path:
    sys.path.append(src_path)

# Global flag for controlling scrapers
running = True
running_lock = threading.Lock()

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('scraper.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

def validate_environment():
    """Validate required environment variables are set"""
    required = ['TELEGRAM_BOT_TOKEN', 'DATABASE_URL', 'GOOGLE_SHEETS_ID']
    missing = [var for var in required if not os.getenv(var)]
    if missing:
        raise ValueError(f"Missing environment variables: {missing}")

def ensure_directories():
    """Ensure required directories exist"""
    try:
        data_dir = Path('data')
        processed_links_dir = data_dir / 'processed_links'
        
        data_dir.mkdir(exist_ok=True)
        processed_links_dir.mkdir(exist_ok=True)
        
        logger.info(f"Directories created: {processed_links_dir}")
    except Exception as e:
        logger.error(f"Directory creation error: {e}")
        raise

def initialize_database():
    """Initialize database tables"""
    try:
        from database.session import engine
        from database.models import Base
        
        Base.metadata.create_all(engine)
        logger.info("Database tables initialized successfully")
    except Exception as e:
        logger.error(f"Database initialization error: {e}")
        raise

def signal_handler(signum, frame):
    """Handle interrupt signal"""
    global running
    with running_lock:
        running = False
    logger.info("\nStopping scrapers gracefully... Please wait.")

def run_scraper(scraper_config):
    """Run scraper with interrupt checking"""
    scraper_class, bot_token, chat_id = scraper_config
    scraper = None
    try:
        logger.info(f"Starting {scraper_class.__name__}")
        scraper = scraper_class(bot_token, chat_id)
        
        while True:
            with running_lock:
                if not running:
                    break
                
            try:
                scraper.run()
            except Exception as e:
                logger.error(f"Error in {scraper_class.__name__}: {e}")
                time.sleep(90)  # Wait before retrying
            
            # Check running flag every 5 seconds
            for _ in range(12):  # 1 minute in 5-second increments
                with running_lock:
                    if not running:
                        return
                time.sleep(5)
    except Exception as e:
        logger.error(f"Critical error in {scraper_class.__name__}: {e}")
    finally:
        if scraper:
            try:
                scraper.__exit__(None, None, None)
            except Exception as e:
                logger.error(f"Error cleaning up {scraper_class.__name__}: {e}")

def main():
    try:
        # Ensure directories exist first
        ensure_directories()
        
        # Validate environment variables
        validate_environment()

        # Initialize database
        initialize_database()
        
        
        # Import scrapers after ensuring directories
        from scrapers import (
            OglasiScraper,
            OglasiSalesScraper
        )
        from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, TELEGRAM_SALE_CHAT_ID

        # Set up signal handlers
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

        # List of scraper configurations
        scrapers = [
            (OglasiScraper, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID),
            (OglasiSalesScraper, TELEGRAM_BOT_TOKEN, TELEGRAM_SALE_CHAT_ID)
        ]
        ACTIVE_SCRAPERS.set(len(scrapers))

        logger.info(f"Starting {len(scrapers)} scrapers")

        # Use ThreadPoolExecutor for better thread management
        with ThreadPoolExecutor(max_workers=len(scrapers)) as executor:
            futures = [executor.submit(run_scraper, scraper_config) for scraper_config in scrapers]

            try:
                # Wait for all futures to complete or until interrupted
                for future in futures:
                    future.result()
            except KeyboardInterrupt:
                logger.info("\nReceived keyboard interrupt. Stopping scrapers...")
                global running
                running = False
                executor.shutdown(wait=True)

        logger.info("All scrapers stopped.")

    except Exception as e:
        logger.error(f"Main process error: {e}")
        raise
    finally:
        try:
            from database.session import engine
            engine.dispose()
        except Exception as e:
            logger.error(f"Error disposing engine: {e}")

if __name__ == "__main__":
    main()