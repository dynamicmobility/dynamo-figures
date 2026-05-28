"""
    File: qr_code.py
    Author: Dynamic Mobility Lab
    Email: njanwani@gatech.edu
    Description: A python script to generate a QR code from a website link,
    optionally with a logo embedded in the center.

    The QR code encodes the URL directly into the image, so the resulting code
    is "permanent" -- it never expires and keeps working as long as the website
    is reachable. (QR codes only "expire" when they point at a URL-shortener that
    redirects elsewhere; this script does no redirection.)

    Embedding a logo relies on QR error correction: at level 'H' a code can lose
    ~30% of its area and still scan. Keeping the logo small (default ~22% of the
    width) and forcing error correction to 'H' keeps the code reliably scannable.
"""

import argparse
from pathlib import Path

import qrcode
from qrcode.constants import (
    ERROR_CORRECT_L,
    ERROR_CORRECT_M,
    ERROR_CORRECT_Q,
    ERROR_CORRECT_H,
)
from PIL import Image, ImageDraw


# Map human-friendly names to qrcode error-correction constants. Higher levels
# tolerate more damage/occlusion at the cost of a denser code.
ERROR_CORRECTION = {
    'L': ERROR_CORRECT_L,  # ~7% recoverable
    'M': ERROR_CORRECT_M,  # ~15% recoverable
    'Q': ERROR_CORRECT_Q,  # ~25% recoverable
    'H': ERROR_CORRECT_H,  # ~30% recoverable
}


