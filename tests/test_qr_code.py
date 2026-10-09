import sys

import cv2
import numpy as np
import pytest
from PIL import Image

from dynamo_figures import qr_code
from dynamo_figures.qr_code import QRCode, load_logo, main

URL = "https://example.com/dynamo"


def decode(img):
    """Decode a Pillow image with OpenCV's QR detector; '' if unreadable."""
    rgb = np.array(img.convert("RGB"))
    text, _, _ = cv2.QRCodeDetector().detectAndDecode(cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR))
    return text


class TestValidation:
    def test_bad_logo_style(self):
        with pytest.raises(ValueError, match="logo_style"):
            QRCode(URL, logo_style="sparkles")

    def test_bad_error_correction(self):
        with pytest.raises(ValueError, match="error_correction"):
            QRCode(URL, error_correction="Z")

    def test_error_correction_is_case_insensitive(self):
        assert QRCode(URL, error_correction="m").error_correction == "M"

    def test_logo_forces_h(self, logo_png, capsys):
        assert QRCode(URL, error_correction="L", logo_path=logo_png).error_correction == "H"
        assert "forcing error_correction='H'" in capsys.readouterr().out

    @pytest.mark.parametrize("style,ratio,warns", [
        ("badge", 0.2, False), ("badge", 0.4, True),
        ("integrate", 0.4, False), ("integrate", 0.7, True)])
    def test_large_logo_warning(self, logo_png, capsys, style, ratio, warns):
        QRCode(URL, logo_path=logo_png, logo_style=style, logo_ratio=ratio)
        assert ("Warning" in capsys.readouterr().out) is warns


class TestMakeImage:
    def test_is_rgba_square(self):
        img = QRCode(URL).make_image()
        assert img.mode == "RGBA" and img.width == img.height

    def test_size_follows_box_size_and_border(self):
        small = QRCode(URL, box_size=5, border=2).make_image()
        big = QRCode(URL, box_size=10, border=2).make_image()
        assert big.width == 2 * small.width

    def test_longer_data_makes_denser_code(self):
        assert QRCode("x" * 300).make_image().width > QRCode("x").make_image().width

    def test_colors(self):
        img = QRCode(URL, fill_color="#ff0000", back_color="#00ff00").make_image()
        colors = {c for _, c in img.getcolors()}
        assert colors == {(255, 0, 0, 255), (0, 255, 0, 255)}

    @pytest.mark.parametrize("ec", ["L", "M", "Q", "H"])
    def test_round_trip_decodes(self, ec):
        assert decode(QRCode(URL, error_correction=ec, box_size=8).make_image()) == URL


class TestLogo:
    def test_load_logo_is_square_rgba(self, logo_png):
        logo = load_logo(logo_png, 40)
        assert logo.size == (40, 40) and logo.mode == "RGBA"

    def test_load_logo_preserves_aspect_ratio(self, tmp_path):
        wide = tmp_path / "wide.png"
        Image.new("RGBA", (200, 100), (255, 0, 0, 255)).save(wide)
        alpha = np.array(load_logo(wide, 40))[..., 3]
        rows = np.where(alpha.any(axis=1))[0]
        assert rows.max() - rows.min() + 1 == pytest.approx(20, abs=1)

    def test_recolor_keeps_shape(self, logo_png):
        logo = load_logo(logo_png, 40, color="#eaaa00")
        opaque = np.array(logo)[np.array(logo)[..., 3] > 200]
        assert len(opaque) and (opaque[:, :3] == (0xea, 0xaa, 0x00)).all()

    def test_missing_logo_file(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            load_logo(tmp_path / "nope.png", 40)

    def test_svg_without_cairosvg_raises(self, tmp_path, monkeypatch):
        monkeypatch.setitem(sys.modules, "cairosvg", None)
        svg = tmp_path / "l.svg"
        svg.write_text("<svg xmlns='http://www.w3.org/2000/svg'/>")
        with pytest.raises(ImportError, match="cairosvg"):
            load_logo(svg, 40)

    def test_svg_logo(self, tmp_path):
        try:
            import cairosvg  # noqa: F401  (OSError when the cairo C library is missing)
        except (ImportError, OSError):
            pytest.skip("cairosvg or the cairo library is not available")
        svg = tmp_path / "l.svg"
        svg.write_text("<svg xmlns='http://www.w3.org/2000/svg' width='10' height='10'>"
                       "<rect width='10' height='10' fill='red'/></svg>")
        assert load_logo(svg, 30).size == (30, 30)

    @pytest.mark.parametrize("style", ["badge", "integrate"])
    def test_logo_changes_center_and_still_scans(self, logo_png, style):
        kw = dict(box_size=10, logo_style=style, logo_ratio=0.2)
        plain = QRCode(URL, box_size=10).make_image()
        with_logo = QRCode(URL, logo_path=logo_png, **kw).make_image()
        assert with_logo.size == plain.size
        c = plain.width // 2
        box = (c - 35, c - 35, c + 35, c + 35)  # the logo is ~0.2 * width wide
        assert np.any(np.array(plain.crop(box)) != np.array(with_logo.crop(box)))
        # Away from the logo, the code is untouched
        corner = (0, 0, plain.width // 4, plain.height // 4)
        assert np.array_equal(np.array(plain.crop(corner)), np.array(with_logo.crop(corner)))
        assert decode(with_logo) == URL

    def test_badge_background_color(self, logo_png):
        img = QRCode(URL, logo_path=logo_png, logo_bg="#ff0000",
                     logo_padding=0.2, logo_ratio=0.2).make_image()
        assert (255, 0, 0, 255) in {c for _, c in img.getcolors(maxcolors=100000)}

    def test_no_badge(self, logo_png):
        assert QRCode(URL, logo_path=logo_png, logo_bg=None).make_image().size


class TestSave:
    def test_png(self, tmp_path):
        out = QRCode(URL).save(tmp_path / "qr.png")
        with Image.open(out) as im:
            assert im.format == "PNG"

    def test_jpeg_is_flattened(self, tmp_path):
        out = QRCode(URL).save(tmp_path / "qr.jpg")
        with Image.open(out) as im:
            assert im.format == "JPEG" and im.mode == "RGB"


class TestCli:
    def run(self, monkeypatch, *args):
        monkeypatch.setattr(sys, "argv", ["prog", *args])
        main()

    def test_writes_decodable_png(self, tmp_path, monkeypatch):
        out = tmp_path / "qr.png"
        self.run(monkeypatch, "--url", URL, "--output", str(out), "--box_size", "8")
        with Image.open(out) as im:
            assert decode(im) == URL

    def test_logo_options(self, tmp_path, monkeypatch, logo_png):
        out = tmp_path / "qr.png"
        self.run(monkeypatch, "--url", URL, "--output", str(out), "--logo", logo_png,
                 "--logo_style", "integrate", "--logo_bg", "none", "--logo_color", "#eaaa00")
        assert out.is_file()

    def test_url_is_required(self, monkeypatch):
        with pytest.raises(SystemExit):
            self.run(monkeypatch)
