import sys

import pytest
from PIL import Image

from dynamo_figures import video_to_gif
from dynamo_figures.video_to_gif import VideoToGif, main
from tests.conftest import VIDEO_FRAMES, VIDEO_H, VIDEO_W


def make(video, **kw):
    return VideoToGif(video, disable_pbar=True, **kw)


def read_gif(path):
    with Image.open(path) as im:
        durations = []
        for i in range(im.n_frames):
            im.seek(i)
            durations.append(im.info.get("duration"))
        return im.n_frames, im.size, durations, im.info.get("loop")


class TestInit:
    def test_clamping(self):
        v = VideoToGif("x", fps=0, start_t=-3, scale=99, speed=0,
                       crop_left=-1, crop_right=-1, crop_top=-1, crop_bottom=-1)
        assert (v.fps, v.start_t, v.scale, v.speed) == (1, 0, 2.0, 0.01)
        assert (v.crop_left, v.crop_right, v.crop_top, v.crop_bottom) == (0, 0, 0, 0)

    def test_scale_lower_clamp(self):
        assert VideoToGif("x", scale=0).scale == 0.01


class TestVideoInfo:
    def test_info(self, synthetic_video):
        info = make(synthetic_video).get_video_info()
        assert (info["width"], info["height"], info["frame_count"]) == (VIDEO_W, VIDEO_H, VIDEO_FRAMES)

    def test_missing(self, tmp_path):
        assert make(str(tmp_path / "x.mp4")).get_video_info() is None


class TestOutputSize:
    def size(self, video, **kw):
        v = make(video, **kw)
        v.get_video_info()
        return v._calculate_output_size()

    def test_identity(self, synthetic_video):
        assert self.size(synthetic_video) == (VIDEO_W, VIDEO_H)

    def test_scale(self, synthetic_video):
        assert self.size(synthetic_video, scale=0.5) == (32, 24)

    def test_width_keeps_aspect_ratio(self, synthetic_video):
        assert self.size(synthetic_video, width=32) == (32, 24)

    def test_dimensions_rounded_up_to_even(self, synthetic_video):
        w, h = self.size(synthetic_video, scale=0.51)  # 32.6 x 24.5 -> 32 x 24
        assert w % 2 == 0 and h % 2 == 0


class TestCropFrame:
    def test_crop_edges(self, synthetic_video):
        import numpy as np
        frame = np.zeros((20, 40, 3), np.uint8)
        out = make(synthetic_video)._crop_frame(frame, 5, 10, 2, 3)
        assert out.shape == (15, 25, 3)

    def test_oversized_crop_leaves_one_pixel(self, synthetic_video):
        import numpy as np
        frame = np.zeros((20, 40, 3), np.uint8)
        out = make(synthetic_video)._crop_frame(frame, 100, 100, 100, 100)
        assert out.shape[0] >= 1 and out.shape[1] >= 1


class TestExtractFrames:
    def test_fps_subsamples_frames(self, synthetic_video):
        assert len(make(synthetic_video, fps=5).extract_frames()) == VIDEO_FRAMES // 2

    def test_time_window(self, synthetic_video):
        assert len(make(synthetic_video, fps=10, start_t=1, end_t=2).extract_frames()) == 10

    def test_frames_are_rgb(self, synthetic_video):
        frame = make(synthetic_video).extract_frames()[0]
        assert frame.shape == (VIDEO_H, VIDEO_W, 3)

    def test_crop_applied_after_scale(self, synthetic_video):
        frame = make(synthetic_video, scale=0.5, crop_left=4, crop_top=2).extract_frames()[0]
        assert frame.shape == (24 - 2, 32 - 4, 3)

    def test_missing_video(self, tmp_path):
        assert make(str(tmp_path / "x.mp4")).extract_frames() is None


