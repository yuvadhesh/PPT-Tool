"""
Presentations API routes — upload, analyze, manage.
"""
import os
import uuid
import json
import tempfile
from typing import Optional
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query, BackgroundTasks, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc
from sqlalchemy.orm import selectinload

from app.services.report_generator import generate_report_data, render_report
from app.services.reading_order_service import reading_order_service

from app.db.session import get_db
from app.models.user import User
from app.models.presentation import Presentation
from app.models.slide import Slide
from app.models.accessibility import AccessibilityIssue, AnalysisRun, Report, VerificationResult
from app.schemas import (
    PresentationResponse, PresentationListResponse, AnalysisResponse,
    IssueListResponse, IssueResponse, FixSafeRequest, JobStatusResponse,
    AnalysisRunResponse, ReportResponse, VerificationResponse, DashboardStatsResponse,
    SlideResponse, ReadingOrderCheckResponse, ReadingOrderFixResponse
)
from app.core.security import get_current_user
from app.core.config import settings
from app.services.storage_service import storage_service
from app.workers.celery_app import celery_app, is_celery_available

router = APIRouter(prefix="/presentations", tags=["presentations"])


def _run_analyze_fallback(presentation_id: str, tmp_path: str, run_ai: bool, task_id: str):
    from app.tasks.analysis_tasks import analyze_presentation
    try:
        analyze_presentation.apply(args=[presentation_id, tmp_path, run_ai], task_id=task_id)
    except Exception as e:
        from app.core.logging import logger
        logger.error("Analyze fallback failed", error=str(e), presentation_id=presentation_id)


def _run_fixes_fallback(presentation_id: str, fixes: list, task_id: str):
    from app.tasks.analysis_tasks import apply_safe_fixes as run_apply_safe_fixes
    try:
        run_apply_safe_fixes.apply(args=[presentation_id, fixes], task_id=task_id)
    except Exception as e:
        from app.core.logging import logger
        logger.error("Fixes fallback failed", error=str(e), presentation_id=presentation_id)


def _run_report_fallback(presentation_id: str, format: str, task_id: str):
    from app.tasks.analysis_tasks import generate_report as run_generate_report
    try:
        run_generate_report.apply(args=[presentation_id, format], task_id=task_id)
    except Exception as e:
        from app.core.logging import logger
        logger.error("Report fallback failed", error=str(e), presentation_id=presentation_id)


def _validate_pptx(file: UploadFile) -> None:
    """Validate uploaded file is a valid PPTX."""
    if not file.filename or not file.filename.lower().endswith(".pptx"):
        raise HTTPException(status_code=400, detail="Only .pptx files are supported")


