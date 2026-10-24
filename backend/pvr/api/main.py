"""FastAPI application. Phase 0 exposes only the health check."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from pvr import __version__
from pvr.config import DATA_DIR, GOLDEN_PATH


class HealthResponse(BaseModel):
    """Response body of `GET /api/health`."""

    status: str
    version: str
    data_dir_found: bool
    golden_found: bool


app = FastAPI(title="PVR Agent Room", version=__version__)

# The Vite dev server proxies /api, but allow direct calls from it too.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """Health check. Also reports whether the repository data folders are reachable."""
    return HealthResponse(
        status="ok",
        version=__version__,
        data_dir_found=DATA_DIR.is_dir(),
        golden_found=GOLDEN_PATH.is_file(),
    )
