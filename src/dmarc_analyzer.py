import os
import sys
import xml.etree.ElementTree as ET
import gzip
import zipfile
from datetime import datetime
from elasticsearch import Elasticsearch, ConnectionError 
import time
import shutil
from pathlib import Path
import logging
from es_setup import setup_elasticsearch_indices
from analysis_utils import (
    calculate_authentication_rates,
    generate_report_stats,
    check_duplicate_report,
    batch_save_documents
)




# ロギング設定
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class DMARCAnalyzer:
    def __init__(self, report_directory, extract_directory, es_url, domain: str):
        """
        DMARCアナライザーの初期化
        Args:
            report_directory: レポートディレクトリのパス
            extract_directory: 展開ディレクトリのパス
            es_url: ElasticsearchのURL
            domain: 解析対象のドメイン
        """
        self.report_directory = report_directory
        self.extract_directory = extract_directory
        self.es_url = es_url
        self.processed_files = set()
        
        # 初期化を__init__で実行
        self._initialize()
        
    

    def _initialize(self):
        """初期化処理"""
        try:
            # ディレクトリの作成
            Path(self.extract_directory).mkdir(parents=True, exist_ok=True)
            logger.info(f"Extract directory created/confirmed: {self.extract_directory}")
            
            # Elasticsearchへの接続
            self._connect_elasticsearch()
            
            # インデックスの設定
            setup_elasticsearch_indices(self.es)
            logger.info("Elasticsearch indices setup completed")
            
        except Exception as e:
            logger.error(f"Initialization error: {e}")
            raise

    def _connect_elasticsearch(self):
        """Elasticsearchへの接続を確立"""
        retries = 5
        for i in range(retries):
            try:
                self.es = Elasticsearch([self.es_url])
                if self.es.ping():
                    logger.info("Successfully connected to Elasticsearch")
                    break
            except ConnectionError:
                logger.warning(f"Connection attempt {i+1} failed, retrying...")
                time.sleep(10)
            except Exception as e:
                logger.error(f"Unexpected error: {e}")
                time.sleep(10)

        if not hasattr(self, 'es') or not self.es.ping():
            raise ConnectionError("Failed to connect to Elasticsearch")

    def analyze_reports(self):
        """レポートディレクトリ内のXMLファイルを解析"""
        logger.info(f"Analyzing reports in directory: {self.report_directory}")
        
        if not os.path.exists(self.report_directory):
            logger.error(f"レポートディレクトリが存在しません: {self.report_directory}")
            return
            
        if not os.path.isdir(self.report_directory):
            logger.error(f"指定されたパスはディレクトリではありません: {self.report_directory}")
            return
            
        files = os.listdir(self.report_directory)
        logger.info(f"Found {len(files)} files in directory")
        for file in files:
            logger.info(f"Found file: {file}")
        
        try:
            for root, _, files in os.walk(self.report_directory):
                for file in files:
                    file_path = os.path.join(root, file)
                    if file.endswith(".xml"):
                        logger.info(f"Processing XML file: {file_path}")
                        self.process_report_file(file_path)
                    elif file.endswith((".zip", ".gz")):
                        logger.info(f"Extracting archive file: {file_path}")
                        extracted_files = self._extract_nested_archives(file_path, self.extract_directory)
                        for extracted_file in extracted_files:
                            if extracted_file.endswith(".xml"):
                                logger.info(f"Processing extracted XML file: {extracted_file}")
                                self.process_report_file(extracted_file)
        except Exception as e:
            logger.error(f"Error analyzing reports: {e}")
            raise

    def process_report_file(self, file_path):
        """レポートファイルの処理（ロック機能付き）"""
        lock_file = file_path + '.lock'
        if os.path.exists(lock_file):
            logger.info(f"File is being processed: {file_path}")
            return

        try:
            with open(lock_file, 'w') as f:
                f.write(str(datetime.now()))
            
            self.process_xml_file(file_path)
            
        finally:
            if os.path.exists(lock_file):
                os.remove(lock_file)

    def process_xml_file(self, xml_file_path: str) -> None:
        """XMLファイルを直接処理してElasticsearchに保存"""
        logger.info(f"XMLファイルの処理開始: {xml_file_path}")
        
        try:
            # インデックスの存在確認と作成
            current_month = datetime.now().strftime("%Y.%m")
            aggregate_index = f"aggregate_reports-{current_month}"
            forensic_index = f"forensic_reports-{current_month}"

            if not (self.es.indices.exists(index=aggregate_index) and 
                   self.es.indices.exists(index=forensic_index)):
                setup_elasticsearch_indices(self.es)
                logger.info("Created required indices")

            # XMLファイルのパース
            tree = ET.parse(xml_file_path)
            root = tree.getroot()
            
            # レポートタイプの判定
            is_forensic = False
            
            # フォレンジックレポートの特徴を確認
            if root.tag == 'feedback':
                feedback_type = root.find('feedback-type')
                if feedback_type is not None and feedback_type.text == 'failure report':
                    is_forensic = True
                elif 'forensic' in xml_file_path.lower():
                    is_forensic = True
            
            if is_forensic:
                # フォレンジックレポートの処理
                report_data = self._parse_forensic_report(root)
                if report_data:
                    self._save_forensic_report(report_data)
                    logger.info(f"フォレンジックレポートを保存しました: {xml_file_path}")
                else:
                    logger.warning(f"フォレンジックレポートのパースに失敗: {xml_file_path}")
            else:
                # 集計レポートの処理
                report_data = self._parse_aggregate_report(root)
                if report_data:
                    self._save_aggregate_report(report_data)
                    logger.info(f"集計レポートを保存しました: {xml_file_path}")
                else:
                    logger.warning(f"集計レポートのパースに失敗: {xml_file_path}")
                    
        except ET.ParseError as e:
            logger.error(f"XMLパースエラー {xml_file_path}: {e}")
        except Exception as e:
            logger.error(f"予期せぬエラー {xml_file_path}: {e}", exc_info=True)

    def _parse_aggregate_report(self, root):
        """集計レポートのパース"""
        try:
            report_metadata = root.find('report_metadata')
            if report_metadata is None:
                logger.warning("No report_metadata found in XML")
                return None

            policy_published = root.find('policy_published')
            if policy_published is None:
                logger.warning("No policy_published found in XML")
                return None

            parsed_data = {
                "org_name": report_metadata.findtext('org_name', 'unknown'),
                "report_id": report_metadata.findtext('report_id', 'unknown'),
                "report_date": None,
                "date_range": {
                    "begin": None,
                    "end": None
                },
                "policy_published": {
                    "domain": policy_published.findtext('domain', 'unknown'),
                    "adkim": policy_published.findtext('adkim', 'unknown'),
                    "aspf": policy_published.findtext('aspf', 'unknown'),
                    "p": policy_published.findtext('p', 'unknown'),
                    "sp": policy_published.findtext('sp', 'unknown'),
                    "pct": policy_published.findtext('pct', 'unknown')
                },
                "records": []
            }

            date_range = report_metadata.find('date_range')
            if date_range is not None:
                begin = date_range.findtext('begin')
                end = date_range.findtext('end')
                if begin:
                    begin_date = datetime.fromtimestamp(int(begin))
                    parsed_data['date_range']['begin'] = begin_date.isoformat()
                    parsed_data['report_date'] = begin_date.date().isoformat()
                if end:
                    parsed_data['date_range']['end'] = datetime.fromtimestamp(int(end)).isoformat()

            for record in root.findall('record'):
                row = record.find('row')
                identifiers = record.find('identifiers')
                auth_results = record.find('auth_results')
                
                if row is not None:
                    record_data = {
                        "source_ip": row.findtext('source_ip', 'unknown'),
                        "count": int(row.findtext('count', '0')),
                        "policy_evaluated": {},
                        "auth_results": {},
                        "header_from": "unknown"
                    }

                    policy_evaluated = row.find('policy_evaluated')
                    if policy_evaluated is not None:
                        record_data["policy_evaluated"] = {
                            "disposition": policy_evaluated.findtext('disposition', 'none'),
                            "dkim": policy_evaluated.findtext('dkim', 'none'),
                            "spf": policy_evaluated.findtext('spf', 'none')
                        }

                    if auth_results is not None:
                        record_data["auth_results"] = {
                            "dkim": auth_results.findtext('.//dkim/result', 'none'),
                            "spf": auth_results.findtext('.//spf/result', 'none')
                        }

                    if identifiers is not None:
                        record_data["header_from"] = identifiers.findtext('header_from', 'unknown')

                    parsed_data["records"].append(record_data)

            logger.debug(f"Parsed aggregate report data: {parsed_data}")
            return parsed_data

        except Exception as e:
            logger.error(f"Error parsing aggregate report: {e}")
            return None

    def _parse_forensic_report(self, root):
        """フォレンジックレポートのパース"""
        try:
            # 基本メタデータ
            parsed_data = {
                "@timestamp": datetime.now().isoformat(),
                "report_date": datetime.now().isoformat(),
                "feedback_type": "failure report",
                "version": root.findtext('version', '1.0'),
                "report_metadata": {
                    "org_name": root.findtext('.//org_name', 'unknown'),
                    "email": root.findtext('.//email', 'unknown'),
                    "report_id": root.findtext('.//report_id', f"FR-{int(datetime.now().timestamp())}"),
                    "date_range": datetime.now().isoformat()
                }
            }

            # Identity Alignment
            identity_alignment = root.find('identity_alignment')
            if identity_alignment is not None:
                parsed_data["identity_alignment"] = {
                    "dkim": identity_alignment.findtext('dkim', 'false').lower() == 'true',
                    "spf": identity_alignment.findtext('spf', 'false').lower() == 'true'
                }

            # Original Mail Data とIPアドレスの抽出
            original_mail = root.find('original_mail_data')
            if original_mail is not None and original_mail.text:
                import base64
                try:
                    # オリジナルのエンコーディング情報を保持
                    original_encoding = original_mail.get('encoding', 'base64')
                    
                    # Base64デコード
                    decoded_content = base64.b64decode(original_mail.text).decode('utf-8', errors='ignore')
                    
                    # デコードされたコンテンツを保存
                    parsed_data["original_mail_data"] = {
                        "content": decoded_content,
                        "encoding": original_encoding
                    }
                    
                except Exception as e:
                    logger.warning(f"Failed to decode mail content: {e}")
                    parsed_data["original_mail_data"] = {
                        "content": original_mail.text,
                        "encoding": original_mail.get('encoding', 'unknown')
                    }

            # Source Information
            source = root.find('.//source')
            if source is not None:
                ip_address = source.findtext('ip_address', '0.0.0.0')
                smtp_hostname = source.findtext('smtp_hostname', 'unknown')
                parsed_data["source"] = {
                    "ip_address": ip_address,
                    "smtp_hostname": smtp_hostname
                }
            else:
                parsed_data["source"] = {
                    "ip_address": "0.0.0.0",
                    "smtp_hostname": "unknown"
                }
                logger.warning("No source information found in report")

            # Auth Results with human readable results
            auth_results = root.find('auth_results')
            if auth_results is not None:
                parsed_data["auth_results"] = {
                    "dkim": {
                        "domain": auth_results.findtext('.//dkim/domain', 'unknown'),
                        "selector": auth_results.findtext('.//dkim/selector', 'unknown'),
                        "result": auth_results.findtext('.//dkim/result', 'none'),
                        "human_result": self._get_human_readable_result('dkim', auth_results.findtext('.//dkim/result', 'none'))
                    },
                    "spf": {
                        "domain": auth_results.findtext('.//spf/domain', 'unknown'),
                        "scope": auth_results.findtext('.//spf/scope', 'unknown'),
                        "result": auth_results.findtext('.//spf/result', 'none'),
                        "human_result": self._get_human_readable_result('spf', auth_results.findtext('.//spf/result', 'none'))
                    },
                    "dmarc": {
                        "domain": auth_results.findtext('.//dmarc/domain', 'unknown'),
                        "result": auth_results.findtext('.//dmarc/result', 'none'),
                        "human_result": self._get_human_readable_result('dmarc', auth_results.findtext('.//dmarc/result', 'none'))
                    }
                }

            # Failure Details
            failure_details = root.find('failure_details')
            if failure_details is not None:
                parsed_data["failure_details"] = {
                    "reason": failure_details.findtext('reason', 'unknown')
                }

            return parsed_data

        except Exception as e:
            logger.error(f"Error parsing forensic report: {e}", exc_info=True)
            return None

    def _get_human_readable_result(self, auth_type: str, result: str) -> str:
        """認証結果のヒューマンリーダブルな説明を生成"""
        explanations = {
            'dkim': {
                'pass': '電子署名が正常に検証されました',
                'fail': '電子署名の検証に失敗しました',
                'neutral': '検証結果は中立です',
                'none': '電子署名が見つかりませんでした'
            },
            'spf': {
                'pass': '送信元IPアドレスは承認されています',
                'fail': '送信元IPアドレスは承認されていません',
                'softfail': '送信元IPアドレスは疑わしいとマークされています',
                'neutral': '検証結果は中立です',
                'none': 'SPFレコードが見つかりませんでした'
            },
            'dmarc': {
                'pass': 'DMARCポリシーに準拠しています',
                'fail': 'DMARCポリシーに違反しています',
                'none': 'DMARCポリシーが見つかりませんでした'
            }
        }
        
        return explanations.get(auth_type, {}).get(result.lower(), '不明な結果です')

    def _parse_mail_headers(self, mail_content: str) -> dict:
        """メールヘッダーをパース"""
        if not mail_content:
            return {}

        headers = {
            'from': '',
            'to': '',
            'subject': '',
            'date': None
        }

        try:
            # メールヘッダー部分を抽出
            header_lines = []
            for line in mail_content.split('\n'):
                if line.strip() == '':
                    break
                header_lines.append(line)

            current_header = None
            current_value = ''

            for line in header_lines:
                if line.startswith(' ') or line.startswith('\t'):
                    # 継続行
                    current_value += ' ' + line.strip()
                else:
                    # 新しいヘッダー
                    if current_header:
                        if current_header.lower() in headers:
                            headers[current_header.lower()] = current_value.strip()
                    
                    if ':' in line:
                        current_header, value = line.split(':', 1)
                        current_header = current_header.lower()
                        current_value = value.strip()

            # 最後のヘッダーを処理
            if current_header and current_header.lower() in headers:
                headers[current_header.lower()] = current_value.strip()

            # 日付の変換
            if headers['date']:
                try:
                    headers['date'] = datetime.strptime(
                        headers['date'], 
                        '%a, %d %b %Y %H:%M:%S %z'
                    ).isoformat()
                except ValueError:
                    headers['date'] = None

        except Exception as e:
            logger.error(f"Error parsing mail headers: {e}")

        return headers
    
    def _is_valid_ip(self, ip_string: str) -> bool:
        """IPアドレスが有効かどうかを確認"""
        if not ip_string or ip_string.lower() == 'unknown':
            return False
            
        import re
        # 簡易的なIPv4アドレスの正規表現パターン
        pattern = r'^(\d{1,3}\.){3}\d{1,3}$'
        if not re.match(pattern, ip_string):
            return False
        
        # 各オクテットが0-255の範囲内かチェック
        try:
            return all(0 <= int(octet) <= 255 for octet in ip_string.split('.'))
        except (ValueError, AttributeError):
            return False
        

    def _save_aggregate_report(self, report):
        """集計レポートの保存"""
        try:
            if 'records' not in report:
                logger.warning("No records found in aggregate report")
                return

            # 重複チェック
            if check_duplicate_report(self.es, report['report_id']):
                logger.info(f"Skipping duplicate report: {report['report_id']}")
                return

            # 基本メタデータの準備
            base_metadata = {k: v for k, v in report.items() if k != 'records'}
            base_metadata.update({
                'analyzed_at': datetime.now().isoformat()
            })

            # 認証率の計算
            auth_rates = calculate_authentication_rates(report['records'])
            base_metadata.update(auth_rates)

            # インデックス名に日付を含める
            index_name = f"aggregate_reports-{datetime.now():%Y.%m}"

            # ドキュメントの準備
            documents = []
            for record in report['records']:
                document = {**base_metadata, **record}
                documents.append(document)

            # バッチ保存
            batch_save_documents(self.es, documents, index_name)

            # 統計情報の生成と保存
            stats = generate_report_stats(documents, report['policy_published']['domain'])
            self.es.index(
                index=f"dmarc_stats-{datetime.now():%Y.%m}",
                document={
                    'stats': stats,
                    'timestamp': datetime.now().isoformat()
                }
            )

        except Exception as e:
            logger.error(f"Error saving aggregate report: {e}")

    def _save_forensic_report(self, report):
        """フォレンジックレポートの保存"""
        try:
            current_month = datetime.now().strftime("%Y.%m")
            index_name = f"forensic_reports-{current_month}"
            
            # タイムスタンプフィールドの追加
            current_time = datetime.now()
            report.update({
                '@timestamp': current_time.isoformat(),
                'report_date': current_time.isoformat()
            })
            
            response = self.es.index(
                index=index_name,
                document=report
            )
            logger.info(f"フォレンジックレポートを保存しました: {response['result']}")
        except Exception as e:
            logger.error(f"フォレンジックレポートの保存中にエラーが発生: {e}", exc_info=True)

    def _extract_nested_archives(self, file_path, extract_dir):
        """再帰的にアーカイブを展開"""
        logger.debug(f"アーカイブの展開開始: {file_path}")
        
        try:
            temp_dir = os.path.join(
                extract_dir, 
                f"temp_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"
            )
            os.makedirs(temp_dir, exist_ok=True)
            logger.debug(f"一時ディレクトリを作成: {temp_dir}")

            extracted_files = []

            try:
                if zipfile.is_zipfile(file_path):
                    logger.debug(f"ZIPファイルの処理: {file_path}")
                    with zipfile.ZipFile(file_path, 'r') as zip_ref:
                        for file_info in zip_ref.filelist:
                            try:
                                file_name = file_info.filename
                                extracted_path = os.path.join(temp_dir, os.path.basename(file_name))
                                
                                with zip_ref.open(file_info) as source, \
                                    open(extracted_path, 'wb') as target:
                                    shutil.copyfileobj(source, target)

                                if file_name.lower().endswith(('.zip', '.gz')):
                                    nested_files = self._extract_nested_archives(extracted_path, extract_dir)
                                    extracted_files.extend(nested_files)
                                    os.remove(extracted_path)
                                elif file_name.lower().endswith('.xml'):
                                    final_path = os.path.join(extract_dir, 
                                        f"{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}_{os.path.basename(file_name)}")
                                    shutil.move(extracted_path, final_path)
                                    extracted_files.append(final_path)
                            except Exception as e:
                                logger.error(f"ZIPファイル内のファイル処理エラー {file_name}: {e}")

                elif file_path.endswith('.gz'):
                    logger.debug(f"GZファイルの処理: {file_path}")
                    output_path = os.path.join(temp_dir, 
                        f"{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}_{os.path.basename(file_path)[:-3]}")
                    
                    with gzip.open(file_path, 'rb') as f_in:
                        with open(output_path, 'wb') as f_out:
                            shutil.copyfileobj(f_in, f_out)

                    if output_path.lower().endswith('.zip'):
                        nested_files = self._extract_nested_archives(output_path, extract_dir)
                        extracted_files.extend(nested_files)
                        os.remove(output_path)
                    elif output_path.lower().endswith('.xml'):
                        final_path = os.path.join(extract_dir, os.path.basename(output_path))
                        shutil.move(output_path, final_path)
                        extracted_files.append(final_path)

                return extracted_files

            finally:
                if os.path.exists(temp_dir):
                    shutil.rmtree(temp_dir, ignore_errors=True)
                    logger.debug(f"一時ディレクトリを削除: {temp_dir}")

        except Exception as e:
            logger.error(f"アーカイブ展開エラー {file_path}: {e}")
            return []

    

