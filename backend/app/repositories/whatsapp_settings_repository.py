from sqlalchemy.orm import Session

from app.models.whatsapp_settings import WhatsAppSettings


class WhatsAppSettingsRepository:

    @staticmethod
    def get_by_user_id(db: Session, user_id: int):
        return (
            db.query(WhatsAppSettings)
            .filter(WhatsAppSettings.user_id == user_id)
            .first()
        )

    @staticmethod
    def create(db: Session, settings_row: WhatsAppSettings):
        db.add(settings_row)
        db.commit()
        db.refresh(settings_row)
        return settings_row

    @staticmethod
    def update(db: Session, settings_row: WhatsAppSettings):
        db.commit()
        db.refresh(settings_row)
        return settings_row
