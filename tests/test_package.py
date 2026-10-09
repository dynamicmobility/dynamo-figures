import importlib
import subprocess
import sys
from pathlib import Path

import pytest

import dynamo_figures

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10
    import tomli as tomllib

ROOT = Path(__file__).parent.parent
PYPROJECT = tomllib.loads((ROOT / "pyproject.toml").read_text())


def test_version_matches_pyproject():
    assert dynamo_figures.__version__ == PYPROJECT["project"]["version"]


def test_all_exports_exist():
    for name in dynamo_figures.__all__:
        assert hasattr(dynamo_figures, name), name


def test_blur_faces_subpackage_exports():
    from dynamo_figures import blur_faces
    assert {"FaceBlur", "FaceTracker", "gpu_provider"} <= set(dir(blur_faces))


@pytest.mark.parametrize("name,target", PYPROJECT["project"]["scripts"].items())
def test_entry_points_resolve(name, target):
    module, func = target.split(":")
    assert callable(getattr(importlib.import_module(module), func))


@pytest.mark.parametrize("module", [
    "dynamo_figures",  # python -m dynamo_figures runs composite_image
    "dynamo_figures.composite_image",
    "dynamo_figures.pic_from_video",
    "dynamo_figures.video_to_gif",
    "dynamo_figures.qr_code",
    "dynamo_figures.tex2img",
    "dynamo_figures.blur_faces",
])
def test_cli_help_exits_zero(module):
    result = subprocess.run([sys.executable, "-m", module, "--help"],
                            capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stderr
    assert "usage" in result.stdout.lower()


def test_bundled_model_is_packaged():
    from dynamo_figures.blur_faces.detectors import MODEL_PATH
    assert MODEL_PATH.is_file()
    assert PYPROJECT["tool"]["setuptools"]["package-data"]["dynamo_figures"] == [
        "blur_faces/models/*.onnx"]
