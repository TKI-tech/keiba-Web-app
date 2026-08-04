"""会員（Stripeサブスクリプション状態）の永続化。

Streamlit自体にはユーザーアカウントの概念がないため、メールアドレスを
識別子とした最小限の会員テーブルをSQLiteで持つ。会員登録状態の正としては
Stripe Webhook（core/billing.py, webhook_server.py）からの更新のみを信頼し、
Checkout完了後のリダイレクトのクエリパラメータ自体は状態確定に使わない
（改ざん・タイミングのズレを避けるため）。
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


@dataclass
class Member:
    email: str
    stripe_customer_id: str | None
    stripe_subscription_id: str | None
    subscription_status: str | None
    updated_at: str

    @property
    def is_active(self) -> bool:
        return self.subscription_status in ACTIVE_STATUSES


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute(_SCHEMA)
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
