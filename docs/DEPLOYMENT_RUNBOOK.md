# 🚀 Deployment Runbook (REQ-DOC-004)

Panduan langkah-demi-langkah untuk deploy kiosk absensi ke device baru.

---

## Pre-Deployment Checklist

- [ ] Server API sudah siap & terhubung (endpoint `/health` merespon 200).
- [ ] Device terdaftar di server (DEVICE_ID + DEVICE_API_KEY sudah didapat dari admin server).
- [ ] FACE_ENCRYPTION_KEY dan DB_ENCRYPTION_KEY sudah didapat dari admin server.
- [ ] Kamera USB/Webcam terhubung & terdeteksi oleh Windows.
- [ ] Python 3.14+ terpasang di device.

---

## 1. Device Registration (Server-Side)

Hubungi tim server untuk mendaftarkan device baru:

- Dapatkan `DEVICE_ID` (format: `DEV-XXXX`).
- Dapatkan `DEVICE_API_KEY` (panjang 32+ karakter).
- Dapatkan `FACE_ENCRYPTION_KEY` dan `DB_ENCRYPTION_KEY`.

---

## 2. Configuration (.env Setup)

Buat file `.env` di folder instalasi aplikasi:

```ini
SERVER_URL=https://absen.smkn2malinau.sch.id
DEVICE_ID=DEV-XXXX
DEVICE_API_KEY=your_api_key_here
FACE_ENCRYPTION_KEY=your_face_key_here
DB_ENCRYPTION_KEY=your_db_key_here
SYNC_INTERVAL_SECONDS=45
TOLERANSI_TERLAMBAT_MENIT=5
```

> **Catatan:** Untuk keamanan produksi, semua secret (API key, encryption keys) akan otomatis dipindahkan ke **Windows Credential Manager** pada startup pertama.

---

## 3. Installation

### Option A: Development (Python)

```bash
cd d:\Project Absensi\client-windows
pip install -r requirements.txt
python main.py
```

### Option B: Production (PyInstaller + Inno Setup)

1. Build executable:
   ```bash
   pyinstaller --onefile --windowed main.py
   ```
2. Jalankan installer Inno Setup (`AbsensiKiosk-Setup.exe`) untuk deploy ke device produksi.

---

## 4. Post-Installation Verification

1. Buka kiosk, pastikan UI muncul.
2. Scan wajah test (gunakan siswa uji).
3. Periksa log di `data/logs/application.log` — tidak boleh ada error.
4. Verifikasi sync: buka `data/performance_metrics.jsonl` — harus ada entry sync cycle.

---

## 5. Rollback Procedure

Jika terjadi error kritis setelah update:

1. Hentikan aplikasi.
2. Restore database dari backup terbaru:
   ```python
   from app.database.backup import DatabaseBackup
   backup = DatabaseBackup("data/absensi_lokal.db", "data/backup")
   backup.restore_backup("data/backup/absensi_lokal_YYYY-MM-DD_HHMMSS.db.enc", "YOUR_ENCRYPTION_KEY")
   ```
3. Rollback kode ke versi sebelumnya (gunakan Git tag).
4. Restart aplikasi.

---

## 6. Post-Deployment Monitoring

- Periksa log harian di `data/logs/application.log`.
- Pantau sync status via `data/performance_metrics.jsonl`.
- Jalankan health check mingguan:
  ```python
  from app.health import HealthChecker
  hc = HealthChecker("data/absensi_lokal.db")
  print(hc.get_full_health())
  ```
