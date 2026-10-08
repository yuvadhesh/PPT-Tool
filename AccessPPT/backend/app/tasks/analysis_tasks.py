"""
Celery background tasks for PPTX analysis, remediation, and report generation.
"""
import os
import tempfile
from datetime import datetime, timezone

from celery import Task

from app.workers.celery_app import celery_app
from app.db.session import SyncSessionLocal
from app.core.logging import logger


class DatabaseTask(Task):
    """Base task with DB session management."""
    abstract = True

    def get_db(self):
        return SyncSessionLocal()


@celery_app.task(
    bind=True,
    base=DatabaseTask,
    name="app.tasks.analysis_tasks.analyze_presentation",
    max_retries=2,
    soft_time_limit=600,
    time_limit=700,
)
def analyze_presentation(self, presentation_id: str, pptx_path: str, run_ai: bool = True):
    """
    Full accessibility analysis pipeline:
    1. Parse PPTX
    2. Store slides and objects in DB
    3. Run deterministic checks
    4. Run Gemini AI semantic analysis
    5. Calculate score
    """
    from app.models.presentation import Presentation, PresentationStatus
    from app.models.slide import Slide, SlideObject
    from app.models.accessibility import AnalysisRun
    from app.services.pptx_parser import pptx_parser
    from app.services.accessibility_analyzer import AccessibilityAnalyzer

    db = self.get_db()
    try:
        # Update task ID on presentation
        pres = db.query(Presentation).filter(Presentation.id == presentation_id).first()
        if not pres:
            logger.error("Presentation not found", id=presentation_id)
            return {"error": "Presentation not found"}

        pres.status = PresentationStatus.PARSING
        pres.celery_task_id = self.request.id
        db.commit()

        # Create analysis run
        run = AnalysisRun(
            presentation_id=presentation_id,
            celery_task_id=self.request.id,
            status="running",
            progress=0,
            current_step="Starting analysis...",
            started_at=datetime.now(timezone.utc),
            steps_completed={
                "uploaded": True,
                "parsing": False,
                "rule_checks": False,
                "ai_analysis": False,
                "scoring": False,
            },
        )
        db.add(run)
        db.commit()

        # Step 1: Parse PPTX
        logger.info("Parsing PPTX", path=pptx_path)
        run.current_step = "Parsing PPTX..."
        run.progress = 10
        db.commit()

        parsed = pptx_parser.parse_presentation(pptx_path)

        # Step 2: Store slides in DB
        run.current_step = f"Processing {parsed['slide_count']} slides..."
        run.progress = 25
        pres.slide_count = parsed["slide_count"]
        pres.pptx_width_emu = parsed.get("slide_width_emu")
        pres.pptx_height_emu = parsed.get("slide_height_emu")
        pres.presentation_language = parsed.get("presentation_language")
        pres.status = PresentationStatus.ANALYZING
        db.commit()

        total_objects = 0
        for slide_data in parsed["slides"]:
            # Check if slide already exists (idempotent)
            existing_slide = db.query(Slide).filter(
                Slide.presentation_id == presentation_id,
                Slide.slide_index == slide_data["slide_index"],
            ).first()

            if existing_slide:
                db_slide = existing_slide
            else:
                db_slide = Slide(
                    presentation_id=presentation_id,
                    slide_index=slide_data["slide_index"],
                    slide_number=slide_data["slide_number"],
                    title=slide_data.get("title"),
                    title_placeholder_id=slide_data.get("title_placeholder_id"),
                    speaker_notes=slide_data.get("speaker_notes"),
                    has_notes=slide_data.get("has_notes", False),
                    slide_xml_hash=slide_data.get("slide_xml_hash"),
                )
                db.add(db_slide)
                db.flush()

            for obj_data in slide_data.get("objects", []):
                existing_obj = db.query(SlideObject).filter(
                    SlideObject.slide_id == db_slide.id,
                    SlideObject.shape_id == obj_data.get("shape_id"),
                ).first()

                if not existing_obj:
                    db_obj = SlideObject(
                        slide_id=db_slide.id,
                        presentation_id=presentation_id,
                        shape_id=obj_data.get("shape_id"),
                        name=obj_data.get("name"),
                        object_type=obj_data.get("object_type", "other"),
                        left_emu=obj_data.get("left_emu"),
                        top_emu=obj_data.get("top_emu"),
                        width_emu=obj_data.get("width_emu"),
                        height_emu=obj_data.get("height_emu"),
                        text_content=obj_data.get("text_content"),
                        alt_text=obj_data.get("alt_text"),
                        alt_text_title=obj_data.get("alt_text_title"),
                        is_decorative=obj_data.get("is_decorative"),
                        has_audio=obj_data.get("has_audio", False),
                        has_video=obj_data.get("has_video", False),
                        has_animation=obj_data.get("has_animation", False),
                        chart_title=obj_data.get("chart_title"),
                        has_table_headers=obj_data.get("has_table_headers"),
                        image_hash=obj_data.get("image_hash"),
                        extra_data=obj_data.get("extra_data"),
                    )
                    db.add(db_obj)
                    total_objects += 1

        db.commit()
        pres.object_count = total_objects
        run.steps_completed["parsing"] = True
        db.commit()

        # Step 3 & 4: Run checks
        run.current_step = "Running accessibility checks..."
        run.progress = 40
        pres.status = PresentationStatus.AI_ANALYSIS if run_ai else PresentationStatus.ANALYZING
        db.commit()

        analyzer = AccessibilityAnalyzer(db, presentation_id, pptx_path, run_ai=run_ai)
        result = analyzer.analyze(run)

        run.steps_completed["rule_checks"] = True
        run.steps_completed["ai_analysis"] = run_ai
        run.steps_completed["scoring"] = True
        run.status = "complete"
        run.progress = 100
        run.completed_at = datetime.now(timezone.utc)
        pres.status = PresentationStatus.COMPLETE
        db.commit()

        logger.info(
            "Analysis complete",
            presentation_id=presentation_id,
            score=result["score"],
        )
        return {"success": True, "score": result["score"], "issues": result["issue_counts"]}

    except Exception as e:
        logger.error("Analysis task failed", error=str(e), presentation_id=presentation_id)
        try:
            pres = db.query(Presentation).filter(Presentation.id == presentation_id).first()
            if pres:
                pres.status = "failed"
                pres.error_message = str(e)
                db.commit()
        except Exception:
            pass
        raise self.retry(exc=e, countdown=10)
    finally:
        db.close()


