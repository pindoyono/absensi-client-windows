"""
Mencocokkan embedding hasil capture kamera terhadap cache embedding
siswa lokal (sudah didekripsi). Dipanggil tiap kali FaceEngine berhasil
mendeteksi wajah + lolos liveness.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from app.database.repository import AbsensiRepository
from app.face.crypto_embedding import decrypt_embedding
from app.face.engine_base import FaceEngine


@dataclass
class HasilMatching:
    ditemukan: bool
    siswa_id: int | None = None
    nama: str | None = None
    kelas: str | None = None
    jarak: float | None = None


# Ambang batas jarak embedding — di bawah ini dianggap "orang yang sama".
# NILAI INI HARUS DIKALIBRASI ULANG saat FaceEngine diganti dari
# placeholder ke MiniFASNet — ambang batas sangat tergantung skala/
# distribusi embedding model yang dipakai, tidak bisa dipakai lintas model.
AMBANG_BATAS_JARAK = 0.4083


def cari_siswa_cocok(
    embedding_capture: np.ndarray,
    repo: AbsensiRepository,
    engine: FaceEngine,
    face_encryption_key: str,
    ambang_batas: float = AMBANG_BATAS_JARAK,
) -> HasilMatching:
    kandidat_terbaik: HasilMatching = HasilMatching(ditemukan=False)
    jarak_terkecil = float("inf")

    for siswa_id, nama, kelas, embedding_encrypted in repo.semua_embedding():
        embedding_siswa = np.array(
            decrypt_embedding(embedding_encrypted, face_encryption_key), dtype=np.float32
        )
        jarak = engine.jarak_embedding(embedding_capture, embedding_siswa)

        if jarak < jarak_terkecil:
            jarak_terkecil = jarak
            kandidat_terbaik = HasilMatching(
                ditemukan=jarak < ambang_batas,
                siswa_id=siswa_id, nama=nama, kelas=kelas, jarak=jarak,
            )

    return kandidat_terbaik
