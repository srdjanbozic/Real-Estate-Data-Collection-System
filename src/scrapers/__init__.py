# src/scrapers/__init__.py
from .base_scraper import BaseScraper, ProcessedLink, ACTIVE_SCRAPERS

# Active scrapers
from .oglasi_scraper import OglasiScraper
from .oglasi_sales_scraper import OglasiSalesScraper

# Portfolio scrapers - available but not running in production
from .cetiri_zida_scraper import CetiriZidaScraper
from .halooglasi_scraper import HaloOglasiScraper
from .nekretnine_scraper import NekretnineRSScraper
from .sasomange_scraper import SasoMangeScraper

# Only export active scrapers for main.py
__all__ = [
    'OglasiScraper', 
    'OglasiSalesScraper',
    'BaseScraper',
    'ProcessedLink', 
    'ACTIVE_SCRAPERS'
]

# Portfolio scrapers available for development/testing
__portfolio__ = [
    'CetiriZidaScraper',
    'HaloOglasiScraper', 
    'NekretnineRSScraper',
    'SasoMangeScraper'
]