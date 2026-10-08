"""
Pydantic request/response schemas for all API endpoints.
"""
from datetime import datetime
from typing import Optional, Any
from pydantic import BaseModel, EmailStr, field_validator


# ─── Auth ────────────────────────────────────────────────────────────────────

class UserRegisterRequest(BaseModel):
    email: EmailStr
    full_name: str
    password: str

    @field_validator("password")
    @classmethod
    def password_strength(cls, v):
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        return v


class UserLoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class UserResponse(BaseModel):
    id: str
    email: str
    full_name: str
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


# ─── Presentations ─────────────────────────────────────────────────────────

class PresentationResponse(BaseModel):
    id: str
    filename: str
    original_filename: str
    file_size: int
    slide_count: Optional[int]
    object_count: Optional[int]
    accessibility_score: Optional[float]
    error_count: int
    warning_count: int
    review_count: int
    pass_count: int
    status: str
    celery_task_id: Optional[str]
    error_message: Optional[str]
    presentation_language: Optional[str]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class PresentationListResponse(BaseModel):
    items: list[PresentationResponse]
    total: int
    page: int
    page_size: int


# ─── Slides ──────────────────────────────────────────────────────────────────

class SlideObjectResponse(BaseModel):
    id: str
    shape_id: Optional[int]
    name: Optional[str]
    object_type: str
    left_emu: Optional[int]
    top_emu: Optional[int]
    width_emu: Optional[int]
    height_emu: Optional[int]
    text_content: Optional[str]
    alt_text: Optional[str]
    alt_text_title: Optional[str]
    is_decorative: Optional[bool]
    reading_order: Optional[int]
    has_audio: bool
    has_video: bool
    has_animation: bool
    chart_title: Optional[str]
    has_table_headers: Optional[bool]
    ai_analyzed: bool
    ai_suggestions: Optional[dict]
    extra_data: Optional[dict]

    model_config = {"from_attributes": True}


class SlideResponse(BaseModel):
    id: str
    presentation_id: Optional[str] = None
    slide_index: int
    slide_number: int
    title: Optional[str] = None
    speaker_notes: Optional[str] = None
    has_notes: bool = False
    accessibility_score: Optional[float] = None
    error_count: int = 0
    warning_count: int = 0
    thumbnail_s3_key: Optional[str] = None
    created_at: Optional[datetime] = None
    objects: list[SlideObjectResponse] = []

    model_config = {"from_attributes": True}


# ─── Issues ──────────────────────────────────────────────────────────────────

class IssueResponse(BaseModel):
    id: str
    rule_id: str
    category: str
    severity: str
    title: str
    description: str
    why_it_matters: Optional[str]
    recommendation: Optional[str]
    standard_reference: Optional[str]
    context_data: Optional[dict]
    auto_fix_supported: bool
    manual_review_required: bool
    status: str
    ai_analyzed: bool
    ai_suggestion: Optional[str]
    ai_confidence: Optional[float]
    ai_confidence_level: Optional[str]
    slide_id: Optional[str]
    object_id: Optional[str]
    created_at: datetime

    model_config = {"from_attributes": True}


class IssueListResponse(BaseModel):
    items: list[IssueResponse]
    total: int
    by_severity: dict[str, int]
    by_category: dict[str, int]


class ApplyFixRequest(BaseModel):
    value: Optional[str] = None
    applied_by: str = "user"


class FixSafeRequest(BaseModel):
    fix_all: bool = True
    issue_ids: list[str] = []


# ─── Jobs ────────────────────────────────────────────────────────────────────

class JobStatusResponse(BaseModel):
    job_id: str
    status: str
    progress: int
    current_step: Optional[str]
    steps_completed: Optional[dict]
    result: Optional[dict]
    error: Optional[str]


# ─── Analysis ────────────────────────────────────────────────────────────────

class AnalysisResponse(BaseModel):
    presentation_id: str
    status: str
    accessibility_score: Optional[float]
    error_count: int
    warning_count: int
    review_count: int
    pass_count: int
    category_scores: dict[str, Any] = {}
    slides_analyzed: int
    objects_analyzed: int
    ai_suggestions_count: int


