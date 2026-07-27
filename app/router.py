"""Application configuration - root APIRouter.

Defines all FastAPI application endpoints.

Resources:
    1. https://fastapi.tiangolo.com/tutorial/bigger-applications

"""

from fastapi import APIRouter

from app.controllers.v1 import llm, video
from app.controllers.v2 import (
    admin,
    api_keys,
    assets,
    auth,
    automation,
    creative,
    editorial_formats,
    projects,
)

root_api_router = APIRouter()
# v1
root_api_router.include_router(video.router)
root_api_router.include_router(llm.router)
# v2 platform
root_api_router.include_router(auth.router)
root_api_router.include_router(admin.router)
root_api_router.include_router(projects.router)
root_api_router.include_router(editorial_formats.router)
root_api_router.include_router(creative.router)
root_api_router.include_router(api_keys.router)
root_api_router.include_router(automation.router)
root_api_router.include_router(assets.router)
