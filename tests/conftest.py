"""Shared fixtures: synthetic videos and images, so no binary assets are needed."""

import os
import shutil
from pathlib import Path

import cv2
import numpy as np
import pytest

os.environ.setdefault("MPLBACKEND", "Agg")

DATA_DIR = Path(__file__).parent / "data"

VIDEO_W, VIDEO_H, VIDEO_FPS, VIDEO_FRAMES = 64, 48, 10, 30
SQUARE = 10  # side of the moving square, in pixels


def square_origin(i):
    """Top-left corner of the moving square in frame i (moves right 1 px / frame)."""
    return 4 + i, 19


def make_frame(i):
    """Mid-grey background with a bright white square at square_origin(i)."""
    frame = np.full((VIDEO_H, VIDEO_W, 3), 60, np.uint8)
    x, y = square_origin(i)
    frame[y:y + SQUARE, x:x + SQUARE] = 255
    return frame


def write_video(path, frames, fps=VIDEO_FPS):
    h, w = frames[0].shape[:2]
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), fps, (w, h))
    assert writer.isOpened(), "cv2 could not open a video writer for the fixture"
    for frame in frames:
        writer.write(frame)
    writer.release()
    return path


@pytest.fixture(scope="session")
def synthetic_video(tmp_path_factory):
    """64x48, 10 fps, 30 frames (3 s) video with a white square moving right."""
    path = tmp_path_factory.mktemp("video") / "synthetic.mp4"
    return str(write_video(path, [make_frame(i) for i in range(VIDEO_FRAMES)]))


@pytest.fixture
def faces_image():
    """Real photo with several faces, for detector tests."""
    return str(DATA_DIR / "faces.jpg")


@pytest.fixture
def blank_image(tmp_path):
    path = tmp_path / "blank.png"
    cv2.imwrite(str(path), np.full((120, 160, 3), 128, np.uint8))
    return str(path)


@pytest.fixture
def logo_png(tmp_path):
    """Small black-ring logo on a transparent background."""
    from PIL import Image, ImageDraw
    img = Image.new("RGBA", (100, 100), (0, 0, 0, 0))
    ImageDraw.Draw(img).ellipse((10, 10, 90, 90), outline=(0, 0, 0, 255), width=12)
    path = tmp_path / "logo.png"
    img.save(path)
    return str(path)


requires_ffmpeg = pytest.mark.skipif(
    shutil.which("ffmpeg") is None, reason="ffmpeg not installed")

requires_latex = pytest.mark.skipif(
    any(shutil.which(b) is None for b in ("pdflatex", "pdfcrop", "latex", "dvisvgm", "gs")),
    reason="LaTeX toolchain (pdflatex, pdfcrop, latex, dvisvgm, gs) not installed")
