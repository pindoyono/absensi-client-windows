"""
Dekripsi embedding wajah yang ditarik dari server. Logika ini SENGAJA
identik dengan app/services/crypto.py di project absensi-server —
key yang sama (FACE_ENCRYPTION_KEY) harus didistribusikan manual oleh
admin ke tiap device (lihat docs/API_CONTRACT.md bagian 7, Opsi A).
"""
import struct

from cryptography.fernet import Fernet, InvalidToken


class KunciEnkripsiSalah(Exception):
    pass


def decrypt_embedding(encrypted: bytes, key: str) -> list[float]:
    fernet = Fernet(key.encode())
    try:
        raw = fernet.decrypt(encrypted)
    except InvalidToken as e:
        raise KunciEnkripsiSalah(
            "Gagal dekripsi embedding — FACE_ENCRYPTION_KEY di device ini "
            "tidak cocok dengan yang dipakai server saat enrollment"
        ) from e
    n_floats = len(raw) // 4
    return list(struct.unpack(f"{n_floats}f", raw))


def encrypt_embedding(embedding: list[float] | np.ndarray, key: str) -> bytes:
    """Enkripsi embedding float list/array menjadi bytes terenkripsi Fernet."""
    if hasattr(embedding, "tolist"):
        embedding = embedding.tolist()
    raw = struct.pack(f"{len(embedding)}f", *embedding)
    fernet = Fernet(key.encode())
    return fernet.encrypt(raw)
