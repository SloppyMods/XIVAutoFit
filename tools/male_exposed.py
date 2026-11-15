"""Score how much skin shows through a garment: the check to use instead of raw poke counts.

    python3 male_exposed.py <build.glb or .mdl> [more]

Exposed skin is measured by area on dense skin sample points: a point counts when cloth lies within XPREACH behind it and no cloth is
in front of it within XPFRONT. Inner cloth walls behind the skin are therefore not counted, which is what makes raw poke counts misleading.
Also prints crossed layers (a vertex with an opposite-facing cloth layer just in front of it, so an inner wall has come through the outer one)
and the percent of edges stretched past 1.5x. Stretch is reported only: it did not separate a known-bad pair of pants from a known-good one.

Env: XPBODY=<a.mdl,b.mdl> body measured against (the Chubby torso), XPOWNSKIN=1 use the skin stored in the file instead,
XPPOSES=<a,b> pose names from male_check.POSES plus jiggle, XPSPACE=<m> sample spacing (0.006), XPREACH=<m> (0.015), XPFRONT=<m> (0.2),
XPLAG=<share> counter-rotate n_hkata by this share of the upper-arm turn, to imitate a twist bone (0; the game's real share is unknown),
XPEXTRA=1 also print, per pose, exposed skin counting only outward-facing cover, deep pokes (cloth behind deeper than XPREACH, up to XPDEEP 0.06 m)
and skin covered at rest that a camera sees in the pose (tears, gaps); with XPFULLBODY=<a.mdl,b.mdl> also the reference skin missing from the build
(see exposure_extra.py; off by default, so the normal output is unchanged),
XPREGIONS=1 also print the body regions each pose's exposed skin is in, XPSKELETON=<c0901 .glb> skeleton for .mdl input. Results split at XPWAIST=<m> (1.30), below which torso skin meets the pants.
"""
import os
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import glb_raw  # noqa: E402
import male_body as mb  # noqa: E402
import male_check as mc  # noqa: E402
import male_regions as mr  # noqa: E402
import male_score as ms  # noqa: E402
import mdl_read  # noqa: E402
import exposure_extra as xe  # noqa: E402

CROSS_REACH, MIN_GAP, STRETCHED = 0.012, 3e-4, 1.5
JIGGLE_BONES = ("iv_kyokin_phys_l", "iv_kyokin_phys_r", "iv_fukubu_phys")
JIGGLE_DEGREES = 15
DEFAULT_POSES = "stand,bend,twist,arms_up,arms_forward,jiggle"
SLOTS = 8


@dataclass(frozen=True)
class Mesh:
    positions: np.ndarray
    triangles: np.ndarray
    joints: np.ndarray  # indices into the skeleton's bone names
    weights: np.ndarray


@dataclass(frozen=True)
class Skeleton:
    names: list[str]
    rest: np.ndarray
    parents: list[int]

    def index(self) -> dict[str, int]:
        return {name: i for i, name in enumerate(self.names)}


def merged_glb(doc: dict, blob: bytes, prims: list[dict]) -> Mesh:
    positions, triangles, joints, weights, start = [], [], [], [], 0
    read = lambda prim, name: glb_raw.read_accessor(doc, blob, prim["attributes"][name]).astype("f8")
    for prim in prims:
        points = read(prim, "POSITION")
        blank = np.zeros((len(points), 4))
        positions.append(points)
        triangles.append(glb_raw.read_accessor(doc, blob, prim["indices"]).astype("i8").reshape(-1, 3) + start)
        joints.append(np.c_[read(prim, "JOINTS_0"), read(prim, "JOINTS_1") if "JOINTS_1" in prim["attributes"] else blank].astype("i8"))
        weights.append(np.c_[read(prim, "WEIGHTS_0"), read(prim, "WEIGHTS_1") if "WEIGHTS_1" in prim["attributes"] else blank])
        start += len(points)
    table = np.vstack(weights)
    return Mesh(np.vstack(positions), np.vstack(triangles), np.vstack(joints), table / np.maximum(table.sum(1, keepdims=True), 1e-9))


