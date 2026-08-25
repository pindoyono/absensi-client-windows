"""
Setup device — alur otomatis: Login Google → Registrasi Device → Simpan API Key.

Alur:
1. Admin buka browser login Google
2. Setelah callback ke localhost, app ambil ID token
3. Kirim ID token ke /auth/login/google → dapat JWT
4. Pakai JWT untuk POST /device/register → dapat API key
5. Simpan API key ke config lokal
"""
from __future__ import annotations

import json
import logging
import os
import socket
import threading
from dataclasses import dataclass
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Optional
from urllib.parse import urlparse, parse_qs, urlencode

import requests

logger = logging.getLogger(__name__)

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "data", "device_config.json")


@dataclass
class SetupResult:
    success: bool
    api_key: str = ""
    device_id: str = ""
    nama: str = ""
    role: str = ""
    error: str = ""
    jwt_token: str = ""


def _cari_port_kosong() -> int:
    """Cari port localhost yang tersedia."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class _OAuthCallbackHandler(BaseHTTPRequestHandler):
    """Handler sederhana untuk menangkap callback OAuth dari browser."""

    auth_code: str | None = None

    def do_GET(self):
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)

        if "code" in params:
            _OAuthCallbackHandler.auth_code = params["code"][0]
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(
                b"<html><body><h2>Login Berhasil!</h2>"
                b"<p>Silakan kembali ke aplikasi.</p>"
                b"<script>window.close();</script></body></html>"
            )
        elif "error" in params:
            self.send_response(400)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            error_msg = params.get("error_description", params["error"])[0]
            self.wfile.write(f"<h2>Error: {error_msg}</h2>".encode())
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        pass  # Suppress HTTP server logs


def buka_browser_google_oauth(
    client_id: str,
    redirect_uri: str,
    scopes: list[str] | None = None,
) -> str | None:
    """Buka browser untuk Google OAuth login. Return auth code atau None."""
    if scopes is None:
        scopes = [
            "openid",
            "email",
            "profile",
        ]

    _OAuthCallbackHandler.auth_code = None

    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": " ".join(scopes),
        "access_type": "offline",
        "prompt": "consent",
    }

    auth_url = f"https://accounts.google.com/o/oauth2/auth?{urlencode(params)}"

    # Buka browser
    import webbrowser
    webbrowser.open(auth_url)

    # Jalankan HTTP server untuk tangkap callback
    parsed = urlparse(redirect_uri)
    port = parsed.port or 8080
    server = HTTPServer(("127.0.0.1", port), _OAuthCallbackHandler)

    logger.info("Menunggu callback OAuth di %s ...", redirect_uri)
    server.timeout = 120  # 2 menit timeout
    server.handle_request()

    return _OAuthCallbackHandler.auth_code


def tukar_code_untuk_token(
    client_id: str, client_secret: str, code: str, redirect_uri: str,
) -> dict:
    """Tukar authorization code untuk Google tokens."""
    resp = requests.post(
        "https://oauth2.googleapis.com/token",
        data={
            "code": code,
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        },
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()


def login_dengan_id_token(server_url: str, google_id_token: str) -> dict:
    """Login ke server menggunakan Google ID token."""
    resp = requests.post(
        f"{server_url}/auth/login/google",
        json={"google_id_token": google_id_token},
        timeout=15,
    )
    if resp.status_code == 200:
        return resp.json()
    resp.raise_for_status()
    return {}


def registrasi_device(
    server_url: str, jwt_token: str,
    device_id: str, nama_lokasi: str, platform: str = "windows",
) -> dict:
    """Registrasi device ke server. Return data device (termasuk api_key jika ada)."""
    headers = {"Authorization": f"Bearer {jwt_token}"}
    resp = requests.post(
        f"{server_url}/device/register",
        json={
            "device_id": device_id,
            "nama_lokasi": nama_lokasi,
            "platform": platform,
        },
        headers=headers,
        timeout=15,
    )
    if resp.status_code in (200, 201):
        return resp.json()
    resp.raise_for_status()
    return {}


def simpan_config_lokal(api_key: str, device_id: str, jwt_token: str = "") -> None:
    """Simpan API key dan device ID ke config lokal."""
    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
    config = {}
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "r") as f:
            config = json.load(f)

    config["api_key"] = api_key
    config["device_id"] = device_id
    if jwt_token:
        config["jwt_token"] = jwt_token

    with open(CONFIG_PATH, "w") as f:
        json.dump(config, f, indent=2)

    logger.info("Config tersimpan ke %s", CONFIG_PATH)


def load_config_lokal() -> dict:
    """Load config lokal. Return dict kosong jika tidak ada."""
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "r") as f:
            return json.load(f)
    return {}


def update_env_file(api_key: str) -> None:
    """Update DEVICE_API_KEY di file .env."""
    env_path = os.path.join(os.path.dirname(__file__), "..", "..", ".env")
    if not os.path.exists(env_path):
        return

    lines = []
    with open(env_path, "r") as f:
        for line in f:
            if line.strip().startswith("DEVICE_API_KEY="):
                lines.append(f"DEVICE_API_KEY={api_key}\n")
            else:
                lines.append(line)

    with open(env_path, "w") as f:
        f.writelines(lines)

    logger.info("API Key diperbarui di .env")


def proses_setup_device(
    server_url: str, device_id: str, nama_lokasi: str,
    google_client_id: str = "", google_client_secret: str = "",
) -> SetupResult:
    """
    Alur lengkap setup device:
    1. Login Google (ID token dari browser)
    2. Register device
    3. Simpan config

    Return SetupResult.
    """
    # Cek apakah sudah ada config lokal
    config = load_config_lokal()
    if config.get("api_key") and config.get("device_id") == device_id:
        # Sudah terdaftar, cek apakah masih valid
        try:
            headers = {"X-Device-Api-Key": config["api_key"]}
            resp = requests.get(f"{server_url}/health", headers=headers, timeout=5)
            if resp.status_code == 200:
                return SetupResult(
                    success=True,
                    api_key=config["api_key"],
                    device_id=device_id,
                    jwt_token=config.get("jwt_token", ""),
                )
        except requests.RequestException:
            pass

    return SetupResult(success=False, error="Perlu login Google terlebih dahulu")


def proses_login_google_manual(
    server_url: str, google_id_token: str, device_id: str, nama_lokasi: str,
) -> SetupResult:
    """Login dengan ID token manual (paste dari browser)."""
    try:
        # Login ke server
        login_data = login_dengan_id_token(server_url, google_id_token)
        jwt_token = login_data.get("access_token", "")

        if not jwt_token:
            return SetupResult(success=False, error="Server tidak mengembalikan token")

        # Register device
        device_data = registrasi_device(server_url, jwt_token, device_id, nama_lokasi)
        api_key = device_data.get("api_key", "")

        if not api_key:
            return SetupResult(
                success=False, jwt_token=jwt_token,
                error="Registrasi berhasil tapi server tidak mengembalikan API key",
            )

        # Simpan config
        simpan_config_lokal(api_key, device_id, jwt_token)
        update_env_file(api_key)

        return SetupResult(
            success=True, api_key=api_key, device_id=device_id,
            jwt_token=jwt_token,
            nama=login_data.get("nama", ""),
            role=login_data.get("role", ""),
        )

    except requests.RequestException as e:
        return SetupResult(success=False, error=f"Error jaringan: {e}")
    except Exception as e:
        return SetupResult(success=False, error=f"Error: {e}")
