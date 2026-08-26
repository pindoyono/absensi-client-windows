"""
HTTP client untuk integrasi dengan server API.
Implementasi REQ-CRED-001 (JWT auto-refresh) dan REQ-QA-003 (error handling).
"""
import logging
import time
import jwt as pyjwt
from datetime import datetime, timedelta
from threading import Timer
from typing import Optional, Dict, Any, List

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)


class ApiClient:
    """HTTP client untuk komunikasi dengan absensi-server.
    
    Features:
    - JWT service token auto-refresh (REQ-CRED-001)
    - Exponential backoff retry (REQ-QA-003)
    - Comprehensive error handling
    - Request timeout
    """
    
    def __init__(
        self,
        server_url: str,
        device_id: str,
        device_api_key: str,
        service_jwt: str = "",
        request_timeout: int = 10,
        max_retries: int = 3,
    ):
        """
        Initialize API client.
        
        Args:
            server_url: Base URL server (e.g., https://absen.example.com)
            device_id: Device identifier
            device_api_key: API key untuk device authentication
            service_jwt: JWT token untuk akses endpoint yang butuh guru auth (jadwal)
            request_timeout: Request timeout dalam detik (default 10s)
            max_retries: Max retry attempts untuk failed requests (default 3)
        """
        self.server_url = server_url.rstrip("/")
        self.device_id = device_id
        self.device_api_key = device_api_key
        self.service_jwt = service_jwt
        self.request_timeout = request_timeout
        self.max_retries = max_retries
        self.jwt_refresh_timer: Optional[Timer] = None
        
        # Setup session dengan retry strategy (exponential backoff)
        self.session = requests.Session()
        retry_strategy = Retry(
            total=max_retries,
            backoff_factor=1,  # 1s, 2s, 4s, 8s
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["HEAD", "GET", "OPTIONS", "POST"],
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)
        
        logger.info(
            f"ApiClient initialized: server={server_url}, device_id={device_id}"
        )
        
        # Schedule JWT refresh jika service_jwt ada
        if self.service_jwt:
            self._schedule_jwt_refresh()
    
    def _schedule_jwt_refresh(self) -> None:
        """Schedule JWT refresh 1 jam sebelum expiry (REQ-CRED-001)."""
        try:
            decoded = pyjwt.decode(
                self.service_jwt,
                options={"verify_signature": False}
            )
            exp_time = decoded.get("exp")
            
            if not exp_time:
                logger.warning("JWT has no expiry, skipping refresh scheduling")
                return
            
            now = time.time()
            time_until_expiry = exp_time - now
            
            # Refresh 1 jam (3600s) sebelum expiry, minimal 60s
            refresh_in = max(time_until_expiry - 3600, 60)
            
            logger.info(
                f"JWT refresh scheduled in {refresh_in/3600:.1f} hours "
                f"(expiry in {time_until_expiry/3600:.1f} hours)"
            )
            
            # Cancel existing timer jika ada
            if self.jwt_refresh_timer:
                self.jwt_refresh_timer.cancel()
            
            self.jwt_refresh_timer = Timer(refresh_in, self._refresh_jwt)
            self.jwt_refresh_timer.daemon = True
            self.jwt_refresh_timer.start()
        
        except pyjwt.DecodeError as e:
            logger.warning(f"Failed to decode JWT for refresh scheduling: {e}")
        except Exception as e:
            logger.error(f"Error scheduling JWT refresh: {e}", exc_info=True)
    
    def _refresh_jwt(self) -> None:
        """Refresh service JWT (REQ-CRED-001)."""
        try:
            logger.info("Attempting to refresh service JWT")
            response = self.session.post(
                f"{self.server_url}/auth/refresh-service-jwt",
                headers={"X-Device-Api-Key": self.device_api_key},
                timeout=self.request_timeout,
            )
            response.raise_for_status()
            
            new_jwt = response.json().get("service_jwt")
            if new_jwt:
                self.service_jwt = new_jwt
                logger.info("Service JWT refreshed successfully")
                self._schedule_jwt_refresh()  # Schedule next refresh
            else:
                logger.error("Server did not return new JWT")
        
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to refresh JWT: {e}")
            # Don't crash, will retry at next sync cycle
        except Exception as e:
            logger.error(f"Unexpected error during JWT refresh: {e}", exc_info=True)
    
    def _add_auth_headers(self, headers: Optional[Dict] = None) -> Dict:
        """Add authentication headers ke request.
        
        Returns:
            Headers dict dengan device API key + service JWT (jika ada)
        """
        if headers is None:
            headers = {}
        
        headers["X-Device-Id"] = self.device_id
        headers["X-Device-Api-Key"] = self.device_api_key
        
        if self.service_jwt:
            headers["Authorization"] = f"Bearer {self.service_jwt}"
        
        return headers
    
    def cek_koneksi(self) -> bool:
        """Check connectivity ke server.
        
        Returns:
            True jika server terjangkau, False jika tidak
        """
        try:
            response = self.session.get(
                f"{self.server_url}/health",
                timeout=self.request_timeout,
            )
            is_online = response.status_code == 200
            logger.info(f"Connectivity check: {'online' if is_online else 'offline'}")
            
            # Trigger JWT refresh jika offline sebelumnya dan sekarang online
            if is_online and self.service_jwt and not self.jwt_refresh_timer:
                self._schedule_jwt_refresh()
            
            return is_online
        
        except requests.exceptions.RequestException:
            logger.debug("Server unreachable")
            return False
        except Exception as e:
            logger.error(f"Error checking connectivity: {e}", exc_info=True)
            return False
    
    def sync_absensi(self, records: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Push attendance records ke server.
        
        Args:
            records: List of attendance records untuk di-sync
        
        Returns:
            Response dari server dengan status setiap record
        
        Raises:
            requests.exceptions.RequestException: Jika HTTP request gagal
        """
        try:
            payload = {"records": records}
            response = self.session.post(
                f"{self.server_url}/absensi/sync",
                json=payload,
                headers=self._add_auth_headers(),
                timeout=self.request_timeout,
            )
            response.raise_for_status()
            
            result = response.json()
            logger.info(
                f"Sync absensi success: {result.get('disimpan', 0)} saved, "
                f"{result.get('duplikat', 0)} duplicate, "
                f"{result.get('gagal', 0)} failed"
            )
            return result
        
        except requests.exceptions.Timeout:
            logger.error(f"Sync absensi timeout after {self.request_timeout}s")
            raise
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 401:
                logger.error("Unauthorized: device API key invalid or expired")
            else:
                logger.error(f"Sync absensi failed: {e.response.status_code} {e.response.text}")
            raise
        except Exception as e:
            logger.error(f"Error during sync absensi: {e}", exc_info=True)
            raise
    
    def fetch_embeddings(self, updated_since: Optional[str] = None) -> Dict[str, Any]:
        """Fetch embedded wajah siswa untuk sync ke cache lokal.
        
        Args:
            updated_since: ISO 8601 timestamp, ambil embeddings yang diupdate setelah waktu ini
        
        Returns:
            Response dengan list embeddings
        
        Raises:
            requests.exceptions.RequestException: Jika HTTP request gagal
        """
        try:
            params = {}
            if updated_since:
                params["diperbarui_sejak"] = updated_since
            
            response = self.session.get(
                f"{self.server_url}/embeddings/sync",
                params=params,
                headers=self._add_auth_headers(),
                timeout=self.request_timeout,
            )
            response.raise_for_status()
            
            result = response.json()
            logger.info(f"Fetched embeddings: {result.get('jumlah', 0)} records")
            return result
        
        except requests.exceptions.Timeout:
            logger.error(f"Fetch embeddings timeout after {self.request_timeout}s")
            raise
        except requests.exceptions.HTTPError as e:
            logger.error(f"Fetch embeddings failed: {e.response.status_code}")
            raise
        except Exception as e:
            logger.error(f"Error fetching embeddings: {e}", exc_info=True)
            raise
    
    def fetch_jadwal(self, kelas: str) -> Dict[str, Any]:
        """Fetch jadwal efektif untuk kelas tertentu.
        
        Args:
            kelas: Nama kelas (e.g., "XI Elektronika")
        
        Returns:
            Response dengan jadwal (jam_masuk, jam_pulang, sumber)
        
        Raises:
            requests.exceptions.RequestException: Jika HTTP request gagal
        """
        try:
            response = self.session.get(
                f"{self.server_url}/jadwal/efektif",
                params={"kelas": kelas},
                headers=self._add_auth_headers(),
                timeout=self.request_timeout,
            )
            response.raise_for_status()
            
            result = response.json()
            logger.debug(f"Fetched jadwal for {kelas}: {result}")
            return result
        
        except requests.exceptions.Timeout:
            logger.error(f"Fetch jadwal timeout after {self.request_timeout}s")
            raise
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 401:
                logger.warning("Unauthorized to fetch jadwal (service JWT expired?), using cached")
            else:
                logger.error(f"Fetch jadwal failed: {e.response.status_code}")
            raise
        except Exception as e:
            logger.error(f"Error fetching jadwal: {e}", exc_info=True)
            raise
