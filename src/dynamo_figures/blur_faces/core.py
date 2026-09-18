"""
    File: core.py
    Description: FaceBlur, the high-level API for anonymizing faces in images
    and videos. Combines a detector (detectors.py), a tracker (tracking.py),
    an obscurer (obscure.py), and threaded video I/O (video_io.py).
"""

import os
import shutil
import tempfile
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import cv2
from tqdm import tqdm

from dynamo_figures.blur_faces.detectors import DEVICES, create_detector
from dynamo_figures.blur_faces.obscure import SHAPES, STYLES, Obscurer
from dynamo_figures.blur_faces.tracking import FaceTracker
from dynamo_figures.blur_faces.video_io import FrameReader, open_writer


class FaceBlur:
    """Class for detecting and obscuring faces in images and videos."""

    STYLES = STYLES
    SHAPES = SHAPES
    DEVICES = DEVICES

    def __init__(self, style='blur', shape='ellipse', padding=0.25,
                 score_threshold=0.6, nms_threshold=0.3, detect_max_dim=2048,
                 blur_strength=0.5, pixel_blocks=10, fill_color='black',
                 hold_frames=5, smoothing=0.5, draw_boxes=False, disable_pbar=False,
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
            smoothing: (Video) box smoothing between frames (0..1, 0 = off)
            draw_boxes: Draw detection boxes and scores instead of obscuring
            disable_pbar: Disable the progress bar for videos
            device: 'gpu' (ONNX Runtime with CUDA/CoreML), 'cpu' (OpenCV), or
                    'auto' (GPU if available, otherwise CPU)
            batch_size: (Video) number of frames detected per batch
            workers: (Video) number of CPU threads (default: number of cores)
        """
        self.obscurer = Obscurer(style, shape, padding, blur_strength,
                                 pixel_blocks, fill_color, draw_boxes)
        self.tracker = FaceTracker(hold_frames, smoothing)
        self.detector = create_detector(device, score_threshold, nms_threshold)
        self.detect_max_dim = detect_max_dim
        self.disable_pbar = disable_pbar
        self.batch_size = max(1, batch_size)
        self.workers = workers or os.cpu_count() or 4

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
        if self.detector.batched and 1 < len(smalls) < self.batch_size:
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
        return self.obscurer.apply(image, faces, inplace)

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

    def process_video(self, input_path, output_path, keep_audio=True, crf=18,
                      start_t=None, end_t=None):
        """
        Obscure faces in every frame of a video file and save the result.

        Frames are decoded on a background thread, detected in batches,
        tracked in order, obscured on a thread pool, and streamed to the
        encoder in their original order.

        Args:
            input_path: Path to the input video
            output_path: Path for the output video
            keep_audio: Copy the original audio track (requires ffmpeg)
            crf: H.264 quality when encoding with ffmpeg (lower = better)
            start_t: Trim the output to start at this many seconds in
                     (None or 0 = from the beginning)
            end_t: Trim the output to end at this many seconds in, exclusive
                   (None = to the end of the video)

        Returns:
            bool: True if successful, False otherwise
        """
        if start_t is not None and start_t < 0:
            print("Error: start_t must be >= 0.")
            return False
        if start_t is not None and end_t is not None and end_t <= start_t:
            print("Error: end_t must be greater than start_t.")
            return False

        cap = cv2.VideoCapture(input_path)
        if not cap.isOpened():
            print(f"Error: Could not open video file '{input_path}'.")
            return False

        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

        start_frame = round((start_t or 0.0) * fps)
        if start_frame and not cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame):
            print(f"Error: Could not seek to {start_t:g}s in '{input_path}'.")
            cap.release()
            return False

        ret, first = cap.read()
        if not ret:
            where = f' at {start_t:g}s' if start_frame else ''
            print(f"Error: Could not read frames from '{input_path}'{where}.")
            cap.release()
            return False

        max_frames = None
        if end_t is not None:
            max_frames = max(1, round(end_t * fps) - start_frame)
        # Use the decoded frame size, which already accounts for rotation metadata
        height, width = first.shape[:2]
        frame_count = max(0, total_frames - start_frame) or total_frames
        if max_frames is not None and frame_count:
            frame_count = min(frame_count, max_frames)
        print(f" -- Video info: {width}x{height}, {total_frames} frames, {fps:.2f} FPS")
        if start_frame or max_frames is not None:
            end_label = f'{end_t:g}s' if end_t is not None else 'end'
            print(f" -- Trimming to {(start_t or 0.0):g}s..{end_label} ({frame_count} frames)")
        print(f" -- Detector: {self.device_name}, batch size {self.batch_size}, {self.workers} worker(s)")

        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        tmp_dir = tempfile.mkdtemp(prefix='blur_faces_')
        try:
            writer = open_writer(output_path, width, height, fps, crf,
                                 audio_source=input_path if keep_audio else None, log_dir=tmp_dir,
                                 audio_start=start_frame / fps if (start_frame or max_frames is not None) else None)
        except IOError as e:
            print(f"Error: {e}")
            cap.release()
            shutil.rmtree(tmp_dir, ignore_errors=True)
            return False

        reader = FrameReader(cap, first, max_queue=self.batch_size * 2,
                             max_frames=max_frames).start()

        # Many single-threaded workers beat OpenCV's own internal threading here
        prev_threads = cv2.getNumThreads()
        cv2.setNumThreads(1)
        executor = ThreadPoolExecutor(self.workers)
        self.detector.executor = executor

        self.tracker.reset()
        total_faces = 0
        frames_with_faces = 0
        pending = deque()
        success = True
        try:
            with tqdm(total=frame_count, disable=self.disable_pbar, desc="Processing") as pbar:
                for batch in reader.batches(self.batch_size):
                    for frame, detections in zip(batch, self.detect_batch(batch)):
                        total_faces += len(detections)
                        frames_with_faces += bool(detections)
                        # Tracking depends on frame order, so it stays on this thread
                        faces = self.tracker.update(detections)
                        pending.append(executor.submit(self.apply, frame, faces, True))

                    # Write finished frames in order, keeping a bounded backlog
                    while pending and (pending[0].done() or len(pending) > self.workers * 2):
                        writer.write(pending.popleft().result())
                        pbar.update(1)
                while pending:
                    writer.write(pending.popleft().result())
                    pbar.update(1)
        except BrokenPipeError:
            success = False
        finally:
            reader.close()
            cap.release()
            executor.shutdown(wait=True)
            cv2.setNumThreads(prev_threads)
            self.detector.executor = None
            success = writer.close() and success
            shutil.rmtree(tmp_dir, ignore_errors=True)

        print(f" -- Faces found in {frames_with_faces} frame(s), {total_faces} detection(s) total")
        if not success:
            return False
        print(f" -- Output saved to: {output_path}")
        return True
