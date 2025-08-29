import enum, uuid, datetime as dt
from sqlalchemy import Column, String, DateTime, Enum, JSON, Integer
from sqlalchemy.orm import declarative_base

Base = declarative_base()

class JobStatus(str, enum.Enum):
    queued = "queued"
    processing = "processing"
    done = "done"
    error = "error"

class ImageJob(Base):
    __tablename__ = "image_jobs"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, nullable=False)
    original_path = Column(String, nullable=False)
    processed_path = Column(String, nullable=True)
    mime_type = Column(String, nullable=False)
    params = Column(JSON, nullable=False, default=dict)
    status = Column(Enum(JobStatus), default=JobStatus.queued, nullable=False)
    error_message = Column(String, nullable=True)
    width = Column(Integer, nullable=True)
    height = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=dt.datetime.utcnow, nullable=False)
