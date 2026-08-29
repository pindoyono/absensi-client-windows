import pytest
import requests.exceptions
import responses

from app.api.client import ApiClient, KoneksiGagal
from app.database.repository import RekamanAbsensi


BASE_URL = "https://absen.smkn2malinau.sch.id"


@responses.activate
def test_cek_koneksi_online():
    responses.add(responses.GET, f"{BASE_URL}/health", json={"status": "ok"}, status=200)
    api = ApiClient(BASE_URL, "dev1", "key1")
    assert api.cek_koneksi() is True


@responses.activate
def test_cek_koneksi_offline_tidak_raise():
    responses.add(responses.GET, f"{BASE_URL}/health", body=requests.exceptions.ConnectionError())
    api = ApiClient(BASE_URL, "dev1", "key1")
    # TIDAK BOLEH melempar exception — harus balik False dengan tenang
    assert api.cek_koneksi() is False


@responses.activate
def test_sync_absensi_format_request_sesuai_kontrak():
    responses.add(
        responses.POST, f"{BASE_URL}/absensi/sync",
        json={
            "total": 1, "disimpan": 1, "duplikat": 0, "gagal": 0,
            "hasil": [{"record_id": "rid-1", "status": "disimpan", "pesan": None}],
        },
        status=200,
    )
    api = ApiClient(BASE_URL, "dev1", "rahasia-key")
    rekaman = RekamanAbsensi(
        "rid-1", 1, "2026-08-24", "MASUK", "2026-08-24T07:00:00",
        "NORMAL", None, "dev1", False, None,
    )
    hasil = api.sync_absensi([rekaman.asdict()])

    assert len(hasil) == 1
    assert hasil[0].status == "disimpan"

    # Verifikasi header X-Device-Api-Key terkirim (kontrak wajib, lihat API_CONTRACT.md)
    req = responses.calls[0].request
    assert req.headers["X-Device-Api-Key"] == "rahasia-key"

    import json
    body = json.loads(req.body)
    assert body["records"][0]["record_id"] == "rid-1"
    assert body["records"][0]["type"] == "MASUK"


@responses.activate
def test_sync_absensi_gagal_jadi_koneksi_gagal_bukan_crash():
    responses.add(responses.POST, f"{BASE_URL}/absensi/sync", body=requests.exceptions.ConnectionError())
    api = ApiClient(BASE_URL, "dev1", "key1")
    rekaman = RekamanAbsensi("rid-1", 1, "2026-08-24", "MASUK", "x", "NORMAL", None, "dev1", False, None)

    try:
        api.sync_absensi([rekaman])
        assert False, "Seharusnya melempar KoneksiGagal"
    except KoneksiGagal:
        pass  # sesuai harapan


@responses.activate
def test_tarik_embedding_header_device_id():
    responses.add(
        responses.GET, f"{BASE_URL}/embeddings/sync",
        json={"server_time": "2026-08-24T10:00:00", "jumlah": 0, "data": []},
        status=200,
    )
    api = ApiClient(BASE_URL, "kiosk-01", "key1")
    api.tarik_embedding()

    req = responses.calls[0].request
    assert req.headers["X-Device-Id"] == "kiosk-01"
    assert req.headers["X-Device-Api-Key"] == "key1"


@responses.activate
def test_tarik_jadwal_dengan_device_api_key_terkirim_benar():
    responses.add(
        responses.GET, f"{BASE_URL}/jadwal/efektif",
        json={"sumber": "standar", "jam_masuk": "07:00:00", "jam_pulang": "15:00:00"},
        status=200,
    )
    api = ApiClient(BASE_URL, "dev1", "key1")
    hasil = api.tarik_jadwal_efektif("XI Elektronika")

    assert hasil["jam_masuk"] == "07:00:00"
    req = responses.calls[0].request
    assert req.headers["X-Device-Id"] == "dev1"
    assert req.headers["X-Device-Api-Key"] == "key1"
    assert "kelas=XI" in req.url
