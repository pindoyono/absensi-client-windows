import requests
import json
import os
from app.device.setup import load_config_lokal

BASE_URL = "https://absen.smkn2malinau.sch.id"

def get_active_token():
    """Membaca token yang sedang aktif dari device_config.json atau environment."""
    config = load_config_lokal()
    token = config.get("jwt_token") or os.getenv("DEVICE_API_KEY")
    if not token:
        print("❌ Tidak ada token aktif! Silakan login admin terlebih dahulu lewat aplikasi main.py.")
        return None
    return token

def test_endpoints():
    token = get_active_token()
    if not token:
        return

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    print("--- Testing Endpoints Menggunakan Token Aktif ---")
    print(f"Token: {token[:15]}...")

    # 1. GET /siswa
    try:
        r = requests.get(f"{BASE_URL}/siswa", headers=headers, timeout=10)
        print(f"\n[1] GET /siswa -> Status: {r.status_code}")
        if r.status_code == 200:
            data = r.json()
            print(f"    Berhasil! Jumlah siswa di server: {len(data)}")
            if len(data) > 0:
                print(f"    Contoh data siswa pertama: {data[0]}")
        else:
            print(f"    Response: {r.text}")
    except Exception as e:
        print(f"    GET /siswa Error: {e}")

    # 3. POST /siswa/{id}/enroll
    try:
        # Coba ambil id siswa pertama dari GET /siswa
        r_get = requests.get(f"{BASE_URL}/siswa", headers=headers, timeout=10)
        if r_get.status_code == 200 and len(r_get.json()) > 0:
            siswa_id = r_get.json()[0]["id"]
            
            # Buat dummy embedding 512 float
            dummy_embedding = [float(i) * 0.001 for i in range(512)]
            payload = {
                "embedding": dummy_embedding,
                "model_version": "minifasnet-v1"
            }
            
            print(f"\n[3] Testing POST /siswa/{siswa_id}/enroll...")
            r_enroll = requests.post(f"{BASE_URL}/siswa/{siswa_id}/enroll", headers=headers, json=payload, timeout=30)
            print(f"    Status: {r_enroll.status_code}")
            print(f"    Response: {r_enroll.text}")
    except Exception as e:
        print(f"    POST /siswa/enroll Error: {e}")

if __name__ == "__main__":
    test_endpoints()
