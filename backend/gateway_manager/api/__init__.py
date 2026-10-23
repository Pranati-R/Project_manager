from fastapi import APIRouter

from . import auth, config, logs, projects, settings, status

router = APIRouter()
for module in (auth, projects, config, status, logs, settings):
    router.include_router(module.router)
