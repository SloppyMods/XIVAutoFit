"""Restore the vertex data Blender drops from our .glb builds, from the Penumbra exports they came from. Plain Python.

    python3 tools/restore_attrs.py [--force] [--fit-tol MM] <built.glb> <source_export.glb> [<body_export.glb> ...] <out.glb>

Blender's glTF round trip loses data that Penumbra exports carry (builds/_dionys/e6175skin/REPORT.md):
  influences 5-8 (JOINTS_1/WEIGHTS_1), the `_FFXIV_COLOR*`
  names (Blender renames them COLOR_n), sometimes TEXCOORD_1/2, and the atr_* node extras on some meshes.

Per built primitive this script picks the source file whose primitives (same material name, Blender ".NNN" suffix
ignored) match best, maps every built vertex to a source vertex and then:
  - TANGENT: never written; a TANGENT in the build is removed. Penumbra's export tangent is 90 deg off the game's
    and its import keeps what it is given, so the output must have none and Penumbra computes the right one
    (builds/_debug6066/REPORT.md, "Bug 2 - UPDATE"; the 2026-11-12 builds that copied it were 90 deg off in game).
  - 8 influences: when the built 4 weights equal the source top 4 (renormalised, same joint names, within 1e-3)
    and the source vertex has more than 4, the full source set is written (JOINTS_0/1, WEIGHTS_0/1), remapped by
    joint name into the built skin. Changed weights (our weight transfer) and joints missing from the built skin
    keep the built 4 (counted). Joints are never added to a skin.
  - Colours: every source `_FFXIV_COLOR*` attribute under its source name and accessor type. Blender COLOR_n are kept:
    Penumbra (Import/Models/Import/VertexAttribute.cs Color) reads `_FFXIV_COLOR`, else COLOR_0, so COLOR_n only wins
    when the source has no `_FFXIV_COLOR`, and then COLOR_0 already equals `_FFXIV_COLOR_0`.
  - TEXCOORD_1/2: copied when the built primitive lacks them and the source has them. TEXCOORD_1 is added only if
    every sub-mesh of that mesh group ("mesh N.*") ends up with it (Penumbra needs one vertex declaration per group).
  - atr_* (node extras with value true; Penumbra SubMeshImporter.BuildMetaAttributes): copied from the source mesh
    the vertices map to, when the built node has none. Built atr_* are never changed.
POSITION, NORMAL, TEXCOORD_0, indices, materials and names are untouched.

Vertex matching: index map when the same-named source primitive has the same count and equal UV0. Otherwise every
built vertex takes the source vertex with exactly equal UV0 (1e-5) that is nearest in position (normal breaks ties);
UV-equal vertices up to --fit-tol (default 30 mm) away count as "fit-moved" (the fit step moves cloth). Vertices
without an equal UV take the nearest position and must be within 0.5 mm. A vertex is bad when neither holds.
"ambig" counts fit-moved vertices where another UV-equal source vertex (mirrored UVs) was almost as near.
Exit 1 (writes nothing) if any matched mesh has more than 1% bad vertices, unless --force.
"""
import argparse
import os
import re
import sys
from collections import Counter, defaultdict

import numpy as np
from scipy.spatial import cKDTree

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import glb_raw  # noqa: E402

UV_EPS = 1e-5
CLOSE = 0.0005  # 0.5 mm
WEIGHT_EPS = 1e-3
BAD_FRACTION = 0.01
KIND_NAMES = ["index", "uv", "fitmoved", "pos", "bad"]


def floats(doc, blob, index):
    """Accessor as float64, with normalised integers scaled to 0..1."""
    acc = doc["accessors"][index]
    data = glb_raw.read_accessor(doc, blob, index).astype("f8")
    if acc.get("normalized") and acc["componentType"] in glb_raw.DIVISOR:
        data = data / glb_raw.DIVISOR[acc["componentType"]]
    return data


def base_material(name):
    return re.sub(r"\.\d{3}$", "", name or "")


