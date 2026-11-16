import logging

import httpx

# httpx logs full request URLs at INFO level, and the Telegram URL contains the bot token
logging.getLogger("httpx").setLevel(logging.WARNING)


class TelegramAPIError(Exception):
    def __init__(self, description: str, error_code: int | None = None):
        super().__init__(description)
        self.description = description
        self.error_code = error_code


class TelegramClient:
    """Minimal Telegram Bot API client (only the methods this app needs)."""

    def __init__(self, token: str, *, timeout: float = 10.0):
        self._http = httpx.AsyncClient(base_url=f"https://api.telegram.org/bot{token}/", timeout=timeout)

    async def _call(self, method: str, **params) -> dict | bool:
        response = await self._http.post(method, json={k: v for k, v in params.items() if v is not None})
        try:
            body = response.json()
        except ValueError:
            raise TelegramAPIError(f"{method}: HTTP {response.status_code}", response.status_code) from None
        if not body.get("ok"):
            raise TelegramAPIError(body.get("description", "unknown error"), body.get("error_code"))
        return body["result"]

    async def get_me(self) -> dict:
        return await self._call("getMe")

    async def send_message(self, chat_id: int, text: str, message_thread_id: int | None = None) -> int:
        """Sends an HTML message and returns its message_id."""
        result = await self._call(
            "sendMessage",
            chat_id=chat_id,
            text=text,
            message_thread_id=message_thread_id,
            parse_mode="HTML",
            link_preview_options={"is_disabled": True},
        )
        return result["message_id"]

    async def edit_message_text(self, chat_id: int, message_id: int, text: str) -> None:
        await self._call(
            "editMessageText",
            chat_id=chat_id,
            message_id=message_id,
            text=text,
            parse_mode="HTML",
            link_preview_options={"is_disabled": True},
        )

    async def set_webhook(self, url: str, secret_token: str | None = None) -> None:
        await self._call("setWebhook", url=url, secret_token=secret_token, allowed_updates=["message"])

    async def close(self) -> None:
        await self._http.aclose()
