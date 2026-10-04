---
layout: default
title: Home
nav_order: 1
description: "Dynamo Figures - An internal Python package for creating figures for publications."
permalink: /
---

# Dynamo Figures
{: .fs-9 }

An internal Python package for creating figures for publications.
{: .fs-6 .fw-300 }

[Get Started](#installation){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }
[View on GitHub](https://github.com/dynamicmobility/dynamo_figures){: .btn .fs-5 .mb-4 .mb-md-0 }

---

## Overview

Dynamo Figures provides helpful, easy-to-run tools for video processing:

- **Composite Image**: Create cool visual effects by merging video frames using various composition modes
- **Frame Extraction**: Extract single frames from videos at specific times or frame numbers
- **Video to GIF**: Convert videos to animated GIFs with frame rate and size control
- **QR Code**: Generate permanent QR codes from links, with optional logo embedding and recoloring
- **Blur Faces**: Anonymize faces in photos and videos by blurring, pixelating, or covering them (runs fully locally)
- **Tex2Img**: Convert a `.tex` file into an SVG or PNG image, cropped to its content

### Conributing
Please feel free to contribute. Highly recommend Claude! Chat with Neil if you have questions.

## Installation

### Install from Git

```bash
pip install git+ssh://git@github.com/dynamicmobility/dynamo_figures.git
```

With GPU acceleration (note the quotes):

```bash
pip install "dynamo-figures[gpu] @ git+ssh://git@github.com/dynamicmobility/dynamo_figures.git"
```

### Install from Local Directory

```bash
git clone git@github.com:dynamicmobility/dynamo_figures.git
cd dynamo_figures
pip install -e .
```

With GPU acceleration:

```bash
pip install -e ".[gpu]"
```

{: .note }
> The `[gpu]` extra is optional. It installs [ONNX Runtime](https://onnxruntime.ai/)
> so that [Blur Faces](blur-faces#gpu-acceleration) can run face detection on the
> GPU (CoreML on Apple Silicon, CUDA on NVIDIA). Everything still works without
> it; detection just runs on the CPU.

## Quick Start

### Create a Composite Image

```bash
dynamo-composite-image --video_path ./video.mp4 --mode VAR --alpha 0.4 --output composite.png
```

### Extract a Frame from Video

```bash
dynamo-pic-from-video --video_path ./video.mp4 --time 5.0 --output frame.jpg
```

### Convert Video to GIF

```bash
dynamo-video-to-gif --video_path ./video.mp4 --fps 15 --start_t 2.0 --end_t 5.0 --output animation.gif
```

### Generate a QR Code

```bash
dynamo-qr-code --url "https://dynamicmobility.github.io/" --logo lab_icon.svg --logo_style integrate --logo_ratio 0.4 --logo_color "#eaaa00" --output link.png
```

### Convert a TeX File (or a Math Expression) to an Image

```bash
dynamo-tex2img --input equation.tex --output equation.svg
dynamo-tex2img --math "E = mc^2" --output equation.png
```

## Dependencies

| Package | Version |
|:--------|:--------|
| Python | >= 3.8 |
| opencv-python | >= 4.0.0 |
| numpy | >= 1.20.0 |
| tqdm | >= 4.0.0 |
| Pillow | >= 8.0.0 |
| qrcode | >= 7.0.0 |
| cairosvg *(optional, for SVG logos)* | >= 2.5.0 |

---

## License

All Rights Reserved 2023

## Credits

Composite Video Generation: renyunfan (renyf@connect.hku.hk)
Claude!
