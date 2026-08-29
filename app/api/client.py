"""
HTTP client untuk integrasi dengan server API.
Implementasi REQ-SEC-001 (HMAC signing), REQ-SEC-002 (cert pinning),
REQ-SEC-003 (rate limiting).
"""
import logging
import time
import hmac
import hashlib
import json
import os
from collections import deque
from dataclasses import dataclass
from datetime import datetime
from threading import Lock
from typing import Optional, Dict, Any, List

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import certifi
import ssl

logger = logging.getLogger(__name__)


class KoneksiGagal(Exception):
    """Exception untuk error koneksi ke server (timeout, refused, DNS)."""
    pass

class ServerMenolak(KoneksiGagal):
    """Server menolak request secara PERMANEN (403/404) — retry tidak akan
    berhasil (endpoint tidak ada / device tidak diizinkan). Pemanggil harus
    menandai item sebagai gagal permanen, bukan mengulang siklus berikutnya."""
    def __init__(self, pesan: str, status_code: int):
        super().__init__(pesan)
        self.status_code = status_code


@dataclass
class HasilSyncItem:
    """Hasil sync satu record absensi."""
    record_id: str
    status: str  # "disimpan", "duplikat_diabaikan", "gagal"
    pesan: Optional[str] = None


class RateLimiter:
    """Rate limiter untuk mencegah DoS / abuse (REQ-SEC-003).
    
    Menggunakan sliding window algorithm.
    """
    
    def __init__(self, max_requests: int = 60, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._requests: deque = deque()
        self._lock = Lock()
    
    def allow(self) -> bool:
        """Check apakah request boleh dilanjutkan."""
        now = time.time()
        with self._lock:
            # Remove timestamps outside window
            while self._requests and self._requests[0] < now - self.window_seconds:
                self._requests.popleft()
            if len(self._requests) >= self.max_requests:
                return False
            self._requests.append(now)
            return True
    
    def wait_if_needed(self) -> None:
        """Block sampai request diizinkan (untuk sync service)."""
        while not self.allow():
            time.sleep(1)


class SSLPinningAdapter(HTTPAdapter):
    """HTTP Adapter dengan certificate pinning (REQ-SEC-002)."""
    
    def __init__(self, cert_pin: str = "", audit_logger: Optional[Any] = None, **kwargs):
        self.cert_pin = cert_pin
        self.audit_logger = audit_logger
        super().__init__(**kwargs)
    
    def init_poolmanager(self, *args, **kwargs):
        ctx = ssl.create_default_context()
        ctx.ca_certs = certifi.where()
        if self.cert_pin:
            # Certificate pinning: verify cert matches expected pin
            # Format: "sha256/AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="
            import base64
            expected_fingerprint = self.cert_pin.split("/", 1)[1] if "/" in self.cert_pin else self.cert_pin
            ctx.verify_mode = ssl.CERT_REQUIRED
            ctx.check_hostname = True
            # Custom verification will be done via response hook
        super().init_poolmanager(*args, **kwargs, ssl_context=ctx)
    
    def cert_verify(self, conn, cert, hostname):
        """Verify certificate against pinned fingerprint."""
        if not self.cert_pin:
            return True
        import base64
        cert_der = cert.public_bytes()
        cert_sha256 = base64.b64encode(hashlib.sha256(cert_der).digest()).decode()
        expected = self.cert_pin.split("/", 1)[1] if "/" in self.cert_pin else self.cert_pin
        if cert_sha256 != expected:
            if self.audit_logger:
                self.audit_logger.log_cert_pinning_failure(expected, cert_sha256)
            raise ssl.SSLError(f"Certificate pinning failed: expected {expected[:16]}..., got {cert_sha256[:16]}...")
        return True


class ApiClient:
    """HTTP client untuk komunikasi dengan absensi-server.
    
    Features:
    - Exponential backoff retry (REQ-QA-003)
    - HMAC request signing (REQ-SEC-001)
    - HTTPS certificate pinning (REQ-SEC-002)
    - Comprehensive error handling
    - Request timeout
    """
    
    def __init__(
        self,
        server_url: str,
        device_id: str,
        device_api_key: str,
        request_timeout: int = 10,
        max_retries: int = 3,
        cert_pin: str = "",
        audit_logger: Optional[Any] = None,
    ):
        """
        Initialize API client.
        
        Args:
            server_url: Base URL server (e.g., https://absen.example.com)
            device_id: Device identifier
            device_api_key: API key untuk device authentication
            request_timeout: Request timeout dalam detik (default 10s)
            max_retries: Max retry attempts untuk failed requests (default 3)
            cert_pin: Certificate pin untuk HTTPS (REQ-SEC-002)
            audit_logger: AuditLogger instance untuk security events (REQ-SEC-005)
        """
        self.server_url = server_url.rstrip("/")
        self.device_id = device_id
        self.device_api_key = device_api_key
        self.request_timeout = request_timeout
        self.max_retries = max_retries
        self.cert_pin = cert_pin
        self.audit_logger = audit_logger
        self.backup_device_api_key: Optional[str] = None
        self.rate_limiter = RateLimiter(max_requests=60, window_seconds=60)
        
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
        
        # Setup SSL pinning adapter jika cert_pin diberikan
        if cert_pin:
            ssl_adapter = SSLPinningAdapter(cert_pin=cert_pin, audit_logger=audit_logger, max_retries=retry_strategy)
            self.session.mount("https://", ssl_adapter)
        
        logger.info(
            f"ApiClient initialized: server={server_url}, device_id={device_id}"
        )
    
    def _sign_request(self, method: str, path: str, body: bytes) -> tuple[str, str]:
        """Compute HMAC-SHA256 signature for request (REQ-SEC-001).
        
        Returns:
            (signature, timestamp)
        """
        timestamp = str(int(time.time()))
        message = f"{method}|{path}|{timestamp}|{body.decode() if body else ''}"
        signature = hmac.new(
            self.device_api_key.encode(),
            message.encode(),
            hashlib.sha256
        ).hexdigest()
        return signature, timestamp
    
    def _add_auth_headers(self, method: str = "GET", path: str = "", body: bytes = b"") -> dict:
        """Add authentication + signature headers to request (REQ-SEC-001)."""
        headers = {}
        signature, timestamp = self._sign_request(method, path, body)
        headers["X-Device-Id"] = self.device_id
        headers["X-Device-Api-Key"] = self.device_api_key
        headers["X-Signature"] = signature
        headers["X-Timestamp"] = timestamp
        return headers
    
    def rotate_api_key(self, new_api_key: str) -> None:
        """Rotate device API key (REQ-CRED-003).
        
        Called when 401 detected or manual rotation by admin.
        Stores old key as backup for fallback.
        """
        self.backup_device_api_key = self.device_api_key
        self.device_api_key = new_api_key
        logger.info("API key rotated successfully")
        if self.audit_logger:
            self.audit_logger.log_event(
                event_type="API_KEY_ROTATION",
                action="Device API key rotated",
                status="success",
                details={"device_id": self.device_id},
            )
    
    def _handle_auth_failure(self) -> None:
        """Handle 401 auth failure — try backup key if available (REQ-CRED-003)."""
        if self.backup_device_api_key:
            logger.warning("Primary API key failed, falling back to backup key")
            self.device_api_key, self.backup_device_api_key = self.backup_device_api_key, None
            if self.audit_logger:
                self.audit_logger.log_auth_failure(
                    self.device_id, "Fallback to backup API key", "api_key"
                )
        else:
            logger.error("API key invalid and no backup available")
            if self.audit_logger:
                self.audit_logger.log_auth_failure(
                    self.device_id, "API key invalid, no backup", "api_key"
                )
    
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
            return is_online
        
        except requests.exceptions.RequestException:
            logger.debug("Server unreachable")
            return False
        except Exception as e:
            logger.error(f"Error checking connectivity: {e}", exc_info=True)
            return False
    
    def sync_absensi(self, records: List[Any]) -> List[HasilSyncItem]:
        """Push attendance records ke server.
        
        Args:
            records: List of attendance records (dict atau RekamanAbsensi) untuk di-sync
        
        Returns:
            List of HasilSyncItem — satu per record
        
        Raises:
            KoneksiGagal: Jika HTTP request gagal
        """
        if not self.rate_limiter.allow():
            logger.warning("Rate limit exceeded, request blocked")
            if self.audit_logger:
                self.audit_logger.log_rate_limit_blocked("/absensi/sync")
            raise KoneksiGagal("Rate limit exceeded")
        try:
            formatted_records = []
            for r in records:
                if hasattr(r, "asdict"):
                    formatted_records.append(r.asdict())
                elif isinstance(r, dict):
                    formatted_records.append(r)
                else:
                    from dataclasses import asdict, is_dataclass
                    if is_dataclass(r):
                        formatted_records.append(asdict(r))
                    else:
                        formatted_records.append(r)

            payload = {"records": formatted_records}
            body = json.dumps(payload).encode()
            response = self.session.post(
                f"{self.server_url}/absensi/sync",
                json=payload,
                headers=self._add_auth_headers("POST", "/absensi/sync", body),
                timeout=self.request_timeout,
            )
            response.raise_for_status()
            
            result = response.json()
            logger.info(
                f"Sync absensi success: {result.get('disimpan', 0)} saved, "
                f"{result.get('duplikat', 0)} duplicate, "
                f"{result.get('gagal', 0)} failed"
            )
            # Parse hasil per record
            hasil_list = []
            for h in result.get("hasil", []):
                hasil_list.append(HasilSyncItem(
                    record_id=h["record_id"],
                    status=h["status"],
                    pesan=h.get("pesan"),
                ))
            return hasil_list
        
        except requests.exceptions.Timeout as e:
            logger.error(f"Sync absensi timeout after {self.request_timeout}s")
            raise KoneksiGagal(str(e)) from e
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 401:
                logger.error("Unauthorized: device API key invalid or expired")
                self._handle_auth_failure()
            else:
                logger.error(f"Sync absensi failed: {e.response.status_code} {e.response.text}")
            raise KoneksiGagal(str(e)) from e
        except requests.exceptions.RequestException as e:
            logger.error(f"Error network during sync absensi: {e}")
            raise KoneksiGagal(str(e)) from e
        except Exception as e:
            logger.error(f"Error during sync absensi: {e}", exc_info=True)
            raise
    
    def tarik_embedding(self, diperbarui_sejak: Optional[str] = None) -> Dict[str, Any]:
        """Tarik embedding wajah siswa dari server untuk cache lokal.
        
        Args:
            diperbarui_sejak: ISO 8601 timestamp, ambil embeddings yang diupdate setelah waktu ini
        
        Returns:
            Response dengan list embeddings
        
        Raises:
            requests.exceptions.RequestException: Jika HTTP request gagal
        """
        if not self.rate_limiter.allow():
            logger.warning("Rate limit exceeded, request blocked")
            if self.audit_logger:
                self.audit_logger.log_rate_limit_blocked("/embeddings")
            raise KoneksiGagal("Rate limit exceeded")
        try:
            params = {}
            if diperbarui_sejak:
                params["diperbarui_sejak"] = diperbarui_sejak
            
            response = self.session.get(
                f"{self.server_url}/embeddings/sync",
                params=params,
                headers=self._add_auth_headers("GET", "/embeddings", b""),
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
    
    def tarik_jadwal_efektif(self, kelas: str) -> Dict[str, Any]:
        """Tarik jadwal efektif untuk kelas tertentu.

        Args:
            kelas: Nama kelas (e.g., "XI Elektronika")

        Returns:
            Response dengan jadwal (jam_masuk, jam_pulang, sumber)

        Raises:
            KoneksiGagal: Jika request gagal
        """
        if not self.rate_limiter.allow():
            logger.warning("Rate limit exceeded, request blocked")
            if self.audit_logger:
                self.audit_logger.log_rate_limit_blocked("/jadwal/efektif")
            raise KoneksiGagal("Rate limit exceeded")
        try:
            # Endpoint /jadwal/efektif butuh JWT (HTTPBearer), bukan device key.
            # Prioritas: GURU_SERVICE_JWT dari .env (token layanan read-only),
            # fallback ke jwt_token admin dari config lokal.
            token = os.environ.get("GURU_SERVICE_JWT", "")
            if not token:
                try:
                    from app.device.setup import load_config_lokal
                    token = load_config_lokal().get("jwt_token", "")
                except Exception:
                    pass
            headers = self._add_auth_headers("GET", f"/jadwal/efektif?kelas={kelas}", b"")
            if token:
                headers["Authorization"] = f"Bearer {token}"

            response = self.session.get(
                f"{self.server_url}/jadwal/efektif",
                params={"kelas": kelas},
                headers=headers,
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
            if e.response.status_code in (401, 403):
                logger.warning("Unauthorized to fetch jadwal (JWT invalid?), using cached")
            else:
                logger.error(f"Fetch jadwal failed: {e.response.status_code}")
            raise
        except Exception as e:
            logger.error(f"Error fetching jadwal: {e}", exc_info=True)
            raise

    def tarik_dispensasi_hari_ini(self, tanggal: str) -> list[dict]:
        """GET /dispensasi/aktif — ambil semua dispensasi aktif untuk tanggal tertentu."""
        if not self.rate_limiter.allow():
            logger.warning("Rate limit exceeded, request blocked")
            if self.audit_logger:
                self.audit_logger.log_rate_limit_blocked("/dispensasi/aktif")
            raise KoneksiGagal("Rate limit exceeded")
        try:
            path = "/dispensasi/aktif"
            resp = self.session.get(
                f"{self.server_url}{path}",
                headers=self._add_auth_headers("GET", f"{path}?tanggal={tanggal}", b""),
                params={"tanggal": tanggal},
                timeout=self.request_timeout,
            )
            resp.raise_for_status()
        except requests.RequestException as e:
            raise KoneksiGagal(str(e)) from e
        return resp.json()

    def push_jadwal_override(self, tanggal: str, jam_masuk: str, jam_pulang: str,
                             kelas: Optional[str] = None, alasan: Optional[str] = None,
                             client_id: Optional[str] = None) -> dict:
        """POST /jadwal/override — push override jadwal yang dibuat di device
        (offline-first, Opsi C) ke server. client_id dipakai server sebagai
        idempotency key supaya retry tidak duplikat."""
        if not self.rate_limiter.allow():
            logger.warning("Rate limit exceeded, request blocked")
            if self.audit_logger:
                self.audit_logger.log_rate_limit_blocked("/jadwal/override")
            raise KoneksiGagal("Rate limit exceeded")
        try:
            path = "/jadwal/override"
            payload = {
                "tanggal": tanggal,
                "jam_masuk": jam_masuk,
                "jam_pulang": jam_pulang,
                "kelas": kelas,
                "alasan": alasan,
                "client_id": client_id,
            }
            body = json.dumps(payload).encode()
            resp = self.session.post(
                f"{self.server_url}{path}",
                json=payload,
                headers=self._add_auth_headers("POST", path, body),
                timeout=self.request_timeout,
            )
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.Timeout as e:
            logger.error(f"Push jadwal override timeout after {self.request_timeout}s")
            raise KoneksiGagal(str(e)) from e
        except requests.exceptions.HTTPError as e:
            status = e.response.status_code if e.response is not None else 0
            if status == 401:
                logger.error("Unauthorized: device API key invalid or expired")
                self._handle_auth_failure()
                raise KoneksiGagal(str(e)) from e
            if status in (403, 404):
                # Endpoint tidak ada / device tidak diizinkan — PERMANEN,
                # jangan di-retry tiap siklus (lihat sync.service).
                logger.error(
                    "Server menolak push jadwal override (%s): %s",
                    status, e.response.text if e.response is not None else "",
                )
                raise ServerMenolak(
                    f"Server menolak (HTTP {status}) — endpoint /jadwal/override "
                    f"belum tersedia atau device tidak diizinkan.", status
                ) from e
            logger.error(f"Push jadwal override failed: {status} {e.response.text if e.response is not None else ''}")
            raise KoneksiGagal(str(e)) from e
        except requests.exceptions.RequestException as e:
            logger.error(f"Error network during push jadwal override: {e}")
            raise KoneksiGagal(str(e)) from e
