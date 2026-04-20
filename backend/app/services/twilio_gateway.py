import asyncio
import re
from dataclasses import dataclass
from functools import partial
from typing import Any

import httpx
from fastapi import Request
from twilio.base.exceptions import TwilioException
from twilio.request_validator import RequestValidator
from twilio.rest import Client as TwilioRestClient
from twilio.twiml.messaging_response import MessagingResponse

from app.core.config import settings


@dataclass
class OutboundSendResult:
    ok: bool
    sid: str | None
    error: str | None = None
    stub: bool = False


class TwilioGateway:
    def normalize_e164(self, phone: str) -> str:
        value = phone.strip()
        if value.lower().startswith("whatsapp:"):
            value = value.split(":", 1)[1]
        value = value.replace(" ", "")
        if not value.startswith("+"):
            value = f"+{value}"
        if not re.fullmatch(r"\+[1-9]\d{7,14}", value):
            raise ValueError("Phone must be valid E.164 format.")
        return value

    def to_twiml(self, text: str | None = None) -> str:
        response = MessagingResponse()
        if text:
            response.message(text)
        return str(response)

    async def validate_signature(self, request: Request, form_data: dict[str, Any]) -> bool:
        if not settings.twilio_validate_signature:
            return True
        token = settings.twilio_auth_token.strip()
        if not token:
            return False
        signature = request.headers.get("X-Twilio-Signature", "")
        validator = RequestValidator(token)
        return bool(validator.validate(str(request.url), form_data, signature))

    async def send_client_message(
        self,
        *,
        to_phone_e164: str,
        channel: str,
        text: str,
    ) -> OutboundSendResult:
        account_sid = settings.twilio_account_sid.strip()
        auth_token = settings.twilio_auth_token.strip()
        if not account_sid or not auth_token:
            return OutboundSendResult(ok=True, sid=None, stub=True)

        from_num = settings.twilio_sms_number.strip()
        to_num = to_phone_e164
        if channel == "whatsapp":
            from_num = settings.twilio_whatsapp_number.strip() or from_num
            to_num = f"whatsapp:{to_phone_e164}"
            if not from_num.startswith("whatsapp:"):
                from_num = f"whatsapp:{from_num}"

        if not from_num:
            return OutboundSendResult(
                ok=False,
                sid=None,
                error="Twilio sender number is not configured",
            )

        try:
            client = TwilioRestClient(account_sid, auth_token)
            # The Twilio REST SDK is synchronous. Run it in a thread-pool
            # executor so it never blocks the async event loop.
            loop = asyncio.get_event_loop()
            msg = await loop.run_in_executor(
                None,
                partial(client.messages.create, from_=from_num, to=to_num, body=text),
            )
            return OutboundSendResult(ok=True, sid=msg.sid)
        except TwilioException as exc:
            return OutboundSendResult(ok=False, sid=None, error=str(exc))

    async def fetch_media_binary(self, source_url: str) -> tuple[bytes, str | None]:
        account_sid = settings.twilio_account_sid.strip()
        auth_token = settings.twilio_auth_token.strip()
        auth: tuple[str, str] | None = None
        if account_sid and auth_token:
            auth = (account_sid, auth_token)

        timeout = httpx.Timeout(settings.media_fetch_timeout_seconds)
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True, auth=auth) as client:
            resp = await client.get(source_url)
            resp.raise_for_status()
            content_type = resp.headers.get("content-type")
            return resp.content, content_type
