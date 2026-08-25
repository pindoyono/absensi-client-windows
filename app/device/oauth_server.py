"""
OAuth 2.0 otomatis untuk Google Login — zero-paste.

Flow:
  1. Mulai HTTP server lokal (localhost) di port random.
  2. Buka browser ke Google OAuth consent screen (dengan PKCE).
  3. User login → Google redirect ke localhost/?code=...
  4. Tukar authorization code (dengan PKCE) → ID token.
  5. Kirim ID token ke POST /auth/login/google → JWT + role.
  6. Register device via POST /device/register → API key.
  7. Simpan config lokal → .env + device_config.json.
  8. Matikan server lokal. Status ONLINE.

Client ID: Google OAuth Client ID dari project Google Cloud Console.
  - Bisa di-set via env GOOGLE_CLIENT_ID atau data/device_config.json
  - Jika tidak ada, flow manual (paste token) masih bisa dipakai
  - PKCE flow tidak butuh client_secret (aman untuk desktop app)
"""

import base64
import hashlib
import json
import os
import threading
import time
import urllib.parse
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path

import requests

# ── Google OAuth endpoints ──
GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"

# Scope: openid + email + profile
SCOPES = "openid email profile"

# Redirect URI (localhost — tanpa path agar sesuai Authorized redirect URI root)
REDIRECT_HOST = "localhost"
REDIRECT_PORT = 18080
REDIRECT_PATH = "/"
REDIRECT_URI = f"http://{REDIRECT_HOST}:{REDIRECT_PORT}"

# File config
DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
CONFIG_FILE = DATA_DIR / "device_config.json"
ENV_FILE = DATA_DIR / ".env"


# ═══════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════


DEFAULT_CLIENT_ID = "726713411026-ugpcekftqkj7qna8ov3vcv1lgkoid8nu.apps.googleusercontent.com"


def get_client_id() -> str:
    """Ambil Google Client ID dari env, config, atau default."""
    cid = os.environ.get("GOOGLE_CLIENT_ID", "")
    if cid:
        return cid
    try:
        cfg = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        cid = cfg.get("google_client_id", "")
        if cid:
            return cid
    except Exception:
        pass
    return DEFAULT_CLIENT_ID


def _generate_pkce_pair() -> tuple[str, str]:
    """Generate PKCE code_verifier dan code_challenge (S256)."""
    verifier = base64.urlsafe_b64encode(os.urandom(32)).decode("ascii").rstrip("=")
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest())
        .decode("ascii")
        .rstrip("=")
    )
    return verifier, challenge


class _OAuthCallbackHandler(BaseHTTPRequestHandler):
    """HTTP handler untuk menangkap Google OAuth redirect."""

    # Shared state dari parent
    auth_code: str | None = None
    auth_error: str | None = None
    done_event: threading.Event | None = None
    server_ref: "OAuthCallbackServer | None" = None

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)

        if parsed.path != REDIRECT_PATH:
            self.send_response(404)
            self.end_headers()
            return

        params = urllib.parse.parse_qs(parsed.query)

        if "code" in params:
            _OAuthCallbackHandler.auth_code = params["code"][0]
            _OAuthCallbackHandler.auth_error = None
            # Tampilkan halaman sukses
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(
                b"<html><body style='font-family:sans-serif;text-align:center;padding:60px;'>"
                b"<h1>&#x2705; Login Berhasil!</h1>"
                b"<p>Anda bisa menutup browser ini.</p>"
                b"<p>Device akan otomatis terdaftar ke server.</p>"
                b"</body></html>"
            )
        elif "error" in params:
            _OAuthCallbackHandler.auth_error = params["error"][0]
            self.send_response(400)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            msg = urllib.parse.unquote_plus(params.get("error_description", ["Unknown error"])[0])
            self.wfile.write(
                f"<html><body style='font-family:sans-serif;text-align:center;padding:60px;'>"
                f"<h1>&#x274C; Login Gagal</h1><p>{msg}</p></body></html>".encode()
            )
        else:
            # Implicit flow: id_token ada di fragment (#), tidak dikirim ke server.
            # Tampilkan halaman JS yang extract fragment lalu POST ke /token endpoint lokal.
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            html = (
                "<!DOCTYPE html><html><head><meta charset='utf-8'>"
                "<title>Memproses Login...</title></head><body>"
                "<h1>Memproses login...</h1>"
                "<script>"
                "try {"
                "  var hash = window.location.hash.substring(1);"
                "  var params = new URLSearchParams(hash);"
                "  var idToken = params.get('id_token');"
                "  var error = params.get('error');"
                "  if (error) {"
                "    document.body.innerHTML = '<h1>&#x274C; Login Gagal</h1><p>' + error + '</p>';"
                "  } else if (idToken) {"
                "    var xhr = new XMLHttpRequest();"
                "    xhr.open('POST', '/token', false);"
                "    xhr.setRequestHeader('Content-Type', 'application/json');"
                "    xhr.send(JSON.stringify({id_token: idToken}));"
                "    if (xhr.status === 200) {"
                "      document.body.innerHTML = '<h1>&#x2705; Login Berhasil!</h1><p>Anda bisa menutup browser ini.</p>';"
                "    } else {"
                "      document.body.innerHTML = '<h1>&#x274C; Gagal kirim token ke aplikasi</h1><p>' + xhr.status + '</p>';"
                "    }"
                "  } else {"
                "    document.body.innerHTML = '<h1>&#x274C; Tidak ada token di URL</h1><p>Hash: ' + window.location.hash + '</p>';"
                "  }"
                "} catch(e) {"
                "  document.body.innerHTML = '<h1>&#x274C; Error</h1><p>' + e.message + '</p>';"
                "}"
                "</script>"
                "</body></html>"
            )
            self.wfile.write(html.encode("utf-8"))
            # JANGAN set event atau shutdown di sini — token datang via do_POST
            return

        if _OAuthCallbackHandler.done_event:
            _OAuthCallbackHandler.done_event.set()

        if _OAuthCallbackHandler.server_ref:
            threading.Thread(target=lambda: (_shutdown_server(_OAuthCallbackHandler.server_ref)), daemon=True).start()

    def do_POST(self):
        """Terima id_token dari halaman callback JS (implicit flow)."""
        if self.path != "/token":
            self.send_response(404)
            self.end_headers()
            return

        try:
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length).decode("utf-8")
            data = json.loads(body)
            _OAuthCallbackHandler.auth_code = data.get("id_token", "")
            _OAuthCallbackHandler.auth_error = None
        except Exception as e:
            _OAuthCallbackHandler.auth_error = f"parse_error: {e}"
            self.send_response(400)
            self.end_headers()
            return

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"status":"ok"}')

        if _OAuthCallbackHandler.done_event:
            _OAuthCallbackHandler.done_event.set()
        if _OAuthCallbackHandler.server_ref:
            threading.Thread(target=lambda: (_shutdown_server(_OAuthCallbackHandler.server_ref)), daemon=True).start()

    def log_message(self, format, *args):
        pass  # Suppress HTTP logs


