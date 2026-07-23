from sqlalchemy.orm import Session

from app.models.resource import Resource


class ResourceRepository:

    @staticmethod
    def create(db: Session, resource: Resource):
        db.add(resource)
        db.commit()
        db.refresh(resource)
        return resource

    @staticmethod
    def get_by_id(db: Session, resource_id: int):
        return (
            db.query(Resource)
            .filter(Resource.id == resource_id)
            .first()
        )

    @staticmethod
    def get_active(db: Session):
        return (
            db.query(Resource)
            .filter(Resource.is_active == True)
            .order_by(Resource.name)
            .all()
        )

    @staticmethod
    def get_by_ids(db: Session, resource_ids: list[int]) -> dict[int, Resource]:
        """Bulk lookup for Resource Analytics - avoids one query per
        distinct resource_id when summarizing bookings across many
        resources."""
        if not resource_ids:
            return {}

        rows = (
            db.query(Resource)
            .filter(Resource.id.in_(resource_ids))
            .all()
        )
        return {resource.id: resource for resource in rows}

    @staticmethod
    def update(db: Session, resource: Resource):
        db.commit()
        db.refresh(resource)
        return resource
