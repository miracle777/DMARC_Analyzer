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
from customer_manager import CustomerManager
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
        
        self.customer_manager = CustomerManager()
        customer_info = self.customer_manager.get_customer_by_domain(domain)
        
        if customer_info is None:
            self.customer_id = self.customer_manager.register_customer(
                domain=domain,
                email=f"admin@{domain}"
            )
        else:
            self.customer_id = customer_info['id']
            
        # 初期化を__init__で実行
        self._initialize()

    def analyze_reports(self):
        """レポートディレクトリ内のXMLファイルを解析"""
        logger.info(f"Analyzing reports in directory: {self.report_directory}")
        
        try:
            # レポートディレクトリ内の全ファイルを確認
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
        """レポートファイルの処理（重複チェック含む）"""
        if file_path in self.processed_files:
            logger.info(f"Skipping duplicate file: {file_path}")
            return

        self.processed_files.add(file_path)
        self.process_xml_file(file_path)

    def process_xml_file(self, xml_file_path: str) -> None:
        """XMLファイルを直接処理してElasticsearchに保存"""
        logger.info(f"XMLファイルの処理開始: {xml_file_path}")
        
        try:
            # インデックスの存在確認と作成
            current_month = datetime.now().strftime("%Y.%m")
            aggregate_index = f"aggregate_reports-{current_month}"

            if not self.es.indices.exists(index=aggregate_index):
                setup_elasticsearch_indices(self.es)
                logger.info("Created required indices")

            # XMLファイルのパース
            tree = ET.parse(xml_file_path)
            root = tree.getroot()
            
            # レポートタイプの判定とパース
            if root.tag == 'feedback':
                report_data = self._parse_aggregate_report(root)
                if report_data:
                    self._save_aggregate_report(report_data)
                    logger.info(f"集計レポートを保存しました: {xml_file_path}")
                else:
                    logger.warning(f"集計レポートのパースに失敗: {xml_file_path}")
            else:
                logger.warning(f"未対応のXMLフォーマット: {xml_file_path}")
                
        except ET.ParseError as e:
            logger.error(f"XMLパースエラー {xml_file_path}: {e}")
        except Exception as e:
            logger.error(f"予期せぬエラー {xml_file_path}: {e}")

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
   

    def _save_aggregate_report(self, report):
        """集計レポートの保存（バッチ処理対応）"""
        try:
            if 'records' not in report:
                logger.warning("No records found in aggregate report")
                return

            # 重複チェック
            if check_duplicate_report(self.es, report['report_id'], self.customer_id):
                logger.info(f"Skipping duplicate report: {report['report_id']}")
                return

            # 基本メタデータの準備
            base_metadata = {k: v for k, v in report.items() if k != 'records'}
            base_metadata.update({
                'customer_id': self.customer_id,
                'analyzed_at': datetime.now().isoformat()
            })

            # 認証率の計算
            auth_rates = calculate_authentication_rates(report['records'])
            base_metadata.update(auth_rates)

            # ドキュメントの準備
            documents = []
            for record in report['records']:
                document = {**base_metadata, **record}
                documents.append(document)

            # インデックス名に日付を含める
            index_name = f"aggregate_reports-{datetime.now():%Y.%m}"
            
            # バッチ保存
            batch_save_documents(self.es, documents, index_name)
            
            # 統計情報の生成と保存
            stats = generate_report_stats(documents, report['policy_published']['domain'])
            self.es.index(
                index=f"dmarc_stats-{datetime.now():%Y.%m}",
                document={
                    'customer_id': self.customer_id,
                    'stats': stats,
                    'timestamp': datetime.now().isoformat()
                }
            )

        except Exception as e:
            logger.error(f"Error saving aggregate report: {e}")

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

    def _extract_nested_archives(self, file_path, extract_dir):
        """再帰的にアーカイブを展開"""
        logger.debug(f"アーカイブの展開開始: {file_path}")
        
        try:
            # 一時ディレクトリの作成（ユニークな名前）
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
                        # ファイル名の文字エンコーディング対策
                        for file_info in zip_ref.filelist:
                            try:
                                file_name = file_info.filename
                                extracted_path = os.path.join(temp_dir, os.path.basename(file_name))
                                
                                # 個別にファイルを展開
                                with zip_ref.open(file_info) as source, \
                                    open(extracted_path, 'wb') as target:
                                    shutil.copyfileobj(source, target)

                                if file_name.lower().endswith(('.zip', '.gz')):
                                    # 再帰的に処理
                                    nested_files = self._extract_nested_archives(extracted_path, extract_dir)
                                    extracted_files.extend(nested_files)
                                    os.remove(extracted_path)  # 中間ファイルを削除
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
                        os.remove(output_path)  # 中間ファイルを削除
                    elif output_path.lower().endswith('.xml'):
                        final_path = os.path.join(extract_dir, os.path.basename(output_path))
                        shutil.move(output_path, final_path)
                        extracted_files.append(final_path)

                return extracted_files

            finally:
                # 一時ディレクトリの削除
                if os.path.exists(temp_dir):
                    shutil.rmtree(temp_dir, ignore_errors=True)
                    logger.debug(f"一時ディレクトリを削除: {temp_dir}")

        except Exception as e:
            logger.error(f"アーカイブ展開エラー {file_path}: {e}")
            return []

    

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

            # 基本データの取得
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

            # タイムスタンプの処理
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

            # レコードの処理
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

                    # Policy Evaluated
                    policy_evaluated = row.find('policy_evaluated')
                    if policy_evaluated is not None:
                        record_data["policy_evaluated"] = {
                            "disposition": policy_evaluated.findtext('disposition', 'none'),
                            "dkim": policy_evaluated.findtext('dkim', 'none'),
                            "spf": policy_evaluated.findtext('spf', 'none')
                        }

                    # Auth Results
                    if auth_results is not None:
                        record_data["auth_results"] = {
                            "dkim": auth_results.findtext('.//dkim/result', 'none'),
                            "spf": auth_results.findtext('.//spf/result', 'none')
                        }

                    # Header From
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
            parsed_data = {
                "arrival_date": None,
                "report_id": root.findtext('report-id', 'unknown'),
                "original_mail_date": None,
                "source_ip": root.findtext('source-ip', 'unknown'),
                "auth_results": {
                    "dkim": "none",
                    "spf": "none",
                    "dmarc": "none"
                },
                "envelope_to": root.findtext('envelope-to', 'unknown'),
                "envelope_from": root.findtext('envelope-from', 'unknown'),
                "header_from": root.findtext('header-from', 'unknown'),
                "reported_domain": root.findtext('reported-domain', 'unknown')
            }

            # 日付の処理
            arrival_date = root.findtext('arrival-date')
            if arrival_date:
                try:
                    parsed_data['arrival_date'] = datetime.strptime(arrival_date, 
                        '%Y-%m-%d %H:%M:%S%z').isoformat()
                except ValueError:
                    try:
                        parsed_data['arrival_date'] = datetime.strptime(arrival_date, 
                            '%Y-%m-%d %H:%M:%S').isoformat()
                    except ValueError as e:
                        logger.warning(f"Could not parse arrival date: {e}")

            # 元のメールの日付
            original_date = root.findtext('original-mail-date')
            if original_date:
                try:
                    parsed_data['original_mail_date'] = datetime.strptime(original_date, 
                        '%Y-%m-%d %H:%M:%S%z').isoformat()
                except ValueError:
                    try:
                        parsed_data['original_mail_date'] = datetime.strptime(original_date, 
                            '%Y-%m-%d %H:%M:%S').isoformat()
                    except ValueError as e:
                        logger.warning(f"Could not parse original mail date: {e}")

            # 認証結果の処理
            auth_results = root.find('auth-results')
            if auth_results is not None:
                parsed_data['auth_results'] = {
                    'dkim': auth_results.findtext('dkim', 'none'),
                    'spf': auth_results.findtext('spf', 'none'),
                    'dmarc': auth_results.findtext('dmarc', 'none')
                }

            logger.debug(f"Parsed forensic report data: {parsed_data}")
            return parsed_data

        except Exception as e:
            logger.error(f"Error parsing forensic report: {e}")
            return None

    def _save_aggregate_report(self, report):
        """集計レポートの保存（バッチ処理対応）"""
        try:
            if 'records' not in report:
                logger.warning("No records found in aggregate report")
                return

            # 重複チェック
            if check_duplicate_report(self.es, report['report_id'], self.customer_id):
                logger.info(f"Skipping duplicate report: {report['report_id']}")
                return

            # 基本メタデータの準備
            base_metadata = {k: v for k, v in report.items() if k != 'records'}
            base_metadata.update({
                'customer_id': self.customer_id,
                'analyzed_at': datetime.now().isoformat()
            })

            # インデックス名に日付を含める
            index_name = f"aggregate_reports-{datetime.now():%Y.%m}"

            # ドキュメントの準備
            documents = []
            for record in report['records']:
                document = {**base_metadata, **record}
                documents.append(document)

            # バッチ保存
            batch_save_documents(self.es, documents, index_name)

        except Exception as e:
            logger.error(f"Error saving aggregate report: {e}")

    def _save_forensic_report(self, report):
        """フォレンジックレポートの保存"""
        try:
            response = self.es.index(index='forensic_reports', document=report)
            logger.info(f"Saved forensic report: {response['result']}")
        except Exception as e:
            logger.error(f"Error saving forensic report: {e}")


    def process_xml_file(self, xml_file_path: str) -> None:
        """XMLファイルを直接処理してElasticsearchに保存"""
        logger.info(f"XMLファイルの処理開始: {xml_file_path}")
        
        try:
            # インデックスの存在確認と作成
            current_month = datetime.now().strftime("%Y.%m")
            aggregate_index = f"aggregate_reports-{current_month}"
            forensic_index = f"forensic_reports-{current_month}"

            if not self.es.indices.exists(index=aggregate_index):
                setup_elasticsearch_indices(self.es)
                logger.info("Created required indices")

            # XMLファイルのパース
            tree = ET.parse(xml_file_path)
            root = tree.getroot()
            
            # レポートタイプの判定とパース
            if root.tag == 'feedback':
                report_data = self._parse_aggregate_report(root)
                if report_data:
                    self._save_aggregate_report(report_data)
                    logger.info(f"集計レポートを保存しました: {xml_file_path}")
                else:
                    logger.warning(f"集計レポートのパースに失敗: {xml_file_path}")
            else:
                logger.warning(f"未対応のXMLフォーマット: {xml_file_path}")
                
        except ET.ParseError as e:
            logger.error(f"XMLパースエラー {xml_file_path}: {e}")
        except Exception as e:
            logger.error(f"予期せぬエラー {xml_file_path}: {e}")




if __name__ == "__main__":
    # 環境変数からドメインを取得
    domain = os.getenv("DOMAIN")
    if not domain:
        print("Error: DOMAIN environment variable is not set. Exiting.")
        sys.exit(1)
        
    analyzer = DMARCAnalyzer(
        report_directory="/app/files", 
        extract_directory="/app/files/extracted",
        es_url="http://elasticsearch:9200",
        domain=domain
    )
    analyzer.analyze_reports()