import logging

from fastapi import Request
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError


logger = logging.getLogger(__name__)


async def global_exception_handler(
    request: Request,
    exc: Exception,
):
    logger.exception(
        "Unhandled exception. method=%s path=%s",
        request.method,
        request.url.path,
        exc_info=exc,
    )

    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "message": "Internal server error",
            "status": 500,
        },
    )


async def integrity_error_handler(
    request: Request,
    exc: IntegrityError,
):
    """
    Safety net for any database constraint violation that a service
    did not already translate into a specific HTTPException (services
    are expected to catch and handle the cases they know about, e.g.
    deleting a user who still owns meetings). This never leaks raw
    SQL or constraint details to the client.
    """
    logger.warning(
        "Unhandled IntegrityError. method=%s path=%s",
        request.method,
        request.url.path,
        exc_info=exc,
    )

    return JSONResponse(
        status_code=409,
        content={
            "success": False,
            "message": (
                "The request could not be completed because it "
                "conflicts with related data."
            ),
            "status": 409,
        },
    )
