"""Blender script: render bodies in Cycles with a tangent-space normal map on a plain clay colour, front and back, to check bumps.

    blender --factory-startup --disable-autoexec -b -t 3 -P render_normal.py -- <prefix> <height> <centre y> <normal.png> <body.mdl> [more .mdl]

RENDER_SIZE and RENDER_X work as in render_tattoo.py. The normal PNG must already use Blender's direction: green high points up the image.
"""
import math
import os
import sys
from pathlib import Path

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parent))
import render_tattoo as rt  # noqa: E402

SAMPLES = int(os.environ.get("RENDER_SAMPLES", "24"))


def clay(normal_path: str) -> bpy.types.Material:
    material = bpy.data.materials.new("clay")
    material.use_nodes = True
    tree = material.node_tree
    bsdf = tree.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = (0.62, 0.62, 0.62, 1)
    bsdf.inputs["Roughness"].default_value = 0.65
    image = tree.nodes.new("ShaderNodeTexImage")
    image.image = bpy.data.images.load(normal_path)
    image.image.colorspace_settings.name = "Non-Color"
    node = tree.nodes.new("ShaderNodeNormalMap")
    node.space = "TANGENT"
    node.uv_map = "uv"
    tree.links.new(image.outputs["Color"], node.inputs["Color"])
    tree.links.new(node.outputs["Normal"], bsdf.inputs["Normal"])
    return material


def light(angle_x: float, angle_y: float, strength: float) -> None:
    sun = bpy.data.lights.new("sun", "SUN")
    sun.energy = strength
    node = bpy.data.objects.new("sun", sun)
    node.rotation_euler = (angle_x, angle_y, 0)
    bpy.context.scene.collection.objects.link(node)


def main() -> None:
    args = sys.argv[sys.argv.index("--") + 1:]
    prefix, height, centre, normal_path, models = args[0], float(args[1]), float(args[2]), args[3], args[4:]
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = SAMPLES
    scene.cycles.use_denoising = False
    world = bpy.data.worlds.new("world")
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs[0].default_value = (0.25, 0.25, 0.28, 1)
    world.node_tree.nodes["Background"].inputs[1].default_value = 0.35
    scene.world = world
    material = clay(normal_path)
    for path in models:
        rt.add_body(path, material)
    light(math.radians(105), math.radians(38), 3.0)
    light(math.radians(255), math.radians(-30), 1.0)
    scene.render.resolution_x = rt.SIZE
    scene.render.resolution_y = rt.SIZE
    camera = bpy.data.objects.new("camera", bpy.data.cameras.new("camera"))
    scene.collection.objects.link(camera)
    scene.camera = camera
    camera.data.type = "ORTHO"
    camera.data.ortho_scale = height
    for name, y, angle in (("front", -4.0, 0.0), ("back", 4.0, math.pi)):
        camera.location = (rt.CENTRE_X, y, centre)
        camera.rotation_euler = (math.pi / 2, 0.0, angle)
        scene.render.filepath = f"{prefix}_{name}.png"
        bpy.ops.render.render(write_still=True)


if __name__ == "__main__":
    main()
