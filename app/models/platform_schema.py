from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=1024)


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=1024)
    new_password: str = Field(min_length=1, max_length=1024)


class UserCreateRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    display_name: str = Field(min_length=1, max_length=160)
    password: str = Field(min_length=1, max_length=1024)
    system_role: str = "user"

    @field_validator("system_role")
    @classmethod
    def validate_role(cls, value: str) -> str:
        if value not in {"admin", "user"}:
            raise ValueError("system_role must be admin or user")
        return value


class UserUpdateRequest(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=160)
    system_role: str | None = None
    status: str | None = None

    @field_validator("system_role")
    @classmethod
    def validate_role(cls, value: str | None) -> str | None:
        if value is not None and value not in {"admin", "user"}:
            raise ValueError("system_role must be admin or user")
        return value

    @field_validator("status")
    @classmethod
    def validate_status(cls, value: str | None) -> str | None:
        if value is not None and value not in {"active", "invited", "suspended"}:
            raise ValueError("invalid user status")
        return value


class PasswordResetRequest(BaseModel):
    new_password: str = Field(min_length=1, max_length=1024)


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    email: str
    display_name: str
    system_role: str
    status: str
    last_login_at: datetime | None
    created_at: datetime


class AuthResponse(BaseModel):
    user: UserResponse


class ProjectCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    niche: str = Field(default="", max_length=255)
    description: str = Field(default="", max_length=4000)
    primary_language: str = Field(default="pt-BR", max_length=32)
    target_audience: str = Field(default="", max_length=4000)
    workspace_id: str | None = None


class ProjectUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    niche: str | None = Field(default=None, max_length=255)
    description: str | None = Field(default=None, max_length=4000)
    primary_language: str | None = Field(default=None, max_length=32)
    target_audience: str | None = Field(default=None, max_length=4000)


class ProjectResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    workspace_id: str
    name: str
    slug: str
    niche: str
    description: str
    primary_language: str
    target_audience: str
    status: str
    created_at: datetime
    updated_at: datetime


class CreativeProfileCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    configuration: dict = Field(default_factory=dict)


class CreativeProfileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    version: int
    name: str
    is_active: bool
    configuration: dict
    created_by: str
    created_at: datetime


class GenerationPresetCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    creative_profile_id: str
    platform: str = Field(default="youtube_shorts", max_length=64)
    configuration: dict = Field(default_factory=dict)
    is_default: bool = False


class GenerationPresetUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    platform: str | None = Field(default=None, max_length=64)
    configuration: dict | None = None
    creative_profile_id: str | None = None
    is_default: bool | None = None


class GenerationPresetResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    creative_profile_id: str
    name: str
    platform: str
    configuration: dict
    is_default: bool
    created_at: datetime
    updated_at: datetime


class EditorialFormatCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    format_type: str = Field(default="ranking", max_length=64)
    configuration: dict = Field(default_factory=dict)
    is_default: bool = True


class EditorialFormatUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    configuration: dict | None = None
    is_default: bool | None = None


class EditorialFormatResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    name: str
    format_type: str
    configuration: dict
    is_default: bool
    created_at: datetime
    updated_at: datetime


class RankingItemRequest(BaseModel):
    position: int = Field(ge=1, le=20)
    title: str = Field(min_length=1, max_length=160)
    asset_id: str | None = None


class CreativeScriptRequest(BaseModel):
    video_subject: str = Field(min_length=3, max_length=500)
    narrative_structure: str = Field(default="auto", max_length=64)
    paragraph_number: int = Field(default=1, ge=1, le=10)


class CreativeScenePlanRequest(CreativeScriptRequest):
    video_script: str = Field(default="", max_length=8000)


class CreativeGenerationRequest(CreativeScriptRequest):
    preset_id: str | None = None
    editorial_format_id: str | None = None
    ranking_items: list[RankingItemRequest] = Field(default_factory=list, max_length=20)
    # Plan, source, download and rank the footage automatically from the subject
    # instead of expecting `ranking_items` with previously uploaded assets.
    auto_ranking: bool = False
    ranking_size: int | None = Field(default=None, ge=2, le=10)
    overrides: dict = Field(default_factory=dict)


class GenerationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    preset_id: str | None
    creative_profile_id: str | None
    creative_profile_version: int | None
    editorial_format_id: str | None
    editorial_format_snapshot: dict
    legacy_task_id: str | None
    status: str
    video_subject: str
    script: str
    scene_plan: dict
    error_stage: str | None
    error_message: str | None
    created_at: datetime


class ApiKeyCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    project_id: str | None = None
    scopes: list[str] = Field(default_factory=lambda: ["generations:create", "generations:read"])


class ApiKeyResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    workspace_id: str
    project_id: str | None
    name: str
    key_prefix: str
    scopes: list[str]
    last_used_at: datetime | None
    expires_at: datetime | None
    revoked_at: datetime | None
    created_at: datetime


class ApiKeyCreatedResponse(ApiKeyResponse):
    key: str


class AssetResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    generation_id: str | None
    kind: str
    original_filename: str
    mime_type: str
    size_bytes: int
    created_at: datetime
    download_url: str


class AdminOverviewResponse(BaseModel):
    users: int
    active_projects: int
    queued_generations: int
    processing_generations: int
    failed_generations: int
    completed_generations: int
    stored_asset_bytes: int
