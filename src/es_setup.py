from elasticsearch import Elasticsearch
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

def setup_elasticsearch_indices(es: Elasticsearch):
    """Elasticsearchのインデックス設定"""
    try:
        current_month = datetime.now().strftime("%Y.%m")
        
        # 集計レポート用テンプレート (変更なし)
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

        # フォレンジックレポート用テンプレート (更新版)
        forensic_template = {
            "index_patterns": ["forensic_reports-*"],
            "settings": {
                "number_of_shards": 1,
                "number_of_replicas": 0
            },
            "mappings": {
                "properties": {
                    "@timestamp": {"type": "date"},
                    "report_date": {"type": "date"},
                    "feedback_type": {"type": "keyword"},
                    "version": {"type": "keyword"},
                    "report_metadata": {
                        "properties": {
                            "org_name": {"type": "keyword"},
                            "email": {"type": "keyword"},
                            "report_id": {"type": "keyword"},
                            "date_range": {"type": "date"}
                        }
                    },
                    "identity_alignment": {
                        "properties": {
                            "dkim": {"type": "boolean"},
                            "spf": {"type": "boolean"}
                        }
                    },
                    "failure_details": {
                        "properties": {
                            "reason": {"type": "keyword"}
                        }
                    },
                    "auth_results": {
                        "properties": {
                            "dkim": {
                                "properties": {
                                    "domain": {"type": "keyword"},
                                    "selector": {"type": "keyword"},
                                    "result": {"type": "keyword"},
                                    "human_result": {"type": "text"}
                                }
                            },
                            "spf": {
                                "properties": {
                                    "domain": {"type": "keyword"},
                                    "scope": {"type": "keyword"},
                                    "result": {"type": "keyword"},
                                    "human_result": {"type": "text"}
                                }
                            },
                            "dmarc": {
                                "properties": {
                                    "domain": {"type": "keyword"},
                                    "result": {"type": "keyword"},
                                    "human_result": {"type": "text"}
                                }
                            }
                        }
                    },
                    "source": {
                        "properties": {
                            "ip_address": {"type": "ip"},
                            "smtp_hostname": {"type": "keyword"}
                        }
                    },
                    "original_mail_data": {
                        "properties": {
                            "encoding": {"type": "keyword"},
                            "content": {"type": "text"}
                        }
                    },
                    "headers": {
                        "properties": {
                            "from": {"type": "keyword"},
                            "to": {"type": "keyword"},
                            "subject": {"type": "text"},
                            "date": {"type": "date"}
                        }
                    }
                }
            }
        }

        # テンプレートの作成または更新
        for template_name, template in [
            ("dmarc_aggregate", aggregate_template),
            ("dmarc_forensic", forensic_template)
        ]:
            logger.info(f"Creating/Updating {template_name} template...")
            es.indices.put_template(name=template_name, body=template)
            logger.info(f"Created/Updated {template_name} template successfully")

        # インデックスの存在確認と作成
        indices = [
            f"aggregate_reports-{current_month}",
            f"forensic_reports-{current_month}"
        ]
        
        for index_name in indices:
            if not es.indices.exists(index=index_name):
                logger.info(f"Creating index: {index_name}")
                es.indices.create(index=index_name)
                logger.info(f"Successfully created index: {index_name}")
            else:
                logger.info(f"Index already exists: {index_name}")
            
            # マッピングの確認
            mapping = es.indices.get_mapping(index=index_name)
            logger.info(f"Current mapping for {index_name}: {mapping}")

        return True

    except Exception as e:
        logger.error(f"Error setting up Elasticsearch indices: {str(e)}")
        logger.exception("Detailed error information:")
        raise