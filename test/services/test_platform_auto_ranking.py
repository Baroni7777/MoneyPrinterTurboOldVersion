import json

import pytest

from app.models.schema import MaterialInfo, VideoAspect
from app.services import platform_auto_ranking
from app.services.platform_ranking import RankingStageError
from test.services.test_platform_auth import USER_PASSWORD, login

pytest_plugins = ["test.services.test_platform_auth"]


def _material(url: str, provider: str = "pexels") -> MaterialInfo:
    item = MaterialInfo()
    item.provider = provider
    item.url = url
    item.duration = 12
    return item


def _plan_response(items) -> str:
    return json.dumps(items)


def test_plan_ranking_items_parses_and_orders_llm_plan(monkeypatch):
    monkeypatch.setattr(
        platform_auto_ranking.llm,
        "_generate_response",
        lambda prompt: _plan_response(
            [
                {"position": 2, "title": "Segundo", "search_term": "second thing"},
                {"position": 1, "title": "Primeiro", "search_term": "first thing"},
            ]
        ),
    )

    items = platform_auto_ranking.plan_ranking_items("Praias do Brasil", 5)

    assert [item["position"] for item in items] == [1, 2]
    assert items[0]["title"] == "Primeiro"
    assert items[0]["search_term"] == "first thing"


def test_plan_ranking_items_recovers_json_from_fenced_response(monkeypatch):
    payload = _plan_response(
        [
            {"position": 1, "title": "A", "search_term": "a footage"},
            {"position": 2, "title": "B", "search_term": "b footage"},
            {"position": 3, "title": "C", "search_term": "c footage"},
        ]
    )
    monkeypatch.setattr(
        platform_auto_ranking.llm,
        "_generate_response",
        lambda prompt: f"Aqui está:\n```json\n{payload}\n```",
    )

    items = platform_auto_ranking.plan_ranking_items("Carros", 3)

    assert len(items) == 3


def test_plan_ranking_items_truncates_to_requested_size(monkeypatch):
    monkeypatch.setattr(
        platform_auto_ranking.llm,
        "_generate_response",
        lambda prompt: _plan_response(
            [
                {"position": index, "title": f"T{index}", "search_term": f"t{index}"}
                for index in range(1, 9)
            ]
        ),
    )

    items = platform_auto_ranking.plan_ranking_items("Cidades", 5)

    assert [item["position"] for item in items] == [1, 2, 3, 4, 5]


def test_plan_ranking_items_fails_with_dedicated_stage(monkeypatch):
    monkeypatch.setattr(
        platform_auto_ranking.llm,
        "_generate_response",
        lambda prompt: "Error: provider unavailable",
    )

    with pytest.raises(RankingStageError) as error:
        platform_auto_ranking.plan_ranking_items("Cidades", 5)

    assert error.value.stage == "ranking_plan"


def test_choose_clip_without_twelvelabs_keeps_provider_order(monkeypatch):
    monkeypatch.setattr(platform_auto_ranking.twelvelabs, "is_enabled", lambda: False)
    candidates = [_material("https://a.mp4"), _material("https://b.mp4")]

    assert platform_auto_ranking.choose_clip("Praias", "Ilha", candidates).url == (
        "https://a.mp4"
    )


def test_choose_clip_picks_highest_ai_score(monkeypatch):
    scores = {"https://a.mp4": "3", "https://b.mp4": "Score: 9/10", "https://c.mp4": "7"}
    monkeypatch.setattr(platform_auto_ranking.twelvelabs, "is_enabled", lambda: True)
    monkeypatch.setattr(
        platform_auto_ranking.twelvelabs,
        "analyze_clip",
        lambda url, prompt="": scores[url],
    )
    candidates = [
        _material("https://a.mp4"),
        _material("https://b.mp4"),
        _material("https://c.mp4"),
    ]

    chosen = platform_auto_ranking.choose_clip("Praias", "Ilha", candidates)

    assert chosen.url == "https://b.mp4"


