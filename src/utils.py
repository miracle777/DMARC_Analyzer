
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

import xml.etree.ElementTree as ET
from datetime import datetime

def parse_aggregate_report(root):
    """Parse DMARC aggregate report"""
    try:
        # Get report metadata
        report_metadata = root.find('report_metadata')
        if report_metadata is None:
            return None

        # Convert timestamps to ISO format
        date_range = report_metadata.find('date_range')
        begin_time = None
        end_time = None
        
        if date_range is not None:
            begin_elem = date_range.find('begin')
            end_elem = date_range.find('end')
            
            if begin_elem is not None and begin_elem.text:
                try:
                    begin_time = datetime.fromtimestamp(int(begin_elem.text)).isoformat()
                except ValueError as e:
                    print(f"Error parsing begin timestamp: {e}")
            
            if end_elem is not None and end_elem.text:
                try:
                    end_time = datetime.fromtimestamp(int(end_elem.text)).isoformat()
                except ValueError as e:
                    print(f"Error parsing end timestamp: {e}")

        parsed_data = {
            "org_name": report_metadata.findtext('org_name', 'unknown'),
            "report_id": report_metadata.findtext('report_id', 'unknown'),
            "date_range": {
                "begin": begin_time,
                "end": end_time
            },
            "policy_published": {
                "domain": root.findtext('./policy_published/domain', 'unknown'),
                "adkim": root.findtext('./policy_published/adkim', 'unknown'),
                "aspf": root.findtext('./policy_published/aspf', 'unknown'),
                "p": root.findtext('./policy_published/p', 'unknown'),
                "sp": root.findtext('./policy_published/sp', 'unknown'),
                "pct": root.findtext('./policy_published/pct', 'unknown')
            },
            "records": []
        }

        # Process each record
        for record in root.findall('./record'):
            row = record.find('row')
            auth_results = record.find('auth_results')
            
            if row is None or auth_results is None:
                continue

            record_data = {
                "source_ip": row.findtext('source_ip', 'unknown'),
                "count": int(row.findtext('count', '0')),
                "policy_evaluated": {
                    "disposition": row.findtext('./policy_evaluated/disposition', 'none'),
                    "dkim": row.findtext('./policy_evaluated/dkim', 'none'),
                    "spf": row.findtext('./policy_evaluated/spf', 'none')
                },
                "auth_results": {
                    "dkim": auth_results.findtext('.//dkim/result', 'none'),
                    "spf": auth_results.findtext('.//spf/result', 'none')
                },
                "header_from": record.findtext('./identifiers/header_from', 'unknown')
            }
            
            parsed_data["records"].append(record_data)

        return parsed_data
    except Exception as e:
        print(f"Error parsing aggregate report: {e}")
        return None

def parse_forensic_report(root):
    """Parse DMARC forensic report"""
    try:
        arrival_date = None
        original_mail_date = None
        
        # 到着日時の取得（フォレンジックレポートの日時）
        arrival_date_elem = root.find('arrival-date')
        if arrival_date_elem is not None and arrival_date_elem.text:
            try:
                arrival_date = datetime.strptime(arrival_date_elem.text, 
                                               '%Y-%m-%d %H:%M:%S%z').isoformat()
            except ValueError:
                try:
                    arrival_date = datetime.strptime(arrival_date_elem.text, 
                                                   '%Y-%m-%d %H:%M:%S').isoformat()
                except ValueError as e:
                    print(f"Error parsing arrival date: {e}")

        # 元のメールの日時の取得
        original_mail_date_elem = root.find('original-mail-date')
        if original_mail_date_elem is not None and original_mail_date_elem.text:
            try:
                original_mail_date = datetime.strptime(original_mail_date_elem.text, 
                                                     '%Y-%m-%d %H:%M:%S%z').isoformat()
            except ValueError:
                try:
                    original_mail_date = datetime.strptime(original_mail_date_elem.text, 
                                                         '%Y-%m-%d %H:%M:%S').isoformat()
                except ValueError as e:
                    print(f"Error parsing original mail date: {e}")

        return {
            "envelope_to": root.findtext('envelope-to', 'unknown'),
            "envelope_from": root.findtext('envelope-from', 'unknown'),
            "header_from": root.findtext('header-from', 'unknown'),
            "arrival_date": arrival_date,
            "original_mail_date": original_mail_date,
            "reported_domain": root.findtext('reported-domain', 'unknown')
        }
    except Exception as e:
        print(f"Error parsing forensic report: {e}")
        return None