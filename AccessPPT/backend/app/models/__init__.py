# Import all models so Alembic can discover them
from app.db.base import Base
from app.models.user import User
from app.models.presentation import Presentation
from app.models.slide import Slide, SlideObject
from app.models.accessibility import (
    AccessibilityIssue,
    AISuggestion,
    RemediationAction,
    AnalysisRun,
    Report,
    VerificationResult,
)

__all__ = [
    "Base",
    "User",
    "Presentation",
    "Slide",
    "SlideObject",
    "AccessibilityIssue",
    "AISuggestion",
    "RemediationAction",
    "AnalysisRun",
    "Report",
    "VerificationResult",
]
