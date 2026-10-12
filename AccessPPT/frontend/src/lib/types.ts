export type Severity = "error" | "warning" | "review" | "pass";

export type IssueCategory =
  | "slide_title"
  | "alt_text"
  | "decorative"
  | "reading_order"
  | "tables"
  | "color_contrast"
  | "color_meaning"
  | "hyperlinks"
  | "font_size"
  | "language"
  | "images_with_text"
  | "charts"
  | "smart_art"
  | "audio"
  | "video"
  | "animations"
  | "speaker_notes"
  | "grouped_objects";

export interface User {
  id: string;
  email: string;
  full_name: string;
  is_active: boolean;
  is_superuser: boolean;
  created_at: string;
}

export interface Presentation {
  id: string;
  user_id: string;
  filename: string;
  original_filename: string;
  file_size: number;
  slide_count: number | null;
  object_count: number | null;
  accessibility_score: number | null;
  error_count: number;
  warning_count: number;
  review_count: number;
  pass_count: number;
  status:
    | "uploaded"
    | "parsing"
    | "analyzing"
    | "ai_analysis"
    | "remediating"
    | "verifying"
    | "complete"
    | "failed"
    | "verification_failed";
  celery_task_id?: string | null;
  error_message?: string | null;
  presentation_language?: string | null;
  original_s3_key?: string | null;
  processed_s3_key?: string | null;
  report_s3_key?: string | null;
  created_at: string;
  updated_at: string;
}

export interface Slide {
  id: string;
  presentation_id: string;
  slide_index: number;
  slide_number: number;
  title: string | null;
  title_placeholder_id?: string | null;
  speaker_notes: string | null;
  has_notes: boolean;
  accessibility_score: number | null;
  error_count: number;
  warning_count: number;
  thumbnail_s3_key?: string | null;
  objects?: SlideObject[];
  created_at: string;
}

export interface OutlineSlide {
  slide_id: string;
  slide_index: number;
  slide_number: number;
  title: string;
  items: string[];
}

export interface SlideObject {
  id: string;
  slide_id: string;
  presentation_id: string;
  shape_id?: number | null;
  name?: string | null;
  object_type: string;
  left_emu?: number | null;
  top_emu?: number | null;
  width_emu?: number | null;
  height_emu?: number | null;
  text_content?: string | null;
  alt_text?: string | null;
  alt_text_title?: string | null;
  is_decorative?: boolean | null;
  reading_order?: number | null;
  has_audio: boolean;
  has_video: boolean;
  has_animation: boolean;
  chart_title?: string | null;
  has_table_headers?: boolean | null;
  image_hash?: string | null;
  image_s3_key?: string | null;
  ai_analyzed: boolean;
  ai_suggestions?: any;
}

export interface AccessibilityIssue {
  id: string;
  presentation_id: string;
  slide_id?: string | null;
  object_id?: string | null;
  rule_id: string;
  category: IssueCategory;
  severity: Severity;
  title: string;
  description: string;
  why_it_matters?: string | null;
  recommendation?: string | null;
  standard_reference?: string | null;
  context_data?: any;
  auto_fix_supported: boolean;
  manual_review_required: boolean;
  status: "open" | "fixed" | "ignored" | "pending_review";
  ai_analyzed: boolean;
  ai_suggestion?: string | null;
  ai_confidence?: number | null;
  ai_confidence_level?: "high" | "medium" | "low" | null;
  created_at: string;
  fixed_at?: string | null;
}

export interface VerificationResult {
  id: string;
  presentation_id: string;
  status: "passed" | "failed";
  visual_changes: number;
  content_changes: number;
  layout_changes: number;
  accessibility_changes: number;
  details?: {
    verified_elements?: number;
    visual_fidelity_score?: number;
    diffs_detected?: string[];
    safe_modifications?: string[];
  };
}

export interface DashboardStats {
  total_presentations: number;
  total_slides_analyzed: number;
  avg_accessibility_score: number;
  total_issues_fixed?: number;
  presentations_above_90?: number;
  issues_by_severity: {
    error: number;
    warning: number;
    review: number;
    pass: number;
  };
  issues_summary?: Record<string, number>;
  recent_presentations: Presentation[];
}

export interface AnalysisRun {
  id: string;
  presentation_id?: string;
  status: "pending" | "running" | "complete" | "failed";
  progress: number;
  current_step?: string | null;
  error_message?: string | null;
  started_at?: string | null;
  completed_at?: string | null;
}

export interface ReadingOrderItem {
  shape_id: number;
  name: string;
  object_type: string;
  semantic_role: string;
  placeholder_type?: string | null;
  is_placeholder?: boolean;
  is_title: boolean;
  text_snippet: string | null;
  alt_text: string | null;
  is_decorative: boolean;
  current_position: number;
  recommended_position: number;
  is_misplaced: boolean;
  norm_left: number;
  norm_top: number;
  norm_width: number;
  norm_height: number;
}

