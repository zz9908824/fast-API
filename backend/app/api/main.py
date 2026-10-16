from fastapi import APIRouter

from app.api.routes import items, login, matter_imports, precheck, private, users, utils
from app.core.config import settings

api_router = APIRouter()
api_router.include_router(login.router)
api_router.include_router(users.router)
api_router.include_router(utils.router)
api_router.include_router(items.router)
api_router.include_router(precheck.router)
api_router.include_router(matter_imports.router)


if settings.FASTAPI_ENV == "development":
    api_router.include_router(private.router)
