from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.cache import (
    RESOURCES_TTL_SECONDS,
    cache_delete,
    cache_get,
    cache_set,
    resource_detail_key,
    resources_list_key,
)
from app.models.resource import Resource
from app.models.user import User
from app.repositories.resource_repository import ResourceRepository
from app.schemas.resource import (
    ResourceCreate,
    ResourceResponse,
    ResourceUpdate,
)


class ResourceService:

    @staticmethod
    def create_resource(
        db: Session,
        resource: ResourceCreate,
        current_user: User,
    ):
        db_resource = Resource(
            name=resource.name,
            resource_type=resource.resource_type,
            description=resource.description,
            location=resource.location,
            created_by_id=current_user.id,
        )

        db_resource = ResourceRepository.create(db, db_resource)

        cache_delete(resources_list_key())

        return db_resource

    @staticmethod
    def list_active_resources(db: Session):
        cached = cache_get(resources_list_key())

        if cached is not None:
            return cached

        resources = ResourceRepository.get_active(db)

        serialized = [
            ResourceResponse.model_validate(resource).model_dump(
                mode="json"
            )
            for resource in resources
        ]

        if serialized:
            cache_set(
                resources_list_key(),
                serialized,
                RESOURCES_TTL_SECONDS,
            )

        return serialized

    @staticmethod
    def get_resource(
        db: Session,
        resource_id: int,
    ):
        cache_key = resource_detail_key(resource_id)
        cached = cache_get(cache_key)

        if cached is not None:
            return cached

        resource = ResourceRepository.get_by_id(db, resource_id)

        if resource is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Resource not found",
            )

        serialized = ResourceResponse.model_validate(
            resource
        ).model_dump(mode="json")

        cache_set(cache_key, serialized, RESOURCES_TTL_SECONDS)

        return serialized

    @staticmethod
    def update_resource(
        db: Session,
        resource_id: int,
        resource_data: ResourceUpdate,
        current_user: User,
    ):
        resource = ResourceRepository.get_by_id(db, resource_id)

        if resource is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Resource not found",
            )

        if resource.created_by_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only the resource creator can update this resource.",
            )

        update_data = resource_data.model_dump(exclude_unset=True)

        for key, value in update_data.items():
            setattr(resource, key, value)

        resource = ResourceRepository.update(db, resource)

        cache_delete(
            resources_list_key(),
            resource_detail_key(resource_id),
        )

        return resource
