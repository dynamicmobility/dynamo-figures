---
layout: default
title: Home
nav_order: 1
description: "Dynamo Figures - A Python package for creating composite images and extracting frames from videos."
permalink: /
---

# Dynamo Figures
{: .fs-9 }

A Python package for creating composite images from videos and extracting individual frames.
{: .fs-6 .fw-300 }

[Get Started](#installation){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }
[View on GitHub](https://github.com/dynamicmobility/dynamo_figures){: .btn .fs-5 .mb-4 .mb-md-0 }

---

## Overview

Dynamo Figures provides powerful tools for video processing:

- **Composite Image**: Create stunning visual effects by merging video frames using various composition modes
- **Frame Extraction**: Extract single frames from videos at specific times or frame numbers

## Installation

### Install from Git

```bash
pip install git+ssh://git@github.com/dynamicmobility/dynamo_figures.git
```

### Install from Local Directory

```bash
git clone git@github.com:dynamicmobility/dynamo_figures.git
cd dynamo_figures
pip install -e .
```

## Quick Start

### Create a Composite Image

```bash
composite-image --video_path ./video.mp4 --mode VAR --alpha 0.4 --output composite.png
```

### Extract a Frame from Video

```bash
pic-from-video --video_path ./video.mp4 --time 5.0 --output frame.jpg
```

## Dependencies

| Package | Version |
|:--------|:--------|
| Python | >= 3.8 |
| opencv-python | >= 4.0.0 |
| numpy | >= 1.20.0 |
| tqdm | >= 4.0.0 |

---

## License

All Rights Reserved 2023

## Credits

Original Author: renyunfan (renyf@connect.hku.hk)
