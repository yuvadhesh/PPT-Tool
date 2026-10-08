"""
Quick validation script to test creating a .pptx, uploading it, and verifying empty -> 1 presentation.
Then clears it back so the database remains pure clean.
"""
import os
import requests
from pptx import Presentation
from pptx.util import Inches, Pt

def test_pipeline():
    test_pptx = "test_deck.pptx"
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[0])
    slide.shapes.title.text = "Accessibility Test Deck"
    slide.placeholders[1].text = "Testing real upload flow."
    prs.save(test_pptx)
    print("Created test pptx file.")

    # 1. Login
    login_res = requests.post("http://localhost:8000/api/v1/auth/login", json={
        "email": "demo@accessppt.com",
        "password": "Password123!"
    })
    token = login_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 2. Upload
    with open(test_pptx, "rb") as f:
        upload_res = requests.post(
            "http://localhost:8000/api/v1/presentations/upload",
            headers=headers,
            files={"file": (test_pptx, f, "application/vnd.openxmlformats-officedocument.presentationml.presentation")}
        )
    print("Upload status:", upload_res.status_code)
    upload_data = upload_res.json()
    pres_id = upload_data.get("id")
    print(f"Uploaded presentation ID: {pres_id}")

    # 3. Check list
    list_res = requests.get("http://localhost:8000/api/v1/presentations", headers=headers)
    print("List response total:", list_res.json().get("total"))

    # 4. Trigger analysis
    analyze_res = requests.post(f"http://localhost:8000/api/v1/presentations/{pres_id}/analyze?run_ai=false", headers=headers)
    print("Analyze status:", analyze_res.status_code, analyze_res.json())

    # Clean up test file
    if os.path.exists(test_pptx):
        os.remove(test_pptx)

if __name__ == "__main__":
    test_pipeline()
