import argparse
import sys
import logging
from pathlib import Path
from typing import Optional
from dmarc_analyzer import DMARCAnalyzer
from customer_manager import CustomerManager

# ロギング設定
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def setup_argparse() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description='DMARC Report Analyzer'
    )
    
    # 既存の引数に加えて、以下を追加
    parser.add_argument(
        '--xml-file',
        type=str,
        help='処理するXMLファイルのパス'
    )
        
    
    parser.add_argument(
        '--domain',
        type=str,
        help='解析対象のドメイン（例：example.com）'
    )
    
    parser.add_argument(
        '--list-customers',
        action='store_true',
        help='登録済み顧客の一覧を表示'
    )
    
    parser.add_argument(
        '--report-dir',
        type=str,
        default='/app/reports',
        help='DMARCレポートが格納されているディレクトリ'
    )
    
    parser.add_argument(
        '--extract-dir',
        type=str,
        default='/app/files/extracted',
        help='一時的な展開用ディレクトリ'
    )
    
    parser.add_argument(
        '--es-url',
        type=str,
        default='http://elasticsearch:9200',
        help='ElasticsearchのURL'
    )
    
    parser.add_argument(
        '--all-customers',
        action='store_true',
        help='全ての登録済み顧客のレポートを解析'
    )

    return parser

def list_customers(customer_manager: CustomerManager) -> None:
    """登録済み顧客の一覧表示"""
    customers = customer_manager.get_all_active_customers()
    if not customers:
        print("登録済みの顧客はありません。")
        return

    print("\n登録済み顧客一覧:")
    print("-" * 80)
    print(f"{'顧客ID':<30} {'ドメイン':<20} {'組織名':<20} {'状態'}")
    print("-" * 80)
    
    for customer in customers:
        status = "有効" if customer.get("active", True) else "無効"
        print(f"{customer['customer_id']:<30} "
              f"{customer['domain']:<20} "
              f"{customer['organization'][:20]:<20} "
              f"{status}")
    print("-" * 80)

def process_single_domain(args) -> None:
    """単一ドメインの処理"""
    try:
        # 環境変数からドメイン名を取得（デフォルトでexample.comを指定）
        domain = os.getenv('DOMAIN', 'example.com')
        
        # 環境変数でドメインが指定されている場合のみサブディレクトリを作成
        report_dir = Path(args.report_dir)
        extract_dir = Path(args.extract_dir)
        
        # 必要であればディレクトリを作成
        report_dir.mkdir(parents=True, exist_ok=True)
        extract_dir.mkdir(parents=True, exist_ok=True)
        
        analyzer = DMARCAnalyzer(
            report_directory=str(report_dir),
            extract_directory=str(extract_dir),
            es_url=args.es_url,
            domain=domain
        )
        
        logger.info(f"Processing reports for domain: {domain}")
        analyzer.analyze_reports()
        logger.info(f"Completed processing for domain: {domain}")
        
    except Exception as e:
        logger.error(f"Error processing domain {domain}: {e}")
        raise

def main() -> None:
    """メイン処理"""
    parser = setup_argparse()
    args = parser.parse_args()
    
    
    try:
        # XMLファイルの直接処理
        if args.xml_file:
            if not os.path.exists(args.xml_file):
                logger.error(f"指定されたXMLファイルが見つかりません: {args.xml_file}")
                return
                
            analyzer = DMARCAnalyzer(
                report_directory="/app/reports",
                extract_directory="/app/files/extracted",
                es_url=args.es_url,
                domain=args.domain or "unknown"
            )
            
            analyzer.process_xml_file(args.xml_file)
            logger.info("XMLファイルの処理が完了しました")
            return
    
        # 顧客一覧の表示
        if args.list_customers:
            list_customers(customer_manager)
            return

        # 全顧客の処理
        if args.all_customers:
            customers = customer_manager.get_all_active_customers()
            if not customers:
                logger.error("処理対象の顧客が見つかりません")
                return
                
            for customer in customers:
                try:
                    process_single_domain(customer['domain'], args)
                except Exception as e:
                    logger.error(f"Error processing {customer['domain']}: {e}")
                    continue
            
            logger.info("全ての顧客の処理が完了しました")
            return

        # 単一ドメインの処理
        if args.domain:
            process_single_domain(args.domain, args)
            return

        # 引数が不足している場合
        parser.print_help()
        sys.exit(1)

    except Exception as e:
        logger.error(f"実行中にエラーが発生しました: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()