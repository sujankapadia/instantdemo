"""Unit tests for versioned takes (M4).
Spec: tests/test-specs/test_takes.md."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from instantdemo import takes


def make_project(tmp_path: Path, *, video: bool = True) -> Path:
    (tmp_path / ".instantdemo").mkdir(exist_ok=True)
    if video:
        (tmp_path / "demo.mp4").write_bytes(b"FILM-v0")
    (tmp_path / "demo-script.json").write_text('{"segments": []}')
    (tmp_path / ".instantdemo" / "storyboard.json").write_text('{"scenes": []}')
    (tmp_path / ".instantdemo" / "segment-timing.json").write_text('{}')
    return tmp_path


class TestSnapshot:
    def test_full_snapshot(self, tmp_path: Path):  # T1
        project = make_project(tmp_path)
        n = takes.snapshot(project, "render")
        assert n == 1
        v1 = takes.takes_dir(project) / "v1"
        for name in ("demo.mp4", "demo-script.json", "storyboard.json",
                     "segment-timing.json", "meta.json"):
            assert (v1 / name).exists(), name
        meta = json.loads((v1 / "meta.json").read_text())
        assert meta["n"] == 1 and meta["label"] == "render"
        assert meta["created_at"]

    def test_videoless_snapshot(self, tmp_path: Path):  # T2
        project = make_project(tmp_path, video=False)
        n = takes.snapshot(project, "edit")
        v1 = takes.takes_dir(project) / f"v{n}"
        assert not (v1 / "demo.mp4").exists()
        assert (v1 / "storyboard.json").exists()

    def test_numbering_scans_dirs(self, tmp_path: Path):  # T3
        project = make_project(tmp_path)
        takes.snapshot(project, "a")
        takes.snapshot(project, "b")
        takes.snapshot(project, "c")
        assert [t["n"] for t in takes.list_takes(project)] == [3, 2, 1]
        assert takes.next_take_number(project) == 4

    def test_video_retention(self, tmp_path: Path):  # T4
        project = make_project(tmp_path)
        for i in range(5):
            (project / "demo.mp4").write_bytes(f"FILM-{i}".encode())
            takes.snapshot(project, f"take-{i}")
        listing = takes.list_takes(project)
        with_video = [t["n"] for t in listing if t["video_exists"]]
        assert sorted(with_video) == [3, 4, 5]
        # JSON + meta survive pruning on all five
        for n in range(1, 6):
            vdir = takes.takes_dir(project) / f"v{n}"
            assert (vdir / "meta.json").exists()
            assert (vdir / "storyboard.json").exists()

    def test_list_fields(self, tmp_path: Path):  # T5
        project = make_project(tmp_path)
        takes.snapshot(project, "render")
        listing = takes.list_takes(project)
        assert listing[0]["n"] == 1
        assert listing[0]["label"] == "render"
        assert listing[0]["video_exists"] is True
        assert listing[0]["created_at"]

    def test_is_current_flag(self, tmp_path: Path):  # T9
        project = make_project(tmp_path)
        takes.snapshot(project, "render")
        # Fresh post-render snapshot IS the current film
        assert takes.list_takes(project)[0]["is_current"] is True
        # After the film changes, it's a genuine previous version
        (project / "demo.mp4").write_bytes(b"FILM-v1-different")
        assert takes.list_takes(project)[0]["is_current"] is False

    def test_snapshot_unless_current(self, tmp_path: Path):  # T10
        project = make_project(tmp_path)
        takes.snapshot(project, "render")
        # The first edit after a render must NOT duplicate the take
        assert takes.snapshot_unless_current(project, "re-record") is None
        assert [t["n"] for t in takes.list_takes(project)] == [1]
        # Once the film has changed, the pre-mutation snapshot happens
        (project / "demo.mp4").write_bytes(b"FILM-v1-different")
        assert takes.snapshot_unless_current(project, "re-record") == 2
        assert [t["n"] for t in takes.list_takes(project)] == [2, 1]


class TestRestore:
    def test_round_trip(self, tmp_path: Path):  # T6
        project = make_project(tmp_path)
        takes.snapshot(project, "v1-state")
        # Mutate everything
        (project / "demo.mp4").write_bytes(b"FILM-v2")
        (project / "demo-script.json").write_text('{"segments": [1]}')
        (project / ".instantdemo" / "storyboard.json").write_text(
            '{"scenes": [1]}'
        )
        takes.restore(project, 1)
        assert (project / "demo.mp4").read_bytes() == b"FILM-v0"
        assert (project / "demo-script.json").read_text() == '{"segments": []}'
        assert (
            project / ".instantdemo" / "storyboard.json"
        ).read_text() == '{"scenes": []}'

    def test_pruned_video_refused(self, tmp_path: Path):  # T7
        project = make_project(tmp_path)
        for i in range(5):
            takes.snapshot(project, f"t{i}")
        with pytest.raises(ValueError, match="pruned"):
            takes.restore(project, 1)

    def test_missing_take_refused(self, tmp_path: Path):  # T8
        project = make_project(tmp_path)
        with pytest.raises(ValueError, match="no take"):
            takes.restore(project, 9)
