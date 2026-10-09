import cv2
import numpy as np
import pytest

from dynamo_figures.blur_faces import detectors
from dynamo_figures.blur_faces.detectors import (MODEL_PATH, OnnxDetector, OpenCVDetector,
                                                 create_detector, gpu_provider)

# faces.jpg holds four clear faces: left edge (x~110) x2 and right edge (x~720) x2
EXPECTED_FACES = 4


@pytest.fixture
def faces(faces_image):
    return cv2.imread(faces_image)


def centers(dets):
    return sorted((round(float(x + w / 2)), round(float(y + h / 2))) for x, y, w, h, _ in dets)


class TestCreateDetector:
    def test_rejects_unknown_device(self):
        with pytest.raises(ValueError, match="device"):
            create_detector("tpu", 0.6, 0.3)

    def test_missing_model(self, monkeypatch, tmp_path):
        monkeypatch.setattr(detectors, "MODEL_PATH", tmp_path / "gone.onnx")
        with pytest.raises(FileNotFoundError):
            create_detector("cpu", 0.6, 0.3)

    def test_cpu_uses_opencv(self):
        assert isinstance(create_detector("cpu", 0.6, 0.3), OpenCVDetector)

    def test_auto_without_gpu_falls_back_to_cpu(self, monkeypatch):
        monkeypatch.setattr(detectors, "gpu_provider", lambda: None)
        assert isinstance(create_detector("auto", 0.6, 0.3), OpenCVDetector)

    def test_gpu_without_provider_warns_and_uses_cpu(self, monkeypatch, capsys):
        monkeypatch.setattr(detectors, "gpu_provider", lambda: None)
        assert isinstance(create_detector("gpu", 0.6, 0.3), OpenCVDetector)
        assert "no GPU provider" in capsys.readouterr().out

    def test_cpu_never_probes_for_gpu(self, monkeypatch):
        def boom():
            raise AssertionError("probed")
        monkeypatch.setattr(detectors, "gpu_provider", boom)
        create_detector("cpu", 0.6, 0.3)


class TestGpuProvider:
    def test_without_onnxruntime(self, monkeypatch):
        import sys
        monkeypatch.setitem(sys.modules, "onnxruntime", None)
        assert gpu_provider() is None

    def test_picks_first_known_provider(self, monkeypatch):
        import sys, types
        fake = types.SimpleNamespace(
            get_available_providers=lambda: ["CPUExecutionProvider", "CoreMLExecutionProvider"])
        monkeypatch.setitem(sys.modules, "onnxruntime", fake)
        assert gpu_provider() == "CoreMLExecutionProvider"

    def test_cpu_only_runtime(self, monkeypatch):
        import sys, types
        fake = types.SimpleNamespace(get_available_providers=lambda: ["CPUExecutionProvider"])
        monkeypatch.setitem(sys.modules, "onnxruntime", fake)
        assert gpu_provider() is None


def test_model_file_present():
    assert MODEL_PATH.is_file() and MODEL_PATH.stat().st_size > 10_000


class TestOpenCVDetector:
    def test_finds_all_faces_in_photo(self, faces):
        dets = OpenCVDetector(0.6, 0.3).detect_batch([faces])[0]
        assert len(dets) == EXPECTED_FACES
        for x, y, w, h, score in dets:
            assert w > 50 and h > 50 and 0.6 <= score <= 1.0
        # two faces on the left edge, two on the right
        xs = [cx for cx, _ in centers(dets)]
        assert sum(cx < 400 for cx in xs) == 2 and sum(cx > 600 for cx in xs) == 2

    def test_blank_image_has_no_faces(self):
        assert OpenCVDetector(0.6, 0.3).detect_batch([np.full((120, 160, 3), 128, np.uint8)]) == [[]]

    def test_high_threshold_finds_fewer(self, faces):
        strict = OpenCVDetector(0.99, 0.3).detect_batch([faces])[0]
        assert len(strict) < EXPECTED_FACES

    def test_batch_returns_one_list_per_image(self, faces):
        out = OpenCVDetector(0.6, 0.3).detect_batch([faces, faces, faces])
        assert [len(d) for d in out] == [EXPECTED_FACES] * 3

    def test_threaded_executor_matches_serial(self, faces):
        from concurrent.futures import ThreadPoolExecutor
        serial = OpenCVDetector(0.6, 0.3).detect_batch([faces, faces])
        det = OpenCVDetector(0.6, 0.3)
        with ThreadPoolExecutor(2) as ex:
            det.executor = ex
            threaded = det.detect_batch([faces, faces])
        assert centers(threaded[0]) == centers(serial[0]) == centers(threaded[1])


class TestOnnxDetector:
    @pytest.fixture
    def det(self):
        pytest.importorskip("onnxruntime")
        return OnnxDetector(0.6, 0.3, "CPUExecutionProvider")

    def test_name_reflects_provider(self, det):
        assert "CPU" in det.name and det.batched

    def test_matches_opencv_detections(self, det, faces):
        onnx = det.detect_batch([faces])[0]
        cv = OpenCVDetector(0.6, 0.3).detect_batch([faces])[0]
        assert len(onnx) == len(cv) == EXPECTED_FACES
        for (ox, oy), (cx, cy) in zip(centers(onnx), centers(cv)):
            assert abs(ox - cx) < 15 and abs(oy - cy) < 15

    def test_batch_of_two(self, det, faces):
        out = det.detect_batch([faces, faces])
        assert [len(d) for d in out] == [EXPECTED_FACES] * 2

    def test_blank_image(self, det):
        assert det.detect_batch([np.full((64, 64, 3), 100, np.uint8)]) == [[]]

    def test_grid_sizes(self, det):
        grids = det._grid(64, 96)
        assert [len(c) for c, _, _ in grids] == [8 * 12, 4 * 6, 2 * 3]
        assert [s for _, _, s in grids] == [8, 16, 32]

    def test_preprocess_pads_to_multiple_of_32(self, det):
        img = np.full((40, 50, 3), 7, np.uint8)
        blob = det._preprocess([img])
        assert blob.shape == (1, 3, 64, 64) and blob.dtype == np.float32
        assert blob[0, 0, :40, :50].min() == 7 and blob[0, 0, 40:, :].max() == 0

    def test_nms_merges_duplicates(self, det):
        faces = [(10, 10, 50, 50, 0.9), (12, 11, 50, 50, 0.8), (200, 200, 50, 50, 0.95)]
        assert len(det._nms(faces)) == 2
        assert det._nms([]) == []
