from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.db.database import get_db
from app.models.user import User
from app.schemas.resource import (
    ResourceCreate,
    ResourceUpdate,
    ResourceResponse,
)
from app.services.resource_service import ResourceService

router = APIRouter(
    prefix="/resources",
    tags=["Resources"],
)


@router.post(
    "/",
    response_model=ResourceResponse,
    status_code=201,
)
def create_resource(
    resource: ResourceCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return ResourceService.create_resource(
        db,
        resource,
        current_user,
    )


@router.get(
    "/",
    response_model=list[ResourceResponse],
)
def list_active_resources(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return ResourceService.list_active_resources(db)


@router.get(
    "/{resource_id}",
    response_model=ResourceResponse,
)
def get_resource(
    resource_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return ResourceService.get_resource(
        db,
        resource_id,
    )


@router.put(
    "/{resource_id}",
    response_model=ResourceResponse,
)
def update_resource(
    resource_id: int,
    resource: ResourceUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return ResourceService.update_resource(
        db,
        resource_id,
        resource,
        current_user,
    )
