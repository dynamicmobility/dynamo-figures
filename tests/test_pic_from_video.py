import sys

import cv2
import pytest

from dynamo_figures.pic_from_video import FrameExtractor, main
from tests.conftest import (SQUARE, VIDEO_FPS, VIDEO_FRAMES, VIDEO_H, VIDEO_W,
                            square_origin)


class TestVideoInfo:
    def test_properties(self, synthetic_video):
        info = FrameExtractor(synthetic_video).get_video_info()
        assert (info["width"], info["height"]) == (VIDEO_W, VIDEO_H)
        assert info["frame_count"] == VIDEO_FRAMES
        assert info["fps"] == pytest.approx(VIDEO_FPS)
        assert info["duration"] == pytest.approx(VIDEO_FRAMES / VIDEO_FPS)

    def test_missing_file(self, tmp_path):
        assert FrameExtractor(str(tmp_path / "nope.mp4")).get_video_info() is None

    def test_not_a_video(self, tmp_path):
        bad = tmp_path / "bad.mp4"
        bad.write_text("not a video")
        assert FrameExtractor(str(bad)).get_video_info() is None


def square_center_is_white(path, frame_idx):
    img = cv2.imread(path)
    x, y = square_origin(frame_idx)
    return img[y + SQUARE // 2, x + SQUARE // 2].min() > 200


class TestExtractFrame:
    def test_by_frame_number(self, synthetic_video, tmp_path):
        out = str(tmp_path / "f.png")
        assert FrameExtractor(synthetic_video, frame_number=5).extract_frame(out)
        assert cv2.imread(out).shape == (VIDEO_H, VIDEO_W, 3)
        assert square_center_is_white(out, 5)

    def test_by_time(self, synthetic_video, tmp_path):
        out = str(tmp_path / "f.png")
        assert FrameExtractor(synthetic_video, time_seconds=2.0).extract_frame(out)
        assert square_center_is_white(out, 20)

    def test_defaults_to_middle_frame(self, synthetic_video, tmp_path):
        out = str(tmp_path / "f.png")
        assert FrameExtractor(synthetic_video).extract_frame(out)
        assert square_center_is_white(out, VIDEO_FRAMES // 2)

    def test_creates_parent_directories(self, synthetic_video, tmp_path):
        out = tmp_path / "a" / "b" / "f.png"
        assert FrameExtractor(synthetic_video, frame_number=0).extract_frame(str(out))
        assert out.is_file()

    @pytest.mark.parametrize("frame", [-1, VIDEO_FRAMES, 10_000])
    def test_out_of_range(self, synthetic_video, tmp_path, frame):
        out = tmp_path / "f.png"
        assert not FrameExtractor(synthetic_video, frame_number=frame).extract_frame(str(out))
        assert not out.exists()

    def test_missing_video(self, tmp_path):
        assert not FrameExtractor(str(tmp_path / "x.mp4"), 0).extract_frame(str(tmp_path / "f.png"))


class TestCli:
    def run(self, monkeypatch, *args):
        monkeypatch.setattr(sys, "argv", ["prog", *args])
        main()

    def test_extract(self, synthetic_video, tmp_path, monkeypatch):
        out = tmp_path / "f.png"
        self.run(monkeypatch, "--video_path", synthetic_video, "--frame", "3", "--output", str(out))
        assert out.is_file()

    def test_default_output_name(self, synthetic_video, tmp_path, monkeypatch):
        import shutil
        copy = tmp_path / "clip.mp4"
        shutil.copy(synthetic_video, copy)
        self.run(monkeypatch, "--video_path", str(copy))
        assert (tmp_path / "clip_frame.jpg").is_file()

    def test_info_only_writes_nothing(self, synthetic_video, tmp_path, monkeypatch, capsys):
        self.run(monkeypatch, "--video_path", synthetic_video, "--info_only")
        assert f"{VIDEO_W}x{VIDEO_H}" in capsys.readouterr().out

    def test_frame_and_time_are_exclusive(self, synthetic_video, monkeypatch):
        with pytest.raises(SystemExit) as exc:
            self.run(monkeypatch, "--video_path", synthetic_video, "--frame", "1", "--time", "1")
        assert exc.value.code == 1

    def test_failure_exits_nonzero(self, tmp_path, monkeypatch):
        with pytest.raises(SystemExit) as exc:
            self.run(monkeypatch, "--video_path", str(tmp_path / "nope.mp4"))
        assert exc.value.code == 1
