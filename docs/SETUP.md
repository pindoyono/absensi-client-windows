# Panduan Setup Device — Client Windows

Untuk admin/operator yang memasang aplikasi kiosk di komputer gerbang sekolah.

## Prasyarat

- Windows 10/11
- Kamera terpasang (webcam USB atau bawaan laptop)
- Koneksi internet (untuk setup awal & sync — aplikasi tetap bisa dipakai offline setelahnya)

## Langkah Setup

### 1. Registrasi device di server (dilakukan admin, dari komputer manapun)

Buka `https://absen.smkn2malinau.sch.id/docs`, login sebagai admin, panggil:

```
POST /device/register
{
  "device_id": "gerbang-utama-01",
  "nama_lokasi": "Gerbang Utama",
  "platform": "windows"
}
```

**Salin `api_key` dari response — hanya tampil sekali.**

### 2. Dapatkan FACE_ENCRYPTION_KEY dari admin server

Ini key yang sama dipakai server untuk enkripsi embedding wajah (lihat
`.env` di server, variabel `FACE_ENCRYPTION_KEY`). **Minta lewat jalur
aman** (bukan chat/email biasa) — kalau key ini bocor bersama akses ke
device, embedding wajah bisa didekripsi orang tidak berwenang.

### 2b. (Dihapus — endpoint jadwal kini menerima Device API Key)

Endpoint `/jadwal/efektif` di server sudah menerima `X-Device-Api-Key`
langsung (sejak `get_guru_or_device` ditambahkan), sama seperti
`/dispensasi/aktif`. Device **tidak lagi butuh** `GURU_SERVICE_JWT` —
kredensial device sendiri sudah cukup untuk sync jadwal.

### 3. Install aplikasi

- Jalankan installer `AbsensiKiosk-Setup.exe` (lihat `docs/BUILD_INSTALLER.md` untuk cara build)
- Aplikasi ter-install ke `C:\Program Files\AbsensiKiosk\`

### 4. Konfigurasi `.env`

Di folder yang sama dengan `.exe`, buat/edit file `.env`:

```env
SERVER_URL=https://absen.smkn2malinau.sch.id
DEVICE_ID=gerbang-utama-01
DEVICE_API_KEY=<api_key dari langkah 1>
SYNC_INTERVAL_SECONDS=45
TOLERANSI_TERLAMBAT_MENIT=5
```

> **Keamanan (REQ-SEC-003):** Semua secret (API key, FACE_ENCRYPTION_KEY, DB_ENCRYPTION_KEY) akan otomatis disimpan di **Windows Credential Manager** pada startup pertama. Anda tidak perlu menulis key secara manual di `.env` — aplikasi akan meminta input sekali lalu menyimpannya secara aman di Windows Credential Manager.

**Generate `DB_ENCRYPTION_KEY` unik untuk device ini** (jangan sama antar device):

```powershell
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

### 5. Credential Manager Setup (Pertama Kali Jalan)

1. Jalankan aplikasi pertama kali.
2. Jika ada dialog permintaan credential, isikan:
   - `device_api_key` = nilai dari langkah 1
   - `face_encryption_key` = nilai dari langkah 2
   - `db_encryption_key` = nilai yang baru generate
3. Credential akan disimpan di Windows Credential Manager dengan service name `AbsensiKiosk`.

> **Catatan:** Jika `.env` sudah berisi key, aplikasi akan fallback ke `.env` dulu. Hapus key dari `.env` setelah verifikasi Credential Manager berfungsi.

### 5. Test jalan

```powershell
python main.py
```

Cek: window kiosk muncul, badge status jaringan menunjukkan "Online",
kamera aktif (coba arahkan wajah — kalau belum ada siswa ter-enroll,
akan muncul "Wajah tidak dikenali", ini normal).

### 6. Set auto-start saat Windows boot

Buat shortcut ke `.exe`, taruh di folder Startup:

```
C:\Users\<user>\AppData\Roaming\Microsoft\Windows\Start Menu\Programs\Startup
```

### 7. Nonaktifkan sleep/screensaver

Kiosk harus tetap menyala sepanjang jam sekolah — atur Power Settings
Windows: "Never sleep" saat plugged in.

---

## ⚠️ PENTING — Sebelum Dipakai Siswa Asli

Engine wajah yang terpasang saat ini (`OpenCVPlaceholderEngine`)
adalah **placeholder untuk validasi pipeline**, BUKAN untuk produksi:

- Tidak ada liveness detection sungguhan (foto di layar HP bisa lolos)
- Akurasi pengenalan wajah tidak memadai untuk membedakan 1000 siswa

**Wajib diganti dengan model MiniFASNet** (yang sudah pernah dibangun
sebelumnya di project terpisah) sebelum pilot dengan siswa asli — lihat
`app/face/engine_base.py` untuk titik integrasinya.

## Troubleshooting

| Gejala                                                     | Kemungkinan Penyebab                                                                                                                           |
| ---------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------- |
| Window error "Konfigurasi Belum Lengkap"                   | Ada variabel `.env` yang kosong — cek pesan error, biasanya sebutkan yang mana                                                                 |
| Badge selalu "Offline" padahal internet nyala              | Cek `SERVER_URL` benar, cek firewall Windows tidak blokir aplikasi                                                                             |
| "Wajah tidak dikenali" terus untuk siswa yang sudah enroll | Cek `FACE_ENCRYPTION_KEY` sama persis dengan server; cek sync embedding sudah jalan (lihat log)                                                |
| Kamera tidak muncul/error saat start                       | Cek kamera tidak dipakai aplikasi lain (Zoom, Teams, dst); cek index kamera (`cv2.VideoCapture(0)` — coba ganti ke `1` kalau ada multi-kamera) |
