"""
    File: tex2img.py
    Author: Dynamic Mobility Lab
    Email: njanwani@gatech.edu
    Description: A python script to convert a standalone .tex file into an
    SVG or PNG image.

    Only tools that ship alongside any working LaTeX installation are used,
    so no extra Python dependency is required beyond the LaTeX toolchain the
    user already needs to have a .tex file to convert:

        - PNG output compiles to a PDF (pdflatex/xelatex/lualatex), optionally
          crops it to its content with pdfcrop, then rasterizes it with
          Ghostscript at the requested --dpi.
        - SVG output compiles to a DVI (latex/dvilualatex -- the DVI-producing
          counterpart of pdflatex/lualatex) and converts it directly with
          dvisvgm, which trims to the actual ink extents on its own. xelatex
          has no DVI backend, so SVG with --engine xelatex instead goes
          through dvisvgm's PDF mode, which additionally requires Ghostscript
          < 10.01 or mutool on PATH.
"""

import argparse
import shutil
import subprocess
import tempfile
from pathlib import Path


ENGINES = ('pdflatex', 'xelatex', 'lualatex')

# The DVI-producing counterpart of each PDF engine, used for SVG output.
# xelatex has no DVI backend.
DVI_ENGINES = {'pdflatex': 'latex', 'lualatex': 'dvilualatex'}

DEFAULT_PACKAGES = ('amsmath', 'amssymb')


class TexToImageError(RuntimeError):
    """Raised when a LaTeX/conversion subprocess fails."""


def wrap_document(content, math=False, packages=DEFAULT_PACKAGES):
    """
    Wrap a snippet of LaTeX in a minimal standalone document, so it can be
    compiled on its own.

    If `content` already defines `\\documentclass`, it's returned unchanged
    (treated as a complete document already).

    Args:
        content: The snippet to wrap -- either body content (plain text,
            inline/display math, tabular, tikzpicture, ...) or a complete
            document.
        math: Wrap `content` in `$...$` first, for bare math expressions like
            `'E = mc^2'` (default: False).
        packages: Package names to `\\usepackage` in the generated preamble
            (default: `('amsmath', 'amssymb')`). Ignored if `content` already
            defines `\\documentclass`.

    Returns:
        str: The full LaTeX document source.
    """
    if '\\documentclass' in content:
        return content

    body = f"${content}$" if math else content
    preamble = ''.join(f'\\usepackage{{{pkg}}}\n' for pkg in packages)
    return (
        "\\documentclass[preview]{standalone}\n"
        f"{preamble}"
        "\\begin{document}\n"
        f"{body}\n"
        "\\end{document}\n"
    )


def _require(binary, purpose):
    """Raise a helpful error if `binary` isn't on PATH."""
    if shutil.which(binary) is None:
        raise TexToImageError(
            f"'{binary}' not found on PATH (needed to {purpose}). "
            "Install a LaTeX distribution that provides it, e.g. "
            "MacTeX/TeX Live (brew install --cask mactex-no-gui) or TeX Live "
            "on Linux (apt install texlive-full)."
        )


def _run(cmd, cwd=None, timeout=60):
    """Run a subprocess, raising TexToImageError with its output on failure."""
    try:
        result = subprocess.run(
            cmd, cwd=cwd, timeout=timeout,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        )
    except subprocess.TimeoutExpired as exc:
        raise TexToImageError(
            f"Command timed out after {timeout}s: {' '.join(cmd)}"
        ) from exc

    if result.returncode != 0:
        tail = result.stdout.decode('utf-8', errors='replace')[-4000:]
        raise TexToImageError(
            f"Command failed ({' '.join(cmd)}):\n{tail}"
        )
    return result


