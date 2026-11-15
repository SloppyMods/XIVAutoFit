"""Move a tattoo painted for the TBSE male body onto the hrBody 3 (HR3) Chubby male body, through 3D.

    python3 tattoo_transfer.py ink    # separate the ink from the TBSE skin it was painted on; report ink per body part
    python3 tattoo_transfer.py map    # for each HR3 texture pixel, find the matching spot on the TBSE texture
    python3 tattoo_transfer.py bake   # sample the ink through that map, composite onto HR3's skin, write the .tex

A texture pixel on a body is called a texel. Everything is written to builds/_tattoo/. Reads the Penumbra library, never writes it.
"""
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage
from scipy.spatial import cKDTree

sys.path.insert(0, str(Path(__file__).resolve().parent))
import glb_raw  # noqa: E402
import male_body as mb  # noqa: E402
import mdl_read  # noqa: E402
import tex_io  # noqa: E402

OUT = Path(__file__).resolve().parent.parent / "builds" / "_tattoo"
LIB = "/mnt/STORAGE/Penumbra/"
TATTOO = LIB + "[SilV] Skiggles - TBSE Tattoo/Body - c0101b0001_top/Texture(s)/chara/human/c0101/obj/body/b0001/texture/--c0101b0001_b_d.tex"
TBSE_SKIN = LIB + "The Body SE/p2/step 2- midlander, elezen, miqo'te/type 0/chara/human/c0101/obj/body/b0001/texture/c0101b0001_b_d.tex"
_H = LIB + "The hrBody 3 IVCS2 4K V1_0_0/"
_T = LIB + "The Body SE/"
TBSE_PARTS = {"top": _T + "common/1/c0101e0000_top.mdl",
              "dwn": _T + "p3/step 6- smallclothes options/gen a/chara/equipment/e0000/model/c0101e0000_dwn.mdl",
              "glv": _T + "common/3/c0101e0000_glv.mdl", "sho": _T + "common/7/c0101e0000_sho.mdl"}
HR3_PARTS = {"top": _H + "p1/body type/chubby/chara/equipment/e0000/model/c0901e0000_top.mdl",
             "dwn": _H + "common/3/c0901e0000_dwn.mdl",  # Flaccid M Uncut Loose: bare hips; every skin texel of the underwear model is inside it
             "glv": _H + "common/8/c0901e0000_glv.mdl", "sho": _H + "common/9/c0901e0000_sho.mdl"}
X = Path.home() / "Downloads" / "Male Mods"
REST_TBSE, REST_HR3 = X / "c0101e6025_top.glb", X / "c0901e6024_top.glb"
SKIN_MATERIAL = "b0001_b."  # the bare-skin material; fur (_h), inner mouth (_i) and underwear use other textures
INK_LOW, INK_HIGH = 0.02, 0.06  # ink opacity below LOW is treated as paint noise, above HIGH is kept whole
HR3_SIZE = 4096
PAD_INK, PAD_HR3 = 16, 16
SCHEDULE = (900.0, 600.0, 350.0, 180.0, 90.0, 40.0, 18.0, 8.0, 8.0, 4.0, 4.0, 2.0, 2.0, 1.0, 1.0, 0.5, 0.5, 0.25)
REGISTER_STEP = 0.8
HR3_GENITAL_BOX = (0.60, 0.385, 0.66, 0.50)  # UV box of the small rear crotch island; the shaft island has v above 1
CANDIDATES = 12
TRUSTED_GAP = 0.02  # metres; a match further off the surface than this is not trusted
TRUSTED_STRIDE, TRUSTED_CANDIDATES = 3, 16
RIM_GAP = 0.0015  # metres; a match this far off an open mesh edge is an edge smear, not a real match
MIDLINE = 0.006  # metres; closer to x = 0 than this, left and right are not told apart


@dataclass(frozen=True)
class Parts:
    """Skin meshes merged into one, keeping UV and which body part each triangle came from."""
    positions: np.ndarray
    triangles: np.ndarray
    uv: np.ndarray
    bones: tuple[str, ...]
    joints: np.ndarray
    weights: np.ndarray
    part: np.ndarray  # per triangle, index into names
    names: tuple[str, ...]


