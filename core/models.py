"""ドメインモデルと属性分類ロジック。

分類の閾値（枠・馬体重・体重増減のゾーン分け）は既存モバイル版エンジン
（TypeScript実装の @keiba/shared）の考え方に合わせてある。将来的に実データへ
接続する際もスコアリング側のロジックを変えずに済むようにするため。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date as Date

RUNNING_STYLES: list[str] = ["逃げ", "先行", "差し", "追込"]
COURSE_TYPES: list[str] = ["芝", "ダート"]
TRACK_CONDITIONS: list[str] = ["良", "稍重", "重", "不良"]
VENUES: list[str] = ["札幌", "函館", "福島", "新潟", "東京", "中山", "中京", "京都", "阪神", "小倉"]


@dataclass(frozen=True)
class RaceCondition:
    date: Date
    venue: str
    race_number: int
    course_type: str
    distance: int
    track_condition: str
    race_class: str
    field_size: int


@dataclass(frozen=True)
class Horse:
    number: int
    frame: int
    name: str
    running_style: str
    horse_weight: int
    weight_diff: int
    popularity: int
    odds: float


@dataclass
class CategoryRate:
    key: str
    label: str
    sample_size: int
    tansho_rate: float
    fukusho_rate: float


@dataclass
class Tendency:
    matched_races: int
    baseline_tansho_rate: float
    baseline_fukusho_rate: float
    by_running_style: dict[str, CategoryRate] = field(default_factory=dict)
    by_frame_zone: dict[str, CategoryRate] = field(default_factory=dict)
    by_weight_zone: dict[str, CategoryRate] = field(default_factory=dict)
    by_weight_change_zone: dict[str, CategoryRate] = field(default_factory=dict)
    by_combo: dict[str, CategoryRate] = field(default_factory=dict)
    highlight: str = ""


@dataclass
class HorseScore:
    horse: Horse
    win_score: float
    place_score: float
    reasons: list[str]


def classify_frame_zone(frame: int) -> str:
    if frame <= 2:
        return "内枠"
    if frame >= 7:
        return "外枠"
    return "中枠"


def classify_weight_zone(horse_weight: int) -> str:
    if horse_weight >= 500:
        return "大型馬"
    if horse_weight < 440:
        return "小型馬"
    return "標準馬"


def classify_weight_change_zone(weight_diff: int) -> str:
    if weight_diff <= -4:
        return "体重減"
    if weight_diff >= 4:
        return "体重増"
    return "体重維持"


def combo_key(frame_zone: str, running_style: str) -> str:
    return f"{frame_zone}×{running_style}"
