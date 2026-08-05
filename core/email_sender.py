"""SMTP経由のメール送信（パスワード再設定通知に使用）。

Gmailの「アプリパスワード」や、SendGrid/Mailgun/Resend等のSMTPリレーなど、
利用者自身のSMTP資格情報を .env で設定して使う想定（Stripeキーと同じ方針）。
"""

from __future__ import annotations

import os
import smtplib
from email.mime.text import MIMEText


class EmailNotConfiguredError(RuntimeError):
    pass


def _require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise EmailNotConfiguredError(
            f"{name} が設定されていません。.env.example を参考に .env を用意してください。"
        )
    return value


def send_email(to_email: str, subject: str, body: str) -> None:
    host = _require_env("SMTP_HOST")
    port = int(os.environ.get("SMTP_PORT", "587"))
    user = _require_env("SMTP_USER")
    password = _require_env("SMTP_PASSWORD")
    from_email = os.environ.get("SMTP_FROM_EMAIL", user)

    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = from_email
    msg["To"] = to_email

    with smtplib.SMTP(host, port, timeout=10) as server:
        server.starttls()
        server.login(user, password)
        server.sendmail(from_email, [to_email], msg.as_string())
