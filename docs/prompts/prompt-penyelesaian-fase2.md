# Prompt: Menyelesaikan Fase 2 — Mode Online, Bug, & Fitur Tersisa

Dokumen ini urut berdasarkan **prioritas**, bukan urutan mengerjakan sesuka
hati — 🔴 wajib dulu (ada risiko keamanan/fungsi inti), baru 🟡, baru 🟢.
Kerjakan berurutan, jangan lompat ke fitur baru kalau 🔴 belum beres.

---

## 🔴 PRIORITAS 1 — Tutup celah bypass yang SEKARANG bisa diakses dari layar kiosk

Screenshot terakhir menunjukkan tombol **"Login Admin"** sudah tampil
langsung di layar kiosk yang menghadap publik (gerbang sekolah). Ini
mengubah tingkat urgensi celah yang saya temukan sebelumnya — dulu cuma
"ada di kode", sekarang **siapa saja yang berdiri di depan kiosk bisa
coba akses panel admin**.

Di `app/ui/admin_window.py`, fungsi `_manual_token()` masih punya jalur ini:

```python
if token.lower() == "offline":
    from app.device.setup import simpan_config_lokal
    simpan_config_lokal("offline", self.device_id, "offline")
    self.login_berhasil.emit("offline_token")
    return
```

**Hapus blok ini sepenuhnya.** Alasan aman dihapus: skenario "device
sudah pernah login, boleh dipakai lagi tanpa login ulang" **sudah
ditangani dengan benar** di tempat lain — lihat `AdminWindow.__init__`:

```python
sudah_terdaftar = (
    config.get("device_id") == device_id and
    config.get("api_key") and
    config.get("api_key") != "offline"
)
```

Jadi kalau device memang sudah pernah login sah, dia otomatis masuk
tanpa perlu ketik apapun — jalur `"offline"` di `_manual_token()` itu
murni pintu belakang tambahan yang tidak dibutuhkan, sekaligus
berbahaya karena sekarang terjangkau dari tombol yang tampil publik.

**Setelah dihapus, test manual:** buka kiosk di device yang BELUM
pernah login, klik "Login Admin", coba ketik apa saja di kolom token
manual (termasuk kata "offline") → harus GAGAL, satu-satunya jalur
masuk yang valid adalah tombol "Login dengan Google Sekolah".

### Pertimbangan tambahan (putuskan salah satu):

Apakah tombol "Login Admin" memang seharusnya tampil di kiosk yang
menghadap siswa sepanjang hari? Dua opsi wajar:

- **Opsi A**: biarkan tampil, tapi pastikan SATU-SATUNYA jalur masuk
  adalah Google OAuth asli (setelah bypass di atas dihapus, ini sudah
  cukup aman — siswa iseng klik tombol itu paling mentok cuma bisa
  buka halaman login Google, tidak bisa masuk tanpa akun Google
  sekolah yang valid).
- **Opsi B**: sembunyikan tombol dari tampilan normal, munculkan
  hanya lewat kombinasi tombol tersembunyi (misal tekan `Ctrl+Shift+A`)
  — mengurangi rasa penasaran siswa untuk coba-coba, walau secara
  teknis tidak menambah keamanan (siapapun yang baca source code
  publik tetap tahu kombinasinya).

Opsi A cukup aman SETELAH bypass dihapus — tidak wajib kerjakan Opsi B,
tapi sebutkan pilihan yang diambil di README.

---

## 🔴 PRIORITAS 2 — Diagnosa kenapa badge selalu "Offline"

Dari screenshot, badge menunjukkan "Offline · disimpan lokal" — perlu
dipastikan apakah ini memang device belum ada internet saat itu, atau
ada bug yang membuat status online tidak pernah terdeteksi walau
internet ada. Ikuti urutan diagnosa ini:

### 2.1 Test konektivitas independen dari aplikasi

Di PowerShell, di komputer kiosk yang sama:

```powershell
Invoke-WebRequest https://absen.smkn2malinau.sch.id/health
```

✅ Kalau ini berhasil (`{"status":"ok"}`) tapi aplikasi tetap bilang
"Offline" → bug di aplikasi, lanjut ke 2.2.
❌ Kalau ini GAGAL → bukan bug aplikasi, cek jaringan komputer itu
(firewall Windows, proxy sekolah, DNS).

