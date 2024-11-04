from elasticsearch import Elasticsearch
import logging
from datetime import datetime



logger = logging.getLogger(__name__)

def setup_elasticsearch_indices(es: Elasticsearch):
    """Elasticsearchのインデックス設定"""
    try:
        current_month = datetime.now().strftime("%Y.%m")
        
        # テンプレートの存在確認
        template_exists = es.indices.exists_template("dmarc_aggregate")
        if not template_exists:
            # 集計レポート用インデックステンプレート
            aggregate_template = {
                "index_patterns": ["aggregate_reports-*"],
                "settings": {
                    "number_of_shards": 1,
                    "number_of_replicas": 0
                },
                "mappings": {
                    "properties": {
                        "org_name": {"type": "keyword"},
                        "report_id": {"type": "keyword"},
                        "report_date": {"type": "date"},
                        "analyzed_at": {"type": "date"},
                        "date_range": {
                            "properties": {
                                "begin": {"type": "date"},
                                "end": {"type": "date"}
                            }
                        },
                        "policy_published": {
                            "properties": {
                                "domain": {"type": "keyword"},
                                "adkim": {"type": "keyword"},
                                "aspf": {"type": "keyword"},
                                "p": {"type": "keyword"},
                                "sp": {"type": "keyword"},
                                "pct": {"type": "integer"}
                            }
                        },
                        "source_ip": {"type": "ip"},
                        "count": {"type": "integer"},
                        "policy_evaluated": {
                            "properties": {
                                "disposition": {"type": "keyword"},
                                "dkim": {"type": "keyword"},
                                "spf": {"type": "keyword"}
                            }
                        },
                        "auth_results": {
                            "properties": {
                                "dkim": {"type": "keyword"},
                                "spf": {"type": "keyword"}
                            }
                        },
                        "header_from": {"type": "keyword"}
                    }
                }
            }
            
            # テンプレート作成前にログを追加
            logger.info("Creating aggregate template...")
            es.indices.put_template(name="dmarc_aggregate", body=aggregate_template)
            logger.info("Created aggregate template successfully")


       # インデックスの作成前にログを追加
        logger.info(f"Checking for index: aggregate_reports-{current_month}")
        aggregate_index = f"aggregate_reports-{current_month}"
        
        # インデックスの存在確認と作成を明示的に分離
        index_exists = es.indices.exists(index=aggregate_index)
        if not index_exists:
            logger.info(f"Creating new index: {aggregate_index}")
            es.indices.create(index=aggregate_index)
            logger.info(f"Successfully created index: {aggregate_index}")
        else:
            logger.info(f"Index already exists: {aggregate_index}")
            
        # インデックスのマッピングを確認
        mapping = es.indices.get_mapping(index=aggregate_index)
        logger.info(f"Current mapping for {aggregate_index}: {mapping}")

    except Exception as e:
        logger.error(f"Error setting up Elasticsearch indices: {str(e)}")
        logger.exception("Detailed error information:")
        raise