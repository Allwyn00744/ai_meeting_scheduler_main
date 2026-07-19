"""
Focused tests for Redis Caching V1.

Runs without pytest or a live database: app.core.cache is exercised
against an in-memory fake Redis client, and the AvailabilityService
cache-aside path is exercised against SQLAlchemy model instances
built in-memory (Availability/Resource have no relationships, so no
session/DB is required to construct or serialize them).

Run with: python -m unittest tests.test_redis_cache -v
(from the backend/ directory)
"""
import sys
import unittest
from datetime import datetime, time, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core import cache as cache_module  # noqa: E402

# Importing app.db.base (rather than app.models.availability alone)
# registers every mapped model up front, so SQLAlchemy can resolve the
# string-based relationship() references between them (e.g.
# User -> GoogleCredential) before any model is instantiated below.
from app.db.base import Base  # noqa: E402,F401
from app.models.availability import Availability  # noqa: E402
from app.repositories.availability_repository import (  # noqa: E402
    AvailabilityRepository,
)
from app.schemas.availability import AvailabilityCreate  # noqa: E402
from app.services.availability_service import (  # noqa: E402
    AvailabilityService,
)


class FakeRedis:
    """
    In-memory stand-in for redis.Redis implementing only the subset
    of the client API app.core.cache calls (get/setex/delete/
    scan_iter).
    """

    def __init__(self):
        self.store: dict[str, str] = {}
        self.ttls: dict[str, int] = {}

    def get(self, key):
        return self.store.get(key)

    def setex(self, key, ttl, value):
        self.store[key] = value
        self.ttls[key] = ttl

    def delete(self, *keys):
        for key in keys:
            self.store.pop(key, None)
            self.ttls.pop(key, None)

    def scan_iter(self, match=None, count=None):
        prefix = match[:-1] if match and match.endswith("*") else match
        for key in list(self.store.keys()):
            if prefix is None or key.startswith(prefix):
                yield key


class BrokenRedis:
    """Simulates a disconnected/timing-out Redis: every call raises."""

    def get(self, key):
        raise ConnectionError("simulated Redis outage")

    def setex(self, *args, **kwargs):
        raise ConnectionError("simulated Redis outage")

    def delete(self, *args, **kwargs):
        raise ConnectionError("simulated Redis outage")

    def scan_iter(self, *args, **kwargs):
        raise ConnectionError("simulated Redis outage")


def _reset_client_singleton():
    cache_module._client = None
    cache_module._client_init_attempted = False


class FakeCurrentUser:
    def __init__(self, user_id):
        self.id = user_id


class CacheHelpersTestCase(unittest.TestCase):
    """Unit tests for app.core.cache against a fake Redis backend."""

    def setUp(self):
        _reset_client_singleton()
        self.fake = FakeRedis()
        patcher = patch.object(
            cache_module, "_get_client", return_value=self.fake
        )
        self.addCleanup(patcher.stop)
        patcher.start()

    def test_cache_miss_returns_none(self):
        self.assertIsNone(cache_module.cache_get("missing-key"))

    def test_cache_hit_returns_deserialized_value(self):
        cache_module.cache_set("k1", {"a": 1}, 60)
        self.assertEqual(cache_module.cache_get("k1"), {"a": 1})

    def test_write_uses_setex_with_requested_ttl(self):
        with patch.object(
            self.fake, "setex", wraps=self.fake.setex
        ) as spy:
            cache_module.cache_set("k2", [1, 2, 3], 42)

        spy.assert_called_once()
        args, _ = spy.call_args
        self.assertEqual(args[0], "k2")
        self.assertEqual(args[1], 42)
        self.assertEqual(cache_module.cache_get("k2"), [1, 2, 3])

    def test_malformed_cache_data_is_ignored_and_purged(self):
        self.fake.store["bad"] = "{not valid json"

        result = cache_module.cache_get("bad")

        self.assertIsNone(result)
        self.assertNotIn("bad", self.fake.store)

    def test_user_scoped_keys_are_isolated(self):
        key_user_1 = cache_module.meetings_list_key(1, None, 0)
        key_user_2 = cache_module.meetings_list_key(2, None, 0)

        self.assertNotEqual(key_user_1, key_user_2)

        cache_module.cache_set(key_user_1, ["user-1-data"], 60)

        self.assertEqual(
            cache_module.cache_get(key_user_1), ["user-1-data"]
        )
        self.assertIsNone(cache_module.cache_get(key_user_2))

    def test_prefix_invalidation_only_clears_the_scoped_user(self):
        key_a_1 = cache_module.meetings_list_key(1, 10, 0)
        key_a_2 = cache_module.meetings_list_key(1, 20, 0)
        key_b_1 = cache_module.meetings_list_key(2, 10, 0)

        for key in (key_a_1, key_a_2, key_b_1):
            cache_module.cache_set(key, ["data"], 60)

        cache_module.cache_delete_prefix(
            cache_module.meetings_list_prefix(1)
        )

        self.assertIsNone(cache_module.cache_get(key_a_1))
        self.assertIsNone(cache_module.cache_get(key_a_2))
        self.assertEqual(cache_module.cache_get(key_b_1), ["data"])


class RedisUnavailableTestCase(unittest.TestCase):
    """Every cache operation must degrade silently, never raise."""

    def setUp(self):
        _reset_client_singleton()
        patcher = patch.object(
            cache_module, "_get_client", return_value=BrokenRedis()
        )
        self.addCleanup(patcher.stop)
        patcher.start()

    def test_get_falls_back_to_none(self):
        self.assertIsNone(cache_module.cache_get("any"))

    def test_set_does_not_raise(self):
        cache_module.cache_set("any", {"x": 1}, 60)

    def test_delete_does_not_raise(self):
        cache_module.cache_delete("any")

    def test_delete_prefix_does_not_raise(self):
        cache_module.cache_delete_prefix("prefix:")


