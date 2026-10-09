import matplotlib
matplotlib.use("Agg")

import matplotlib.pyplot as plt
import pytest

from dynamo_figures.dress_axis import (FONT, INK, LABEL_SIZE, LABELPAD_3D, MATH_FONT,
                                       MUTED, TICK_SIZE, TITLE_SIZE, dress_axis)


@pytest.fixture
def ax():
    fig, ax = plt.subplots()
    ax.plot([0, 1, 2], [0, 1, 4], label="curve")
    ax.set_title("title")
    ax.set_xlabel("x")
    ax.set_ylabel("y")
    yield ax
    plt.close(fig)


@pytest.fixture
def ax3d():
    fig = plt.figure()
    ax = fig.add_subplot(projection="3d")
    ax.plot([0, 1], [0, 1], [0, 1])
    yield ax
    plt.close(fig)


def test_returns_same_axes(ax):
    assert dress_axis(ax) is ax


def test_spines(ax):
    dress_axis(ax)
    assert not ax.spines["top"].get_visible() and not ax.spines["right"].get_visible()
    assert ax.spines["left"].get_edgecolor() == pytest.approx(matplotlib.colors.to_rgba(MUTED))
    assert ax.spines["bottom"].get_edgecolor() == pytest.approx(matplotlib.colors.to_rgba(MUTED))


def test_grid_is_faint_and_below_data(ax):
    dress_axis(ax)
    line = ax.xaxis.get_gridlines()[0]
    assert line.get_visible()
    assert line.get_alpha() == pytest.approx(0.12)
    assert line.get_color() == INK
    assert ax.get_axisbelow() is True


def test_default_text_styling(ax):
    ax.legend()
    dress_axis(ax)
    fig = ax.figure
    fig.canvas.draw()
    assert ax.title.get_fontsize() == TITLE_SIZE
    assert ax.xaxis.label.get_fontsize() == LABEL_SIZE
    assert ax.title.get_fontfamily() == [FONT]
    assert ax.title.get_math_fontfamily() == MATH_FONT
    for label in ax.get_xticklabels() + ax.get_yticklabels():
        assert label.get_fontsize() == TICK_SIZE
        assert label.get_fontfamily() == [FONT]
    for text in ax.get_legend().get_texts():
        assert text.get_fontfamily() == [FONT]


def test_custom_sizes_and_fonts(ax):
    dress_axis(ax, tick_size=8, label_size=9, title_size=10, font="DejaVu Sans", math_font="dejavusans")
    ax.figure.canvas.draw()
    assert ax.title.get_fontsize() == 10
    assert ax.yaxis.label.get_fontsize() == 9
    assert ax.get_xticklabels()[0].get_fontsize() == 8
    assert ax.title.get_fontfamily() == ["DejaVu Sans"]
    assert ax.title.get_math_fontfamily() == "dejavusans"


def test_tick_labels_use_mathtext(ax):
    dress_axis(ax)
    assert ax.xaxis.get_major_formatter().get_useMathText()


def test_tick_colors_are_muted(ax):
    dress_axis(ax)
    ax.figure.canvas.draw()
    assert ax.get_xticklabels()[0].get_color() == MUTED


@pytest.mark.parametrize("n", [3, 5])
def test_num_ticks_caps_tick_count(ax, n):
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 100)
    dress_axis(ax, num_xticks=n, num_yticks=n)
    ax.figure.canvas.draw()
    assert len(ax.get_xticks()) <= n + 2  # ticks just outside the view may be listed
    visible = [t for t in ax.get_xticks() if 0 <= t <= 100]
    assert len(visible) <= n


def test_num_ticks_none_keeps_default(ax):
    ax.set_xlim(0, 100)
    ax.figure.canvas.draw()
    before = list(ax.get_xticks())
    dress_axis(ax)
    ax.figure.canvas.draw()
    assert list(ax.get_xticks()) == before


def test_num_zticks_needs_3d(ax):
    with pytest.raises(ValueError, match="3D"):
        dress_axis(ax, num_zticks=3)


def test_3d_axes(ax3d):
    dress_axis(ax3d, num_zticks=3, labelpad_3d=7)
    ax3d.figure.canvas.draw()
    for axis in (ax3d.xaxis, ax3d.yaxis, ax3d.zaxis):
        assert axis.labelpad == 7
        assert axis.label.get_fontfamily() == [FONT]


def test_3d_default_labelpad(ax3d):
    dress_axis(ax3d)
    assert ax3d.zaxis.labelpad == LABELPAD_3D


def test_axes_without_legend_or_title():
    fig, ax = plt.subplots()
    try:
        dress_axis(ax)
    finally:
        plt.close(fig)
