"""Score a fitted TBSE-to-HR3 garment against the mod author's own HR3 version.

    python3 male_score.py <our build.glb> <author: .glb or .mdl> <outfit c0101.glb> <top|dwn>

Prints, for our build and the author's: per-region clearance over the HR3 skin, per-vertex distance to the author's cloth,
bone-weight difference, and skin poking through the cloth standing and in bent poses (the same posing for both).
Poke rule: a skin vertex counts when the nearest cloth surface lies within POKE_REACH and the skin is on the outer side of it.
"""
import os
import sys
from pathlib import Path

import numpy as np
from scipy.spatial import cKDTree

sys.path.insert(0, str(Path(__file__).resolve().parent))
import glb_raw  # noqa: E402
import male_body as mb  # noqa: E402
import mdl_read  # noqa: E402

POKE_REACH = 0.015
SKIN_TRIANGLES: np.ndarray = np.empty((0, 3), dtype="i8")
WHERE: list[np.ndarray] = []
BANDS = {"dwn": (("hem", "y", 0.0, 0.80), ("thigh", "y", 0.80, 0.95), ("hip", "y", 0.95, 1.10), ("waist", "y", 1.10, 1.20), ("top", "y", 1.20, 1.40)),
         "top": (("belly", "y", 0.0, 1.55), ("chest", "y", 1.55, 2.2))}
POSES = {"stand": [], "squat": [("j_asi_a_l", "x", -75), ("j_asi_a_r", "x", -75), ("j_asi_c_l", "x", 105), ("j_asi_c_r", "x", 105), ("j_kosi", "x", 15)],
         "lunge": [("j_asi_a_l", "x", -70), ("j_asi_c_l", "x", 70), ("j_asi_a_r", "x", 30)],
         "bend": [("j_sebo_a", "x", 35), ("j_sebo_b", "x", 15)], "twist": [("j_sebo_a", "y", 30), ("j_sebo_b", "y", 15)],
         "arms_up": [("j_ude_a_l", "z", 100), ("j_ude_a_r", "z", -100)], "arms_forward": [("j_ude_a_l", "y", -80), ("j_ude_a_r", "y", 80)]}


def read_cloth(path: str) -> dict:
    if path.endswith(".mdl"):
        model = mdl_read.read_mdl(path)
        mesh = [m for m in model.meshes if "b0001" not in m.material and "top_b" in m.material or "dwn_b" in m.material][0]
        return dict(positions=mesh.positions, triangles=mesh.triangles, uv=mesh.uv, bones=list(model.bones), joints=mesh.joints, weights=mesh.weights)
    doc, blob = glb_raw.load(path)
    prims = [p for p in glb_raw.primitives(doc) if "b0001" not in p["material"]]
    p = prims[0]
    read = lambda attr: glb_raw.read_accessor(doc, blob, p["attributes"][attr]).astype("f8")
    names, _ = glb_raw.joint_matrices(doc, blob)
    return dict(positions=read("POSITION"), triangles=glb_raw.read_accessor(doc, blob, p["indices"]).astype("i8").reshape(-1, 3), uv=read("TEXCOORD_0"), bones=names,
                joints=np.c_[read("JOINTS_0"), read("JOINTS_1")].astype("i8"), weights=np.c_[read("WEIGHTS_0"), read("WEIGHTS_1")])


def correspond(ours: dict, author: dict) -> np.ndarray:
    """Map each of our vertices to the author's same vertex: equal first UV, ties broken by nearest position."""
    candidates = cKDTree(author["uv"]).query_ball_point(ours["uv"], 1.5e-3)
    out = np.full(len(ours["uv"]), -1)
    for i, group in enumerate(candidates):
        if group:
            out[i] = group[int(np.argmin(np.linalg.norm(author["positions"][group] - ours["positions"][i], axis=1)))]
    return out