@celery_app.task(
    bind=True,
    base=DatabaseTask,
    name="app.tasks.analysis_tasks.apply_safe_fixes",
    max_retries=1,
    soft_time_limit=300,
    time_limit=350,
)
def apply_safe_fixes(self, presentation_id: str, fixes: list[dict]):
    """Apply approved safe accessibility fixes and verify originality."""
    from app.models.presentation import Presentation, PresentationStatus
    from app.models.accessibility import AccessibilityIssue, RemediationAction, VerificationResult
    from app.services.storage_service import storage_service
    from app.services.remediation_service import remediation_service
    from app.services.originality_checker import originality_checker

    db = self.get_db()
    try:
        pres = db.query(Presentation).filter(Presentation.id == presentation_id).first()
        if not pres or not pres.original_s3_key:
            return {"error": "Presentation or original file not found"}

        pres.status = PresentationStatus.REMEDIATING
        db.commit()

        with tempfile.TemporaryDirectory() as tmp_dir:
            original_path = os.path.join(tmp_dir, "original.pptx")
            processed_path = os.path.join(tmp_dir, "processed.pptx")
            input_path = os.path.join(tmp_dir, "input.pptx")

            # Download original for verification
            if not storage_service.download_to_path(pres.original_s3_key, original_path):
                return {"error": "Failed to download original PPTX"}

            # Download current processed PPTX (or original if first run) to preserve cumulative fixes
            source_key = pres.processed_s3_key or pres.original_s3_key
            if not storage_service.download_to_path(source_key, input_path):
                return {"error": "Failed to download base PPTX"}

            # Apply fixes onto input_path
            success, error_msg = remediation_service.apply_fixes(input_path, processed_path, fixes)
            if not success:
                return {"error": error_msg}

            # Log remediation actions and mark issues as fixed
            fixed_ids = []
            for fix in fixes:
                iid = fix.get("issue_id", "")
                if iid:
                    fixed_ids.append(iid)
                action = RemediationAction(
                    issue_id=iid,
                    presentation_id=presentation_id,
                    action_type=fix.get("type", ""),
                    action_data=fix,
                    applied_by=fix.get("applied_by", "auto"),
                    success=True,
                )
                db.add(action)

                if fix.get("type") == "set_slide_title":
                    s_idx = fix.get("slide_index")
                    new_val = fix.get("value")
                    if s_idx is not None and new_val:
                        from app.models.slide import Slide
                        db.query(Slide).filter(
                            Slide.presentation_id == presentation_id,
                            Slide.slide_index == s_idx,
                        ).update({"title": new_val}, synchronize_session=False)

            if fixed_ids:
                db.query(AccessibilityIssue).filter(
                    AccessibilityIssue.presentation_id == presentation_id,
                    AccessibilityIssue.id.in_(fixed_ids),
                ).update({"status": "fixed"}, synchronize_session=False)

            # Verify originality
            pres.status = PresentationStatus.VERIFYING
            db.commit()

            result = originality_checker.check(original_path, processed_path)
            verification = VerificationResult(
                presentation_id=presentation_id,
                status=result.status,
                visual_changes=result.visual_changes,
                content_changes=result.content_changes,
                layout_changes=result.layout_changes,
                accessibility_changes=result.accessibility_changes,
                details=result.to_dict(),
            )
            db.add(verification)

            if result.status == "failed":
                pres.status = "verification_failed"
                db.commit()
                return {"error": "Verification failed", "details": result.to_dict()}

            # Recalculate metrics
            from app.services.accessibility_analyzer import calculate_score

            total_issues = db.query(AccessibilityIssue).filter(
                AccessibilityIssue.presentation_id == presentation_id
            ).count()
            open_errors = db.query(AccessibilityIssue).filter(
                AccessibilityIssue.presentation_id == presentation_id,
                AccessibilityIssue.status == "open",
                AccessibilityIssue.severity == "error"
            ).count()
            open_warnings = db.query(AccessibilityIssue).filter(
                AccessibilityIssue.presentation_id == presentation_id,
                AccessibilityIssue.status == "open",
                AccessibilityIssue.severity == "warning"
            ).count()
            open_reviews = db.query(AccessibilityIssue).filter(
                AccessibilityIssue.presentation_id == presentation_id,
                AccessibilityIssue.status == "open",
                AccessibilityIssue.severity == "review"
            ).count()
            fixed_count = db.query(AccessibilityIssue).filter(
                AccessibilityIssue.presentation_id == presentation_id,
                AccessibilityIssue.status == "fixed"
            ).count()

            pres.error_count = open_errors
            pres.warning_count = open_warnings
            pres.review_count = open_reviews
            pres.pass_count = fixed_count
            pres.accessibility_score = calculate_score(open_errors, open_warnings, open_reviews, fixed_count)

            # Upload processed PPTX
            processed_key = storage_service.make_key(
                f"processed/{presentation_id}", pres.original_filename
            )
            storage_service.upload_from_path(processed_path, processed_key)
            pres.processed_s3_key = processed_key
            pres.status = PresentationStatus.COMPLETE
            db.commit()

        return {
            "success": True,
            "verification": result.to_dict(),
            "fixes_applied": len(fixes),
        }

    except Exception as e:
        logger.error("Fix task failed", error=str(e))
        raise self.retry(exc=e, countdown=10)
    finally:
        db.close()


