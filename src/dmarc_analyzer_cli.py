import argparse
import sys
import logging
from pathlib import Path
from typing import Optional
from dmarc_analyzer import DMARCAnalyzer
from customer_manager import CustomerManager
from elasticsearch import Elasticsearch




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
    
        


        # 引数が不足している場合
        parser.print_help()
        sys.exit(1)

    except Exception as e:
        logger.error(f"実行中にエラーが発生しました: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()