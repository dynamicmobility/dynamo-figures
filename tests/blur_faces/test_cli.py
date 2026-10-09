import sys

import cv2
import numpy as np
import pytest

from dynamo_figures.blur_faces import cli
from dynamo_figures.blur_faces.cli import main


class SpyFaceBlur:
    """Stands in for FaceBlur: records constructor / process_* arguments, does no work."""
    STYLES, SHAPES, DEVICES = ("blur", "pixelate", "fill"), ("ellipse", "rect"), ("auto", "gpu", "cpu")
    init, calls = {}, {}

    def __init__(self, **kw):
        SpyFaceBlur.init = kw

    def process_image(self, input_path, output_path):
        SpyFaceBlur.calls = dict(kind="image", input=input_path, output=output_path)
        return True

    def process_video(self, input_path, output_path, **kw):
        SpyFaceBlur.calls = dict(kind="video", input=input_path, output=output_path, **kw)
        return True


@pytest.fixture
def spy(monkeypatch):
    monkeypatch.setattr(cli, "FaceBlur", SpyFaceBlur)
    SpyFaceBlur.init, SpyFaceBlur.calls = {}, {}
    return SpyFaceBlur


def run(monkeypatch, *args):
    monkeypatch.setattr(sys, "argv", ["prog", "--device", "cpu", *args])
    main()


def exit_code(monkeypatch, *args):
    with pytest.raises(SystemExit) as exc:
        run(monkeypatch, *args)
    return exc.value.code


class TestImage:
    def test_blurs_photo(self, faces_image, tmp_path, monkeypatch):
        out = tmp_path / "out.jpg"
        run(monkeypatch, "--input", faces_image, "--output", str(out), "--style", "pixelate")
        before, after = cv2.imread(faces_image), cv2.imread(str(out))
        assert after.shape == before.shape and not np.array_equal(before, after)

    def test_default_output_name(self, faces_image, tmp_path, monkeypatch):
        import shutil
        copy = tmp_path / "party.jpg"
        shutil.copy(faces_image, copy)
        run(monkeypatch, "--input", str(copy))
        assert (tmp_path / "party_blurred.jpg").is_file()

    def test_options_reach_the_pipeline(self, faces_image, monkeypatch, spy):
        run(monkeypatch, "--input", faces_image, "--style", "fill", "--shape", "rect", "--padding", "0.1",
            "--fill_color", "#123456", "--score_threshold", "0.8", "--detect_max_dim", "0",
            "--draw_boxes", "--disable_pbar")
        kw = spy.init
        assert kw["style"] == "fill" and kw["shape"] == "rect" and kw["padding"] == 0.1
        assert kw["fill_color"] == "#123456" and kw["score_threshold"] == 0.8
        assert kw["detect_max_dim"] == 0 and kw["draw_boxes"] and kw["device"] == "cpu"
        assert spy.calls["kind"] == "image"

    def test_failed_processing_exits_1(self, tmp_path, monkeypatch):
        bad = tmp_path / "broken.jpg"
        bad.write_text("not an image")
        assert exit_code(monkeypatch, "--input", str(bad)) == 1


class TestVideo:
    def test_blurs_video(self, faces_video, tmp_path, monkeypatch):
        out = tmp_path / "out.mp4"
        run(monkeypatch, "--input", faces_video, "--output", str(out), "--disable_pbar", "--no_audio",
            "--batch_size", "4", "--workers", "2")
        assert out.is_file()
        cap = cv2.VideoCapture(str(out))
        assert cap.read()[0]

    def test_trim_options_reach_process_video(self, faces_video, monkeypatch, spy):
        run(monkeypatch, "--input", faces_video, "--start_t", "0.5", "--end_t", "1.5",
            "--no_audio", "--crf", "30")
        call = spy.calls
        assert call["kind"] == "video" and call["start_t"] == 0.5 and call["end_t"] == 1.5
        assert call["keep_audio"] is False and call["crf"] == 30
        assert call["output"].endswith("_blurred.mp4")


class TestErrors:
    def test_missing_input(self, tmp_path, monkeypatch):
        assert exit_code(monkeypatch, "--input", str(tmp_path / "nope.jpg")) == 1

    def test_unsupported_extension(self, tmp_path, monkeypatch):
        f = tmp_path / "notes.txt"
        f.write_text("x")
        assert exit_code(monkeypatch, "--input", str(f)) == 1

    def test_input_is_required(self, monkeypatch):
        with pytest.raises(SystemExit) as exc:
            run(monkeypatch)
        assert exc.value.code == 2

    @pytest.mark.parametrize("flag,value", [("--smoothing", "1.0"), ("--smoothing", "-0.5")])
    def test_bad_smoothing(self, faces_image, monkeypatch, flag, value):
        assert exit_code(monkeypatch, "--input", faces_image, flag, value) == 1

    @pytest.mark.parametrize("args", [["--start_t", "1"], ["--end_t", "1"]])
    def test_trim_flags_rejected_for_images(self, faces_image, monkeypatch, args):
        assert exit_code(monkeypatch, "--input", faces_image, *args) == 1

    def test_negative_start(self, faces_video, monkeypatch):
        assert exit_code(monkeypatch, "--input", faces_video, "--start_t", "-1") == 1

    def test_end_not_after_start(self, faces_video, monkeypatch):
        assert exit_code(monkeypatch, "--input", faces_video, "--start_t", "2", "--end_t", "1") == 1

    def test_invalid_choice(self, faces_image, monkeypatch):
        with pytest.raises(SystemExit) as exc:
            run(monkeypatch, "--input", faces_image, "--style", "sparkle")
        assert exc.value.code == 2
