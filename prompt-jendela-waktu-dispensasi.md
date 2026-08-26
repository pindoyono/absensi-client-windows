# Prompt: Jendela Waktu Absen + Dispensasi Guru Piket

Fitur baru, dikerjakan di 2 repo: **Server dulu, baru Client** (client
butuh endpoint dispensasi dari server untuk sinkronisasi).

## Aturan yang diimplementasikan

- **MASUK**: hanya bisa dilakukan mulai `jam_masuk_standar − 2 jam`.
  Sebelum itu → ditolak, "belum waktunya". Setelah jam masuk tetap
  boleh (jadi TERLAMBAT, tidak berubah dari sekarang) — tidak ada
  batas akhir untuk MASUK.
- **PULANG**: hanya bisa dilakukan mulai `jam_pulang_standar`. Sebelum
  itu → ditolak, KECUALI ada **dispensasi aktif** untuk siswa &
  tanggal tsb yang sudah diberikan guru piket sebelumnya.
- Dispensasi adalah **izin di muka** (sebelum siswa scan) — beda
  dengan `status_kehadiran_final`/approve yang sudah ada (itu
  verifikasi SESUDAH absen tercatat, untuk kasus TERLAMBAT biasa).

---

# BAGIAN A — Server (`absensi-server`)

## A.1 Tabel baru: `dispensasi`

Tambahkan ke `schema.sql`, buat migration Alembic baru
(`alembic revision --autogenerate -m "tambah tabel dispensasi"` setelah
update `app/models.py`):

```sql
CREATE TABLE dispensasi (
    id SERIAL PRIMARY KEY,
    siswa_id INT NOT NULL REFERENCES siswa(id),
    tanggal DATE NOT NULL,
    jenis VARCHAR(20) NOT NULL CHECK (jenis IN ('PULANG_CEPAT')),
    kategori VARCHAR(20) NOT NULL DEFAULT 'IZIN',
        -- IZIN | SAKIT | DISPENSASI_KEGIATAN | LAINNYA
    alasan TEXT,
    dibuat_oleh INT NOT NULL REFERENCES guru(id),
    dibuat_pada TIMESTAMP DEFAULT now(),
    UNIQUE (siswa_id, tanggal, jenis)
);
```

**Catatan:** `jenis` sengaja cuma `PULANG_CEPAT` untuk sekarang — MASUK
tidak butuh dispensasi (datang kepagian tidak perlu didokumentasikan,
cukup ditolak & disuruh tunggu). Kalau nanti ada kasus butuh dispensasi
untuk MASUK juga (misal siswa lomba butuh datang lebih pagi dari jam
buka jendela normal), tinggal tambah value di constraint ini.

`UNIQUE (siswa_id, tanggal, jenis)` — 1 siswa cuma bisa punya 1
dispensasi PULANG_CEPAT per hari (kalau guru piket salah input, harus
`PUT` update yang sudah ada, bukan bikin baru).

Model SQLAlchemy di `app/models.py`:
```python
class Dispensasi(Base):
    __tablename__ = "dispensasi"
    __table_args__ = (UniqueConstraint("siswa_id", "tanggal", "jenis"),)

    id = Column(Integer, primary_key=True)
    siswa_id = Column(Integer, ForeignKey("siswa.id"), nullable=False)
    tanggal = Column(Date, nullable=False)
    jenis = Column(String(20), nullable=False, default="PULANG_CEPAT")
    kategori = Column(String(20), nullable=False, default="IZIN")
    alasan = Column(Text)
    dibuat_oleh = Column(Integer, ForeignKey("guru.id"), nullable=False)
    dibuat_pada = Column(DateTime, server_default=func.now())
```

## A.2 Endpoint baru — `app/routers/dispensasi.py`

