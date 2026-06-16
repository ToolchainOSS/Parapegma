"""Centralized, type-safe construction of chat LLM clients.

All ``ChatOpenAI`` instantiation flows through :func:`make_chat_llm` so the
OpenAI-specific quirks (``SecretStr`` API keys, the ``max_completion_tokens``
field alias) live in exactly one place instead of being repeated at every
call site.
"""

from __future__ import annotations

from langchain_core.callbacks import BaseCallbackHandler
from langchain_openai import ChatOpenAI
from pydantic import SecretStr

__all__ = ["make_chat_llm"]


def make_chat_llm(
    *,
    model: str,
    api_key: str,
    temperature: float | None = None,
    max_tokens: int | None = None,
    callbacks: list[BaseCallbackHandler] | None = None,
) -> ChatOpenAI:
    """Build a :class:`ChatOpenAI` client with type-correct arguments.

    ``api_key`` is accepted as a plain ``str`` and wrapped in ``SecretStr`` so
    callers never handle the secret type directly. ``max_tokens`` is forwarded
    via the ``max_completion_tokens`` field alias expected by current
    ``langchain-openai`` releases.
    """
    return ChatOpenAI(
        model=model,
        api_key=SecretStr(api_key),
        temperature=temperature,
        max_completion_tokens=max_tokens,
        callbacks=callbacks,
    )
