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
