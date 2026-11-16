from fastapi import APIRouter

from app.api import gitlab, health, telegram

api_router = APIRouter()
api_router.include_router(gitlab.router)
api_router.include_router(telegram.router)
api_router.include_router(health.router)