def atr_of(extras):
    return sorted(k for k, v in (extras or {}).items() if v is True)


def group_of(name):
    m = re.match(r"mesh (\d+)\.(\d+)", name or "")
    return int(m.group(1)) if m else None


class Prim:
    """One primitive's data, read once."""

    def __init__(self, doc, blob, rec):
        self.rec = rec
        a = rec["attributes"]
        self.name = rec["name"]
        self.material = base_material(rec["material"])
        self.pos = floats(doc, blob, a["POSITION"])
        self.n = len(self.pos)
        self.nrm = floats(doc, blob, a["NORMAL"]) if "NORMAL" in a else np.zeros((self.n, 3))
        self.uv0 = floats(doc, blob, a["TEXCOORD_0"]) if "TEXCOORD_0" in a else np.zeros((self.n, 2))
        self.uv = {k: floats(doc, blob, a[k]) for k in ("TEXCOORD_1", "TEXCOORD_2") if k in a}
        self.colors = {k: (glb_raw.read_accessor(doc, blob, a[k]), doc["accessors"][a[k]]) for k in a if k.startswith("_FFXIV_COLOR")}
        self.atr = atr_of(doc["nodes"][rec["node"]].get("extras"))
        skin = rec["skin"]
        self.joint_names = [doc["nodes"][j].get("name") for j in doc["skins"][skin]["joints"]] if skin is not None else []
        self.infl = None
        if "JOINTS_0" in a and "WEIGHTS_0" in a:
            j = [glb_raw.read_accessor(doc, blob, a["JOINTS_0"]).astype(int)]
            w = [floats(doc, blob, a["WEIGHTS_0"])]
            if "JOINTS_1" in a and "WEIGHTS_1" in a:
                j.append(glb_raw.read_accessor(doc, blob, a["JOINTS_1"]).astype(int))
                w.append(floats(doc, blob, a["WEIGHTS_1"]))
            self.joints = np.concatenate(j, 1)
            self.weights = np.concatenate(w, 1)
            self.infl = (self.joints, self.weights)


class SourceSet:
    """All primitives of one source file sharing a material, concatenated."""

    def __init__(self, prims):
        self.prims = prims
        self.owner = np.concatenate([np.full(p.n, i) for i, p in enumerate(prims)])
        self.local = np.concatenate([np.arange(p.n) for p in prims])
        self.pos = np.concatenate([p.pos for p in prims])
        self.nrm = np.concatenate([p.nrm for p in prims])
        self.uv0 = np.concatenate([p.uv0 for p in prims])
        self.uv_tree = cKDTree(self.uv0)
        self.pos_tree = cKDTree(self.pos)


