import os

import pytest

from app.services import social_sources


class FakeDownloader:
    """Minimal stand-in for yt_dlp.YoutubeDL used as a context manager."""

    def __init__(self, options):
        self.options = options
        FakeDownloader.last_options = options

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


def _fake_yt_dlp(monkeypatch, extract_info, prepare_filename=None):
    class FakeModule:
        class YoutubeDL(FakeDownloader):
            def extract_info(self, query, download=False):
                FakeModule.last_query = query
                FakeModule.last_download = download
                return extract_info(query)

            def prepare_filename(self, info):
                return prepare_filename(info)

        class utils:
            @staticmethod
            def download_range_func(chapters, ranges):
                return ("range", ranges)

    monkeypatch.setattr(social_sources, "_yt_dlp", lambda: FakeModule)
    return FakeModule


def test_is_social_source():
    assert social_sources.is_social_source("youtube")
    assert social_sources.is_social_source("TikTok")
    assert not social_sources.is_social_source("pexels")
    assert not social_sources.is_social_source("")


def test_youtube_search_builds_query_and_filters_by_duration(monkeypatch):
    entries = {
        "entries": [
            {"id": "short", "duration": 2},
            {"id": "good", "duration": 40, "url": "https://youtu.be/good"},
            {"id": "movie", "duration": 7340},
            {"id": "byid", "duration": 30},
        ]
    }
    module = _fake_yt_dlp(monkeypatch, lambda query: entries)

    items = social_sources.search_videos_youtube("brazil beach", minimum_duration=7)

    assert module.last_query.startswith("ytsearch")
    assert "brazil beach" in module.last_query
    # 2s is under the minimum and 7340s is over social_max_duration.
    assert [item.url for item in items] == [
        "https://youtu.be/good",
        "https://www.youtube.com/watch?v=byid",
    ]
    assert all(item.provider == "youtube" for item in items)


def test_youtube_search_survives_broken_extractor(monkeypatch):
    def explode(query):
        raise RuntimeError("extractor is broken")

    _fake_yt_dlp(monkeypatch, explode)

    assert social_sources.search_videos_youtube("qualquer", minimum_duration=5) == []


def test_tiktok_search_uses_hashtag_feed(monkeypatch):
    module = _fake_yt_dlp(
        monkeypatch,
        lambda query: {
            "entries": [
                {"id": "a", "url": "https://www.tiktok.com/@u/video/1", "duration": 12}
            ]
        },
    )

    items = social_sources.search_videos_tiktok("Praias do Brasil", minimum_duration=5)

    assert module.last_query == "https://www.tiktok.com/tag/praiasdobrasil"
    assert items[0].provider == "tiktok"


def test_tiktok_search_accepts_entries_without_duration(monkeypatch):
    _fake_yt_dlp(
        monkeypatch,
        lambda query: {
            "entries": [{"id": "a", "url": "https://www.tiktok.com/@u/video/1"}]
        },
    )

    items = social_sources.search_videos_tiktok("beach", minimum_duration=7)

    assert len(items) == 1
    assert items[0].duration == 7


def test_tiktok_search_without_usable_hashtag(monkeypatch):
    _fake_yt_dlp(monkeypatch, lambda query: {"entries": []})

    assert social_sources.search_videos_tiktok("!!!", minimum_duration=5) == []


def test_resolve_stream_url_prefers_direct_url(monkeypatch):
    _fake_yt_dlp(monkeypatch, lambda query: {"url": "https://cdn/video.mp4"})

    assert social_sources.resolve_stream_url("https://youtu.be/x") == (
        "https://cdn/video.mp4"
    )


def test_resolve_stream_url_falls_back_to_progressive_format(monkeypatch):
    _fake_yt_dlp(
        monkeypatch,
        lambda query: {
            "formats": [
                {"url": "https://cdn/audio", "acodec": "mp4a", "vcodec": "none"},
                {"url": "https://cdn/muxed", "acodec": "mp4a", "vcodec": "avc1"},
            ]
        },
    )

    assert social_sources.resolve_stream_url("https://youtu.be/x") == (
        "https://cdn/muxed"
    )