def load_parts(paths: dict[str, str], keep: tuple[str, ...], drop_genitals: bool = False) -> Parts:
    positions, triangles, uv, joints, weights, part = [], [], [], [], [], []
    bone_ids: dict[str, int] = {}
    count = 0
    names = tuple(paths)
    for index, name in enumerate(names):
        if name not in keep:
            continue
        model = mdl_read.read_mdl(paths[name])
        for mesh in model.meshes:
            if SKIN_MATERIAL not in mesh.material:
                continue
            remap = np.array([bone_ids.setdefault(bone, len(bone_ids)) for bone in model.bones])
            positions.append(mesh.positions)
            triangles.append(mesh.triangles + count)
            uv.append(mesh.uv)
            joints.append(remap[mesh.joints])
            weights.append(mesh.weights)
            part.append(np.full(len(mesh.triangles), index))
            count += len(mesh.positions)
    width = max(j.shape[1] for j in joints)
    joints = [np.pad(j, ((0, 0), (0, width - j.shape[1]))) for j in joints]
    weights = [np.pad(w, ((0, 0), (0, width - w.shape[1]))) for w in weights]
    merged, uv_all, part_all = np.vstack(triangles), np.vstack(uv), np.concatenate(part)
    if drop_genitals:
        # The tattoo has no art for these islands and TBSE's matching model has no such geometry, so they stay plain skin.
        centre = uv_all[merged].mean(1)
        low_u, low_v, high_u, high_v = HR3_GENITAL_BOX
        boxed = (centre[:, 0] > low_u) & (centre[:, 0] < high_u) & (centre[:, 1] > low_v) & (centre[:, 1] < high_v)
        drop = (part_all == names.index("dwn")) & (boxed | (centre[:, 1] > 1.0))
        merged, part_all = merged[~drop], part_all[~drop]
    return Parts(np.vstack(positions), merged, uv_all, tuple(bone_ids), np.vstack(joints), np.vstack(weights), part_all, names)


