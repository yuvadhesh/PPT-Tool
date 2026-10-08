import uuid
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import String, Integer, Float, Boolean, DateTime, ForeignKey, Text, Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base
import enum


def utcnow():
    return datetime.now(timezone.utc)


class PresentationStatus(str, enum.Enum):
    UPLOADED = "uploaded"
    PARSING = "parsing"
    ANALYZING = "analyzing"
    AI_ANALYSIS = "ai_analysis"
    REMEDIATING = "remediating"
    VERIFYING = "verifying"
    COMPLETE = "complete"
    FAILED = "failed"

    


class Presentation(Base):
    __tablename__ = "presentations"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    filename: Mapped[str] = mapped_column(String(500), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(500), nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)
    slide_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    object_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Storage keys
    original_s3_key: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    processed_s3_key: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    report_s3_key: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)

    # Accessibility score
    accessibility_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    error_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    warning_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    review_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    pass_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    status: Mapped[str] = mapped_column(
        String(50), default=PresentationStatus.UPLOADED, nullable=False
    )
    celery_task_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Metadata
    pptx_width_emu: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    pptx_height_emu: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    presentation_language: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="presentations")
    slides: Mapped[list["Slide"]] = relationship(
        "Slide", back_populates="presentation", cascade="all, delete-orphan", order_by="Slide.slide_index"
    )
    issues: Mapped[list["AccessibilityIssue"]] = relationship(
        "AccessibilityIssue", back_populates="presentation", cascade="all, delete-orphan"
    )
    analysis_runs: Mapped[list["AnalysisRun"]] = relationship(
        "AnalysisRun", back_populates="presentation", cascade="all, delete-orphan"
    )
    reports: Mapped[list["Report"]] = relationship(
        "Report", back_populates="presentation", cascade="all, delete-orphan"
    )
    verification_results: Mapped[list["VerificationResult"]] = relationship(
        "VerificationResult", back_populates="presentation", cascade="all, delete-orphan"
    )
