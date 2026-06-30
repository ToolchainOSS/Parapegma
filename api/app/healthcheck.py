"""Container healthcheck entry point — correct for both API and worker roles.

The API and worker share one image, so the image's baked ``HEALTHCHECK`` must do
the right thing for whichever role the container is running. The role is read
from ``FLOW_ROLE`` (``api`` by default):

* ``api`` (or anything else): HTTP ``GET /healthz`` on ``$API_PORT`` must return
  a 2xx. ``localhost`` resolves on both IPv4 and IPv6, so this works whether
  uvicorn bound v4, v6, or dual-stack (``::``).
* ``worker``: there is no HTTP server, so liveness is "the heartbeat file the
  worker loop refreshes every iteration is younger than ``HEARTBEAT_MAX_AGE_S``".

Kept deliberately dependency-light (stdlib + :mod:`app.config` only) so it starts
fast and does not import the heavy worker/engine modules on every probe.

Exit code ``0`` means healthy; any non-zero means unhealthy.
"""

from __future__ import annotations

import os
import sys
import time
import urllib.request

from app import config

# Heartbeat file the worker loop refreshes once per iteration (~5s poll). Defined
# here, in the light module, and imported by the worker so the producer and the
# consumer of the heartbeat can never drift apart.
HEARTBEAT_FILENAME = "worker.heartbeat"

# A heartbeat older than this is treated as a wedged loop. Generous relative to
# the ~5s poll so a single slow iteration never flaps the container unhealthy.
HEARTBEAT_MAX_AGE_S = 60.0


def heartbeat_path() -> str:
    """Return the absolute path of the worker heartbeat file."""
    return os.path.join(config.get_data_dir(), HEARTBEAT_FILENAME)


def _check_worker() -> int:
    """Return ``0`` when the worker heartbeat is fresh, ``1`` otherwise."""
    path = heartbeat_path()
    try:
        age = time.time() - os.path.getmtime(path)
    except OSError:
        # No heartbeat yet (or unreadable): unhealthy. The HEALTHCHECK
        # start-period covers the brief window before the first heartbeat.
        return 1
    return 0 if age < HEARTBEAT_MAX_AGE_S else 1


def _check_api() -> int:
    """Return ``0`` when ``GET /healthz`` returns a 2xx, ``1`` otherwise."""
    url = f"http://localhost:{config.get_port()}/healthz"
    try:
        with urllib.request.urlopen(url, timeout=4) as resp:
            return 0 if 200 <= resp.status < 300 else 1
    except Exception:
        return 1


def main() -> int:
    """Dispatch to the role-appropriate probe and return its exit code."""
    role = config.get_role()
    if role == "worker":
        return _check_worker()
    return _check_api()


if __name__ == "__main__":
    sys.exit(main())
