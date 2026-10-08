"""
Gemini AI Service — isolated provider interface.
All AI calls go through this service. Change the model or provider here without
touching any other part of the application.
"""
import json
import base64
import re
from typing import Optional, Any
import google.generativeai as genai
from pydantic import BaseModel, field_validator

from app.core.config import settings
from app.core.logging import logger


# ─── Pydantic response schemas ───────────────────────────────────────────────

class ConfidenceLevel(str):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


def get_confidence_level(confidence: float) -> str:
    if confidence >= 0.90:
        return "high"
    elif confidence >= 0.70:
        return "medium"
    else:
        return "low"


class GeminiBaseResponse(BaseModel):
    result: Optional[str] = None
    confidence: float = 0.0
    reason: Optional[str] = None
    suggestion: Optional[str] = None

    @property
    def confidence_level(self) -> str:
        return get_confidence_level(self.confidence)

    @property
    def human_review_recommended(self) -> bool:
        return self.confidence < 0.70


class AltTextResponse(GeminiBaseResponse):
    suggestion: str = ""
    is_meaningful: bool = False


class DecorativeImageResponse(GeminiBaseResponse):
    result: str = "meaningful"  # meaningful | decorative
    is_decorative: bool = False


class ChartDescriptionResponse(GeminiBaseResponse):
    description: str = ""


class SlideQualityResponse(GeminiBaseResponse):
    is_meaningful: bool = False
    suggested_title: Optional[str] = None


class ReadingOrderResponse(BaseModel):
    recommended_order: list[int] = []
    reason: str = ""
    confidence: float = 0.0

    @property
    def confidence_level(self) -> str:
        return get_confidence_level(self.confidence)

    @property
    def human_review_recommended(self) -> bool:
        return self.confidence < 0.70


class ColorMeaningResponse(GeminiBaseResponse):
    uses_color_only: bool = False
    affected_elements: list[str] = []
    recommendation: str = ""


class ImageTextResponse(GeminiBaseResponse):
    contains_text: bool = False
    extracted_text: str = ""


class AnimationContentResponse(GeminiBaseResponse):
    has_important_content: bool = False
    content_description: str = ""


# ─── Gemini Service ──────────────────────────────────────────────────────────