def rotation(axis: str, degrees: float) -> np.ndarray:
    angle = np.radians(degrees)
    c, s = np.cos(angle), np.sin(angle)
    return {"x": np.array([[1, 0, 0], [0, c, -s], [0, s, c]]), "y": np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]]), "z": np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]])}[axis]


def pose_matrices(names: list[str], parents: list[int], rest: np.ndarray, spec: list) -> np.ndarray:
    """World 4x4 per bone: each listed bone turns about its own rest position, about a world axis, and carries its children."""
    index = {n: i for i, n in enumerate(names)}
    local = np.tile(np.eye(4), (len(names), 1, 1))
    for bone, axis, degrees in spec:
        if bone not in index:
            continue
        pivot = rest[index[bone]][:3, 3]
        m = np.eye(4)
        m[:3, :3] = rotation(axis, degrees)
        m[:3, 3] = pivot - m[:3, :3] @ pivot
        local[index[bone]] = m
    out = np.zeros_like(local)
    done = [False] * len(names)

    def resolve(i: int) -> np.ndarray:
        if done[i]:
            return out[i]
        out[i] = local[i] if parents[i] < 0 else resolve(parents[i]) @ local[i]
        done[i] = True
        return out[i]

    for i in range(len(names)):
        resolve(i)
    return out


def skin_points(points: np.ndarray, bones, joints: np.ndarray, weights: np.ndarray, posed: np.ndarray, skeleton_index: dict) -> np.ndarray:
    table = np.stack([posed[skeleton_index.get(b, skeleton_index["n_root"])] for b in bones])
    share = weights / np.maximum(weights.sum(1, keepdims=True), 1e-9)
    blended = (table[joints] * share[:, :, None, None]).sum(1)
    return (blended[:, :3, :3] @ points[..., None])[..., 0] + blended[:, :3, 3]


def poke_count(skin: np.ndarray, cloth: np.ndarray, triangles: np.ndarray) -> tuple[int, float]:
    """A skin vertex pokes when a ray from it going straight inward hits cloth within POKE_REACH (same rule as skin_poke.py)."""
    normals = mb.vertex_normals(skin, SKIN_TRIANGLES)
    hits = mb.inward_hits(skin, normals, cloth, triangles, POKE_REACH)
    by_vertex: dict[int, float] = {}
    for vertex, _, depth in hits:
        by_vertex[vertex] = max(by_vertex.get(vertex, 0.0), depth)
    if by_vertex:
        WHERE.append(skin[sorted(by_vertex)])
    return len(by_vertex), max(by_vertex.values(), default=0.0) * 1000


def weight_gap(ours: dict, author: dict, pairs: np.ndarray) -> np.ndarray:
    def table(c: dict, i: int) -> dict:
        out: dict[str, float] = {}
        total = float(c["weights"][i].sum()) or 1.0
        for j, w in zip(c["joints"][i], c["weights"][i]):
            if w > 0:
                out[c["bones"][j]] = out.get(c["bones"][j], 0.0) + float(w) / total
        return out

    gaps = []
    for i in np.where(pairs >= 0)[0][::4]:
        a, b = table(ours, i), table(author, pairs[i])
        gaps.append(0.5 * sum(abs(a.get(k, 0) - b.get(k, 0)) for k in a.keys() | b.keys()))
    return np.array(gaps)


