"""Blender script: render a body with a flat texture on it, front and back, so a texture can be checked by eye.

    blender --factory-startup --disable-autoexec -b -P render_tattoo.py -- <prefix> <height> <centre y> <texture.png> <body.mdl> [more .mdl]

Writes <prefix>_front.png and <prefix>_back.png. Only meshes using the bare-skin material are drawn; V is flipped for Blender.
"""
import math
import os
import sys
from pathlib import Path

import bpy
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import mdl_read  # noqa: E402

SKIN_MATERIAL = "b0001_b."
SIZE = int(os.environ.get("RENDER_SIZE", "1100"))
CENTRE_X = float(os.environ.get("RENDER_X", "0"))  # game x of the view centre, for close-ups of a hand


def add_body(path: str, material: bpy.types.Material) -> None:
    """Make one Blender mesh per skin mesh in the .mdl, in game axes turned to Blender's Z up."""
    for index, mesh in enumerate(mdl_read.read_mdl(path).meshes):
        if SKIN_MATERIAL not in mesh.material:
            continue
        data = bpy.data.meshes.new(f"{Path(path).stem}_{index}")
        points = np.c_[mesh.positions[:, 0], -mesh.positions[:, 2], mesh.positions[:, 1]]
        data.from_pydata(points.tolist(), [], mesh.triangles.tolist())
        layer = data.uv_layers.new(name="uv")
        loops = mesh.triangles.ravel()
        uv = np.c_[mesh.uv[loops, 0], 1.0 - mesh.uv[loops, 1]]
        layer.data.foreach_set("uv", uv.ravel())
        data.materials.append(material)
        data.update()
        for polygon in data.polygons:
            polygon.use_smooth = True
        node = bpy.data.objects.new(data.name, data)
        bpy.context.scene.collection.objects.link(node)


def textured(path: str) -> bpy.types.Material:
    material = bpy.data.materials.new("skin")
    material.use_nodes = True
    tree = material.node_tree
    image = tree.nodes.new("ShaderNodeTexImage")
    image.image = bpy.data.images.load(path)
    image.image.colorspace_settings.name = "sRGB"
    tree.links.new(image.outputs["Color"], tree.nodes["Principled BSDF"].inputs["Base Color"])
    return material


def main() -> None:
    args = sys.argv[sys.argv.index("--") + 1:]
    prefix, height, centre, texture, models = args[0], float(args[1]), float(args[2]), args[3], args[4:]
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    material = textured(texture)
    for path in models:
        add_body(path, material)
    scene.render.engine = "BLENDER_WORKBENCH"
    scene.display.shading.light = "STUDIO"
    scene.display.shading.color_type = "TEXTURE"
    scene.display.shading.show_backface_culling = True
    scene.render.resolution_x = SIZE
    scene.render.resolution_y = SIZE
    camera = bpy.data.objects.new("camera", bpy.data.cameras.new("camera"))
    scene.collection.objects.link(camera)
    scene.camera = camera
    camera.data.type = "ORTHO"
    camera.data.ortho_scale = height
    for name, y, angle in (("front", -4.0, 0.0), ("back", 4.0, math.pi)):
        camera.location = (CENTRE_X, y, centre)
        camera.rotation_euler = (math.pi / 2, 0.0, angle)
        scene.render.filepath = f"{prefix}_{name}.png"
        bpy.ops.render.render(write_still=True)


if __name__ == "__main__":
    main()
