# Streamlit本体・Stripe Webhook受信サーバー・Caddy(PWA配信+リバースプロキシ)を
# 1コンテナにまとめたデモ/本番デプロイ用イメージ。3プロセスの起動はstart.sh参照。
FROM python:3.12-slim

ARG CADDY_VERSION=2.11.4

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates \
    && curl -fsSL "https://github.com/caddyserver/caddy/releases/download/v${CADDY_VERSION}/caddy_${CADDY_VERSION}_linux_amd64.tar.gz" -o /tmp/caddy.tar.gz \
    && tar -xzf /tmp/caddy.tar.gz -C /usr/local/bin caddy \
    && chmod +x /usr/local/bin/caddy \
    && rm /tmp/caddy.tar.gz \
    && apt-get purge -y curl \
    && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN chmod +x start.sh

ENV STREAMLIT_SERVER_HEADLESS=true

EXPOSE 8080

CMD ["./start.sh"]
