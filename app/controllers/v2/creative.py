from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.controllers.v2.base import get_current_user, new_router
from app.database.models import Generation, User
from app.database.session import get_db_session
from app.models.platform_schema import (
    CreativeGenerationRequest,
    CreativeScenePlanRequest,
    CreativeScriptRequest,
    GenerationResponse,
)
from app.services import llm, platform_assets, platform_creative, platform_worker, state as sm
from app.services import platform_generations, platform_projects

router = new_router(["V2 Creative"])


@router.post("/projects/{project_id}/creative/scripts")
def create_script(project_id: str, body: CreativeScriptRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db_session)):
    platform_projects.get_project_access(db, user, project_id, write=True)
    _, _, params = platform_generations.resolve_params(db, project_id, body, None)
    script = llm.generate_script(params.video_subject, params.video_language, params.paragraph_number, params.video_script_prompt, params.custom_system_prompt)
    if not script or script.startswith("Error:"):
        raise HTTPException(status_code=502, detail="script generation failed")
    return {"video_script": script, "video_script_prompt": params.video_script_prompt}


@router.post("/projects/{project_id}/creative/scene-plans")
def create_scene_plan(project_id: str, body: CreativeScenePlanRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db_session)):
    platform_projects.get_project_access(db, user, project_id, write=True)
    _, _, params = platform_generations.resolve_params(db, project_id, body, None)
    script = body.video_script or llm.generate_script(params.video_subject, params.video_language, params.paragraph_number, params.video_script_prompt, params.custom_system_prompt)
    if not script or script.startswith("Error:"):
        raise HTTPException(status_code=502, detail="script generation failed")
    terms = llm.generate_terms(params.video_subject, script, amount=8, match_script_order=True)
    return {"video_script": script, "scene_plan": platform_creative.build_scene_plan(script, terms)}


@router.post("/projects/{project_id}/generations", response_model=GenerationResponse, status_code=status.HTTP_201_CREATED)
def create_generation(project_id: str, body: CreativeGenerationRequest, idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"), user: User = Depends(get_current_user), db: Session = Depends(get_db_session)):
    project = platform_projects.get_project_access(db, user, project_id, write=True)
    generation = platform_generations.enqueue_generation(
        db,
        project=project,
        body=body,
        requested_by=user,
        idempotency_key=idempotency_key,
    )
    db.commit()
    db.refresh(generation)
    return generation


@router.get("/projects/{project_id}/generations", response_model=list[GenerationResponse])
def list_generations(project_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db_session)):
    platform_projects.get_project_access(db, user, project_id)
    return list(db.scalars(select(Generation).where(Generation.project_id == project_id).order_by(Generation.created_at.desc())))


@router.get("/projects/{project_id}/generations/{generation_id}", response_model=GenerationResponse)
def get_generation(project_id: str, generation_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db_session)):
    platform_projects.get_project_access(db, user, project_id)
    generation = db.get(Generation, generation_id)
    if generation is None or generation.project_id != project_id:
        raise HTTPException(status_code=404, detail="generation not found")
    task = sm.state.get_task(generation.legacy_task_id) if generation.legacy_task_id else None
    if task:
        platform_worker._sync_generation_from_task(generation, task)
        platform_assets.sync_task_outputs(db, generation, task)
        db.commit()
    return generation
