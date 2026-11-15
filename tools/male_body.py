"""Bodies and the body-to-body move for fitting TBSE male cloth (c0101) onto HR3 male bodies (c0901).

Three steps, all arrays and no Blender:
1. race_place: the game's own race conversion from human.pbd, one matrix per bone, blended by the vertex's bone weights.
2. register: non-rigid fit of the placed TBSE body onto the HR3 body, smoothed along the body's own surface.
3. body_field: for any cloth point, the move of the closest TBSE body point.
"""
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import scipy.sparse as sp
import scipy.sparse.linalg as spl
from scipy.spatial import cKDTree

sys.path.insert(0, str(Path(__file__).resolve().parent))
import mdl_read  # noqa: E402
import pbd  # noqa: E402  human.pbd parser (copied from builds/_a0158, which is not in git)
import sqpack_read  # noqa: E402  reads human.pbd straight from the game files

HUMAN_PBD = Path(__file__).resolve().parent.parent / "builds" / "_male" / "human.pbd"
RACE_HR3 = 901
SAMPLE_SPACING = 0.002
DEFAULT_TBSE = ("/mnt/STORAGE/Penumbra/The Body SE/common/1/c0101e0000_top.mdl",
                "/mnt/STORAGE/Penumbra/The Body SE/p3/step 6- smallclothes options/sfw/chara/equipment/e0000/model/c0101e0000_dwn.mdl")
_HRB = "/mnt/STORAGE/Penumbra/The hrBody 3 IVCS2 4K V1_0_0/p1/"
DEFAULT_HR3 = (_HRB + "body type/chubby/chara/equipment/e0000/model/c0901e0000_top.mdl",
               _HRB + "legs (smallclothes legs)/underwear sfw/chara/equipment/e0000/model/c0901e0000_dwn.mdl")
BODY_MATERIALS = ("b0001_b.", "e0000_dwn_")  # bare skin plus the tight underwear, which is the body surface under shorts


@dataclass(frozen=True)
class Body:
    positions: np.ndarray
    triangles: np.ndarray
    bones: tuple[str, ...]
    joints: np.ndarray
    weights: np.ndarray


def load_body(paths: tuple[str, ...]) -> Body:
    """Merge the skin meshes of several .mdl files into one body, with one shared bone-name table."""
    positions, triangles, joints, weights = [], [], [], []
    names: dict[str, int] = {}
    count = 0
    for path in paths:
        model = mdl_read.read_mdl(path)
        for mesh in model.meshes:
            if not any(token in mesh.material for token in BODY_MATERIALS):
                continue
            remap = np.array([names.setdefault(bone, len(names)) for bone in model.bones])
            positions.append(mesh.positions)
            triangles.append(mesh.triangles + count)
            joints.append(remap[mesh.joints])
            weights.append(mesh.weights)
            count += len(mesh.positions)
    if not positions:
        raise ValueError(f"no skin meshes in {paths}")
    width = max(j.shape[1] for j in joints)
    joints = [np.pad(j, ((0, 0), (0, width - j.shape[1]))) for j in joints]
    weights = [np.pad(w, ((0, 0), (0, width - w.shape[1]))) for w in weights]
    return Body(np.vstack(positions), np.vstack(triangles), tuple(names), np.vstack(joints), np.vstack(weights))


