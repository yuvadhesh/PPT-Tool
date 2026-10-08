"""
Integration test for the Check Reading Order API endpoint.
Tests uploading a deck, running reading order check, and validating the response schema.
"""
import os
import tempfile
import pytest
import pptx
from pptx.util import Inches
from fastapi.testclient import TestClient

from app.main import app
from app.core.security import create_access_token


def test_reading_order_api_endpoint():
    client = TestClient(app)

    # 1. Login as demo user
    login_res = client.post(
        "/api/v1/auth/login",
        json={"email": "demo@accessppt.com", "password": "Password123!"},
    )
    assert login_res.status_code == 200, login_res.text
    token = login_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    with tempfile.TemporaryDirectory() as tmp_dir:
        # Create a test deck where title is added after body text (misplaced order in XML)
        deck_path = os.path.join(tmp_dir, "ro_api_test.pptx")
        prs = pptx.Presentation()
        slide = prs.slides.add_slide(prs.slide_layouts[6])

        # Body shape first (pos 1 in XML)
        b = slide.shapes.add_textbox(Inches(1), Inches(3), Inches(4), Inches(2))
        b.text = "Body text that appears before title in XML"

        # Title shape second (pos 2 in XML)
        t = slide.shapes.add_textbox(Inches(1), Inches(0.5), Inches(8), Inches(1))
        t.text = "Executive Summary"

        prs.save(deck_path)

        # 2. Upload presentation
        with open(deck_path, "rb") as f:
            upload_res = client.post(
                "/api/v1/presentations/upload",
                headers=headers,
                files={"file": ("ro_api_test.pptx", f, "application/vnd.openxmlformats-officedocument.presentationml.presentation")},
            )

        assert upload_res.status_code == 201, upload_res.text
        pres_id = upload_res.json()["id"]

        # 3. Call Check Reading Order endpoint
        ro_res = client.post(
            f"/api/v1/presentations/{pres_id}/check-reading-order?use_ai=false",
            headers=headers,
        )
        assert ro_res.status_code == 200, ro_res.text
        data = ro_res.json()

        # 4. Validate response structure
        assert "summary" in data
        assert data["summary"]["total_slides_checked"] == 1
        assert data["summary"]["slides_failed"] == 1
        assert data["summary"]["total_issues"] >= 1

        slide0 = data["slides"][0]
        assert slide0["status"] == "FAIL"
        assert "TITLE_NOT_FIRST" in [i["code"] for i in slide0["issues"]]
        assert len(slide0["current_sequence"]) == 2
        assert len(slide0["recommended_sequence"]) == 2
        assert len(slide0["preview_objects"]) == 2
        assert "Executive Summary" in slide0["sequence_display"]

        # 5. Call GET endpoint
        get_res = client.get(
            f"/api/v1/presentations/{pres_id}/reading-order",
            headers=headers,
        )
        assert get_res.status_code == 200
        get_data = get_res.json()
        assert get_data["summary"]["total_slides_checked"] == 1
        assert get_data["slides"][0]["status"] == "FAIL"

        # 6. Call Fix Reading Order endpoint
        fix_res = client.post(
            f"/api/v1/presentations/{pres_id}/fix-reading-order?use_ai=false",
            headers=headers,
        )
        assert fix_res.status_code == 200, fix_res.text
        fix_data = fix_res.json()
        assert fix_data["success"] is True
        assert fix_data["summary"]["total_slides"] == 1
        assert fix_data["summary"]["fixed"] == 1
        assert fix_data["summary"]["issues_remaining"] == 0
        assert fix_data["summary"]["verification_status"] == "SUCCESS"
        assert len(fix_data["slides"]) == 1
        assert fix_data["slides"][0]["status"] == "fixed"
        assert fix_data["slides"][0]["after_status"] == "PASS"

        # 7. Download corrected PPTX and verify actual internal XML shape sequence
        dl_res = client.get(
            f"/api/v1/presentations/{pres_id}/download",
            headers=headers,
        )
        assert dl_res.status_code == 200
        fixed_deck_path = os.path.join(tmp_dir, "fixed_deck.pptx")
        with open(fixed_deck_path, "wb") as f:
            f.write(dl_res.content)

        fixed_prs = pptx.Presentation(fixed_deck_path)
        fixed_slide = fixed_prs.slides[0]
        # First shape in spTree must now be Executive Summary (Title)
        assert "Executive Summary" in fixed_slide.shapes[0].text
        # Second shape in spTree must now be Body text
        assert "Body text" in fixed_slide.shapes[1].text


if __name__ == "__main__":
    test_reading_order_api_endpoint()
    print("API Integration test passed successfully!")

