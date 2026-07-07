"""Unit tests for the Spark A/B library: file loading, Sheets parsing, cache."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from app.services.spark_library import (
    ALL_FRAMES,
    SparkLibraryEntry,
    _compute_hash,
    _load_from_file,
    clear_library_cache,
    library_version,
    pick_static_sparks,
)
from app.services.spark_sheets_source import _parse_rows

# ---------------------------------------------------------------------------
# Autouse fixture: reset cache between tests
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_library_cache() -> None:  # type: ignore[return]
    clear_library_cache()
    yield  # type: ignore[misc]
    clear_library_cache()


# ---------------------------------------------------------------------------
# File-based loading
# ---------------------------------------------------------------------------


def test_load_from_file_satisfies_tag_count_invariant() -> None:
    entries = _load_from_file()
    assert len(entries) >= 1
    for frame in ALL_FRAMES:
        count = sum(1 for entry in entries if frame in entry.tags)
        assert count >= 2, f"tag '{frame}' has fewer than 2 entries"


def test_load_from_file_entries_have_no_video_links() -> None:
    entries = _load_from_file()
    for entry in entries:
        blob = f"{entry.title} {entry.action} {entry.reward}".lower()
        assert "http://" not in blob
        assert "https://" not in blob
        assert "loom.com" not in blob
        assert "youtube" not in blob
        assert "youtu.be" not in blob


# ---------------------------------------------------------------------------
# library_version()
# ---------------------------------------------------------------------------


def test_library_version_is_stable_dict_shape() -> None:
    version = library_version()
    assert version["prompt_file"] == "spark_library"
    assert isinstance(version["prompt_sha256"], str)
    assert len(version["prompt_sha256"]) == 64  # sha256 hex digest length


@pytest.mark.asyncio
async def test_library_version_reflects_cache_after_load(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.config import clear_config_cache

    monkeypatch.delenv("SPARK_SHEETS_SPREADSHEET_ID", raising=False)
    monkeypatch.delenv("SPARK_SHEETS_CREDENTIALS_JSON", raising=False)
    clear_config_cache()

    await pick_static_sparks(condition="A", frame_preference=None, count=1)
    version = library_version()
    assert version["prompt_file"] == "spark_library"
    assert len(version["prompt_sha256"]) == 64

    clear_config_cache()


# ---------------------------------------------------------------------------
# _compute_hash()
# ---------------------------------------------------------------------------


def test_compute_hash_is_deterministic() -> None:
    entries = _load_from_file()
    assert _compute_hash(entries) == _compute_hash(entries)
    assert len(_compute_hash(entries)) == 64


def test_compute_hash_changes_on_content_change() -> None:
    entries = _load_from_file()
    old = entries[0]
    modified = (
        SparkLibraryEntry(
            id=old.id,
            tags=old.tags,
            title="CHANGED: " + old.title,
            action=old.action,
            reward=old.reward,
        ),
        *entries[1:],
    )
    assert _compute_hash(entries) != _compute_hash(modified)


def test_compute_hash_is_order_independent() -> None:
    """Reversing the entry order must not change the hash (sorted by id)."""
    entries = _load_from_file()
    assert _compute_hash(entries) == _compute_hash(tuple(reversed(entries)))


# ---------------------------------------------------------------------------
# Sheets row parsing (_parse_rows)
# ---------------------------------------------------------------------------


def test_parse_rows_valid() -> None:
    rows: list[list[str]] = [
        ["id", "title", "action", "reward", "tags"],
        ["r1", "Title A", "Do X", "Feel Y", "calm,zoomies"],
        ["r2", "Title B", "Do Z", "Feel W", "silly"],
    ]
    entries = _parse_rows(rows)
    assert len(entries) == 2
    assert entries[0].id == "r1"
    assert entries[0].tags == ("calm", "zoomies")
    assert entries[1].id == "r2"
    assert entries[1].tags == ("silly",)


def test_parse_rows_column_order_independent() -> None:
    rows: list[list[str]] = [
        ["tags", "reward", "action", "title", "id"],
        ["calm", "Feel good", "Do calm thing", "Calm Title", "c1"],
    ]
    entries = _parse_rows(rows)
    assert len(entries) == 1
    assert entries[0].id == "c1"
    assert entries[0].tags == ("calm",)
    assert entries[0].title == "Calm Title"


def test_parse_rows_missing_required_column_raises() -> None:
    rows: list[list[str]] = [
        ["id", "title", "action", "reward"],  # no "tags"
        ["r1", "Title", "Act", "Reward"],
    ]
    with pytest.raises(ValueError, match="missing required column"):
        _parse_rows(rows)


def test_parse_rows_empty_raises() -> None:
    with pytest.raises(ValueError, match="empty"):
        _parse_rows([])


def test_parse_rows_only_header_raises() -> None:
    rows: list[list[str]] = [["id", "title", "action", "reward", "tags"]]
    with pytest.raises(ValueError, match="No valid entries"):
        _parse_rows(rows)


def test_parse_rows_unknown_tags_skipped_valid_tag_kept() -> None:
    rows: list[list[str]] = [
        ["id", "title", "action", "reward", "tags"],
        ["r1", "T", "A", "R", "calm,unknown_vibe"],
    ]
    entries = _parse_rows(rows)
    assert len(entries) == 1
    assert entries[0].tags == ("calm",)


def test_parse_rows_all_unknown_tags_drops_entry() -> None:
    rows: list[list[str]] = [
        ["id", "title", "action", "reward", "tags"],
        ["r1", "T1", "A1", "R1", "bogus,nope"],
        ["r2", "T2", "A2", "R2", "science"],
    ]
    entries = _parse_rows(rows)
    assert len(entries) == 1
    assert entries[0].id == "r2"


def test_parse_rows_short_row_padded() -> None:
    """A row shorter than the header should not crash; missing cells are ''."""
    rows: list[list[str]] = [
        ["id", "title", "action", "reward", "tags"],
        ["r1", "T", "A", "R"],  # missing tags cell
    ]
    # No valid tags → entry is skipped, only-header path triggers ValueError
    with pytest.raises(ValueError, match="No valid entries"):
        _parse_rows(rows)


def test_parse_rows_empty_id_skipped() -> None:
    rows: list[list[str]] = [
        ["id", "title", "action", "reward", "tags"],
        ["", "T", "A", "R", "calm"],
        ["r2", "T2", "A2", "R2", "science"],
    ]
    entries = _parse_rows(rows)
    assert len(entries) == 1
    assert entries[0].id == "r2"


# ---------------------------------------------------------------------------
# pick_static_sparks (async)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pick_static_sparks_condition_a_ignores_frame_preference(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.config import clear_config_cache

    monkeypatch.delenv("SPARK_SHEETS_SPREADSHEET_ID", raising=False)
    monkeypatch.delenv("SPARK_SHEETS_CREDENTIALS_JSON", raising=False)
    clear_config_cache()

    resolved = await pick_static_sparks(condition="A", frame_preference="calm", count=1)
    assert len(resolved) == 1
    assert resolved[0].frame in ALL_FRAMES

    clear_config_cache()


@pytest.mark.asyncio
async def test_pick_static_sparks_condition_b_matches_requested_frame(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.config import clear_config_cache

    monkeypatch.delenv("SPARK_SHEETS_SPREADSHEET_ID", raising=False)
    monkeypatch.delenv("SPARK_SHEETS_CREDENTIALS_JSON", raising=False)
    clear_config_cache()

    resolved = await pick_static_sparks(
        condition="B", frame_preference="science", count=5
    )
    assert len(resolved) >= 1
    assert all(entry.frame == "science" for entry in resolved)

    clear_config_cache()


@pytest.mark.asyncio
async def test_pick_static_sparks_condition_b_requires_frame_preference(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.config import clear_config_cache

    monkeypatch.delenv("SPARK_SHEETS_SPREADSHEET_ID", raising=False)
    monkeypatch.delenv("SPARK_SHEETS_CREDENTIALS_JSON", raising=False)
    clear_config_cache()

    with pytest.raises(ValueError, match="frame_preference is required"):
        await pick_static_sparks(condition="B", frame_preference=None, count=3)

    clear_config_cache()


@pytest.mark.asyncio
async def test_pick_static_sparks_caps_count_to_pool_size(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.config import clear_config_cache

    monkeypatch.delenv("SPARK_SHEETS_SPREADSHEET_ID", raising=False)
    monkeypatch.delenv("SPARK_SHEETS_CREDENTIALS_JSON", raising=False)
    clear_config_cache()

    # "challenge" only has 2 entries in the curated library
    resolved = await pick_static_sparks(
        condition="B", frame_preference="challenge", count=5
    )
    assert 1 <= len(resolved) <= 2

    clear_config_cache()


# ---------------------------------------------------------------------------
# Cache and fallback behaviour
# ---------------------------------------------------------------------------


def _make_fake_entries(count_per_frame: int = 2) -> tuple[SparkLibraryEntry, ...]:
    """Minimal valid library: ``count_per_frame`` entries per frame."""
    return tuple(
        SparkLibraryEntry(
            id=f"fake-{frame}-{i}",
            tags=(frame,),
            title=f"Fake {frame} {i}",
            action="act",
            reward="rew",
        )
        for frame in ALL_FRAMES
        for i in range(count_per_frame)
    )


@pytest.mark.asyncio
async def test_get_library_uses_file_when_sheets_not_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.config import clear_config_cache
    from app.services import spark_library

    monkeypatch.delenv("SPARK_SHEETS_SPREADSHEET_ID", raising=False)
    monkeypatch.delenv("SPARK_SHEETS_CREDENTIALS_JSON", raising=False)
    clear_config_cache()

    await pick_static_sparks(condition="A", frame_preference=None, count=1)

    assert spark_library._cache is not None
    assert spark_library._cache.source == "file"

    clear_config_cache()


@pytest.mark.asyncio
async def test_get_library_uses_sheets_when_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.config import clear_config_cache
    from app.services import spark_library

    fake_entries = _make_fake_entries()
    monkeypatch.setenv("SPARK_SHEETS_SPREADSHEET_ID", "test-sheet-id")
    monkeypatch.setenv("SPARK_SHEETS_CREDENTIALS_JSON", '{"type": "service_account"}')
    clear_config_cache()

    with patch(
        "app.services.spark_sheets_source.fetch_entries_from_sheets",
        MagicMock(return_value=fake_entries),
    ):
        await pick_static_sparks(condition="A", frame_preference=None, count=1)

    assert spark_library._cache is not None
    assert spark_library._cache.source == "sheets"
    assert spark_library._cache.entries == fake_entries

    clear_config_cache()


@pytest.mark.asyncio
async def test_do_refresh_falls_back_to_file_on_sheets_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Cold-start Sheets failure should transparently load the bundled JSON."""
    from app.config import clear_config_cache
    from app.services import spark_library

    monkeypatch.setenv("SPARK_SHEETS_SPREADSHEET_ID", "test-sheet-id")
    monkeypatch.setenv("SPARK_SHEETS_CREDENTIALS_JSON", '{"type": "service_account"}')
    clear_config_cache()

    with patch(
        "app.services.spark_sheets_source.fetch_entries_from_sheets",
        MagicMock(side_effect=RuntimeError("connection refused")),
    ):
        resolved = await pick_static_sparks(
            condition="A", frame_preference=None, count=1
        )

    assert len(resolved) == 1
    assert spark_library._cache is not None
    assert spark_library._cache.source == "file"

    clear_config_cache()


