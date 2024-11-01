# DMARCデータのみをリセットするスクリプト

# コンテナを停止（ボリュームは削除しない）
docker-compose down

# DMARCデータのボリュームのみを削除
docker volume rm dmarc_analyzer_dmarc_data

# キャッシュを使用せずに再ビルド
docker-compose build --no-cache

# コンテナを起動
docker-compose up -d

# ログを表示
docker-compose logs -f dmarc_analyzer