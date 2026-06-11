"""Route tests for the voice API (M3, #59).
Spec: tests/test-specs/test_voice_routes.md."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from instantdemo import tts_config
from instantdemo.tts_config import TTSConfig


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("INSTANTDEMO_PROJECT_DIR", str(tmp_path))
    from fastapi.testclient import TestClient
    from instantdemo.server.app import create_app

    with TestClient(create_app()) as c:
        yield tmp_path, c


def make_wav(path: Path, seconds: float, silent: bool = False) -> None:
    source = (
        "anullsrc=r=24000:cl=mono"
        if silent
        else "sine=frequency=220:sample_rate=24000"
    )
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", source,
         "-t", str(seconds), str(path)],
        capture_output=True, check=True,
    )


class TestGetVoice:
    def test_fresh_project(self, client):  # V1
        _, c = client
        body = c.get("/api/project/voice").json()
        assert body["persisted"] is False
        assert body["config"]["provider"] == "pocket-tts"
        assert body["config"]["voice"] == "alba"
        assert "alba" in body["voices"] and len(body["voices"]) >= 20
        assert isinstance(body["pocket_installed"], bool)

    def test_persisted_with_ref(self, client):  # V2
        project, c = client
        (project / ".instantdemo").mkdir()
        (project / ".instantdemo" / "voice-reference.wav").write_bytes(b"RIFF")
        tts_config.save(project, TTSConfig(
            voice="marius", ref_wav=".instantdemo/voice-reference.wav",
        ))
        body = c.get("/api/project/voice").json()
        assert body["persisted"] is True
        assert body["ref_exists"] is True
        assert body["config"]["voice"] == "marius"


class TestPutVoice:
    def test_update_voice(self, client):  # V3
        project, c = client
        res = c.put("/api/project/voice", json={"voice": "javert"})
        assert res.status_code == 200
        assert tts_config.load(project).voice == "javert"

    def test_unknown_voice(self, client):  # V4
        _, c = client
        res = c.put("/api/project/voice", json={"voice": "nonexistent"})
        assert res.status_code == 422

    def test_update_pronunciations_drops_blanks(self, client):  # V5
        project, c = client
        res = c.put("/api/project/voice", json={"pronunciations": [
            {"match": "Evernote", "say": "Ever note"},
            {"match": "  ", "say": "x"},
            {"match": "y", "say": ""},
        ]})
        assert res.status_code == 200
        loaded = tts_config.load(project)
        assert [(e.match, e.say) for e in loaded.pronunciations] == [
            ("Evernote", "Ever note")
        ]

    def test_active_run_409(self, client):  # V6
        _, c = client

        class FakeRun:
            status = "running"

        c.app.state.run_manager.active = FakeRun()
        try:
            res = c.put("/api/project/voice", json={"voice": "alba"})
            assert res.status_code == 409
        finally:
            c.app.state.run_manager.active = None


class TestReferenceUpload:
    def _upload(self, c, wav: Path, consent: bool):
        with open(wav, "rb") as f:
            return c.post(
                "/api/project/voice/reference",
                files={"file": (wav.name, f, "audio/wav")},
                data={"consent": "true" if consent else "false"},
            )

    def test_consent_required(self, client, tmp_path):  # V7
        project, c = client
        wav = tmp_path / "in.wav"
        make_wav(wav, 5.0)
        res = self._upload(c, wav, consent=False)
        assert res.status_code == 422
        assert "right to use" in res.json()["detail"]
        assert not (project / ".instantdemo" / "voice-reference.wav").exists()

    def test_too_short(self, client, tmp_path):  # V8
        project, c = client
        wav = tmp_path / "short.wav"
        make_wav(wav, 1.0)
        res = self._upload(c, wav, consent=True)
        assert res.status_code == 422
        assert "too short" in res.json()["detail"]
        assert not (project / ".instantdemo" / "voice-reference.wav").exists()

    def test_silent(self, client, tmp_path):  # V9
        project, c = client
        wav = tmp_path / "silent.wav"
        make_wav(wav, 5.0, silent=True)
        res = self._upload(c, wav, consent=True)
        assert res.status_code == 422
        assert "silent" in res.json()["detail"]
        assert not (project / ".instantdemo" / "voice-reference.wav").exists()

    def test_valid_upload_and_delete(self, client, tmp_path):  # V10+V11
        project, c = client
        wav = tmp_path / "voice.wav"
        make_wav(wav, 5.0)
        res = self._upload(c, wav, consent=True)
        assert res.status_code == 200, res.text
        stored = project / ".instantdemo" / "voice-reference.wav"
        assert stored.exists()
        assert stored.read_bytes()[:4] == b"RIFF"
        config = tts_config.load(project)
        assert config.ref_wav == ".instantdemo/voice-reference.wav"
        assert config.consent and config.consent["given"] is True

        res = c.delete("/api/project/voice/reference")
        assert res.status_code == 200
        assert not stored.exists()
        config = tts_config.load(project)
        assert config.ref_wav is None and config.consent is None


class TestPreview:
    def test_default_preview(self, client, monkeypatch):  # V12
        _, c = client
        seen = {}

        def fake_synth(text, voice, ref):
            seen.update(text=text, voice=voice, ref=ref)
            return b"RIFFfakewav"

        monkeypatch.setattr(
            "instantdemo.server.routes.voice._synthesize_preview",
            fake_synth,
        )
        res = c.post("/api/project/voice/preview", json={})
        assert res.status_code == 200
        assert res.headers["content-type"] == "audio/wav"
        assert seen["voice"] == "alba" and seen["ref"] is None

    def test_preview_with_overrides(self, client, monkeypatch):  # V13
        _, c = client
        seen = {}

        def fake_synth(text, voice, ref):
            seen.update(text=text, voice=voice)
            return b"RIFF"

        monkeypatch.setattr(
            "instantdemo.server.routes.voice._synthesize_preview",
            fake_synth,
        )
        res = c.post("/api/project/voice/preview", json={
            "text": "Evernote keeps notes",
            "voice": "marius",
            "pronunciations": [
                {"match": "Evernote", "say": "Ever note"}
            ],
        })
        assert res.status_code == 200
        assert seen["text"] == "Ever note keeps notes"
        assert seen["voice"] == "marius"

    def test_reference_missing_404(self, client):  # V14
        _, c = client
        res = c.post(
            "/api/project/voice/preview", json={"use_reference": True}
        )
        assert res.status_code == 404
