"""Move a transparent Bibo+ overlay (a colour PNG) onto the hrBody 3 Chubby skin by chaining two layout maps.

    python3 overlay_transfer.py <overlay.png> <output folder inside builds/_tattoo>

Chain per HR3 texel: map.npz gives its TBSE UV (made by tattoo_transfer.py map), Proteus's bibo_to_tbse_transfer.tif gives the Bibo UV
for that spot, and the overlay is sampled there. The transfer map must already be decoded to builds/_tattoo/b2t.npy (float RGBA:
R and G = Bibo UV, A = valid). Writes c0901b0001_b_d.tex over plain HR3 skin (plain/) and over the tattooed HR3 skin (tattoo/).
Env: OVERLAY_MAP=<file in builds/_tattoo> picks the HR3-to-TBSE map (map.npz); OVERLAY_CLOSE=<texels> fills bare gaps on the hands; OVERLAY_GREY=<0..1> makes the overlay grey at that average brightness (off keeps its own colours).
"""
import os
import sys
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage

sys.path.insert(0, str(Path(__file__).resolve().parent))
import tattoo_transfer as tt  # noqa: E402
import tex_io  # noqa: E402

Image.MAX_IMAGE_PIXELS = None
CLOSE_RADIUS = int(os.environ.get("OVERLAY_CLOSE", "0"))  # texels; closes bare gaps in the overlay on the hands
GREY = float(os.environ["OVERLAY_GREY"]) if "OVERLAY_GREY" in os.environ else None  # average brightness 0..1 to recolour the overlay to
VALID = 0.5
PAD = 16
LUMA = (0.2126, 0.7152, 0.0722)  # how much red, green and blue each add to perceived brightness
GROW_MAP = 32  # texels; how far valid entries of the Proteus map are copied outward to close small holes


def to_grey(rgba: np.ndarray, target: float) -> np.ndarray:
    """Remove the colour and set the average brightness of the visible overlay to target (0..1), keeping its light and dark detail."""
    luma = rgba[..., :3] @ np.array(LUMA, "f4")
    mean = float(luma[rgba[..., 3] > 0.5].mean())
    grey = np.clip(luma / mean * target, 0, 1)
    return np.dstack([grey, grey, grey, rgba[..., 3]])


def premultiplied(path: str, grey: float | None) -> np.ndarray:
    rgba = np.asarray(Image.open(path).convert("RGBA")).astype("f4") / 255
    if grey is not None:
        rgba = to_grey(rgba, grey)
    rgba[..., :3] *= rgba[..., 3:]
    return rgba


def filled_map(raw: np.ndarray) -> np.ndarray:
    """The Bibo UV of each TBSE texel, with holes filled from the nearest valid texel."""
    valid = raw[..., 3] > VALID
    uv = np.zeros(raw.shape, "f4")
    uv[..., :2] = raw[..., :2]
    uv[..., 3] = valid
    return tt.grow(uv, valid, GROW_MAP)


def close_holes(layer: np.ndarray, region: np.ndarray, radius: int) -> np.ndarray:
    """Fill bare gaps narrower than 2 * radius inside the overlay, only in region, using the colour of the nearest covered texel."""
    covered = layer[..., 3] > 0.5
    grown = ndimage.distance_transform_edt(~covered) <= radius
    closed = ndimage.distance_transform_edt(grown) > radius
    holes = closed & ~covered & region
    _, (row, col) = ndimage.distance_transform_edt(~covered, return_indices=True)
    out = layer.copy()
    out[holes] = layer[row[holes], col[holes]]
    print(f"bare gaps filled: {holes.sum()} texels")
    return out


def composite(base: np.ndarray, layer: np.ndarray) -> np.ndarray:
    alpha = layer[..., 3:]
    colour = np.clip(base[..., :3].astype("f4") / 255 * (1 - alpha) + layer[..., :3], 0, 1)
    return np.dstack([(colour * 255 + 0.5).astype("u1"), base[..., 3]])


def main() -> None:
    overlay_path, out_name = sys.argv[1:3]
    out = tt.OUT / out_name
    (out / "plain").mkdir(parents=True, exist_ok=True)
    (out / "tattoo").mkdir(parents=True, exist_ok=True)
    data = np.load(tt.OUT / os.environ.get("OVERLAY_MAP", "map.npz"))
    rows, cols, tbse_uv = data["rows"], data["cols"], data["uv"]
    transfer = filled_map(np.load(tt.OUT / "b2t.npy"))
    # Nearest lookup: the map jumps at island borders, so blending neighbouring UVs there would sample unrelated art.
    x = np.clip((tbse_uv[:, 0] * 4096).astype(int), 0, 4095)
    y = np.clip((tbse_uv[:, 1] * 4096).astype(int), 0, 4095)
    found = transfer[y, x]
    known = found[:, 3] > VALID
    print(f"HR3 texels with a Bibo match: {known.mean():.4f}")
    sampled = tt.sample_bilinear(premultiplied(overlay_path, GREY), found[:, :2]).astype("f4")
    sampled[~known] = 0
    layer = np.zeros((tt.HR3_SIZE, tt.HR3_SIZE, 4), "f4")
    layer[rows, cols] = sampled
    inside = np.zeros((tt.HR3_SIZE, tt.HR3_SIZE), bool)
    inside[rows, cols] = True
    if CLOSE_RADIUS:
        glove = np.zeros(inside.shape, bool)
        hand = data["part"] == 2  # body part 2 is the glove model: hands and wrists
        glove[rows[hand], cols[hand]] = True
        layer = close_holes(layer, glove, CLOSE_RADIUS)
    layer = tt.grow(layer, inside, PAD)
    print(f"overlay texels over 0.5 opacity on HR3: {(layer[..., 3] > 0.5).sum()}")
    for name, base in (("plain", np.load(tt.OUT / "hr3_b_d.npy")), ("tattoo", np.load(tt.OUT / "hr3_tattoo_rgba.npy"))):
        result = composite(base, layer)
        path = str(out / name / "c0901b0001_b_d.tex")
        tex_io.write_bgra(path, result)
        print(name, "read back identical:", np.array_equal(tex_io.read_bgra(path), result))
        Image.fromarray(result[..., :3]).resize((2048, 2048), Image.BOX).save(out / f"{name}.png")
    Image.fromarray((layer[..., 3] * 255).astype("u1")).resize((1024, 1024), Image.BOX).save(out / "alpha.png")


if __name__ == "__main__":
    main()