@pytest.mark.asyncio
async def test_do_refresh_preserves_snapshot_on_subsequent_sheets_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """After a successful Sheets load, a later failure must keep the snapshot."""
    from app.config import clear_config_cache
    from app.services import spark_library
    from app.services.spark_library import _do_refresh

    fake_entries = _make_fake_entries()
    monkeypatch.setenv("SPARK_SHEETS_SPREADSHEET_ID", "test-sheet-id")
    monkeypatch.setenv("SPARK_SHEETS_CREDENTIALS_JSON", '{"type": "service_account"}')
    clear_config_cache()

    # First load succeeds from Sheets.
    with patch(
        "app.services.spark_sheets_source.fetch_entries_from_sheets",
        MagicMock(return_value=fake_entries),
    ):
        await _do_refresh()

    first_cache = spark_library._cache
    assert first_cache is not None
    assert first_cache.source == "sheets"

    # Second refresh fails; snapshot must be preserved.
    with patch(
        "app.services.spark_sheets_source.fetch_entries_from_sheets",
        MagicMock(side_effect=RuntimeError("Sheets down")),
    ):
        await _do_refresh()

    # Cache object is unchanged: same entries, same instance.
    assert spark_library._cache is first_cache

    clear_config_cache()


@pytest.mark.asyncio
async def test_stale_cache_served_immediately_and_refresh_triggered(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Stale cache is returned without blocking; background refresh flag is set."""
    import asyncio as _asyncio

    from app.config import clear_config_cache
    from app.services import spark_library
    from app.services.spark_library import _CacheState

    monkeypatch.delenv("SPARK_SHEETS_SPREADSHEET_ID", raising=False)
    monkeypatch.delenv("SPARK_SHEETS_CREDENTIALS_JSON", raising=False)
    clear_config_cache()

    # Prime the cache from file.
    await pick_static_sparks(condition="A", frame_preference=None, count=1)
    assert spark_library._cache is not None

    # Wind the clock back so the cache appears stale.
    stale_cache = _CacheState(
        entries=spark_library._cache.entries,
        version_hash=spark_library._cache.version_hash,
        source=spark_library._cache.source,
        fetched_at=spark_library._cache.fetched_at - 9999.0,
        is_refreshing=False,
    )
    spark_library._cache = stale_cache

    # The request should return immediately (stale data) without blocking.
    resolved = await pick_static_sparks(condition="A", frame_preference=None, count=1)
    assert len(resolved) == 1
    assert spark_library._cache.is_refreshing is True

    # Let the background task run and reset the flag.
    await _asyncio.sleep(0.05)

    clear_config_cache()


@pytest.mark.asyncio
async def test_sheets_invariant_violation_falls_back_to_file(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Sheets data that violates the ≥2 entries/frame rule falls back to bundled JSON."""
    from app.config import clear_config_cache
    from app.services import spark_library

    # Only one entry total — fails the ≥2 per frame invariant.
    bad_entries = (
        SparkLibraryEntry(
            id="only-one", tags=("calm",), title="T", action="A", reward="R"
        ),
    )
    monkeypatch.setenv("SPARK_SHEETS_SPREADSHEET_ID", "test-sheet-id")
    monkeypatch.setenv("SPARK_SHEETS_CREDENTIALS_JSON", '{"type": "service_account"}')
    clear_config_cache()

    with patch(
        "app.services.spark_sheets_source.fetch_entries_from_sheets",
        MagicMock(return_value=bad_entries),
    ):
        await pick_static_sparks(condition="A", frame_preference=None, count=1)

    assert spark_library._cache is not None
    assert spark_library._cache.source == "file"

    clear_config_cache()
