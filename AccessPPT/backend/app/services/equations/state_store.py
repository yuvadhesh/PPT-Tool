"""Persists per-presentation equation scan/conversion state via the storage service."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Optional

from app.services.storage_service import storage_service


def state_key(presentation_id: str) -> str:
    return f"equations/{presentation_id}/state.json"


def converted_key(presentation_id: str) -> str:
    return f"equations/{presentation_id}/converted.pptx"


def report_key(presentation_id: str) -> str:
    return f"equations/{presentation_id}/report.json"


def load_state(presentation_id: str) -> dict:
    data = storage_service.download_file(state_key(presentation_id))
    if not data:
        return {"status": "idle", "progress": 0}
    try:
        return json.loads(data)
    except ValueError:
        return {"status": "idle", "progress": 0}


def save_state(presentation_id: str, **updates) -> dict:
    state = load_state(presentation_id)
    state.update(updates)
    state["updated_at"] = datetime.now(timezone.utc).isoformat()
    storage_service.upload_file(json.dumps(state).encode("utf-8"), state_key(presentation_id), "application/json")
    return state


def get_report(presentation_id: str) -> Optional[dict]:
    data = storage_service.download_file(report_key(presentation_id))
    return json.loads(data) if data else None
