# MathType worker (Windows)

MathType is a Windows/macOS desktop application. It cannot run inside the Linux
backend or its Docker containers, so the backend never creates MathType objects
itself. Genuine conversion is delegated to a worker running on a Windows PC that
has PowerPoint and MathType installed.

## Status

| Piece | State |
|-------|-------|
| Backend scan / classification / OMML → MathML | Implemented, works on any OS |
| Backend `WindowsWorkerAdapter` + HTTP contract + output validation | Implemented |
| Windows discovery script (`discover_mathtype.ps1`) | Implemented (read-only) |
| Worker conversion implementation | **Not implemented yet** – it depends on the MathType version and the supported interfaces reported by the discovery script |

Until a worker is configured the backend reports *MathType unavailable*, the
**Convert to MathType** button stays disabled, and no file is ever presented as
converted.

## Step 1 – discovery

On the Windows PC, in PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File .\discover_mathtype.ps1
```

It only reads installed-software records (uninstall entries, the `Equation.*`
COM registrations, PowerPoint path/version and add-ins) and writes
`mathtype_discovery.json`. Share that file so the worker can be written against
the interfaces that installation actually supports.

## Step 2 – worker contract

The backend (`app/services/equations/mathtype_adapter.py`) talks to the worker over HTTP:

* `GET /health` →
  `{"available": bool, "mathtype_version": str|null, "conversion_method": str|null, "requires_user_interaction": bool, "details": str}`
* `POST /convert` with `{"mathml": str, "omml": [str], "font_size_pt": float|null}` →
  `{"prog_id": "Equation.DSMT4", "ole_object_b64": str, "preview_b64": str, "preview_content_type": "image/x-emf"|"image/x-wmf"|"image/png", "width_emu": int, "height_emu": int}`

`ole_object_b64` must be the OLE compound file of a real MathType equation
object (it must contain an `Equation Native` stream). The backend rejects
anything else, including images, SVG or text, and reports that equation as failed.

## Step 3 – connect the backend

```
MATHTYPE_ADAPTER=windows_worker
MATHTYPE_WORKER_URL=http://<windows-pc>:8765
MATHTYPE_WORKER_TOKEN=<shared secret>
```
