#!/usr/bin/env python3
"""
    File: blur_faces.py
    Description: A python script to anonymize faces in a photo or video.
    Detects faces with OpenCV's YuNet model (bundled with the package, runs
    fully locally) and obscures them with a blur, pixelation, or solid fill.
    Detection runs on the GPU through ONNX Runtime (CoreML on Apple Silicon,
    CUDA on NVIDIA) when it is installed, and on the CPU through OpenCV
    otherwise. For videos, frames are decoded, detected in batches, obscured,
    and encoded in parallel; detections are held for a few frames to avoid
    flicker, and the original audio is preserved when ffmpeg is available.
"""

import argparse
import os
import queue
import shutil
import subprocess
import sys
import tempfile
import threading
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import cv2
import numpy as np
from PIL import ImageColor
from tqdm import tqdm

MODEL_PATH = Path(__file__).parent / 'models' / 'face_detection_yunet_2023mar.onnx'

IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.bmp', '.tif', '.tiff', '.webp'}
VIDEO_EXTENSIONS = {'.mp4', '.mov', '.avi', '.mkv', '.m4v', '.webm', '.wmv'}

YUNET_STRIDES = (8, 16, 32)
GPU_PROVIDERS = ('CUDAExecutionProvider', 'CoreMLExecutionProvider')


def _iou(a, b):
    """Intersection-over-union of two (x, y, w, h) boxes."""
    ax2, ay2 = a[0] + a[2], a[1] + a[3]
    bx2, by2 = b[0] + b[2], b[1] + b[3]
    iw = max(0.0, min(ax2, bx2) - max(a[0], b[0]))
    ih = max(0.0, min(ay2, by2) - max(a[1], b[1]))
    inter = iw * ih
    union = a[2] * a[3] + b[2] * b[3] - inter
    return inter / union if union > 0 else 0.0


def gpu_provider():
    """
    Return the name of the ONNX Runtime GPU provider available on this machine.

    Returns:
        str: 'CUDAExecutionProvider', 'CoreMLExecutionProvider', or None
    """
    try:
        import onnxruntime as ort
    except ImportError:
        return None
    if hasattr(ort, 'preload_dlls'):
        # Load CUDA/cuDNN libraries installed via pip (onnxruntime-gpu[cuda,cudnn])
        try:
            ort.preload_dlls()
        except Exception:
            pass
    available = ort.get_available_providers()
    for provider in GPU_PROVIDERS:
        if provider in available:
            return provider
    return None


class _OpenCVDetector:
    """YuNet via OpenCV's FaceDetectorYN (CPU). One detector per thread."""

    name = 'OpenCV (CPU)'

    def __init__(self, score_threshold, nms_threshold):
        self.score_threshold = score_threshold
        self.nms_threshold = nms_threshold
        self.executor = None
        self._local = threading.local()

    def _detector(self):
        if not hasattr(self._local, 'detector'):
            self._local.detector = cv2.FaceDetectorYN.create(
                str(MODEL_PATH), '', (320, 320), self.score_threshold, self.nms_threshold, 5000
            )
        return self._local.detector

    def _detect_one(self, image):
        detector = self._detector()
        detector.setInputSize((image.shape[1], image.shape[0]))
        _, faces = detector.detect(image)
        if faces is None:
            return []
        return [(f[0], f[1], f[2], f[3], float(f[14])) for f in faces]

    def detect_batch(self, images):
        if self.executor is None or len(images) == 1:
            return [self._detect_one(im) for im in images]
        return list(self.executor.map(self._detect_one, images))


