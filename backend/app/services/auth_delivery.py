"""Optional SMTP only. Codes exist in memory until delivery, never in an outbox/log."""
from email.message import EmailMessage
import smtplib
import socket
import ssl

from app.core.config import settings
from app.core.locality import classify_host


def send_code(address, code, purpose):
    host = settings.smtp_host
    addresses = socket.getaddrinfo(host, settings.smtp_port, type=socket.SOCK_STREAM)
    if not addresses:
        raise ValueError("SMTP unavailable")
    if settings.deployment_mode == "confidential" and any(classify_host(row[4][0]) not in {"local", "private"} for row in addresses):
        raise ValueError("SMTP destination is not private")
    if settings.smtp_tls == "none" and not (settings.deployment_mode == "development" and
                                             all(classify_host(row[4][0]) == "local" for row in addresses)):
        raise ValueError("SMTP requires TLS")
    destination = addresses[0][4][0]

    class PinnedSMTP(smtplib.SMTP):
        def _get_socket(self, host, port, timeout):
            return socket.create_connection((destination, port), timeout)

    class PinnedSSL(smtplib.SMTP_SSL):
        def _get_socket(self, host, port, timeout):
            raw = socket.create_connection((destination, port), timeout)
            try:
                return self._context.wrap_socket(raw, server_hostname=host)
            except Exception:
                raw.close()
                raise

    message = EmailMessage()
    message["From"], message["To"] = settings.smtp_sender, address
    message["Subject"] = "Workbench verification code"
    message.set_content(f"Your Workbench {'password recovery' if purpose == 'password' else 'email verification'} code is {code}.\n"
                        "It expires in 10 minutes and can be used once. If you did not request it, ignore this message.")
    client = PinnedSSL if settings.smtp_tls == "tls" else PinnedSMTP
    kwargs = {"context": ssl.create_default_context()} if settings.smtp_tls == "tls" else {}
    with client(host, settings.smtp_port, timeout=10, **kwargs) as connection:
        if settings.smtp_tls == "starttls":
            connection.starttls(context=ssl.create_default_context())
        if settings.smtp_username:
            connection.login(settings.smtp_username, settings.smtp_password)
        connection.send_message(message)


def deliver(address, challenge_id, code, purpose):
    try:
        send_code(address, code, purpose)
    except Exception:
        # Background failure cannot reveal account existence or include provider exception text.
        from app.db.session import SessionLocal
        from app.db.models import AuthChallenge
        from app.services.accounts import event, now
        try:
            with SessionLocal() as db:
                challenge = db.get(AuthChallenge, challenge_id)
                if challenge and not challenge.consumed_at:
                    challenge.consumed_at = now()
                event(db, "AUTH_DELIVERY_FAILED", challenge_id=challenge_id)
                db.commit()
        except Exception:
            pass  # The short-lived challenge still expires if diagnostics storage is down.
