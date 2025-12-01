# core/base/repository.py
"""
Base repository class cho tất cả API clients.
Provides retry logic, error handling, và standardized HTTP methods.
"""

from abc import ABC
import requests
from typing import Dict, Any, Optional
import time
import logging

logger = logging.getLogger(__name__)


class BaseRepository(ABC):
    """
    Base repository cho API calls với retry logic và error handling.
    
    Usage:
        class MyAPIRepository(BaseRepository):
            def get_something(self, id: int) -> Dict[str, Any]:
                return self.get(f"something/{id}")
        
        repo = MyAPIRepository(session, "https://api.example.com")
        data = repo.get_something(123)
    """
    
    def __init__(self, session: requests.Session, base_url: str):
        """
        Initialize repository.
        
        Args:
            session: requests.Session với headers/cookies đã setup
            base_url: Base URL của API (không có trailing slash)
        """
        self.session = session
        self.base_url = base_url.rstrip('/')
    
    def _build_url(self, path: str) -> str:
        """
        Build full URL từ path.
        
        Args:
            path: Path relative to base_url (có thể có hoặc không có leading slash)
            
        Returns:
            Full URL
        """
        path = path.lstrip('/')
        return f"{self.base_url}/{path}"
    
    def _request(
        self, 
        method: str, 
        path: str, 
        retry: int = 3,
        retry_delay: float = 1.0,
        timeout: int = 30,
        **kwargs
    ) -> requests.Response:
        """
        Make HTTP request với retry logic.
        
        Args:
            method: HTTP method (GET, POST, PUT, DELETE)
            path: API path
            retry: Số lần retry khi gặp network error
            retry_delay: Delay giữa các retry (seconds)
            timeout: Request timeout (seconds)
            **kwargs: Additional arguments cho requests (params, json, data, headers...)
            
        Returns:
            requests.Response object
            
        Raises:
            requests.RequestException: Khi request fail sau khi retry hết
        """
        url = self._build_url(path)
        last_exception = None
        
        for attempt in range(retry):
            try:
                request_start = time.time()
                # Log full URL với params để debug
                if 'params' in kwargs:
                    from urllib.parse import urlencode
                    params_str = urlencode(kwargs['params'])
                    full_url = f"{url}?{params_str}" if params_str else url
                    logger.debug(f"[{method}] {full_url} (attempt {attempt + 1}/{retry})")
                else:
                    logger.debug(f"[{method}] {url} (attempt {attempt + 1}/{retry})")
                
                response = self.session.request(
                    method=method,
                    url=url,
                    timeout=timeout,
                    **kwargs
                )
                
                request_time = time.time() - request_start
                # Log response status và thời gian
                logger.debug(f"Response: {response.status_code} (took {request_time:.2f}s)")
                
                # Log performance cho các API calls quan trọng
                if path.startswith("orders") or path.startswith("variants"):
                    logger.info(f"[PERF] API {method} {path}: {response.status_code} in {request_time:.2f}s")
                
                return response
                
            except requests.Timeout as e:
                # Timeout: chỉ retry 1 lần để tăng tốc xử lý
                last_exception = e
                logger.warning(
                    f"Request timeout (attempt {attempt + 1}/{retry}): {e}"
                )
                
                # Chỉ retry 1 lần cho timeout (không phải 3 lần)
                timeout_retry_limit = min(1, retry - 1)
                if attempt < timeout_retry_limit:
                    logger.info(f"Retrying timeout request in {retry_delay}s...")
                    time.sleep(retry_delay)
                else:
                    logger.error(f"Request timeout after {timeout_retry_limit + 1} attempt(s), skipping...")
                    raise
            
            except requests.ConnectionError as e:
                last_exception = e
                logger.warning(
                    f"Request failed (attempt {attempt + 1}/{retry}): {e}"
                )
                
                if attempt < retry - 1:
                    # Exponential backoff
                    sleep_time = retry_delay * (2 ** attempt)
                    logger.info(f"Retrying in {sleep_time}s...")
                    time.sleep(sleep_time)
                else:
                    logger.error(f"Request failed after {retry} attempts")
                    raise
            
            except requests.RequestException as e:
                # Các lỗi khác (HTTPError, etc.) không retry
                logger.error(f"Request error: {e}")
                raise
        
        # Should not reach here, but just in case
        if last_exception:
            raise last_exception
    
    def get(self, path: str, **kwargs) -> Dict[str, Any]:
        """
        GET request.
        
        Args:
            path: API path
            **kwargs: params, headers, timeout, retry, etc.
            
        Returns:
            Response JSON as dict
        """
        response = self._request('GET', path, **kwargs)
        response.raise_for_status()
        
        try:
            return response.json()
        except ValueError:
            # Response không phải JSON
            logger.warning(f"Response is not JSON: {response.text[:200]}")
            return {}
    
    def post(self, path: str, **kwargs) -> Dict[str, Any]:
        """
        POST request.
        
        Args:
            path: API path
            **kwargs: json, data, headers, timeout, retry, etc.
            
        Returns:
            Response JSON as dict
        """
        response = self._request('POST', path, **kwargs)
        response.raise_for_status()
        
        try:
            return response.json()
        except ValueError:
            return {}
    
    def put(self, path: str, **kwargs) -> Dict[str, Any]:
        """
        PUT request.
        
        Args:
            path: API path
            **kwargs: json, data, headers, timeout, retry, etc.
            
        Returns:
            Response JSON as dict
        """
        response = self._request('PUT', path, **kwargs)
        response.raise_for_status()
        
        try:
            return response.json()
        except ValueError:
            return {}
    
    def delete(self, path: str, **kwargs) -> Dict[str, Any]:
        """
        DELETE request.
        
        Args:
            path: API path
            **kwargs: params, headers, timeout, retry, etc.
            
        Returns:
            Response JSON as dict
        """
        response = self._request('DELETE', path, **kwargs)
        response.raise_for_status()
        
        try:
            return response.json()
        except ValueError:
            return {}
    
    def get_raw_response(self, path: str, **kwargs) -> requests.Response:
        """
        GET request trả về raw Response object (không parse JSON).
        Dùng cho download file, PDF, etc.
        
        Args:
            path: API path
            **kwargs: params, headers, timeout, retry, etc.
            
        Returns:
            requests.Response object
        """
        response = self._request('GET', path, **kwargs)
        response.raise_for_status()
        return response
