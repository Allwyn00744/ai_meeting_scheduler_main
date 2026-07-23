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
    def update(db: Session, resource: Resource):
        db.commit()
        db.refresh(resource)
        return resource
