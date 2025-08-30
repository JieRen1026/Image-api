# app/models.py
from sqlalchemy import (
    Column, String, Integer, DateTime, JSON, Enum, ForeignKey, func, Index
)
from sqlalchemy.orm import relationship
from app.db import Base
import enum
from datetime import datetime
import uuid


# ----- Enums -----
class JobStatus(str, enum.Enum):
    processing = "processing"
    done = "done"
    error = "error"


# ----- Core: Image processing job -----
class ImageJob(Base):
    __tablename__ = "image_jobs"

    # UUID stored as string for portability
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))

    # Keep user_id as String to match your existing code/auth layer
    user_id = Column(String, nullable=False)

    original_path = Column(String, nullable=False)
    processed_path = Column(String, nullable=True)
    mime_type = Column(String, nullable=False)

    # Parameters used for processing (e.g., {"op": "grayscale", "sigma": 1.5})
    params = Column(JSON, nullable=True)

    status = Column(Enum(JobStatus), nullable=False, default=JobStatus.processing)
    error_message = Column(String, nullable=True)

    width = Column(Integer, nullable=True)
    height = Column(Integer, nullable=True)

    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    # NEW: convenient back-reference to logs for this job
    logs = relationship("ProcessingLog", back_populates="job", cascade="all, delete-orphan")


# Optional: a helpful index for recent jobs
Index("ix_image_jobs_created_at", ImageJob.created_at)


# ----- Additional data type: Processing logs/history -----
class ProcessingLog(Base):
    __tablename__ = "processing_logs"

    id = Column(Integer, primary_key=True, index=True)

    # Keep this as String to match your existing user_id type
    user_id = Column(String, nullable=False)

    # Link logs directly to the job they describe
    job_id = Column(String, ForeignKey("image_jobs.id", ondelete="CASCADE"), nullable=False)

    # e.g. "upload", "grayscale", "edge_detect", "resize", "error"
    action = Column(String, nullable=False)

    # optional free-form details (duration ms, parameters applied, error text, etc.)
    details = Column(JSON, nullable=True)

    # server-side timestamp
    timestamp = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationship back to parent job
    job = relationship("ImageJob", back_populates="logs")


# Optional: index for faster admin queries by time or action
Index("ix_processing_logs_timestamp", ProcessingLog.timestamp)
Index("ix_processing_logs_action", ProcessingLog.action)
