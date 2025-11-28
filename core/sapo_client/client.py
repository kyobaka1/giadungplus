# core/sapo_client/client.py
"""
Sapo Client - Main client để authenticate và access Sapo APIs.
Quản lý 2 sessions riêng cho Core API và Marketplace API.
"""

import json
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

from core.models import SapoToken
from core.system_settings import SAPO_BASIC, SAPO_TMDT

from .repositories import SapoCoreRepository, SapoMarketplaceRepository, SapoPromotionRepository
from .exceptions import SeleniumLoginInProgressException

logger = logging.getLogger(__name__)

# Debug print function
DEBUG_PRINT_ENABLED = True

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
        # (có thể background thread khác vừa hoàn tất)
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
            # Nhưng cũng có thể login vừa hoàn tất và chưa release lock
            # Thử load token một lần nữa để tránh trigger login không cần thiết
            logger.debug("[SapoClient] Lock active, checking if marketplace token is ready...")
            debug_print("   - Lock active, checking token again...")
            headers = self._load_tmdt_token()
            if headers and self._check_tmdt_valid_remote(headers):
                logger.info("[SapoClient] Marketplace token found in DB after lock check, using it")
                debug_print("   ✅ Token found, applying to session")
                self._apply_tmdt_headers_to_session(headers)
                self.tmdt_valid = True
                return
            
            logger.warning("[SapoClient] Selenium login already in progress for marketplace")
            debug_print("   ⚠️  Lock is active, raising exception")
            raise SeleniumLoginInProgressException(
                "Selenium login is currently in progress. Please wait."
            )
        
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
            chrome_options = webdriver.ChromeOptions()
            # chrome_options.add_argument("--headless")  # Disabled for testing - browser will be visible
            chrome_options.add_argument("--disable-gpu")
            chrome_options.add_argument("--window-size=1920,1080")
            chrome_options.add_argument("--no-sandbox")
            chrome_options.add_argument("--disable-dev-shm-usage")
            debug_print("   - Chrome options đã cấu hình xong")
            
            # Xác định chromedriver path dựa trên hệ điều hành
            system = platform.system()
            if system == "Windows":
                chromedriver_path = "chromedriver.exe"
                debug_print(f"   - Hệ điều hành: Windows, sử dụng {chromedriver_path}")
            else:
                # Linux/Ubuntu
                chromedriver_path = "chromedriver-linux"
                debug_print(f"   - Hệ điều hành: {system}, sử dụng {chromedriver_path}")
            
            driver = webdriver.Chrome(executable_path=chromedriver_path, options=chrome_options)
            debug_print("✅ [Selenium] Chrome browser đã khởi động thành công")
            captured_core_headers: Dict[str, str] = {}
        except Exception as e:
            debug_print(f"❌ [Selenium] LỖI khi khởi động Chrome: {type(e).__name__}: {str(e)}")
            self._release_selenium_lock()
            raise
        
        try:
            # === LOGIN ===
            debug_print("\n📄 [Selenium] Bước 3: Mở trang login Sapo...")
            logger.debug("[SapoClient] Opening login page...")
            try:
                driver.get(f"{SAPO_BASIC.MAIN_URL}/authorization/login")
                debug_print(f"   - URL: {SAPO_BASIC.MAIN_URL}/authorization/login")
                debug_print("✅ [Selenium] Đã mở trang login thành công")
            except Exception as e:
                debug_print(f"❌ [Selenium] LỖI khi mở trang login: {type(e).__name__}: {str(e)}")
                raise
            
            # Wait for form elements
            debug_print("\n⏳ [Selenium] Bước 4: Đợi form elements xuất hiện...")
            try:
                debug_print("   - Đang đợi username field...")
                login_field = WebDriverWait(driver, 50).until(
                    EC.presence_of_element_located((By.XPATH, SAPO_BASIC.LOGIN_USERNAME_FIELD))
                )
                debug_print("   ✓ Username field đã xuất hiện")
                
                debug_print("   - Đang đợi password field...")
                password_field = WebDriverWait(driver, 50).until(
                    EC.presence_of_element_located((By.XPATH, SAPO_BASIC.LOGIN_PASSWORD_FIELD))
                )
                debug_print("   ✓ Password field đã xuất hiện")
                
                debug_print("   - Đang đợi login button...")
                login_button = WebDriverWait(driver, 50).until(
                    EC.presence_of_element_located((By.XPATH, SAPO_BASIC.LOGIN_BUTTON))
                )
                debug_print("   ✓ Login button đã xuất hiện")
                debug_print("✅ [Selenium] Tất cả form elements đã ready")
            except Exception as e:
                debug_print(f"❌ [Selenium] LỖI khi đợi form elements: {type(e).__name__}: {str(e)}")
                debug_print(f"   - Current URL: {driver.current_url}")
                raise
            
            # Submit credentials
            debug_print("\n🔑 [Selenium] Bước 5: Điền thông tin đăng nhập...")
            logger.debug("[SapoClient] Submitting login...")
            try:
                debug_print(f"   - Điền username: {SAPO_BASIC.USERNAME[:3]}***")
                login_field.send_keys(SAPO_BASIC.USERNAME)
                
                debug_print("   - Điền password: ***")
                password_field.send_keys(SAPO_BASIC.PASSWORD)
                
                debug_print("   - Đợi 2 giây...")
                time.sleep(2)
                
                debug_print("   - Click nút đăng nhập...")
                login_button.click()
                debug_print("✅ [Selenium] Đã submit form đăng nhập")
            except Exception as e:
                debug_print(f"❌ [Selenium] LỖI khi submit login: {type(e).__name__}: {str(e)}")
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
