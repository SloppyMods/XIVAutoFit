"""Add a transparent Bibo+ overlay's bump detail to the hrBody 3 Chubby normal map, through the same layout maps as its colour.

    python3 bandage_normal.py <overlay colour.png> <overlay Normal_DirectX.png> <overlay Height.png> <output folder in builds/_tattoo>

Directions in a normal map follow the UV island it is painted on, so each texel's X and Y are turned from the Bibo layout's orientation
to the HR3 layout's, using the local rotation (or mirror) of the map between them. Only the red and green channels change: blue and
alpha are HR3's own. Writes c0901b0001_b_n.tex and previews. Y direction: this source file has green high toward the image's bottom;
the game's skin normals have green high toward the top (measured), so the green channel is flipped on the way in.
"""
import sys
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage

sys.path.insert(0, str(Path(__file__).resolve().parent))
import overlay_transfer as ot  # noqa: E402
import tattoo_transfer as tt  # noqa: E402
import tex_io  # noqa: E402

Image.MAX_IMAGE_PIXELS = None
STEP = 8  # texels; distance used to measure the local map direction, large enough to ignore the map's stair steps
MAX_STRETCH = 6.0  # Bibo texels per HR3 texel; a bigger change than this between neighbours is a jump between islands
SMOOTH = 5.0
ISLAND_JUMP = 0.02  # UV distance between neighbouring map entries that means an island border
CLOSE_RADIUS = 50
SOURCE_GREEN_DOWN = 1.0  # measured: + means green high is toward the bottom of the image


def smooth_lookup(transfer: np.ndarray, uv: np.ndarray) -> np.ndarray:
    """Read the Proteus map with bilinear filtering inside an island and nearest-pixel at an island border, as (Bibo u, Bibo v, unused, valid)."""
    size = transfer.shape[0]
    x, y = uv[:, 0] * size - 0.5, uv[:, 1] * size - 0.5
    x0, y0 = np.clip(np.floor(x).astype(int), 0, size - 2), np.clip(np.floor(y).astype(int), 0, size - 2)
    fx, fy = np.clip(x - x0, 0, 1)[:, None], np.clip(y - y0, 0, 1)[:, None]
    a, b, c, d = transfer[y0, x0], transfer[y0, x0 + 1], transfer[y0 + 1, x0], transfer[y0 + 1, x0 + 1]
    corners = np.stack([a, b, c, d], 1)
    spread = corners[:, :, :2].max(1) - corners[:, :, :2].min(1)
    usable = (corners[:, :, 3] > ot.VALID).all(1) & (spread.max(1) < ISLAND_JUMP)
    out = transfer[np.clip((uv[:, 1] * size).astype(int), 0, size - 1), np.clip((uv[:, 0] * size).astype(int), 0, size - 1)].copy()
    out[usable] = ((a * (1 - fx) + b * fx) * (1 - fy) + (c * (1 - fx) + d * fx) * fy)[usable]
    return out


def height_check(height_path: str, bibo_uv: np.ndarray, rows: np.ndarray, cols: np.ndarray, part: np.ndarray, base: np.ndarray, result: np.ndarray, mask: np.ndarray) -> None:
    """Warp the overlay's height through the same map; print whether the final normal slopes the right way in each area (raised, not inverted)."""
    height = np.asarray(Image.open(height_path).convert("RGB")).astype("f4")[..., 0] / 255
    warped = np.zeros((tt.HR3_SIZE, tt.HR3_SIZE), "f4")
    warped[rows, cols] = tt.sample_bilinear(height[..., None], bibo_uv)[:, 0]
    grad_row, grad_col = np.gradient(ndimage.gaussian_filter(warped, 1.5))
    x = result[..., 0].astype("f4") - base[..., 0].astype("f4")
    y = result[..., 1].astype("f4") - base[..., 1].astype("f4")
    inner = ndimage.binary_erosion(mask, iterations=6)
    for name, code, side in (("hand left", 2, -1), ("hand right", 2, 1), ("foot left", 3, -1), ("foot right", 3, 1)):
        area = np.zeros(mask.shape, bool)
        keep = part == code
        area[rows[keep], cols[keep]] = True
        area &= inner
        half = np.arange(tt.HR3_SIZE)[None, :] > tt.HR3_SIZE / 2 if side > 0 else np.arange(tt.HR3_SIZE)[None, :] <= tt.HR3_SIZE / 2
        area &= half
        print(f"{name:11s} corr(R change, dH/dcol) {np.corrcoef(x[area], grad_col[area])[0, 1]:+.3f}  corr(G change, dH/drow) {np.corrcoef(y[area], grad_row[area])[0, 1]:+.3f}  (raised detail: R negative, G positive)")


