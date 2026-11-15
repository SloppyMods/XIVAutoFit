"""Paint the neck of an FFXIV face colour texture solid black, to blend with a body tattoo's black neck, and package it as a Penumbra mod.

    python3 face_black_neck.py [--cutoff Y] [--slope S] [--update] [--no-mod]

Each face vertex gets w = clip((cut(z) - y) / ramp, 0, 1), cut(z) = cutoff + slope*(z - 0.10) - chin_dip*smoothstep on z > chin_z,
so the black fades along the 3D surface under the jaw. w is rasterised through the UVs (barycentric), lightly blurred and grown
into the padding. Alpha and every texel with weight 0 stay byte-identical.

Writes builds/_face/ (texture, mask, comparisons, numbers) and the mod folder under /mnt/STORAGE/Penumbra.
"""
import argparse
import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from scipy import ndimage
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent))
import mdl_read  # noqa: E402
import tex_io  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "builds" / "_face"
SOURCE = Path("/home/you/Downloads/Telegram Desktop/Reborn [Bibo+] - Little Hideout Mods/Reborn [Bibo+]/[LOOSE FILES]/Overlay Face/c0801f0002_fac_base.tex")
MODEL = Path("/mnt/STORAGE/Penumbra/[SATSU] Alphinaud_For_Miqo'te_Females/face 104 ( keeper )/elzen ears/chara/human/c0801/obj/face/f0104/model/c0801f0104_fac.mdl")
BODY_TEX = ROOT / "builds" / "_vampire" / "diffuse_black_neck.tex"
BODY_MDL = Path("/mnt/STORAGE/Penumbra/[HS] Bibo+ (Bibo+ Base Install)/files/breasts - small clothes/nude - small/chara/equipment/e0000/model/c0201e0000_top.mdl")
PENUMBRA = Path("/mnt/STORAGE/Penumbra")
MOD_DIR = PENUMBRA / "Reborn Face Black Neck [Miqo'te F]"
MOD_TEX = "chara/c0801_fac_base_black_neck.tex"
FACE_IDS = ("0001", "0002", "0003", "0004", "0101", "0102", "0103", "0104")
WIDTH, HEIGHT = 1024, 2048
GROW_PX = 4
BLUR_SIGMA = 1.5
CHIN_BLEND = 0.03  # z span over which the cutoff dips onto the chin's front face
PIVOT_Z = 0.10  # game z of the chin front; the cutoff plane tilts around it
MOD_NAME = "Reborn Face Black Neck [Miqo'te F]"
DESCRIPTION = (
    "Face colour texture of Reborn (Little Hideout) with the neck area painted solid black, to blend with the black neck "
    "of a body tattoo. Everything above the jaw and the ear are unchanged.\n\n"
    "Priority: in the collection this mod must sit at a HIGHER priority than the Alphinaud mod (which supplies the face "
    "texture it replaces), or the Alphinaud texture wins.\n\n"
    "Pairs with the black-neck options of the Unholy and Vampire Heartbeat body mods."
)


def main_piece(pos: np.ndarray, tris: np.ndarray) -> np.ndarray:
    """Per-triangle flag: part of the largest welded piece (head + neck + ears). The earring is separate small pieces."""
    _, weld = np.unique(np.round(pos, 5), axis=0, return_inverse=True)
    weld = weld.ravel()
    n = weld.max() + 1
    a = np.r_[weld[tris[:, 0]], weld[tris[:, 1]]]
    b = np.r_[weld[tris[:, 1]], weld[tris[:, 2]]]
    _, label = connected_components(coo_matrix((np.ones(len(a)), (a, b)), shape=(n, n)))
    tri_label = label[weld[tris[:, 0]]]
    return tri_label == np.bincount(tri_label).argmax()


