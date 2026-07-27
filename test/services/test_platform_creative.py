from app.database.models import Generation
from app.models import const
from app.services import state as sm
from test.services.test_platform_auth import USER_PASSWORD, login

pytest_plugins = ["test.services.test_platform_auth"]


def _project_and_profile(client):
    project = client.post("/api/v2/projects", json={"name": "Criativo"}).json()
    profile = client.get(
        f"/api/v2/projects/{project['id']}/creative-profiles"
    ).json()[0]
    return project, profile


def test_creative_script_and_scene_plan(auth_context, monkeypatch):
    client, _ = auth_context
    assert login(client, "user@example.com", USER_PASSWORD).status_code == 200
    project, _ = _project_and_profile(client)

    monkeypatch.setattr(
        "app.controllers.v2.creative.llm.generate_script",
        lambda *args, **kwargs: "Primeira parte.\n\nSegunda parte.",
    )
    monkeypatch.setattr(
        "app.controllers.v2.creative.llm.generate_terms",
        lambda *args, **kwargs: ["first visual", "second visual"],
    )

    script = client.post(
        f"/api/v2/projects/{project['id']}/creative/scripts",
        json={"video_subject": "Foco no trabalho", "narrative_structure": "problem_solution"},
    )
    assert script.status_code == 200
    assert "perspectiva original" in script.json()["video_script_prompt"]

    scene_plan = client.post(
        f"/api/v2/projects/{project['id']}/creative/scene-plans",
        json={"video_subject": "Foco", "video_script": "A.\n\nB."},
    )
    assert scene_plan.status_code == 200
    assert len(scene_plan.json()["scene_plan"]["scenes"]) == 2


def test_generation_enqueues_existing_pipeline_and_tracks_task(auth_context, monkeypatch):
    client, session_factory = auth_context
    assert login(client, "user@example.com", USER_PASSWORD).status_code == 200
    project, _ = _project_and_profile(client)
    queued = []

    def capture_task(*args, **kwargs):
        with session_factory() as db:
            assert db.get(Generation, kwargs["generation_id"]) is not None
        queued.append((args, kwargs))

    monkeypatch.setattr(
        "app.services.platform_generations.task_manager.add_task", capture_task
    )
    response = client.post(
        f"/api/v2/projects/{project['id']}/generations",
        headers={"Idempotency-Key": "n8n-1"},
        json={"video_subject": "Como manter o foco"},
    )
    assert response.status_code == 201
    generation = response.json()
    assert queued
    assert queued[0][1]["params"].match_materials_to_script is True
    assert generation["editorial_format_id"] is not None
    assert generation["editorial_format_snapshot"]["format_type"] == "ranking"
    assert (
        generation["editorial_format_snapshot"]["configuration"]["ranking_size"]
        == 5
    )

    duplicate = client.post(
        f"/api/v2/projects/{project['id']}/generations",
        headers={"Idempotency-Key": "n8n-1"},
        json={"video_subject": "Como manter o foco"},
    )
    assert duplicate.status_code == 201
    assert duplicate.json()["id"] == generation["id"]

    sm.state.update_task(
        generation["legacy_task_id"],
        state=const.TASK_STATE_COMPLETE,
        progress=100,
        script="Roteiro concluído",
    )
    tracked = client.get(
        f"/api/v2/projects/{project['id']}/generations/{generation['id']}"
    )
    assert tracked.status_code == 200
    assert tracked.json()["status"] == "completed"
    assert tracked.json()["script"] == "Roteiro concluído"


def test_ranking_generation_uses_dedicated_renderer(auth_context, monkeypatch):
    client, _ = auth_context
    assert login(client, "user@example.com", USER_PASSWORD).status_code == 200
    project, _ = _project_and_profile(client)
    editorial_format = client.get(
        f"/api/v2/projects/{project['id']}/editorial-formats"
    ).json()[0]
    queued = []
    monkeypatch.setattr(
        "app.services.platform_generations.task_manager.add_task",
        lambda function, **kwargs: queued.append((function, kwargs)),
    )

    response = client.post(
        f"/api/v2/projects/{project['id']}/generations",
        json={
            "video_subject": "Funny cats",
            "editorial_format_id": editorial_format["id"],
            "ranking_items": [
                {"position": 2, "title": "Segundo", "asset_id": "asset-2"},
                {"position": 1, "title": "Primeiro", "asset_id": "asset-1"},
            ],
        },
    )

    assert response.status_code == 201
    assert queued[0][0].__name__ == "execute_ranking_generation"
    ranking_items = response.json()["editorial_format_snapshot"][
        "ranking_items"
    ]
    assert ranking_items[0]["position"] == 2
