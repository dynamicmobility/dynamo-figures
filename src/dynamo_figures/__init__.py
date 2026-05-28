"""
dynamo_figures - A Python package for dynamic figure generation
"""

__version__ = "0.1.0"

from dynamo_figures.composite_image import CompositeImage, CompositeMode
from dynamo_figures.video_to_gif import VideoToGif
from dynamo_figures.qr_code import QRCode

__all__ = ["CompositeImage", "CompositeMode", "VideoToGif", "QRCode", "__version__"]
