import struct

import numpy as np
import pytest
from cryptography.fernet import Fernet

from app.face.opencv_engine import OpenCVPlaceholderEngine
from app.face.crypto_embedding import decrypt_embedding, KunciEnkripsiSalah
from app.face.matcher import cari_siswa_cocok


@pytest.fixture()
def engine():
    return OpenCVPlaceholderEngine()


def test_frame_kosong_tidak_terdeteksi_wajah(engine):
    frame_kosong = np.zeros((300, 300, 3), dtype=np.uint8)
    hasil = engine.proses_frame(frame_kosong)
    assert hasil.wajah_terdeteksi is False
    assert hasil.embedding is None


def test_jarak_embedding_identik_nol(engine):
    e = np.array([1.0, 2.0, 3.0])
    assert engine.jarak_embedding(e, e) == 0.0


def test_jarak_embedding_berbeda_positif(engine):
    e1 = np.array([1.0, 0.0])
    e2 = np.array([0.0, 1.0])
    assert engine.jarak_embedding(e1, e2) > 0


def _encrypt(vec: list[float], key: str) -> bytes:
    fernet = Fernet(key.encode())
    raw = struct.pack(f"{len(vec)}f", *vec)
    return fernet.encrypt(raw)


def test_decrypt_embedding_roundtrip():
    key = Fernet.generate_key().decode()
    original = [0.1, 0.2, -0.3, 0.4]
    encrypted = _encrypt(original, key)

    decrypted = decrypt_embedding(encrypted, key)
    for a, b in zip(original, decrypted):
        assert abs(a - b) < 1e-5


def test_decrypt_embedding_key_salah_raise_error_jelas():
    key_benar = Fernet.generate_key().decode()
    key_salah = Fernet.generate_key().decode()
    encrypted = _encrypt([0.1, 0.2], key_benar)

    with pytest.raises(KunciEnkripsiSalah):
        decrypt_embedding(encrypted, key_salah)


def test_matcher_menemukan_siswa_paling_mirip(repo, engine):
    key = Fernet.generate_key().decode()
    emb_a = [1.0, 0.0, 0.0] + [0.0] * 509
    emb_b = [0.0, 1.0, 0.0] + [0.0] * 509

    repo.upsert_siswa(1, "A001", "Siswa A", "XI")
    repo.upsert_siswa(2, "A002", "Siswa B", "XI")
    repo.upsert_embedding(1, _encrypt(emb_a, key), "test-v0", "2026-08-24T00:00:00")
    repo.upsert_embedding(2, _encrypt(emb_b, key), "test-v0", "2026-08-24T00:00:00")

    capture = np.array([0.95, 0.05, 0.0] + [0.0] * 509, dtype=np.float32)
    hasil = cari_siswa_cocok(capture, repo, engine, key)

    assert hasil.ditemukan is True
    assert hasil.siswa_id == 1


def test_matcher_wajah_asing_tidak_ditemukan(repo, engine):
    key = Fernet.generate_key().decode()
    emb_a = [1.0, 0.0, 0.0] + [0.0] * 509
    repo.upsert_siswa(1, "A001", "Siswa A", "XI")
    repo.upsert_embedding(1, _encrypt(emb_a, key), "test-v0", "2026-08-24T00:00:00")

    capture_asing = np.array([0.0, 0.0, 1.0] + [0.0] * 509, dtype=np.float32)
    hasil = cari_siswa_cocok(capture_asing, repo, engine, key)

    assert hasil.ditemukan is False


def test_matcher_cache_kosong_tidak_ditemukan(repo, engine):
    capture = np.random.rand(512).astype(np.float32)
    hasil = cari_siswa_cocok(capture, repo, engine, Fernet.generate_key().decode())
    assert hasil.ditemukan is False

def test_hapus_embedding_tidak_sesuai_kunci(repo):
    key_lama = Fernet.generate_key().decode()
    key_baru = Fernet.generate_key().decode()
    repo.upsert_siswa(1, "A001", "Siswa A", "XI")
    repo.upsert_siswa(2, "A002", "Siswa B", "XI")
    # Embedding 1 dienkripsi kunci lama, embedding 2 kunci baru
    repo.upsert_embedding(1, _encrypt([0.1, 0.2], key_lama), "test-v0", "2026-08-24T00:00:00")
    repo.upsert_embedding(2, _encrypt([0.3, 0.4], key_baru), "test-v0", "2026-08-24T00:00:00")

    n = repo.hapus_embedding_tidak_sesuai_kunci(key_baru)
    assert n == 1  # hanya embedding 1 (kunci lama) yang dihapus
    sisa = repo.semua_embedding()
    assert [s[0] for s in sisa] == [2]

def test_hapus_embedding_tidak_sesuai_kunci_semua_cocok(repo):
    key = Fernet.generate_key().decode()
    repo.upsert_siswa(1, "A001", "Siswa A", "XI")
    repo.upsert_embedding(1, _encrypt([0.1, 0.2], key), "test-v0", "2026-08-24T00:00:00")
    assert repo.hapus_embedding_tidak_sesuai_kunci(key) == 0

def test_reset_metadata_tarik_embedding(repo):
    repo.set_metadata("embedding_diperbarui_sejak", "2026-08-24T00:00:00")
    repo.reset_metadata_tarik_embedding()
    assert repo.get_metadata("embedding_diperbarui_sejak") is None

def test_hapus_siswa_dan_embedding(repo):
    key = Fernet.generate_key().decode()
    repo.upsert_siswa(1, "A001", "Siswa A", "XI")
    repo.upsert_embedding(1, _encrypt([0.1, 0.2], key), "test-v0", "2026-08-24T00:00:00")
    assert repo.get_siswa(1) is not None
    assert repo.semua_embedding() != []

    assert repo.hapus_siswa_dan_embedding(1) is True
    assert repo.get_siswa(1) is None
    assert repo.semua_embedding() == []

def test_hapus_siswa_dan_embedding_tidak_ada(repo):
    assert repo.hapus_siswa_dan_embedding(999) is False
