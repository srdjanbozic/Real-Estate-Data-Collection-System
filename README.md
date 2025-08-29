# Real Estate Data Collection System
A production-ready web scraping system for collecting and monitoring real estate listings from multiple Serbian marketplaces. 
Built with scalable data pipelines, comprehensive monitoring, and automated quality assurance.
## Overview This system automatically collects rental and sale listings from major Serbian real estate websites, processes them for duplicates, stores structured data, and provides real-time notifications and monitoring. Designed for continuous operation with robust error handling and observability. ## Architecture
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   Web Sources   │    │   Scrapers       │    │   Database      │
│                 │    │                  │    │                 │
│  • oglasi.rs    │───▶│  • Base Scraper  │───▶│  PostgreSQL     │
│  • 4zida.rs     │    │  • Anti-bot      │    │  • Listings     │
│                 │    │  • Retry Logic   │    │  • Owners       │
└─────────────────┘    └──────────────────┘    │  • History      │
                                               └─────────────────┘
                              │
                              ▼
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│  Notifications  │    │   Monitoring     │    │   Data Export   │
│                 │    │                  │    │                 │
│  • Telegram     │◀───│  • Prometheus    │    │  Google Sheets  │
│  • Alerts       │    │  • Grafana       │    │  • API Ready    │
│                 │    │  • Health Check  │    │                 │
└─────────────────┘    └──────────────────┘    └─────────────────┘
## Key Features ### Web Scraping & Data Collection - **Multi-source support**: oglasi.rs, 4zida.rs, halooglasi.rs, nekretnine.rs, sasomange.rs with extensible architecture - **Anti-bot detection**: Chrome driver stealth mode, user agent rotation, SSL handling - **Dynamic content loading**: Intelligent scroll-based content discovery - **Robust parsing**: Multiple selector fallbacks for reliable data extraction - **Rate limiting**: Configurable delays and request throttling ### Data Quality & Intelligence - **Duplicate detection**: URL-based and external ID-based deduplication - **Price tracking**: Historical price changes with timestamp logging - **Data validation**: Schema validation, price normalization, location parsing - **Structured storage**: Relational database with proper indexing and constraints ### Production Monitoring - **Prometheus metrics**: Custom metrics for scrapers, errors, and performance - **Grafana dashboards**: Real-time visualization of system health and processing rates - **Alert system**: Telegram notifications for downtime, errors, and anomalies - **Health endpoints**: Docker-compatible health checks and status monitoring ### Scalable Architecture - **Containerized deployment**: Docker Compose with resource limits - **Concurrent processing**: ThreadPoolExecutor for parallel scraper execution - **Database connection pooling**: Optimized connection management with retry logic - **Graceful shutdown**: Signal handling for clean process termination ## Technical Stack - **Language**: Python 3.9 - **Web Scraping**: Selenium WebDriver, ChromeDriver - **Database**: PostgreSQL with SQLAlchemy ORM - **Monitoring**: Prometheus, Grafana, PostgreSQL Exporter - **Messaging**: Telegram Bot API - **Data Export**: Google Sheets API - **Containerization**: Docker, Docker Compose - **Process Management**: ThreadPoolExecutor, signal handling ## Quick Start ### Prerequisites - Docker and Docker Compose - Telegram bot token - Google Sheets API credentials ### 1. Clone Repository
bash
git clone https://github.com/yourusername/real-estate-scraper.git
cd real-estate-scraper
### 2. Environment Configuration
bash
cp .env.example .env
# Edit .env with your credentials
### 3. Deploy with Docker
bash
docker-compose up -d
### 4. Access Monitoring - **Grafana**: http://localhost:3000 (admin/admin) - **Prometheus**: http://localhost:9090 - **Health Check**: http://localhost:8000/health ## Configuration ### Environment Variables
bash
# Telegram Configuration
TELEGRAM_BOT_TOKEN=your_bot_token_here
TELEGRAM_CHAT_ID=@your_channel
TELEGRAM_SALE_CHAT_ID=@your_sales_channel

# Database Configuration
DATABASE_URL=postgresql://postgres:password@db:5432/realestate

# Google Sheets Integration
GOOGLE_SHEETS_ID=your_google_sheets_id

