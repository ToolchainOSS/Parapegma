from __future__ import annotations

import asyncio

import pytest

from app.schemas.bandit import ArmConfig
from app.services import prefetch


@pytest.mark.asyncio
async def test_prefetch_pipeline_runs_arms_concurrently(monkeypatch):
    async def fake_condense_query(history: str, current_msg: str) -> str:
        return "condensed query"

    async def fake_fetch_rag(query: str) -> str:
        await asyncio.sleep(0.05)
        return "RAG MARKDOWN"

    async def fake_fetch_web(history_messages: list) -> str:
        await asyncio.sleep(0.05)
        return "WEB MARKDOWN"

    monkeypatch.setattr(prefetch, "_condense_query", fake_condense_query)
    monkeypatch.setattr(prefetch, "_fetch_rag", fake_fetch_rag)
    monkeypatch.setattr(prefetch, "_fetch_web", fake_fetch_web)

    arm = ArmConfig(arm_id="ab", use_memory=True, use_rag=True, use_web=True)
    start = asyncio.get_running_loop().time()
    result = await prefetch.execute_prefetch_pipeline(
        arm=arm,
        history_messages=[{"role": "user", "content": "hello"}],
        current_msg="hello",
    )
    elapsed = asyncio.get_running_loop().time() - start

    assert result["rag_context"] == "RAG MARKDOWN"
    assert result["web_context"] == "WEB MARKDOWN"
    assert elapsed < 0.09


@pytest.mark.asyncio
async def test_prefetch_pipeline_strict_arm_gating(monkeypatch):
    calls = {"condense": 0, "rag": 0, "web": 0}

    async def fake_condense_query(history: str, current_msg: str) -> str:
        calls["condense"] += 1
        return "q"

    async def fake_fetch_rag(query: str) -> str:
        calls["rag"] += 1
        return "RAG"

    async def fake_fetch_web(history_messages: list) -> str:
        calls["web"] += 1
        return "WEB"

    monkeypatch.setattr(prefetch, "_condense_query", fake_condense_query)
    monkeypatch.setattr(prefetch, "_fetch_rag", fake_fetch_rag)
    monkeypatch.setattr(prefetch, "_fetch_web", fake_fetch_web)

    arm = ArmConfig(arm_id="off", use_memory=True, use_rag=False, use_web=False)
    result = await prefetch.execute_prefetch_pipeline(
        arm=arm,
        history_messages=[],
        current_msg="hello",
    )

    assert result == {"rag_context": "", "web_context": ""}
    assert calls == {"condense": 0, "rag": 0, "web": 0}

    arm_web_only = ArmConfig(arm_id="web-only", use_memory=True, use_rag=False, use_web=True)
    result_web_only = await prefetch.execute_prefetch_pipeline(
        arm=arm_web_only,
        history_messages=[{"role": "user", "content": "raw history"}],
        current_msg="hello",
    )
    assert result_web_only["rag_context"] == ""
    assert result_web_only["web_context"] == "WEB"
    assert calls["condense"] == 0
    assert calls["rag"] == 0
    assert calls["web"] == 1


@pytest.mark.asyncio
async def test_prefetch_pipeline_timeout_and_error_fail_silent(monkeypatch):
    async def timeout_web(history_messages: list) -> str:
        await asyncio.sleep(2)
        return "never"

    async def fail_condense(history: str, current_msg: str) -> str:
        raise RuntimeError("boom")

    monkeypatch.setattr(prefetch, "_fetch_web", timeout_web)
    monkeypatch.setattr(prefetch, "_condense_query", fail_condense)

    arm = ArmConfig(arm_id="on", use_memory=True, use_rag=True, use_web=True)
    result = await prefetch.execute_prefetch_pipeline(
        arm=arm,
        history_messages=[{"role": "user", "content": "x"}],
        current_msg="x",
    )

    assert result == {"rag_context": "", "web_context": ""}
