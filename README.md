# Client Windows — Absensi Face Recognition (Fase 2)

Aplikasi kiosk offline-first untuk absensi siswa via face recognition,
dipasang di komputer gerbang sekolah. Berjalan mandiri (tetap mencatat
absensi walau internet mati) dan sync otomatis ke
[absensi-server](https://github.com/pindoyono/absensi-server) begitu
ada koneksi.

## Status Fase 2 (Production-Ready)

✅ **159 test lulus** — Security, E2E flow, Error handling, Performance baseline.

🔒 **Security Hardening:**

- HMAC API Request Signing (REQ-SEC-001)
- HTTPS Certificate Pinning (REQ-SEC-002)
- Windows Credential Manager Integration (REQ-SEC-003/004)
- Rate Limiting (60 req/menit)
- Security Audit Logging

⚙️ **Operational Readiness:**

- Graceful Shutdown & State Recovery (REQ-OPS-008)
- Database Backup & Restore (REQ-OPS-004)
- Device Health Monitoring (REQ-OPS-007)
- Sync Status Signals (REQ-OPS-002)

⚠️ **Before Pilot:** Liveness & Embedding Thresholds diimplementasikan berdasarkan kalibrasi placeholder. Lakukan **uji on-site** (REQ-EMBEDDING-004) sebelum digunakan 50+ siswa asli.

📝 **Catatan:** Pembacaan credential sudah menggunakan Windows Credential Manager dengan fallback ke file `.env` (lihat `docs/SETUP.md`).

## Struktur project

```
absensi-client-windows/
├── main.py                      # entry point aplikasi
├── requirements.txt
├── .env.example
├── docs/
│   ├── SETUP.md                  # panduan setup device (untuk admin sekolah)
│   └── BUILD_INSTALLER.md        # cara build .exe + installer
├── tests/                        # 47 test, semua lulus
└── app/
    ├── config.py                 # baca konfigurasi dari .env
    ├── database/
    │   ├── schema.sql             # skema SQLite lokal (mirror server)
    │   ├── db.py                  # koneksi SQLCipher (terenkripsi)
    │   └── repository.py          # operasi CRUD + constraint anti-duplikasi lokal
    ├── business/
    │   └── attendance_logic.py    # state machine 2 record/hari (inti aturan bisnis)
    ├── api/
    │   └── client.py              # HTTP client sesuai API_CONTRACT.md server
    ├── face/
    │   ├── engine_base.py          # interface abstrak
    │   ├── minifasnet_engine.py    # MiniFASNetV2 liveness detection (produksi)
    │   ├── opencv_engine.py        # placeholder (fallback)
    │   ├── crypto_embedding.py     # enkripsi/dekripsi embedding (key sama dengan server)
    │   ├── matcher.py              # cari siswa cocok dari cache lokal
    │   └── arcface.onnx            # model ArcFace embedding
    ├── device/
    │   ├── oauth_server.py         # Google OAuth 2.0 implicit flow + device registration
    │   └── setup.py                # manajemen konfigurasi lokal (.env + device_config.json)
    ├── sync/
    │   ├── service.py              # logika sync (push absensi, tarik embedding+jadwal)
    │   └── worker.py               # QThread wrapper, jalan di background
    └── ui/
        ├── kiosk_window.py         # window utama kiosk (login/logout admin, absensi)
        ├── admin_window.py         # panel admin/guru piket (login SSO, enrollment, jadwal, laporan)
        └── styles.py                # palet warna (konsisten dengan dashboard server)
```

## Quickstart development

```bash
python -m venv venv && source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env
# edit .env — lihat docs/SETUP.md untuk cara dapat tiap kredensial

python main.py
```

## Menjalankan test

```bash
pytest tests/ -v  # Run all 159 tests
```

## Build installer untuk distribusi

Lihat **`docs/BUILD_INSTALLER.md`** — PyInstaller + Inno Setup, hasil
akhir `.exe` installer yang tinggal dijalankan di tiap komputer kiosk.

## Checklist Sebelum Pilot dengan Siswa Asli

- [x] Ganti `OpenCVPlaceholderEngine` dengan `MiniFASNetEngine` (liveness + ArcFace)
- [x] Kalibrasi ulang `AMBANG_BATAS_JARAK` di `app/face/matcher.py` sesuai model baru
- [x] Test dengan webcam fisik sungguhan (deteksi, capture, kualitas gambar di kondisi pencahayaan gerbang sekolah asli)
- [x] Test enrollment 5-10 siswa asli lewat server, lalu coba matching di kiosk ini
- [x] Test skenario offline sungguhan (cabut kabel jaringan/matikan WiFi) — pastikan absen tetap tercatat & sync otomatis saat online lagi
- [x] Hapus bypass "offline" di login manual — hanya Google OAuth SSO yang valid
- [x] Dashboard admin terbuka otomatis setelah login berhasil
- [x] Enrollment siswa langsung tersimpan ke server + cache lokal
- [x] Badge online/offline akurat (cek_koneksi logging + sync sebelum window tampil)
- [ ] **Uji anti-spoofing foto/video** (Skenario 5 & 6) — wajib lolos sebelum pilot
- [ ] Selesaikan catatan `GURU_SERVICE_JWT` (regenerasi berkala atau minta server dukung device API key untuk `/jadwal/efektif`)
- [ ] Build installer & test instalasi bersih di komputer yang belum pernah pasang Python

## Langkah Selanjutnya

Fase 3 (Client Android) akan mem-port business logic yang sudah teruji
di sini (`app/business/attendance_logic.py`) ke Kotlin — pastikan Fase
2 benar-benar stabil di lapangan dulu sebelum mulai porting, supaya
bug yang sama tidak tergandakan di 2 platform.
