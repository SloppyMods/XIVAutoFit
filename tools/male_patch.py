"""Lift one mesh of a build off the skin in a height band and make it move with the skin there, leaving every other mesh as it was.

    python3 male_patch.py <in.glb> <out name.glb> "<mesh name>"

HR3BODY lists the body .mdl files. Env: MPLOW=<y> full effect below this height (1.30), MPHIGH=<y> no effect above it (1.42),
MPCLEAR=<mm> skin clearance to reach in the band (9). Only for meshes that keep their vertex count; the file goes to builds/_male/.
"""
import os
import sys
from pathlib import Path

import numpy as np
from scipy.spatial import cKDTree

sys.path.insert(0, str(Path(__file__).resolve().parent))
import glb_raw  # noqa: E402
import male_body as mb  # noqa: E402
import male_fit as mf  # noqa: E402
import male_regions as mr  # noqa: E402

LOW, HIGH, CLEAR = float(os.environ.get("MPLOW", "1.30")), float(os.environ.get("MPHIGH", "1.42")), float(os.environ.get("MPCLEAR", "9")) / 1000
BLUR = 0.012
TIP_CLEAR, TIP_REACH = 0.004, 0.03


def rescue_tips(points: np.ndarray, skin: mb.Samples) -> np.ndarray:
    """Move any vertex still inside the skin straight out from the body's centre line until it clears the skin.

    Needed under a belly overhang: there the nearest skin faces downward, so pushing along its normal never brings the point out.
    Neighbours within TIP_REACH share the move, fading with distance, so the edge does not spike.
    """
    def depth(p: np.ndarray) -> np.ndarray:
        _, near = skin.tree.query(p)
        return ((p - skin.points[near]) * skin.normals[near]).sum(1)

    inside = np.where(depth(points) < 0)[0]
    if len(inside) == 0:
        return points
    moves = np.zeros_like(points)
    for i in inside:
        direction = points[i] * np.array([1.0, 0.0, 1.0])
        direction /= max(float(np.linalg.norm(direction)), 1e-9)
        for step in np.arange(0.002, 0.08, 0.002):
            if depth((points[i] + direction * step)[None])[0] > TIP_CLEAR:
                moves[i] = direction * step
                break
    sources = inside[np.linalg.norm(moves[inside], axis=1) > 0]
    print(f"tips under the skin: {len(inside)}, moved out {len(sources)}, largest {np.linalg.norm(moves, axis=1).max() * 1000:.1f} mm")
    if len(sources) == 0:
        return points
    result = points.copy()
    for i, group in enumerate(cKDTree(points[sources]).query_ball_point(points, TIP_REACH)):
        if group:
            idx = sources[np.array(group)]
            fade = np.clip(1 - np.linalg.norm(points[idx] - points[i], axis=1) / TIP_REACH, 0, 1)
            fade = fade * fade * (3 - 2 * fade)
            best = int((fade * np.linalg.norm(moves[idx], axis=1)).argmax())
            result[i] = points[i] + moves[idx[best]] * fade[best]
    return result


def main() -> None:
    source, out_name, target_name = sys.argv[1:4]
    doc, blob = glb_raw.load(source)
    prim = next(p for p in glb_raw.primitives(doc) if p["name"] == target_name)
    read = lambda a: glb_raw.read_accessor(doc, blob, prim["attributes"][a]).astype("f8")
    points, normals, tangents = read("POSITION"), read("NORMAL"), read("TANGENT")
    joints = np.c_[read("JOINTS_0"), read("JOINTS_1")].astype("i8")
    weights = np.c_[read("WEIGHTS_0"), read("WEIGHTS_1")]
    triangles = glb_raw.read_accessor(doc, blob, prim["indices"]).astype("i8").reshape(-1, 3)
    names, _ = glb_raw.joint_matrices(doc, blob)
    body = mr.skin_only(os.environ["HR3BODY"].split(","))
    skin = mb.sample_surface(body.positions, body.triangles)

    share = np.clip((HIGH - points[:, 1]) / (HIGH - LOW), 0, 1)
    share = share * share * (3 - 2 * share)
    _, near = skin.tree.query(points)
    signed = ((points - skin.points[near]) * skin.normals[near]).sum(1)
    lift = skin.normals[near] * np.maximum(CLEAR - signed, 0)[:, None] * share[:, None]
    groups = cKDTree(points).query_ball_point(points, 3 * BLUR, workers=3)
    smooth = lift.copy()
    for i, group in enumerate(groups):
        idx = np.array(group)
        fade = np.exp(-((points[idx] - points[i]) ** 2).sum(1) / (2 * BLUR * BLUR))
        smooth[i] = (lift[idx] * fade[:, None]).sum(0) / fade.sum()
    moved = rescue_tips(points + smooth, skin)

    index = {n: i for i, n in enumerate(names)}
    table = np.array([index[b] for b in body.bones])
    tri = body.triangles[skin.faces[near]]
    new_joints, new_weights = joints.copy(), weights.copy()
    for i in np.where(share > 0)[0]:
        pool: dict[int, float] = {}
        for corner, vertex in zip(skin.bary[near[i]], tri[i]):
            total = body.weights[vertex].sum() or 1.0
            for joint, weight in zip(body.joints[vertex], body.weights[vertex]):
                if weight > 0:
                    pool[int(table[joint])] = pool.get(int(table[joint]), 0.0) + corner * float(weight) / total * share[i]
        total_old = weights[i].sum() or 1.0
        for joint, weight in zip(joints[i], weights[i]):
            if weight > 0:
                pool[int(joint)] = pool.get(int(joint), 0.0) + float(weight) / total_old * (1 - share[i])
        ranked = sorted(pool.items(), key=lambda kv: -kv[1])[:8]
        new_joints[i], new_weights[i] = 0, 0
        for slot, (joint, weight) in enumerate(ranked):
            new_joints[i, slot], new_weights[i, slot] = joint, weight
        new_weights[i] /= new_weights[i].sum()

    new_normals, new_tangents = mf.rotate_frames(points, moved, triangles, normals, tangents)
    writer = glb_raw.GlbWriter(doc, blob)
    attributes = writer.doc["meshes"][prim["mesh"]]["primitives"][prim["prim"]]["attributes"]
    attributes["POSITION"] = writer.add_accessor(moved.astype("f4"), 5126, "VEC3")
    attributes["NORMAL"] = writer.add_accessor(new_normals.astype("f4"), 5126, "VEC3")
    attributes["TANGENT"] = writer.add_accessor(new_tangents.astype("f4"), 5126, "VEC4")
    attributes["JOINTS_0"] = writer.add_accessor(new_joints[:, :4].astype("u2"), 5123, "VEC4")
    attributes["JOINTS_1"] = writer.add_accessor(new_joints[:, 4:].astype("u2"), 5123, "VEC4")
    attributes["WEIGHTS_0"] = writer.add_accessor(new_weights[:, :4].astype("f4"), 5126, "VEC4")
    attributes["WEIGHTS_1"] = writer.add_accessor(new_weights[:, 4:].astype("f4"), 5126, "VEC4")
    path = Path(__file__).resolve().parent.parent / "builds" / "_male" / out_name
    writer.save(str(path))
    lengths = np.linalg.norm(smooth, axis=1) * 1000
    print(f"{target_name}: moved {np.count_nonzero(lengths > 0.05)} of {len(points)} vertices, largest move {lengths.max():.1f} mm; wrote {path}")


if __name__ == "__main__":
    main()
