from fastapi import Request

from app.services.cache import Cache
from app.telegram.client import TelegramClient


def get_telegram(request: Request) -> TelegramClient:
    return request.app.state.telegram


def get_bot_username(request: Request) -> str:
    return getattr(request.app.state, "bot_username", "")


def get_cache(request: Request) -> Cache:
    return request.app.state.cache