def test_choose_clip_falls_back_when_every_analysis_fails(monkeypatch):
    monkeypatch.setattr(platform_auto_ranking.twelvelabs, "is_enabled", lambda: True)
    monkeypatch.setattr(
        platform_auto_ranking.twelvelabs, "analyze_clip", lambda url, prompt="": None
    )
    candidates = [_material("https://a.mp4"), _material("https://b.mp4")]

    assert platform_auto_ranking.choose_clip("Praias", "Ilha", candidates).url == (
        "https://a.mp4"
    )


def test_choose_clip_returns_none_without_candidates(monkeypatch):
    monkeypatch.setattr(platform_auto_ranking.twelvelabs, "is_enabled", lambda: False)

    assert platform_auto_ranking.choose_clip("Praias", "Ilha", []) is None


def test_choose_clip_falls_back_to_gemini_when_twelvelabs_is_off(monkeypatch):
    monkeypatch.setattr(platform_auto_ranking.twelvelabs, "is_enabled", lambda: False)
    monkeypatch.setattr(platform_auto_ranking.gemini_video, "is_enabled", lambda: True)
    scores = {"/tmp/a.mp4": "4", "/tmp/b.mp4": "9"}
    monkeypatch.setattr(
        platform_auto_ranking.gemini_video,
        "analyze_clip",
        lambda path, prompt="": scores[path],
    )
    downloaded = []

    def downloader(candidate):
        downloaded.append(candidate.url)
        return f"/tmp/{candidate.url[-5:]}"

    candidates = [_material("https://x/a.mp4"), _material("https://x/b.mp4")]

    chosen = platform_auto_ranking.choose_clip(
        "Praias", "Ilha", candidates, downloader=downloader
    )

    assert chosen.url == "https://x/b.mp4"
    # Gemini cannot read a URL, so every candidate had to be fetched first.
    assert downloaded == ["https://x/a.mp4", "https://x/b.mp4"]


def test_twelvelabs_takes_precedence_over_gemini(monkeypatch):
    monkeypatch.setattr(platform_auto_ranking.twelvelabs, "is_enabled", lambda: True)
    monkeypatch.setattr(platform_auto_ranking.gemini_video, "is_enabled", lambda: True)
    monkeypatch.setattr(
        platform_auto_ranking.twelvelabs, "analyze_clip", lambda url, prompt="": "5"
    )

    def fail(*_a, **_k):
        raise AssertionError("Gemini must not run while TwelveLabs is enabled")

    monkeypatch.setattr(platform_auto_ranking.gemini_video, "analyze_clip", fail)

    chosen = platform_auto_ranking.choose_clip(
        "Praias", "Ilha", [_material("https://x/a.mp4")], downloader=fail
    )

    assert chosen.url == "https://x/a.mp4"


def test_gemini_is_skipped_without_a_downloader(monkeypatch):
    monkeypatch.setattr(platform_auto_ranking.twelvelabs, "is_enabled", lambda: False)
    monkeypatch.setattr(platform_auto_ranking.gemini_video, "is_enabled", lambda: True)

    def fail(*_a, **_k):
        raise AssertionError("Gemini needs a local file, so it must not run here")

    monkeypatch.setattr(platform_auto_ranking.gemini_video, "analyze_clip", fail)
    candidates = [_material("https://x/a.mp4"), _material("https://x/b.mp4")]

    assert platform_auto_ranking.choose_clip("Praias", "Ilha", candidates) is candidates[0]


def test_gemini_skips_candidates_that_fail_to_download(monkeypatch):
    monkeypatch.setattr(platform_auto_ranking.twelvelabs, "is_enabled", lambda: False)
    monkeypatch.setattr(platform_auto_ranking.gemini_video, "is_enabled", lambda: True)
    analyzed = []

    def analyze(path, prompt=""):
        analyzed.append(path)
        return "8"

    monkeypatch.setattr(platform_auto_ranking.gemini_video, "analyze_clip", analyze)
    candidates = [_material("https://x/a.mp4"), _material("https://x/b.mp4")]

    chosen = platform_auto_ranking.choose_clip(
        "Praias",
        "Ilha",
        candidates,
        downloader=lambda c: "" if c.url.endswith("a.mp4") else "/tmp/b.mp4",
    )

    assert analyzed == ["/tmp/b.mp4"]
    assert chosen.url == "https://x/b.mp4"


