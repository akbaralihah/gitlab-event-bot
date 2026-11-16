import logging

from app.services.cache import Cache
from app.telegram.client import TelegramAPIError, TelegramClient

log = logging.getLogger(__name__)


async def send_or_edit(
    tg: TelegramClient,
    cache: Cache,
    *,
    chat_id: int,
    thread_id: int | None,
    text: str,
    key: str | None = None,
    final: bool = False,
) -> None:
    """Send `text`; if `key` already has a message, edit it instead.
    `final` forgets the message after this update."""
    if key is None:
        await tg.send_message(chat_id, text, message_thread_id=thread_id)
        return

    async with cache.lock(key):
        message_id = await cache.get_message_id(key)

        if message_id:
            try:
                await tg.edit_message_text(chat_id, message_id, text)
            except TelegramAPIError as e:
                if "message is not modified" not in e.description:
                    log.warning("cannot edit message %s (%s), sending a new one", message_id, e.description)
                    message_id = None
        if not message_id:
            message_id = await tg.send_message(chat_id, text, message_thread_id=thread_id)

        if final:
            await cache.delete_message_id(key)
        else:
            await cache.set_message_id(key, message_id)
