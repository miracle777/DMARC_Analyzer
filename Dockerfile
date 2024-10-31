# ベースイメージ
FROM python:3.9-slim

# 必要なパッケージをインストール
RUN apt-get update && apt-get install -y \
    unzip \
    build-essential \
    sqlite3 \
    && rm -rf /var/lib/apt/lists/*

# 作業ディレクトリを作成
WORKDIR /app

# requirements.txtをコピーしてインストール
COPY src/requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

# ソースコードをコピー
COPY src /app

# データベース用ディレクトリを作成し、権限を設定
RUN mkdir -p /var/lib/dmarc && \
    chmod 777 /var/lib/dmarc

# Pythonのバッファリングを無効化
ENV PYTHONUNBUFFERED=1