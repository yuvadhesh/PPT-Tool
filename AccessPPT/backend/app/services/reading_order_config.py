"""
Reading Order Configuration — Constants, Thresholds, and Rules
Production-Ready Hybrid PowerPoint Reading Order Algorithm according to WCAG 2.1 AA (SC 1.3.2).

All thresholds are named constants relative to slide dimensions.
"""

# ==============================================================================
# STEP 0: READING ORDER SEMANTICS DOCUMENTATION
# ==============================================================================
# 1. Reading Order = Document order of children inside <p:cSld>/<p:spTree>.
# 2. First element in <p:spTree> = Read FIRST by screen readers (JAWS, NVDA, Narrator).
# 3. Z-order in PowerPoint OOXML follows the exact same order:
#    - First element = back-most (rendered first, bottom of visual stack)
#    - Last element  = front-most (rendered last, top of visual stack)
# 4. PowerPoint's GUI Reading Order Pane DISPLAYS the list in REVERSE:
#    - Top item of the GUI pane corresponds to the LAST element in XML (front-most).
#    - Bottom item of the GUI pane corresponds to the FIRST element in XML (read first).
# 5. Internal convention:
#    - reading_index 0 = first read = first in XML (position 1 in 1-based display).
#    - When UI mirrors PowerPoint's pane display, an explicit label is attached.
# ==============================================================================

# ------------------------------------------------------------------------------
# XY-CUT & LAYOUT THRESHOLDS (relative to slide width / height)
# ------------------------------------------------------------------------------
GAP_THRESHOLD_HORIZONTAL = 0.015   # Whitespace gap relative to slide height to cut into rows
GAP_THRESHOLD_VERTICAL = 0.015     # Whitespace gap relative to slide width to cut into columns
SPANNING_WIDTH_RATIO = 0.60        # Width > 60% of region is treated as full-width spanning band
BAND_TOLERANCE_RATIO = 0.04        # Relative tolerance for grouping into horizontal bands (4% slide height)

# ------------------------------------------------------------------------------
# RELATIONSHIPS & GLUING THRESHOLDS
# ------------------------------------------------------------------------------
CAPTION_MAX_WIDTH_RATIO = 1.35     # Caption width <= 1.35 * media width
CAPTION_MAX_GAP_RATIO = 0.08       # Caption vertical gap < 8% slide height (~0.5 in)
CAPTION_HORIZONTAL_OVERLAP = 0.25  # Caption must horizontally overlap media by at least 25%
CAPTION_MAX_TEXT_LEN = 160         # Maximum character length for a caption snippet

HEADING_BODY_X_OVERLAP = 0.50      # Heading glued to body below if horizontal overlap > 50%
HEADING_BODY_MAX_GAP_RATIO = 0.12  # Vertical distance between heading and body < 12% slide height

# ------------------------------------------------------------------------------
# GRID & ALIGNMENT THRESHOLDS
# ------------------------------------------------------------------------------
GRID_ALIGNMENT_AMBIGUITY_THRESHOLD = 0.10  # If row vs column alignment consistency diff < 10%, mark AMBIGUOUS
COLUMN_OVERLAP_CLUSTER_RATIO = 0.35        # Horizontal overlap to cluster into same column
COLUMN_CENTER_DIST_RATIO = 0.12            # Center distance threshold to cluster into same column

# ------------------------------------------------------------------------------
# Z-ORDER & OVERLAP SAFETY THRESHOLDS
# ------------------------------------------------------------------------------
Z_ORDER_OVERLAP_AREA_RATIO = 0.02   # Overlap intersection area > 2% of smaller object triggers check
CONTAINER_CONTAINMENT_RATIO = 0.60  # Background shape contains foreground content if overlap > 60% fg area

# ------------------------------------------------------------------------------
# SCORING & TIE-BREAKER WEIGHTS
# ------------------------------------------------------------------------------
WEIGHT_SEMANTIC = 0.40
WEIGHT_LAYOUT = 0.25
WEIGHT_VERTICAL = 0.15
WEIGHT_HORIZONTAL = 0.10
WEIGHT_GROUPING = 0.05
WEIGHT_RELATIONSHIP = 0.05

# ------------------------------------------------------------------------------
# GEMINI AI FALLBACK CONFIGURATION
# ------------------------------------------------------------------------------
AMBIGUITY_CONFIDENCE_GAP = 0.15     # Trigger AI when top-2 candidate confidence difference < 15%
GEMINI_TEMPERATURE = 0.0            # Strict deterministic output
GEMINI_TEXT_SNIPPET_MAX_LEN = 80    # Compact text snippet limit for AI payload

# Standard slide dimensions in EMUs
DEFAULT_SLIDE_WIDTH_EMU = 9144000   # 10 inches
DEFAULT_SLIDE_HEIGHT_EMU = 6858000  # 7.5 inches