class RaceTable:
    """Per-bone race matrices from human.pbd.

    A bone the table lacks uses its nearest listed ancestor, never the identity. A listed bone whose matrix misses the HR3
    skeleton by more than BONE_FAIL (the check is: does the matrix carry the c0101 rest bone onto the c0901 rest bone?) is
    replaced by the skeleton's own move times a limb-length scale, because some human.pbd arm entries are unusable as a
    placement. This rule is what makes the sleeves work; the body registration fixes girth afterwards.
    """

    BONE_FAIL = 0.2

    def __init__(self, names: list[str], parents: list[int], rest_c0101: np.ndarray, rest_c0901: np.ndarray, race: int = RACE_HR3):
        raw = HUMAN_PBD.read_bytes() if HUMAN_PBD.exists() else sqpack_read.read("chara/xls/bonedeformer/human.pbd")
        table, _, _ = pbd.parse(raw)
        self.table = table[race]["bones"]
        self.index = {name: i for i, name in enumerate(names)}
        self.parents = parents
        self.names = names
        self.rest_a = rest_c0101
        self.rest_b = rest_c0901
        self.children: dict[int, list[int]] = {}
        for child, parent in enumerate(parents):
            if parent >= 0:
                self.children.setdefault(parent, []).append(child)
        self.failed = [n for n in self.table if n in self.index and self._misses(n)]
        print(f"race table: {len(self.failed)} bones fail the placement check and use the skeleton instead: {self.failed}")

    def _misses(self, bone: str) -> bool:
        i = self.index[bone]
        placed = self.table[bone][:3, :3] @ self.rest_a[i][:3, 3] + self.table[bone][:3, 3]
        return float(np.linalg.norm(placed - self.rest_b[i][:3, 3])) > self.BONE_FAIL

    def _limb_scale(self, bone: str) -> float:
        i = self.index[bone]
        for child in self.children.get(i, []):
            length_a = float(np.linalg.norm(self.rest_a[child][:3, 3] - self.rest_a[i][:3, 3]))
            length_b = float(np.linalg.norm(self.rest_b[child][:3, 3] - self.rest_b[i][:3, 3]))
            if length_a > 0.03:
                return float(np.clip(length_b / length_a, 0.8, 2.5))
        return 1.25

    def _skeleton_matrix(self, i: int, scale: float) -> np.ndarray:
        """Bone-to-model on the HR3 skeleton, scaled about the bone, times model-to-bone on the TBSE skeleton."""
        return (self.rest_b[i] @ np.diag([scale, scale, scale, 1.0]) @ np.linalg.inv(self.rest_a[i]))[:3, :]

    def matrix(self, bone: str) -> np.ndarray:
        if bone in self.failed:
            return self._skeleton_matrix(self.index[bone], self._limb_scale(bone))
        current = self.index.get(bone, -1)
        while current >= 0:
            name = self.names[current]
            found = self.table.get(name)
            if found is not None:
                if name in self.failed:
                    return self._skeleton_matrix(current, self._limb_scale(name))
                return found
            current = self.parents[current]
        return np.eye(3, 4)

    def blend(self, bones: tuple[str, ...] | list[str], joints: np.ndarray, weights: np.ndarray) -> np.ndarray:
        """Per-vertex 3x4 race matrix, from the bones weighted on that vertex."""
        by_bone = np.stack([self.matrix(bone) for bone in bones])
        share = weights / np.maximum(weights.sum(1, keepdims=True), 1e-9)
        return (by_bone[joints] * share[:, :, None, None]).sum(1)


def apply_matrices(points: np.ndarray, matrices: np.ndarray) -> np.ndarray:
    return (matrices[:, :3, :3] @ points[..., None])[..., 0] + matrices[:, :3, 3]


def face_normals(points: np.ndarray, triangles: np.ndarray) -> np.ndarray:
    return np.cross(points[triangles[:, 1]] - points[triangles[:, 0]], points[triangles[:, 2]] - points[triangles[:, 0]])


def vertex_normals(points: np.ndarray, triangles: np.ndarray) -> np.ndarray:
    normals = np.zeros_like(points)
    for corner in range(3):
        np.add.at(normals, triangles[:, corner], face_normals(points, triangles))
    return normals / np.maximum(np.linalg.norm(normals, axis=1, keepdims=True), 1e-12)


@dataclass(frozen=True)
class Samples:
    """Points spread over a surface, with each one's triangle and barycentric weights, for fast closest-point lookups."""
    points: np.ndarray
    normals: np.ndarray
    faces: np.ndarray
    bary: np.ndarray
    tree: cKDTree


