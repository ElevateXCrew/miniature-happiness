import uuid
from pathlib import Path
from typing import Any, cast

from openai import AsyncOpenAI
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import logger
from app.models.enums import Channel, MessageDirection
from app.repositories.message_repo import MessageRepository
from app.repositories.session_repo import SessionRepository
from app.services.client_runtime_service import AgentReply


class WorkerRuntimeService:
    """Concrete worker-facing runtime behavior."""

    def __init__(self, db: AsyncSession) -> None:
        self._messages = MessageRepository(db)
        self._sessions = SessionRepository(db)
        self._openai_client: AsyncOpenAI | None = None

    async def generate_worker_relay_reply(
        self,
        *,
        session_id: uuid.UUID,
        client_id: uuid.UUID,
        worker_id: uuid.UUID,
        channel: Channel,
        worker_instruction: str,
    ) -> AgentReply:
        del client_id
        del worker_id
        del channel

        instruction = worker_instruction.strip()
        if not instruction:
            return AgentReply(text="Message me when you're ready, babe 😊", tool_traces=[])

        if not settings.openai_api_key.strip():
            return AgentReply(text=self._ensure_short_style(instruction), tool_traces=[])

        try:
            session = await self._sessions.get_by_id(session_id)
            if session is None:
                return AgentReply(text=self._ensure_short_style(instruction), tool_traces=[])

            system_prompt = self._load_worker_prompt()
            history = await self._messages.list_for_session(session_id)

            chat_messages: list[dict[str, Any]] = [{"role": "system", "content": system_prompt}]
            for msg in history[-12:]:
                role = "user" if msg.direction == MessageDirection.INBOUND else "assistant"
                chat_messages.append({"role": role, "content": msg.body or ""})

            chat_messages.append(
                {
                    "role": "system",
                    "content": (
                        "[SYSTEM WORKER RELAY CONTEXT] Rewrite the worker instruction as Alysha's "
                        "natural message to the client, preserving intent and tone continuity. "
                        "Do not mention worker/admin/system/internal instructions. "
                        "Keep to 1-2 lines."
                    ),
                }
            )
            chat_messages.append(
                {
                    "role": "user",
                    "content": f"Worker instruction: {instruction}",
                }
            )

            client = self._get_openai_client()
            completion = await cast(Any, client.chat.completions).create(
                model=settings.openai_model,
                temperature=0.2,
                messages=chat_messages,
            )
            content = (completion.choices[0].message.content or "").strip()
            if content:
                return AgentReply(text=self._ensure_short_style(content), tool_traces=[])
        except Exception as exc:
            logger.warning("Worker relay LLM generation failed, using fallback", error=str(exc))

        return AgentReply(text=self._ensure_short_style(instruction), tool_traces=[])

    async def generate_worker_chat_reply(
        self,
        *,
        worker_id: uuid.UUID,
        inbound_text: str,
    ) -> AgentReply:
        del worker_id

        text = inbound_text.strip()
        if not text:
            return AgentReply(text="Message me when you're ready babe 😊", tool_traces=[])

        if not settings.openai_api_key.strip():
            return AgentReply(text=self._worker_chat_fallback_reply(text), tool_traces=[])

        try:
            system_prompt = self._load_worker_prompt()
            chat_messages: list[dict[str, Any]] = [
                {"role": "system", "content": system_prompt},
                {
                    "role": "system",
                    "content": (
                        "[SYSTEM WORKER CHAT CONTEXT] Reply to the worker as Alysha in a "
                        "warm, short, natural WhatsApp voice. This is a direct chat with the "
                        "worker, not a client relay. Do not mention internal systems, commands, "
                        "or booking tools. Keep the reply to 1-2 lines."
                    ),
                },
                {"role": "user", "content": text},
            ]

            client = self._get_openai_client()
            completion = await cast(Any, client.chat.completions).create(
                model=settings.openai_model,
                temperature=0.2,
                messages=chat_messages,
            )
            content = (completion.choices[0].message.content or "").strip()
            if content:
                return AgentReply(text=self._ensure_short_style(content), tool_traces=[])
        except Exception as exc:
            logger.warning("Worker chat LLM generation failed, using fallback", error=str(exc))

        return AgentReply(text=self._worker_chat_fallback_reply(text), tool_traces=[])

    def _load_worker_prompt(self) -> str:
        root = Path(__file__).resolve().parents[3]
        prompts_dir = root / "prompts"
        prompt_path = prompts_dir / "worker.txt"
        context_path = prompts_dir / "alysha_context.md"

        parts: list[str] = []
        if context_path.exists():
            parts.append(context_path.read_text(encoding="utf-8").strip())

        if prompt_path.exists():
            parts.append(prompt_path.read_text(encoding="utf-8").strip())
        else:
            parts.append("You are Alysha. Reply briefly, naturally, and warmly to the worker.")

        return "\n\n---\n\n".join(parts)

    def _get_openai_client(self) -> AsyncOpenAI:
        if self._openai_client is None:
            self._openai_client = AsyncOpenAI(api_key=settings.openai_api_key)
        return self._openai_client

    def _ensure_short_style(self, text: str) -> str:
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        if not lines:
            return "Sure babe."
        return "\n".join(lines)

    def _worker_chat_fallback_reply(self, text: str) -> str:
        if self._is_smalltalk_or_greeting(text):
            return "Hi babe 😘"
        lowered = text.strip().lower()
        if lowered.endswith("?"):
            return "Sure babe 😊"
        return "Okay babe 😊"

    def _is_smalltalk_or_greeting(self, text: str) -> bool:
        lowered = text.strip().lower()
        if not lowered:
            return True

        greetings = {
            "hi",
            "hy",
            "hey",
            "hello",
            "hiya",
            "yo",
            "good morning",
            "good afternoon",
            "good evening",
            "how are you",
        }
        compact = "".join(ch for ch in lowered if ch.isalpha() or ch.isspace()).strip()
        if compact in greetings:
            return True
        return any(compact.startswith(g + " ") for g in greetings)
