import cv2
import numpy as np
import pytest

from tests.conftest import write_video

FACE_VIDEO_FRAMES = 20
FACE_VIDEO_FPS = 10


@pytest.fixture(scope="session")
def faces_video(tmp_path_factory, request):
    """2 s clip made from faces.jpg (shrunk), nudged each frame so it is a real video."""
    from tests.conftest import DATA_DIR
    base = cv2.resize(cv2.imread(str(DATA_DIR / "faces.jpg")), (562, 360))
    frames = [np.roll(base, i, axis=1) for i in range(FACE_VIDEO_FRAMES)]
    path = tmp_path_factory.mktemp("facevideo") / "faces.mp4"
    return str(write_video(path, frames, fps=FACE_VIDEO_FPS))


class StubDetector:
    """Detector double: returns whatever `fn(image)` says, and records its calls."""
    batched = False
    name = "stub"

    def __init__(self, fn=lambda image: []):
        self.fn = fn
        self.executor = None
        self.calls = []  # list of batch sizes

    def detect_batch(self, images):
        self.calls.append([im.shape for im in images])
        return [self.fn(im) for im in images]


@pytest.fixture
def stub_detector():
    return StubDetector
