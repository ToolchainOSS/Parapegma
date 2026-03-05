"""Tests for default timezone config, LLM time context, worker prompt, and specialist prompt context."""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.config import clear_config_cache, get_default_timezone


# ---------------------------------------------------------------------------
# Default timezone fallback (config helper)
# ---------------------------------------------------------------------------


class TestDefaultTimezone:
    def setup_method(self) -> None:
        clear_config_cache()

    def teardown_method(self) -> None:
        os.environ.pop("TZ", None)
        clear_config_cache()

    def test_no_tz_env_defaults_to_america_toronto(self) -> None:
        os.environ.pop("TZ", None)
        clear_config_cache()
        assert get_default_timezone() == "America/Toronto"

    def test_valid_tz_env_is_used(self) -> None:
        os.environ["TZ"] = "Europe/Berlin"
        clear_config_cache()
        assert get_default_timezone() == "Europe/Berlin"

    def test_invalid_tz_env_defaults_to_america_toronto(self) -> None:
        os.environ["TZ"] = "Narnia/Lamppost"
        clear_config_cache()
        assert get_default_timezone() == "America/Toronto"

    def test_empty_tz_env_defaults_to_america_toronto(self) -> None:
        os.environ["TZ"] = ""
        clear_config_cache()
        assert get_default_timezone() == "America/Toronto"


# ---------------------------------------------------------------------------
# LLM time context helper
# ---------------------------------------------------------------------------


class TestLlmTimeContext:
    def setup_method(self) -> None:
        os.environ.pop("TZ", None)
        clear_config_cache()

    def teardown_method(self) -> None:
        os.environ.pop("TZ", None)
        clear_config_cache()

    def test_with_explicit_timezone(self) -> None:
        from app.services.llm_time_context import get_llm_time_context

        now = datetime(2026, 3, 5, 22, 0, 0, tzinfo=UTC)  # 17:00 Toronto (EST)
        ctx = get_llm_time_context("America/Toronto", now)
        assert ctx["timezone"] == "America/Toronto"
        assert ctx["current_date"] == "2026-03-05"
        assert ctx["current_time"] == "17:00"
        assert ctx["current_datetime"] == "2026-03-05 17:00"

    def test_with_none_falls_back_to_default(self) -> None:
        from app.services.llm_time_context import get_llm_time_context

        now = datetime(2026, 3, 5, 22, 0, 0, tzinfo=UTC)
        ctx = get_llm_time_context(None, now)
        # Default is America/Toronto
        assert ctx["timezone"] == "America/Toronto"
        assert ctx["current_time"] == "17:00"

    def test_with_invalid_tz_falls_back(self) -> None:
        from app.services.llm_time_context import get_llm_time_context

        now = datetime(2026, 1, 15, 12, 0, 0, tzinfo=UTC)
        ctx = get_llm_time_context("Invalid/Zone", now)
        assert ctx["timezone"] == "America/Toronto"


# ---------------------------------------------------------------------------
# Worker prompt-context regression test
# ---------------------------------------------------------------------------


class TestWorkerPromptContext:
    """Prove the worker LLM gets the actual current time, not stale preferred_time."""

    @pytest.mark.asyncio
    async def test_worker_uses_actual_current_time_not_preferred_time(self) -> None:
        """Profile preferred_time=11:15, but actual fire time is 17:00 Toronto.
        The LLM input must contain 17:00 as current_time, not 11:15."""
        from app.schemas.patches import UserProfileData

        profile = UserProfileData(
            prompt_anchor="morning jog",
            preferred_time="11:15",
            display_name="Alice",
        )

        captured_invoke_args: dict = {}

        async def fake_ainvoke(args: dict) -> MagicMock:
            captured_invoke_args.update(args)
            m = MagicMock()
            m.content = "Time to run!"
            return m

        fake_chain = MagicMock()
        fake_chain.ainvoke = fake_ainvoke

        # Freeze now_utc to 22:00 UTC = 17:00 America/Toronto (EST)
        frozen_now = datetime(2026, 1, 15, 22, 0, 0, tzinfo=UTC)

        with (
            patch("app.worker.notification_worker.config") as mock_config,
            patch(
                "app.worker.notification_worker.load_user_profile",
                new_callable=AsyncMock,
            ) as mock_load,
            patch("app.worker.notification_worker.ChatOpenAI"),
            patch(
                "app.worker.notification_worker.ChatPromptTemplate"
            ) as mock_prompt_cls,
            patch(
                "app.services.llm_time_context.get_user_timezone",
                new_callable=AsyncMock,
                return_value="America/Toronto",
            ),
            patch(
                "app.services.llm_time_context.datetime",
            ) as mock_dt,
        ):
            mock_config.get_openai_api_key.return_value = "fake-key"
            mock_config.get_llm_model.return_value = "gpt-4o-mini"
            mock_load.return_value = profile

            mock_dt.now.return_value = frozen_now
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)

            mock_prompt_instance = MagicMock()
            mock_prompt_cls.from_messages.return_value = mock_prompt_instance
            mock_prompt_instance.__or__ = MagicMock(return_value=fake_chain)

            from app.worker.notification_worker import _generate_custom_prompt

            fake_db = MagicMock()
            result = await _generate_custom_prompt(fake_db, 1, "Daily Nudge")

        assert result == "Time to run!"
        # The authoritative current_time should be 17:00, not 11:15
        assert captured_invoke_args["current_time"] == "17:00"
        assert captured_invoke_args["timezone"] == "America/Toronto"
        # preferred_time should NOT be in the profile_json payload
        profile_json = captured_invoke_args["profile_json"]
        profile_data = json.loads(profile_json)
        assert "preferred_time" not in profile_data


# ---------------------------------------------------------------------------
# Specialist prompt context test
# ---------------------------------------------------------------------------


class TestSpecialistPromptContext:
    """Verify specialist prompts include localized time placeholders."""

    def test_coach_prompt_has_time_placeholders(self) -> None:
        from app.prompt_loader import load_prompt

        text = load_prompt("coach_system")
        assert "{current_date}" in text
        assert "{current_time}" in text
        assert "{timezone}" in text

    def test_intake_prompt_has_time_placeholders(self) -> None:
        from app.prompt_loader import load_prompt

        text = load_prompt("intake_system")
        assert "{current_date}" in text
        assert "{current_time}" in text
        assert "{timezone}" in text

    def test_feedback_prompt_has_time_placeholders(self) -> None:
        from app.prompt_loader import load_prompt

        text = load_prompt("feedback_system")
        assert "{current_date}" in text
        assert "{current_time}" in text
        assert "{timezone}" in text

    def test_prompt_generator_has_authoritative_time_guidance(self) -> None:
        from app.prompt_loader import load_prompt

        text = load_prompt("prompt_generator_system")
        assert "{current_date}" in text
        assert "{current_time}" in text
        assert "{timezone}" in text
        assert "authoritative" in text.lower()

    def test_specialist_agent_formats_time_into_prompt(self) -> None:
        """Verify _create_specialist_agent applies time context args to prompt text."""
        from app.prompt_loader import load_prompt

        raw = load_prompt("coach_system")
        args = {
            "display_name": "TestUser",
            "current_date": "2026-03-05",
            "current_time": "17:00",
            "timezone": "America/Toronto",
            "current_datetime": "2026-03-05 17:00",
        }
        formatted = raw.format(**args)
        assert "17:00" in formatted
        assert "2026-03-05" in formatted
        assert "America/Toronto" in formatted
        assert "{current_time}" not in formatted
