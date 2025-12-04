# core/sapo_client/client.py
"""
Sapo Client - Main client để authenticate và access Sapo APIs.
Quản lý 2 sessions riêng cho Core API và Marketplace API.
"""

import json
import os
import time
import threading
import platform
from typing import Dict, Any, Optional
import logging

import requests
from django.utils import timezone
from django.core.cache import cache
from seleniumwire import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.common.action_chains import ActionChains
from selenium.common.exceptions import StaleElementReferenceException, NoSuchWindowException

# Import Service cho Selenium 4.6+
try:
    from selenium.webdriver.chrome.service import Service as ChromeService
    SELENIUM_NEW_VERSION = True
except ImportError:
    # Fallback cho Selenium cũ
    ChromeService = None
    SELENIUM_NEW_VERSION = False

from core.models import SapoToken
from core.system_settings import SAPO_BASIC, SAPO_TMDT

from .repositories import SapoCoreRepository, SapoMarketplaceRepository, SapoPromotionRepository
from .exceptions import SeleniumLoginInProgressException

logger = logging.getLogger(__name__)

# Debug print function
# Mặc định tắt để tránh spam log trên server; bật tạm thời khi cần debug Sapo Selenium.
DEBUG_PRINT_ENABLED = False

def debug_print(*args, **kwargs):
    if DEBUG_PRINT_ENABLED:
        print("[DEBUG]", *args, **kwargs)

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
        self._promotion_repo: Optional[SapoPromotionRepository] = None
        
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
            
            # Parse cookie từ headers nếu có
            test_headers = dict(headers)
            cookies = {}
            raw_cookie = test_headers.pop("cookie", None) or test_headers.pop("Cookie", None)
            test_headers.pop("host", None)  # requests tự set
            
            if raw_cookie:
                for kv in raw_cookie.split("; "):
                    if "=" in kv:
                        k, v = kv.split("=", 1)
                        cookies[k] = v
            
            debug_print(f"[SapoClient] Testing marketplace token validation...")
            debug_print(f"   - URL: {url}")
            debug_print(f"   - Headers count: {len(test_headers)}")
            debug_print(f"   - Cookies count: {len(cookies)}")
            
            # Dùng session để test (giống như cách apply vào tmdt_session)
            test_session = requests.Session()
            test_session.headers.update(test_headers)
            if cookies:
                test_session.cookies.update(cookies)
            
            res = test_session.get(url, timeout=10)
            
            debug_print(f"   - Response status: {res.status_code}")
            
            if res.status_code != 200:
                logger.warning(f"[SapoClient] Marketplace token invalid status {res.status_code}")
                debug_print(f"   ❌ Validation FAILED: status {res.status_code}")
                if res.status_code == 401 or res.status_code == 403:
                    debug_print(f"   - Response text: {res.text[:200]}")
                return False
            
            try:
                data = res.json()
                if "sapo_account_id" not in data:
                    logger.warning("[SapoClient] Missing sapo_account_id in scopes response")
                    debug_print(f"   ❌ Validation FAILED: Missing sapo_account_id in response")
                    debug_print(f"   - Response keys: {list(data.keys()) if isinstance(data, dict) else 'Not a dict'}")
                    return False
            except Exception as json_err:
                logger.warning(f"[SapoClient] Failed to parse JSON response: {json_err}")
                debug_print(f"   ❌ Validation FAILED: Cannot parse JSON - {json_err}")
                debug_print(f"   - Response text: {res.text[:200]}")
                return False
            
            logger.debug("[SapoClient] Marketplace token is valid ✓")
            debug_print(f"   ✅ Validation SUCCESS")
            return True
            
        except Exception as e:
            logger.error(f"[SapoClient] Marketplace token validation error: {e}")
            debug_print(f"   ❌ Validation ERROR: {type(e).__name__}: {str(e)}")
            import traceback
            debug_print(f"   - Traceback: {traceback.format_exc()}")
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
        
        # Trước khi trigger login mới, kiểm tra lại xem có token trong DB không
        # (có thể đã được lưu bởi background thread khác)
        if self._check_selenium_lock_status():
            # Lock đang active - có thể login đang chạy
            # Nhưng cũng có thể login vừa hoàn tất và chưa release lock
            # Thử load token một lần nữa để tránh trigger login không cần thiết
            logger.debug("[SapoClient] Lock active, checking if token is ready...")
            headers = self._load_token_from_db()
            if headers and self._check_token_valid_remote():
                logger.info("[SapoClient] Token found in DB after lock check, using it")
                self.core_valid = True
                return
            
            logger.warning("[SapoClient] Selenium login already in progress")
            raise SeleniumLoginInProgressException(
                "Selenium login is currently in progress. Please wait."
            )
        
        # Kiểm tra lại token một lần nữa trước khi trigger login
        # (có thể background thread khác vừa hoàn tất và release lock)
        # Đợi thêm một chút để đảm bảo token đã được commit vào DB
        logger.debug("[SapoClient] Lock not active, waiting a bit for possible token commit...")
        time.sleep(2)  # Đợi 2 giây để DB commit xong nếu login vừa hoàn thành
        
        headers = self._load_token_from_db()
        if headers and self._check_token_valid_remote():
            logger.info("[SapoClient] Token found in DB, using it (avoid duplicate login)")
            self.core_valid = True
            self.core_initialized = True
            return
        
        # Need new login - start background login
        logger.info("[SapoClient] Starting background Selenium login")
        self._start_background_login()
        
        # Raise exception để redirect tới loading page
        raise SeleniumLoginInProgressException(
            "Starting Selenium login. Please wait."
        )
    
    def _ensure_tmdt_headers(self):
        """Đảm bảo marketplace session đã authenticated."""
        debug_print("\n[DEBUG] _ensure_tmdt_headers() called")
        debug_print(f"   - tmdt_valid: {self.tmdt_valid}")
        
        if self.tmdt_valid:
            logger.debug("[SapoClient] Marketplace session already valid")
            debug_print("   ✅ Session already valid, returning")
            return
        
        debug_print("   - Loading token from DB...")
        headers = self._load_tmdt_token()
        
        if not headers:
            debug_print("   ❌ No token found in DB")
            logger.warning("[SapoClient] No marketplace token in DB, need login")
        else:
            debug_print(f"   ✓ Token loaded from DB (expires_at check passed)")
            debug_print(f"   - Headers keys: {list(headers.keys())[:10]}...")  # Show first 10 keys
        
        if headers and self._check_tmdt_valid_remote(headers):
            logger.info("[SapoClient] Marketplace session ready (from DB)")
            debug_print("   ✅ Token validation passed, applying to session")
            self._apply_tmdt_headers_to_session(headers)
            self.tmdt_valid = True
            debug_print("   ✅ tmdt_valid set to True")
            return
        
        # Need refresh - check if login is already in progress
        debug_print("   ⚠️  Token validation failed or no token, checking lock...")
        if self._check_selenium_lock_status():
            # Lock đang active - có thể login đang chạy
            # Đợi một chút và kiểm tra lại token (có thể login đang hoàn tất)
            logger.debug("[SapoClient] Lock active, waiting for login to complete...")
            debug_print("   - Lock active, đợi login hoàn tất (tối đa 120 giây)...")
            
            # Đợi lock được release hoặc token sẵn sàng, check mỗi 2 giây
            wait_timeout = 120  # 2 phút
            check_interval = 2
            elapsed = 0
            
            while elapsed < wait_timeout:
                # Kiểm tra xem token đã sẵn sàng chưa
                headers = self._load_tmdt_token()
                if headers and self._check_tmdt_valid_remote(headers):
                    logger.info("[SapoClient] Marketplace token found while waiting, using it")
                    debug_print("   ✅ Token found, applying to session")
                    self._apply_tmdt_headers_to_session(headers)
                    self.tmdt_valid = True
                    return
                
                # Kiểm tra xem lock còn active không
                if not self._check_selenium_lock_status():
                    debug_print("   ✓ Lock đã được release, đợi để token được commit...")
                    # Đợi một chút để đảm bảo token đã được commit vào DB
                    time.sleep(2)
                    
                    # Lock đã release, kiểm tra token một lần nữa
                    headers = self._load_tmdt_token()
                    if headers and self._check_tmdt_valid_remote(headers):
                        logger.info("[SapoClient] Marketplace token found after lock release, using it")
                        debug_print("   ✅ Token found, applying to session")
                        self._apply_tmdt_headers_to_session(headers)
                        self.tmdt_valid = True
                        return
                    # Nếu không có token, thoát loop và tiếp tục trigger login
                    break
                
                # Đợi trước khi check lại
                time.sleep(check_interval)
                elapsed += check_interval
                if elapsed % 10 == 0:  # Log mỗi 10 giây
                    debug_print(f"   - Đang đợi... ({elapsed}/{wait_timeout} giây)")
            
            if elapsed >= wait_timeout:
                logger.warning("[SapoClient] Timeout waiting for login to complete")
                debug_print("   ⚠️  Timeout đợi login, sẽ trigger login mới")
            else:
                debug_print("   - Lock đã được release, đợi thêm để token được commit...")
                # Đợi thêm một chút để đảm bảo token đã được commit vào DB
                time.sleep(2)
        
        # Kiểm tra lại token một lần nữa trước khi trigger login
        # (có thể background thread khác vừa hoàn tất)
        debug_print("   - Checking token one more time before triggering login...")
        headers = self._load_tmdt_token()
        if headers and self._check_tmdt_valid_remote(headers):
            logger.info("[SapoClient] Marketplace token found in DB, using it (avoid duplicate login)")
            debug_print("   ✅ Token found, applying to session")
            self._apply_tmdt_headers_to_session(headers)
            self.tmdt_valid = True
            return
        
        # Reset core để force browser login (sẽ capture cả marketplace token)
        debug_print("   🔄 Starting new Selenium login...")
        self.core_valid = False
        self.core_initialized = False
        
        # Start background login and raise exception
        logger.info("[SapoClient] Starting background Selenium login for marketplace")
        self._start_background_login()
        
        # Raise exception để redirect tới loading page
        debug_print("   🚀 Background login started, raising exception")
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
                
                # Đợi một chút để đảm bảo token đã được lưu vào DB thành công
                # Tránh trường hợp request khác load token ngay sau khi save nhưng chưa commit
                logger.debug("[BackgroundLogin] Waiting for DB commit...")
                time.sleep(2)  # Đợi 2 giây để DB commit xong
                
                # Update state của instance sau khi login thành công
                # Load token vào session và set core_valid = True
                headers = self._load_token_from_db()
                if headers and self._check_token_valid_remote():
                    self.core_valid = True
                    self.core_initialized = True
                    logger.info("[BackgroundLogin] Core instance state updated ✓")
                
                # Cũng update marketplace token state nếu có
                tmdt_headers = self._load_tmdt_token()
                if tmdt_headers and self._check_tmdt_valid_remote(tmdt_headers):
                    self._apply_tmdt_headers_to_session(tmdt_headers)
                    self.tmdt_valid = True
                    logger.info("[BackgroundLogin] Marketplace instance state updated ✓")
                
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
        Lưu timestamp để có thể check stale lock.
        
        Returns:
            True nếu acquire được lock, False nếu lock đang được giữ bởi process khác
        """
        import time
        # Thử set lock với timestamp
        lock_value = {
            'timestamp': time.time(),
            'pid': os.getpid() if hasattr(os, 'getpid') else None
        }
        acquired = cache.add(SELENIUM_LOCK_KEY, lock_value, SELENIUM_LOCK_TIMEOUT)
        
        if acquired:
            logger.info("[SapoClient] Selenium lock acquired ✓")
        else:
            logger.warning("[SapoClient] Selenium lock is held by another process")
        
        return acquired
    
    def _refresh_selenium_lock(self):
        """
        Refresh lock để kéo dài timeout. Gọi định kỳ trong quá trình login.
        """
        import time
        lock_value = cache.get(SELENIUM_LOCK_KEY)
        if lock_value:
            # Update timestamp và refresh timeout
            if isinstance(lock_value, dict):
                lock_value['timestamp'] = time.time()
            else:
                # Backward compatibility với lock cũ (chỉ là True)
                lock_value = {
                    'timestamp': time.time(),
                    'pid': os.getpid() if hasattr(os, 'getpid') else None
                }
            cache.set(SELENIUM_LOCK_KEY, lock_value, SELENIUM_LOCK_TIMEOUT)
            logger.debug("[SapoClient] Selenium lock refreshed ✓")
    
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
    
    def _wait_for_selenium_lock_release(self, timeout: int = 120, check_interval: int = 2) -> bool:
        """
        Đợi lock được release, đồng thời kiểm tra xem token đã sẵn sàng chưa.
        
        Args:
            timeout: Tổng thời gian đợi (giây)
            check_interval: Khoảng thời gian giữa các lần check (giây)
            
        Returns:
            True nếu lock được release, False nếu timeout
        """
        import time
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            if not self._check_selenium_lock_status():
                logger.debug("[SapoClient] Lock released, proceeding...")
                return True
            time.sleep(check_interval)
        
        logger.warning(f"[SapoClient] Lock wait timeout after {timeout} seconds")
        return False
    
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
        debug_print("="*60)
        debug_print("🚀 [Selenium] BẮT ĐẦU QUÁ TRÌNH LOGIN VÀ CAPTURE COOKIE")
        debug_print("="*60)
        logger.info("[SapoClient] Starting browser login (Selenium Wire)...")
        
        # Kiểm tra lock trước
        debug_print("🔒 [Selenium] Bước 1: Kiểm tra và acquire lock...")
        if not self._acquire_selenium_lock():
            debug_print("❌ [Selenium] THẤT BẠI: Có một Selenium login khác đang chạy")
            logger.warning("[SapoClient] Another Selenium login is in progress")
            raise SeleniumLoginInProgressException(
                "Another Selenium login process is currently running. Please wait."
            )
        debug_print("✅ [Selenium] Đã acquire lock thành công")
        
        debug_print("🌐 [Selenium] Bước 2: Khởi tạo Chrome browser với Selenium Wire...")
        try:
            # Khai báo system ngay đầu để dùng trong except block
            system = platform.system()
            chromedriver_path = None  # Khai báo trước để dùng trong except block
            
            chrome_options = webdriver.ChromeOptions()
            
            # Mode headless / GPU config theo OS
            if system == "Linux":
                # Server Linux: luôn headless + tắt GPU
                chrome_options.add_argument("--headless=new")
                debug_print("   - Headless mode: ENABLED (Linux server)")
            else:
                # Windows/Mac: cho phép cấu hình qua env, default cũng dùng headless để ổn định
                import os as _os
                headless_flag = (_os.getenv("SELENIUM_HEADLESS") or "1").strip()
                if headless_flag in ("1", "true", "True", "yes", "YES"):
                    chrome_options.add_argument("--headless=new")
                    debug_print("   - Headless mode: ENABLED (Windows/Mac via env/DEFAULT)")
                else:
                    debug_print("   - Headless mode: DISABLED (Windows/Mac, SELENIUM_HEADLESS=0)")
            
            # Options chung để tránh lỗi GPU / renderer trên cả 2 môi trường
            chrome_options.add_argument("--disable-gpu")
            chrome_options.add_argument("--disable-software-rasterizer")
            chrome_options.add_argument("--disable-extensions")
            chrome_options.add_argument("--disable-logging")
            chrome_options.add_argument("--disable-background-timer-throttling")
            chrome_options.add_argument("--disable-backgrounding-occluded-windows")
            chrome_options.add_argument("--disable-renderer-backgrounding")
            chrome_options.add_argument("--window-size=1920,1080")
            
            # Chỉ dùng no-sandbox + disable-dev-shm-usage trên Linux (root / container)
            if system == "Linux":
                chrome_options.add_argument("--no-sandbox")
                chrome_options.add_argument("--disable-dev-shm-usage")
            
            # Không set cứng remote-debugging-port để tránh conflict "Only one usage of each socket address..."
            # Nếu cần debug, có thể bật qua env riêng (ví dụ: SELENIUM_REMOTE_DEBUG_PORT)
            
            # User agent để tránh bị phát hiện là bot (dùng UA general, không hard-code Linux)
            chrome_options.add_argument(
                "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
            
            debug_print("   - Chrome options đã cấu hình xong")
            
            # Xác định chromedriver path dựa trên hệ điều hành
            import os
            import stat
            from pathlib import Path
            
            BASE_DIR = Path(__file__).resolve().parent.parent.parent
            
            if system == "Windows":
                chromedriver_path = str(BASE_DIR / "chromedriver.exe")
                debug_print(f"   - Hệ điều hành: Windows, sử dụng {chromedriver_path}")
            else:
                # Linux/Ubuntu - thử nhiều vị trí
                chromedriver_path = None
                possible_paths = [
                    str(BASE_DIR / "chromedriver-linux"),
                    str(BASE_DIR / "chromedriver"),
                    "/usr/bin/chromedriver",
                    "/usr/local/bin/chromedriver",
                    "chromedriver-linux",
                    "chromedriver"
                ]
                for path in possible_paths:
                    full_path = path if os.path.isabs(path) else str(BASE_DIR / path)
                    if os.path.exists(full_path):
                        chromedriver_path = full_path
                        break
                
                if not chromedriver_path:
                    chromedriver_path = str(BASE_DIR / "chromedriver-linux")
                    debug_print(f"   - Hệ điều hành: {system}, sử dụng {chromedriver_path} (file có thể chưa tồn tại)")
                else:
                    debug_print(f"   - Hệ điều hành: {system}, sử dụng {chromedriver_path}")
                
                # Tự động set quyền execute cho chromedriver trên Linux
                if chromedriver_path and os.path.exists(chromedriver_path):
                    try:
                        # Kiểm tra xem file đã có quyền execute chưa
                        current_mode = os.stat(chromedriver_path).st_mode
                        is_executable = bool(current_mode & stat.S_IEXEC)
                        
                        if not is_executable:
                            debug_print(f"   - File {chromedriver_path} chưa có quyền execute, đang set quyền...")
                            # Set quyền execute (chmod +x)
                            os.chmod(chromedriver_path, current_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
                            debug_print(f"   ✅ Đã set quyền execute cho {chromedriver_path}")
                        else:
                            debug_print(f"   ✅ File {chromedriver_path} đã có quyền execute")
                    except Exception as e:
                        debug_print(f"   ⚠️  Không thể set quyền execute cho {chromedriver_path}: {e}")
                        debug_print(f"   💡 Vui lòng chạy thủ công: chmod +x {chromedriver_path}")
            
            # Selenium 4.6+ không còn dùng executable_path trong webdriver.Chrome()
            # Nhưng Selenium Wire có thể vẫn hỗ trợ executable_path
            # Thử theo thứ tự: Service -> executable_path -> auto-detect
            
            driver = None
            last_error = None
            
            # Cách 1: Thử dùng Service (cho Selenium 4.6+ thông thường)
            if SELENIUM_NEW_VERSION and ChromeService and os.path.exists(chromedriver_path):
                try:
                    service = ChromeService(executable_path=chromedriver_path)
                    driver = webdriver.Chrome(service=service, options=chrome_options)
                    debug_print("   ✅ Khởi tạo thành công với Service")
                except (TypeError, ValueError) as e:
                    last_error = e
                    debug_print(f"   ⚠️  Service không hoạt động: {e}")
            
            # Cách 2: Thử dùng executable_path trực tiếp (Selenium Wire có thể hỗ trợ)
            if driver is None:
                try:
                    if os.path.exists(chromedriver_path):
                        # Selenium Wire có thể vẫn hỗ trợ executable_path
                        driver = webdriver.Chrome(executable_path=chromedriver_path, options=chrome_options)
                        debug_print("   ✅ Khởi tạo thành công với executable_path")
                    else:
                        raise FileNotFoundError(f"ChromeDriver not found at: {chromedriver_path}")
                except (TypeError, ValueError) as e:
                    last_error = e
                    debug_print(f"   ⚠️  executable_path không hoạt động: {e}")
            
            # Cách 3: Auto-detect (chromedriver phải có trong PATH)
            if driver is None:
                try:
                    debug_print("   ⚠️  Thử auto-detect chromedriver từ PATH...")
                    driver = webdriver.Chrome(options=chrome_options)
                    debug_print("   ✅ Khởi tạo thành công với auto-detect")
                except Exception as e:
                    last_error = e
                    debug_print(f"   ❌ Auto-detect cũng thất bại: {e}")
            
            # Nếu tất cả đều thất bại
            if driver is None:
                error_msg = f"Không thể khởi tạo Chrome WebDriver. Lỗi cuối: {last_error}"
                debug_print(f"   ❌ {error_msg}")
                
                # Thêm hướng dẫn khắc phục cho Linux
                if system == "Linux":
                    debug_print("\n   💡 HƯỚNG DẪN KHẮC PHỤC:")
                    debug_print("   1. Cài đặt Chrome/Chromium:")
                    debug_print("      sudo apt-get update")
                    debug_print("      sudo apt-get install -y google-chrome-stable")
                    debug_print("      # hoặc")
                    debug_print("      sudo apt-get install -y chromium-browser")
                    debug_print("   2. Kiểm tra ChromeDriver version khớp với Chrome:")
                    debug_print("      google-chrome --version")
                    debug_print("      chromedriver --version")
                    debug_print("   3. Đảm bảo ChromeDriver có quyền thực thi:")
                    debug_print("      chmod +x chromedriver-linux")
                    debug_print("      # hoặc cài vào PATH:")
                    debug_print("      sudo cp chromedriver-linux /usr/local/bin/chromedriver")
                    debug_print("      sudo chmod +x /usr/local/bin/chromedriver")
                
                raise RuntimeError(error_msg)
            
            debug_print("✅ [Selenium] Chrome browser đã khởi động thành công")
            captured_core_headers: Dict[str, str] = {}
        except Exception as e:
            error_type = type(e).__name__
            error_msg = str(e)
            debug_print(f"❌ [Selenium] LỖI khi khởi động Chrome: {error_type}: {error_msg}")
            
            # Xử lý lỗi SessionNotCreatedException đặc biệt
            if "SessionNotCreatedException" in error_type or "session not created" in error_msg.lower():
                debug_print("\n   🔍 PHÂN TÍCH LỖI:")
                debug_print("   - Chrome instance exited: Chrome không thể khởi động")
                if system == "Linux":
                    debug_print("\n   💡 GIẢI PHÁP CHO LINUX SERVER:")
                    debug_print("   1. Đảm bảo Chrome/Chromium đã được cài đặt:")
                    debug_print("      which google-chrome || which chromium-browser")
                    debug_print("   2. Nếu chưa cài, chạy:")
                    debug_print("      sudo apt-get update")
                    debug_print("      sudo apt-get install -y google-chrome-stable")
                    debug_print("   3. Kiểm tra ChromeDriver và Chrome version:")
                    debug_print("      google-chrome --version")
                    debug_print(f"      {chromedriver_path} --version")
                    debug_print("   4. Test Chrome có chạy được không:")
                    debug_print("      google-chrome --headless --disable-gpu --no-sandbox --version")
                else:
                    debug_print("   - Kiểm tra Chrome/ChromeDriver đã được cài đặt đúng chưa")
                    debug_print("   - Kiểm tra version Chrome và ChromeDriver có khớp không")
            
            self._release_selenium_lock()
            
            # Tạo error message chi tiết hơn
            detailed_error = f"{error_type}: {error_msg}"
            if "SessionNotCreatedException" in error_type:
                detailed_error += "\n\nChrome không thể khởi động. Vui lòng kiểm tra:\n"
                detailed_error += "- Chrome/Chromium đã được cài đặt chưa?\n"
                detailed_error += "- ChromeDriver version có khớp với Chrome không?\n"
                if system == "Linux":
                    detailed_error += "- Đã cài đặt các dependencies cần thiết chưa? (libnss3, libatk-bridge2.0-0, etc.)\n"
            
            raise RuntimeError(detailed_error) from e
        
        try:
            # === LOGIN ===
            debug_print("\n📄 [Selenium] Bước 3: Mở trang login Sapo...")
            logger.debug("[SapoClient] Opening login page...")
            try:
                login_url = f"{SAPO_BASIC.MAIN_URL}/authorization/login"
                debug_print(f"   - URL ban đầu: {login_url}")
                driver.get(login_url)
                
                # Đợi trang load và redirect xong (nếu có)
                debug_print("   - Đợi trang redirect và load xong...")
                time.sleep(3)  # Đợi redirect
                
                # Kiểm tra window còn tồn tại không
                try:
                    current_url = driver.current_url
                    window_handles = driver.window_handles
                    debug_print(f"   - Current URL sau redirect: {current_url}")
                    debug_print(f"   - Số windows: {len(window_handles)}")
                    
                    # Nếu có nhiều windows, chuyển sang window mới (có thể là redirect)
                    if len(window_handles) > 1:
                        debug_print(f"   - Phát hiện {len(window_handles)} windows, chuyển sang window mới...")
                        driver.switch_to.window(window_handles[-1])  # Chuyển sang window mới nhất
                        current_url = driver.current_url
                        debug_print(f"   - Current URL sau khi switch window: {current_url}")
                    elif len(window_handles) == 0:
                        debug_print("   ⚠️  Không có window nào!")
                        raise RuntimeError("All browser windows were closed")
                    
                    # Đợi document ready
                    WebDriverWait(driver, 20).until(
                        lambda d: d.execute_script("return document.readyState") == "complete"
                    )
                    debug_print("   ✓ Document ready")
                    
                    # Đợi thêm một chút để JavaScript load xong
                    time.sleep(2)
                    
                    debug_print("✅ [Selenium] Đã mở trang login thành công")
                    # Refresh lock sau khi mở trang thành công
                    self._refresh_selenium_lock()
                except Exception as window_check_error:
                    error_type = type(window_check_error).__name__
                    if "NoSuchWindowException" in error_type or "no such window" in str(window_check_error).lower():
                        debug_print(f"   ❌ Window đã bị đóng: {error_type}")
                        # Thử tìm lại window hoặc tạo mới
                        if len(driver.window_handles) == 0:
                            raise RuntimeError("Browser window was closed and no windows available")
                        else:
                            driver.switch_to.window(driver.window_handles[0])
                            current_url = driver.current_url
                            debug_print(f"   ✓ Đã chuyển sang window khả dụng: {current_url}")
                    else:
                        raise
            except Exception as e:
                debug_print(f"❌ [Selenium] LỖI khi mở trang login: {type(e).__name__}: {str(e)}")
                raise
            
            # Wait for form elements - chỉ đợi để verify elements có sẵn
            debug_print("\n⏳ [Selenium] Bước 4: Đợi form elements xuất hiện...")
            try:
                # Kiểm tra window còn tồn tại trước khi tìm elements
                if len(driver.window_handles) == 0:
                    raise RuntimeError("Browser window was closed")
                
                # Đảm bảo đang ở đúng window
                current_window = driver.current_window_handle
                if current_window not in driver.window_handles:
                    debug_print("   - Current window không còn tồn tại, chuyển sang window mới...")
                    driver.switch_to.window(driver.window_handles[0])
                
                debug_print(f"   - Current URL: {driver.current_url}")
                debug_print("   - Đang đợi username field...")
                
                # Đợi username field với retry cho window closed
                max_wait_attempts = 5
                for attempt in range(max_wait_attempts):
                    try:
                        WebDriverWait(driver, 10).until(
                            EC.element_to_be_clickable((By.XPATH, SAPO_BASIC.LOGIN_USERNAME_FIELD))
                        )
                        debug_print("   ✓ Username field đã sẵn sàng")
                        break
                    except Exception as e:
                        if attempt < max_wait_attempts - 1:
                            error_msg = str(e).lower()
                            if "nosuchwindow" in error_msg or "window" in error_msg:
                                debug_print(f"   - ⚠️  Window issue, retrying... ({attempt+1}/{max_wait_attempts})")
                                if len(driver.window_handles) > 0:
                                    driver.switch_to.window(driver.window_handles[0])
                                time.sleep(1)
                                continue
                        raise
                
                debug_print("   - Đang đợi password field...")
                WebDriverWait(driver, 10).until(
                    EC.element_to_be_clickable((By.XPATH, SAPO_BASIC.LOGIN_PASSWORD_FIELD))
                )
                debug_print("   ✓ Password field đã sẵn sàng")
                
                # KHÔNG đợi login button ở đây - button sẽ bị disabled cho đến khi điền username/password
                # Button sẽ được đợi SAU KHI điền username và password
                
                debug_print("✅ [Selenium] Form fields đã ready (button sẽ được enable sau khi điền thông tin)")
            except Exception as e:
                error_type = type(e).__name__
                error_msg = str(e)
                debug_print(f"❌ [Selenium] LỖI khi đợi form elements: {error_type}: {error_msg}")
                
                # Debug thông tin
                try:
                    if len(driver.window_handles) > 0:
                        debug_print(f"   - Current URL: {driver.current_url}")
                        debug_print(f"   - Windows available: {len(driver.window_handles)}")
                        # Lưu page source để debug
                        try:
                            page_source = driver.page_source[:500]
                            debug_print(f"   - Page source preview: {page_source}")
                        except:
                            pass
                    else:
                        debug_print("   - ⚠️  Không còn window nào!")
                except:
                    pass
                
                raise
            
            # Submit credentials - Tìm lại elements ngay trước khi dùng để tránh stale element
            debug_print("\n🔑 [Selenium] Bước 5: Điền thông tin đăng nhập...")
            logger.debug("[SapoClient] Submitting login...")
            
            # Helper function để tìm lại element nếu bị stale
            def find_and_interact_element(xpath_or_selectors, action_func, element_name, max_retries=3, is_button=False):
                """
                Tìm lại element và thực hiện action với retry cho stale element
                
                Args:
                    xpath_or_selectors: XPATH string hoặc list of selectors (cho button)
                    action_func: Function để thực hiện trên element
                    element_name: Tên element để log
                    max_retries: Số lần retry
                    is_button: Nếu True, sẽ thử nhiều selector cho button
                """
                # Nếu là button và có nhiều selectors, thử từng cái
                selectors = xpath_or_selectors if isinstance(xpath_or_selectors, list) else [xpath_or_selectors]
                
                for attempt in range(max_retries):
                    for selector_idx, xpath in enumerate(selectors):
                        try:
                            if attempt == 0 and selector_idx > 0:
                                debug_print(f"   - [{attempt+1}/{max_retries}] Thử selector {selector_idx + 1} cho {element_name}...")
                            elif attempt > 0:
                                debug_print(f"   - [{attempt+1}/{max_retries}] Retry tìm {element_name}...")
                            
                            element = WebDriverWait(driver, 5 if selector_idx > 0 else 10).until(
                                EC.element_to_be_clickable((By.XPATH, xpath))
                            )
                            action_func(element)
                            return True
                        except StaleElementReferenceException:
                            if selector_idx == len(selectors) - 1:  # Chỉ retry nếu đã thử hết selectors
                                debug_print(f"   - ⚠️  Stale element detected, retrying... ({attempt+1}/{max_retries})")
                                time.sleep(0.5)  # Đợi một chút để DOM ổn định
                                if attempt == max_retries - 1:
                                    raise
                                break  # Break khỏi selector loop, retry với attempt mới
                            else:
                                # Thử selector tiếp theo
                                continue
                        except Exception as e:
                            if selector_idx < len(selectors) - 1:
                                # Thử selector tiếp theo
                                continue
                            # Đã thử hết selectors, retry với attempt mới
                            if attempt < max_retries - 1:
                                debug_print(f"   - ⚠️  Lỗi: {e}, retrying... ({attempt+1}/{max_retries})")
                                time.sleep(0.5)
                                break  # Break khỏi selector loop, retry với attempt mới
                            else:
                                raise
                return False
            
            try:
                # Điền username - tìm lại element ngay trước khi dùng
                debug_print(f"   - Điền username: {SAPO_BASIC.USERNAME[:3]}***")
                find_and_interact_element(
                    SAPO_BASIC.LOGIN_USERNAME_FIELD,
                    lambda el: el.send_keys(SAPO_BASIC.USERNAME),
                    "username field"
                )
                
                # Đợi một chút để form xử lý
                time.sleep(0.5)
                
                # Điền password - tìm lại element ngay trước khi dùng
                debug_print("   - Điền password: ***")
                find_and_interact_element(
                    SAPO_BASIC.LOGIN_PASSWORD_FIELD,
                    lambda el: el.send_keys(SAPO_BASIC.PASSWORD),
                    "password field"
                )
                
                # Đợi một chút để form xử lý và button được enable
                debug_print("   - Đợi 1 giây để form xử lý và button được enable...")
                time.sleep(1)
                
                # Đợi login button trở nên enabled/clickable (sau khi đã điền username/password)
                debug_print("   - Đợi login button trở nên enabled (clickable)...")
                button_selectors = [
                    SAPO_BASIC.LOGIN_BUTTON,  # Selector mặc định
                    # Thử các selector khác nếu mặc định không tìm được
                    "//form//button[contains(text(), 'Đăng nhập')]",  # Button trong form
                    f"{SAPO_BASIC.LOGIN_PASSWORD_FIELD}/ancestor::form//button[contains(text(), 'Đăng nhập')]",  # Button trong cùng form với password
                    f"{SAPO_BASIC.LOGIN_PASSWORD_FIELD}/following::button[contains(text(), 'Đăng nhập')][1]",  # Button sau password field
                    "//button[@type='submit' and contains(text(), 'Đăng nhập')]",  # Submit button
                    "//button[normalize-space(text())='Đăng nhập' and not(contains(@class, 'Facebook')) and not(contains(@class, 'Google'))]",  # Exclude social buttons
                ]
                
                login_button = None
                for selector_idx, button_selector in enumerate(button_selectors):
                    try:
                        debug_print(f"      - Thử selector {selector_idx + 1}/{len(button_selectors)} cho button...")
                        # element_to_be_clickable sẽ tự động đợi button enabled (không disabled)
                        login_button = WebDriverWait(driver, 10).until(
                            EC.element_to_be_clickable((By.XPATH, button_selector))
                        )
                        debug_print(f"   ✓ Login button đã enabled và sẵn sàng click")
                        break
                    except Exception as e:
                        if selector_idx == len(button_selectors) - 1:
                            debug_print(f"      ❌ Tất cả selectors đều thất bại: {str(e)}")
                            raise
                        debug_print(f"      ⚠️  Selector {selector_idx + 1} không tìm được button, thử tiếp...")
                        continue
                
                if login_button is None:
                    raise RuntimeError("Không thể tìm được login button với bất kỳ selector nào")
                
                # Click button
                debug_print("   - Click nút đăng nhập...")
                try:
                    login_button.click()
                except StaleElementReferenceException:
                    # Button bị stale, tìm lại
                    debug_print("   - ⚠️  Button bị stale, tìm lại...")
                    login_button = WebDriverWait(driver, 5).until(
                        EC.element_to_be_clickable((By.XPATH, button_selectors[0]))
                    )
                    login_button.click()
                
                debug_print("✅ [Selenium] Đã submit form đăng nhập")
                # Refresh lock sau khi submit form thành công
                self._refresh_selenium_lock()
            except Exception as e:
                error_type = type(e).__name__
                error_msg = str(e)
                debug_print(f"❌ [Selenium] LỖI khi submit login: {error_type}: {error_msg}")
                
                # Thử cách khác nếu gặp stale element
                if "StaleElementReferenceException" in error_type or "stale element" in error_msg.lower():
                    debug_print("   💡 Thử cách khác: Tìm lại tất cả elements và retry...")
                    try:
                        time.sleep(1)  # Đợi DOM ổn định
                        
                        # Tìm lại username và password fields (KHÔNG tìm button vì nó sẽ bị disabled)
                        login_field = WebDriverWait(driver, 10).until(
                            EC.element_to_be_clickable((By.XPATH, SAPO_BASIC.LOGIN_USERNAME_FIELD))
                        )
                        password_field = WebDriverWait(driver, 10).until(
                            EC.element_to_be_clickable((By.XPATH, SAPO_BASIC.LOGIN_PASSWORD_FIELD))
                        )
                        
                        # Clear và điền lại
                        login_field.clear()
                        login_field.send_keys(SAPO_BASIC.USERNAME)
                        time.sleep(0.5)
                        
                        password_field.clear()
                        password_field.send_keys(SAPO_BASIC.PASSWORD)
                        time.sleep(1)  # Đợi form xử lý và button được enable
                        
                        # Đợi button trở nên enabled sau khi điền username/password
                        debug_print("   - Đợi button được enable sau khi điền lại...")
                        login_button = WebDriverWait(driver, 10).until(
                            EC.element_to_be_clickable((By.XPATH, SAPO_BASIC.LOGIN_BUTTON))
                        )
                        
                        # Sử dụng ActionChains để click nếu button bị stale
                        actions = ActionChains(driver)
                        actions.move_to_element(login_button).click().perform()
                        
                        debug_print("✅ [Selenium] Đã submit form đăng nhập (retry thành công)")
                        # Refresh lock sau khi retry thành công
                        self._refresh_selenium_lock()
                    except Exception as retry_error:
                        debug_print(f"   ❌ Retry cũng thất bại: {type(retry_error).__name__}: {str(retry_error)}")
                        raise
                else:
                    raise
            
            # Wait for dashboard
            debug_print("\n🏠 [Selenium] Bước 6: Đợi và điều hướng đến dashboard...")
            logger.debug("[SapoClient] Waiting for dashboard...")
            try:
                debug_print("   - Đợi 5 giây sau khi login...")
                time.sleep(5)
                debug_print(f"   - Current URL: {driver.current_url}")
                
                debug_print("   - Điều hướng đến dashboard...")
                driver.get(f"{SAPO_BASIC.MAIN_URL}/dashboard")
                debug_print(f"   - URL dashboard: {SAPO_BASIC.MAIN_URL}/dashboard")
                
                debug_print("   - Đợi 10 giây để trang load...")
                time.sleep(10)
                debug_print(f"   - Current URL: {driver.current_url}")
                debug_print("✅ [Selenium] Đã vào dashboard thành công")
                # Refresh lock sau khi vào dashboard thành công
                self._refresh_selenium_lock()
            except Exception as e:
                debug_print(f"❌ [Selenium] LỖI khi vào dashboard: {type(e).__name__}: {str(e)}")
                raise
            
            # === CAPTURE CORE HEADERS ===
            debug_print("\n🎯 [Selenium] Bước 7: Capture CORE HEADERS từ network requests...")
            logger.debug("[SapoClient] Capturing core headers...")
            try:
                debug_print("   - Đang quét tất cả requests tìm 'delivery_service_providers.json'...")
                total_requests = 0
                for request in driver.requests:
                    total_requests += 1
                    if "delivery_service_providers.json" in request.url:
                        logger.debug(f"[SapoClient] Found core request: {request.url}")
                        debug_print(f"   - Tìm thấy request mục tiêu: {request.url}")
                        captured_core_headers = dict(request.headers)
                        debug_print(f"   - Số headers captured: {len(captured_core_headers)}")
                        debug_print("✅ [Selenium] Đã capture CORE HEADERS thành công từ Sapo")
                        break
                
                if not captured_core_headers:
                    debug_print(f"⚠️  [Selenium] Không tìm thấy request 'delivery_service_providers.json' (Đã quét {total_requests} requests)")
                else:
                    debug_print(f"   - Tổng số requests đã quét: {total_requests}")
            except Exception as e:
                debug_print(f"❌ [Selenium] LỖI khi capture core headers: {type(e).__name__}: {str(e)}")
                raise
            
            # === CAPTURE MARKETPLACE HEADERS ===
            debug_print("\n🏪 [Selenium] Bước 8: Điều hướng đến Marketplace và capture headers...")
            logger.debug("[SapoClient] Navigating to marketplace...")
            try:
                debug_print(f"   - Điều hướng đến: {SAPO_BASIC.MAIN_URL}/apps/market-place/home/overview")
                driver.get(f"{SAPO_BASIC.MAIN_URL}/apps/market-place/home/overview")
                debug_print("   - Đợi 30 giây để trang marketplace load...")
                time.sleep(30)
                debug_print(f"   - Current URL: {driver.current_url}")
                debug_print("✅ [Selenium] Đã vào trang marketplace")
            except Exception as e:
                debug_print(f"❌ [Selenium] LỖI khi vào marketplace: {type(e).__name__}: {str(e)}")
                # Không raise, vẫn cố gắng capture headers
            
            tmdt_headers = None
            
            # Try to find /v2/orders request
            debug_print("\n🎯 [Selenium] Bước 9: Capture MARKETPLACE HEADERS...")
            try:
                debug_print("   - Đang tìm request '/v2/orders'...")
                mp_requests_count = 0
                for req in driver.requests:
                    if "/v2/orders" in req.url:
                        mp_requests_count += 1
                        logger.debug(f"[SapoClient] Found marketplace request: {req.url}")
                        debug_print(f"   - Tìm thấy request: {req.url}")
                        tmdt_headers = dict(req.headers)
                        debug_print(f"   - Số headers captured: {len(tmdt_headers)}")
                        debug_print("✅ [Selenium] Đã capture MARKETPLACE HEADERS từ /v2/orders")
                        break
                
                if not tmdt_headers:
                    debug_print(f"   ⚠️  Không tìm thấy request '/v2/orders'")
            except Exception as e:
                debug_print(f"❌ [Selenium] LỖI khi tìm /v2/orders: {type(e).__name__}: {str(e)}")
            
            # Fallback to scopes
            if not tmdt_headers:
                debug_print("   - Fallback: Đang tìm request '/api/staffs/.../scopes'...")
                try:
                    for req in driver.requests:
                        if "/api/staffs/" in req.url and "/scopes" in req.url:
                            logger.debug(f"[SapoClient] Fallback to scopes: {req.url}")
                            debug_print(f"   - Tìm thấy scopes request: {req.url}")
                            tmdt_headers = dict(req.headers)
                            debug_print(f"   - Số headers captured: {len(tmdt_headers)}")
                            debug_print("✅ [Selenium] Đã capture MARKETPLACE HEADERS từ /scopes (fallback)")
                            break
                    
                    if not tmdt_headers:
                        debug_print("   ⚠️  Không tìm thấy scopes request")
                except Exception as e:
                    debug_print(f"❌ [Selenium] LỖI khi tìm scopes: {type(e).__name__}: {str(e)}")
            
            # Save marketplace headers
            debug_print("\n💾 [Selenium] Bước 10: Lưu marketplace headers...")
            if tmdt_headers:
                try:
                    self._save_tmdt_token(tmdt_headers)
                    logger.info("[SapoClient] Marketplace headers captured ✓")
                    debug_print("✅ [Selenium] Đã lưu marketplace token vào database")
                    
                    # Đợi một chút để đảm bảo token đã được lưu vào DB thành công
                    # Tránh trường hợp request khác load token ngay sau khi save nhưng chưa commit
                    debug_print("   - Đợi 2 giây để DB commit xong...")
                    time.sleep(2)
                except Exception as e:
                    debug_print(f"❌ [Selenium] LỖI khi lưu marketplace token: {type(e).__name__}: {str(e)}")
            else:
                logger.warning("[SapoClient] Failed to capture marketplace headers")
                debug_print("⚠️  [Selenium] Không capture được MARKETPLACE HEADERS")
        
        except Exception as e:
            debug_print(f"\n💥 [Selenium] LỖI NGHIÊM TRỌNG trong quá trình login")
            debug_print(f"   - Loại lỗi: {type(e).__name__}")
            debug_print(f"   - Chi tiết: {str(e)}")
            import traceback
            debug_print(f"   - Traceback:\n{traceback.format_exc()}")
            raise
        finally:
            debug_print("\n🔚 [Selenium] Bước 11: Cleanup...")
            try:
                debug_print("   - Đóng browser...")
                driver.quit()
                debug_print("   ✓ Browser đã đóng")
            except Exception as e:
                debug_print(f"   ⚠️  Lỗi khi đóng browser: {type(e).__name__}: {str(e)}")
            
            # Always release lock khi hoàn tất (hoặc lỗi)
            debug_print("   - Release lock...")
            self._release_selenium_lock()
            debug_print("   ✓ Lock đã release")
        
        debug_print("\n🔍 [Selenium] Bước 12: Kiểm tra kết quả...")
        if not captured_core_headers:
            debug_print("❌ [Selenium] THẤT BẠI: Không capture được CORE HEADERS")
            raise RuntimeError("Failed to capture core headers from browser session")
        
        debug_print(f"✅ [Selenium] Đã capture {len(captured_core_headers)} core headers")
        logger.info("[SapoClient] Browser login complete ✓")
        debug_print("="*60)
        debug_print("🎉 [Selenium] HOÀN TẤT QUÁ TRÌNH LOGIN VÀ CAPTURE COOKIE")
        debug_print("="*60)
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
    
    @property
    def promotion(self) -> SapoPromotionRepository:
        """
        Access Sapo Promotion API Repository.
        
        Returns:
            SapoPromotionRepository instance
        """
        self._ensure_logged_in()
        self._ensure_sapo_headers()
        
        if not self._promotion_repo:
            self._promotion_repo = SapoPromotionRepository(
                session=self.core_session,
                base_url=SAPO_BASIC.MAIN_URL
            )
        
        return self._promotion_repo
    
    # ========================= DEPRECATED (backward compatibility) =========================
    
    def core_api(self):
        """Deprecated: Use .core property instead."""
        logger.warning("[SapoClient] core_api() is deprecated, use .core property")
        return self.core
    
    def marketplace_api(self):
        """Deprecated: Use .marketplace property instead."""
        logger.warning("[SapoClient] marketplace_api() is deprecated, use .marketplace property")
        return self.marketplace
