"""
Interface abstrak untuk deteksi wajah + liveness + embedding.

PENTING: Ini adalah TITIK INTEGRASI untuk model MiniFASNet yang sudah
pernah dibangun sebelumnya (project terpisah). Implementasi di
opencv_engine.py adalah PLACEHOLDER untuk membuktikan seluruh pipeline
(capture -> deteksi -> embedding -> matching -> business logic -> sync)
bekerja, BUKAN untuk dipakai produksi — akurasinya tidak memadai untuk
1000 siswa sungguhan.

Sebelum pilot dengan siswa asli, ganti FaceEngine di titik ini dengan
adapter yang memanggil MiniFASNet yang sudah ada, mengikuti interface
yang sama persis (lihat class FaceEngine di bawah) supaya tidak perlu
ubah kode lain sama sekali.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

import numpy as np


@dataclass
class HasilDeteksi:
    wajah_terdeteksi: bool
    lolos_liveness: bool
    embedding: np.ndarray | None  # vector float, None kalau wajah/liveness gagal
    alasan_gagal: str | None = None


class FaceEngine(ABC):
    """Kontrak yang harus dipenuhi model apapun yang dipakai (MiniFASNet,
    ArcFace, dst) — sync worker & UI kiosk hanya bicara lewat interface
    ini, tidak tahu model konkretnya."""

    @abstractmethod
    def proses_frame(self, frame_bgr: np.ndarray) -> HasilDeteksi:
        """Input: 1 frame kamera (BGR, format OpenCV standar).
        Output: HasilDeteksi — kalau wajah_terdeteksi=False atau
        lolos_liveness=False, embedding harus None."""
        ...

    @abstractmethod
    def jarak_embedding(self, emb1: np.ndarray, emb2: np.ndarray) -> float:
        """Jarak antar 2 embedding — semakin kecil semakin mirip.
        Dipakai untuk cari siswa yang paling cocok di cache lokal."""
        ...

    @property
    @abstractmethod
    def model_version(self) -> str:
        ...
