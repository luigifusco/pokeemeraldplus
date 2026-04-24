"""FastAPI application for the randomizer web UI.

Only the scaffold lives here for now. Real routes (build, events,
stop, presets, evolution-graph) land in later phases.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
STATIC_DIR = Path(__file__).resolve().parent / "static"


def create_app() -> FastAPI:
    app = FastAPI(
        title="pokeemeraldplus randomizer",
        version="0.1.0",
        docs_url="/api/docs",
        redoc_url=None,
    )

    STATIC_DIR.mkdir(exist_ok=True)
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/api/health")
    def health() -> JSONResponse:
        return JSONResponse({"ok": True, "repo": str(REPO_ROOT)})

    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        index_path = STATIC_DIR / "index.html"
        if not index_path.exists():
            return JSONResponse(
                {
                    "message": (
                        "Web UI scaffold is running. Static shell lands in "
                        "phase 5. GET /api/health to confirm the server works."
                    )
                }
            )
        return FileResponse(index_path)

    return app


app = create_app()