export interface ReadingOrderIssue {
  code: string;
  severity: string;
  affected_shape_ids: number[];
  shape_name: string;
  current_position: number;
  recommended_position: number;
  description: string;
  suggestion: string;
}

export interface SlideReadingOrder {
  slide_index: number;
  slide_number: number;
  title: string | null;
  status: "PASS" | "FAIL";
  total_objects: number;
  sequence_display: string;
  issues: ReadingOrderIssue[];
  current_sequence: ReadingOrderItem[];
  recommended_sequence: ReadingOrderItem[];
  preview_objects: ReadingOrderItem[];
  layout_type?: string;
  confidence?: "HIGH" | "MEDIUM" | "LOW" | string;
  is_safe?: boolean;
  safety_reason?: string | null;
  manual_review_reason?: string | null;
}

export interface ReadingOrderSummary {
  total_slides_checked: number;
  slides_passed: number;
  slides_failed: number;
  total_issues: number;
  compliance_rate: number;
}

export interface ReadingOrderReport {
  presentation_id: string;
  summary: ReadingOrderSummary;
  slide_width_emu: number;
  slide_height_emu: number;
  slides: SlideReadingOrder[];
}

export interface SlideFixDetail {
  slide_index: number;
  slide_number: number;
  title: string | null;
  status: "fixed" | "already_correct" | "manual_review" | "error";
  before_status: "PASS" | "FAIL";
  after_status: "PASS" | "FAIL";
  issues_before: number;
  issues_after: number;
  current_sequence: ReadingOrderItem[];
  recommended_sequence: ReadingOrderItem[];
  error_message?: string | null;
  layout_type?: string;
  confidence?: "HIGH" | "MEDIUM" | "LOW" | string;
  manual_review_reason?: string | null;
}

export interface ReadingOrderFixSummary {
  total_slides: number;
  already_correct: number;
  fixed: number;
  manual_review?: number;
  failed: number;
  issues_remaining: number;
  verification_status: "SUCCESS" | "PARTIAL" | "MANUAL_REVIEW" | "FAILED";
}

export interface ReadingOrderFixResult {
  success: boolean;
  presentation_id: string;
  message: string;
  summary: ReadingOrderFixSummary;
  slides: SlideFixDetail[];
  download_url: string;
}


export interface EquationGeometry {
  x: number;
  y: number;
  cx: number;
  cy: number;
  rot: number;
  flip_h: boolean;
  flip_v: boolean;
}

export type EquationCategory =
  | "omml"
  | "mathtype_ole"
  | "equation_editor_ole"
  | "other_equation_ole"
  | "math_text"
  | "image";

export type EquationEligibility = "eligible" | "already_mathtype" | "needs_review" | "pending";

export interface EquationCandidate {
  id: string;
  slide_number: number;
  shape_id: number;
  shape_name: string;
  category: EquationCategory;
  placement: "standalone_shape" | "inline_text" | "table_cell";
  geometry: EquationGeometry;
  group_path: string[];
  text: string;
  mathml?: string | null;
  constructs: string[];
  unsupported: string[];
  prog_id?: string | null;
  font_size_pt?: number | null;
  confidence: string;
  eligibility: EquationEligibility;
  reason: string;
  unit_id?: string | null;
}

export interface EquationInventory {
  slide_count: number;
  total: number;
  by_category: Partial<Record<EquationCategory, number>>;
  by_eligibility: Partial<Record<EquationEligibility, number>>;
  category_labels: Record<EquationCategory, string>;
  slides: { slide_number: number; equations: EquationCandidate[] }[];
}

export interface MathTypeIntegrationStatus {
  adapter: string;
  available: boolean;
  mathtype_version?: string | null;
  conversion_method?: string | null;
  requires_user_interaction: boolean;
  details: string;
  guidance: string[];
}

export interface EquationReportItem {
  id: string;
  slide_number: number;
  shape_id: number;
  shape_name: string;
  category: EquationCategory;
  text: string;
  status: "converted" | "failed" | "skipped" | "needs_review";
  reason: string;
}

export interface EquationConversionReport {
  generated_at: string;
  adapter: MathTypeIntegrationStatus;
  original_sha256: string;
  summary: {
    before: Partial<Record<EquationCategory, number>>;
    after: Partial<Record<EquationCategory, number>>;
    converted: number;
    failed: number;
    skipped: number;
    needs_review: number;
  };
  validation: { passed: boolean; checks: { name: string; passed: boolean; detail: string }[] };
  items: EquationReportItem[];
}

export interface EquationState {
  status: "idle" | "scanned" | "queued" | "running" | "complete" | "failed" | "unavailable";
  progress: number;
  current_step?: string | null;
  error?: string | null;
  converted_available?: boolean;
  scan?: EquationInventory;
  report?: EquationConversionReport | null;
  updated_at?: string;
}
