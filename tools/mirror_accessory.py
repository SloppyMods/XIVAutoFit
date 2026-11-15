import bpy, sys, os
# usage: blender -b -P mirror_accessory.py -- <in.glb> <Out.glb>
# For a one-sided accessory (e.g. a shoulder/arm piece weighted to the right arm): copies every "mesh G.S" across x=0,
# reverses the faces, swaps the _r bone weights to _l (and vice versa), and joins the copy into the same mesh so the
# model keeps its mesh and material count. No fitting.
argv = sys.argv[sys.argv.index("--") + 1:]
src, out = argv[0], argv[1]
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "builds") + "/"

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=src)

for o in [o for o in bpy.data.objects if o.type == "MESH" and o.name.startswith("Icosphere")]:
    bpy.data.objects.remove(o)

def swap_side(name):
    if name.endswith("_r"): return name[:-2] + "_l"
    if name.endswith("_l"): return name[:-2] + "_r"
    return name

meshes = [o for o in bpy.data.objects if o.type == "MESH" and o.name.startswith("mesh ")]
for o in meshes:
    c = o.copy(); c.data = o.data.copy(); c.name = o.name + "_mir"
    bpy.context.collection.objects.link(c)
    for v in c.data.vertices: v.co.x = -v.co.x            # mirror across the body centre line
    c.data.flip_normals()                                   # a mirror turns faces inside out; flip them back
    # swap each side bone's weights to its opposite: rename the groups on the copy only
    old = [g.name for g in c.vertex_groups]
    for g in c.vertex_groups: g.name = "tmp_" + g.name
    for g in c.vertex_groups: g.name = swap_side(g.name[4:])
    c.data.update()
    bpy.ops.object.select_all(action="DESELECT")
    c.select_set(True); o.select_set(True); bpy.context.view_layer.objects.active = o
    n0 = len(o.data.vertices)
    bpy.ops.object.join()
    print("mirrored", o.name, n0, "->", len(o.data.vertices), "verts")

bpy.ops.export_scene.gltf(filepath=OUT + out, export_format="GLB", export_extras=True)
print("wrote", OUT + out)
