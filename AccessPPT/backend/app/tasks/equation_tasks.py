"""Background job: convert native equations in a presentation to MathType objects."""
import json
import os
import tempfile

from app.core.logging import logger
from app.db.session import SyncSessionLocal
from app.services.equations import state_store
from app.services.equations.mathtype_adapter import MathTypeUnavailableError, get_mathtype_adapter
from app.services.equations.pipeline import convert_file
from app.services.storage_service import storage_service
from app.workers.celery_app import celery_app


def run_equation_conversion(presentation_id: str) -> dict:
    from app.models.presentation import Presentation

    db = SyncSessionLocal()
    try:
        pres = db.query(Presentation).filter(Presentation.id == presentation_id).first()
        source_key = pres.original_s3_key if pres else None
    finally:
        db.close()
    if not source_key:
        state_store.save_state(presentation_id, status="failed", error="Original presentation file not found")
        return {"error": "not found"}

    def progress(pct: int, msg: str):
        state_store.save_state(presentation_id, status="running", progress=pct, current_step=msg)

    with tempfile.TemporaryDirectory() as tmp:
        original = os.path.join(tmp, "original.pptx")
        working = os.path.join(tmp, "working.pptx")
        output = os.path.join(tmp, "converted.pptx")
        if not storage_service.download_to_path(source_key, original):
            state_store.save_state(presentation_id, status="failed", error="Could not read the original file")
            return {"error": "download failed"}
        try:
            report = convert_file(original, working, output, get_mathtype_adapter(), progress)
        except MathTypeUnavailableError as e:
            state_store.save_state(presentation_id, status="unavailable", progress=0, error=str(e))
            return {"error": str(e)}
        except Exception as e:
            logger.error("Equation conversion failed", presentation_id=presentation_id, error=str(e))
            state_store.save_state(presentation_id, status="failed", error=str(e))
            return {"error": str(e)}

        storage_service.upload_file(
            json.dumps(report).encode("utf-8"), state_store.report_key(presentation_id), "application/json"
        )
        has_output = report["validation"]["passed"] and report["summary"]["converted"] > 0
        if has_output:
            storage_service.upload_from_path(output, state_store.converted_key(presentation_id))
        state_store.save_state(
            presentation_id,
            status="complete" if report["validation"]["passed"] else "failed",
            progress=100,
            current_step="Done",
            converted_available=has_output,
            summary=report["summary"],
            error=None if report["validation"]["passed"] else "Output validation failed; converted file withheld.",
        )
        return {"presentation_id": presentation_id, "summary": report["summary"]}


@celery_app.task(name="app.tasks.equation_tasks.convert_equations", soft_time_limit=1800, time_limit=1900)
def convert_equations(presentation_id: str):
    return run_equation_conversion(presentation_id)