class _OnnxDetector:
    """YuNet via ONNX Runtime (CoreML / CUDA / CPU), with batched inference."""

    def __init__(self, score_threshold, nms_threshold, provider):
        import onnxruntime as ort
        self.ort = ort
        self.score_threshold = score_threshold
        self.nms_threshold = nms_threshold
        self.provider = provider
        self._sessions = {}
        self._anchors = {}
        self._blob = None
        self.executor = None
        self.name =f"ONNX Runtime ({provider.replace('ExecutionProvider', '')})"

    def _providers(self):
        if self.provider == 'CoreMLExecutionProvider':
            return [(self.provider, {'ModelFormat': 'MLProgram', 'MLComputeUnits': 'CPUAndGPU'}),
                    'CPUExecutionProvider']
        return [self.provider, 'CPUExecutionProvider']

    def _session(self, batch, height, width):
        key = (batch, height, width)
        if key not in self._sessions:
            options = self.ort.SessionOptions()
            options.log_severity_level = 3
            # Fixed shapes let CoreML/CUDA compile an optimized graph for this size
            options.add_free_dimension_override_by_name('batch', batch)
            options.add_free_dimension_override_by_name('height', height)
            options.add_free_dimension_override_by_name('width', width)
            try:
                session = self.ort.InferenceSession(str(MODEL_PATH), options, providers=self._providers())
            except Exception:
                # Older onnxruntime versions don't accept CoreML provider options
                session = self.ort.InferenceSession(str(MODEL_PATH), options,
                                                    providers=[self.provider, 'CPUExecutionProvider'])
            if self.provider not in session.get_providers():
                # e.g. CUDA/cuDNN libraries missing; onnxruntime silently falls back to CPU
                print(f" -- Warning: {self.provider} failed to initialize; detection is running on the CPU")
                self.name = 'ONNX Runtime (CPU fallback)'
            self._sessions[key] = session
        return self._sessions[key]

    def _grid(self, height, width):
        """Anchor (col, row, stride) arrays for every output position, cached per size."""
        key = (height, width)
        if key not in self._anchors:
            grids = []
            for s in YUNET_STRIDES:
                rows, cols = height // s, width // s
                c, r = np.meshgrid(np.arange(cols, dtype=np.float32), np.arange(rows, dtype=np.float32))
                grids.append((c.ravel(), r.ravel(), s))
            self._anchors[key] = grids
        return self._anchors[key]

    def detect_batch(self, images):
        h, w = images[0].shape[:2]
        # YuNet needs dimensions divisible by 32; pad bottom/right with zeros like OpenCV does
        ph, pw = -(-h // 32) * 32, -(-w // 32) * 32
        shape = (len(images), 3, ph, pw)
        if self._blob is None or self._blob.shape != shape:
            self._blob = np.zeros(shape, dtype=np.float32)
        blob = self._blob

        def fill(i):
            for ch in range(3):
                blob[i, ch, :h, :w] = images[i][:, :, ch]

        # HWC uint8 -> NCHW float32 is the slowest step per frame, so spread it across threads
        if self.executor is None:
            for i in range(len(images)):
                fill(i)
        else:
            list(self.executor.map(fill, range(len(images))))

        session = self._session(len(images), ph, pw)
        # The model's reshapes hard-code batch 1, flattening the batch into one row; split it back out
        n = len(images)
        outputs = {o.name: v.reshape(n, -1, v.shape[-1])
                   for o, v in zip(session.get_outputs(), session.run(None, {'input': blob}))}

        results = [[] for _ in images]
        for c, r, s in self._grid(ph, pw):
            cls = np.clip(outputs[f'cls_{s}'][..., 0], 0, 1)
            obj = np.clip(outputs[f'obj_{s}'][..., 0], 0, 1)
            scores = np.sqrt(cls * obj)
            bbox = outputs[f'bbox_{s}']
            for i in range(len(images)):
                keep = scores[i] >= self.score_threshold
                if not keep.any():
                    continue
                b = bbox[i][keep]
                bw, bh = np.exp(b[:, 2]) * s, np.exp(b[:, 3]) * s
                x = (c[keep] + b[:, 0]) * s - bw / 2
                y = (r[keep] + b[:, 1]) * s - bh / 2
                results[i].extend(zip(x, y, bw, bh, scores[i][keep]))

        final = []
        for faces in results:
            if not faces:
                final.append([])
                continue
            boxes = [[float(f[0]), float(f[1]), float(f[2]), float(f[3])] for f in faces]
            scores = [float(f[4]) for f in faces]
            idx = cv2.dnn.NMSBoxes(boxes, scores, self.score_threshold, self.nms_threshold, top_k=5000)
            final.append([(*boxes[j], scores[j]) for j in np.array(idx).ravel()])
        return final


class FaceBlur:
    """Class for detecting and obscuring faces in images and videos."""

    STYLES = ('blur', 'pixelate', 'fill')
    SHAPES = ('ellipse', 'rect')
    DEVICES = ('auto', 'gpu', 'cpu')

    def __init__(self, style='blur', shape='ellipse', padding=0.25,
                 score_threshold=0.6, nms_threshold=0.3, detect_max_dim=2048,
                 blur_strength=0.5, pixel_blocks=10, fill_color='black',
                 hold_frames=5, draw_boxes=False, disable_pbar=False,
                 device='auto', batch_size=8, workers=None):
        """
        Initialize FaceBlur.

        Args:
            style: How to obscure faces: 'blur', 'pixelate', or 'fill'
            shape: Region shape to obscure: 'ellipse' or 'rect'
            padding: Fraction to enlarge each face box by on every side
            score_threshold: Minimum detector confidence (0..1)
            nms_threshold: Non-maximum suppression IoU threshold (0..1)
            detect_max_dim: Downscale frames so the longest side is at most this
                            many pixels before detection (0 = full resolution)
            blur_strength: Blur kernel size as a fraction of face size
            pixel_blocks: Number of mosaic blocks across each face (pixelate)
            fill_color: Color name or hex code for the 'fill' style
            hold_frames: (Video) keep obscuring a face for this many frames
                         after the detector loses it
            draw_boxes: Draw detection boxes and scores instead of obscuring
            disable_pbar: Disable the progress bar for videos
            device: 'gpu' (ONNX Runtime with CUDA/CoreML), 'cpu' (OpenCV), or
                    'auto' (GPU if available, otherwise CPU)
            batch_size: (Video) number of frames detected per batch
            workers: (Video) number of CPU threads (default: number of cores)
        """
        if style not in self.STYLES:
            raise ValueError(f"style must be one of {self.STYLES}")
        if shape not in self.SHAPES:
            raise ValueError(f"shape must be one of {self.SHAPES}")
        if device not in self.DEVICES:
            raise ValueError(f"device must be one of {self.DEVICES}")
        if not MODEL_PATH.exists():
            raise FileNotFoundError(f"Face detection model not found at '{MODEL_PATH}'")

        self.style = style
        self.shape = shape
        self.padding = padding
        self.detect_max_dim = detect_max_dim
        self.blur_strength = blur_strength
        self.pixel_blocks = max(1, pixel_blocks)
        r, g, b = ImageColor.getrgb(fill_color)[:3]
        self.fill_color = (b, g, r)
        self.hold_frames = max(0, hold_frames)
        self.draw_boxes = draw_boxes
        self.disable_pbar = disable_pbar
        self.batch_size = max(1, batch_size)
        self.workers = workers or os.cpu_count() or 4

        provider = gpu_provider() if device != 'cpu' else None
        if device == 'gpu' and provider is None:
            print(" -- Warning: no GPU provider found (install onnxruntime / onnxruntime-gpu); using CPU")
        if provider is not None:
            self.detector = _OnnxDetector(score_threshold, nms_threshold, provider)
        else:
            self.detector = _OpenCVDetector(score_threshold, nms_threshold)
        self._tracks = []  # list of [box, score, frames_since_seen]

    @property
    def device_name(self):
        """Human-readable name of the detection backend."""
        return self.detector.name

    def _downscale(self, image):
        """Resize an image for detection; returns (image, scale)."""
        h, w = image.shape[:2]
        if self.detect_max_dim and max(h, w) > self.detect_max_dim:
            scale = self.detect_max_dim / max(h, w)
            small = cv2.resize(image, (round(w * scale), round(h * scale)),
                               interpolation=cv2.INTER_AREA)
            return small, scale
        return image, 1.0

    def detect_batch(self, images):
        """
        Detect faces in a list of same-sized images.

        Args:
            images: list of BGR images (numpy arrays) with identical shapes

        Returns:
            list: one list of (x, y, w, h, score) tuples per image, in
                  original image coordinates
        """
        scaled = [self._downscale(im) for im in images]
        scale = scaled[0][1]
        smalls = [s[0] for s in scaled]
        if len(smalls) < self.batch_size and isinstance(self.detector, _OnnxDetector) and len(images) > 1:
            # Pad partial batches so the GPU session for this batch size is reused
            smalls = smalls + [smalls[-1]] * (self.batch_size - len(smalls))
        detections = self.detector.detect_batch(smalls)[:len(images)]
        return [[(x / scale, y / scale, w / scale, h / scale, s) for x, y, w, h, s in faces]
                for faces in detections]

    def detect(self, image):
        """
        Detect faces in an image.

        Args:
            image: BGR image (numpy array)

        Returns:
            list: (x, y, w, h, score) tuples in original image coordinates
        """
        return self.detect_batch([image])[0]

    def _update_tracks(self, detections):
        """Match detections to held boxes so briefly-missed faces stay obscured."""
        unmatched = list(detections)
        for track in self._tracks:
            best, best_iou = None, 0.1
            for det in unmatched:
                overlap = _iou(track[0], det[:4])
                if overlap > best_iou:
                    best, best_iou = det, overlap
            if best is not None:
                unmatched.remove(best)
                track[0], track[1], track[2] = best[:4], best[4], 0
            else:
                track[2] += 1
        self._tracks = [t for t in self._tracks if t[2] <= self.hold_frames]
        self._tracks += [[d[:4], d[4], 0] for d in unmatched]
        return [(*t[0], t[1]) for t in self._tracks]

    def _padded_box(self, box, img_w, img_h):
        """Enlarge a box by the padding fraction and clip it to the image."""
        x, y, w, h = box[:4]
        # YuNet boxes are tight around the face; extend upward a bit more to cover the forehead/hair
        x0 = int(max(0, x - w * self.padding))
        x1 = int(min(img_w, x + w * (1 + self.padding)))
        y0 = int(max(0, y - h * self.padding * 1.4))
        y1 = int(min(img_h, y + h * (1 + self.padding)))
        return x0, y0, x1, y1

    def _obscured_roi(self, roi):
        """Return an obscured version of a region of interest."""
        rh, rw = roi.shape[:2]
        if self.style == 'fill':
            return np.full_like(roi, self.fill_color)
        if self.style == 'pixelate':
            bw = self.pixel_blocks
            bh = max(1, round(self.pixel_blocks * rh / rw))
            small = cv2.resize(roi, (bw, bh), interpolation=cv2.INTER_AREA)
            return cv2.resize(small, (rw, rh), interpolation=cv2.INTER_NEAREST)
        # Blur a downscaled copy so large faces stay fast, then upscale
        factor = max(1, max(rh, rw) // 128)
        small = cv2.resize(roi, (max(1, rw // factor), max(1, rh // factor)),
                           interpolation=cv2.INTER_AREA)
        k = int(max(small.shape[:2]) * self.blur_strength) | 1
        small = cv2.GaussianBlur(small, (k, k), 0)
        small = cv2.GaussianBlur(small, (k, k), 0)
        return cv2.resize(small, (rw, rh), interpolation=cv2.INTER_LINEAR)

    def apply(self, image, faces, inplace=False):
        """
        Obscure (or annotate) the given faces in an image.

        Args:
            image: BGR image (numpy array)
            faces: list of (x, y, w, h, score) tuples
            inplace: modify image directly instead of a copy

        Returns:
            numpy array: the processed image
        """
        out = image if inplace else image.copy()
        img_h, img_w = image.shape[:2]
        for face in faces:
            x0, y0, x1, y1 = self._padded_box(face, img_w, img_h)
            if x1 - x0 < 2 or y1 - y0 < 2:
                continue

            if self.draw_boxes:
                t = max(2, img_w // 500)
                cv2.rectangle(out, (x0, y0), (x1, y1), (0, 255, 0), t)
                cv2.putText(out, f"{face[4]:.2f}", (x0, max(0, y0 - 2 * t)),
                            cv2.FONT_HERSHEY_SIMPLEX, t / 3, (0, 255, 0), t)
                continue

            roi = out[y0:y1, x0:x1]
            obscured = self._obscured_roi(roi)
            if self.shape == 'rect':
                out[y0:y1, x0:x1] = obscured
                continue

            mask = np.zeros(roi.shape[:2], dtype=np.float32)
            cx, cy = (x1 - x0) // 2, (y1 - y0) // 2
            cv2.ellipse(mask, (cx, cy), (cx, cy), 0, 0, 360, 1.0, -1)
            if self.style != 'fill':
                # Feather the edge so the blur blends in
                k = max(3, int(min(roi.shape[:2]) * 0.1) | 1)
                mask = cv2.GaussianBlur(mask, (k, k), 0)
            mask = mask[..., None]
            out[y0:y1, x0:x1] = (obscured * mask + roi * (1 - mask)).astype(np.uint8)
        return out

    def process_image(self, input_path, output_path):
        """
        Obscure faces in an image file and save the result.

        Returns:
            bool: True if successful, False otherwise
        """
        image = cv2.imread(input_path)
        if image is None:
            print(f"Error: Could not read image '{input_path}'.")
            return False

        print(f" -- Image info: {image.shape[1]}x{image.shape[0]}")
        faces = self.detect(image)
        print(f" -- Detected {len(faces)} face(s)")
        result = self.apply(image, faces, inplace=True)

        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        if not cv2.imwrite(output_path, result):
            print(f"Error: Could not save image to '{output_path}'")
            return False
        print(f" -- Output saved to: {output_path}")
        return True

    @staticmethod
    def _read_frames(cap, first_frame, frames_queue, stop):
        """Decode frames on a background thread."""
        frames_queue.put(first_frame)
        while not stop.is_set():
            ret, frame = cap.read()
            if not ret:
                break
            frames_queue.put(frame)
        frames_queue.put(None)

    def _open_writer(self, input_path, output_path, width, height, fps, keep_audio, crf, tmp_dir):
        """
        Start the output encoder.

        Returns:
            tuple: (write function, close function returning bool)
        """
        ffmpeg = shutil.which('ffmpeg')
        if ffmpeg is None:
            print(" -- Warning: ffmpeg not found; output will have no audio and use the mp4v codec")
            writer = cv2.VideoWriter(output_path, cv2.VideoWriter_fourcc(*'mp4v'), fps, (width, height))
            if not writer.isOpened():
                return None, None

            def close():
                writer.release()
                return True
            return writer.write, close

        # Stream raw frames straight into ffmpeg so encoding runs in parallel
        cmd = [ffmpeg, '-y', '-loglevel', 'error',
               '-f', 'rawvideo', '-pix_fmt', 'bgr24', '-s', f'{width}x{height}', '-r', f'{fps}', '-i', '-']
        if keep_audio:
            cmd += ['-i', input_path, '-map', '0:v:0', '-map', '1:a?', '-c:a', 'copy']
        cmd += ['-vf', 'pad=ceil(iw/2)*2:ceil(ih/2)*2',  # yuv420p needs even dimensions
                '-c:v', 'libx264', '-crf', str(crf), '-pix_fmt', 'yuv420p',
                '-movflags', '+faststart', output_path]
        log = open(os.path.join(tmp_dir, 'ffmpeg.log'), 'w+')
        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=log)

        def write(frame):
            proc.stdin.write(frame.tobytes())

        def close():
            try:
                proc.stdin.close()
            except BrokenPipeError:
                pass
            code = proc.wait()
            log.seek(0)
            err = log.read().strip()
            log.close()
            if code != 0:
                print(f"Error: ffmpeg failed: {err}")
            return code == 0
        return write, close

    def process_video(self, input_path, output_path, keep_audio=True, crf=18):
        """
        Obscure faces in every frame of a video file and save the result.

        Args:
            input_path: Path to the input video
            output_path: Path for the output video
            keep_audio: Copy the original audio track (requires ffmpeg)
            crf: H.264 quality when encoding with ffmpeg (lower = better)

        Returns:
            bool: True if successful, False otherwise
        """
        cap = cv2.VideoCapture(input_path)
        if not cap.isOpened():
            print(f"Error: Could not open video file '{input_path}'.")
            return False

        ret, first = cap.read()
        if not ret:
            print(f"Error: Could not read frames from '{input_path}'.")
            cap.release()
            return False

        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        # Use the decoded frame size, which already accounts for rotation metadata
        height, width = first.shape[:2]
        frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        print(f" -- Video info: {width}x{height}, {frame_count} frames, {fps:.2f} FPS")
        print(f" -- Detector: {self.device_name}, batch size {self.batch_size}, {self.workers} worker(s)")

        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        tmp_dir = tempfile.mkdtemp(prefix='blur_faces_')
        write, close = self._open_writer(input_path, output_path, width, height, fps, keep_audio, crf, tmp_dir)
        if write is None:
            print(f"Error: Could not open video writer for '{output_path}'")
            cap.release()
            shutil.rmtree(tmp_dir, ignore_errors=True)
            return False

        frames_queue = queue.Queue(maxsize=self.batch_size * 2)
        stop = threading.Event()
        reader = threading.Thread(target=self._read_frames, args=(cap, first, frames_queue, stop), daemon=True)

        # One thread each for OpenCV's own ops is slower than many single-threaded workers
        prev_threads = cv2.getNumThreads()
        cv2.setNumThreads(1)
        executor = ThreadPoolExecutor(self.workers)
        self.detector.executor = executor

        self._tracks = []
        total_faces = 0
        frames_with_faces = 0
        pending = deque()
        success = True
        reader.start()
        try:
            with tqdm(total=frame_count, disable=self.disable_pbar, desc="Processing") as pbar:
                done = False
                while not done:
                    batch = []
                    while len(batch) < self.batch_size:
                        frame = frames_queue.get()
                        if frame is None:
                            done = True
                            break
                        batch.append(frame)
                    if not batch:
                        break

                    for frame, detections in zip(batch, self.detect_batch(batch)):
                        total_faces += len(detections)
                        frames_with_faces += bool(detections)
                        # Tracking depends on frame order, so it stays on this thread
                        faces = self._update_tracks(detections) if self.hold_frames else detections
                        pending.append(executor.submit(self.apply, frame, faces, True))

                    # Write finished frames in order, keeping a bounded backlog
                    while pending and (pending[0].done() or len(pending) > self.workers * 2):
                        write(pending.popleft().result())
                        pbar.update(1)
                while pending:
                    write(pending.popleft().result())
                    pbar.update(1)
        except BrokenPipeError:
            success = False
        finally:
            stop.set()
            # Unblock the reader if it is waiting on a full queue
            while reader.is_alive():
                try:
                    frames_queue.get_nowait()
                except queue.Empty:
                    reader.join(timeout=0.1)
            cap.release()
            executor.shutdown(wait=True)
            cv2.setNumThreads(prev_threads)
            self.detector.executor = None
            success = close() and success
            shutil.rmtree(tmp_dir, ignore_errors=True)

        print(f" -- Faces found in {frames_with_faces} frame(s), {total_faces} detection(s) total")
        if not success:
            return False
        print(f" -- Output saved to: {output_path}")
        return True


def main():
    """Main function for command-line interface."""
    parser = argparse.ArgumentParser(
        prog='blur-faces',
        description='Blur, pixelate, or cover faces in a photo or video. Runs fully locally.',
        epilog='-'
    )
    parser.add_argument('--input', type=str, required=True,
                        help='path of input image or video file.')
    parser.add_argument('--output', type=str, default=None,
                        help='output file path (default: same directory as input with _blurred suffix)')
    parser.add_argument('--style', default='blur', choices=FaceBlur.STYLES,
                        help='how to obscure faces (default: blur)')
    parser.add_argument('--shape', default='ellipse', choices=FaceBlur.SHAPES,
                        help='shape of the obscured region (default: ellipse)')
    parser.add_argument('--padding', type=float, default=0.25,
                        help='fraction to enlarge each face box on every side (default: 0.25)')
    parser.add_argument('--blur_strength', type=float, default=0.5,
                        help='blur kernel size as a fraction of face size, for --style blur (default: 0.5)')
    parser.add_argument('--pixel_blocks', type=int, default=10,
                        help='number of mosaic blocks across each face, for --style pixelate (default: 10)')
    parser.add_argument('--fill_color', type=str, default='black',
                        help='color name or hex code, for --style fill (default: black)')
    parser.add_argument('--score_threshold', type=float, default=0.6,
                        help='minimum detection confidence 0..1; lower catches more faces but more false positives (default: 0.6)')
    parser.add_argument('--nms_threshold', type=float, default=0.3,
                        help='overlap threshold for merging duplicate detections (default: 0.3)')
    parser.add_argument('--detect_max_dim', type=int, default=2048,
                        help='downscale so the longest side is at most this before detection; '
                             'raise for tiny faces, lower for speed, 0 = full resolution (default: 2048)')
    parser.add_argument('--device', default='auto', choices=FaceBlur.DEVICES,
                        help='detection device: gpu needs onnxruntime (CoreML) or onnxruntime-gpu (CUDA); '
                             'auto uses the GPU when available (default: auto)')
    parser.add_argument('--batch_size', type=int, default=8,
                        help='video only: frames detected per batch (default: 8)')
    parser.add_argument('--workers', type=int, default=None,
                        help='video only: CPU threads for detection/blurring (default: number of cores)')
    parser.add_argument('--hold_frames', type=int, default=5,
                        help='video only: keep obscuring a face for this many frames after it is lost (default: 5)')
    parser.add_argument('--no_audio', action='store_true',
                        help='video only: drop the audio track')
    parser.add_argument('--crf', type=int, default=18,
                        help='video only: H.264 quality, lower is better (default: 18)')
    parser.add_argument('--draw_boxes', action='store_true',
                        help='draw detection boxes and scores instead of obscuring (for tuning)')
    parser.add_argument('--disable_pbar', action='store_true',
                        help='disable progress bar when processing videos')

    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"Error: Input file '{input_path}' not found.")
        sys.exit(1)

    ext = input_path.suffix.lower()
    if ext in IMAGE_EXTENSIONS:
        is_video = False
    elif ext in VIDEO_EXTENSIONS:
        is_video = True
    else:
        print(f"Error: Unsupported file type '{ext}'.")
        sys.exit(1)

    if args.output:
        output_path = args.output
    else:
        out_ext = '.mp4' if is_video else ext
        output_path = str(input_path.parent / f'{input_path.stem}_blurred{out_ext}')

    print(" -- Load Param: input", input_path)
    print(" -- Load Param: output", output_path)
    print(" -- Load Param: style", args.style)
    print(" -- Load Param: shape", args.shape)
    print(" -- Load Param: score_threshold", args.score_threshold)
    print(" -- Load Param: device", args.device)

    blurrer = FaceBlur(
        style=args.style,
        shape=args.shape,
        padding=args.padding,
        score_threshold=args.score_threshold,
        nms_threshold=args.nms_threshold,
        detect_max_dim=args.detect_max_dim,
        blur_strength=args.blur_strength,
        pixel_blocks=args.pixel_blocks,
        fill_color=args.fill_color,
        hold_frames=args.hold_frames,
        draw_boxes=args.draw_boxes,
        disable_pbar=args.disable_pbar,
        device=args.device,
        batch_size=args.batch_size,
        workers=args.workers,
    )

    if is_video:
        success = blurrer.process_video(str(input_path), output_path,
                                        keep_audio=not args.no_audio, crf=args.crf)
    else:
        success = blurrer.process_image(str(input_path), output_path)

    if not success:
        sys.exit(1)


if __name__ == "__main__":
    main()