def sample_surface(points: np.ndarray, triangles: np.ndarray, spacing: float = SAMPLE_SPACING, seed: int = 7) -> Samples:
    rng = np.random.default_rng(seed)
    cross = face_normals(points, triangles)
    area = 0.5 * np.linalg.norm(cross, axis=1)
    counts = np.ceil(area / (spacing * spacing)).astype(int) + 1
    faces = np.repeat(np.arange(len(triangles)), counts)
    u, v = rng.random(len(faces)), rng.random(len(faces))
    flip = u + v > 1
    u[flip], v[flip] = 1 - u[flip], 1 - v[flip]
    bary = np.c_[1 - u - v, u, v]
    tri = triangles[faces]
    located = (points[tri] * bary[:, :, None]).sum(1)
    normals = cross[faces] / np.maximum(np.linalg.norm(cross[faces], axis=1, keepdims=True), 1e-12)
    return Samples(located, normals, faces, bary, cKDTree(located))


def weld(points: np.ndarray, triangles: np.ndarray, tolerance: float = 1e-4) -> tuple[np.ndarray, np.ndarray]:
    """Merge vertices at the same spot (UV seams split them). Returns each vertex's welded id and the welded triangles."""
    keys = np.round(points / tolerance).astype("i8")
    _, ids = np.unique(keys, axis=0, return_inverse=True)
    return ids.ravel(), ids.ravel()[triangles]


def laplacian(count: int, triangles: np.ndarray) -> sp.csr_matrix:
    edges = np.vstack([triangles[:, [0, 1]], triangles[:, [1, 2]], triangles[:, [2, 0]]])
    pairs = np.vstack([edges, edges[:, ::-1]])
    adj = sp.coo_matrix((np.ones(len(pairs)), (pairs[:, 0], pairs[:, 1])), shape=(count, count)).tocsr()
    adj.data[:] = 1
    return sp.diags(np.asarray(adj.sum(1)).ravel()) - adj


def closest_compatible(sources: np.ndarray, normals: np.ndarray, target: Samples, neighbours: int = 12, max_angle_cos: float = 0.25) -> tuple[np.ndarray, np.ndarray]:
    """For each point, the nearest target sample whose surface faces roughly the same way, or NaN if none does.

    The facing test stops a thigh from matching the other thigh or an arm from matching the ribs.
    """
    _, found = target.tree.query(sources, k=neighbours)
    agreement = (target.normals[found] * normals[:, None, :]).sum(2)
    usable = agreement > max_angle_cos
    choice = usable.argmax(1)
    rows = np.arange(len(sources))
    picked = found[rows, choice]
    matched = target.points[picked]
    matched[~usable[rows, choice]] = np.nan
    return matched, picked


def register(source: Body, placed: np.ndarray, target: Samples, schedule: tuple[float, ...], step: float, max_move: float) -> np.ndarray:
    """Move the placed TBSE body onto the HR3 surface. Returns the moved TBSE vertices.

    Each round finds a closest target point per welded vertex, then spreads the wanted moves along the body's own surface:
    solving (I + t L) x = d, where L is the surface graph's Laplacian and t sets how wide the spreading is. Early rounds are
    wide (whole-limb moves), later ones narrow (local shape).
    """
    ids, welded = weld(source.positions, source.triangles)
    count = ids.max() + 1
    current = np.zeros((count, 3))
    current[ids] = placed
    lap = laplacian(count, welded)
    identity = sp.identity(count, format="csr")
    for spread in schedule:
        normals = vertex_normals(current, welded)
        matched, _ = closest_compatible(current, normals, target)
        wanted = matched - current
        known = np.isfinite(wanted[:, 0])
        wanted[~known] = 0
        length = np.linalg.norm(wanted, axis=1, keepdims=True)
        wanted *= np.minimum(1, max_move / np.maximum(length, 1e-9))
        solver = spl.factorized((identity + spread * lap).tocsc())
        confidence = solver(known.astype("f8"))
        smooth = np.stack([solver(wanted[:, axis]) for axis in range(3)], 1)
        smooth /= np.maximum(confidence, 1e-3)[:, None]
        current += step * smooth
        print(f"register spread={spread:6.1f} unmatched={np.count_nonzero(~known)} mean gap={np.nanmean(np.linalg.norm(wanted[known], axis=1)) * 1000:.1f} mm")
    return current[ids]