@celery_app.task(
    bind=True,
    base=DatabaseTask,
    name="app.tasks.analysis_tasks.generate_report",
    max_retries=1,
    soft_time_limit=120,
    time_limit=150,
)
def generate_report(self, presentation_id: str, format: str = "json"):
    """Generate accessibility report in specified format."""
    from app.models.presentation import Presentation
    from app.models.accessibility import AccessibilityIssue, AISuggestion, Report
    from app.services.storage_service import storage_service
    from app.services.report_generator import generate_report_data, render_report

    db = self.get_db()
    try:
        pres = db.query(Presentation).filter(Presentation.id == presentation_id).first()
        if not pres:
            return {"error": "Presentation not found"}

        issues = db.query(AccessibilityIssue).filter(
            AccessibilityIssue.presentation_id == presentation_id
        ).all()

        report_data = generate_report_data(pres, issues)
        content, content_type = render_report(report_data, format)

        key = storage_service.make_key(
            f"reports/{presentation_id}", f"report.{format}"
        )
        storage_service.upload_file(content, key, content_type)

        report = Report(
            presentation_id=presentation_id,
            format=format,
            s3_key=key,
            file_size=len(content),
        )
        db.add(report)
        db.commit()

        return {"success": True, "key": key, "format": format}

    except Exception as e:
        logger.error("Report generation failed", error=str(e))
        raise
    finally:
        db.close()
