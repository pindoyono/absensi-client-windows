# 📚 Operations Manual (REQ-DOC-001)

Dokumen ini adalah panduan operasional harian untuk administrator device kiosk _Absensi-Client-Windows_.

---

## 1. Startup & Shutdown Procedures

### Startup (Pagi Hari sebelum Gerbang Buka)

1. Nyalakan PC Windows Kiosk.
2. Pastikan koneksi internet (Wi-Fi/LAN) terhubung ke server sekolah.
3. Aplikasi akan otomatis berjalan atau jalankan manual:
   ```cmd
   python main.py
   ```
4. Perhatikan status badge di UI kiosk:
   - 🟢 **Online / OK**: Terhubung ke server, sync normal, jadwal valid.
   - 🟡 **Offline / Partial**: Tidak ada internet; absen tetap tersimpan lokal di SQLite terenkripsi dan otomatis sync saat online kembali.
   - 🔴 **Error / Liveness Failed**: Periksa log di `data/logs/application.log`.

### Shutdown (Sore Hari setelah Gerbang Tutup)

1. Aplikasi mendukung **Graceful Shutdown** (REQ-OPS-008).
2. Tekan `Alt + F4` atau kirim sinyal terminate (`SIGTERM`). Background worker akan menyelesaikan antrian sync aktif, flush database, dan menutup koneksi secara aman tanpa risiko korupsi data.

---

## 2. Monitoring Health & Sync Status

### Dashboard Kesehatan Device (REQ-OPS-007)

Administrator dapat memantau kesehatan device melalui log atau script health check:

- **Disk Space**: Minimal tersedia 1 GB.
- **Database Size**: SQLCipher database (`data/absensi_lokal.db`). Peringatan jika > 2 GB.
- **Sync Status**: Memantau record `synced = 0` (antrian belum terkirim).

### Audit Logs (REQ-OPS-001)

Semua aktivitas penting (Login, Sync, Attendance, Error, Security Events) tercatat di tabel `device_audit_log` dan dibackup ke `data/audit_backup.jsonl`.

- Untuk melihat log terbaru:
  ```sql
  SELECT * FROM device_audit_log ORDER BY timestamp DESC LIMIT 20;
  ```

---

## 3. Database Backup & Restore (REQ-OPS-004)

### Daily Encrypted Backup

Device secara otomatis melakukan enkripsi backup harian ke folder `data/backup/` menggunakan kunci enkripsi Fernet. Retensi lokal diatur selama 30 hari.

### Restore Manual

Jika terjadi kerusakan hardware / korupsi database:

1. Hentikan aplikasi.
2. Jalankan pemulihan dari backup terenkripsi:
   ```python
   from app.database.backup import DatabaseBackup
   backup = DatabaseBackup("data/absensi_lokal.db", "data/backup")
   backup.restore_backup("data/backup/absensi_lokal_YYYY-MM-DD_HHMMSS.db.enc", "YOUR_ENCRYPTION_KEY")
   ```

---

## 4. Troubleshooting Guide

| Gejala                      | Penyebab Umum                          | Solusi                                                                         |
| --------------------------- | -------------------------------------- | ------------------------------------------------------------------------------ |
| **Kiosk offline terus**     | Kabel LAN lepas / Wi-Fi putus          | Cek koneksi internet, restart network adapter.                                 |
| **Gagal face recognition**  | Lensa kamera kotor / pencahayaan buruk | Bersihkan lensa kamera web, sesuaikan lampu gerbang.                           |
| **API Key ditolak (401)**   | Kunci API device diganti di server     | Update `.env` atau Windows Credential Manager dengan `DEVICE_API_KEY` terbaru. |
| **Database error / locked** | Aplikasi tertutup paksa (hard reset)   | Cek integritas SQLite, restore dari backup terbaru di `data/backup/`.          |

---

## 5. Security & Maintenance

- **Credentials:** Sensitif credential tersimpan di Windows Credential Manager (REQ-SEC-003).
- **API Signing:** Setiap request HTTP ditandatangani dengan HMAC-SHA256 (`X-Signature`, REQ-SEC-001).
- **Cert Pinning:** Koneksi HTTPS diverifikasi dengan certificate pinning (`SSLPinningAdapter`, REQ-SEC-002).
- **Rate Limiting:** Kiosk membatasi maksimal 60 request/menit untuk mencegah DoS abuse (REQ-SEC-003).
