# 競馬予想Webアプリ（MVP）

初心者向け競馬予想Webアプリ。開催日・競馬場・レース番号を選ぶだけで、過去5年の
傾向データと出走馬データを照合し、1着適合率・複勝率のスコア、本命馬、おすすめの
穴馬、おすすめ馬券（回収率×的中率バランス、30点以内）、初心者向けの買い目を
提示する。PWA対応、Stripeによる会員登録、予想実績の自動集計ページを持つ。

## 現在の状態

- 過去5年データ、当日の出走馬データはいずれも **ダミーデータ** で動作する
  （`core/history_source.py`, `core/mock_data.py`）。
- JRA-VAN（JV-Link）等の実データ連携は未実装。`core/data_source.py` の
  `EntryDataSource` を実装した別クラスに差し替えることで接続できる設計にしてある。
  会員登録が必要なため対応は最後に回す方針。
- Stripe連携は「メールアドレスでCheckout→サブスク登録→Billing Portalで管理」を
  実装済み。**本命馬のみ無料、それ以外（おすすめ馬券・おすすめの穴馬・買い目提案・
  出走馬一覧スコア表）は会員限定**で実際に機能ロックしている（`app.py` の
  `is_member` 判定）。
- 「おすすめ馬券」はHarville式の着順確率モデル（`core/probability.py`）で見積もった
  的中率と、出走馬のオッズから見積もった回収率のバランスが良い1点を、30点以内で
  選ぶ。表示会員かどうかに関わらず、予想を出すたびに「このアプリの公式予想」として
  `data/predictions.db` に記録される。
- 「過去の実績」ページ（`pages/01_過去の実績.py`、サイドバーから遷移）が、レース日を
  過ぎた予想から順にダミーの実結果（`core/result_source.py`、予想時と同じ確率モデルで
  生成）と自動照合し、会場別の回収率をグラフで表示する。JRA-VAN連携後は、この照合を
  実際のレース結果に基づくものへ差し替える想定（`core/settlement.py`）。

## 全体構成

```
                ┌─────────────┐
  ブラウザ ───▶ │   Caddy      │  :8080
                │ (static_pwa  │
                │  + proxy)    │
                └──────┬──────┘
              ┌────────┼─────────────┐
              ▼                      ▼
   /app/*  Streamlit          /webhook/*  webhook_server.py
           :8501 (baseUrlPath=app)         :8502
              │                              │
              └───────────┬──────────────────┘
                           ▼
                  data/members.db (SQLite)
                           ▲
                           │ Webhookイベント
                        Stripe
```

- **Caddy**: `static_pwa/`（manifest.json・Service Worker・アイコン・ラッパー
  `index.html`）を配信しつつ、`/app/*` はStreamlit、`/webhook/*` はWebhook受信
  サーバーへプロキシする。Streamlit本体やそのパッケージ内部ファイルは一切変更
  していない（`pip install --upgrade streamlit` しても壊れない）。
- **ラッパーindex.html**: `<link rel="manifest">` とService Worker登録を持つ
  静的ページが、実際のアプリ（Streamlit）を同一オリジンの `/app/` に`iframe`で
  埋め込む。これによりStreamlit側を一切変更せずにPWA化している。
- **webhook_server.py**: StripeのWebhookを受信し、署名検証の上で
  `data/members.db` の会員状態を更新する。Checkout完了後のブラウザ側リダイレクト
  (`?checkout=success`)は改ざん耐性がないため状態確定には使わず、あくまで
  Webhook経由の更新のみを正としている。

## セットアップ

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

Caddyが未インストールの場合:

```bash
winget install CaddyServer.Caddy
```

### Stripeを使う場合

1. `.env.example` を `.env` にコピーし、Stripeダッシュボード（テストモード）で
   発行した値を埋める（`STRIPE_SECRET_KEY` / `STRIPE_PRICE_ID`）。
2. ローカルでWebhookを受け取るには [Stripe CLI](https://stripe.com/docs/stripe-cli)
   を使う。

   ```bash
   stripe listen --forward-to localhost:8080/webhook/stripe
   ```

   表示された `whsec_...` を `.env` の `STRIPE_WEBHOOK_SECRET` に設定する。

Stripeキーを設定しなくてもアプリ自体は起動・動作する（会員登録ボタンを押すと
「未設定です」というエラーメッセージが出るだけで、予想機能には影響しない）。

## 起動（ローカル、Caddy経由でPWAとして）

3つのプロセスを起動する。

```bash
# 1. Streamlit本体（Caddyの背後で動くのでbaseUrlPathを合わせる）
streamlit run app.py --server.port 8501 --server.baseUrlPath app

# 2. Stripe Webhook受信サーバー
python webhook_server.py

# 3. Caddy（静的PWA配信 + 上記2つへのリバースプロキシ）
caddy run --config Caddyfile
```

ブラウザで `http://localhost:8080` を開く。スマートフォンのブラウザでは
「ホーム画面に追加」からインストールできる（PWAのインストール判定は
localhostであればHTTPS無しでも有効）。

Streamlitだけを単体で確認したい場合（PWA機能なし）は `streamlit run app.py`
だけでも起動できる。

## 本番デプロイ（Render / Vercel想定）

- Caddyがドメイン名を検出すると自動でHTTPS証明書を取得する
  （Caddyfile冒頭の `:8080` を実際のドメインに変更する）。
- Streamlit・webhook_server・CaddyをそれぞれRenderの1サービスずつ、または
  1コンテナ内でプロセスを束ねて動かす（構成はデプロイ先の制約に応じて調整）。
- StripeのWebhookエンドポイントには本番ドメインの `https://<domain>/webhook/stripe`
  を登録し、発行された署名シークレットを `STRIPE_WEBHOOK_SECRET` に設定する。

## 構成

```
app.py                     Streamlit UI本体（予想結果・会員登録サイドバー）
webhook_server.py          Stripe Webhook受信（stdlib httpのみ、依存追加なし）
Caddyfile                  リバースプロキシ + 静的PWA配信の設定
static_pwa/                manifest.json / sw.js / offline.html / icons / ラッパーindex.html
scripts/generate_icons.py  PWAアイコン(プレースホルダー)生成スクリプト

core/models.py             ドメインモデル・属性分類ロジック
core/mock_data.py          出走馬ダミーデータ生成（将来JRA-VANに差し替え）
core/data_source.py        出走馬データ取得の抽象化
core/history_source.py     過去5年傾向データ（ダミー）
core/scoring.py            1着適合率・複勝率のスコアリング
core/underdog.py           おすすめの穴馬の選定
core/bet_recommendation.py 堅実タイプ / 荒れ狙いタイプの買い目提案
core/probability.py        Harville式の着順確率モデル
core/payout_model.py       オッズ→払戻倍率のおおまかな換算式（見積もりと実績生成で共有）
core/recommended_ticket.py おすすめ馬券（回収率×的中率バランス、30点以内）の選定
core/result_source.py      ダミー実結果の生成（将来JRA-VANに差し替え）
core/settlement.py         予想馬券と実結果の照合・回収率確定
core/predictions_db.py     予想履歴のSQLite永続化・会場別集計
core/billing.py            Stripe Checkout / Billing Portalセッション作成
core/members_db.py         会員（サブスクリプション状態）のSQLite永続化

pages/01_過去の実績.py      過去の予想と的中実績（会場別回収率グラフ）
```

## 今後

- JRA-VAN（JV-Link）連携（会員登録の仕組みが整ったので次に着手）。連携後は
  `core/history_source.py` / `core/mock_data.py`（過去データ・出走馬）に加えて
  `core/result_source.py`（レース結果）も実データに差し替える
