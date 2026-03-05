---
layout: default
title: API Reference
nav_order: 5
description: "Complete API reference for Dynamo Figures Python package."
---

# API Reference
{: .fs-9 }

Complete reference for the Dynamo Figures Python API.
{: .fs-6 .fw-300 }

---

## Table of Contents

- [CompositeMode](#class-compositemode)
- [CompositeImage](#class-compositeimage)
- [FrameExtractor](#class-frameextractor)
- [VideoToGif](#class-videotogif)

---

## Module: `dynamo_figures.composite_image`

### Class: `CompositeMode`

Enumeration of available composite image modes.

```python
from dynamo_figures import CompositeMode
```

| Value | Name | Description |
|:------|:-----|:------------|
| `0` | `MAX_VARIATION` | Uses pixels furthest from the mean |
| `1` | `MIN_VALUE` | Keeps darkest pixels |
| `2` | `MAX_VALUE` | Keeps lightest pixels |

---

### Class: `CompositeImage`

Main class for creating composite images from video files.

#### Constructor

```python
CompositeImage(
    mode: CompositeMode,
    video_path: str,
    start_t: float = 0,
    end_t: float = 999,
    skip_frame: int = 1,
    alpha: float = 0.5,
    disable_pbar: bool = False
)
```

**Parameters:**

| Parameter | Type | Default | Description |
|:----------|:-----|:--------|:------------|
| `mode` | `CompositeMode` | Required | Composition mode |
| `video_path` | `str` | Required | Path to input video |
| `start_t` | `float` | `0` | Start time in seconds |
| `end_t` | `float` | `999` | End time in seconds |
| `skip_frame` | `int` | `1` | Frames to skip |
| `alpha` | `float` | `0.5` | Alpha blending (0.0-1.0) |
| `disable_pbar` | `bool` | `False` | Disable progress bar |

#### Methods

##### `extract_frames()`

Extract frames from the video file.

```python
frames = merger.extract_frames()
```

**Returns:** `list[numpy.ndarray]` - List of frames as numpy arrays

---

##### `merge_images()`

Create a composite image from extracted frames.

```python
result = merger.merge_images()
```

**Returns:** `numpy.ndarray` - The composite image

---

## Module: `dynamo_figures.pic_from_video`

### Class: `FrameExtractor`

Class for extracting individual frames from video files.

#### Constructor

```python
FrameExtractor(
    video_path: str,
    frame_number: int = None,
    time_seconds: float = None
)
```

**Parameters:**

| Parameter | Type | Default | Description |
|:----------|:-----|:--------|:------------|
| `video_path` | `str` | Required | Path to input video |
| `frame_number` | `int` | `None` | Frame to extract (0-indexed) |
| `time_seconds` | `float` | `None` | Time in seconds |

{: .note }
> If neither `frame_number` nor `time_seconds` is specified, the middle frame will be extracted.

#### Properties

| Property | Type | Description |
|:---------|:-----|:------------|
| `video_path` | `str` | Path to the video file |
| `frame_number` | `int` | Target frame number |
| `time_seconds` | `float` | Target time in seconds |
| `fps` | `float` | Video frames per second |
| `frame_count` | `int` | Total frame count |
| `width` | `int` | Video width in pixels |
| `height` | `int` | Video height in pixels |
| `duration` | `float` | Video duration in seconds |

#### Methods

##### `get_video_info()`

Get video information without extracting a frame.

```python
info = extractor.get_video_info()
```

**Returns:** `dict` or `None` - Video information dictionary

**Dictionary keys:**

| Key | Type | Description |
|:----|:-----|:------------|
| `path` | `str` | Video file path |
| `width` | `int` | Width in pixels |
| `height` | `int` | Height in pixels |
| `frame_count` | `int` | Total frames |
| `fps` | `float` | Frames per second |
| `duration` | `float` | Duration in seconds |

---

##### `extract_frame(output_path)`

Extract a frame and save it to a file.

```python
success = extractor.extract_frame("output.jpg")
```

**Parameters:**

| Parameter | Type | Description |
|:----------|:-----|:------------|
| `output_path` | `str` | Path to save the image |

**Returns:** `bool` - `True` if successful, `False` otherwise

---

## Usage Examples

### Create Composite Image

```python
from dynamo_figures import CompositeImage, CompositeMode
import cv2

# Initialize with VAR mode
merger = CompositeImage(
    mode=CompositeMode.MAX_VARIATION,
    video_path="input.mp4",
    start_t=0,
    end_t=30,
    skip_frame=2,
    alpha=0.4
)

# Generate and save
result = merger.merge_images()
cv2.imwrite("composite.jpg", result)
```

### Extract Frame at Specific Time

```python
from dynamo_figures.pic_from_video import FrameExtractor

extractor = FrameExtractor(
    video_path="input.mp4",
    time_seconds=15.0
)

extractor.extract_frame("frame_at_15s.jpg")
```

### Get Video Information

```python
from dynamo_figures.pic_from_video import FrameExtractor

extractor = FrameExtractor(video_path="input.mp4")
info = extractor.get_video_info()

print(f"Duration: {info['duration']:.2f}s")
print(f"Resolution: {info['width']}x{info['height']}")
print(f"Frame Rate: {info['fps']:.2f} FPS")
```

### Batch Processing

```python
from dynamo_figures.pic_from_video import FrameExtractor
from pathlib import Path

video_files = Path("videos").glob("*.mp4")

for video in video_files:
    extractor = FrameExtractor(video_path=str(video))
    output = f"frames/{video.stem}_frame.jpg"
    extractor.extract_frame(output)
    print(f"Extracted: {output}")
```

---

## Module: `dynamo_figures.video_to_gif`

### Class: `VideoToGif`

Class for converting video files to animated GIFs.

#### Constructor

```python
VideoToGif(
    video_path: str,
    fps: int = 10,
    start_t: float = 0,
    end_t: float = None,
    scale: float = 1.0,
    width: int = None,
    loop: int = 0,
    optimize: bool = True,
    reverse: bool = False,
    disable_pbar: bool = False
)
```

**Parameters:**

| Parameter | Type | Default | Description |
|:----------|:-----|:--------|:------------|
| `video_path` | `str` | Required | Path to input video |
| `fps` | `int` | `10` | Output GIF frame rate |
| `start_t` | `float` | `0` | Start time in seconds |
| `end_t` | `float` | `None` | End time in seconds (None = end of video) |
| `scale` | `float` | `1.0` | Scale factor for output (0.01-2.0) |
| `width` | `int` | `None` | Target width in pixels (overrides scale) |
| `loop` | `int` | `0` | Number of loops (0 = infinite) |
| `optimize` | `bool` | `True` | Optimize GIF for smaller size |
| `reverse` | `bool` | `False` | Add reverse frames (boomerang) |
| `disable_pbar` | `bool` | `False` | Disable progress bar |

#### Properties

| Property | Type | Description |
|:---------|:-----|:------------|
| `video_path` | `str` | Path to the video file |
| `fps` | `int` | Output frame rate |
| `start_t` | `float` | Start time in seconds |
| `end_t` | `float` | End time in seconds |
| `scale` | `float` | Scale factor |
| `width` | `int` | Target width |
| `video_fps` | `float` | Source video FPS (after loading) |
| `video_duration` | `float` | Source video duration (after loading) |

#### Methods

##### `get_video_info()`

Get video information without extracting frames.

```python
info = converter.get_video_info()
```

**Returns:** `dict` or `None` - Video information dictionary

---

##### `extract_frames()`

Extract frames from the video file.

```python
frames = converter.extract_frames()
```

**Returns:** `list[numpy.ndarray]` or `None` - List of frames as RGB numpy arrays

---

##### `convert(output_path)`

Convert video to GIF and save to file.

```python
success = converter.convert("output.gif")
```

**Parameters:**

| Parameter | Type | Description |
|:----------|:-----|:------------|
| `output_path` | `str` | Path to save the GIF |

**Returns:** `bool` - `True` if successful, `False` otherwise

---

### Convert Video to GIF

```python
from dynamo_figures.video_to_gif import VideoToGif

converter = VideoToGif(
    video_path="input.mp4",
    fps=15,
    start_t=2.0,
    end_t=5.0,
    scale=0.5,
    reverse=True
)

converter.convert("output.gif")
```

### Create Boomerang GIF

```python
from dynamo_figures.video_to_gif import VideoToGif

converter = VideoToGif(
    video_path="input.mp4",
    fps=12,
    reverse=True
)

converter.convert("boomerang.gif")
```
