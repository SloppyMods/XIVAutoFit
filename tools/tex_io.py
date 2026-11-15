"""Read and write FFXIV .tex files holding plain B8G8R8A8 pixels, and wrap compressed ones as .dds for Blender to decode.

Used by the tattoo conversion scripts. No game tools needed.
"""
import struct
from pathlib import Path

import numpy as np
from PIL import Image

HEADER_SIZE = 80
FORMAT_BGRA8 = 0x1450
FORMAT_BC1 = 0x3420
FORMAT_BC7 = 0x6432
_DXGI = {FORMAT_BC1: 71, FORMAT_BC7: 98}


def read_header(path: str) -> tuple[int, int, int, int]:
    """Return (format, width, height, mip count)."""
    _, fmt, width, height, _, mips = struct.unpack_from("<IIHHHH", Path(path).read_bytes()[:16])
    return fmt, width, height, mips & 0xFF


def read_bgra(path: str) -> np.ndarray:
    """Top mip of a B8G8R8A8 .tex as an (h, w, 4) RGBA array."""
    data = Path(path).read_bytes()
    _, fmt, width, height, _, _ = struct.unpack_from("<IIHHHH", data)
    if fmt != FORMAT_BGRA8:
        raise ValueError(f"{path}: format {fmt:#x} is not B8G8R8A8")
    return np.frombuffer(data, "u1", width * height * 4, HEADER_SIZE).reshape(height, width, 4)[..., [2, 1, 0, 3]]


def tex_to_dds(path: str, out: str) -> None:
    """Copy the top mip of a BC-compressed .tex into a .dds file, which Blender can decode."""
    data = Path(path).read_bytes()
    _, fmt, width, height, _, _ = struct.unpack_from("<IIHHHH", data)
    if fmt not in _DXGI:
        raise ValueError(f"{path}: format {fmt:#x} is not handled")
    block = 8 if fmt == FORMAT_BC1 else 16
    size = max(1, (width + 3) // 4) * max(1, (height + 3) // 4) * block
    flags = 0x1 | 0x2 | 0x4 | 0x1000 | 0x80000
    pitch = size
    head = struct.pack("<4s7I44x", b"DDS ", 124, flags, height, width, pitch, 0, 1)
    pixel_format = struct.pack("<II4s5I", 32, 0x4, b"DX10", 0, 0, 0, 0, 0)
    caps = struct.pack("<5I", 0x1000, 0, 0, 0, 0)
    dx10 = struct.pack("<5I", _DXGI[fmt], 3, 0, 1, 0)
    Path(out).write_bytes(head + pixel_format + caps + dx10 + data[HEADER_SIZE:HEADER_SIZE + size])


def _half(top: np.ndarray) -> np.ndarray:
    """Average each 2x2 block, every channel on its own.

    Never resize through Pillow's RGBA mode: it premultiplies by alpha, so wherever alpha is 0 the colour of the smaller copy
    becomes 0. In game textures alpha is often data, not transparency (a skin normal map's alpha is the glow mask), and that
    turned every non-glowing texel's normal to (0, 0) in the mips: faceted, broken shading at any distance."""
    height, width = top.shape[:2]
    if height % 2 == 0 and width % 2 == 0:
        blocks = top.reshape(height // 2, 2, width // 2, 2, top.shape[2]).astype(np.uint32).sum((1, 3))
        return ((blocks + 2) // 4).astype(np.uint8)
    channels = [np.asarray(Image.fromarray(np.ascontiguousarray(top[..., c]), "L").resize((width // 2, height // 2), Image.BOX)) for c in range(top.shape[2])]
    return np.stack(channels, -1)


def _mip_chain(rgba: np.ndarray) -> list[np.ndarray]:
    """Box-filtered smaller copies down to one pixel on the short side, each from the previous one, channels independent."""
    chain = [rgba]
    while min(chain[-1].shape[:2]) > 1:
        chain.append(_half(chain[-1]))
    return chain


def read_mip(path: str, level: int) -> np.ndarray:
    """One mip level of a B8G8R8A8 .tex as an (h, w, 4) RGBA array, for checking what the game sees at a distance."""
    data = Path(path).read_bytes()
    _, fmt, width, height, _, _ = struct.unpack_from("<IIHHHH", data)
    if fmt != FORMAT_BGRA8:
        raise ValueError(f"{path}: format {fmt:#x} is not B8G8R8A8")
    offset = struct.unpack_from("<13I", data, 28)[level]
    w, h = max(1, width >> level), max(1, height >> level)
    return np.frombuffer(data, "u1", w * h * 4, offset).reshape(h, w, 4)[..., [2, 1, 0, 3]]


def write_bgra(path: str, rgba: np.ndarray) -> None:
    """Write an (h, w, 4) RGBA array as an uncompressed B8G8R8A8 .tex with a full mip chain."""
    height, width = rgba.shape[:2]
    chain = _mip_chain(rgba)[:13]
    offsets, position = [], HEADER_SIZE
    for level in chain:
        offsets.append(position)
        position += level.size
    lod = struct.pack("<3I", 0, 1, 2)
    table = struct.pack(f"<{len(offsets)}I", *offsets) + b"\0" * (4 * (13 - len(offsets)))
    header = struct.pack("<IIHHHH", 0x00800000, FORMAT_BGRA8, width, height, 1, len(chain)) + lod + table
    assert len(header) == HEADER_SIZE, len(header)
    with open(path, "wb") as handle:
        handle.write(header)
        for level in chain:
            handle.write(level[..., [2, 1, 0, 3]].tobytes())
