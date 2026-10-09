import cv2
import numpy as np
import pytest

from dynamo_figures.blur_faces import core, video_io
from dynamo_figures.blur_faces.core import FaceBlur
from dynamo_figures.blur_faces.detectors import OpenCVDetector
from tests.blur_faces.conftest import FACE_VIDEO_FPS, FACE_VIDEO_FRAMES, StubDetector
from tests.conftest import (VIDEO_FRAMES, VIDEO_H, VIDEO_W, requires_ffmpeg, square_origin)


def fb(detector=None, **kw):
    kw.setdefault("device", "cpu")
    kw.setdefault("disable_pbar", True)
    blur = FaceBlur(**kw)
    if detector is not None:
        blur.detector = detector
    return blur


def frame_count(path):
    cap = cv2.VideoCapture(path)
    n = 0
    while cap.read()[0]:
        n += 1
    cap.release()
    return n


def bright_square_finder(image):
    """Stub 'face detection': a 2 px wide strip on the white square's left edge.

    The strip is narrow on purpose: a box detected on a neighbouring frame is
    off by >= 1 px and would miss it, so a mix-up in frame order shows up.
    """
    ys, xs = np.where(image.min(axis=2) > 200)
    if not len(xs):
        return []
    return [(float(xs.min()), float(ys.min()), 2.0, float(ys.max() - ys.min() + 1), 0.99)]


class TestInit:
    def test_defaults_build_cpu_pipeline(self):
        blur = fb()
        assert isinstance(blur.detector, OpenCVDetector)
        assert blur.device_name == "OpenCV (CPU)"

    def test_class_constants(self):
        assert FaceBlur.STYLES == ("blur", "pixelate", "fill")
        assert FaceBlur.SHAPES == ("ellipse", "rect")
        assert FaceBlur.DEVICES == ("auto", "gpu", "cpu")

    @pytest.mark.parametrize("kw", [dict(style="x"), dict(shape="x"), dict(device="x"), dict(smoothing=1)])
    def test_invalid_options(self, kw):
        with pytest.raises(ValueError):
            FaceBlur(**kw)

    def test_batch_size_floor_and_workers_default(self):
        blur = fb(batch_size=0)
        assert blur.batch_size == 1 and blur.workers >= 1
        assert fb(workers=3).workers == 3


class TestDetect:
    def test_real_detector_finds_faces(self, faces_image):
        faces = fb().detect(cv2.imread(faces_image))
        assert len(faces) == 4

    def test_downscaled_detection_maps_back_to_original_coordinates(self):
        seen = []
        def fn(image):
            seen.append(image.shape[:2])
            return [(10.0, 20.0, 30.0, 40.0, 0.9)]
        blur = fb(StubDetector(fn), detect_max_dim=100)
        out = blur.detect(np.zeros((200, 400, 3), np.uint8))
        assert seen == [(50, 100)]  # longest side shrunk to 100
        assert out == [(40.0, 80.0, 120.0, 160.0, 0.9)]

    def test_no_downscale_when_small_or_disabled(self):
        stub = StubDetector()
        blur = fb(stub, detect_max_dim=500)
        blur.detect(np.zeros((200, 400, 3), np.uint8))
        fb(stub, detect_max_dim=0).detect(np.zeros((2000, 4000, 3), np.uint8))
        assert stub.calls == [[(200, 400, 3)], [(2000, 4000, 3)]]

    def test_batched_detector_gets_padded_partial_batches(self):
        stub = StubDetector(lambda im: [(1.0, 1.0, 5.0, 5.0, 0.9)])
        stub.batched = True
        blur = fb(stub, batch_size=4)
        imgs = [np.zeros((32, 32, 3), np.uint8)] * 3
        out = blur.detect_batch(imgs)
        assert len(stub.calls[0]) == 4  # padded so the GPU session shape is reused
        assert len(out) == 3

    def test_single_image_is_not_padded(self):
        stub = StubDetector()
        stub.batched = True
        fb(stub, batch_size=4).detect(np.zeros((32, 32, 3), np.uint8))
        assert len(stub.calls[0]) == 1


