"""Per-project brand config (M6): logo watermark + outro card.

`<project>/brand.json`, mirroring tts.json's pattern. Everything is
OFF by default — films are exactly as before until the user uploads
a logo or enables the outro in the Brand tab. The logo is burned in
at RECORD time (a page-level element, like the cursor), so changes
apply to the next recording, never retroactively to existing frames.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

BRAND_FILENAME = "brand.json"
LOGO_RELPATH = ".instantdemo/logo.png"


@dataclass
class BrandConfig:
    # Relative path to the logo image, or None. The upload endpoint
    # always writes LOGO_RELPATH; the field exists so a project can
    # point elsewhere by hand.
    logo: str | None = None
    outro_enabled: bool = False
    outro_text: str = ""
    outro_duration_s: float = 4.0


def load(project_dir: Path) -> BrandConfig | None:
    path = project_dir / BRAND_FILENAME
    if not path.exists():
        return None
    try:
        raw = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return None
    return BrandConfig(
        logo=raw.get("logo"),
        outro_enabled=bool(raw.get("outro_enabled", False)),
        outro_text=str(raw.get("outro_text") or ""),
        outro_duration_s=float(raw.get("outro_duration_s") or 4.0),
    )


def load_or_default(project_dir: Path) -> BrandConfig:
    return load(project_dir) or BrandConfig()


def save(project_dir: Path, config: BrandConfig) -> None:
    path = project_dir / BRAND_FILENAME
    path.write_text(json.dumps(asdict(config), indent=2) + "\n")


def resolve_logo(project_dir: Path, config: BrandConfig) -> Path | None:
    """Absolute logo path when configured AND present, else None
    (dangling references degrade to no watermark, like ref_wav)."""
    if not config.logo:
        return None
    path = (project_dir / config.logo).resolve()
    return path if path.exists() else None
