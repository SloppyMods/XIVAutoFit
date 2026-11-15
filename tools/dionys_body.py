"""Write the Dionys AFAB "Gen Doll" body as reference .glb files, one per slot, with no piercings, no overlays, no underwear and no nails.

Run on the devkit, in Blender, with auto-run scripts off (the .blend is a download). Name each slot you want (top, dwn, glv, sho):

    PATH=/usr/bin:/bin blender -b --factory-startup --disable-autoexec <Dionys_Devkit.blend> -P dionys_body.py -- <out dir> top=<mod top.mdl> dwn=<mod dwn.mdl>

Output: <out dir>/dionys_<slot>.glb. Each holds the skin as `mesh 0.N` on `/mt_c0201b0001_bibo.mtrl`, so
`transplant_body.py` accepts them as the body and keeps the Dionys material and UVs.

The devkit is saved with the mod's real leg size (Medium 1, Small 0.4) and Gen Doll on, and those values are read from the file, not set here.
The script stops if they ever differ. Modifiers are evaluated so the weights and normals the devkit transfers onto each part are kept, except the
Armature modifier, which is switched off so nothing is posed. The `atr_` tags that tell the game when to hide a piece come from the mod's own models
(the part number in each devkit object name is its submesh number there).
"""
import os
import re
import sys
from pathlib import Path

import bpy
from mathutils import Matrix

sys.path.insert(0, str(Path(__file__).resolve().parent))

SKIN_MATERIAL = "/mt_c0201b0001_bibo.mtrl"
ARMATURE_NAME = "Armature IVCS2.0"
EXPECTED_KEYS = {"Medium": 1.0, "Small": 0.4, "Gen Doll": 1.0}
TOP_PARTS = ("Dionys Torso Part 0.0", "Dionys Wrists Part 0.1", "Dionys Neck Part 0.2", "Dionys Elbows Part 0.3", "Dionys Neck Connector Part 0.4")
DWN_PARTS = ("Dionys Butt Part 0.0", "Dionys Knee Part 0.1", "Dionys Shins Part 0.2", "Dionys Ankle Connector Part 0.3")
SLOTS = {"top": TOP_PARTS, "dwn": DWN_PARTS, "glv": ("Dionys Hands Part 0.0", "Dionys Wrist Connector Part 0.1"), "sho": ("Dionys Foot Part 0.0",)}


def check_saved_shape(obj: bpy.types.Object) -> None:
    """Refuse a devkit whose saved shape is not the mod's size with Gen Doll: every number here depends on it."""
    if not obj.data.shape_keys:
        return
    for key in obj.data.shape_keys.key_blocks:
        if key.name in EXPECTED_KEYS and abs(key.value - EXPECTED_KEYS[key.name]) > 1e-4:
            sys.exit(f"{obj.name}: key {key.name} is {key.value}, expected {EXPECTED_KEYS[key.name]}")
        if key.name in ("Gen B", "Gen C") and key.value > 1e-4 and not key.mute:
            sys.exit(f"{obj.name}: key {key.name} is active, expected off")


def baked_copy(source: bpy.types.Object, graph: bpy.types.Depsgraph, name: str, tags: tuple[str, ...], armature: bpy.types.Object, material: bpy.types.Material) -> bpy.types.Object:
    """A new object holding the part's evaluated shape in world space, with its bone weights, bound to the armature."""
    evaluated = source.evaluated_get(graph)
    mesh = bpy.data.meshes.new_from_object(evaluated, preserve_all_data_layers=True, depsgraph=graph)
    mesh.transform(source.matrix_world)
    mesh.materials.clear()
    mesh.materials.append(material)
    target = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(target)
    for group in evaluated.vertex_groups:
        target.vertex_groups.new(name=group.name)
    target.parent = armature
    target.matrix_parent_inverse = Matrix.Identity(4)
    target.modifiers.new("Armature", "ARMATURE").object = armature
    for tag in tags:
        target[tag] = True
    return target


def export(objects: list[bpy.types.Object], armature: bpy.types.Object, path: str) -> None:
    """Export only the given meshes and the armature."""
    bpy.ops.object.select_all(action="DESELECT")
    for obj in [*objects, armature]:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = armature
    bpy.ops.export_scene.gltf(filepath=path, export_format="GLB", use_selection=True, export_extras=True, export_skins=True, export_morph=False)


def main() -> None:
    from mdl_read import read_mdl

    args = sys.argv[sys.argv.index("--") + 1:]
    out_dir = args[0]
    models = dict(arg.split("=", 1) for arg in args[1:])  # slot=path of the mod's .mdl for that slot
    armature = bpy.data.objects[ARMATURE_NAME]
    armature.hide_set(False)
    armature.hide_viewport = False
    for collection in bpy.data.collections:
        collection.hide_viewport = False
    material = bpy.data.materials[SKIN_MATERIAL]  # the devkit's own: a new one would come out named .001 or .002
    for slot in models:  # one evaluation for every part, because each new evaluation of this scene takes about a minute
        for part in SLOTS[slot]:
            check_saved_shape(bpy.data.objects[part])
            for modifier in bpy.data.objects[part].modifiers:
                if modifier.type == "ARMATURE":
                    modifier.show_viewport = False
    graph = bpy.context.evaluated_depsgraph_get()
    for slot, mdl in models.items():
        submeshes = read_mdl(mdl).meshes[0].submeshes
        made = []
        for part in SLOTS[slot]:
            sub = int(re.search(r"Part 0\.(\d+)$", part).group(1))
            tags = tuple(t for t in submeshes[sub][2] if t.startswith("atr_"))
            made.append(baked_copy(bpy.data.objects[part], graph, f"mesh 0.{sub}", tags, armature, material))
            print(part, "->", made[-1].name, len(made[-1].data.vertices), "tags", tags)
        export(made, armature, os.path.join(out_dir, f"dionys_{slot}.glb"))
        for obj in made:  # free the names, or the next slot's "mesh 0.0" comes out as "mesh 0.005"
            bpy.data.objects.remove(obj)


main()