def _shutdown_server(server: "OAuthCallbackServer"):
    time.sleep(0.5)
    try:
        server.shutdown()
    except Exception:
        pass


class OAuthCallbackServer:
    """HTTP server sederhana untuk OAuth callback."""

    def __init__(self):
        self.port = REDIRECT_PORT
        self._httpd: HTTPServer | None = None

    def start_and_wait(self, timeout: int = 300) -> tuple[str | None, str | None]:
        """
        Start server, tunggu callback.
        Return (auth_code, auth_error).
        """
        _OAuthCallbackHandler.auth_code = None
        _OAuthCallbackHandler.auth_error = None
        _OAuthCallbackHandler.done_event = threading.Event()
        _OAuthCallbackHandler.server_ref = None

        self._httpd = HTTPServer(("127.0.0.1", self.port), _OAuthCallbackHandler)
        _OAuthCallbackHandler.server_ref = self._httpd

        thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)
        thread.start()

        try:
            _OAuthCallbackHandler.done_event.wait(timeout=timeout)
        finally:
            try:
                self._httpd.shutdown()
            except Exception:
                pass

        return _OAuthCallbackHandler.auth_code, _OAuthCallbackHandler.auth_error


def tukar_code_untuk_token(
    code: str,
    client_id: str,
    client_secret: str,
    redirect_uri: str,
) -> dict:
    """Tukar authorization code untuk ID token."""
    resp = requests.post(
        GOOGLE_TOKEN_URL,
        data={
            "code": code,
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        },
        timeout=30,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"Token exchange gagal: {resp.status_code} {resp.text}")
    return resp.json()


def simpan_config_device(
    api_key: str,
    device_id: str,
    nama_lokasi: str,
    nama: str = "",
    role: str = "",
    email: str = "",
    google_client_id: str = "",
    jwt_token: str = "",
):
    """Simpan konfigurasi device ke .env dan device_config.json."""
    from app.device.setup import simpan_config_lokal, update_env_file, load_config_lokal
    simpan_config_lokal(api_key, device_id, jwt_token, role=role, nama=nama)
    update_env_file(api_key)
    
    # Update tambahan info ke config
    cfg = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    cfg.update({
        "nama": nama,
        "role": role,
        "email": email,
        "google_client_id": google_client_id
    })
    CONFIG_FILE.write_text(json.dumps(cfg, indent=2), encoding="utf-8")


class LoginResult:
    def __init__(self):
        self.success: bool = False
        self.jwt_token: str = ""
        self.api_key: str = ""
        self.nama: str = ""
        self.role: str = ""
        self.email: str = ""
        self.error: str = ""


