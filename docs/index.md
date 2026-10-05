---
layout: default
title: Home
nav_order: 1
description: "Dynamo Figures - An internal Python package for creating figures for publications."
permalink: /
---

# Dynamo Figures
{: .fs-9 }

A package for creating figures for publications.
{: .fs-6 .fw-300 }

[Get Started](#installation){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }
[View on GitHub](https://github.com/dynamicmobility/dynamo-figures){: .btn .fs-5 .mb-4 .mb-md-0 }

---

## Overview

Dynamo Figures provides helpful, easy-to-run tools for image and video processing. Use the search bar above or the side-panel on the left to find tools you're looking for. A few common ones are listed below:

- [**Composite Image**](composite-image): Create cool visual effects by merging video frames using various composition modes
- [**Video to GIF**](video-to-gif): Convert videos to animated GIFs with frame rate and size control
- [**QR Code**](qr-code): Generate permanent QR codes from links, with optional logo embedding and recoloring
- [**Blur Faces**](blur-faces): Anonymize faces in photos and videos by blurring, pixelating, or covering them (runs fully locally)
- [**Tex2Img**](tex2img): Convert a `.tex` file into an SVG or PNG image, cropped to its content

### Contributing
Please feel free to contribute, or request new tools by [making an issue on our Github](https://github.com/dynamicmobility/dynamo-figures/issues).

## Installation

### Install from PyPI

```bash
pip install dynamo-figures
```

With GPU acceleration (note the quotes), which can speed up the blurring faces tool:

```bash
pip install "dynamo-figures[gpu]"
```

### Install from Local Directory

```bash
git clone git@github.com:dynamicmobility/dynamo-figures.git
cd dynamo-figures
pip install -e .
```

With GPU acceleration:

```bash
pip install -e ".[gpu]"
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

Composite Video Generation inspired by renyunfan (renyf@connect.hku.hk)
This codebase was built with help from AI coding agents.