### 2.2 Cek isi `.env` device benar

```powershell
type .env | findstr SERVER_URL
```

Pastikan persis `SERVER_URL=https://absen.smkn2malinau.sch.id` — tanpa
salah ketik, tanpa spasi tersembunyi, tanpa `http://` (harus `https://`).

### 2.3 Tambahkan logging sementara di `cek_koneksi()`

`ApiClient.cek_koneksi()` saat ini **menelan semua exception secara
diam-diam** — bagus untuk stabilitas produksi, tapi menyulitkan
diagnosa sekarang. Tambahkan logging sementara:

```python
# app/api/client.py
def cek_koneksi(self) -> bool:
    try:
        resp = requests.get(f"{self.base_url}/health", timeout=3)
        return resp.status_code == 200
    except requests.RequestException as e:
        import logging
        logging.getLogger(__name__).warning("cek_koneksi gagal: %s", e)  # TEMPORARY
        return False
```

Jalankan `python main.py` lagi, lihat log muncul di terminal — pesan
error aslinya (timeout? SSL error? connection refused?) akan
menunjukkan penyebab sebenarnya. **Hapus baris logging ini lagi**
setelah masalahnya ketemu (atau ganti jadi `logger.debug` permanen,
bukan `print`/`warning` yang berisik di produksi).

### 2.4 Kemungkinan lain: badge butuh waktu

Badge baru ter-update setelah siklus sync PERTAMA selesai (lihat
`SyncWorker.run()` — jalan sekali di awal sebelum `sleep()`). Kalau
screenshot diambil PERSIS saat aplikasi baru dibuka, mungkin itu cuma
soal timing, bukan bug. Kalau setelah ditunggu 1-2 menit tetap
"Offline" padahal 2.1 berhasil, itu baru bug beneran.

### 2.5 Perbaikan UX kecil (opsional tapi direkomendasikan)

Supaya tidak perlu nunggu 45 detik pertama, jalankan 1 pengecekan
konektivitas SINKRON sebelum window ditampilkan, di `main.py`:

```python
# Setelah window dibuat, sebelum sync_worker.start():
window.set_status_online(api.cek_koneksi())
```

---

## 🔴 PRIORITAS 3 — Sambungkan enrollment ke server sungguhan

Ini gap terbesar yang masih sama sejak review pertama saya. Saat ini
`_start_cam()` di `admin_window.py` cuma simpan ke SQLite lokal dengan
`siswa_id` acak — siswa yang di-enroll dari device ini **tidak pernah
sampai ke server**, jadi tidak akan dikenali di kiosk device lain.

### 3.1 Simpan JWT dari hasil login, teruskan ke fungsi enrollment

Saat ini setelah OAuth sukses, `jwt_token` cuma disimpan ke
`device_config.json`, tidak diteruskan ke bagian enrollment UI.
Tambahkan sebagai atribut `AdminWindow`:

```python
# Di AdminWindow._on_login_success(), setelah dashboard dibangun:
config = load_config_lokal()
self.jwt_token = config.get("jwt_token", "")
```

### 3.2 Ganti `_start_cam()` supaya kirim ke server dulu, baru cache lokal

