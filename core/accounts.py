"""アカウント登録・ログイン・パスワード再設定のビジネスロジック。

core/members_db.py は永続化のみ、core/auth.py はハッシュ化のみを担当し、
このモジュールがそれらを組み合わせて「登録」「ログイン」「パスワード再設定」という
ユースケースを提供する。
"""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone

from core import members_db
from core.app_url import base_url as app_base_url
from core.auth import hash_password, verify_password
from core.email_sender import send_email

RESET_TOKEN_TTL = timedelta(hours=1)
MIN_PASSWORD_LENGTH = 8


class AccountError(RuntimeError):
    pass


class EmailAlreadyRegisteredError(AccountError):
    pass


class InvalidCredentialsError(AccountError):
    pass


class InvalidResetTokenError(AccountError):
    pass


class WeakPasswordError(AccountError):
    pass


def _validate_password(password: str) -> None:
    if len(password) < MIN_PASSWORD_LENGTH:
        raise WeakPasswordError(f"パスワードは{MIN_PASSWORD_LENGTH}文字以上にしてください。")


def register(email: str, password: str) -> None:
    _validate_password(password)
    existing = members_db.get_member(email)
    if existing and existing.has_account:
        raise EmailAlreadyRegisteredError("このメールアドレスは既に登録されています。ログインしてください。")
    members_db.set_password_hash(email, hash_password(password))


def login(email: str, password: str) -> None:
    member = members_db.get_member(email)
    if not member or not member.has_account or not verify_password(password, member.password_hash):
        raise InvalidCredentialsError("メールアドレスまたはパスワードが正しくありません。")


def request_password_reset(email: str) -> None:
    """該当メールアドレスが未登録でも例外を出さない(登録有無を外部に漏らさないため)。"""
    member = members_db.get_member(email)
    if not member or not member.has_account:
        return

    token = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + RESET_TOKEN_TTL
    members_db.set_reset_token(email, token, expires_at.isoformat())

    reset_url = f"{app_base_url()}/app/?reset_token={token}"
    body = (
        "競馬予想Webアプリのパスワード再設定を受け付けました。\n\n"
        f"以下のリンクから新しいパスワードを設定してください(1時間有効です)。\n{reset_url}\n\n"
        "心当たりがない場合はこのメールを無視してください。"
    )
    send_email(email, "【競馬予想Webアプリ】パスワード再設定のご案内", body)


def reset_password(token: str, new_password: str) -> str:
    """トークンを検証してパスワードを更新し、更新したメールアドレスを返す。"""
    member = members_db.get_member_by_reset_token(token)
    if member is None or not member.reset_token_expires:
        raise InvalidResetTokenError("リンクが無効か、有効期限が切れています。")
    if datetime.fromisoformat(member.reset_token_expires) < datetime.now(timezone.utc):
        raise InvalidResetTokenError("リンクが無効か、有効期限が切れています。")

    _validate_password(new_password)
    members_db.set_password_hash(member.email, hash_password(new_password))
    members_db.clear_reset_token(member.email)
    return member.email
