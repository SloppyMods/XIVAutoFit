"""Extra exposure numbers for male_exposed.py and dionys_exposed.py (review F3), printed only with XPEXTRA=1.

The main exposed score counts skin with cloth just behind it and nothing in front. It misses four cases:
- outward: the same score, but cloth in front counts as cover only when that triangle faces outward
  (a body-facing inner wall the game may cull is not cover);
- deep: skin with cloth behind it deeper than XPREACH (up to XPDEEP, 60 mm) and nothing in front, which the main score drops;
- see-through: skin that was under cloth at rest and, in the pose, is seen by one of 8 horizontal orthographic cameras
  (so a tear or gap shows up even though no cloth lies behind it);
- missing (rest pose, needs a full reference body): reference skin with no build skin within 4 mm, split into seen / under cloth.

Cameras are depth rasters at XPPIXEL (2 mm) over cloth and skin together, so a slit narrower than about one pixel is missed.
All numbers are cm2 of skin.
"""
import os

import numpy as np
from scipy.spatial import cKDTree

import male_body as mb

DEEP = float(os.environ.get("XPDEEP", "0.06"))
PIXEL = float(os.environ.get("XPPIXEL", "0.002"))
SKIN_TOLERANCE = 0.003  # skin this close in front is the point's own surface, not a blocker
CLOTH_TOLERANCE = 0.0005  # cloth more than this in front blocks the view
FACING = 0.3  # cameras only see skin that faces them at least this much (cosine)
MISSING_GAP = 0.004
CAMERAS = np.array([(np.sin(a), 0.0, np.cos(a)) for a in np.linspace(0, 2 * np.pi, 8, endpoint=False)])


def enabled() -> bool:
    return bool(int(os.environ.get("XPEXTRA", "0")))


def unit(vectors: np.ndarray) -> np.ndarray:
    return vectors / np.maximum(np.linalg.norm(vectors, axis=1, keepdims=True), 1e-12)


def front_cover(points: np.ndarray, normals: np.ndarray, cloth: np.ndarray, triangles: np.ndarray, front: float, outward_only: bool) -> np.ndarray:
    """Points with cloth in front of them within `front`; with outward_only, only outward-facing triangles count."""
    hits = mb.inward_hits(points, -normals, cloth, triangles, front)
    if not hits:
        return np.zeros(len(points), bool)
    index = np.array([h[0] for h in hits], "i8")
    if outward_only:
        faces = unit(mb.face_normals(cloth, triangles))[np.array([h[1] for h in hits], "i8")]
        index = index[(faces * normals[index]).sum(1) > 0]
    mask = np.zeros(len(points), bool)
    mask[index] = True
    return mask


def behind_depth(points: np.ndarray, normals: np.ndarray, cloth: np.ndarray, triangles: np.ndarray, reach: float) -> np.ndarray:
    """Depth of the nearest cloth straight behind each point, up to reach (inf where none)."""
    depth = np.full(len(points), np.inf)
    for i, _, t in mb.inward_hits(points, normals, cloth, triangles, reach):
        depth[i] = min(depth[i], t)
    return depth


def _raster_max_depth(vertices: np.ndarray, triangles: np.ndarray, camera: np.ndarray, origin: np.ndarray, shape: tuple[int, int]) -> np.ndarray:
    """Orthographic depth raster along `camera`: per pixel, the largest dot(x, camera) (closest to the camera)."""
    side = unit(np.cross([[0.0, 1.0, 0.0]], camera[None]))[0]
    up = np.array([0.0, 1.0, 0.0])
    uv = np.c_[(vertices @ side - origin[0]) / PIXEL, (vertices @ up - origin[1]) / PIXEL]
    depth = vertices @ camera
    raster = np.full(shape, -np.inf)
    for tri in triangles:
        p, d = uv[tri], depth[tri]
        lo, hi = np.floor(p.min(0)).astype(int), np.ceil(p.max(0)).astype(int)
        lo, hi = np.maximum(lo, 0), np.minimum(hi, np.array(shape) - 1)
        if (hi < lo).any():
            continue
        gx, gy = np.meshgrid(np.arange(lo[0], hi[0] + 1) + 0.5, np.arange(lo[1], hi[1] + 1) + 0.5, indexing="ij")
        (x0, y0), (x1, y1), (x2, y2) = p
        area = (x1 - x0) * (y2 - y0) - (x2 - x0) * (y1 - y0)
        if abs(area) < 1e-12:
            continue
        w1 = ((gx - x0) * (y2 - y0) - (x2 - x0) * (gy - y0)) / area
        w2 = ((x1 - x0) * (gy - y0) - (gx - x0) * (y1 - y0)) / area
        inside = (w1 >= 0) & (w2 >= 0) & (w1 + w2 <= 1)
        if not inside.any():
            continue
        z = d[0] + w1 * (d[1] - d[0]) + w2 * (d[2] - d[0])
        block = raster[lo[0]:hi[0] + 1, lo[1]:hi[1] + 1]
        np.maximum(block, np.where(inside, z, -np.inf), out=block)
    return raster


