import shutil
import subprocess

import cv2
import numpy as np
import pytest

from dynamo_figures.blur_faces import video_io
from dynamo_figures.blur_faces.video_io import FFmpegWriter, FrameReader, OpenCVWriter, open_writer
from tests.conftest import (VIDEO_FRAMES, VIDEO_H, VIDEO_W, make_frame, requires_ffmpeg,
                            square_origin)


def open_cap(path):
    cap = cv2.VideoCapture(path)
    ok, first = cap.read()
    assert ok
    return cap, first


def read_all(path):
    cap = cv2.VideoCapture(path)
    frames = []
    while True:
        ok, f = cap.read()
        if not ok:
            break
        frames.append(f)
    cap.release()
    return frames


class TestFrameReader:
    def test_yields_every_frame_in_order(self, synthetic_video):
        cap, first = open_cap(synthetic_video)
        reader = FrameReader(cap, first, max_queue=4).start()
        batches = list(reader.batches(8))
        reader.close()
        assert [len(b) for b in batches] == [8, 8, 8, 6]
        flat = [f for b in batches for f in b]
        assert len(flat) == VIDEO_FRAMES
        assert np.array_equal(flat[0], first)
        for i, frame in enumerate(flat):  # in order: the square moves right 1 px per frame
            x, y = square_origin(i)
            assert frame[y + 5, x + 5].min() > 200, i

    def test_max_frames(self, synthetic_video):
        cap, first = open_cap(synthetic_video)
        reader = FrameReader(cap, first, max_queue=4, max_frames=5).start()
        total = sum(len(b) for b in reader.batches(2))
        reader.close()
        assert total == 5

    def test_max_frames_of_one_is_just_the_first(self, synthetic_video):
        cap, first = open_cap(synthetic_video)
        reader = FrameReader(cap, first, max_queue=2, max_frames=1).start()
        assert sum(len(b) for b in reader.batches(4)) == 1
        reader.close()

    def test_close_unblocks_a_full_queue(self, synthetic_video):
        cap, first = open_cap(synthetic_video)
        reader = FrameReader(cap, first, max_queue=1).start()
        reader.close()  # reader is blocked on put(); must not hang
        assert not reader._thread.is_alive()


class TestOpenCVWriter:
    def test_round_trip(self, tmp_path):
        out = str(tmp_path / "o.mp4")
        w = OpenCVWriter(out, VIDEO_W, VIDEO_H, 10)
        for i in range(10):
            w.write(make_frame(i))
        assert w.close() is True
        frames = read_all(out)
        assert len(frames) == 10 and frames[0].shape == (VIDEO_H, VIDEO_W, 3)

    def test_unwritable_path(self, tmp_path):
        with pytest.raises(IOError):
            OpenCVWriter(str(tmp_path / "missing_dir" / "o.mp4"), VIDEO_W, VIDEO_H, 10)


class TestOpenWriter:
    def test_falls_back_without_ffmpeg(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setattr(video_io.shutil, "which", lambda name: None)
        w = open_writer(str(tmp_path / "o.mp4"), VIDEO_W, VIDEO_H, 10, log_dir=str(tmp_path))
        assert isinstance(w, OpenCVWriter)
        assert "ffmpeg not found" in capsys.readouterr().out
        w.close()

    @requires_ffmpeg
    @pytest.mark.requires_ffmpeg
    def test_uses_ffmpeg_when_present(self, tmp_path):
        w = open_writer(str(tmp_path / "o.mp4"), VIDEO_W, VIDEO_H, 10, log_dir=str(tmp_path))
        assert isinstance(w, FFmpegWriter)
        w.write(make_frame(0))
        assert w.close()


@requires_ffmpeg
@pytest.mark.requires_ffmpeg
class TestFFmpegWriter:
    def write(self, tmp_path, n=10, w=VIDEO_W, h=VIDEO_H, **kw):
        out = str(tmp_path / "o.mp4")
        writer = FFmpegWriter(shutil.which("ffmpeg"), out, w, h, 10, log_dir=str(tmp_path), **kw)
        for i in range(n):
            writer.write(cv2.resize(make_frame(i), (w, h)))
        assert writer.close() is True
        return out

    def test_round_trip(self, tmp_path):
        frames = read_all(self.write(tmp_path))
        assert len(frames) == 10 and frames[0].shape == (VIDEO_H, VIDEO_W, 3)

    def test_odd_dimensions_are_padded_to_even(self, tmp_path):
        frames = read_all(self.write(tmp_path, w=63, h=47))
        assert frames[0].shape[:2] == (48, 64)

    def test_close_reports_ffmpeg_failure(self, tmp_path, capsys):
        writer = FFmpegWriter(shutil.which("ffmpeg"), str(tmp_path / "nodir" / "o.mp4"),
                              VIDEO_W, VIDEO_H, 10, log_dir=str(tmp_path))
        try:
            writer.write(make_frame(0))
        except BrokenPipeError:
            pass
        assert writer.close() is False
        assert "ffmpeg failed" in capsys.readouterr().out

    def test_audio_is_copied(self, tmp_path):
        src = str(tmp_path / "with_audio.mp4")
        subprocess.run([shutil.which("ffmpeg"), "-y", "-loglevel", "error",
                        "-f", "lavfi", "-i", "color=c=blue:s=64x48:r=10:d=2",
                        "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
                        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", src],
                       check=True)
        out = self.write(tmp_path, n=20, audio_source=src)
        streams = subprocess.run(
            [shutil.which("ffprobe") or "ffprobe", "-v", "error", "-show_entries", "stream=codec_type",
             "-of", "csv=p=0", out], capture_output=True, text=True).stdout.split()
        assert "audio" in streams and "video" in streams

    def test_no_audio_stream_when_source_has_none(self, tmp_path, synthetic_video):
        out = self.write(tmp_path, audio_source=synthetic_video)  # mp4v fixture has no audio
        assert len(read_all(out)) == 10
