#!/bin/bash

# コンテナとボリュームを停止・削除
docker-compose down -v

# イメージを再ビルド
docker-compose build --no-cache

# 起動
docker-compose up -d

# ログの確認
docker-compose logs -f dmarc_analyzer