# 📊 Calibration Report (REQ-DOC-002)

Laporan kalibrasi threshold liveness dan embedding matching.

---

## 1. Liveness Detection Calibration

### Threshold Saat Ini

- **AMBANG_LIVENESS:** 0.752
- **Target TPR:** ≥ 98%
- **Target FPR:** ≤ 0.5%

### Dataset Kalibrasi

- **Jumlah Sampel:** 40 (20 real + 20 spoofing)
- **Sumber:** Placeholder (belum ada data real dari lapangan)
- **Status:** ⚠️ Menunggu data testing lapangan

### Hasil Analisis (Template)

| Metrik                    | Target | Actual | Status |
| ------------------------- | ------ | ------ | ------ |
| TPR (True Positive Rate)  | ≥ 98%  | \_\_%  | ⏳     |
| FPR (False Positive Rate) | ≤ 0.5% | \_\_%  | ⏳     |
| FRR (False Reject Rate)   | ≤ 2%   | \_\_%  | ⏳     |

### Confusion Matrix (Template)

```
                    Predicted
                    Real    Fake
Actual Real     [ TP=?  ] [ FN=? ]
Actual Fake     [ FP=?  ] [ TN=? ]
```

### ROC Curve

_Menunggu data testing lapangan untuk generate ROC curve._

---

## 2. Embedding Matching Calibration

### Threshold Saat Ini

- **AMBANG_BATAS_JARAK:** 0.3542
- **Target FAR:** ≤ 0.5%
- **Target FRR:** ≤ 2%

### Dataset Kalibrasi

- **Jumlah Siswa:** 30
- **Foto per Siswa:** 5-10 (berbagai sudut, pencahayaan)
- **Total Sampel:** 150+
- **Status:** ⚠️ Menunggu data testing lapangan

### Hasil Analisis (Template)

| Metrik                  | Target | Actual | Status |
| ----------------------- | ------ | ------ | ------ |
| FAR (False Accept Rate) | ≤ 0.5% | \_\_%  | ⏳     |
| FRR (False Reject Rate) | ≤ 2%   | \_\_%  | ⏳     |
| Akurasi Overall         | ≥ 95%  | \_\_%  | ⏳     |

### Distance Distribution

_Menunggu data testing lapangan untuk generate histogram._

### ROC Curve

_Menunggu data testing lapangan untuk generate ROC curve._

---

## 3. Rekomendasi untuk Pilot

### Kondisi yang Bekerja Baik

- _(Menunggu hasil testing lapangan)_

### Kondisi yang Perlu Perhatian

- _(Menunggu hasil testing lapangan)_

### Threshold yang Direkomendasikan

| Parameter | Threshold Saat Ini | Threshold Baru | Justifikasi       |
| --------- | ------------------ | -------------- | ----------------- |
| Liveness  | 0.752              | \_\_           | _(Menunggu data)_ |
| Embedding | 0.3542             | \_\_           | _(Menunggu data)_ |

---

## 4. Catatan Penting

1. **Sebelum pilot wajib:** Lakukan testing lapangan (lihat `docs/ON_SITE_TESTING.md`)
2. **Update threshold:** Jika threshold berubah, update di:
   - `app/face/minifasnet_engine.py` (AMBANG_LIVENESS)
   - `app/face/matcher.py` (AMBANG_BATAS_JARAK)
3. **Re-run tests:** `pytest tests/ -v` setelah update threshold
4. **Dokumentasi:** Update laporan ini dengan hasil aktual

---

_Dokumen ini akan diupdate setelah testing lapangan selesai._
