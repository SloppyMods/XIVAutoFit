# usage: blender -b -P armpit_tuck.py -- <in.glb> <out.glb>
# Armpit tuck (post-process, moves hidden Doll skin/joint positions only, never cloth, never weights).
# Pushes the skin and joints covered by the jacket INWARD, so they stay behind the cloth when the arm is raised while the
# cloth, and so the silhouette, does not change at all.  Run it after armpit_wsync.py.  Skin that can be seen at rest
# never moves: every skin/joint point is ray-tested from a sphere of cameras with only the cloth the game shows
# (TVMASK), and the tuck fades in with distance from the nearest visible point.
# The move is a function of position only, so skin/skin and skin/joint vertices that share a position cannot split:
#   direction = -(Doll skin normal around the nearest skin point, Gaussian-averaged over ATR metres)
#   amount    = ATD mm * ramp(|x|) * ramp(z) * ramp(distance to nearest rest-visible point)
# Env (defaults in brackets):
#   ATD     tuck distance, mm [8]
#   ATX     |x| ramp lo,full,full-end,hi [0.05,0.07,0.24,0.27]
#   ATZ     z ramp lo,full,full-end,hi [1.13,1.18,1.36,1.40]
#   ATZNECK z1,z2,x1,x2: near the neck (|x| below x1) the z ramp ends at z1,z2 instead of ATZ's; blended over |x| x1..x2,
#           so visible skin at the base of the neck keeps its shape while the shoulder joint further out is still tucked [off]
#   ATR     skin-normal averaging radius, m [0.025]
#   ATFADE  distance from a rest-visible point over which the tuck fades in, m [0.02]
#   ATCAMS  cameras per visibility sphere; two spheres (2.5 m, 1.2 m), above the floor only [400]
#   ATMINCAM a point counts as visible from this many cameras with a direct view [5]
#   ATDOT   a view is direct when the ray meets the surface at cos(angle) above this; slivers seen edge-on through the
#           few mm between skin and jacket do not count, or nearly all skin under the jacket would freeze [0.25]
#   TVMASK  atr_tv_ letters the game shows, the rest are ignored as cover [a]
#   ATNZ    lo,hi: scale the tuck by a ramp on z of the averaged skin normal (0 at lo, 1 at hi), so skin under the armpit
#           apex (facing down, z about -0.8..-1) stays put; there "inward" points across the crease, not into the body [off]
#   ATDUMP  write the moves to this JSON file (x,y,z -> dx,dy,dz), for checks that need the same vertices before and after
#   ATKEEP  cloth meshes whose buried vertices must stay buried: no tuck within ATFADE of a cloth vertex of these meshes
#           that sits behind the skin at rest and near the rest-visible area, so a jacket edge cannot pop out ["mesh 3.0"]
import bpy, sys, os, math
from mathutils import Vector
from mathutils.bvhtree import BVHTree
from mathutils.kdtree import KDTree
a = sys.argv[sys.argv.index("--") + 1:]
src, out = a[0], a[1]
D = float(os.environ.get("ATD", "8")) / 1000.0
X = [float(v) for v in os.environ.get("ATX", "0.05,0.07,0.24,0.27").split(",")]
Z = [float(v) for v in os.environ.get("ATZ", "1.13,1.18,1.36,1.40").split(",")]
R = float(os.environ.get("ATR", "0.025"))
FADE = float(os.environ.get("ATFADE", "0.02"))
NCAM = int(os.environ.get("ATCAMS", "400"))
MINCAM = int(os.environ.get("ATMINCAM", "5"))
DOT = float(os.environ.get("ATDOT", "0.25"))
NECK = [float(v) for v in os.environ["ATZNECK"].split(",")] if os.environ.get("ATZNECK") else None
NZ = [float(v) for v in os.environ["ATNZ"].split(",")] if os.environ.get("ATNZ") else None
TV = os.environ.get("TVMASK", "a")
KEEP = [x for x in os.environ.get("ATKEEP", "mesh 3.0").split(",") if x]
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=src)
def mat(o): return o.material_slots[0].material.name if o.material_slots and o.material_slots[0].material else ""
def kind(o):
    m = mat(o)
    return "joint" if "DOLL" in m else ("skin" if "b0001" in m else "cloth")
meshes = [o for o in bpy.data.objects if o.type == "MESH" and o.name.startswith("mesh ")]
shown = [o for o in meshes if all(not k.startswith("atr_tv_") or k[-1] in TV for k in o.keys())]
under = [o for o in meshes if kind(o) != "cloth"]
skin = [o for o in meshes if kind(o) == "skin"]
def ss(t): t = min(1.0, max(0.0, t)); return t * t * (3 - 2 * t)
def ramp(v, lo, f0, f1, hi):
    if v <= lo or v >= hi: return 0.0
    if v < f0: return ss((v - lo) / (f0 - lo))
    if v > f1: return ss((hi - v) / (hi - f1))
    return 1.0
def build(objs):
    vs, fs = [], []
    for o in objs:
        off = len(vs); mw = o.matrix_world
        vs += [mw @ v.co for v in o.data.vertices]
        fs += [[off + i for i in p.vertices] for p in o.data.polygons]
    return vs, BVHTree.FromPolygons(vs, fs)
