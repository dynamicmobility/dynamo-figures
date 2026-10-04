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
from PIL import Image, ImageDraw, ImageFilter


# Map human-friendly names to qrcode error-correction constants. Higher levels
# tolerate more damage/occlusion at the cost of a denser code.
ERROR_CORRECTION = {
    'L': ERROR_CORRECT_L,  # ~7% recoverable
    'M': ERROR_CORRECT_M,  # ~15% recoverable
    'Q': ERROR_CORRECT_Q,  # ~25% recoverable
    'H': ERROR_CORRECT_H,  # ~30% recoverable
}


def load_logo(logo_path, size, color=None):
    """
    Load a logo and return it as a square RGBA Pillow image of (size, size).

    SVG logos are rasterized with cairosvg (imported lazily so it is only
    required when an SVG logo is actually used). Raster logos (PNG/JPG/...) are
    opened directly. The logo is scaled to fit inside a (size, size) box while
    preserving aspect ratio, then centered on a transparent canvas.

    If `color` is given (any Pillow color string, e.g. '#eaaa00'), the logo is
    recolored to that solid color while keeping its original shape (alpha).
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

    # Recolor: keep the alpha (shape), replace RGB with the requested color.
    if color is not None:
        alpha = canvas.split()[-1]
        tinted = Image.new('RGBA', canvas.size, color)
        tinted.putalpha(alpha)
        canvas = tinted

    return canvas


class QRCode:
    """Class for generating QR codes from a URL (or any text)."""

    def __init__(self, data, box_size=10, border=4, error_correction='H',
                 fill_color='black', back_color='white',
                 logo_path=None, logo_ratio=0.22, logo_padding=0.0,
                 logo_bg='white', logo_style='badge', logo_halo=0.04,
                 logo_color=None):
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
                None for no badge (default: 'white'). Used by 'badge' style.
            logo_style: How the logo is composited (default: 'badge'):
                'badge'     -- logo on a solid rounded square (blanks a square
                               region; safest, but lots of white space for
                               line-art logos).
                'integrate' -- carve out only the modules under the logo's
                               strokes (plus a halo), then draw the logo. Uses
                               far less of the error-correction budget for thin
                               line-art logos, so the logo can be larger.
            logo_halo: For 'integrate' style, width of the cleared halo around
                the logo strokes, as a fraction of the logo size (default:
                0.04). Larger = more contrast but more modules removed.
            logo_color: Optional Pillow color string (e.g. '#eaaa00') to recolor
                the logo to a solid color, keeping its shape (default: None,
                i.e. the logo's original colors).
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
        self.logo_style = logo_style
        self.logo_halo = logo_halo
        self.logo_color = logo_color

        if self.logo_style not in ('badge', 'integrate'):
            raise ValueError(
                f"logo_style must be 'badge' or 'integrate', got {logo_style!r}"
            )

        if self.error_correction not in ERROR_CORRECTION:
            raise ValueError(
                f"error_correction must be one of {list(ERROR_CORRECTION)}, "
                f"got {error_correction!r}"
            )

        # A logo occludes the center, so force maximum error correction.
        if self.logo_path is not None and self.error_correction != 'H':
            print(" -- Note: forcing error_correction='H' for logo embedding.")
            self.error_correction = 'H'

        # Level 'H' can recover ~30% of the code. The 'badge' style blanks a
        # solid square, so its safe ratio is small; the 'integrate' style only
        # removes modules under the logo's strokes, so it tolerates larger logos.
        warn_above = 0.3 if self.logo_style == 'badge' else 0.6
        if self.logo_path is not None and self.logo_ratio > warn_above:
            rec = '<= 0.25' if self.logo_style == 'badge' else '<= 0.5'
            print(
                f" -- Warning: logo_ratio={self.logo_ratio} is large for "
                f"logo_style='{self.logo_style}' and may make the QR code "
                f"unscannable. Recommended: {rec} (test the output with a real "
                "scanner before printing)."
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
        """Dispatch to the configured logo style."""
        if self.logo_style == 'integrate':
            return self._embed_logo_integrate(qr_img)
        return self._embed_logo_badge(qr_img)

    def _embed_logo_integrate(self, qr_img):
        """
        Carve out only the modules under the logo's strokes, then draw the logo.

        For thin line-art logos this removes far fewer modules than a solid
        badge, leaving most of the QR intact while letting the logo span a much
        larger area. A small halo of background color is cleared around the
        strokes so the logo stays distinct from the surrounding modules.
        """
        qr_w, qr_h = qr_img.size
        logo_size = int(qr_w * self.logo_ratio)
        logo = load_logo(self.logo_path, logo_size, color=self.logo_color)

        # Place the logo on a full-size transparent layer so coordinates align
        # with the QR image.
        pos = ((qr_w - logo_size) // 2, (qr_h - logo_size) // 2)
        logo_layer = Image.new('RGBA', (qr_w, qr_h), (0, 0, 0, 0))
        logo_layer.paste(logo, pos, logo)

        # Binary mask of the logo's ink, then dilate it to form the halo.
        alpha = logo_layer.split()[-1]
        mask = alpha.point(lambda a: 255 if a > 16 else 0)
        halo_px = max(1, int(logo_size * self.logo_halo))
        kernel = halo_px * 2 + 1
        halo_mask = mask.filter(ImageFilter.MaxFilter(kernel))

        # Clear the halo region to the background color, then draw the logo.
        bg = Image.new('RGBA', (qr_w, qr_h), self.back_color)
        qr_img.paste(bg, (0, 0), halo_mask)
        qr_img.paste(logo_layer, (0, 0), logo_layer)
        return qr_img

    def _embed_logo_badge(self, qr_img):
        """Paste the logo (with optional badge) centered onto the QR image."""
        qr_w, qr_h = qr_img.size
        logo_size = int(qr_w * self.logo_ratio)
        logo = load_logo(self.logo_path, logo_size, color=self.logo_color)

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
        prog='dynamo-qr-code',
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
    parser.add_argument('--logo_style', default='badge', choices=['badge', 'integrate'],
                        help="'badge' (solid square behind logo) or 'integrate' "
                             "(carve only around logo strokes) (default: badge).")
    parser.add_argument('--logo_halo', type=float, default=0.04,
                        help="for 'integrate', cleared halo width around strokes "
                             "as a fraction of logo size (default: 0.04).")
    parser.add_argument('--logo_color', type=str, default=None,
                        help="recolor the logo to a solid color, e.g. '#eaaa00' "
                             "(default: keep original colors).")

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
        logo_style=args.logo_style,
        logo_halo=args.logo_halo,
        logo_color=args.logo_color,
    )

    output_path = Path(args.output)
    qr.save(output_path)
    print(f" -- QR code saved to: {output_path}")


if __name__ == "__main__":
    main()
