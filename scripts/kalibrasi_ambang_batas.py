import os
import cv2
import numpy as np
from app.face.minifasnet_engine import MiniFASNetEngine

MODEL_PATH = "models/minifasnet.onnx"
CALIB_DIR = "foto_kalibrasi"

def main():
    if not os.path.exists(MODEL_PATH):
        print(f"ERROR: Model '{MODEL_PATH}' tidak ditemukan. Tempatkan file model sebelum menjalankan kalibrasi.")
        return

    if not os.path.exists(CALIB_DIR):
        print(f"INFO: Folder '{CALIB_DIR}' tidak ditemukan. Buat struktur: foto_kalibrasi/<orang>/1.jpg, dst.")
        return

    engine = MiniFASNetEngine(MODEL_PATH)
    embeddings_per_orang = {}

    for orang in os.listdir(CALIB_DIR):
        orang_dir = os.path.join(CALIB_DIR, orang)
        if not os.path.isdir(orang_dir):
            continue
        embeddings_per_orang[orang] = []
        for file in os.listdir(orang_dir):
            file_path = os.path.join(orang_dir, file)
            frame = cv2.imread(file_path)
            if frame is None:
                continue
            hasil = engine.proses_frame(frame)
            if hasil.embedding is not None:
                embeddings_per_orang[orang].append(hasil.embedding)

    print("=== Jarak ORANG SAMA (harus kecil, konsisten) ===")
    same_distances = []
    for orang, embs in embeddings_per_orang.items():
        for i in range(len(embs)):
            for j in range(i+1, len(embs)):
                d = engine.jarak_embedding(embs[i], embs[j])
                same_distances.append(d)
                print(f"{orang}: {d:.4f}")

    print("\n=== Jarak ORANG BERBEDA (harus jelas lebih besar) ===")
    diff_distances = []
    orang_list = list(embeddings_per_orang.keys())
    for i in range(len(orang_list)):
        for j in range(i+1, len(orang_list)):
            e1_list = embeddings_per_orang[orang_list[i]]
            e2_list = embeddings_per_orang[orang_list[j]]
            if e1_list and e2_list:
                d = engine.jarak_embedding(e1_list[0], e2_list[0])
                diff_distances.append(d)
                print(f"{orang_list[i]} vs {orang_list[j]}: {d:.4f}")

    if same_distances and diff_distances:
        max_same = max(same_distances)
        min_diff = min(diff_distances)
        recommended = (max_same + min_diff) / 2
        print(f"\nMax Jarak Sama: {max_same:.4f}")
        print(f"Min Jarak Berbeda: {min_diff:.4f}")
        print(f"Rekomendasi AMBANG_BATAS_JARAK: {recommended:.4f}")
    else:
        print("\nData tidak cukup untuk menghitung ambang batas.")

if __name__ == "__main__":
    main()
