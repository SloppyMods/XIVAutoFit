"""Redo the HR3-to-TBSE texture map on the fingers, where the closest-point match slides along and between fingers.

    python3 finger_remap.py     # reads builds/_tattoo/map.npz, writes builds/_tattoo/map_fingers.npz

A finger is treated as a tube. Each point gets two numbers: how far along the finger it is (0 at the base, 1 at the tip) and its angle
around the finger. An HR3 finger texel takes the TBSE spot on the same finger with the same two numbers, so anything painted at a set
distance along a finger stays at that distance. Near the finger base the new mapping fades into the old one so the knuckles don't step.
"""
import re
import sys
from pathlib import Path

import numpy as np
from scipy.spatial import cKDTree

sys.path.insert(0, str(Path(__file__).resolve().parent))
import glb_raw  # noqa: E402
import male_body as mb  # noqa: E402
import tattoo_transfer as tt  # noqa: E402

FINGER_BONE = re.compile(r"^(?:j|iv)_(oya|hito|naka|kusu|ko)_([abc])_([lr])$")
ALONG_WEIGHT = 3.0  # how much one finger length counts against one radian-scale step around the finger, in the lookup
SAMPLE_SPACING = 0.0005
BLEND_END = 0.18  # fraction of the finger length over which the new mapping fades in from the base
SAME_ISLAND = 0.05  # UV distance; if old and new are further apart they are on different islands and cannot be mixed


def labels(parts: tt.Parts) -> np.ndarray:
    """Each vertex's finger as a string like 'hito_l', or '' when its heaviest bone is not a finger bone."""
    heaviest = parts.joints[np.arange(len(parts.joints)), parts.weights.argmax(1)]
    names = []
    for bone in parts.bones:
        found = FINGER_BONE.match(bone)
        names.append(f"{found[1]}_{found[3]}" if found else "")
    return np.array(names, dtype=object)[heaviest]


def bone_positions(path: Path) -> dict[str, np.ndarray]:
    doc, blob = glb_raw.load(str(path))
    names, rest = glb_raw.joint_matrices(doc, blob)
    return {name: rest[index][:3, 3] for index, name in enumerate(names)}


