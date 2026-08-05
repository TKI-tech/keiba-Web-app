#!/usr/bin/env bash
# コンテナ内で3プロセス(Streamlit / Webhook受信サーバー / Caddy)を起動する。
# Renderのようにサービスを1つしか立てられない環境向けの構成。
# Caddyを最後にexecしてPID 1に据えることで、コンテナへのシグナルが正しく届く。
set -euo pipefail

streamlit run app.py --server.headless true --server.port 8501 --server.baseUrlPath app &
STREAMLIT_PID=$!

python webhook_server.py &
WEBHOOK_PID=$!

cleanup() {
  kill "$STREAMLIT_PID" "$WEBHOOK_PID" 2>/dev/null || true
}
trap cleanup EXIT

exec caddy run --config Caddyfile --adapter caddyfile
