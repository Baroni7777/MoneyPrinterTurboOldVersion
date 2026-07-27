from app.models import const
from app.services import state as sm
from test.services.test_platform_auth import USER_PASSWORD, login

pytest_plugins = ["test.services.test_platform_auth"]


def test_generation_output_is_private_and_downloadable(auth_context, monkeypatch, tmp_path):
    client, _ = auth_context
    assert login(client, "user@example.com", USER_PASSWORD).status_code == 200
    project_response = client.post("/api/v2/projects", json={"name": "Privado"})
    project = project_response.json()
    monkeypatch.setattr(
        "app.services.platform_generations.task_manager.add_task",
        lambda *args, **kwargs: None,
    )
    created = client.post(
        f"/api/v2/projects/{project['id']}/generations",
        json={"video_subject": "Arquivo protegido"},
    )
    generation = created.json()
    task_root = tmp_path / "tasks"
    output_path = task_root / generation["legacy_task_id"] / "final.mp4"
    output_path.parent.mkdir(parents=True)
    output_path.write_bytes(b"fake-video")
    monkeypatch.setattr("app.services.platform_assets.utils.task_dir", lambda: str(task_root))
    monkeypatch.setattr("app.controllers.v2.assets.utils.task_dir", lambda: str(task_root))
    sm.state.update_task(
        generation["legacy_task_id"],
        state=const.TASK_STATE_COMPLETE,
        progress=100,
        videos=[str(output_path)],
    )

    tracked = client.get(
        f"/api/v2/projects/{project['id']}/generations/{generation['id']}"
    )
    assert tracked.status_code == 200
    assets = client.get(
        f"/api/v2/projects/{project['id']}/generations/{generation['id']}/assets"
    )
    assert assets.status_code == 200
    assert len(assets.json()) == 1
    download_url = assets.json()[0]["download_url"]
    download = client.get(download_url)
    assert download.status_code == 200
    assert download.content == b"fake-video"

    other = client.post("/api/v2/auth/logout")
    assert other.status_code == 204
    assert client.get(download_url).status_code == 401


def test_project_video_upload_is_available_to_ranking(
    auth_context, monkeypatch, tmp_path
):
    client, _ = auth_context
    assert login(client, "user@example.com", USER_PASSWORD).status_code == 200
    project = client.post(
        "/api/v2/projects", json={"name": "Clipes próprios"}
    ).json()
    task_root = tmp_path / "tasks"
    task_root.mkdir()

    def temporary_task_dir(sub_dir=""):
        directory = task_root / sub_dir
        directory.mkdir(parents=True, exist_ok=True)
        return str(directory)

    monkeypatch.setattr(
        "app.controllers.v2.assets.utils.task_dir",
        temporary_task_dir,
    )

    uploaded = client.post(
        f"/api/v2/projects/{project['id']}/assets",
        files={"file": ("gato.mp4", b"fake-mp4-content", "video/mp4")},
    )

    assert uploaded.status_code == 201
    assert uploaded.json()["kind"] == "source_video"
    listed = client.get(f"/api/v2/projects/{project['id']}/assets")
    assert listed.status_code == 200
    assert listed.json()[0]["original_filename"] == "gato.mp4"
