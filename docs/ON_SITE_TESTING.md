# 📋 On-Site Testing Guide (REQ-LIVENESS-003 & REQ-EMBEDDING-004)

Panduan testing di lapangan (gerbang sekolah) sebelum pilot 50+ siswa.

> **⚠️ Gate Otomatis (REQ-TEST-001):**
> Aplikasi terinstall dengan `ON_SITE_TESTING_SELESAI=false` di `.env`.
> Selama masih `false`, aplikasi berjalan dalam **MODE TESTING**:
>
> - Banner "MODE TESTING" tampil di kiosk
> - Hasil scan wajah **TIDAK disimpan** ke DB (hanya simulasi)
>
> Setelah testing selesai & lolos, ubah `.env`:
>
> ```
> ON_SITE_TESTING_SELESAI=true
> ```
>
> Lalu restart aplikasi. Ini memastikan device tidak dipakai reguler
> sebelum liveness & embedding diverifikasi di lapangan.

---

## 1. Persiapan Sebelum Testing

### Equipment yang Harus Dibawa

- [ ] Laptop/PC dengan aplikasi kiosk terinstall
- [ ] Webcam USB (minimal 2 model untuk komparasi)
- [ ] Kabel power (laptop harus menyala sepanjang testing)
- [ ] Kertas A4 + printer (untuk cetak foto spoofing)
- [ ] HP dengan video wajah (untuk testing replay attack)
- [ ] Lampu senter (untuk testing backlight)

### Struktur Folder Hasil Testing

```
data/on_site_testing/
├── gerbang_YYYY-MM-DD.csv           # Log scan siswa
├── liveness_scores_YYYY-MM-DD.csv   # Skor liveness per frame
├── photos/                          # Foto calibration (opsional)
│   ├── real/
│   └── spoof/
└── embedding_results.csv            # Hasil embedding matching
```

### Template CSV: `gerbang_YYYY-MM-DD.csv`

```csv
timestamp,siswa_id,nama,scan_type,status_kehadiran,liveness_score,liveness_passed,distance,matched_correct,lighting_condition,webcam_model,notes
2026-09-15 07:01:23,1001,Budi Santoso,MASUK,HADIR,0.892,true,0.234,true,natural_outdoor,Logitech C920,
2026-09-15 07:02:45,1002,Siti Aisyah,MASUK,TERLAMBAT,0.845,true,0.312,true,natural_outdoor,Logitech C920,
```

### Template CSV: `embedding_results.csv`

```csv
timestamp,actual_siswa_id,matched_siswa_id,distance,liveness_score,liveness_passed,scan_type,lighting_condition,webcam_model
2026-09-15 07:01:23,1001,1001,0.234,0.892,true,real,natural_outdoor,Logitech C920
2026-09-15 07:02:45,1002,1002,0.312,0.845,true,real,natural_outdoor,Logitech C920
```

---

## 2. Testing Sessions (3 Sesi)

### Sesi 1: Pagi (07:00 - 08:00)

- **Kondisi Pencahayaan:** Natural outdoor light (matahari pagi)
- **Target:** 20 siswa scan wajah
- **Catatan:** Rekam kondisi cahaya (terang/sedang/redup)

### Sesi 2: Siang (11:00 - 12:00)

- **Kondisi Pencahayaan:** Outdoor backlight (matahari di belakang siswa)
- **Target:** 20 siswa scan wajah
- **Catatan:** Perhatikan bayangan di wajah

### Sesi 3: Sore (14:00 - 15:00)

- **Kondisi Pencahayaan:** Indoor artificial light (lampu ruangan)
- **Target:** 20 siswa scan wajah
- **Catatan:** Kombinasi cahaya lampu + sisa matahari

---

## 3. Testing Anti-Spoofing (Liveness)

### Skenario Spoofing yang Harus Dites

1. **Foto Print 4x6"**: Cetak foto siswa, pegang di depan kamera
2. **Video Replay**: Putar video wajah siswa di HP, arahkan ke kamera
3. **Foto di Layar HP**: Tampilkan foto di layar HP, arahkan ke kamera
4. **Topeng/Masker**: Gunakan topeng wajah (jika tersedia)

### Template CSV: `liveness_scores_YYYY-MM-DD.csv`

```csv
timestamp,frame_id,is_real,liveness_score,ambang_saat_itu,attack_type,success_blocked
2026-09-15 07:15:00,1,1,0.892,0.752,real_face,false
2026-09-15 07:15:01,2,0,0.123,0.752,photo_print,true
2026-09-15 07:15:02,3,0,0.234,0.752,video_replay,true
```

---

## 4. Analisis Hasil

### Hitung Threshold Optimal

```bash
python scripts/kalibrasi_ambang_batas.py --data data/on_site_testing/embedding_results.csv
```

### Hitung Liveness Metrics

```python
from scripts.kalibrasi_ambang_batas import analisis_results
analisis_results("data/on_site_testing/embedding_results.csv")
```

### Target Metrics

| Metrik               | Target | Actual  |
| -------------------- | ------ | ------- |
| Accuracy (Matching)  | ≥ 95%  | \_\_\_% |
| TPR (Live Detection) | ≥ 98%  | \_\_\_% |
| FPR (Spoof Block)    | ≤ 0.5% | \_\_\_% |
| FRR (False Reject)   | ≤ 2%   | \_\_\_% |

---

## 5. Dokumentasi Temuan

Setelah testing selesai, buat laporan di `docs/CALIBRATION_REPORT.md`:

- Threshold yang dipilih + justifikasi
- Confusion matrix
- ROC curve (jika ada data cukup)
- Rekomendasi untuk pilot
