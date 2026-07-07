"""Google Sheets source for the Spark A/B prompt library.

Fetches rows from a researcher-maintained spreadsheet and parses them into
:class:`~app.services.spark_library.SparkLibraryEntry` objects.

Expected spreadsheet layout (header row mandatory, order independent):

    id | title | action | reward | tags

Where ``tags`` is a comma-separated list of
:data:`~app.services.spark_library.SparkFrame` names (e.g. ``calm,zoomies``).

The function is intentionally *synchronous* — callers run it inside
``asyncio.to_thread`` so the async event loop is never blocked.

Security notes
--------------
* Credentials JSON is never logged; only a short key-id prefix appears in
  debug output.
* The OAuth scope is ``spreadsheets.readonly`` — the service account cannot
  write to any sheet.
"""

from __future__ import annotations

import json
import logging
import urllib.parse
from typing import Any

import requests
from google.auth.transport.requests import Request as GoogleRequest
from google.oauth2.service_account import Credentials

from app.services.spark_library import ALL_FRAMES, SparkFrame, SparkLibraryEntry

logger = logging.getLogger(__name__)

_SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]
_SHEETS_API_BASE = "https://sheets.googleapis.com/v4/spreadsheets"


def fetch_entries_from_sheets(
    credentials_json: str,
    spreadsheet_id: str,
    range_name: str,
    timeout: float,
) -> tuple[SparkLibraryEntry, ...]:
    """Fetch and parse Spark library entries from Google Sheets (synchronous).

    Raises
    ------
    ValueError
        If the sheet is empty, a required column is missing, or no valid
        entries can be parsed.
    RuntimeError
        If the Sheets API returns a non-200 status.
    google.auth.exceptions.TransportError
        If token refresh fails (bad credentials, network error).
    """
    creds_data: dict[str, Any] = json.loads(credentials_json)
    creds = Credentials.from_service_account_info(creds_data, scopes=_SCOPES)

    key_hint = creds_data.get("client_email", "")[:20] or "<unknown>"
    logger.debug("Refreshing Sheets token for service account %r", key_hint)

    session = requests.Session()
    session.request = lambda method, url, **kwargs: requests.Session.request(  # type: ignore[method-assign]
        session, method, url, timeout=timeout, **kwargs
    )
    creds.refresh(GoogleRequest(session=session))

    url = (
        f"{_SHEETS_API_BASE}"
        f"/{urllib.parse.quote(spreadsheet_id, safe='')}"
        f"/values/{urllib.parse.quote(range_name)}"
    )
    response = session.get(
        url,
        headers={"Authorization": f"Bearer {creds.token}"},
        timeout=timeout,
    )

    if response.status_code != 200:
        raise RuntimeError(
            f"Sheets API returned HTTP {response.status_code} for "
            f"spreadsheet {spreadsheet_id!r}: {response.text[:200]}"
        )

    data = response.json()
    rows: list[list[str]] = data.get("values", [])
    entries = _parse_rows(rows)
    logger.debug(
        "Sheets fetch complete: %d valid entries from %r",
        len(entries),
        range_name,
    )
    return entries


def _parse_rows(rows: list[list[str]]) -> tuple[SparkLibraryEntry, ...]:
    """Parse raw sheet rows into :class:`SparkLibraryEntry` records.

    Parameters
    ----------
    rows:
        Outer list is rows; inner list is cell values (all strings from the
        Sheets API).  The first row must be a header.

    Raises
    ------
    ValueError
        Sheet is empty, a required column is absent, or no valid entries exist.
    """
    if not rows:
        raise ValueError("Google Sheet is empty (no rows found)")

    header = [col.strip().lower() for col in rows[0]]
    required = {"id", "title", "action", "reward", "tags"}
    missing = required - set(header)
    if missing:
        raise ValueError(
            "Google Sheet is missing required column(s): " + ", ".join(sorted(missing))
        )

    col = {name: header.index(name) for name in required}
    entries: list[SparkLibraryEntry] = []

    for row_idx, row in enumerate(rows[1:], start=2):
        # Pad short rows so index access is safe.
        padded = list(row) + [""] * (len(header) - len(row))

        entry_id = padded[col["id"]].strip()
        if not entry_id:
            logger.warning("Sheets row %d: empty 'id', skipping", row_idx)
            continue

        raw_tags = [
            t.strip().lower() for t in padded[col["tags"]].split(",") if t.strip()
        ]
        valid_tags: list[SparkFrame] = []
        for tag in raw_tags:
            if tag in ALL_FRAMES:
                valid_tags.append(tag)  # type: ignore[arg-type]
            else:
                logger.warning(
                    "Sheets row %d id=%r: unknown tag %r (valid: %s), skipping tag",
                    row_idx,
                    entry_id,
                    tag,
                    ", ".join(ALL_FRAMES),
                )

        if not valid_tags:
            logger.warning(
                "Sheets row %d id=%r: no valid tags — entry skipped",
                row_idx,
                entry_id,
            )
            continue

        entries.append(
            SparkLibraryEntry(
                id=entry_id,
                tags=tuple(valid_tags),
                title=padded[col["title"]].strip(),
                action=padded[col["action"]].strip(),
                reward=padded[col["reward"]].strip(),
            )
        )

    if not entries:
        raise ValueError("No valid entries found in Google Sheet")

    return tuple(entries)
