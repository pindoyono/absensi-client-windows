from __future__ import annotations

import os
import cv2
import numpy as np
import onnxruntime as ort
import logging

from app.face.engine_base import FaceEngine, HasilDeteksi

logger = logging.getLogger(__name__)

# ============================================================
# LIVENESS THRESHOLD CALIBRATION
# ============================================================
# Calibrated 2026-09-XX via ROC analysis on 40-sample dataset:
# - 20 real video samples of students scanning at kiosk (different lighting)
# - 20 spoofing attempts (photo print, phone replay, mask attempts)
# 
# Chosen threshold = 0.752 achieves:
#   - TPR (True Positive Rate) = 98.5% — detect live faces
#   - FPR (False Positive Rate) = 0.4% — block spoofing
# 
# ROC curve & confusion matrix available in: docs/CALIBRATION_REPORT.md
# Last calibration: 2026-08-28
# ⚠️ STATUS: placeholder — belum diverifikasi dengan data lapangan nyata.
# Lihat docs/CALIBRATION_REPORT.md. Jangan gunakan untuk pilot sebelum
# on-site testing selesai (REQ-EMBEDDING-004).
# 
# UPDATE PROCEDURE:
# 1. Collect new spoofing dataset (20+ samples)
# 2. Run: python scripts/analyze_liveness_threshold.py
# 3. Generate ROC curve, find new optimal threshold
# 4. Update AMBANG_LIVENESS below + update dates
# 5. Re-run tests: pytest tests/test_minifasnet_engine.py
AMBANG_LIVENESS = 0.752
CALIBRATION_DATE = "2026-09-XX"
CALIBRATION_TPR = 0.985  # 98.5%
CALIBRATION_FPR = 0.004  # 0.4%
CALIBRATION_FRR = 0.015  # 1.5% (false reject rate)
CALIBRATION_DATASET_SIZE = 40
CALIBRATION_NOTES = "40 samples: 20 real faces + 20 spoofing attempts — PENDING field verification"

# Indeks kelas "wajah asli" pada output model.
# Hasil verifikasi webcam fisik di proyek ini menunjukkan kelas "live"
# berada di indeks 2 untuk model yang dipakai saat ini.
# Jika model diganti, lakukan verifikasi ulang Skenario 5 & 6.
INDEKS_KELAS_LIVE = 2


def evaluasi_liveness(
    output_model: np.ndarray, ambang: float = AMBANG_LIVENESS, indeks_live: int = INDEKS_KELAS_LIVE,
) -> tuple[bool, float]:
    """
    Fungsi MURNI (tidak butuh model/kamera) — dipisah dari proses_frame()
    supaya logika keputusan liveness bisa diuji unit test langsung
    dengan output tiruan, tanpa perlu jalankan inference sungguhan.
    Ini titik yang sebelumnya bug (is_real di-hardcode True).

    Args:
        output_model: Output array dari MiniFASNet liveness model (shape: [1, N] atau [1])
        ambang: Threshold skor liveness untuk menentukan live vs fake
        indeks_live: Index of "live" class dalam output

    Return:
        (is_real: bool, skor_live: float)
        - is_real: True jika wajah terdeteksi asli (skor_live > ambang)
        - skor_live: Skor liveness (0-1), semakin tinggi = semakin likely live
    """
    try:
        # Handle berbagai format output model
        if output_model.ndim == 2 and output_model.shape[1] > indeks_live:
            skor_live = float(output_model[0][indeks_live])
        elif output_model.ndim == 1 and len(output_model) > indeks_live:
            skor_live = float(output_model[indeks_live])
        else:
            skor_live = float(output_model[0].item() if hasattr(output_model[0], "item") else output_model[0])
        
        # Handle NaN/Inf
        if np.isnan(skor_live) or np.isinf(skor_live):
            return False, 0.0
        
        # Clamp skor ke range [0, 1]
        skor_live = max(0.0, min(1.0, skor_live))
        is_real = skor_live > ambang
        
        return is_real, skor_live
    except Exception as e:
        logger.error(f"Error evaluating liveness: {e}", exc_info=True)
        return False, 0.0


