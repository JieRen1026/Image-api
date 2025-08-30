# app/db.py
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

Base = declarative_base()

def _resolve_db_url():
    # Try common env names
    url = (os.getenv("DATABASE_URL")
           or os.getenv("SQLALCHEMY_DATABASE_URL")
           or os.getenv("DB_URL"))
    if not url:
        data_dir = os.getenv("DATA_DIR", "/data")
        os.makedirs(data_dir, exist_ok=True)
        url = f"sqlite:///{os.path.join(data_dir, 'app.db')}"
    # Ensure parent dir exists for sqlite paths
    if url.startswith("sqlite:///"):
        db_path = url[len("sqlite:///"):]
        parent = os.path.dirname(db_path)
        if parent:
            os.makedirs(parent, exist_ok=True)
    return url

DATABASE_URL = _resolve_db_url()
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def init_db():
    Base.metadata.create_all(bind=engine)
