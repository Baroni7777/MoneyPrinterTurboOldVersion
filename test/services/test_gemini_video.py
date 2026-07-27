import sys
from types import SimpleNamespace

import pytest

from app.config import config
from app.services import gemini_video


@pytest.fixture(autouse=True)
def clean_config():
    previous = {
        key: config.app.get(key)
        for key in ("gemini_api_key", "gemini_video_analysis", "gemini_video_model")
    }
    yield
    for key, value in previous.items():
        if value is None:
            config.app.pop(key, None)
        else:
            config.app[key] = value


def _enable(monkeypatch):
    monkeypatch.setitem(config.app, "gemini_api_key", "gem-key")
    monkeypatch.setitem(config.app, "gemini_video_analysis", True)


class _FakeFiles:
    def __init__(self, states, fail_delete=False):
        self._states = list(states)
        self.uploaded = []
        self.deleted = []
        self.fail_delete = fail_delete

    def upload(self, file):
        self.uploaded.append(file)
        return SimpleNamespace(name="files/abc", state=self._states.pop(0))

    def get(self, name):
        return SimpleNamespace(name=name, state=self._states.pop(0))

    def delete(self, name):
        if self.fail_delete:
            raise RuntimeError("delete failed")
        self.deleted.append(name)


class _FakeModels:
    def __init__(self, text="8", explode=False):
        self.text = text
        self.explode = explode
        self.calls = []

    def generate_content(self, model, contents):
        if self.explode:
            raise RuntimeError("generate failed")
        self.calls.append((model, contents))
        return SimpleNamespace(text=self.text)


class _FakeClient:
    def __init__(self, files, models):
        self.files = files
        self.models = models


def _install_client(monkeypatch, files, models):
    client = _FakeClient(files, models)
    monkeypatch.setattr(gemini_video, "_client", lambda: client)
    monkeypatch.setattr(gemini_video, "_PROCESSING_POLL_SECONDS", 0)
    return client


def _video(tmp_path):
    path = tmp_path / "clip.mp4"
    path.write_bytes(b"video-bytes")
    return str(path)


def test_disabled_without_opt_in(monkeypatch):
    monkeypatch.setitem(config.app, "gemini_api_key", "gem-key")
    monkeypatch.setitem(config.app, "gemini_video_analysis", False)

    assert gemini_video.is_enabled() is False


def test_disabled_without_api_key(monkeypatch):
    monkeypatch.setitem(config.app, "gemini_api_key", "")
    monkeypatch.setitem(config.app, "gemini_video_analysis", True)

    assert gemini_video.is_enabled() is False


def test_enabled_with_key_and_opt_in(monkeypatch):
    _enable(monkeypatch)

    assert gemini_video.is_enabled() is True


def test_analyze_uploads_waits_and_cleans_up(monkeypatch, tmp_path):
    _enable(monkeypatch)
    files = _FakeFiles(states=["PROCESSING", "ACTIVE"])
    models = _FakeModels(text="7")
    _install_client(monkeypatch, files, models)
    path = _video(tmp_path)

    answer = gemini_video.analyze_clip(path, prompt="Rate it")

    assert answer == "7"
    assert files.uploaded == [path]
    # The upload is polled until ACTIVE before generate_content runs.
    assert models.calls[0][1][1] == "Rate it"
    assert files.deleted == ["files/abc"]


def test_analyze_accepts_enum_like_state(monkeypatch, tmp_path):
    _enable(monkeypatch)
    files = _FakeFiles(states=[SimpleNamespace(name="ACTIVE")])
    models = _FakeModels(text="9")
    _install_client(monkeypatch, files, models)

    assert gemini_video.analyze_clip(_video(tmp_path), prompt="Rate") == "9"


def test_analyze_returns_none_when_processing_fails(monkeypatch, tmp_path):
    _enable(monkeypatch)
    files = _FakeFiles(states=["FAILED"])
    _install_client(monkeypatch, files, _FakeModels())

    assert gemini_video.analyze_clip(_video(tmp_path), prompt="Rate") is None
    # Even a failed analysis must not leak the upload.
    assert files.deleted == ["files/abc"]


def test_analyze_returns_none_when_generation_fails(monkeypatch, tmp_path):
    _enable(monkeypatch)
    files = _FakeFiles(states=["ACTIVE"])
    _install_client(monkeypatch, files, _FakeModels(explode=True))

    assert gemini_video.analyze_clip(_video(tmp_path), prompt="Rate") is None
    assert files.deleted == ["files/abc"]


def test_failed_cleanup_does_not_break_the_answer(monkeypatch, tmp_path):
    _enable(monkeypatch)
    files = _FakeFiles(states=["ACTIVE"], fail_delete=True)
    _install_client(monkeypatch, files, _FakeModels(text="6"))

    assert gemini_video.analyze_clip(_video(tmp_path), prompt="Rate") == "6"


def test_analyze_returns_none_when_disabled(monkeypatch, tmp_path):
    monkeypatch.setitem(config.app, "gemini_video_analysis", False)

    assert gemini_video.analyze_clip(_video(tmp_path), prompt="Rate") is None


def test_analyze_returns_none_for_missing_file(monkeypatch):
    _enable(monkeypatch)

    assert gemini_video.analyze_clip("does-not-exist.mp4", prompt="Rate") is None


def test_model_override_is_used(monkeypatch, tmp_path):
    _enable(monkeypatch)
    monkeypatch.setitem(config.app, "gemini_video_model", "gemini-custom")
    models = _FakeModels(text="5")
    _install_client(monkeypatch, _FakeFiles(states=["ACTIVE"]), models)

    gemini_video.analyze_clip(_video(tmp_path), prompt="Rate")

    assert models.calls[0][0] == "gemini-custom"


def test_default_model_is_used_without_override(monkeypatch, tmp_path):
    _enable(monkeypatch)
    models = _FakeModels(text="5")
    _install_client(monkeypatch, _FakeFiles(states=["ACTIVE"]), models)

    gemini_video.analyze_clip(_video(tmp_path), prompt="Rate")

    assert models.calls[0][0] == gemini_video.DEFAULT_MODEL


def test_client_is_built_from_the_configured_key(monkeypatch):
    _enable(monkeypatch)
    captured = {}

    class _Genai:
        @staticmethod
        def Client(api_key):
            captured["api_key"] = api_key
            return "client"

    monkeypatch.setitem(sys.modules, "google", SimpleNamespace(genai=_Genai))
    monkeypatch.setitem(sys.modules, "google.genai", _Genai)

    assert gemini_video._client() == "client"
    assert captured["api_key"] == "gem-key"
