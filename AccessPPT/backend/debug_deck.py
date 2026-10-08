import os
import tempfile
from app.services.reading_order_service import reading_order_service

deck_in = "before_reorder_slide4.pptx"
with tempfile.TemporaryDirectory() as tmp:
    out = os.path.join(tmp, "out.pptx")
    res = reading_order_service.fix_presentation_reading_order(deck_in, out)
    print("Summary:", res["summary"])
    for s in res["slides"]:
        if s["status"] != "already_correct" and s["after_status"] != "PASS":
            print(f"Slide {s['slide_number']}: status={s['status']}, after_status={s['after_status']}, issues_after={s['issues_after']}, err={s['error_message']}")
