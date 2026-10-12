"""
MathType integration adapter layer.

MathType is a Windows/macOS desktop application, so it cannot run inside the
Linux backend or its Docker containers. Genuine conversion is delegated to a
Windows worker (see ``AccessPPT/mathtype_worker``) that has MathType installed
and exposes a small HTTP contract:

* ``GET  /health``  -> ``{"available": bool, "mathtype_version": str|null,
  "conversion_method": str|null, "requires_user_interaction": bool, "details": str}``
* ``POST /convert`` -> request ``{"mathml": str, "omml": [str], "font_size_pt": float|null}``;
  response ``{"prog_id": str, "ole_object_b64": str, "preview_b64": str,
  "preview_content_type": str, "width_emu": int, "height_emu": int}``

New MathType versions or integration methods are supported by adding an adapter
class (or a new worker backend) without touching the rest of the pipeline.
"""
from __future__ import annotations

import base64
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from typing import Optional

import httpx

from app.core.config import settings

INSTALL_GUIDANCE = [
    "MathType runs only on Windows or macOS, so it cannot run inside the Linux backend.",
    "On a Windows PC with PowerPoint and MathType installed, run "
    "mathtype_worker/discover_mathtype.ps1 to record the installed version and its supported interfaces.",
    "Start the MathType worker on that PC, then set MATHTYPE_ADAPTER=windows_worker and "
    "MATHTYPE_WORKER_URL=http://<pc>:8765 in the backend .env and restart the backend.",
]


class MathTypeUnavailableError(RuntimeError):
    pass


class MathTypeConversionError(RuntimeError):
    pass


@dataclass
class AdapterStatus:
    adapter: str
    available: bool
    mathtype_version: Optional[str] = None
    conversion_method: Optional[str] = None
    requires_user_interaction: bool = False
    details: str = ""
    guidance: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ConversionRequest:
    unit_id: str
    mathml: str
    omml: list[str]
    font_size_pt: Optional[float] = None


@dataclass
class MathTypeObject:
    prog_id: str
    ole_object: bytes
    preview_image: bytes
    preview_content_type: str
    width_emu: int
    height_emu: int


class MathTypeAdapter(ABC):
    name = "base"

    @abstractmethod
    def status(self) -> AdapterStatus: ...

    @abstractmethod
    def convert(self, request: ConversionRequest) -> MathTypeObject: ...


class UnavailableAdapter(MathTypeAdapter):
    """Default adapter: reports that no supported MathType integration is configured."""

    name = "none"

    def status(self) -> AdapterStatus:
        return AdapterStatus(
            adapter=self.name,
            available=False,
            details="No MathType integration is configured for this server.",
            guidance=INSTALL_GUIDANCE,
        )

    def convert(self, request: ConversionRequest) -> MathTypeObject:
        raise MathTypeUnavailableError("No MathType integration is configured for this server.")


class WindowsWorkerAdapter(MathTypeAdapter):
    """Delegates conversion to a Windows worker that has MathType installed."""

    name = "windows_worker"

    def __init__(self, base_url: str, token: str = "", timeout: float = 60.0):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout = timeout

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.token}"} if self.token else {}

    def status(self) -> AdapterStatus:
        if not self.base_url:
            return AdapterStatus(self.name, False, details="MATHTYPE_WORKER_URL is not set.", guidance=INSTALL_GUIDANCE)
        try:
            resp = httpx.get(f"{self.base_url}/health", headers=self._headers(), timeout=5.0)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            return AdapterStatus(
                self.name, False, details=f"MathType worker at {self.base_url} is unreachable: {e}", guidance=INSTALL_GUIDANCE
            )
        available = bool(data.get("available"))
        return AdapterStatus(
            adapter=self.name,
            available=available,
            mathtype_version=data.get("mathtype_version"),
            conversion_method=data.get("conversion_method"),
            requires_user_interaction=bool(data.get("requires_user_interaction")),
            details=data.get("details", ""),
            guidance=[] if available else INSTALL_GUIDANCE,
        )

    def convert(self, request: ConversionRequest) -> MathTypeObject:
        try:
            resp = httpx.post(
                f"{self.base_url}/convert",
                json={"mathml": request.mathml, "omml": request.omml, "font_size_pt": request.font_size_pt},
                headers=self._headers(),
                timeout=self.timeout,
            )
        except Exception as e:
            raise MathTypeConversionError(f"MathType worker request failed: {e}") from e
        if resp.status_code != 200:
            raise MathTypeConversionError(f"MathType worker returned HTTP {resp.status_code}: {resp.text[:300]}")
        try:
            data = resp.json()
            return MathTypeObject(
                prog_id=data["prog_id"],
                ole_object=base64.b64decode(data["ole_object_b64"]),
                preview_image=base64.b64decode(data["preview_b64"]),
                preview_content_type=data["preview_content_type"],
                width_emu=int(data["width_emu"]),
                height_emu=int(data["height_emu"]),
            )
        except Exception as e:
            raise MathTypeConversionError(f"Malformed MathType worker response: {e}") from e


def get_mathtype_adapter() -> MathTypeAdapter:
    if settings.MATHTYPE_ADAPTER == "windows_worker":
        return WindowsWorkerAdapter(
            settings.MATHTYPE_WORKER_URL, settings.MATHTYPE_WORKER_TOKEN, settings.MATHTYPE_WORKER_TIMEOUT
        )
    return UnavailableAdapter()