_, bvh_shown = build(shown)
sv, bvh_skin = build(skin)
sn = []
for o in skin:
    m3 = o.matrix_world.to_3x3()
    sn += [(m3 @ v.normal).normalized() for v in o.data.vertices]
kd = KDTree(len(sv))
for i, c in enumerate(sv): kd.insert(c, i)
kd.balance()
def key(c): return (round(c.x, 6), round(c.y, 6), round(c.z, 6))
def zramp(c):
    t = ramp(c.z, *Z)
    if NECK:
        w = ss((abs(c.x) - NECK[2]) / (NECK[3] - NECK[2]))
        t = w * t + (1 - w) * ramp(c.z, Z[0], Z[1], NECK[0], NECK[1])
    return t
# visibility spheres (Fibonacci) around the chest, floor at z 0: the near one looks up at the armpit from below
cams = []
for rad in (2.5, 1.2):
    for i in range(NCAM):
        zz = 1 - 2 * (i + 0.5) / NCAM; r = math.sqrt(max(0, 1 - zz * zz)); ph = i * math.pi * (3 - math.sqrt(5))
        c = Vector((0, 0, 1.2)) + Vector((r * math.cos(ph), r * math.sin(ph), zz)) * rad
        if c.z >= 0.1: cams.append(c)
def visible(c, n):
    seen = 0
    for org in cams:
        d = c - org; L = d.length; d /= L
        if abs(d.dot(n)) < DOT: continue
        loc, _, _, dist = bvh_shown.ray_cast(org, d, L + 0.001)
        if loc is None or dist >= L - 0.0008:
            seen += 1
            if seen >= MINCAM: return True
    return False
pts = {}
for o in under:
    mw = o.matrix_world; m3 = mw.to_3x3()
    for v in o.data.vertices:
        c = mw @ v.co
        # test a margin around the box too, so visible skin just outside it still fades the tuck
        if X[0] - FADE < abs(c.x) < X[3] + FADE and Z[0] - FADE < c.z < Z[3] + FADE:
            k = key(c)
            if k not in pts: pts[k] = (c, (m3 @ v.normal).normalized())
print(f"attuck visibility test: {len(pts)} points, {len(cams)} cameras", flush=True)
vis = [c for c, n in pts.values() if visible(c, n)]
print(f"attuck rest-visible points: {len(vis)}", flush=True)
# jacket vertices buried behind the skin at rest, next to the visible area: leave the skin over them alone
buried = []
for o in meshes:
    if o.name not in KEEP: continue
    mw = o.matrix_world
    for v in o.data.vertices:
        c = mw @ v.co
        if not (abs(c.x) < X[3] and Z[0] < c.z < Z[3]): continue
        loc, nor, _, dist = bvh_skin.find_nearest(c)
        if loc is not None and (c - loc).dot(nor) < 0 and abs(c.x) < X[1]:
            buried.append(c)
print(f"attuck buried front-edge cloth verts kept: {len(buried)}", flush=True)
frozen = vis + buried
kf = KDTree(max(1, len(frozen)))
for i, c in enumerate(frozen): kf.insert(c, i)
kf.balance()
def move_at(c):
    t = ramp(abs(c.x), *X) * zramp(c)
    if t <= 0: return None
    if frozen:
        _, _, df = kf.find(c)
        t *= ss(df / FADE)
    if t <= 0: return None
    loc, nor, _, _ = bvh_skin.find_nearest(c)
    acc = Vector()
    for _, i, d in kd.find_range(loc, R):
        acc += sn[i] * math.exp(-(d / (R / 2)) ** 2)
    if acc.length < 1e-9: acc = nor.copy()
    acc.normalize()
    if NZ: t *= ss((acc.z - NZ[0]) / (NZ[1] - NZ[0]))
    if t <= 0: return None
    return acc * (-D * t)
cache = {}
stats = []
for o in under:
    mw = o.matrix_world; m3i = mw.inverted().to_3x3()
    keys = o.data.shape_keys.key_blocks if o.data.shape_keys else []
    n = 0; mx = 0.0
    for v in o.data.vertices:
        c = mw @ v.co
        k = key(c)
        if k not in cache: cache[k] = move_at(c)
        mv = cache[k]
        if mv is None: continue
        dl = m3i @ mv
        v.co += dl
        for kb in keys: kb.data[v.index].co += dl
        n += 1; mx = max(mx, mv.length); stats.append(mv.length * 1000)
    if n: print(f"attuck {o.name} moved={n} max={mx * 1000:.2f}mm")
if os.environ.get("ATDUMP"):
    import json
    json.dump([[*k, *v] for k, v in cache.items() if v is not None], open(os.environ["ATDUMP"], "w"))
stats.sort()
if stats:
    print(f"attuck all moved={len(stats)} median={stats[len(stats) // 2]:.2f}mm max={stats[-1]:.2f}mm")
bpy.ops.export_scene.gltf(filepath=out, export_format="GLB", export_extras=True)
print("wrote", out)
