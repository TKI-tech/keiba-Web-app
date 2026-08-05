"""初心者向け競馬予想Webアプリ（PWA） - MVP

現状は「過去5年データ」「当日の出走馬データ」ともにダミーデータで動作する。
実データ接続時に差し替える箇所は core/data_source.py と core/history_source.py。
"""

from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

from core.bet_recommendation import BET_TYPES, recommend_bets
from core.billing import BillingNotConfiguredError, create_billing_portal_session, create_checkout_session
from core.data_source import get_entry_data_source
from core.history_source import build_tendency
from core.members_db import get_member
from core.models import VENUES
from core.predictions_db import find_prediction, save_prediction
from core.recommended_ticket import pick_recommended_ticket
from core.scoring import score_horses
from core.underdog import pick_underdog

load_dotenv()

st.set_page_config(page_title="競馬予想Webアプリ", layout="wide")


def render_membership_sidebar() -> bool:
    """会員登録・プラン管理の導線。戻り値は、入力されたメールアドレスが
    有効な会員かどうか（本命馬以外の会員限定機能の表示判定に使う）。
    """
    st.sidebar.subheader("会員登録・ログイン")
    email = st.sidebar.text_input("メールアドレス", key="member_email")
    if not email:
        st.sidebar.caption("メールアドレスを入力すると会員状態を確認できます。")
        return False

    member = get_member(email)
    if member and member.is_active:
        st.sidebar.success(f"会員登録済みです（状態: {member.subscription_status}）")
        if st.sidebar.button("プランを管理する"):
            try:
                portal_url = create_billing_portal_session(member.stripe_customer_id)
                st.sidebar.link_button("Stripeで管理画面を開く", portal_url)
            except BillingNotConfiguredError as exc:
                st.sidebar.error(str(exc))
        return True

    st.sidebar.info("未登録、または手続き中です。")
    if st.sidebar.button("登録リンクを作成"):
        try:
            checkout_url = create_checkout_session(email)
            st.sidebar.link_button("Stripeで登録手続きへ進む", checkout_url)
        except BillingNotConfiguredError as exc:
            st.sidebar.error(str(exc))
    return False


def render_locked_section(title: str, description: str) -> None:
    st.subheader(title)
    st.info(
        f"この機能は会員限定です。サイドバーでメールアドレスを入力し、登録すると{description}",
        icon="🔒",
    )


is_member = render_membership_sidebar()
st.sidebar.divider()
st.sidebar.page_link("pages/01_過去の実績.py", label="過去の予想実績を見る")

checkout_status = st.query_params.get("checkout")
if checkout_status == "success":
    st.success(
        "決済処理を受け付けました。会員状態への反映まで数秒かかる場合があります。"
        "サイドバーのメールアドレス欄で登録状態をご確認ください。"
    )
elif checkout_status == "cancel":
    st.warning("決済手続きがキャンセルされました。")

st.title("初心者向け競馬予想Webアプリ")
st.caption(
    "独自の分析ロジックが過去5年分のレースデータと出走馬を照合し、馬ごとの"
    "「適合率」を算出。勘や人気だけに頼らない、データに基づいた競馬予想を"
    "初心者にもわかりやすく提案します。"
)
st.info(
    "現在は開発中のためダミーデータで動作しています。過去データ・当日の出走馬データは"
    "実際のレース結果ではありません。",
    icon="ℹ️",
)

with st.form("race_select_form"):
    col1, col2, col3 = st.columns([1, 1, 2])
    with col1:
        target_date = st.date_input("開催日", value=date.today() + timedelta(days=(5 - date.today().weekday()) % 7))
    with col2:
        venue = st.selectbox("競馬場", VENUES)
    with col3:
        race_number = st.radio("レース番号", list(range(1, 13)), horizontal=True, format_func=lambda n: f"{n}R")

    submitted = st.form_submit_button("データから予想する", type="primary")

if submitted:
    data_source = get_entry_data_source()
    condition, horses = data_source.get_race(target_date, venue, race_number)
    tendency = build_tendency(condition)
    scores = score_horses(tendency, horses)
    ticket = pick_recommended_ticket(scores)

    # 会員かどうかに関わらず、このアプリの「公式予想」として記録する
    # （的中実績ページの集計対象。会員限定なのは表示のみ）。同じレースの
    # 予想は毎回同じ内容になる(決定的なダミーデータ生成)ため、二重登録はしない。
    if find_prediction(condition.date, condition.venue, condition.race_number) is None:
        save_prediction(
            race_date=condition.date,
            venue=condition.venue,
            race_number=condition.race_number,
            bet_type=ticket.candidate.bet_type,
            horse_numbers=[h.horse.number for h in ticket.candidate.horses],
            horse_names=[h.horse.name for h in ticket.candidate.horses],
            points=ticket.candidate.points,
            estimated_hit_rate=ticket.candidate.hit_rate,
            estimated_return_rate=ticket.candidate.return_rate,
        )

    st.session_state["result"] = {
        "condition": condition,
        "tendency": tendency,
        "scores": scores,
        "ticket": ticket,
    }

