"""Stateless Spark prototype routes.

These endpoints are intentionally isolated from existing Flow conversation
state and perform no database writes. They proxy validated requests to the
configured LLM and return structured Spark card payloads.

Remix model
-----------
The endpoint is stateless. The *client* owns the remix history:
- First generate: ``base_card=None``, ``adjustment_history=[]``
- Each subsequent adjust: ``base_card=<current card>``,
  ``adjustment_history=[oldest, ..., newest]`` (capped at 20 items).

The system prompt instructs the model to transform ``base_card`` in-place when
it is present, applying all accumulated adjustments cumulatively so the card
evolves rather than resetting.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, status
from h4ckath0n.auth import require_user
from h4ckath0n.auth.models import User
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field, ValidationError, field_validator

from app.config import get_llm_model, get_openai_api_key
from app.llm import make_chat_llm
from app.prompt_loader import prompt_version

logger = logging.getLogger(__name__)

router = APIRouter()

PROMPT_NAME = "spark_proxy_system"
_MAX_HISTORY = 20


class SparkCard(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    frame: Literal["calm", "zoomies", "silly", "challenge", "science"]
    action: str = Field(min_length=1, max_length=600)
    reward: str = Field(min_length=1, max_length=300)
    why: str = Field(min_length=1, max_length=400)
    fit_score: int | None = Field(default=None, ge=0, le=100)


class SparkGenerateRequest(BaseModel):
    condition: Literal["A", "B", "C", "D"]
    frame_preference: (
        Literal["calm", "zoomies", "silly", "challenge", "science"] | None
    ) = None
    context: str | None = Field(default=None, max_length=800)
    # Remix fields -------------------------------------------------------
    # base_card: the card currently displayed to the user; None on first generate.
    base_card: SparkCard | None = None
    # adjustment_history: ordered list of free-text adjustments from oldest to newest.
    # The model applies them cumulatively to base_card when present.
    adjustment_history: Annotated[list[str], Field(default_factory=list)]
    count: int = Field(default=3, ge=1, le=5)

    @field_validator("adjustment_history", mode="before")
    @classmethod
    def _cap_history(cls, v: object) -> object:
        if isinstance(v, list):
            return [str(item)[:400] for item in v[-_MAX_HISTORY:]]
        return v


class SparkGenerateResponse(BaseModel):
    condition: Literal["A", "B", "C", "D"]
    cards: list[SparkCard] = Field(min_length=1, max_length=5)
    model: str
    prompt_version: dict[str, str]


class _SparkModelPayload(BaseModel):
    cards: list[SparkCard] = Field(min_length=1, max_length=5)


def _content_to_text(content: object) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict):
                text_val = item.get("text")
                if isinstance(text_val, str):
                    parts.append(text_val)
        return "\n".join(parts)
    return str(content)


def _extract_json_object(text: str) -> dict[str, object]:
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    candidate = fenced.group(1) if fenced else text

    try:
        loaded = json.loads(candidate)
    except json.JSONDecodeError:
        start = candidate.find("{")
        end = candidate.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise
        loaded = json.loads(candidate[start : end + 1])

    if not isinstance(loaded, dict):
        raise ValueError("Spark model output must be a JSON object")
    return loaded


def _build_user_prompt(body: SparkGenerateRequest) -> str:
    payload: dict[str, object] = {
        "condition": body.condition,
        "frame_preference": body.frame_preference,
        "context": body.context,
        "adjustment_history": body.adjustment_history,
        "count": body.count,
    }
    if body.base_card is not None:
        payload["base_card"] = body.base_card.model_dump()
    return json.dumps(payload, ensure_ascii=True)


@router.post("/spark/generate", tags=["spark"])
async def spark_generate(
    body: SparkGenerateRequest,
    _user: User = require_user(),
) -> SparkGenerateResponse:
    """Generate one or more Spark cards via a stateless LLM proxy endpoint."""
    llm_key = get_openai_api_key()
    if not llm_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="OpenAI API key not configured",
        )

    model_name = get_llm_model()
    llm = make_chat_llm(
        model=model_name,
        api_key=llm_key,
        temperature=0.6,
        max_tokens=800,
    )

    try:
        from app.prompt_loader import load_prompt

        system_prompt = load_prompt(PROMPT_NAME)
        response = await asyncio.wait_for(
            llm.ainvoke(
                [
                    SystemMessage(content=system_prompt),
                    HumanMessage(content=_build_user_prompt(body)),
                ]
            ),
            timeout=25,
        )
        text = _content_to_text(response.content)
        parsed = _extract_json_object(text)
        payload = _SparkModelPayload.model_validate(parsed)
    except ValidationError as exc:
        logger.warning("Spark payload validation failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Spark model produced invalid response shape",
        ) from exc
    except (json.JSONDecodeError, ValueError) as exc:
        logger.warning("Spark response JSON parse failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Spark model did not return valid JSON",
        ) from exc
    except TimeoutError as exc:
        logger.warning("Spark LLM timeout")
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="Spark model request timed out",
        ) from exc
    except Exception as exc:  # pragma: no cover - network/provider dependent
        logger.exception("Spark model request failed")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Spark generation request failed",
        ) from exc

    cards = payload.cards
    if body.condition in {"A", "C"}:
        cards = cards[:1]
    elif body.condition == "D":
        cards = sorted(cards, key=lambda card: card.fit_score or 0, reverse=True)

    if not cards:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Spark model returned no cards",
        )

    return SparkGenerateResponse(
        condition=body.condition,
        cards=cards,
        model=model_name,
        prompt_version=prompt_version(PROMPT_NAME),
    )
