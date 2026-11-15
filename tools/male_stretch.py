"""How much a build's cloth stretches or splits when posed. Run on any export or build:

    python3 male_stretch.py <build.glb> [more builds]

Two numbers per pose. Seam split: vertices stored twice at one spot (UV seams) that end up apart, which shows as a tear.
Stretch: how much each triangle edge grows compared with standing.
"""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import glb_raw  # noqa: E402
import male_body as mb  # noqa: E402
import male_check as mc  # noqa: E402
import male_score as ms  # noqa: E402

SHOW = ("walk", "run", "side_step", "lunge", "squat", "sit")
SPLIT_LIMIT = 0.002


def main() -> None:
    for build in sys.argv[1:]:
        doc, blob = glb_raw.load(build)
        prims = [p for p in glb_raw.primitives(doc) if "b0001" not in p["material"]]
        positions, joints, weights, triangles, start = [], [], [], [], 0
        read = lambda p, a: glb_raw.read_accessor(doc, blob, p["attributes"][a]).astype("f8")
        for p in prims:
            pos = read(p, "POSITION")
            extra = np.zeros((len(pos), 4))
            positions.append(pos)
            joints.append(np.c_[read(p, "JOINTS_0"), read(p, "JOINTS_1") if "JOINTS_1" in p["attributes"] else extra].astype("i8"))
            weights.append(np.c_[read(p, "WEIGHTS_0"), read(p, "WEIGHTS_1") if "WEIGHTS_1" in p["attributes"] else extra])
            triangles.append(glb_raw.read_accessor(doc, blob, p["indices"]).astype("i8").reshape(-1, 3) + start)
            start += len(pos)
        positions, joints, weights, triangles = np.vstack(positions), np.vstack(joints), np.vstack(weights), np.vstack(triangles)
        names, rest = glb_raw.joint_matrices(doc, blob)
        parents = glb_raw.joint_parents(doc)
        index = {n: i for i, n in enumerate(names)}
        ids, _ = mb.weld(positions, triangles)
        order = np.argsort(ids)
        same = ids[order[1:]] == ids[order[:-1]]
        pair_a, pair_b = order[:-1][same], order[1:][same]
        edges = np.unique(np.sort(np.vstack([triangles[:, [0, 1]], triangles[:, [1, 2]], triangles[:, [2, 0]]]), axis=1), axis=0)
        rest_length = np.linalg.norm(positions[edges[:, 0]] - positions[edges[:, 1]], axis=1)
        usable = rest_length > 1e-4
        print(f"{Path(build).name}: {len(positions)} vertices, {len(pair_a)} seam pairs")
        for pose in SHOW:
            delta = ms.pose_matrices(names, parents, rest, mc.POSES[pose])
            posed = ms.skin_points(positions, names, joints, weights, delta, index)
            split = np.linalg.norm(posed[pair_a] - posed[pair_b], axis=1) * 1000
            ratio = np.linalg.norm(posed[edges[:, 0]] - posed[edges[:, 1]], axis=1)[usable] / rest_length[usable]
            print(f"  {pose:10s} seam split: over 2 mm {np.count_nonzero(split > SPLIT_LIMIT * 1000):5d}, max {split.max():6.1f} mm | edges stretched over 1.5x {np.count_nonzero(ratio > 1.5):5d}, over 2x {np.count_nonzero(ratio > 2):5d}, worst {ratio.max():5.1f}x")


if __name__ == "__main__":
    main()
