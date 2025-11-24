# core/sapo_client/client.py
"""
Sapo Client - Main client để authenticate và access Sapo APIs.
Quản lý 2 sessions riêng cho Core API và Marketplace API.
"""

import json
import time
import threading
from typing import Dict, Any, Optional
import logging

import requests
from django.utils import timezone
from django.core.cache import cache
from seleniumwire import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from core.models import SapoToken
from core.system_settings import SAPO_BASIC, SAPO_TMDT

from .repositories import SapoCoreRepository, SapoMarketplaceRepository
from .exceptions import SeleniumLoginInProgressException

logger = logging.getLogger(__name__)

# Lock key for Selenium login process
SELENIUM_LOCK_KEY = "sapo_selenium_login_lock"
SELENIUM_LOCK_TIMEOUT = 300  # 5 minutes


class SapoClient:
    """
    Main Sapo client để authenticate và truy cập Sapo APIs.
    
    Quản lý 2 sessions:
    - core_session: Cho Sapo Core API (sisapsan.mysapogo.com/admin)
    - tmdt_session: Cho Sapo Marketplace API (market-place.sapoapps.vn)
    
    Usage:
        sapo = SapoClient()
        
        # Access Core API
        orders = sapo.core.list_orders_raw(limit=50, location_id=241737)
        
        # Access Marketplace API
        mp_orders = sapo.marketplace.list_orders_raw(
            connection_ids="10925,155174",
            account_id=319911
        )
    """
    
    def __init__(self):
        """Initialize Sapo client với 2 sessions."""
        self.core_session = requests.Session()
        self.tmdt_session = requests.Session()
        
        # Add default headers cho core session (cần thiết cho API calls)
        self.core_session.headers.update({
            "x-sapo-client": "sapo-frontend-v3",
            "x-sapo-serviceid": "sapo-frontend-v3",
            "accept": "application/json, text/plain, */*",
            "content-type": "application/json;charset=UTF-8"
        })
        
        # State tracking
        self.core_initialized = False
        self.core_valid = False
        self.tmdt_loaded = False
        self.tmdt_valid = False
        
        # Repositories (lazy init)
        self._core_repo: Optional[SapoCoreRepository] = None
        self._marketplace_repo: Optional[SapoMarketplaceRepository] = None
        
        logger.debug("[SapoClient] Initialized with default headers")
    
    # ========================= TOKEN MANAGEMENT (CORE) =========================
    
    def _load_token_from_db(self) -> Optional[Dict[str, Any]]:
        """Load core token từ database."""
        logger.debug("[SapoClient] Loading core token from DB...")
        
        try:
            token = SapoToken.objects.get(key="loginss")
        except SapoToken.DoesNotExist:
            logger.debug("[SapoClient] No core token in DB")
            return None
        
        if not token.is_valid():
            logger.debug("[SapoClient] Core token expired")
            return None
        
        logger.debug(f"[SapoClient] Core token OK, expires at {token.expires_at}")
        # Extract cookies from headers if present
        headers = dict(token.headers)
        cookie_header = headers.pop("cookie", None) or headers.pop("Cookie", None)
        
        self.core_session.headers.update(headers)
        
        if cookie_header:
            cookies = {}
            for kv in cookie_header.split("; "):
                if "=" in kv:
                    k, v = kv.split("=", 1)
                    cookies[k] = v
            self.core_session.cookies.update(cookies)
        
        # Đảm bảo x-sapo-client luôn có (không bị ghi đè bởi token.headers)
        self.core_session.headers.update({
            "x-sapo-client": "sapo-frontend-v3",
            "x-sapo-serviceid": "sapo-frontend-v3",
        })
        
        return token.headers
    
    def _save_token_to_db(self, headers: Dict[str, Any], lifetime_hours: int = 6):
        """Save core token vào database."""
        logger.info("[SapoClient] Saving core token to DB")
        
        expires_at = timezone.now() + timezone.timedelta(hours=lifetime_hours)
        
        # Đảm bảo x-sapo-client luôn có trong headers trước khi save
        headers_with_sapo = dict(headers)
        headers_with_sapo.update({
            "x-sapo-client": "sapo-frontend-v3",
            "x-sapo-serviceid": "sapo-frontend-v3",
        })
        
        SapoToken.objects.update_or_create(
            key="loginss",
            defaults={
                "headers": headers_with_sapo,
                "expires_at": expires_at,
            },
        )
        self.core_session.headers.update(headers_with_sapo)
        logger.debug(f"[SapoClient] Core token saved with x-sapo-client, expires at {expires_at}")
    
    # ========================= TOKEN MANAGEMENT (MARKETPLACE) =========================
    
    def _load_tmdt_token(self) -> Optional[Dict[str, Any]]:
        """Load marketplace token từ database."""
        try:
            token = SapoToken.objects.get(key="tmdt")
        except SapoToken.DoesNotExist:
            logger.debug("[SapoClient] No marketplace token in DB")
            return None
        
        if not token.is_valid():
            logger.debug("[SapoClient] Marketplace token expired")
            return None
        
        logger.debug(f"[SapoClient] Marketplace token OK, expires at {token.expires_at}")
        return token.headers
    
    def _save_tmdt_token(self, headers: Dict[str, Any], lifetime_hours: int = 6):
        """Save marketplace token vào database."""
        logger.info("[SapoClient] Saving marketplace token to DB")
        
        expires_at = timezone.now() + timezone.timedelta(hours=lifetime_hours)
        SapoToken.objects.update_or_create(
            key="tmdt",
            defaults={
                "headers": headers,
                "expires_at": expires_at,
            },
        )
        logger.debug(f"[SapoClient] Marketplace token saved, expires at {expires_at}")
    
    def _apply_tmdt_headers_to_session(self, headers: Dict[str, Any]):
        """
        Apply marketplace headers vào tmdt_session.
        Tách cookie ra và apply riêng.
        """
        h = dict(headers)  # copy
        
        # Extract và apply cookies
        raw_cookie = h.pop("cookie", None)
        h.pop("host", None)  # requests tự set
        
        # Apply headers
        self.tmdt_session.headers.clear()
        self.tmdt_session.headers.update(h)
        
        # Apply cookies
        if raw_cookie:
            cookies = {}
            for kv in raw_cookie.split("; "):
                if "=" in kv:
                    k, v = kv.split("=", 1)
                    cookies[k] = v
            self.tmdt_session.cookies.update(cookies)
        
        logger.debug("[SapoClient] Applied marketplace headers to session")
    
    # ========================= TOKEN VALIDATION =========================
    
    def _check_token_valid_remote(self) -> bool:
        """Test core token bằng cách gọi /orders.json."""
        logger.debug("[SapoClient] Testing core token...")
        
        try:
            url_orders = f"{SAPO_BASIC.MAIN_URL}/orders.json"
            res = self.core_session.get(url_orders, params={"limit": 1}, timeout=10)
            
            if res.status_code != 200:
                logger.warning(f"[SapoClient] Invalid status {res.status_code}")
                return False
            
            if len(res.text) < 200:
                logger.warning("[SapoClient] Response too short, possible auth failure")
                return False
            
            logger.debug("[SapoClient] Core token is valid ✓")
            return True
            
        except Exception as e:
            logger.error(f"[SapoClient] Token validation error: {e}")
            return False
    
    def _check_tmdt_valid_remote(self, headers: Dict[str, Any]) -> bool:
        """Test marketplace token bằng cách gọi scopes API."""
        try:
            url = f"{SAPO_TMDT.SCOPES_URL}/api/staffs/{SAPO_TMDT.STAFF_ID}/scopes"
            res = requests.get(url, headers=headers, timeout=10)
            
            if res.status_code != 200:
                logger.warning(f"[SapoClient] Marketplace token invalid status {res.status_code}")
                return False
            
            data = res.json()
            if "sapo_account_id" not in data:
                logger.warning("[SapoClient] Missing sapo_account_id in scopes response")
                return False
            
            logger.debug("[SapoClient] Marketplace token is valid ✓")
            return True
            
        except Exception as e:
            logger.error(f"[SapoClient] Marketplace token validation error: {e}")
            return False
    
    # ========================= ENSURE AUTHENTICATION =========================
    
    def _ensure_logged_in(self):
        """Đảm bảo core session đã authenticated."""
        if self.core_valid:
            logger.debug("[SapoClient] Core session already valid")
            return
        
        if not self.core_initialized:
            logger.debug("[SapoClient] First-time init, loading core token from DB")
            headers = self._load_token_from_db()
            self.core_initialized = True
            
            if headers and self._check_token_valid_remote():
                logger.info("[SapoClient] Core session ready (from DB)")
                self.core_valid = True
                return
        
        # Need new login - check if login is already in progress
        if self._check_selenium_lock_status():
            logger.warning("[SapoClient] Selenium login already in progress")
            raise SeleniumLoginInProgressException(
                "Selenium login is currently in progress. Please wait."
            )
        
        # Start background login and raise exception to show loading page
        logger.info("[SapoClient] Starting background Selenium login")
        self._start_background_login()
        
        # Raise exception để redirect tới loading page
        raise SeleniumLoginInProgressException(
            "Starting Selenium login. Please wait."
        )
    
    def _ensure_tmdt_headers(self):
        """Đảm bảo marketplace session đã authenticated."""
        if self.tmdt_valid:
            logger.debug("[SapoClient] Marketplace session already valid")
            return
        
        headers = self._load_tmdt_token()
        
        if headers and self._check_tmdt_valid_remote(headers):
            logger.info("[SapoClient] Marketplace session ready (from DB)")
            self._apply_tmdt_headers_to_session(headers)
            self.tmdt_valid = True
            return
        
        # Need refresh - check if login is already in progress
        if self._check_selenium_lock_status():
            logger.warning("[SapoClient] Selenium login already in progress for marketplace")
            raise SeleniumLoginInProgressException(
                "Selenium login is currently in progress. Please wait."
            )
        
        # Reset core để force browser login (sẽ capture cả marketplace token)
        self.core_valid = False
        self.core_initialized = False
        
        # Start background login and raise exception
        logger.info("[SapoClient] Starting background Selenium login for marketplace")
        self._start_background_login()
        
        # Raise exception để redirect tới loading page
        raise SeleniumLoginInProgressException(
            "Starting Selenium login for marketplace. Please wait."
        )
    
    # ========================= BACKGROUND LOGIN =========================
    
    def _start_background_login(self):
        """
        Start Selenium login trong background thread.
        Thread sẽ acquire lock, login, và release lock khi hoàn tất.
        """
        def background_login_task():
            try:
                logger.info("[BackgroundLogin] Starting Selenium login...")
                core_headers = self._login_via_browser()
                self._save_token_to_db(core_headers)
                logger.info("[BackgroundLogin] Selenium login complete ✓")
            except Exception as e:
                logger.error(f"[BackgroundLogin] Login failed: {e}")
                # Release lock nếu có lỗi
                self._release_selenium_lock()
        
        # Start thread
        thread = threading.Thread(target=background_login_task, daemon=True)
        thread.start()
        logger.info("[SapoClient] Background login thread started")
    
    # ========================= SELENIUM LOCK MANAGEMENT =========================
    
    def _acquire_selenium_lock(self) -> bool:
        """
        Acquire lock để đảm bảo chỉ 1 Selenium instance chạy tại một thời điểm.
        
        Returns:
            True nếu acquire được lock, False nếu lock đang được giữ bởi process khác
        """
        # Thử set lock với timeout
        acquired = cache.add(SELENIUM_LOCK_KEY, True, SELENIUM_LOCK_TIMEOUT)
        
        if acquired:
            logger.info("[SapoClient] Selenium lock acquired ✓")
        else:
            logger.warning("[SapoClient] Selenium lock is held by another process")
        
        return acquired
    
    def _release_selenium_lock(self):
        """Release Selenium lock."""
        cache.delete(SELENIUM_LOCK_KEY)
        logger.info("[SapoClient] Selenium lock released ✓")
    
    def _check_selenium_lock_status(self) -> bool:
        """
        Check xem có lock nào đang active không.
        
        Returns:
            True nếu lock đang active (login đang chạy), False nếu không
        """
        return cache.get(SELENIUM_LOCK_KEY) is not None
    
    # ========================= BROWSER LOGIN (SELENIUM) =========================
    
    def _login_via_browser(self) -> Dict[str, Any]:
        """
        Login via Selenium Wire để capture headers cho cả Core và Marketplace.
        
        Returns:
            Core API headers
            
        Side effect:
            Lưu marketplace headers vào DB
            
        Raises:
            SeleniumLoginInProgressException: Nếu có Selenium login khác đang chạy
        """
        logger.info("[SapoClient] Starting browser login (Selenium Wire)...")
        
        # Kiểm tra lock trước
        if not self._acquire_selenium_lock():
            logger.warning("[SapoClient] Another Selenium login is in progress")
            raise SeleniumLoginInProgressException(
                "Another Selenium login process is currently running. Please wait."
            )
        
        chrome_options = webdriver.ChromeOptions()
        # chrome_options.add_argument("--headless")  # Disabled for testing - browser will be visible
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--window-size=1920,1080")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        
        driver = webdriver.Chrome(options=chrome_options)
        captured_core_headers: Dict[str, str] = {}
        
        try:
            # === LOGIN ===
            logger.debug("[SapoClient] Opening login page...")
            driver.get(f"{SAPO_BASIC.MAIN_URL}/authorization/login")
            
            # Wait for form elements
            login_field = WebDriverWait(driver, 50).until(
                EC.presence_of_element_located((By.XPATH, SAPO_BASIC.LOGIN_USERNAME_FIELD))
            )
            password_field = WebDriverWait(driver, 50).until(
                EC.presence_of_element_located((By.XPATH, SAPO_BASIC.LOGIN_PASSWORD_FIELD))
            )
            login_button = WebDriverWait(driver, 50).until(
                EC.presence_of_element_located((By.XPATH, SAPO_BASIC.LOGIN_BUTTON))
            )
            
            # Submit credentials
            logger.debug("[SapoClient] Submitting login...")
            login_field.send_keys(SAPO_BASIC.USERNAME)
            password_field.send_keys(SAPO_BASIC.PASSWORD)
            time.sleep(2)
            login_button.click()
            
            # Wait for dashboard
            logger.debug("[SapoClient] Waiting for dashboard...")
            time.sleep(5)
            driver.get(f"{SAPO_BASIC.MAIN_URL}/dashboard")
            time.sleep(10)
            
            # === CAPTURE CORE HEADERS ===
            logger.debug("[SapoClient] Capturing core headers...")
            for request in driver.requests:
                if "delivery_service_providers.json" in request.url:
                    logger.debug(f"[SapoClient] Found core request: {request.url}")
                    captured_core_headers = dict(request.headers)
                    break
            
            # === CAPTURE MARKETPLACE HEADERS ===
            logger.debug("[SapoClient] Navigating to marketplace...")
            driver.get(f"{SAPO_BASIC.MAIN_URL}/apps/market-place/home/overview")
            time.sleep(30)
            
            tmdt_headers = None
            
            # Try to find /v2/orders request
            for req in driver.requests:
                if "/v2/orders" in req.url:
                    logger.debug(f"[SapoClient] Found marketplace request: {req.url}")
                    tmdt_headers = dict(req.headers)
                    break
            
            # Fallback to scopes
            if not tmdt_headers:
                for req in driver.requests:
                    if "/api/staffs/" in req.url and "/scopes" in req.url:
                        logger.debug(f"[SapoClient] Fallback to scopes: {req.url}")
                        tmdt_headers = dict(req.headers)
                        break
            
            if tmdt_headers:
                self._save_tmdt_token(tmdt_headers)
                logger.info("[SapoClient] Marketplace headers captured ✓")
            else:
                logger.warning("[SapoClient] Failed to capture marketplace headers")
        
        finally:
            driver.quit()
            # Always release lock khi hoàn tất (hoặc lỗi)
            self._release_selenium_lock()
        
        if not captured_core_headers:
            raise RuntimeError("Failed to capture core headers from browser session")
        
        logger.info("[SapoClient] Browser login complete ✓")
        return captured_core_headers
    
    # ========================= REPOSITORY ACCESS =========================
    
    def _ensure_sapo_headers(self):
        """
        Đảm bảo core_session luôn có x-sapo-client headers.
        
        Gọi method này trước mỗi API call để đảm bảo headers không bị mất
        do token cũ trong DB không có x-sapo-client.
        """
        current_headers = self.core_session.headers
        
        # Kiểm tra nếu thiếu x-sapo-client thì thêm vào
        if "x-sapo-client" not in current_headers:
            logger.warning("[SapoClient] x-sapo-client missing in session, adding now...")
            self.core_session.headers.update({
                "x-sapo-client": "sapo-frontend-v3",
                "x-sapo-serviceid": "sapo-frontend-v3",
                "accept": "application/json, text/plain, */*",
                "content-type": "application/json;charset=UTF-8",
            })
            logger.info("[SapoClient] x-sapo-client headers restored ✓")
    
    @property
    def core(self) -> SapoCoreRepository:
        """
        Access Sapo Core API Repository.
        
        Returns:
            SapoCoreRepository instance
        """
        self._ensure_logged_in()
        
        # Đảm bảo x-sapo-client luôn có (fix token cũ trong DB)
        self._ensure_sapo_headers()
        
        if not self._core_repo:
            self._core_repo = SapoCoreRepository(
                session=self.core_session,
                base_url=SAPO_BASIC.MAIN_URL
            )
        
        return self._core_repo
    
    @property
    def marketplace(self) -> SapoMarketplaceRepository:
        """
        Access Sapo Marketplace API Repository.
        
        Returns:
            SapoMarketplaceRepository instance
        """
        self._ensure_tmdt_headers()
        
        if not self._marketplace_repo:
            self._marketplace_repo = SapoMarketplaceRepository(
                session=self.tmdt_session,
                base_url=SAPO_TMDT.SCOPES_URL
            )
        
        return self._marketplace_repo
    
    # ========================= DEPRECATED (backward compatibility) =========================
    
    def core_api(self):
        """Deprecated: Use .core property instead."""
        logger.warning("[SapoClient] core_api() is deprecated, use .core property")
        return self.core
    
    def marketplace_api(self):
        """Deprecated: Use .marketplace property instead."""
        logger.warning("[SapoClient] marketplace_api() is deprecated, use .marketplace property")
        return self.marketplace
