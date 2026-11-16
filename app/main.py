import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from redis.asyncio import Redis
from sqlalchemy import select

from app import __version__
from app.admin import setup_admin
from app.api import api_router
from app.config import Settings, get_settings
from app.db.session import engine, session_factory
from app.models import TelegramAdmin
from app.services.cache import Cache
from app.telegram.client import TelegramClient

log = logging.getLogger(__name__)


async def seed_admins(settings: Settings) -> None:
    """Make sure the ids from TELEGRAM_ADMIN_IDS are bot admins."""
    if not settings.admin_ids:
        return
    async with session_factory() as session:
        known = set(await session.scalars(select(TelegramAdmin.telegram_id)))
        for telegram_id in settings.admin_ids:
            if telegram_id not in known:
                session.add(TelegramAdmin(telegram_id=telegram_id, full_name=str(telegram_id)))
        await session.commit()


async def setup_telegram(app: FastAPI, tg: TelegramClient, settings: Settings) -> None:
    """Learn who the bot is and tell Telegram where to send updates.
    A failure here must not take the HTTP API down with it."""
    app.state.bot_username = ""
    try:
        me = await tg.get_me()
        app.state.bot_username = me.get("username", "")
        log.info("Telegram bot: @%s", app.state.bot_username)
    except Exception as e:
        log.error("getMe failed, check TELEGRAM_BOT_TOKEN and the network (the API keeps working): %s", e)
        return

    if not settings.project_url.startswith("https://"):
        log.warning("PROJECT_URL is not an https:// address: the Telegram webhook is NOT set, the bot gets no commands")
        return
    try:
        await tg.set_webhook(f"{settings.project_url}/api/telegram/webhook", settings.webhook_secret or None)
    except Exception as e:
        log.error("cannot set the Telegram webhook (the API keeps working): %s", e)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    tg = TelegramClient(settings.telegram_bot_token)
    app.state.telegram, app.state.cache = tg, Cache(redis)

    await seed_admins(settings)
    await setup_telegram(app, tg, settings)
    try:
        yield
    finally:
        await tg.close()
        await redis.aclose()
        await engine.dispose()


DESCRIPTION = """
Пересылает события GitLab (**push**, **merge request**, **pipeline**) в топик Telegram-супергруппы.

Merge request и pipeline — это **одно сообщение**, которое редактируется при смене статуса.

Админ-панель: [`/admin`](/admin) (включается, если задан `ADMIN_PASSWORD`).
"""

TAGS = [
    {"name": "GitLab", "description": "Приём событий из GitLab."},
    {"name": "Telegram", "description": "Приём обновлений от Telegram (команды бота)."},
    {"name": "Служебное", "description": "Проверка состояния сервиса."},
]


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="GitLab Event Bot",
        version=__version__,
        description=DESCRIPTION,
        openapi_tags=TAGS,
        lifespan=lifespan,
        swagger_ui_parameters={"defaultModelsExpandDepth": 0},
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/api/openapi.json",
    )
    app.include_router(api_router, prefix="/api")

    if settings.admin_password:
        setup_admin(app, engine, settings)
    else:
        log.warning("ADMIN_PASSWORD is empty, the /admin panel is disabled")
    return app


app = create_app()
