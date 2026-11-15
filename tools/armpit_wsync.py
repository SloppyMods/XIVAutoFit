# usage: blender -b -P armpit_wsync.py -- <in.glb> <out.glb>
# Armpit weight sync (post-process, changes bone weights only, never positions, never the cloth).
# Doll skin (mesh 0.*) and Doll joints (DOLL material) under the armpit/side/shoulder get the bone weights of the cloth
# surface right over them (nearest cloth triangle, corners blended barycentrically, top 4 bones, normalised), so in any
# pose they move with the jacket instead of sliding out through it.  Weights are faded in by position only, so
# vertices that share a position (skin/joint seams) keep identical weights and cannot split.
# Env (defaults in brackets):
#   AWSRC   cloth meshes to copy from ["mesh 3.0"]  (only cloth the game shows; e6120 Normal/No Panty = atr_tv_a)
#   AWX     |x| fade-in start,full,full-end,fade-out end [0.09,0.12,0.21,0.24]   (keeps off the open chest |x|<0.09)
#   AWZ     z  fade-in start,full,full-end,fade-out end  [1.12,1.15,1.42,1.45]
#   AWD     cloth distance full,zero (m) [0.025,0.04]
import bpy, sys, os
from mathutils.bvhtree import BVHTree
a = sys.argv[sys.argv.index("--") + 1:]
src, out = a[0], a[1]
SRC = [x for x in os.environ.get("AWSRC", "mesh 3.0").split(",") if x]
X = [float(v) for v in os.environ.get("AWX", "0.09,0.12,0.21,0.24").split(",")]
Z = [float(v) for v in os.environ.get("AWZ", "1.12,1.15,1.42,1.45").split(",")]
D = [float(v) for v in os.environ.get("AWD", "0.025,0.04").split(",")]
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=src)
def mat(o): return o.material_slots[0].material.name if o.material_slots and o.material_slots[0].material else ""
meshes = [o for o in bpy.data.objects if o.type == "MESH" and o.name.startswith("mesh ")]
cloth = [o for o in meshes if o.name in SRC]
under = [o for o in meshes if "DOLL" in mat(o) or (o.name.startswith("mesh 0.") and "b0001" in mat(o))]
assert cloth, "no source cloth"
def ramp(v, lo, f0, f1, hi):
    if v <= lo or v >= hi: return 0.0
    if v < f0: return (v - lo) / (f0 - lo)
    if v > f1: return (hi - v) / (hi - f1)
    return 1.0
tv, tf, own = [], [], []
for c in cloth:
    base = len(tv); mw = c.matrix_world
    tv += [mw @ v.co for v in c.data.vertices]
    for p in c.data.polygons:
        for t in range(1, len(p.vertices) - 1):
            tf.append((base + p.vertices[0], base + p.vertices[t], base + p.vertices[t + 1]))
            own.append((c, p.vertices[0], p.vertices[t], p.vertices[t + 1]))
bvh = BVHTree.FromPolygons(tv, tf)
def corner(c, i):
    gn = c.vertex_groups
    return [(gn[g.group].name, g.weight) for g in c.data.vertices[i].groups if g.weight > 0]
# Nearest cloth point only (a function of position).  Taking the cloth along each vertex normal instead was tried
# and rejected: skin and joint vertices that share a position have different normals, got different weights and the
# skin/joint seams opened up to 24 mm in a raised-arm pose.
def cloth_weights(co):
    loc, _, fi, dist = bvh.find_nearest(co)
    if loc is None: return None, 9
    c, i0, i1, i2 = own[fi]; A, B, C = (tv[k] for k in tf[fi])
    v0, v1, v2 = B - A, C - A, loc - A
    d00, d01, d11, d20, d21 = v0.dot(v0), v0.dot(v1), v1.dot(v1), v2.dot(v0), v2.dot(v1)
    den = (d00 * d11 - d01 * d01) or 1e-12
    u1 = (d11 * d20 - d01 * d21) / den; u2 = (d00 * d21 - d01 * d20) / den
    mix = {}
    for share, ci in ((1 - u1 - u2, i0), (u1, i1), (u2, i2)):
        for n, w in corner(c, ci): mix[n] = mix.get(n, 0) + max(share, 0) * w
    return mix, dist
for o in under:
    gn = {g.index: g.name for g in o.vertex_groups}
    n_full = n_part = 0; maxd = 0.0
    for v in o.data.vertices:
        co = o.matrix_world @ v.co
        t = ramp(abs(co.x), *X) * ramp(co.z, *Z)
        if t <= 0: continue
        mix, dist = cloth_weights(co)
        if mix is None: continue
        t *= 1.0 if dist <= D[0] else max(0.0, (D[1] - dist) / (D[1] - D[0]))
        if t <= 0: continue
        own_w = {gn[g.group]: g.weight for g in v.groups if g.weight > 0}
        new = {}
        for n in set(own_w) | set(mix):
            new[n] = (1 - t) * own_w.get(n, 0) + t * mix.get(n, 0)
        top = sorted(new.items(), key=lambda x: -x[1])[:4]          # the game keeps 4 bones per vertex
        s = sum(w for _, w in top) or 1
        top = [(n, w / s) for n, w in top if w / s > 1e-4]
        maxd = max(maxd, sum(abs(dict(top).get(n, 0) - own_w.get(n, 0)) for n in set(own_w) | set(dict(top))))
        for g in list(v.groups): o.vertex_groups[g.group].remove([v.index])
        for n, w in top:
            vg = o.vertex_groups.get(n) or o.vertex_groups.new(name=n)
            vg.add([v.index], w, "REPLACE")
        if t >= 0.999: n_full += 1
        else: n_part += 1
    if n_full or n_part:
        print(f"awsync {o.name} full={n_full} faded={n_part} max_weight_change(L1)={maxd:.2f}")
bpy.ops.export_scene.gltf(filepath=out, export_format="GLB", export_extras=True)
print("wrote", out)
