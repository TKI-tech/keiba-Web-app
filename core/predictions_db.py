"""「おすすめ馬券」の予想履歴と的中実績の永続化。

会員個人に紐付くデータではなく、アプリが出した予想そのものの実績(=このアプリの
予想精度の記録)としてSQLiteに保存する。予想が生成されるたびに(閲覧者が会員かどうか
に関わらず)1件保存し、レース日を過ぎたら core/settlement.py で実結果と照合して
確定させる。
"""

from __future__ import annotations

import json
import os
import sqlite3
from dataclasses import dataclass
from datetime import date as Date
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(
    os.environ.get("PREDICTIONS_DB_PATH", Path(__file__).resolve().parent.parent / "data" / "predictions.db")
)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS predictions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    race_date TEXT NOT NULL,
    venue TEXT NOT NULL,
    race_number INTEGER NOT NULL,
    bet_type TEXT NOT NULL,
    horse_numbers TEXT NOT NULL,
    horse_names TEXT NOT NULL,
    points INTEGER NOT NULL,
    estimated_hit_rate REAL NOT NULL,
    estimated_return_rate REAL NOT NULL,
    settled INTEGER NOT NULL DEFAULT 0,
    actual_hit INTEGER,
    stake INTEGER,
    payout_total INTEGER,
    actual_return_rate REAL,
    settled_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_predictions_settled ON predictions (settled, race_date);
CREATE UNIQUE INDEX IF NOT EXISTS idx_predictions_race ON predictions (race_date, venue, race_number);
"""


@dataclass
class Prediction:
    id: int
    created_at: str
    race_date: str
    venue: str
    race_number: int
    bet_type: str
    horse_numbers: list[int]
    horse_names: list[str]
    points: int
    estimated_hit_rate: float
    estimated_return_rate: float
    settled: bool
    actual_hit: bool | None
    stake: int | None
    payout_total: int | None
    actual_return_rate: float | None
    settled_at: str | None

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "Prediction":
        data = dict(row)
        data["horse_numbers"] = json.loads(data["horse_numbers"])
        data["horse_names"] = json.loads(data["horse_names"])
        data["settled"] = bool(data["settled"])
        data["actual_hit"] = None if data["actual_hit"] is None else bool(data["actual_hit"])
        return cls(**data)


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA)
    return conn


def find_prediction(race_date: Date, venue: str, race_number: int) -> Prediction | None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM predictions WHERE race_date = ? AND venue = ? AND race_number = ?",
            (race_date.isoformat(), venue, race_number),
        ).fetchone()
    return Prediction.from_row(row) if row else None


def save_prediction(
    race_date: Date,
    venue: str,
    race_number: int,
    bet_type: str,
    horse_numbers: list[int],
    horse_names: list[str],
    points: int,
    estimated_hit_rate: float,
    estimated_return_rate: float,
) -> int:
    now = datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        cur = conn.execute(
            "INSERT INTO predictions "
            "(created_at, race_date, venue, race_number, bet_type, horse_numbers, horse_names, "
            " points, estimated_hit_rate, estimated_return_rate) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                now,
                race_date.isoformat(),
                venue,
                race_number,
                bet_type,
                json.dumps(horse_numbers),
                json.dumps(horse_names, ensure_ascii=False),
                points,
                estimated_hit_rate,
                estimated_return_rate,
            ),
        )
        conn.commit()
        return cur.lastrowid


def get_settleable(today: Date) -> list[Prediction]:
    """レース日を過ぎていて、まだ確定していない予想の一覧。"""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM predictions WHERE settled = 0 AND race_date <= ? ORDER BY race_date",
            (today.isoformat(),),
        ).fetchall()
    return [Prediction.from_row(r) for r in rows]


def mark_settled(prediction_id: int, hit: bool, stake: int, payout_total: int, return_rate: float) -> None:
    now = datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        conn.execute(
            "UPDATE predictions SET settled = 1, actual_hit = ?, stake = ?, payout_total = ?, "
            "actual_return_rate = ?, settled_at = ? WHERE id = ?",
            (1 if hit else 0, stake, payout_total, return_rate, now, prediction_id),
        )
        conn.commit()


def get_all_settled() -> list[Prediction]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM predictions WHERE settled = 1 ORDER BY race_date DESC, id DESC"
        ).fetchall()
    return [Prediction.from_row(r) for r in rows]


@dataclass
class VenueStats:
    venue: str
    count: int
    hit_count: int
    total_stake: int
    total_payout: int

    @property
    def hit_rate(self) -> float:
        return self.hit_count / self.count * 100 if self.count else 0.0

    @property
    def return_rate(self) -> float:
        return self.total_payout / self.total_stake * 100 if self.total_stake else 0.0


def venue_stats() -> list[VenueStats]:
    settled = get_all_settled()
    by_venue: dict[str, VenueStats] = {}
    for p in settled:
        stats = by_venue.setdefault(p.venue, VenueStats(p.venue, 0, 0, 0, 0))
        stats.count += 1
        stats.hit_count += 1 if p.actual_hit else 0
        stats.total_stake += p.stake or 0
        stats.total_payout += p.payout_total or 0
    return sorted(by_venue.values(), key=lambda s: s.venue)