def mesh_from_mdl(model: mdl_read.MdlModel, mesh: mdl_read.MdlMesh, index: dict[str, int]) -> Mesh:
    remap = np.array([index[bone] for bone in model.bones])
    joints, weights = remap[mesh.joints], mesh.weights.astype("f8")
    pad = ((0, 0), (0, SLOTS - joints.shape[1]))
    return Mesh(mesh.positions.astype("f8"), mesh.triangles.astype("i8"), np.pad(joints, pad).astype("i8"), np.pad(weights, pad) / np.maximum(weights.sum(1, keepdims=True), 1e-9))


def merged_mdl(meshes: list[Mesh]) -> Mesh:
    offsets = np.cumsum([0] + [len(m.positions) for m in meshes[:-1]])
    return Mesh(np.vstack([m.positions for m in meshes]), np.vstack([m.triangles + o for m, o in zip(meshes, offsets)]), np.vstack([m.joints for m in meshes]), np.vstack([m.weights for m in meshes]))


def load_skeleton(path: str) -> Skeleton:
    doc, blob = glb_raw.load(path)
    names, rest = glb_raw.joint_matrices(doc, blob)
    return Skeleton(names, rest, glb_raw.joint_parents(doc))


def load_garment(path: str, skeleton: Skeleton) -> tuple[Mesh, Mesh]:
    """(cloth, own skin) of a .glb or .mdl."""
    if path.endswith(".mdl"):
        model = mdl_read.read_mdl(path)
        skin = next(m for m in model.meshes if m.material.endswith("b0001_b.mtrl"))
        return merged_mdl([mesh_from_mdl(model, m, skeleton.index()) for m in model.meshes if "b0001" not in m.material and len(m.positions)]), mesh_from_mdl(model, skin, skeleton.index())
    doc, blob = glb_raw.load(path)
    prims = glb_raw.primitives(doc)
    return (merged_glb(doc, blob, [p for p in prims if "b0001" not in p["material"]]),
            merged_glb(doc, blob, [p for p in prims if p["material"].endswith("b0001_b.mtrl")]))


def body_mesh(paths: list[str], skeleton: Skeleton) -> Mesh:
    body = mr.skin_only(paths)
    table = np.array([skeleton.index()[bone] for bone in body.bones])
    return Mesh(body.positions, body.triangles, table[body.joints], body.weights)


def pose_spec(name: str, lag: float) -> list:
    spec = [(bone, "x", JIGGLE_DEGREES) for bone in JIGGLE_BONES] if name == "jiggle" else list(mc.POSES.get(name, []))
    if lag > 0:
        spec += [(bone.replace("j_ude_a", "n_hkata"), axis, -degrees * lag) for bone, axis, degrees in spec if bone.startswith("j_ude_a")]
    return spec


def posed(mesh: Mesh, skeleton: Skeleton, delta: np.ndarray) -> np.ndarray:
    return ms.skin_points(mesh.positions, skeleton.names, mesh.joints, mesh.weights, delta, skeleton.index())


def exposed_mask(points: np.ndarray, normals: np.ndarray, cloth: np.ndarray, triangles: np.ndarray, reach: float, front: float) -> np.ndarray:
    behind = np.unique([hit[0] for hit in mb.inward_hits(points, normals, cloth, triangles, reach)]).astype("i8")
    mask = np.zeros(len(points), bool)
    if len(behind) == 0:
        return mask
    mask[behind] = True
    covered = np.unique([hit[0] for hit in mb.inward_hits(points[behind], -normals[behind], cloth, triangles, front)]).astype("i8")
    mask[behind[covered]] = False
    return mask


def crossed_layers(cloth: Mesh, skin: mb.Samples) -> int:
    """Outer-facing vertices with a body-facing cloth layer just in front of them: an inner wall that came through the outer one."""
    return len(mb.crossed_vertices(cloth.positions, cloth.triangles, skin, CROSS_REACH, MIN_GAP))


def stretched_percent(cloth: Mesh, moved: np.ndarray) -> float:
    edges = np.unique(np.sort(np.vstack([cloth.triangles[:, [0, 1]], cloth.triangles[:, [1, 2]], cloth.triangles[:, [2, 0]]]), axis=1), axis=0)
    rest = np.linalg.norm(cloth.positions[edges[:, 0]] - cloth.positions[edges[:, 1]], axis=1)
    usable = rest > 1e-4
    ratio = np.linalg.norm(moved[edges[:, 0]] - moved[edges[:, 1]], axis=1)[usable] / rest[usable]
    return float(np.mean(ratio > STRETCHED) * 100)


