from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Numeric, Text, func, UniqueConstraint
from sqlalchemy.orm import relationship, declarative_base

Base = declarative_base()

class Owner(Base):
    __tablename__ = 'owners'
    
    id = Column(Integer, primary_key=True)
    name = Column(String(100))
    phone = Column(String(50))
    source = Column(String(50))  
    external_id = Column(String(100))
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    
    listings = relationship("Listing", back_populates="owner")

class Listing(Base):
    __tablename__ = 'listings'
    
    id = Column(Integer, primary_key=True)
    owner_id = Column(Integer, ForeignKey('owners.id'))
    source = Column(String(50))
    external_id = Column(String(100))
    title = Column(Text)
    price = Column(Numeric)
    square_meters = Column(Integer)
    rooms = Column(String(50))
    description = Column(Text)
    location = Column(String(100))
    posted_date = Column(DateTime)
    processed_date = Column(DateTime)
    url = Column(Text, unique=True)
    status = Column(String(20))
    listing_type = Column(String(20), default='rent')  # 'rent' or 'sale'
    building_condition = Column(String(50), nullable=True)  # For sales
    floor_level = Column(String(50), nullable=True)  # For sales
    image_url = Column(Text)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    
    __table_args__ = (
        UniqueConstraint('source', 'external_id', name='uix_source_external_id'),
    )

    owner = relationship("Owner", back_populates="listings")
    history = relationship("ListingHistory", back_populates="listing")

class ListingHistory(Base):
    __tablename__ = 'listing_history'
    
    id = Column(Integer, primary_key=True)
    listing_id = Column(Integer, ForeignKey('listings.id'))
    price = Column(Numeric)
    changed_date = Column(DateTime)
    change_type = Column(String(50))
    created_at = Column(DateTime, default=func.now())
    
    listing = relationship("Listing", back_populates="history")