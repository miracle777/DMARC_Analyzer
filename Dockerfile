FROM python:3.9-slim

# 必要なパッケージをインストール（sqlite3を追加）
RUN apt-get update && apt-get install -y \
    unzip \
    build-essential \
    sqlite3 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# requirements.txtをコピーしてインストール
COPY src/requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

# ソースコードをコピー
COPY src /app

# データベースディレクトリを作成
RUN mkdir -p /var/lib/dmarc

ENV PYTHONUNBUFFERED=1