class ExternalGuestService:
    """
    Resolves the final set of external guest emails for a meeting,
    given emails that have already been syntactically validated
    (Pydantic EmailStr) and normalized/deduplicated
    (normalize_external_guest_emails).

    This is the identity-collision layer: it silently excludes emails
    that collide with the meeting owner or with a registered
    participant of *this same request*. It never queries the users
    table by arbitrary external email - only the owner's own email
    and the emails of the explicitly supplied participant_ids are
    used for comparison, so this endpoint cannot be used to probe
    whether an arbitrary address has a registered account.
    """

    @staticmethod
    def resolve_guests(
        normalized_emails: list[str],
        owner_email: str,
        participant_emails: list[str],
    ) -> list[str]:
        owner_email = owner_email.strip().lower()

        participant_email_set = {
            email.strip().lower() for email in participant_emails
        }

        return [
            email
            for email in normalized_emails
            if email != owner_email
            and email not in participant_email_set
        ]
