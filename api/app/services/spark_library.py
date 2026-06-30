"""Static, researcher-curated Spark library for conditions A and B.

Conditions A ("Random Spark") and B ("pick a vibe, no intake") are Spark's
non-adaptive control groups: they never personalize to the user, so unlike
C/D they need no LLM call at all. This module loads a small set of
researcher-written one-minute movement prompts from
``api/config/spark_library.json`` and selects among them at request time:

  Condition A: pick uniformly at random from the *entire* library, ignoring
               any ``frame_preference`` (true random, no choice).
  Condition B: the user has already picked one of the five Spark vibes
               (``frame_preference``) via the vibe wheel; pick uniformly at
               random among entries tagged with that vibe. An entry may carry
               more than one tag.
"""

from __future__ import annotations

import json
import random
from dataclasses import dataclass
from functools import lru_cache
from hashlib import sha256
from pathlib import Path
from typing import Literal

SparkFrame = Literal["calm", "zoomies", "silly", "challenge", "science"]
ALL_FRAMES: tuple[SparkFrame, ...] = (
    "calm",
    "zoomies",
    "silly",
    "challenge",
    "science",
)

# Generic, frame-level rationale -- mirrors the tone already established for
# each vibe in sparkData.ts / spark_proxy_system.txt. The library itself only
# supplies the concrete action/reward (pure researcher content); this fills
# the required SparkCard "why" field consistently per resolved frame rather
# than fabricating a bespoke rationale for every entry.
_WHY_BY_FRAME: dict[SparkFrame, str] = {
    "calm": (
        "A slow, low-effort reset like this can ease physical tension and "
        "help you refocus without raising your heart rate."
    ),
    "zoomies": (
        "A quick burst of movement gets your blood flowing and counters the "
        "energy dip that comes from sitting still."
    ),
    "silly": (
        "Movement doesn't have to be serious to work -- a playful break "
        "still delivers the same physical reset, and a grin is a bonus."
    ),
    "challenge": (
        "A higher-intensity option recruits more muscle groups and gives a "
        "stronger nudge to your alertness than a gentle stretch."
    ),
    "science": (
        "Short movement breaks are linked to better circulation and renewed "
        "focus, even in just sixty seconds."
    ),
}

_LIBRARY_PATH = Path(__file__).resolve().parents[2] / "config" / "spark_library.json"


@dataclass(frozen=True)
class SparkLibraryEntry:
    id: str
    tags: tuple[SparkFrame, ...]
    title: str
    action: str
    reward: str


@dataclass(frozen=True)
class ResolvedSpark:
    """A library entry resolved to a single concrete frame for one response."""

    id: str
    frame: SparkFrame
    title: str
    action: str
    reward: str
    why: str


@lru_cache(maxsize=1)
def _load_library() -> tuple[SparkLibraryEntry, ...]:
    with _LIBRARY_PATH.open(encoding="utf-8") as config_file:
        raw = json.load(config_file)

    if not isinstance(raw, dict) or not isinstance(raw.get("sparks"), list):
        raise ValueError("spark_library.json must contain a 'sparks' array")

    entries: list[SparkLibraryEntry] = []
    for item in raw["sparks"]:
        if not isinstance(item, dict):
            raise ValueError("Each spark_library entry must be an object")
        tags = item.get("tags")
        if not isinstance(tags, list) or not tags:
            raise ValueError(
                f"Entry '{item.get('id')}' must have a non-empty 'tags' list"
            )
        for tag in tags:
            if tag not in ALL_FRAMES:
                raise ValueError(f"Entry '{item.get('id')}' has unknown tag '{tag}'")
        entries.append(
            SparkLibraryEntry(
                id=str(item["id"]),
                tags=tuple(tags),
                title=str(item["title"]),
                action=str(item["action"]),
                reward=str(item["reward"]),
            )
        )

    if not entries:
        raise ValueError("spark_library.json must contain at least one entry")

    # Make-invalid-states-unrepresentable guard: every Spark vibe must be
    # selectable in condition B, so every tag needs at least two entries (one
    # entry alone would make that vibe deterministic, not a choice).
    for frame in ALL_FRAMES:
        tag_count = sum(1 for entry in entries if frame in entry.tags)
        if tag_count < 2:
            raise ValueError(
                f"spark_library.json tag '{frame}' has only {tag_count} "
                "entry(ies); every tag needs at least 2"
            )

    return tuple(entries)


@lru_cache(maxsize=1)
def library_version() -> dict[str, str]:
    """Return ``{"prompt_file": ..., "prompt_sha256": ...}`` for the static
    library, mirroring the shape ``app.prompt_loader.prompt_version`` uses for
    LLM prompts so API consumers see a consistent versioning contract."""
    digest = sha256(_LIBRARY_PATH.read_bytes()).hexdigest()
    return {"prompt_file": "spark_library", "prompt_sha256": digest}


def pick_static_sparks(
    condition: Literal["A", "B"],
    frame_preference: SparkFrame | None,
    count: int,
) -> list[ResolvedSpark]:
    """Select up to ``count`` static Sparks (fewer if the matching pool is
    smaller).

    Condition A ignores ``frame_preference`` and draws from the whole
    library, resolving each entry's frame to one of its own tags. Condition B
    requires ``frame_preference`` and draws only from entries tagged with it,
    resolving every card's frame to that exact preference (so the rendered
    card always matches the vibe the user picked).

    Raises ``ValueError`` if condition B is missing a ``frame_preference``;
    callers should turn that into an HTTP 422.
    """
    library = _load_library()

    if condition == "A":
        pool = library
    else:
        if frame_preference is None:
            raise ValueError("frame_preference is required for condition B")
        pool = tuple(entry for entry in library if frame_preference in entry.tags)

    k = min(count, len(pool))
    chosen = random.sample(pool, k=k)

    resolved: list[ResolvedSpark] = []
    for entry in chosen:
        frame = frame_preference if condition == "B" else random.choice(entry.tags)
        assert frame is not None  # narrowed above when condition == "B"
        resolved.append(
            ResolvedSpark(
                id=entry.id,
                frame=frame,
                title=entry.title,
                action=entry.action,
                reward=entry.reward,
                why=_WHY_BY_FRAME[frame],
            )
        )
    return resolved