def rasterize(uv: np.ndarray, triangles: np.ndarray, size: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Which triangle covers each texel, with barycentric weights. Row 0 is v = 0. Returns (face, bary, overlap count)."""
    face = np.full((size, size), -1, "i4")
    bary = np.zeros((size, size, 3), "f4")
    hits = np.zeros((size, size), "u1")
    corners = uv[triangles] * size - 0.5  # texel centres sit at integer coordinates after this shift
    for index, (a, b, c) in enumerate(corners):
        low = np.maximum(np.floor(np.minimum(np.minimum(a, b), c)).astype(int), 0)
        high = np.minimum(np.ceil(np.maximum(np.maximum(a, b), c)).astype(int), size - 1)
        if (high < low).any():
            continue
        xs, ys = np.meshgrid(np.arange(low[0], high[0] + 1), np.arange(low[1], high[1] + 1))
        v0, v1 = b - a, c - a
        den = v0[0] * v1[1] - v1[0] * v0[1]
        if abs(den) < 1e-12:
            continue
        dx, dy = xs - a[0], ys - a[1]
        w1 = (dx * v1[1] - v1[0] * dy) / den
        w2 = (v0[0] * dy - dx * v0[1]) / den
        w0 = 1 - w1 - w2
        inside = (w0 >= -1e-4) & (w1 >= -1e-4) & (w2 >= -1e-4)
        row, col = ys[inside], xs[inside]
        face[row, col] = index
        bary[row, col] = np.c_[w0[inside], w1[inside], w2[inside]]
        hits[row, col] = np.minimum(hits[row, col].astype(int) + 1, 255)
    return face, bary, hits


def closest_on_triangles(points: np.ndarray, a: np.ndarray, b: np.ndarray, c: np.ndarray) -> np.ndarray:
    """Barycentric weights of the closest point on each triangle to each point (all arrays have the same length)."""
    ab, ac, ap = b - a, c - a, points - a
    d1, d2 = (ab * ap).sum(1), (ac * ap).sum(1)
    bp = points - b
    d3, d4 = (ab * bp).sum(1), (ac * bp).sum(1)
    cp = points - c
    d5, d6 = (ab * cp).sum(1), (ac * cp).sum(1)
    vc = d1 * d4 - d3 * d2
    vb = d5 * d2 - d1 * d6
    va = d3 * d6 - d5 * d4
    with np.errstate(divide="ignore", invalid="ignore"):
        denom = 1.0 / (va + vb + vc)
        v, w = vb * denom, vc * denom
        out = np.c_[1 - v - w, v, w]
        region = (d1 <= 0) & (d2 <= 0)  # corner a
        out[region] = (1, 0, 0)
        mask = (d3 >= 0) & (d4 <= d3)  # corner b
        out[mask] = (0, 1, 0)
        mask = (d6 >= 0) & (d5 <= d6)  # corner c
        out[mask] = (0, 0, 1)
        mask = (vc <= 0) & (d1 >= 0) & (d3 <= 0)  # edge ab
        t = d1 / (d1 - d3)
        out[mask] = np.c_[1 - t, t, np.zeros_like(t)][mask]
        mask = (vb <= 0) & (d2 >= 0) & (d6 <= 0)  # edge ac
        t = d2 / (d2 - d6)
        out[mask] = np.c_[1 - t, np.zeros_like(t), t][mask]
        mask = (va <= 0) & ((d4 - d3) >= 0) & ((d5 - d6) >= 0)  # edge bc
        t = (d4 - d3) / ((d4 - d3) + (d5 - d6))
        out[mask] = np.c_[np.zeros_like(t), 1 - t, t][mask]
    return out


def separate_ink(tattoo: np.ndarray, skin: np.ndarray) -> np.ndarray:
    """Colour-to-alpha: the least opaque ink that explains each pixel, given the skin it was painted on. Returns premultiplied RGBA 0..1."""
    t, s = tattoo[..., :3].astype("f4") / 255, skin[..., :3].astype("f4") / 255
    darker = np.clip((s - t) / np.maximum(s, 1e-3), 0, 1)
    brighter = np.clip((t - s) / np.maximum(1 - s, 1e-3), 0, 1)
    alpha = np.maximum(darker, brighter).max(2)
    with np.errstate(divide="ignore", invalid="ignore"):
        ink = np.where(alpha[..., None] > 1e-4, (t - (1 - alpha[..., None]) * s) / alpha[..., None], 0)
    ink = np.clip(ink, 0, 1)
    keep = np.clip((alpha - INK_LOW) / (INK_HIGH - INK_LOW), 0, 1)
    keep = keep * keep * (3 - 2 * keep)
    final = alpha * keep
    return np.dstack([ink * final[..., None], final])


def grow(premultiplied: np.ndarray, inside: np.ndarray, reach: int) -> np.ndarray:
    """Copy each island's edge colours outward up to reach texels, so filtering at a seam does not pull in empty paint."""
    distance, (row, col) = ndimage.distance_transform_edt(~inside, return_indices=True)
    out = premultiplied.copy()
    near = (distance > 0) & (distance <= reach)
    out[near] = premultiplied[row[near], col[near]]
    out[distance > reach] = 0
    return out


def sample_bilinear(image: np.ndarray, uv: np.ndarray) -> np.ndarray:
    height, width = image.shape[:2]
    x, y = uv[:, 0] * width - 0.5, uv[:, 1] * height - 0.5
    x0, y0 = np.clip(np.floor(x).astype(int), 0, width - 1), np.clip(np.floor(y).astype(int), 0, height - 1)
    x1, y1 = np.minimum(x0 + 1, width - 1), np.minimum(y0 + 1, height - 1)
    fx, fy = (x - x0)[:, None], (y - y0)[:, None]
    return (image[y0, x0] * (1 - fx) + image[y0, x1] * fx) * (1 - fy) + (image[y1, x0] * (1 - fx) + image[y1, x1] * fx) * fy


def stage_ink() -> None:
    tattoo, skin = tex_io.read_bgra(TATTOO), tex_io.read_bgra(TBSE_SKIN)
    ink = separate_ink(tattoo, skin)
    tbse = load_parts(TBSE_PARTS, tuple(TBSE_PARTS))
    face, _, _ = rasterize(tbse.uv, tbse.triangles, 2048)
    alpha = ink[..., 3]
    print(f"ink opacity: mean {alpha.mean():.3f}, texels over 0.5: {(alpha > 0.5).mean():.3f}")
    for index, name in enumerate(tbse.names):
        cover = (face >= 0) & (tbse.part[np.maximum(face, 0)] == index)
        print(f"  {name}: covers {cover.sum()} texels, ink over 0.5 on {(alpha[cover] > 0.5).sum()} ({(alpha[cover] > 0.5).mean():.3f}), mean opacity {alpha[cover].mean():.3f}")
    print(f"  outside any island: ink over 0.5 on {(alpha[face < 0] > 0.5).sum()} texels, mean opacity {alpha[face < 0].mean():.4f}")
    np.save(OUT / "ink_premult.npy", ink.astype("f4"))
    Image.fromarray((alpha * 255).astype("u1")).resize((1024, 1024), Image.BOX).save(OUT / "ink_alpha.png")
    sheet = (ink[..., :3] + (1 - alpha[..., None])) * 255
    Image.fromarray(sheet.astype("u1")).resize((1024, 1024), Image.BOX).save(OUT / "ink_on_white.png")


def register_bodies(keep: tuple[str, ...]) -> tuple[Parts, Parts, np.ndarray]:
    tbse, hr3 = load_parts(TBSE_PARTS, keep), load_parts(HR3_PARTS, keep, drop_genitals=True)
    doc_a, blob_a = glb_raw.load(str(REST_TBSE))
    doc_b, blob_b = glb_raw.load(str(REST_HR3))
    names, rest_a = glb_raw.joint_matrices(doc_a, blob_a)
    parents = glb_raw.joint_parents(doc_a)
    names_b, rest_b = glb_raw.joint_matrices(doc_b, blob_b)
    if names != names_b:
        sys.exit("skeleton exports list different joints")
    table = mb.RaceTable(names, parents, rest_a, rest_b)
    placed = mb.apply_matrices(tbse.positions, table.blend(tbse.bones, tbse.joints, tbse.weights))
    samples = mb.sample_surface(hr3.positions, hr3.triangles)
    moved = mb.register(mb.Body(tbse.positions, tbse.triangles, tbse.bones, tbse.joints, tbse.weights), placed, samples, SCHEDULE, step=REGISTER_STEP, max_move=0.15)
    return tbse, hr3, moved


def rim_faces(points: np.ndarray, triangles: np.ndarray) -> np.ndarray:
    """True for triangles touching an open edge of the surface (an edge only one triangle uses)."""
    _, welded = mb.weld(points, triangles)
    edges = np.sort(np.vstack([welded[:, [0, 1]], welded[:, [1, 2]], welded[:, [2, 0]]]), axis=1)
    _, inverse, counts = np.unique(edges, axis=0, return_inverse=True, return_counts=True)
    open_edge = (counts[inverse.ravel()] == 1).reshape(3, -1).T
    return open_edge.any(1)


def match_texels(points: np.ndarray, normals: np.ndarray, tree: cKDTree, sample_faces: np.ndarray, corners: tuple[np.ndarray, np.ndarray, np.ndarray],
                 tbse_normals: np.ndarray, tbse: Parts, candidates: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Closest spot on the moved TBSE surface for each HR3 texel. Returns (TBSE UV, gap in metres, or 10+ if no usable match; TBSE face)."""
    a, b, c = corners
    out_uv, out_gap, out_face = np.zeros((len(points), 2), "f4"), np.zeros(len(points), "f4"), np.zeros(len(points), "i4")
    chunk = 300_000
    for start in range(0, len(points), chunk):
        end = min(start + chunk, len(points))
        p, n, count = points[start:end], normals[start:end], end - start
        _, near = tree.query(p, k=candidates, workers=3)
        flat_p, flat_f = np.repeat(p, candidates, axis=0), sample_faces[near].ravel()
        solved = closest_on_triangles(flat_p, a[flat_f], b[flat_f], c[flat_f])
        where = solved[:, 0, None] * a[flat_f] + solved[:, 1, None] * b[flat_f] + solved[:, 2, None] * c[flat_f]
        distance = np.linalg.norm(where - flat_p, axis=1).reshape(count, candidates)
        facing = (tbse_normals[flat_f] * np.repeat(n, candidates, axis=0)).sum(1).reshape(count, candidates)
        side = np.sign(where[:, 0]).reshape(count, candidates) * np.sign(p[:, 0])[:, None]
        same = (side >= 0) | (np.abs(p[:, 0])[:, None] < MIDLINE)
        score = distance + (facing < 0.15) * 1.0 + (~same) * 1.0
        pick, rows = score.argmin(1), np.arange(count)
        base = rows * candidates + pick
        chosen, weights = flat_f[base], solved[base]
        out_uv[start:end] = (tbse.uv[tbse.triangles[chosen]] * weights[:, :, None]).sum(1)
        out_gap[start:end] = distance[rows, pick] + 10 * (score[rows, pick] >= 1.0)
        out_face[start:end] = chosen
    return out_uv, out_gap, out_face


def copy_from_trusted(points: np.ndarray, normals: np.ndarray, uv: np.ndarray, untrusted: np.ndarray) -> np.ndarray:
    """For texels with no clean match, take the mapping of the closest cleanly matched HR3 texel on the same side and facing the same way."""
    trusted = np.where(~untrusted)[0][::TRUSTED_STRIDE]
    tree = cKDTree(points[trusted])
    wanted = np.where(untrusted)[0]
    out = uv.copy()
    for start in range(0, len(wanted), 200_000):
        chunk = wanted[start:start + 200_000]
        _, near = tree.query(points[chunk], k=TRUSTED_CANDIDATES, workers=3)
        facing = (normals[trusted[near]] * normals[chunk][:, None, :]).sum(2)
        side = (np.sign(points[trusted[near], 0]) * np.sign(points[chunk, 0])[:, None] >= 0) | (np.abs(points[chunk, 0])[:, None] < MIDLINE)
        usable = (facing > 0.2) & side
        pick = usable.argmax(1)
        out[chunk] = uv[trusted[near[np.arange(len(chunk)), pick]]]
    return out


def stage_map(keep: tuple[str, ...]) -> None:
    tbse, hr3, moved = register_bodies(keep)
    np.save(OUT / "tbse_moved.npy", moved)
    ids, welded = mb.weld(hr3.positions, hr3.triangles)
    welded_points = np.zeros((ids.max() + 1, 3))
    welded_points[ids] = hr3.positions
    normals = mb.vertex_normals(welded_points, welded)[ids]
    face, bary, hits = rasterize(hr3.uv, hr3.triangles, HR3_SIZE)
    rows, cols = np.where(face >= 0)
    print(f"HR3 skin covers {len(rows)} of {HR3_SIZE ** 2} texels; texels drawn by two or more triangles: {(hits > 1).sum()}")
    tri = hr3.triangles[face[rows, cols]]
    weights = bary[rows, cols][:, :, None]
    points = (hr3.positions[tri] * weights).sum(1)
    point_normals = (normals[tri] * weights).sum(1)
    point_normals /= np.maximum(np.linalg.norm(point_normals, axis=1, keepdims=True), 1e-9)
    area = mb.face_normals(moved, tbse.triangles)
    tbse_normals = area / np.maximum(np.linalg.norm(area, axis=1, keepdims=True), 1e-12)
    samples = mb.sample_surface(moved, tbse.triangles, spacing=0.0035, seed=11)
    a, b, c = moved[tbse.triangles[:, 0]], moved[tbse.triangles[:, 1]], moved[tbse.triangles[:, 2]]
    corners = (a, b, c)
    tree = cKDTree(samples.points)
    print(f"TBSE lookup points: {len(samples.points)}")
    out_uv, out_gap, out_face = match_texels(points, point_normals, tree, samples.faces, corners, tbse_normals, tbse, CANDIDATES)
    rim = rim_faces(tbse.positions, tbse.triangles)
    untrusted = (rim[out_face] & (out_gap > RIM_GAP)) | (out_gap > TRUSTED_GAP)
    print(f"texels with no clean TBSE match, copied from the nearest clean HR3 texel: {untrusted.sum()}")
    out_uv = copy_from_trusted(points, point_normals, out_uv, untrusted)
    out_gap[untrusted] = 0.0
    bad = out_gap >= 10
    gap = out_gap[~bad] * 1000
    print(f"mapped: no usable match on {bad.sum()} texels; gap to TBSE surface mm median {np.median(gap):.2f}, p90 {np.percentile(gap, 90):.2f}, p99 {np.percentile(gap, 99):.2f}, max {gap.max():.1f}")
    hr3_uv = (np.c_[cols + 0.5, rows + 0.5] / HR3_SIZE).astype("f4")
    delta = np.linalg.norm((out_uv - hr3_uv) * 2048, axis=1)
    print(f"UV difference (2048 texture, texels): median {np.median(delta):.0f}, p10 {np.percentile(delta, 10):.0f}, p90 {np.percentile(delta, 90):.0f}; within 8 texels: {(delta < 8).mean():.4f}")
    np.savez(OUT / "map.npz", rows=rows.astype("i4"), cols=cols.astype("i4"), uv=out_uv, gap=out_gap, part=hr3.part[face[rows, cols]])


def stage_bake() -> None:
    data = np.load(OUT / "map.npz")
    rows, cols, uv, gap = data["rows"], data["cols"], data["uv"], data["gap"]
    ink = np.load(OUT / "ink_premult.npy")
    tbse = load_parts(TBSE_PARTS, tuple(TBSE_PARTS))
    face, _, _ = rasterize(tbse.uv, tbse.triangles, 2048)
    ink = grow(ink, face >= 0, PAD_INK)
    sampled = sample_bilinear(ink, uv).astype("f4")
    sampled[gap >= 10] = 0
    layer = np.zeros((HR3_SIZE, HR3_SIZE, 4), "f4")
    layer[rows, cols] = sampled
    inside = np.zeros((HR3_SIZE, HR3_SIZE), bool)
    inside[rows, cols] = True
    layer = grow(layer, inside, PAD_HR3)
    skin = np.load(OUT / "hr3_b_d.npy")
    print(f"HR3 skin {skin.shape}, tattoo layer max opacity {layer[..., 3].max():.3f}")
    alpha = layer[..., 3:]
    colour = np.clip(skin[..., :3].astype("f4") / 255 * (1 - alpha) + layer[..., :3], 0, 1)
    out = np.dstack([(colour * 255 + 0.5).astype("u1"), skin[..., 3]])
    np.save(OUT / "hr3_tattoo_rgba.npy", out)
    tex_io.write_bgra(str(OUT / "c0901b0001_b_d.tex"), out)
    back = tex_io.read_bgra(str(OUT / "c0901b0001_b_d.tex"))
    print(f"written and read back identical: {np.array_equal(back, out)}, {tex_io.read_header(str(OUT / 'c0901b0001_b_d.tex'))}")
    Image.fromarray(out[..., :3]).resize((1024, 1024), Image.BOX).save(OUT / "hr3_tattoo.png")
    Image.fromarray((layer[..., 3] * 255).astype("u1")).resize((1024, 1024), Image.BOX).save(OUT / "hr3_ink_alpha.png")


if __name__ == "__main__":
    stage = sys.argv[1]
    if stage == "ink":
        stage_ink()
    elif stage == "map":
        stage_map(tuple(sys.argv[2].split(",")) if len(sys.argv) > 2 else tuple(TBSE_PARTS))
    elif stage == "bake":
        stage_bake()
    else:
        sys.exit("stage must be ink, map or bake")
