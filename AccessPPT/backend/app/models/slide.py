import uuid
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import String, Integer, Float, Boolean, DateTime, ForeignKey, Text, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base


def utcnow():
    return datetime.now(timezone.utc)


class Slide(Base):
    __tablename__ = "slides"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    presentation_id: Mapped[str] = mapped_column(String(36), ForeignKey("presentations.id", ondelete="CASCADE"), nullable=False, index=True)
    slide_index: Mapped[int] = mapped_column(Integer, nullable=False)
    slide_number: Mapped[int] = mapped_column(Integer, nullable=False)  # 1-based

    # Title info
    title: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    title_placeholder_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    # Notes
    speaker_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    has_notes: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Accessibility scores for this slide
    accessibility_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    error_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    warning_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Raw XML for debugging
    slide_xml_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    # Thumbnail S3 key
    thumbnail_s3_key: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    # Relationships
    presentation: Mapped["Presentation"] = relationship("Presentation", back_populates="slides")
    objects: Mapped[list["SlideObject"]] = relationship(
        "SlideObject", back_populates="slide", cascade="all, delete-orphan"
    )
    issues: Mapped[list["AccessibilityIssue"]] = relationship(
        "AccessibilityIssue", back_populates="slide", cascade="all, delete-orphan"
    )


class ObjectType(str):
    IMAGE = "image"
    TEXT_BOX = "text_box"
    SHAPE = "shape"
    TABLE = "table"
    CHART = "chart"
    SMART_ART = "smart_art"
    AUDIO = "audio"
    VIDEO = "video"
    GROUP = "group"
    OTHER = "other"


class SlideObject(Base):
    __tablename__ = "slide_objects"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    slide_id: Mapped[str] = mapped_column(String(36), ForeignKey("slides.id", ondelete="CASCADE"), nullable=False, index=True)
    presentation_id: Mapped[str] = mapped_column(String(36), ForeignKey("presentations.id", ondelete="CASCADE"), nullable=False, index=True)

    # Object identity
    shape_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    name: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    object_type: Mapped[str] = mapped_column(String(50), nullable=False)

    # Position and size (EMU)
    left_emu: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    top_emu: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    width_emu: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    height_emu: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Text content
    text_content: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Accessibility properties
    alt_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    alt_text_title: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    is_decorative: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    reading_order: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Media properties
    has_audio: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    has_video: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    has_animation: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Chart/table specific
    chart_title: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    has_table_headers: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)

    # Image hash for comparison
    image_hash: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    image_s3_key: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)

    # AI analysis
    ai_analyzed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    ai_suggestions: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    # Extra metadata
    extra_data: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    # Relationships
    slide: Mapped["Slide"] = relationship("Slide", back_populates="objects")
    issues: Mapped[list["AccessibilityIssue"]] = relationship(
        "AccessibilityIssue", back_populates="object", cascade="all, delete-orphan"
    )
    ai_suggestion_records: Mapped[list["AISuggestion"]] = relationship(
        "AISuggestion", back_populates="object", cascade="all, delete-orphan"
    )
