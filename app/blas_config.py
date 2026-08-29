"""
Konfigurasi BLAS/threading untuk performa optimal di Windows.

NumPy & onnxruntime di Windows secara default pakai BLAS single-threaded,
yang membuat operasi matmul (mis. cosine distance 1000 embedding) lambat.
Modul ini wajib di-import SEBELUM numpy/onnxruntime pertama kali di-load,
karena threadpool settings hanya berpengaruh saat library tersebut
diinisialisasi.

Dipanggil dari main.py (baris paling atas) dan conftest.py.
"""
import os
import sys

def _setup():
    # Batasi thread per operasi BLAS — di bawah 1 thread NumPy lambat,
    # di atas 4 thread di device gerbang sekolah tidak menambah banyak
    # (single-socket CPU). Biarkan sistem memilih bila jumlah core kecil.
    n_threads = os.environ.get("ABSENSI_NUM_THREADS", "")
    if not n_threads:
        import os as _os
        try:
            n_threads = str(os.cpu_count() or 4)
        except Exception:
            n_threads = "4"
    os.environ.setdefault("OMP_NUM_THREADS", n_threads)
    os.environ.setdefault("OPENBLAS_NUM_THREADS", n_threads)
    os.environ.setdefault("MKL_NUM_THREADS", n_threads)

    # Pastikan threadpoolctl bisa dibaca oleh numpy (blas kontrol di
    # bawah hood memakai library ini kalau tersedia)
    try:
        import threadpoolctl  # noqa: F401
    except ImportError:
        pass

    return n_threads

N_THREADS = _setup()
