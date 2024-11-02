# DMARCデータを完全にリセットするスクリプト

# 1. 既存のコンテナとボリュームを停止・削除
docker-compose down --volumes

# 2. すべてのボリュームを確実に削除
docker volume rm dmarc_analyzer_dmarc_data
docker volume rm dmarc_analyzer_grafana_storage


# 3. キャッシュを使用せずに再ビルド
docker-compose build --no-cache

# 4. 新しいボリュームでコンテナを起動
docker-compose up -d

# 5. 数秒待機してからログを表示（コンテナの起動を待つ）
Start-Sleep -Seconds 5
docker-compose logs -f dmarc_analyzer