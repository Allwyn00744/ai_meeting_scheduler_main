from sqlalchemy.orm import Session

from app.models.push_subscription import PushSubscription


class PushSubscriptionRepository:

    @staticmethod
    def get_by_user_id(db: Session, user_id: int):
        return (
            db.query(PushSubscription)
            .filter(PushSubscription.user_id == user_id)
            .all()
        )

    @staticmethod
    def get_enabled_by_user_id(db: Session, user_id: int):
        return (
            db.query(PushSubscription)
            .filter(
                PushSubscription.user_id == user_id,
                PushSubscription.is_enabled.is_(True),
            )
            .all()
        )

    @staticmethod
    def get_by_endpoint(db: Session, user_id: int, endpoint: str):
        return (
            db.query(PushSubscription)
            .filter(
                PushSubscription.user_id == user_id,
                PushSubscription.endpoint == endpoint,
            )
            .first()
        )

    @staticmethod
    def create(db: Session, subscription_row: PushSubscription):
        db.add(subscription_row)
        db.commit()
        db.refresh(subscription_row)
        return subscription_row

    @staticmethod
    def update(db: Session, subscription_row: PushSubscription):
        db.commit()
        db.refresh(subscription_row)
        return subscription_row

    @staticmethod
    def delete(db: Session, subscription_row: PushSubscription):
        db.delete(subscription_row)
        db.commit()
