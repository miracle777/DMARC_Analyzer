# DMARCレポート解析ツール

## 概要
このツールは、メールサーバーから受信したDMARCレポートを解析し、視覚化するシステムです。ZIPまたはGZIP形式で圧縮されたXMLレポートを処理し、SQLiteデータベースに保存、Grafanaを使用してダッシュボード形式で表示します。

主な機能：
- DMARCレポート（ZIP/GZIP）の自動解析
- ネストされたZIPファイルの処理対応
- SPF/DKIM認証結果の分析
- 組織別のメール統計情報
- 時系列での認証状況の可視化

## システム要件
- Docker
- Docker Compose
- 約2GB以上の空きディスク容量

## インストール方法

1. リポジトリのクローン：
```bash
git clone [リポジトリURL]
cd DMARC_Analyzer
```

2. 必要なディレクトリの作成：
```bash
mkdir -p files 
```

3. システムの起動：
```bash
docker-compose build
docker-compose up -d
```

## 使用方法

### DMARCレポートの処理

1. レポートファイルの配置：
   - `files`ディレクトリにDMARCレポートファイル（.zip/.gz）を配置

2. データの更新：
```bash
# コンテナの再起動でレポートを処理
docker-compose restart dmarc_analyzer

# ログの確認
docker-compose logs -f dmarc_analyzer
```

### Grafanaダッシュボードへのアクセス

1. ブラウザで以下のURLにアクセス：
   - http://localhost:3000
   - 初期ログイン情報：
     - ユーザー名: admin
     - パスワード: admin

2. ダッシュボードの表示：
   - 左メニュー → Dashboards → DMARCレポート概要

### データの更新と保守

1. 新しいレポートの追加：
```bash
# 新しいレポートをfilesディレクトリに配置
# コンテナを再起動
docker-compose restart dmarc_analyzer
```

2. システムの完全リセット：
```bash
# すべてを停止してクリーンアップ
docker-compose down

# 再ビルドして起動
docker-compose build --no-cache
docker-compose up -d
```

### トラブルシューティング

1. データベース接続エラーの場合：
```bash
docker-compose exec dmarc_analyzer bash
sqlite3 /var/lib/dmarc/dmarc.db
.tables
```

2. ログの確認：
```bash
docker-compose logs -f dmarc_analyzer
```

3. Grafanaの再起動：
```bash
docker-compose restart grafana
```

### 異なるドメインのデータを分析する場合


# 1. 既存のコンテナを停止
docker-compose down

# 2. filesディレクトリの中身をクリア
Remove-Item .\files\* -Force

# 3. 新しいファイルを配置
Copy-Item "新しいDMARCレポート.zip" .\files\

# 4. リセットスクリプトを実行
.\reset-analysis.sh

#### PowerShellで実行する場合
.\reset-analysis.ps1

##### または個別のコマンドで実行
docker-compose down -v
docker-compose build --no-cache
docker-compose up -d
docker-compose logs -f dmarc_analyzer


## Grafanaダッシュボードの管理

### ダッシュボード構成

1. `dmarc_summary_dashboard.json`
   - 概要：DMARCレポートの概要ダッシュボード
   - 主な機能：
     - 分析対象ドメインの情報表示
     - SPF/DKIM認証結果の全体概要
     - 組織別の認証状況

2. `dmarc_daily_analysis.json`
   - 概要：単日のDMARC詳細分析用ダッシュボード
   - 主な機能：
     - 時間帯別の認証結果推移
     - 詳細なエラー分析
     - 送信元IPごとの分析

3. `dmarc_trend_analysis.json`
   - 概要：長期トレンド分析用ダッシュボード
   - 主な機能：
     - 日次の認証結果推移
     - 組織別の認証成功率トレンド
     - 週次/月次のサマリー

### ダッシュボードの更新手順

1. エクスポート：
   ```
   1. Grafana UIで対象のダッシュボードを開く
   2. 設定（⚙）アイコン → Share dashboard → Export
   3. 'Export for sharing externally' を選択
   4. 'Save to file' をクリック
   ```

2. 保存：
   - エクスポートしたJSONファイルを `grafana/dashboards/` ディレクトリに保存
   - ファイル名規則に従って保存（例：dmarc_summary_dashboard.json）

3. バージョン管理：
   - 変更内容をコミット
   - 変更履歴を記録（どのような更新を行ったか）

### ダッシュボードの説明

#### 概要ダッシュボード（dmarc_summary_dashboard.json）
- 目的：DMARCレポートの全体像を把握
- 主要パネル：
  - 分析対象ドメイン情報
  - SPF/DKIM認証結果の分布
  - 組織別メール数と認証結果

#### 単日分析ダッシュボード（dmarc_daily_analysis.json）
- 目的：特定日の詳細な認証結果分析
- 主要パネル：
  - 時間帯別認証結果グラフ
  - エラー詳細テーブル
  - 送信元IP分析

