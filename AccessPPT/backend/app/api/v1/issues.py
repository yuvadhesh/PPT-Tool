"""
Issues API — individual issue management.
"""
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.db.session import get_db
from app.models.user import User
from app.models.accessibility import AccessibilityIssue, IssueStatus
from app.schemas import IssueResponse, ApplyFixRequest
from app.core.security import get_current_user

router = APIRouter(prefix="/issues", tags=["issues"])


@router.get("/{issue_id}", response_model=IssueResponse)
async def get_issue(
    issue_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(AccessibilityIssue).where(AccessibilityIssue.id == issue_id)
    )
    issue = result.scalar_one_or_none()
    if not issue:
        raise HTTPException(status_code=404, detail="Issue not found")
    return issue


@router.post("/{issue_id}/fix", response_model=IssueResponse)
async def apply_issue_fix(
    issue_id: str,
    request: ApplyFixRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Apply a fix to a single issue (user-approved)."""
    result = await db.execute(
        select(AccessibilityIssue).where(AccessibilityIssue.id == issue_id)
    )
    issue = result.scalar_one_or_none()
    if not issue:
        raise HTTPException(status_code=404, detail="Issue not found")

    if not issue.auto_fix_supported:
        raise HTTPException(
            status_code=400,
            detail="This issue does not support automatic fixing"
        )

    # Queue single fix
    from app.workers.celery_app import celery_app
    from app.models.slide import SlideObject, Slide

    obj_data = {}
    if issue.object_id:
        obj_result = await db.execute(
            select(SlideObject).where(SlideObject.id == issue.object_id)
        )
        obj = obj_result.scalar_one_or_none()
        if obj:
            slide_result = await db.execute(
                select(Slide).where(Slide.id == obj.slide_id)
            )
            slide = slide_result.scalar_one_or_none()
            if slide:
                obj_data = {
                    "slide_index": slide.slide_index,
                    "shape_id": obj.shape_id,
                }

    from app.api.v1.presentations import _issue_to_fix_type
    fix = {
        "issue_id": issue_id,
        "type": _issue_to_fix_type(issue) or "set_alt_text",
        "value": request.value or issue.ai_suggestion or "",
        "applied_by": request.applied_by,
        **obj_data,
    }

    celery_app.send_task(
        "app.tasks.analysis_tasks.apply_safe_fixes",
        args=[issue.presentation_id, [fix]],
    )

    issue.status = IssueStatus.FIXED
    issue.fixed_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(issue)
    return issue


@router.post("/{issue_id}/ignore", response_model=IssueResponse)
async def ignore_issue(
    issue_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(AccessibilityIssue).where(AccessibilityIssue.id == issue_id)
    )
    issue = result.scalar_one_or_none()
    if not issue:
        raise HTTPException(status_code=404, detail="Issue not found")

    issue.status = IssueStatus.IGNORED
    await db.commit()
    await db.refresh(issue)
    return issue


@router.post("/{issue_id}/reopen", response_model=IssueResponse)
async def reopen_issue(
    issue_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(AccessibilityIssue).where(AccessibilityIssue.id == issue_id)
    )
    issue = result.scalar_one_or_none()
    if not issue:
        raise HTTPException(status_code=404, detail="Issue not found")

    issue.status = IssueStatus.OPEN
    issue.fixed_at = None
    await db.commit()
    await db.refresh(issue)
    return issue
