"""Remove the leg skin that a boots build carries, keeping only the foot skin (from the Dionys Boots0507 batch).

    PATH=/usr/bin:/bin blender -b --factory-startup --disable-autoexec -P strip_leg_skin.py -- <in.glb> <out.glb>

A boots fit needs foot and leg skin as its reference (BODY2=<legs>), but the legs belong to the bottoms slot, so the
delivered boots keep only the foot. Every skin mesh (material containing `b0001`) except the ones named in
LSKEEP="mesh 0.0" (the default, the foot) is deleted; cloth is left as it is. Prints what it removed.
Refuses to overwrite an existing output.
"""
import os
import sys

import bpy

args = sys.argv[sys.argv.index("--") + 1:]
SOURCE, OUT = args[0], args[1]
KEEP = [name for name in os.environ.get("LSKEEP", "mesh 0.0").split(",") if name]
if os.path.exists(OUT):
    sys.exit(f"refusing to overwrite {OUT}; pick a new name")


def material_name(obj: bpy.types.Object) -> str:
    slot = obj.material_slots[0] if obj.material_slots else None
    return slot.material.name if slot and slot.material else ""


bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=SOURCE)
skin = [o for o in bpy.data.objects if o.type == "MESH" and "b0001" in material_name(o)]
missing = [name for name in KEEP if name not in {o.name for o in skin}]
if missing:
    sys.exit(f"LSKEEP names no skin mesh in {SOURCE}: {missing}; skin meshes are {[o.name for o in skin]}")
removed = [o for o in skin if o.name not in KEEP]
print("removed skin:", [(o.name, len(o.data.vertices)) for o in removed], "kept:", KEEP)
for obj in removed:
    bpy.data.objects.remove(obj)
bpy.ops.export_scene.gltf(filepath=OUT, export_format="GLB", export_extras=True)
