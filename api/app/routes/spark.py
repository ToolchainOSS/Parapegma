"""Spark prototype generation and pseudonymous research telemetry routes.

Spark remains isolated from existing Flow conversation state and requires no
registration. The client carries remix state as before. Each request also
contains a browser-local pseudonymous identifier and optional ThumbmarkJS
fingerprint; raw values are immediately keyed-hashed and never persisted or logged.

Conditions A ("Random Spark") and B ("pick a vibe") are non-adaptive control
groups: they are served entirely from a researcher-curated static library
(``app.services.spark_library``) and never call the LLM. Conditions C and D
are the adaptive, intake-informed conditions and proxy validated requests to
the configured LLM, returning structured Spark card payloads.

Remix model (conditions C/D only)
----------------------------------
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
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field, ValidationError, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_llm_model, get_openai_api_key
from app.db import get_db
from app.llm import make_chat_llm
from app.prompt_loader import prompt_version
from app.schemas.spark_research import SparkClientIdentity, SparkEventRequest
from app.services.spark_library import SparkFrame, library_version, pick_static_sparks
from app.services.spark_research import (
    ResolvedSparkParticipant,
    SparkResearchConfigurationError,
    get_spark_interaction,
    persist_spark_interaction,
    resolve_spark_participant,
)

logger = logging.getLogger(__name__)

router = APIRouter()

PROMPT_NAME = "spark_proxy_system"
_MAX_HISTORY = 20


class SparkCard(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    frame: SparkFrame
    action: str = Field(min_length=1, max_length=600)
    reward: str = Field(min_length=1, max_length=300)
    why: str = Field(min_length=1, max_length=400)
    fit_score: int | None = Field(default=None, ge=0, le=100)


class SparkGenerateRequest(BaseModel):
    identity: SparkClientIdentity
    flow_id: UUID
    client_event_id: UUID
    condition: Literal["A", "B", "C", "D"]
    frame_preference: SparkFrame | None = None
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


async def _resolve_participant_or_503(
    db: AsyncSession, identity: SparkClientIdentity
) -> ResolvedSparkParticipant:
    try:
        return await resolve_spark_participant(
            db,
            installation_id=str(identity.installation_id),
            fingerprint=identity.fingerprint,
            fingerprint_version=identity.fingerprint_version,
            timezone=identity.timezone,
            locale=identity.locale,
        )
    except SparkResearchConfigurationError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Spark research identity is not configured",
        ) from exc


def _generation_event_payload(
    body: SparkGenerateRequest, response: SparkGenerateResponse
) -> dict[str, object]:
    """Build persisted data without the raw browser identity inputs."""
    request_payload: dict[str, object] = {
        "condition": body.condition,
        "frame_preference": body.frame_preference,
        "context": body.context,
        "adjustment_history": body.adjustment_history,
        "count": body.count,
    }
    if body.base_card is not None:
        request_payload["base_card"] = body.base_card.model_dump(mode="json")
    return {
        "request": request_payload,
        "response": response.model_dump(mode="json"),
    }


async def _persist_generation_response(
    db: AsyncSession,
    *,
    participant: ResolvedSparkParticipant,
    body: SparkGenerateRequest,
    response: SparkGenerateResponse,
) -> SparkGenerateResponse:
    await persist_spark_interaction(
        db,
        participant_id=participant.participant_id,
        flow_id=str(body.flow_id),
        client_event_id=str(body.client_event_id),
        condition=body.condition,
        event_type="generation_succeeded",
        payload=_generation_event_payload(body, response),
    )
    await db.commit()
    return response


@router.post("/spark/generate", tags=["spark"])
async def spark_generate(
    body: SparkGenerateRequest,
    db: AsyncSession = Depends(get_db),
) -> SparkGenerateResponse:
    """Generate one or more Spark cards.

    Intentionally unauthenticated: Spark is a public, no-login prototype so
    anyone can try it without creating an account. The persisted research
    identity is pseudonymous and is never an authentication factor.

    Conditions A and B are served from the static, researcher-curated
    library and never touch the LLM. Conditions C and D proxy to the LLM.
    """
    participant = await _resolve_participant_or_503(db, body.identity)
    existing = await get_spark_interaction(
        db,
        participant_id=participant.participant_id,
        client_event_id=str(body.client_event_id),
    )
    if existing is not None:
        if existing.event_type != "generation_succeeded":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Spark event id was already used for a different event",
            )
        stored_response = existing.payload_json.get("response")
        try:
            response = SparkGenerateResponse.model_validate(stored_response)
        except ValidationError as exc:  # pragma: no cover - persisted corruption guard
            logger.exception("Stored Spark generation response is invalid")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Stored Spark generation response is invalid",
            ) from exc
        await db.commit()
        return response

    if body.condition in ("A", "B"):
        try:
            resolved = await pick_static_sparks(
                condition=body.condition,
                frame_preference=body.frame_preference,
                count=body.count,
            )
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=str(exc),
            ) from exc
        except Exception as exc:
            logger.warning("Spark A/B library error: %s", exc)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Spark library is temporarily unavailable",
            ) from exc

        cards = [
            SparkCard(
                title=entry.title,
                frame=entry.frame,
                action=entry.action,
                reward=entry.reward,
                why=entry.why,
            )
            for entry in resolved
        ]
        if body.condition == "A":
            cards = cards[:1]

        return await _persist_generation_response(
            db,
            participant=participant,
            body=body,
            response=SparkGenerateResponse(
                condition=body.condition,
                cards=cards,
                model="static-library",
                prompt_version=library_version(),
            ),
        )

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
    if body.condition == "C":
        cards = cards[:1]
    elif body.condition == "D":
        cards = sorted(cards, key=lambda card: card.fit_score or 0, reverse=True)

    if not cards:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Spark model returned no cards",
        )

    return await _persist_generation_response(
        db,
        participant=participant,
        body=body,
        response=SparkGenerateResponse(
            condition=body.condition,
            cards=cards,
            model=model_name,
            prompt_version=prompt_version(PROMPT_NAME),
        ),
    )


@router.post("/spark/events", status_code=status.HTTP_204_NO_CONTENT, tags=["spark"])
async def spark_record_event(
    body: SparkEventRequest,
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Persist a strictly typed, idempotent Spark interaction event."""
    participant = await _resolve_participant_or_503(db, body.identity)
    event_payload = body.event.model_dump(mode="json")
    await persist_spark_interaction(
        db,
        participant_id=participant.participant_id,
        flow_id=str(body.flow_id),
        client_event_id=str(body.client_event_id),
        condition=body.condition,
        event_type=event_payload["event_type"],
        payload=event_payload,
    )
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
