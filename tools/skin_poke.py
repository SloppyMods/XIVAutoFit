"""Find skin that pokes through cloth, the case fitcheck.py cannot see because it only measures cloth vertices.

    blender -b -P skin_poke.py -- <build.glb>

A skin vertex pokes when cloth lies behind it: a ray from the vertex going inward along its normal hits cloth within 15 mm.
"""
import sys

import bmesh
import bpy
import numpy as np
from mathutils.bvhtree import BVHTree

REACH = 0.015
path = sys.argv[sys.argv.index("--") + 1]


def material_name(obj):
    slot = obj.material_slots[0] if obj.material_slots else None
    return slot.material.name if slot and slot.material else ""


bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=path)
meshes = [o for o in bpy.data.objects if o.type == "MESH" and material_name(o)]
cloth_mesh = bmesh.new()
for obj in meshes:
    if not material_name(obj).startswith("/mt_c0201b0001_"):
        cloth_mesh.from_mesh(obj.data)
cloth_tree = BVHTree.FromBMesh(cloth_mesh)
for obj in meshes:
    if not material_name(obj).startswith("/mt_c0201b0001_b."):
        continue
    hits = []
    for vertex in obj.data.vertices:
        start = vertex.co + vertex.normal * 0.0001
        location, _, _, depth = cloth_tree.ray_cast(start, -vertex.normal, REACH)
        if location is not None:
            hits.append((depth * 1000, vertex.co.x, vertex.co.y, vertex.co.z))
    if hits:
        hits.sort(reverse=True)
        heights = np.array([h[3] for h in hits])
        print(f"POKE {obj.name}: {len(hits)} of {len(obj.data.vertices)} vertices, deepest {hits[0][0]:.1f} mm "
              f"at z {hits[0][3]:.2f}, heights {heights.min():.2f}..{heights.max():.2f}")
    else:
        print(f"POKE {obj.name}: none of {len(obj.data.vertices)} vertices")
