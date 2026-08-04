"""Spark prototype generation and pseudonymous research telemetry routes.

Spark remains isolated from existing Flow conversation state and requires no
registration. The client carries remix state as before. Each request also
contains a browser-local pseudonymous identifier and optional ThumbmarkJS
fingerprint; raw values are immediately keyed-hashed and never persisted or logged.

Conditions A ("Random Spark") and B ("Spark Wheel") are non-adaptive control
groups: they are served entirely from a researcher-curated static library
(``app.services.spark_library``) and never call the LLM. Conditions C and D
are the adaptive, intake-informed conditions and proxy validated requests to
the configured LLM, returning structured Spark card payloads.

Choice model (why no condition asks for a vibe up front)
---------------------------------------------------------
Participants generally cannot name the vibe they want before seeing a Spark, so
no condition takes ``frame_preference`` as a *user* input any more. B serves one
random Spark per vibe (five concrete cards); D fans out one LLM call per vibe and
returns ``5 x 5`` ranked options. In both, the chosen vibe is derived from the
card the participant actually picks. ``frame_preference`` survives only as an
internal request field: the D catalog uses it to pin each fan-out call to one
vibe, and C/D remixes use it to carry an explicit "switch to X vibe" adjustment.

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
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field, ValidationError, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_llm_model, get_openai_api_key
from app.db import get_db
from app.llm import make_chat_llm
from app.prompt_loader import prompt_version
from app.schemas.spark_research import SparkClientIdentity, SparkEventRequest
from app.services.spark_library import (
    ALL_FRAMES,
    SparkFrame,
    library_version,
    pick_one_spark_per_frame,
    pick_random_sparks,
)
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
# Condition D catalog: one fan-out LLM call per vibe, this many options each.
_D_OPTIONS_PER_FRAME = 5
# Widest response any condition can produce (the D catalog).
_MAX_RESPONSE_CARDS = len(ALL_FRAMES) * _D_OPTIONS_PER_FRAME
# Cards a single LLM round-trip may return.
_MAX_CARDS_PER_CALL = 5


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
    cards: list[SparkCard] = Field(min_length=1, max_length=_MAX_RESPONSE_CARDS)
    model: str
    prompt_version: dict[str, str]


class _SparkModelPayload(BaseModel):
    cards: list[SparkCard] = Field(min_length=1, max_length=_MAX_CARDS_PER_CALL)


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


def _build_user_prompt(
    body: SparkGenerateRequest,
    frame_preference: SparkFrame | None,
    count: int,
) -> str:
    """Serialize one model request.

    ``frame_preference`` and ``count`` are passed explicitly rather than read off
    ``body`` because the condition D catalog issues one call per vibe, each
    overriding both.
    """
    payload: dict[str, object] = {
        "condition": body.condition,
        "frame_preference": frame_preference,
        "context": body.context,
        "adjustment_history": body.adjustment_history,
        "count": count,
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


async def _invoke_spark_model(
    llm: BaseChatModel,
    system_prompt: str,
    user_prompt: str,
) -> list[SparkCard]:
    """One bounded model round-trip → validated cards.

    Every failure mode is mapped to an ``HTTPException`` here so callers — including
    the concurrent condition D catalog — never have to re-classify provider errors.
    """
    try:
        response = await asyncio.wait_for(
            llm.ainvoke(
                [
                    SystemMessage(content=system_prompt),
                    HumanMessage(content=user_prompt),
                ]
            ),
            timeout=25,
        )
        text = _content_to_text(response.content)
        parsed = _extract_json_object(text)
        return _SparkModelPayload.model_validate(parsed).cards
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
    except HTTPException:
        raise
    except Exception as exc:  # pragma: no cover - network/provider dependent
        logger.exception("Spark model request failed")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Spark generation request failed",
        ) from exc


async def _generate_frame_catalog(
    llm: BaseChatModel,
    system_prompt: str,
    body: SparkGenerateRequest,
) -> list[SparkCard]:
    """Condition D first generate — ``_D_OPTIONS_PER_FRAME`` options for every vibe.

    The five calls are independent, so they are issued concurrently (applicative,
    not sequential). ``return_exceptions=True`` lets every call settle before the
    first failure is re-raised — ``gather`` would otherwise leave the siblings
    running detached against the provider. Failure is all-or-nothing on purpose:
    a participant seeing three of five vibes would be a silent confound.

    Each call is pinned to one vibe and the returned cards are forced to it, so
    the five categories are structurally guaranteed rather than model-trusted.
    """
    results = await asyncio.gather(
        *(
            _invoke_spark_model(
                llm,
                system_prompt,
                _build_user_prompt(body, frame, _D_OPTIONS_PER_FRAME),
            )
            for frame in ALL_FRAMES
        ),
        return_exceptions=True,
    )

    catalog: list[SparkCard] = []
    for frame, result in zip(ALL_FRAMES, results, strict=True):
        if isinstance(result, BaseException):
            raise result
        ranked = sorted(result, key=lambda card: card.fit_score or 0, reverse=True)
        catalog.extend(card.model_copy(update={"frame": frame}) for card in ranked)
    return catalog


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
        # A is exactly one random Spark; B is exactly one Spark per vibe. Both
        # selectors are total on a valid library, so the only failure left here
        # is the library itself being unavailable.
        try:
            resolved = (
                await pick_random_sparks(1)
                if body.condition == "A"
                else await pick_one_spark_per_frame()
            )
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

    from app.prompt_loader import load_prompt

    try:
        system_prompt = load_prompt(PROMPT_NAME)
    except Exception as exc:  # pragma: no cover - packaging/deployment defect
        logger.exception("Spark system prompt failed to load")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Spark generation request failed",
        ) from exc

    model_name = get_llm_model()

    # A D catalog call returns five full cards, so it needs a wider budget than
    # the single-card C generate or a remix.
    is_catalog = body.condition == "D" and body.base_card is None
    llm = make_chat_llm(
        model=model_name,
        api_key=llm_key,
        temperature=0.6,
        max_tokens=1600 if is_catalog else 800,
    )

    if is_catalog:
        cards = await _generate_frame_catalog(llm, system_prompt, body)
    else:
        cards = await _invoke_spark_model(
            llm,
            system_prompt,
            _build_user_prompt(body, body.frame_preference, body.count),
        )
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