def proses_oauth_token(
    server_url: str,
    id_token: str,
    device_id: str,
    nama_lokasi: str = "",
    google_client_id: str = "",
) -> LoginResult:
    """
    Kirim id_token ke server → register device → simpan config.
    Dipanggil dari UI atau dari OAuth callback.
    """
    from app.device.setup import load_config_lokal

    result = LoginResult()

    # 1. Login ke server
    try:
        resp = requests.post(
            f"{server_url}/auth/login/google",
            json={"google_id_token": id_token},
            timeout=15,
        )
        if resp.status_code != 200:
            result.error = f"Login gagal ({resp.status_code}): {resp.text}"
            return result
    except Exception as e:
        result.error = f"Koneksi server gagal: {e}"
        return result

    data = resp.json()
    jwt_token = data.get("access_token", "")
    nama = data.get("nama", "")
    role = data.get("role", "")
    result.jwt_token = jwt_token
    result.nama = nama
    result.role = role

    # 2. Register device
    try:
        resp_reg = requests.post(
            f"{server_url}/device/register",
            headers={"Authorization": f"Bearer {jwt_token}"},
            json={
                "device_id": device_id,
                "nama_lokasi": nama_lokasi or "Gerbang Utama",
                "platform": "windows",
            },
            timeout=15,
        )
        if resp_reg.status_code == 409:
            # Device sudah terdaftar — pakai API key lokal yang tersimpan
            config = load_config_lokal()
            api_key = config.get("api_key", "")
            if not api_key:
                result.error = "Device sudah terdaftar tapi API key tidak ditemukan di lokal"
                return result
            result.api_key = api_key
        elif resp_reg.status_code != 200:
            result.error = f"Registrasi device gagal ({resp_reg.status_code}): {resp_reg.text}"
            return result
        else:
            reg_data = resp_reg.json()
            api_key = reg_data.get("api_key", reg_data.get("device_api_key", ""))
            result.api_key = api_key
    except Exception as e:
        result.error = f"Registrasi device gagal: {e}"
        return result

    # 3. Simpan config lokal
    simpan_config_device(
        api_key=api_key,
        device_id=device_id,
        nama_lokasi=nama_lokasi,
        nama=nama,
        role=role,
        google_client_id=google_client_id,
        jwt_token=jwt_token,
    )

    result.success = True
    return result


def mulai_google_oauth_flow(
    server_url: str,
    device_id: str,
    nama_lokasi: str = "",
    on_progress=None,
    on_success=None,
    on_error=None,
) -> str | None:
    """
    Mulai flow OAuth Google otomatis.
    Buka browser → login → callback → register.

    Return: None jika flow berjalan (async), atau string error jika gagal langsung.
    Callback: on_success(api_key, nama), on_error(msg)
    """
    client_id = get_client_id()

    if not client_id:
        return (
            "Google Client ID belum dikonfigurasi.\n"
            "Set env GOOGLE_CLIENT_ID atau isi google_client_id di data/device_config.json.\n"
            "Bisa juga paste token manual di bawah."
        )

    client_secret = os.environ.get("GOOGLE_CLIENT_SECRET", "")

    # Mulai local server
    if on_progress:
        on_progress("Menjalankan server callback lokal...")

    try:
        server = OAuthCallbackServer()
    except Exception as e:
        return f"Gagal menjalankan server lokal: {e}"

    redirect_uri = REDIRECT_URI

    # Build Google OAuth URL (Implicit flow — ID token langsung di fragment)
    nonce = base64.urlsafe_b64encode(os.urandom(16)).decode("ascii")
    auth_params = urllib.parse.urlencode({
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "id_token",
        "scope": SCOPES,
        "prompt": "consent",
        "nonce": nonce,
    })
    auth_url = f"{GOOGLE_AUTH_URL}?{auth_params}"

    # Buka browser
    import webbrowser
    webbrowser.open(auth_url)

    if on_progress:
        on_progress("Browser terbuka. Login dengan akun Google sekolah...")

    # Jalankan server di thread terpisah
    def _run_flow():
        try:
            code, error = server.start_and_wait(timeout=300)
        except Exception as e:
            if on_error:
                on_error(f"Server error: {e}")
            return

        if error or not code:
            if on_error:
                on_error(f"Login Google gagal: {error or 'Tidak ada ID token diterima'}")
            return

        # Implicit flow: code = id_token (langsung dari callback)
        id_token = code

        if not id_token:
            if on_error:
                on_error("Tidak mendapat ID token dari Google")
            return

        if on_progress:
            on_progress("Login ke server & daftarkan device...")

        # Proses login + register
        result = proses_oauth_token(
            server_url=server_url,
            id_token=id_token,
            device_id=device_id,
            nama_lokasi=nama_lokasi,
            google_client_id=client_id,
        )

        if result.success:
            if on_success:
                on_success(result.api_key, result.nama)
        else:
            if on_error:
                on_error(result.error)

    thread = threading.Thread(target=_run_flow, daemon=True)
    thread.start()

    return None  # Flow berjalan async
