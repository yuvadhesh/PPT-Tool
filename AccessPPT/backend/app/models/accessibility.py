import uuid
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import String, Integer, Float, Boolean, DateTime, ForeignKey, Text, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base


def utcnow():
    return datetime.now(timezone.utc)


class IssueSeverity(str):
    ERROR = "error"
    WARNING = "warning"
    REVIEW = "review"
    PASS = "pass"


class IssueCategory(str):
    SLIDE_TITLE = "slide_title"
    ALT_TEXT = "alt_text"
    DECORATIVE = "decorative"
    READING_ORDER = "reading_order"
    TABLES = "tables"
    COLOR_CONTRAST = "color_contrast"
    COLOR_MEANING = "color_meaning"
    HYPERLINKS = "hyperlinks"
    FONT_SIZE = "font_size"
    LANGUAGE = "language"
    IMAGES_WITH_TEXT = "images_with_text"
    CHARTS = "charts"
    SMART_ART = "smart_art"
    AUDIO = "audio"
    VIDEO = "video"
    ANIMATIONS = "animations"
    SPEAKER_NOTES = "speaker_notes"
    GROUPED_OBJECTS = "grouped_objects"


class IssueStatus(str):
    OPEN = "open"
    FIXED = "fixed"
    IGNORED = "ignored"
    PENDING_REVIEW = "pending_review"


class AccessibilityIssue(Base):
    __tablename__ = "accessibility_issues"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    presentation_id: Mapped[str] = mapped_column(String(36), ForeignKey("presentations.id", ondelete="CASCADE"), nullable=False, index=True)
    slide_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("slides.id", ondelete="CASCADE"), nullable=True, index=True)
    object_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("slide_objects.id", ondelete="CASCADE"), nullable=True, index=True)

    # Rule info
    rule_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    category: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    severity: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    why_it_matters: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    recommendation: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    standard_reference: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)

    # Context
    context_data: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    # Fix support
    auto_fix_supported: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    manual_review_required: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default=IssueStatus.OPEN, nullable=False)

    # AI info
    ai_analyzed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    ai_suggestion: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    ai_confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    ai_confidence_level: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    fixed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    presentation: Mapped["Presentation"] = relationship("Presentation", back_populates="issues")
    slide: Mapped[Optional["Slide"]] = relationship("Slide", back_populates="issues")
    object: Mapped[Optional["SlideObject"]] = relationship("SlideObject", back_populates="issues")
    remediation_actions: Mapped[list["RemediationAction"]] = relationship(
        "RemediationAction", back_populates="issue", cascade="all, delete-orphan"
    )


class AISuggestion(Base):
    __tablename__ = "ai_suggestions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    presentation_id: Mapped[str] = mapped_column(String(36), ForeignKey("presentations.id", ondelete="CASCADE"), nullable=False, index=True)
    object_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("slide_objects.id", ondelete="CASCADE"), nullable=True, index=True)

    check_type: Mapped[str] = mapped_column(String(100), nullable=False)
    result: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    confidence_level: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    suggestion: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    raw_response: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    is_valid: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    human_review_recommended: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    object: Mapped[Optional["SlideObject"]] = relationship("SlideObject", back_populates="ai_suggestion_records")


class RemediationAction(Base):
    __tablename__ = "remediation_actions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    issue_id: Mapped[str] = mapped_column(String(36), ForeignKey("accessibility_issues.id", ondelete="CASCADE"), nullable=False, index=True)
    presentation_id: Mapped[str] = mapped_column(String(36), ForeignKey("presentations.id", ondelete="CASCADE"), nullable=False, index=True)

    action_type: Mapped[str] = mapped_column(String(100), nullable=False)
    action_data: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    applied_by: Mapped[str] = mapped_column(String(50), nullable=False, default="auto")  # auto / user
    success: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    issue: Mapped["AccessibilityIssue"] = relationship("AccessibilityIssue", back_populates="remediation_actions")


class AnalysisRun(Base):
    __tablename__ = "analysis_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    presentation_id: Mapped[str] = mapped_column(String(36), ForeignKey("presentations.id", ondelete="CASCADE"), nullable=False, index=True)
    celery_task_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    status: Mapped[str] = mapped_column(String(50), nullable=False, default="pending")
    progress: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    current_step: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    steps_completed: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    presentation: Mapped["Presentation"] = relationship("Presentation", back_populates="analysis_runs")


class ReportFormat(str):
    PDF = "pdf"
    HTML = "html"
    CSV = "csv"
    JSON = "json"


class Report(Base):
    __tablename__ = "reports"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    presentation_id: Mapped[str] = mapped_column(String(36), ForeignKey("presentations.id", ondelete="CASCADE"), nullable=False, index=True)
    format: Mapped[str] = mapped_column(String(20), nullable=False)
    s3_key: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    file_size: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    presentation: Mapped["Presentation"] = relationship("Presentation", back_populates="reports")


class VerificationResult(Base):
    __tablename__ = "verification_results"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    presentation_id: Mapped[str] = mapped_column(String(36), ForeignKey("presentations.id", ondelete="CASCADE"), nullable=False, index=True)

    status: Mapped[str] = mapped_column(String(50), nullable=False)  # passed / failed
    visual_changes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    content_changes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    layout_changes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    accessibility_changes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    details: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    presentation: Mapped["Presentation"] = relationship("Presentation", back_populates="verification_results")
