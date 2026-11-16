import logging
from hmac import compare_digest
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.db.session import get_session
from app.deps import get_bot_username, get_cache, get_telegram
from app.schemas.common import ErrorResponse, StatusResponse
from app.services.cache import Cache
from app.telegram.client import TelegramClient
from app.telegram.handlers import handle_update
from app.telegram.schemas import Update

log = logging.getLogger(__name__)

router = APIRouter(tags=["Telegram"])

REQUEST_BODY_EXAMPLE = {
    "requestBody": {
        "required": True,
        "content": {
            "application/json": {
                "schema": {"type": "object", "title": "Update от Telegram"},
                "example": {
                    "update_id": 1,
                    "message": {
                        "message_id": 10,
                        "from": {"id": 123456789},
                        "chat": {"id": 123456789, "type": "private"},
                        "text": "/start",
                    },
                },
            }
        },
    }
}


@router.post(
    "/telegram/webhook",
    summary="Вебхук Telegram",
    description=(
        "Принимает обновления (`Update`) от Telegram. Адрес регистрируется у Telegram автоматически "
        "при запуске приложения (`PROJECT_URL/api/telegram/webhook`), вручную вызывать его не нужно.\n\n"
        "Обрабатываются команды:\n"
        "- в личном чате: `/start` — привязка GitLab ID к Telegram-аккаунту;\n"
        "- в группе (только для администраторов бота): `/register`, `/start`, `/stop`.\n\n"
        "Если задан `WEBHOOK_SECRET`, заголовок `X-Telegram-Bot-Api-Secret-Token` должен совпадать с ним.\n\n"
        "Ответ всегда `200`, даже если обработчик упал (ошибка пишется в лог): "
        "иначе Telegram будет бесконечно присылать это же обновление повторно."
    ),
    response_model=StatusResponse,
    responses={
        400: {"model": ErrorResponse, "description": "Тело запроса не является корректным обновлением Telegram"},
        401: {"model": ErrorResponse, "description": "Неверный секретный токен"},
    },
    openapi_extra=REQUEST_BODY_EXAMPLE,
)
async def telegram_webhook(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
    tg: Annotated[TelegramClient, Depends(get_telegram)],
    cache: Annotated[Cache, Depends(get_cache)],
    settings: Annotated[Settings, Depends(get_settings)],
    bot_username: Annotated[str, Depends(get_bot_username)],
    x_telegram_bot_api_secret_token: Annotated[
        str | None,
        Header(description="Секретный токен, переданный Telegram при `setWebhook`; проверяется, если задан `WEBHOOK_SECRET`"),
    ] = None,
) -> dict:
    secret = settings.webhook_secret
    if secret and not compare_digest((x_telegram_bot_api_secret_token or "").encode(), secret.encode()):
        raise HTTPException(status_code=401, detail="Неверный секретный токен")

    try:
        update = Update.model_validate(await request.json())
    except (ValueError, ValidationError):
        raise HTTPException(status_code=400, detail="Некорректное обновление Telegram")

    # Telegram re-sends an update until it gets a 2xx, so a handler failure is logged, not returned.
    try:
        await handle_update(update, session=session, tg=tg, cache=cache, bot_username=bot_username)
    except Exception:
        log.exception("failed to handle telegram update %s", update.update_id)
    return {"status": "ok"}