def inward_hits(skin: np.ndarray, normals: np.ndarray, cloth: np.ndarray, triangles: np.ndarray, reach: float) -> list[tuple[int, int, float]]:
    """Rays from skin vertices going straight inward; returns (skin vertex, cloth triangle, depth) for every ray that hits cloth within reach."""
    samples = sample_surface(cloth, triangles, spacing=0.005)
    groups = samples.tree.query_ball_point(skin, reach + 0.012, workers=3)
    a, b, c = cloth[triangles[:, 0]], cloth[triangles[:, 1]], cloth[triangles[:, 2]]
    found: list[tuple[int, int, float]] = []
    for i, group in enumerate(groups):
        if not group:
            continue
        candidates = np.unique(samples.faces[np.array(group)])
        origin, direction = skin[i] + normals[i] * 1e-4, -normals[i]
        e1, e2 = b[candidates] - a[candidates], c[candidates] - a[candidates]
        h = np.cross(direction, e2)
        det = (e1 * h).sum(1)
        with np.errstate(divide="ignore", invalid="ignore"):
            inverse = 1.0 / det
            offset = origin - a[candidates]
            u = inverse * (offset * h).sum(1)
            q = np.cross(offset, e1)
            v = inverse * (direction * q).sum(1)
            t = inverse * (e2 * q).sum(1)
        good = (np.abs(det) > 1e-12) & (u >= 0) & (v >= 0) & (u + v <= 1) & (t >= 0) & (t < reach)
        for index in np.where(good)[0]:
            found.append((i, int(candidates[index]), float(t[index])))
    return found


def body_field(cloth: np.ndarray, cloth_normals: np.ndarray, placed_body: Samples, move: np.ndarray, body_triangles: np.ndarray, angle_cos: float) -> tuple[np.ndarray, np.ndarray]:
    """For each cloth point: the body's move at its closest compatible body point, and the distance to that point (NaN if none).

    An angle_cos of -2 turns the facing test off, so neighbouring cloth layers that face opposite ways still pick the same body point.
    """
    matched, picked = closest_compatible(cloth, cloth_normals, placed_body, max_angle_cos=angle_cos)
    tri = body_triangles[placed_body.faces[picked]]
    moved = (move[tri] * placed_body.bary[picked][:, :, None]).sum(1)
    gap = np.linalg.norm(cloth - matched, axis=1)
    moved[~np.isfinite(gap)] = 0
    return moved, gap


def crossed_vertices(points: np.ndarray, triangles: np.ndarray, skin: Samples, reach: float, own_gap: float = 3e-4) -> dict[int, tuple[float, np.ndarray]]:
    """Welded vertex id to (depth, normal) where an outer-facing cloth vertex has a body-facing cloth layer just in front of it, meaning an inner wall came through.

    Each surface is judged against its own nearest skin, so two outer surfaces that merely face each other across a gap (a sleeve and the torso) do not count.
    """
    ids, welded = weld(points, triangles)
    normals = vertex_normals(points, triangles)
    faces = face_normals(points, triangles)
    centres = points[triangles].mean(1)
    outward = (normals * skin.normals[skin.tree.query(points)[1]]).sum(1) > 0
    face_inward = (faces * skin.normals[skin.tree.query(centres)[1]]).sum(1) < 0
    found: dict[int, tuple[float, np.ndarray]] = {}
    for vertex, face, depth in inward_hits(points, -normals, points, triangles, reach):
        if not (outward[vertex] and face_inward[face]) or depth <= own_gap or ids[vertex] in welded[face]:
            continue
        key = int(ids[vertex])
        if key not in found or depth > found[key][0]:
            found[key] = (depth, normals[vertex])
    return found
