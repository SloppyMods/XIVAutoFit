"""Push an outfit's cloth clear of a body it does not contain, leaving everything else as exported.

Use for a slot whose body lives in another slot's model, like long boots over legs that come from the bottoms.
The reference body is only measured against; it is not added to the output.

    blender -b -P fit_to_ref.py -- <outfit.glb> <reference body.glb> <out name.glb>

Env: FITCLEAR=<mm> target clearance (3), FITR=<mm> falloff radius (25), FITDEEP=<mm> ignore vertices deeper than this
as hidden inner parts (20), FITZMIN=<m> no pushing below this height (0.16), FITPASSES=<n> rounds (6), FITSIGMA=<mm> smoothing width (10),
FITSMOOTH=<n> smoothing rounds (3), FITSPLITZ=<m> pushes and smoothing stay on one side of the body only below this height (everywhere by default;
set it to the crotch for a garment that crosses the middle, or the centre seam tears), FITMIDX=<mm> below FITSPLITZ, cloth within
this of x=0 counts as both sides, so the centre seam is not split hard (0 = old hard split),
FITPOKE=<mm> also push the cloth triangle wherever a skin vertex comes through it, up to this deep (off by default; for coarse cloth,
where long triangles cut through a rounded body even though every cloth vertex is clear), FITPOKEZ=<m> only skin above this height counts
(set it above a leg opening, or skin just past the hem crumples it).

Each round finds the cloth vertices too close to the skin, then moves every cloth vertex on the same side of the body
by the strongest push reaching it, fading to zero over FITR. Layered parts near a push move together and keep their
spacing, which pushing vertices one at a time does not do. The total movement is then blurred, so the final clearance
can land a little under FITCLEAR; measure it afterwards.
"""
import os
import sys

import bpy
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree

args = sys.argv[sys.argv.index("--") + 1:]
OUTFIT, REF, OUT_NAME = args[0], args[1], args[2]
OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "builds")
if os.path.exists(os.path.join(OUT_DIR, OUT_NAME)):
    sys.exit(f"refusing to overwrite {os.path.join(OUT_DIR, OUT_NAME)}; pick a new name")
CLEAR = float(os.environ.get("FITCLEAR", "3")) / 1000
RADIUS = float(os.environ.get("FITR", "25")) / 1000
DEEP = float(os.environ.get("FITDEEP", "20")) / 1000
ZMIN = float(os.environ.get("FITZMIN", "0.16"))
PASSES = int(os.environ.get("FITPASSES", "6"))
SIGMA = float(os.environ.get("FITSIGMA", "10")) / 1000
SMOOTH_ROUNDS = int(os.environ.get("FITSMOOTH", "3"))
SPLIT_Z = float(os.environ.get("FITSPLITZ", "9"))
MID_BAND = float(os.environ.get("FITMIDX", "0")) / 1000  # below FITSPLITZ, cloth within this of x=0 joins both sides (0 = hard split)


def same_side_of(other_x, x):
    """Which of other_x count as the same side as x; anything within FITMIDX of x=0 counts for both sides."""
    return (np.sign(other_x) == np.sign(x)) | (np.abs(other_x) < MID_BAND) | (abs(x) < MID_BAND)
POKE = float(os.environ.get("FITPOKE", "0")) / 1000
POKE_ZMIN = float(os.environ.get("FITPOKEZ", "-9"))
SKIN_TOKEN = "/mt_c0201b0001_b"  # also matches _bibo, so outfit skin is left out of the cloth list


def material_name(obj):
    slot = obj.material_slots[0] if obj.material_slots else None
    return slot.material.name if slot and slot.material else ""


# Load the reference first and keep only its skin as plain BVH trees, so nothing from it reaches the export.
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=REF)
trees = []
skin_points = []
for obj in bpy.data.objects:
    if obj.type == "MESH" and material_name(obj).startswith(SKIN_TOKEN):
        points = [tuple(obj.matrix_world @ v.co) for v in obj.data.vertices]
        trees.append(BVHTree.FromPolygons(points, [tuple(p.vertices) for p in obj.data.polygons]))
        skin_points += [(Vector(point), v.normal.copy()) for point, v in zip(points, obj.data.vertices)]
if not trees:
    sys.exit(f"no skin meshes ({SKIN_TOKEN}*) found in {REF}")

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=OUTFIT)
for obj in list(bpy.data.objects):
    if obj.type == "MESH" and obj.name.startswith("Icosphere"):  # Penumbra's export marker, not part of the model
        bpy.data.objects.remove(obj)
