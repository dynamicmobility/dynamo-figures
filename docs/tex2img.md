---
layout: default
title: Tex2Img
nav_order: 6
description: "Convert a standalone .tex file into an SVG or PNG image."
---

# Tex2Img
{: .fs-9 }

Convert a `.tex` file into an SVG or PNG image, cropped to its content.
{: .fs-6 .fw-300 }

---

## Overview

The `dynamo-tex2img` tool compiles a `.tex` file and converts the result into
an SVG or PNG image — handy for dropping a LaTeX-typeset equation, TikZ
figure, or table straight into a slide deck or paper figure as a standalone
image.

It only relies on tools that ship alongside any working LaTeX installation
(no extra Python dependency is added):

- **PNG** — compiles to a PDF (`pdflatex`/`xelatex`/`lualatex`), optionally
  crops it to its content with `pdfcrop`, then rasterizes it with Ghostscript
  at the requested `--dpi`.
- **SVG** — compiles to a DVI (`latex`/`dvilualatex`, the DVI-producing
  counterpart of `pdflatex`/`lualatex`) and converts it directly with
  `dvisvgm`, which trims to the actual ink extents on its own.
  `--engine xelatex` has no DVI backend, so SVG output falls back to
  `dvisvgm`'s PDF mode, which additionally requires Ghostscript < 10.01.0 or
  `mutool` on `PATH`.

