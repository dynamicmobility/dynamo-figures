"""
    Package: dynamo_figures.blur_faces
    Description: Anonymize faces in photos and videos, fully locally.

    Modules:
        core       FaceBlur, the high-level image/video API
        detectors  YuNet detection on CPU (OpenCV) or GPU (ONNX Runtime)
        tracking   Frame-to-frame box smoothing and hold for videos
        obscure    Blur / pixelate / fill rendering
        video_io   Threaded frame reading and ffmpeg encoding
        cli        The dynamo-blur-faces command-line tool
"""

from dynamo_figures.blur_faces.core import FaceBlur
from dynamo_figures.blur_faces.detectors import gpu_provider
from dynamo_figures.blur_faces.tracking import FaceTracker

__all__ = ["FaceBlur", "FaceTracker", "gpu_provider"]