def match(built, sset, fit_tol):
    """Returns (global source index, distance, kind, ambiguous) per built vertex."""
    n = built.n
    for i, p in enumerate(sset.prims):
        if p.name == built.name and p.n == n and np.abs(p.uv0 - built.uv0).max(initial=0) <= UV_EPS:
            start = int(np.flatnonzero(sset.owner == i)[0])
            idx = start + np.arange(n)
            dist = np.linalg.norm(sset.pos[idx] - built.pos, axis=1)
            kind = np.where(dist <= fit_tol, 0, 4)
            return idx, dist, kind, np.zeros(n, bool)
    k = min(16, len(sset.pos))
    du, iu = sset.uv_tree.query(built.uv0, k=k)
    dp, ip = sset.pos_tree.query(built.pos, k=min(4, len(sset.pos)))
    if k == 1:
        du, iu = du[:, None], iu[:, None]
    if dp.ndim == 1:
        dp, ip = dp[:, None], ip[:, None]
    # UV-equal candidates: the UV neighbours plus position neighbours whose UV is equal too
    cand = np.concatenate([iu, ip], 1)
    uv_ok = np.concatenate([du <= UV_EPS, np.abs(sset.uv0[ip] - built.uv0[:, None, :]).max(2) <= UV_EPS], 1)
    pdist = np.linalg.norm(sset.pos[cand] - built.pos[:, None, :], axis=2)
    ndot = np.einsum("vkc,vc->vk", sset.nrm[cand], built.nrm)
    same_name = np.array([p.name == built.name for p in sset.prims])[sset.owner[cand]]
    cost = pdist + 1e-4 * (1 - ndot) + 1e-6 * ~same_name  # seam duplicates: prefer the same-named source mesh
    uv_cost = np.where(uv_ok, cost, np.inf)
    best = uv_cost.argmin(1)
    rows = np.arange(n)
    has_uv = np.isfinite(uv_cost[rows, best])
    idx = np.where(has_uv, cand[rows, best], 0)
    dist = np.where(has_uv, pdist[rows, best], np.inf)
    # ambiguity: another UV-equal candidate at a different place (>1 mm from the chosen) almost as near
    chosen_pos = sset.pos[idx]
    other_far = np.linalg.norm(sset.pos[cand] - chosen_pos[:, None, :], axis=2) > 0.001
    near = uv_ok & other_far & (pdist < dist[:, None] + 0.010)
    ambiguous = has_uv & (dist > CLOSE) & near.any(1)
    # no equal UV: nearest position (normal breaks ties)
    pcost = pdist[:, k:] + 1e-4 * (1 - ndot[:, k:])
    pbest = pcost.argmin(1)
    pidx = ip[rows, pbest]
    pd = pdist[:, k:][rows, pbest]
    kind = np.where(has_uv, np.where(dist <= CLOSE, 1, np.where(dist <= fit_tol, 2, 4)), np.where(pd <= CLOSE, 3, 4))
    idx = np.where(has_uv, idx, pidx)
    dist = np.where(has_uv, dist, pd)
    # a UV-equal vertex beyond fit_tol: the plain nearest position may still be a close match
    far = has_uv & (kind == 4) & (pd <= CLOSE)
    idx[far], dist[far], kind[far] = pidx[far], pd[far], 3
    return idx, dist, kind, ambiguous


def score(kind, dist):
    return ((kind == 4).mean(), (kind == 2).mean(), float(np.median(dist)) if len(dist) else 0.0)


