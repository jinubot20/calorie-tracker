from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from datetime import datetime

DATABASE_URL = "sqlite:///./calorie_tracker.db"

Base = declarative_base()

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    telegram_id = Column(String, unique=True, index=True, nullable=True)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    name = Column(String)
    daily_target = Column(Integer, default=2000)
    
    # New fields for Fuel Share
    share_enabled = Column(Integer, default=0) # 0=False, 1=True
    share_token = Column(String, unique=True, index=True, nullable=True)
    
    cached_summary = Column(String, nullable=True)
    summary_date = Column(String, nullable=True) # YYYY-MM-DD
    meals = relationship("Meal", back_populates="owner")

class Meal(Base):
    __tablename__ = "meals"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    food_name = Column(String)
    meal_type = Column(String, nullable=True) # breakfast, lunch, snacks, dinner
    description = Column(String, nullable=True)
    calories = Column(Integer)
    protein = Column(Integer, default=0)
    carbs = Column(Integer, default=0)
    fat = Column(Integer, default=0)
    image_paths = Column(String, nullable=True) # JSON string of paths
    portion = Column(Float, default=1.0)
    items_json = Column(String, nullable=True) # JSON list of {name, portion}
    timestamp = Column(DateTime, default=datetime.utcnow)
    
    # New field for Trainer/Public comments
    trainer_notes = Column(String, nullable=True)
    
    owner = relationship("User", back_populates="meals")

class DailyFeedback(Base):
    __tablename__ = "daily_feedback"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    date = Column(String, index=True) # YYYY-MM-DD
    content = Column(String, nullable=True)

class DailySummary(Base):
    __tablename__ = "daily_summaries"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    date = Column(String, index=True) # YYYY-MM-DD
    content = Column(String, nullable=True)

from sqlalchemy import create_engine
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def init_db():
    Base.metadata.create_all(bind=engine)