class TexToImage:
    """Class for converting a .tex file (or a string of LaTeX) into an SVG or PNG image."""

    def __init__(self, tex_path=None, tex_source=None, engine='pdflatex',
                 crop=True, margin=10, timeout=60):
        """
        Initialize TexToImage. Give exactly one of `tex_path` or `tex_source`.

        Args:
            tex_path: Path to the input .tex file.
            tex_source: Raw LaTeX source as a string, used instead of
                `tex_path`. A complete document (containing
                `\\documentclass`) is compiled as-is; anything else is
                compiled as-is too, so wrap bare content (e.g. a math
                expression) with `wrap_document()` first -- `from_string()`
                and `from_math()` do this for you.
            engine: LaTeX engine to compile with: 'pdflatex', 'xelatex', or
                'lualatex' (default: 'pdflatex'). Use 'xelatex' or 'lualatex'
                for documents that need system fonts or fontspec/unicode-math.
                For SVG output, 'pdflatex' and 'lualatex' are compiled via
                their DVI-producing counterparts ('latex'/'dvilualatex') so
                dvisvgm can convert directly without Ghostscript; 'xelatex'
                has no DVI mode and goes through dvisvgm's PDF mode instead.
            crop: For PNG output, trim the compiled PDF to its content with
                pdfcrop before rasterizing (default: True). SVG output always
                trims to content automatically (ignores this flag).
            margin: Padding (in big points) kept around the content when
                `crop` is True (default: 10). Only applies to PNG output.
            timeout: Seconds to allow each subprocess (LaTeX compile, crop,
                conversion) to run before giving up (default: 60).
        """
        if (tex_path is None) == (tex_source is None):
            raise ValueError("give exactly one of tex_path or tex_source")

        self.tex_path = Path(tex_path) if tex_path is not None else None
        self.tex_source = tex_source
        self.engine = engine
        self.crop = crop
        self.margin = margin
        self.timeout = timeout

        if self.tex_path is not None and not self.tex_path.is_file():
            raise FileNotFoundError(f"No such file: {self.tex_path}")

        if self.engine not in ENGINES:
            raise ValueError(f"engine must be one of {ENGINES}, got {engine!r}")

    @classmethod
    def from_string(cls, body, **kwargs):
        """Build a TexToImage from a LaTeX body snippet (wrapped in a minimal standalone document)."""
        return cls(tex_source=wrap_document(body, math=False), **kwargs)

    @classmethod
    def from_math(cls, expr, **kwargs):
        """Build a TexToImage from a bare math expression, e.g. `'E = mc^2'`."""
        return cls(tex_source=wrap_document(expr, math=True), **kwargs)

    def _materialize(self, workdir):
        """Return the .tex file to compile, writing `tex_source` into `workdir` if needed."""
        if self.tex_source is not None:
            tex_path = Path(workdir) / 'input.tex'
            tex_path.write_text(self.tex_source)
            return tex_path
        return self.tex_path

    def _compile(self, binary, workdir, output_suffix):
        """Run `binary` on the .tex file inside `workdir`, return the output path."""
        tex_path = self._materialize(workdir)
        _require(binary, f"compile {tex_path.name}")

        _run([
            binary,
            '-interaction=nonstopmode',
            '-halt-on-error',
            '-output-directory', str(workdir),
            str(tex_path.resolve()),
        ], cwd=workdir, timeout=self.timeout)

        out_path = Path(workdir) / (tex_path.stem + output_suffix)
        if not out_path.is_file():
            raise TexToImageError(
                f"{binary} did not produce a {output_suffix} file; check "
                f"{tex_path.stem}.log"
            )
        return out_path

    def compile_pdf(self, workdir):
        """Compile the .tex file to a PDF inside `workdir`, returning its path."""
        return self._compile(self.engine, workdir, '.pdf')

    def compile_dvi(self, workdir):
        """Compile the .tex file to a DVI inside `workdir`, returning its path."""
        binary = DVI_ENGINES.get(self.engine)
        if binary is None:
            raise TexToImageError(
                f"--engine {self.engine} has no DVI backend; SVG output will "
                "instead compile a PDF and convert it with dvisvgm's PDF "
                "mode, which requires Ghostscript < 10.01.0 or mutool on "
                "PATH."
            )
        return self._compile(binary, workdir, '.dvi')

    def crop_pdf(self, pdf_path):
        """Crop `pdf_path` to its content (in place, via a pdfcrop sidecar)."""
        _require('pdfcrop', "crop the compiled PDF")

        cropped = pdf_path.with_name(pdf_path.stem + '-crop.pdf')
        _run([
            'pdfcrop', '--margins', str(self.margin),
            str(pdf_path), str(cropped),
        ], cwd=pdf_path.parent, timeout=self.timeout)
        return cropped

    def to_svg(self, workdir, output_path):
        """Compile the .tex file and convert it to an SVG with dvisvgm."""
        _require('dvisvgm', "convert to SVG")

        output_path = Path(output_path)
        try:
            dvi_path = self.compile_dvi(workdir)
            cmd = ['dvisvgm', str(dvi_path), '-o', str(output_path)]
            cwd = dvi_path.parent
        except TexToImageError:
            # No DVI backend for this engine (xelatex): fall back to PDF mode.
            pdf_path = self.compile_pdf(workdir)
            cmd = ['dvisvgm', '--pdf', str(pdf_path), '-o', str(output_path)]
            cwd = pdf_path.parent

        _run(cmd, cwd=cwd, timeout=self.timeout)
        return output_path

    def to_png(self, workdir, output_path, dpi=300, transparent=True):
        """Compile the .tex file and convert it to a PNG with Ghostscript."""
        _require('gs', "convert to PNG")

        output_path = Path(output_path)
        pdf_path = self.compile_pdf(workdir)
        if self.crop:
            pdf_path = self.crop_pdf(pdf_path)

        device = 'pngalpha' if transparent else 'png16m'
        cmd = [
            'gs', '-q', '-dSAFER', '-dBATCH', '-dNOPAUSE',
            f'-sDEVICE={device}', f'-r{dpi}',
            f'-sOutputFile={output_path}', str(pdf_path),
        ]
        _run(cmd, cwd=pdf_path.parent, timeout=self.timeout)
        return output_path

    def convert(self, output_path, dpi=300, transparent=True, fmt=None,
                keep_aux=False, workdir=None):
        """
        Compile the .tex file and convert it to an image.

        Args:
            output_path: Where to save the resulting image.
            dpi: Pixels per inch for PNG output (ignored for SVG) (default:
                300).
            transparent: Transparent background for PNG output (default:
                True). SVG output is always transparent.
            fmt: 'svg' or 'png', or None to infer from `output_path`'s suffix
                (default: None).
            keep_aux: Keep the intermediate compiler files (.pdf/.dvi/.log/
                .aux/...) in a '<output stem>_aux' folder next to
                `output_path` instead of discarding them (default: False).
            workdir: Directory to compile in. Defaults to a fresh temporary
                directory that is removed afterwards.

        Returns:
            Path: `output_path`.
        """
        # Resolve before any chdir'd subprocess runs, since compilation and
        # conversion happen with cwd set to the (temporary) workdir.
        output_path = Path(output_path).resolve()
        fmt = (fmt or output_path.suffix.lstrip('.') or 'png').lower()
        if fmt not in ('svg', 'png'):
            raise ValueError(f"fmt must be 'svg' or 'png', got {fmt!r}")

        use_tmp = workdir is None
        workdir = Path(workdir) if workdir else Path(tempfile.mkdtemp(prefix='tex2img_'))

        try:
            output_path.parent.mkdir(parents=True, exist_ok=True)

            if fmt == 'svg':
                self.to_svg(workdir, output_path)
            else:
                self.to_png(workdir, output_path, dpi=dpi, transparent=transparent)

            if keep_aux:
                aux_dir = output_path.parent / (output_path.stem + '_aux')
                aux_dir.mkdir(exist_ok=True)
                for item in Path(workdir).iterdir():
                    shutil.copy2(item, aux_dir / item.name)

            return output_path
        finally:
            if use_tmp:
                shutil.rmtree(workdir, ignore_errors=True)


