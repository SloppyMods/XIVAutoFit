"""Carry cloth from the body it was made for onto the Doll body, tightening loose spots as well as clearing clips.

    blender -b -P wrap_to_body.py -- <Doll build.glb> <original export.glb> <out name.glb>

The Doll build comes from transplant_body.py (Doll skin in the file, cloth untouched). The original export supplies the
body the cloth was designed on. Each cloth vertex moves by how far the Doll surface sits from the original surface at
that spot, so a designed gap (2 mm stockings, a looser skirt) stays the same size. Follow with fit_to_ref.py to clear
any spot that was already under the skin in the original.

Env: WRAPFADE=<mm,mm> full movement up to the first distance from the original skin, none past the second (30,70),
WRAPSIGMA=<mm> blur width that keeps neighbouring parts together (12), WRAPMAX=<mm> longest allowed move (25),
WRAPSHOULDER=<z0,z1,scale> sideways (|x|>0.05) cloth between z0 and z1 keeps only this share of its move, easing back to the full move 25 mm
below z0 and above z1, for a vest edge that the wrap pulls in and leaves skin showing beside it (off),
WRAPSPLITZ=<m> below this height the blur stays on one leg (off), WRAPPIERCE=<x,y,z mm> extra shift for piercings, for a navel
that sits somewhere else on the Doll body (0,0,0).
"""
import os
import sys

import bpy
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree

args = sys.argv[sys.argv.index("--") + 1:]
BUILD, ORIGINAL, OUT_NAME = args[0], args[1], args[2]
OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "builds")
FADE_FULL, FADE_NONE = (float(x) / 1000 for x in os.environ.get("WRAPFADE", "30,70").split(","))
SIGMA = float(os.environ.get("WRAPSIGMA", "12")) / 1000
MAX_MOVE = float(os.environ.get("WRAPMAX", "25")) / 1000
SHOULDER = [float(x) for x in os.environ["WRAPSHOULDER"].split(",")] if "WRAPSHOULDER" in os.environ else None
SHOULDER_EASE = 0.025
SHOULDER_MIN_X = 0.05
SPLIT_Z = float(os.environ.get("WRAPSPLITZ", "-9"))
PIERCE_SHIFT = np.array([float(x) for x in os.environ.get("WRAPPIERCE", "0,0,0").split(",")]) / 1000
SKIN_PREFIX = "/mt_c0201b0001_"
ORIGINAL_SKIN = SKIN_PREFIX + "bibo"
DOLL_SKIN = SKIN_PREFIX + "b.mtrl"
PIERCING = SKIN_PREFIX + "piercings"
CHUNK = 500  # vertices blurred per numpy batch, to keep memory use small


def material_name(obj):
    slot = obj.material_slots[0] if obj.material_slots else None
    return slot.material.name if slot and slot.material else ""


def tree_for(prefix):
    """One BVH (a search tree for closest-surface lookups) over every mesh whose material starts with prefix."""
    points, faces = [], []
    for obj in bpy.data.objects:
        if obj.type == "MESH" and material_name(obj).startswith(prefix):
            base = len(points)
            points += [tuple(obj.matrix_world @ v.co) for v in obj.data.vertices]
            faces += [tuple(i + base for i in p.vertices) for p in obj.data.polygons]
    if not points:
        sys.exit(f"no meshes with material {prefix}* in the loaded file")
    return BVHTree.FromPolygons(points, faces)


bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=ORIGINAL)
original_tree = tree_for(ORIGINAL_SKIN)

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=BUILD)
doll_tree = tree_for(DOLL_SKIN)
cloth = [o for o in bpy.data.objects if o.type == "MESH" and material_name(o) and not material_name(o).startswith(SKIN_PREFIX)]
piercings = [o for o in bpy.data.objects if o.type == "MESH" and material_name(o).startswith(PIERCING)]
if not cloth:
    sys.exit(f"no cloth meshes in {BUILD}")


def body_difference(points):
    """For each point: the step from the original surface to the Doll surface, faded with distance from the original."""
    moves = np.zeros_like(points)
    for i, point in enumerate(points):
        on_original, _, _, gap = original_tree.find_nearest(Vector(point))
        if on_original is None:
            continue
        on_doll = doll_tree.find_nearest(on_original)[0]
        if on_doll is None:
            continue
        move = np.array(on_doll - on_original)
        length = np.linalg.norm(move)
        if length > MAX_MOVE:
            move *= MAX_MOVE / length
        fade = np.clip((FADE_NONE - gap) / (FADE_NONE - FADE_FULL), 0, 1)
        moves[i] = move * fade * fade * (3 - 2 * fade)
    return moves


def blurred(points, moves):
    """Gaussian blur of the moves, so parts layered on each other travel together and nothing creases."""
    result = moves.copy()
    below_split = points[:, 2] < SPLIT_Z
    for start in range(0, len(points), CHUNK):
        batch = np.arange(start, min(start + CHUNK, len(points)))
        gaps = ((points[batch, None, :] - points[None, :, :]) ** 2).sum(axis=2)
        weights = np.exp(-gaps / (2 * SIGMA * SIGMA))
        other_leg = below_split[batch, None] & (np.sign(points[batch, None, 0]) != np.sign(points[None, :, 0]))
        weights[other_leg] = 0
        result[batch] = (weights @ moves) / weights.sum(axis=1, keepdims=True)
    return result


def shoulder_share(points):
    """Share of the wrap kept per point: the chosen scale inside the z band, easing back to 1 outside it and near the spine."""
    if SHOULDER is None:
        return np.ones(len(points))
    low, high, scale = SHOULDER
    outside = np.maximum(np.maximum(low - points[:, 2], points[:, 2] - high), 0)
    ease = np.clip(outside / SHOULDER_EASE, 0, 1)
    near_spine = np.clip((SHOULDER_MIN_X + 0.02 - np.abs(points[:, 0])) / 0.02, 0, 1)
    ease = np.maximum(ease, near_spine)
    return scale + (1 - scale) * ease


def shift_vertex(obj, index, move):
    """Move one vertex. Blender exports shape-key meshes from their keys, so every key has to move too."""
    step = Vector(move)
    obj.data.vertices[index].co += step
    if obj.data.shape_keys:
        for key in obj.data.shape_keys.key_blocks:
            key.data[index].co += step


positions = np.array([tuple(v.co) for o in cloth for v in o.data.vertices])
moves = blurred(positions, body_difference(positions)) * shoulder_share(positions)[:, None]
lengths = np.linalg.norm(moves, axis=1) * 1000
print(f"WRAP {len(positions)} cloth vertices, move mm p50/p95/max {np.percentile(lengths, 50):.1f} "
      f"{np.percentile(lengths, 95):.1f} {lengths.max():.1f}")

start = 0
for obj in cloth:
    for vertex in obj.data.vertices:
        shift_vertex(obj, vertex.index, moves[start])
        start += 1
    obj.data.update()

for obj in piercings:  # a piercing moves as one solid piece so it keeps its shape
    points = np.array([tuple(v.co) for v in obj.data.vertices])
    step = body_difference(points).mean(axis=0) + PIERCE_SHIFT
    print(f"WRAP {obj.name} piercing moved by {np.round(step * 1000, 1)} mm")
    for vertex in obj.data.vertices:
        shift_vertex(obj, vertex.index, step)
    obj.data.update()

bpy.ops.export_scene.gltf(filepath=os.path.join(OUT_DIR, OUT_NAME), export_format="GLB", export_extras=True)
