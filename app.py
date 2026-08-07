"""初心者向け競馬予想Webアプリ（PWA） - MVP

現状は「過去5年データ」「当日の出走馬データ」ともにダミーデータで動作する。
実データ接続時に差し替える箇所は core/data_source.py と core/history_source.py。
"""

from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

from core.accounts import (
    AccountError,
    EmailAlreadyRegisteredError,
    EmailNotVerifiedError,
    InvalidCredentialsError,
    InvalidResetTokenError,
    InvalidVerificationTokenError,
    ensure_master_account,
    login,
    normalize_email,
    register,
    request_password_reset,
    resend_verification_email,
    reset_password,
    verify_email,
)
from core.app_url import AppUrlNotConfiguredError
from core.bet_recommendation import BET_TYPES, recommend_bets
from core.billing import BillingNotConfiguredError, create_billing_portal_session, create_checkout_session
from core.data_source import get_entry_data_source
from core.email_sender import EmailNotConfiguredError, EmailSendError
from core.history_source import build_tendency
from core.members_db import get_member
from core.models import VENUES
from core.predictions_db import find_prediction, save_prediction
from core.recommended_ticket import pick_recommended_ticket
from core.scoring import score_horses
from core.underdog import pick_underdog

load_dotenv()

st.set_page_config(page_title="競馬予想Webアプリ", layout="wide")


@st.cache_resource
def _bootstrap_master_account() -> None:
    # st.cache_resourceによりサーバープロセス起動後1回だけ実行される
    # (毎リラン時にパスワードのハッシュ計算(意図的に低速)が走らないようにするため)。
    ensure_master_account()


_bootstrap_master_account()


def render_reset_password_form(token: str) -> None:
    """パスワード再設定メールのリンク(?reset_token=...)を踏んだ場合の専用画面。
    通常のレース予想UIより先に、これだけを表示する。
    """
    st.title("パスワードの再設定")
    with st.form("reset_password_form"):
        new_password = st.text_input("新しいパスワード", type="password")
        confirm_password = st.text_input("新しいパスワード（確認）", type="password")
        submitted = st.form_submit_button("パスワードを更新する", type="primary")

    if submitted:
        if new_password != confirm_password:
            st.error("パスワードが一致しません。")
        else:
            try:
                email = reset_password(token, new_password)
            except AccountError as exc:
                st.error(str(exc))
            else:
                st.query_params.clear()
                st.success(f"{email} のパスワードを更新しました。サイドバーからログインしてください。")
                st.stop()


def render_verify_email_page(token: str) -> None:
    """確認メールのリンク(?verify_token=...)を踏んだ場合の専用画面。"""
    st.title("メールアドレスの確認")
    try:
        email = verify_email(token)
    except AccountError as exc:
        st.error(str(exc))
        st.page_link("app.py", label="予想画面に戻る")
    else:
        st.query_params.clear()
        st.success(f"{email} の確認が完了しました。サイドバーからログインしてください。")
        st.page_link("app.py", label="予想画面に戻る")
    st.stop()


def render_membership_sidebar() -> bool:
    """ログイン・新規登録・パスワード再設定 + Stripe会員登録の導線。
    戻り値は、ログイン中のアカウントが有効な会員（サブスク中）かどうか
    （本命馬以外の会員限定機能の表示判定に使う）。
    """
    st.sidebar.subheader("会員登録・ログイン")

    logged_in_email = st.session_state.get("auth_email")

    if not logged_in_email:
        tab_login, tab_register, tab_forgot = st.sidebar.tabs(["ログイン", "新規登録", "パスワードを忘れた方"])

        with tab_login:
            with st.form("login_form"):
                email = st.text_input("メールアドレス", key="login_email")
                password = st.text_input("パスワード", type="password", key="login_password")
                if st.form_submit_button("ログイン"):
                    email = normalize_email(email)
                    try:
                        login(email, password)
                    except EmailNotVerifiedError as exc:
                        st.error(str(exc))
                        st.session_state["unverified_login_email"] = email
                    except AccountError as exc:
                        st.error(str(exc))
                    else:
                        st.session_state.pop("unverified_login_email", None)
                        st.session_state["auth_email"] = email
                        st.rerun()

            unverified_email = st.session_state.get("unverified_login_email")
            if unverified_email and st.button("確認メールを再送する", key="resend_verification_button"):
                try:
                    resend_verification_email(unverified_email)
                except (AppUrlNotConfiguredError, EmailNotConfiguredError, EmailSendError) as exc:
                    st.error(str(exc))
                else:
                    st.success("確認メールを再送しました。")

        with tab_register:
            with st.form("register_form"):
                email = st.text_input("メールアドレス", key="register_email")
                password = st.text_input("パスワード（8文字以上）", type="password", key="register_password")
                confirm = st.text_input("パスワード（確認）", type="password", key="register_confirm")
                if st.form_submit_button("登録する"):
                    email = normalize_email(email)
                    if password != confirm:
                        st.error("パスワードが一致しません。")
                    else:
                        try:
                            register(email, password)
                        except (AccountError, AppUrlNotConfiguredError, EmailNotConfiguredError, EmailSendError) as exc:
                            st.error(str(exc))
                        else:
                            st.success(
                                f"{email} 宛に確認メールを送信しました。メール内のリンクをクリックして"
                                "登録を完了してください（届かない場合は迷惑メールフォルダもご確認ください）。"
                            )

        with tab_forgot:
            with st.form("forgot_password_form"):
                email = st.text_input("メールアドレス", key="forgot_email")
                if st.form_submit_button("再設定メールを送る"):
                    email = normalize_email(email)
                    try:
                        request_password_reset(email)
                    except (AppUrlNotConfiguredError, EmailNotConfiguredError, EmailSendError) as exc:
                        st.error(str(exc))
                    else:
                        st.success(
                            "登録されているメールアドレスの場合、パスワード再設定用のリンクを送信しました。"
                        )

        return False

    st.sidebar.write(f"ログイン中: {logged_in_email}")
    if st.sidebar.button("ログアウト"):
        del st.session_state["auth_email"]
        st.rerun()

    member = get_member(logged_in_email)
    if member and member.is_active:
        st.sidebar.success(f"会員登録済みです（状態: {member.subscription_status}）")
        if st.sidebar.button("プランを管理する"):
            try:
                portal_url = create_billing_portal_session(member.stripe_customer_id)
                st.sidebar.link_button("Stripeで管理画面を開く", portal_url)
            except BillingNotConfiguredError as exc:
                st.sidebar.error(str(exc))
        return True

    st.sidebar.info("会員未登録、または手続き中です。")
    st.sidebar.page_link("pages/02_特定商取引法に基づく表記.py", label="特定商取引法に基づく表記")
    if st.sidebar.button("登録リンクを作成"):
        try:
            checkout_url = create_checkout_session(logged_in_email)
            st.sidebar.link_button("Stripeで登録手続きへ進む", checkout_url)
        except BillingNotConfiguredError as exc:
            st.sidebar.error(str(exc))
    return False


