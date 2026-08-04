"""ダミーの出走馬データ生成。

本来は JRA-VAN（JV-Link）等から取得すべきデータだが、有料契約とWindows専用
ソフトが必要で今すぐの自動連携ができないため、当面はモックで代替する。
差し替え時は core/data_source.py の EntryDataSource 実装を JRA-VAN 版に
入れ替えるだけで済むようにしてある。

日付・会場・レース番号から生成される内容は毎回同じになるよう乱数を seed して
いる（同じレースを選べば毎回同じ出馬表が出る方が、デモとして挙動を理解しやすい
ため）。
"""

from __future__ import annotations

import random
from datetime import date as Date

from core.models import COURSE_TYPES, RUNNING_STYLES, TRACK_CONDITIONS, Horse, RaceCondition

_DISTANCES = [1000, 1200, 1400, 1600, 1800, 2000, 2200, 2400, 3000]
_RACE_CLASSES = [
    "3歳未勝利",
    "1勝クラス",
    "2勝クラス",
    "3勝クラス",
    "オープン",
    "G3",
    "G2",
]

_NAME_PREFIX = [
    "メイショウ", "トウカイ", "ゴールド", "サクラ", "タイキ", "エピック", "ブラック",
    "シルバー", "ウイニング", "スターダム", "レジェンド", "クリスタル", "インペリアル",
    "ロイヤル", "ノーザン", "フェニックス", "ブルー", "レッド", "グリーン", "ホワイト",
]
_NAME_SUFFIX = [
    "フウジン", "タイヨウ", "ドリーム", "バレット", "スピリット", "キング", "クイーン",
    "ヴィクトリー", "フレイム", "ライトニング", "オーロラ", "ジャスティス", "プリンセス",
    "ナイト", "ホープ", "グローリー", "エース", "ダッシュ", "ソニック", "パワー",
]


def _seed_for(*parts: object) -> int:
    return abs(hash(tuple(str(p) for p in parts))) % (2**31)


def generate_race_condition(target_date: Date, venue: str, race_number: int) -> RaceCondition:
    rng = random.Random(_seed_for(target_date, venue, race_number))
    course_type = rng.choices(COURSE_TYPES, weights=[0.55, 0.45])[0]
    distance = rng.choice(_DISTANCES)
    track_condition = rng.choices(TRACK_CONDITIONS, weights=[0.55, 0.25, 0.13, 0.07])[0]
    # メインレース（11R前後）ほど格上のクラスになりやすい、という簡易な重み付け。
    class_weights = [1, 1, 1, 1, 1, 1, 1]
    if race_number >= 10:
        class_weights = [0.2, 0.6, 0.8, 1.0, 1.2, 1.3, 1.1]
    race_class = rng.choices(_RACE_CLASSES, weights=class_weights)[0]
    field_size = rng.randint(8, 18)

    return RaceCondition(
        date=target_date,
        venue=venue,
        race_number=race_number,
        course_type=course_type,
        distance=distance,
        track_condition=track_condition,
        race_class=race_class,
        field_size=field_size,
    )


def generate_entries(condition: RaceCondition) -> list[Horse]:
    rng = random.Random(_seed_for(condition.date, condition.venue, condition.race_number, "entries"))
    names_used: set[str] = set()
    horses: list[Horse] = []

    for number in range(1, condition.field_size + 1):
        while True:
            name = rng.choice(_NAME_PREFIX) + rng.choice(_NAME_SUFFIX)
            if name not in names_used:
                names_used.add(name)
                break

        frame = min(8, (number - 1) // 2 + 1)
        running_style = rng.choices(RUNNING_STYLES, weights=[0.15, 0.35, 0.35, 0.15])[0]
        horse_weight = rng.randint(410, 540)
        weight_diff = rng.randint(-12, 12)
        popularity = number  # 人気順は後段でオッズから並べ直す
        odds = round(rng.uniform(1.5, 60.0), 1)

        horses.append(
            Horse(
                number=number,
                frame=frame,
                name=name,
                running_style=running_style,
                horse_weight=horse_weight,
                weight_diff=weight_diff,
                popularity=popularity,
                odds=odds,
            )
        )

    # オッズ順に人気番号を振り直す(1人気=最もオッズが低い馬)。
    for rank, horse in enumerate(sorted(horses, key=lambda h: h.odds), start=1):
        horses[horse.number - 1] = Horse(
            number=horse.number,
            frame=horse.frame,
            name=horse.name,
            running_style=horse.running_style,
            horse_weight=horse.horse_weight,
            weight_diff=horse.weight_diff,
            popularity=rank,
            odds=horse.odds,
        )

    return horses
