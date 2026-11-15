"""Render a Dionys build standing and in test poses, with the skin bright cyan so any skin showing through cloth is easy to spot.

    PATH=/usr/bin:/bin RENDER_POSES=<poses.json> blender -b --factory-startup --disable-autoexec -P dionys_render.py -- <build.glb> <out prefix> [centre height m] [view width m] [pose,pose,...]

Writes <prefix>_<pose>_<front|back|side>.png. Poses are the simulated ones in `male_check.POSES`, not game animation; dump them to JSON first, because
Blender's Python cannot import that module.
"""
import json
import math
import os
import sys
from pathlib import Path

import bpy
from mathutils import Matrix, Vector

sys.path.insert(0, str(Path(__file__).resolve().parent))

AXES = {"x": Vector((1, 0, 0)), "y": Vector((0, 0, 1)), "z": Vector((0, -1, 0))}  # glb is y-up; Blender is z-up
VIEWS = {"front": ((0, -3), (90, 0, 0)), "back": ((0, 3), (90, 0, 180)), "side": ((3, 0), (90, 0, 90))}
CLOTH_COLOURS = ((0.35, 0.4, 0.5, 1), (0.3, 0.5, 0.4, 1), (0.5, 0.45, 0.3, 1), (0.45, 0.35, 0.5, 1))


def load_poses() -> dict:
    """The pose table, from the JSON file named by RENDER_POSES (Blender's Python cannot import male_check, which needs scipy)."""
    return json.loads(Path(os.environ["RENDER_POSES"]).read_text())


def material_name(obj: bpy.types.Object) -> str:
    slot = obj.material_slots[0] if obj.material_slots else None
    return slot.material.name if slot and slot.material else ""


def paint(meshes: list[bpy.types.Object]) -> None:
    for obj in meshes:
        if material_name(obj).startswith("/mt_c0201b0001_"):
            obj.color = (0, 1, 1, 1)
        else:
            obj.color = CLOTH_COLOURS[(int(obj.name.split()[1].split(".")[0]) - 1) % 4]


def set_pose(armature: bpy.types.Object, spec: list) -> None:
    """Turn each listed bone about its own head, around a world axis, children following."""
    for bone in armature.pose.bones:
        bone.matrix_basis = Matrix.Identity(4)
    bpy.context.view_layer.update()
    for name, axis, degrees in spec:
        bone = armature.pose.bones.get(name)
        if bone is None:
            continue
        head = bone.matrix.translation.copy()
        turn = Matrix.Translation(head) @ Matrix.Rotation(math.radians(degrees), 4, AXES[axis]) @ Matrix.Translation(-head)
        bone.matrix = turn @ bone.matrix
        bpy.context.view_layer.update()


def main() -> None:
    args = sys.argv[sys.argv.index("--") + 1:]
    source, prefix = args[0], args[1]
    centre = float(args[2]) if len(args) > 2 else 1.15
    width = float(args[3]) if len(args) > 3 else 0.9
    wanted = args[4].split(",") if len(args) > 4 else ["stand", "walk", "bend", "arms_up", "arms_forward", "squat", "sit"]
    poses = load_poses()
    poses.setdefault("stand", [])
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=source)
    meshes = [o for o in bpy.data.objects if o.type == "MESH" and o.name.startswith("mesh ")]
    for obj in [o for o in bpy.data.objects if o.type == "MESH" and o not in meshes]:
        bpy.data.objects.remove(obj)
    paint(meshes)
    armature = next(o for o in bpy.data.objects if o.type == "ARMATURE")
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_WORKBENCH"
    scene.display.shading.light = "STUDIO"
    scene.display.shading.color_type = "OBJECT"
    scene.display.shading.show_cavity = True
    scene.render.resolution_x = scene.render.resolution_y = 900
    camera = bpy.data.objects.new("c", bpy.data.cameras.new("c"))
    scene.collection.objects.link(camera)
    scene.camera = camera
    camera.data.type = "ORTHO"
    camera.data.ortho_scale = width
    bpy.context.view_layer.objects.active = armature
    bpy.ops.object.mode_set(mode="POSE")
    for pose in wanted:
        set_pose(armature, poses[pose])
        for view, ((x, y), rotation) in VIEWS.items():
            camera.location = (x, y, centre)
            camera.rotation_euler = tuple(math.radians(a) for a in rotation)
            scene.render.filepath = f"{prefix}_{pose}_{view}.png"
            bpy.ops.render.render(write_still=True)


main()
