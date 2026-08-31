"""
Implementasi PLACEHOLDER dari FaceEngine, pakai OpenCV Haar Cascade
(deteksi wajah) + histogram sederhana sebagai "embedding".

INI BUKAN UNTUK PRODUKSI. Tidak ada liveness detection sungguhan di
sini (anti-spoofing selalu return True) dan "embedding"-nya cuma
histogram grayscale — cukup untuk membuktikan pipeline end-to-end
bekerja (deteksi -> embedding -> bandingkan -> keputusan), TIDAK cukup
akurat untuk membedakan 1000 wajah siswa sungguhan.

Ganti dengan adapter MiniFASNet sebelum pilot — lihat catatan di
engine_base.py.
"""
from __future__ import annotations

import os
import sys
import cv2
import numpy as np

from app.face.engine_base import FaceEngine, HasilDeteksi

# Support PyInstaller bundle path
if getattr(sys, 'frozen', False):
    _CASCADE_PATH = os.path.join(sys._MEIPASS, 'cv2', 'data', 'haarcascade_frontalface_default.xml')
else:
    _CASCADE_PATH = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"


class OpenCVPlaceholderEngine(FaceEngine):
    def __init__(self):
        self._detector = cv2.CascadeClassifier(_CASCADE_PATH)
        if self._detector.empty():
            raise RuntimeError(f"Gagal load Haar Cascade dari {_CASCADE_PATH}")

    def proses_frame(self, frame_bgr: np.ndarray, skip_liveness: bool = False) -> HasilDeteksi:
        # skip_liveness tidak berpengaruh di sini — placeholder ini memang
        # tidak pernah punya liveness check sungguhan (selalu lolos)
        gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
        faces = self._detector.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(80, 80))

        if len(faces) == 0:
            return HasilDeteksi(wajah_terdeteksi=False, lolos_liveness=False, embedding=None,
                                 alasan_gagal="Wajah tidak terdeteksi")

        # Ambil wajah terbesar (paling dekat kamera)
        x, y, w, h = max(faces, key=lambda f: f[2] * f[3])
        wajah = gray[y:y + h, x:x + w]
        wajah = cv2.resize(wajah, (100, 100))

        # PLACEHOLDER embedding: histogram grayscale dinormalisasi.
        # Model asli (MiniFASNet) harus menghasilkan vector embedding
        # yang benar-benar merepresentasikan identitas wajah.
        hist = cv2.calcHist([wajah], [0], None, [64], [0, 256]).flatten()
        embedding = hist / (np.linalg.norm(hist) + 1e-8)

        # PLACEHOLDER liveness: SELALU True — TIDAK ADA anti-spoofing
        # sungguhan di sini. Ini gap keamanan yang wajib ditutup sebelum
        # produksi (foto di layar HP bisa lolos "deteksi" placeholder ini).
        return HasilDeteksi(wajah_terdeteksi=True, lolos_liveness=True, embedding=embedding)

    def jarak_embedding(self, emb1: np.ndarray, emb2: np.ndarray) -> float:
        return float(np.linalg.norm(emb1 - emb2))

    @property
    def model_version(self) -> str:
        return "opencv-placeholder-v0-BUKAN-UNTUK-PRODUKSI"
