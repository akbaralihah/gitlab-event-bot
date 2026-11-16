"""Verification of GitLab webhook signatures (Standard Webhooks scheme).

GitLab signs every delivery with the "signing token" it generated for the webhook (`whsec_<base64>`):
    webhook-signature = "v1," + base64(HMAC_SHA256(key, f"{webhook-id}.{webhook-timestamp}.{body}"))
The header may hold several space-separated signatures.
"""
import base64
import binascii
import hashlib
import hmac
import time

TOLERANCE_SECONDS = 5 * 60
PREFIX = "whsec_"


def _key(token: str) -> bytes:
    token = token.strip().removeprefix(PREFIX)
    try:
        return base64.b64decode(token, validate=True)
    except (binascii.Error, ValueError):
        return token.encode()


def sign(token: str, msg_id: str, timestamp: str, body: bytes) -> str:
    digest = hmac.new(_key(token), f"{msg_id}.{timestamp}.".encode() + body, hashlib.sha256).digest()
    return "v1," + base64.b64encode(digest).decode()


def verify(
    tokens: list[str],
    msg_id: str | None,
    timestamp: str | None,
    signature: str | None,
    body: bytes,
    now: float | None = None,
) -> bool:
    """True if the signature matches at least one of the tokens and the timestamp is fresh."""
    if not (msg_id and timestamp and signature):
        return False
    try:
        if abs((now if now is not None else time.time()) - int(timestamp)) > TOLERANCE_SECONDS:
            return False
    except ValueError:
        return False
    received = signature.split()
    return any(
        hmac.compare_digest(sign(token, msg_id, timestamp, body).encode(), candidate.encode())
        for token in tokens
        for candidate in received
    )
