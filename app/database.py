from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from app.config.settings import DATABASE_URI, SESSION_POOL_SIZE

engine = create_engine(
    DATABASE_URI,
    pool_size=SESSION_POOL_SIZE,
    max_overflow=20,
    pool_timeout=30,
    pool_recycle=240,
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()
