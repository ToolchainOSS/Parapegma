"""Domain-separated BLAKE3 subkey derivation from Flow's master secret.

Every security-sensitive feature receives a distinct, fixed-length subkey.
Calling code must never use the master secret directly or reuse a subkey across
contexts.
"""

from __future__ import annotations

import base64
import binascii
import re
from functools import cache

from blake3 import blake3

from app.config import get_flow_crypto_master_key

MASTER_KEY_BYTES = 32
DERIVED_KEY_BYTES = 32

_SPARK_IDENTITY_CONTEXT = "flow.spark.identity-hmac.v1"
_RANDOMIZATION_CONTEXT = "flow.experiment.randomization.v1"


class CryptoConfigurationError(RuntimeError):
    """Raised when the deployment master key is absent or malformed."""


def _decode_master_key(encoded_key: str) -> bytes:
    normalized = encoded_key.strip()
    if not normalized:
        raise CryptoConfigurationError("FLOW_CRYPTO_MASTER_KEY must be configured")
    if not re.fullmatch(r"[A-Za-z0-9_-]+", normalized):
        raise CryptoConfigurationError(
            "FLOW_CRYPTO_MASTER_KEY must be unpadded Base64URL-encoded key material"
        )

    try:
        padded = normalized + "=" * (-len(normalized) % 4)
        key = base64.b64decode(padded, altchars=b"-_", validate=True)
    except (ValueError, binascii.Error) as exc:
        raise CryptoConfigurationError(
            "FLOW_CRYPTO_MASTER_KEY must be unpadded Base64URL-encoded key material"
        ) from exc

    if len(key) != MASTER_KEY_BYTES:
        raise CryptoConfigurationError(
            "FLOW_CRYPTO_MASTER_KEY must decode to exactly 32 bytes"
        )
    return key


@cache
def _master_key() -> bytes:
    return _decode_master_key(get_flow_crypto_master_key())


def derive_subkey(context: str) -> bytes:
    """Derive a 32-byte subkey in BLAKE3's dedicated derivation mode."""
    return blake3(_master_key(), derive_key_context=context).digest(DERIVED_KEY_BYTES)


def get_spark_identity_hmac_key() -> bytes:
    """Return the domain-separated HMAC key for Spark pseudonymous identity."""
    return derive_subkey(_SPARK_IDENTITY_CONTEXT)


def get_randomization_key() -> bytes:
    """Return the domain-separated key for experiment block randomization."""
    return derive_subkey(_RANDOMIZATION_CONTEXT)


def is_crypto_master_key_configured() -> bool:
    """Report key validity without exposing master-key contents."""
    try:
        _master_key()
    except CryptoConfigurationError:
        return False
    return True


def clear_crypto_key_cache() -> None:
    """Clear derived-key cache for configuration tests."""
    _master_key.cache_clear()
