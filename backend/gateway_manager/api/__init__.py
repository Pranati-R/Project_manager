from fastapi import APIRouter

from . import auth, config, docs, logs, projects, settings, status

router = APIRouter()
for module in (auth, projects, config, status, logs, settings, docs):
    router.include_router(module.router)
