import os
import tempfile
import pptx
from app.services.reading_order_service import reading_order_service

deck_in = "before_reorder_slide4.pptx"
prs = pptx.Presentation(deck_in)
sh = prs.slide_height

print("Testing all slides with title_id passed to enforce_z_order_safety:")
for idx, slide in enumerate(prs.slides):
    slide_num = idx + 1
    pre = reading_order_service.analyze_slide(slide, idx, prs.slide_width, sh, use_ai_fallback=False)
    title_shape = reading_order_service._detect_primary_title_shape(slide, sh)
    title_id = title_shape.shape_id if title_shape else None
    
    seq_to_apply, is_safe, reason = reading_order_service._enforce_z_order_safety(slide, pre["recommended_sequence"], title_id)
    rec_ids = [o["shape_id"] for o in pre["recommended_sequence"]]
    apply_ids = [o["shape_id"] for o in seq_to_apply]
    
    if rec_ids != apply_ids:
        print(f"Slide {slide_num}: rec_ids != apply_ids! diff: {rec_ids} vs {apply_ids}")
    if not is_safe:
        print(f"Slide {slide_num}: not safe: {reason}")
