"""Side-by-side workbench renders of male builds: skin tan, fur grey, cloth colored by file.

    blender -b -P render_male.py -- <out prefix> <center height> <width> <glb> [<glb> ...]

Renders each file from front, side and back into <prefix>_<i>_<view>.png. Run with --disable-autoexec for safety.
"""
import math
import os
import sys

import bpy

args = sys.argv[sys.argv.index("--") + 1:]
prefix, center, width = args[0], float(args[1]), float(args[2])
X_OFFSET = float(os.environ.get("RMX", "0"))  # camera shift sideways, to zoom in on one hand
files = args[3:]
CLOTH = [(0.1, 0.35, 0.8, 1), (0.8, 0.3, 0.1, 1), (0.2, 0.6, 0.3, 1)]
VIEWS = {"front": ((X_OFFSET, -3, center), (math.radians(90), 0, 0)), "side": ((X_OFFSET + 3, 0, center), (math.radians(90), 0, math.radians(90))), "back": ((X_OFFSET, 3, center), (math.radians(90), 0, math.radians(180)))}

MERGE = bool(os.environ.get("RMMERGE"))  # one combined scene, to see how pieces from several files meet at a seam
if MERGE:
    bpy.ops.wm.read_factory_settings(use_empty=True)
for number, path in enumerate(files):
    if not MERGE:
        bpy.ops.wm.read_factory_settings(use_empty=True)
    known = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=path)
    for obj in set(bpy.data.objects) - known:
        if obj.type != "MESH":
            continue
        material = obj.material_slots[0].material.name if obj.material_slots and obj.material_slots[0].material else ""
        if "b0001_b" in material:
            obj.color = (0.85, 0.72, 0.58, 1)
        elif "b0001_h" in material:
            obj.color = (0.5, 0.45, 0.4, 1)
        elif os.environ.get("RMNOCLOTH"):
            obj.hide_render = True
        else:
            obj.color = CLOTH[number % len(CLOTH)]
    if MERGE and number < len(files) - 1:
        continue
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_WORKBENCH"
    scene.display.shading.light = "STUDIO"
    scene.display.shading.color_type = "OBJECT"
    scene.display.shading.show_cavity = True
    scene.render.resolution_x = scene.render.resolution_y = 900
    camera = bpy.data.objects.new("camera", bpy.data.cameras.new("camera"))
    scene.collection.objects.link(camera)
    scene.camera = camera
    camera.data.type = "ORTHO"
    camera.data.ortho_scale = width
    for name, (location, rotation) in VIEWS.items():
        camera.location = location
        camera.rotation_euler = rotation
        scene.render.filepath = f"{prefix}_{number}_{name}.png"
        bpy.ops.render.render(write_still=True)
