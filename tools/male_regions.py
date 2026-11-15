"""Where a build's cloth sits under the skin, standing and posed, by body region.

    python3 male_regions.py <build.glb>

HR3BODY lists the body .mdl files. Only real skin is measured (mt_...b0001_b); underwear and fur do not count. A cloth vertex is under the
skin when it is more than TOL behind the nearest skin surface, in a place within REACH of skin. Clusters are groups of under-skin vertices
within 20 mm of each other, so a report line is one visible spot, and cloth that is merely inner lining still counts: judge it with a render.
Set MRSAMELIMB=1 to compare cloth with skin on its own limb only, which leaves out body parts that overlap each other in a pose.
"""
import os
import re
import sys
from pathlib import Path

import numpy as np
import scipy.sparse as sp
import scipy.sparse.csgraph as csg
from scipy.spatial import cKDTree

sys.path.insert(0, str(Path(__file__).resolve().parent))
import glb_raw  # noqa: E402
import male_body as mb  # noqa: E402
import male_check as mc  # noqa: E402
import male_score as ms  # noqa: E402
import mdl_read  # noqa: E402

TOL, REACH = 0.0005, 0.04
REGIONS = (("hip_butt", r"j_kosi|iv_shiri|iv_daitai|iv_kougan|iv_ochinko"), ("thigh", r"j_asi_a"), ("knee_calf", r"j_asi_[bc]"), ("foot", r"j_asi_[de]"),
           ("spine_chest", r"j_sebo|j_kubi|n_hara|iv_fukubu|iv_kyokin|j_mune|j_sako"), ("upper_arm", r"j_ude_a|n_hkata|iv_nitoukin"), ("forearm", r"j_ude_b|n_hhiji|iv_ude"),
           ("hand", r"n_hte|j_te|j_buki"), ("fingers", r"j_(oya|hito|naka|kusu|ko)_[a-z]_"))


def skin_only(paths: list[str]) -> mb.Body:
    positions, triangles, joints, weights, names, start = [], [], [], [], {}, 0
    for path in paths:
        model = mdl_read.read_mdl(path)
        for mesh in model.meshes:
            if not mesh.material.endswith("b0001_b.mtrl"):
                continue
            remap = np.array([names.setdefault(b, len(names)) for b in model.bones])
            positions.append(mesh.positions)
            triangles.append(mesh.triangles + start)
            joints.append(np.pad(remap[mesh.joints], ((0, 0), (0, 8 - mesh.joints.shape[1]))))
            weights.append(np.pad(mesh.weights, ((0, 0), (0, 8 - mesh.weights.shape[1]))))
            start += len(mesh.positions)
    return mb.Body(np.vstack(positions), np.vstack(triangles), tuple(names), np.vstack(joints), np.vstack(weights))


def region_of(names: list[str], joints: np.ndarray, weights: np.ndarray) -> np.ndarray:
    dominant = joints[np.arange(len(joints)), weights.argmax(1)]
    table = {}
    for j in np.unique(dominant):
        table[j] = next((label for label, pattern in REGIONS if re.match(pattern, names[j])), "other")
    return np.array([table[j] for j in dominant])


def family(names, joints: np.ndarray, weights: np.ndarray) -> np.ndarray:
    """Which limb each vertex belongs to, so posed checks compare cloth with skin on the same limb, not with a belly a raised thigh sinks into."""
    dominant = joints[np.arange(len(joints)), weights.argmax(1)]
    def label(bone: str) -> str:
        side = bone[-1] if bone[-2:] in ("_l", "_r") else "c"
        if re.match(r"j_asi|iv_daitai|iv_shiri", bone):
            return "leg_" + side
        if re.match(r"j_ude|n_hkata|n_hhiji|iv_nitoukin|iv_ude|j_sako|n_hte|j_te|j_(oya|hito|naka|kusu|ko)_[a-z]_", bone):
            return "arm_" + side
        return "core"
    table = {j: label(names[j]) for j in np.unique(dominant)}
    return np.array([table[j] for j in dominant])