```python
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Dispensasi, Guru
from app.auth import require_role, get_current_guru

router = APIRouter(prefix="/dispensasi", tags=["dispensasi"])


class DispensasiIn(BaseModel):
    siswa_id: int
    tanggal: date
    jenis: str = "PULANG_CEPAT"
    kategori: str = "IZIN"
    alasan: Optional[str] = None


@router.post("")
def buat_dispensasi(
    body: DispensasiIn,
    db: Session = Depends(get_db),
    guru: Guru = Depends(require_role("admin", "guru_piket")),
):
    existing = db.query(Dispensasi).filter(
        Dispensasi.siswa_id == body.siswa_id,
        Dispensasi.tanggal == body.tanggal,
        Dispensasi.jenis == body.jenis,
    ).first()
    if existing:
        existing.kategori = body.kategori
        existing.alasan = body.alasan
        existing.dibuat_oleh = guru.id
    else:
        db.add(Dispensasi(**body.model_dump(), dibuat_oleh=guru.id))
    db.commit()
    return {"status": "ok"}


@router.get("/aktif")
def list_dispensasi_aktif(
    tanggal: date,
    db: Session = Depends(get_db),
    guru: Guru = Depends(get_current_guru),
):
    """Dipanggil client untuk sinkronisasi cache lokal — semua
    dispensasi yang berlaku untuk tanggal tertentu."""
    rows = db.query(Dispensasi).filter(Dispensasi.tanggal == tanggal).all()
    return [
        {
            "siswa_id": r.siswa_id, "tanggal": str(r.tanggal), "jenis": r.jenis,
            "kategori": r.kategori, "alasan": r.alasan,
        }
        for r in rows
    ]


@router.delete("/{dispensasi_id}")
def batalkan_dispensasi(
    dispensasi_id: int,
    db: Session = Depends(get_db),
    guru: Guru = Depends(require_role("admin", "guru_piket")),
):
    row = db.query(Dispensasi).filter(Dispensasi.id == dispensasi_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Dispensasi tidak ditemukan")
    db.delete(row)
    db.commit()
    return {"status": "dibatalkan"}
```

Daftarkan di `app/main.py`:
```python
from app.routers import dispensasi
app.include_router(dispensasi.router)
```

## A.3 Validasi jendela waktu di `/absensi/sync` (pertahanan berlapis)

Client akan menolak duluan (Bagian B), tapi server **tetap harus
validasi ulang** — prinsip yang sama dengan anti-duplikasi: client bisa
salah/di-modifikasi, server yang jadi wasit akhir. Di
`app/routers/absensi.py`, tambahkan pengecekan sebelum `db.add(row)`:

```python
from datetime import timedelta
from app.models import Dispensasi

BATAS_AWAL_MASUK_JAM = 2

def _validasi_jendela_waktu(db: Session, rec, jadwal_efektif: dict) -> Optional[str]:
    """Return None kalau valid, atau pesan alasan penolakan."""
    jam_masuk = jadwal_efektif["jam_masuk"]
    jam_pulang = jadwal_efektif["jam_pulang"]
    waktu_aktual = rec.jam_aktual.time()

    if rec.type == "MASUK":
        earliest = (datetime.combine(rec.tanggal, jam_masuk) - timedelta(hours=BATAS_AWAL_MASUK_JAM)).time()
        if waktu_aktual < earliest:
            return f"Absen masuk belum dibuka (mulai {earliest.strftime('%H:%M')})"

    if rec.type == "PULANG" and waktu_aktual < jam_pulang:
        ada_dispensasi = db.query(Dispensasi).filter(
            Dispensasi.siswa_id == rec.siswa_id, Dispensasi.tanggal == rec.tanggal,
            Dispensasi.jenis == "PULANG_CEPAT",
        ).first()
        if not ada_dispensasi:
            return f"Belum waktunya pulang (mulai {jam_pulang.strftime('%H:%M')}), tidak ada dispensasi"

    return None
```

Panggil fungsi ini di loop `sync_absensi()`, sebelum insert — kalau
return pesan (bukan None), masukkan ke `hasil` dengan status baru
`"ditolak_kebijakan"` (tambahkan literal ini ke `schemas.py`
`SyncResultItem.status` dan `docs/API_CONTRACT.md`), **jangan** insert
ke database. Ambil `jadwal_efektif` pakai logika yang sama seperti
endpoint `/jadwal/efektif` yang sudah ada (bisa refactor jadi fungsi
bersama `_ambil_jadwal_efektif(db, kelas, tanggal)` dipakai di 2 tempat).

## A.4 Update dokumentasi

