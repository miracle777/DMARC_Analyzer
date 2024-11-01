import os
import gzip
import zipfile
import pandas as pd
import xmltodict
import sqlite3
from datetime import datetime
import io

print("Starting DMARC analysis...")

# パス設定
DATA_PATH = './files'
DB_PATH = os.getenv('DB_PATH', '/var/lib/dmarc/dmarc.db')

# データベースディレクトリの作成
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

def extract_report_date(filename):
    """ファイル名からレポート期間の開始日を抽出"""
    try:
        # ファイル名のフォーマット: domain!start_timestamp!end_timestamp
        parts = filename.split('!')
        if len(parts) >= 3:
            # 開始時刻のタイムスタンプを使用
            timestamp = parts[-2]  # start_timestamp
            return datetime.fromtimestamp(int(timestamp)).strftime('%Y-%m-%d %H:%M:%S')
    except Exception as e:
        print(f"Error extracting date from filename {filename}: {e}")
        return datetime.now().strftime('%Y-%m-%d %H:%M:%S')

def extract_file(file_path):
    """ネストされたZIPファイルからXMLを抽出"""
    print(f"Processing file: {file_path}")
    results = []
    
    def process_zip_content(zip_content):
        """ZIPファイルの内容を処理する再帰的な関数"""
        with zipfile.ZipFile(zip_content) as z:
            for file_info in z.filelist:
                with z.open(file_info) as f:
                    content = f.read()
                    if file_info.filename.endswith('.xml'):
                        try:
                            xml_data = xmltodict.parse(content)
                            print(f"Successfully parsed XML from {file_info.filename}")
                            results.append(xml_data)
                        except Exception as e:
                            print(f"Error parsing XML from {file_info.filename}: {e}")
                    elif file_info.filename.endswith('.zip'):
                        print(f"Found nested ZIP file: {file_info.filename}")
                        process_zip_content(io.BytesIO(content))
                    elif file_info.filename.endswith('.gz'):
                        try:
                            with gzip.open(io.BytesIO(content)) as gz:
                                xml_content = gz.read()
                                xml_data = xmltodict.parse(xml_content)
                                print(f"Successfully parsed XML from gzipped file {file_info.filename}")
                                results.append(xml_data)
                        except Exception as e:
                            print(f"Error processing gzipped file {file_info.filename}: {e}")

    try:
        if file_path.endswith('.zip'):
            with open(file_path, 'rb') as f:
                process_zip_content(io.BytesIO(f.read()))
        elif file_path.endswith('.gz'):
            with gzip.open(file_path, 'rb') as f:
                content = f.read()
                results.append(xmltodict.parse(content))
    except Exception as e:
        print(f"Error processing file {file_path}: {e}")
    
    print(f"Found {len(results)} XML documents in {file_path}")
    return results

