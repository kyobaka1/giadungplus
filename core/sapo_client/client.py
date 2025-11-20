# core/sapo_client/client.py
import json
import time
from typing import Dict, Any, Optional

import requests
from django.utils import timezone
from seleniumwire import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from core.models import SapoToken
from core.system_settings import (
    SAPO_BASIC,
    SAPO_TMDT,
    HOME_PARAM,
    HOATOC_HN_ON,
    HOATOC_HCM_ON,
)

from .core_api import SapoCoreAPI
from .marketplace_api import SapoMarketplaceAPI


SAPO_DEBUG = False


def debug(*args, **kwargs):
    if SAPO_DEBUG:
        print(*args, **kwargs)


class SapoClient:
    """
    Client nói chuyện với Sapo (MAIN_URL) và Marketplace.
    - core_session: dùng cho MAIN_URL (admin)
    - tmdt_session: dùng cho market-place.sapoapps.vn
    """

    def __init__(self):
        self.core_session = requests.Session()
        self.tmdt_session = requests.Session()

        self.core_initialized = False
        self.core_valid = False

        self.tmdt_loaded = False     # đã load TMDT headers từ DB chưa
        self.tmdt_valid = False      # headers TMDT còn sống không

        self._tmdt_headers: Dict[str, Any] = {}

        debug("[SAPO] SapoClient initialized")

    # -------------------------------------------------------
    # LOAD TOKEN TỪ DB
    # -------------------------------------------------------
    def _load_token_from_db(self) -> Optional[Dict[str, Any]]:
        debug("[SAPO::TOKEN] Loading core token from DB...")

        try:
            token = SapoToken.objects.get(key="loginss")
        except SapoToken.DoesNotExist:
            debug("[SAPO::TOKEN] No core token in DB")
            return None

        if not token.is_valid():
            debug("[SAPO::TOKEN] Core token found but EXPIRED")
            return None

        debug(f"[SAPO::TOKEN] Core token OK, expires at {token.expires_at}")
        self.core_session.headers.update(token.headers)
        return token.headers

    def _save_token_to_db(self, headers: Dict[str, Any], lifetime_hours: int = 6):
        debug(f"[SAPO::TOKEN] Saving core token (valid {lifetime_hours}h)")

        expires_at = timezone.now() + timezone.timedelta(hours=lifetime_hours)
        SapoToken.objects.update_or_create(
            key="loginss",
            defaults={
                "headers": headers,
                "expires_at": expires_at,
            },
        )
        self.core_session.headers.update(headers)

        debug(f"[SAPO::TOKEN] Core token saved, expires at {expires_at}")

    # -------------------------------------------------------
    # TMDT TOKEN (MARKETPLACE)
    # -------------------------------------------------------
    def _save_tmdt_token(self, headers: Dict[str, Any], lifetime_hours: int = 6):
        expires_at = timezone.now() + timezone.timedelta(hours=lifetime_hours)
        SapoToken.objects.update_or_create(
            key="tmdt",
            defaults={
                "headers": headers,
                "expires_at": expires_at,
            },
        )
        debug(f"[SAPO::TMDT] TMDT token saved, expires at {expires_at}")

    def _load_tmdt_token(self) -> Optional[Dict[str, Any]]:
        try:
            token = SapoToken.objects.get(key="tmdt")
        except SapoToken.DoesNotExist:
            debug("[SAPO::TMDT] No TMDT token in DB")
            return None

        if not token.is_valid():
            debug("[SAPO::TMDT] TMDT token expired")
            return None

        debug(f"[SAPO::TMDT] TMDT token OK, expires at {token.expires_at}")
        return token.headers

    def _apply_tmdt_headers_to_session(self, headers: Dict[str, Any]):
        """
        Nhận full headers đã capture từ Selenium và apply vào tmdt_session:
        - Tách cookie, cho vào session.cookies
        - Bỏ host (requests tự set)
        - Còn lại set vào session.headers
        """
        h = dict(headers)  # copy

        raw_cookie = h.pop("cookie", None)
        h.pop("host", None)

        # apply headers
        self.tmdt_session.headers.clear()
        self.tmdt_session.headers.update(h)

        # apply cookies nếu có
        if raw_cookie:
            cookies = {}
            for kv in raw_cookie.split("; "):
                if "=" in kv:
                    k, v = kv.split("=", 1)
                    cookies[k] = v
            self.tmdt_session.cookies.update(cookies)

        self._tmdt_headers = h  # lưu lại nếu cần debug
        debug("[SAPO::TMDT] Applied TMDT headers + cookies to tmdt_session ✓")

    # -------------------------------------------------------
    # KIỂM TRA TOKEN CÓ DÙNG ĐƯỢC KHÔNG
    # -------------------------------------------------------
    def _check_token_valid_remote(self) -> bool:
        debug("[SAPO::CHECK] Testing core token with /orders.json ...")
        try:
            url_orders = f"{SAPO_BASIC.MAIN_URL}/orders.json"
            res = self.core_session.get(url_orders, timeout=10)
            if res.status_code != 200:
                debug(f"[SAPO::CHECK] Invalid status {res.status_code}")
                return False
            if len(res.text) < 500:
                debug("[SAPO::CHECK] Response too short, maybe login failed")
                return False
            debug("[SAPO::CHECK] Core token is VALID ✓")
            return True
        except Exception as e:
            debug(f"[SAPO::CHECK] EXCEPTION: {e}")
            return False

    def _ensure_logged_in(self):
        debug("[SAPO] Ensuring core login...")

        if self.core_valid:
            debug("[SAPO] Core session already valid, skip login ✓")
            return

        if not self.core_initialized:
            debug("[SAPO] First-time init → load core token from DB")
            headers = self._load_token_from_db()
            self.core_initialized = True

            if headers:
                debug("[SAPO] Core token loaded → checking valid...")
                if self._check_token_valid_remote():
                    debug("[SAPO] Ready ✓ (use DB core token)")
                    self.core_valid = True
                    return
                else:
                    debug("[SAPO] Core token invalid → need new login")

        # Chưa có token hợp lệ → login bằng browser
        debug("[SAPO] Core login via browser required → start")
        core_headers = self._login_via_browser()
        self._save_token_to_db(core_headers)
        self.core_valid = True
        debug("[SAPO] Core login done ✓ (browser)")

    # -------------------------------------------------------
    # LOGIN SELENIUM – LẤY CẢ CORE + MARKETPLACE TOKEN
    # -------------------------------------------------------
    def _login_via_browser(self) -> Dict[str, Any]:
        debug("[SAPO::LOGIN] Starting browser login (Chrome headless)...")

        chrome_options = webdriver.ChromeOptions()
        # chrome_options.add_argument("--headless")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--window-size=1920,1080")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("executable_path=chromedriver.exe")

        DRIVER_CR = webdriver.Chrome(options=chrome_options)
        captured_core_headers: Dict[str, str] = {}

        try:
            debug("[SAPO::LOGIN] Opening login page...")
            DRIVER_CR.get(f"{SAPO_BASIC.MAIN_URL}/authorization/login")

            login = WebDriverWait(DRIVER_CR, 50).until(
                EC.presence_of_element_located((By.XPATH, SAPO_BASIC.LOGIN_USERNAME_FIELD))
            )
            password = WebDriverWait(DRIVER_CR, 50).until(
                EC.presence_of_element_located((By.XPATH, SAPO_BASIC.LOGIN_PASSWORD_FIELD))
            )
            login_button = WebDriverWait(DRIVER_CR, 50).until(
                EC.presence_of_element_located((By.XPATH, SAPO_BASIC.LOGIN_BUTTON))
            )

            debug("[SAPO::LOGIN] Sending credentials...")
            login.send_keys(SAPO_BASIC.USERNAME)
            password.send_keys(SAPO_BASIC.PASSWORD)
            time.sleep(2)
            login_button.click()

            debug("[SAPO::LOGIN] Waiting for dashboard...")
            time.sleep(5)
            DRIVER_CR.get(f"{SAPO_BASIC.MAIN_URL}/dashboard")
            time.sleep(10)

            # CORE HEADERS
            debug("[SAPO::LOGIN] Capturing headers (core)...")
            for request in DRIVER_CR.requests:
                if "delivery_service_providers.json" in request.url:
                    debug(f"[SAPO::LOGIN] Found target core request: {request.url}")
                    captured_core_headers = dict(request.headers)
                    break

            # ====== TMDT LOGIN (MARKETPLACE) ======
            debug("[SAPO::TMDT] Getting marketplace token...")

            DRIVER_CR.get(f"{SAPO_BASIC.MAIN_URL}/apps/market-place/home/overview")
            time.sleep(30)

            tmdt_headers = None

            # Ưu tiên bắt /v2/orders, nếu không thì fallback /scopes
            for req in DRIVER_CR.requests:
                if "/v2/orders" in req.url:
                    debug(f"[SAPO::TMDT] Found /v2/orders request: {req.url}")
                    tmdt_headers = dict(req.headers)
                    break

            if not tmdt_headers:
                for req in DRIVER_CR.requests:
                    if "/api/staffs/" in req.url and "/scopes" in req.url:
                        debug(f"[SAPO::TMDT] Fallback scopes request: {req.url}")
                        tmdt_headers = dict(req.headers)
                        break

            if tmdt_headers:
                self._save_tmdt_token(tmdt_headers)
                debug("[SAPO::TMDT] TMDT headers (FULL) saved ✓")
            else:
                debug("[SAPO::TMDT] ERROR: Cannot capture any marketplace headers")

        finally:
            DRIVER_CR.quit()

        if not captured_core_headers:
            debug("[SAPO::LOGIN] ERROR: No core headers captured")
            raise RuntimeError("Không lấy được headers login Sapo")

        debug("[SAPO::LOGIN] Captured core headers OK ✓")
        return captured_core_headers

    def _check_tmdt_valid_remote(self, headers: Dict[str, Any]) -> bool:
        """
        Gọi đến SCOPES_URL để xem TMDT token còn sống không.
        """
        try:
            url = f"{SAPO_TMDT.SCOPES_URL}/api/staffs/319911/scopes"
            res = requests.get(url, headers=headers, timeout=10)
            if res.status_code != 200:
                debug(f"[SAPO::TMDT] Invalid status {res.status_code}")
                return False

            data = res.json()
            if "sapo_account_id" not in data:
                debug("[SAPO::TMDT] No sapo_account_id in response")
                return False

            debug("[SAPO::TMDT] TMDT token is VALID ✓")
            return True
        except Exception as e:
            debug(f"[SAPO::TMDT] EXCEPTION: {e}")
            return False

    def _ensure_tmdt_headers(self):
        """
        Đảm bảo đã có session cho Marketplace:
          1. Đọc full headers từ DB.
          2. Check còn sống (scopes).
          3. Nếu không → gọi _login_via_browser (sẽ lưu lại tmdt token mới).
        """
        if self.tmdt_valid:
            return

        headers = self._load_tmdt_token()

        if headers and self._check_tmdt_valid_remote(headers):
            debug("[SAPO::TMDT] Using existing TMDT token from DB ✓")
            self._apply_tmdt_headers_to_session(headers)
            self.tmdt_valid = True
            return

        debug("[SAPO::TMDT] Need refresh TMDT token → force browser login")

        # Reset core state cho chắc, để _login_via_browser chạy lại
        self.core_valid = False
        self.core_initialized = False

        core_headers = self._login_via_browser()
        self._save_token_to_db(core_headers)

        headers = self._load_tmdt_token()
        if not headers or not self._check_tmdt_valid_remote(headers):
            raise RuntimeError("Không lấy được TMDT token sau khi login")

        self._apply_tmdt_headers_to_session(headers)
        self.tmdt_valid = True
        debug("[SAPO::TMDT] TMDT headers ready ✓")

    # -------------------------------------------------------
    # PUBLIC HTTP METHODS (CORE)
    # -------------------------------------------------------
    def get(self, path: str, **kwargs) -> requests.Response:
        debug(f"[SAPO::REQ] CORE GET {path}")
        self._ensure_logged_in()
        url = SAPO_BASIC.MAIN_URL.rstrip("/") + "/" + path.lstrip("/")
        return self.core_session.get(url, **kwargs)

    def post(self, path: str, **kwargs) -> requests.Response:
        debug(f"[SAPO::REQ] CORE POST {path}")
        self._ensure_logged_in()
        url = SAPO_BASIC.MAIN_URL.rstrip("/") + "/" + path.lstrip("/")
        return self.core_session.post(url, **kwargs)

    def put(self, path: str, **kwargs) -> requests.Response:
        debug(f"[SAPO::REQ] CORE PUT {path}")
        self._ensure_logged_in()
        url = SAPO_BASIC.MAIN_URL.rstrip("/") + "/" + path.lstrip("/")
        return self.core_session.put(url, **kwargs)

    # -------------------------------------------------------
    # EXPOSE API CLIENTS
    # -------------------------------------------------------
    @property
    def core_api(self) -> SapoCoreAPI:
        """API cho kênh CORE (https://.../admin/orders.json, customers.json...)"""
        self._ensure_logged_in()
        return SapoCoreAPI(base_url=SAPO_BASIC.MAIN_URL, session=self.core_session)

    @property
    def marketplace_api(self) -> SapoMarketplaceAPI:
        """API cho Marketplace (https://market-place.sapoapps.vn/v2)"""
        self._ensure_tmdt_headers()
        return SapoMarketplaceAPI(
            base_url="https://market-place.sapoapps.vn",
            session=self.tmdt_session,
        )
