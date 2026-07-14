"""Strict request models for the anonymous Spark research telemetry plane.

The browser sends a persistent, random installation identifier from localStorage
and an optional ThumbmarkJS fingerprint. Route handlers immediately derive
BLAKE3 keyed hashes and never persist or log either raw identifier.
"""

from __future__ import annotations

from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.services.spark_library import SparkFrame


class SparkClientIdentity(BaseModel):
    """Pseudonymous identity inputs supplied on every Spark request."""

    model_config = ConfigDict(extra="forbid")

    installation_id: UUID
    fingerprint: str | None = Field(default=None, min_length=1, max_length=512)
    fingerprint_version: str | None = Field(default=None, max_length=64)
    timezone: str | None = Field(default=None, max_length=64)
    locale: str | None = Field(default=None, max_length=35)


class SparkFlowStartedEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_type: Literal["flow_started"]


class SparkIntakeAnsweredEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_type: Literal["intake_answered"]
    field: Literal["anchor", "action", "frame", "time"]
    value: str = Field(min_length=1, max_length=120)


class SparkFrameSelectedEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_type: Literal["frame_selected"]
    frame: SparkFrame


class SparkCardSelectedEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_type: Literal["card_selected"]
    rank: int = Field(ge=1, le=5)


class SparkTimerFinishedEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_type: Literal["timer_finished"]
    completion: Literal["completed", "skipped"]


class SparkFeedbackSubmittedEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_type: Literal["feedback_submitted"]
    tried: int = Field(ge=0, le=2)
    reason: str | None = Field(default=None, max_length=100)
    tweak: str = Field(default="", max_length=400)


class SparkCueSelectedEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_type: Literal["cue_selected"]
    cue: str = Field(min_length=1, max_length=120)
    reminder: Literal["calendar", "email", "skip"] | None = None
    confidence: int | None = Field(default=None, ge=1, le=5)


class SparkConditionCompletedEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_type: Literal["condition_completed"]
    fit: int = Field(ge=1, le=5)
    clarity: int = Field(ge=1, le=5)
    willing: int = Field(ge=1, le=5)


SparkClientEvent = Annotated[
    SparkFlowStartedEvent
    | SparkIntakeAnsweredEvent
    | SparkFrameSelectedEvent
    | SparkCardSelectedEvent
    | SparkTimerFinishedEvent
    | SparkFeedbackSubmittedEvent
    | SparkCueSelectedEvent
    | SparkConditionCompletedEvent,
    Field(discriminator="event_type"),
]


class SparkEventRequest(BaseModel):
    """An idempotent, immutable client-side Spark interaction event."""

    model_config = ConfigDict(extra="forbid")

    identity: SparkClientIdentity
    flow_id: UUID
    client_event_id: UUID
    condition: Literal["A", "B", "C", "D"]
    event: SparkClientEvent
