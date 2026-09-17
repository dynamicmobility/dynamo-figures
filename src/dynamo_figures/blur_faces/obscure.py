"""
    File: obscure.py
    Description: Rendering of obscured face regions (blur, pixelate, or fill).
"""

import cv2
import numpy as np
from PIL import ImageColor

STYLES = ('blur', 'pixelate', 'fill')
SHAPES = ('ellipse', 'rect')


class Obscurer:
    """Draws blurred, pixelated, or filled regions over face boxes."""

    def __init__(self, style='blur', shape='ellipse', padding=0.25,
                 blur_strength=0.5, pixel_blocks=10, fill_color='black',
                 draw_boxes=False):
        """
        Initialize Obscurer.

        Args:
            style: How to obscure faces: 'blur', 'pixelate', or 'fill'
            shape: Region shape to obscure: 'ellipse' or 'rect'
            padding: Fraction to enlarge each face box by on every side
            blur_strength: Blur kernel size as a fraction of face size
            pixel_blocks: Number of mosaic blocks across each face (pixelate)
            fill_color: Color name or hex code for the 'fill' style
            draw_boxes: Draw detection boxes and scores instead of obscuring
        """
        if style not in STYLES:
            raise ValueError(f"style must be one of {STYLES}")
        if shape not in SHAPES:
            raise ValueError(f"shape must be one of {SHAPES}")
        self.style = style
        self.shape = shape
        self.padding = padding
        self.blur_strength = blur_strength
        self.pixel_blocks = max(1, pixel_blocks)
        r, g, b = ImageColor.getrgb(fill_color)[:3]
        self.fill_color = (b, g, r)
        self.draw_boxes = draw_boxes

    def _padded_box(self, box, img_w, img_h):
        """Enlarge a box by the padding fraction and clip it to the image."""
        x, y, w, h = box[:4]
        # YuNet boxes are tight around the face; extend upward a bit more to cover the forehead/hair
        x0 = int(max(0, x - w * self.padding))
        x1 = int(min(img_w, x + w * (1 + self.padding)))
        y0 = int(max(0, y - h * self.padding * 1.4))
        y1 = int(min(img_h, y + h * (1 + self.padding)))
        return x0, y0, x1, y1

    def _obscured_roi(self, roi):
        """Return an obscured version of a region of interest."""
        rh, rw = roi.shape[:2]
        if self.style == 'fill':
            return np.full_like(roi, self.fill_color)
        if self.style == 'pixelate':
            bw = self.pixel_blocks
            bh = max(1, round(self.pixel_blocks * rh / rw))
            small = cv2.resize(roi, (bw, bh), interpolation=cv2.INTER_AREA)
            return cv2.resize(small, (rw, rh), interpolation=cv2.INTER_NEAREST)
        # Blur a downscaled copy so large faces stay fast, then upscale
        factor = max(1, max(rh, rw) // 128)
        small = cv2.resize(roi, (max(1, rw // factor), max(1, rh // factor)),
                           interpolation=cv2.INTER_AREA)
        k = int(max(small.shape[:2]) * self.blur_strength) | 1
        small = cv2.GaussianBlur(small, (k, k), 0)
        small = cv2.GaussianBlur(small, (k, k), 0)
        return cv2.resize(small, (rw, rh), interpolation=cv2.INTER_LINEAR)

    def apply(self, image, faces, inplace=False):
        """
        Obscure (or annotate) the given faces in an image.

        Args:
            image: BGR image (numpy array)
            faces: list of (x, y, w, h, score) tuples
            inplace: modify image directly instead of a copy

        Returns:
            numpy array: the processed image
        """
        out = image if inplace else image.copy()
        img_h, img_w = image.shape[:2]
        for face in faces:
            x0, y0, x1, y1 = self._padded_box(face, img_w, img_h)
            if x1 - x0 < 2 or y1 - y0 < 2:
                continue

            if self.draw_boxes:
                t = max(2, img_w // 500)
                cv2.rectangle(out, (x0, y0), (x1, y1), (0, 255, 0), t)
                cv2.putText(out, f"{face[4]:.2f}", (x0, max(0, y0 - 2 * t)),
                            cv2.FONT_HERSHEY_SIMPLEX, t / 3, (0, 255, 0), t)
                continue

            roi = out[y0:y1, x0:x1]
            obscured = self._obscured_roi(roi)
            if self.shape == 'rect':
                out[y0:y1, x0:x1] = obscured
                continue

            mask = np.zeros(roi.shape[:2], dtype=np.float32)
            cx, cy = (x1 - x0) // 2, (y1 - y0) // 2
            cv2.ellipse(mask, (cx, cy), (cx, cy), 0, 0, 360, 1.0, -1)
            if self.style != 'fill':
                # Feather the edge so the blur blends in
                k = max(3, int(min(roi.shape[:2]) * 0.1) | 1)
                mask = cv2.GaussianBlur(mask, (k, k), 0)
            mask = mask[..., None]
            out[y0:y1, x0:x1] = (obscured * mask + roi * (1 - mask)).astype(np.uint8)
        return out
