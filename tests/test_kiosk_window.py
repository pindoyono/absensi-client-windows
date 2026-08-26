from datetime import time as dtime

from app.business.attendance_logic import HasilAbsen, KeputusanAbsen
from app.database.repository import RekamanAbsensi
from app.face.opencv_engine import OpenCVPlaceholderEngine
from app.ui.kiosk_window import KioskWindow


def _buat_window(repo, qtbot):
    engine = OpenCVPlaceholderEngine()
    window = KioskWindow(
        repo=repo, engine=engine, device_id="test-kiosk",
        face_encryption_key="dummy",
        jam_masuk_standar=dtime(7, 0), jam_pulang_standar=dtime(15, 0),
        gunakan_kamera=False,
    )
    qtbot.addWidget(window)
    window.show()  # perlu di-show supaya isVisible() pada child widget akurat (offscreen platform)
    return window


def test_window_terbentuk_dengan_state_idle(repo, qtbot):
    window = _buat_window(repo, qtbot)
    assert window.windowTitle() == "Absensi SMK — Kiosk"
    assert window.label_hasil.text() == "Arahkan wajah ke kamera"
    assert window.kartu_status.isVisible() is False


def test_tampilkan_hasil_absen_berhasil(repo, qtbot):
    window = _buat_window(repo, qtbot)
    rekaman = RekamanAbsensi("rid-1", 1, "2026-08-24", "MASUK", "2026-08-24T07:00:00",
                              "NORMAL", None, "test-kiosk", False, None)
    keputusan = KeputusanAbsen(hasil=HasilAbsen.BERHASIL_MASUK, rekaman=rekaman, pesan="Tepat waktu")

    window._tampilkan_keputusan("Ahmad Fauzan", "XI Elektronika", keputusan)

    assert window.label_nama.text() == "Ahmad Fauzan"
    assert window.label_kelas.text() == "XI Elektronika"
    assert "berhasil" in window.label_hasil.text().lower()
    assert window.kartu_status.isVisible() is True


def test_tampilkan_hasil_ditolak_sudah_absen(repo, qtbot):
    window = _buat_window(repo, qtbot)
    keputusan = KeputusanAbsen(hasil=HasilAbsen.DITOLAK_SUDAH_ABSEN, pesan="Masuk & pulang sudah tercatat hari ini")

    window._tampilkan_keputusan("Siti Rahma", "X Elektronika", keputusan)

    assert "sudah absen" in window.label_hasil.text().lower()


def test_kembali_ke_idle_mereset_tampilan(repo, qtbot):
    window = _buat_window(repo, qtbot)
    rekaman = RekamanAbsensi("rid-1", 1, "2026-08-24", "MASUK", "x", "NORMAL", None, "test-kiosk", False, None)
    keputusan = KeputusanAbsen(hasil=HasilAbsen.BERHASIL_MASUK, rekaman=rekaman, pesan="Tepat waktu")
    window._tampilkan_keputusan("Ahmad", "XI", keputusan)

    window._kembali_ke_idle()

    assert window.label_nama.text() == ""
    assert window.label_hasil.text() == "Arahkan wajah ke kamera"
    assert window.kartu_status.isVisible() is False


def test_set_status_online_offline(repo, qtbot):
    window = _buat_window(repo, qtbot)

    window.set_status_online(False)
    assert "Offline" in window.label_status_jaringan.text()

    window.set_status_online(True)
    assert "Online" in window.label_status_jaringan.text()


def test_tampilkan_hasil_spoofing(repo, qtbot):
    window = _buat_window(repo, qtbot)

    window._tampilkan_hasil_spoofing("Terdeteksi spoofing (skor: 0.12)")

    assert window.label_hasil.text() == "Akses ditolak"
    assert "foto/video" in window.label_status_detail.text().lower()
    assert window.kartu_status.isVisible() is True
