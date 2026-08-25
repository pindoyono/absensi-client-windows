import cv2
import numpy as np
import os
from app.face.minifasnet_engine import MiniFASNetEngine
from app.database.db import get_connection
from app.database.repository import AbsensiRepository

def enroll_manual():
    engine = MiniFASNetEngine("models/minifasnet.onnx", "models/arcface.onnx")
    repo = AbsensiRepository(get_connection())

    cap = cv2.VideoCapture(0)
    print("Menyiapkan kamera... Pastikan wajah terlihat jelas.")
    
    # Bersihkan buffer
    for _ in range(10): cap.read()
    
    ok, frame = cap.read()
    cap.release()

    if not ok:
        print("Gagal mengakses kamera.")
        return

    hasil = engine.proses_frame(frame)
    if hasil.embedding is not None:
        from app.face.crypto_embedding import encrypt_embedding
        from app.config import settings
        from datetime import datetime
        
        # Simpan data siswa ke siswa_cache
        repo.upsert_siswa(1, "NIS001", "Siswa Uji", "XI")
        
        # Enkripsi embedding dan simpan ke embedding_cache
        emb_encrypted = encrypt_embedding(hasil.embedding, settings.face_encryption_key)
        repo.upsert_embedding(1, emb_encrypted, engine.model_version, datetime.now().isoformat())
        
        print("\n✅ Enrollment SUKSES!")
        print("Data 'Siswa Uji' (ID: 1) telah disimpan ke database lokal.")
        print("Sekarang jalankan 'python main.py' dan berdiri di depan kamera.")
    else:
        print(f"\n❌ Gagal: {hasil.alasan_gagal}")

if __name__ == "__main__":
    enroll_manual()
