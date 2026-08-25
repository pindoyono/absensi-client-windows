# Kontrak API — Panduan Integrasi Client (Windows & Android)

Dokumen ini adalah referensi wajib untuk mengembangkan client Windows (PyQt) dan Android (Kotlin). Semua endpoint di bawah sudah diuji berjalan (lihat catatan verifikasi di tiap bagian). Base URL contoh: `https://absensi.smkxxx.sch.id`.

Dokumentasi interaktif lengkap (coba langsung tiap endpoint) tersedia di `/docs` setelah server jalan.

---

## 1. Autentikasi

Ada **2 jenis autentikasi berbeda** di sistem ini — jangan tertukar:

| Jenis | Dipakai oleh | Cara |
|---|---|---|
| **JWT guru** (Bearer token) | Dashboard web guru piket/admin | Login Google SSO → dapat token → header `Authorization: Bearer <token>` |
| **API key device** | Client Windows/Android (kiosk) | Didapat sekali saat registrasi device → header `X-Device-Api-Key: <key>` |

Client kiosk (Windows/Android) **tidak pernah login sebagai guru** — device punya identitasnya sendiri lewat API key, terpisah dari akun manusia.

### 1.1 Registrasi device (dilakukan admin, sekali per device)

```
POST /device/register
Authorization: Bearer <JWT admin>
Content-Type: application/json

{
  "device_id": "gerbang-utama-01",
  "nama_lokasi": "Gerbang Utama",
  "platform": "windows"
}
```

Response (**api_key hanya tampil sekali di sini** — simpan di konfigurasi lokal device, misal file config terenkripsi atau Android Keystore):

```json
{
  "device_id": "gerbang-utama-01",
  "api_key": "bWPQ6zMvkPZrutPiOGRogQp2auVGrWo2JBlRz8p5vSs",
  "peringatan": "Simpan api_key ini sekarang — tidak akan ditampilkan lagi."
}
```

✅ Sudah diuji: register device → dapat api_key → dipakai untuk sync, berhasil end-to-end.

---

## 2. Alur Enrollment Wajah

**Penting — keputusan desain:** embedding wajah dihitung **di sisi client** (memakai engine MiniFASNet yang sama dipakai untuk matching harian), server hanya menyimpan hasilnya. Ini supaya model yang dipakai untuk enrollment dan untuk absen harian selalu konsisten.

```
POST /siswa/{siswa_id}/enroll
Authorization: Bearer <JWT admin atau guru_piket>
Content-Type: application/json

{
  "embedding": [0.123, -0.456, ...],   // vector dari engine MiniFASNet, minimal 64 nilai
  "model_version": "minifasnet-v1"
}
```

Alur di client saat proses enrollment (lihat detail lengkap di dokumen arsitektur bagian 10.2):
1. Ambil 3-5 foto wajah dari sudut berbeda
2. Cek kualitas tiap foto (pencahayaan, wajah tidak terpotong) — di client, sebelum dikirim
3. Generate embedding dari foto-foto tsb (di client)
4. Kirim embedding ke endpoint di atas
5. **Uji langsung**: minta siswa scan di kiosk yang sama, pastikan berhasil dikenali sebelum dianggap selesai

✅ Sudah diuji: endpoint enroll berhasil menyimpan embedding terenkripsi dan set `enrolled=true`.

---

## 3. Sync Embedding ke Cache Lokal Client

Client menarik embedding semua siswa (untuk matching offline) lewat:

```
GET /embeddings/sync?diperbarui_sejak=2026-08-20T00:00:00
X-Device-Id: gerbang-utama-01
X-Device-Api-Key: <api_key device>
```

Response:

```json
{
  "server_time": "2026-08-23T10:00:00",
  "jumlah": 3,
  "data": [
    {
      "siswa_id": 1,
      "nis": "22001",
      "nama": "Ahmad Fauzan",
      "kelas": "XI Elektronika",
      "embedding_encrypted": "gAAAAABm...(hex string)",
      "model_version": "minifasnet-v1",
      "diperbarui_pada": "2026-08-20T08:00:00"
    }
  ]
}
```

**Cara pakai di client:**
- Simpan `embedding_encrypted` (hex string) apa adanya ke SQLite lokal (kolom BLOB, decode dari hex dulu).
- **Jangan didekripsi di client dengan key yang sama seperti server** — client seharusnya punya mekanisme dekripsi sendiri yang konsisten (lihat catatan keamanan di bagian 7).
- Panggil endpoint ini secara periodik (misal tiap kali online, atau tiap beberapa jam) dengan `diperbarui_sejak` = waktu sync terakhir, supaya tidak menarik ulang semua data tiap kali.
- Simpan `server_time` dari response sebagai acuan `diperbarui_sejak` untuk sync berikutnya (bukan waktu lokal device, untuk menghindari drift jam).

---

## 4. Sync Absensi — Endpoint Paling Kritis

```
POST /absensi/sync
X-Device-Api-Key: <api_key device>
Content-Type: application/json

{
  "records": [
    {
      "record_id": "c99b4ed1-a692-4cad-b304-d0a9b087ad83",
      "siswa_id": 1,
      "tanggal": "2026-08-23",
      "type": "MASUK",
      "jam_aktual": "2026-08-23T07:02:15+08:00",
      "status_kehadiran_otomatis": "NORMAL",
      "catatan": null,
      "device_id": "gerbang-utama-01"
    }
  ]
}
```

