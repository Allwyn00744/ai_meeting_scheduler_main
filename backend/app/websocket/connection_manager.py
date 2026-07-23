"""
In-memory WebSocket connection registry, keyed by user_id (mirrors the
multi-subscription-per-user shape already used for Push
Notifications - a user can have the app open in several tabs/devices
at once).

FastAPI runs every plain `def` route (which is all of them in this
codebase - see MeetingService) in a worker thread via
starlette.concurrency.run_in_threadpool, not on the event loop thread
itself. broadcast_to_user_sync exists specifically to bridge that: it
schedules the async broadcast onto the event loop from whatever
worker thread the calling sync service method happens to be running
on, via asyncio.run_coroutine_threadsafe - the standard primitive for
exactly this cross-thread scenario. The loop reference is captured
once, at startup, in app/main.py's lifespan (which runs on the loop
itself).
"""
import asyncio
import logging
from collections import defaultdict

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:

    def __init__(self) -> None:
        self._connections: dict[int, list[WebSocket]] = defaultdict(list)
        self._loop: asyncio.AbstractEventLoop | None = None

    def set_event_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    async def connect(self, user_id: int, websocket: WebSocket) -> None:
        await websocket.accept()
        self._connections[user_id].append(websocket)

    def disconnect(self, user_id: int, websocket: WebSocket) -> None:
        connections = self._connections.get(user_id)
        if not connections:
            return
        if websocket in connections:
            connections.remove(websocket)
        if not connections:
            self._connections.pop(user_id, None)

    async def broadcast_to_user(self, user_id: int, message: dict) -> None:
        """Best-effort - a dead/broken connection is dropped, never raised."""
        connections = list(self._connections.get(user_id, ()))

        for websocket in connections:
            try:
                await websocket.send_json(message)
            except Exception:
                logger.info(
                    "Dropping a dead WebSocket connection. user_id=%s",
                    user_id,
                )
                self.disconnect(user_id, websocket)

    def broadcast_to_user_sync(self, user_id: int, message: dict) -> None:
        """
        Sync-callable entry point for MeetingService's plain `def`
        methods. Never raises - a broadcast failure must never affect
        the HTTP response, same as the cache-invalidation and
        notification calls it sits alongside at each call site.
        """
        if self._loop is None:
            return

        try:
            asyncio.run_coroutine_threadsafe(
                self.broadcast_to_user(user_id, message),
                self._loop,
            )
        except Exception:
            logger.warning(
                "Failed to schedule WebSocket broadcast. user_id=%s",
                user_id,
            )


connection_manager = ConnectionManager()