def clusters(points: np.ndarray, depths: np.ndarray) -> list[tuple[int, np.ndarray, float]]:
    pairs = cKDTree(points).query_pairs(0.02, output_type="ndarray")
    graph = sp.coo_matrix((np.ones(len(pairs)), (pairs[:, 0], pairs[:, 1])), shape=(len(points), len(points)))
    _, labels = csg.connected_components(graph, directed=False)
    found = []
    for label in np.unique(labels):
        chosen = labels == label
        found.append((int(chosen.sum()), points[chosen].mean(0), float(depths[chosen].min())))
    return sorted(found, key=lambda c: -c[0])


def main() -> None:
    build = sys.argv[1]
    body = skin_only(os.environ["HR3BODY"].split(","))
    doc, blob = glb_raw.load(build)
    prims = [p for p in glb_raw.primitives(doc) if "b0001" not in p["material"]]
    positions, joints, weights, start = [], [], [], 0
    read = lambda p, a: glb_raw.read_accessor(doc, blob, p["attributes"][a]).astype("f8")
    for p in prims:
        pos = read(p, "POSITION")
        positions.append(pos)
        extra = np.zeros((len(pos), 4))
        joints.append(np.c_[read(p, "JOINTS_0"), read(p, "JOINTS_1") if "JOINTS_1" in p["attributes"] else extra].astype("i8"))
        weights.append(np.c_[read(p, "WEIGHTS_0"), read(p, "WEIGHTS_1") if "WEIGHTS_1" in p["attributes"] else extra])
    positions, joints, weights = np.vstack(positions), np.vstack(joints), np.vstack(weights)
    names, rest = glb_raw.joint_matrices(doc, blob)
    parents = glb_raw.joint_parents(doc)
    index = {n: i for i, n in enumerate(names)}
    regions = region_of(names, joints, weights)
    print(f"{Path(build).name}: {len(positions)} cloth vertices")
    same_limb = bool(os.environ.get("MRSAMELIMB"))
    cloth_family = family(names, joints, weights)
    skin_family = family(list(body.bones), body.joints, body.weights)
    for pose, spec in mc.POSES.items():
        delta = ms.pose_matrices(names, parents, rest, spec)
        skin = ms.skin_points(body.positions, body.bones, body.joints, body.weights, delta, index)
        cloth = ms.skin_points(positions, names, joints, weights, delta, index)
        samples = mb.sample_surface(skin, body.triangles, spacing=0.003)
        if same_limb:
            near = np.zeros(len(cloth), "i8")
            gap = np.full(len(cloth), 9.0)
            owner = skin_family[body.triangles[samples.faces, 0]]
            for fam in np.unique(cloth_family):
                allowed = owner == fam if fam != "core" else np.ones(len(owner), bool)
                which = np.where(allowed)[0]
                mine = np.where(cloth_family == fam)[0]
                if len(which) and len(mine):
                    found = cKDTree(samples.points[which]).query(cloth[mine])
                    gap[mine], near[mine] = found[0], which[found[1]]
        else:
            gap, near = samples.tree.query(cloth)
        signed = ((cloth - samples.points[near]) * samples.normals[near]).sum(1)
        under = (signed < -TOL) & (gap < REACH)
        line = f"  {pose:12s} under {under.sum():5d}"
        for label in dict.fromkeys(r for r, _ in REGIONS):
            count = np.count_nonzero(under & (regions == label))
            if count:
                line += f"  {label}={count}"
        print(line)
        if under.any():
            for size, center, depth in clusters(cloth[under], signed[under] * 1000)[:3]:
                print(f"      spot n={size:4d} deepest {depth:6.1f} mm at x {center[0]:+.3f} y {center[1]:.3f} z {center[2]:+.3f}")


if __name__ == "__main__":
    main()
