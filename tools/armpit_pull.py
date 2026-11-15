# usage: blender -b -P armpit_pull.py -- <in.glb> <out.glb>
# Armpit pull (post-process, moves cloth positions only, never weights, never skin/joints).
# Pushes the jacket cloth under the arm OUTWARD, away from the Doll skin, so the skin/joint under the armpit stays
# behind the cloth when the arm is raised.  Run it after armpit_wsync.py (weights first, then the pull).
# The move is a function of position only:
#   direction = Doll skin (mesh 0.*) normal around the nearest skin point, Gaussian-averaged over APR metres
#   amount    = APD mm * ramp(|x|) * ramp(z)   (smoothstep ramps, so no step or crease)
# so vertices that share a position (seams between jacket pieces) get the identical move and cannot tear, and every
# layer/piece at a place moves by the same amount, which keeps layer order and spacing.
# Env (defaults in brackets):
#   APMESH  cloth meshes to move ["mesh 3.0,mesh 5.0"]   (all cloth layers in the region; skin/joints never move)
#   APD     push distance, mm [6]
#   APX     |x| ramp lo,full,full-end,hi [0.12,0.15,0.22,0.26]   (0 at |x|<=0.12 keeps the chest panel unchanged)
#   APZ     z ramp lo,full,full-end,hi [1.18,1.23,1.33,1.38]
#   APR     skin-normal averaging radius, m [0.025]
#   APMAXD  only move cloth within this distance of the skin, m, faded over the last third [0.06]
#   APNX    lo,hi: also scale the move by a ramp on |x| of the averaged skin normal, so only cloth over skin that
#           faces sideways moves and the front-facing chest panel (normal toward -y) stays put [off]
#   APNZ    lo,hi: also scale the move by a ramp on z of the averaged skin normal (0 at lo, 1 at hi), so the cloth
#           under the armpit apex (skin facing down, z about -0.8..-1) stays put [off]
#   APPANEL xmax,fade: hard keep-out for the front chest panel: no move where |x| < xmax and y < 0, faded in over
#           `fade` metres in |x| or y outside it (move = 0 inside, exactly) [off]
#   APLAT   xmax,fade: softer chest-panel rule: where |x| < xmax and y < 0 drop the front/back (y) part of the move,
#           so cloth there only moves sideways/up-down and the chest does not stand further forward; faded over
#           `fade` metres outside it [off]
import bpy, sys, os, math
from mathutils import Vector
from mathutils.bvhtree import BVHTree
from mathutils.kdtree import KDTree
a = sys.argv[sys.argv.index("--") + 1:]
src, out = a[0], a[1]
MESH = [x for x in os.environ.get("APMESH", "mesh 3.0,mesh 5.0").split(",") if x]
D = float(os.environ.get("APD", "6")) / 1000.0
X = [float(v) for v in os.environ.get("APX", "0.12,0.15,0.22,0.26").split(",")]
Z = [float(v) for v in os.environ.get("APZ", "1.18,1.23,1.33,1.38").split(",")]
R = float(os.environ.get("APR", "0.025"))
MAXD = float(os.environ.get("APMAXD", "0.06"))
NX = [float(v) for v in os.environ["APNX"].split(",")] if os.environ.get("APNX") else None
NZ = [float(v) for v in os.environ["APNZ"].split(",")] if os.environ.get("APNZ") else None
PANEL = [float(v) for v in os.environ["APPANEL"].split(",")] if os.environ.get("APPANEL") else None
LAT = [float(v) for v in os.environ["APLAT"].split(",")] if os.environ.get("APLAT") else None
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=src)
def mat(o): return o.material_slots[0].material.name if o.material_slots and o.material_slots[0].material else ""
meshes = [o for o in bpy.data.objects if o.type == "MESH" and o.name.startswith("mesh ")]
skin = [o for o in meshes if o.name.startswith("mesh 0.") and "b0001" in mat(o) and "DOLL" not in mat(o)]
cloth = [o for o in meshes if o.name in MESH]
assert skin and cloth, "need skin mesh 0.* and APMESH cloth"
def ss(t): t = min(1.0, max(0.0, t)); return t * t * (3 - 2 * t)
def ramp(v, lo, f0, f1, hi):
    if v <= lo or v >= hi: return 0.0
    if v < f0: return ss((v - lo) / (f0 - lo))
    if v > f1: return ss((hi - v) / (hi - f1))
    return 1.0
sv, sf, sn = [], [], []
for o in skin:
    off = len(sv); mw = o.matrix_world; m3 = mw.to_3x3()
    sv += [mw @ v.co for v in o.data.vertices]
    sn += [(m3 @ v.normal).normalized() for v in o.data.vertices]
    sf += [[off + i for i in p.vertices] for p in o.data.polygons]
bvh = BVHTree.FromPolygons(sv, sf)
kd = KDTree(len(sv))
for i, c in enumerate(sv): kd.insert(c, i)
kd.balance()
def move_at(c):
    t = ramp(abs(c.x), *X) * ramp(c.z, *Z)
    if PANEL: t *= max(ss((abs(c.x) - PANEL[0]) / PANEL[1]), ss(c.y / PANEL[1]))
    if t <= 0: return None
    loc, nor, fi, dist = bvh.find_nearest(c)
    if loc is None or dist > MAXD: return None
    t *= ss((MAXD - dist) / (MAXD / 3))
    if t <= 0: return None
    acc = Vector()
    for co, i, d in kd.find_range(loc, R):
        acc += sn[i] * math.exp(-(d / (R / 2)) ** 2)
    if acc.length < 1e-9: acc = nor.copy()
    acc.normalize()
    if NX: t *= ss((abs(acc.x) - NX[0]) / (NX[1] - NX[0]))
    if NZ: t *= ss((acc.z - NZ[0]) / (NZ[1] - NZ[0]))
    if t <= 0: return None
    mv = acc * (D * t)
    if LAT: mv.y *= max(ss((abs(c.x) - LAT[0]) / LAT[1]), ss(c.y / LAT[1]))
    return mv
cache = {}
stats = []
for o in cloth:
    mw = o.matrix_world; mi = mw.inverted(); m3i = mi.to_3x3()
    keys = o.data.shape_keys.key_blocks if o.data.shape_keys else []
    n = 0; mx = 0.0
    for v in o.data.vertices:
        c = mw @ v.co
        k = (round(c.x, 6), round(c.y, 6), round(c.z, 6))
        if k not in cache: cache[k] = move_at(c)
        mv = cache[k]
        if mv is None: continue
        dl = m3i @ mv
        v.co += dl
        for kb in keys: kb.data[v.index].co += dl
        n += 1; mx = max(mx, mv.length); stats.append(mv.length * 1000)
    print(f"appull {o.name} moved={n} max={mx * 1000:.2f}mm shapekeys={len(keys)}")
stats.sort()
if stats:
    print(f"appull all moved={len(stats)} median={stats[len(stats) // 2]:.2f}mm max={stats[-1]:.2f}mm")
bpy.ops.export_scene.gltf(filepath=out, export_format="GLB", export_extras=True)
print("wrote", out)
