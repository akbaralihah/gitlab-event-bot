import logging

from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import GitlabUser, TelegramAdmin, TelegramGroup
from app.services.cache import Cache
from app.telegram.client import TelegramClient
from app.telegram.schemas import Message, Update

log = logging.getLogger(__name__)

GROUP_COMMANDS = {"register", "start", "stop"}


def parse_command(text: str | None, bot_username: str = "") -> str | None:
    """'/start@my_bot arg' -> 'start'. None when it is not a command or is addressed to another bot."""
    if not text or not text.startswith("/"):
        return None
    name, _, mention = text.split(maxsplit=1)[0][1:].partition("@")
    if mention and bot_username and mention.lower() != bot_username.lower().lstrip("@"):
        return None
    return name.lower()


async def handle_update(
    update: Update,
    *,
    session: AsyncSession,
    tg: TelegramClient,
    cache: Cache,
    bot_username: str = "",
) -> None:
    message = update.message
    if message is None or message.from_user is None:
        return

    command = parse_command(message.text, bot_username)
    if message.chat.type == "private":
        await _handle_private(message, command, session, tg, cache)
    elif message.chat.type in ("group", "supergroup") and command in GROUP_COMMANDS:
        is_admin = await session.scalar(select(exists().where(TelegramAdmin.telegram_id == message.from_user.id)))
        if is_admin:
            await _GROUP_HANDLERS[command](message, session, tg)


async def _reply(tg: TelegramClient, message: Message, text: str) -> None:
    await tg.send_message(message.chat.id, text, message_thread_id=message.topic_id)


# ---------- private chat: a developer links his GitLab ID ----------


async def _handle_private(
    message: Message, command: str | None, session: AsyncSession, tg: TelegramClient, cache: Cache
) -> None:
    user_id = message.from_user.id

    if command == "start":
        registered = await session.scalar(select(GitlabUser).where(GitlabUser.telegram_id == user_id))
        if registered:
            await cache.clear_registration(user_id)
            await _reply(tg, message, "ℹ️ Siz allaqachon ro'yxatdan o'tgansiz.")
        else:
            await cache.start_registration(user_id)
            await _reply(tg, message, "🔑 Iltimos, GitLab ID'ingizni yuboring.")
        return

    if command is None and message.text and await cache.is_registering(user_id):
        text = message.text.strip()
        if not text.isdigit():
            await _reply(tg, message, "❗️ GitLab ID faqat raqamlardan iborat bo'lishi kerak.")
            return
        if await session.scalar(select(GitlabUser).where(GitlabUser.gitlab_id == int(text))):
            await _reply(tg, message, "❗️ Bu GitLab ID allaqachon ishlatilgan.")
        else:
            session.add(GitlabUser(gitlab_id=int(text), telegram_id=user_id))
            await session.commit()
            await _reply(tg, message, "✅ Ro'yxatdan muvaffaqiyatli o'tdingiz!")
        await cache.clear_registration(user_id)


# ---------- group chat: admins manage where notifications go ----------


async def _get_group(session: AsyncSession, chat_id: int) -> TelegramGroup | None:
    return await session.scalar(select(TelegramGroup).where(TelegramGroup.chat_id == chat_id))


async def _group_register(message: Message, session: AsyncSession, tg: TelegramClient) -> None:
    chat = message.chat
    topic = message.reply_to_message.forum_topic_created if message.reply_to_message else None

    group = await _get_group(session, chat.id)
    if group is None:
        group = TelegramGroup(chat_id=chat.id)
        session.add(group)
    group.chat_name = chat.title or str(chat.id)
    group.chat_type = chat.type
    group.username = chat.username
    group.is_forum = chat.is_forum
    group.message_thread_id = message.topic_id
    group.message_thread_name = topic.name if topic and message.topic_id else None
    await session.commit()

    await _reply(tg, message, "✅ Guruh muvaffaqiyatli ro'yxatdan o'tkazildi.")


async def _group_start(message: Message, session: AsyncSession, tg: TelegramClient) -> None:
    group = await _get_group(session, message.chat.id)
    if group is None:
        await _reply(tg, message, "❗️ Avval /register buyrug'ini yuboring.")
    elif group.is_active:
        await _reply(tg, message, "🤖 Bot allaqachon ishga tushgan.")
    else:
        group.is_active = True
        await session.commit()
        await _reply(tg, message, "🤖 Bot ishga tushdi.")


async def _group_stop(message: Message, session: AsyncSession, tg: TelegramClient) -> None:
    group = await _get_group(session, message.chat.id)
    if group is None:
        await _reply(tg, message, "❗️ Avval /register buyrug'ini yuboring.")
    elif not group.is_active:
        await _reply(tg, message, "🛑 Bot allaqachon to'xtatilgan.")
    else:
        group.is_active = False
        await session.commit()
        await _reply(tg, message, "🛑 Bot to'xtatildi.")


_GROUP_HANDLERS = {"register": _group_register, "start": _group_start, "stop": _group_stop}
