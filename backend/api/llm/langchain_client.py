from __future__ import annotations

import os

from langchain.chat_models import init_chat_model
from langchain_core.messages import HumanMessage, SystemMessage


class LangChainClient:
    """LangChain-backed LLM client.

    Uses `init_chat_model` so the concrete provider (anthropic, openai, ...) is
    decided by env vars at construction time. No provider-specific code lives
    here — swap providers by installing the corresponding `langchain-*`
    integration and setting `LLM_PROVIDER`.
    """

    def __init__(
        self,
        *,
        model: str | None = None,
        provider: str | None = None,
        max_tokens: int = 8192,
        temperature: float = 0.0,
    ) -> None:
        model = model or os.environ.get("LLM_MODEL", "claude-opus-4-7")
        provider = provider or os.environ.get("LLM_PROVIDER", "anthropic")
        self._require_key_for(provider)
        self._llm = init_chat_model(
            model,
            model_provider=provider,
            max_tokens=max_tokens,
            temperature=temperature,
        )

    @staticmethod
    def _require_key_for(provider: str) -> None:
        key_env = {
            "anthropic": "ANTHROPIC_API_KEY",
            "openai": "OPENAI_API_KEY",
            "google_genai": "GOOGLE_API_KEY",
        }.get(provider)
        if key_env and not os.environ.get(key_env):
            raise RuntimeError(
                f"{key_env} is not set. Copy backend/.env.example to backend/.env "
                f"and fill it in (or export it in your shell)."
            )

    def generate(self, system: str, user: str) -> str:
        msg = self._llm.invoke(
            [SystemMessage(content=system), HumanMessage(content=user)]
        )
        content = msg.content
        if isinstance(content, str):
            return content
        # Some providers return a list of content blocks
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict):
                text = block.get("text")
                if text:
                    parts.append(text)
        return "".join(parts)
