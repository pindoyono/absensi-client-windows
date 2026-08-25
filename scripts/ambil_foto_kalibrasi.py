import os
import time
import cv2

def capture_calibration_photos(person_name="orang_1", count=4, delay=1.0):
    folder = os.path.join("foto_kalibrasi", person_name)
    os.makedirs(folder, exist_ok=True)

    cap = cv2.VideoCapture(0) # Kembali ke index 0 tanpa DSHOW
    if not cap.isOpened():
        print("ERROR: Tidak dapat membuka kamera.")
        return

    print(f"Mengambil {count} foto untuk '{person_name}'. Pastikan wajah menghadap kamera...")
    time.sleep(3)  # Tambah waktu persiapan

    for i in range(1, count + 1):
        # Ambil frame beberapa kali untuk membersihkan buffer
        for _ in range(10):
            cap.read()
        
        ok, frame = cap.read()
        if ok:
            # Debug: Tampilkan frame sebentar agar user bisa memastikan posisi wajah
            cv2.imshow("Capture", frame)
            cv2.waitKey(500)
            
            file_path = os.path.join(folder, f"{i}.jpg")
            cv2.imwrite(file_path, frame)
            print(f"[{i}/{count}] Tersimpan: {file_path}")
        else:
            print(f"[{i}/{count}] Gagal mengambil frame.")
        time.sleep(delay)

    cap.release()
    cv2.destroyAllWindows()
    print(f"Selesai mengambil foto untuk {person_name}!\n")

if __name__ == "__main__":
    import sys
    name = sys.argv[1] if len(sys.argv) > 1 else "orang_1"
    capture_calibration_photos(name)
