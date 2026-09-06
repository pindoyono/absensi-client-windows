"""AdminWindow._normalisasi_jadwal_override — harus mempertahankan `id`
supaya tombol hapus override server (DELETE /jadwal/override/{id}) bisa jalan."""
from app.ui.admin_window import AdminWindow

_norm = AdminWindow._normalisasi_jadwal_override


def test_pertahankan_id_dari_response_server():
    hasil = _norm([
        {"id": 12, "tanggal": "2026-09-03", "kelas": None,
         "jam_masuk": "07:13:00", "jam_pulang": "10:13:00", "alasan": "ss"},
    ])
    assert hasil[0]["id"] == 12
    assert hasil[0]["kelas"] == "Semua kelas"
    assert hasil[0]["tanggal"] == "2026-09-03"


def test_input_bukan_list_atau_bukan_dict_aman():
    assert _norm(None) == []
    assert _norm("bukan list") == []
    assert _norm([1, "x", None]) == []


def test_id_hilang_jadi_none_bukan_error():
    hasil = _norm([{"tanggal": "2026-09-06", "jam_masuk": "07:00", "jam_pulang": "15:00"}])
    assert hasil[0]["id"] is None
