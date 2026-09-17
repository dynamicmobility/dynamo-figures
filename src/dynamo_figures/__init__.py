"""
dynamo_figures - A Python package for dynamic figure generation
"""

__version__ = "0.3.1"

from dynamo_figures.composite_image import CompositeImage, CompositeMode
from dynamo_figures.video_to_gif import VideoToGif
from dynamo_figures.qr_code import QRCode
from dynamo_figures.blur_faces import FaceBlur

__all__ = ["CompositeImage", "CompositeMode", "VideoToGif", "QRCode", "FaceBlur", "__version__"]
