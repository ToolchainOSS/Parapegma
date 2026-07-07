"""Static, researcher-curated Spark library for conditions A and B.

Conditions A ("Random Spark") and B ("pick a vibe, no intake") are Spark's
non-adaptive control groups: they never personalize to the user, so unlike
C/D they need no LLM call at all.

Data source (in priority order)
--------------------------------
1. **Google Sheets** — when ``SPARK_SHEETS_SPREADSHEET_ID`` *and*
   ``SPARK_SHEETS_CREDENTIALS_JSON`` are configured the library is loaded
   from a researcher-maintained spreadsheet.  Collaborators can add or edit
   prompts without touching the repository.
2. **Bundled JSON** (``api/config/spark_library.json``) — always-present
   fallback loaded via :func:`app.config_loader.resolve_config_path`.

Cache strategy (stale-while-revalidate)
----------------------------------------
* Fresh (age < TTL, default 60 s): served immediately from memory.
* Stale: the current snapshot is returned *immediately*; a background task
  refreshes from Sheets without blocking the request.
* Sheets-never-succeeded (cold start failure): bundled JSON is used.
* Sheets-failed-after-success: the last-good Sheets snapshot is served
  indefinitely until a refresh succeeds.

Selection logic (unchanged)
----------------------------
  Condition A: pick uniformly at random from the *entire* library, ignoring
               any ``frame_preference`` (true random, no choice).
  Condition B: the user has already picked one of the five Spark vibes
               (``frame_preference``) via the vibe wheel; pick uniformly at
               random among entries tagged with it.
"""

from __future__ import annotations

import asyncio
import json
import logging
import random
from dataclasses import dataclass, field
from hashlib import sha256
from time import monotonic
from typing import Literal

from app.config_loader import resolve_config_path

logger = logging.getLogger(__name__)

SparkFrame = Literal["calm", "zoomies", "silly", "challenge", "science"]
ALL_FRAMES: tuple[SparkFrame, ...] = (
    "calm",
    "zoomies",
    "silly",
    "challenge",
    "science",
)

# Generic, frame-level rationale — mirrors the tone established for each vibe
# in sparkData.ts / spark_proxy_system.txt.
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

_LIBRARY_FILENAME = "spark_library.json"


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# In-memory cache state
# ---------------------------------------------------------------------------


@dataclass
class _CacheState:
    entries: tuple[SparkLibraryEntry, ...]
    version_hash: str
    source: Literal["sheets", "file"]
    fetched_at: float = field(default_factory=monotonic)
    is_refreshing: bool = False


_cache: _CacheState | None = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _validate_entries(entries: tuple[SparkLibraryEntry, ...]) -> None:
    """Raise ``ValueError`` unless every frame has ≥ 2 entries.

    This is the make-invalid-states-unrepresentable guard: every Spark vibe
    must be selectable in condition B so every frame needs at least two
    entries (one alone would make that vibe deterministic, not a choice).
    """
    if not entries:
        raise ValueError("Spark library must contain at least one entry")
    for frame in ALL_FRAMES:
        tag_count = sum(1 for entry in entries if frame in entry.tags)
        if tag_count < 2:
            raise ValueError(
                f"Spark library tag '{frame}' has only {tag_count} "
                "entry(ies); every tag needs at least 2"
            )


def _compute_hash(entries: tuple[SparkLibraryEntry, ...]) -> str:
    """Return a deterministic SHA-256 hex digest of the library content.

    The hash is sorted by entry id and uses canonical JSON so that identical
    data from any source produces the same digest — enabling reliable change
    detection in the ``prompt_version`` field regardless of Sheets vs file.
    """
    sorted_entries = sorted(entries, key=lambda e: e.id)
    payload = json.dumps(
        [
            {
                "id": e.id,
                "title": e.title,
                "action": e.action,
                "reward": e.reward,
                "tags": sorted(e.tags),
            }
            for e in sorted_entries
        ],
        sort_keys=True,
        ensure_ascii=True,
    )
    return sha256(payload.encode()).hexdigest()


def _load_from_file() -> tuple[SparkLibraryEntry, ...]:
    """Load and validate SparkLibraryEntry records from the bundled JSON file."""
    library_path = resolve_config_path(_LIBRARY_FILENAME)
    with library_path.open(encoding="utf-8") as config_file:
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

    result = tuple(entries)
    _validate_entries(result)
    return result


def _sheets_is_configured() -> bool:
    from app.config import (
        get_spark_sheets_credentials_json,
        get_spark_sheets_spreadsheet_id,
    )

    return bool(
        get_spark_sheets_credentials_json() and get_spark_sheets_spreadsheet_id()
    )


# ---------------------------------------------------------------------------
# Async refresh pipeline
# ---------------------------------------------------------------------------


