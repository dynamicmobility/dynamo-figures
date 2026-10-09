import cv2
import numpy as np
import pytest

from dynamo_figures.blur_faces.obscure import SHAPES, STYLES, Obscurer

H, W = 100, 120
FACE = (40, 30, 30, 30, 0.9)  # x, y, w, h, score


@pytest.fixture
def image():
    """Noisy image so blur / pixelate visibly change pixels."""
    return np.random.default_rng(0).integers(0, 256, (H, W, 3), dtype=np.uint8)


class TestValidation:
    def test_bad_style(self):
        with pytest.raises(ValueError, match="style"):
            Obscurer(style="smudge")

    def test_bad_shape(self):
        with pytest.raises(ValueError, match="shape"):
            Obscurer(shape="star")

    def test_bad_color(self):
        with pytest.raises(ValueError):
            Obscurer(style="fill", fill_color="notacolor")

    def test_fill_color_is_stored_bgr(self):
        assert Obscurer(fill_color="#ff0000").fill_color == (0, 0, 255)

    def test_pixel_blocks_floor(self):
        assert Obscurer(pixel_blocks=0).pixel_blocks == 1


@pytest.mark.parametrize("style", STYLES)
@pytest.mark.parametrize("shape", SHAPES)
class TestApply:
    def test_changes_face_only(self, image, style, shape):
        out = Obscurer(style, shape, padding=0).apply(image, [FACE])
        diff = np.any(out != image, axis=2)
        assert diff[30:60, 40:70].any()
        outside = diff.copy()
        outside[30:60, 40:70] = False
        assert not outside.any()

    def test_input_not_modified_by_default(self, image, style, shape):
        original = image.copy()
        out = Obscurer(style, shape).apply(image, [FACE])
        assert np.array_equal(image, original) and out is not image

    def test_inplace(self, image, style, shape):
        original = image.copy()
        out = Obscurer(style, shape).apply(image, [FACE], inplace=True)
        assert out is image and not np.array_equal(image, original)

    def test_no_faces_is_identity(self, image, style, shape):
        assert np.array_equal(Obscurer(style, shape).apply(image, []), image)

    def test_face_at_image_edge_is_clipped(self, image, style, shape):
        out = Obscurer(style, shape).apply(image, [(-10, -10, 40, 40, 0.9), (100, 80, 50, 50, 0.9)])
        assert out.shape == image.shape

    def test_degenerate_box_is_skipped(self, image, style, shape):
        out = Obscurer(style, shape).apply(image, [(10, 10, 0.5, 0.5, 0.9)])
        assert np.array_equal(out, image)


class TestStyles:
    def test_fill_rect_is_exact_color(self, image):
        out = Obscurer("fill", "rect", padding=0, fill_color="#00ff00").apply(image, [FACE])
        face = out[30:60, 40:70]
        assert (face == (0, 255, 0)).all()

    def test_fill_ellipse_center_is_color_corner_untouched(self, image):
        out = Obscurer("fill", "ellipse", padding=0, fill_color="red").apply(image, [FACE])
        assert tuple(out[45, 55]) == (0, 0, 255)
        assert tuple(out[30, 40]) == tuple(image[30, 40])  # box corner lies outside the ellipse

    def test_pixelate_makes_blocks(self, image):
        out = Obscurer("pixelate", "rect", padding=0, pixel_blocks=3).apply(image, [FACE])
        face = out[30:60, 40:70]
        assert len(np.unique(face.reshape(-1, 3), axis=0)) <= 9

    def test_blur_reduces_variance(self, image):
        out = Obscurer("blur", "rect", padding=0).apply(image, [FACE])
        assert out[30:60, 40:70].std() < image[30:60, 40:70].std() / 2

    def test_stronger_blur_is_smoother(self, image):
        weak = Obscurer("blur", "rect", padding=0, blur_strength=0.05).apply(image, [FACE])
        strong = Obscurer("blur", "rect", padding=0, blur_strength=1.0).apply(image, [FACE])
        assert strong[30:60, 40:70].std() <= weak[30:60, 40:70].std()

    def test_padding_enlarges_region(self, image):
        tight = np.any(Obscurer("fill", "rect", padding=0).apply(image, [FACE]) != image, axis=2).sum()
        loose = np.any(Obscurer("fill", "rect", padding=0.5).apply(image, [FACE]) != image, axis=2).sum()
        assert loose > tight

    def test_draw_boxes_annotates_instead_of_obscuring(self, image):
        out = Obscurer("fill", "rect", draw_boxes=True).apply(image, [FACE])
        green = np.all(out == (0, 255, 0), axis=2)
        assert green.any()
        # the face interior is left as-is: only box outline and score text change
        assert np.array_equal(out[40:50, 50:60], image[40:50, 50:60])
