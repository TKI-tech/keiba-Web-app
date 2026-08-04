"""Stripe Webhook受信サーバー。

Checkout完了後のブラウザ側リダイレクト(query param)は改ざん・タイミングのズレの
リスクがあるため会員状態の正としては使わない。会員状態(有効/解約など)は必ず
このWebhookが受け取るStripeからのサーバー間通知を正として core/members_db.py
に反映する。

Streamlit本体とは別プロセスで動かし、Caddyが /webhook/* をここへプロキシする
（Caddyfile参照）。stdlib のみで動かし、依存を増やさない。
"""

from __future__ import annotations

import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import stripe
from dotenv import load_dotenv

from core.members_db import get_member_by_customer_id, upsert_member

load_dotenv()

_ACTIVE_LIKE_EVENTS = {"customer.subscription.updated", "customer.subscription.created", "customer.subscription.deleted"}


def _resolve_email_for_customer(customer_id: str | None) -> str | None:
    if not customer_id:
        return None
    member = get_member_by_customer_id(customer_id)
    if member:
        return member.email
    try:
        customer = stripe.Customer.retrieve(customer_id)
        return customer.to_dict().get("email")
    except stripe.error.StripeError:
        return None


def handle_event(event: dict) -> None:
    # StripeObjectは dict の .get() を持たないため、素の dict に変換してから読む。
    event_type = event["type"]
    obj = event["data"]["object"].to_dict()

    if event_type == "checkout.session.completed":
        email = obj.get("client_reference_id") or (obj.get("customer_details") or {}).get("email")
        if not email:
            return
        upsert_member(
            email,
            stripe_customer_id=obj.get("customer"),
            stripe_subscription_id=obj.get("subscription"),
            subscription_status="active",
        )

    elif event_type in _ACTIVE_LIKE_EVENTS:
        customer_id = obj.get("customer")
        email = _resolve_email_for_customer(customer_id)
        if not email:
            return
        upsert_member(
            email,
            stripe_customer_id=customer_id,
            stripe_subscription_id=obj.get("id"),
            subscription_status=obj.get("status"),
        )


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args) -> None:  # noqa: A002 - stdlib signature
        pass

    def do_GET(self) -> None:
        if self.path == "/webhook/health":
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"ok")
            return
        self.send_response(404)
        self.end_headers()

    def do_POST(self) -> None:
        if self.path != "/webhook/stripe":
            self.send_response(404)
            self.end_headers()
            return

        webhook_secret = os.environ.get("STRIPE_WEBHOOK_SECRET")
        if not webhook_secret:
            self.send_response(500)
            self.end_headers()
            self.wfile.write(b"STRIPE_WEBHOOK_SECRET is not configured")
            return

        length = int(self.headers.get("Content-Length", 0))
        payload = self.rfile.read(length)
        sig_header = self.headers.get("Stripe-Signature", "")

        try:
            event = stripe.Webhook.construct_event(payload, sig_header, webhook_secret)
        except (ValueError, stripe.error.SignatureVerificationError) as exc:
            self.send_response(400)
            self.end_headers()
            self.wfile.write(str(exc).encode("utf-8"))
            return

        try:
            handle_event(event)
        except Exception as exc:  # noqa: BLE001 - Stripeへは200を返しリトライ地獄を避ける
            print(f"[webhook] error handling {event.get('type')}: {exc}")

        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"{}")


def main() -> None:
    stripe.api_key = os.environ.get("STRIPE_SECRET_KEY", "")
    port = int(os.environ.get("WEBHOOK_PORT", "8502"))
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"Stripe webhook server listening on :{port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