class TestProcessImage:
    def test_blurs_only_faces(self, faces_image, tmp_path):
        out = str(tmp_path / "out.jpg")
        assert fb(style="fill", fill_color="#00ff00", shape="rect").process_image(faces_image, out)
        before, after = cv2.imread(faces_image), cv2.imread(out)
        assert after.shape == before.shape
        changed = np.any(np.abs(after.astype(int) - before.astype(int)) > 40, axis=2)
        assert 0.02 < changed.mean() < 0.5
        # the strip between the left and right faces has none, so it is only recompressed
        assert changed[:, 400:600].mean() < 0.02

    @pytest.mark.parametrize("style", ["blur", "pixelate", "fill"])
    def test_every_style_changes_each_face(self, faces_image, tmp_path, style):
        blur = fb(style=style)
        img = cv2.imread(faces_image)
        faces = blur.detect(img)
        out = blur.apply(img, faces)
        for x, y, w, h, _ in faces:
            cx, cy = int(x + w / 2), int(y + h / 2)
            assert not np.array_equal(out[cy - 10:cy + 10, cx - 10:cx + 10],
                                      img[cy - 10:cy + 10, cx - 10:cx + 10])

    def test_blank_image_is_unchanged(self, blank_image, tmp_path):
        out = str(tmp_path / "out.png")
        assert fb().process_image(blank_image, out)
        assert np.array_equal(cv2.imread(out), cv2.imread(blank_image))

    def test_creates_output_directory(self, blank_image, tmp_path):
        out = tmp_path / "a" / "b" / "out.png"
        assert fb().process_image(blank_image, str(out))
        assert out.is_file()

    def test_unreadable_input(self, tmp_path, capsys):
        assert not fb().process_image(str(tmp_path / "nope.png"), str(tmp_path / "o.png"))
        assert "Could not read image" in capsys.readouterr().out

    def test_draw_boxes_mode(self, faces_image, tmp_path):
        out = str(tmp_path / "o.png")
        fb(draw_boxes=True).process_image(faces_image, out)
        green = np.all(cv2.imread(out) == (0, 255, 0), axis=2)
        assert green.any()


class TestProcessVideoValidation:
    @pytest.mark.parametrize("kw", [dict(start_t=-1), dict(start_t=2, end_t=1), dict(start_t=1, end_t=1)])
    def test_bad_times(self, synthetic_video, tmp_path, kw, capsys):
        out = tmp_path / "o.mp4"
        assert not fb().process_video(synthetic_video, str(out), **kw)
        assert "Error" in capsys.readouterr().out and not out.exists()

    def test_missing_input(self, tmp_path):
        assert not fb().process_video(str(tmp_path / "nope.mp4"), str(tmp_path / "o.mp4"))

    def test_start_past_end_of_video(self, synthetic_video, tmp_path):
        assert not fb().process_video(synthetic_video, str(tmp_path / "o.mp4"), start_t=60)

    def test_unwritable_output(self, synthetic_video, tmp_path, monkeypatch):
        monkeypatch.setattr(video_io.shutil, "which", lambda n: None)
        def bad_writer(*a, **k):
            raise IOError("nope")
        monkeypatch.setattr(core, "open_writer", bad_writer)
        assert not fb().process_video(synthetic_video, str(tmp_path / "o.mp4"))


@pytest.fixture(params=["opencv-writer", pytest.param("ffmpeg", marks=requires_ffmpeg)])
def writer_backend(request, monkeypatch):
    if request.param == "opencv-writer":
        monkeypatch.setattr(video_io.shutil, "which", lambda n: None)
    return request.param


class RecordingWriter:
    """Writer double that keeps frames in memory, so tests see pixels without codec loss."""

    def __init__(self):
        self.frames = []

    def write(self, frame):
        self.frames.append(frame.copy())

    def close(self):
        return True


@pytest.fixture
def recording_writer(monkeypatch):
    writer = RecordingWriter()
    monkeypatch.setattr(core, "open_writer", lambda *a, **k: writer)
    return writer


