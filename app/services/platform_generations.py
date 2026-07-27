from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.controllers.manager.base_manager import TaskQueueFullError
from app.controllers.v1.video import task_manager
from app.database.models import CreativeProfile, Generation, GenerationPreset, Project, User
from app.models.platform_schema import CreativeGenerationRequest, CreativeScriptRequest
from app.services import (
    platform_auth,
    platform_auto_ranking,
    platform_creative,
    platform_editorial_formats,
    platform_ranking,
    platform_worker,
    state as sm,
)
from app.utils import utils


def profile_and_preset(
    db: Session, project_id: str, preset_id: str | None
) -> tuple[CreativeProfile, GenerationPreset | None]:
    if preset_id:
        preset = db.get(GenerationPreset, preset_id)
        if preset is None or preset.project_id != project_id:
            raise HTTPException(status_code=404, detail="preset not found")
        profile = db.get(CreativeProfile, preset.creative_profile_id)
        if profile is None:
            raise HTTPException(status_code=400, detail="preset has no creative profile")
        return profile, preset

    profile = db.scalar(
        select(CreativeProfile)
        .where(
            CreativeProfile.project_id == project_id,
            CreativeProfile.is_active.is_(True),
        )
        .order_by(CreativeProfile.created_at.desc())
    )
    if profile is None:
        raise HTTPException(
            status_code=400, detail="project has no active creative profile"
        )
    preset = db.scalar(
        select(GenerationPreset).where(
            GenerationPreset.project_id == project_id,
            GenerationPreset.is_default.is_(True),
        )
    )
    return profile, preset


def resolve_params(
    db: Session,
    project_id: str,
    body: CreativeScriptRequest,
    preset_id: str | None,
    overrides: dict | None = None,
):
    profile, preset = profile_and_preset(db, project_id, preset_id)
    params = platform_creative.resolve_video_params(
        profile_config=profile.configuration,
        preset_config=preset.configuration if preset else {},
        subject=body.video_subject,
        narrative_structure=body.narrative_structure,
        paragraph_number=body.paragraph_number,
        overrides=overrides or {},
    )
    return profile, preset, params


def enqueue_generation(
    db: Session,
    *,
    project: Project,
    body: CreativeGenerationRequest,
    requested_by: User,
    idempotency_key: str | None,
) -> Generation:
    if idempotency_key:
        existing = db.scalar(
            select(Generation).where(
                Generation.project_id == project.id,
                Generation.idempotency_key == idempotency_key,
            )
        )
        if existing:
            return existing

    profile, preset, params = resolve_params(
        db, project.id, body, body.preset_id, body.overrides
    )
    editorial_format = (
        platform_editorial_formats.get_format(
            db, project.id, body.editorial_format_id
        )
        if body.editorial_format_id
        else platform_editorial_formats.get_default_format(db, project.id)
    )
    if body.auto_ranking:
        if body.ranking_items:
            raise HTTPException(
                status_code=422,
                detail="auto_ranking cannot be combined with explicit ranking items",
            )
        if editorial_format is None or editorial_format.format_type != "ranking":
            raise HTTPException(
                status_code=422,
                detail="auto_ranking requires a ranking editorial format",
            )

    editorial_snapshot = {}
    if editorial_format:
        if body.ranking_items:
            if len(body.ranking_items) < 2:
                raise HTTPException(
                    status_code=422,
                    detail="ranking requires at least two items",
                )
            positions = [item.position for item in body.ranking_items]
            if len(set(positions)) != len(positions):
                raise HTTPException(
                    status_code=422,
                    detail="ranking positions must be unique",
                )
            if any(not item.asset_id for item in body.ranking_items):
                raise HTTPException(
                    status_code=422,
                    detail="every ranking item requires a video asset",
                )
        configuration = editorial_format.configuration
        if body.auto_ranking:
            # The automatic pipeline reads clip_duration/ranking_size directly,
            # so normalize the snapshot instead of trusting stored values.
            overrides = (
                {"ranking_size": body.ranking_size} if body.ranking_size else {}
            )
            configuration = platform_editorial_formats.normalized_configuration(
                {**configuration, **overrides}
            )
        editorial_snapshot = {
            "name": editorial_format.name,
            "format_type": editorial_format.format_type,
            "configuration": configuration,
            "auto_ranking": body.auto_ranking,
            "ranking_items": [
                item.model_dump(mode="json") for item in body.ranking_items
            ],
        }
    task_id = utils.get_uuid()
    generation = Generation(
        workspace_id=project.workspace_id,
        project_id=project.id,
        preset_id=preset.id if preset else None,
        creative_profile_id=profile.id,
        creative_profile_version=profile.version,
        editorial_format_id=editorial_format.id if editorial_format else None,
        editorial_format_snapshot=editorial_snapshot,
        legacy_task_id=task_id,
        requested_by=requested_by.id,
        idempotency_key=idempotency_key,
        status="queued",
        video_subject=body.video_subject,
        resolved_configuration=params.model_dump(mode="json"),
    )
    db.add(generation)
    db.flush()
    platform_auth.audit(
        db,
        "generation.created",
        "generation",
        generation.id,
        requested_by.id,
        project.workspace_id,
    )
    # The worker runs in another database session. Commit the record before
    # handing work to its thread so SQLite/PostgreSQL can see it immediately.
    db.commit()
    sm.state.update_task(task_id)
    try:
        if body.auto_ranking:
            task_manager.add_task(
                platform_auto_ranking.execute_auto_ranking_generation,
                generation_id=generation.id,
                task_id=task_id,
            )
        elif body.ranking_items:
            task_manager.add_task(
                platform_ranking.execute_ranking_generation,
                generation_id=generation.id,
                task_id=task_id,
            )
        else:
            task_manager.add_task(
                platform_worker.execute_generation,
                generation_id=generation.id,
                task_id=task_id,
                params=params,
                stop_at="video",
            )
    except TaskQueueFullError as exc:
        sm.state.delete_task(task_id)
        generation.status = "failed"
        generation.error_stage = "queue"
        generation.error_message = str(exc)
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=str(exc)
        ) from exc
    return generation
