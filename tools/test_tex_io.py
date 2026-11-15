"""Tests for tex_io: the mips of a written .tex must keep colour where alpha is 0 (alpha is data in game textures).

    python3 -m pytest test_tex_io.py
"""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import tex_io  # noqa: E402


def _image_with_zero_alpha() -> np.ndarray:
    rng = np.random.default_rng(7)
    rgba = rng.integers(0, 256, (64, 64, 4), dtype=np.uint8)
    rgba[:32, :, 3] = 0  # top half: alpha 0, like non-glowing skin in a normal map
    return rgba


def test_mips_keep_colour_under_zero_alpha(tmp_path: Path) -> None:
    # Arrange
    rgba = _image_with_zero_alpha()
    path = str(tmp_path / "t.tex")

    # Act
    tex_io.write_bgra(path, rgba)
    mip1 = tex_io.read_mip(path, 1)

    # Assert: every channel is the plain 2x2 average, also where alpha is 0
    expected = (rgba.reshape(32, 2, 32, 2, 4).astype(np.uint32).sum((1, 3)) + 2) // 4
    assert np.array_equal(mip1, expected.astype(np.uint8))
    assert mip1[:16, :, :3].mean() > 60  # random colours average near 127, never 0


def test_top_mip_reads_back_identical(tmp_path: Path) -> None:
    rgba = _image_with_zero_alpha()
    path = str(tmp_path / "t.tex")
    tex_io.write_bgra(path, rgba)
    assert np.array_equal(tex_io.read_bgra(path), rgba)
    assert np.array_equal(tex_io.read_mip(path, 0), rgba)


def test_mip_count_reaches_one_pixel(tmp_path: Path) -> None:
    path = str(tmp_path / "t.tex")
    tex_io.write_bgra(path, _image_with_zero_alpha())
    assert tex_io.read_header(path)[3] == 7  # 64, 32, 16, 8, 4, 2, 1
    assert tex_io.read_mip(path, 6).shape == (1, 1, 4)