#### トレンド分析ダッシュボード（dmarc_trend_analysis.json）
- 目的：長期的な認証結果の傾向分析
- 主要パネル：
  - 日次認証結果推移
  - 組織別サマリー
  - 週次トレンドグラフ

### 注意事項
- ダッシュボードの更新時は必ずバックアップを作成
- 重要な変更は事前にテスト環境で確認
- パネルの配置や設定を変更した場合は、その内容をREADMEに反映

### トラブルシューティング
1. ダッシュボードが表示されない場合：
   ```bash
   # Grafanaコンテナの再起動
   docker-compose restart grafana
   ```

2. データが更新されない場合：
   ```bash
   # DMARCアナライザーの再実行
   ./reset-analysis.ps1
   ```

### 運用手順：
#### ダッシュボードの更新時：
1. Grafana UIでダッシュボードを編集
2. Share dashboard → Export → Save to file
3. ダウンロードしたJSONを grafana/dashboards/ に保存

#### システムの再構築時：
完全なリセットと再構築
.\reset-analysis.ps1

#### 新しい環境へのデプロイ時：
# 必要なファイルをコピー
grafana/
docker-compose.yaml
Dockerfile
src/

### Grafanaダッシュボードの管理

1. ダッシュボードのエクスポート：
   - Grafana UIで Share dashboard → Export
   - JSONファイルを `grafana/dashboards/` に保存

2. ダッシュボードの更新：
   - JSONファイルを編集または置き換え
   - システムを再起動: `docker-compose restart grafana`

3. 新しいダッシュボードの追加：
   - JSONファイルを `grafana/dashboards/` に配置
   - `grafana/provisioning/dashboards/dashboards.yaml` を必要に応じて更新

## 設定のカスタマイズ

### Docker設定の変更
`docker-compose.yaml`ファイルで以下の設定が可能：
- ポート番号の変更
- ボリュームのマウントポイント
- 環境変数の設定

### Grafanaダッシュボードのカスタマイズ
1. 新しいパネルの追加：
   - 「Add panel」→ 「Add new panel」
   - 適切なビジュアライゼーションの選択
   - SQLクエリの設定

2. 既存パネルの編集：
   - パネルのタイトルをクリック
   - 「Edit」を選択

## 注意事項
- システムを停止する場合は `docker-compose down` を使用
- データベースのバックアップは定期的に実施することを推奨
- Grafanaの初期パスワードは必ず変更してください

## ライセンス
このプロジェクトはMITライセンスの下で公開されています：

```
MIT License

Copyright (c) 2024 [あなたの名前 または プロジェクト名]

以下に定める条件に従い、本ソフトウェアおよび関連文書のファイル（以下「ソフトウェア」）の複製を取得するすべての人に対し、
ソフトウェアを無制限に扱うことを無償で許可します。これには、ソフトウェアの複製を使用、複写、変更、結合、掲載、頒布、
サブライセンス、および/または販売する権利、およびソフトウェアを提供する相手に同じことを許可する権利も無制限に含まれます。

上記の著作権表示および本許諾表示を、ソフトウェアのすべての複製または重要な部分に記載するものとします。

ソフトウェアは「現状のまま」で、明示であるか暗黙であるかを問わず、何らの保証もなく提供されます。
ここでいう保証とは、商品性、特定の目的への適合性、および権利非侵害についての保証も含みますが、それに限定されるものではありません。
作者または著作権者は、契約行為、不法行為、またはそれ以外であろうと、ソフトウェアに起因または関連し、
あるいはソフトウェアの使用またはその他の扱いによって生じる一切の請求、損害、その他の義務について
何らの責任も負わないものとします。
```

## サポートと免責事項

### サポート
- GitHub Issuesを通じて問い合わせを受け付けています
- 可能な範囲で回答やサポートを提供しますが、即時の対応や継続的なサポートを保証するものではありません
- プルリクエストや機能改善の提案も歓迎します

### 免責事項
1. 本ソフトウェアは「現状のまま」提供され、明示または黙示を問わず、いかなる種類の保証も伴いません
2. 作者は以下について一切の責任を負いません：
   - ソフトウェアの使用により生じたいかなる損害
   - データの損失や業務の中断
   - その他の商業的な損害や損失
3. 本ソフトウェアを使用する場合、すべてのリスクはユーザーが負うものとします
4. DMARCレポートの解析結果の正確性について、完全性を保証するものではありません
5. 重要なシステムやセキュリティに関わる判断を行う場合は、必ず他の手段での確認も併せて行ってください

### 推奨事項
- 本番環境で使用する前に、テスト環境での十分な検証を行ってください
- 定期的なデータのバックアップを推奨します
- セキュリティに関する重要な判断は、複数の情報源と手段を用いて行ってください