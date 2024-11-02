import hashlib
from datetime import datetime
import json
import os
from typing import Dict, Optional, List
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

class CustomerManager:
    def __init__(self, config_path: str = "config/customers.json"):
        """
        顧客管理クラスの初期化
        Args:
            config_path: 顧客設定ファイルのパス
        """
        self.config_path = config_path
        self.customers = self._load_customers()
        
    def _load_customers(self) -> Dict[str, Dict]:
        """顧客設定ファイルの読み込み"""
        try:
            config_dir = os.path.dirname(self.config_path)
            if not os.path.exists(config_dir):
                os.makedirs(config_dir)
                
            if os.path.exists(self.config_path):
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            return {}
        except Exception as e:
            logger.error(f"Error loading customer config: {e}")
            return {}

    def _save_customers(self) -> None:
        """顧客設定の保存"""
        try:
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(self.customers, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Error saving customer config: {e}")

    def generate_customer_id(self, domain: str) -> str:
        """
        ドメインからcustomer_idを生成
        Args:
            domain: 顧客のドメイン名
        Returns:
            生成されたcustomer_id
        """
        # ドメインをベースにハッシュを生成
        domain_hash = hashlib.sha256(domain.encode()).hexdigest()[:8]
        # 読みやすい形式でIDを生成（例：CUST_example_com_a1b2c3d4）
        return f"CUST_{domain.replace('.', '_')}_{domain_hash}"

    def register_customer(self, domain: str, email: str, organization: str = "") -> str:
        """
        新規顧客の登録
        Args:
            domain: 顧客のドメイン名
            email: 顧客の連絡先メールアドレス
            organization: 組織名（オプション）
        Returns:
            生成されたcustomer_id
        """
        customer_id = self.generate_customer_id(domain)
        
        if customer_id not in self.customers:
            self.customers[customer_id] = {
                "domain": domain,
                "email": email,
                "organization": organization,
                "registered_at": datetime.now().isoformat(),
                "last_updated": datetime.now().isoformat(),
                "active": True
            }
            self._save_customers()
            logger.info(f"Registered new customer: {customer_id} for domain: {domain}")
        
        return customer_id

    def get_customer_by_domain(self, domain: str) -> Optional[Dict]:
        """
        ドメインから顧客情報を取得
        Args:
            domain: 顧客のドメイン名
        Returns:
            顧客情報（存在しない場合はNone）
        """
        for customer_id, info in self.customers.items():
            if info["domain"] == domain:
                return {"customer_id": customer_id, **info}
        return None

    def get_all_active_customers(self) -> List[Dict]:
        """
        アクティブな顧客一覧の取得
        Returns:
            アクティブな顧客情報のリスト
        """
        return [
            {"customer_id": cid, **info}
            for cid, info in self.customers.items()
            if info.get("active", True)
        ]

    def update_customer(self, customer_id: str, **kwargs) -> bool:
        """
        顧客情報の更新
        Args:
            customer_id: 更新対象の顧客ID
            **kwargs: 更新するフィールドと値
        Returns:
            更新成功の場合True
        """
        if customer_id in self.customers:
            self.customers[customer_id].update(kwargs)
            self.customers[customer_id]["last_updated"] = datetime.now().isoformat()
            self._save_customers()
            logger.info(f"Updated customer: {customer_id}")
            return True
        return False

    def deactivate_customer(self, customer_id: str) -> bool:
        """
        顧客の無効化
        Args:
            customer_id: 無効化する顧客ID
        Returns:
            無効化成功の場合True
        """
        if customer_id in self.customers:
            self.customers[customer_id]["active"] = False
            self.customers[customer_id]["last_updated"] = datetime.now().isoformat()
            self._save_customers()
            logger.info(f"Deactivated customer: {customer_id}")
            return True
        return False