def neck_weight(args) -> tuple[np.ndarray, int]:
    """Texture-sized float weight (0..1): 1 solid black under the jaw, fading to 0 up the surface.

    Per-vertex w = clip((cut(z) - y) / RAMP, 0, 1) from the 3D position, then barycentric interpolation over the triangles'
    UVs (max where they overlap), a light blur, and a dilation into the padding. cut(z) tilts with the jaw and dips on the
    chin's front face."""
    mesh = next(m for m in mdl_read.read_mdl(str(MODEL)).meshes if "fac_a" in m.material)
    pos, uv = mesh.positions, mesh.uv * [WIDTH, HEIGHT]
    front = np.clip((pos[:, 2] - args.chin_z) / CHIN_BLEND, 0.0, 1.0)
    front = front * front * (3 - 2 * front)  # smoothstep
    cut = args.cutoff + args.slope * (pos[:, 2] - PIVOT_Z) - args.chin_dip * front
    vertex_w = np.clip((cut - pos[:, 1]) / args.ramp, 0.0, 1.0)
    centroid = pos[mesh.triangles].mean(1)
    keep = (np.abs(centroid[:, 0]) < args.ear_x) & main_piece(pos, mesh.triangles)  # |x| >= ear_x is the ear
    weight = np.zeros((HEIGHT, WIDTH), np.float32)
    count = 0
    for tri in mesh.triangles[keep]:
        if vertex_w[tri].max() <= 0:
            continue
        count += 1
        p = uv[tri]
        x0, x1 = int(max(np.floor(p[:, 0].min()) - 1, 0)), int(min(np.ceil(p[:, 0].max()) + 1, WIDTH - 1))
        y0, y1 = int(max(np.floor(p[:, 1].min()) - 1, 0)), int(min(np.ceil(p[:, 1].max()) + 1, HEIGHT - 1))
        gx, gy = np.meshgrid(np.arange(x0, x1 + 1) + 0.5, np.arange(y0, y1 + 1) + 0.5)
        det = (p[1, 1] - p[2, 1]) * (p[0, 0] - p[2, 0]) + (p[2, 0] - p[1, 0]) * (p[0, 1] - p[2, 1])
        if abs(det) < 1e-9:
            continue
        l0 = ((p[1, 1] - p[2, 1]) * (gx - p[2, 0]) + (p[2, 0] - p[1, 0]) * (gy - p[2, 1])) / det
        l1 = ((p[2, 1] - p[0, 1]) * (gx - p[2, 0]) + (p[0, 0] - p[2, 0]) * (gy - p[2, 1])) / det
        l2 = 1 - l0 - l1
        inside = (l0 >= -0.02) & (l1 >= -0.02) & (l2 >= -0.02)
        w = np.clip(l0, 0, 1) * vertex_w[tri[0]] + np.clip(l1, 0, 1) * vertex_w[tri[1]] + np.clip(l2, 0, 1) * vertex_w[tri[2]]
        block = weight[y0:y1 + 1, x0:x1 + 1]
        np.maximum(block, np.where(inside, w, 0).astype(np.float32), out=block)
    blurred = ndimage.gaussian_filter(weight, BLUR_SIGMA)
    return np.clip(ndimage.maximum_filter(blurred, size=2 * GROW_PX + 1), 0, 1), count


def measure_body_black() -> np.ndarray:
    """Median colour of near-black texels over the Bibo+ body's neck (triangles above y 1.42), through the body UVs."""
    mesh = mdl_read.read_mdl(str(BODY_MDL)).meshes[0]
    size = 4096
    uv = mesh.uv.copy()
    uv[:, 1] %= 1.0  # the body's v runs -1..0
    image = Image.new("L", (size, size), 0)
    draw = ImageDraw.Draw(image)
    for tri in mesh.triangles:
        if mesh.positions[tri, 1].min() > 1.42:
            draw.polygon([tuple(uv[i] * size) for i in tri], fill=255)
    texels = tex_io.read_bgra(str(BODY_TEX))[np.asarray(image) > 0][:, :3].astype(int)
    dark = texels[texels.sum(1) < 60]
    print(f"body neck: {len(texels)} texels, {len(dark)} near-black")
    return np.median(dark, 0)


