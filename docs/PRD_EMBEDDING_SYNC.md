# PRD: Sinkronisasi Status Aktif/Hapus Siswa pada Endpoint Embeddings (`GET /embeddings/sync`)

**Status:** Ready for Implementation
**Tanggal:** 2026-08-29
**Komponen Terkait:** Server (`absensi-server-fase1`) & Client Windows (`client-windows`)

---

## 1. Latar Belakang & Masalah

Saat ini, client kiosk melakukan sinkronisasi embedding wajah berkala melalui **`GET /embeddings/sync`** (dengan parameter opsional `diperbarui_sejak`).

**Masalah:**

1. Server saat ini menggunakan filter `.filter(Siswa.aktif == True)`, sehingga siswa yang dinonaktifkan (`aktif = False`) atau dihapus tidak pernah dikirimkan status terbarunya ke client.
2. Client hanya melakukan `upsert` (tambah/update) data siswa & embedding yang diterima, tanpa mekanisme penghapusan lokal.
3. Akibatnya, siswa yang sudah dihapus/dinonaktifkan di server **tetap tersimpan di SQLite lokal client** dan **masih bisa melakukan absensi wajah** di device kiosk.

---

## 2. Tujuan Produk

1. Memastikan client kiosk menerima informasi status siswa (`aktif: true / false`) dari server.
2. Memungkinkan client menghapus data siswa dan embedding secara otomatis dari cache lokal jika siswa tersebut sudah dinonaktifkan atau dihapus di server.
3. Menjaga integritas absensi agar siswa yang sudah nonaktif/dihapus tidak dapat melakukan absensi di device offline-first.

---

## 3. Kebutuhan Fungsional (Server)

| ID    | Kebutuhan                                                                                                                                                                                                                                                                |
| ----- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| SRV-1 | Modifikasi query pada `GET /embeddings/sync` (`app/routers/embeddings.py`) agar **tidak memfilter secara kaku** `Siswa.aktif == True`, melainkan menyertakan siswa yang mengalami pembaruan (termasuk yang `aktif = False` jika `diperbarui_pada` > `diperbarui_sejak`). |
| SRV-2 | Tambahkan field boolean **`aktif`** pada setiap item data siswa di dalam payload respons `GET /embeddings/sync`.                                                                                                                                                         |

### Contoh Payload Respons Baru:

```json
{
  "server_time": "2026-08-29T12:00:00Z",
  "jumlah": 2,
  "data": [
    {
      "siswa_id": 12,
      "nis": "12345",
      "nama": "Ahmad",
      "kelas": "XI",
      "aktif": true,
      "embedding_encrypted": "...",
      "model_version": "minifasnet-v1",
      "diperbarui_pada": "2026-08-29T10:00:00Z"
    },
    {
      "siswa_id": 15,
      "nis": "12346",
      "nama": "Budi",
      "kelas": "XII",
      "aktif": false,
      "embedding_encrypted": "...",
      "model_version": "minifasnet-v1",
      "diperbarui_pada": "2026-08-29T11:30:00Z"
    }
  ]
}
```

---

## 4. Kebutuhan Fungsional (Client — Referensi untuk Implementasi Nanti)

| ID    | Kebutuhan                                                                                                |
| ----- | -------------------------------------------------------------------------------------------------------- |
| CLI-1 | Membaca field `aktif` dari item sync embedding.                                                          |
| CLI-2 | Jika `aktif == false`: Hapus data dari tabel `siswa_cache` dan `embedding_cache` berdasarkan `siswa_id`. |
| CLI-3 | Jika `aktif == true`: Lakukan `upsert` seperti biasa ke `siswa_cache` dan `embedding_cache`.             |

---

## 5. Rencana Pengujian (Acceptance Criteria)

1. **Admin menonaktifkan siswa X di server.**
2. **Client melakukan siklus sync berkala.**
3. **Hasil:**
   - Data siswa X hilang dari tabel `siswa_cache` dan `embedding_cache` di database lokal client.
   - Siswa X tidak lagi terdeteksi/bisa absen di kamera kiosk.