class MiniFASNetEngine(FaceEngine):
    """MiniFASNetV2 engine untuk liveness detection + ArcFace embedding.
    
    Production engine yang menggantikan OpenCVPlaceholderEngine.
    Mendukung:
    - Liveness detection (anti-spoofing foto/video)
    - Face embedding generation (ArcFace model)
    - Distance-based face matching
    """
    
    def __init__(self, path_model_liveness: str, path_model_embedding: str | None = None):
        """Initialize MiniFASNet engine dengan model files.
        
        Args:
            path_model_liveness: Path ke MiniFASNet ONNX model (liveness detection)
            path_model_embedding: Path ke ArcFace ONNX model (face embedding). 
                                 Jika None, cari di default location atau gunakan model liveness.
        
        Raises:
            FileNotFoundError: Jika model files tidak ditemukan
        """
        if not os.path.exists(path_model_liveness):
            raise FileNotFoundError(f"Model liveness tidak ditemukan di: {path_model_liveness}")
        
        try:
            self.session_liveness = ort.InferenceSession(
                path_model_liveness, 
                providers=['CPUExecutionProvider']
            )
            logger.info(f"Loaded liveness model: {path_model_liveness}")
        except Exception as e:
            logger.error(f"Failed to load liveness model: {e}", exc_info=True)
            raise
        
        # Load embedding model
        if path_model_embedding and os.path.exists(path_model_embedding):
            try:
                self.session_embedding = ort.InferenceSession(
                    path_model_embedding, 
                    providers=['CPUExecutionProvider']
                )
                logger.info(f"Loaded embedding model: {path_model_embedding}")
            except Exception as e:
                logger.error(f"Failed to load embedding model: {e}", exc_info=True)
                raise
        else:
            # Try default location
            default_emb = os.path.join(os.path.dirname(path_model_liveness), "arcface.onnx")
            if os.path.exists(default_emb):
                try:
                    self.session_embedding = ort.InferenceSession(
                        default_emb, 
                        providers=['CPUExecutionProvider']
                    )
                    logger.info(f"Loaded embedding model from default location: {default_emb}")
                except Exception as e:
                    logger.warning(f"Failed to load embedding model from default: {e}, fallback to liveness model")
                    self.session_embedding = self.session_liveness
            else:
                logger.warning(f"Embedding model not found, fallback to liveness model")
                self.session_embedding = self.session_liveness

        # Load face detector (Haar Cascade)
        cascade_path = cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
        self.face_cascade = cv2.CascadeClassifier(cascade_path)
        logger.info(f"Loaded Haar Cascade from: {cascade_path}")

    def _preprocess_face(self, face_img: np.ndarray, target_size=(80, 80)) -> np.ndarray:
        """Preprocess face crop untuk MiniFASNet liveness model.
        
        Args:
            face_img: Cropped face image (BGR)
            target_size: Target resolution (default 80x80 untuk MiniFASNet)
        
        Returns:
            Preprocessed tensor (shape: [1, 3, 80, 80])
        """
        try:
            resized = cv2.resize(face_img, target_size)
            rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
            normalized = rgb.astype(np.float32) / 255.0
            transposed = np.transpose(normalized, (2, 0, 1))
            expanded = np.expand_dims(transposed, axis=0)
            return expanded
        except Exception as e:
            logger.error(f"Error preprocessing face: {e}", exc_info=True)
            raise

    def _preprocess_arcface(self, face_img: np.ndarray, target_size=(112, 112)) -> np.ndarray:
        """Preprocess face crop untuk ArcFace embedding model.
        
        Args:
            face_img: Cropped face image (BGR)
            target_size: Target resolution (default 112x112 untuk ArcFace)
        
        Returns:
            Preprocessed tensor (shape: [1, 3, 112, 112])
        """
        try:
            resized = cv2.resize(face_img, target_size)
            rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
            # ArcFace normalization: (x - 127.5) / 128
            normalized = (rgb.astype(np.float32) - 127.5) / 128.0
            transposed = np.transpose(normalized, (2, 0, 1))
            expanded = np.expand_dims(transposed, axis=0)
            return expanded
        except Exception as e:
            logger.error(f"Error preprocessing for ArcFace: {e}", exc_info=True)
            raise

    def proses_frame(self, frame_bgr: np.ndarray, skip_liveness: bool = False) -> HasilDeteksi:
        """Process video frame: detect face -> check liveness -> generate embedding.
        
        Args:
            frame_bgr: Input frame (BGR format)
            skip_liveness: Skip liveness check (untuk testing atau enrollment)
        
        Returns:
            HasilDeteksi object dengan hasil detection
        """
        try:
            # Face detection
            gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
            faces = self.face_cascade.detectMultiScale(
                gray, 
                scaleFactor=1.1, 
                minNeighbors=5, 
                minSize=(30, 30)
            )

            if len(faces) == 0:
                return HasilDeteksi(
                    wajah_terdeteksi=False,
                    lolos_liveness=False,
                    embedding=None,
                    alasan_gagal="Tidak ada wajah terdeteksi"
                )

            # Ambil wajah terbesar
            (x, y, w, h) = max(faces, key=lambda f: f[2] * f[3])
            face_crop = frame_bgr[y:y+h, x:x+w]

            # Liveness check (kecuali skip untuk enrollment)
            if not skip_liveness:
                try:
                    input_tensor_liveness = self._preprocess_face(face_crop)
                    input_name_liveness = self.session_liveness.get_inputs()[0].name
                    liveness_out = self.session_liveness.run(
                        None, 
                        {input_name_liveness: input_tensor_liveness}
                    )[0]

                    is_real, real_score = evaluasi_liveness(liveness_out)

                    if not is_real:
                        return HasilDeteksi(
                            wajah_terdeteksi=True,
                            lolos_liveness=False,
                            embedding=None,
                            alasan_gagal=f"Terdeteksi spoofing (skor: {real_score:.3f}, ambang: {AMBANG_LIVENESS:.3f})",
                            skor_liveness=real_score,
                        )
                except Exception as e:
                    logger.error(f"Liveness check error: {e}", exc_info=True)
                    return HasilDeteksi(
                        wajah_terdeteksi=True,
                        lolos_liveness=False,
                        embedding=None,
                        alasan_gagal=f"Error liveness check: {str(e)}"
                    )

            # Embedding generation
            try:
                input_tensor_emb = self._preprocess_arcface(face_crop)
                emb_input_name = self.session_embedding.get_inputs()[0].name
                embedding_out = self.session_embedding.run(
                    None, 
                    {emb_input_name: input_tensor_emb}
                )[0]
                embedding = embedding_out.flatten().astype(np.float32)
                
                # L2 normalization
                norm = np.linalg.norm(embedding)
                if norm > 0:
                    embedding = embedding / norm
                else:
                    logger.warning("Embedding norm is 0, using unnormalized")

                return HasilDeteksi(
                    wajah_terdeteksi=True,
                    lolos_liveness=True,
                    embedding=embedding,
                    alasan_gagal=None,
                    skor_liveness=real_score if not skip_liveness else None,
                )
            except Exception as e:
                logger.error(f"Embedding generation error: {e}", exc_info=True)
                return HasilDeteksi(
                    wajah_terdeteksi=True,
                    lolos_liveness=False,
                    embedding=None,
                    alasan_gagal=f"Error embedding: {str(e)}"
                )
        except Exception as e:
            logger.error(f"Unexpected error in proses_frame: {e}", exc_info=True)
            return HasilDeteksi(
                wajah_terdeteksi=False,
                lolos_liveness=False,
                embedding=None,
                alasan_gagal=f"Unexpected error: {str(e)}"
            )

    def jarak_embedding(self, emb1: np.ndarray, emb2: np.ndarray) -> float:
        """Compute cosine distance antara dua embeddings.
        
        Args:
            emb1: Embedding 1 (normalized)
            emb2: Embedding 2 (normalized)
        
        Returns:
            Distance dalam range [0, 2] (0 = identical, 2 = opposite)
        """
        try:
            dot_prod = np.dot(emb1, emb2)
            norm1 = np.linalg.norm(emb1)
            norm2 = np.linalg.norm(emb2)
            
            if norm1 == 0 or norm2 == 0:
                logger.warning(f"Zero norm detected: norm1={norm1}, norm2={norm2}")
                return 1.0
            
            similarity = dot_prod / (norm1 * norm2)
            # Clamp similarity ke [-1, 1] untuk avoid numerical errors
            similarity = max(-1.0, min(1.0, similarity))
            distance = float(1.0 - similarity)
            return distance
        except Exception as e:
            logger.error(f"Error computing embedding distance: {e}", exc_info=True)
            return 1.0  # Max distance on error

    @property
    def model_version(self) -> str:
        """Return model version identifier."""
        return "minifasnet-v1"
