"""Brand API (M6): logo watermark + outro card config.

Mirrors the voice routes' shapes. Everything is per-project state in
brand.json; the logo file lives at .instantdemo/logo.png. Changes
apply to the NEXT recording (the logo is burned in at record time,
like the cursor) — never retroactively to existing frames.
"""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from instantdemo import brand as brand_mod

router = APIRouter(prefix="/api", tags=["brand"])

_MAX_LOGO_BYTES = 2 * 1024 * 1024
_ALLOWED_SUFFIXES = {".png", ".jpg", ".jpeg"}


class BrandState(BaseModel):
    logo: str | None = None
    logo_exists: bool = False
    outro_enabled: bool = False
    outro_text: str = ""
    outro_duration_s: float = Field(default=4.0, ge=2.0, le=10.0)


def _project_dir() -> Path:
    override = os.environ.get("INSTANTDEMO_PROJECT_DIR")
    return Path(override).resolve() if override else Path.cwd()


def _state(project: Path) -> BrandState:
    config = brand_mod.load_or_default(project)
    return BrandState(
        logo=config.logo,
        logo_exists=brand_mod.resolve_logo(project, config) is not None,
        outro_enabled=config.outro_enabled,
        outro_text=config.outro_text,
        outro_duration_s=config.outro_duration_s,
    )


@router.get("/project/brand", response_model=BrandState)
def get_brand() -> BrandState:
    return _state(_project_dir())


class BrandUpdate(BaseModel):
    outro_enabled: bool = False
    outro_text: str = ""
    outro_duration_s: float = Field(default=4.0, ge=2.0, le=10.0)


@router.put("/project/brand", response_model=BrandState)
def put_brand(body: BrandUpdate) -> BrandState:
    project = _project_dir()
    config = brand_mod.load_or_default(project)
    config.outro_enabled = body.outro_enabled
    config.outro_text = body.outro_text.strip()
    config.outro_duration_s = body.outro_duration_s
    brand_mod.save(project, config)
    return _state(project)


@router.get("/project/brand/logo")
def get_logo() -> FileResponse:
    project = _project_dir()
    path = brand_mod.resolve_logo(
        project, brand_mod.load_or_default(project)
    )
    if path is None:
        raise HTTPException(status_code=404, detail="no logo uploaded")
    media = "image/jpeg" if path.suffix.lower() in (".jpg", ".jpeg") else "image/png"
    return FileResponse(path=str(path), media_type=media)


@router.post("/project/brand/logo", response_model=BrandState)
async def upload_logo(file: UploadFile) -> BrandState:
    project = _project_dir()
    suffix = Path(file.filename or "logo.png").suffix.lower()
    if suffix not in _ALLOWED_SUFFIXES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="the logo must be a PNG or JPEG image",
        )
    data = await file.read()
    if len(data) > _MAX_LOGO_BYTES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="the logo must be 2MB or smaller",
        )
    if not data:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="the uploaded file is empty",
        )
    dest = project / brand_mod.LOGO_RELPATH
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    config = brand_mod.load_or_default(project)
    config.logo = brand_mod.LOGO_RELPATH
    brand_mod.save(project, config)
    return _state(project)


@router.delete("/project/brand/logo", response_model=BrandState)
def delete_logo() -> BrandState:
    project = _project_dir()
    config = brand_mod.load_or_default(project)
    path = brand_mod.resolve_logo(project, config)
    if path is not None:
        path.unlink()
    config.logo = None
    brand_mod.save(project, config)
    return _state(project)
