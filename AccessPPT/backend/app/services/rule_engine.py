"""
Deterministic Accessibility Rule Engine.
Each rule is independent of AI and produces structured issues.
"""
from dataclasses import dataclass, field
from typing import Optional, Any
import re


@dataclass
class AccessibilityRule:
    rule_id: str
    category: str
    severity: str
    title: str
    description: str
    why_it_matters: str
    recommendation: str
    standard_reference: str
    auto_fix_supported: bool = False
    manual_review_required: bool = False


@dataclass
class RuleViolation:
    rule: AccessibilityRule
    slide_index: Optional[int] = None
    slide_number: Optional[int] = None
    object_name: Optional[str] = None
    object_id: Optional[str] = None
    context_data: dict = field(default_factory=dict)
    ai_needed: bool = False


# ─── Rule Definitions ─────────────────────────────────────────────────────────

RULES: dict[str, AccessibilityRule] = {
    # Alt Text
    "ALT-001": AccessibilityRule(
        rule_id="ALT-001", category="alt_text", severity="error",
        title="Missing Alt Text",
        description="Image has no alternative text.",
        why_it_matters="Screen-reader users cannot understand this visual without alternative text.",
        recommendation="Add descriptive alt text that conveys the content and purpose of the image.",
        standard_reference="WCAG 2.1 Success Criterion 1.1.1",
        auto_fix_supported=True,
        manual_review_required=False,
    ),
    "ALT-002": AccessibilityRule(
        rule_id="ALT-002", category="alt_text", severity="error",
        title="Empty Alt Text on Meaningful Image",
        description="Image has empty alt text but appears to be meaningful.",
        why_it_matters="An empty alt attribute marks an image as decorative. If the image conveys information, screen-reader users will miss it.",
        recommendation="Add descriptive alt text or mark the image as decorative if it adds no information.",
        standard_reference="WCAG 2.1 Success Criterion 1.1.1",
        auto_fix_supported=True,
        manual_review_required=True,
    ),
    "ALT-003": AccessibilityRule(
        rule_id="ALT-003", category="alt_text", severity="warning",
        title="Filename Used as Alt Text",
        description="The alt text appears to be a filename rather than a description.",
        why_it_matters="Filenames like 'image1.png' provide no useful context for screen-reader users.",
        recommendation="Replace the filename alt text with a meaningful description of the image content.",
        standard_reference="WCAG 2.1 Success Criterion 1.1.1",
        auto_fix_supported=True,
        manual_review_required=False,
    ),
    "ALT-004": AccessibilityRule(
        rule_id="ALT-004", category="alt_text", severity="warning",
        title="Very Short Alt Text",
        description="The alt text is extremely short and may not adequately describe the image.",
        why_it_matters="Alt text that is too brief may not convey sufficient information to screen-reader users.",
        recommendation="Expand the alt text to include the content and purpose of the image.",
        standard_reference="WCAG 2.1 Success Criterion 1.1.1",
        auto_fix_supported=True,
        manual_review_required=True,
    ),
    "ALT-005": AccessibilityRule(
        rule_id="ALT-005", category="alt_text", severity="review",
        title="Poor Quality Alt Text",
        description="The alt text may not adequately describe the image content.",
        why_it_matters="Vague or inaccurate alt text is as unhelpful as no alt text for screen-reader users.",
        recommendation="Use AI suggestion to improve the alt text quality.",
        standard_reference="WCAG 2.1 Success Criterion 1.1.1",
        auto_fix_supported=True,
        manual_review_required=True,
    ),
    # Slide Titles
    "TITLE-001": AccessibilityRule(
        rule_id="TITLE-001", category="slide_title", severity="error",
        title="Missing Slide Title",
        description="This slide has no title placeholder.",
        why_it_matters="Screen-reader users rely on slide titles to navigate presentations. Missing titles make navigation impossible.",
        recommendation="Add a title to this slide. Each slide should have a unique, descriptive title.",
        standard_reference="WCAG 2.1 Success Criterion 2.4.6",
        auto_fix_supported=False,
        manual_review_required=True,
    ),
    "TITLE-002": AccessibilityRule(
        rule_id="TITLE-002", category="slide_title", severity="error",
        title="Empty Slide Title",
        description="This slide has a title placeholder but it is empty.",
        why_it_matters="An empty title does not help screen-reader users understand the slide content.",
        recommendation="Add a descriptive title to this slide.",
        standard_reference="WCAG 2.1 Success Criterion 2.4.6",
        auto_fix_supported=False,
        manual_review_required=True,
    ),
    "TITLE-003": AccessibilityRule(
        rule_id="TITLE-003", category="slide_title", severity="warning",
        title="Duplicate Slide Title",
        description="Multiple slides share the same title.",
        why_it_matters="Duplicate titles make it difficult for screen-reader users to navigate to a specific slide.",
        recommendation="Ensure each slide has a unique, descriptive title.",
        standard_reference="WCAG 2.1 Success Criterion 2.4.6",
        auto_fix_supported=True,
        manual_review_required=False,
    ),
    "TITLE-004": AccessibilityRule(
        rule_id="TITLE-004", category="slide_title", severity="warning",
        title="Generic Slide Title",
        description="The slide title appears to be generic (e.g., 'Slide 1', 'Title', 'Untitled').",
        why_it_matters="Generic titles do not help users understand the content of the slide.",
        recommendation="Replace the generic title with a descriptive title that reflects the slide content.",
        standard_reference="WCAG 2.1 Success Criterion 2.4.6",
        auto_fix_supported=False,
        manual_review_required=True,
    ),
    # Reading Order
    "ORDER-001": AccessibilityRule(
        rule_id="ORDER-001", category="reading_order", severity="warning",
        title="Reading Order May Be Illogical",
        description="The reading order of objects on this slide may not match the visual layout.",
        why_it_matters="Screen readers follow the z-order of objects, which may not match the visual reading sequence.",
        recommendation="Verify and correct the reading order using the Selection Pane in PowerPoint.",
        standard_reference="WCAG 2.1 Success Criterion 1.3.2",
        auto_fix_supported=True,
        manual_review_required=True,
    ),
    # Tables
    "TABLE-001": AccessibilityRule(
        rule_id="TABLE-001", category="tables", severity="error",
        title="Table Missing Header Row",
        description="This table does not have a designated header row.",
        why_it_matters="Without header row markup, screen readers cannot associate data cells with their headers.",
        recommendation="Enable the 'Header Row' setting for this table in PowerPoint.",
        standard_reference="WCAG 2.1 Success Criterion 1.3.1",
        auto_fix_supported=True,
        manual_review_required=False,
    ),
    "TABLE-002": AccessibilityRule(
        rule_id="TABLE-002", category="tables", severity="warning",
        title="Table Contains Empty Cells",
        description="This table has empty cells which may confuse screen-reader users.",
        why_it_matters="Empty cells may cause screen readers to skip content or misinterpret the table structure.",
        recommendation="Add placeholder text or merge cells to eliminate unexpected empty cells.",
        standard_reference="WCAG 2.1 Success Criterion 1.3.1",
        auto_fix_supported=False,
        manual_review_required=True,
    ),
    "TABLE-003": AccessibilityRule(
        rule_id="TABLE-003", category="tables", severity="review",
        title="Complex Table Structure",
        description="This table has merged cells or complex structure that may be difficult for screen readers.",
        why_it_matters="Complex tables with merged cells can confuse screen-reader reading order.",
        recommendation="Consider splitting complex tables into simpler structures or adding a text description.",
        standard_reference="WCAG 2.1 Success Criterion 1.3.1",
        auto_fix_supported=False,
        manual_review_required=True,
    ),
    # Color Contrast
    "CONTRAST-001": AccessibilityRule(
        rule_id="CONTRAST-001", category="color_contrast", severity="error",
        title="Insufficient Color Contrast",
        description="Text does not meet the minimum contrast ratio of 4.5:1 for normal text.",
        why_it_matters="Low contrast makes text difficult or impossible to read for users with low vision or color blindness.",
        recommendation="Increase the contrast between the text color and background to at least 4.5:1.",
        standard_reference="WCAG 2.1 Success Criterion 1.4.3",
        auto_fix_supported=False,
        manual_review_required=True,
    ),
    "CONTRAST-002": AccessibilityRule(
        rule_id="CONTRAST-002", category="color_contrast", severity="warning",
        title="Insufficient Contrast for Large Text",
        description="Large text does not meet the minimum contrast ratio of 3:1.",
        why_it_matters="Insufficient contrast for large text makes content difficult to read for users with vision impairments.",
        recommendation="Increase the contrast between large text and its background to at least 3:1.",
        standard_reference="WCAG 2.1 Success Criterion 1.4.3",
        auto_fix_supported=False,
        manual_review_required=True,
    ),
    # Hyperlinks
    "LINK-001": AccessibilityRule(
        rule_id="LINK-001", category="hyperlinks", severity="error",
        title="Empty Hyperlink Text",
        description="A hyperlink has no visible text.",
        why_it_matters="Screen-reader users need descriptive link text to understand where a link goes.",
        recommendation="Add descriptive text to the hyperlink.",
        standard_reference="WCAG 2.1 Success Criterion 2.4.4",
        auto_fix_supported=False,
        manual_review_required=True,
    ),
    "LINK-002": AccessibilityRule(
        rule_id="LINK-002", category="hyperlinks", severity="warning",
        title="Generic Hyperlink Text",
        description="Hyperlink text is generic (e.g., 'click here', 'here', 'link', URL).",
        why_it_matters="Generic link text does not convey the destination or purpose of the link.",
        recommendation="Replace generic link text with a description of the link destination.",
        standard_reference="WCAG 2.1 Success Criterion 2.4.4",
        auto_fix_supported=False,
        manual_review_required=True,
    ),
    # Font Size
    "FONT-001": AccessibilityRule(
        rule_id="FONT-001", category="font_size", severity="warning",
        title="Very Small Font Size",
        description="Text with a font size below 10pt may be difficult to read.",
        why_it_matters="Very small text is inaccessible to users with low vision.",
        recommendation="Use a minimum font size of 18pt for body text and 24pt for headings.",
        standard_reference="WCAG 2.1 Success Criterion 1.4.4",
        auto_fix_supported=False,
        manual_review_required=True,
    ),
    # Language
    "LANG-001": AccessibilityRule(
        rule_id="LANG-001", category="language", severity="warning",
        title="Presentation Language Not Set",
        description="The presentation does not have a language defined.",
        why_it_matters="Screen readers need language metadata to pronounce text correctly.",
        recommendation="Set the presentation language in File > Options > Language.",
        standard_reference="WCAG 2.1 Success Criterion 3.1.1",
        auto_fix_supported=True,
        manual_review_required=False,
    ),
    # Charts
    "CHART-001": AccessibilityRule(
        rule_id="CHART-001", category="charts", severity="error",
        title="Chart Missing Alt Text",
        description="A chart has no alternative text description.",
        why_it_matters="Screen-reader users cannot understand chart data without an alternative description.",
        recommendation="Add a text description of the chart's key findings as alt text.",
        standard_reference="WCAG 2.1 Success Criterion 1.1.1",
        auto_fix_supported=True,
        manual_review_required=False,
    ),
    "CHART-002": AccessibilityRule(
        rule_id="CHART-002", category="charts", severity="warning",
        title="Chart Missing Title",
        description="A chart does not have a title.",
        why_it_matters="A chart title helps all users understand the purpose of the chart.",
        recommendation="Add a descriptive title to the chart.",
        standard_reference="WCAG 2.1 Success Criterion 1.3.1",
        auto_fix_supported=False,
        manual_review_required=True,
    ),
    # SmartArt
    "SMART-001": AccessibilityRule(
        rule_id="SMART-001", category="smart_art", severity="warning",
        title="SmartArt Missing Description",
        description="A SmartArt object has no alternative text description.",
        why_it_matters="Screen-reader users may not be able to understand complex SmartArt without a text description.",
        recommendation="Add alt text describing the structure and meaning of the SmartArt.",
        standard_reference="WCAG 2.1 Success Criterion 1.1.1",
        auto_fix_supported=True,
        manual_review_required=True,
    ),
    # Animations
    "ANIM-001": AccessibilityRule(
        rule_id="ANIM-001", category="animations", severity="review",
        title="Animation May Hide Content",
        description="Content on this slide uses animations that may hide important information.",
        why_it_matters="Users who cannot trigger animations may miss important content.",
        recommendation="Ensure all animated content is also accessible in a non-animated state.",
        standard_reference="WCAG 2.1 Success Criterion 1.3.1",
        auto_fix_supported=True,
        manual_review_required=False,
    ),
    # Media
    "MEDIA-001": AccessibilityRule(
        rule_id="MEDIA-001", category="audio", severity="error",
        title="Audio Missing Transcript",
        description="An audio object does not have an associated transcript.",
        why_it_matters="Users who are deaf or hard of hearing cannot access audio content without a transcript.",
        recommendation="Add a text transcript for all audio content.",
        standard_reference="WCAG 2.1 Success Criterion 1.2.1",
        auto_fix_supported=False,
        manual_review_required=True,
    ),
    "MEDIA-002": AccessibilityRule(
        rule_id="MEDIA-002", category="video", severity="error",
        title="Video Missing Captions",
        description="A video object does not have captions.",
        why_it_matters="Users who are deaf or hard of hearing cannot access spoken video content without captions.",
        recommendation="Add closed captions to all video content.",
        standard_reference="WCAG 2.1 Success Criterion 1.2.2",
        auto_fix_supported=False,
        manual_review_required=True,
    ),
    # Color Meaning
    "COLOR-001": AccessibilityRule(
        rule_id="COLOR-001", category="color_meaning", severity="warning",
        title="Color Used as Only Means of Communication",
        description="Important information may be conveyed using color alone.",
        why_it_matters="Users who are colorblind or using screen readers may miss color-only information.",
        recommendation="Add text labels, icons, or patterns to supplement color-coded information.",
        standard_reference="WCAG 2.1 Success Criterion 1.4.1",
        auto_fix_supported=False,
        manual_review_required=True,
    ),
    # Grouped Objects
    "GROUP-001": AccessibilityRule(
        rule_id="GROUP-001", category="grouped_objects", severity="warning",
        title="Grouped Objects Without Description",
        description="A group of objects has no collective alternative text.",
        why_it_matters="Screen readers may not handle groups correctly without a group description.",
        recommendation="Add alt text to the group that describes the combined meaning of all objects.",
        standard_reference="WCAG 2.1 Success Criterion 1.1.1",
        auto_fix_supported=True,
        manual_review_required=True,
    ),
}


# ─── Helper: Generic title patterns ──────────────────────────────────────────

GENERIC_TITLE_PATTERNS = re.compile(
    r"^(slide\s*\d*|title|untitled|click\s+to\s+(add|edit)\s+title|placeholder\s*\d*|new\s+slide)$",
    re.IGNORECASE
)

FILENAME_PATTERNS = re.compile(
    r"\.(png|jpg|jpeg|gif|bmp|tiff|svg|webp|emf|wmf)$", re.IGNORECASE
)

GENERIC_LINK_PATTERNS = re.compile(
    r"^(click\s+here|here|link|more|read\s+more|www\.|http).*", re.IGNORECASE
)


def is_filename_alt_text(text: str) -> bool:
    return bool(FILENAME_PATTERNS.search(text))


def is_generic_title(text: str) -> bool:
    return bool(GENERIC_TITLE_PATTERNS.match(text.strip()))


def is_generic_link_text(text: str) -> bool:
    return bool(GENERIC_LINK_PATTERNS.match(text.strip()))


def get_rule(rule_id: str) -> Optional[AccessibilityRule]:
    return RULES.get(rule_id)