def score(label: str, cloth: Mesh, body: Mesh, skeleton: Skeleton) -> dict[str, tuple[float, float]]:
    """Print and return {pose: (exposed cm2 above the waist line, below it)}."""
    spacing, reach, front = (float(os.environ.get(key, default)) for key, default in (("XPSPACE", "0.006"), ("XPREACH", "0.015"), ("XPFRONT", "0.2")))
    waist, lag = float(os.environ.get("XPWAIST", "1.30")), float(os.environ.get("XPLAG", "0"))
    samples = mb.sample_surface(body.positions, body.triangles, spacing=spacing)
    face_area = 0.5 * np.linalg.norm(mb.face_normals(body.positions, body.triangles), axis=1)
    area = (face_area / np.maximum(np.bincount(samples.faces, minlength=len(face_area)), 1))[samples.faces] * 1e4  # cm2 each sample stands for: triangles get unequal sample density
    upper = samples.points[:, 1] >= waist
    corners = body.triangles[samples.faces]
    names = np.array(mr.region_of(skeleton.names, body.joints, body.weights))[corners[:, 0]]
    result = {}
    parts, extra_parts = [], []
    if xe.enabled():
        rest_points = (body.positions[corners] * samples.bary[:, :, None]).sum(1)
        rest_normals = xe.unit(mb.face_normals(body.positions, body.triangles)[samples.faces])
        rest_covered = xe.front_cover(rest_points, rest_normals, cloth.positions, cloth.triangles, front, outward_only=False)
    for pose in os.environ.get("XPPOSES", DEFAULT_POSES).split(","):
        delta = ms.pose_matrices(skeleton.names, skeleton.parents, skeleton.rest, pose_spec(pose, lag))
        moved_body, moved_cloth = posed(body, skeleton, delta), posed(cloth, skeleton, delta)
        points = (moved_body[corners] * samples.bary[:, :, None]).sum(1)
        normals = mb.face_normals(moved_body, body.triangles)[samples.faces]
        normals /= np.maximum(np.linalg.norm(normals, axis=1, keepdims=True), 1e-12)
        mask = exposed_mask(points, normals, moved_cloth, cloth.triangles, reach, front)
        result[pose] = (float(area[mask & upper].sum()), float(area[mask & ~upper].sum()))
        if xe.enabled():
            extra_parts.append(xe.format_pose(pose, xe.pose_numbers(points, normals, area, moved_cloth, cloth.triangles, moved_body, body.triangles, rest_covered, reach, front)))
        parts.append(f"{pose}={result[pose][0]:.0f}+{result[pose][1]:.0f}/{stretched_percent(cloth, moved_cloth):.2f}%")
        if os.environ.get("XPREGIONS"):
            print(f"   {pose}: " + ", ".join(f"{region}={area[mask & (names == region)].sum():.0f}" for region in np.unique(names[mask])))
    print(f"{label}: crossed {crossed_layers(cloth, mb.sample_surface(body.positions, body.triangles, spacing=0.003))} | exposed cm2 above+below waist / edges over 1.5x: " + "  ".join(parts))
    if xe.enabled():
        print(f"{label}: extra cm2 (outward-only cover / deep pokes / seen though covered at rest): " + "  ".join(extra_parts))
    return result


def main() -> None:
    skeleton = load_skeleton(os.environ.get("XPSKELETON", os.path.expanduser("~/Downloads/Male Mods/c0901e6024_top.glb")))
    body_paths = os.environ.get("XPBODY", "")
    for path in sys.argv[1:]:
        cloth, own_skin = load_garment(path, skeleton)
        body = own_skin if os.environ.get("XPOWNSKIN") or not body_paths else body_mesh(body_paths.split(","), skeleton)
        score(Path(path).name, cloth, body, skeleton)
        if xe.enabled() and os.environ.get("XPFULLBODY"):
            full = body_mesh(os.environ["XPFULLBODY"].split(","), skeleton)
            missing = xe.missing_numbers(own_skin.positions, own_skin.triangles, full.positions, full.triangles, cloth.positions, cloth.triangles, 0.006, 0.2)
            print(f"{Path(path).name}: missing skin cm2 seen {missing['missing_seen']:.0f}, under cloth {missing['missing_under_cloth']:.0f}")


if __name__ == "__main__":
    main()
