from fastapi import Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.controllers.v2.base import get_current_user, new_router
from app.database.models import (
    CreativeProfile,
    GenerationPreset,
    Project,
    User,
    WorkspaceMembership,
)
from app.database.session import get_db_session
from app.models.platform_schema import (
    CreativeProfileCreateRequest,
    CreativeProfileResponse,
    GenerationPresetCreateRequest,
    GenerationPresetResponse,
    GenerationPresetUpdateRequest,
    ProjectCreateRequest,
    ProjectResponse,
    ProjectUpdateRequest,
)
from app.services import platform_auth, platform_projects

router = new_router(["V2 Projects"])


@router.get("/projects", response_model=list[ProjectResponse])
def list_projects(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session),
):
    query = select(Project)
    if user.system_role != "admin":
        query = query.join(
            WorkspaceMembership,
            WorkspaceMembership.workspace_id == Project.workspace_id,
        ).where(WorkspaceMembership.user_id == user.id)
    return list(db.scalars(query.order_by(Project.created_at.desc())).unique())


@router.post(
    "/projects", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED
)
def create_project(
    body: ProjectCreateRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session),
):
    project = platform_projects.create_project(db, user, **body.model_dump())
    platform_auth.audit(
        db, "project.created", "project", project.id, user.id, project.workspace_id
    )
    db.commit()
    db.refresh(project)
    return project


@router.get("/projects/{project_id}", response_model=ProjectResponse)
def get_project(
    project_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session),
):
    return platform_projects.get_project_access(db, user, project_id)


@router.patch("/projects/{project_id}", response_model=ProjectResponse)
def update_project(
    project_id: str,
    body: ProjectUpdateRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session),
):
    project = platform_projects.get_project_access(db, user, project_id, write=True)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(project, field, value.strip() if isinstance(value, str) else value)
    platform_auth.audit(
        db, "project.updated", "project", project.id, user.id, project.workspace_id
    )
    db.commit()
    db.refresh(project)
    return project


@router.delete("/projects/{project_id}", response_model=ProjectResponse)
def archive_project(
    project_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session),
):
    project = platform_projects.get_project_access(db, user, project_id, write=True)
    project.status = "archived"
    platform_auth.audit(
        db, "project.archived", "project", project.id, user.id, project.workspace_id
    )
    db.commit()
    db.refresh(project)
    return project


@router.get(
    "/projects/{project_id}/creative-profiles",
    response_model=list[CreativeProfileResponse],
)
def list_profiles(
    project_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session),
):
    platform_projects.get_project_access(db, user, project_id)
    return list(
        db.scalars(
            select(CreativeProfile)
            .where(CreativeProfile.project_id == project_id)
            .order_by(CreativeProfile.name, CreativeProfile.version.desc())
        )
    )


@router.post(
    "/projects/{project_id}/creative-profiles",
    response_model=CreativeProfileResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_profile(
    project_id: str,
    body: CreativeProfileCreateRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session),
):
    project = platform_projects.get_project_access(db, user, project_id, write=True)
    existing = db.scalar(
        select(CreativeProfile)
        .where(
            CreativeProfile.project_id == project.id,
            CreativeProfile.name == body.name.strip(),
        )
        .order_by(CreativeProfile.version.desc())
    )
    profile = CreativeProfile(
        project_id=project.id,
        name=body.name.strip(),
        version=(existing.version + 1 if existing else 1),
        configuration=body.configuration,
        created_by=user.id,
    )
    db.add(profile)
    platform_auth.audit(
        db,
        "creative_profile.created",
        "creative_profile",
        profile.id,
        user.id,
        project.workspace_id,
    )
    db.commit()
    db.refresh(profile)
    return profile


@router.post(
    "/projects/{project_id}/creative-profiles/{profile_id}/versions",
    response_model=CreativeProfileResponse,
    status_code=status.HTTP_201_CREATED,
)
def version_profile(
    project_id: str,
    profile_id: str,
    body: CreativeProfileCreateRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session),
):
    project = platform_projects.get_project_access(db, user, project_id, write=True)
    source = platform_projects.get_profile_for_project(db, project.id, profile_id)
    latest = db.scalar(
        select(CreativeProfile)
        .where(
            CreativeProfile.project_id == project.id,
            CreativeProfile.name == source.name,
        )
        .order_by(CreativeProfile.version.desc())
    )
    profile = CreativeProfile(
        project_id=project.id,
        name=source.name,
        version=(latest.version + 1 if latest else source.version + 1),
        configuration=body.configuration,
        created_by=user.id,
    )
    source.is_active = False
    db.add(profile)
    platform_auth.audit(
        db,
        "creative_profile.versioned",
        "creative_profile",
        profile.id,
        user.id,
        project.workspace_id,
    )
    db.commit()
    db.refresh(profile)
    return profile


@router.get(
    "/projects/{project_id}/presets", response_model=list[GenerationPresetResponse]
)
def list_presets(
    project_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session),
):
    platform_projects.get_project_access(db, user, project_id)
    return list(
        db.scalars(
            select(GenerationPreset)
            .where(GenerationPreset.project_id == project_id)
            .order_by(GenerationPreset.is_default.desc(), GenerationPreset.name)
        )
    )


@router.post(
    "/projects/{project_id}/presets",
    response_model=GenerationPresetResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_preset(
    project_id: str,
    body: GenerationPresetCreateRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session),
):
    project = platform_projects.get_project_access(db, user, project_id, write=True)
    platform_projects.get_profile_for_project(db, project.id, body.creative_profile_id)
    preset = GenerationPreset(project_id=project.id, **body.model_dump())
    db.add(preset)
    db.flush()
    if preset.is_default:
        platform_projects.set_default_preset(db, project.id, preset.id)
    platform_auth.audit(
        db, "preset.created", "preset", preset.id, user.id, project.workspace_id
    )
    db.commit()
    db.refresh(preset)
    return preset


@router.patch(
    "/projects/{project_id}/presets/{preset_id}",
    response_model=GenerationPresetResponse,
)
def update_preset(
    project_id: str,
    preset_id: str,
    body: GenerationPresetUpdateRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session),
):
    project = platform_projects.get_project_access(db, user, project_id, write=True)
    preset = db.get(GenerationPreset, preset_id)
    if preset is None or preset.project_id != project.id:
        raise HTTPException(status_code=404, detail="preset not found")
    changes = body.model_dump(exclude_unset=True)
    if "creative_profile_id" in changes:
        platform_projects.get_profile_for_project(
            db, project.id, changes["creative_profile_id"]
        )
    for field, value in changes.items():
        setattr(preset, field, value)
    if preset.is_default:
        platform_projects.set_default_preset(db, project.id, preset.id)
    platform_auth.audit(
        db, "preset.updated", "preset", preset.id, user.id, project.workspace_id
    )
    db.commit()
    db.refresh(preset)
    return preset


@router.delete(
    "/projects/{project_id}/presets/{preset_id}", status_code=status.HTTP_204_NO_CONTENT
)
def delete_preset(
    project_id: str,
    preset_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session),
):
    project = platform_projects.get_project_access(db, user, project_id, write=True)
    preset = db.get(GenerationPreset, preset_id)
    if preset is None or preset.project_id != project.id:
        raise HTTPException(status_code=404, detail="preset not found")
    db.delete(preset)
    platform_auth.audit(
        db, "preset.deleted", "preset", preset_id, user.id, project.workspace_id
    )
    db.commit()
