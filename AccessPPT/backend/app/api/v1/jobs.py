"""
Jobs / Task status API.
"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.db.session import get_db
from app.models.accessibility import AnalysisRun
from app.models.presentation import Presentation
from app.workers.celery_app import celery_app, is_celery_available
from app.schemas import JobStatusResponse

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("/{job_id}", response_model=JobStatusResponse)
async def get_job_status(job_id: str, db: AsyncSession = Depends(get_db)):
    """Get status of an analysis or background task with DB-first lookup."""
    # 1. Query AnalysisRun in database
    result = await db.execute(
        select(AnalysisRun).where(
            (AnalysisRun.celery_task_id == job_id) | (AnalysisRun.presentation_id == job_id)
        ).order_by(AnalysisRun.started_at.desc())
    )
    run = result.scalars().first()
    if run:
        return JobStatusResponse(
            job_id=job_id,
            status=run.status,
            progress=run.progress,
            current_step=run.current_step,
            steps_completed=run.steps_completed,
            result={"presentation_id": run.presentation_id},
            error=run.error_message,
        )

    # 2. Check presentation table directly
    pres_res = await db.execute(
        select(Presentation).where(
            (Presentation.celery_task_id == job_id) | (Presentation.id == job_id)
        )
    )
    pres = pres_res.scalars().first()
    if pres:
        status_val = "complete" if pres.status in ("analyzed", "remediated") else (
            "failed" if pres.status == "error" else "running"
        )
        return JobStatusResponse(
            job_id=job_id,
            status=status_val,
            progress=100 if status_val == "complete" else 50,
            current_step=pres.status,
            steps_completed=None,
            result={"presentation_id": pres.id, "score": pres.accessibility_score},
            error=pres.error_message,
        )

    # 3. Fallback to celery AsyncResult if Celery broker is online
    if is_celery_available():
        try:
            res = celery_app.AsyncResult(job_id)
            status_map = {
                "PENDING": "pending",
                "STARTED": "running",
                "SUCCESS": "complete",
                "FAILURE": "failed",
                "RETRY": "running",
                "REVOKED": "cancelled",
            }
            task_result = res.result if (res.state == "SUCCESS" and isinstance(res.result, dict)) else {}
            error = str(res.result) if res.state == "FAILURE" else None
            return JobStatusResponse(
                job_id=job_id,
                status=status_map.get(res.state, res.state.lower()),
                progress=task_result.get("progress", 100) if task_result else 0,
                current_step=None,
                steps_completed=None,
                result=task_result,
                error=error,
            )
        except Exception:
            pass

    return JobStatusResponse(
        job_id=job_id,
        status="complete",
        progress=100,
        current_step="Completed",
        steps_completed=None,
        result=None,
        error=None,
    )
