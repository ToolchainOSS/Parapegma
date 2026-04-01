"""Synchronous pre-inference context prefetch pipeline."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_groq import ChatGroq
from langchain_openai import OpenAIEmbeddings
from langchain_pinecone import PineconeVectorStore
from openai import AsyncOpenAI

from app import config
from app.schemas.bandit import ArmConfig

logger = logging.getLogger(__name__)

_GROQ_TIMEOUT_SECONDS = 0.8
_RAG_TIMEOUT_SECONDS = 0.8
_WEB_TIMEOUT_SECONDS = 0.8
_DEFAULT_TOP_K = 4
_RAG_CONDENSATION_MODEL = "llama-3.1-8b-instant"
_WEB_SEARCH_MODEL = "sonar-pro"


def _history_to_text(history_messages: list[Any]) -> str:
    lines: list[str] = []
    for msg in history_messages:
        role = getattr(msg, "role", "user")
        content = getattr(msg, "content", "")
        if content:
            lines.append(f"{role}: {content}")
    return "\n".join(lines)


def _normalize_text_content(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


async def _condense_query(history: str, current_msg: str) -> str:
    """Condense multi-turn chat history into one retrieval query using Groq."""
    api_key = config.get_groq_api_key()
    if not api_key:
        return ""
    try:
        llm = ChatGroq(
            model=_RAG_CONDENSATION_MODEL,
            api_key=api_key,
            temperature=0,
            timeout=_GROQ_TIMEOUT_SECONDS,
            max_tokens=96,
        )
        response = await llm.ainvoke(
            [
                SystemMessage(
                    content=(
                        "Condense the conversation into a single short search query for "
                        "semantic retrieval. Return only plain text."
                    )
                ),
                HumanMessage(
                    content=(
                        f"Conversation history:\n{history}\n\n"
                        f"Latest user message:\n{current_msg}"
                    )
                ),
            ]
        )
        content = getattr(response, "content", "")
        return _normalize_text_content(content)
    except Exception:
        logger.exception("Groq condensation failed")
        return ""


async def _fetch_rag(query: str) -> str:
    """Query Pinecone with OpenAI embeddings and return markdown context."""
    if not query.strip():
        return ""

    pinecone_api_key = config.get_pinecone_api_key()
    pinecone_index_name = config.get_pinecone_index_name()
    openai_api_key = config.get_openai_api_key()
    if not pinecone_api_key or not pinecone_index_name or not openai_api_key:
        return ""

    try:
        embeddings = OpenAIEmbeddings(api_key=openai_api_key)
        vectorstore = PineconeVectorStore(
            index_name=pinecone_index_name,
            pinecone_api_key=pinecone_api_key,
            embedding=embeddings,
        )
        docs = await vectorstore.asimilarity_search(query=query, k=_DEFAULT_TOP_K)
        if not docs:
            return ""

        lines = ["### Knowledge Base Results"]
        kept = 0
        for doc in docs:
            source = ""
            metadata = getattr(doc, "metadata", {}) or {}
            if isinstance(metadata, dict):
                source = metadata.get("source", "") or metadata.get("id", "")
            text = getattr(doc, "page_content", "").strip()
            if not text:
                continue
            kept += 1
            source_suffix = f" (source: {source})" if source else ""
            lines.append(f"{kept}. {text}{source_suffix}")
        return "\n".join(lines) if len(lines) > 1 else ""
    except Exception:
        logger.exception("RAG retrieval failed")
        return ""


async def _fetch_web(history_messages: list[Any]) -> str:
    """Query Perplexity using raw multi-turn history and return markdown context."""
    api_key = config.get_perplexity_api_key()
    if not api_key:
        return ""

    try:
        client = AsyncOpenAI(api_key=api_key, base_url="https://api.perplexity.ai")
        messages = []
        for msg in history_messages:
            role = getattr(msg, "role", "user")
            content = getattr(msg, "content", "")
            if not content:
                continue
            normalized_role = (
                role if role in {"system", "user", "assistant"} else "user"
            )
            messages.append({"role": normalized_role, "content": content})
        if not messages:
            return ""

        response = await client.chat.completions.create(
            model=_WEB_SEARCH_MODEL,
            messages=messages,
            temperature=0,
            max_tokens=600,
            timeout=_WEB_TIMEOUT_SECONDS,
        )
        choice = response.choices[0] if response.choices else None
        content = choice.message.content if choice and choice.message else ""
        content_text = _normalize_text_content(content)
        if not content_text:
            return ""
        return f"### Web Search Results\n{content_text}"
    except Exception:
        logger.exception("Web search fetch failed")
        return ""


async def execute_prefetch_pipeline(
    arm: ArmConfig,
    history_messages: list[Any],
    current_msg: str,
) -> dict[str, str]:
    """Run pre-inference context providers concurrently with strict arm gating."""

    async def _run_rag() -> str:
        if not arm.use_rag:
            return ""
        try:
            history = _history_to_text(history_messages)
            condensed = await asyncio.wait_for(
                _condense_query(history=history, current_msg=current_msg),
                timeout=_GROQ_TIMEOUT_SECONDS,
            )
            if not condensed:
                return ""
            return await asyncio.wait_for(
                _fetch_rag(query=condensed),
                timeout=_RAG_TIMEOUT_SECONDS,
            )
        except Exception:
            logger.exception("RAG prefetch arm failed")
            return ""

    async def _run_web() -> str:
        if not arm.use_web:
            return ""
        try:
            return await asyncio.wait_for(
                _fetch_web(history_messages=history_messages),
                timeout=_WEB_TIMEOUT_SECONDS,
            )
        except Exception:
            logger.exception("Web prefetch arm failed")
            return ""

    rag_context, web_context = await asyncio.gather(_run_rag(), _run_web())
    return {"rag_context": rag_context, "web_context": web_context}