```python
def _start_cam(self, engine, repo, face_encryption_key):
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        self.lbl_status.setText("❌ Kamera tidak dapat dibuka!")
        return

    self.lbl_status.setText("⏳ Mengambil foto wajah...")
    ok, frame = cap.read()
    cap.release()
    if not ok:
        self.lbl_status.setText("❌ Gagal capture frame kamera.")
        return

    hasil = engine.proses_frame(frame)
    if hasil.embedding is None:
        self.lbl_status.setText(f"❌ Gagal deteksi wajah: {hasil.alasan_gagal}")
        return

    nis = self.input_nis.text().strip()
    nama = self.input_nama.text().strip()
    kelas = self.input_kelas.text().strip()
    if not nis or not nama or not kelas:
        self.lbl_status.setText("❌ NIS, nama, dan kelas wajib diisi.")
        return

    if not self.jwt_token:
        self.lbl_status.setText("❌ Sesi login tidak valid, silakan login ulang.")
        return

    headers = {"Authorization": f"Bearer {self.jwt_token}"}
    self.lbl_status.setText("⏳ Mendaftarkan siswa ke server...")

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

        # 2. Kirim embedding ke server (server yang enkripsi & simpan permanen)
        self.lbl_status.setText("⏳ Mengirim data wajah ke server...")
        resp_enroll = requests.post(
            f"{self.server_url}/siswa/{siswa_id}/enroll", headers=headers,
            json={"embedding": hasil.embedding.tolist(), "model_version": engine.model_version},
            timeout=15,
        )
        resp_enroll.raise_for_status()

    except requests.RequestException as e:
        self.lbl_status.setText(f"❌ Gagal kirim ke server: {e}")
        QMessageBox.critical(self, "Gagal", f"Enrollment TIDAK tersimpan di server.\n\n{e}")
        return

    # 3. Baru cache ke lokal (device ini langsung bisa kenali tanpa nunggu sync)
    repo.upsert_siswa(siswa_id, nis, nama, kelas)
    enc = encrypt_embedding(hasil.embedding, face_encryption_key)
    repo.upsert_embedding(siswa_id, enc, engine.model_version, datetime.now().isoformat())

    self.lbl_status.setText(f"✅ {nama} berhasil di-enroll (tersimpan di server)!")
    QMessageBox.information(self, "Berhasil", f"Siswa {nama} berhasil di-enroll ke SERVER.")
```

**Catatan penting:** `server_url` juga perlu jadi atribut `self` di
`AdminWindow` (cek apakah sudah ada — kalau belum, tambahkan di
`__init__` sebelum dipakai di atas).

### 3.3 Test end-to-end setelah perubahan ini

1. Enroll 1 siswa lewat panel admin di device A
2. Cek langsung ke server: `GET /siswa` (lewat Swagger `/docs`) — siswa
   baru itu harus muncul di sana, bukan cuma di device A
3. Di device B (atau tunggu siklus sync berikutnya di device A sendiri
   lewat `GET /embeddings/sync`), pastikan siswa itu bisa dikenali juga

---

## 🟡 PRIORITAS 4 — Rapikan duplikasi kode OAuth

Ada 2 implementasi OAuth flow yang tumpang tindih:

- `app/device/oauth_server.py` — implicit flow, port hardcode 18080, **ini yang benar-benar dipakai** `admin_window.py`
- `app/device/setup.py` — authorization code flow + `client_secret`, port dinamis, **fungsi OAuth-nya jadi kode mati** (cuma `simpan_config_lokal`/`load_config_lokal`/`update_env_file` yang masih dipakai)

Pilih salah satu jadi satu-satunya sumber kebenaran:

- Kalau tetap pakai implicit flow (`oauth_server.py`) — **hapus** fungsi OAuth di `setup.py` (`buka_browser_google_oauth`, `tukar_code_untuk_token`, `login_dengan_id_token` kalau tidak dipakai lagi, `registrasi_device`, `proses_setup_device`), sisakan cuma fungsi config lokal yang memang masih dipakai.
- Pindahkan fungsi config lokal (`simpan_config_lokal`, `load_config_lokal`, `update_env_file`, `CONFIG_PATH`) ke file baru `app/device/config_lokal.py` supaya jelas pemisahannya, atau biarkan di `setup.py` tapi hapus semua yang tidak terpakai supaya tidak membingungkan pembaca kode berikutnya.

---

## 🟡 PRIORITAS 5 — Tambah test untuk kode `app/device/`

775 baris kode auth/networking baru, 0 test. Bagian yang **logika
murni** (tidak butuh browser/server sungguhan) bisa dites seperti
pola `test_api_client.py` yang sudah ada:

```python
# tests/test_device_setup.py
import json
from app.device.setup import simpan_config_lokal, load_config_lokal

def test_simpan_dan_load_config(tmp_path, monkeypatch):
    import app.device.setup as setup_mod
    monkeypatch.setattr(setup_mod, "CONFIG_PATH", str(tmp_path / "device_config.json"))

    simpan_config_lokal("key-123", "kiosk-01", "jwt-abc")
    hasil = load_config_lokal()

    assert hasil["api_key"] == "key-123"
    assert hasil["device_id"] == "kiosk-01"
    assert hasil["jwt_token"] == "jwt-abc"
```

