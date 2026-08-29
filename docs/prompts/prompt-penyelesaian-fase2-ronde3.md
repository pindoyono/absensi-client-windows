# Prompt: Penyelesaian Bug & Catatan Kecil Fase 2 (Ronde 3)

Lanjutan dari review sebelumnya — 5 dari 8 prioritas sudah selesai
dengan baik. Dokumen ini fokus ke sisanya: 1 bug baru yang ditemukan,
2 prioritas yang belum dikerjakan, dan 3 catatan kecil. Urutan
prioritas sama seperti sebelumnya — 🔴 dulu.

---

## 🔴 WAJIB — Fix `UnboundLocalError` di alur enrollment offline

**File:** `app/ui/admin_window.py`, method yang isinya alur kirim ke server (sekitar baris 558-608, dalam fungsi yang berisi `resp_list = requests.get(f"{self.server_url}/siswa"...)`.

**Masalah:** kalau `GET /siswa` gagal (server tak terjangkau), kode masuk
`except` tapi TIDAK `return` — lanjut ke `repo.upsert_siswa(siswa_id, ...)`
padahal `siswa_id` belum pernah punya nilai. Crash `UnboundLocalError`.

**Keputusan desain yang perlu dipahami dulu:** enrollment BERBEDA dari
absensi. Absensi memang didesain offline-first (client generate UUID
sendiri). Enrollment butuh `siswa_id` INTEGER dari server (auto-increment
di database `siswa`) — tidak ada skema ID lokal yang valid untuk
menggantikannya. Jadi solusi yang benar BUKAN "coba tetap simpan
lokal", tapi: **kalau server tidak terjangkau, enrollment gagal
dengan jelas, minta admin coba lagi saat online.**

**Ganti seluruh blok `try/except` beserta bagian setelahnya jadi:**

```python
        try:
            # 1. Cari siswa yang sudah ada berdasarkan NIS, atau buat baru
            resp_list = requests.get(f"{self.server_url}/siswa", headers=headers, timeout=15)
            resp_list.raise_for_status()
            existing = next((s for s in resp_list.json() if s["nis"] == nis), None)

            if existing:
                siswa_id = existing["id"]
            else:
                resp_create = requests.post(
                    f"{self.server_url}/siswa", headers=headers,
                    json={"nis": nis, "nama": nama, "kelas": kelas}, timeout=15,
                )
                resp_create.raise_for_status()
                siswa_id = resp_create.json()["id"]

            # 2. Kirim embedding ke server
            self.lbl_status.setText("⏳ Mengirim data wajah ke server...")
            payload = {
                "embedding": hasil.embedding.tolist(),
                "model_version": engine.model_version,   # <-- fix catatan kecil #3, lihat bawah
            }
            logger.debug("Enroll payload: %d dim, model=%s", len(payload["embedding"]), payload["model_version"])
            resp_enroll = requests.post(
                f"{self.server_url}/siswa/{siswa_id}/enroll", headers=headers,
                json=payload, timeout=30,
            )
            logger.debug("Enroll response: %s %s", resp_enroll.status_code, resp_enroll.text[:200])
            resp_enroll.raise_for_status()

        except requests.RequestException as e:
            err_msg = str(e)
            if e.response is not None:
                err_msg = f"{e.response.status_code} {e.response.reason}: {e.response.text[:300]}"
            logger.warning("Enrollment gagal ke server: %s", err_msg)
            self.lbl_status.setText(f"❌ Enrollment gagal: {err_msg}")
            QMessageBox.critical(
                self, "Enrollment Gagal",
                f"Tidak bisa mendaftarkan siswa ke server.\n\n{err_msg}\n\n"
                "Enrollment butuh koneksi ke server (ID siswa berasal dari "
                "server). Coba lagi setelah koneksi tersedia.",
            )
            return   # <-- KUNCI PERBAIKAN: hentikan di sini, jangan lanjut

        # Titik ini HANYA tercapai kalau proses ke server berhasil penuh
        repo.upsert_siswa(siswa_id, nis, nama, kelas)
        enc = encrypt_embedding(hasil.embedding, face_encryption_key)
        repo.upsert_embedding(siswa_id, enc, engine.model_version, datetime.now().isoformat())

        self.lbl_status.setText(f"✅ {nama} berhasil di-enroll!")
        QMessageBox.information(self, "Berhasil", f"Siswa {nama} berhasil di-enroll ke server.")
```

**Tambahan wajib** — pastikan baris ini ada di bagian atas
`admin_window.py` (kalau belum ada), untuk `logger.debug`/`logger.warning` di atas:
```python
import logging
logger = logging.getLogger(__name__)
```

**Test manual setelah fix:**
1. Matikan WiFi/cabut LAN di komputer
2. Coba enroll siswa lewat panel admin
3. ✅ Harus muncul dialog error jelas "Enrollment Gagal... coba lagi
   setelah koneksi tersedia" — **BUKAN** crash aplikasi
4. Nyalakan lagi internet, coba enroll siswa yang sama
5. ✅ Harus berhasil, dan siswa itu muncul di `GET /siswa` server

---

## 🟡 Rapikan duplikasi kode OAuth (`setup.py` vs `oauth_server.py`)

Cara paling aman: untuk TIAP fungsi di `setup.py`, cek dulu apakah
benar-benar dipakai di luar filenya sendiri sebelum hapus:

```bash
cd D:\Project Absensi\client-windows
for /f %f in ('findstr /r "^def " app\device\setup.py') do echo %f
```

Atau lebih mudah, jalankan satu-satu (ganti `NAMA_FUNGSI`):
```bash
grep -rn "NAMA_FUNGSI" --include="*.py" . | grep -v "app/device/setup.py"
```

Kalau hasilnya KOSONG (tidak ada baris muncul), fungsi itu aman dihapus
dari `setup.py`. Berdasarkan pengecekan saya sebelumnya, kandidat yang
kemungkinan besar aman dihapus:
- `buka_browser_google_oauth` (duplikat konsep dengan `oauth_server.py`)
- `tukar_code_untuk_token` (nama PERSIS sama juga ada di `oauth_server.py` — pasti ada yang salah satu harus hilang)
- `registrasi_device`
- `proses_setup_device`

**Verifikasi ulang masing-masing dengan grep di atas SEBELUM hapus** —
jangan percaya daftar ini buta, karena kode bisa saja sudah berubah
lagi sejak saya cek terakhir.

Setelah bersih, jalankan test suite untuk pastikan tidak ada yang
ternyata masih bergantung ke fungsi yang dihapus:
```bash
pytest tests/ -v
```

---

## 🟡 Tambah kalibrasi ke 4-5 orang

`foto_kalibrasi/` masih cuma `orang_1` dan `orang_2`. Tambahkan 2-3
orang lagi:

```bash
python scripts/ambil_foto_kalibrasi.py
# ikuti prompt, simpan ke foto_kalibrasi/orang_3/, orang_4/, dst
# (4-5 foto per orang, sudut/pencahayaan sedikit berbeda tiap foto)
```

Lalu jalankan ulang kalibrasi:
```bash
python scripts/kalibrasi_ambang_batas.py
```

Bandingkan hasil `AMBANG_BATAS_JARAK` baru dengan yang lama (`0.1623`).
Kalau berubah signifikan (misal selisih >0.05), update nilainya di
`app/face/matcher.py`. Kalau cuma bergeser sedikit, boleh dipertahankan
yang lama tapi catat di README bahwa kalibrasi sudah divalidasi dengan
sampel lebih besar.

---

## 🟢 Perbaiki konsistensi interface `skip_liveness`

**File:** `app/face/engine_base.py` — update signature abstrak:
```python
@abstractmethod
def proses_frame(self, frame_bgr: np.ndarray, skip_liveness: bool = False) -> HasilDeteksi:
    """
    skip_liveness: True untuk kondisi terkontrol/diawasi admin (mis.
    proses enrollment) di mana anti-spoofing tidak relevan — device
    kiosk untuk absensi harian TIDAK BOLEH pernah memakai True.
    """
    ...
```

**File:** `app/face/opencv_engine.py` — update signature biar konsisten
(placeholder ini tidak punya liveness sungguhan, jadi parameternya
diterima tapi tidak berpengaruh — cukup untuk menjaga kontrak interface):
```python
def proses_frame(self, frame_bgr: np.ndarray, skip_liveness: bool = False) -> HasilDeteksi:
    # skip_liveness tidak berpengaruh di sini — placeholder ini memang
    # tidak pernah punya liveness check sungguhan (selalu lolos)
    ...  # isi method tetap sama seperti sebelumnya
```

Setelah ini, tambahkan 1 test di `tests/test_face_matching.py` untuk
memastikan kontraknya konsisten:
```python
def test_opencv_engine_menerima_parameter_skip_liveness(engine):
    frame = np.zeros((300, 300, 3), dtype=np.uint8)
    # tidak boleh raise TypeError gara-gara parameter tidak dikenal
    hasil = engine.proses_frame(frame, skip_liveness=True)
    assert hasil is not None
```

---

## 🟢 Bersihkan sisa `print(f"[DEBUG]...")`

Sudah tercakup di patch enrollment di atas (diganti `logger.debug`).
Cek sekali lagi tidak ada sisa di file lain:
```bash
grep -rn "print(f\"\[DEBUG\]" --include="*.py" .
```
Kalau ada yang tersisa di luar `admin_window.py`, ganti pola yang sama
(`logger.debug(...)`, pastikan `import logging` + `logger = logging.getLogger(__name__)` ada di file itu).

---

## 🟢 `model_version` yang dikirim ke server

Sudah ikut diperbaiki di patch enrollment di atas (`engine.model_version`
menggantikan hardcode `"minifasnet-v1"`). Tidak ada langkah tambahan.

---

## Definition of Done — Ronde 3

- [ ] Enrollment saat offline menampilkan error jelas, **bukan crash** (test manual: cabut internet, coba enroll)
- [ ] Enrollment saat online tetap berhasil seperti sebelumnya (test manual: enroll 1 siswa, cek muncul di `GET /siswa` server)
- [ ] Duplikasi fungsi OAuth sudah dihapus, tidak ada nama fungsi yang sama persis di 2 file
- [ ] `pytest tests/ -v` tetap 48+ lulus setelah pembersihan
- [ ] Kalibrasi pakai 4-5 orang, `AMBANG_BATAS_JARAK` diperbarui kalau perlu
- [ ] `FaceEngine.proses_frame()` konsisten menerima `skip_liveness` di semua implementasi
- [ ] Tidak ada lagi `print(f"[DEBUG]...")` tersisa di codebase
- [ ] `model_version` yang tersimpan di server sesuai `engine.model_version` sesungguhnya, bukan string hardcode

Setelah semua tercentang di sini DAN checklist Ronde 2 sebelumnya
(`prompt-penyelesaian-fase2.md`) juga tercentang penuh — termasuk
Skenario 5 & 6 pengujian webcam fisik — barulah Fase 2 pantas dianggap
selesai sepenuhnya.
