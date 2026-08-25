import os
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
