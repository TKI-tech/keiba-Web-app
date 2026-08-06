"""SMTP経由のメール送信（パスワード再設定通知に使用）。

Gmailの「アプリパスワード」や、SendGrid/Mailgun/Resend等のSMTPリレーなど、
利用者自身のSMTP資格情報を .env で設定して使う想定（Stripeキーと同じ方針）。
"""

from __future__ import annotations

import contextlib
import os
import smtplib
import socket
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


@contextlib.contextmanager
def _force_ipv4_dns():
    """RenderのようなホスティングではコンテナにIPv6アドレスが割り当てられていても
    実際にはIPv6の経路がなく、smtp.gmail.com 等IPv6も公開しているホストへの接続が
    "Network is unreachable" で失敗することがある。この間だけ名前解決をIPv4限定にし、
    smtplib が意図せずIPv6アドレスへ接続を試みないようにする(呼び出し元のホスト名は
    そのまま使うため、TLSのホスト名検証には影響しない)。
    """
    original_getaddrinfo = socket.getaddrinfo

    def ipv4_only_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
        return original_getaddrinfo(host, port, socket.AF_INET, type, proto, flags)

    socket.getaddrinfo = ipv4_only_getaddrinfo
    try:
        yield
    finally:
        socket.getaddrinfo = original_getaddrinfo


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

    with _force_ipv4_dns(), smtplib.SMTP(host, port, timeout=10) as server:
        server.starttls()
        server.login(user, password)
        server.sendmail(from_email, [to_email], msg.as_string())
