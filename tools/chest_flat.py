"""Pull Bibo-shaped chest cloth in onto the flat Doll chest, front only, limited to a chest panel (from e0753).

    blender -b -P chest_flat.py -- <in.glb> <out.glb|-> [clearance_mm=2] [maxpull_mm=30]
Mode out '-' only prints the gap profile (cloth-to-skin gap per height, `min` and `p10` in mm).  Run it that way first:
if `min` stays above about 5 mm at z 1.20-1.34, the cups stand off the chest and this script should run.
Env CFZ="lo0,lo1,hi0,hi1" and CFX="x0,x1" change the panel; CFMESH="mesh 1.0,mesh 2.0" names the cloth meshes to pull
(default is e0753's); CFR is the shell-depth radius in mm.  Input is a finished build (skin meshes are `mesh 0.*` on
`/mt_c0201b0001_b.mtrl`).

CFFIELD=1 (added for e6120, off by default) switches to a position-only displacement field, so pockets, flaps, straps
and every seam move with the fabric under them and nothing tears open; see the comment at `if os.environ.get("CFFIELD")`
for its options (CFWRAP, CFWZ, CFWFADE, CFWSIGMA, CFSMOOTH, CFGRID, CFLIFT, CFRIGID, CFFOLLOW, CFPROBE).  It prints
SEAMCHECK (largest separation of vertices that started on the same spot) and STRETCH (edge length ratios).
"""
import os, sys, statistics
import bpy
from mathutils import Vector, kdtree
from mathutils.kdtree import KDTree
from mathutils.bvhtree import BVHTree
a = sys.argv[sys.argv.index("--") + 1:]
src, out = a[0], a[1]
if out != "-" and os.path.exists(out):
    sys.exit(f"refusing to overwrite {out}; pick a new name")
CLEAR = float(a[2]) / 1000 if len(a) > 2 else 0.002
MAXPULL = float(a[3]) / 1000 if len(a) > 3 else 0.05
Z = [float(v) for v in os.environ.get("CFZ", "1.14,1.18,1.33,1.38").split(",")]
XF = [float(v) for v in os.environ.get("CFX", "0.15,0.19").split(",")]
CLOTH = os.environ.get("CFMESH", "mesh 1.0,mesh 2.0").split(",")
PASSES = 25
RADIUS = float(os.environ.get('CFR','10')) / 1000

def ramp(v, lo, hi):
    t = min(1.0, max(0.0, (v - lo) / (hi - lo)))
    return t * t * (3 - 2 * t)

def panel(co):
    return ramp(co.z, Z[0], Z[1]) * (1 - ramp(co.z, Z[2], Z[3])) * (1 - ramp(abs(co.x), *XF))

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=src)
def mat(o):
    return o.material_slots[0].material.name if o.material_slots and o.material_slots[0].material else ""
SKIN_MAT = os.environ.get("CFSKINMAT", "/mt_c0201b0001_b.mtrl")  # chest_flat_dionys.py sets the Dionys skin, /mt_c0201b0001_bibo.mtrl
skins = [o for o in bpy.data.objects if o.type == "MESH" and mat(o) == SKIN_MAT and o.name.startswith("mesh 0.")]
verts, tris = [], []
for o in skins:
    base = len(verts)
    verts += [v.co.copy() for v in o.data.vertices]
    for p in o.data.polygons:
        tris.append(tuple(base + i for i in p.vertices[:3]))
tree = BVHTree.FromPolygons([tuple(v) for v in verts], tris)
bust = max((v for v in verts if 1.25 < v.z < 1.32 and abs(v.x) < 0.1), key=lambda v: abs(v.y))
FRONT = 1 if bust.y > 0 else -1
print("front sign", FRONT)

def profile(obj, label):
    rows = {}
    for v in obj.data.vertices:
        co = Vector(v.co)
        if abs(co.x) > 0.14 or not 1.14 <= co.z <= 1.38:
            continue
        loc, nrm, _, dist = tree.find_nearest(co)
        if nrm is None or nrm.y * FRONT < 0.2 or dist > 0.08:
            continue
        sd = dist if (co - loc).dot(nrm) >= 0 else -dist
        rows.setdefault(round(co.z * 50) / 50, []).append(sd * 1000)
    for z in sorted(rows):
        r = sorted(rows[z])
        print(f"GAP {label} {obj.name} z={z:.2f} n={len(r)} min={r[0]:.1f} p10={r[len(r)//10]:.1f} med={statistics.median(r):.1f}")