def main() -> None:
    build, author_path, outfit, slot = sys.argv[1:5]
    ours, author = read_cloth(build), read_cloth(author_path)
    hr3_paths = tuple(os.environ.get("HR3BODY", ",".join(mb.DEFAULT_HR3)).split(","))
    body = mb.load_body(hr3_paths)
    global SKIN_TRIANGLES
    SKIN_TRIANGLES = body.triangles
    skin_samples = mb.sample_surface(body.positions, body.triangles)
    pairs = correspond(ours, author)
    ok = pairs >= 0
    print(f"vertex correspondence: {ok.sum()} of {len(ok)} matched, {len(set(pairs[ok].tolist()))} unique")
    distance = np.linalg.norm(ours["positions"][ok] - author["positions"][pairs[ok]], axis=1) * 1000
    print(f"all vertices, distance to author's same vertex mm p50/p90/p99/max {np.percentile(distance, [50, 90, 99, 100]).round(1)}")
    reference = author["positions"][pairs[ok]]
    bands = BANDS[slot]
    for name, axis, low, high in bands:
        k = (reference[:, 1] >= low) & (reference[:, 1] < high)
        if slot == "top":
            k &= np.abs(reference[:, 0]) < 0.33
        if k.any():
            print(f"  region {name:7s} n={k.sum():5d} vertex distance mm p50={np.median(distance[k]):6.1f} p90={np.percentile(distance[k], 90):6.1f}")
    if slot == "top":
        k = np.abs(reference[:, 0]) >= 0.33
        print(f"  region sleeve  n={k.sum():5d} vertex distance mm p50={np.median(distance[k]):6.1f} p90={np.percentile(distance[k], 90):6.1f}")

    def clearance_row(label: str, positions: np.ndarray) -> None:
        signed, _ = (lambda p: (((p - skin_samples.points[skin_samples.tree.query(p)[1]]) * skin_samples.normals[skin_samples.tree.query(p)[1]]).sum(1), None))(positions)
        signed *= 1000
        print(f"  {label:13s} clearance to HR3 skin mm p1={np.percentile(signed, 1):6.1f} p5={np.percentile(signed, 5):6.1f} p50={np.median(signed):6.1f}  under skin {np.count_nonzero(signed < 0):5d}  under -2mm {np.count_nonzero(signed < -2):5d}")

    print("clearance over the whole garment:")
    clearance_row("ours", ours["positions"])
    clearance_row("author", author["positions"])
    print("clearance by region:")
    for name, axis, low, high in bands:
        ko = (ours["positions"][:, 1] >= low) & (ours["positions"][:, 1] < high)
        ka = (author["positions"][:, 1] >= low) & (author["positions"][:, 1] < high)
        if ko.any():
            clearance_row("ours " + name, ours["positions"][ko])
        if ka.any():
            clearance_row("auth " + name, author["positions"][ka])
    gaps = weight_gap(ours, author, pairs)
    print(f"bone weights vs author (0 same, 1 different bones): mean {gaps.mean():.3f}, p90 {np.percentile(gaps, 90):.3f}")

    shell_doc, shell_blob = glb_raw.load(build)
    names, rest = glb_raw.joint_matrices(shell_doc, shell_blob)
    parents = glb_raw.joint_parents(shell_doc)
    index = {n: i for i, n in enumerate(names)}
    print("poke-through (skin vertices outside the cloth within 15 mm; ours vs author):")
    for pose, spec in POSES.items():
        delta = pose_matrices(names, parents, rest, spec)
        skin = skin_points(body.positions, body.bones, body.joints, body.weights, delta, index)
        ours_posed = skin_points(ours["positions"], ours["bones"], ours["joints"], ours["weights"], delta, index)
        author_posed = skin_points(author["positions"], author["bones"], author["joints"], author["weights"], delta, index)
        WHERE.clear()
        o = poke_count(skin, ours_posed, ours["triangles"])
        a = poke_count(skin, author_posed, author["triangles"])
        if pose == "stand":
            for label, w in zip(("ours", "author"), WHERE):
                h = np.histogram(w[:, 1], bins=10, range=(0.8 if slot == "dwn" else 1.1, 1.3 if slot == "dwn" else 2.1))[0]
                near_x = (np.abs(w[:, 0]) < 0.35).sum()
                print(f"    {label}: height histogram {h.tolist()}  within |x|<0.35: {near_x}")
        print(f"  {pose:12s} ours {o[0]:5d} (deepest {o[1]:4.1f} mm)   author {a[0]:5d} (deepest {a[1]:4.1f} mm)")


if __name__ == "__main__":
    main()
