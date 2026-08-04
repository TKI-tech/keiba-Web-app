"""出走馬データ取得の抽象化。

現状は MockEntryDataSource のみが存在する。将来 JRA-VAN（JV-Link）や外部APIに
接続する際は、この Protocol を満たす実装（例: JraVanEntryDataSource）を追加し、
get_entry_data_source() の戻り値を差し替えるだけで良い。UI・スコアリング側の
コードは変更不要な設計にしてある。
"""

from __future__ import annotations

from datetime import date as Date
from typing import Protocol

from core.mock_data import generate_entries, generate_race_condition
from core.models import Horse, RaceCondition


class EntryDataSource(Protocol):
    def get_race(self, target_date: Date, venue: str, race_number: int) -> tuple[RaceCondition, list[Horse]]: ...


class MockEntryDataSource:
    """ダミーデータで出馬表を生成する実装。JRA-VAN連携までの暫定版。"""

    def get_race(self, target_date: Date, venue: str, race_number: int) -> tuple[RaceCondition, list[Horse]]:
        condition = generate_race_condition(target_date, venue, race_number)
        horses = generate_entries(condition)
        return condition, horses


def get_entry_data_source() -> EntryDataSource:
    return MockEntryDataSource()