[Command-Line Usage](#command-line-usage){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }
[Python API](#python-api){: .btn .fs-5 .mb-4 .mb-md-0 }

## Command-Line Usage

```bash
dynamo-tex2img (--input <path.tex> | --math <expr> | --string <tex>) [options]
```

### Required Arguments

Exactly one of the following:

| Argument | Description |
|:---------|:------------|
| `--input` | Path to the input `.tex` file |
| `--math` | A math expression to render, e.g. `"E = mc^2"` (wrapped in `$...$` inside a minimal standalone document) |
| `--string` | Raw LaTeX source to render: a complete document (containing `\documentclass`) is used as-is; anything else (body content, e.g. a `tabular` or `align` environment) is wrapped in a minimal standalone document |

{: .note }
> `--output` defaults to `<input stem>.svg` with `--input`, or `tex2img.svg`
> with `--math`/`--string`.

### Optional Arguments

| Argument | Type | Default | Description |
|:---------|:-----|:--------|:------------|
| `--output` | `str` | `<input stem>.svg` | Output image path. The extension sets the format when `--format` isn't given |
| `--format` | `str` | `svg` | `svg` or `png`; overrides the extension in `--output` |
| `--dpi` | `int` | `300` | Pixels per inch for PNG output (ignored for SVG) |
| `--engine` | `str` | `pdflatex` | LaTeX engine: `pdflatex`, `xelatex`, or `lualatex` |
| `--no_crop` | flag | off | Keep the full page instead of cropping to content (PNG only; SVG always trims to content) |
| `--margin` | `float` | `10` | Padding (big points) kept around content when cropping PNG output |
| `--no_transparent` | flag | off | Render PNG output on an opaque white background instead of transparent |
| `--keep_aux` | flag | off | Keep intermediate compiler files (`.pdf`/`.dvi`/`.log`/`.aux`/…) in a `<name>_aux` folder next to the output |
| `--timeout` | `float` | `60` | Seconds allowed per subprocess step (compile, crop, convert) |

{: .note }
> Use `xelatex` or `lualatex` for documents that need system fonts or
> `fontspec`/`unicode-math`.

---

## Usage Examples

### Render a Math Expression Directly (no .tex file needed)

```bash
dynamo-tex2img --math "E = mc^2" --output equation.png --dpi 600
```

### Render Raw LaTeX Body Content

Any body content works, not just math -- it's wrapped in a minimal standalone
document:

```bash
dynamo-tex2img --string '\begin{align*} a &= b + c \\ &= d \end{align*}' --output align.png
```

A `--string` that already contains `\documentclass` is used as-is instead of
being wrapped.

{: .warning }
> **Use single quotes for `--math`/`--string` in the shell.** Double quotes
> let the shell expand `$...` as a variable reference *before* your text ever
> reaches the tool. For example `"$x + 3 = 6$"` is parsed by bash/zsh as the
> variable `$x` (usually empty) followed by literal `" + 3 = 6$"`, silently
> dropping the `x` and the opening `$`. Single quotes (`'$x + 3 = 6$'`)
> disable that expansion so the LaTeX reaches the tool unchanged.

### Render an Equation File to PNG

```bash
dynamo-tex2img --input equation.tex --output equation.png --dpi 600
```

### Render to SVG (vector, scales to any size)

```bash
dynamo-tex2img --input equation.tex --output equation.svg
dynamo-tex2img --math "\int_0^\infty e^{-x}\,dx = 1" --output integral.svg
```

### Keep the Full Page Instead of Cropping

```bash
dynamo-tex2img --input page.tex --output page.png --no_crop
```

### Opaque Background Instead of Transparent

```bash
dynamo-tex2img --input equation.tex --output equation.png --no_transparent
```

### Compile with XeLaTeX (system fonts)

```bash
dynamo-tex2img --input figure.tex --output figure.png --engine xelatex
```

{: .warning }
> SVG output with `--engine xelatex` requires Ghostscript < 10.01.0 or
> `mutool` on `PATH` (xelatex has no DVI backend for `dvisvgm` to use
> directly). `pdflatex` and `lualatex` don't have this requirement for SVG.

### Debug a Failed Compile

```bash
dynamo-tex2img --input figure.tex --output figure.png --keep_aux
```

Inspect `figure_aux/figure.log` for the LaTeX log.

---

## Tips

- A minimal input that crops tightly with no extra whitespace:

  ```latex
  \documentclass[preview]{standalone}
  \usepackage{amsmath}
  \begin{document}
  $E = mc^2$
  \end{document}
  ```

  The `standalone` class (with the `preview` option, or the standalone
  `preview` package) sizes the page to the content, which both the PNG and
  SVG paths pick up automatically.
- For a document that isn't `standalone`/`preview` (e.g. a full `article`),
  `--no_crop` keeps the whole page for PNG output; SVG output always trims to
  the ink extents regardless.

---

## Python API

You can also use the `TexToImage` class programmatically, from a file or a
string:

```python
from dynamo_figures import TexToImage

# From a .tex file
converter = TexToImage("equation.tex", engine="pdflatex")
converter.convert("equation.svg")
converter.convert("equation.png", dpi=600)

# From a bare math expression
TexToImage.from_math("E = mc^2").convert("equation.png", dpi=600)

# From raw LaTeX body content
TexToImage.from_string(
    r"\begin{align*} a &= b + c \\ &= d \end{align*}"
).convert("align.png")
```

### Constructor Parameters

```python
TexToImage(
    tex_path=None,        # Path to the input .tex file
    tex_source=None,      # Raw LaTeX source as a string, instead of tex_path
    engine='pdflatex',    # 'pdflatex', 'xelatex', or 'lualatex'
    crop=True,            # Crop PNG output to content via pdfcrop
    margin=10,            # Padding (big points) when cropping PNG output
    timeout=60,           # Seconds allowed per subprocess step
)
```

Give exactly one of `tex_path` or `tex_source`. `tex_source` is compiled
as-is, so wrap bare content first with `wrap_document()` -- or use the
`from_string()`/`from_math()` classmethods, which do that for you.

### Class Methods

| Method | Returns | Description |
|:-------|:--------|:------------|
| `TexToImage.from_string(body, **kwargs)` | `TexToImage` | Build from LaTeX body content, wrapped in a minimal standalone document |
| `TexToImage.from_math(expr, **kwargs)` | `TexToImage` | Build from a bare math expression, wrapped in `$...$` |

### Methods

| Method | Returns | Description |
|:-------|:--------|:------------|
| `convert(output_path, dpi=300, transparent=True, fmt=None, keep_aux=False, workdir=None)` | `Path` | Compile and convert, saving to `output_path` |
| `compile_pdf(workdir)` | `Path` | Compile to a PDF in `workdir` |
| `compile_dvi(workdir)` | `Path` | Compile to a DVI in `workdir` (raises if the engine has no DVI backend) |
| `crop_pdf(pdf_path)` | `Path` | Crop a compiled PDF to its content with `pdfcrop` |
| `to_svg(workdir, output_path)` | `Path` | Compile and convert to SVG with `dvisvgm` |
| `to_png(workdir, output_path, dpi=300, transparent=True)` | `Path` | Compile and convert to PNG with Ghostscript |

### Function: `wrap_document(content, math=False, packages=('amsmath', 'amssymb'))`

Wrap a LaTeX snippet in a minimal standalone document (returned unchanged if
`content` already defines `\documentclass`). Set `math=True` to wrap bare
content in `$...$` first.

```python
from dynamo_figures.tex2img import wrap_document

wrap_document("E = mc^2", math=True)
```

---

## Dependencies

`dynamo-tex2img` requires a working LaTeX installation that provides:

- One of `pdflatex`, `xelatex`, `lualatex` (compilation)
- `latex` / `dvilualatex` (SVG output with the `pdflatex`/`lualatex` engines)
- `dvisvgm` (SVG output)
- `pdfcrop` (PNG cropping; skipped automatically with `--no_crop`)
- Ghostscript (`gs`) (PNG output)

All of these ship with a standard TeX Live or MacTeX installation:

```bash
# macOS
brew install --cask mactex-no-gui

# Debian/Ubuntu
apt install texlive-full
```

{: .note }
> No Python package extra is required — unlike `[gpu]` or `[svg]`,
> `tex2img` doesn't add a `pip` dependency, only an external LaTeX
> toolchain.