def restore_weights(built, src_prim_of, src_local, sources_prims):
    """Returns (joints8, weights8 or None, counters)."""
    c = Counter()
    if built.infl is None:
        return None, None, c
    bj, bw = built.infl
    name_to_built = {nm: i for i, nm in enumerate(built.joint_names)}
    out_j = np.zeros((built.n, 8), int)
    out_w = np.zeros((built.n, 8))
    out_j[:, :bj.shape[1]] = np.where(bw > 0, bj, 0)
    out_w[:, :bw.shape[1]] = bw
    any_restored = False
    for v in range(built.n):
        sp = sources_prims[src_prim_of[v]]
        if sp.infl is None:
            c["no source weights"] += 1
            continue
        sj, sw = sp.infl[0][src_local[v]], sp.infl[1][src_local[v]]
        order = np.argsort(-sw, kind="stable")
        src = [(sp.joint_names[sj[i]], sw[i]) for i in order if sw[i] > 0]
        if len(src) <= 4:
            c["<=4 in source"] += 1
            continue
        top = src[:4]
        total = sum(w for _, w in top)
        built_map = defaultdict(float)
        for i in range(bw.shape[1]):
            if bw[v, i] > 0:
                built_map[built.joint_names[bj[v, i]]] += bw[v, i]
        names = set(built_map) | {nm for nm, _ in top}
        top_map = dict(top)
        equal = all(abs(built_map.get(nm, 0) - top_map.get(nm, 0) / total) <= WEIGHT_EPS for nm in names) or \
            all(abs(built_map.get(nm, 0) - top_map.get(nm, 0)) <= WEIGHT_EPS for nm in names)
        if not equal:
            c["kept (weights changed)"] += 1
            continue
        if any(nm not in name_to_built for nm, _ in src):
            c["kept (joint missing in built skin)"] += 1
            continue
        out_j[v] = 0
        out_w[v] = 0
        for i, (nm, w) in enumerate(src[:8]):
            out_j[v, i] = name_to_built[nm]
            out_w[v, i] = w
        c["restored 5-8"] += 1
        any_restored = True
    if not any_restored:
        return None, None, c
    return out_j, out_w, c


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("files", nargs="+")
    ap.add_argument("--force", action="store_true", help="write even if a mesh has more than 1%% bad matches")
    ap.add_argument("--fit-tol", type=float, default=30.0, help="max distance in mm for UV-equal fit-moved vertices")
    args = ap.parse_args(argv)
    if len(args.files) < 3:
        ap.error("need <built.glb> <source.glb> [...] <out.glb>")
    built_path, source_paths, out_path = args.files[0], args.files[1:-1], args.files[-1]
    if os.path.exists(out_path):
        print(f"refusing: {out_path} exists (never overwrite)")
        return 2
    fit_tol = args.fit_tol / 1000.0

    bdoc, bblob = glb_raw.load(built_path)
    sources = []
    for path in source_paths:
        doc, blob = glb_raw.load(path)
        sources.append((os.path.basename(path), [Prim(doc, blob, r) for r in glb_raw.primitives(doc)]))
    sets = {}  # (source index, material) -> SourceSet

    def source_set(si, material):
        key = (si, material)
        if key not in sets:
            prims = [p for p in sources[si][1] if p.material == material]
            sets[key] = SourceSet(prims) if prims else None
        return sets[key]

    writer = glb_raw.GlbWriter(bdoc, bblob)
    built_prims = [Prim(bdoc, bblob, r) for r in glb_raw.primitives(bdoc)]
    plans = []
    refuse = []
    trials = []
    for bp in built_prims:
        trial = {}
        for si in range(len(sources)):
            sset = source_set(si, bp.material)
            if sset is not None:
                res = match(bp, sset, fit_tol)
                trial[si] = (score(res[2], res[1]), sset, res)
        trials.append(trial)
    # one source per mesh group ("mesh N.*") when it serves every sub-mesh (keeps one vertex declaration per group);
    # ties go to the last source given, so a body export listed after the outfit export wins for skin
    group_source = {}
    for g in {group_of(bp.name) for bp in built_prims}:
        members = [t for bp, t in zip(built_prims, trials) if group_of(bp.name) == g]
        best = None
        for si in range(len(sources)):
            if not all(si in t for t in members) or any(t[si][0][0] > BAD_FRACTION for t in members):
                continue
            total = tuple(sum(t[si][0][k] for t in members) for k in range(3))
            if best is None or total <= best[0]:
                best = (total, si)
        group_source[g] = best[1] if best else None
    for bp, trial in zip(built_prims, trials):
        if not trial:
            plans.append(dict(prim=bp, source=None))
            continue
        si = group_source[group_of(bp.name)]
        if si is None:
            si = min(trial, key=lambda s: (trial[s][0], -s))
        _, sset, (idx, dist, kind, amb) = trial[si]
        bad = int((kind == 4).sum())
        if bad > BAD_FRACTION * bp.n:
            refuse.append(bp.name)
        plans.append(dict(prim=bp, source=si, sset=sset, idx=idx, dist=dist, kind=kind, amb=amb))

    # TEXCOORD_1 only when the whole mesh group gets it
    group_has_uv1 = defaultdict(list)
    for pl in plans:
        bp = pl["prim"]
        will = "TEXCOORD_1" in bp.rec["attributes"] or (pl["source"] is not None and
                                                         all("TEXCOORD_1" in p.uv for p in {pl["sset"].prims[o] for o in np.unique(pl["sset"].owner[pl["idx"]])}))
        group_has_uv1[group_of(bp.name)].append(will)

    print(f"restore_attrs: {os.path.basename(built_path)} <- {', '.join(s[0] for s in sources)}")
    print(f"{'mesh':9} {'verts':>6} {'source':18} {'index':>6} {'uv':>6} {'fitmv':>6} {'pos':>5} {'bad':>4} {'ambig':>5} {'max mm':>7} "
          f"{'p99 mm':>7} {'-tan':>6} {'8infl+':>6} {'kept':>5}  colours | uv | atr")
    totals = Counter()
    for pl in plans:
        bp = pl["prim"]
        prim_json = writer.doc["meshes"][bp.rec["mesh"]]["primitives"][bp.rec["prim"]]
        attrs = prim_json["attributes"]
        if pl["source"] is None:
            print(f"{bp.name:9} {bp.n:6} {'-- no source with material ' + bp.material}")
            totals["meshes without source"] += 1
            continue
        sset, idx, dist, kind, amb = pl["sset"], pl["idx"], pl["dist"], pl["kind"], pl["amb"]
        owner, local = sset.owner[idx], sset.local[idx]
        kc = Counter(kind.tolist())
        notes = []
        # TANGENT: never written, and dropped if the build has one. Penumbra's exported tangent is 90 deg off the
        # game's and its import stores what it is given; with no TANGENT it computes the correct one
        # (builds/_debug6066/REPORT.md, "Bug 2 - UPDATE").
        ntan = 1 if attrs.pop("TANGENT", None) is not None else 0
        if ntan:
            notes.append("built TANGENT dropped")
        # weights
        joints8, weights8, wc = restore_weights(bp, owner, local, sset.prims)
        if joints8 is not None:
            attrs["JOINTS_0"] = writer.add_accessor(joints8[:, :4], 5123, "VEC4")
            attrs["JOINTS_1"] = writer.add_accessor(joints8[:, 4:], 5123, "VEC4")
            attrs["WEIGHTS_0"] = writer.add_accessor(weights8[:, :4].astype("f4"), 5126, "VEC4")
            attrs["WEIGHTS_1"] = writer.add_accessor(weights8[:, 4:].astype("f4"), 5126, "VEC4")
        kept = wc["kept (weights changed)"] + wc["kept (joint missing in built skin)"]
        if wc["kept (joint missing in built skin)"]:
            notes.append(f"{wc['kept (joint missing in built skin)']} kept: joint missing")
        # colours
        colour_names = sorted(set().union(*[set(sset.prims[o].colors) for o in np.unique(owner)]))
        written = []
        for cname in colour_names:
            if not all(cname in sset.prims[o].colors for o in np.unique(owner)):
                notes.append(f"{cname} not in every source mesh: skipped")
                continue
            first = sset.prims[owner[0]].colors[cname][1]
            data = np.zeros((bp.n, glb_raw.COUNT[first["type"]]), sset.prims[owner[0]].colors[cname][0].dtype)
            for o in np.unique(owner):
                sel = owner == o
                data[sel] = sset.prims[o].colors[cname][0][local[sel]]
            attrs[cname] = writer.add_accessor(data, first["componentType"], first["type"], first.get("normalized", False))
            written.append(cname)
        # TEXCOORD_1/2
        uvs = []
        for uname in ("TEXCOORD_1", "TEXCOORD_2"):
            if uname in attrs:
                continue
            if uname == "TEXCOORD_1" and not all(group_has_uv1[group_of(bp.name)]):
                notes.append("TEXCOORD_1 skipped: not on every sub-mesh of the group")
                continue
            if uname == "TEXCOORD_2" and "TEXCOORD_1" not in attrs:
                continue
            if all(uname in sset.prims[o].uv for o in np.unique(owner)):
                data = np.zeros((bp.n, 2))
                for o in np.unique(owner):
                    sel = owner == o
                    data[sel] = sset.prims[o].uv[uname][local[sel]]
                attrs[uname] = writer.add_accessor(data.astype("f4"), 5126, "VEC2")
                uvs.append(uname[-1])
        # atr_* node extras
        share = Counter(owner.tolist()).most_common()
        main_src = sset.prims[share[0][0]]
        node = writer.doc["nodes"][bp.rec["node"]]
        if bp.atr:
            atr_state = "kept " + ",".join(bp.atr) + ("" if bp.atr == main_src.atr else f" (source has {','.join(main_src.atr) or 'none'})")
        elif main_src.atr:
            extras = dict(node.get("extras") or {})
            extras.update({k: True for k in main_src.atr})
            node["extras"] = extras
            atr_state = "restored " + ",".join(main_src.atr)
            totals["atr restored"] += 1
        else:
            atr_state = "none in source"
        if len(share) > 1:
            notes.append("maps to " + "+".join(f"{sset.prims[o].name}:{c}" for o, c in share))
        p99 = float(np.percentile(dist, 99)) * 1000 if bp.n else 0.0
        print(f"{bp.name:9} {bp.n:6} {sources[pl['source']][0][:18]:18} {kc[0]:6} {kc[1]:6} {kc[2]:6} {kc[3]:5} {kc[4]:4} "
              f"{int(amb.sum()):5} {dist.max(initial=0) * 1000:7.2f} {p99:7.2f} {ntan:6} {wc['restored 5-8']:6} {kept:5}  "
              f"{','.join(written) or '-'} | {','.join(uvs) or '-'} | {atr_state}" + (f"  [{'; '.join(notes)}]" if notes else ""))
        totals["verts"] += bp.n
        totals["tangents dropped"] += ntan
        totals["restored 5-8"] += wc["restored 5-8"]
        totals["kept"] += kept
        totals["bad"] += kc[4]
        totals["ambig"] += int(amb.sum())
    # no TANGENT anywhere in the output, also on meshes without a source
    for p in glb_raw.primitives(writer.doc):
        if writer.doc["meshes"][p["mesh"]]["primitives"][p["prim"]]["attributes"].pop("TANGENT", None) is not None:
            totals["tangents dropped"] += 1
    # same attribute names inside a mesh group: give the 4-influence sub-meshes zero JOINTS_1/WEIGHTS_1
    all_prims = glb_raw.primitives(writer.doc)
    eight = {group_of(p["name"]) for p in all_prims if "JOINTS_1" in p["attributes"]}
    for p in all_prims:
        a = writer.doc["meshes"][p["mesh"]]["primitives"][p["prim"]]["attributes"]
        if group_of(p["name"]) in eight and "JOINTS_0" in a and "JOINTS_1" not in a:
            count = writer.doc["accessors"][a["JOINTS_0"]]["count"]
            a["JOINTS_1"] = writer.add_accessor(np.zeros((count, 4)), 5123, "VEC4")
            a["WEIGHTS_1"] = writer.add_accessor(np.zeros((count, 4), "f4"), 5126, "VEC4")
    # bones per mesh group (Penumbra builds one bone table per mesh)
    groups = defaultdict(set)
    for mesh_prim in glb_raw.primitives(writer.doc):
        g = group_of(mesh_prim["name"])
        a = mesh_prim["attributes"]
        if mesh_prim["skin"] is None or "JOINTS_0" not in a:
            continue
        names = [writer.doc["nodes"][j].get("name") for j in writer.doc["skins"][mesh_prim["skin"]]["joints"]]
        blob = bytes(writer.blob)
        for jk, wk in (("JOINTS_0", "WEIGHTS_0"), ("JOINTS_1", "WEIGHTS_1")):
            if jk in a:
                j = glb_raw.read_accessor(writer.doc, blob, a[jk]).astype(int)
                w = floats(writer.doc, blob, a[wk])
                groups[g].update(names[x] for x in j[w > 0].ravel())
    big = {g: len(s) for g, s in groups.items() if len(s) > 64}
    print("totals: " + ", ".join(f"{k} {v}" for k, v in totals.items()) +
          f"; bones per group max {max((len(s) for s in groups.values()), default=0)}" + (f" (over 64: {big})" if big else ""))
    if refuse and not args.force:
        print(f"REFUSED: more than 1% bad matches in {', '.join(refuse)} (use --force); nothing written")
        return 1
    writer.save(out_path)
    print(f"wrote {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