def create_database():
    """データベーステーブルの作成"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # 集計レポート用テーブル
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS dmarc_aggregate (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        organization TEXT,
        report_id TEXT,
        source_ip TEXT,
        count INTEGER,
        spf_result TEXT,
        dkim_result TEXT,
        spf_aligned TEXT,
        dkim_aligned TEXT,
        dmarc_result TEXT,
        created_at TIMESTAMP
    )
    ''')
    
    # 詳細レポート用テーブル
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS dmarc_forensic (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        source_ip TEXT,
        from_address TEXT,
        to_address TEXT,
        spf_result TEXT,
        dkim_result TEXT,
        dmarc_result TEXT,
        created_at TIMESTAMP
    )
    ''')
    
    conn.commit()
    conn.close()

def process_report(report, report_date):
    """DMARCレポートを処理"""
    try:
        if 'feedback' not in report:
            print("Warning: No feedback element in report")
            print(f"Report structure: {report.keys()}")
            return [], []

        aggregate_results = []
        forensic_results = []
        
        feedback = report['feedback']
        org_info = feedback.get('report_metadata', {})
        policy_published = feedback.get('policy_published', {})
        
        records = feedback.get('record', [])
        if isinstance(records, dict):
            records = [records]
        
        if not records:
            print("Warning: No records found in report")
            return [], []

        print(f"Processing {len(records)} records from organization: {org_info.get('org_name', 'unknown')}")

        for record in records:
            try:
                row = record.get('row', {})
                auth_results = record.get('auth_results', {})
                
                source_ip = row.get('source_ip', 'unknown')
                count = int(row.get('count', 0))
                
                spf = auth_results.get('spf', {})
                dkim = auth_results.get('dkim', {})
                
                spf_result = (spf[0] if isinstance(spf, list) else spf).get('result', 'none')
                dkim_result = (dkim[0] if isinstance(dkim, list) else dkim).get('result', 'none')
                
                dmarc_result = row.get('policy_evaluated', {}).get('disposition', 'none')
                
                aggregate_results.append({
                    'organization': org_info.get('org_name', 'unknown'),
                    'report_id': org_info.get('report_id', 'unknown'),
                    'source_ip': source_ip,
                    'count': count,
                    'spf_result': spf_result,
                    'dkim_result': dkim_result,
                    'spf_aligned': policy_published.get('aspf', 'none'),
                    'dkim_aligned': policy_published.get('adkim', 'none'),
                    'dmarc_result': dmarc_result,
                    'created_at': report_date
                })
                
                identifiers = record.get('identifiers', {})
                forensic_results.append({
                    'source_ip': source_ip,
                    'from_address': identifiers.get('header_from', 'unknown'),
                    'to_address': identifiers.get('envelope_to', 'unknown'),
                    'spf_result': spf_result,
                    'dkim_result': dkim_result,
                    'dmarc_result': dmarc_result,
                    'created_at': report_date
                })
                
            except Exception as e:
                print(f"Error processing record: {e}")
                continue

        print(f"Successfully processed {len(aggregate_results)} aggregate records")
        return aggregate_results, forensic_results
        
    except Exception as e:
        print(f"Error in process_report: {e}")
        if 'report' in locals():
            print(f"Report structure: {report.keys()}")
        return [], []

def save_to_database(aggregate_data, forensic_data):
    """データをSQLiteに保存"""
    conn = sqlite3.connect(DB_PATH)
    
    try:
        if not aggregate_data.empty:
            aggregate_data.to_sql('dmarc_aggregate', conn, if_exists='append', index=False)
            print(f"Saved {len(aggregate_data)} aggregate records to database")
        
        if not forensic_data.empty:
            forensic_data.to_sql('dmarc_forensic', conn, if_exists='append', index=False)
            print(f"Saved {len(forensic_data)} forensic records to database")
    
    except Exception as e:
        print(f"Error saving to database: {e}")
    finally:
        conn.close()

def parse_reports():
    aggregate_data = []
    forensic_data = []
    
    print(f"Looking for files in: {DATA_PATH}")
    if not os.path.exists(DATA_PATH):
        print(f"Error: Directory {DATA_PATH} does not exist")
        return pd.DataFrame(), pd.DataFrame()
    
    files = [f for f in os.listdir(DATA_PATH) if f.endswith(('.zip', '.gz'))]
    print(f"Found files: {files}")
    
    if not files:
        print("No .zip or .gz files found")
        return pd.DataFrame(), pd.DataFrame()

    for file_name in files:
        try:
            file_path = os.path.join(DATA_PATH, file_name)
            print(f"Processing: {file_path}")
            
            # ファイル名から日付を抽出
            report_date = extract_report_date(file_name)
            print(f"Extracted report date: {report_date}")
            
            for report in extract_file(file_path):
                if report:
                    agg, err = process_report(report, report_date)
                    if agg:
                        aggregate_data.extend(agg)
                    if err:
                        forensic_data.extend(err)
        except Exception as e:
            print(f"Error processing {file_name}: {e}")
            continue

    print(f"Processed {len(aggregate_data)} aggregate records and {len(forensic_data)} forensic records")
    return pd.DataFrame(aggregate_data), pd.DataFrame(forensic_data)

if __name__ == '__main__':
    try:
        print("Starting DMARC analysis...")
        
        # データベースディレクトリの作成
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
        
        # データベーステーブルの作成
        create_database()
        
        # レポートの解析
        aggregate_df, forensic_df = parse_reports()
        
        if not aggregate_df.empty or not forensic_df.empty:
            print(f"Saving {len(aggregate_df)} aggregate records and {len(forensic_df)} forensic records to database")
            save_to_database(aggregate_df, forensic_df)
            print("Data successfully saved to database")
        else:
            print("No data to save to database")
    
    except Exception as e:
        print(f"Error in main execution: {e}")
        raise