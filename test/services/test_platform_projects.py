from app.database.models import Project, User
from test.services.test_platform_auth import (
    ADMIN_PASSWORD,
    USER_PASSWORD,
    login,
)

pytest_plugins = ["test.services.test_platform_auth"]


def test_user_creates_project_with_default_profile(auth_context):
    client, _ = auth_context
    assert login(client, "user@example.com", USER_PASSWORD).status_code == 200

    response = client.post(
        "/api/v2/projects",
        json={
            "name": "Produtividade sem distrações",
            "niche": "produtividade",
            "target_audience": "profissionais brasileiros",
        },
    )

    assert response.status_code == 201
    project = response.json()
    assert project["slug"] == "produtividade-sem-distracoes"

    profiles = client.get(
        f"/api/v2/projects/{project['id']}/creative-profiles"
    )
    assert profiles.status_code == 200
    assert profiles.json()[0]["name"] == "Perfil padrão"


def test_project_profile_versions_and_preset(auth_context):
    client, _ = auth_context
    assert login(client, "user@example.com", USER_PASSWORD).status_code == 200
    project = client.post("/api/v2/projects", json={"name": "Curiosidades"}).json()
    default_profile = client.get(
        f"/api/v2/projects/{project['id']}/creative-profiles"
    ).json()[0]

    version = client.post(
        f"/api/v2/projects/{project['id']}/creative-profiles/{default_profile['id']}/versions",
        json={
            "name": "ignorado pelo versionamento",
            "configuration": {"editorial": {"tone": "casual"}},
        },
    )
    assert version.status_code == 201
    assert version.json()["version"] == 2
    assert version.json()["configuration"]["editorial"]["tone"] == "casual"

    preset = client.post(
        f"/api/v2/projects/{project['id']}/presets",
        json={
            "name": "Short casual",
            "creative_profile_id": version.json()["id"],
            "platform": "youtube_shorts",
            "configuration": {"video_aspect": "9:16", "subtitle_enabled": True},
            "is_default": True,
        },
    )
    assert preset.status_code == 201
    assert preset.json()["is_default"] is True


def test_project_has_editable_default_ranking_format(auth_context):
    client, _ = auth_context
    assert login(client, "user@example.com", USER_PASSWORD).status_code == 200
    project = client.post(
        "/api/v2/projects", json={"name": "Ranking diário"}
    ).json()

    formats = client.get(
        f"/api/v2/projects/{project['id']}/editorial-formats"
    )
    assert formats.status_code == 200
    default_format = formats.json()[0]
    assert default_format["format_type"] == "ranking"
    assert default_format["is_default"] is True
    assert default_format["configuration"]["ranking_size"] == 5

    updated = client.patch(
        f"/api/v2/projects/{project['id']}/editorial-formats/{default_format['id']}",
        json={
            "name": "Top 7 gatos",
            "configuration": {
                **default_format["configuration"],
                "ranking_size": 7,
                "title_position": {"x": 47.5, "y": 9},
                "accent_color": "#00ff88",
            },
        },
    )
    assert updated.status_code == 200
    assert updated.json()["name"] == "Top 7 gatos"
    assert updated.json()["configuration"]["ranking_size"] == 7
    assert updated.json()["configuration"]["title_position"]["x"] == 47.5


def test_user_cannot_access_another_users_project(auth_context):
    client, session_factory = auth_context
    assert login(client, "admin@example.com", ADMIN_PASSWORD).status_code == 200
    response = client.post("/api/v2/admin/users", json={
        "email": "other@example.com",
        "display_name": "Other",
        "password": "Other-password-123",
    })
    assert response.status_code == 201
    other_id = response.json()["id"]
    with session_factory() as db:
        other = db.get(User, other_id)
        project = Project(
            workspace_id=other.memberships[0].workspace_id,
            name="Privado",
            slug="privado",
            created_by=other.id,
        )
        db.add(project)
        db.commit()
        project_id = project.id

    client.cookies.clear()
    assert login(client, "user@example.com", USER_PASSWORD).status_code == 200
    assert client.get(f"/api/v2/projects/{project_id}").status_code == 404
