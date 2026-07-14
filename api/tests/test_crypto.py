"""Tests for Flow's unified cryptographic master-key derivation."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest
from app import config
from app.services.crypto import (
    CryptoConfigurationError,
    derive_subkey,
    get_randomization_key,
    get_spark_identity_hmac_key,
    is_crypto_master_key_configured,
)
from app.services.randomization import get_daily_condition

_TEST_MASTER_KEY = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"


@pytest.fixture(autouse=True)
def _clear_crypto_caches() -> None:
    config.clear_config_cache()
    yield
    config.clear_config_cache()


def test_subkeys_are_deterministic_and_domain_separated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FLOW_CRYPTO_MASTER_KEY", _TEST_MASTER_KEY)
    config.clear_config_cache()

    spark_key = get_spark_identity_hmac_key()
    randomization_key = get_randomization_key()

    assert len(spark_key) == 32
    assert len(randomization_key) == 32
    assert spark_key != randomization_key
    assert spark_key == get_spark_identity_hmac_key()
    assert derive_subkey("flow.test.domain.v1") != spark_key
    assert is_crypto_master_key_configured() is True


@pytest.mark.parametrize(
    "master_key",
    ["", "not a base64url key", "AQID", "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="],
)
def test_invalid_master_key_fails_closed(
    monkeypatch: pytest.MonkeyPatch, master_key: str
) -> None:
    monkeypatch.setenv("FLOW_CRYPTO_MASTER_KEY", master_key)
    config.clear_config_cache()

    with pytest.raises(CryptoConfigurationError):
        get_randomization_key()
    assert is_crypto_master_key_configured() is False


def test_derived_randomization_key_keeps_each_block_balanced(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FLOW_CRYPTO_MASTER_KEY", _TEST_MASTER_KEY)
    config.clear_config_cache()
    key = get_randomization_key()
    start = datetime(2026, 7, 1, tzinfo=UTC)

    first_block = [
        get_daily_condition(17, start, date(2026, 7, 1) + timedelta(days=offset), key)
        for offset in range(4)
    ]
    repeated_block = [
        get_daily_condition(17, start, date(2026, 7, 1) + timedelta(days=offset), key)
        for offset in range(4)
    ]

    assert sorted(first_block) == ["A", "B", "C", "D"]
    assert repeated_block == first_block