```python
# tests/test_oauth_server.py
from app.device.oauth_server import _generate_pkce_pair
import hashlib, base64

def test_pkce_challenge_sesuai_verifier():
    verifier, challenge = _generate_pkce_pair()
    expected = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode()).digest()
    ).decode().rstrip("=")
    assert challenge == expected
```

Untuk bagian yang butuh HTTP call sungguhan (`proses_oauth_token`,
`registrasi_device`), pakai `responses` library (sudah ada di
dependencies) seperti pola `test_api_client.py` — mock respons server,
verifikasi request yang dikirim formatnya benar.

---

## 🟡 PRIORITAS 6 — Update README

README saat ini masih bilang "41 test lulus" dan membahas
`OpenCVPlaceholderEngine` seolah MiniFASNet belum terintegrasi. Setelah
semua di atas selesai, update bagian "Status Fase 2" mencerminkan
kondisi sebenarnya: jumlah test terbaru, engine yang dipakai (MiniFASNet

- ArcFace), status mode online, status enrollment-ke-server, dan
  checklist item mana yang masih tersisa.

---

## 🟡 PRIORITAS 7 — Kalibrasi dengan lebih banyak orang

`foto_kalibrasi/` masih cuma 2 orang. Tambahkan minimal 2-3 orang lagi
(target 4-5 total), jalankan ulang `scripts/kalibrasi_ambang_batas.py`,
update `AMBANG_BATAS_JARAK` di `matcher.py` kalau hasilnya berubah
signifikan dari `0.1623` yang sekarang.

---

## 🟢 PRIORITAS 8 — Lanjutkan pengujian webcam fisik (Bagian B, tertunda)

Sejak liveness detection sudah benar-benar aktif (bug hardcode sudah
diperbaiki), **Skenario 5 & 6** dari prompt sebelumnya (todongkan
foto/video ke kamera) belum pernah benar-benar diuji dengan liveness
yang aktif. Ini WAJIB dilakukan sebelum pilot — lihat dokumen
`prompt-integrasi-minifasnet-dan-uji-webcam.md` Bagian B untuk detail
lengkap 10 skenarionya. Kalau skenario 5/6 gagal (foto masih bisa
lolos), berarti `AMBANG_LIVENESS` atau `INDEKS_KELAS_LIVE` di
`minifasnet_engine.py` perlu dikalibrasi ulang — coba nilai `INDEKS_KELAS_LIVE = 1` kalau `0` ternyata terbalik.

---

## Definition of Done — Fase 2 Benar-Benar Selesai

- [ ] Bypass `"offline"` di `_manual_token()` sudah dihapus total
- [ ] Badge online/offline terbukti akurat (test: cabut & sambung internet, badge berubah sesuai)
- [ ] Enroll 1 siswa lewat panel admin → **terbukti muncul di server** (`GET /siswa`), bukan cuma lokal
- [ ] Siswa yang di-enroll di device A bisa dikenali di device B (atau minimal setelah 1 siklus sync)
- [ ] Duplikasi `oauth_server.py`/`setup.py` sudah dirapikan jadi satu sumber kebenaran
- [ ] Ada test untuk bagian logika murni di `app/device/`
- [ ] README mencerminkan kondisi sebenarnya (jumlah test, engine, status online, status enrollment)
- [ ] Kalibrasi pakai minimal 4-5 orang berbeda
- [ ] Skenario 5 & 6 (anti-spoofing foto/video) lolos dengan liveness yang sudah aktif
- [ ] Seluruh test suite (`pytest tests/ -v`) lulus tanpa ada yang di-skip karena model hilang

Setelah semua tercentang, baru pantas dianggap Fase 2 selesai dan siap
pilot terbatas (1 kelas) sebelum lanjut ke Fase 3 (Client Android).

Sesuai instruksi, langkah selanjutnya adalah Kalibrasi dengan lebih banyak orang dan Uji webcam fisik. Apakah Anda ingin saya membantu menjalankan script kalibrasi sekarang?
