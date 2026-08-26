-- ============================================================
-- Skema Database Lokal Client Windows (SQLite via SQLCipher)
-- ============================================================
-- Prinsip: skema ini sengaja LEBIH SEDERHANA dari server (tidak ada
-- semua kolom audit dsb) — cukup yang dibutuhkan untuk validasi
-- offline dan antrian sync. Sumber kebenaran tetap server.

-- Cache data siswa (ditarik dari server, read-only di sisi client
-- kecuali kolom yang memang diisi lokal)
CREATE TABLE IF NOT EXISTS siswa_cache (
    siswa_id INTEGER PRIMARY KEY,
    nis TEXT NOT NULL,
    nama TEXT NOT NULL,
    kelas TEXT NOT NULL
);

-- Cache embedding wajah (terenkripsi, ditarik dari server)
CREATE TABLE IF NOT EXISTS embedding_cache (
    siswa_id INTEGER PRIMARY KEY REFERENCES siswa_cache (siswa_id),
    embedding_encrypted BLOB NOT NULL,
    model_version TEXT NOT NULL,
    diperbarui_pada TEXT NOT NULL
);

-- Cache jadwal efektif per kelas (ditarik dari server secara berkala)
CREATE TABLE IF NOT EXISTS jadwal_cache (
    kelas TEXT, -- NULL = berlaku semua kelas
    tanggal TEXT, -- diisi kalau sumbernya override; NULL kalau standar
    hari TEXT, -- diisi kalau sumbernya standar; NULL kalau override
    jam_masuk TEXT NOT NULL,
    jam_pulang TEXT NOT NULL,
    sumber TEXT NOT NULL, -- 'standar' | 'override'
    ditarik_pada TEXT NOT NULL
);

-- Absensi yang tercatat DI DEVICE INI — ini yang jadi antrian sync.
-- record_id dibuat di client (UUID), inilah idempotency key ke server.

CREATE TABLE IF NOT EXISTS absensi_lokal (
    record_id TEXT PRIMARY KEY,
    siswa_id INTEGER NOT NULL,
    tanggal TEXT NOT NULL,
    type TEXT NOT NULL CHECK (type IN ('MASUK','PULANG')),
    jam_aktual TEXT NOT NULL,
    status_kehadiran_otomatis TEXT NOT NULL DEFAULT 'NORMAL',
    catatan TEXT,
    device_id TEXT NOT NULL,

    synced INTEGER NOT NULL DEFAULT 0,     -- 0=belum, 1=sudah (disimpan ATAU duplikat_diabaikan)
    sync_status TEXT,                       -- 'disimpan' | 'duplikat_diabaikan' | NULL (belum dicoba)
    percobaan_sync INTEGER NOT NULL DEFAULT 0,
    dibuat_pada TEXT NOT NULL,

-- Jaring pengaman LOKAL — cermin dari constraint server. Ini yang
-- membuat validasi "sudah absen atau belum" bisa dicek instan dari
-- SQLite tanpa perlu tanya server dulu (lihat app/business/attendance_logic.py)
UNIQUE (siswa_id, tanggal, type) );

CREATE INDEX IF NOT EXISTS idx_absensi_lokal_belum_sync ON absensi_lokal (synced)
WHERE
    synced = 0;

CREATE INDEX IF NOT EXISTS idx_absensi_lokal_siswa_tanggal ON absensi_lokal (siswa_id, tanggal);

-- Metadata sync — dipakai untuk parameter `diperbarui_sejak` saat
-- menarik ulang embedding/jadwal, supaya tidak transfer ulang semua
-- data tiap kali (lihat docs/API_CONTRACT.md bagian 3)
CREATE TABLE IF NOT EXISTS sync_metadata (
    kunci TEXT PRIMARY KEY,
    nilai TEXT
);

-- Cache dispensasi aktif (ditarik dari server per tanggal)
CREATE TABLE IF NOT EXISTS dispensasi_cache (
    siswa_id INTEGER NOT NULL,
    tanggal TEXT NOT NULL,
    jenis TEXT NOT NULL,
    kategori TEXT,
    alasan TEXT,
    PRIMARY KEY (siswa_id, tanggal, jenis)
);