- `docs/API_CONTRACT.md` — tambah bagian dispensasi (contoh request/response), dan update tabel status `SyncResultItem` dengan `ditolak_kebijakan`
- `schema.sql` — tambahkan definisi tabel `dispensasi` supaya tetap jadi 1 sumber kebenaran

## A.5 Test

```python
def test_pulang_sebelum_jadwal_ditolak_tanpa_dispensasi(db_session):
    # ... setup siswa, device, jadwal
    hasil = sync_absensi_dengan_record(type="PULANG", jam_aktual="12:00", jam_pulang_standar="15:00")
    assert hasil.status == "ditolak_kebijakan"

def test_pulang_sebelum_jadwal_diterima_dengan_dispensasi(db_session):
    # ... buat dispensasi PULANG_CEPAT untuk siswa & tanggal itu dulu
    hasil = sync_absensi_dengan_record(type="PULANG", jam_aktual="12:00", jam_pulang_standar="15:00")
    assert hasil.status == "disimpan"

def test_masuk_sebelum_jendela_ditolak(db_session):
    hasil = sync_absensi_dengan_record(type="MASUK", jam_aktual="04:00", jam_masuk_standar="07:00")
    assert hasil.status == "ditolak_kebijakan"

def test_masuk_dalam_jendela_2jam_diterima(db_session):
    hasil = sync_absensi_dengan_record(type="MASUK", jam_aktual="05:30", jam_masuk_standar="07:00")
    assert hasil.status == "disimpan"
```

---

# BAGIAN B — Client (`absensi-client-windows`)

## B.1 Tabel cache lokal baru

Tambahkan ke `app/database/schema.sql`:
```sql
CREATE TABLE IF NOT EXISTS dispensasi_cache (
    siswa_id INTEGER NOT NULL,
    tanggal TEXT NOT NULL,
    jenis TEXT NOT NULL,
    kategori TEXT,
    alasan TEXT,
    PRIMARY KEY (siswa_id, tanggal, jenis)
);
```

## B.2 Repository — method baru

Tambahkan ke `app/database/repository.py`:
```python
def replace_dispensasi_cache(self, tanggal: str, entries: list[dict]) -> None:
    self.conn.execute("DELETE FROM dispensasi_cache WHERE tanggal = ?", (tanggal,))
    for e in entries:
        self.conn.execute(
            "INSERT INTO dispensasi_cache (siswa_id, tanggal, jenis, kategori, alasan) VALUES (?, ?, ?, ?, ?)",
            (e["siswa_id"], e["tanggal"], e["jenis"], e.get("kategori"), e.get("alasan")),
        )
    self.conn.commit()

def punya_dispensasi_aktif(self, siswa_id: int, tanggal: str, jenis: str = "PULANG_CEPAT") -> Optional[sqlcipher3.Row]:
    return self.conn.execute(
        "SELECT * FROM dispensasi_cache WHERE siswa_id = ? AND tanggal = ? AND jenis = ?",
        (siswa_id, tanggal, jenis),
    ).fetchone()
```

## B.3 API client — tarik dispensasi

Tambahkan ke `app/api/client.py`:
```python
def tarik_dispensasi_hari_ini(self, tanggal: str) -> list[dict]:
    if not self.service_jwt:
        raise LayananJadwalBelumSiap("GURU_SERVICE_JWT belum dikonfigurasi")
    headers = {"Authorization": f"Bearer {self.service_jwt}"}
    try:
        resp = requests.get(
            f"{self.base_url}/dispensasi/aktif",
            headers=headers, params={"tanggal": tanggal}, timeout=self.timeout,
        )
        resp.raise_for_status()
    except requests.RequestException as e:
        raise KoneksiGagal(str(e)) from e
    return resp.json()
```

## B.4 Sync service — tarik dispensasi tiap siklus

Di `app/sync/service.py`, tambahkan langkah baru (mirip pola jadwal),
setelah bagian tarik jadwal:
```python
try:
    from datetime import date as date_cls
    hari_ini = date_cls.today().isoformat()
    entries = self.api.tarik_dispensasi_hari_ini(hari_ini)
    self.repo.replace_dispensasi_cache(hari_ini, entries)
    ringkasan.dispensasi_diperbarui = len(entries)
except LayananJadwalBelumSiap as e:
    logger.info("Dispensasi tidak di-refresh: %s", e)
except KoneksiGagal as e:
    ringkasan.pesan_error = (ringkasan.pesan_error or "") + f" | Koneksi terputus saat tarik dispensasi: {e}"
```
(Tambahkan `dispensasi_diperbarui: int = 0` ke `RingkasanSiklus`.)

