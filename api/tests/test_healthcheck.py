"""Tests for the role-aware container healthcheck.

The API and worker share one image, so ``app.healthcheck`` must pick the right
probe based on ``FLOW_ROLE``. These tests cover both roles without binding a
socket or running a server: the API probe is exercised via a monkeypatched
``urlopen`` and the worker probe via a real heartbeat file on disk.
"""

from __future__ import annotations

import os
import time
from collections.abc import Iterator
from types import SimpleNamespace

import pytest
from app import config, healthcheck


@pytest.fixture(autouse=True)
def _clear_config_cache() -> Iterator[None]:
    config.clear_config_cache()
    yield
    config.clear_config_cache()


class TestWorkerProbe:
    def test_fresh_heartbeat_is_healthy(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path
    ) -> None:
        monkeypatch.setenv("FLOW_ROLE", "worker")
        monkeypatch.setenv("FLOW_DATA_DIR", str(tmp_path))
        (tmp_path / healthcheck.HEARTBEAT_FILENAME).write_text("now", encoding="utf-8")
        assert healthcheck.main() == 0

    def test_stale_heartbeat_is_unhealthy(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path
    ) -> None:
        monkeypatch.setenv("FLOW_ROLE", "worker")
        monkeypatch.setenv("FLOW_DATA_DIR", str(tmp_path))
        hb = tmp_path / healthcheck.HEARTBEAT_FILENAME
        hb.write_text("old", encoding="utf-8")
        old = time.time() - (healthcheck.HEARTBEAT_MAX_AGE_S + 30)
        os.utime(hb, (old, old))
        assert healthcheck.main() == 1

    def test_missing_heartbeat_is_unhealthy(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path
    ) -> None:
        monkeypatch.setenv("FLOW_ROLE", "worker")
        monkeypatch.setenv("FLOW_DATA_DIR", str(tmp_path))
        assert healthcheck.main() == 1


class TestApiProbe:
    def test_default_role_is_api(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("FLOW_ROLE", raising=False)
        assert config.get_role() == "api"

    def test_2xx_is_healthy(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("FLOW_ROLE", raising=False)

        class _Resp:
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, *exc) -> None:
                return None

        monkeypatch.setattr(
            healthcheck.urllib.request, "urlopen", lambda *a, **k: _Resp()
        )
        assert healthcheck.main() == 0

    def test_5xx_is_unhealthy(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("FLOW_ROLE", raising=False)

        resp = SimpleNamespace(
            status=503,
            __enter__=lambda self: self,
            __exit__=lambda self, *exc: None,
        )

        def _fake_urlopen(*a, **k):
            return resp

        monkeypatch.setattr(healthcheck.urllib.request, "urlopen", _fake_urlopen)
        assert healthcheck.main() == 1

    def test_connection_error_is_unhealthy(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("FLOW_ROLE", raising=False)

        def _boom(*a, **k):
            raise OSError("connection refused")

        monkeypatch.setattr(healthcheck.urllib.request, "urlopen", _boom)
        assert healthcheck.main() == 1
