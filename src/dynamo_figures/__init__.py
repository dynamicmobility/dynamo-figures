"""
dynamo_figures - A Python package for dynamic figure generation
"""

__version__ = "0.3.2"

from dynamo_figures.composite_image import CompositeImage, CompositeMode
from dynamo_figures.video_to_gif import VideoToGif
from dynamo_figures.qr_code import QRCode
from dynamo_figures.blur_faces import FaceBlur
from dynamo_figures.tex2img import TexToImage

__all__ = ["CompositeImage", "CompositeMode", "VideoToGif", "QRCode", "FaceBlur", "TexToImage", "__version__"]
