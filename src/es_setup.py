from elasticsearch import Elasticsearch
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

def setup_elasticsearch_indices(es: Elasticsearch):
    """Elasticsearchのインデックス設定"""
    try:
        # 集計レポート用インデックステンプレート
        aggregate_template = {
            "index_patterns": ["aggregate_reports-*"],
            "settings": {
                "number_of_shards": 1,
                "number_of_replicas": 0
            },
            "mappings": {
                "properties": {
                    "customer_id": {"type": "keyword"},
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
                    "header_from": {"type": "keyword"},
                    "envelope_from": {"type": "keyword"},
                    "envelope_to": {"type": "keyword"},
                    "email_count": {"type": "integer"},
                    "dkim_pass_rate": {"type": "float"},
                    "spf_pass_rate": {"type": "float"},
                    "total_pass_rate": {"type": "float"}
                }
            }
        }

        # フォレンジックレポート用インデックステンプレート
        forensic_template = {
            "index_patterns": ["forensic_reports-*"],
            "settings": {
                "number_of_shards": 1,
                "number_of_replicas": 0
            },
            "mappings": {
                "properties": {
                    "customer_id": {"type": "keyword"},
                    "arrival_date": {"type": "date"},
                    "analyzed_at": {"type": "date"},
                    "report_id": {"type": "keyword"},
                    "original_mail_date": {"type": "date"},
                    "source_ip": {"type": "ip"},
                    "auth_results": {
                        "properties": {
                            "dkim": {"type": "keyword"},
                            "spf": {"type": "keyword"},
                            "dmarc": {"type": "keyword"}
                        }
                    },
                    "envelope_to": {"type": "keyword"},
                    "envelope_from": {"type": "keyword"},
                    "header_from": {"type": "keyword"},
                    "reported_domain": {"type": "keyword"}
                }
            }
        }

        # テンプレートの作成
        es.indices.put_template(name="dmarc_aggregate", body=aggregate_template)
        es.indices.put_template(name="dmarc_forensic", body=forensic_template)
        logger.info("Successfully created index templates")

        # 初期インデックスの作成
        current_month = datetime.now().strftime("%Y.%m")
        aggregate_index = f"aggregate_reports-{current_month}"
        forensic_index = f"forensic_reports-{current_month}"

        if not es.indices.exists(index=aggregate_index):
            es.indices.create(index=aggregate_index)
            logger.info(f"Created initial aggregate index: {aggregate_index}")

        if not es.indices.exists(index=forensic_index):
            es.indices.create(index=forensic_index)
            logger.info(f"Created initial forensic index: {forensic_index}")

        # エイリアスの設定
        alias_actions = [
            {"add": {"index": "aggregate_reports-*", "alias": "dmarc_aggregate_all"}},
            {"add": {"index": "forensic_reports-*", "alias": "dmarc_forensic_all"}}
        ]
        
        es.indices.update_aliases(body={"actions": alias_actions})
        logger.info("Successfully set up aliases")



    except Exception as e:
        logger.error(f"Error setting up Elasticsearch: {e}")
        raise