for n in CLOTH:
    profile(bpy.data.objects[n], "before")
if out == "-":
    sys.exit(0)

if os.environ.get("CFFIELD"):
    # CFFIELD=1 (added for e6120, off by default): move the chest with ONE displacement field that depends on position
    # only, instead of per vertex.  The default mode smooths each mesh along its own edges, so vertices that sit on the
    # same spot but belong to different pieces (a pocket sewn onto the jacket, seam duplicates, the armhole seam) got
    # different moves and tore apart, and pockets more than MAXPULL off the skin were never moved at all.
    # Here the chest is a grid over (x, z).  Each cell takes the smallest pull among CFMESH front vertices within CFR mm
    # (the layer nearest the skin), the grid is filled and blurred, and every front vertex of CFMESH and CFFOLLOW is
    # moved by the field at its (x, z).  Everything in one column moves together: pockets, flaps, buttons and straps
    # keep their height over the fabric, layers keep their order and coincident vertices stay together.  The clearance
    # pass works the same way (a column is lifted together; CFLIFT, 1.6, is its per-pass overshoot).  CFFOLLOW="mesh a,
    # mesh b" moves extra meshes with the field without sampling them; CFGRID (mm, 2.5) is the cell size; CFSMOOTH (12)
    # the blur passes; CFRIGID=<mm> moves loose pieces smaller than that (rivets, buckles) as blocks.  CFWRAP (below)
    # first carries the cloth by the difference between the export's own body and the Doll body.
    H = float(os.environ.get("CFGRID", "2.5")) / 1000
    SMOOTH = int(os.environ.get("CFSMOOTH", "12"))
    FOLLOW = [x for x in os.environ.get("CFFOLLOW", "").split(",") if x]
    cloth = [bpy.data.objects[n] for n in CLOTH]
    movers = cloth + [bpy.data.objects[n] for n in FOLLOW if n not in CLOTH]
    WZ = [float(v) for v in os.environ.get("CFWZ", ",".join(map(str, Z))).split(",")]  # CFWZ: height panel of the CFWRAP step
    X0, X1, Z0, Z1 = -XF[1], XF[1], min(Z[0], WZ[0]), max(Z[3], WZ[3])
    NX, NZ = int(round((X1 - X0) / H)) + 1, int(round((Z1 - Z0) / H)) + 1
    def cxz(x, z):
        return (x - X0) / H, (z - Z0) / H
    mid = {}
    for i in range(NX):
        for k in range(NZ):
            x, z = X0 + i * H, Z0 + k * H
            hf = tree.ray_cast(Vector((x, FRONT * 0.6, z)), Vector((0, -FRONT, 0)))
            hb = tree.ray_cast(Vector((x, -FRONT * 0.6, z)), Vector((0, FRONT, 0)))
            if hf[0] is not None and hb[0] is not None:
                mid[i, k] = (hf[0].y + hb[0].y) / 2
    def midat(x, z):
        i, k = cxz(x, z); i = min(NX - 1, max(0, int(round(i)))); k = min(NZ - 1, max(0, int(round(k))))
        return mid.get((i, k), 0.0)
    def weight(co):  # panel x front side of the body (from the skin's front/back mid-plane)
        return panel(co) * ramp((co.y - midat(co.x, co.z)) * FRONT, 0.01, 0.04)
    def wweight(co):  # the same with the CFWZ heights, for the CFWRAP step
        return (ramp(co.z, WZ[0], WZ[1]) * (1 - ramp(co.z, WZ[2], WZ[3])) * (1 - ramp(abs(co.x), *XF))
                * ramp((co.y - midat(co.x, co.z)) * FRONT, 0.01, 0.04))
    def bilinear(G, x, z):
        fi, fk = cxz(x, z)
        fi = min(NX - 1.001, max(0.0, fi)); fk = min(NZ - 1.001, max(0.0, fk))
        i, k = int(fi), int(fk); a, b = fi - i, fk - k
        return (G[i][k] * ((1 - a) * (1 - b)) + G[i + 1][k] * (a * (1 - b)) + G[i][k + 1] * ((1 - a) * b)
                + G[i + 1][k + 1] * (a * b))
    def blur(G, passes):
        for _ in range(passes):
            N = [[Vector(G[i][k]) for k in range(NZ)] for i in range(NX)]
            for i in range(NX):
                for k in range(NZ):
                    nb = [G[i2][k2] for i2, k2 in ((i - 1, k), (i + 1, k), (i, k - 1), (i, k + 1)) if 0 <= i2 < NX and 0 <= k2 < NZ]
                    N[i][k] = G[i][k] * 0.5 + sum(nb, Vector()) * (0.5 / len(nb))
            G = N
        return G
    # coincident vertices across all moved meshes, to prove afterwards that nothing separated
    allco = [(o.name, v.index, Vector(v.co)) for o in movers for v in o.data.vertices]
    kda = KDTree(len(allco))
    for j, (_, _, c) in enumerate(allco): kda.insert(c, j)
    kda.balance()
    pairs = [(j, j2) for j, (_, _, c) in enumerate(allco) for _, j2, _ in kda.find_range(c, 0.00005) if j2 > j]
    PROBE = Vector([float(x) for x in os.environ["CFPROBE"].split(",")]) if os.environ.get("CFPROBE") else None
    def probe(tag):  # CFPROBE="x,y,z" (debug): how the vertices that started within 6 mm of that point have moved so far
        if PROBE is None: return
        for _, j, _ in sorted(kda.find_range(PROBE, 0.006), key=lambda t: t[2]):
            nm, vi, c = allco[j]
            co = Vector(bpy.data.objects[nm].data.vertices[vi].co)
            loc, nrm, _, dist = tree.find_nearest(co)
            print(f"PROBE {tag} {nm}:{vi} start {tuple(round(x, 4) for x in c)} move mm {tuple(round(x * 1000, 1) for x in co - c)} gap {dist * 1000:.1f}")
    WRAP = os.environ.get("CFWRAP")
    hidden = set()  # with CFWRAP: vertices that sat inside the export's skin; the clearance pass leaves them inside
    if WRAP:
        # CFWRAP=<original export.glb>: first carry the chest cloth by the body difference, like wrap_to_body.py but only
        # inside the chest panel: each vertex moves by the step from the export's own skin (the bust the cloth was made
        # for) to the Doll skin at that spot, then the moves are blurred by 3D position (CFWSIGMA mm, 12).  A pocket
        # hanging under a Bibo bust moves with the bust it hung from, so it lands on the flat chest instead of staying
        # in the air.  Full move up to CFWFADE (mm, "30,70") from the export skin, none past the second value.
        import numpy as np
        old = set(bpy.data.objects)
        bpy.ops.import_scene.gltf(filepath=WRAP)
        new = [o for o in bpy.data.objects if o not in old]
        OV, OT = [], []
        for o in new:
            if o.type == "MESH" and mat(o).startswith("/mt_c0201b0001_") and "DOLL" not in mat(o):
                b0 = len(OV); OV += [tuple(o.matrix_world @ v.co) for v in o.data.vertices]
                OT += [tuple(b0 + i for i in p.vertices) for p in o.data.polygons]
        for o in new: bpy.data.objects.remove(o)
        otree = BVHTree.FromPolygons(OV, OT)
        WF0, WF1 = (float(x) / 1000 for x in os.environ.get("CFWFADE", "30,70").split(","))
        WS = float(os.environ.get("CFWSIGMA", "12")) / 1000
        P = np.array([tuple(c) for _, _, c in allco])
        M = np.zeros_like(P)
        for j, p in enumerate(P):
            co = Vector(p); w = wweight(co)
            if w <= 0: continue
            on_o, on_n, _, gap = otree.find_nearest(co)
            if on_o is None: continue
            if (co - on_o).dot(on_n) < 0: hidden.add(allco[j][:2])  # inside the export's own skin: hidden by design
            on_d = tree.find_nearest(on_o)[0]
            if on_d is None: continue
            f = min(1.0, max(0.0, (WF1 - gap) / (WF1 - WF0)))
            M[j] = np.array(on_d - on_o) * w * f * f * (3 - 2 * f)
        act = np.where(np.abs(M).sum(axis=1) > 0)[0]
        near = np.where(np.array([wweight(Vector(p)) for p in P]) > 0)[0]
        B = np.zeros_like(P)
        for s0 in range(0, len(near), 500):
            idx = near[s0:s0 + 500]
            d2 = ((P[idx, None, :] - P[None, near, :]) ** 2).sum(axis=2)
            wt = np.exp(-d2 / (2 * WS * WS))
            B[idx] = (wt @ M[near]) / wt.sum(axis=1, keepdims=True)
        for j in near:  # B already carries the panel weight; the extra factor only stops blur leaking past the panel edge
            nm, vi, c = allco[j]
            bpy.data.objects[nm].data.vertices[vi].co = Vector(P[j] + B[j] * min(1.0, wweight(Vector(P[j])) * 4))
        L = np.linalg.norm(B[near], axis=1) * 1000
        print(f"wrap: {len(hidden)} vertices start inside the export skin (left hidden), {len(act)} with a body step, "
              f"moved {len(near)}, mm p50/p95/max {np.percentile(L, 50):.1f} {np.percentile(L, 95):.1f} {L.max():.1f}")
        probe("wrap")
    # 1. pull field: smallest pull per column
    samp = []
    for o in cloth:
        for v in o.data.vertices:
            co = Vector(v.co)
            if weight(co) <= 0: continue
            loc, nrm, _, dist = tree.find_nearest(co)
            if nrm is None or nrm.y * FRONT < 0.2 or dist > MAXPULL + CLEAR or (co - loc).dot(nrm) < 0: continue
            samp.append((co.x, co.z, max(0.0, dist - CLEAR), (loc - co).normalized()))
    kds = KDTree(len(samp))
    for j, s in enumerate(samp): kds.insert((s[0], s[1], 0), j)
    kds.balance()
    G = [[None] * NZ for _ in range(NX)]
    for i in range(NX):
        for k in range(NZ):
            near = kds.find_range((X0 + i * H, Z0 + k * H, 0), RADIUS)
            if near:
                s = samp[min(near, key=lambda t: samp[t[1]][2])[1]]
                G[i][k] = s[3] * s[2]
    for _ in range(400):  # fill empty cells from their neighbours
        empty = [(i, k) for i in range(NX) for k in range(NZ) if G[i][k] is None]
        if not empty: break
        fill = {}
        for i, k in empty:
            nb = [G[i2][k2] for i2, k2 in ((i - 1, k), (i + 1, k), (i, k - 1), (i, k + 1)) if 0 <= i2 < NX and 0 <= k2 < NZ and G[i2][k2] is not None]
            if nb: fill[i, k] = sum(nb, Vector()) / len(nb)
        if not fill:
            for i, k in empty: G[i][k] = Vector()
            break
        for (i, k), val in fill.items(): G[i][k] = val
    G = blur(G, SMOOTH)
    moved, mx = 0, 0.0
    for o in movers:
        for v in o.data.vertices:
            co = Vector(v.co); w = weight(co)
            if w <= 0: continue
            d = bilinear(G, co.x, co.z) * w
            if d.length > 1e-6:
                v.co = co + d; moved += 1; mx = max(mx, d.length)
    print("field pull: samples", len(samp), "moved", moved, "max mm", round(mx * 1000, 1))
    probe("pull")
    # 2. clearance field: lift whole columns until every CFMESH front vertex is CLEAR off the skin
    shorts = []
    CLIFT = float(os.environ.get("CFLIFT", "1.6"))  # overshoot of the column lift per pass (blur lowers the peaks)
    startpos = {(nm, vi): c for nm, vi, c in allco}
    for it in range(8):
        S = [[Vector() for _ in range(NZ)] for _ in range(NX)]
        nshort = 0
        for o in cloth:
            for v in o.data.vertices:
                co = Vector(v.co); w = weight(co)
                if w < 0.05 or (o.name, v.index) in hidden: continue
                loc, nrm, _, dist = tree.find_nearest(co)
                if nrm is None or nrm.y * FRONT < 0.2 or dist > 0.03: continue
                sd = dist if (co - loc).dot(nrm) >= 0 else -dist
                if sd >= CLEAR - 0.0001: continue
                nshort += 1
                if PROBE is not None and it == 0: shorts.append((round(sd * 1000, 1), o.name, tuple(round(x, 3) for x in co), "from", tuple(round(x, 3) for x in startpos[o.name, v.index])))
                need = nrm * min(0.012, (CLEAR - sd + 0.0003) / max(w, 0.3))
                fi, fk = cxz(co.x, co.z)
                for i in range(int(fi) - 1, int(fi) + 3):
                    for k in range(int(fk) - 1, int(fk) + 3):
                        if 0 <= i < NX and 0 <= k < NZ and need.length > S[i][k].length: S[i][k] = need
        print("clear pass", it, "short", nshort)
        if PROBE is not None and it == 0:
            shorts.sort()
            for s in shorts[:25]: print("SHORT", s)
            print("SHORT sd quartiles", [shorts[len(shorts) * q // 4][0] for q in range(4)] if shorts else "-")
        if not nshort: break
        S = blur(S, 2)
        for i in range(NX):
            for k in range(NZ): S[i][k] = S[i][k] * CLIFT
        for o in movers:
            for v in o.data.vertices:
                co = Vector(v.co); w = weight(co)
                if w > 0: v.co = co + bilinear(S, co.x, co.z) * w
    for o in movers: o.data.update()
    probe("clear")
    RIGID = float(os.environ.get("CFRIGID", "0")) / 1000
    if RIGID:
        # CFRIGID=<mm>: loose pieces (after welding coincident vertices) smaller than this across, such as rivets, buttons
        # and buckles, move as one block by their mean move, so the field cannot stretch or squash them.
        par = list(range(len(allco)))
        def fnd(i):
            while par[i] != i:
                par[i] = par[par[i]]; i = par[i]
            return i
        idx = {(nm, vi): j for j, (nm, vi, _) in enumerate(allco)}
        for o in movers:
            for e in o.data.edges:
                a1, b1 = fnd(idx[o.name, e.vertices[0]]), fnd(idx[o.name, e.vertices[1]])
                if a1 != b1: par[a1] = b1
        for a1, b1 in pairs:
            ra, rb = fnd(a1), fnd(b1)
            if ra != rb: par[ra] = rb
        groups = {}
        for j in range(len(allco)): groups.setdefault(fnd(j), []).append(j)
        nr = 0
        for g in groups.values():
            pts = [allco[j][2] for j in g]
            lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
            hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
            if (hi - lo).length >= RIGID: continue
            vs_ = [bpy.data.objects[allco[j][0]].data.vertices[allco[j][1]] for j in g]
            mv = sum((Vector(v.co) - allco[j][2] for v, j in zip(vs_, g)), Vector()) / len(g)
            if mv.length < 1e-6: continue
            for v, j in zip(vs_, g): v.co = allco[j][2] + mv
            nr += 1
        for o in movers: o.data.update()
        print("rigid pieces moved as blocks:", nr)
        probe("rigid")
    cur = {(o.name, v.index): Vector(v.co) for o in movers for v in o.data.vertices}
    sep = [(cur[allco[a][:2]] - cur[allco[b][:2]]).length * 1000 for a, b in pairs]
    print("SEAMCHECK coincident pairs", len(pairs), "max separation mm", round(max(sep) if sep else 0.0, 3))
    orig = {(nm, vi): c for nm, vi, c in allco}
    for o in movers:  # edge stretch inside the moved area (1.0 = unchanged length)
        r = []
        for e in o.data.edges:
            k0, k1 = (o.name, e.vertices[0]), (o.name, e.vertices[1])
            l0 = (orig[k0] - orig[k1]).length
            if l0 < 1e-5 or ((cur[k0] - orig[k0]).length < 1e-5 and (cur[k1] - orig[k1]).length < 1e-5): continue
            r.append(((cur[k0] - cur[k1]).length / l0, l0, orig[k0]))
        if r:
            r.sort(key=lambda t: t[0])
            q = [t[0] for t in r]
            print(f"STRETCH {o.name} moved edges {len(q)} p1={q[len(q)//100]:.2f} p50={q[len(q)//2]:.2f} "
                  f"p99={q[len(q)*99//100]:.2f} min={q[0]:.2f} max={q[-1]:.2f} "
                  f"outside 0.5-2x: {sum(1 for x in q if x < 0.5 or x > 2)}")
            if PROBE is not None:
                for t in r[:3] + r[-3:]:
                    print(f"STRETCHAT {o.name} ratio {t[0]:.2f} start length {t[1]*1000:.2f} mm at {tuple(round(x, 3) for x in t[2])}")
    for n in CLOTH:
        profile(bpy.data.objects[n], "after")
    bpy.ops.export_scene.gltf(filepath=out, export_format="GLB", export_extras=True)
    sys.exit(0)

for n in CLOTH:
    obj = bpy.data.objects[n]
    vs = obj.data.vertices
    disp = [Vector((0, 0, 0)) for _ in vs]
    raw, direction = {}, {}
    for v in vs:
        co = Vector(v.co)
        if panel(co) <= 0:
            continue
        loc, nrm, _, dist = tree.find_nearest(co)
        if nrm is None or nrm.y * FRONT < 0.2 or dist > MAXPULL + CLEAR or (co - loc).dot(nrm) < 0:
            continue
        raw[v.index] = max(0.0, dist - CLEAR)
        direction[v.index] = (loc - co).normalized()
    # a cup is a shell: its outer face is far from the skin, so pulling every vertex to the skin would flatten it.
    # Use the smallest pull within RADIUS (the skin-side face) for the whole thickness, which keeps the shell's depth.
    kd = KDTree(len(vs))
    for v in vs:
        kd.insert(v.co, v.index)
    kd.balance()
    for i in raw:
        near = [raw[j] for _, j, _ in kd.find_range(vs[i].co, RADIUS) if j in raw]
        disp[i] = direction[i] * (min(near) * panel(Vector(vs[i].co)))
    nb = [[] for _ in vs]
    for e in obj.data.edges:
        nb[e.vertices[0]].append(e.vertices[1]); nb[e.vertices[1]].append(e.vertices[0])
    for _ in range(PASSES):
        new = list(disp)
        for i in range(len(vs)):
            if not nb[i] or panel(Vector(vs[i].co)) <= 0:
                continue
            avg = sum((disp[j] for j in nb[i]), Vector()) / len(nb[i])
            new[i] = disp[i] * 0.5 + avg * 0.5
        disp = new
    moved = 0
    for v in vs:
        if disp[v.index].length > 1e-5:
            v.co = Vector(v.co) + disp[v.index]; moved += 1
    for _ in range(3):  # clear pass: anything now closer than CLEAR (or under the skin) is pushed back out along the skin normal
        short, normal = {}, {}
        for v in vs:
            co = Vector(v.co)
            if panel(co) <= 0:
                continue
            loc, nrm, _, dist = tree.find_nearest(co)
            if nrm is None or nrm.y * FRONT < 0.2 or dist > 0.03:
                continue
            sd = dist if (co - loc).dot(nrm) >= 0 else -dist
            if sd < CLEAR:
                short[v.index] = CLEAR - sd
                normal[v.index] = nrm.copy()
        if not short:
            break
        kd = KDTree(len(vs))
        for v in vs:
            kd.insert(v.co, v.index)
        kd.balance()
        moves = {}
        for i in short:
            reach = max(short.get(j, 0.0) for _, j, _ in kd.find_range(vs[i].co, 0.006))
            moves[i] = normal[i] * (reach * panel(Vector(vs[i].co)) + 0.0003)
        for i, d in moves.items():
            vs[i].co = Vector(vs[i].co) + d
    obj.data.update()
    print("flat", n, "moved", moved, "max mm", max(d.length for d in disp) * 1000)
    # seam duplicates: moves happen per vertex; snap coincident verts together
for n in CLOTH:
    profile(bpy.data.objects[n], "after")
bpy.ops.export_scene.gltf(filepath=out, export_format="GLB", export_extras=True)
