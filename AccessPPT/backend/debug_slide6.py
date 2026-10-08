import os
import pptx
from app.services.reading_order_service import reading_order_service

deck_in = "before_reorder_slide4.pptx"
prs = pptx.Presentation(deck_in)
slide = prs.slides[5] # Slide 6 (0-indexed 5)

sw = prs.slide_width
sh = prs.slide_height

pre = reading_order_service.analyze_slide(slide, 5, sw, sh, use_ai_fallback=False)
print("=== Slide 6 PRE ===")
print("Current IDs:", [o["shape_id"] for o in pre["current_sequence"]])
print("Recommended IDs:", [o["shape_id"] for o in pre["recommended_sequence"]])
for o in pre["recommended_sequence"]:
    print(f"  Rec: ID={o['shape_id']}, type={o['object_type']}, name={o['shape_name']}, ph={o['placeholder_type']}")

title_shape = reading_order_service._detect_primary_title_shape(slide, sh)
title_id = title_shape.shape_id if title_shape else None
print("Title shape:", title_id, getattr(title_shape, "name", None))

seq_applied, is_safe, reason = reading_order_service._enforce_z_order_safety(slide, pre["recommended_sequence"], title_id)
print("Safe?", is_safe, reason)
print("Applied IDs:", [o["shape_id"] for o in seq_applied])

# What does fix_presentation_reading_order do right now?
# Line 1240 was: seq_to_apply, is_safe, safety_reason = self._enforce_z_order_safety(slide, pre["recommended_sequence"])
seq_without_title, is_safe2, reason2 = reading_order_service._enforce_z_order_safety(slide, pre["recommended_sequence"])
print("Applied without title IDs:", [o["shape_id"] for o in seq_without_title])
