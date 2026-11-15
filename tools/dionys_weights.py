"""Copy the skin's bone weights onto cloth that sits close to it, as the outfits made for Dionys do.

    PATH=/usr/bin:/bin blender -b --factory-startup --disable-autoexec -P dionys_weights.py -- <in.glb> <out.glb>

Rules, each from `builds/_dionys/dionys_study_findings.md`:
- Cloth near the body takes the weights of the skin directly under it, physics bones (`iv_`) included.
- The copy fades out with distance, so loose parts (wide sleeves, skirts) keep their own weights. WNEAR=<mm> full copy up to here (12), WFAR=<mm> none past here (30).
- A vertex keeps its share on cloth-only bones (`j_sk_`, `j_ex_`): those drive skirts and flaps the skin does not have.
- Nothing crosses between limbs: if the nearest skin belongs to another body part (arm, leg, torso) than the cloth vertex does, it keeps its own weights.

Opt-in (both off by default, which gives the old output exactly):
- WSAMELIMB=1: a vertex whose nearest skin is on another limb copies from the nearest skin on its own limb instead of
  keeping its own weights, so the copy fades in over distance (WNEAR/WFAR) rather than switching per vertex at a crotch or armpit.
- WBONES=<n>: keep up to n bones per vertex (4); above 4 the glTF export keeps all influences.

Refuses to overwrite an existing output. Prints how many vertices changed and the mean copy strength per cloth mesh.
"""
import os
import re
import sys

import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree
from mathutils.interpolate import poly_3d_calc

SKIN_PREFIX = "/mt_c0201b0001_b"
BODY_PREFIX = "/mt_c0201b0001_"
OWN_BONES = ("j_sk_", "j_ex_")
BONE_LIMIT = int(os.environ.get("WBONES", "4"))
SAME_LIMB = bool(int(os.environ.get("WSAMELIMB", "0")))
NEAR = float(os.environ.get("WNEAR", "12")) / 1000
FAR = float(os.environ.get("WFAR", "30")) / 1000


def material_name(obj: bpy.types.Object) -> str:
    slot = obj.material_slots[0] if obj.material_slots else None
    return slot.material.name if slot and slot.material else ""


def family(bone: str) -> str:
    """Which body part a bone drives."""
    if re.match(r"j_ude|n_hkata|n_hhiji|n_hte|j_te|n_ude", bone):
        return "arm_l" if bone.endswith("_l") else "arm_r"
    if re.match(r"j_asi|n_hizasoubi|iv_daitai|iv_asi", bone):
        return "leg_l" if bone.endswith("_l") else "leg_r"
    return "torso"


def dominant_family(weights: dict[str, float]) -> str:
    totals: dict[str, float] = {}
    for bone, weight in weights.items():
        totals[family(bone)] = totals.get(family(bone), 0.0) + weight
    return max(totals, key=totals.get) if totals else "torso"


def vertex_weights(obj: bpy.types.Object) -> list[dict[str, float]]:
    names = {group.index: group.name for group in obj.vertex_groups}
    return [{names[g.group]: g.weight for g in vertex.groups if g.weight > 0 and g.group in names} for vertex in obj.data.vertices]


def smoothstep(value: float) -> float:
    value = max(0.0, min(1.0, value))
    return value * value * (3 - 2 * value)


def skin_lookup(skin: list[bpy.types.Object]) -> list[tuple]:
    """(tree, triangles, positions, per-vertex weights) for each skin mesh."""
    out = []
    for obj in skin:
        points = [v.co.copy() for v in obj.data.vertices]
        triangles = [tuple(p.vertices) for p in obj.data.polygons]
        out.append((BVHTree.FromPolygons(points, triangles), triangles, points, vertex_weights(obj)))
    return out


def skin_lookup_by_family(skin: list[bpy.types.Object]) -> dict[str, list[tuple]]:
    """skin_lookup, split by the body part (family) each skin triangle mostly belongs to."""
    out: dict[str, list[tuple]] = {}
    for obj in skin:
        points = [v.co.copy() for v in obj.data.vertices]
        weights = vertex_weights(obj)
        by_family: dict[str, list[tuple]] = {}
        for polygon in obj.data.polygons:
            corners = tuple(polygon.vertices)
            mixed: dict[str, float] = {}
            for corner in corners:
                for bone, weight in weights[corner].items():
                    mixed[bone] = mixed.get(bone, 0.0) + weight
            by_family.setdefault(dominant_family(mixed), []).append(corners)
        for name, triangles in by_family.items():
            out.setdefault(name, []).append((BVHTree.FromPolygons(points, triangles), triangles, points, weights))
    return out


