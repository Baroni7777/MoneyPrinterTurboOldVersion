from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.controllers.v2.base import get_api_key_actor, new_router
from app.database.models import Generation
from app.database.session import get_db_session
from app.models.platform_schema import CreativeGenerationRequest, GenerationResponse
from app.services import platform_api_keys, platform_generations, platform_projects

router = new_router(["V2 Automation"])


def _project_for_key(
    db: Session, actor: platform_api_keys.ApiKeyActor, project_id: str
):
    project = platform_projects.get_project_access(db, actor.user, project_id, write=True)
    key = actor.key
    if key.project_id and key.project_id != project.id:
        raise HTTPException(status_code=403, detail="API key is limited to another project")
    if key.workspace_id != project.workspace_id:
        raise HTTPException(status_code=403, detail="API key is limited to another workspace")
    return project


@router.post(
    "/automation/projects/{project_id}/generations",
    response_model=GenerationResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_automation_generation(
    project_id: str,
    body: CreativeGenerationRequest,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    actor: platform_api_keys.ApiKeyActor = Depends(get_api_key_actor),
    db: Session = Depends(get_db_session),
):
    platform_api_keys.require_scope(actor, "generations:create")
    project = _project_for_key(db, actor, project_id)
    generation = platform_generations.enqueue_generation(
        db,
        project=project,
        body=body,
        requested_by=actor.user,
        idempotency_key=idempotency_key,
    )
    db.commit()
    db.refresh(generation)
    return generation


@router.get(
    "/automation/projects/{project_id}/generations/{generation_id}",
    response_model=GenerationResponse,
)
def get_automation_generation(
    project_id: str,
    generation_id: str,
    actor: platform_api_keys.ApiKeyActor = Depends(get_api_key_actor),
    db: Session = Depends(get_db_session),
):
    platform_api_keys.require_scope(actor, "generations:read")
    project = _project_for_key(db, actor, project_id)
    generation = db.get(Generation, generation_id)
    if generation is None or generation.project_id != project.id:
        raise HTTPException(status_code=404, detail="generation not found")
    return generation
