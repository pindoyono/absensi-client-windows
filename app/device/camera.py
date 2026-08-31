"""
Deteksi & enumerasi kamera yang tersedia di device.

Dipakai panel admin untuk dropdown pilihan kamera aktif, dan sebagai
referensi index yang valid untuk CAMERA_INDEX di .env.
"""
from __future__ import annotations

import logging
import cv2

logger = logging.getLogger(__name__)


def daftar_kamera() -> list[dict]:
    """Enumerasi kamera yang tersedia di sistem.

    Menggunakan PySide6 QMediaDevices untuk mendapatkan nama asli hardware
    (misal: 'Logi C270 HD WebCam', 'Integrated Camera') tanpa mengunci/membuka
    stream video. Fallback ke probing OpenCV jika QMediaDevices tidak tersedia.

    Returns:
        List dict: [{"index": int, "nama": str}, ...]
    """
    hasil: list[dict] = []
    
    # 1. Coba lewat Qt Multimedia QMediaDevices (Paling akurat & cepat)
    try:
        from PySide6.QtMultimedia import QMediaDevices
        devices = QMediaDevices.videoInputs()
        if devices:
            for idx, dev in enumerate(devices):
                nama = dev.description() or f"Kamera {idx}"
                hasil.append({"index": idx, "nama": str(nama)})
            if hasil:
                return hasil
    except Exception as e:
        logger.debug("QMediaDevices gagal: %s, fallback ke OpenCV", e)

    # 2. Fallback OpenCV probing
    for i in range(4):
        cap = cv2.VideoCapture(i)
        if cap.isOpened():
            hasil.append({"index": i, "nama": f"Kamera {i}"})
            cap.release()

    return hasil