class GeminiService:
    """
    Isolated AI service wrapper for Google Gemini.
    Replace the implementation here to swap AI providers.
    """

    def __init__(self):
        if not settings.GEMINI_API_KEY:
            logger.warning("GEMINI_API_KEY not set. AI analysis will return mock results.")
            self._enabled = False
            return

        genai.configure(api_key=settings.GEMINI_API_KEY)
        self._model = genai.GenerativeModel(settings.GEMINI_MODEL)
        self._enabled = True
        logger.info("Gemini AI service initialized", model=settings.GEMINI_MODEL)

    @property
    def is_enabled(self) -> bool:
        return self._enabled

    def _parse_json_response(self, text: str) -> Optional[dict]:
        """Safely parse JSON from Gemini response, handling markdown code blocks."""
        # Strip markdown code blocks
        text = text.strip()
        text = re.sub(r"^```json\s*", "", text)
        text = re.sub(r"^```\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
        text = text.strip()

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            # Try to find JSON object in the text
            match = re.search(r"\{.*\}", text, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group())
                except json.JSONDecodeError:
                    pass
        return None

    def _generate(self, prompt: str, image_data: Optional[bytes] = None, mime_type: str = "image/png") -> Optional[str]:
        """Call Gemini API with optional image."""
        if not self._enabled:
            return None
        try:
            if image_data:
                response = self._model.generate_content([
                    prompt,
                    {"mime_type": mime_type, "data": image_data}
                ])
            else:
                response = self._model.generate_content(prompt)
            return response.text
        except Exception as e:
            logger.error("Gemini API error", error=str(e))
            return None

    def _build_structured_prompt(self, task: str, context: str, output_schema: str) -> str:
        return f"""You are an accessibility expert analyzing PowerPoint presentations.

Task: {task}

Context: {context}

Respond ONLY with valid JSON matching this schema:
{output_schema}

Important:
- Be precise and factual
- Confidence should be between 0.0 and 1.0
- Do not include any text outside the JSON object
"""

    # ─── Public AI Methods ────────────────────────────────────────────────────

    def analyze_alt_text(
        self, existing_alt: Optional[str], image_data: Optional[bytes] = None,
        slide_context: str = "", object_name: str = ""
    ) -> AltTextResponse:
        """Evaluate and/or generate alt text for an image."""
        schema = '''{
  "result": "meaningful|poor|missing",
  "confidence": 0.0-1.0,
  "reason": "brief explanation",
  "suggestion": "proposed alt text",
  "is_meaningful": true|false
}'''
        context = f"""
Object name: {object_name}
Existing alt text: {existing_alt or "(none)"}
Slide context: {slide_context}
"""
        prompt = self._build_structured_prompt(
            "Evaluate the quality of existing alt text and generate improved alt text if needed.",
            context,
            schema
        )
        raw = self._generate(prompt, image_data)
        if not raw:
            return AltTextResponse(confidence=0.0, reason="AI unavailable")

        data = self._parse_json_response(raw)
        if not data:
            logger.warning("Failed to parse Gemini alt text response", raw=raw[:200])
            return AltTextResponse(confidence=0.0, reason="Invalid AI response")

        try:
            return AltTextResponse(**data)
        except Exception as e:
            logger.error("AltTextResponse validation error", error=str(e))
            return AltTextResponse(confidence=0.0, reason="AI response validation failed")

    def analyze_decorative_image(
        self, image_data: Optional[bytes], object_name: str = "", slide_context: str = ""
    ) -> DecorativeImageResponse:
        """Determine if an image is decorative or meaningful."""
        schema = '''{
  "result": "meaningful|decorative",
  "confidence": 0.0-1.0,
  "reason": "brief explanation",
  "is_decorative": true|false
}'''
        context = f"Object name: {object_name}\nSlide context: {slide_context}"
        prompt = self._build_structured_prompt(
            "Determine if this image is decorative (purely visual, adds no information) or meaningful (conveys important information).",
            context, schema
        )
        raw = self._generate(prompt, image_data)
        if not raw:
            return DecorativeImageResponse(confidence=0.0, reason="AI unavailable")

        data = self._parse_json_response(raw)
        if not data:
            return DecorativeImageResponse(confidence=0.0, reason="Invalid AI response")

        try:
            resp = DecorativeImageResponse(**data)
            resp.is_decorative = resp.result == "decorative"
            return resp
        except Exception as e:
            return DecorativeImageResponse(confidence=0.0, reason="AI response validation failed")

    def analyze_chart(
        self, image_data: Optional[bytes], chart_title: str = "", axis_labels: str = ""
    ) -> ChartDescriptionResponse:
        """Generate a meaningful description for a chart."""
        schema = '''{
  "result": "described",
  "confidence": 0.0-1.0,
  "reason": "brief explanation",
  "description": "concise chart description for screen readers"
}'''
        context = f"Chart title: {chart_title or '(none)'}\nAxis labels: {axis_labels or '(none)'}"
        prompt = self._build_structured_prompt(
            "Analyze this chart and generate a concise, meaningful description suitable for screen-reader users.",
            context, schema
        )
        raw = self._generate(prompt, image_data)
        if not raw:
            return ChartDescriptionResponse(confidence=0.0, reason="AI unavailable")

        data = self._parse_json_response(raw)
        if not data:
            return ChartDescriptionResponse(confidence=0.0, reason="Invalid AI response")

        try:
            return ChartDescriptionResponse(**data)
        except Exception:
            return ChartDescriptionResponse(confidence=0.0, reason="AI response validation failed")

    def analyze_slide_title_quality(
        self, title: str, slide_content_summary: str = ""
    ) -> SlideQualityResponse:
        """Evaluate whether the slide title meaningfully describes the slide content."""
        schema = '''{
  "result": "good|poor|generic|missing",
  "confidence": 0.0-1.0,
  "reason": "brief explanation",
  "is_meaningful": true|false,
  "suggested_title": "better title or null"
}'''
        context = f"Slide title: {title or '(none)'}\nSlide content: {slide_content_summary or '(none)'}"
        prompt = self._build_structured_prompt(
            "Evaluate whether this slide title meaningfully describes the slide content.",
            context, schema
        )
        raw = self._generate(prompt)
        if not raw:
            return SlideQualityResponse(confidence=0.0, reason="AI unavailable")

        data = self._parse_json_response(raw)
        if not data:
            return SlideQualityResponse(confidence=0.0, reason="Invalid AI response")

        try:
            return SlideQualityResponse(**data)
        except Exception:
            return SlideQualityResponse(confidence=0.0, reason="AI response validation failed")

    def analyze_reading_order(
        self, objects: list[dict]
    ) -> ReadingOrderResponse:
        """Recommend logical reading order for slide objects."""
        schema = '''{
  "recommended_order": [list of object indices in logical reading order],
  "reason": "explanation",
  "confidence": 0.0-1.0
}'''
        context = "Objects on slide:\n" + "\n".join(
            f"Index {i}: type={o.get('type')}, name={o.get('name')}, "
            f"position=({o.get('left')},{o.get('top')}), text={o.get('text','')[:50]}"
            for i, o in enumerate(objects)
        )
        prompt = self._build_structured_prompt(
            "Analyze these slide objects and recommend the most logical reading order for screen-reader users. "
            "Return indices in the order a screen reader should announce them.",
            context, schema
        )
        raw = self._generate(prompt)
        if not raw:
            return ReadingOrderResponse(confidence=0.0, reason="AI unavailable")

        data = self._parse_json_response(raw)
        if not data:
            return ReadingOrderResponse(confidence=0.0, reason="Invalid AI response")

        try:
            return ReadingOrderResponse(**data)
        except Exception:
            return ReadingOrderResponse(confidence=0.0, reason="AI response validation failed")

    def analyze_color_meaning(
        self, image_data: Optional[bytes], slide_text: str = ""
    ) -> ColorMeaningResponse:
        """Detect if color is the only means of conveying information."""
        schema = '''{
  "result": "color_only|not_color_only",
  "confidence": 0.0-1.0,
  "reason": "brief explanation",
  "uses_color_only": true|false,
  "affected_elements": ["list of elements relying on color only"],
  "recommendation": "suggested fix"
}'''
        context = f"Slide text: {slide_text[:500] or '(none)'}"
        prompt = self._build_structured_prompt(
            "Analyze this slide and determine if any important information is conveyed using color alone "
            "(e.g., red = bad, green = good) without text or icons.",
            context, schema
        )
        raw = self._generate(prompt, image_data)
        if not raw:
            return ColorMeaningResponse(confidence=0.0, reason="AI unavailable")

        data = self._parse_json_response(raw)
        if not data:
            return ColorMeaningResponse(confidence=0.0, reason="Invalid AI response")

        try:
            return ColorMeaningResponse(**data)
        except Exception:
            return ColorMeaningResponse(confidence=0.0, reason="AI response validation failed")

    def analyze_image_text(
        self, image_data: bytes
    ) -> ImageTextResponse:
        """Detect important text content inside images."""
        schema = '''{
  "result": "has_text|no_text",
  "confidence": 0.0-1.0,
  "reason": "brief explanation",
  "contains_text": true|false,
  "extracted_text": "text found in image"
}'''
        prompt = self._build_structured_prompt(
            "Analyze this image and detect any text content embedded within it. "
            "If text is present and important, extract it.",
            "", schema
        )
        raw = self._generate(prompt, image_data)
        if not raw:
            return ImageTextResponse(confidence=0.0, reason="AI unavailable")

        data = self._parse_json_response(raw)
        if not data:
            return ImageTextResponse(confidence=0.0, reason="Invalid AI response")

        try:
            return ImageTextResponse(**data)
        except Exception:
            return ImageTextResponse(confidence=0.0, reason="AI response validation failed")

    def analyze_animation_content(
        self, animation_data: dict
    ) -> AnimationContentResponse:
        """Analyze whether important content is hidden behind animations."""
        schema = '''{
  "result": "important_content|decorative_only",
  "confidence": 0.0-1.0,
  "reason": "brief explanation",
  "has_important_content": true|false,
  "content_description": "description of animated content"
}'''
        context = json.dumps(animation_data, indent=2)
        prompt = self._build_structured_prompt(
            "Analyze this animation data and determine if important information may only be "
            "accessible through animation playback.",
            context, schema
        )
        raw = self._generate(prompt)
        if not raw:
            return AnimationContentResponse(confidence=0.0, reason="AI unavailable")

        data = self._parse_json_response(raw)
        if not data:
            return AnimationContentResponse(confidence=0.0, reason="Invalid AI response")

        try:
            return AnimationContentResponse(**data)
        except Exception:
            return AnimationContentResponse(confidence=0.0, reason="AI response validation failed")


# Singleton
gemini_service = GeminiService()