def uv_image(rows: np.ndarray, cols: np.ndarray, uv: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    field = np.zeros((tt.HR3_SIZE, tt.HR3_SIZE, 2), "f4")
    valid = np.zeros((tt.HR3_SIZE, tt.HR3_SIZE), bool)
    field[rows, cols] = uv
    valid[rows, cols] = True
    return field, valid


def difference(field: np.ndarray, valid: np.ndarray, axis: int) -> tuple[np.ndarray, np.ndarray]:
    """Change in field per HR3 texel along one axis, with a mask of where that change is a real, in-island change."""
    forward, back = np.roll(field, -STEP, axis), np.roll(field, STEP, axis)
    ok_forward, ok_back = np.roll(valid, -STEP, axis), np.roll(valid, STEP, axis)
    delta = (forward - back) * tt.HR3_SIZE / (2 * STEP)
    both = valid & ok_forward & ok_back
    good = both & (np.abs(delta).max(2) < MAX_STRETCH)
    return delta.astype("f4"), good


def jacobian_field(field: np.ndarray, valid: np.ndarray) -> np.ndarray:
    """2x2 map (Bibo texels per HR3 texel) per texel, smoothed inside islands and filled from the nearest valid texel where unknown."""
    d_col, ok_col = difference(field, valid, 1)
    d_row, ok_row = difference(field, valid, 0)
    good = ok_col & ok_row
    weight = ndimage.gaussian_filter(good.astype("f4"), SMOOTH)
    parts = []
    for arr in (d_col[..., 0], d_row[..., 0], d_col[..., 1], d_row[..., 1]):
        parts.append(ndimage.gaussian_filter(np.where(good, arr, 0), SMOOTH) / np.maximum(weight, 1e-3))
    jac = np.stack(parts, axis=2)
    known = weight > 0.1
    _, (row, col) = ndimage.distance_transform_edt(~known, return_indices=True)
    print(f"texels with a measured direction: {(known & valid).sum() / valid.sum():.4f}")
    return jac[row, col].reshape(tt.HR3_SIZE, tt.HR3_SIZE, 2, 2)


def rotations(jac: np.ndarray) -> np.ndarray:
    """The rotation or mirror closest to each 2x2 matrix (polar decomposition, through the singular value decomposition)."""
    u, _, vh = np.linalg.svd(jac)
    return u @ vh


def reoriented(base: np.ndarray, detail: np.ndarray) -> np.ndarray:
    """Reoriented normal mapping: tilt the detail normal by the base normal. Both are (x, y) in [-1, 1]; returns (x, y)."""
    bz = np.sqrt(np.maximum(1 - (base**2).sum(1), 0))
    dz = np.sqrt(np.maximum(1 - (detail**2).sum(1), 0))
    t = np.c_[base, bz + 1]
    u = np.c_[-detail, dz]
    n = t * ((t * u).sum(1, keepdims=True) / t[:, 2:]) - u
    return (n / np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-9))[:, :2]


def main() -> None:
    colour_path, normal_path, height_path, out_name = sys.argv[1:5]
    out = tt.OUT / out_name
    out.mkdir(parents=True, exist_ok=True)
    data = np.load(tt.OUT / "map_fingers.npz")
    rows, cols, tbse_uv, part = data["rows"], data["cols"], data["uv"], data["part"]
    transfer = ot.filled_map(np.load(tt.OUT / "b2t.npy"))
    found = smooth_lookup(transfer, tbse_uv)
    bibo_uv = found[:, :2]
    colour = np.asarray(Image.open(colour_path).convert("RGBA")).astype("f4") / 255
    normal = np.asarray(Image.open(normal_path).convert("RGB")).astype("f4") / 255
    source = np.dstack([normal[..., 0] * 2 - 1, (normal[..., 1] * 2 - 1) * SOURCE_GREEN_DOWN, np.zeros(colour.shape[:2], "f4"), colour[..., 3]])
    source[..., :2] *= source[..., 3:]  # scale the detail by the overlay's coverage, so its soft edges fade out
    sampled = tt.sample_bilinear(source, bibo_uv).astype("f4")
    sampled[found[:, 3] <= ot.VALID] = 0
    field, valid = uv_image(rows, cols, bibo_uv)
    rotation = rotations(jacobian_field(field, valid))[rows, cols]
    # R turns an HR3 direction into a Bibo direction, so a Bibo direction becomes an HR3 one through R's transpose.
    turned = (np.swapaxes(rotation, 1, 2) @ sampled[:, :2, None])[:, :, 0]
    layer = np.zeros((tt.HR3_SIZE, tt.HR3_SIZE, 4), "f4")
    layer[rows, cols, :2] = turned
    layer[rows, cols, 3] = sampled[:, 3]
    glove = np.zeros(valid.shape, bool)
    hand = part == 2
    glove[rows[hand], cols[hand]] = True
    layer = ot.close_holes(layer, glove, CLOSE_RADIUS)
    layer = tt.grow(layer, valid, ot.PAD)
    base = np.load(tt.OUT / "hr3_b_n.npy")
    result = base.copy()
    where = layer[..., 3] > 1e-3
    print(f"texels changed: {where.sum()}")
    base_xy = np.c_[base[where, 0].astype("f4") / 127.5 - 1, 1 - base[where, 1].astype("f4") / 127.5]  # to (right, down), game green points up
    out_xy = reoriented(base_xy, layer[where, :2])
    result[where, 0] = np.clip((out_xy[:, 0] + 1) * 127.5 + 0.5, 0, 255).astype("u1")
    result[where, 1] = np.clip((1 - out_xy[:, 1]) * 127.5 + 0.5, 0, 255).astype("u1")
    untouched = ~where
    print(f"outside the bandage, identical to HR3: {np.array_equal(result[untouched], base[untouched])}; blue and alpha identical everywhere: {np.array_equal(result[..., 2:], base[..., 2:])}")
    height_check(height_path, bibo_uv, rows, cols, part, base, result, where)
    path = str(out / "c0901b0001_b_n.tex")
    tex_io.write_bgra(path, result)
    print(f"read back identical: {np.array_equal(tex_io.read_bgra(path), result)}")
    Image.fromarray(result[..., :3]).save(out / "new_normal.png")
    Image.fromarray(base[..., :3]).save(out / "base_normal.png")


if __name__ == "__main__":
    main()