cloth = [o for o in bpy.data.objects if o.type == "MESH" and not material_name(o).startswith("/mt_c0201b0001_")]
if not cloth:
    sys.exit(f"no cloth meshes found in {OUTFIT}")

positions = np.array([tuple(v.co) for o in cloth for v in o.data.vertices])
cloth_faces = []
face_start = 0
for obj in cloth:
    cloth_faces += [tuple(face_start + i for i in p.vertices) for p in obj.data.polygons]
    face_start += len(obj.data.vertices)


def nearest_signed(point):
    """Signed distance to the closest skin surface (negative = inside) and that surface's normal."""
    best = None
    for tree in trees:
        hit = tree.find_nearest(Vector(point))
        if hit[0] is not None and (best is None or hit[3] < best[3]):
            best = hit
    return (Vector(point) - best[0]).dot(best[1]), np.array(best[1])


def poke_pushes(current):
    """Corners of each cloth triangle a skin vertex comes through, with the push that clears that vertex. The vertex test cannot see these."""
    tree = BVHTree.FromPolygons(current.tolist(), cloth_faces)
    sources, pushes = [], []
    for point, normal in skin_points:
        if point.z < POKE_ZMIN:
            continue
        location, _, face, depth = tree.ray_cast(point + normal * 0.0001, -normal, POKE)
        if location is not None:
            for corner in cloth_faces[face]:
                sources.append(current[corner])
                pushes.append(np.array(normal) * (depth + CLEAR))
    return sources, pushes


def push_round(current):
    """One round of pushes; returns the new positions and how many vertices were too close."""
    sources, pushes = [], []
    for point in current:
        if point[2] < ZMIN:
            continue
        signed, normal = nearest_signed(point)
        if -DEEP <= signed < CLEAR:
            sources.append(point)
            pushes.append(normal * (CLEAR - signed))
    if POKE:
        poke_sources, poke_vectors = poke_pushes(current)
        sources += poke_sources
        pushes += poke_vectors
    if not sources:
        return current, 0
    sources, pushes = np.array(sources), np.array(pushes)
    strength = np.linalg.norm(pushes, axis=1)
    moved = current.copy()
    for i, point in enumerate(current):
        same_side = same_side_of(sources[:, 0], point[0])  # a push on one leg must not move the other leg
        if point[2] >= SPLIT_Z:
            same_side = np.ones(len(sources), dtype=bool)
        if not same_side.any():
            continue
        fade = np.clip(1 - np.linalg.norm(sources[same_side] - point, axis=1) / RADIUS, 0, 1)
        fade = fade * fade * (3 - 2 * fade)
        reach = fade * strength[same_side]
        strongest = int(reach.argmax())
        if reach[strongest] > 0:
            moved[i] = point + pushes[same_side][strongest] * fade[strongest]
    return moved, len(sources)


def smoothed(current):
    """Blur the total movement over nearby vertices. Neighbours following different pushes otherwise leave a crease."""
    movement = current - original
    blurred = movement.copy()
    for i, point in enumerate(original):
        if point[2] < ZMIN:
            continue
        same_side = same_side_of(original[:, 0], point[0])
        if point[2] >= SPLIT_Z:
            same_side = np.ones(len(original), dtype=bool)
        gaps = np.linalg.norm(original[same_side] - point, axis=1)
        weights = np.exp(-(gaps * gaps) / (2 * SIGMA * SIGMA))
        blurred[i] = (movement[same_side] * weights[:, None]).sum(axis=0) / weights.sum()
    return original + blurred


original = positions.copy()
for round_number in range(PASSES):
    positions, count = push_round(positions)
    print(f"round {round_number}: {count} vertices under {CLEAR * 1000:.1f} mm")
    if not count:
        break
for smooth_round in range(SMOOTH_ROUNDS):
    positions = smoothed(positions)
    if smooth_round < SMOOTH_ROUNDS - 1:  # blurring gives back some clearance; recover it, then finish on a blur
        positions, count = push_round(positions)
        print(f"smooth {smooth_round}: {count} vertices under {CLEAR * 1000:.1f} mm")

start = 0
for obj in cloth:
    for vertex in obj.data.vertices:
        step = Vector(positions[start]) - vertex.co
        vertex.co += step
        if obj.data.shape_keys:  # Blender exports shape-key meshes from their keys, so every key has to move too
            for key in obj.data.shape_keys.key_blocks:
                key.data[vertex.index].co += step
        start += 1
    obj.data.update()

bpy.ops.export_scene.gltf(filepath=os.path.join(OUT_DIR, OUT_NAME), export_format="GLB", export_extras=True)
