"""会員（アカウント認証情報 + Stripeサブスクリプション状態）の永続化。

Streamlit自体にはユーザーアカウントの概念がないため、メールアドレスを
識別子とした最小限の会員テーブルをSQLiteで持つ。認証情報(password_hash等)と
Stripeサブスクリプション状態は同じ行で管理する(同じメールアドレスに対して、
アカウント登録がStripe決済より先でも後でも自然につながるようにするため)。

サブスクリプション状態の正としては Stripe Webhook（core/billing.py,
webhook_server.py）からの更新のみを信頼し、Checkout完了後のリダイレクトの
クエリパラメータ自体は状態確定に使わない（改ざん・タイミングのズレを避けるため）。
"""

from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(os.environ.get("MEMBERS_DB_PATH", Path(__file__).resolve().parent.parent / "data" / "members.db"))

ACTIVE_STATUSES = {"active", "trialing"}

_SCHEMA = """
CREATE TABLE IF NOT EXISTS members (
    email TEXT PRIMARY KEY,
    stripe_customer_id TEXT,
    stripe_subscription_id TEXT,
    subscription_status TEXT,
    updated_at TEXT NOT NULL
);
"""

# 既存DB(旧スキーマ)にも安全に追加できるよう、CREATE TABLEとは別にALTERで補う。
# email_verified は DEFAULT 1 にしてあり、この機能を追加する前から存在していた
# アカウント(既にパスワードでログインできていた行)を、追加後にいきなりログイン
# できなくしないため(=既存アカウントは検証済み扱いのまま維持する)。新規登録
# (core/accounts.py の register())だけが明示的に 0 にする。
_MIGRATION_COLUMNS = {
    "password_hash": "TEXT",
    "reset_token": "TEXT",
    "reset_token_expires": "TEXT",
    "email_verified": "INTEGER DEFAULT 1",
    "verification_token": "TEXT",
    "verification_token_expires": "TEXT",
    "failed_login_attempts": "INTEGER DEFAULT 0",
    "lockout_until": "TEXT",
}


@dataclass
class Member:
    email: str
    stripe_customer_id: str | None
    stripe_subscription_id: str | None
    subscription_status: str | None
    updated_at: str
    password_hash: str | None = None
    reset_token: str | None = None
    reset_token_expires: str | None = None
    email_verified: int | None = 1
    verification_token: str | None = None
    verification_token_expires: str | None = None
    failed_login_attempts: int | None = 0
    lockout_until: str | None = None

    @property
    def is_active(self) -> bool:
        return self.subscription_status in ACTIVE_STATUSES

    @property
    def has_account(self) -> bool:
        return self.password_hash is not None

    @property
    def is_email_verified(self) -> bool:
        return bool(self.email_verified)


def _migrate(conn: sqlite3.Connection) -> None:
    existing_columns = {row[1] for row in conn.execute("PRAGMA table_info(members)")}
    for column, col_type in _MIGRATION_COLUMNS.items():
        if column not in existing_columns:
            conn.execute(f"ALTER TABLE members ADD COLUMN {column} {col_type}")


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute(_SCHEMA)
    _migrate(conn)
    return conn


def get_member(email: str) -> Member | None:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM members WHERE email = ?", (email,)).fetchone()
    if row is None:
        return None
    return Member(**dict(row))


def get_member_by_customer_id(stripe_customer_id: str) -> Member | None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM members WHERE stripe_customer_id = ?", (stripe_customer_id,)
        ).fetchone()
    if row is None:
        return None
    return Member(**dict(row))


def get_member_by_reset_token(token: str) -> Member | None:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM members WHERE reset_token = ?", (token,)).fetchone()
    if row is None:
        return None
    return Member(**dict(row))


def get_member_by_verification_token(token: str) -> Member | None:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM members WHERE verification_token = ?", (token,)).fetchone()
    if row is None:
        return None
    return Member(**dict(row))