async def _do_refresh() -> None:
    """Load entries from Sheets (if configured) or the bundled JSON.

    On Sheets failure after a prior successful load the existing snapshot is
    preserved so the endpoint keeps serving stale-but-valid data.  ``fetched_at``
    is intentionally *not* updated in that case so the next request re-triggers
    a retry after the TTL expires.
    """
    global _cache

    if _sheets_is_configured():
        from app.config import (
            get_spark_sheets_credentials_json,
            get_spark_sheets_range,
            get_spark_sheets_spreadsheet_id,
            get_spark_sheets_timeout,
        )
        from app.services.spark_sheets_source import fetch_entries_from_sheets

        try:
            entries = await asyncio.to_thread(
                fetch_entries_from_sheets,
                get_spark_sheets_credentials_json(),
                get_spark_sheets_spreadsheet_id(),
                get_spark_sheets_range(),
                get_spark_sheets_timeout(),
            )
            _validate_entries(entries)
            _cache = _CacheState(
                entries=entries,
                version_hash=_compute_hash(entries),
                source="sheets",
            )
            logger.info(
                "Spark library loaded from Sheets: %d entries (hash %s…)",
                len(entries),
                _cache.version_hash[:8],
            )
            return
        except Exception as exc:
            fate = (
                "keeping last-good snapshot"
                if _cache is not None
                else "falling back to bundled JSON"
            )
            logger.warning(
                "Spark Sheets fetch failed (%s: %s); %s",
                type(exc).__name__,
                exc,
                fate,
            )
            if _cache is not None:
                # Keep serving existing snapshot; do NOT update fetched_at so
                # the next stale request triggers another retry after the TTL.
                return

    # Sheets not configured or first-ever Sheets fetch failed — load bundled JSON.
    file_entries = _load_from_file()  # propagates on failure
    _cache = _CacheState(
        entries=file_entries,
        version_hash=_compute_hash(file_entries),
        source="file",
    )
    logger.debug(
        "Spark library loaded from bundled JSON: %d entries", len(file_entries)
    )


async def _background_refresh() -> None:
    """Background coroutine: refresh the cache and reset the in-flight flag."""
    global _cache
    try:
        await _do_refresh()
    except Exception as exc:
        logger.error("Spark library background refresh failed entirely: %s", exc)
    finally:
        # Reset the flag on whatever cache object is current so future stale
        # requests can schedule another refresh attempt.
        if _cache is not None:
            _cache.is_refreshing = False


async def _get_library() -> tuple[SparkLibraryEntry, ...]:
    """Return library entries, applying stale-while-revalidate semantics."""
    global _cache
    from app.config import get_spark_sheets_cache_ttl

    ttl = get_spark_sheets_cache_ttl()
    now = monotonic()

    if _cache is not None:
        if (now - _cache.fetched_at) < ttl:
            return _cache.entries  # fresh: serve immediately

        # Stale: return current snapshot and kick off a background refresh.
        if not _cache.is_refreshing:
            _cache.is_refreshing = True
            asyncio.get_running_loop().create_task(_background_refresh())
        return _cache.entries

    # Cold start: first request triggers a synchronous load.
    await _do_refresh()
    if _cache is not None:
        return _cache.entries

    raise RuntimeError(  # pragma: no cover — _do_refresh raises before this
        "Spark library failed to load from all sources"
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def library_version() -> dict[str, str]:
    """Return ``{"prompt_file": ..., "prompt_sha256": ...}`` for the active dataset.

    Mirrors the shape :func:`app.prompt_loader.prompt_version` uses for LLM
    prompts so API consumers see a consistent versioning contract regardless
    of whether A/B data comes from Sheets or the bundled JSON.  The hash is
    computed over entry content (not raw file bytes) for determinism across
    sources.
    """
    if _cache is not None:
        return {"prompt_file": "spark_library", "prompt_sha256": _cache.version_hash}
    # Pre-load fallback: called before any async request context (e.g. some tests).
    try:
        digest = sha256(resolve_config_path(_LIBRARY_FILENAME).read_bytes()).hexdigest()
    except FileNotFoundError:
        digest = "0" * 64
    return {"prompt_file": "spark_library", "prompt_sha256": digest}


def clear_library_cache() -> None:
    """Reset the in-memory cache.  Used in tests to isolate cache state."""
    global _cache
    _cache = None


async def pick_static_sparks(
    condition: Literal["A", "B"],
    frame_preference: SparkFrame | None,
    count: int,
) -> list[ResolvedSpark]:
    """Select up to ``count`` static Sparks (fewer if the matching pool is smaller).

    Condition A ignores ``frame_preference`` and draws from the whole library,
    resolving each entry's frame to one of its own tags.  Condition B requires
    ``frame_preference`` and draws only from entries tagged with it, resolving
    every card to that exact preference.

    Raises ``ValueError`` if condition B is missing a ``frame_preference``;
    callers should turn that into an HTTP 422.
    """
    library = await _get_library()

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
