"""
Rate limiting (slowapi/limits), applied only to the brute-force-prone
auth endpoints (login/register/Google login) - see app/api/auth_routes.py.

Mirrors app/core/cache.py's "Redis is optional infrastructure"
philosophy: when REDIS_URL is configured, limits are shared across
every worker process via Redis; when it isn't, slowapi falls back to
an in-memory store scoped to a single process. Either way this must
never prevent the app from starting - if Redis is unreachable at
import time, slowapi's own storage layer handles that internally
(it lazily connects), so no extra guarding is needed here.
"""
import sys

from slowapi import Limiter
from slowapi.util import get_remote_address

from app.core.config import settings

_storage_uri = settings.REDIS_URL if settings.REDIS_URL else None

# slowapi's in-memory store is a single counter per client key,
# process-wide - every test file's TestClient shares one fake client
# address, so without this the unittest suite (25+ files, each
# registering/logging in its own users in setUp) would trip the same
# shared bucket and start failing unrelated tests with 429s well
# before any real limit-behavior test runs. Disabled by default
# whenever the process was started under `python -m unittest`;
# tests/test_rate_limiting.py explicitly re-enables it for the
# duration of its own assertions. Never true for a real `uvicorn`
# process, which never imports the stdlib `unittest` module.
_running_under_unittest = "unittest" in sys.modules

limiter = Limiter(
    key_func=get_remote_address,
    storage_uri=_storage_uri,
    enabled=not _running_under_unittest,
)
