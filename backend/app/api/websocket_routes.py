import logging

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session

from app.auth.jwt_handler import verify_access_token
from app.db.database import get_db
from app.models.user import User
from app.websocket.connection_manager import connection_manager

logger = logging.getLogger(__name__)

router = APIRouter(tags=["WebSocket"])


def _authenticate_ws_token(token: str | None, db: Session) -> User | None:
    """
    A WebSocket handshake can't carry a normal Authorization header
    the way get_current_user (app/auth/dependencies.py) expects, so
    the token travels as a query param instead - reuses the same
    verify_access_token this whole app already relies on, just with a
    different transport. Takes db via the same Depends(get_db) every
    other route uses (rather than opening an independent SessionLocal()
    like the best-effort logging services do) so it participates in
    the standard per-request session lifecycle and honors the get_db
    override tests already rely on.
    """
    if not token:
        return None

    payload = verify_access_token(token)
    if payload is None:
        return None

    return (
        db.query(User)
        .filter(User.id == payload["user_id"])
        .first()
    )


@router.websocket("/ws")
async def meetings_websocket(
    websocket: WebSocket,
    token: str | None = Query(default=None),
    db: Session = Depends(get_db),
):
    """
    Pushes meeting_created/meeting_updated/meeting_cancelled events to
    the owning user's connected clients (see the broadcast_to_user_sync
    calls in MeetingService), so pages like Analytics/Dashboard can
    invalidate their React Query caches instantly instead of waiting
    for their periodic refetch.
    """
    user = _authenticate_ws_token(token, db)

    if user is None:
        await websocket.close(code=4401)
        return

    await connection_manager.connect(user.id, websocket)

    try:
        while True:
            # This app never expects the client to send anything
            # meaningful over this socket - it exists purely to
            # detect disconnection. Any inbound message is discarded.
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        connection_manager.disconnect(user.id, websocket)