@router.post("/upload", response_model=PresentationResponse, status_code=201)
async def upload_presentation(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Upload a PPTX file for accessibility analysis."""
    _validate_pptx(file)

    file_data = await file.read()
    if len(file_data) > settings.max_file_size_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"File size exceeds limit of {settings.MAX_FILE_SIZE_MB}MB"
        )
    if len(file_data) == 0:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")

    pres_id = str(uuid.uuid4())
    safe_filename = file.filename.replace(" ", "_")
    s3_key = storage_service.make_key(f"originals/{pres_id}", safe_filename)

    try:
        storage_service.upload_file(
            file_data, s3_key,
            "application/vnd.openxmlformats-officedocument.presentationml.presentation"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"File storage error: {str(e)}")

    pres = Presentation(
        id=pres_id,
        user_id=current_user.id,
        filename=safe_filename,
        original_filename=file.filename,
        file_size=len(file_data),
        original_s3_key=s3_key,
        status="uploaded",
    )
    db.add(pres)
    await db.commit()
    await db.refresh(pres)
    return pres


@router.post("/{presentation_id}/analyze", response_model=dict)
async def trigger_analysis(
    presentation_id: str,
    background_tasks: BackgroundTasks,
    run_ai: bool = Query(default=True),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Trigger background accessibility analysis for a presentation."""
    result = await db.execute(
        select(Presentation).where(
            Presentation.id == presentation_id,
            Presentation.user_id == current_user.id
        )
    )
    pres = result.scalar_one_or_none()
    if not pres:
        raise HTTPException(status_code=404, detail="Presentation not found")

    if not pres.original_s3_key:
        raise HTTPException(status_code=400, detail="No file attached to this presentation")

    # Download to temp path for analysis worker
    with tempfile.NamedTemporaryFile(suffix=".pptx", delete=False) as tmp:
        tmp_path = tmp.name

    if not storage_service.download_to_path(pres.original_s3_key, tmp_path):
        raise HTTPException(status_code=500, detail="Failed to retrieve presentation file")

    task_id = str(uuid.uuid4())
    dispatched = False
    if is_celery_available():
        try:
            task = celery_app.send_task(
                "app.tasks.analysis_tasks.analyze_presentation",
                args=[presentation_id, tmp_path, run_ai],
            )
            task_id = task.id
            dispatched = True
        except Exception:
            dispatched = False

    if not dispatched:
        background_tasks.add_task(_run_analyze_fallback, presentation_id, tmp_path, run_ai, task_id)

    pres.celery_task_id = task_id
    pres.status = "analyzing"
    await db.commit()

    return {"task_id": task_id, "status": "analyzing", "presentation_id": presentation_id}


@router.get("/{presentation_id}", response_model=PresentationResponse)
async def get_presentation(
    presentation_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Presentation).where(
            Presentation.id == presentation_id,
            Presentation.user_id == current_user.id
        )
    )
    pres = result.scalar_one_or_none()
    if not pres:
        raise HTTPException(status_code=404, detail="Presentation not found")
    return pres


