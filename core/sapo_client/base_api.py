# core/sapo_client/base_api.py
from typing import Optional, Dict, Any

import requests

SAPO_DEBUG = False

def debug(*args, **kwargs):
    if SAPO_DEBUG:
        print(*args, **kwargs)

class BaseAPIClient:
    """
    Client HTTP cho 1 base_url cụ thể.
    """
    def __init__(self, base_url: str, session: requests.Session, extra_headers: Optional[Dict[str, str]] = None):
        self.base_url = base_url.rstrip("/")
        self.session = session
        self.extra_headers = extra_headers or {}

    def _build_url(self, path: str) -> str:
        return self.base_url + "/" + path.lstrip("/")

    def get(self, path: str, **kwargs) -> requests.Response:
        headers = kwargs.pop("headers", {})
        headers.update(self.extra_headers)
        url = self._build_url(path)
        debug("[HTTP][GET]", url, "params=", kwargs.get("params"))

        return self.session.get(self._build_url(path), headers=headers, **kwargs)

    def post(self, path: str, **kwargs) -> requests.Response:
        headers = kwargs.pop("headers", {})
        headers.update(self.extra_headers)
        return self.session.post(self._build_url(path), headers=headers, **kwargs)

    def put(self, path: str, **kwargs) -> requests.Response:
        headers = kwargs.pop("headers", {})
        headers.update(self.extra_headers)
        return self.session.put(self._build_url(path), headers=headers, **kwargs)
