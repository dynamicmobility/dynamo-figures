import pytest

from dynamo_figures.blur_faces.tracking import FaceTracker, contains, iou, union_box


class TestGeometry:
    def test_iou_identical(self):
        assert iou((0, 0, 10, 10), (0, 0, 10, 10)) == 1.0

    def test_iou_disjoint(self):
        assert iou((0, 0, 10, 10), (20, 20, 5, 5)) == 0.0

    def test_iou_half_overlap(self):
        # intersection 50, union 150
        assert iou((0, 0, 10, 10), (5, 0, 10, 10)) == pytest.approx(1 / 3)

    def test_iou_zero_area(self):
        assert iou((0, 0, 0, 0), (0, 0, 0, 0)) == 0.0

    def test_contains(self):
        assert contains((0, 0, 10, 10), (2, 2, 5, 5))
        assert not contains((0, 0, 10, 10), (8, 8, 5, 5))

    def test_contains_margin(self):
        assert contains((0, 0, 10, 10), (8, 8, 5, 5), margin=0.5)

    def test_union_box(self):
        assert union_box((0, 0, 10, 10), (5, 5, 10, 10)) == (0, 0, 15, 15)


class TestTracker:
    def test_invalid_smoothing(self):
        for bad in (-0.1, 1.0, 2):
            with pytest.raises(ValueError, match="smoothing"):
                FaceTracker(smoothing=bad)

    def test_new_detection_passes_through(self):
        det = (10, 10, 20, 20, 0.9)
        assert FaceTracker().update([det]) == [det]

    def test_no_detections_no_faces(self):
        assert FaceTracker().update([]) == []

    def test_smoothing_off_follows_detection(self):
        t = FaceTracker(smoothing=0)
        t.update([(0, 0, 10, 10, 0.9)])
        out = t.update([(2, 0, 10, 10, 0.8)])
        assert out == [(2, 0, 10, 10, 0.8)]

    def test_smoothing_blends_with_previous_box(self):
        t = FaceTracker(smoothing=0.5, lag_margin=1.0)
        t.update([(0, 0, 10, 10, 0.9)])
        (x, y, w, h, score), = t.update([(4, 0, 10, 10, 0.8)])
        assert (x, w) == (2.0, 10.0) and score == 0.8

    def test_lag_margin_covers_fast_motion(self):
        t = FaceTracker(smoothing=0.9, lag_margin=0.1)
        t.update([(0, 0, 10, 10, 0.9)])
        (x, y, w, h, _), = t.update([(8, 0, 10, 10, 0.9)])
        # the smoothed box barely moved, but the raw detection must stay covered
        assert x <= 8 and x + w >= 18

    def test_lost_face_is_held_then_dropped(self):
        t = FaceTracker(hold_frames=2)
        t.update([(0, 0, 10, 10, 0.9)])
        assert len(t.update([])) == 1
        assert len(t.update([])) == 1
        assert t.update([]) == []

    def test_zero_hold_drops_immediately(self):
        t = FaceTracker(hold_frames=0)
        t.update([(0, 0, 10, 10, 0.9)])
        assert t.update([]) == []

    def test_held_face_is_found_again(self):
        t = FaceTracker(hold_frames=3, smoothing=0)
        t.update([(0, 0, 10, 10, 0.9)])
        t.update([])
        assert t.update([(1, 0, 10, 10, 0.9)]) == [(1, 0, 10, 10, 0.9)]
        assert len(t._tracks) == 1  # continued, not duplicated

    def test_far_detection_starts_a_new_track(self):
        t = FaceTracker(hold_frames=5, smoothing=0)
        t.update([(0, 0, 10, 10, 0.9)])
        faces = t.update([(100, 100, 10, 10, 0.9)])
        assert len(faces) == 2  # held old face + new face

    def test_two_faces_keep_their_identity(self):
        t = FaceTracker(smoothing=0.5, lag_margin=1.0)
        a, b = (0, 0, 10, 10, 0.9), (100, 0, 10, 10, 0.9)
        t.update([a, b])
        out = t.update([(2, 0, 10, 10, 0.9), (102, 0, 10, 10, 0.9)])
        assert sorted(round(f[0]) for f in out) == [1, 101]

    def test_reset_forgets_tracks(self):
        t = FaceTracker(hold_frames=5)
        t.update([(0, 0, 10, 10, 0.9)])
        t.reset()
        assert t.update([]) == []
