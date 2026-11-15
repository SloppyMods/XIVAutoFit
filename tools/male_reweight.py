"""Give a finished build new bone weights without moving a single vertex.

    python3 male_reweight.py <in.glb> <out name.glb>

Cloth weights come from weight_inpaint.py. Skin and fur lose their iv_ bones (handed to the nearest non-iv_ ancestor), so a
belly or butt cannot shift on bones the cloth ignores. Positions, normals and shape keys are left alone.

Env: RWBODY=<a.mdl,b.mdl> body to copy weights from (needed unless RWIVONLY is on), RWSETTINGS=<near mm,cos,far mm,keep above m> (30,0.866,60,9),
RWIVONLY=1 cloth also just loses its iv_ bones instead of being re-solved; this suits tops, where re-solving made chest and arm poses worse.
The file goes to builds/_male/ and an existing file is never overwritten.
"""
import os
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import glb_raw  # noqa: E402
import male_body as mb  # noqa: E402
import male_fit as mf  # noqa: E402
import male_regions as mr  # noqa: E402
import weight_inpaint as wi  # noqa: E402

SKIN_ENDINGS = ("b0001_b.mtrl", "b0001_h.mtrl")
SLOTS_PER_ACCESSOR = 4
IV_ONLY = bool(int(os.environ.get("RWIVONLY", "0")))


def read_float(doc: dict, blob: bytes, prim: dict, attribute: str) -> np.ndarray:
    return glb_raw.read_accessor(doc, blob, prim["attributes"][attribute]).astype("f8")


def bone_arrays(doc: dict, blob: bytes, prim: dict) -> tuple[np.ndarray, np.ndarray]:
    joints = np.c_[read_float(doc, blob, prim, "JOINTS_0"), read_float(doc, blob, prim, "JOINTS_1")].astype("i8")
    weights = np.c_[read_float(doc, blob, prim, "WEIGHTS_0"), read_float(doc, blob, prim, "WEIGHTS_1")]
    return joints, weights


def store_bones(writer: glb_raw.GlbWriter, prim: dict, joints: np.ndarray, weights: np.ndarray) -> None:
    attributes = writer.doc["meshes"][prim["mesh"]]["primitives"][prim["prim"]]["attributes"]
    attributes["JOINTS_0"] = writer.add_accessor(joints[:, :SLOTS_PER_ACCESSOR].astype("u2"), 5123, "VEC4")
    attributes["JOINTS_1"] = writer.add_accessor(joints[:, SLOTS_PER_ACCESSOR:].astype("u2"), 5123, "VEC4")
    attributes["WEIGHTS_0"] = writer.add_accessor(weights[:, :SLOTS_PER_ACCESSOR].astype("f4"), 5126, "VEC4")
    attributes["WEIGHTS_1"] = writer.add_accessor(weights[:, SLOTS_PER_ACCESSOR:].astype("f4"), 5126, "VEC4")


def reweighted_cloth(doc: dict, blob: bytes, prims: list[dict], names: list[str], parents: list[int], settings: wi.InpaintSettings) -> tuple[np.ndarray, np.ndarray]:
    """New weights for all cloth at once, so pieces that touch across meshes are solved together."""
    positions, triangles, joints, weights, start = [], [], [], [], 0
    for prim in prims:
        points = read_float(doc, blob, prim, "POSITION")
        positions.append(points)
        triangles.append(glb_raw.read_accessor(doc, blob, prim["indices"]).astype("i8").reshape(-1, 3) + start)
        prim_joints, prim_weights = bone_arrays(doc, blob, prim)
        joints.append(prim_joints)
        weights.append(prim_weights)
        start += len(points)
    body = mr.skin_only(os.environ["RWBODY"].split(","))
    samples = mb.sample_surface(body.positions, body.triangles)
    return wi.inpainted_weights(np.vstack(positions), np.vstack(triangles), np.vstack(joints), np.vstack(weights), body, samples, names, parents, settings)


def main() -> None:
    source, out_name = sys.argv[1:3]
    doc, blob = glb_raw.load(source)
    names, _ = glb_raw.joint_matrices(doc, blob)
    parents = glb_raw.joint_parents(doc)
    near, facing, far, keep_above = (float(x) for x in os.environ.get("RWSETTINGS", "30,0.866,60,9").split(","))
    settings = wi.InpaintSettings(near / 1000, facing, far / 1000, keep_above)
    prims = glb_raw.primitives(doc)
    cloth = [p for p in prims if "b0001" not in p["material"]]
    skin = [p for p in prims if p["material"].endswith(SKIN_ENDINGS)]
    writer = glb_raw.GlbWriter(doc, blob)
    if IV_ONLY:
        store_without_iv(writer, doc, blob, cloth, names, parents)
    else:
        store_solved(writer, doc, blob, cloth, names, parents, settings)
    store_without_iv(writer, doc, blob, skin, names, parents)
    path = Path(__file__).resolve().parent.parent / "builds" / "_male" / out_name
    writer.save(str(path))
    print(f"wrote {path}")


def store_solved(writer: glb_raw.GlbWriter, doc: dict, blob: bytes, cloth: list[dict], names: list[str], parents: list[int], settings: wi.InpaintSettings) -> None:
    joints, weights = reweighted_cloth(doc, blob, cloth, names, parents, settings)
    start = 0
    for prim in cloth:
        count = glb_raw.read_accessor(doc, blob, prim["attributes"]["POSITION"]).shape[0]
        store_bones(writer, prim, joints[start:start + count], weights[start:start + count])
        start += count


def store_without_iv(writer: glb_raw.GlbWriter, doc: dict, blob: bytes, prims: list[dict], names: list[str], parents: list[int]) -> None:
    for prim in prims:
        joints, weights = bone_arrays(doc, blob, prim)
        weights = weights / np.maximum(weights.sum(1, keepdims=True), 1e-9)
        new_joints, new_weights = mf.without_iv_bones(joints, weights, names, parents)
        store_bones(writer, prim, new_joints, new_weights)


if __name__ == "__main__":
    main()
