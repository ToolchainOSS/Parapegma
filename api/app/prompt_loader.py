"""Thin loader for prompt text files with in-memory caching.

Prompts are resolved from an ordered list of candidate directories so that a
deployment can mount a custom ``prompts/`` directory to override the shipped
text, while still falling back to a copy baked into the image at a location
that lives **completely outside** the application working tree. This matters in
production where ``docker-compose`` bind-mounts host directories over paths
under ``/app`` (e.g. ``./prompts -> /app/prompts`` and ``./app -> /app/data``):
a stale mount that predates a newly added prompt would otherwise shadow it and
raise ``FileNotFoundError`` at request time.

Resolution order (first match wins):

1. ``$FLOW_PROMPTS_DIR`` (explicit override, optional).
2. ``<repo>/prompts`` — the mountable directory (``/app/prompts`` in Docker).
3. ``$FLOW_BAKED_PROMPTS_DIR`` / ``/opt/flow/prompts`` — baked into the image
   outside ``/app``, so no bind-mount under ``/app`` can ever shadow it.
"""

from __future__ import annotations

import os
from hashlib import sha256
from pathlib import Path

_PACKAGE_DIR = Path(__file__).resolve().parent

# Absolute, image-baked fallback that lives outside the /app working tree so it
# cannot be shadowed by any bind-mount under /app. Overridable via env for tests
# and bespoke deployments. The Dockerfile copies prompts here and sets the var.
_BAKED_PROMPTS_DIR = Path(os.environ.get("FLOW_BAKED_PROMPTS_DIR", "/opt/flow/prompts"))

# Candidate directories in priority order. The mountable directory is checked
# first so operators can override individual prompts; the image-baked copy is
# the always-present fallback that a bind-mount under /app cannot shadow.
_CANDIDATE_DIRS: list[Path] = [
    _PACKAGE_DIR.parent / "prompts",  # mountable: api/prompts or /app/prompts
    _BAKED_PROMPTS_DIR,  # baked fallback outside /app: /opt/flow/prompts
]

_cache: dict[str, str] = {}


def _resolve_prompt_path(name: str) -> Path:
    """Return the first existing path for ``prompts/{name}.txt``.

    The optional ``FLOW_PROMPTS_DIR`` environment variable is consulted first so
    it can be changed at runtime without reimporting the module.
    """
    candidates: list[Path] = []
    override = os.environ.get("FLOW_PROMPTS_DIR")
    if override:
        candidates.append(Path(override))
    candidates.extend(_CANDIDATE_DIRS)

    for directory in candidates:
        path = directory / f"{name}.txt"
        if path.is_file():
            return path

    raise FileNotFoundError(
        f"Prompt '{name}' not found in any of: "
        + ", ".join(str(directory) for directory in candidates)
    )


def load_prompt(name: str) -> str:
    """Return the content of ``prompts/{name}.txt``, cached after first read."""
    if name not in _cache:
        _cache[name] = _resolve_prompt_path(name).read_text(encoding="utf-8")
    return _cache[name]


def prompt_hash(name: str) -> str:
    """Return the SHA-256 hex digest of the prompt content."""
    return sha256(load_prompt(name).encode("utf-8")).hexdigest()


def prompt_version(name: str) -> dict:
    """Return ``{"prompt_file": name, "prompt_sha256": hash}``."""
    return {"prompt_file": name, "prompt_sha256": prompt_hash(name)}
