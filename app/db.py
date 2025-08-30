import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# Use env var if provided, else default to a file in the mounted /data volume
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:////data/app.db")
# Note: four slashes after 'sqlite:' for an absolute path

# SQLite needs this for FastAPI threading
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def init_db():
    from app import models
    Base.metadata.create_all(bind=engine)
