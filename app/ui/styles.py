"""Palet warna konsisten dengan mockup UI yang sudah disetujui
(kiosk scan screen, dashboard guru piket) — lihat riwayat desain UI/UX.
Prinsip: hijau=berhasil/normal, kuning=terlambat/butuh perhatian ringan,
abu-abu=netral (offline), merah=hanya untuk yang benar-benar perlu
perhatian (bukan dipakai di kiosk sehari-hari)."""

WARNA = {
    "bg": "#0f1115",
    "surface": "#1a1d24",
    "surface_2": "#22262f",
    "border": "#2e333d",
    "teks_utama": "#f0f1f3",
    "teks_sekunder": "#9aa1ac",
    "teks_muted": "#6b7280",

    "sukses_teks": "#4ade80",
    "sukses_bg": "#14291d",
    "sukses_border": "#22c55e",

    "warning_teks": "#fbbf24",
    "warning_bg": "#2e2410",
    "warning_border": "#d97706",

    "bahaya_teks": "#f87171",
    "bahaya_bg": "#2e1414",
    "bahaya_border": "#dc2626",

    "netral_teks": "#9aa1ac",
    "netral_bg": "#20242b",
}

STYLESHEET_DASAR = f"""
QWidget {{
    background-color: {WARNA['bg']};
    color: {WARNA['teks_utama']};
    font-family: 'Segoe UI', sans-serif;
}}
QLabel#namaSiswa {{
    font-size: 26px;
    font-weight: 600;
}}
QLabel#kelasSiswa {{
    font-size: 15px;
    color: {WARNA['teks_sekunder']};
}}
QLabel#jamTampilan {{
    font-size: 13px;
    color: {WARNA['teks_muted']};
}}
"""