class TestProcessVideo:
    def run(self, video, tmp_path, detector=None, **kw):
        out = str(tmp_path / "out.mp4")
        process_kw = {k: kw.pop(k) for k in ("start_t", "end_t", "keep_audio") if k in kw}
        assert fb(detector, **kw).process_video(video, out, **process_kw)
        return out

    def test_frame_count_and_size_preserved(self, synthetic_video, tmp_path, writer_backend):
        out = self.run(synthetic_video, tmp_path)
        assert frame_count(out) == VIDEO_FRAMES
        cap = cv2.VideoCapture(out)
        assert (int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))) \
            == (VIDEO_W, VIDEO_H)

    def test_faces_are_obscured_in_every_frame(self, faces_video, tmp_path, writer_backend):
        out = self.run(faces_video, tmp_path, style="fill", fill_color="#00ff00", shape="rect",
                       smoothing=0)
        src, dst = cv2.VideoCapture(faces_video), cv2.VideoCapture(out)
        n = 0
        while True:
            ok1, a = src.read()
            ok2, b = dst.read()
            if not ok1 or not ok2:
                break
            n += 1
            green = np.all(np.abs(b.astype(int) - (0, 255, 0)) < 60, axis=2)  # tolerant of codec loss
            assert green.sum() > 2000, f"frame {n} has no obscured faces"
        assert n == FACE_VIDEO_FRAMES

    def test_frame_order_is_preserved_through_threads(self, synthetic_video, tmp_path, recording_writer):
        fb(StubDetector(bright_square_finder), style="fill", fill_color="#ff0000", shape="rect",
           padding=0, smoothing=0, hold_frames=0, batch_size=4, workers=4
           ).process_video(synthetic_video, str(tmp_path / "o.mp4"))
        assert len(recording_writer.frames) == VIDEO_FRAMES
        for i, frame in enumerate(recording_writer.frames):
            x, y = square_origin(i)
            assert tuple(frame[y + 5, x]) == (0, 0, 255), f"frame {i} not covered at its own square"
            assert frame[y + 5, x + 6].min() > 200, f"frame {i} covered too much"  # still white

    def test_trim_start_and_end(self, synthetic_video, tmp_path, writer_backend):
        out = self.run(synthetic_video, tmp_path, start_t=1.0, end_t=2.0)
        assert frame_count(out) == 10  # 10 fps

    def test_trim_start_only(self, synthetic_video, tmp_path, writer_backend):
        out = self.run(synthetic_video, tmp_path, start_t=1.0)
        assert frame_count(out) == VIDEO_FRAMES - 10

    def test_trim_end_only(self, synthetic_video, tmp_path, writer_backend):
        out = self.run(synthetic_video, tmp_path, end_t=1.5)
        assert frame_count(out) == 15

    def test_held_face_covers_detector_dropouts(self, synthetic_video, tmp_path, recording_writer):
        state = {"n": 0}
        def flaky(image):
            state["n"] += 1
            return bright_square_finder(image) if state["n"] % 4 else []
        fb(StubDetector(flaky), style="fill", fill_color="#ff0000", shape="rect", padding=0.5,
           smoothing=0, hold_frames=2, batch_size=1, workers=1
           ).process_video(synthetic_video, str(tmp_path / "o.mp4"))
        for i, frame in enumerate(recording_writer.frames):
            x, y = square_origin(i)
            assert tuple(frame[y + 5, x + 1]) == (0, 0, 255), f"frame {i} was left exposed"

    def test_detector_is_cleaned_up(self, synthetic_video, tmp_path):
        stub = StubDetector()
        threads = cv2.getNumThreads()
        self.run(synthetic_video, tmp_path, stub)
        assert stub.executor is None and cv2.getNumThreads() == threads

    def test_creates_output_directory(self, synthetic_video, tmp_path):
        out = tmp_path / "a" / "b" / "o.mp4"
        assert fb().process_video(synthetic_video, str(out))
        assert out.is_file()

    @requires_ffmpeg
    @pytest.mark.requires_ffmpeg
    def test_audio_is_kept_and_can_be_dropped(self, tmp_path):
        import shutil, subprocess
        src = str(tmp_path / "av.mp4")
        subprocess.run([shutil.which("ffmpeg"), "-y", "-loglevel", "error",
                        "-f", "lavfi", "-i", "color=c=gray:s=64x48:r=10:d=2",
                        "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
                        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", src],
                       check=True)

        def streams(path):
            probe = shutil.which("ffprobe") or "ffprobe"
            return subprocess.run([probe, "-v", "error", "-show_entries", "stream=codec_type",
                                   "-of", "csv=p=0", path], capture_output=True, text=True).stdout.split()

        kept, dropped = str(tmp_path / "kept.mp4"), str(tmp_path / "dropped.mp4")
        assert fb().process_video(src, kept, keep_audio=True)
        assert fb().process_video(src, dropped, keep_audio=False)
        assert "audio" in streams(kept)
        assert "audio" not in streams(dropped)
