"""Unit tests for the static Spark library (conditions A and B)."""

from __future__ import annotations

import pytest
from app.services.spark_library import (
    ALL_FRAMES,
    _load_library,
    library_version,
    pick_static_sparks,
)


def test_library_loads_and_satisfies_tag_count_invariant() -> None:
    entries = _load_library()
    assert len(entries) >= 1
    for frame in ALL_FRAMES:
        count = sum(1 for entry in entries if frame in entry.tags)
        assert count >= 2, f"tag '{frame}' has fewer than 2 entries"


def test_library_entries_have_no_video_links() -> None:
    entries = _load_library()
    for entry in entries:
        blob = f"{entry.title} {entry.action} {entry.reward}".lower()
        assert "http://" not in blob
        assert "https://" not in blob
        assert "loom.com" not in blob
        assert "youtube" not in blob
        assert "youtu.be" not in blob


def test_library_version_is_stable_dict_shape() -> None:
    version = library_version()
    assert version["prompt_file"] == "spark_library"
    assert isinstance(version["prompt_sha256"], str)
    assert len(version["prompt_sha256"]) == 64  # sha256 hex digest length


def test_pick_static_sparks_condition_a_ignores_frame_preference() -> None:
    resolved = pick_static_sparks(condition="A", frame_preference="calm", count=1)
    assert len(resolved) == 1
    assert resolved[0].frame in ALL_FRAMES


def test_pick_static_sparks_condition_b_matches_requested_frame() -> None:
    resolved = pick_static_sparks(condition="B", frame_preference="science", count=5)
    assert len(resolved) >= 1
    assert all(entry.frame == "science" for entry in resolved)


def test_pick_static_sparks_condition_b_requires_frame_preference() -> None:
    with pytest.raises(ValueError, match="frame_preference is required"):
        pick_static_sparks(condition="B", frame_preference=None, count=3)


def test_pick_static_sparks_caps_count_to_pool_size() -> None:
    # "challenge" only has 2 entries in the curated library; asking for more
    # than the pool should not raise, just return what's available.
    resolved = pick_static_sparks(condition="B", frame_preference="challenge", count=5)
    assert 1 <= len(resolved) <= 2
