"""
    File: detectors.py
    Description: YuNet face detection backends.
    OpenCVDetector runs on the CPU through OpenCV's FaceDetectorYN.
    OnnxDetector runs batched inference through ONNX Runtime on CoreML
    (Apple Silicon) or CUDA (NVIDIA).
"""

import threading
from pathlib import Path

import cv2
import numpy as np

MODEL_PATH = Path(__file__).parent / 'models' / 'face_detection_yunet_2023mar.onnx'

YUNET_STRIDES = (8, 16, 32)
GPU_PROVIDERS = ('CUDAExecutionProvider', 'CoreMLExecutionProvider')
DEVICES = ('auto', 'gpu', 'cpu')


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


def create_detector(device, score_threshold, nms_threshold):
    """
    Create the best detector for the requested device.

    Args:
        device: 'gpu', 'cpu', or 'auto' (GPU if available, otherwise CPU)
        score_threshold: Minimum detector confidence (0..1)
        nms_threshold: Non-maximum suppression IoU threshold (0..1)

    Returns:
        OpenCVDetector or OnnxDetector
    """
    if device not in DEVICES:
        raise ValueError(f"device must be one of {DEVICES}")
    if not MODEL_PATH.exists():
        raise FileNotFoundError(f"Face detection model not found at '{MODEL_PATH}'")

    provider = gpu_provider() if device != 'cpu' else None
    if device == 'gpu' and provider is None:
        print(" -- Warning: no GPU provider found (install onnxruntime / onnxruntime-gpu); using CPU")
    if provider is not None:
        return OnnxDetector(score_threshold, nms_threshold, provider)
    return OpenCVDetector(score_threshold, nms_threshold)


class OpenCVDetector:
    """YuNet via OpenCV's FaceDetectorYN (CPU). One detector per thread."""

    name = 'OpenCV (CPU)'
    batched = False

    def __init__(self, score_threshold, nms_threshold):
        self.score_threshold = score_threshold
        self.nms_threshold = nms_threshold
        self.executor = None  # optional ThreadPoolExecutor to detect images in parallel
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
        """Detect faces in each image; returns one list of (x, y, w, h, score) per image."""
        if self.executor is None or len(images) == 1:
            return [self._detect_one(im) for im in images]
        return list(self.executor.map(self._detect_one, images))


class OnnxDetector:
    """YuNet via ONNX Runtime (CoreML / CUDA / CPU), with batched inference."""

    batched = True

    def __init__(self, score_threshold, nms_threshold, provider):
        import onnxruntime as ort
        self.ort = ort
        self.score_threshold = score_threshold
        self.nms_threshold = nms_threshold
        self.provider = provider
        self.executor = None  # optional ThreadPoolExecutor to speed up preprocessing
        self.name = f"ONNX Runtime ({provider.replace('ExecutionProvider', '')})"
        self._sessions = {}
        self._anchors = {}
        self._blob = None

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

    def _preprocess(self, images):
        """Pack same-sized BGR uint8 images into a zero-padded NCHW float32 blob."""
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
        return blob

    def _decode(self, outputs, n, height, width):
        """Turn raw YuNet outputs into per-image candidate (x, y, w, h, score) lists."""
        results = [[] for _ in range(n)]
        for c, r, s in self._grid(height, width):
            cls = np.clip(outputs[f'cls_{s}'][..., 0], 0, 1)
            obj = np.clip(outputs[f'obj_{s}'][..., 0], 0, 1)
            scores = np.sqrt(cls * obj)
            bbox = outputs[f'bbox_{s}']
            for i in range(n):
                keep = scores[i] >= self.score_threshold
                if not keep.any():
                    continue
                b = bbox[i][keep]
                bw, bh = np.exp(b[:, 2]) * s, np.exp(b[:, 3]) * s
                x = (c[keep] + b[:, 0]) * s - bw / 2
                y = (r[keep] + b[:, 1]) * s - bh / 2
                results[i].extend(zip(x, y, bw, bh, scores[i][keep]))
        return results

    def _nms(self, faces):
        if not faces:
            return []
        boxes = [[float(f[0]), float(f[1]), float(f[2]), float(f[3])] for f in faces]
        scores = [float(f[4]) for f in faces]
        idx = cv2.dnn.NMSBoxes(boxes, scores, self.score_threshold, self.nms_threshold, top_k=5000)
        return [(*boxes[j], scores[j]) for j in np.array(idx).ravel()]

    def detect_batch(self, images):
        """Detect faces in same-sized images; returns one list of (x, y, w, h, score) per image."""
        n = len(images)
        blob = self._preprocess(images)
        _, _, ph, pw = blob.shape
        session = self._session(n, ph, pw)
        # The model's reshapes hard-code batch 1, flattening the batch into one row; split it back out
        outputs = {o.name: v.reshape(n, -1, v.shape[-1])
                   for o, v in zip(session.get_outputs(), session.run(None, {'input': blob}))}
        return [self._nms(faces) for faces in self._decode(outputs, n, ph, pw)]