def test_analysis_url_resolves_social_page_to_media_url(monkeypatch):
    monkeypatch.setattr(
        platform_auto_ranking.social_sources,
        "resolve_stream_url",
        lambda url: f"{url}/stream.mp4",
    )
    social = _material("https://youtu.be/x", provider="youtube")
    stock = _material("https://cdn/direct.mp4", provider="pexels")

    assert platform_auto_ranking._analysis_url(social) == (
        "https://youtu.be/x/stream.mp4"
    )
    assert platform_auto_ranking._analysis_url(stock) == "https://cdn/direct.mp4"


def test_choose_clip_skips_social_candidates_that_cannot_be_resolved(monkeypatch):
    monkeypatch.setattr(platform_auto_ranking.twelvelabs, "is_enabled", lambda: True)
    monkeypatch.setattr(
        platform_auto_ranking.social_sources,
        "resolve_stream_url",
        lambda url: None if url.endswith("a") else "https://cdn/b.mp4",
    )
    analyzed = []

    def analyze(url, prompt=""):
        analyzed.append(url)
        return "8"

    monkeypatch.setattr(platform_auto_ranking.twelvelabs, "analyze_clip", analyze)
    candidates = [
        _material("https://youtu.be/a", provider="youtube"),
        _material("https://youtu.be/b", provider="youtube"),
    ]

    chosen = platform_auto_ranking.choose_clip("Praias", "Ilha", candidates)

    assert analyzed == ["https://cdn/b.mp4"]
    assert chosen.url == "https://youtu.be/b"


def test_search_candidates_dispatches_to_social_sources(monkeypatch):
    calls = {}

    def fake_youtube(search_term, minimum_duration, video_aspect):
        calls["youtube"] = (search_term, minimum_duration)
        return [_material("https://youtu.be/x", provider="youtube")]

    monkeypatch.setattr(
        platform_auto_ranking.social_sources, "search_videos_youtube", fake_youtube
    )

    items = platform_auto_ranking._search_candidates(
        "beach", "youtube", VideoAspect.portrait, 7
    )

    assert calls["youtube"] == ("beach", 7)
    assert items[0].provider == "youtube"


def test_download_candidate_uses_yt_dlp_for_social_sources(monkeypatch):
    calls = {}

    def fake_social_download(page_url, save_dir, seconds):
        calls["social"] = (page_url, save_dir, seconds)
        return "/tasks/t/social-x.mp4"

    def fake_stock_download(video_url, save_dir=""):
        calls["stock"] = (video_url, save_dir)
        return "/tasks/t/vid-y.mp4"

    monkeypatch.setattr(
        platform_auto_ranking.social_sources, "download_video", fake_social_download
    )
    monkeypatch.setattr(
        platform_auto_ranking.material, "save_video", fake_stock_download
    )

    social_path = platform_auto_ranking._download_candidate(
        _material("https://youtu.be/x", provider="youtube"), "/tasks/t", 7
    )
    stock_path = platform_auto_ranking._download_candidate(
        _material("https://cdn/y.mp4", provider="pexels"), "/tasks/t", 7
    )

    assert calls["social"] == ("https://youtu.be/x", "/tasks/t", 7)
    assert calls["stock"] == ("https://cdn/y.mp4", "/tasks/t")
    assert social_path == "/tasks/t/social-x.mp4"
    assert stock_path == "/tasks/t/vid-y.mp4"


def _auto_generation(client, project, **body):
    editorial_format = client.get(
        f"/api/v2/projects/{project['id']}/editorial-formats"
    ).json()[0]
    payload = {
        "video_subject": "Praias do Brasil",
        "editorial_format_id": editorial_format["id"],
        "auto_ranking": True,
    }
    payload.update(body)
    return client.post(
        f"/api/v2/projects/{project['id']}/generations", json=payload
    )


def _project(client):
    return client.post("/api/v2/projects", json={"name": "Ranking"}).json()


