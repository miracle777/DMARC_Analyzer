from datetime import datetime, timedelta
from typing import Dict, List, Any
import logging
from elasticsearch import helpers 
from elasticsearch import Elasticsearch

def get_domain_from_policy():
    # Initialize Elasticsearch client
    es = Elasticsearch("http://localhost:9200")  # Adjust this URL if necessary

    # Perform search to get the `policy_published.domain` field
    response = es.search(
        index="aggregate_reports-*",
        body={
            "size": 1,
            "_source": ["policy_published.domain"],
            "query": {
                "match_all": {}
            }
        }
    )

    # Extract domain from response
    hits = response.get('hits', {}).get('hits', [])
    if hits:
        domain = hits[0].get('_source', {}).get('policy_published', {}).get('domain', "default.com")
    else:
        domain = "default.com"  # Default domain if not found

    return domain


logger = logging.getLogger(__name__)

def calculate_authentication_rates(records: List[Dict[str, Any]]) -> Dict[str, float]:
    """認証率の計算"""
    total_count = sum(record.get('count', 0) for record in records)
    if total_count == 0:
        return {
            'dkim_pass_rate': 0.0,
            'spf_pass_rate': 0.0,
            'total_pass_rate': 0.0
        }

    dkim_pass = sum(record.get('count', 0) 
                   for record in records 
                   if record.get('auth_results', {}).get('dkim') == 'pass')
    
    spf_pass = sum(record.get('count', 0) 
                  for record in records 
                  if record.get('auth_results', {}).get('spf') == 'pass')

    return {
        'dkim_pass_rate': (dkim_pass / total_count) * 100,
        'spf_pass_rate': (spf_pass / total_count) * 100,
        'total_pass_rate': ((dkim_pass + spf_pass) / (total_count * 2)) * 100
    }

def generate_report_stats(records: List[Dict[str, Any]], domain: str) -> Dict[str, Any]:
    """レポート統計の生成"""
    stats = {
        'domain': domain,
        'total_messages': sum(record.get('count', 0) for record in records),
        'unique_sources': len(set(record.get('source_ip') for record in records)),
        'authentication_results': calculate_authentication_rates(records),
        'period': {
            'start': min(record.get('date_range', {}).get('begin') for record in records),
            'end': max(record.get('date_range', {}).get('end') for record in records)
        }
    }

    return stats

def check_duplicate_report(es, report_id: str, customer_id: str) -> bool:
    """重複レポートのチェック"""
    try:
        result = es.search(
            index="aggregate_reports-*",
            body={
                "query": {
                    "bool": {
                        "must": [
                            {"term": {"report_id": report_id}},
                            {"term": {"customer_id": customer_id}}
                        ]
                    }
                }
            }
        )
        return result['hits']['total']['value'] > 0
    except Exception as e:
        logger.error(f"Error checking for duplicate report: {e}")
        return False

def batch_save_documents(es, documents: List[Dict[str, Any]], index_name: str, 
                        batch_size: int = 500) -> None:
    """ドキュメントのバッチ保存"""
    try:
        if not documents:
            return

        actions = []
        for doc in documents:
            actions.append({
                "_index": index_name,
                "_source": doc
            })

            if len(actions) >= batch_size:
                helpers.bulk(es, actions)
                actions = []

        if actions:  # 残りのドキュメントを保存
            helpers.bulk(es, actions)

    except Exception as e:
        logger.error(f"Error in batch save: {e}")
        raise