import json
import os
from pathlib import Path
from typing import Dict, List, Optional, Any
from django.conf import settings

# Define paths
BASE_DIR = Path(settings.BASE_DIR)
SETTINGS_LOGS_DIR = BASE_DIR / "settings" / "logs"
SAPO_CONFIG_FILE = SETTINGS_LOGS_DIR / "sapo_config.env"
SHOPEE_SHOPS_FILE = SETTINGS_LOGS_DIR / "shopee_shops.json"
COOKIE_DIR = SETTINGS_LOGS_DIR / "raw_cookie"

class SapoConfigService:
    @staticmethod
    def get_config() -> Dict[str, str]:
        """
        Read Sapo configuration from sapo_config.env
        Returns a dictionary of key-value pairs.
        """
        config = {}
        if SAPO_CONFIG_FILE.exists():
            with open(SAPO_CONFIG_FILE, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    key, value = line.split("=", 1)
                    config[key.strip()] = value.strip()
        return config

    @staticmethod
    def save_config(data: Dict[str, str]) -> None:
        """
        Save Sapo configuration to sapo_config.env
        """
        SETTINGS_LOGS_DIR.mkdir(parents=True, exist_ok=True)
        
        # Load existing to preserve comments or order if needed? 
        # For now, just rewrite or append. Simple rewrite is safer for consistency.
        
        lines = []
        for key, value in data.items():
            lines.append(f"{key}={value}")
        
        with open(SAPO_CONFIG_FILE, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

class ShopeeConfigService:
    @staticmethod
    def get_shops() -> List[Dict[str, Any]]:
        """
        Read shops from shopee_shops.json
        """
        if not SHOPEE_SHOPS_FILE.exists():
            return []
        
        try:
            with open(SHOPEE_SHOPS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("shops", [])
        except json.JSONDecodeError:
            return []

    @staticmethod
    def get_shop_by_name(name: str) -> Optional[Dict[str, Any]]:
        shops = ShopeeConfigService.get_shops()
        for shop in shops:
            if shop.get("name") == name:
                return shop
        return None

    @staticmethod
    def get_cookie_content(shop_name: str) -> str:
        """
        Read cookie content for a specific shop.
        """
        cookie_file = COOKIE_DIR / f"{shop_name}.txt"
        if not cookie_file.exists():
            return ""
        
        with open(cookie_file, "r", encoding="utf-8") as f:
            return f.read()

    @staticmethod
    def save_cookie_content(shop_name: str, content: str) -> None:
        """
        Save cookie content for a specific shop.
        """
        try:
            # Tạo thư mục nếu chưa tồn tại
            COOKIE_DIR.mkdir(parents=True, exist_ok=True)
            
            # Cấp quyền ghi cho thư mục (nếu có thể)
            try:
                os.chmod(COOKIE_DIR, 0o775)  # rwxrwxr-x
            except (OSError, PermissionError):
                # Không thể chmod, bỏ qua (có thể cần sudo)
                pass
            
            cookie_file = COOKIE_DIR / f"{shop_name}.txt"
            
            # Normalize content (remove extra newlines, ensure format?)
            # For now, save as is, but maybe strip empty lines at start/end
            content = content.strip()
            
            with open(cookie_file, "w", encoding="utf-8") as f:
                f.write(content)
            
            # Cấp quyền ghi cho file (nếu có thể)
            try:
                os.chmod(cookie_file, 0o664)  # rw-rw-r--
            except (OSError, PermissionError):
                # Không thể chmod, bỏ qua
                pass
                
        except PermissionError as e:
            raise PermissionError(
                f"Không có quyền ghi vào {COOKIE_DIR}. "
                f"Vui lòng chạy lệnh: sudo chmod -R 775 {COOKIE_DIR} && sudo chown -R www-data:www-data {COOKIE_DIR}"
            ) from e
