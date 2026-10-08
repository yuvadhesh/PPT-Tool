"""
Accessibility Analyzer — runs deterministic rules and coordinates AI analysis.
"""
import hashlib
from typing import Optional
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.services.rule_engine import (
    RULES, RuleViolation, is_filename_alt_text, is_generic_title, is_generic_link_text
)
from app.services.pptx_parser import pptx_parser, _calculate_contrast_ratio
from app.services.gemini_service import gemini_service
from app.models.presentation import Presentation
from app.models.slide import Slide, SlideObject
from app.models.accessibility import (
    AccessibilityIssue, AISuggestion, AnalysisRun, IssueStatus
)
from app.core.logging import logger


SEVERITY_WEIGHTS = {"error": 10, "warning": 5, "review": 2, "pass": 0}


def calculate_score(errors: int, warnings: int, reviews: int, passes: int) -> float:
    """Calculate accessibility score 0-100."""
    total = errors + warnings + reviews + passes
    if total == 0:
        return 100.0
    penalty = (errors * 10 + warnings * 5 + reviews * 2)
    max_penalty = total * 10
    score = max(0.0, 100.0 - (penalty / max_penalty * 100.0))
    return round(score, 1)


class AccessibilityAnalyzer:
    """
    Runs all accessibility checks on a parsed PPTX.
    Deterministic checks run first; AI checks augment with semantic analysis.
    """

    def __init__(self, db: Session, presentation_id: str, pptx_path: str, run_ai: bool = True):
        self.db = db
        self.presentation_id = presentation_id
        self.pptx_path = pptx_path
        self.run_ai = run_ai
        self.issues: list[AccessibilityIssue] = []
        self.ai_suggestions: list[AISuggestion] = []

    def analyze(self, analysis_run: AnalysisRun) -> dict:
        """Main entry point — parse + run all checks."""
        self._update_run(analysis_run, 5, "Parsing PPTX...")
        parsed = pptx_parser.parse_presentation(self.pptx_path)

        self._update_run(analysis_run, 20, "Running deterministic accessibility checks...")
        slides_data = parsed["slides"]
        all_titles = [s.get("title") for s in slides_data]
        duplicate_titles = parsed.get("duplicate_titles", {})

        db_slides = self.db.query(Slide).filter(
            Slide.presentation_id == self.presentation_id
        ).order_by(Slide.slide_index).all()

        db_objects: dict[tuple, SlideObject] = {}
        for slide in db_slides:
            for obj in slide.objects:
                db_objects[(slide.slide_index, obj.shape_id)] = obj

        # Run per-slide checks
        for slide_data in slides_data:
            slide_idx = slide_data["slide_index"]
            slide_num = slide_data["slide_number"]
            db_slide = next((s for s in db_slides if s.slide_index == slide_idx), None)
            if not db_slide:
                continue

            self._check_slide_title(slide_data, db_slide, duplicate_titles)
            self._check_animations(slide_data, db_slide)
            self._check_reading_order(slide_data, db_slide)
            self._check_outline_view(slide_data, db_slide)

            for obj_data in slide_data.get("objects", []):
                db_obj = db_objects.get((slide_idx, obj_data.get("shape_id")))
                self._check_object(obj_data, slide_data, db_slide, db_obj)

        # Presentation-level checks
        self._check_language(parsed)

        # Commit deterministic issues
        for issue in self.issues:
            self.db.add(issue)
        self.db.commit()

        # AI analysis
        if self.run_ai and gemini_service.is_enabled:
            self._update_run(analysis_run, 60, "Running Gemini AI semantic analysis...")
            self._run_ai_analysis(slides_data, db_slides, db_objects, analysis_run)
            for sug in self.ai_suggestions:
                self.db.add(sug)
            self.db.commit()

        # Count and score
        self._update_run(analysis_run, 90, "Computing accessibility score...")
        issue_counts = self._count_issues()
        score = calculate_score(
            issue_counts["error"],
            issue_counts["warning"],
            issue_counts["review"],
            issue_counts["pass"],
        )

        # Update presentation
        pres = self.db.query(Presentation).filter(Presentation.id == self.presentation_id).first()
        if pres:
            pres.accessibility_score = score
            pres.error_count = issue_counts["error"]
            pres.warning_count = issue_counts["warning"]
            pres.review_count = issue_counts["review"]
            pres.pass_count = issue_counts["pass"]
            pres.status = "complete"
            self.db.commit()

        self._update_run(analysis_run, 100, "Analysis complete.")
        return {
            "score": score,
            "issue_counts": issue_counts,
        }

    def _update_run(self, run: AnalysisRun, progress: int, step: str):
        run.progress = progress
        run.current_step = step
        self.db.commit()
        logger.info("Analysis progress", progress=progress, step=step)

    def _create_issue(
        self,
        rule_id: str,
        slide: Optional[Slide] = None,
        db_object: Optional[SlideObject] = None,
        context_data: Optional[dict] = None,
        ai_suggestion: Optional[str] = None,
        ai_confidence: Optional[float] = None,
    ) -> AccessibilityIssue:
        rule = RULES[rule_id]
        issue = AccessibilityIssue(
            presentation_id=self.presentation_id,
            slide_id=slide.id if slide else None,
            object_id=db_object.id if db_object else None,
            rule_id=rule.rule_id,
            category=rule.category,
            severity=rule.severity,
            title=rule.title,
            description=rule.description,
            why_it_matters=rule.why_it_matters,
            recommendation=rule.recommendation,
            standard_reference=rule.standard_reference,
            auto_fix_supported=rule.auto_fix_supported,
            manual_review_required=rule.manual_review_required,
            context_data=context_data or {},
            status=IssueStatus.OPEN,
            ai_suggestion=ai_suggestion,
            ai_confidence=ai_confidence,
        )
        if ai_confidence is not None:
            issue.ai_analyzed = True
            issue.ai_confidence_level = (
                "high" if ai_confidence >= 0.9
                else "medium" if ai_confidence >= 0.7
                else "low"
            )
        self.issues.append(issue)
        return issue

    def _check_slide_title(self, slide_data: dict, db_slide: Slide, duplicate_titles: dict):
        title = slide_data.get("title")
        slide_num = slide_data["slide_number"]

        if title is None:
            self._create_issue("TITLE-001", slide=db_slide,
                                context_data={"slide_number": slide_num})
        elif not title.strip():
            self._create_issue("TITLE-002", slide=db_slide,
                                context_data={"slide_number": slide_num})
        else:
            if is_generic_title(title):
                self._create_issue("TITLE-004", slide=db_slide,
                                    context_data={"title": title, "slide_number": slide_num})
            t_lower = title.lower().strip()
            if t_lower in duplicate_titles and len(duplicate_titles[t_lower]) > 1:
                self._create_issue("TITLE-003", slide=db_slide,
                                    context_data={"title": title, "duplicates": duplicate_titles[t_lower]})

    def _check_animations(self, slide_data: dict, db_slide: Slide):
        if slide_data.get("has_animations"):
            self._create_issue("ANIM-001", slide=db_slide, context_data={
                "animation_count": slide_data.get("animation_count", 0),
            })

    def _check_reading_order(self, slide_data: dict, db_slide: Slide):
        objects = slide_data.get("objects", [])
        if len(objects) <= 1:
            return

        title_shape_id = slide_data.get("title_placeholder_id")

        def visual_sort_key(obj):
            shape_id = str(obj.get("shape_id"))
            if title_shape_id and shape_id == title_shape_id:
                return (-1, 0, 0)
            top = obj.get("top_emu") or 0
            left = obj.get("left_emu") or 0
            row = round(top / 350000) if top else 0
            return (0, row, left)

        visual_order = sorted(objects, key=visual_sort_key)
        current_ids = [obj.get("shape_id") for obj in objects]
        desired_ids = [obj.get("shape_id") for obj in visual_order]

        if current_ids != desired_ids:
            self._create_issue(
                "ORDER-001",
                slide=db_slide,
                context_data={
                    "slide_index": slide_data["slide_index"],
                    "slide_number": slide_data["slide_number"],
                    "total_objects": len(objects),
                    "reading_order_fix_available": True,
                },
                ai_suggestion="Reorder shapes to follow logical top-to-bottom reading sequence with title first.",
                ai_confidence=0.95,
            )

    def _check_outline_view(self, slide_data: dict, db_slide: Slide):
        """
        Check if slide title is accessible in PowerPoint Outline View.
        Slides missing an actual title placeholder cannot show titles in Outline View or screen reader slide list.
        """
        title = slide_data.get("title")
        title_placeholder_id = slide_data.get("title_placeholder_id")
        slide_num = slide_data["slide_number"]

        if not title or not title_placeholder_id:
            # If TITLE-001 or TITLE-002 is not already present, flag outline view issue
            existing_title_issues = [
                i for i in self.issues
                if i.slide_id == db_slide.id and i.category == "slide_title"
            ]
            if not existing_title_issues:
                self._create_issue(
                    "TITLE-001",
                    slide=db_slide,
                    context_data={
                        "slide_number": slide_num,
                        "slide_index": slide_data["slide_index"],
                        "outline_view_warning": True,
                        "reason": "Slide title is missing from title placeholder, preventing display in Outline View.",
                    },
                    ai_suggestion="Assign a proper slide title placeholder for Outline View visibility.",
                    ai_confidence=0.9,
                )

    def _check_object(self, obj_data: dict, slide_data: dict, db_slide: Slide, db_obj: Optional[SlideObject]):
        obj_type = obj_data.get("object_type", "")
        alt_text = obj_data.get("alt_text")
        is_decorative = obj_data.get("is_decorative", False)
        slide_num = slide_data["slide_number"]
        slide_idx = slide_data["slide_index"]
        ctx = {
            "slide_number": slide_num,
            "slide_index": slide_idx,
            "shape_id": obj_data.get("shape_id"),
            "object_name": obj_data.get("name"),
            "object_type": obj_type,
        }

        # Alt text checks for images / charts / SmartArt
        if obj_type in ("image", "chart", "smart_art", "group"):
            if not is_decorative:
                if alt_text is None:
                    rule_id = "CHART-001" if obj_type == "chart" else "SMART-001" if obj_type == "smart_art" else "ALT-001"
                    self._create_issue(rule_id, slide=db_slide, db_object=db_obj, context_data=ctx)
                elif not alt_text.strip():
                    self._create_issue("ALT-002", slide=db_slide, db_object=db_obj, context_data=ctx)
                elif is_filename_alt_text(alt_text):
                    self._create_issue("ALT-003", slide=db_slide, db_object=db_obj,
                                        context_data={**ctx, "alt_text": alt_text})
                elif len(alt_text) < 5:
                    self._create_issue("ALT-004", slide=db_slide, db_object=db_obj,
                                        context_data={**ctx, "alt_text": alt_text})

        # Chart checks
        if obj_type == "chart":
            extra = obj_data.get("extra_data", {})
            if not extra.get("has_legend") and extra.get("series_count", 0) > 1:
                pass  # Could add chart-specific rule

            chart_title = obj_data.get("chart_title")
            if not chart_title:
                self._create_issue("CHART-002", slide=db_slide, db_object=db_obj, context_data=ctx)

        # Table checks
        if obj_type == "table":
            extra = obj_data.get("extra_data", {})
            if not extra.get("has_header_row", False):
                self._create_issue("TABLE-001", slide=db_slide, db_object=db_obj, context_data={
                    **ctx, "rows": extra.get("rows"), "cols": extra.get("cols")
                })
            if extra.get("empty_cells", 0) > 0:
                self._create_issue("TABLE-002", slide=db_slide, db_object=db_obj, context_data={
                    **ctx, "empty_cells": extra.get("empty_cells")
                })
            if extra.get("is_complex", False):
                self._create_issue("TABLE-003", slide=db_slide, db_object=db_obj, context_data=ctx)

        # Font size checks
        font_sizes = obj_data.get("font_sizes", [])
        for size in font_sizes:
            if size < 10:
                self._create_issue("FONT-001", slide=db_slide, db_object=db_obj, context_data={
                    **ctx, "font_size": size
                })
                break

        # Hyperlink checks
        for link in obj_data.get("hyperlinks", []):
            text = link.get("text", "").strip()
            if not text:
                self._create_issue("LINK-001", slide=db_slide, db_object=db_obj, context_data={
                    **ctx, "url": link.get("url")
                })
            elif is_generic_link_text(text):
                self._create_issue("LINK-002", slide=db_slide, db_object=db_obj, context_data={
                    **ctx, "link_text": text, "url": link.get("url")
                })

        # Media checks
        if obj_data.get("has_audio"):
            self._create_issue("MEDIA-001", slide=db_slide, db_object=db_obj, context_data=ctx)
        if obj_data.get("has_video"):
            self._create_issue("MEDIA-002", slide=db_slide, db_object=db_obj, context_data=ctx)

        # Grouped objects
        if obj_type == "group":
            if not alt_text and not is_decorative:
                self._create_issue("GROUP-001", slide=db_slide, db_object=db_obj, context_data=ctx)

    def _check_language(self, parsed: dict):
        if not parsed.get("presentation_language"):
            self._create_issue("LANG-001", context_data={})

    def _run_ai_analysis(self, slides_data: list, db_slides: list, db_objects: dict, analysis_run: Optional[AnalysisRun] = None):
        """Run Gemini AI on objects needing semantic analysis."""
        total_slides = len(slides_data)
        ai_calls_made = 0
        max_ai_calls = 12

        for s_idx, slide_data in enumerate(slides_data, start=1):
            if analysis_run and total_slides > 0:
                current_pct = min(88, 60 + int((s_idx / total_slides) * 26))
                self._update_run(analysis_run, current_pct, f"Gemini AI analyzing slide {s_idx} of {total_slides}...")

            slide_index = slide_data["slide_index"]
            db_slide = next((s for s in db_slides if s.slide_index == slide_index), None)
            if not db_slide:
                continue

            for obj_data in slide_data.get("objects", []):
                if ai_calls_made >= max_ai_calls:
                    break

                obj_type = obj_data.get("object_type", "")
                db_obj = db_objects.get((slide_index, obj_data.get("shape_id")))
                if not db_obj:
                    continue

                alt_text = obj_data.get("alt_text")
                image_data = None

                # Get image for vision-capable checks
                if obj_type in ("image", "chart"):
                    try:
                        image_data = pptx_parser.get_image_data(
                            self.pptx_path, slide_index, obj_data["shape_id"]
                        )
                    except Exception:
                        pass

                # Alt text quality evaluation
                if obj_type in ("image", "chart", "smart_art") and not obj_data.get("is_decorative"):
                    existing = alt_text
                    if not existing or len(existing.strip()) < 30:
                        result = gemini_service.analyze_alt_text(
                            existing_alt=existing,
                            image_data=image_data,
                            slide_context=slide_data.get("title") or "",
                            object_name=obj_data.get("name") or "",
                        )
                        ai_calls_made += 1
                        sug = AISuggestion(
                            presentation_id=self.presentation_id,
                            object_id=db_obj.id,
                            check_type="alt_text",
                            result=result.result,
                            confidence=result.confidence,
                            confidence_level=result.confidence_level,
                            reason=result.reason,
                            suggestion=result.suggestion,
                            is_valid=result.confidence > 0,
                            human_review_recommended=result.human_review_recommended,
                        )
                        self.ai_suggestions.append(sug)

                        # Update matching issue with AI suggestion
                        for issue in self.issues:
                            if (issue.object_id == (db_obj.id if db_obj else None) and
                                    issue.category == "alt_text"):
                                issue.ai_analyzed = True
                                issue.ai_suggestion = result.suggestion
                                issue.ai_confidence = result.confidence
                                issue.ai_confidence_level = result.confidence_level

                # Chart description
                if obj_type == "chart" and image_data:
                    result = gemini_service.analyze_chart(
                        image_data=image_data,
                        chart_title=obj_data.get("chart_title") or "",
                    )
                    sug = AISuggestion(
                        presentation_id=self.presentation_id,
                        object_id=db_obj.id,
                        check_type="chart_description",
                        result=result.result,
                        confidence=result.confidence,
                        confidence_level=result.confidence_level,
                        reason=result.reason,
                        suggestion=result.suggestion,
                        is_valid=result.confidence > 0,
                        human_review_recommended=result.human_review_recommended,
                    )
                    self.ai_suggestions.append(sug)

    def _count_issues(self) -> dict:
        from app.models.accessibility import AccessibilityIssue as AIssue
        from sqlalchemy import func
        counts = (
            self.db.query(AIssue.severity, func.count(AIssue.id))
            .filter(AIssue.presentation_id == self.presentation_id)
            .group_by(AIssue.severity)
            .all()
        )
        result = {"error": 0, "warning": 0, "review": 0, "pass": 0}
        for severity, count in counts:
            if severity in result:
                result[severity] = count
        return result


analyzer_factory = AccessibilityAnalyzer
