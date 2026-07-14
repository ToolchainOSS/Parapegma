"""Credential loading and bounded token refresh for Spark Google Sheets.

This module accepts the standard JSON document produced by Google Cloud when a
service-account key is created.  The document is supplied as one JSON string
through ``SPARK_SHEETS_CREDENTIALS_JSON``; escaped ``\\n`` characters in the
``private_key`` value are decoded by :func:`json.loads` before google-auth uses
the PEM key.

Credentials are constrained to the Sheets read-only scope.  The loader reports
safe configuration errors without echoing the source JSON or private key.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import requests
from google.auth.transport.requests import Request as GoogleRequest
from google.oauth2.service_account import Credentials

_SHEETS_READONLY_SCOPE = "https://www.googleapis.com/auth/spreadsheets.readonly"
_REQUIRED_SERVICE_ACCOUNT_FIELDS = frozenset(
    {"type", "client_email", "private_key", "token_uri"}
)


def load_readonly_service_account_credentials(credentials_json: str) -> Credentials:
    """Return read-only Sheets credentials from a standard service-account JSON.

    Google service-account documents include additional metadata such as
    ``project_id``, ``private_key_id``, ``client_id``, certificate URLs, and
    ``universe_domain``.  The full mapping is intentionally passed unchanged
    to google-auth so current and future metadata remains supported.

    Raises ``ValueError`` with a secret-safe message when the input is not a
    valid service-account document.  The original JSON is never included in
    the message or logs.
    """
    try:
        raw = json.loads(credentials_json)
    except json.JSONDecodeError as exc:
        raise ValueError("SPARK_SHEETS_CREDENTIALS_JSON must be valid JSON") from exc

    if not isinstance(raw, dict):
        raise ValueError("SPARK_SHEETS_CREDENTIALS_JSON must be a JSON object")

    missing = sorted(_REQUIRED_SERVICE_ACCOUNT_FIELDS - raw.keys())
    if missing:
        raise ValueError(
            "SPARK_SHEETS_CREDENTIALS_JSON is missing required field(s): "
            + ", ".join(missing)
        )

    bad_types = sorted(
        field
        for field in _REQUIRED_SERVICE_ACCOUNT_FIELDS
        if not isinstance(raw[field], str) or not raw[field].strip()
    )
    if bad_types:
        raise ValueError(
            "SPARK_SHEETS_CREDENTIALS_JSON field(s) must be non-empty strings: "
            + ", ".join(bad_types)
        )

    if raw["type"] != "service_account":
        raise ValueError(
            "SPARK_SHEETS_CREDENTIALS_JSON must contain type 'service_account'"
        )

    try:
        return Credentials.from_service_account_info(
            raw,
            scopes=[_SHEETS_READONLY_SCOPE],
        )
    except (TypeError, ValueError) as exc:
        raise ValueError(
            "SPARK_SHEETS_CREDENTIALS_JSON contains invalid Google "
            "service-account credentials"
        ) from exc


def make_timeout_bound_google_request(
    session: requests.Session,
    timeout: float,
) -> Callable[..., Any]:
    """Return a google-auth request callable that always uses ``timeout``.

    ``Credentials.refresh()`` accepts a request callable but does not take a
    timeout argument itself.  Binding the configured timeout here prevents a
    token refresh from outliving the same deadline applied to the Sheets API
    GET request.
    """
    request = GoogleRequest(session=session)

    def request_with_timeout(*args: Any, **kwargs: Any) -> Any:
        kwargs.setdefault("timeout", timeout)
        return request(*args, **kwargs)

    return request_with_timeout