def nearest_skin(point: Vector, lookup: list[tuple]) -> tuple[float, dict[str, float]]:
    """(distance, interpolated skin weights) at the closest skin surface."""
    best = None
    for entry in lookup:
        hit = entry[0].find_nearest(point)
        if hit[0] is not None and (best is None or hit[3] < best[0][3]):
            best = (hit, entry)
    hit, (_, triangles, points, weights) = best
    corners = triangles[hit[2]]
    bary = poly_3d_calc([points[i] for i in corners], hit[0])
    mixed: dict[str, float] = {}
    for corner, share in zip(corners, bary):
        for bone, weight in weights[corner].items():
            mixed[bone] = mixed.get(bone, 0.0) + weight * share
    return hit[3], mixed


def blended(own: dict[str, float], skin: dict[str, float], strength: float) -> dict[str, float]:
    """The new weights of a vertex: own and skin mixed, limited to BONE_LIMIT bones, summing to 1."""
    total = sum(own.values()) or 1.0
    own = {bone: weight / total for bone, weight in own.items()}
    kept = sum(weight for bone, weight in own.items() if bone.startswith(OWN_BONES))
    strength *= 1 - kept
    mixed = {bone: weight * (1 - strength) for bone, weight in own.items()}
    for bone, weight in skin.items():
        mixed[bone] = mixed.get(bone, 0.0) + weight * strength
    top = dict(sorted(mixed.items(), key=lambda item: -item[1])[:BONE_LIMIT])
    scale = sum(top.values()) or 1.0
    return {bone: weight / scale for bone, weight in top.items()}


def apply(obj: bpy.types.Object, lookup: list[tuple], armature_bones: set[str], by_family: dict[str, list[tuple]]) -> None:
    own_all = vertex_weights(obj)
    changed, strengths = 0, []
    for vertex, own in zip(obj.data.vertices, own_all):
        distance, skin = nearest_skin(vertex.co, lookup)
        if SAME_LIMB and own and dominant_family(own) != dominant_family(skin) and by_family.get(dominant_family(own)):
            distance, skin = nearest_skin(vertex.co, by_family[dominant_family(own)])
        strength = 1 - smoothstep((distance - NEAR) / (FAR - NEAR))
        if strength <= 0 or not own or dominant_family(own) != dominant_family(skin):
            strengths.append(0.0)
            continue
        new = blended(own, {b: w for b, w in skin.items() if b in armature_bones}, strength)
        strengths.append(strength)
        changed += 1
        for bone in own:
            obj.vertex_groups[bone].remove([vertex.index])
        for bone, weight in new.items():
            group = obj.vertex_groups.get(bone) or obj.vertex_groups.new(name=bone)
            group.add([vertex.index], weight, "REPLACE")
    print(f"{obj.name}: changed {changed}/{len(own_all)} verts, mean copy strength {sum(strengths) / max(len(strengths), 1):.2f}")


def main() -> None:
    args = sys.argv[sys.argv.index("--") + 1:]
    source, out = args[0], args[1]
    if os.path.exists(out):
        sys.exit(f"refusing to overwrite {out}")
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=source)
    armature = next(o for o in bpy.data.objects if o.type == "ARMATURE")
    meshes = [o for o in bpy.data.objects if o.type == "MESH" and not o.name.startswith("Icosphere")]
    skin = [o for o in meshes if material_name(o).startswith(SKIN_PREFIX)]
    lookup = skin_lookup(skin)
    by_family = skin_lookup_by_family(skin) if SAME_LIMB else {}
    if not lookup:
        sys.exit(f"no skin meshes ({SKIN_PREFIX}*) in {source}")
    bones = {bone.name for bone in armature.data.bones}
    for obj in [o for o in meshes if not material_name(o).startswith(BODY_PREFIX)]:
        apply(obj, lookup, bones, by_family)
    extra = {"export_all_influences": True} if BONE_LIMIT > 4 else {}  # the exporter cuts to 4 bones per vertex otherwise
    bpy.ops.export_scene.gltf(filepath=out, export_format="GLB", export_extras=True, **extra)


main()