def chain_of(finger: str, bones: dict[str, np.ndarray], tips: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Bone joints from finger base to tip, ending at the finger's furthest vertex. Returns (points, reference direction for angles)."""
    name, side = finger.split("_")
    points = [bones[f"{prefix}_{name}_{level}_{side}"] for prefix, level in (("j", "a"), ("j", "b"), ("iv", "c")) if f"{prefix}_{name}_{level}_{side}" in bones]
    last_dir = points[-1] - points[-2]
    last_dir = last_dir / np.linalg.norm(last_dir)
    reach = float(((tips - points[-1]) @ last_dir).max())
    chain = np.array(points + [points[-1] + last_dir * reach])
    hand = bones[f"j_te_{side}"]
    base_dir = chain[0] - hand
    return chain, base_dir / np.linalg.norm(base_dir)


def tube_coords(points: np.ndarray, chain: np.ndarray, reference: np.ndarray) -> np.ndarray:
    """(along, cos angle, sin angle) for each point, using the closest place on the bone chain."""
    start, end = chain[:-1], chain[1:]
    segment = end - start
    lengths = np.linalg.norm(segment, axis=1)
    offsets = points[:, None, :] - start[None, :, :]
    fraction = np.clip((offsets * segment).sum(2) / (lengths**2), 0, 1)
    nearest = start[None] + fraction[..., None] * segment[None]
    distance = np.linalg.norm(points[:, None, :] - nearest, axis=2)
    pick, rows = distance.argmin(1), np.arange(len(points))
    done = np.r_[0, np.cumsum(lengths)]
    along = (done[pick] + fraction[rows, pick] * lengths[pick]) / done[-1]
    axis = segment[pick] / lengths[pick][:, None]
    outward = points - nearest[rows, pick]
    across = reference - (reference * axis).sum(1, keepdims=True) * axis
    across /= np.maximum(np.linalg.norm(across, axis=1, keepdims=True), 1e-9)
    side = np.cross(axis, across)
    angle = np.arctan2((outward * side).sum(1), (outward * across).sum(1))
    return np.c_[along, np.cos(angle), np.sin(angle)]


def lookup_space(coords: np.ndarray) -> np.ndarray:
    return np.c_[coords[:, 0] * ALONG_WEIGHT, coords[:, 1:]]


def main() -> None:
    hr3 = tt.load_parts(tt.HR3_PARTS, tuple(tt.HR3_PARTS), drop_genitals=True)
    tbse = tt.load_parts(tt.TBSE_PARTS, tuple(tt.TBSE_PARTS))
    bones_hr3, bones_tbse = bone_positions(tt.REST_HR3), bone_positions(tt.REST_TBSE)
    data = np.load(tt.OUT / "map.npz")
    rows, cols, part = data["rows"], data["cols"], data["part"]
    new_uv = data["uv"].copy()
    hr3_labels, tbse_labels = labels(hr3), labels(tbse)
    face, bary, _ = tt.rasterize(hr3.uv, hr3.triangles, tt.HR3_SIZE)
    glove = hr3.names.index("glv")
    hand = np.where(part == glove)[0]
    tri = hr3.triangles[face[rows[hand], cols[hand]]]
    weights = bary[rows[hand], cols[hand]]
    texel_label = hr3_labels[tri[np.arange(len(tri)), weights.argmax(1)]]
    texel_point = (hr3.positions[tri] * weights[:, :, None]).sum(1)
    tbse_tri_label = tbse_labels[tbse.triangles[:, 0]]
    for finger in sorted(set(texel_label) - {""}):
        texels = hand[texel_label == finger]
        points = texel_point[texel_label == finger]
        faces = np.where((tbse_tri_label == finger) & (tbse_labels[tbse.triangles[:, 1]] == finger) & (tbse.part == tbse.names.index("glv")))[0]
        chain_hr3, ref_hr3 = chain_of(finger, bones_hr3, hr3.positions[hr3_labels == finger])
        chain_tbse, ref_tbse = chain_of(finger, bones_tbse, tbse.positions[tbse_labels == finger])
        samples = mb.sample_surface(tbse.positions, tbse.triangles[faces], spacing=SAMPLE_SPACING, seed=3)
        tree = cKDTree(lookup_space(tube_coords(samples.points, chain_tbse, ref_tbse)))
        coords = tube_coords(points, chain_hr3, ref_hr3)
        _, found = tree.query(lookup_space(coords), workers=3)
        source = tbse.triangles[faces[samples.faces[found]]]
        uv = (tbse.uv[source] * samples.bary[found][:, :, None]).sum(1).astype("f4")
        old = new_uv[texels]
        mix = np.clip(coords[:, 0] / BLEND_END, 0, 1)[:, None]
        mix = mix * mix * (3 - 2 * mix)
        apart = np.linalg.norm(uv - old, axis=1) > SAME_ISLAND
        mix[apart & (coords[:, 0] < BLEND_END)] = 1.0
        new_uv[texels] = old * (1 - mix) + uv * mix
        moved = np.linalg.norm((new_uv[texels] - old) * 2048, axis=1)
        print(f"{finger:8s} texels {len(texels):7d}  length HR3 {np.linalg.norm(np.diff(chain_hr3, axis=0), axis=1).sum() * 1000:.0f} mm, TBSE {np.linalg.norm(np.diff(chain_tbse, axis=0), axis=1).sum() * 1000:.0f} mm  old-to-new shift median {np.median(moved):.0f} px")
    np.savez(tt.OUT / "map_fingers.npz", rows=rows, cols=cols, uv=new_uv, gap=data["gap"], part=part)


if __name__ == "__main__":
    main()