class RedisNotConfiguredTestCase(unittest.TestCase):
    """Same contract when REDIS_URL is simply unset (no client at all)."""

    def setUp(self):
        _reset_client_singleton()
        patcher = patch.object(
            cache_module, "_get_client", return_value=None
        )
        self.addCleanup(patcher.stop)
        patcher.start()

    def test_all_operations_are_no_ops(self):
        self.assertIsNone(cache_module.cache_get("k"))
        cache_module.cache_set("k", {"a": 1}, 60)
        cache_module.cache_delete("k")
        cache_module.cache_delete_prefix("prefix:")
        self.assertIsNone(cache_module.cache_get("k"))

    def test_availability_service_still_serves_from_postgres(self):
        """
        Without Redis configured, reads must keep working from
        PostgreSQL exactly as before this feature existed.
        """
        user = FakeCurrentUser(user_id=7)
        db = MagicMock()
        row = Availability(
            id=1,
            user_id=7,
            day_of_week="Monday",
            start_time=time(9, 0),
            end_time=time(17, 0),
            is_available=True,
            created_at=datetime.now(timezone.utc),
        )

        with patch.object(
            AvailabilityRepository, "get_by_user", return_value=[row]
        ) as get_by_user:
            result = AvailabilityService.get_my_availability(db, user)

        get_by_user.assert_called_once()
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["user_id"], 7)


class AvailabilityServiceCacheAsideTestCase(unittest.TestCase):
    """
    End-to-end cache-aside behavior at the service layer: miss reads
    Postgres and populates the cache, a hit skips Postgres entirely,
    and a mutation invalidates the cache so the next read goes back
    to Postgres. PostgreSQL is the only source of truth throughout -
    the cache never diverges from what the repository returns.
    """

    def setUp(self):
        _reset_client_singleton()
        self.fake = FakeRedis()
        patcher = patch.object(
            cache_module, "_get_client", return_value=self.fake
        )
        self.addCleanup(patcher.stop)
        patcher.start()

    @staticmethod
    def _row(row_id, user_id, day="Monday"):
        return Availability(
            id=row_id,
            user_id=user_id,
            day_of_week=day,
            start_time=time(9, 0),
            end_time=time(17, 0),
            is_available=True,
            created_at=datetime.now(timezone.utc),
        )

    def test_cache_miss_reads_postgres_and_populates_cache(self):
        user = FakeCurrentUser(user_id=1)
        db = MagicMock()

        with patch.object(
            AvailabilityRepository,
            "get_by_user",
            return_value=[self._row(1, 1)],
        ) as get_by_user:
            result = AvailabilityService.get_my_availability(db, user)

        get_by_user.assert_called_once()
        self.assertEqual(len(result), 1)
        self.assertIsNotNone(
            cache_module.cache_get(
                cache_module.availability_list_key(1)
            )
        )

    def test_cache_hit_never_touches_postgres(self):
        user = FakeCurrentUser(user_id=2)
        db = MagicMock()
        cache_module.cache_set(
            cache_module.availability_list_key(2),
            [{"id": 9, "user_id": 2}],
            60,
        )

        with patch.object(
            AvailabilityRepository,
            "get_by_user",
            side_effect=AssertionError(
                "must not query Postgres on a cache hit"
            ),
        ):
            result = AvailabilityService.get_my_availability(db, user)

        self.assertEqual(result, [{"id": 9, "user_id": 2}])

    def test_mutation_invalidates_cache_so_next_read_is_fresh(self):
        user = FakeCurrentUser(user_id=3)
        db = MagicMock()

        with patch.object(
            AvailabilityRepository,
            "get_by_user",
            return_value=[self._row(1, 3)],
        ):
            AvailabilityService.get_my_availability(db, user)

        self.assertIsNotNone(
            cache_module.cache_get(
                cache_module.availability_list_key(3)
            )
        )

        payload = AvailabilityCreate(
            day_of_week="Tuesday",
            start_time=time(9, 0),
            end_time=time(10, 0),
            is_available=True,
        )

        with patch.object(
            AvailabilityRepository,
            "create",
            return_value=self._row(2, 3, day="Tuesday"),
        ):
            AvailabilityService.create_availability(db, payload, user)

        self.assertIsNone(
            cache_module.cache_get(
                cache_module.availability_list_key(3)
            )
        )

        with patch.object(
            AvailabilityRepository,
            "get_by_user",
            return_value=[self._row(1, 3), self._row(2, 3, "Tuesday")],
        ) as get_by_user_after_mutation:
            result = AvailabilityService.get_my_availability(db, user)

        get_by_user_after_mutation.assert_called_once()
        self.assertEqual(len(result), 2)

    def test_different_users_never_see_each_others_cached_data(self):
        user_a = FakeCurrentUser(user_id=10)
        user_b = FakeCurrentUser(user_id=11)
        db = MagicMock()

        with patch.object(
            AvailabilityRepository,
            "get_by_user",
            return_value=[self._row(1, 10)],
        ):
            AvailabilityService.get_my_availability(db, user_a)

        # user_b has no cache entry of its own, so a correct
        # implementation must miss and query Postgres rather than
        # somehow returning user_a's cached rows.
        with patch.object(
            AvailabilityRepository,
            "get_by_user",
            return_value=[],
        ) as get_by_user_b:
            result_b = AvailabilityService.get_my_availability(
                db, user_b
            )

        get_by_user_b.assert_called_once()
        self.assertEqual(result_b, [])


if __name__ == "__main__":
    unittest.main()
