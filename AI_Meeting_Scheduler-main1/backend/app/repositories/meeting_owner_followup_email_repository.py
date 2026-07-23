from sqlalchemy.orm import Session

from app.models.meeting_owner_followup_email import MeetingOwnerFollowUpEmail


class MeetingOwnerFollowUpEmailRepository:
    """
    Write methods here never call db.commit() or db.rollback() - the
    caller (MeetingFollowUpEmailService) owns the transaction boundary.
    """

    @staticmethod
    def get_by_meeting_note_id(db: Session, meeting_note_id: int):
        return (
            db.query(MeetingOwnerFollowUpEmail)
            .filter(
                MeetingOwnerFollowUpEmail.meeting_note_id == meeting_note_id
            )
            .first()
        )

    @staticmethod
    def insert(
        db: Session,
        meeting_note_id: int,
        subject: str,
        body: str,
    ) -> MeetingOwnerFollowUpEmail:
        email = MeetingOwnerFollowUpEmail(
            meeting_note_id=meeting_note_id,
            subject=subject,
            body=body,
        )
        db.add(email)
        db.flush()
        return email

    @staticmethod
    def update_email(
        db: Session,
        email: MeetingOwnerFollowUpEmail,
        subject: str,
        body: str,
    ) -> MeetingOwnerFollowUpEmail:
        email.subject = subject
        email.body = body
        db.flush()
        return email
