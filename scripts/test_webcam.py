import cv2

def test_camera():
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("ERROR: Tidak dapat membuka webcam (index 0). Cek koneksi / izin perangkat.")
        return
    
    ok, frame = cap.read()
    if ok:
        print("Kamera terbaca sukses!")
        print("Ukuran frame:", frame.shape)
        cv2.imwrite("test_capture.jpg", frame)
        print("Frame tersimpan di 'test_capture.jpg'")
    else:
        print("ERROR: Kamera terbuka tetapi gagal mengambil frame (read=False).")
    
    cap.release()

if __name__ == "__main__":
    test_camera()
