"""アプリ自身の公開URLの基点を解決する（Stripeのリダイレクト先、パスワード
再設定メールのリンクなど、絶対URLを組み立てる箇所で共通利用する）。
"""

from __future__ import annotations

import os


class AppUrlNotConfiguredError(RuntimeError):
    pass


def base_url() -> str:
    """APP_BASE_URL未設定時は、Renderが自動で注入する RENDER_EXTERNAL_URL に
    フォールバックする(Render上でのデプロイをAPP_BASE_URLの手動設定なしで
    動かすため)。"""
    url = os.environ.get("APP_BASE_URL") or os.environ.get("RENDER_EXTERNAL_URL")
    if not url:
        raise AppUrlNotConfiguredError(
            "APP_BASE_URL が設定されていません。.env.example を参考に .env を用意してください。"
        )
    return url.rstrip("/")
