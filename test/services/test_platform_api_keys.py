from test.services.test_platform_auth import USER_PASSWORD, login

pytest_plugins = ["test.services.test_platform_auth"]


def _project(client, name: str):
    response = client.post("/api/v2/projects", json={"name": name})
    assert response.status_code == 201
    return response.json()


def _create_key(client, project_id: str):
    response = client.post(
        "/api/v2/api-keys",
        json={
            "name": "n8n production",
            "project_id": project_id,
            "scopes": ["generations:create", "generations:read"],
        },
    )
    assert response.status_code == 201
    return response.json()


def test_key_is_returned_once_and_can_be_revoked(auth_context):
    client, _ = auth_context
    assert login(client, "user@example.com", USER_PASSWORD).status_code == 200
    project = _project(client, "Automacao")

    created = _create_key(client, project["id"])
    assert created["key"].startswith("mpt_")

    listed = client.get("/api/v2/api-keys")
    assert listed.status_code == 200
    assert listed.json()[0]["id"] == created["id"]
    assert "key" not in listed.json()[0]

    revoked = client.delete(f"/api/v2/api-keys/{created['id']}")
    assert revoked.status_code == 204


def test_project_key_runs_automation_only_for_its_project(auth_context, monkeypatch):
    client, _ = auth_context
    assert login(client, "user@example.com", USER_PASSWORD).status_code == 200
    project = _project(client, "Canal A")
    other_project = _project(client, "Canal B")
    created = _create_key(client, project["id"])
    queued = []
    monkeypatch.setattr(
        "app.services.platform_generations.task_manager.add_task",
        lambda *args, **kwargs: queued.append((args, kwargs)),
    )
    client.cookies.clear()

    response = client.post(
        f"/api/v2/automation/projects/{project['id']}/generations",
        headers={"X-API-Key": created["key"], "Idempotency-Key": "n8n-run-1"},
        json={"video_subject": "Como manter consistencia"},
    )
    assert response.status_code == 201
    assert queued

    denied = client.post(
        f"/api/v2/automation/projects/{other_project['id']}/generations",
        headers={"X-API-Key": created["key"]},
        json={"video_subject": "Outro assunto"},
    )
    assert denied.status_code == 403

    status_response = client.get(
        f"/api/v2/automation/projects/{project['id']}/generations/"
        f"{response.json()['id']}",
        headers={"Authorization": f"Bearer {created['key']}"},
    )
    assert status_response.status_code == 200


def test_revoked_key_cannot_call_automation(auth_context, monkeypatch):
    client, _ = auth_context
    assert login(client, "user@example.com", USER_PASSWORD).status_code == 200
    project = _project(client, "Canal")
    created = _create_key(client, project["id"])
    assert client.delete(f"/api/v2/api-keys/{created['id']}").status_code == 204
    monkeypatch.setattr(
        "app.services.platform_generations.task_manager.add_task", lambda *args, **kwargs: None
    )
    client.cookies.clear()

    response = client.post(
        f"/api/v2/automation/projects/{project['id']}/generations",
        headers={"X-API-Key": created["key"]},
        json={"video_subject": "Teste de chave revogada"},
    )
    assert response.status_code == 401


def test_api_key_rate_limit(auth_context, monkeypatch):
    client, _ = auth_context
    assert login(client, "user@example.com", USER_PASSWORD).status_code == 200
    project = _project(client, "Rate limit")
    created = _create_key(client, project["id"])
    monkeypatch.setenv("MPT_API_KEY_RATE_LIMIT_PER_MINUTE", "1")
    from app.services import platform_api_keys

    platform_api_keys._rate_limit_records.clear()
    monkeypatch.setattr(
        "app.services.platform_generations.task_manager.add_task", lambda *args, **kwargs: None
    )
    client.cookies.clear()
    first = client.post(
        f"/api/v2/automation/projects/{project['id']}/generations",
        headers={"X-API-Key": created["key"]},
        json={"video_subject": "Primeira chamada"},
    )
    assert first.status_code == 201
    limited = client.get(
        f"/api/v2/automation/projects/{project['id']}/generations/{first.json()['id']}",
        headers={"X-API-Key": created["key"]},
    )
    assert limited.status_code == 429