## B.5 Business logic — inti perubahan

Di `app/business/attendance_logic.py`:

```python
from datetime import timedelta

BATAS_AWAL_MASUK_JAM = 2

class HasilAbsen(Enum):
    BERHASIL_MASUK = "berhasil_masuk"
    BERHASIL_PULANG = "berhasil_pulang"
    DITOLAK_SUDAH_ABSEN = "ditolak_sudah_absen"
    DITOLAK_BELUM_WAKTUNYA_MASUK = "ditolak_belum_waktunya_masuk"   # BARU
    DITOLAK_BELUM_WAKTUNYA_PULANG = "ditolak_belum_waktunya_pulang" # BARU


def proses_absen(
    repo: AbsensiRepository, siswa_id: int, device_id: str,
    jam_masuk_standar: time, jam_pulang_standar: time,
    toleransi_menit: int = 5, sekarang: Optional[datetime] = None,
) -> KeputusanAbsen:
    sekarang = sekarang or datetime.now()
    tanggal = sekarang.date().isoformat()
    status = repo.status_hari_ini(siswa_id, tanggal)

    if status == "SELESAI":
        return KeputusanAbsen(hasil=HasilAbsen.DITOLAK_SUDAH_ABSEN, pesan="Masuk & pulang sudah tercatat hari ini")

    type_ = "MASUK" if status == "BELUM_ABSEN" else "PULANG"

    # --- BARU: validasi jendela waktu ---
    if type_ == "MASUK":
        earliest = (datetime.combine(sekarang.date(), jam_masuk_standar) - timedelta(hours=BATAS_AWAL_MASUK_JAM))
        if sekarang < earliest:
            return KeputusanAbsen(
                hasil=HasilAbsen.DITOLAK_BELUM_WAKTUNYA_MASUK,
                pesan=f"Belum waktunya absen masuk (mulai {earliest.strftime('%H:%M')})",
            )

    if type_ == "PULANG" and sekarang.time() < jam_pulang_standar:
        dispensasi = repo.punya_dispensasi_aktif(siswa_id, tanggal, "PULANG_CEPAT")
        if not dispensasi:
            return KeputusanAbsen(
                hasil=HasilAbsen.DITOLAK_BELUM_WAKTUNYA_PULANG,
                pesan=f"Belum waktunya pulang (mulai {jam_pulang_standar.strftime('%H:%M')})",
            )
        # Ada dispensasi -> lanjut simpan, catatan diambil dari alasan dispensasi
        status_otomatis = dispensasi["kategori"] or "IZIN"
        rekaman = repo.simpan_absensi(
            siswa_id=siswa_id, type_=type_, status_kehadiran_otomatis=status_otomatis,
            device_id=device_id, catatan=dispensasi["alasan"], tanggal=tanggal, jam_aktual=sekarang,
        )
        return KeputusanAbsen(hasil=HasilAbsen.BERHASIL_PULANG, rekaman=rekaman, pesan=f"Pulang dengan izin: {status_otomatis}")

    # --- alur normal (tidak berubah) ---
    status_otomatis = _hitung_status_otomatis(sekarang, type_, jam_masuk_standar, jam_pulang_standar, toleransi_menit)
    rekaman = repo.simpan_absensi(
        siswa_id=siswa_id, type_=type_, status_kehadiran_otomatis=status_otomatis,
        device_id=device_id, tanggal=tanggal, jam_aktual=sekarang,
    )
    hasil = HasilAbsen.BERHASIL_MASUK if type_ == "MASUK" else HasilAbsen.BERHASIL_PULANG
    pesan = {"NORMAL": "Tepat waktu", "TERLAMBAT": f"Terlambat · masuk {sekarang.strftime('%H:%M')}",
             "PULANG_CEPAT": f"Pulang cepat · keluar {sekarang.strftime('%H:%M')}"}[status_otomatis]
    return KeputusanAbsen(hasil=hasil, rekaman=rekaman, pesan=pesan)
```

