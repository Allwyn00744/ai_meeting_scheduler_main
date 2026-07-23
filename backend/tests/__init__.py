"""
Safety net, applied once when the `tests` package is first imported
(before any individual test module loads).

backend/.env holds real Gmail SMTP credentials for local development,
and MeetingNotificationService.notify_meeting_created now always
includes the meeting owner as a recipient (previously, a meeting with
no participants/external guests had nobody to email at all, so this
path was never exercised). Without this guard, every test in the
suite that creates a meeting via POST /meetings and doesn't explicitly
mock EmailService/smtplib would open a real outbound SMTP connection
and send a real email through that Gmail account on every test run.

Patches smtplib.SMTP/SMTP_SSL to a no-op stand-in that never touches
the network. A test that wants to assert on real smtplib call shape
can still do `with patch("smtplib.SMTP", ...)` inside its own test
method - that overrides this default for the duration of the `with`
block and is restored afterward, exactly like patching any other
value.
"""
import smtplib


class _NoNetworkSMTP:
    """Stands in for smtplib.SMTP/SMTP_SSL: accepts the same calls,
    touches no socket, and never suppresses exceptions raised inside
    its `with` block."""

    def __init__(self, *args, **kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False

    def login(self, *args, **kwargs):
        pass

    def starttls(self, *args, **kwargs):
        pass

    def send_message(self, *args, **kwargs):
        pass

    def quit(self):
        pass


smtplib.SMTP = _NoNetworkSMTP
smtplib.SMTP_SSL = _NoNetworkSMTP
