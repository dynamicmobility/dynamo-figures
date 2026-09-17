"""
    File: tracking.py
    Description: Frame-to-frame face tracking for videos.
    Matches detections across frames to smooth box jitter and to keep
    obscuring faces the detector briefly loses.
"""


def iou(a, b):
    """Intersection-over-union of two (x, y, w, h) boxes."""
    ax2, ay2 = a[0] + a[2], a[1] + a[3]
    bx2, by2 = b[0] + b[2], b[1] + b[3]
    iw = max(0.0, min(ax2, bx2) - max(a[0], b[0]))
    ih = max(0.0, min(ay2, by2) - max(a[1], b[1]))
    inter = iw * ih
    union = a[2] * a[3] + b[2] * b[3] - inter
    return inter / union if union > 0 else 0.0


def contains(outer, inner, margin=0.0):
    """True if inner lies within outer grown by margin (fraction of outer's size) on every side."""
    mx, my = outer[2] * margin, outer[3] * margin
    return (inner[0] >= outer[0] - mx and inner[1] >= outer[1] - my
            and inner[0] + inner[2] <= outer[0] + outer[2] + mx
            and inner[1] + inner[3] <= outer[1] + outer[3] + my)


def union_box(a, b):
    """Smallest (x, y, w, h) box containing both boxes."""
    x0, y0 = min(a[0], b[0]), min(a[1], b[1])
    x1, y1 = max(a[0] + a[2], b[0] + b[2]), max(a[1] + a[3], b[1] + b[3])
    return (x0, y0, x1 - x0, y1 - y0)


class _Track:
    __slots__ = ('box', 'score', 'missed')

    def __init__(self, box, score):
        self.box = tuple(box)
        self.score = score
        self.missed = 0


class FaceTracker:
    """Smooths face boxes over time and holds boxes for briefly-missed faces."""

    def __init__(self, hold_frames=5, smoothing=0.5, min_iou=0.1, lag_margin=0.1):
        """
        Initialize FaceTracker.

        Args:
            hold_frames: Keep a face's last box for this many frames after the
                         detector stops finding it
            smoothing: Exponential smoothing weight on the previous box (0..1);
                       0 disables smoothing, higher values are steadier but lag more
            min_iou: Minimum overlap for a detection to continue an existing track
            lag_margin: If the raw detection extends beyond the smoothed box by more
                        than this fraction of its size, cover both boxes
        """
        if not 0 <= smoothing < 1:
            raise ValueError("smoothing must be in [0, 1)")
        self.hold_frames = max(0, hold_frames)
        self.smoothing = smoothing
        self.min_iou = min_iou
        self.lag_margin = lag_margin
        self._tracks = []

    def reset(self):
        """Forget all tracks (call before starting a new video)."""
        self._tracks = []

    def update(self, detections):
        """
        Advance one frame.

        Args:
            detections: list of (x, y, w, h, score) tuples for this frame

        Returns:
            list: (x, y, w, h, score) tuples of the boxes to obscure
        """
        # Greedily match the highest-overlap track/detection pairs first
        pairs = sorted(
            ((iou(t.box, d[:4]), ti, di)
             for ti, t in enumerate(self._tracks)
             for di, d in enumerate(detections)),
            reverse=True,
        )
        matched_tracks, matched_dets = {}, set()
        for overlap, ti, di in pairs:
            if overlap < self.min_iou:
                break
            if ti in matched_tracks or di in matched_dets:
                continue
            matched_tracks[ti] = di
            matched_dets.add(di)

        faces = []
        alive = []
        a = self.smoothing
        for ti, track in enumerate(self._tracks):
            if ti in matched_tracks:
                det = detections[matched_tracks[ti]]
                track.box = tuple(a * p + (1 - a) * c for p, c in zip(track.box, det[:4]))
                track.score = det[4]
                track.missed = 0
                box = track.box
                if not contains(box, det[:4], self.lag_margin):
                    # The smoothed box lags behind fast motion; don't let the face escape it
                    box = union_box(box, det[:4])
                faces.append((*box, track.score))
                alive.append(track)
            else:
                track.missed += 1
                if track.missed <= self.hold_frames:
                    faces.append((*track.box, track.score))
                    alive.append(track)

        for di, det in enumerate(detections):
            if di not in matched_dets:
                alive.append(_Track(det[:4], det[4]))
                faces.append(tuple(det))

        self._tracks = alive
        return faces
