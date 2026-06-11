"""Versioned takes (M4): every recording and every revision quietly
keeps the previous version.

A take is a directory snapshot under `.instantdemo/takes/v<N>/`
holding the film and its three JSON artifacts. Retention follows the
pre-M0 decision: the newest KEEP_VIDEOS takes keep their demo.mp4
(videos are big); JSON + meta are kept forever, so the full text
history survives even when old video is pruned.

Reversibility so effortless it isn't a feature (DESIGN.md
principle 7): the GUI surfaces takes as a "Previous version" toggle
on the player — comparison by watching, restore underneath.
"""

from __future__ import annotations

import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path

TAKES_DIRNAME = "takes"
KEEP_VIDEOS = 3

# (project-relative source path, filename inside the take dir)
SNAPSHOT_FILES: tuple[tuple[str, str], ...] = (
    ("demo.mp4", "demo.mp4"),
    ("demo-script.json", "demo-script.json"),
    (".instantdemo/storyboard.json", "storyboard.json"),
    (".instantdemo/segment-timing.json", "segment-timing.json"),
)

_TAKE_DIR_RE = re.compile(r"^v(\d+)$")


def takes_dir(project: Path) -> Path:
    return project / ".instantdemo" / TAKES_DIRNAME


def _take_dirs(project: Path) -> list[tuple[int, Path]]:
    root = takes_dir(project)
    if not root.is_dir():
        return []
    out: list[tuple[int, Path]] = []
    for child in root.iterdir():
        match = _TAKE_DIR_RE.match(child.name)
        if child.is_dir() and match:
            out.append((int(match.group(1)), child))
    return sorted(out)


def next_take_number(project: Path) -> int:
    dirs = _take_dirs(project)
    return (dirs[-1][0] + 1) if dirs else 1


def snapshot(project: Path, label: str) -> int:
    """Copy the current film + artifacts into takes/v<N>/ and prune
    old videos. Copies what exists; a project with no demo.mp4 yet
    still snapshots its JSON. Returns N."""
    n = next_take_number(project)
    dest = takes_dir(project) / f"v{n}"
    dest.mkdir(parents=True, exist_ok=True)
    for rel_src, name in SNAPSHOT_FILES:
        src = project / rel_src
        if src.exists():
            shutil.copy2(src, dest / name)
    (dest / "meta.json").write_text(json.dumps({
        "n": n,
        "label": label,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }, indent=2) + "\n")
    prune_videos(project, keep=KEEP_VIDEOS)
    return n


def prune_videos(project: Path, *, keep: int = KEEP_VIDEOS) -> list[int]:
    """Delete demo.mp4 from all but the newest `keep` takes. JSON +
    meta stay forever. Returns the take numbers pruned."""
    dirs = _take_dirs(project)
    pruned: list[int] = []
    for n, path in dirs[:-keep] if keep else dirs:
        video = path / "demo.mp4"
        if video.exists():
            video.unlink()
            pruned.append(n)
    return pruned


def list_takes(project: Path) -> list[dict]:
    """Newest first: {n, label, created_at, video_exists}."""
    out: list[dict] = []
    for n, path in reversed(_take_dirs(project)):
        meta: dict = {"n": n, "label": "", "created_at": None}
        meta_path = path / "meta.json"
        if meta_path.exists():
            try:
                meta.update(json.loads(meta_path.read_text()))
            except (json.JSONDecodeError, OSError):
                pass
        meta["video_exists"] = (path / "demo.mp4").exists()
        out.append(meta)
    return out


def take_video_path(project: Path, n: int) -> Path:
    return takes_dir(project) / f"v{n}" / "demo.mp4"


def restore(project: Path, n: int) -> None:
    """Copy take N's files back over the project's current state.
    Raises ValueError when the take doesn't exist or its video was
    pruned (a film-less restore would silently delete the current
    demo's coherence)."""
    src_dir = takes_dir(project) / f"v{n}"
    if not src_dir.is_dir():
        raise ValueError(f"no take v{n}")
    if not (src_dir / "demo.mp4").exists():
        raise ValueError(
            f"take v{n}'s video was pruned (only the newest "
            f"{KEEP_VIDEOS} keep video) — its script/storyboard are "
            "still in the take directory"
        )
    for rel_dst, name in SNAPSHOT_FILES:
        src = src_dir / name
        if src.exists():
            dst = project / rel_dst
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
