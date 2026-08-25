import os
import numpy as np
import pytest

PATH_MODEL = "models/minifasnet.onnx"

pytestmark = pytest.mark.skipif(
    not os.path.exists(PATH_MODEL),
    reason="Model MiniFASNet tidak ditemukan — lewati di environment tanpa model",
)

def test_model_termuat():
    from app.face.minifasnet_engine import MiniFASNetEngine
    engine = MiniFASNetEngine(PATH_MODEL)
    assert engine.model_version == "minifasnet+arcface-v1"


# --- Test evaluasi_liveness: fungsi MURNI, tidak butuh model asli sama
# sekali, jadi tidak perlu di-skip. Inilah yang seharusnya menangkap
# bug "is_real di-hardcode True" kalau sudah ada sejak awal. ---

from app.face.minifasnet_engine import evaluasi_liveness


def test_skor_tinggi_dianggap_asli():
    output_softmax = np.array([[0.95, 0.03, 0.02]])  # live=0.95 di indeks 0
    is_real, skor = evaluasi_liveness(output_softmax, ambang=0.7, indeks_live=0)
    assert is_real is True
    assert skor == pytest.approx(0.95)


def test_skor_rendah_dianggap_spoofing():
    output_softmax = np.array([[0.10, 0.85, 0.05]])  # live rendah, print-attack tinggi
    is_real, skor = evaluasi_liveness(output_softmax, ambang=0.7, indeks_live=0)
    assert is_real is False
    assert skor == pytest.approx(0.10)


def test_skor_persis_di_ambang_batas_ditolak():
    # Di ambang batas TIDAK lolos (pakai '>' murni, bukan '>=') — sengaja
    # konservatif, mendingan false-reject daripada meloloskan spoof
    output = np.array([[0.7, 0.3]])
    is_real, skor = evaluasi_liveness(output, ambang=0.7, indeks_live=0)
    assert is_real is False


def test_indeks_kelas_bisa_diganti_untuk_kalibrasi_ulang():
    output = np.array([[0.2, 0.9, 0.1]])
    is_real_idx0, _ = evaluasi_liveness(output, ambang=0.7, indeks_live=0)
    is_real_idx1, _ = evaluasi_liveness(output, ambang=0.7, indeks_live=1)
    assert is_real_idx0 is False   # skor di indeks 0 rendah (0.2)
    assert is_real_idx1 is True    # skor di indeks 1 tinggi (0.9)