if "result" not in st.session_state:
    st.stop()

result = st.session_state["result"]
condition = result["condition"]
tendency = result["tendency"]
scores = result["scores"]
ticket = result["ticket"]

st.divider()
st.caption(
    f"{condition.date:%Y/%m/%d} {condition.venue} {condition.race_number}R ｜ "
    f"{condition.course_type} {condition.distance}m ｜ 馬場状態: {condition.track_condition} ｜ "
    f"クラス: {condition.race_class} ｜ 出走頭数: {condition.field_size}頭"
)

# --- A. 本命馬の提示 -------------------------------------------------------
honmei = scores[0]
st.subheader("本命馬（軸馬）")

col1, col2, col3 = st.columns([1, 1, 2])
with col1:
    st.markdown("**選定馬**")
    st.markdown(f"## {honmei.horse.number}番 {honmei.horse.name}")
with col2:
    st.metric("1着適合率", f"{honmei.win_score:.1f}%")
    st.metric("想定複勝率", f"{honmei.place_score:.1f}%")
with col3:
    st.markdown("**一言解説**")
    st.write(tendency.highlight)
    for reason in honmei.reasons:
        st.caption(f"・{reason}")

st.divider()

# --- おすすめ馬券（回収率×的中率バランス、会員限定） --------------------------
if is_member:
    st.subheader("おすすめ馬券")
    c = ticket.candidate
    col1, col2, col3 = st.columns([1, 1, 2])
    with col1:
        st.markdown("**券種・組合せ**")
        st.markdown(f"## {c.bet_type}")
        st.caption(f"{c.points}点（" + "、".join(f"{h.horse.number}番 {h.horse.name}" for h in c.horses) + "）")
    with col2:
        st.metric("見積もり的中率", f"{c.hit_rate * 100:.1f}%")
        st.metric("見積もり回収率", f"{c.return_rate:.0f}%")
    with col3:
        st.markdown("**一言解説**")
        st.write(ticket.explanation)
    st.caption(
        "的中率・回収率は過去5年の傾向データとオッズから見積もった参考値です"
        "（実際の払戻額を保証するものではありません）。"
    )
else:
    render_locked_section("おすすめ馬券", "回収率と的中率のバランスが良い、30点以内の買い目1点が確認できます。")

st.divider()

# --- おすすめの穴馬（会員限定） ----------------------------------------------
if is_member:
    st.subheader("おすすめの穴馬")
    underdog = pick_underdog(scores, tendency)
    if underdog is None:
        st.write("この条件では、平均を明確に上回るスコアを持つ穴馬が見つかりませんでした。")
    else:
        col1, col2 = st.columns([1, 3])
        with col1:
            st.markdown("**注目馬**")
            st.markdown(f"## {underdog.horse_score.horse.number}番 {underdog.horse_score.horse.name}")
            st.caption(f"オッズ {underdog.horse_score.horse.odds}倍 ／ {underdog.horse_score.horse.popularity}番人気")
        with col2:
            st.write(underdog.explanation)
else:
    render_locked_section("おすすめの穴馬", "スコアの割に人気がない狙い目の1頭が確認できます。")

st.divider()

# --- B. 買い目提案（会員限定） ------------------------------------------------
if is_member:
    st.subheader("買い目を選ぶ")
    bet_type = st.selectbox("馬券の種類", BET_TYPES)
    solid, rough = recommend_bets(scores, bet_type)

    col_solid, col_rough = st.columns(2)
    with col_solid:
        st.markdown(f"### {solid.style_label}")
        st.markdown(
            " ／ ".join(f"**{h.horse.number}番 {h.horse.name}**" for h in solid.horses)
        )
        st.write(solid.explanation)
    with col_rough:
        st.markdown(f"### {rough.style_label}")
        st.markdown(
            " ／ ".join(f"**{h.horse.number}番 {h.horse.name}**" for h in rough.horses)
        )
        st.write(rough.explanation)
else:
    render_locked_section("買い目を選ぶ", "堅実タイプ・荒れ狙いタイプの買い目提案が確認できます。")

st.divider()

# --- C. 出走馬一覧スコア表（会員限定・折りたたみ） -----------------------------
if is_member:
    with st.expander("出走馬一覧を見る（全頭のスコア表）", expanded=False):
        table = pd.DataFrame(
            [
                {
                    "馬番": s.horse.number,
                    "馬名": s.horse.name,
                    "枠": s.horse.frame,
                    "脚質": s.horse.running_style,
                    "1着適合率(%)": round(s.win_score, 1),
                    "複勝率(%)": round(s.place_score, 1),
                    "オッズ": s.horse.odds,
                    "人気": s.horse.popularity,
                }
                for s in scores
            ]
        )
        st.dataframe(table, hide_index=True, width="stretch")
else:
    render_locked_section("出走馬一覧スコア表", "全頭のスコア表が確認できます。")