def test_resolve_stream_url_returns_none_on_failure(monkeypatch):
    def explode(query):
        raise RuntimeError("nope")

    _fake_yt_dlp(monkeypatch, explode)

    assert social_sources.resolve_stream_url("https://youtu.be/x") is None


def test_download_video_limits_range_and_returns_path(monkeypatch, tmp_path):
    target = tmp_path / "social-abc.mp4"

    def prepare_filename(info):
        target.write_bytes(b"data")
        return str(target)

    module = _fake_yt_dlp(
        monkeypatch, lambda query: {"id": "abc"}, prepare_filename=prepare_filename
    )

    path = social_sources.download_video(
        "https://youtu.be/abc", save_dir=str(tmp_path), seconds=7
    )

    assert path == str(target)
    assert module.last_download is True
    ranges = FakeDownloader.last_options["download_ranges"][1]
    assert ranges == [(0, 7 + social_sources.DOWNLOAD_TAIL_BUFFER)]


def test_download_video_finds_merged_mp4(monkeypatch, tmp_path):
    merged = tmp_path / "social-abc.mp4"

    def prepare_filename(info):
        merged.write_bytes(b"data")
        # yt-dlp reports the pre-merge extension here.
        return str(tmp_path / "social-abc.webm")

    _fake_yt_dlp(
        monkeypatch, lambda query: {"id": "abc"}, prepare_filename=prepare_filename
    )

    assert social_sources.download_video(
        "https://youtu.be/abc", save_dir=str(tmp_path)
    ) == str(merged)


def test_download_video_returns_empty_when_nothing_was_written(monkeypatch, tmp_path):
    _fake_yt_dlp(
        monkeypatch,
        lambda query: {"id": "abc"},
        prepare_filename=lambda info: str(tmp_path / "missing.mp4"),
    )

    assert (
        social_sources.download_video("https://youtu.be/abc", save_dir=str(tmp_path))
        == ""
    )


def test_download_video_creates_the_target_directory(monkeypatch, tmp_path):
    save_dir = tmp_path / "task-9"

    def prepare_filename(info):
        path = save_dir / "social-abc.mp4"
        path.write_bytes(b"data")
        return str(path)

    _fake_yt_dlp(
        monkeypatch, lambda query: {"id": "abc"}, prepare_filename=prepare_filename
    )

    social_sources.download_video("https://youtu.be/abc", save_dir=str(save_dir))

    assert os.path.isdir(save_dir)


def test_cookie_file_is_passed_to_yt_dlp(monkeypatch, tmp_path):
    cookies = tmp_path / "cookies.txt"
    cookies.write_text("# Netscape HTTP Cookie File\n", encoding="utf-8")
    monkeypatch.setitem(
        social_sources.config.app, "social_cookies_file", str(cookies)
    )

    assert social_sources._base_options()["cookiefile"] == str(cookies)


def test_missing_cookie_file_is_ignored(monkeypatch, tmp_path):
    monkeypatch.setitem(
        social_sources.config.app,
        "social_cookies_file",
        str(tmp_path / "absent.txt"),
    )

    assert "cookiefile" not in social_sources._base_options()


def test_browser_cookies_are_passed_to_yt_dlp(monkeypatch):
    monkeypatch.setitem(social_sources.config.app, "social_cookies_file", "")
    monkeypatch.setitem(
        social_sources.config.app, "social_cookies_from_browser", "Chrome"
    )

    assert social_sources._base_options()["cookiesfrombrowser"] == (
        "chrome",
        None,
        None,
        None,
    )


def test_cookie_file_wins_over_browser(monkeypatch, tmp_path):
    cookies = tmp_path / "cookies.txt"
    cookies.write_text("# Netscape HTTP Cookie File\n", encoding="utf-8")
    monkeypatch.setitem(
        social_sources.config.app, "social_cookies_file", str(cookies)
    )
    monkeypatch.setitem(
        social_sources.config.app, "social_cookies_from_browser", "firefox"
    )

    options = social_sources._base_options()

    assert options["cookiefile"] == str(cookies)
    assert "cookiesfrombrowser" not in options


def test_missing_yt_dlp_raises_actionable_error(monkeypatch):
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "yt_dlp":
            raise ImportError("no module named yt_dlp")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    with pytest.raises(RuntimeError, match="social-sources"):
        social_sources._yt_dlp()