@router.get("/{presentation_id}/slides", response_model=list[SlideResponse])
async def get_slides(
    presentation_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Retrieve slides and extracted OpenXML elements for a presentation."""
    pres_result = await db.execute(
        select(Presentation).where(
            Presentation.id == presentation_id,
            Presentation.user_id == current_user.id
        )
    )
    if not pres_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Presentation not found")

    result = await db.execute(
        select(Slide)
        .options(selectinload(Slide.objects))
        .where(Slide.presentation_id == presentation_id)
        .order_by(Slide.slide_index.asc())
    )
    slides = result.scalars().all()
    return list(slides)


@router.get("", response_model=PresentationListResponse)
async def list_presentations(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    offset = (page - 1) * page_size
    total_result = await db.execute(
        select(func.count(Presentation.id)).where(Presentation.user_id == current_user.id)
    )
    total = total_result.scalar() or 0

    items_result = await db.execute(
        select(Presentation)
        .where(Presentation.user_id == current_user.id)
        .order_by(desc(Presentation.created_at))
        .offset(offset)
        .limit(page_size)
    )
    items = items_result.scalars().all()
    return PresentationListResponse(items=list(items), total=total, page=page, page_size=page_size)


@router.get("/{presentation_id}/analysis", response_model=AnalysisRunResponse)
async def get_analysis_status(
    presentation_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Verify ownership
    pres_result = await db.execute(
        select(Presentation).where(
            Presentation.id == presentation_id,
            Presentation.user_id == current_user.id
        )
    )
    if not pres_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Presentation not found")

    result = await db.execute(
        select(AnalysisRun)
        .where(AnalysisRun.presentation_id == presentation_id)
        .order_by(desc(AnalysisRun.created_at))
        .limit(1)
    )
    run = result.scalar_one_or_none()
    if not run:
        raise HTTPException(status_code=404, detail="No analysis run found")
    return run


@router.get("/{presentation_id}/issues", response_model=IssueListResponse)
async def get_issues(
    presentation_id: str,
    severity: Optional[str] = Query(default=None),
    category: Optional[str] = Query(default=None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    pres_result = await db.execute(
        select(Presentation).where(
            Presentation.id == presentation_id,
            Presentation.user_id == current_user.id
        )
    )
    if not pres_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Presentation not found")

    query = select(AccessibilityIssue).where(
        AccessibilityIssue.presentation_id == presentation_id
    )
    if severity:
        query = query.where(AccessibilityIssue.severity == severity)
    if category:
        query = query.where(AccessibilityIssue.category == category)

    result = await db.execute(query)
    issues = result.scalars().all()

    by_severity: dict[str, int] = {}
    by_category: dict[str, int] = {}
    for issue in issues:
        by_severity[issue.severity] = by_severity.get(issue.severity, 0) + 1
        by_category[issue.category] = by_category.get(issue.category, 0) + 1

    return IssueListResponse(
        items=list(issues),
        total=len(issues),
        by_severity=by_severity,
        by_category=by_category,
    )


@router.post("/{presentation_id}/fix-safe", response_model=dict)
async def apply_safe_fixes(
    presentation_id: str,
    background_tasks: BackgroundTasks,
    request: Optional[FixSafeRequest] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Apply all safe auto-fixes to the presentation."""
    req = request or FixSafeRequest()
    pres_result = await db.execute(
        select(Presentation).where(
            Presentation.id == presentation_id,
            Presentation.user_id == current_user.id
        )
    )
    pres = pres_result.scalar_one_or_none()
    if not pres:
        raise HTTPException(status_code=404, detail="Presentation not found")

    # Get auto-fixable issues
    query = select(AccessibilityIssue).options(
        selectinload(AccessibilityIssue.slide),
        selectinload(AccessibilityIssue.object),
    ).where(
        AccessibilityIssue.presentation_id == presentation_id,
        AccessibilityIssue.auto_fix_supported == True,
        AccessibilityIssue.status == "open",
    )
    if req.issue_ids:
        query = query.where(AccessibilityIssue.id.in_(req.issue_ids))

    result = await db.execute(query)
    issues = result.scalars().all()

    # Build fix list from issues
    fixes = []
    for issue in issues:
        ctx = issue.context_data or {}
        slide_idx = ctx.get("slide_index")
        shape_id = ctx.get("shape_id")

        if slide_idx is None and issue.slide:
            slide_idx = issue.slide.slide_index
        if shape_id is None and issue.object:
            shape_id = issue.object.shape_id

        val = issue.ai_suggestion
        if not val:
            if issue.category == "slide_title":
                title = ctx.get("title") or (issue.slide.title if issue.slide else "")
                duplicates = ctx.get("duplicates") or []
                if duplicates and slide_idx is not None and slide_idx in duplicates:
                    part_num = duplicates.index(slide_idx) + 1
                    total_parts = len(duplicates)
                    val = f"{title} ({part_num} of {total_parts})"
                else:
                    val = title
            elif issue.category == "reading_order":
                val = "Reorder slide shapes to follow logical visual reading sequence"
            elif issue.category == "animations":
                val = "Clear animations to ensure static visibility"
            elif issue.category == "grouped_objects":
                obj_name = ctx.get("object_name") or (issue.object.name if issue.object else None) or "Diagram"
                val = f"Grouped diagram: {obj_name}"
            elif issue.category == "alt_text":
                obj_name = ctx.get("object_name") or (issue.object.name if issue.object else None) or "Diagram"
                val = f"Illustration: {obj_name}"
            else:
                obj_name = ctx.get("object_name") or (issue.object.name if issue.object else None) or "Diagram"
                val = obj_name

        fix_type = _issue_to_fix_type(issue)
        if fix_type:
            fixes.append({
                "issue_id": issue.id,
                "type": fix_type,
                "slide_index": slide_idx,
                "shape_id": shape_id,
                "value": val,
                "applied_by": "auto",
            })

    if not fixes:
        return {"message": "No safe fixes available", "fixes_count": 0}

    task_id = str(uuid.uuid4())
    dispatched = False
    if is_celery_available():
        try:
            task = celery_app.send_task(
                "app.tasks.analysis_tasks.apply_safe_fixes",
                args=[presentation_id, fixes],
            )
            task_id = task.id
            dispatched = True
        except Exception:
            dispatched = False

    if not dispatched:
        background_tasks.add_task(_run_fixes_fallback, presentation_id, fixes, task_id)

    return {"task_id": task_id, "fixes_queued": len(fixes)}


def _issue_to_fix_type(issue: AccessibilityIssue) -> Optional[str]:
    mapping = {
        "alt_text": "set_alt_text",
        "charts": "set_chart_description",
        "smart_art": "set_alt_text",
        "language": "set_language",
        "tables": "set_table_header",
        "grouped_objects": "set_alt_text",
        "slide_title": "set_slide_title",
        "animations": "remove_animations",
        "reading_order": "set_reading_order",
    }
    return mapping.get(issue.category)


@router.get("/{presentation_id}/verify", response_model=VerificationResponse)
@router.post("/{presentation_id}/verify", response_model=VerificationResponse)
async def verify_originality(
    presentation_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    pres_result = await db.execute(
        select(Presentation).where(
            Presentation.id == presentation_id,
            Presentation.user_id == current_user.id
        )
    )
    pres = pres_result.scalar_one_or_none()
    if not pres:
        raise HTTPException(status_code=404, detail="Presentation not found")

    result = await db.execute(
        select(VerificationResult)
        .where(VerificationResult.presentation_id == presentation_id)
        .order_by(desc(VerificationResult.created_at))
        .limit(1)
    )
    verification = result.scalar_one_or_none()
    if not verification:
        raise HTTPException(status_code=404, detail="No verification result found")
    return verification


@router.get("/{presentation_id}/report")
async def get_reports(
    presentation_id: str,
    format: Optional[str] = Query(default=None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    pres_result = await db.execute(
        select(Presentation).where(
            Presentation.id == presentation_id,
            Presentation.user_id == current_user.id
        )
    )
    pres = pres_result.scalar_one_or_none()
    if not pres:
        raise HTTPException(status_code=404, detail="Presentation not found")

    if format and format in ("html", "csv", "json"):
        issues_res = await db.execute(
            select(AccessibilityIssue).where(AccessibilityIssue.presentation_id == presentation_id)
        )
        issues = issues_res.scalars().all()
        report_data = generate_report_data(pres, list(issues))
        content, content_type = render_report(report_data, format)
        ext = "html" if format == "html" else ("csv" if format == "csv" else "json")
        filename = f"accessibility_report_{pres.id[:8]}.{ext}"
        return Response(
            content=content,
            media_type=content_type,
            headers={"Content-Disposition": f'attachment; filename="{filename}"'}
        )

    result = await db.execute(
        select(Report).where(Report.presentation_id == presentation_id)
    )
    reports = result.scalars().all()
    response = []
    for r in reports:
        url = storage_service.generate_presigned_url(r.s3_key) if r.s3_key else None
        response.append(ReportResponse(
            id=r.id, format=r.format, file_size=r.file_size,
            created_at=r.created_at, download_url=url
        ))
    return response


@router.post("/{presentation_id}/report/generate", response_model=dict)
async def generate_report(
    presentation_id: str,
    background_tasks: BackgroundTasks,
    format: str = Query(default="json", enum=["json", "html", "csv"]),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    pres_result = await db.execute(
        select(Presentation).where(
            Presentation.id == presentation_id,
            Presentation.user_id == current_user.id
        )
    )
    if not pres_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Presentation not found")

    task_id = str(uuid.uuid4())
    dispatched = False
    if is_celery_available():
        try:
            task = celery_app.send_task(
                "app.tasks.analysis_tasks.generate_report",
                args=[presentation_id, format],
            )
            task_id = task.id
            dispatched = True
        except Exception:
            dispatched = False

    if not dispatched:
        background_tasks.add_task(_run_report_fallback, presentation_id, format, task_id)

    return {"task_id": task_id, "format": format}


@router.get("/{presentation_id}/download")
async def download_processed(
    presentation_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    pres_result = await db.execute(
        select(Presentation).where(
            Presentation.id == presentation_id,
            Presentation.user_id == current_user.id
        )
    )
    pres = pres_result.scalar_one_or_none()
    if not pres:
        raise HTTPException(status_code=404, detail="Presentation not found")

    key = pres.processed_s3_key or pres.original_s3_key
    if not key:
        raise HTTPException(status_code=404, detail="No file available for download")

    file_bytes = storage_service.download_file(key)
    if not file_bytes:
        raise HTTPException(status_code=404, detail="File could not be retrieved")

    orig_name = pres.original_filename or "presentation.pptx"
    filename = f"accessible_{orig_name}"
    return Response(
        content=file_bytes,
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )


@router.get("/{presentation_id}/outline")
async def get_presentation_outline(
    presentation_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    pres_result = await db.execute(
        select(Presentation).where(
            Presentation.id == presentation_id,
            Presentation.user_id == current_user.id
        )
    )
    pres = pres_result.scalar_one_or_none()
    if not pres:
        raise HTTPException(status_code=404, detail="Presentation not found")

    result = await db.execute(
        select(Slide)
        .options(selectinload(Slide.objects))
        .where(Slide.presentation_id == presentation_id)
        .order_by(Slide.slide_index.asc())
    )
    slides = result.scalars().all()

    outline = []
    for s in slides:
        text_objects = [
            obj for obj in s.objects
            if obj.text_content and obj.text_content.strip()
        ]
        text_objects.sort(key=lambda o: (o.reading_order if o.reading_order is not None else 999))

        slide_title = s.title or (text_objects[0].text_content.split("\n")[0] if text_objects else f"Slide {s.slide_number}")

        body_items = []
        for obj in text_objects:
            lines = [line.strip() for line in obj.text_content.split("\n") if line.strip()]
            for line in lines:
                if line != slide_title and line not in body_items:
                    body_items.append(line)

        outline.append({
            "slide_id": s.id,
            "slide_index": s.slide_index,
            "slide_number": s.slide_number,
            "title": slide_title,
            "items": body_items,
        })

    return {"presentation_id": presentation_id, "slides_count": len(slides), "outline": outline}


@router.post("/{presentation_id}/fix-reading-order", response_model=ReadingOrderFixResponse)
async def fix_presentation_reading_order_endpoint(
    presentation_id: str,
    use_ai: bool = Query(default=False),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Real Reading Order CORRECTION feature:
    1. Reads the presentation file.
    2. Analyzes reading order of ALL slides.
    3. Reorders the actual slide objects in the underlying PPTX XML structure (p:spTree).
    4. Preserves visual appearance (zero coordinate/style shift).
    5. Saves the modified PPTX package without overwriting the original file.
    6. Re-opens and re-parses the generated PPTX to verify that Microsoft PowerPoint's
       Reading Order pane reflects the corrected sequence.
    7. Updates presentation records, stores the corrected PPTX, and provides download.
    """
    pres_result = await db.execute(
        select(Presentation).where(
            Presentation.id == presentation_id,
            Presentation.user_id == current_user.id
        )
    )
    pres = pres_result.scalar_one_or_none()
    if not pres:
        raise HTTPException(status_code=404, detail="Presentation not found")

    source_key = pres.processed_s3_key or pres.original_s3_key
    if not source_key:
        raise HTTPException(status_code=400, detail="No presentation file found")

    with tempfile.NamedTemporaryFile(suffix=".pptx", delete=False) as in_tmp, \
         tempfile.NamedTemporaryFile(suffix=".pptx", delete=False) as out_tmp:
        in_path = in_tmp.name
        out_path = out_tmp.name

    try:
        if not storage_service.download_to_path(source_key, in_path):
            raise HTTPException(status_code=500, detail="Failed to retrieve presentation file")

        # Run real PPTX shape reordering & verification
        fix_result = reading_order_service.fix_presentation_reading_order(
            input_pptx_path=in_path,
            output_pptx_path=out_path,
            use_ai_fallback=use_ai,
        )

        # Upload corrected PPTX to storage
        with open(out_path, "rb") as f:
            corrected_bytes = f.read()

        stem = Path(pres.filename).stem
        new_filename = f"{stem}_reading_order_fixed.pptx"
        new_s3_key = storage_service.make_key(f"processed/{presentation_id}", new_filename)
        storage_service.upload_file(
            corrected_bytes,
            new_s3_key,
            "application/vnd.openxmlformats-officedocument.presentationml.presentation"
        )

        # Update presentation record
        pres.processed_s3_key = new_s3_key
        pres.status = "complete"

        # Update Slide and SlideObject records in DB to reflect the new reading order
        post_analysis = fix_result.get("post_analysis")
        if post_analysis:
            post_analysis["presentation_id"] = presentation_id
            report_bytes = json.dumps(post_analysis).encode("utf-8")
            storage_service.upload_file(report_bytes, f"reading_order/{presentation_id}.json", "application/json")

            slides_db_result = await db.execute(
                select(Slide).options(selectinload(Slide.objects)).where(Slide.presentation_id == presentation_id)
            )
            db_slides = {s.slide_index: s for s in slides_db_result.scalars().all()}
            for s_res in post_analysis.get("slides", []):
                idx = s_res["slide_index"]
                db_s = db_slides.get(idx)
                if db_s:
                    obj_map = {obj.shape_id: obj for obj in db_s.objects if obj.shape_id is not None}
                    for rec_item in s_res.get("current_sequence", []):
                        sid = rec_item["shape_id"]
                        if sid in obj_map:
                            obj_map[sid].reading_order = rec_item["current_position"]

        await db.commit()
        await db.refresh(pres)

        verification_status = fix_result["summary"]["verification_status"]
        is_success = verification_status in ("SUCCESS", "PARTIAL", "MANUAL_REVIEW")

        return {
            "success": is_success,
            "presentation_id": presentation_id,
            "message": "Reading order fixed and verified in PPTX." if verification_status == "SUCCESS" else "Reading order partially corrected.",
            "summary": fix_result["summary"],
            "slides": fix_result["slides"],
            "download_url": f"/api/v1/presentations/{presentation_id}/download",
        }

    except HTTPException:
        raise
    except Exception as e:
        from app.core.logging import logger
        logger.error("Fix reading order failed", error=str(e), presentation_id=presentation_id)
        raise HTTPException(status_code=500, detail=f"Reading order correction failed: {str(e)}")
    finally:
        for p in (in_path, out_path):
            if os.path.exists(p):
                try:
                    os.remove(p)
                except Exception:
                    pass


@router.post("/{presentation_id}/sync-reading-order")
async def sync_presentation_reading_order(
    presentation_id: str,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Delegate to real reading order fix endpoint
    return await fix_presentation_reading_order_endpoint(
        presentation_id=presentation_id,
        use_ai=False,
        db=db,
        current_user=current_user,
    )


@router.post("/{presentation_id}/check-reading-order", response_model=ReadingOrderCheckResponse)
async def check_presentation_reading_order(
    presentation_id: str,
    use_ai: bool = Query(default=False),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Validate PowerPoint slide reading order without modifying original presentation.
    Analyzes OOXML shape tree document order slide-by-slide against WCAG 2.1 AA logical reading flow.
    """
    pres_result = await db.execute(
        select(Presentation).where(
            Presentation.id == presentation_id,
            Presentation.user_id == current_user.id
        )
    )
    pres = pres_result.scalar_one_or_none()
    if not pres:
        raise HTTPException(status_code=404, detail="Presentation not found")

    if not pres.original_s3_key:
        raise HTTPException(status_code=400, detail="No presentation file found")

    with tempfile.NamedTemporaryFile(suffix=".pptx", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        if not storage_service.download_to_path(pres.original_s3_key, tmp_path):
            raise HTTPException(status_code=500, detail="Failed to retrieve presentation file")

        analysis = reading_order_service.analyze_presentation(tmp_path, use_ai_fallback=use_ai)
        analysis["presentation_id"] = presentation_id

        # Update SlideObject reading_order in database for future queries without modifying PPTX
        slides_db_result = await db.execute(
            select(Slide).options(selectinload(Slide.objects)).where(Slide.presentation_id == presentation_id)
        )
        db_slides = {s.slide_index: s for s in slides_db_result.scalars().all()}

        for s_res in analysis.get("slides", []):
            idx = s_res["slide_index"]
            db_s = db_slides.get(idx)
            if db_s:
                obj_map = {obj.shape_id: obj for obj in db_s.objects if obj.shape_id is not None}
                for rec_item in s_res.get("recommended_sequence", []):
                    sid = rec_item.get("shape_id")
                    if sid is not None and sid in obj_map:
                        obj_map[sid].reading_order = rec_item.get("recommended_position", rec_item.get("current_position", 1))

        await db.commit()

        # Cache report in storage
        report_bytes = json.dumps(analysis).encode("utf-8")
        storage_service.upload_file(report_bytes, f"reading_order/{presentation_id}.json", "application/json")

        return analysis
    except HTTPException:
        raise
    except Exception as e:
        from app.core.logging import logger
        logger.error("Reading order check failed", error=str(e), presentation_id=presentation_id)
        raise HTTPException(status_code=500, detail=f"Reading order analysis failed: {str(e)}")
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


@router.get("/{presentation_id}/reading-order", response_model=ReadingOrderCheckResponse)
async def get_presentation_reading_order(
    presentation_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Retrieve existing reading order validation report, or compute on the fly if not yet generated."""
    pres_result = await db.execute(
        select(Presentation).where(
            Presentation.id == presentation_id,
            Presentation.user_id == current_user.id
        )
    )
    pres = pres_result.scalar_one_or_none()
    if not pres:
        raise HTTPException(status_code=404, detail="Presentation not found")

    key = f"reading_order/{presentation_id}.json"
    cached_data = storage_service.download_file(key)
    if cached_data:
        try:
            cached_json = json.loads(cached_data.decode("utf-8"))
            return ReadingOrderCheckResponse.model_validate(cached_json)
        except Exception:
            pass

    return await check_presentation_reading_order(presentation_id, use_ai=False, db=db, current_user=current_user)


@router.get("/{presentation_id}/reading-order/debug-report")
async def download_reading_order_debug_report(
    presentation_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """STEP 8: Download comprehensive reading order debug report in JSON format."""
    pres_result = await db.execute(
        select(Presentation).where(
            Presentation.id == presentation_id,
            Presentation.user_id == current_user.id
        )
    )
    pres = pres_result.scalar_one_or_none()
    if not pres:
        raise HTTPException(status_code=404, detail="Presentation not found")

    key = f"reading_order/{presentation_id}.json"
    cached_data = storage_service.download_file(key)
    if not cached_data:
        await check_presentation_reading_order(presentation_id, use_ai=False, db=db, current_user=current_user)
        cached_data = storage_service.download_file(key)

    filename = f"{Path(pres.filename).stem}_reading_order_debug.json"
    return Response(
        content=cached_data or b"{}",
        media_type="application/json",
        headers={"Content-Disposition": f"attachment; filename=\"{filename}\""}
    )