def render_locked_section(title: str, description: str) -> None:
    st.subheader(title)
    st.info(
        f"この機能は会員限定です。サイドバーでログイン・登録すると{description}",
        icon="🔒",
    )


verify_token = st.query_params.get("verify_token")
if verify_token:
    render_verify_email_page(verify_token)
    st.stop()

reset_token = st.query_params.get("reset_token")
if reset_token:
    render_reset_password_form(reset_token)
    st.stop()

is_member = render_membership_sidebar()
st.sidebar.divider()
st.sidebar.page_link("pages/01_過去の実績.py", label="過去の予想実績を見る")
st.sidebar.page_link("pages/02_特定商取引法に基づく表記.py", label="特定商取引法に基づく表記")

checkout_status = st.query_params.get("checkout")
if checkout_status == "success":
    st.success(
        "決済処理を受け付けました。会員状態への反映まで数秒かかる場合があります。"
        "サイドバーでログイン状態をご確認ください。"
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
    st.metric("複勝適合率", f"{honmei.place_score:.1f}%")
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
        if c.bet_type == "枠連":
            horses_desc = "、".join(f"{h.horse.frame}枠（{h.horse.number}番 {h.horse.name}）" for h in c.horses)
        else:
            horses_desc = "、".join(f"{h.horse.number}番 {h.horse.name}" for h in c.horses)
        st.caption(f"{c.points}点（{horses_desc}）")
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

    def _pick_label(h) -> str:
        if bet_type == "枠連":
            return f"**{h.horse.frame}枠**（{h.horse.number}番 {h.horse.name}）"
        return f"**{h.horse.number}番 {h.horse.name}**"

    col_solid, col_rough = st.columns(2)
    with col_solid:
        st.markdown(f"### {solid.style_label}")
        st.markdown(" ／ ".join(_pick_label(h) for h in solid.horses))
        st.write(solid.explanation)
    with col_rough:
        st.markdown(f"### {rough.style_label}")
        st.markdown(" ／ ".join(_pick_label(h) for h in rough.horses))
        st.write(rough.explanation)
else:
    render_locked_section("買い目を選ぶ", "堅実タイプ・荒れ狙いタイプの買い目提案が確認できます。")

st.divider()

# --- C. 出走馬一覧スコア表（会員限定・折りたたみ） -----------------------------
if is_member:
    with st.expander("出走馬一覧を見る（全頭のスコア表）", expanded=False):
        score_columns = ["1着適合率(%)", "複勝適合率(%)"]
        table = pd.DataFrame(
            [
                {
                    "馬番": s.horse.number,
                    "馬名": s.horse.name,
                    "枠": s.horse.frame,
                    "脚質": s.horse.running_style,
                    "1着適合率(%)": round(s.win_score, 1),
                    "複勝適合率(%)": round(s.place_score, 1),
                    "オッズ": s.horse.odds,
                    "人気": s.horse.popularity,
                }
                for s in sorted(scores, key=lambda s: s.horse.number)
            ]
        )

        def _highlight_top3(column: pd.Series) -> list[str]:
            # 同着(タイ)があっても必ず3セルだけ色が付くよう、値ではなく順位(重複なし)で判定する。
            ranks = column.rank(method="first", ascending=False)
            styles = {
                1: "background-color: #FFEE58; color: #000000",
                2: "background-color: #EF9A9A; color: #000000",
                3: "background-color: #80DEEA; color: #000000",
            }
            return [styles.get(int(r), "") for r in ranks]

        styled_table = table.style.apply(_highlight_top3, subset=score_columns).format(
            {"1着適合率(%)": "{:.1f}", "複勝適合率(%)": "{:.1f}", "オッズ": "{:.1f}"}
        )
        st.dataframe(styled_table, hide_index=True, width="stretch")
        st.caption("黄色=1位、赤=2位、水色=3位（1着適合率・複勝適合率それぞれの中で表示）")
        st.caption(
            "1着適合率・複勝適合率は、その馬個体の過去成績ではなく、"
            "過去5年の同条件（会場・コース・距離・馬場状態）のレースで、この馬と同じ特徴"
            "（脚質・枠順・馬体重・体重増減など）を持っていた馬たちが実際に「1着になった割合」"
            "「3着以内に入った割合」をもとに算出した参考スコアです（0〜100%）。"
        )
else:
    render_locked_section("出走馬一覧スコア表", "全頭のスコア表が確認できます。")