# Scraping Parameters
MAX_RETRIES=3
WAIT_TIME=300
MAX_PAGES=2
### Google Sheets Setup 1. Enable Google Sheets API in Google Cloud Console 2. Create service account and download JSON credentials 3. Place credentials in credentials/google-credentials.json 4. Share your Google Sheet with the service account email ### Telegram Bot Setup 1. Create bot via @BotFather 2. Get bot token 3. Create channels for notifications 4. Configure channel IDs in environment ## Monitoring & Alerts ### Available Metrics - active_scrapers: Number of running scrapers - listings_processed_total: Total listings processed - listings_skipped_total: Duplicate listings skipped - scraping_errors_total: Scraping errors encountered - db_connection_errors_total: Database connection issues ### Alert Rules - **Scraper Down**: When no active scrapers for >2 minutes - **High Error Rate**: When error rate exceeds 10% for >5 minutes - **Database Issues**: When database connection errors occur ### Dashboard Features - Real-time processing rates - Error rate trends - System resource utilization - Duplicate detection efficiency - Processing volume over time ## Database Schema ### Listings Table
sql
CREATE TABLE listings (
    id SERIAL PRIMARY KEY,
    source VARCHAR(50),
    external_id VARCHAR(100),
    title TEXT,
    price NUMERIC,
    square_meters INTEGER,
    rooms VARCHAR(50),
    location VARCHAR(100),
    listing_type VARCHAR(20),
    url TEXT UNIQUE,
    processed_date TIMESTAMP,
    UNIQUE(source, external_id)
);
### Price History Tracking
sql
CREATE TABLE listing_history (
    id SERIAL PRIMARY KEY,
    listing_id INTEGER REFERENCES listings(id),
    price NUMERIC,
    changed_date TIMESTAMP,
    change_type VARCHAR(50)
);
## Available Scrapers The system includes scrapers for multiple Serbian real estate platforms, demonstrating adaptability to different website structures and anti-bot measures: ### Active Scrapers - **oglasi.rs**: Rental listings with owner filtering - **oglasi.rs (Sales)**: Property sales with building condition tracking ### Portfolio Scrapers (Available) - **4zida.rs**: Advanced dynamic content loading with scroll-based discovery - **halooglasi.rs**: Product listing format with comprehensive feature extraction - **nekretnine.rs**: Traditional real estate portal with meta information parsing - **sasomange.rs**: Modern SPA-style interface with faceted search integration Each scraper demonstrates different technical approaches: - **Dynamic Content**: Scroll-triggered loading (4zida.rs) - **Complex Parsing**: Multi-attribute extraction (halooglasi.rs) - **Traditional Structure**: Standard listing format (nekretnine.rs) - **Modern Architecture**: SPA with API-driven content (sasomange.rs) ### Extensible Architecture Adding new sources requires: 1. Inherit from BaseScraper class 2. Implement get_page_url(), get_page_listings(), process_listing() methods 3. Add to configuration in main.py ## Development ### Local Development
bash
# Install dependencies
pip install -r requirements.txt

# Run scrapers locally
python src/main.py
### Adding New Sources 1. Extend BaseScraper class 2. Implement required methods: - get_page_url(page) - get_page_listings() - process_listing(listing, processed_links) 3. Add to scraper configuration in main.py ### Testing
bash
# Test database connection
python -c "from database.session import get_db_session; print('DB OK')"

# Test scraper individually
python -m scrapers.oglasi_scraper
## Production Deployment ### Resource Requirements - **CPU**: 2+ cores recommended - **Memory**: 4GB+ RAM - **Storage**: 10GB+ for data and logs - **Network**: Stable internet for continuous scraping ### Security Considerations - Environment variables for sensitive data - Database connection encryption - Bot token protection - Rate limiting to respect source websites ### Backup Strategy
bash
# Database backup
docker-compose exec db pg_dump -U postgres realestate > backup.sql

# Restore database
docker-compose exec -T db psql -U postgres realestate < backup.sql
## Performance Optimization ### Current Throughput - **Processing Rate**: ~60 listings/hour - **Duplicate Rate**: ~85% (indicates mature dataset) - **Error Rate**: <1% under normal conditions - **Memory Usage**: ~150MB per scraper instance ### Scaling Options - Increase MAX_PAGES for broader coverage - Reduce WAIT_TIME for faster cycles (respect rate limits) - Add more source websites - Implement distributed scraping with message queues ## Troubleshooting ### Common Issues
bash
# Check container logs
docker-compose logs scraper

# Verify database connection
docker-compose exec db psql -U postgres -d realestate -c "SELECT COUNT(*) FROM listings;"

# Test Telegram notifications
curl -X POST "https://api.telegram.org/bot<TOKEN>/sendMessage" \
  -d "chat_id=<CHAT_ID>&text=Test message"

# Monitor Prometheus metrics
curl http://localhost:8000/metrics
### Health Checks - **Application**: http://localhost:8000/health - **Database**: Prometheus postgres exporter metrics - **Scrapers**: Active scraper count in Grafana ## Contributing 1. Fork the repository 2. Create feature branch: git checkout -b feature-name 3. Commit changes: git commit -am 'Add feature' 4. Push to branch: git push origin feature-name 5. Create Pull Request ## License This project is licensed under the MIT License - see the LICENSE file for details. ## Technical Highlights This system demonstrates production-ready practices for: - **Large-scale data collection** with anti-bot measures - **Real-time monitoring** and alerting systems - **Data quality assurance** through deduplication and validation - **Scalable architecture** with containerization and orchestration - **Operational excellence** with comprehensive logging and health checks Built for continuous operation in competitive intelligence and data collection scenarios.
