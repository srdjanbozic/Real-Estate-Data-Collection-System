from sqlalchemy import create_engine
from sqlalchemy.orm import scoped_session, sessionmaker
from sqlalchemy.pool import QueuePool
from dotenv import load_dotenv
import os
import logging
from tenacity import retry, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)

load_dotenv()

def get_database_url():
    db_url = os.getenv('DATABASE_URL')
    if 'localhost' in db_url:
        db_url = db_url.replace('localhost', 'db')
    return db_url

# Create engine once
engine = create_engine(
    get_database_url(),
    poolclass=QueuePool,
    pool_size=20,
    max_overflow=20,         # Increased from 10
    pool_timeout=60,         # Added timeout
    pool_pre_ping=True,
    pool_recycle=3600,
    echo=False               # Set to True for SQL debugging if needed
)

# Create session factory
Session = sessionmaker(bind=engine)
SessionFactory = scoped_session(Session)

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
def get_db_session():
    try:
        session = SessionFactory()
        return session
    except Exception as e:
        logger.error(f"Error creating database session: {e}")
        raise
    
def cleanup_db_session(session):
    """Helper function to properly cleanup database sessions"""
    try:
        session.close()
        SessionFactory.remove()
    except Exception as e:
        logger.error(f"Error cleaning up database session: {e}")