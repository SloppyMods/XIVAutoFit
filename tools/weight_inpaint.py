"""Give cloth bone weights from the body where the match is trustworthy, and calculate smooth weights everywhere else.

Follows "Robust Skin Weights Transfer via Weight Inpainting" (Abdrashitov et al., SIGGRAPH Asia 2023), with a uniform
Laplacian (each vertex compares itself with its neighbours equally) instead of the paper's cotangent one, because cloth
triangles here can be long and thin.

A cloth vertex is trustworthy when skin close by faces the same way. Copying everywhere else is what splits the crotch
between the hip and leg bones and stretches the cloth, so those vertices are solved for instead. Vertices far from the
body keep their original weights, and so does any separate piece with no trustworthy vertex (a belt, a hanging flap).
"""
import sys
from dataclasses import dataclass

import numpy as np
import scipy.sparse as sp
from scipy.sparse.csgraph import connected_components
from scipy.sparse.linalg import splu

import male_body as mb

NEIGHBOURS = 12
WAIST_BLEND = 0.05  # metres below the waist height where nothing is copied, so the solve blends the two sets of weights
REGULARIZER = 1e-8


@dataclass(frozen=True)
class InpaintSettings:
    confident_gap: float  # metres: skin must be this close for a copy to be trusted
    confident_cos: float  # cosine of the largest angle between cloth and skin facing
    hold_gap: float  # metres: cloth further than this from the skin keeps its original weights
    waist_height: float  # metres: cloth above this keeps its starting weights, so a belt and its strap stay as they were


def solid_bones(names: list[str], parents: list[int]) -> np.ndarray:
    """For each bone, itself or its nearest ancestor that is not an iv_ bone. Cloth then ignores the bones that shift skin alone."""
    def walk(bone: int) -> int:
        while names[bone].startswith("iv_") and parents[bone] >= 0:
            bone = parents[bone]
        return bone

    return np.array([walk(bone) for bone in range(len(names))])


def original_rows(joints: np.ndarray, weights: np.ndarray, bone_count: int) -> np.ndarray:
    rows = np.zeros((len(joints), bone_count))
    for row, (row_joints, row_weights) in enumerate(zip(joints, weights)):
        total = float(row_weights.sum()) or 1.0
        for joint, weight in zip(row_joints, row_weights):
            if weight > 0:
                rows[row, joint] += float(weight) / total
    return rows


def body_rows(body: mb.Body, samples: mb.Samples, picked: np.ndarray, names: list[str], solid: np.ndarray) -> np.ndarray:
    """Weights at each picked skin sample, blended from its triangle's three corners."""
    index = {name: i for i, name in enumerate(names)}
    missing = sorted(set(body.bones) - set(names))
    if missing:
        sys.exit(f"body bones missing from the skeleton: {missing}")
    table = solid[np.array([index[bone] for bone in body.bones])]
    rows = np.zeros((len(picked), len(names)))
    corners, shares = body.triangles[samples.faces[picked]], samples.bary[picked]
    for row, (triangle, share) in enumerate(zip(corners, shares)):
        for vertex, part in zip(triangle, share):
            total = float(body.weights[vertex].sum()) or 1.0
            for joint, weight in zip(body.joints[vertex], body.weights[vertex]):
                if weight > 0:
                    rows[row, table[joint]] += float(part) * float(weight) / total
    return rows


def fixed_vertices(points: np.ndarray, triangles: np.ndarray, confident: np.ndarray, far: np.ndarray) -> np.ndarray:
    """Vertices the solve may not change: trustworthy, far from the body, or on a piece with nothing trustworthy to spread from."""
    laplacian = mb.laplacian(len(points), triangles)
    _, piece = connected_components(laplacian, directed=False)
    anchored = np.isin(piece, np.unique(piece[confident]))
    return confident | far | ~anchored


def solve_free(laplacian: sp.csr_matrix, rows: np.ndarray, fixed: np.ndarray) -> np.ndarray:
    """Fill in the free rows by minimizing bumpiness, with the fixed rows held in place."""
    free = np.where(~fixed)[0]
    if len(free) == 0:
        return rows
    held = np.where(fixed)[0]
    energy = (laplacian + laplacian @ laplacian).tocsr()
    solver = splu((energy[free][:, free] + REGULARIZER * sp.identity(len(free))).tocsc())
    coupling = energy[free][:, held]
    active = np.where(rows[held].any(0))[0]
    solved = rows.copy()
    solved[free] = 0.0
    for bone in active:
        solved[free, bone] = solver.solve(-(coupling @ rows[held, bone]))
    return solved


def limited(rows: np.ndarray, slots: int) -> tuple[np.ndarray, np.ndarray]:
    """Clamp negatives, keep the strongest bones per vertex, and make each row add up to 1."""
    joints, weights = np.zeros((len(rows), slots), "i8"), np.zeros((len(rows), slots))
    clean = np.maximum(rows, 0.0)
    for row, values in enumerate(clean):
        strongest = np.argsort(-values)[:slots]
        strongest = strongest[values[strongest] > 1e-4]
        total = values[strongest].sum()
        joints[row, :len(strongest)] = strongest
        weights[row, :len(strongest)] = values[strongest] / total
    return joints, weights


def inpainted_weights(positions: np.ndarray, cloth_triangles: np.ndarray, cloth_joints: np.ndarray, cloth_weights: np.ndarray, body: mb.Body,
                      samples: mb.Samples, names: list[str], parents: list[int], settings: InpaintSettings) -> tuple[np.ndarray, np.ndarray]:
    """New (joints, weights) for every cloth vertex. Vertices stored twice at a UV seam get identical weights, so seams cannot split."""
    welded_ids, welded_triangles = mb.weld(positions, cloth_triangles)
    _, first = np.unique(welded_ids, return_index=True)
    points = positions[first]
    normals = mb.vertex_normals(points, welded_triangles)
    rows = original_rows(cloth_joints[first], cloth_weights[first], len(names))

    matched, picked = mb.closest_compatible(points, normals, samples, neighbours=NEIGHBOURS, max_angle_cos=settings.confident_cos)
    gap = np.linalg.norm(matched - points, axis=1)
    confident = (np.nan_to_num(gap, nan=np.inf) < settings.confident_gap) & (points[:, 1] < settings.waist_height - WAIST_BLEND)
    rows[confident] = body_rows(body, samples, picked[confident], names, solid_bones(names, parents))
    far = (samples.tree.query(points)[0] > settings.hold_gap) | (points[:, 1] > settings.waist_height)
    fixed = fixed_vertices(points, welded_triangles, confident, far)
    print(f"weights: {len(points)} cloth points, {np.count_nonzero(confident)} copied, {np.count_nonzero(fixed & ~confident)} kept, {np.count_nonzero(~fixed)} solved")

    solved = solve_free(mb.laplacian(len(points), welded_triangles), rows, fixed)
    joints, weights = limited(solved, cloth_joints.shape[1])
    return joints[welded_ids].astype(cloth_joints.dtype), weights[welded_ids]