def seen_mask(points: np.ndarray, normals: np.ndarray, cloth: tuple[np.ndarray, np.ndarray], skin: tuple[np.ndarray, np.ndarray]) -> np.ndarray:
    """Points that at least one camera sees; cloth and skin both block the view."""
    vertices = np.vstack([cloth[0], skin[0]])
    seen = np.zeros(len(points), bool)
    for camera in CAMERAS:
        side = unit(np.cross([[0.0, 1.0, 0.0]], camera[None]))[0]
        coords = np.c_[vertices @ side, vertices[:, 1]]
        origin = coords.min(0) - PIXEL
        shape = tuple((np.ceil((coords.max(0) - origin) / PIXEL) + 2).astype(int))
        cloth_raster = _raster_max_depth(cloth[0], cloth[1], camera, origin, shape)
        skin_raster = _raster_max_depth(skin[0], skin[1], camera, origin, shape)
        cell = np.floor((np.c_[points @ side, points[:, 1]] - origin) / PIXEL).astype(int)
        cell = np.clip(cell, 0, np.array(shape) - 1)
        own = points @ camera
        clear = (cloth_raster[cell[:, 0], cell[:, 1]] <= own + CLOTH_TOLERANCE) & (skin_raster[cell[:, 0], cell[:, 1]] <= own + SKIN_TOLERANCE)
        seen |= (normals @ camera > FACING) & clear
    return seen


def pose_numbers(points: np.ndarray, normals: np.ndarray, area: np.ndarray, cloth: np.ndarray, cloth_tris: np.ndarray,
                 skin: np.ndarray, skin_tris: np.ndarray, rest_covered: np.ndarray, reach: float, front: float) -> dict[str, float]:
    """cm2 for one pose: outward-only exposed, deep pokes, see-through."""
    depth = behind_depth(points, normals, cloth, cloth_tris, DEEP)
    covered_any = front_cover(points, normals, cloth, cloth_tris, front, outward_only=False)
    covered_out = front_cover(points, normals, cloth, cloth_tris, front, outward_only=True)
    outward = (depth < reach) & ~covered_out
    deep = (depth >= reach) & np.isfinite(depth) & ~covered_any
    through = rest_covered & seen_mask(points, normals, (cloth, cloth_tris), (skin, skin_tris))
    return {"outward": float(area[outward].sum()), "deep": float(area[deep].sum()), "seen": float(area[through].sum())}


def missing_numbers(build_skin: np.ndarray, build_tris: np.ndarray, reference: np.ndarray, reference_tris: np.ndarray,
                    cloth: np.ndarray, cloth_tris: np.ndarray, spacing: float, front: float) -> dict[str, float]:
    """Rest pose: reference skin with no build skin within 4 mm, as cm2 seen by a camera and cm2 under cloth."""
    samples = mb.sample_surface(reference, reference_tris, spacing=spacing)
    face_area = 0.5 * np.linalg.norm(mb.face_normals(reference, reference_tris), axis=1)
    area = (face_area / np.maximum(np.bincount(samples.faces, minlength=len(face_area)), 1))[samples.faces] * 1e4
    normals = unit(mb.face_normals(reference, reference_tris)[samples.faces])
    have = mb.sample_surface(build_skin, build_tris, spacing=0.002).points
    gap, _ = cKDTree(have).query(samples.points, workers=3)
    missing = gap > MISSING_GAP
    seen = seen_mask(samples.points, normals, (cloth, cloth_tris), (build_skin, build_tris))
    return {"missing_seen": float(area[missing & seen].sum()), "missing_under_cloth": float(area[missing & ~seen].sum())}


def format_pose(pose: str, numbers: dict[str, float]) -> str:
    return f"{pose}=out {numbers['outward']:.0f}/deep {numbers['deep']:.0f}/seen {numbers['seen']:.0f}"
