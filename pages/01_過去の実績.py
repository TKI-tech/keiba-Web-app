"""過去の予想と的中実績ページ。

「おすすめ馬券」(app.py)として出した予想を、レース日を過ぎたものから順に
ダミーの実結果(core/result_source.py)と自動照合し、会場別の回収率・的中率を
集計して表示する。JRA-VAN連携後は、この自動照合を実際のレース結果に基づく
ものへ差し替える想定（core/settlement.py参照）。
"""

from __future__ import annotations

from datetime import date

import altair as alt
import pandas as pd
import streamlit as st

from core.predictions_db import get_all_settled, get_settleable, mark_settled, venue_stats
from core.settlement import settle_ticket

st.set_page_config(page_title="過去の実績 - 競馬予想 NEWMARKET", layout="wide")

st.page_link("app.py", label="予想画面に戻る")

st.title("過去の予想と的中実績")
st.caption("「おすすめ馬券」として出した予想を、レース結果と照合した実績です。")
st.info(
    "JRA-VAN連携が未実装のため、実際のレース結果の代わりに、予想時と同じ確率モデル"
    "から生成したダミー結果で自動照合しています。実データ連携後、この照合は本物の"
    "レース結果に基づくものへ差し替わります。",
    icon="ℹ️",
)

settleable = get_settleable(date.today())
if settleable:
    with st.spinner(f"{len(settleable)}件のレース結果と照合しています..."):
        for prediction in settleable:
            result = settle_ticket(
                date.fromisoformat(prediction.race_date),
                prediction.venue,
                prediction.race_number,
                prediction.bet_type,
                prediction.horse_numbers,
                prediction.points,
            )
            mark_settled(prediction.id, result.hit, result.stake, result.payout_total, result.return_rate)

settled = get_all_settled()

if not settled:
    st.write("まだ照合済みの予想がありません。レースを予想すると、レース日を過ぎたものから順にここに反映されます。")
    st.stop()

total_stake = sum(p.stake or 0 for p in settled)
total_payout = sum(p.payout_total or 0 for p in settled)
hit_count = sum(1 for p in settled if p.actual_hit)

col1, col2, col3 = st.columns(3)
col1.metric("確定した予想数", f"{len(settled)}件")
col2.metric("的中率", f"{hit_count / len(settled) * 100:.1f}%")
col3.metric("回収率", f"{(total_payout / total_stake * 100) if total_stake else 0:.1f}%")

st.divider()

st.subheader("会場別の回収率")
stats = venue_stats()
chart_df = pd.DataFrame(
    [{"会場": s.venue, "回収率": round(s.return_rate, 1), "的中率": round(s.hit_rate, 1), "件数": s.count} for s in stats]
)
chart_df["状態"] = chart_df["回収率"].apply(lambda r: "黒字（100%以上）" if r >= 100 else "赤字（100%未満）")

# 100%(損益分岐)を境に「黒字/赤字」で色分けするステータス表現。この2色は
# ライト/ダークいずれの背景でも同じ配色を使う固定のステータスカラー。
color_scale = alt.Scale(domain=["黒字（100%以上）", "赤字（100%未満）"], range=["#0ca30c", "#d03b3b"])

bars = (
    alt.Chart(chart_df)
    .mark_bar(size=28, cornerRadiusTopLeft=4, cornerRadiusTopRight=4)
    .encode(
        x=alt.X(
            "会場:N",
            title=None,
            sort=None,
            axis=alt.Axis(labelAngle=0, labelLimit=200, labelFontSize=13, labelPadding=6),
        ),
        y=alt.Y("回収率:Q", title="回収率(%)"),
        color=alt.Color("状態:N", scale=color_scale, legend=alt.Legend(title=None)),
        tooltip=[
            alt.Tooltip("会場:N"),
            alt.Tooltip("回収率:Q", format=".1f", title="回収率(%)"),
            alt.Tooltip("的中率:Q", format=".1f", title="的中率(%)"),
            alt.Tooltip("件数:Q", title="件数"),
        ],
    )
)
breakeven_rule = alt.Chart(pd.DataFrame({"y": [100]})).mark_rule(color="#898781", strokeDash=[4, 4]).encode(y="y:Q")
labels = bars.mark_text(dy=-8, color="#52514e").encode(text=alt.Text("回収率:Q", format=".0f"))

st.altair_chart((bars + breakeven_rule + labels), width="stretch")
st.caption("点線は損益分岐ライン(回収率100%)。緑=100%以上（黒字）、赤=100%未満（赤字）。")

st.divider()

st.subheader("直近の予想一覧")
table = pd.DataFrame(
    [
        {
            "レース日": p.race_date,
            "会場": p.venue,
            "R": p.race_number,
            "券種": p.bet_type,
            "組合せ": "、".join(p.horse_names),
            "点数": p.points,
            "的中": "○" if p.actual_hit else "×",
            "回収率(%)": round(p.actual_return_rate, 1) if p.actual_return_rate is not None else None,
        }
        for p in settled
    ]
)
st.dataframe(table, hide_index=True, width="stretch")