class TestConvert:
    def test_writes_valid_gif(self, synthetic_video, tmp_path):
        out = tmp_path / "out.gif"
        assert make(synthetic_video).convert(str(out))
        n, size, _, loop = read_gif(out)
        assert n == VIDEO_FRAMES and size == (VIDEO_W, VIDEO_H) and loop == 0

    def test_creates_parent_directories(self, synthetic_video, tmp_path):
        out = tmp_path / "a" / "b" / "out.gif"
        assert make(synthetic_video).convert(str(out))

    def test_scale_changes_size(self, synthetic_video, tmp_path):
        out = tmp_path / "out.gif"
        make(synthetic_video, scale=0.5).convert(str(out))
        assert read_gif(out)[1] == (32, 24)

    def test_reverse_is_boomerang(self, synthetic_video, tmp_path):
        out = tmp_path / "out.gif"
        make(synthetic_video, fps=5, reverse=True).convert(str(out))
        n = VIDEO_FRAMES // 2
        assert read_gif(out)[0] == 2 * n - 2

    def test_speed_shortens_frame_duration(self, synthetic_video, tmp_path):
        slow, fast = tmp_path / "slow.gif", tmp_path / "fast.gif"
        make(synthetic_video).convert(str(slow))
        make(synthetic_video, speed=2.0).convert(str(fast))
        assert read_gif(fast)[2][0] < read_gif(slow)[2][0]

    def test_loop_count(self, synthetic_video, tmp_path):
        out = tmp_path / "out.gif"
        make(synthetic_video, loop=3).convert(str(out))
        assert read_gif(out)[3] == 3

    def test_missing_video_returns_false(self, tmp_path):
        out = tmp_path / "out.gif"
        assert not make(str(tmp_path / "x.mp4")).convert(str(out))
        assert not out.exists()

    def test_falls_back_to_imageio_when_pil_fails(self, synthetic_video, tmp_path, monkeypatch):
        pytest.importorskip("imageio")
        def boom(self, frames, path):
            raise RuntimeError("pil broke")
        monkeypatch.setattr(VideoToGif, "_save_gif_pil", boom)
        out = tmp_path / "out.gif"
        assert make(synthetic_video).convert(str(out))
        assert read_gif(out)[0] == VIDEO_FRAMES

    def test_fails_when_every_writer_fails(self, synthetic_video, tmp_path, monkeypatch):
        monkeypatch.setattr(video_to_gif, "HAS_IMAGEIO", False)
        monkeypatch.setattr(VideoToGif, "_save_gif_pil", lambda *a: (_ for _ in ()).throw(OSError()))
        assert not make(synthetic_video).convert(str(tmp_path / "out.gif"))

    def test_no_encoder_available(self, synthetic_video, tmp_path, monkeypatch):
        monkeypatch.setattr(video_to_gif, "HAS_PIL", False)
        monkeypatch.setattr(video_to_gif, "HAS_IMAGEIO", False)
        assert not make(synthetic_video).convert(str(tmp_path / "out.gif"))


class TestCli:
    def run(self, monkeypatch, *args):
        monkeypatch.setattr(sys, "argv", ["prog", *args, "--disable_pbar"])
        main()

    def test_convert(self, synthetic_video, tmp_path, monkeypatch):
        out = tmp_path / "out.gif"
        self.run(monkeypatch, "--video_path", synthetic_video, "--output", str(out),
                 "--fps", "5", "--scale", "0.5")
        n, size, _, _ = read_gif(out)
        assert n == 15 and size == (32, 24)

    def test_default_output_name(self, synthetic_video, tmp_path, monkeypatch):
        import shutil
        copy = tmp_path / "clip.mp4"
        shutil.copy(synthetic_video, copy)
        self.run(monkeypatch, "--video_path", str(copy))
        assert (tmp_path / "clip.gif").is_file()

    def test_info_only(self, synthetic_video, monkeypatch, capsys):
        self.run(monkeypatch, "--video_path", synthetic_video, "--info_only")
        assert f"{VIDEO_W}x{VIDEO_H}" in capsys.readouterr().out

    def test_failure_exits_nonzero(self, tmp_path, monkeypatch):
        with pytest.raises(SystemExit) as exc:
            self.run(monkeypatch, "--video_path", str(tmp_path / "x.mp4"))
        assert exc.value.code == 1
