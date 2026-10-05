# Dynamo Figures

A package for creating figures for publications.

📖 **Documentation: https://dynamicmobility.github.io/dynamo-figures/**

---

## Overview

Dynamo Figures provides helpful, easy-to-run tools for image and video processing. See the [documentation website](https://dynamicmobility.github.io/dynamo-figures/) for full usage details. A few common tools are listed below:

- [**Composite Image**](https://dynamicmobility.github.io/dynamo-figures/composite-image): Create cool visual effects by merging video frames using various composition modes
- [**Video to GIF**](https://dynamicmobility.github.io/dynamo-figures/video-to-gif): Convert videos to animated GIFs with frame rate and size control
- [**QR Code**](https://dynamicmobility.github.io/dynamo-figures/qr-code): Generate permanent QR codes from links, with optional logo embedding and recoloring
- [**Blur Faces**](https://dynamicmobility.github.io/dynamo-figures/blur-faces): Anonymize faces in photos and videos by blurring, pixelating, or covering them (runs fully locally)
- [**Tex2Img**](https://dynamicmobility.github.io/dynamo-figures/tex2img): Convert a `.tex` file into an SVG or PNG image, cropped to its content

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

This software is licensed by the MIT license agreement.

## Credits

Composite Video Generation inspired by renyunfan (renyf@connect.hku.hk)
This codebase was built with help from AI coding agents.
