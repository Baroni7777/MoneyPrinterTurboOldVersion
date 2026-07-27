"""Durable database updates around executions of the legacy video pipeline."""

from datetime import datetime, timezone

from sqlalchemy import select

from app.database.models import Generation
from app.database.session import SessionLocal
from app.models import const
from app.services import platform_assets, state as sm, task as tm


def _sync_generation_from_task(generation: Generation, task: dict) -> None:
    task_state = task.get("state")
    if task_state == const.TASK_STATE_FAILED:
        generation.status = "failed"
        generation.completed_at = datetime.now(timezone.utc)
    elif task_state == const.TASK_STATE_COMPLETE:
        generation.status = "completed"
        generation.completed_at = datetime.now(timezone.utc)
    else:
        generation.status = "processing"
    generation.script = task.get("script", generation.script)
    generation.error_stage = task.get("failed_stage")
    generation.error_message = task.get("error")


def execute_generation(
    generation_id: str,
    task_id: str,
    params,
    stop_at: str = "video",
) -> dict:
    """Run one task and persist its terminal status before the worker exits."""

    with SessionLocal() as db:
        generation = db.get(Generation, generation_id)
        if generation is None:
            return {"error": "generation not found"}
        generation.status = "processing"
        generation.started_at = generation.started_at or datetime.now(timezone.utc)
        db.commit()

        result = tm.start(task_id=task_id, params=params, stop_at=stop_at)
        task = sm.state.get_task(task_id)
        if task:
            _sync_generation_from_task(generation, task)
            platform_assets.sync_task_outputs(db, generation, task)
        elif isinstance(result, dict) and result.get("error"):
            generation.status = "failed"
            generation.error_stage = "worker"
            generation.error_message = str(result["error"])
            generation.completed_at = datetime.now(timezone.utc)
        db.commit()
        return result


def reconcile_interrupted_generations() -> int:
    """Mark work lost by a non-durable worker restart as retryable failure."""

    reconciled = 0
    with SessionLocal() as db:
        active_generations = db.scalars(
            select(Generation).where(Generation.status.in_(("queued", "processing")))
        )
        for generation in active_generations:
            if generation.legacy_task_id and sm.state.get_task(generation.legacy_task_id):
                continue
            generation.status = "failed"
            generation.error_stage = "restart"
            generation.error_message = "generation interrupted by a worker restart"
            generation.completed_at = datetime.now(timezone.utc)
            reconciled += 1
        if reconciled:
            db.commit()
    return reconciled