def _ensure_row(conn: sqlite3.Connection, email: str, now: str) -> None:
    existing = conn.execute("SELECT 1 FROM members WHERE email = ?", (email,)).fetchone()
    if existing is None:
        conn.execute(
            "INSERT INTO members (email, subscription_status, updated_at) VALUES (?, NULL, ?)",
            (email, now),
        )


def upsert_member(
    email: str,
    stripe_customer_id: str | None = None,
    stripe_subscription_id: str | None = None,
    subscription_status: str | None = None,
) -> None:
    now = datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        existing = conn.execute("SELECT * FROM members WHERE email = ?", (email,)).fetchone()
        if existing is None:
            conn.execute(
                "INSERT INTO members (email, stripe_customer_id, stripe_subscription_id, subscription_status, updated_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (email, stripe_customer_id, stripe_subscription_id, subscription_status, now),
            )
        else:
            conn.execute(
                "UPDATE members SET "
                "stripe_customer_id = COALESCE(?, stripe_customer_id), "
                "stripe_subscription_id = COALESCE(?, stripe_subscription_id), "
                "subscription_status = COALESCE(?, subscription_status), "
                "updated_at = ? "
                "WHERE email = ?",
                (stripe_customer_id, stripe_subscription_id, subscription_status, now, email),
            )
        conn.commit()


def set_password_hash(email: str, password_hash: str) -> None:
    now = datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        _ensure_row(conn, email, now)
        conn.execute(
            "UPDATE members SET password_hash = ?, updated_at = ? WHERE email = ?",
            (password_hash, now, email),
        )
        conn.commit()


def set_reset_token(email: str, token: str, expires_at_iso: str) -> None:
    now = datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        _ensure_row(conn, email, now)
        conn.execute(
            "UPDATE members SET reset_token = ?, reset_token_expires = ?, updated_at = ? WHERE email = ?",
            (token, expires_at_iso, now, email),
        )
        conn.commit()


def clear_reset_token(email: str) -> None:
    now = datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        conn.execute(
            "UPDATE members SET reset_token = NULL, reset_token_expires = NULL, updated_at = ? WHERE email = ?",
            (now, email),
        )
        conn.commit()


def set_email_verified(email: str, verified: bool) -> None:
    now = datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        _ensure_row(conn, email, now)
        conn.execute(
            "UPDATE members SET email_verified = ?, updated_at = ? WHERE email = ?",
            (1 if verified else 0, now, email),
        )
        conn.commit()


def set_verification_token(email: str, token: str, expires_at_iso: str) -> None:
    now = datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        _ensure_row(conn, email, now)
        conn.execute(
            "UPDATE members SET verification_token = ?, verification_token_expires = ?, updated_at = ? WHERE email = ?",
            (token, expires_at_iso, now, email),
        )
        conn.commit()


def clear_verification_token(email: str) -> None:
    now = datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        conn.execute(
            "UPDATE members SET verification_token = NULL, verification_token_expires = NULL, updated_at = ? WHERE email = ?",
            (now, email),
        )
        conn.commit()


def record_failed_login(email: str) -> int:
    """ログイン失敗を1件記録し、更新後の連続失敗回数を返す。
    閾値判定・ロック設定は呼び出し元(core.accounts)が行う。
    """
    now = datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        conn.execute(
            "UPDATE members SET failed_login_attempts = COALESCE(failed_login_attempts, 0) + 1, "
            "updated_at = ? WHERE email = ?",
            (now, email),
        )
        conn.commit()
        row = conn.execute("SELECT failed_login_attempts FROM members WHERE email = ?", (email,)).fetchone()
    return row["failed_login_attempts"] if row else 0


def set_lockout(email: str, lockout_until_iso: str) -> None:
    now = datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        conn.execute(
            "UPDATE members SET lockout_until = ?, failed_login_attempts = 0, updated_at = ? WHERE email = ?",
            (lockout_until_iso, now, email),
        )
        conn.commit()


def reset_failed_login(email: str) -> None:
    now = datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        conn.execute(
            "UPDATE members SET failed_login_attempts = 0, lockout_until = NULL, updated_at = ? WHERE email = ?",
            (now, email),
        )
        conn.commit()
