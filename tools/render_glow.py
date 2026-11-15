"""Blender script: render a body with skin colour, normal map and glow together, to check a glow tattoo by eye before going in game.

    blender --factory-startup --disable-autoexec -b -t 4 -P render_glow.py -- <prefix> <view height> <centre y> <diffuse.png> <normal.png> <body.mdl> [more .mdl]

The normal PNG is the game's normal map as is: red/green = direction (green high points up the image, which is also Blender's
convention), alpha = glow mask. Its alpha is read as data, never as transparency, so the directions under a zero alpha survive.
Glow = EMISSIVE colour x alpha x GLOW_STRENGTH (an approximation of skin.shpk's emissive, not the game's exact curve).
Environment: RENDER_SIZE (px, default 900), RENDER_X (game x of the view centre), RENDER_VIEWS (front,back), SKIN_MATCH
(substring of the skin material name, default b0001_bibo.mtrl), EMISSIVE (r,g,b, default 0.2,0.7,0.5), GLOW_STRENGTH (default 1.5),
RENDER_SAMPLES (default 24). Writes <prefix>_<view>.png. V is flipped for Blender, as in render_tattoo.py.
"""
import math
import os
import sys
from pathlib import Path

import bpy
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import mdl_read  # noqa: E402

SIZE = int(os.environ.get("RENDER_SIZE", "900"))
CENTRE_X = float(os.environ.get("RENDER_X", "0"))
VIEWS = os.environ.get("RENDER_VIEWS", "front").split(",")
SKIN_MATCH = os.environ.get("SKIN_MATCH", "b0001_bibo.mtrl")
EMISSIVE = tuple(float(v) for v in os.environ.get("EMISSIVE", "0.2,0.7,0.5").split(","))
GLOW_STRENGTH = float(os.environ.get("GLOW_STRENGTH", "1.5"))
SAMPLES = int(os.environ.get("RENDER_SAMPLES", "24"))
CAMERAS = {"front": (-4.0, 0.0), "back": (4.0, math.pi)}


def add_body(path: str, material: bpy.types.Material) -> None:
    """One Blender mesh per skin mesh in the .mdl, game axes turned to Blender's Z up."""
    for index, mesh in enumerate(mdl_read.read_mdl(path).meshes):
        if SKIN_MATCH not in mesh.material:
            continue
        data = bpy.data.meshes.new(f"{Path(path).stem}_{index}")
        points = np.c_[mesh.positions[:, 0], -mesh.positions[:, 2], mesh.positions[:, 1]]
        data.from_pydata(points.tolist(), [], mesh.triangles.tolist())
        layer = data.uv_layers.new(name="uv")
        loops = mesh.triangles.ravel()
        layer.data.foreach_set("uv", np.c_[mesh.uv[loops, 0], 1.0 - mesh.uv[loops, 1]].ravel())
        data.materials.append(material)
        data.update()
        for polygon in data.polygons:
            polygon.use_smooth = True
        node = bpy.data.objects.new(data.name, data)
        bpy.context.scene.collection.objects.link(node)


def skin(diffuse_path: str, normal_path: str) -> bpy.types.Material:
    material = bpy.data.materials.new("skin")
    material.use_nodes = True
    tree = material.node_tree
    bsdf = tree.nodes["Principled BSDF"]
    bsdf.inputs["Roughness"].default_value = 0.55
    colour = tree.nodes.new("ShaderNodeTexImage")
    colour.image = bpy.data.images.load(diffuse_path)
    colour.image.colorspace_settings.name = "sRGB"
    tree.links.new(colour.outputs["Color"], bsdf.inputs["Base Color"])
    normal = tree.nodes.new("ShaderNodeTexImage")
    normal.image = bpy.data.images.load(normal_path)
    normal.image.colorspace_settings.name = "Non-Color"
    normal.image.alpha_mode = "CHANNEL_PACKED"  # alpha is the glow mask, not transparency
    mapping = tree.nodes.new("ShaderNodeNormalMap")
    mapping.space = "TANGENT"
    mapping.uv_map = "uv"
    tree.links.new(normal.outputs["Color"], mapping.inputs["Color"])
    tree.links.new(mapping.outputs["Normal"], bsdf.inputs["Normal"])
    bsdf.inputs["Emission Color"].default_value = (*EMISSIVE, 1)
    strength = tree.nodes.new("ShaderNodeMath")
    strength.operation = "MULTIPLY"
    strength.inputs[1].default_value = GLOW_STRENGTH
    tree.links.new(normal.outputs["Alpha"], strength.inputs[0])
    tree.links.new(strength.outputs["Value"], bsdf.inputs["Emission Strength"])
    return material


def sun(angle_x: float, angle_y: float, strength: float) -> None:
    light = bpy.data.lights.new("sun", "SUN")
    light.energy = strength
    node = bpy.data.objects.new("sun", light)
    node.rotation_euler = (angle_x, angle_y, 0)
    bpy.context.scene.collection.objects.link(node)


def main() -> None:
    args = sys.argv[sys.argv.index("--") + 1:]
    prefix, height, centre, diffuse, normal, models = args[0], float(args[1]), float(args[2]), args[3], args[4], args[5:]
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = SAMPLES
    scene.cycles.use_denoising = False
    world = bpy.data.worlds.new("world")
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs[0].default_value = (0.2, 0.2, 0.22, 1)
    world.node_tree.nodes["Background"].inputs[1].default_value = 0.4
    scene.world = world
    material = skin(diffuse, normal)
    for path in models:
        add_body(path, material)
    sun(math.radians(105), math.radians(38), 3.0)  # raking key light from the upper side, so muscles and bumps show
    sun(math.radians(255), math.radians(-30), 0.8)
    scene.render.resolution_x = SIZE
    scene.render.resolution_y = SIZE
    camera = bpy.data.objects.new("camera", bpy.data.cameras.new("camera"))
    scene.collection.objects.link(camera)
    scene.camera = camera
    camera.data.type = "ORTHO"
    camera.data.ortho_scale = height
    for name in VIEWS:
        y, angle = CAMERAS[name]
        camera.location = (CENTRE_X, y, centre)
        camera.rotation_euler = (math.pi / 2, 0.0, angle)
        scene.render.filepath = f"{prefix}_{name}.png"
        bpy.ops.render.render(write_still=True)


if __name__ == "__main__":
    main()
