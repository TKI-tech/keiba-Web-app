"""Stripe連携（Checkout / Billing Portal）。

有料化する機能はまだ未確定のため、ここでは「メールアドレスでCheckoutを開始し、
サブスクリプション登録・管理ができる」という決済・会員管理の土台のみを提供する。
実際に何を有料機能にするかはapp.py側で後から決める。

必要な環境変数（.env.example参照）:
  STRIPE_SECRET_KEY   Stripeのシークレットキー（テストモードは sk_test_... ）
  STRIPE_PRICE_ID     サブスクリプション用のPrice ID
  APP_BASE_URL        CheckoutからのリダイレクトURLの基点（例: http://localhost:8080）
"""

from __future__ import annotations

import os

import stripe


class BillingNotConfiguredError(RuntimeError):
    pass


def _require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise BillingNotConfiguredError(
            f"{name} が設定されていません。.env.example を参考に .env を用意してください。"
        )
    return value


def _configure_stripe() -> None:
    stripe.api_key = _require_env("STRIPE_SECRET_KEY")


def _base_url() -> str:
    """CheckoutからのリダイレクトURLの基点。APP_BASE_URL未設定時は、Renderが
    自動で注入する RENDER_EXTERNAL_URL にフォールバックする(Render上での
    デプロイをAPP_BASE_URLの手動設定なしで動かすため)。"""
    base_url = os.environ.get("APP_BASE_URL") or os.environ.get("RENDER_EXTERNAL_URL")
    if not base_url:
        raise BillingNotConfiguredError(
            "APP_BASE_URL が設定されていません。.env.example を参考に .env を用意してください。"
        )
    return base_url.rstrip("/")


def create_checkout_session(email: str) -> str:
    """指定メールアドレスでサブスクリプション用のCheckoutセッションを作成し、遷移先URLを返す。"""
    _configure_stripe()
    price_id = _require_env("STRIPE_PRICE_ID")
    base_url = _base_url()

    session = stripe.checkout.Session.create(
        mode="subscription",
        customer_email=email,
        line_items=[{"price": price_id, "quantity": 1}],
        success_url=f"{base_url}/app/?checkout=success",
        cancel_url=f"{base_url}/app/?checkout=cancel",
        # Webhook側でメールアドレスと突き合わせるためclient_referenceに残す。
        client_reference_id=email,
    )
    if not session.url:
        raise RuntimeError("Stripe Checkoutセッションの作成に失敗しました（URLが空です）。")
    return session.url


def create_billing_portal_session(stripe_customer_id: str) -> str:
    """既存会員向けの「プラン管理（解約・支払い方法変更など）」ページのURLを返す。"""
    _configure_stripe()
    base_url = _base_url()

    session = stripe.billing_portal.Session.create(
        customer=stripe_customer_id,
        return_url=f"{base_url}/app/",
    )
    return session.url
