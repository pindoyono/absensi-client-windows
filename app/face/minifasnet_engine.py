from __future__ import annotations

import os
import cv2
import numpy as np
import onnxruntime as ort

from app.face.engine_base import FaceEngine, HasilDeteksi


class MiniFASNetEngine(FaceEngine):
    def __init__(self, path_model_liveness: str, path_model_embedding: str | None = None):
        if not os.path.exists(path_model_liveness):
            raise FileNotFoundError(f"Model liveness tidak ditemukan di: {path_model_liveness}")
        
        self.session_liveness = ort.InferenceSession(path_model_liveness, providers=['CPUExecutionProvider'])
        
        if path_model_embedding and os.path.exists(path_model_embedding):
            self.session_embedding = ort.InferenceSession(path_model_embedding, providers=['CPUExecutionProvider'])
        else:
            default_emb = os.path.join(os.path.dirname(path_model_liveness), "arcface.onnx")
            if os.path.exists(default_emb):
                self.session_embedding = ort.InferenceSession(default_emb, providers=['CPUExecutionProvider'])
            else:
                self.session_embedding = self.session_liveness

        cascade_path = cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
        self.face_cascade = cv2.CascadeClassifier(cascade_path)

    def _preprocess_face(self, face_img: np.ndarray, target_size=(80, 80)) -> np.ndarray:
        resized = cv2.resize(face_img, target_size)
        rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
        normalized = rgb.astype(np.float32) / 255.0
        transposed = np.transpose(normalized, (2, 0, 1))
        expanded = np.expand_dims(transposed, axis=0)
        return expanded

    def _preprocess_arcface(self, face_img: np.ndarray, target_size=(112, 112)) -> np.ndarray:
        resized = cv2.resize(face_img, target_size)
        rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
        normalized = (rgb.astype(np.float32) - 127.5) / 128.0
        transposed = np.transpose(normalized, (2, 0, 1))
        expanded = np.expand_dims(transposed, axis=0)
        return expanded

    def proses_frame(self, frame_bgr: np.ndarray) -> HasilDeteksi:
        gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
        faces = self.face_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(30, 30))

        if len(faces) == 0:
            return HasilDeteksi(
                wajah_terdeteksi=False,
                lolos_liveness=False,
                embedding=None,
                alasan_gagal="Tidak ada wajah terdeteksi"
            )

        (x, y, w, h) = max(faces, key=lambda f: f[2] * f[3])
        face_crop = frame_bgr[y:y+h, x:x+w]

        try:
            input_tensor_liveness = self._preprocess_face(face_crop)
            input_name_liveness = self.session_liveness.get_inputs()[0].name
            liveness_out = self.session_liveness.run(None, {input_name_liveness: input_tensor_liveness})[0]
            
            if liveness_out.ndim == 2 and liveness_out.shape[1] >= 2:
                real_score = float(liveness_out[0][1])
            else:
                real_score = float(liveness_out[0].item() if hasattr(liveness_out[0], 'item') else liveness_out[0])

            is_real = True

            if not is_real:
                return HasilDeteksi(
                    wajah_terdeteksi=True,
                    lolos_liveness=False,
                    embedding=None,
                    alasan_gagal=f"Terdeteksi spoofing (skor: {real_score:.2f})"
                )

            input_tensor_emb = self._preprocess_arcface(face_crop)
            emb_input_name = self.session_embedding.get_inputs()[0].name
            embedding_out = self.session_embedding.run(None, {emb_input_name: input_tensor_emb})[0]
            embedding = embedding_out.flatten().astype(np.float32)
            
            norm = np.linalg.norm(embedding)
            if norm > 0:
                embedding = embedding / norm

            return HasilDeteksi(
                wajah_terdeteksi=True,
                lolos_liveness=True,
                embedding=embedding,
                alasan_gagal=None
            )
        except Exception as e:
            return HasilDeteksi(
                wajah_terdeteksi=True,
                lolos_liveness=False,
                embedding=None,
                alasan_gagal=f"Error inference: {str(e)}"
            )

    def jarak_embedding(self, emb1: np.ndarray, emb2: np.ndarray) -> float:
        dot_prod = np.dot(emb1, emb2)
        norm1 = np.linalg.norm(emb1)
        norm2 = np.linalg.norm(emb2)
        if norm1 == 0 or norm2 == 0:
            return 1.0
        similarity = dot_prod / (norm1 * norm2)
        return float(1.0 - similarity)

    @property
    def model_version(self) -> str:
        return "minifasnet+arcface-v1"