def load_logo(logo_path, size):
    """
    Load a logo and return it as a square RGBA Pillow image of (size, size).

    SVG logos are rasterized with cairosvg (imported lazily so it is only
    required when an SVG logo is actually used). Raster logos (PNG/JPG/...) are
    opened directly. The logo is scaled to fit inside a (size, size) box while
    preserving aspect ratio, then centered on a transparent canvas.
    """
    logo_path = Path(logo_path)

    if logo_path.suffix.lower() == '.svg':
        try:
            import cairosvg
        except ImportError as exc:
            raise ImportError(
                "Rendering an SVG logo requires the 'cairosvg' package. "
                "Install it with: pip install cairosvg"
            ) from exc
        import io
        # Rasterize at the target box size; cairosvg keeps the SVG aspect ratio.
        png_bytes = cairosvg.svg2png(
            url=str(logo_path), output_width=size, output_height=size
        )
        logo = Image.open(io.BytesIO(png_bytes)).convert('RGBA')
    else:
        logo = Image.open(logo_path).convert('RGBA')

    # Scale to fit inside the size x size box, preserving aspect ratio.
    logo.thumbnail((size, size), Image.LANCZOS)

    # Center on a transparent square canvas.
    canvas = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    offset = ((size - logo.width) // 2, (size - logo.height) // 2)
    canvas.paste(logo, offset, logo)
    return canvas


class QRCode:
    """Class for generating QR codes from a URL (or any text)."""

    def __init__(self, data, box_size=10, border=4, error_correction='H',
                 fill_color='black', back_color='white',
                 logo_path=None, logo_ratio=0.22, logo_padding=0.0,
                 logo_bg='white'):
        """
        Initialize QRCode.

        Args:
            data: The URL (or text) to encode.
            box_size: Pixels per QR "box" / module (default: 10).
            border: Quiet-zone width in boxes; spec minimum is 4 (default: 4).
            error_correction: One of 'L', 'M', 'Q', 'H' (default: 'H'). When a
                logo is used this is forced to 'H' for scan reliability.
            fill_color: Color of the QR modules (default: 'black').
            back_color: Background color (default: 'white').
            logo_path: Optional path to a logo (SVG or raster) to center in the
                QR code (default: None).
            logo_ratio: Logo width as a fraction of the QR width. Keep <= ~0.3
                so the code still scans (default: 0.22).
            logo_padding: Extra padding around the logo as a fraction of the
                logo size, drawn as a solid badge of `logo_bg` behind the logo
                (default: 0.0).
            logo_bg: Background color of the badge drawn behind the logo, or
                None for no badge (default: 'white').
        """
        self.data = data
        self.box_size = box_size
        self.border = border
        self.error_correction = error_correction.upper()
        self.fill_color = fill_color
        self.back_color = back_color
        self.logo_path = logo_path
        self.logo_ratio = logo_ratio
        self.logo_padding = logo_padding
        self.logo_bg = logo_bg

        if self.error_correction not in ERROR_CORRECTION:
            raise ValueError(
                f"error_correction must be one of {list(ERROR_CORRECTION)}, "
                f"got {error_correction!r}"
            )

        # A logo occludes the center, so force maximum error correction.
        if self.logo_path is not None and self.error_correction != 'H':
            print(" -- Note: forcing error_correction='H' for logo embedding.")
            self.error_correction = 'H'

        # Level 'H' can recover ~30% of the code, but a logo wider than ~0.3 of
        # the QR width tends to occlude too much center data to scan reliably.
        if self.logo_path is not None and self.logo_ratio > 0.3:
            print(
                f" -- Warning: logo_ratio={self.logo_ratio} is large and may "
                "make the QR code unscannable. Recommended: <= 0.25 "
                "(test the output with a real scanner before printing)."
            )

    def make_image(self):
        """Build and return the QR code as a Pillow image."""
        qr = qrcode.QRCode(
            version=None,  # auto-size to fit the data
            error_correction=ERROR_CORRECTION[self.error_correction],
            box_size=self.box_size,
            border=self.border,
        )
        qr.add_data(self.data)
        qr.make(fit=True)
        img = qr.make_image(
            fill_color=self.fill_color, back_color=self.back_color
        ).convert('RGBA')

        if self.logo_path is not None:
            img = self._embed_logo(img)

        return img

    def _embed_logo(self, qr_img):
        """Paste the logo (with optional badge) centered onto the QR image."""
        qr_w, qr_h = qr_img.size
        logo_size = int(qr_w * self.logo_ratio)
        logo = load_logo(self.logo_path, logo_size)

        # Draw a solid badge behind the logo so a dark logo stays distinct from
        # dark QR modules. The badge is a rounded square slightly larger than
        # the logo (controlled by logo_padding).
        if self.logo_bg is not None:
            pad = int(logo_size * self.logo_padding)
            badge_size = logo_size + 2 * pad
            badge = Image.new('RGBA', (badge_size, badge_size), (0, 0, 0, 0))
            draw = ImageDraw.Draw(badge)
            radius = max(1, badge_size // 8)
            draw.rounded_rectangle(
                [(0, 0), (badge_size - 1, badge_size - 1)],
                radius=radius, fill=self.logo_bg,
            )
            badge.paste(logo, (pad, pad), logo)
            overlay = badge
        else:
            overlay = logo

        ov_w, ov_h = overlay.size
        pos = ((qr_w - ov_w) // 2, (qr_h - ov_h) // 2)
        qr_img.paste(overlay, pos, overlay)
        return qr_img

    def save(self, output_path):
        """Generate the QR code and save it to output_path."""
        img = self.make_image()
        # Flatten to RGB for formats (e.g. JPEG) that don't support alpha.
        if Path(output_path).suffix.lower() in ('.jpg', '.jpeg'):
            background = Image.new('RGB', img.size, self.back_color)
            background.paste(img, mask=img.split()[-1])
            img = background
        img.save(str(output_path))
        return output_path


def main():
    """Main function for command-line interface."""
    parser = argparse.ArgumentParser(
        prog='qr-code',
        description='Generate a permanent QR code from a website link, '
                    'optionally with a centered logo.',
        epilog='-'
    )
    parser.add_argument('--url', type=str, required=True,
                        help='the website link (or text) to encode.')
    parser.add_argument('--output', type=str, default='qr_code.png',
                        help='output image path (default: qr_code.png).')
    parser.add_argument('--box_size', type=int, default=10,
                        help='pixels per QR module (default: 10).')
    parser.add_argument('--border', type=int, default=4,
                        help='quiet-zone width in modules; min 4 (default: 4).')
    parser.add_argument('--error_correction', default='H', choices=['L', 'M', 'Q', 'H'],
                        help='error correction level, higher = more robust (default: H).')
    parser.add_argument('--fill_color', type=str, default='black',
                        help='color of the QR modules (default: black).')
    parser.add_argument('--back_color', type=str, default='white',
                        help='background color (default: white).')
    parser.add_argument('--logo', type=str, default=None,
                        help='path to a logo (SVG or raster) to center in the code.')
    parser.add_argument('--logo_ratio', type=float, default=0.22,
                        help='logo width as fraction of QR width; keep <= ~0.3 (default: 0.22).')
    parser.add_argument('--logo_padding', type=float, default=0.0,
                        help='badge padding around the logo, as a fraction of logo size (default: 0.0).')
    parser.add_argument('--logo_bg', type=str, default='white',
                        help="badge color behind the logo, or 'none' for no badge (default: white).")

    args = parser.parse_args()

    print(" -- Load Param: url", args.url)
    print(" -- Load Param: output", args.output)
    print(" -- Load Param: box_size", args.box_size)
    print(" -- Load Param: border", args.border)
    print(" -- Load Param: error_correction", args.error_correction)
    if args.logo:
        print(" -- Load Param: logo", args.logo)
        print(" -- Load Param: logo_ratio", args.logo_ratio)

    logo_bg = None if str(args.logo_bg).lower() == 'none' else args.logo_bg

    qr = QRCode(
        data=args.url,
        box_size=args.box_size,
        border=args.border,
        error_correction=args.error_correction,
        fill_color=args.fill_color,
        back_color=args.back_color,
        logo_path=args.logo,
        logo_ratio=args.logo_ratio,
        logo_padding=args.logo_padding,
        logo_bg=logo_bg,
    )

    output_path = Path(args.output)
    qr.save(output_path)
    print(f" -- QR code saved to: {output_path}")


if __name__ == "__main__":
    main()
