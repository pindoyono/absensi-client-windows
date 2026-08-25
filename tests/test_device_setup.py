import json
import pytest
from app.device.setup import simpan_config_lokal, load_config_lokal

def test_simpan_dan_load_config(tmp_path, monkeypatch):
    # Mock CONFIG_PATH
    config_file = tmp_path / "device_config.json"
    monkeypatch.setattr("app.device.setup.CONFIG_PATH", str(config_file))

    simpan_config_lokal("key-123", "kiosk-01", "jwt-abc", role="admin", nama="Admin")
    hasil = load_config_lokal()

    assert hasil["api_key"] == "key-123"
    assert hasil["device_id"] == "kiosk-01"
    assert hasil["jwt_token"] == "jwt-abc"
    assert hasil["role"] == "admin"
    assert hasil["admin_nama"] == "Admin"
