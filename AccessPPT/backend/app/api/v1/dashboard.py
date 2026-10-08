"""
Dashboard API.
"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc

from app.db.session import get_db
from app.models.user import User
from app.models.slide import Slide
from app.models.presentation import Presentation
from app.models.accessibility import AccessibilityIssue, RemediationAction
from app.schemas import DashboardStatsResponse, PresentationResponse
from app.core.security import get_current_user

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/stats", response_model=DashboardStatsResponse)
async def get_dashboard_stats(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Total presentations
    total_result = await db.execute(
        select(func.count(Presentation.id)).where(Presentation.user_id == current_user.id)
    )
    total = total_result.scalar() or 0

    # Total slides analyzed
    slides_result = await db.execute(
        select(func.count(Slide.id)).where(
            Slide.presentation_id.in_(
                select(Presentation.id).where(Presentation.user_id == current_user.id)
            )
        )
    )
    total_slides = slides_result.scalar() or 0

    # Average score
    avg_result = await db.execute(
        select(func.avg(Presentation.accessibility_score)).where(
            Presentation.user_id == current_user.id,
            Presentation.accessibility_score.isnot(None),
        )
    )
    avg_score = float(avg_result.scalar() or 0)

    # Above 90
    above90_result = await db.execute(
        select(func.count(Presentation.id)).where(
            Presentation.user_id == current_user.id,
            Presentation.accessibility_score >= 90,
        )
    )
    above90 = above90_result.scalar() or 0

    # Total fixes applied
    fixes_result = await db.execute(
        select(func.count(RemediationAction.id)).where(
            RemediationAction.presentation_id.in_(
                select(Presentation.id).where(Presentation.user_id == current_user.id)
            )
        )
    )
    total_fixes = fixes_result.scalar() or 0

    # Issues summary
    issues_result = await db.execute(
        select(AccessibilityIssue.severity, func.count(AccessibilityIssue.id))
        .where(
            AccessibilityIssue.presentation_id.in_(
                select(Presentation.id).where(Presentation.user_id == current_user.id)
            )
        )
        .group_by(AccessibilityIssue.severity)
    )
    issues_summary = {str(row[0]).lower(): row[1] for row in issues_result.fetchall()}

    issues_by_severity = {
        "error": issues_summary.get("error", 0),
        "warning": issues_summary.get("warning", 0),
        "review": issues_summary.get("review", 0),
        "pass": issues_summary.get("pass", 0),
    }

    # Recent presentations
    recent_result = await db.execute(
        select(Presentation)
        .where(Presentation.user_id == current_user.id)
        .order_by(desc(Presentation.created_at))
        .limit(10)
    )
    recent = recent_result.scalars().all()

    return DashboardStatsResponse(
        total_presentations=total,
        total_issues_fixed=total_fixes,
        total_slides_analyzed=total_slides,
        avg_accessibility_score=round(avg_score, 1),
        presentations_above_90=above90,
        issues_by_severity=issues_by_severity,
        recent_presentations=list(recent),
        issues_summary=issues_summary,
    )
