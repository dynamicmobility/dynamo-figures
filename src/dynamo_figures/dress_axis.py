from matplotlib import pyplot as plt
from matplotlib.ticker import ScalarFormatter

INK, MUTED = "#0b0b0b", "#52514e"   # chart ink and recessive furniture

TICK_SIZE   = 12        # tick label size, in points
FONT        = "cmr10"   # matplotlib's bundled Computer Modern roman
MATH_FONT   = "cm"      # mathtext's Computer Modern fontset
LABELPAD_3D = 10        # axis label distance from its ticks on a 3D axes, in points
LABEL_SIZE  = 14        # axis label size, in points
TITLE_SIZE  = 16        # axes title size, in points

def dress_axis(
        ax          : plt.Axes,
        tick_size   : float = TICK_SIZE,
        label_size  : float = LABEL_SIZE,
        title_size  : float = TITLE_SIZE,
        font        : str   = FONT,
        math_font   : str   = MATH_FONT,
        labelpad_3d : float = LABELPAD_3D,
        num_xticks  : int   = None,
        num_yticks  : int   = None,
        num_zticks  : int   = None
    ) -> plt.Axes:
    """Apply the house style: recessive grid, muted ticks, no top/right spines,
    and one font on every text the axes holds when called.

    Args:
        ax: a 2D or 3D ``matplotlib.axes.Axes`` to style.
        tick_size: tick label size, in points.
        label_size: axis label size, in points.
        title_size: axes title size, in points.
        font: font family for every text, e.g. ``"cmr10"``.
        math_font: mathtext fontset for the ``$...$`` parts, e.g. ``"cm"``.
        labelpad_3d: axis label padding, in points; 3D axes only.
        num_xticks, num_yticks, num_zticks: the most ticks that axis draws,
            placed at round values. None keeps matplotlib's own choice.
            ``num_zticks`` needs a 3D axes.

    Returns:
        The ``ax`` that was styled, for chaining.
    """
    ax.grid(True, color=INK, alpha=0.12, lw=0.8)
    ax.set_axisbelow(True)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(MUTED)
    is_3d = ax.name == "3d"
    axes  = (ax.xaxis, ax.yaxis, ax.zaxis) if is_3d else (ax.xaxis, ax.yaxis)
    for which in ("both", "z") if is_3d else ("both",):
        ax.tick_params(axis=which, colors=MUTED, labelsize=tick_size,
                       labelfontfamily=font)
    if is_3d:
        for axis in axes:
            axis.labelpad = labelpad_3d

    for name, num in zip("xyz", (num_xticks, num_yticks, num_zticks)):
        if num is None:
            continue
        if name == "z" and not is_3d:
            raise ValueError("num_zticks needs a 3D axes")
        # nbins counts the gaps between ticks, so n ticks is n - 1 of them
        ax.locator_params(axis=name, nbins=num - 1)

    # cmr10 has no unicode minus, so tick numbers are drawn through mathtext
    for axis in axes:
        if isinstance(axis.get_major_formatter(), ScalarFormatter):
            axis.get_major_formatter().set_useMathText(True)

    legend = ax.get_legend()
    texts  = [ax.title, *ax.texts, *(legend.get_texts() if legend else []),
              *(text for axis in axes
                for text in (axis.label, axis.get_offset_text(),
                             *axis.get_ticklabels()))]
    for text in texts:
        text.set_fontfamily(font)
        text.set_math_fontfamily(math_font)
    for axis in axes:
        axis.label.set_fontsize(label_size)
    ax.title.set_fontsize(title_size)
    return ax