def test_auto_ranking_generation_uses_automatic_worker(auth_context, monkeypatch):
    client, _ = auth_context
    assert login(client, "user@example.com", USER_PASSWORD).status_code == 200
    project = _project(client)
    queued = []
    monkeypatch.setattr(
        "app.services.platform_generations.task_manager.add_task",
        lambda function, **kwargs: queued.append((function, kwargs)),
    )

    response = _auto_generation(client, project, ranking_size=3)

    assert response.status_code == 201
    assert queued[0][0].__name__ == "execute_auto_ranking_generation"
    snapshot = response.json()["editorial_format_snapshot"]
    assert snapshot["auto_ranking"] is True
    assert snapshot["ranking_items"] == []
    assert snapshot["configuration"]["ranking_size"] == 3


def test_auto_ranking_rejects_explicit_items(auth_context, monkeypatch):
    client, _ = auth_context
    assert login(client, "user@example.com", USER_PASSWORD).status_code == 200
    project = _project(client)
    monkeypatch.setattr(
        "app.services.platform_generations.task_manager.add_task",
        lambda function, **kwargs: None,
    )

    response = _auto_generation(
        client,
        project,
        ranking_items=[
            {"position": 1, "title": "Um", "asset_id": "asset-1"},
            {"position": 2, "title": "Dois", "asset_id": "asset-2"},
        ],
    )

    assert response.status_code == 422


def test_prepare_auto_ranking_items_downloads_and_registers_assets(
    auth_context, monkeypatch, tmp_path
):
    client, session_factory = auth_context
    assert login(client, "user@example.com", USER_PASSWORD).status_code == 200
    project = _project(client)
    monkeypatch.setattr(
        "app.services.platform_generations.task_manager.add_task",
        lambda function, **kwargs: None,
    )
    generation_id = _auto_generation(client, project, ranking_size=3).json()["id"]

    monkeypatch.setattr(
        platform_auto_ranking.llm,
        "_generate_response",
        lambda prompt: _plan_response(
            [
                {"position": 1, "title": "Um", "search_term": "one"},
                {"position": 2, "title": "Dois", "search_term": "two"},
                {"position": 3, "title": "Tres", "search_term": "three"},
            ]
        ),
    )
    monkeypatch.setattr(platform_auto_ranking.twelvelabs, "is_enabled", lambda: False)
    monkeypatch.setattr(
        platform_auto_ranking,
        "_search_candidates",
        lambda search_term, source, video_aspect, minimum_duration: (
            [] if search_term == "two" else [_material(f"https://{search_term}.mp4")]
        ),
    )

    task_root = tmp_path / "tasks"
    task_root.mkdir()
    monkeypatch.setattr(
        platform_auto_ranking.utils,
        "task_dir",
        lambda sub_dir="": str(task_root / sub_dir) if sub_dir else str(task_root),
    )

    def fake_save(video_url, save_dir=""):
        target = task_root / "task-1"
        target.mkdir(exist_ok=True)
        path = target / f"{video_url.rsplit('/', 1)[-1]}"
        path.write_bytes(b"video-bytes")
        return str(path)

    monkeypatch.setattr(platform_auto_ranking.material, "save_video", fake_save)

    with session_factory() as db:
        from app.database.models import Asset, Generation

        generation = db.get(Generation, generation_id)
        platform_auto_ranking.prepare_auto_ranking_items(db, generation, "task-1")
        items = generation.editorial_format_snapshot["ranking_items"]
        db.commit()

        # "two" had no footage, so the remaining items are renumbered 1..2.
        assert [item["position"] for item in items] == [1, 2]
        assert [item["title"] for item in items] == ["Um", "Tres"]
        assets = {
            asset.id: asset
            for asset in db.query(Asset).filter(
                Asset.generation_id == generation_id
            )
        }
        assert len(assets) == 2
        for item in items:
            asset = assets[item["asset_id"]]
            assert asset.kind == "source_video"
            assert asset.storage_key.startswith("task-1/")
            assert asset.size_bytes == len(b"video-bytes")


