# core/shopee_client/cookie_manager.py
"""
Shopee Cookie Manager - Quản lý cookies cho multi-shop.
"""

from pathlib import Path
from typing import Dict, Optional
import logging

logger = logging.getLogger(__name__)


class ShopeeCookieManager:
    """
    Quản lý cookies cho Shopee shops.
    Mỗi shop có 1 file cookie riêng trong logs/raw_cookie/
    """
    
    def __init__(self, cookie_dir: str = "logs/raw_cookie"):
        """
        Args:
            cookie_dir: Directory chứa cookie files
        """
        self.cookie_dir = Path(cookie_dir)
        
        if not self.cookie_dir.exists():
            logger.warning(f"[ShopeeCookieManager] Cookie dir not found: {cookie_dir}")
            self.cookie_dir.mkdir(parents=True, exist_ok=True)
    
    def load_cookie(self, cookie_file_path: str) -> Dict[str, str]:
        """
        Load cookie từ file.
        
        Format file: Mỗi 2 dòng là 1 cặp key-value:
        ```
        accept
        application/json
        cookie
        SPC_F=...; SPC_R_T_ID=...
        ...
        ```
        
        Args:
            cookie_file_path: Đường dẫn đến cookie file (relative hoặc absolute)
            
        Returns:
            Dict của headers
        """
        file_path = Path(cookie_file_path)
        
        if not file_path.is_absolute():
            file_path = Path.cwd() / file_path
        
        if not file_path.exists():
            raise FileNotFoundError(f"Cookie file not found: {file_path}")
        
        logger.debug(f"[ShopeeCookieManager] Loading cookie from: {file_path}")
        
        with open(file_path, "r", encoding="utf-8") as f:
            raw = f.read()
        
        headers = self.parse_headers(raw)
        logger.info(f"[ShopeeCookieManager] Loaded {len(headers)} headers from '{file_path.name}'")
        
        return headers
    
    def parse_headers(self, raw_text: str) -> Dict[str, str]:
        """
        Parse raw cookie file thành dict headers.
        
        Format: 2 dòng cho 1 cặp key-value.
        
        Args:
            raw_text: Nội dung file cookie
            
        Returns:
            Dict của headers
        """
        if not raw_text:
            logger.warning("[ShopeeCookieManager] Empty raw text")
            return {}
        
        lines = [l.strip("\r") for l in raw_text.splitlines() if l.strip()]
        headers = {}
        
        it = iter(lines)
        for key in it:
            try:
                value = next(it)
                headers[key] = value
            except StopIteration:
                logger.warning(f"[ShopeeCookieManager] Missing value for key '{key}'")
                break
        
        logger.debug(f"[ShopeeCookieManager] Parsed {len(headers)} headers")
        return headers
    
    def save_cookie(self, headers: Dict[str, str], cookie_file_path: str):
        """
        Save headers vào cookie file.
        
        Args:
            headers: Dict of headers
            cookie_file_path: Path to save
        """
        file_path = Path(cookie_file_path)
        
        if not file_path.is_absolute():
            file_path = Path.cwd() / file_path
        
        file_path.parent.mkdir(parents=True, exist_ok=True)
        
        logger.debug(f"[ShopeeCookieManager] Saving cookie to: {file_path}")
        
        lines = []
        for key, value in headers.items():
            lines.append(key)
            lines.append(value)
        
        with open(file_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        
        logger.info(f"[ShopeeCookieManager] Saved {len(headers)} headers to '{file_path.name}'")