def build_texture(args) -> dict:
    OUT.mkdir(parents=True, exist_ok=True)
    source = np.array(tex_io.read_bgra(str(SOURCE)))
    weight, tri_count = neck_weight(args)
    mask = weight > 0

    rgb = source[..., :3].astype(np.float32)
    neck = rgb[weight >= 0.99]
    darkest = neck[np.argsort(neck.sum(1))[: max(1, len(neck) // 20)]]
    face_ink = np.median(darkest, 0)
    body_black = measure_body_black()
    print(f"face ink (darkest 5% of neck): {face_ink}   body black: {body_black}")
    black = body_black if args.black == "body" else face_ink
    out = source.copy()
    mixed = rgb * (1 - weight[..., None]) + black * weight[..., None]
    out[..., :3] = np.clip(np.rint(mixed), 0, 255).astype("u1")
    tex_path = OUT / "c0801_fac_base_black_neck.tex"
    tex_io.write_bgra(str(tex_path), out)

    changed = np.any(out != source, axis=-1)
    touched = weight > 0
    back = tex_io.read_bgra(str(tex_path))
    mip1 = tex_io.read_mip(str(tex_path), 1)
    top = back.astype(np.uint32)
    expect = ((top.reshape(HEIGHT // 2, 2, WIDTH // 2, 2, 4).sum((1, 3)) + 2) // 4).astype("u1")
    report = {
        "triangles": tri_count,
        "black": [float(v) for v in black],
        "face_ink": [float(v) for v in face_ink],
        "body_black": [float(v) for v in body_black],
        "mask_px": int(mask.sum()),
        "texels_changed": int(changed.sum()),
        "texels_untouched": int((~changed).sum()),
        "outside_mask_identical": bool(np.array_equal(out[~touched], source[~touched])),
        "alpha_identical": bool(np.array_equal(out[..., 3], source[..., 3])),
        "readback_identical": bool(np.array_equal(back, out)),
        "mip1_exact": bool(np.array_equal(mip1, expect)),
        "mip_count": tex_io.read_header(str(tex_path))[3],
    }
    for key, value in report.items():
        print(f"{key}: {value}")
    evidence(source, out, mask, weight)
    return report


def evidence(source: np.ndarray, out: np.ndarray, mask: np.ndarray, weight: np.ndarray) -> None:
    rgb = Image.fromarray(np.ascontiguousarray(source[..., :3]))
    overlay = np.array(rgb).astype(np.float32)
    overlay[mask] = overlay[mask] * 0.45 + np.array([255, 0, 0]) * 0.55 * weight[mask][:, None] + np.array([255, 160, 0]) * 0.55 * (1 - weight[mask][:, None])
    Image.fromarray(overlay.astype("u1")).resize((512, 1024)).save(OUT / "mask_over_texture.png")
    pair = Image.new("RGB", (1024, 1024))
    pair.paste(rgb.resize((512, 1024)), (0, 0))
    pair.paste(Image.fromarray(np.ascontiguousarray(out[..., :3])).resize((512, 1024)), (512, 0))
    pair.save(OUT / "before_after.png")


def write_mod(update: bool) -> None:
    existing = MOD_DIR / "meta.json"
    identifier = str(uuid.uuid4())
    if MOD_DIR.exists():
        if not update:
            sys.exit(f"{MOD_DIR} exists; pass --update to overwrite it")
        identifier = json.loads(existing.read_text())["Identifier"]
    meta = {"FileVersion": 4}  # Penumbra's current format: groups inline in meta.json
    meta.update({
        "Identifier": identifier,
        "LastWrite": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.0000000Z"),
        "Name": MOD_NAME,
        "Author": "Little Hideout (Reborn) (edit: black neck)",
        "Description": DESCRIPTION,
        "Version": "1.0",
        "Website": "",
        "ModTags": ["Miqote", "Face", "Tattoo"],
    })
    meta["DefaultData"] = {"Files": {f"chara/human/c0801/obj/face/f{i}/texture/c0801f{i}_fac_base.tex": MOD_TEX.replace("/", "\\") for i in FACE_IDS}}
    meta["Groups"] = []
    (MOD_DIR / "chara").mkdir(parents=True, exist_ok=True)
    (MOD_DIR / "chara" / "c0801_fac_base_black_neck.tex").write_bytes((OUT / "c0801_fac_base_black_neck.tex").read_bytes())
    existing.write_text(json.dumps(meta, indent="\t"))
    print(f"mod written: {MOD_DIR}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cutoff", type=float, default=1.395)
    parser.add_argument("--slope", type=float, default=-0.3)
    parser.add_argument("--ramp", type=float, default=0.008)
    parser.add_argument("--chin-z", type=float, default=0.08)
    parser.add_argument("--chin-dip", type=float, default=0.012)
    parser.add_argument("--ear-x", type=float, default=0.07)
    parser.add_argument("--black", choices=("body", "face"), default="body")
    parser.add_argument("--update", action="store_true")
    parser.add_argument("--no-mod", action="store_true")
    args = parser.parse_args()
    if not args.no_mod and MOD_DIR.exists() and not args.update:
        sys.exit(f"{MOD_DIR} exists; pass --update to overwrite it")
    report = build_texture(args)
    (OUT / "report.json").write_text(json.dumps(report, indent=2))
    if not args.no_mod:
        write_mod(args.update)


if __name__ == "__main__":
    main()