def main():
    """Main function for command-line interface."""
    parser = argparse.ArgumentParser(
        prog='dynamo-tex2img',
        description='Compile a .tex file and convert it to an SVG or PNG image.',
        epilog='-'
    )
    source_group = parser.add_mutually_exclusive_group(required=True)
    source_group.add_argument('--input', type=str, default=None,
                        help='path to the input .tex file.')
    source_group.add_argument('--math', type=str, default=None,
                        help='a math expression to render, e.g. "E = mc^2" '
                             '(wrapped in $...$ inside a minimal standalone '
                             'document).')
    source_group.add_argument('--string', type=str, default=None,
                        help='raw LaTeX source to render: a complete document '
                             '(containing \\documentclass) is used as-is; '
                             'anything else is wrapped in a minimal standalone '
                             'document.')
    parser.add_argument('--output', type=str, default=None,
                        help='output image path (default: <input stem>.svg, '
                             'or tex2img.svg when using --math/--string).')
    parser.add_argument('--format', type=str, default=None, choices=['svg', 'png'],
                        help='output format; default: inferred from --output, '
                             'else svg.')
    parser.add_argument('--dpi', type=int, default=300,
                        help='pixels per inch for PNG output (default: 300).')
    parser.add_argument('--engine', type=str, default='pdflatex', choices=list(ENGINES),
                        help='LaTeX engine to compile with (default: pdflatex). '
                             'For SVG output, pdflatex/lualatex use their DVI '
                             'counterpart; xelatex has no DVI mode and needs '
                             "Ghostscript < 10.01.0 or mutool for SVG.")
    parser.add_argument('--no_crop', action='store_true',
                        help='keep the full page instead of cropping to content '
                             '(PNG output only; SVG is always trimmed to content).')
    parser.add_argument('--margin', type=float, default=10,
                        help='padding (big points) kept around content when '
                             'cropping PNG output (default: 10).')
    parser.add_argument('--no_transparent', action='store_true',
                        help='render PNG output on an opaque white background '
                             'instead of transparent.')
    parser.add_argument('--keep_aux', action='store_true',
                        help='keep intermediate compiler files next to the '
                             'output, in a "<name>_aux" folder.')
    parser.add_argument('--timeout', type=float, default=60,
                        help='seconds allowed per subprocess step (default: 60).')

    args = parser.parse_args()

    fmt = args.format or (Path(args.output).suffix.lstrip('.') if args.output else 'svg')

    if args.input:
        tex_path, tex_source = Path(args.input), None
        default_output = tex_path.with_suffix(f".{fmt}")
        print(" -- Load Param: input", tex_path)
    else:
        tex_path = None
        snippet = args.math if args.math is not None else args.string
        tex_source = wrap_document(snippet, math=args.math is not None)
        default_output = Path(f"tex2img.{fmt}")
        print(" -- Load Param:", "math" if args.math is not None else "string", repr(snippet))

    output_path = Path(args.output) if args.output else default_output

    print(" -- Load Param: output", output_path)
    print(" -- Load Param: format", fmt)
    print(" -- Load Param: engine", args.engine)
    if fmt == 'png':
        print(" -- Load Param: dpi", args.dpi)
        print(" -- Load Param: crop", not args.no_crop)
        print(" -- Load Param: transparent", not args.no_transparent)

    try:
        converter = TexToImage(
            tex_path=tex_path,
            tex_source=tex_source,
            engine=args.engine,
            crop=not args.no_crop,
            margin=args.margin,
            timeout=args.timeout,
        )
    except (FileNotFoundError, ValueError) as exc:
        parser.error(str(exc))

    try:
        converter.convert(
            output_path,
            dpi=args.dpi,
            transparent=not args.no_transparent,
            fmt=fmt,
            keep_aux=args.keep_aux,
        )
    except (TexToImageError, FileNotFoundError, ValueError) as exc:
        parser.error(str(exc))

    print(f" -- Image saved to: {output_path}")


if __name__ == "__main__":
    main()