if __name__ == "__main__":
    print("\n=== DMARC解析システムを起動します ===")
    logger.info("Starting DMARC Analyzer")
    
    try:
        # デフォルトドメインを環境変数から取得
        default_domain = os.getenv("DEFAULT_DOMAIN", "admin")
        logger.info(f"Using default domain: {default_domain}")
        print(f"解析対象ドメイン: {default_domain}")
            
        # DMARCAnalyzerの初期化
        analyzer = DMARCAnalyzer(
            report_directory="/app/files", 
            extract_directory="/app/files/extracted",
            es_url="http://elasticsearch:9200",
            domain=default_domain
        )
        
        # 初期の解析を実行
        print("\n🔍 初期解析を開始します...")
        analyzer.analyze_reports()
        print("✅ 初期解析が完了しました")
        logger.info("Initial DMARC analysis completed")
        
        # Grafana URLの表示
        print("\n📊 Grafanaダッシュボードにアクセスできます:")
        print("URL: http://localhost:3000")
        print("ユーザー名: admin")
        print("パスワード: admin")
        
        print("\n=== ファイル監視を開始します ===")
        print(f"監視対象ディレクトリ: /app/files")
        logger.info("Starting file monitoring")
        
        # ディレクトリの存在確認とパーミッション
        if not os.path.exists("/app/files"):
            print("❌ 監視対象ディレクトリが存在しません")
            logger.error("Monitor directory does not exist")
            os.makedirs("/app/files")
            print("✅ ディレクトリを作成しました")
            
        permissions = oct(os.stat("/app/files").st_mode)[-3:]
        print(f"📁 ディレクトリのパーミッション: {permissions}")
        
        # ディレクトリの内容を表示
        print("\n📂 現在のディレクトリ内容:")
        for root, dirs, files in os.walk("/app/files"):
            print(f"ディレクトリ: {root}")
            for d in dirs:
                print(f" - Dir: {d}")
            for f in files:
                print(f" - File: {f}")
        
            
    except Exception as e:
        logger.error(f"An error occurred: {e}", exc_info=True)
        print(f"\n❌ エラーが発生しました: {e}")
        sys.exit(1)