## B.6 UI — tampilkan status penolakan baru

Di `app/ui/kiosk_window.py`, method `_tampilkan_keputusan()`, tambahkan
case untuk 2 hasil baru (pakai warna kuning/warning, bukan merah —
ini bukan pelanggaran, cuma informasi "belum waktunya"):

```python
elif keputusan.hasil in (HasilAbsen.DITOLAK_BELUM_WAKTUNYA_MASUK, HasilAbsen.DITOLAK_BELUM_WAKTUNYA_PULANG):
    self._set_kartu_status(keputusan.pesan, WARNA["warning_teks"], WARNA["warning_bg"])
    self.label_hasil.setText("Belum waktunya")
    self.label_hasil.setStyleSheet(f"font-size: 15px; color: {WARNA['warning_teks']};")
```

## B.7 Test

Tambahkan ke `tests/test_attendance_logic.py`:
```python
def test_masuk_sebelum_jendela_2jam_ditolak(repo):
    keputusan = proses_absen(repo, 1, "dev1", JAM_MASUK, JAM_PULANG, sekarang=datetime(2026, 8, 24, 4, 0))
    assert keputusan.hasil == HasilAbsen.DITOLAK_BELUM_WAKTUNYA_MASUK
    assert repo.status_hari_ini(1, "2026-08-24") == "BELUM_ABSEN"  # tidak ada record tersimpan

def test_masuk_persis_di_jendela_2jam_diterima(repo):
    keputusan = proses_absen(repo, 1, "dev1", JAM_MASUK, JAM_PULANG, sekarang=datetime(2026, 8, 24, 5, 0))
    assert keputusan.hasil == HasilAbsen.BERHASIL_MASUK

def test_pulang_sebelum_jadwal_tanpa_dispensasi_ditolak(repo):
    proses_absen(repo, 1, "dev1", JAM_MASUK, JAM_PULANG, sekarang=datetime(2026, 8, 24, 7, 0))
    keputusan = proses_absen(repo, 1, "dev1", JAM_MASUK, JAM_PULANG, sekarang=datetime(2026, 8, 24, 12, 0))
    assert keputusan.hasil == HasilAbsen.DITOLAK_BELUM_WAKTUNYA_PULANG

def test_pulang_sebelum_jadwal_dengan_dispensasi_diterima(repo):
    proses_absen(repo, 1, "dev1", JAM_MASUK, JAM_PULANG, sekarang=datetime(2026, 8, 24, 7, 0))
    repo.replace_dispensasi_cache("2026-08-24", [
        {"siswa_id": 1, "tanggal": "2026-08-24", "jenis": "PULANG_CEPAT", "kategori": "SAKIT", "alasan": "Demam"}
    ])
    keputusan = proses_absen(repo, 1, "dev1", JAM_MASUK, JAM_PULANG, sekarang=datetime(2026, 8, 24, 12, 0))
    assert keputusan.hasil == HasilAbsen.BERHASIL_PULANG
    assert keputusan.rekaman.status_kehadiran_otomatis == "SAKIT"
```

---

## Definition of Done

- [ ] Server: tabel `dispensasi`, endpoint `POST/GET/DELETE /dispensasi`, validasi jendela waktu di `/absensi/sync` — semua test lulus
- [ ] Client: cache lokal, sync dispensasi tiap siklus, `proses_absen()` menolak sesuai jendela waktu, UI menampilkan pesan penolakan dengan jelas
- [ ] Test manual end-to-end: siswa coba absen masuk jam 4 pagi (jadwal 07:00) → ditolak. Siswa sama coba jam 05:30 → diterima
- [ ] Test manual: siswa coba absen pulang jam 12:00 (jadwal 15:00) tanpa dispensasi → ditolak. Guru piket buat dispensasi lewat `POST /dispensasi`, device sync (atau tunggu siklus), siswa coba lagi → diterima, tercatat sebagai SAKIT/IZIN sesuai kategori
- [ ] Cara guru piket BUAT dispensasi masih lewat Swagger (`/docs`) untuk sekarang — kalau mau lewat UI, itu pekerjaan terpisah (perlu tambah menu di dashboard/panel admin, di luar cakupan prompt ini)
