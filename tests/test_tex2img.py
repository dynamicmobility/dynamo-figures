import subprocess
import sys

import pytest
from PIL import Image

from dynamo_figures import tex2img
from dynamo_figures.tex2img import TexToImage, TexToImageError, _require, _run, main, wrap_document
from tests.conftest import requires_latex

BAD_TEX = "\\documentclass{article}\\begin{document}\\undefinedcommand\\end{document}"


class TestWrapDocument:
    def test_wraps_body(self):
        doc = wrap_document("hello")
        assert "\\documentclass[preview]{standalone}" in doc
        assert "\\begin{document}\nhello\n\\end{document}" in doc

    def test_math_mode(self):
        assert "$E=mc^2$" in wrap_document("E=mc^2", math=True)

    def test_default_packages(self):
        doc = wrap_document("x")
        assert "\\usepackage{amsmath}" in doc and "\\usepackage{amssymb}" in doc

    def test_custom_packages(self):
        doc = wrap_document("x", packages=("tikz",))
        assert "\\usepackage{tikz}" in doc and "amsmath" not in doc

    def test_complete_document_is_unchanged(self):
        full = "\\documentclass{article}\n\\begin{document}hi\\end{document}"
        assert wrap_document(full, math=True, packages=("tikz",)) == full


class TestConstructor:
    def test_needs_exactly_one_source(self, tmp_path):
        with pytest.raises(ValueError, match="exactly one"):
            TexToImage()
        tex = tmp_path / "a.tex"
        tex.write_text("x")
        with pytest.raises(ValueError, match="exactly one"):
            TexToImage(tex_path=tex, tex_source="x")

    def test_missing_file(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            TexToImage(tex_path=tmp_path / "nope.tex")

    def test_bad_engine(self):
        with pytest.raises(ValueError, match="engine"):
            TexToImage(tex_source="x", engine="wordperfect")

    def test_from_math(self):
        t = TexToImage.from_math("x^2", engine="lualatex")
        assert "$x^2$" in t.tex_source and t.engine == "lualatex"

    def test_defaults(self):
        t = TexToImage(tex_source="x")
        assert (t.engine, t.crop, t.margin, t.timeout) == ("pdflatex", True, 10, 60)


class TestSubprocessHelpers:
    def test_require_missing_binary(self, monkeypatch):
        monkeypatch.setattr(tex2img.shutil, "which", lambda b: None)
        with pytest.raises(TexToImageError, match="not found on PATH"):
            _require("pdflatex", "compile")

    def test_require_present_binary(self, monkeypatch):
        monkeypatch.setattr(tex2img.shutil, "which", lambda b: "/bin/" + b)
        _require("pdflatex", "compile")

    def test_run_success(self):
        assert _run([sys.executable, "-c", "print('hi')"]).stdout.strip() == b"hi"

    def test_run_failure_includes_output(self):
        with pytest.raises(TexToImageError, match="boom"):
            _run([sys.executable, "-c", "import sys; print('boom'); sys.exit(2)"])

    def test_run_timeout(self):
        with pytest.raises(TexToImageError, match="timed out"):
            _run([sys.executable, "-c", "import time; time.sleep(30)"], timeout=0.2)


class TestConvertDispatch:
    """convert() logic, with the conversion steps stubbed out."""

    @pytest.fixture
    def calls(self, monkeypatch):
        calls = []
        monkeypatch.setattr(TexToImage, "to_svg", lambda self, wd, out: calls.append(("svg", out)))
        monkeypatch.setattr(TexToImage, "to_png",
                            lambda self, wd, out, dpi, transparent: calls.append(("png", dpi, transparent)))
        return calls

    def test_format_inferred_from_suffix(self, tmp_path, calls):
        t = TexToImage(tex_source="x")
        t.convert(tmp_path / "a.svg")
        t.convert(tmp_path / "a.png", dpi=150, transparent=False)
        assert [c[0] for c in calls] == ["svg", "png"]
        assert calls[1] == ("png", 150, False)

    def test_explicit_fmt_overrides_suffix(self, tmp_path, calls):
        TexToImage(tex_source="x").convert(tmp_path / "a.out", fmt="svg")
        assert calls[0][0] == "svg"

    def test_bad_format(self, tmp_path, calls):
        with pytest.raises(ValueError, match="fmt"):
            TexToImage(tex_source="x").convert(tmp_path / "a.gif")

    def test_creates_output_directory(self, tmp_path, calls):
        TexToImage(tex_source="x").convert(tmp_path / "deep" / "er" / "a.svg")
        assert (tmp_path / "deep" / "er").is_dir()

    def test_temp_workdir_removed(self, tmp_path, calls, monkeypatch):
        seen = []
        monkeypatch.setattr(TexToImage, "to_svg", lambda self, wd, out: seen.append(wd))
        TexToImage(tex_source="x").convert(tmp_path / "a.svg")
        assert not seen[0].exists()

    def test_missing_compiler_is_a_clear_error(self, tmp_path, monkeypatch):
        monkeypatch.setattr(tex2img.shutil, "which", lambda b: None)
        with pytest.raises(TexToImageError, match="not found on PATH"):
            TexToImage.from_math("x").convert(tmp_path / "a.png")

    def test_xelatex_has_no_dvi_backend(self, tmp_path):
        with pytest.raises(TexToImageError, match="no DVI backend"):
            TexToImage(tex_source="x", engine="xelatex").compile_dvi(tmp_path)


@requires_latex
@pytest.mark.requires_latex
class TestIntegration:
    def test_math_to_svg(self, tmp_path):
        out = TexToImage.from_math("x^2 + y^2 = z^2").convert(tmp_path / "eq.svg")
        text = out.read_text()
        assert "<svg" in text and "</svg>" in text

    def test_math_to_png(self, tmp_path):
        out = TexToImage.from_math("E = mc^2").convert(tmp_path / "eq.png", dpi=100)
        with Image.open(out) as im:
            assert im.format == "PNG" and im.mode == "RGBA"
            assert im.width > im.height > 5

    def test_png_not_transparent(self, tmp_path):
        out = TexToImage.from_math("a").convert(tmp_path / "eq.png", dpi=100, transparent=False)
        with Image.open(out) as im:
            assert im.mode == "RGB"

    def test_dpi_scales_png(self, tmp_path):
        t = TexToImage.from_math("a+b")
        lo = Image.open(t.convert(tmp_path / "lo.png", dpi=72))
        hi = Image.open(t.convert(tmp_path / "hi.png", dpi=144))
        assert hi.width == pytest.approx(2 * lo.width, rel=0.1)

    def test_margin_and_crop(self, tmp_path):
        cropped = Image.open(TexToImage.from_math("a", margin=0).convert(tmp_path / "c.png", dpi=100))
        padded = Image.open(TexToImage.from_math("a", margin=20).convert(tmp_path / "p.png", dpi=100))
        assert padded.width > cropped.width

    def test_from_tex_file(self, tmp_path):
        tex = tmp_path / "doc.tex"
        tex.write_text(wrap_document("hello"))
        out = TexToImage(tex_path=tex).convert(tmp_path / "doc.svg")
        assert out.is_file()

    def test_keep_aux(self, tmp_path):
        TexToImage.from_math("a").convert(tmp_path / "eq.svg", keep_aux=True)
        files = {p.suffix for p in (tmp_path / "eq_aux").iterdir()}
        assert {".tex", ".dvi", ".log"} <= files

    def test_broken_latex_raises_with_log(self, tmp_path):
        with pytest.raises(TexToImageError, match="undefinedcommand"):
            TexToImage(tex_source=BAD_TEX).convert(tmp_path / "x.svg")

    def test_timeout(self, tmp_path):
        with pytest.raises(TexToImageError, match="timed out"):
            TexToImage.from_math("a", timeout=0.001).convert(tmp_path / "x.svg")


class TestCli:
    def run(self, monkeypatch, *args):
        monkeypatch.setattr(sys, "argv", ["prog", *args])
        main()

    def test_source_options_are_exclusive(self, monkeypatch):
        with pytest.raises(SystemExit):
            self.run(monkeypatch, "--math", "x", "--string", "y")

    def test_requires_a_source(self, monkeypatch):
        with pytest.raises(SystemExit):
            self.run(monkeypatch)

    def test_missing_input_file(self, monkeypatch, tmp_path):
        with pytest.raises(SystemExit):
            self.run(monkeypatch, "--input", str(tmp_path / "nope.tex"))

    def test_converter_gets_cli_options(self, monkeypatch, tmp_path):
        seen = {}
        def fake_convert(self, output, **kw):
            seen.update(output=output, engine=self.engine, crop=self.crop, margin=self.margin, **kw)
        monkeypatch.setattr(TexToImage, "convert", fake_convert)
        self.run(monkeypatch, "--math", "x", "--output", str(tmp_path / "o.png"), "--dpi", "50",
                 "--engine", "lualatex", "--no_crop", "--margin", "3", "--no_transparent")
        assert seen["fmt"] == "png" and seen["dpi"] == 50 and seen["engine"] == "lualatex"
        assert seen["crop"] is False and seen["margin"] == 3 and seen["transparent"] is False

    def test_default_format_is_svg(self, monkeypatch, tmp_path):
        seen = {}
        monkeypatch.setattr(TexToImage, "convert", lambda self, out, **kw: seen.update(kw, out=out))
        monkeypatch.chdir(tmp_path)
        self.run(monkeypatch, "--math", "x")
        assert seen["fmt"] == "svg" and str(seen["out"]) == "tex2img.svg"

    def test_conversion_error_exits_via_parser(self, monkeypatch, tmp_path):
        def fail(self, *a, **k):
            raise TexToImageError("kaboom")
        monkeypatch.setattr(TexToImage, "convert", fail)
        with pytest.raises(SystemExit) as exc:
            self.run(monkeypatch, "--math", "x", "--output", str(tmp_path / "o.svg"))
        assert exc.value.code == 2

    @requires_latex
    def test_end_to_end(self, monkeypatch, tmp_path):
        out = tmp_path / "eq.svg"
        self.run(monkeypatch, "--math", "a^2", "--output", str(out))
        assert "<svg" in out.read_text()
