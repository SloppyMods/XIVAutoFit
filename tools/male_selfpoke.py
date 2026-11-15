"""Skin poking through the cloth, using the skin stored in the build itself, standing and posed.

    python3 male_selfpoke.py <build.glb> [more builds]

male_check.py measures a body read from the mod; this one measures what the game will actually draw from this file.
"""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import glb_raw  # noqa: E402
import male_body as mb  # noqa: E402
import male_check as mc  # noqa: E402
import male_score as ms  # noqa: E402

REACH = 0.06
SHOW = ("stand", "walk", "run", "side_step", "bend", "twist", "lunge", "squat", "sit")


def gather(doc: dict, blob: bytes, prims: list[dict]) -> tuple[np.ndarray, ...]:
    positions, triangles, joints, weights, start = [], [], [], [], 0
    read = lambda p, a: glb_raw.read_accessor(doc, blob, p["attributes"][a]).astype("f8")
    for p in prims:
        pos = read(p, "POSITION")
        extra = np.zeros((len(pos), 4))
        positions.append(pos)
        joints.append(np.c_[read(p, "JOINTS_0"), read(p, "JOINTS_1") if "JOINTS_1" in p["attributes"] else extra].astype("i8"))
        weights.append(np.c_[read(p, "WEIGHTS_0"), read(p, "WEIGHTS_1") if "WEIGHTS_1" in p["attributes"] else extra])
        triangles.append(glb_raw.read_accessor(doc, blob, p["indices"]).astype("i8").reshape(-1, 3) + start)
        start += len(pos)
    return np.vstack(positions), np.vstack(triangles), np.vstack(joints), np.vstack(weights)


def main() -> None:
    for build in sys.argv[1:]:
        doc, blob = glb_raw.load(build)
        prims = glb_raw.primitives(doc)
        cloth = gather(doc, blob, [p for p in prims if "b0001" not in p["material"]])
        skin = gather(doc, blob, [p for p in prims if p["material"].endswith("b0001_b.mtrl")])
        names, rest = glb_raw.joint_matrices(doc, blob)
        parents = glb_raw.joint_parents(doc)
        index = {n: i for i, n in enumerate(names)}
        print(Path(build).name, "skin vertices", len(skin[0]))
        for pose in SHOW:
            delta = ms.pose_matrices(names, parents, rest, mc.POSES.get(pose, []))
            posed_skin = ms.skin_points(skin[0], names, skin[2], skin[3], delta, index)
            posed_cloth = ms.skin_points(cloth[0], names, cloth[2], cloth[3], delta, index)
            normals = mb.vertex_normals(posed_skin, skin[1])
            hits = mb.inward_hits(posed_skin, normals, posed_cloth, cloth[1], REACH)
            depth: dict[int, float] = {}
            for vertex, _, t in hits:
                depth[vertex] = max(depth.get(vertex, 0.0), t)
            where = ""
            if depth:
                p = posed_skin[sorted(depth)]
                front = int(np.count_nonzero(p[:, 2] > 0))
                where = f" front {front}, back {len(p) - front}, y {p[:, 1].min():.2f}..{p[:, 1].max():.2f}"
            print(f"  {pose:10s} poking {len(depth):5d}, deepest {max(depth.values(), default=0.0) * 1000:5.1f} mm{where}")


if __name__ == "__main__":
    main()
