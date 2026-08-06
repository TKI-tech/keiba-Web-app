"""Resend(HTTPS API)経由のメール送信（確認メール・パスワード再設定通知に使用）。

以前はSMTP(smtplib)で実装していたが、Renderのようなホスティングはスパム対策として
コンテナからの外向きSMTP通信(ポート587/465等)をネットワークレベルでブロックしている
ことが多く、実際にこのアプリもRender上でSMTP接続がタイムアウトすることを確認した
(IPv4/IPv6の経路の問題ではなく、ポート自体が塞がれている)。HTTPS(443番)経由の
メール送信APIに切り替えることで、この種のポート制限を回避している。

Resendは無料枠(月3,000通/日100通)があり、独自ドメインが無くても
onboarding@resend.dev という送信元ですぐに送信できる。

User-Agentを明示的に指定しているのは、urllibのデフォルトUser-Agent
("Python-urllib/3.x")がResendの手前にあるCloudflareのボット対策(Error 1010:
Bad Bot)に自動プログラムの典型的な特徴として検知され、Resendまでリクエストが
届く前に拒否されることを実際に確認したため。
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

_API_URL = "https://api.resend.com/emails"
_DEFAULT_FROM_EMAIL = "onboarding@resend.dev"


class EmailNotConfiguredError(RuntimeError):
    pass


class EmailSendError(RuntimeError):
    """設定は揃っているが、Resend側がリクエストを拒否した場合(ドメイン未認証で
    自分以外の宛先に送ろうとした等)。呼び出し元でユーザー向けの案内に変換しやすい
    よう、EmailNotConfiguredErrorとは別の型にしてある。
    """

    pass


def _require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise EmailNotConfiguredError(
            f"{name} が設定されていません。.env.example を参考に .env を用意してください。"
        )
    return value


def send_email(to_email: str, subject: str, body: str) -> None:
    api_key = _require_env("RESEND_API_KEY")
    from_email = os.environ.get("RESEND_FROM_EMAIL", _DEFAULT_FROM_EMAIL)

    payload = json.dumps(
        {
            "from": from_email,
            "to": [to_email],
            "subject": subject,
            "text": body,
        }
    ).encode("utf-8")

    request = urllib.request.Request(
        _API_URL,
        data=payload,
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": "keiba-web-app-mailer/1.0",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            if response.status >= 300:
                body_text = response.read().decode("utf-8", errors="replace")
                raise EmailSendError(f"Resendでのメール送信に失敗しました(status={response.status}): {body_text}")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise EmailSendError(f"Resendでのメール送信に失敗しました(status={exc.code}): {detail}") from exc
