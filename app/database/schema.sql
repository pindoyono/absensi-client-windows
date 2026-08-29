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

-- Override jadwal yang dibuat DI DEVICE (offline-first, Opsi C).
-- Saat online, baris ini di-push ke server (POST /jadwal/override) lalu
-- ditandai terkirim=1. Kadaluarsa otomatis: baris dengan tanggal < hari ini
-- dibersihkan (lihat repository.buang_jadwal_lokal_kadaluarsa).
CREATE TABLE IF NOT EXISTS jadwal_override_lokal (
    id TEXT PRIMARY KEY, -- UUID, idempotency key untuk push ke server
    tanggal TEXT NOT NULL,
    kelas TEXT, -- NULL = berlaku semua kelas
    jam_masuk TEXT NOT NULL,
    jam_pulang TEXT NOT NULL,
    alasan TEXT,
    dibuat_pada TEXT NOT NULL,
    terkirim INTEGER NOT NULL DEFAULT 0, -- 1 = tidak perlu push lagi (ok ATAU ditolak permanen)
    status_push TEXT NOT NULL DEFAULT 'pending', -- 'pending' | 'ok' | 'ditolak'
    pesan_push TEXT -- pesan error kalau status 'ditolak'
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

-- ============================================================
-- OPS-001: Audit Log Table — track semua actions untuk compliance
-- ============================================================
CREATE TABLE IF NOT EXISTS device_audit_log (
    log_id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL, -- ISO 8601 format
    event_type TEXT NOT NULL, -- LOGIN, LOGOUT, ENROLLMENT, SYNC_START, SYNC_COMPLETE, SYNC_FAIL, ATTENDANCE_RECORD, CONFIG_CHANGE, ERROR
    actor TEXT, -- email (untuk OAuth) atau 'system'
    action TEXT NOT NULL, -- deskripsi action
    details TEXT, -- JSON string dengan extra details
    status TEXT NOT NULL, -- 'success', 'failed'
    error_message TEXT, -- jika ada error
    device_id TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON device_audit_log (timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_audit_event_type ON device_audit_log (event_type);

-- ============================================================
-- LIVENESS-004: Liveness Log Table — track setiap liveness check
-- ============================================================
CREATE TABLE IF NOT EXISTS liveness_log (
    log_id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL, -- ISO 8601 format
    frame_id TEXT, -- unique frame identifier (untuk debugging)
    wajah_terdeteksi INTEGER NOT NULL, -- 0 atau 1
    is_real INTEGER, -- 0=fake, 1=real (NULL jika wajah tidak terdeteksi)
    liveness_score REAL, -- skor liveness dari model
    ambang_saat_itu REAL NOT NULL, -- AMBANG_LIVENESS yang dipakai saat itu
    alasan_gagal TEXT, -- error message jika ada
    siswa_id INTEGER, -- jika matching berhasil, NULL kalau gagal
    device_id TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_liveness_timestamp ON liveness_log (timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_liveness_wajah_terdeteksi ON liveness_log (wajah_terdeteksi);

-- ============================================================
-- OPS-002: Sync Event Log — track setiap sync cycle
-- ============================================================
CREATE TABLE IF NOT EXISTS sync_event_log (
    log_id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL, -- waktu sync dimulai
    duration_ms INTEGER, -- durasi sync dalam milliseconds
    status TEXT NOT NULL, -- 'success', 'partial', 'failed'
    batch_count INTEGER, -- jumlah records di-sync
    success_count INTEGER, -- jumlah berhasil
    duplicate_count INTEGER, -- jumlah duplikat
    fail_count INTEGER, -- jumlah gagal
    error_message TEXT, -- error message jika ada
    device_id TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_sync_event_timestamp ON sync_event_log (timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_sync_event_status ON sync_event_log (status);