**Aturan wajib di sisi client:**
- `record_id` dibuat DI CLIENT saat capture (pakai UUID v4), **bukan** ditunggu dari server. Ini yang membuat retry aman.
- Boleh kirim banyak record sekaligus dalam 1 array (batch) — penting untuk kasus device lama offline lalu online, ada banyak antrian record.
- Kirim ulang record yang gagal sync tanpa mengubah `record_id`-nya — server akan mengenali sebagai retry, bukan data baru.

Response:

```json
{
  "total": 1,
  "disimpan": 1,
  "duplikat": 0,
  "gagal": 0,
  "hasil": [
    {"record_id": "c99b4ed1-...", "status": "disimpan", "pesan": null}
  ]
}
```

**Cara client menangani tiap status di `hasil`:**

| Status | Aksi di client |
|---|---|
| `disimpan` | Tandai record lokal `synced = true` |
| `duplikat_diabaikan` | Tandai juga `synced = true` — JANGAN retry lagi, ini bukan error |
| `gagal` | Biarkan `synced = false`, akan dicoba ulang di siklus sync berikutnya |

✅ **Sudah diuji end-to-end lewat HTTP asli**: kirim MASUK pertama → `disimpan`. Kirim MASUK kedua untuk siswa & tanggal sama dengan `record_id` berbeda → otomatis `duplikat_diabaikan`. Ini membuktikan aturan "maksimal 2 record per hari" ditegakkan oleh server, bukan cuma diasumsikan benar dari sisi client.

---

## 5. Jadwal (untuk Menghitung Status Terlambat/Pulang Cepat)

```
GET /jadwal/efektif?kelas=XI%20Elektronika
Authorization: Bearer <JWT>   -- lihat catatan bagian 7 soal auth device vs guru
```

Response memberi jam masuk/pulang yang berlaku HARI INI (sudah menghitung override kalau ada):

```json
{"sumber": "standar", "jam_masuk": "07:00:00", "jam_pulang": "15:00:00"}
```

Client harus:
1. Tarik & cache jadwal ini secara berkala (idealnya tiap sync sukses), simpan ke SQLite lokal.
2. Saat offline, pakai jadwal yang di-cache terakhir untuk menghitung `status_kehadiran_otomatis` (`TERLAMBAT` kalau jam_aktual > jam_masuk + toleransi, dst).

---

## 6. Skenario Error yang Harus Ditangani Client

| Kondisi | HTTP Status | Penanganan client |
|---|---|---|
| Device belum terdaftar/dinonaktifkan | 401 | Tampilkan pesan ke admin, hentikan sync sampai device didaftarkan ulang |
| API key device salah | 401 | Sama seperti di atas — jangan retry otomatis tanpa batas |
| Siswa tidak ditemukan (enroll ke siswa_id invalid) | 404 | Sinkronkan ulang data siswa dari server |
| Server tidak terjangkau (timeout/connection error) | — | Ini kondisi **offline normal**, bukan error aplikasi — simpan lokal, retry nanti sesuai desain offline-first |

---

## 7. Catatan Keamanan untuk Developer Client

- SQLite lokal **wajib dienkripsi** (SQLCipher) — device Windows/Android bisa hilang/dicuri, data 1000 siswa (termasuk embedding wajah) ada di dalamnya.
- API key device disimpan di **Windows Credential Manager** (Windows) atau **Android Keystore** (Android) — jangan hardcode di file config plain text.
- Endpoint `/embeddings/sync` mengirim embedding dalam bentuk `embedding_encrypted` (hasil enkripsi Fernet server) sebagai hex string. **Skema saat ini: client menyimpan bytes terenkripsi ini apa adanya di SQLite, TIDAK didekripsi di client.** Matching wajah di client dilakukan dengan membandingkan embedding hasil capture kamera (belum dienkripsi) terhadap — ini butuh keputusan desain tambahan sebelum implementasi client dimulai:
  - **Opsi A** (lebih sederhana): client juga menyimpan `FACE_ENCRYPTION_KEY` yang sama dengan server (didistribusikan lewat setup device yang aman), dekripsi saat perlu matching, held di memory saja (tidak ditulis ke disk plain).
  - **Opsi B** (lebih aman tapi lebih rumit): server expose endpoint matching (`POST /embeddings/match`) yang menerima embedding hasil capture dan mengembalikan siswa_id yang cocok — TAPI ini butuh koneksi internet, bertentangan dengan syarat "harus bisa matching offline".
  - **Rekomendasi**: pakai Opsi A untuk versi awal (offline-first tetap terpenuhi), key didistribusikan manual saat setup device oleh admin (bukan lewat API), dicatat sebagai keputusan yang perlu di-review ulang kalau nanti threat model berubah.

---

## 8. Ringkasan Alur Lengkap Client (Referensi Cepat)

```
Setup device (sekali):
  1. Admin register device → dapat api_key → simpan aman di device

Startup / berkala saat online:
  2. GET /jadwal/efektif → cache jadwal lokal
  3. GET /embeddings/sync?diperbarui_sejak=... → update cache embedding lokal

Saat siswa scan wajah:
  4. Capture wajah → liveness check → cari embedding cocok dari cache lokal
  5. Cek status hari ini di SQLite lokal (BELUM_ABSEN/SUDAH_MASUK/SELESAI)
  6. Hitung status_kehadiran_otomatis dari jadwal ter-cache
  7. Generate record_id (UUID) → simpan ke SQLite lokal, synced=false
  8. Tampilkan feedback ke siswa (sesuai mockup UI kiosk)

Background sync worker (tiap 30-60 detik jika online):
  9. Ambil semua record synced=false dari SQLite
  10. POST /absensi/sync dengan batch record tsb
  11. Update status lokal sesuai hasil (disimpan/duplikat_diabaikan/gagal)
```
