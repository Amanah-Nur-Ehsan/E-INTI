import smtplib
from email.message import EmailMessage
from functools import lru_cache
from typing import Protocol

from app.core.config import Settings, get_settings


class EmailSender(Protocol):
    """Sends one email. Synchronous (SMTP is blocking); callers wrap it in
    asyncio.to_thread so the event loop stays free."""

    def send(self, to: str, subject: str, text: str, html: str) -> None: ...


class SmtpEmailSender:
    def __init__(self, settings: Settings):
        self._settings = settings

    def send(self, to: str, subject: str, text: str, html: str) -> None:
        s = self._settings
        message = EmailMessage()
        message["From"] = s.smtp_from
        message["To"] = to
        message["Subject"] = subject
        message.set_content(text)
        message.add_alternative(html, subtype="html")

        with smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=30) as server:
            if s.smtp_use_tls:
                server.starttls()
            if s.smtp_username:
                server.login(s.smtp_username, s.smtp_password)
            server.send_message(message)


@lru_cache
def get_email_sender() -> EmailSender:
    return SmtpEmailSender(get_settings())
