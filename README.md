# Client Windows — Absensi Face Recognition (Fase 2)

Aplikasi kiosk offline-first untuk absensi siswa via face recognition,
dipasang di komputer gerbang sekolah. Berjalan mandiri (tetap mencatat
absensi walau internet mati) dan sync otomatis ke
[absensi-server](https://github.com/pindoyono/absensi-server) begitu
ada koneksi.

## Status Fase 2

✅ **41 test lulus** — business logic, database lokal terenkripsi,
API client (sesuai kontrak server), face matching, sync service, dan
UI kiosk (diuji headless dengan Qt offscreen) semua terverifikasi
bekerja end-to-end di level unit/integration test.

⚠️ **Belum siap pilot dengan siswa asli** — engine wajah yang
terpasang (`OpenCVPlaceholderEngine`) adalah placeholder untuk
membuktikan pipeline bekerja, BUKAN model produksi:
- Tidak ada liveness detection sungguhan (rawan foto/video spoofing)
- Akurasi tidak memadai untuk membedakan banyak wajah siswa

**Wajib diganti dengan MiniFASNet** (model yang sudah pernah dibangun
sebelumnya) sebelum dipakai siswa asli — lihat `app/face/engine_base.py`.

⚠️ **Belum diuji dengan kamera fisik sungguhan** — sandbox pengembangan
tidak punya akses kamera. Semua pengujian di atas pakai frame
sintetis/mock. **Wajib ditest dengan webcam asli** sebelum dianggap
selesai — lihat checklist di bagian bawah README ini.

📝 **Catatan arsitektur terbuka**: endpoint `/jadwal/efektif` di server
butuh JWT guru, bukan device API key. Solusi sementara: `GURU_SERVICE_JWT`
(akun layanan read-only, lihat `docs/SETUP.md` langkah 2b) — token ini
kedaluwarsa (default 12 jam), perlu diregenerasi berkala sampai server
menambahkan dukungan device API key untuk endpoint ini.

## Struktur project

```
absensi-client-windows/
├── main.py                      # entry point aplikasi
├── requirements.txt
├── .env.example
├── docs/
│   ├── SETUP.md                  # panduan setup device (untuk admin sekolah)
│   └── BUILD_INSTALLER.md        # cara build .exe + installer
├── tests/                        # 41 test, semua lulus
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
    │   ├── engine_base.py          # interface abstrak — TITIK INTEGRASI MiniFASNet
    │   ├── opencv_engine.py        # placeholder (BUKAN produksi)
    │   ├── crypto_embedding.py     # dekripsi embedding (key sama dengan server)
    │   └── matcher.py              # cari siswa cocok dari cache lokal
    ├── sync/
    │   ├── service.py              # logika sync (push absensi, tarik embedding+jadwal)
    │   └── worker.py               # QThread wrapper, jalan di background
    └── ui/
        ├── kiosk_window.py         # window utama, sesuai mockup yang disetujui
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
export QT_QPA_PLATFORM=offscreen  # tidak perlu di Windows dengan display asli
pytest tests/ -v
```

## Build installer untuk distribusi

Lihat **`docs/BUILD_INSTALLER.md`** — PyInstaller + Inno Setup, hasil
akhir `.exe` installer yang tinggal dijalankan di tiap komputer kiosk.

## Checklist Sebelum Pilot dengan Siswa Asli

- [ ] Ganti `OpenCVPlaceholderEngine` dengan adapter MiniFASNet (lihat `app/face/engine_base.py`)
- [ ] Kalibrasi ulang `AMBANG_BATAS_JARAK` di `app/face/matcher.py` sesuai model baru
- [ ] Test dengan webcam fisik sungguhan (deteksi, capture, kualitas gambar di kondisi pencahayaan gerbang sekolah asli)
- [ ] Test enrollment 5-10 siswa asli lewat server, lalu coba matching di kiosk ini
- [ ] Test skenario offline sungguhan (cabut kabel jaringan/matikan WiFi) — pastikan absen tetap tercatat & sync otomatis saat online lagi
- [ ] Selesaikan catatan `GURU_SERVICE_JWT` (regenerasi berkala atau minta server dukung device API key untuk `/jadwal/efektif`)
- [ ] Build installer & test instalasi bersih di komputer yang belum pernah pasang Python

## Langkah Selanjutnya

Fase 3 (Client Android) akan mem-port business logic yang sudah teruji
di sini (`app/business/attendance_logic.py`) ke Kotlin — pastikan Fase
2 benar-benar stabil di lapangan dulu sebelum mulai porting, supaya
bug yang sama tidak tergandakan di 2 platform.