class AnalysisRunResponse(BaseModel):
    id: str
    status: str
    progress: int
    current_step: Optional[str]
    steps_completed: Optional[dict]
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    error_message: Optional[str]

    model_config = {"from_attributes": True}


# ─── Reports ─────────────────────────────────────────────────────────────────

class ReportResponse(BaseModel):
    id: str
    format: str
    file_size: Optional[int]
    created_at: datetime
    download_url: Optional[str] = None

    model_config = {"from_attributes": True}


# ─── Verification ────────────────────────────────────────────────────────────

class VerificationResponse(BaseModel):
    status: str
    visual_changes: int
    content_changes: int
    layout_changes: int
    accessibility_changes: int
    details: Optional[dict]

    model_config = {"from_attributes": True}


# ─── Dashboard ───────────────────────────────────────────────────────────────

class DashboardStatsResponse(BaseModel):
    total_presentations: int
    total_issues_fixed: int
    avg_accessibility_score: float
    presentations_above_90: int
    total_slides_analyzed: int = 0
    issues_by_severity: dict[str, int] = {}
    recent_presentations: list[PresentationResponse]
    issues_summary: dict[str, int]


# ─── Reading Order ───────────────────────────────────────────────────────────

class ReadingOrderItemResponse(BaseModel):
    shape_id: int
    name: str = "Object"
    object_type: str = "Shape"
    semantic_role: str = "shape"
    placeholder_type: Optional[str] = None
    is_placeholder: bool = False
    is_title: bool = False
    text_snippet: Optional[str] = None
    alt_text: Optional[str] = None
    is_decorative: bool = False
    current_position: int = 1
    recommended_position: int = 1
    is_misplaced: bool = False
    norm_left: float = 0.0
    norm_top: float = 0.0
    norm_width: float = 0.0
    norm_height: float = 0.0


class ReadingOrderIssueResponse(BaseModel):
    code: str
    severity: str = "FAIL"
    affected_shape_ids: list[int] = []
    shape_name: str
    current_position: int
    recommended_position: int
    description: str
    suggestion: str


class SlideReadingOrderResponse(BaseModel):
    slide_index: int
    slide_number: int
    title: Optional[str] = None
    status: str  # "PASS" | "FAIL"
    total_objects: int
    sequence_display: str
    issues: list[ReadingOrderIssueResponse] = []
    current_sequence: list[ReadingOrderItemResponse] = []
    recommended_sequence: list[ReadingOrderItemResponse] = []
    preview_objects: list[ReadingOrderItemResponse] = []


class ReadingOrderSummaryResponse(BaseModel):
    total_slides_checked: int
    slides_passed: int
    slides_failed: int
    total_issues: int
    compliance_rate: float


class ReadingOrderCheckResponse(BaseModel):
    presentation_id: str
    summary: ReadingOrderSummaryResponse
    slide_width_emu: int
    slide_height_emu: int
    slides: list[SlideReadingOrderResponse]


class SlideReadingOrderFixDetail(BaseModel):
    slide_index: int
    slide_number: int
    title: Optional[str] = None
    status: str  # "fixed" | "already_correct" | "error"
    before_status: str  # "PASS" | "FAIL"
    after_status: str  # "PASS" | "FAIL"
    issues_before: int = 0
    issues_after: int = 0
    current_sequence: list[ReadingOrderItemResponse] = []
    recommended_sequence: list[ReadingOrderItemResponse] = []
    error_message: Optional[str] = None


class ReadingOrderFixSummaryResponse(BaseModel):
    total_slides: int
    already_correct: int
    fixed: int
    manual_review: int = 0
    failed: int
    issues_remaining: int
    verification_status: str  # "SUCCESS" | "PARTIAL" | "FAILED" | "MANUAL_REVIEW"


class ReadingOrderFixResponse(BaseModel):
    success: bool
    presentation_id: str
    message: str
    summary: ReadingOrderFixSummaryResponse
    slides: list[SlideReadingOrderFixDetail] = []
    download_url: str

