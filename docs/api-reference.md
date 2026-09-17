---
layout: default
title: API Reference
nav_order: 7
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
- [QRCode](#class-qrcode)
- [FaceBlur](#class-faceblur)

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

---

## Module: `dynamo_figures.qr_code`

### Class: `QRCode`

Class for generating QR codes from a URL (or any text), with optional logo
embedding and recoloring.

#### Constructor

```python
QRCode(
    data: str,
    box_size: int = 10,
    border: int = 4,
    error_correction: str = 'H',
    fill_color: str = 'black',
    back_color: str = 'white',
    logo_path: str = None,
    logo_ratio: float = 0.22,
    logo_padding: float = 0.0,
    logo_bg: str = 'white',
    logo_style: str = 'badge',
    logo_halo: float = 0.04,
    logo_color: str = None
)
```

**Parameters:**

| Parameter | Type | Default | Description |
|:----------|:-----|:--------|:------------|
| `data` | `str` | Required | The URL (or text) to encode |
| `box_size` | `int` | `10` | Pixels per QR module |
| `border` | `int` | `4` | Quiet-zone width in modules (min 4) |
| `error_correction` | `str` | `'H'` | `'L'`, `'M'`, `'Q'`, or `'H'` (forced to `'H'` with a logo) |
| `fill_color` | `str` | `'black'` | Color of the QR modules |
| `back_color` | `str` | `'white'` | Background color |
| `logo_path` | `str` | `None` | Path to a logo (SVG or raster) to center |
| `logo_ratio` | `float` | `0.22` | Logo width as a fraction of the QR width |
| `logo_padding` | `float` | `0.0` | *(badge)* Badge padding, fraction of logo size |
| `logo_bg` | `str` | `'white'` | *(badge)* Badge color, or `None` for no badge |
| `logo_style` | `str` | `'badge'` | `'badge'` or `'integrate'` |
| `logo_halo` | `float` | `0.04` | *(integrate)* Halo width, fraction of logo size |
| `logo_color` | `str` | `None` | Recolor logo to a solid color, e.g. `'#eaaa00'` |

#### Methods

##### `make_image()`

Build the QR code (with the logo, if configured) as a Pillow image.

```python
img = qr.make_image()
```

**Returns:** `PIL.Image.Image` - The QR code image (RGBA)

---

##### `save(output_path)`

Generate the QR code and save it to a file. The format is chosen by the file
extension; JPEG output is flattened onto `back_color`.

```python
path = qr.save("link.png")
```

**Parameters:**

| Parameter | Type | Description |
|:----------|:-----|:------------|
| `output_path` | `str` | Path to save the image |

**Returns:** `str` - The output path

---

### Generate a QR Code with a Logo

```python
from dynamo_figures import QRCode

qr = QRCode(
    data="https://dynamicmobility.github.io/",
    logo_path="lab_icon.svg",
    logo_style="integrate",
    logo_ratio=0.4,
    logo_color="#eaaa00",
)

qr.save("link.png")
```

---

## Module: `dynamo_figures.blur_faces`

### Class: `FaceBlur`

Class for detecting faces with the bundled YuNet model and obscuring them in
images and videos. Runs fully locally.

#### Constructor

```python
FaceBlur(
    style: str = 'blur',
    shape: str = 'ellipse',
    padding: float = 0.25,
    score_threshold: float = 0.6,
    nms_threshold: float = 0.3,
    detect_max_dim: int = 2048,
    blur_strength: float = 0.5,
    pixel_blocks: int = 10,
    fill_color: str = 'black',
    hold_frames: int = 5,
    draw_boxes: bool = False,
    disable_pbar: bool = False,
    device: str = 'auto',
    batch_size: int = 8,
    workers: int = None
)
```

**Parameters:**

| Parameter | Type | Default | Description |
|:----------|:-----|:--------|:------------|
| `style` | `str` | `'blur'` | `'blur'`, `'pixelate'`, or `'fill'` |
| `shape` | `str` | `'ellipse'` | `'ellipse'` or `'rect'` |
| `padding` | `float` | `0.25` | Fraction to enlarge each face box on every side |
| `score_threshold` | `float` | `0.6` | Minimum detection confidence (0–1) |
| `nms_threshold` | `float` | `0.3` | Non-maximum suppression IoU threshold |
| `detect_max_dim` | `int` | `2048` | Longest side, in pixels, used for detection (`0` = full resolution) |
| `blur_strength` | `float` | `0.5` | *(blur)* Kernel size as a fraction of face size |
| `pixel_blocks` | `int` | `10` | *(pixelate)* Blocks across each face |
| `fill_color` | `str` | `'black'` | *(fill)* Color name or hex code |
| `hold_frames` | `int` | `5` | *(video)* Frames to keep a lost face obscured |
| `draw_boxes` | `bool` | `False` | Draw boxes and scores instead of obscuring |
| `disable_pbar` | `bool` | `False` | Disable the video progress bar |
| `device` | `str` | `'auto'` | `'gpu'` (ONNX Runtime with CUDA/CoreML), `'cpu'` (OpenCV), or `'auto'` |
| `batch_size` | `int` | `8` | *(video)* Frames detected per batch |
| `workers` | `int` | `None` | *(video)* CPU threads; defaults to the number of cores |

**Attributes:**

- `device_name` (`str`): the detection backend in use, e.g. `'ONNX Runtime (CoreML)'`

#### Methods

##### `detect(image)`

Detect faces in a BGR image.

**Returns:** `list` - `(x, y, w, h, score)` tuples in image coordinates

---

##### `detect_batch(images)`

Detect faces in a list of same-sized BGR images. On the GPU, the images are
run through the model as one batch.

**Returns:** `list` - One list of `(x, y, w, h, score)` tuples per image

---

##### `apply(image, faces, inplace=False)`

Return `image` with the given faces obscured (or annotated, if
`draw_boxes=True`). The image is copied first unless `inplace=True`.

**Returns:** `numpy.ndarray` - The processed image

---

##### `process_image(input_path, output_path)`

Obscure faces in an image file and save the result.

**Returns:** `bool` - True if successful

---

##### `process_video(input_path, output_path, keep_audio=True, crf=18)`

Obscure faces in every frame of a video. When `ffmpeg` is available, the output
is encoded as H.264 with quality `crf`, and the original audio is kept if
`keep_audio` is set.

**Returns:** `bool` - True if successful