def test_prepare_auto_ranking_items_uses_youtube_when_selected(
    auth_context, monkeypatch, tmp_path
):
    client, session_factory = auth_context
    assert login(client, "user@example.com", USER_PASSWORD).status_code == 200
    project = _project(client)
    monkeypatch.setattr(
        "app.services.platform_generations.task_manager.add_task",
        lambda function, **kwargs: None,
    )
    generation_id = _auto_generation(
        client,
        project,
        ranking_size=2,
        overrides={"video_source": "youtube"},
    ).json()["id"]

    monkeypatch.setattr(
        platform_auto_ranking.llm,
        "_generate_response",
        lambda prompt: _plan_response(
            [
                {"position": 1, "title": "Um", "search_term": "one"},
                {"position": 2, "title": "Dois", "search_term": "two"},
            ]
        ),
    )
    monkeypatch.setattr(platform_auto_ranking.twelvelabs, "is_enabled", lambda: False)

    searched = []

    def fake_youtube(search_term, minimum_duration, video_aspect):
        searched.append(search_term)
        return [_material(f"https://youtu.be/{search_term}", provider="youtube")]

    monkeypatch.setattr(
        platform_auto_ranking.social_sources, "search_videos_youtube", fake_youtube
    )

    task_root = tmp_path / "tasks"
    task_root.mkdir()
    monkeypatch.setattr(
        platform_auto_ranking.utils,
        "task_dir",
        lambda sub_dir="": str(task_root / sub_dir) if sub_dir else str(task_root),
    )
    downloads = []

    def fake_social_download(page_url, save_dir, seconds):
        downloads.append((page_url, seconds))
        target = task_root / "task-yt"
        target.mkdir(exist_ok=True)
        path = target / f"social-{page_url.rsplit('/', 1)[-1]}.mp4"
        path.write_bytes(b"clip")
        return str(path)

    monkeypatch.setattr(
        platform_auto_ranking.social_sources, "download_video", fake_social_download
    )

    with session_factory() as db:
        from app.database.models import Asset, Generation

        generation = db.get(Generation, generation_id)
        clip_duration = generation.editorial_format_snapshot["configuration"][
            "clip_duration"
        ]
        platform_auto_ranking.prepare_auto_ranking_items(db, generation, "task-yt")
        items = generation.editorial_format_snapshot["ranking_items"]
        db.commit()

        assert searched == ["one", "two"]
        # Only the seconds the renderer actually uses get downloaded.
        assert [seconds for _, seconds in downloads] == [clip_duration] * 2
        assert [item["source_url"] for item in items] == [
            "https://youtu.be/one",
            "https://youtu.be/two",
        ]
        providers = {
            asset.source_provider
            for asset in db.query(Asset).filter(Asset.generation_id == generation_id)
        }
        assert providers == {"youtube"}


def test_prepare_auto_ranking_items_fails_without_enough_footage(
    auth_context, monkeypatch
):
    client, session_factory = auth_context
    assert login(client, "user@example.com", USER_PASSWORD).status_code == 200
    project = _project(client)
    monkeypatch.setattr(
        "app.services.platform_generations.task_manager.add_task",
        lambda function, **kwargs: None,
    )
    generation_id = _auto_generation(client, project).json()["id"]

    monkeypatch.setattr(
        platform_auto_ranking.llm,
        "_generate_response",
        lambda prompt: _plan_response(
            [
                {"position": 1, "title": "Um", "search_term": "one"},
                {"position": 2, "title": "Dois", "search_term": "two"},
            ]
        ),
    )
    monkeypatch.setattr(platform_auto_ranking.twelvelabs, "is_enabled", lambda: False)
    monkeypatch.setattr(
        platform_auto_ranking,
        "_search_candidates",
        lambda search_term, source, video_aspect, minimum_duration: [],
    )

    with session_factory() as db:
        from app.database.models import Generation

        generation = db.get(Generation, generation_id)
        with pytest.raises(RankingStageError) as error:
            platform_auto_ranking.prepare_auto_ranking_items(db, generation, "task-2")

    assert error.value.stage == "ranking_materials"
