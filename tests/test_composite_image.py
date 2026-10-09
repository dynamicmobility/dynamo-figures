import sys

import cv2
import numpy as np
import pytest

from dynamo_figures.composite_image import CompositeImage, CompositeMode, main
from tests.conftest import SQUARE, VIDEO_FRAMES, VIDEO_H, VIDEO_W, square_origin


def make(video, mode=CompositeMode.MAX_VALUE, **kw):
    return CompositeImage(mode, video, disable_pbar=True, **kw)


class TestInit:
    @pytest.mark.parametrize("given,expected", [(-1, 0.0), (0.3, 0.3), (7, 1.0)])
    def test_alpha_is_clamped(self, given, expected):
        assert CompositeImage(CompositeMode.MAX_VALUE, "x", alpha=given).alpha == expected

    def test_modes_are_distinct(self):
        assert len({m.value for m in CompositeMode}) == 3


class TestExtractFrames:
    def test_all_frames(self, synthetic_video):
        frames = make(synthetic_video).extract_frames()
        assert len(frames) == VIDEO_FRAMES
        assert frames[0].shape == (VIDEO_H, VIDEO_W, 3)

    def test_skip_frame(self, synthetic_video):
        assert len(make(synthetic_video, skip_frame=3).extract_frames()) == 10

    def test_time_window(self, synthetic_video):
        # 10 fps: 1 s .. 2 s is frames 10..20 inclusive
        frames = make(synthetic_video, start_t=1, end_t=2).extract_frames()
        assert len(frames) == 11

    def test_no_path(self):
        assert CompositeImage(CompositeMode.MAX_VALUE, None).extract_frames() is None


class TestMerge:
    def test_output_shape_and_dtype(self, synthetic_video):
        out = make(synthetic_video).merge_images()
        assert out.shape == (VIDEO_H, VIDEO_W, 3)
        assert out.dtype == np.uint8

    def test_max_value_keeps_square_at_every_position(self, synthetic_video):
        out = make(synthetic_video, alpha=1.0).merge_images()
        for i in (0, VIDEO_FRAMES // 2, VIDEO_FRAMES - 1):
            x, y = square_origin(i)
            assert out[y + SQUARE // 2, x + SQUARE // 2].min() > 200, i

    def test_min_value_removes_bright_square(self, synthetic_video):
        # The square moves, so the darkest value at each pixel is the background
        # wherever the square is absent in at least one frame.
        out = make(synthetic_video, CompositeMode.MIN_VALUE, alpha=1.0).merge_images()
        x, y = square_origin(0)
        assert out[y + SQUARE // 2, x + 1].max() < 100

    def test_max_variation_shows_motion(self, synthetic_video):
        out = make(synthetic_video, CompositeMode.MAX_VARIATION, alpha=1.0).merge_images()
        x, y = square_origin(VIDEO_FRAMES // 2)
        assert out[y + SQUARE // 2, x + SQUARE // 2].min() > 100
        assert out[2, 2].max() < 100  # untouched background stays background

    def test_single_frame_returns_that_frame(self, synthetic_video):
        out = make(synthetic_video, start_t=0, end_t=0).merge_images()
        np.testing.assert_allclose(out.astype(int), make(synthetic_video).extract_frames()[0], atol=1)

    def test_missing_video_exits(self, tmp_path):
        with pytest.raises(SystemExit):
            make(str(tmp_path / "nope.mp4")).merge_images()


class TestCli:
    @pytest.mark.parametrize("mode", ["VAR", "MAX", "MIN"])
    def test_writes_image(self, synthetic_video, tmp_path, monkeypatch, mode):
        out = tmp_path / "composite.png"
        monkeypatch.setattr(sys, "argv", [
            "prog", "--video_path", synthetic_video, "--mode", mode,
            "--output", str(out), "--disable_pbar"])
        main()
        img = cv2.imread(str(out))
        assert img.shape == (VIDEO_H, VIDEO_W, 3)

    def test_default_output_next_to_video(self, synthetic_video, tmp_path, monkeypatch):
        import shutil
        copy = tmp_path / "clip.mp4"
        shutil.copy(synthetic_video, copy)
        monkeypatch.setattr(sys, "argv", ["prog", "--video_path", str(copy), "--disable_pbar"])
        main()
        assert (tmp_path / "clip.jpg").is_file()
