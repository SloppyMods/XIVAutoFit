"""Fit report for a build with no answer key: cloth-to-skin clearance by height band, and skin poking through the cloth in posed bends.

    python3 male_check.py <build.glb>

Set HR3BODY to the body .mdl files to measure against (comma separated). Poke rule as in male_score.py: a ray from a skin vertex going
straight inward hits cloth within 15 mm. The body is posed with its own bone weights, the cloth with the build's weights.
"""
import os
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import glb_raw  # noqa: E402
import male_body as mb  # noqa: E402
import male_score as ms  # noqa: E402

POSES = dict(ms.POSES, sit=[("j_asi_a_l", "x", -90), ("j_asi_a_r", "x", -90), ("j_asi_c_l", "x", 90), ("j_asi_c_r", "x", 90)],
             wrist_bend=[("j_te_l", "z", 40), ("j_te_r", "z", -40), ("j_ude_b_l", "y", -40), ("j_ude_b_r", "y", 40)],
             ankle_flex=[("j_asi_d_l", "x", 30), ("j_asi_d_r", "x", -30)],
             walk=[("j_asi_a_l", "x", -30), ("j_asi_c_l", "x", 25), ("j_asi_a_r", "x", 22), ("j_asi_c_r", "x", 45), ("j_kosi", "y", 8)],
             run=[("j_asi_a_l", "x", -55), ("j_asi_c_l", "x", 50), ("j_asi_a_r", "x", 35), ("j_asi_c_r", "x", 85), ("j_kosi", "y", 12), ("j_sebo_a", "x", 10)],
             side_step=[("j_asi_a_l", "z", 25), ("j_asi_a_r", "z", -12)],
             physics=[("iv_shiri_l", "x", 18), ("iv_shiri_r", "x", 18), ("iv_daitai_phys_l", "x", 12), ("iv_daitai_phys_r", "x", 12), ("iv_fukubu_phys", "x", 12)])


def main() -> None:
    build = sys.argv[1]
    hr3_paths = tuple(os.environ["HR3BODY"].split(","))
    body = mb.load_body(hr3_paths)
    ms.SKIN_TRIANGLES = body.triangles
    skin = mb.sample_surface(body.positions, body.triangles)
    doc, blob = glb_raw.load(build)
    prims = [p for p in glb_raw.primitives(doc) if "b0001" not in p["material"]]
    positions, triangles, joints, weights, start = [], [], [], [], 0
    read = lambda p, a: glb_raw.read_accessor(doc, blob, p["attributes"][a]).astype("f8")
    for p in prims:
        pos = read(p, "POSITION")
        positions.append(pos)
        triangles.append(glb_raw.read_accessor(doc, blob, p["indices"]).astype("i8").reshape(-1, 3) + start)
        if "JOINTS_1" in p["attributes"]:
            joints.append(np.c_[read(p, "JOINTS_0"), read(p, "JOINTS_1")].astype("i8"))
            weights.append(np.c_[read(p, "WEIGHTS_0"), read(p, "WEIGHTS_1")])
        else:
            joints.append(np.c_[read(p, "JOINTS_0"), np.zeros((len(pos), 4))].astype("i8"))
            weights.append(np.c_[read(p, "WEIGHTS_0"), np.zeros((len(pos), 4))])
        start += len(pos)
    positions = np.vstack(positions)
    triangles = np.vstack(triangles)
    joints = np.vstack(joints)
    weights = np.vstack(weights)
    gap, near = skin.tree.query(positions)
    signed = ((positions - skin.points[near]) * skin.normals[near]).sum(1) * 1000
    print(f"cloth vertices {len(positions)}, clearance mm p1={np.percentile(signed, 1):.1f} p5={np.percentile(signed, 5):.1f} p50={np.median(signed):.1f}; under skin {np.count_nonzero(signed < 0)}, under -2 mm {np.count_nonzero(signed < -2)}")
    low, high = positions[:, 1].min(), positions[:, 1].max()
    edges = np.linspace(low, high, 7)
    for a, b in zip(edges[:-1], edges[1:]):
        k = (positions[:, 1] >= a) & (positions[:, 1] <= b)
        if k.any():
            print(f"  y {a:.3f}..{b:.3f}: n={k.sum():5d} clearance p1={np.percentile(signed[k], 1):6.1f} p50={np.median(signed[k]):6.1f} under {np.count_nonzero(signed[k] < 0):4d}")
    names, rest = glb_raw.joint_matrices(doc, blob)
    parents = glb_raw.joint_parents(doc)
    index = {n: i for i, n in enumerate(names)}
    for pose, spec in POSES.items():
        delta = ms.pose_matrices(names, parents, rest, spec)
        skin_posed = ms.skin_points(body.positions, body.bones, body.joints, body.weights, delta, index)
        cloth_posed = ms.skin_points(positions, names, joints, weights, delta, index)
        ms.WHERE.clear()
        count, deepest = ms.poke_count(skin_posed, cloth_posed, triangles)
        place = ""
        if ms.WHERE:
            ys = ms.WHERE[-1][:, 1]
            place = f" y {ys.min():.2f}..{ys.max():.2f}"
        print(f"  {pose:12s} poke {count:5d} deepest {deepest:4.1f} mm{place}")


if __name__ == "__main__":
    main()
