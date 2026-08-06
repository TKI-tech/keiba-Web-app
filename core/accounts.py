"""アカウント登録・ログイン・メール確認・パスワード再設定のビジネスロジック。

core/members_db.py は永続化のみ、core/auth.py はハッシュ化のみを担当し、
このモジュールがそれらを組み合わせて各ユースケースを提供する。
"""

from __future__ import annotations

import os
import secrets
from datetime import datetime, timedelta, timezone

from core import members_db
from core.app_url import base_url as app_base_url
from core.auth import hash_password, verify_password
from core.email_sender import send_email

RESET_TOKEN_TTL = timedelta(hours=1)
VERIFICATION_TOKEN_TTL = timedelta(hours=24)
MIN_PASSWORD_LENGTH = 8


class AccountError(RuntimeError):
    pass


class EmailAlreadyRegisteredError(AccountError):
    pass


class InvalidCredentialsError(AccountError):
    pass


class EmailNotVerifiedError(AccountError):
    pass


class InvalidResetTokenError(AccountError):
    pass


class InvalidVerificationTokenError(AccountError):
    pass


class WeakPasswordError(AccountError):
    pass


def _validate_password(password: str) -> None:
    if len(password) < MIN_PASSWORD_LENGTH:
        raise WeakPasswordError(f"パスワードは{MIN_PASSWORD_LENGTH}文字以上にしてください。")


def _send_verification_email(email: str) -> None:
    token = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + VERIFICATION_TOKEN_TTL
    members_db.set_verification_token(email, token, expires_at.isoformat())

    verify_url = f"{app_base_url()}/app/?verify_token={token}"
    body = (
        "競馬予想Webアプリへのご登録ありがとうございます。\n\n"
        f"以下のリンクをクリックして、メールアドレスの確認を完了してください(24時間有効です)。\n{verify_url}\n\n"
        "心当たりがない場合はこのメールを無視してください。"
    )
    send_email(email, "【競馬予想Webアプリ】メールアドレスの確認", body)


def register(email: str, password: str) -> None:
    """アカウントを作成する。作成直後はメール未確認状態で、確認メールのリンクを
    踏むまでログインできない(login()がEmailNotVerifiedErrorを送出する)。
    """
    _validate_password(password)
    existing = members_db.get_member(email)
    if existing and existing.has_account:
        raise EmailAlreadyRegisteredError("このメールアドレスは既に登録されています。ログインしてください。")
    members_db.set_password_hash(email, hash_password(password))
    members_db.set_email_verified(email, False)
    _send_verification_email(email)


def login(email: str, password: str) -> None:
    member = members_db.get_member(email)
    if not member or not member.has_account or not verify_password(password, member.password_hash):
        raise InvalidCredentialsError("メールアドレスまたはパスワードが正しくありません。")
    if not member.is_email_verified:
        raise EmailNotVerifiedError(
            "メールアドレスがまだ確認されていません。届いた確認メールのリンクをクリックしてください。"
        )


def resend_verification_email(email: str) -> None:
    """未登録・確認済みの場合は何もしない(登録有無を外部に漏らさないため)。"""
    member = members_db.get_member(email)
    if not member or not member.has_account or member.is_email_verified:
        return
    _send_verification_email(email)


def verify_email(token: str) -> str:
    """トークンを検証してメールアドレスを確認済みにし、そのメールアドレスを返す。"""
    member = members_db.get_member_by_verification_token(token)
    if member is None or not member.verification_token_expires:
        raise InvalidVerificationTokenError("リンクが無効か、有効期限が切れています。")
    if datetime.fromisoformat(member.verification_token_expires) < datetime.now(timezone.utc):
        raise InvalidVerificationTokenError("リンクが無効か、有効期限が切れています。")

    members_db.set_email_verified(member.email, True)
    members_db.clear_verification_token(member.email)
    return member.email


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


def ensure_master_account() -> None:
    """MASTER_EMAIL / MASTER_PASSWORD が設定されていれば、常時有効な
    テスト用会員アカウントを用意する(Stripe決済なしで会員限定画面を確認するため)。

    認証情報はリポジトリに含めず環境変数(.env、またはRenderのEnvironment)で
    渡す運用にしてある。未設定なら何もしない(=デフォルトでは作成されない)。
    メール確認は不要(テスト用のためスキップする)。
    """
    master_email = os.environ.get("MASTER_EMAIL")
    master_password = os.environ.get("MASTER_PASSWORD")
    if not master_email or not master_password:
        return
    members_db.set_password_hash(master_email, hash_password(master_password))
    members_db.set_email_verified(master_email, True)
    members_db.upsert_member(master_email, subscription_status="active")


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
