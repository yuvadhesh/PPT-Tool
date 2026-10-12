"""
Equation → MathType API: scan a presentation for equations, convert eligible ones
via the configured MathType adapter, and download the result and report.
"""
import json
import os
import tempfile
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_user
from app.db.session import get_db
from app.models.presentation import Presentation
from app.models.user import User
from app.services.equations import state_store
from app.services.equations.mathtype_adapter import get_mathtype_adapter
from app.services.equations.pipeline import scan_file
from app.services.storage_service import storage_service
from app.workers.celery_app import celery_app, is_celery_available

router = APIRouter(tags=["equations"])


async def _get_presentation(presentation_id: str, db: AsyncSession, user: User) -> Presentation:
    res = await db.execute(
        select(Presentation).where(Presentation.id == presentation_id, Presentation.user_id == user.id)
    )
    pres = res.scalar_one_or_none()
    if not pres:
        raise HTTPException(status_code=404, detail="Presentation not found")
    if not pres.original_s3_key:
        raise HTTPException(status_code=404, detail="Original presentation file not found")
    return pres


@router.get("/equations/integration")
async def get_integration_status(current_user: User = Depends(get_current_user)):
    """Report whether a supported MathType integration is configured and reachable."""
    return get_mathtype_adapter().status().to_dict()


@router.post("/presentations/{presentation_id}/equations/scan")
async def scan_equations(
    presentation_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    pres = await _get_presentation(presentation_id, db, current_user)
    data = storage_service.download_file(pres.original_s3_key)
    if not data:
        raise HTTPException(status_code=404, detail="File could not be retrieved")
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "scan.pptx")
        with open(path, "wb") as f:
            f.write(data)
        try:
            inventory = scan_file(path)
        except Exception as e:
            raise HTTPException(status_code=422, detail=f"Could not read presentation: {e}")
    state = state_store.load_state(presentation_id)
    if state.get("status") not in ("running", "queued"):
        state_store.save_state(presentation_id, status="scanned", progress=0, scan=inventory, error=None)
    else:
        state_store.save_state(presentation_id, scan=inventory)
    return inventory


@router.post("/presentations/{presentation_id}/equations/convert")
async def convert_equations(
    presentation_id: str,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _get_presentation(presentation_id, db, current_user)
    status = get_mathtype_adapter().status()
    if not status.available:
        state_store.save_state(presentation_id, status="unavailable", error=status.details)
        raise HTTPException(status_code=409, detail=f"MathType is unavailable: {status.details}")
    if state_store.load_state(presentation_id).get("status") in ("queued", "running"):
        raise HTTPException(status_code=409, detail="A conversion is already running")

    task_id = str(uuid.uuid4())
    state_store.save_state(
        presentation_id, status="queued", progress=0, current_step="Queued", task_id=task_id,
        error=None, converted_available=False,
    )
    queued = False
    if is_celery_available():
        try:
            celery_app.send_task(
                "app.tasks.equation_tasks.convert_equations", args=[presentation_id], task_id=task_id
            )
            queued = True
        except Exception:
            queued = False
    if not queued:
        from app.tasks.equation_tasks import run_equation_conversion
        background_tasks.add_task(run_equation_conversion, presentation_id)
    return {"task_id": task_id, "status": "queued"}


@router.get("/presentations/{presentation_id}/equations")
async def get_equation_state(
    presentation_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _get_presentation(presentation_id, db, current_user)
    state = state_store.load_state(presentation_id)
    state["report"] = state_store.get_report(presentation_id) if state.get("status") in ("complete", "failed") else None
    return state


@router.get("/presentations/{presentation_id}/equations/download")
async def download_converted(
    presentation_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    pres = await _get_presentation(presentation_id, db, current_user)
    if not state_store.load_state(presentation_id).get("converted_available"):
        raise HTTPException(status_code=404, detail="No validated converted presentation is available")
    data = storage_service.download_file(state_store.converted_key(presentation_id))
    if not data:
        raise HTTPException(status_code=404, detail="Converted file could not be retrieved")
    name = f"mathtype_{pres.original_filename or 'presentation.pptx'}"
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )


@router.get("/presentations/{presentation_id}/equations/report")
async def download_report(
    presentation_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _get_presentation(presentation_id, db, current_user)
    report = state_store.get_report(presentation_id)
    if report is None:
        raise HTTPException(status_code=404, detail="No conversion report yet")
    return Response(
        content=json.dumps(report, indent=2),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="equation_report_{presentation_id}.json"'},
    )
