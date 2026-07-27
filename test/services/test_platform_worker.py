from sqlalchemy import select

from app.database.models import Generation, Project, User, WorkspaceMembership
from app.models import const
from app.services import platform_worker, state as sm


def test_worker_persists_completed_generation(auth_context, monkeypatch):
    _, session_factory = auth_context
    with session_factory.begin() as db:
        user = db.scalar(select(User).where(User.email == "user@example.com"))
        membership = db.scalar(
            select(WorkspaceMembership).where(WorkspaceMembership.user_id == user.id)
        )
        project = Project(
            workspace_id=membership.workspace_id,
            name="Worker project",
            slug="worker-project",
            created_by=user.id,
        )
        db.add(project)
        db.flush()
        generation = Generation(
            workspace_id=membership.workspace_id,
            project_id=project.id,
            requested_by=user.id,
            legacy_task_id="persistent-task",
            status="queued",
            video_subject="Persistent task",
            resolved_configuration={},
        )
        db.add(generation)
        db.flush()
        generation_id = generation.id

    monkeypatch.setattr(platform_worker, "SessionLocal", session_factory)

    def complete_task(task_id, **_kwargs):
        sm.state.update_task(
            task_id,
            state=const.TASK_STATE_COMPLETE,
            progress=100,
            script="Persisted script",
        )
        return {"script": "Persisted script"}

    monkeypatch.setattr(platform_worker.tm, "start", complete_task)
    result = platform_worker.execute_generation(
        generation_id=generation_id,
        task_id="persistent-task",
        params=object(),
    )

    assert result == {"script": "Persisted script"}
    with session_factory() as db:
        stored = db.get(Generation, generation_id)
        assert stored.status == "completed"
        assert stored.script == "Persisted script"
        assert stored.started_at is not None
        assert stored.completed_at is not None


def test_worker_marks_missing_task_after_restart(auth_context, monkeypatch):
    _, session_factory = auth_context
    with session_factory.begin() as db:
        user = db.scalar(select(User).where(User.email == "user@example.com"))
        membership = db.scalar(
            select(WorkspaceMembership).where(WorkspaceMembership.user_id == user.id)
        )
        project = Project(
            workspace_id=membership.workspace_id,
            name="Restart project",
            slug="restart-project",
            created_by=user.id,
        )
        db.add(project)
        db.flush()
        generation = Generation(
            workspace_id=membership.workspace_id,
            project_id=project.id,
            requested_by=user.id,
            legacy_task_id="missing-after-restart",
            status="processing",
            video_subject="Interrupted task",
            resolved_configuration={},
        )
        db.add(generation)
        db.flush()
        generation_id = generation.id

    monkeypatch.setattr(platform_worker, "SessionLocal", session_factory)
    assert platform_worker.reconcile_interrupted_generations() == 1
    with session_factory() as db:
        stored = db.get(Generation, generation_id)
        assert stored.status == "failed"
        assert stored.error_stage == "restart"
