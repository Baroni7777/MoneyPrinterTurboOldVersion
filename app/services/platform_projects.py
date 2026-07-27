import re
import unicodedata

from fastapi import HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.database.models import (
    CreativeProfile,
    EditorialFormat,
    GenerationPreset,
    Project,
    User,
    Workspace,
    WorkspaceMembership,
)
from app.services.platform_editorial_formats import RANKING_DEFAULTS


def slugify(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value).encode(
        "ascii", "ignore"
    ).decode()
    slug = re.sub(r"[^a-z0-9]+", "-", normalized.casefold()).strip("-")
    return slug[:140] or "project"


def get_workspace_access(
    db: Session, user: User, workspace_id: str, write: bool = False
) -> Workspace:
    if user.system_role == "admin":
        workspace = db.get(Workspace, workspace_id)
        if workspace:
            return workspace
    membership = db.scalar(
        select(WorkspaceMembership).where(
            WorkspaceMembership.workspace_id == workspace_id,
            WorkspaceMembership.user_id == user.id,
        )
    )
    if membership is None or (write and membership.role not in {"owner", "editor"}):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="workspace not found")
    return membership.workspace


def get_default_workspace(db: Session, user: User) -> Workspace:
    workspace = db.scalar(
        select(Workspace)
        .join(WorkspaceMembership)
        .where(WorkspaceMembership.user_id == user.id)
        .order_by(Workspace.created_at.asc())
    )
    if workspace is None:
        raise HTTPException(status_code=400, detail="user has no workspace")
    return workspace


def get_project_access(
    db: Session, user: User, project_id: str, write: bool = False
) -> Project:
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="project not found")
    get_workspace_access(db, user, project.workspace_id, write=write)
    return project


def create_project(
    db: Session, user: User, *, name: str, niche: str, description: str,
    primary_language: str, target_audience: str, workspace_id: str | None,
) -> Project:
    workspace = (
        get_workspace_access(db, user, workspace_id, write=True)
        if workspace_id
        else get_default_workspace(db, user)
    )
    base_slug = slugify(name)
    slug = base_slug
    suffix = 2
    while db.scalar(select(Project.id).where(Project.workspace_id == workspace.id, Project.slug == slug)):
        slug = f"{base_slug[:130]}-{suffix}"
        suffix += 1
    project = Project(
        workspace_id=workspace.id, name=name.strip(), slug=slug,
        niche=niche.strip(), description=description.strip(),
        primary_language=primary_language.strip() or "pt-BR",
        target_audience=target_audience.strip(), created_by=user.id,
    )
    db.add(project)
    db.flush()
    db.add(CreativeProfile(
        project_id=project.id, name="Perfil padrão", version=1,
        configuration={}, created_by=user.id, is_active=True,
    ))
    db.add(
        EditorialFormat(
            project_id=project.id,
            name="Ranking Top 5",
            format_type="ranking",
            configuration=RANKING_DEFAULTS,
            is_default=True,
            created_by=user.id,
        )
    )
    return project


def get_profile_for_project(db: Session, project_id: str, profile_id: str) -> CreativeProfile:
    profile = db.get(CreativeProfile, profile_id)
    if profile is None or profile.project_id != project_id:
        raise HTTPException(status_code=404, detail="creative profile not found")
    return profile


def set_default_preset(db: Session, project_id: str, preset_id: str) -> None:
    db.execute(update(GenerationPreset).where(GenerationPreset.project_id == project_id).values(is_default=False))
    preset = db.get(GenerationPreset, preset_id)
    if preset:
        preset.is_default = True
