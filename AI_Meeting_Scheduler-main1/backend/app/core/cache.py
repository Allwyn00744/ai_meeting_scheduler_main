"""
Centralized Redis cache client and cache-aside helpers.

Redis is optional infrastructure: every function here is best-effort
and swallows all Redis/serialization failures internally, falling
back to "no cache" (returns None / no-ops) rather than raising. Callers
never need their own try/except around these calls, and a Redis outage
never turns an otherwise-valid request into a 500.

Do not create Redis connections directly in routes/services - always
go through this module so timeout/serialization/failure handling stays
in one place.
"""
from __future__ import annotations

import json
import logging
from typing import Any

import redis

from app.core.config import settings

logger = logging.getLogger(__name__)

# Versioned so a future incompatible change to what we store under a
# given key can be rolled out without colliding with old entries -
# they simply age out under their old TTL and are never read again.
CACHE_NAMESPACE = "ai-meeting-scheduler:v1"

MEETINGS_LIST_TTL_SECONDS = 60
RESOURCES_TTL_SECONDS = 300
AVAILABILITY_TTL_SECONDS = 300
KPI_TTL_SECONDS = 60

_client: redis.Redis | None = None
_client_init_attempted = False


def _get_client() -> redis.Redis | None:
    """
    Lazily constructs the shared Redis client on first use. Returns
    None (never raises) when Redis is not configured or the client
    could not be constructed, so every call site can treat "no client"
    as an ordinary, expected outcome.
    """
    global _client, _client_init_attempted

    if not settings.REDIS_URL:
        return None

    if _client is not None or _client_init_attempted:
        return _client

    _client_init_attempted = True

    try:
        _client = redis.Redis.from_url(
            settings.REDIS_URL,
            socket_timeout=settings.REDIS_SOCKET_TIMEOUT_SECONDS,
            socket_connect_timeout=settings.REDIS_CONNECT_TIMEOUT_SECONDS,
            decode_responses=True,
            # Pinned to RESP2 for broad compatibility: modern
            # redis-py negotiates RESP3 via a HELLO handshake by
            # default, which older/alternate Redis-protocol servers
            # (e.g. Redis < 6, some managed/Windows builds) reject
            # outright, breaking every connection before a single
            # command runs.
            protocol=2,
        )
    except Exception:
        logger.warning(
            "Failed to construct Redis client from REDIS_URL; "
            "caching disabled for this process.",
            exc_info=True,
        )
        _client = None

    return _client


def cache_get(key: str) -> Any | None:
    """
    Cache-aside read. Returns the deserialized value on a valid hit,
    or None on a miss, malformed entry, or any Redis failure - all of
    which the caller should treat identically (query PostgreSQL).
    """
    client = _get_client()

    if client is None:
        return None

    try:
        raw = client.get(key)
    except Exception:
        logger.warning(
            "Redis GET failed; falling back to source of truth. "
            "key=%s",
            key,
            exc_info=True,
        )
        return None

    if raw is None:
        return None

    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        logger.warning(
            "Malformed cached JSON; discarding entry. key=%s",
            key,
        )
        cache_delete(key)
        return None


def cache_set(key: str, value: Any, ttl_seconds: int) -> None:
    """Best-effort cache write. Never raises."""
    client = _get_client()

    if client is None:
        return

    try:
        payload = json.dumps(value, default=str)
    except (TypeError, ValueError):
        logger.warning(
            "Value is not JSON-serializable; skipping cache write. "
            "key=%s",
            key,
        )
        return

    try:
        client.setex(key, ttl_seconds, payload)
    except Exception:
        logger.warning(
            "Redis SET failed; continuing without cache. key=%s",
            key,
            exc_info=True,
        )


def cache_delete(*keys: str) -> None:
    """Best-effort deletion of one or more explicit keys."""
    if not keys:
        return

    client = _get_client()

    if client is None:
        return

    try:
        client.delete(*keys)
    except Exception:
        logger.warning(
            "Redis DELETE failed. keys=%s",
            keys,
            exc_info=True,
        )


def cache_delete_prefix(prefix: str) -> None:
    """
    Best-effort deletion of every key under `prefix`, via SCAN rather
    than KEYS so it never blocks the Redis event loop. Used only for
    key groups whose exact members aren't known to the caller (e.g. a
    list cached under several limit/offset variants).
    """
    client = _get_client()

    if client is None:
        return

    try:
        keys = list(client.scan_iter(match=f"{prefix}*", count=200))

        if keys:
            client.delete(*keys)
    except Exception:
        logger.warning(
            "Redis SCAN/DELETE failed. prefix=%s",
            prefix,
            exc_info=True,
        )


def meetings_list_prefix(user_id: int) -> str:
    return f"{CACHE_NAMESPACE}:meetings:user:{user_id}:list:"


def meetings_list_key(
    user_id: int,
    limit: int | None,
    offset: int,
) -> str:
    return f"{meetings_list_prefix(user_id)}{limit}:{offset}"


def resources_list_key() -> str:
    return f"{CACHE_NAMESPACE}:resources:list"


def resource_detail_key(resource_id: int) -> str:
    return f"{CACHE_NAMESPACE}:resources:detail:{resource_id}"


def availability_list_key(user_id: int) -> str:
    return f"{CACHE_NAMESPACE}:availability:user:{user_id}:list"


def kpis_key(user_id: int) -> str:
    return f"{CACHE_NAMESPACE}:analytics:user:{user_id}:kpis"
