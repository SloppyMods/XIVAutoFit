"""Fit a TBSE male outfit (Penumbra c0101 export) onto the HR3 male body, writing a c0901 .glb.

    python3 male_fit.py <outfit c0101.glb> <HR3 shell c0901.glb> <output name.glb>

The output name is a bare filename written into builds/_male/; an existing file is never overwritten. The shell is any Penumbra
c0901 export of that slot: it supplies the skeleton, the skin and fur meshes, and the attribute tags. The shell's own cloth is
dropped and the outfit's cloth, moved onto the HR3 body, takes its place.

Env: MFCLEAR=<mm> skin clearance (3.0), MFRADIUS=<mm> push reach (18), MFDEEP=<mm> skip vertices deeper than this (70),
MFBLUR=<mm> blur width for moves (20), MFFADE=<near,far mm> full body move up to near, none past far (70,220), MFFILTER=<cos> body lookup keeps faces facing the cloth (-2 means off),
MFWSYNC=<mm> take bone weights from the nearest HR3 skin wherever the cloth is within this far of it (off; weight blends off over the last 40%; only |x| above MFWSYNCX, default 0.25 m: sleeves benefit, hips get worse),
MFPOKE=<mm> also push cloth triangles a skin vertex comes through, up to this deep (30), MFFUR=<mm> delete fur within this far of the cloth (80), MFFINISH=<n> n extra rounds after the final blur that lift only the cloth still under the clearance, with a small radius (0),
MFFINISHMAX=<mm> no vertex moves further than this in all the finish rounds together (off),
MFDENSEPOKE=<mm> during finish rounds, also lift cloth triangles that skin points this far apart come through, so coarse triangles with clear corners are caught, ignoring folded layers that face the body (off); MFDENSEPUSH=1 also uses these rays in the main wide-radius pushes, which made a sleeved coat much worse,
MFUNCROSS=<n> n final rounds that move an outer-facing cloth vertex with a body-facing cloth layer just in front of it back outside that layer (0),
MFWSYNCSAFE=1 make MFWSYNC write 8 bones per vertex, keep j_sk_/j_ex_ cloth bones, and copy only from skin on the same limb (off),
MFPOKEY=<low,high m> only skin in this height band can push cloth (all), for keeping a waistband clear of it,
MFTUCK=<mm> pull skin under the cloth inward so it stays this far behind it (off); the cloth does not move,
MFEXTRASKIN=<text> also keep the SKINMDL mesh whose material contains this, drawn with the skin material (for hrBody SFW underwear, which is the body surface there),
MFDROPBONES=<a,b> leave skin on bones starting with these out of the output, MFTRIMPOKE=1 also leave out main-skin triangles poking through the cloth, up to MFTRIMREACH=<mm> out (15),
MFCULLCOVER=<mm> leave out main-skin triangles hidden under the cloth, keeping a strip this wide next to the skin that stays visible (off),
MFWINPAINT=<near mm,cos,far mm,waist m> set cloth weights with weight_inpaint.py: copy from the clearance body where skin within near mm faces within that cosine, keep the starting weights (the MFWSYNC result if on) past far mm and above the waist height, solve the rest (off),
MFSKINNOIV=1 move the output skin's weight off iv_ bones onto their nearest non-iv_ ancestor, for skin under cloth that has no iv_ weights (off),
MFCLEARBODY=<top.mdl,dwn.mdl> measure skin clearance against this body, less anything on MFDROPBONES, instead of the body the cloth was carried onto (off); use it when SKINMDL is a different legs option, so the cloth clears the skin the game will draw,
MFSOLE=<m> cloth below this height in the outfit keeps its original height, so a shoe sole stays flat on the floor (off),
MFHIPY=<m> below this height a leg moves on its own (1.12), MFMIDX=<mm> below MFHIPY, cloth within this of x=0 counts as both legs, so the crotch seam is not split hard (0 = old hard split),
MFWSYNC refuses to run when SKINMDL is a legs option (_dwn.mdl) missing from HR3BODY (weights would come from other legs than the game draws),
or when MFWSYNCX=0 lacks MFWSYNCSAFE=1 (cross-limb copy at the hips); MFWSYNCLEGACY=1 turns both into warnings, only to rebuild a recorded recipe. Body overrides: HR3BODY=<top.mdl,dwn.mdl> TBSEBODY=<top.mdl,dwn.mdl>.
SKINMDL=<.mdl> take the output skin and fur from this full-body HR3 model instead of the shell; use it when the shell export has its skin
cut away under a longer garment than the one being fitted (fur under the new cloth is deleted, because it would poke through).
"""
import copy
import os
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from scipy.spatial import cKDTree

sys.path.insert(0, str(Path(__file__).resolve().parent))
import glb_raw  # noqa: E402
import male_body as mb  # noqa: E402
import mdl_read  # noqa: E402
import male_regions as mr  # noqa: E402
import weight_inpaint as wi  # noqa: E402

OUT_DIR = Path(__file__).resolve().parent.parent / "builds" / "_male"
CLEAR = float(os.environ.get("MFCLEAR", "3.0")) / 1000
RADIUS = float(os.environ.get("MFRADIUS", "18")) / 1000
DEEP = float(os.environ.get("MFDEEP", "70")) / 1000
BLUR = float(os.environ.get("MFBLUR", "20")) / 1000
FADE_NEAR, FADE_FAR = (float(x) / 1000 for x in os.environ.get("MFFADE", "70,220").split(","))
LEG_SPLIT_Y = float(os.environ.get("MFHIPY", "1.12"))
MID_BAND = float(os.environ.get("MFMIDX", "0")) / 1000  # below MFHIPY, cloth within this of x=0 joins both sides (0 = hard split)
SOLE_Y = float(os.environ.get("MFSOLE", "0"))
FILTER = float(os.environ.get("MFFILTER", "-2"))
FUR_REACH = float(os.environ.get("MFFUR", "80")) / 1000
POKE_REACH = float(os.environ.get("MFPOKE", "30")) / 1000
WSYNC = float(os.environ.get("MFWSYNC", "0"))
WSYNC_X = float(os.environ.get("MFWSYNCX", "0.25"))
FINISH = int(os.environ.get("MFFINISH", "0"))
FINISH_RADIUS = 0.01
PASSES, SMOOTHS, TAIL_BLUR = int(os.environ.get("MFPASSES", "9")), 3, 2
NO_POKE_BONES = ("j_kubi", "j_kao", "j_ago", "j_mimi", "j_kami")  # a collar must not react to the neck
NECK_MARGIN = 0.08
DROP_BONES = tuple(x for x in os.environ.get("MFDROPBONES", "").split(",") if x)
TRIM_POKE = bool(int(os.environ.get("MFTRIMPOKE", "0")))
TRIM_REACH = float(os.environ.get("MFTRIMREACH", "15")) / 1000
CULL_MARGIN = float(os.environ.get("MFCULLCOVER", "0")) / 1000
CLEAR_BODY = os.environ.get("MFCLEARBODY", "")
SKIN_NO_IV = bool(int(os.environ.get("MFSKINNOIV", "0")))
W_INPAINT = os.environ.get("MFWINPAINT", "")
COVER_REACH, COVER_NEIGHBOURHOOD, COVER_MIN_OPEN_SHARE = 0.12, 0.02, 0.3
TUCK = float(os.environ.get("MFTUCK", "0")) / 1000
EXTRA_SKIN = os.environ.get("MFEXTRASKIN", "")
TUCK_REACH, TUCK_MAX, TUCK_BLUR = 0.09, 0.09, 0.012
POKE_Y = tuple(float(x) for x in os.environ.get("MFPOKEY", "-9,9").split(","))
VERTICAL_LIMIT = 0.7
SCHEDULE = (900.0, 600.0, 350.0, 180.0, 90.0, 40.0, 18.0, 8.0, 4.0, 2.0)
SKIN_TOKENS = ("b0001_",)
FINISH_MAX = float(os.environ.get("MFFINISHMAX", "0")) / 1000
DENSE_POKE = float(os.environ.get("MFDENSEPOKE", "0")) / 1000
UNCROSS = int(os.environ.get("MFUNCROSS", "0"))
UNCROSS_REACH, UNCROSS_MARGIN = 0.012, 0.001  # metres: how close a crossing layer must be, and how far past it the vertex ends up
DENSE_PUSH = bool(int(os.environ.get("MFDENSEPUSH", "0")))
WSYNC_SAFE = bool(int(os.environ.get("MFWSYNCSAFE", "0")))
WSYNC_LEGACY = bool(int(os.environ.get("MFWSYNCLEGACY", "0")))
OWN_SURFACE_GAP = 3e-4  # metres: a ray hit closer than this is the vertex's own surface
CLOTH_PHYSICS_BONES = ("j_sk_", "j_ex_")
SAFE_SLOTS = 8


@dataclass(frozen=True)
class SkinRays:
    """Rays cast inward from skin, for finding cloth the skin comes through. With outer_only, cloth facing the body (a folded inner layer) is ignored."""
    points: np.ndarray
    normals: np.ndarray
    outer_only: bool = False


def is_skin(material: str) -> bool:
    return any(token in material for token in SKIN_TOKENS)


def cloth_arrays(doc: dict, blob: bytes) -> dict:
    """Merge the outfit's cloth primitives into single arrays with one id range per primitive."""
    prims = [p for p in glb_raw.primitives(doc) if not is_skin(p["material"])]
    if not prims:
        sys.exit("no cloth primitives found in the outfit")
    read = lambda p, attribute: glb_raw.read_accessor(doc, blob, p["attributes"][attribute]).astype("f8")
    positions = [read(p, "POSITION") for p in prims]
    joints = [np.c_[read(p, "JOINTS_0"), read(p, "JOINTS_1")].astype("i8") if "JOINTS_1" in p["attributes"] else read(p, "JOINTS_0").astype("i8") for p in prims]
    weights = [np.c_[read(p, "WEIGHTS_0"), read(p, "WEIGHTS_1")] if "WEIGHTS_1" in p["attributes"] else read(p, "WEIGHTS_0") for p in prims]
    triangles, start = [], 0
    for p, pos in zip(prims, positions):
        triangles.append(glb_raw.read_accessor(doc, blob, p["indices"]).astype("i8").reshape(-1, 3) + start)
        start += len(pos)
    return dict(prims=prims, positions=np.vstack(positions), joints=np.vstack(joints), weights=np.vstack(weights),
                triangles=np.vstack(triangles), counts=[len(p) for p in positions])


def same_side(other_x: np.ndarray, x: float) -> np.ndarray:
    """Which of other_x count as the same leg as x; anything within MFMIDX of x=0 counts for both legs."""
    return (np.sign(other_x) == np.sign(x)) | (np.abs(other_x) < MID_BAND) | (abs(x) < MID_BAND)


def blur_moves(points: np.ndarray, moves: np.ndarray, sigma: float) -> np.ndarray:
    """Gaussian blur of a move field over nearby cloth, keeping the two legs apart below the crotch."""
    tree = cKDTree(points)
    groups = tree.query_ball_point(points, 3 * sigma, workers=3)
    out = moves.copy()
    below = points[:, 1] < LEG_SPLIT_Y
    for i, group in enumerate(groups):
        idx = np.array(group)
        if below[i]:
            idx = idx[same_side(points[idx, 0], points[i, 0])]
        if len(idx) == 0:
            continue
        gap = ((points[idx] - points[i]) ** 2).sum(1)
        weight = np.exp(-gap / (2 * sigma * sigma))
        out[i] = (moves[idx] * weight[:, None]).sum(0) / weight.sum()
    return out


def signed_clearance(points: np.ndarray, skin: mb.Samples) -> tuple[np.ndarray, np.ndarray]:
    """Distance from each point to the skin, negative when inside it, plus the skin's outward normal there."""
    _, near = skin.tree.query(points)
    return ((points - skin.points[near]) * skin.normals[near]).sum(1), skin.normals[near]


def needed_pushes(points: np.ndarray, triangles: np.ndarray, needy: np.ndarray, vertex_pushes: np.ndarray, rays: SkinRays) -> tuple[np.ndarray, np.ndarray]:
    """Where cloth must move and by how much: vertices under the clearance, plus the corners of any cloth triangle a skin ray comes through."""
    sources, pushes = list(points[needy]), list(vertex_pushes[needy])
    hits = mb.inward_hits(rays.points, rays.normals, points, triangles, POKE_REACH) if POKE_REACH > 0 else []
    facing = mb.face_normals(points, triangles) if rays.outer_only else None
    for ray, face, depth in hits:
        if facing is not None and float(facing[face] @ rays.normals[ray]) <= 0:
            continue
        for corner in triangles[face]:
            sources.append(points[corner])
            pushes.append(rays.normals[ray] * (depth + CLEAR))
    return np.array(sources).reshape(-1, 3), np.array(pushes).reshape(-1, 3)


def push_clear(points: np.ndarray, skin: mb.Samples, triangles: np.ndarray, rays: SkinRays) -> tuple[np.ndarray, int]:
    """One push round: every vertex takes the strongest nearby needed push, fading over RADIUS.

    Pushes come from cloth vertices under the clearance, plus the corners of any cloth triangle a skin vertex comes through,
    which the vertex test cannot see on coarse cloth over a rounded limb.
    """
    signed, normal = signed_clearance(points, skin)
    needy = (signed < CLEAR) & (signed > -DEEP)
    sources, pushes = needed_pushes(points, triangles, needy, normal * (CLEAR - signed)[:, None], rays)
    if len(sources) == 0:
        return points, 0
    groups = cKDTree(sources).query_ball_point(points, RADIUS, workers=3)
    below = points[:, 1] < LEG_SPLIT_Y
    moved = points.copy()
    strength = np.linalg.norm(pushes, axis=1)
    below_source = sources[:, 1] < LEG_SPLIT_Y
    for i, group in enumerate(groups):
        if not group:
            continue
        idx = np.array(group)
        if below[i]:
            idx = idx[same_side(sources[idx, 0], points[i, 0]) | ~below_source[idx]]
        if len(idx) == 0:
            continue
        fade = np.clip(1 - np.linalg.norm(sources[idx] - points[i], axis=1) / RADIUS, 0, 1)
        fade = fade * fade * (3 - 2 * fade)
        best = int((fade * strength[idx]).argmax())
        moved[i] = points[i] + pushes[idx[best]] * fade[best]
    return moved, len(sources)


def clearance_pass(points: np.ndarray, skin: mb.Samples, triangles: np.ndarray, rays: SkinRays, finish_rays: SkinRays) -> np.ndarray:
    start = points.copy()
    current = points
    for number in range(PASSES):
        current, count = push_clear(current, skin, triangles, rays)
        print(f"clearance round {number}: {count} vertices under {CLEAR * 1000:.1f} mm")
        if count == 0:
            break
    for round_number in range(SMOOTHS):
        current = start + blur_moves(start, current - start, BLUR * 0.7)
        if round_number < SMOOTHS - 1:
            current, count = push_clear(current, skin, triangles, rays)
            print(f"after smooth {round_number}: {count} vertices under {CLEAR * 1000:.1f} mm")
    before_finish = current.copy()
    for number in range(FINISH):  # after the last blur, so what these lift stays lifted; a small radius keeps the move local
        current, count = finish_round(current, skin, triangles, finish_rays)
        print(f"finish round {number}: {count} vertices lifted")
    current = capped_moves(before_finish, current)
    for number in range(UNCROSS):
        current, count = uncrossed(current, triangles, skin)
        print(f"uncross round {number}: {count} vertices moved")
    return current


def uncrossed(points: np.ndarray, triangles: np.ndarray, skin: mb.Samples) -> tuple[np.ndarray, int]:
    """Move each outer-facing vertex with a body-facing cloth layer just in front of it to the far side of that layer. Vertices stored twice at a UV seam move together."""
    needed = mb.crossed_vertices(points, triangles, skin, UNCROSS_REACH, OWN_SURFACE_GAP)
    if not needed:
        return points, 0
    ids, _ = mb.weld(points, triangles)
    moved = points.copy()
    for vertex in range(len(points)):
        found = needed.get(int(ids[vertex]))
        if found is not None:
            moved[vertex] = points[vertex] + found[1] * (found[0] + UNCROSS_MARGIN)
    return moved, len(needed)

def capped_moves(before: np.ndarray, after: np.ndarray) -> np.ndarray:
    """Limit each vertex's total finish move, so a hem or inner wall left deep in the body is not dragged out."""
    if FINISH_MAX <= 0:
        return after
    move = after - before
    length = np.linalg.norm(move, axis=1, keepdims=True)
    print(f"finish moves: largest {length.max() * 1000:.1f} mm, {np.count_nonzero(length > FINISH_MAX)} vertices capped at {FINISH_MAX * 1000:.0f} mm")
    return before + move * np.minimum(1.0, FINISH_MAX / np.maximum(length, 1e-12))


def finish_round(points: np.ndarray, skin: mb.Samples, triangles: np.ndarray, rays: SkinRays) -> tuple[np.ndarray, int]:
    """Lift each vertex under the clearance straight out, and neighbours within 10 mm by a fading share. With MFDENSEPOKE it also lifts triangles skin comes through."""
    signed, normal = signed_clearance(points, skin)
    needy = (signed < CLEAR) & (signed > -DEEP)
    vertex_pushes = normal * (CLEAR - signed)[:, None]
    if DENSE_POKE > 0:
        sources, pushes = needed_pushes(points, triangles, needy, vertex_pushes, rays)
    else:
        sources, pushes = points[needy], vertex_pushes[needy]
    if len(sources) == 0:
        return points, 0
    moved = points.copy()
    groups = cKDTree(sources).query_ball_point(points, FINISH_RADIUS, workers=3)
    below = points[:, 1] < LEG_SPLIT_Y
    strength = np.linalg.norm(pushes, axis=1)
    for i, group in enumerate(groups):
        if not group:
            continue
        idx = np.array(group)
        if below[i]:
            idx = idx[same_side(sources[idx, 0], points[i, 0])]
        if len(idx) == 0:
            continue
        fade = np.clip(1 - np.linalg.norm(sources[idx] - points[i], axis=1) / FINISH_RADIUS, 0, 1)
        best = int((fade * strength[idx]).argmax())
        moved[i] = points[i] + pushes[idx[best]] * fade[best]
    return moved, len(sources)


def rotate_frames(old: np.ndarray, new: np.ndarray, triangles: np.ndarray, normals: np.ndarray, tangents: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Rotate stored normals and tangents by each vertex's change of surface direction; UV-seam hard edges survive this way."""
    before, after = mb.vertex_normals(old, triangles), mb.vertex_normals(new, triangles)
    axis = np.cross(before, after)
    sine = np.linalg.norm(axis, axis=1, keepdims=True)
    cosine = (before * after).sum(1, keepdims=True)
    axis = axis / np.maximum(sine, 1e-12)
    rodrigues = lambda v: v * cosine + np.cross(axis, v) * sine + axis * ((axis * v).sum(1, keepdims=True)) * (1 - cosine)
    new_normals = rodrigues(normals)
    new_normals /= np.maximum(np.linalg.norm(new_normals, axis=1, keepdims=True), 1e-12)
    new_tangents = rodrigues(tangents[:, :3])
    new_tangents -= new_normals * (new_tangents * new_normals).sum(1, keepdims=True)
    new_tangents /= np.maximum(np.linalg.norm(new_tangents, axis=1, keepdims=True), 1e-12)
    return new_normals, np.c_[new_tangents, tangents[:, 3]]


FIRST_CLOTH_GROUP = 2  # groups 0 and 1 are the HR3 skin and fur


def cloth_node_name(name: str, prims: list[dict], base: int) -> str:
    """Output name 'mesh G.S': source mesh groups map to consecutive output groups, so each material stays in its own group."""
    groups = sorted({int(p["name"].split()[1].split(".")[0]) for p in prims})
    source_group, sub = name.split()[1].split(".")
    return f"mesh {base + groups.index(int(source_group))}.{sub}"


def detach_node(doc: dict, index: int) -> None:
    """Leave a node in the file as an empty transform; it renders nothing and the skeleton indices stay valid."""
    doc["nodes"][index].pop("mesh", None)
    doc["nodes"][index].pop("skin", None)
    doc["nodes"][index].pop("extras", None)
    doc["nodes"][index].pop("weights", None)
    doc["nodes"][index].pop("name", None)


def under_cloth(points: np.ndarray, cloth: np.ndarray, triangles: np.ndarray) -> np.ndarray:
    """True for fur near the cloth on either side: the fur has outward tufts, so inside-only culling leaves spikes through the shirt."""
    samples = mb.sample_surface(cloth, triangles, spacing=0.003)
    gap, _ = samples.tree.query(points)
    return gap < FUR_REACH


def tucked_positions(mesh: mdl_read.MdlMesh, cloth: np.ndarray, cloth_triangles: np.ndarray) -> np.ndarray:
    """Pull main-submesh skin that lies under the cloth inward, so it stays at least TUCK behind it. The cloth does not move.

    Coverage comes from rays along the skin's normal: outward hitting cloth means the skin is under it, inward hitting cloth means it pokes through.
    The moves are blurred once so the skin stays smooth, then any shortfall is applied directly.
    """
    first, count, _ = mesh.submeshes[0]
    triangles = mesh.triangles
    main = np.unique(triangles[first // 3:(first + count) // 3])
    positions = mesh.positions.copy()
    for round_number in range(2):
        normals = mb.vertex_normals(positions, triangles)
        wanted = np.zeros(len(positions))
        for vertex, _, t in mb.inward_hits(positions[main], -normals[main], cloth, cloth_triangles, TUCK_REACH):  # cloth outside the skin
            wanted[main[vertex]] = max(wanted[main[vertex]], TUCK - t)
        for vertex, _, t in mb.inward_hits(positions[main], normals[main], cloth, cloth_triangles, TUCK_REACH):  # skin outside the cloth
            wanted[main[vertex]] = max(wanted[main[vertex]], t + TUCK)
        wanted = np.minimum(wanted, TUCK_MAX)
        moves = -normals * wanted[:, None]
        if round_number == 0:
            blurred = moves.copy()
            groups = cKDTree(positions[main]).query_ball_point(positions[main], 3 * TUCK_BLUR, workers=3)
            for i, group in enumerate(groups):
                idx = main[np.array(group)]
                fade = np.exp(-((positions[idx] - positions[main[i]]) ** 2).sum(1) / (2 * TUCK_BLUR * TUCK_BLUR))
                blurred[main[i]] = (moves[idx] * fade[:, None]).sum(0) / fade.sum()
            moves = blurred
        positions += moves
        print(f"tuck round {round_number}: {np.count_nonzero(wanted[main] > 0)} of {len(main)} skin vertices moved, largest {np.linalg.norm(moves, axis=1).max() * 1000:.1f} mm")
    return positions


def without_dropped_bones(body: mb.Body) -> mb.Body:
    """The same body minus every triangle touching a vertex mainly on a DROP_BONES bone."""
    dominant = body.joints[np.arange(len(body.joints)), body.weights.argmax(1)]
    flagged = np.array([body.bones[j].startswith(DROP_BONES) for j in dominant]) if DROP_BONES else np.zeros(len(body.positions), bool)
    kept = body.triangles[~flagged[body.triangles].any(1)]
    used, inverse = np.unique(kept, return_inverse=True)
    print(f"clear body: {len(kept)} of {len(body.triangles)} triangles kept")
    return mb.Body(body.positions[used], inverse.reshape(-1, 3), body.bones, body.joints[used], body.weights[used])


def hidden_vertices(positions: np.ndarray, triangles: np.ndarray, main: np.ndarray, cloth: np.ndarray, cloth_triangles: np.ndarray) -> np.ndarray:
    """True for main-submesh vertices under the cloth and more than CULL_MARGIN from any skin that stays visible.

    A ray that slips between two cloth triangles would mark one lone vertex visible and leave a patch of skin around it,
    so a vertex only counts as visible when a fair share of the skin around it is uncovered too.
    """
    normals = mb.vertex_normals(positions, triangles)
    covered = np.zeros(len(positions), bool)
    hits = mb.inward_hits(positions[main], -normals[main], cloth, cloth_triangles, COVER_REACH)
    covered[main[np.unique([vertex for vertex, _, _ in hits]).astype("i8")]] = True
    tree = cKDTree(positions[main])
    open_share = np.array([np.mean(~covered[main[group]]) for group in tree.query_ball_point(positions[main], COVER_NEIGHBOURHOOD, workers=3)])
    visible = (~covered[main]) & (open_share >= COVER_MIN_OPEN_SHARE)
    hidden = np.zeros(len(positions), bool)
    if not visible.any():
        sys.exit("cull cover: no skin stays visible, refusing to delete all of it")
    gap, _ = cKDTree(positions[main][visible]).query(positions[main])
    hidden[main] = covered[main] & (gap > CULL_MARGIN)
    print(f"cull cover: {np.count_nonzero(covered[main])} of {len(main)} main vertices under cloth, {np.count_nonzero(hidden)} removable")
    return hidden


def trimmed_skin(mesh: mdl_read.MdlMesh, model: mdl_read.MdlModel, cloth: np.ndarray, cloth_triangles: np.ndarray, positions: np.ndarray) -> np.ndarray:
    """Which skin triangles to keep: drops those on the listed bones and, in the main (first) submesh, those a poke test finds coming through the cloth or hidden under it."""
    keep = np.ones(len(mesh.triangles), bool)
    if DROP_BONES:
        dominant = mesh.joints[np.arange(len(mesh.joints)), mesh.weights.argmax(1)]
        flagged = np.array([model.bones[j].startswith(DROP_BONES) for j in dominant])
        keep &= ~flagged[mesh.triangles].any(1)
    if TRIM_POKE:
        first, count, _ = mesh.submeshes[0]
        main = np.zeros(len(mesh.triangles), bool)
        main[first // 3:(first + count) // 3] = True
        normals = mb.vertex_normals(positions, mesh.triangles)
        poking = np.unique([vertex for vertex, _, _ in mb.inward_hits(positions, normals, cloth, cloth_triangles, TRIM_REACH)]).astype("i8")
        flagged = np.zeros(len(positions), bool)
        flagged[poking] = True
        keep &= ~(flagged[mesh.triangles].any(1) & main)
    if CULL_MARGIN > 0:  # last, so skin already deleted above cannot count as visible and protect what surrounds it
        first, count, _ = mesh.submeshes[0]
        main_triangle = np.zeros(len(mesh.triangles), bool)
        main_triangle[first // 3:(first + count) // 3] = True
        survivors = np.unique(mesh.triangles[keep & main_triangle])
        hidden = hidden_vertices(positions, mesh.triangles, survivors, cloth, cloth_triangles)
        keep &= ~(hidden[mesh.triangles].all(1) & main_triangle)
    print(f"skin {mesh.material}: removed {np.count_nonzero(~keep)} of {len(mesh.triangles)} triangles")
    return keep


def without_iv_bones(joints: np.ndarray, weights: np.ndarray, skeleton: list[str], parents: list[int]) -> tuple[np.ndarray, np.ndarray]:
    """Hand weight on iv_ bones to the nearest non-iv_ ancestor, so skin under cloth cannot shift on bones the cloth ignores."""
    def solid_ancestor(bone: int) -> int:
        while skeleton[bone].startswith("iv_") and parents[bone] >= 0:
            bone = parents[bone]
        return bone

    target = np.array([solid_ancestor(bone) for bone in range(len(skeleton))])
    new_joints, new_weights = np.zeros_like(joints), np.zeros_like(weights)
    for row, (row_joints, row_weights) in enumerate(zip(joints, weights)):
        merged: dict[int, float] = {}
        for joint, weight in zip(row_joints, row_weights):
            if weight > 0:
                merged[int(target[joint])] = merged.get(int(target[joint]), 0.0) + float(weight)
        for slot, (joint, weight) in enumerate(sorted(merged.items(), key=lambda item: -item[1])):
            new_joints[row, slot], new_weights[row, slot] = joint, weight
    return new_joints, new_weights


def add_skin_from_mdl(writer: glb_raw.GlbWriter, model: mdl_read.MdlModel, skeleton: list[str], cloth: np.ndarray, cloth_triangles: np.ndarray) -> None:
    """Replace the shell's skin and fur with the skin and fur of a full-body HR3 model, one glTF node per submesh."""
    doc = writer.doc
    template = next(p for p in glb_raw.primitives(doc) if is_skin(p["material"]))
    shell_skin = [p for p in glb_raw.primitives(doc) if is_skin(p["material"])]
    shell_positions = {p["node"]: glb_raw.read_accessor(doc, bytes(writer.blob), p["attributes"]["POSITION"]).astype("f8") for p in shell_skin}
    index = {name: i for i, name in enumerate(skeleton)}
    missing = sorted(set(model.bones) - set(skeleton))
    if missing:
        sys.exit(f"skin bones missing from the shell skeleton: {missing}")
    reused: set[int] = set()
    group = 0
    skin_submeshes = 0
    for mesh in model.meshes:
        as_skin = bool(EXTRA_SKIN) and EXTRA_SKIN in mesh.material
        if not mesh.material.endswith(("b0001_b.mtrl", "b0001_h.mtrl")) and not as_skin:
            continue
        keep_triangle = np.ones(len(mesh.triangles), bool)
        if "b0001_h" in mesh.material:
            hidden = under_cloth(mesh.positions, cloth, cloth_triangles)
            keep_triangle = hidden[mesh.triangles].sum(1) < 2
            print(f"fur {mesh.material}: removed {np.count_nonzero(~keep_triangle)} of {len(mesh.triangles)} triangles under the cloth")
        skin_positions = mesh.positions
        if mesh.material.endswith("b0001_b.mtrl") and TUCK > 0:
            skin_positions = tucked_positions(mesh, cloth, cloth_triangles)
        if mesh.material.endswith("b0001_b.mtrl") and (DROP_BONES or TRIM_POKE or CULL_MARGIN > 0):
            keep_triangle = trimmed_skin(mesh, model, cloth, cloth_triangles, skin_positions)
        material_name = next((m.material for m in model.meshes if m.material.endswith("b0001_b.mtrl")), mesh.material) if as_skin else mesh.material
        material_slot = next((i for i, m in enumerate(doc["materials"]) if m["name"] == material_name), None)
        if material_slot is None:
            doc["materials"].append(dict(copy.deepcopy(doc["materials"][doc["meshes"][template["mesh"]]["primitives"][template["prim"]]["material"]]), name=material_name))
            material_slot = len(doc["materials"]) - 1
        joints = np.array([[index[model.bones[j]] for j in row] for row in mesh.joints], "i4")
        weights = mesh.weights.astype("f8")
        weights = weights / np.maximum(weights.sum(1, keepdims=True), 1e-9)
        if SKIN_NO_IV and mesh.material.endswith("b0001_b.mtrl"):
            joints, weights = without_iv_bones(joints, weights, skeleton, glb_raw.joint_parents(doc))
        tangent = np.c_[mesh.tangents[:, :3] * 2 - 1, np.sign(mesh.tangents[:, 3] * 2 - 1)]
        tangent[:, 3][tangent[:, 3] == 0] = 1
        tangent[:, :3] /= np.maximum(np.linalg.norm(tangent[:, :3], axis=1, keepdims=True), 1e-9)
        normal = mesh.normals / np.maximum(np.linalg.norm(mesh.normals, axis=1, keepdims=True), 1e-9)
        for sub, (first, count, attrs) in enumerate(mesh.submeshes):
            all_indices = mesh.triangles.reshape(-1)
            chunk = all_indices[first:first + count].reshape(-1, 3)
            keep = keep_triangle[first // 3:(first + count) // 3]
            if keep.all():  # keep the shell's own primitive for this piece when it is the same mesh: it carries the HR3 shape keys
                sub_points = mesh.positions[np.unique(chunk)]
                match = next((p for p in shell_skin if shell_positions[p["node"]].shape[0] == len(sub_points) and p["node"] not in reused and p["material"] == mesh.material and float(cKDTree(sub_points).query(shell_positions[p["node"]])[0].max()) < 2e-4), None)
                print(f"  {mesh.material} submesh {sub}: {len(sub_points)} verts, shell match: {match['name'] if match is not None else 'none'}")
                if match is not None:
                    reused.add(match["node"])
                    node = doc["nodes"][match["node"]]
                    node["extras"] = {**{k: v for k, v in (node.get("extras") or {}).items() if not k.startswith("atr_")}, **{a: True for a in attrs}}  # the shell's tags can differ from the body's
                    continue
            else:
                print(f"  {mesh.material} submesh {sub}: culled, rebuilt from the model")
            chunk = chunk[keep]
            if len(chunk) == 0:
                continue
            used, inverse = np.unique(chunk, return_inverse=True)
            inverse = inverse.reshape(-1, 3)
            accessors = {
                "POSITION": writer.add_accessor(skin_positions[used].astype("f4"), 5126, "VEC3"),
                "NORMAL": writer.add_accessor(normal[used].astype("f4"), 5126, "VEC3"),
                "TANGENT": writer.add_accessor(tangent[used].astype("f4"), 5126, "VEC4"),
                "TEXCOORD_0": writer.add_accessor(mesh.uvs[0][used, :2].astype("f4"), 5126, "VEC2"),
                "TEXCOORD_1": writer.add_accessor(mesh.uvs[0][used, 2:4].astype("f4") if mesh.uvs[0].shape[1] >= 4 else mesh.uvs[0][used, :2].astype("f4"), 5126, "VEC2"),
                "TEXCOORD_2": writer.add_accessor(mesh.uvs[1][used, :2].astype("f4") if len(mesh.uvs) > 1 else mesh.uvs[0][used, :2].astype("f4"), 5126, "VEC2"),
                "_FFXIV_COLOR": writer.add_accessor((mesh.colors[used] * 255).round().astype("u1"), 5121, "VEC4", normalized=True),
                "JOINTS_0": writer.add_accessor(joints[used][:, :4].astype("u2"), 5123, "VEC4"),
                "WEIGHTS_0": writer.add_accessor(weights[used][:, :4].astype("f4"), 5126, "VEC4"),
            }
            if joints.shape[1] > 4:
                accessors["JOINTS_1"] = writer.add_accessor(joints[used][:, 4:8].astype("u2"), 5123, "VEC4")
                accessors["WEIGHTS_1"] = writer.add_accessor(weights[used][:, 4:8].astype("f4"), 5126, "VEC4")
            indices = writer.add_accessor(inverse.reshape(-1).astype("u4"), 5125, "SCALAR")
            name = f"mesh 0.{skin_submeshes + sub}" if as_skin else f"mesh {group}.{sub}"
            doc["meshes"].append({"name": name, "primitives": [{"attributes": accessors, "indices": indices, "material": material_slot}]})
            doc["nodes"].append({"name": name, "mesh": len(doc["meshes"]) - 1, "skin": template["skin"], "extras": {a: True for a in attrs}})
            doc["scenes"][doc.get("scene", 0)]["nodes"].append(len(doc["nodes"]) - 1)
        if mesh.material.endswith("b0001_b.mtrl"):
            skin_submeshes = len(mesh.submeshes)
        if not as_skin:
            group += 1
    for prim in shell_skin:  # shell skin that matched no piece of the full-body model is cut-down skin: drop it
        if prim["node"] not in reused:
            detach_node(doc, prim["node"])
    print(f"kept {len(reused)} shell skin pieces with their shape keys, replaced {len(shell_skin) - len(reused)}")


def nearest_skin(positions: np.ndarray, cloth: dict, hr3: mb.Body, hr3_samples: mb.Samples, names: list[str]) -> tuple[np.ndarray, np.ndarray]:
    """Distance to and index of the nearest skin sample; with MFWSYNCSAFE, only skin on the same limb as the cloth vertex counts."""
    if not WSYNC_SAFE:
        return hr3_samples.tree.query(positions)
    cloth_family = mr.family(names, cloth["joints"], cloth["weights"])
    sample_family = mr.family(list(hr3.bones), hr3.joints, hr3.weights)[hr3.triangles[hr3_samples.faces, 0]]
    gap, near = np.full(len(positions), np.inf), np.zeros(len(positions), "i8")
    for family in np.unique(cloth_family):
        allowed, mine = np.where(sample_family == family)[0], np.where(cloth_family == family)[0]
        if len(allowed):
            found = cKDTree(hr3_samples.points[allowed]).query(positions[mine])
            gap[mine], near[mine] = found[0], allowed[found[1]]
    return gap, near


def synced_weights(positions: np.ndarray, cloth: dict, hr3: mb.Body, hr3_samples: mb.Samples, names: list[str]) -> tuple[np.ndarray, np.ndarray]:
    """Bone weights blended from the nearest HR3 skin triangle, out to the WSYNC distance. Keeps the original weights past it."""
    index = {name: i for i, name in enumerate(names)}
    table = np.array([index[b] if b in index else -1 for b in hr3.bones])
    if (table < 0).any():
        sys.exit("HR3 body bones are missing from the skeleton")
    gap, near = nearest_skin(positions, cloth, hr3, hr3_samples, names)
    triangle = hr3.triangles[hr3_samples.faces[near]]
    bary = hr3_samples.bary[near]
    limit = WSYNC / 1000
    x_ramp = 1.0 if WSYNC_SAFE and WSYNC_X <= 0 else np.clip((np.abs(positions[:, 0]) - WSYNC_X) / 0.05, 0, 1)  # MFWSYNCSAFE has no midline dip when the torso is included
    blend = np.clip((limit - gap) / (0.4 * limit), 0, 1) * x_ramp
    slots = SAFE_SLOTS if WSYNC_SAFE else cloth["joints"].shape[1]
    protected = np.array([WSYNC_SAFE and name.startswith(CLOTH_PHYSICS_BONES) for name in names])
    new_joints = np.pad(cloth["joints"], ((0, 0), (0, slots - cloth["joints"].shape[1])))
    new_weights = np.pad(cloth["weights"].astype("f8"), ((0, 0), (0, slots - cloth["joints"].shape[1])))
    for i in np.where(blend > 0)[0]:
        old_total = cloth["weights"][i].sum() or 1.0
        kept = float(sum(w for j, w in zip(cloth["joints"][i], cloth["weights"][i]) if protected[j])) / old_total
        acc: dict[int, float] = {}
        for b_corner, v in zip(bary[i], triangle[i]):
            total = hr3.weights[v].sum() or 1.0
            for joint, weight in zip(hr3.joints[v], hr3.weights[v]):
                if weight > 0:
                    acc[int(table[joint])] = acc.get(int(table[joint]), 0.0) + b_corner * float(weight) / total * blend[i] * (1 - kept)
        for joint, weight in zip(cloth["joints"][i], cloth["weights"][i]):
            if weight > 0:
                share = 1.0 if protected[joint] else 1 - blend[i]
                acc[int(joint)] = acc.get(int(joint), 0.0) + share * float(weight) / old_total
        ranked = sorted(acc.items(), key=lambda kv: -kv[1])[:slots]
        new_joints[i] = 0
        new_weights[i] = 0
        for slot, (joint, weight) in enumerate(ranked):
            new_joints[i, slot], new_weights[i, slot] = joint, weight
        new_weights[i] /= new_weights[i].sum()
    return new_joints, new_weights


def write_output(shell_doc: dict, shell_blob: bytes, source_doc: dict, source_blob: bytes, cloth: dict, new_positions: np.ndarray,
                 frames: list[tuple[np.ndarray, np.ndarray]], out_name: str, override: tuple[np.ndarray, np.ndarray] | None, race_3x3: np.ndarray) -> Path:
    writer = glb_raw.GlbWriter(shell_doc, shell_blob)
    doc = writer.doc
    skin_mdl = os.environ.get("SKINMDL")
    if skin_mdl:
        names, _ = glb_raw.joint_matrices(shell_doc, shell_blob)
        add_skin_from_mdl(writer, mdl_read.read_mdl(skin_mdl), names, new_positions, cloth["triangles"])
    shell_cloth = [p for p in glb_raw.primitives(doc) if not is_skin(p["material"])]
    if not shell_cloth:
        sys.exit("the shell has no cloth primitive to replace")
    start = 0
    for i, (prim, count) in enumerate(zip(cloth["prims"], cloth["counts"])):
        slot = shell_cloth[min(i, len(shell_cloth) - 1)]
        if i >= len(shell_cloth):  # more cloth pieces than the shell has: clone its last cloth node
            doc["meshes"].append(copy.deepcopy(doc["meshes"][slot["mesh"]]))
            doc["nodes"].append(dict(copy.deepcopy(doc["nodes"][slot["node"]]), mesh=len(doc["meshes"]) - 1))
            doc["scenes"][doc.get("scene", 0)]["nodes"].append(len(doc["nodes"]) - 1)
            slot = dict(slot, mesh=len(doc["meshes"]) - 1, node=len(doc["nodes"]) - 1)
        mesh = doc["meshes"][slot["mesh"]]
        target = mesh["primitives"][slot["prim"]]
        doc["nodes"][slot["node"]]["name"] = cloth_node_name(prim["name"], cloth["prims"], FIRST_CLOTH_GROUP)
        attributes = {}
        for name, accessor in prim["attributes"].items():
            attributes[name] = writer.copy_accessor(source_doc, source_blob, accessor)
        normals, tangents = frames[i]
        if override is not None:
            joints, weights = override[0][start:start + count], override[1][start:start + count]
            for slot_index, (name_j, name_w) in enumerate((("JOINTS_0", "WEIGHTS_0"), ("JOINTS_1", "WEIGHTS_1"))):
                if name_j in attributes or (slot_index == 1 and joints.shape[1] > 4):
                    attributes[name_j] = writer.add_accessor(joints[:, slot_index * 4:slot_index * 4 + 4].astype("u2"), 5123, "VEC4")
                    attributes[name_w] = writer.add_accessor(weights[:, slot_index * 4:slot_index * 4 + 4].astype("f4"), 5126, "VEC4")
        attributes["POSITION"] = writer.add_accessor(new_positions[start:start + count].astype("f4"), 5126, "VEC3")
        attributes["NORMAL"] = writer.add_accessor(normals.astype("f4"), 5126, "VEC3")
        attributes["TANGENT"] = writer.add_accessor(tangents.astype("f4"), 5126, "VEC4")
        target["attributes"] = attributes
        target["indices"] = writer.copy_accessor(source_doc, source_blob, prim["indices"])
        target.pop("targets", None)
        source_prim = source_doc["meshes"][prim["mesh"]]["primitives"][prim["prim"]]
        names_of_keys = (source_doc["meshes"][prim["mesh"]].get("extras") or {}).get("targetNames") or (prim["extras"] or {}).get("targetNames") or []
        if source_prim.get("targets"):  # the outfit's own shape keys: same deltas, turned and scaled by the race matrix of each vertex
            kept = []
            for morph in source_prim["targets"]:
                entry = {key: writer.copy_accessor(source_doc, source_blob, accessor) for key, accessor in morph.items() if key != "POSITION"}
                delta = glb_raw.read_accessor(source_doc, source_blob, morph["POSITION"]).astype("f8")
                entry["POSITION"] = writer.add_accessor((race_3x3[start:start + count] @ delta[..., None])[..., 0].astype("f4"), 5126, "VEC3")
                kept.append(entry)
            target["targets"] = kept
        material = doc["materials"][target["material"]]
        if material["name"] != prim["material"]:  # rename a copy, so another primitive using the shell's material keeps it
            doc["materials"].append(dict(copy.deepcopy(material), name=prim["material"]))
            target["material"] = len(doc["materials"]) - 1
        mesh.setdefault("extras", {})["targetNames"] = list(names_of_keys) if source_prim.get("targets") else []
        node = doc["nodes"][slot["node"]]
        node.pop("weights", None)
        node["extras"] = {k: v for k, v in (prim["extras"] or {}).items() if k != "targetNames"}  # the outfit's own tags, never the shell's
        if source_prim.get("targets"):
            node["extras"]["targetNames"] = list(names_of_keys)
        start += count
    for extra in shell_cloth[len(cloth["prims"]):]:
        detach_node(doc, extra["node"])
    path = OUT_DIR / out_name
    if path.exists():
        sys.exit(f"{path} already exists; pick a new name")
    writer.save(str(path))
    return path


def poke_rays(body: mb.Body, mask: np.ndarray, normals: np.ndarray, dense: bool) -> SkinRays:
    """Starting points and directions for the skin rays: the allowed skin vertices, or points every MFDENSEPOKE on allowed skin."""
    if not dense or DENSE_POKE <= 0:
        return SkinRays(body.positions[mask], normals[mask])
    samples = mb.sample_surface(body.positions, body.triangles, spacing=DENSE_POKE)
    keep = mask[body.triangles[samples.faces]].all(1)
    print(f"poke rays: {np.count_nonzero(keep)} dense points")
    return SkinRays(samples.points[keep], samples.normals[keep], outer_only=not DENSE_PUSH)


def warn_unused_options() -> None:
    """Say so when a setting has no effect because the option it depends on is off."""
    for active, message in ((DENSE_PUSH and DENSE_POKE <= 0, "MFDENSEPUSH needs MFDENSEPOKE"), (WSYNC_SAFE and not WSYNC, "MFWSYNCSAFE needs MFWSYNC"),
                            (DENSE_POKE > 0 and POKE_REACH <= 0, "MFDENSEPOKE needs MFPOKE above 0"), (DENSE_POKE > 0 and FINISH == 0 and not DENSE_PUSH, "MFDENSEPOKE needs MFFINISH or MFDENSEPUSH"),
                            (FINISH_MAX > 0 and FINISH == 0, "MFFINISHMAX needs MFFINISH"), (WSYNC_SAFE and bool(W_INPAINT), "MFWINPAINT overwrites what MFWSYNCSAFE protects")):
        if active:
            print(f"warning: {message}")


def _legs(paths: list[str]) -> set[str]:
    return {os.path.realpath(p) for p in paths if p.endswith("_dwn.mdl")}


def check_weight_source(hr3_paths: tuple[str, ...]) -> None:
    """Refuse MFWSYNC set-ups that copy weights from the wrong body or across limbs (review F2, F5).

    MFWSYNC copies weights from HR3BODY, not from SKINMDL. When SKINMDL is a legs option (_dwn.mdl) that HR3BODY does
    not contain, the cloth gets one legs body's weights while the game draws another. MFWSYNCX=0 without MFWSYNCSAFE
    copies from the nearest skin on any limb, across the hips. MFWSYNCLEGACY=1 turns both refusals into warnings, only
    to rebuild a recorded recipe exactly.
    """
    if not WSYNC:
        return
    problems = []
    skin_mdl = os.environ.get("SKINMDL", "")
    if skin_mdl.endswith("_dwn.mdl") and _legs([skin_mdl]) - _legs(list(hr3_paths)):
        problems.append(f"SKINMDL {skin_mdl} is a legs option that HR3BODY (the body MFWSYNC copies weights from) does not contain; "
                        "set HR3BODY=<top.mdl>,<the SKINMDL file>")
    if WSYNC_X <= 0 and not WSYNC_SAFE:
        problems.append("MFWSYNCX=0 without MFWSYNCSAFE=1 copies weights across limbs at the hips; add MFWSYNCSAFE=1")
    for problem in problems:
        if not WSYNC_LEGACY:
            sys.exit(f"refusing: {problem} (MFWSYNCLEGACY=1 only to rebuild an old recipe)")
        print(f"warning (MFWSYNCLEGACY): {problem}")


def main() -> None:
    warn_unused_options()
    outfit_path, shell_path, out_name = sys.argv[1:4]
    if (OUT_DIR / out_name).exists():
        sys.exit(f"{OUT_DIR / out_name} already exists; pick a new name")
    check_weight_source(tuple(os.environ.get("HR3BODY", ",".join(mb.DEFAULT_HR3)).split(",")))
    outfit_doc, outfit_blob = glb_raw.load(outfit_path)
    shell_doc, shell_blob = glb_raw.load(shell_path)
    cloth = cloth_arrays(outfit_doc, outfit_blob)
    names, rest_tbse = glb_raw.joint_matrices(outfit_doc, outfit_blob)
    parents = glb_raw.joint_parents(outfit_doc)
    shell_names, rest_hr3 = glb_raw.joint_matrices(shell_doc, shell_blob)
    if shell_names != names:
        sys.exit("outfit and shell skeletons list different joints")
    table = mb.RaceTable(names, parents, rest_tbse, rest_hr3)
    tbse_paths = tuple(os.environ.get("TBSEBODY", ",".join(mb.DEFAULT_TBSE)).split(","))
    hr3_paths = tuple(os.environ.get("HR3BODY", ",".join(mb.DEFAULT_HR3)).split(","))
    tbse = mb.load_body(tbse_paths)
    hr3 = mb.load_body(hr3_paths)

    placed_body = mb.apply_matrices(tbse.positions, table.blend(tbse.bones, tbse.joints, tbse.weights))
    hr3_samples = mb.sample_surface(hr3.positions, hr3.triangles)
    moved_body = mb.register(tbse, placed_body, hr3_samples, SCHEDULE, step=0.7, max_move=0.15)
    body_move = moved_body - placed_body
    placed_samples = mb.sample_surface(placed_body, tbse.triangles)

    placed_cloth = mb.apply_matrices(cloth["positions"], table.blend(names, cloth["joints"], cloth["weights"]))
    normals_placed = mb.vertex_normals(placed_cloth, cloth["triangles"])
    move, gap = mb.body_field(placed_cloth, normals_placed, placed_samples, body_move, tbse.triangles, FILTER)
    fade = np.clip((FADE_FAR - np.nan_to_num(gap, nan=FADE_FAR)) / (FADE_FAR - FADE_NEAR), 0, 1)
    move *= (fade * fade * (3 - 2 * fade))[:, None]
    wrapped = placed_cloth + blur_moves(placed_cloth, move, BLUR)
    lengths = np.linalg.norm(wrapped - placed_cloth, axis=1) * 1000
    print(f"wrap: {len(wrapped)} cloth vertices, body move mm p50/p95/max {np.percentile(lengths, 50):.1f} {np.percentile(lengths, 95):.1f} {lengths.max():.1f}")

    if SOLE_Y > 0:  # the race table stretches feet vertically and tips the sole; put the ground-contact part back at its outfit height
        original_y = cloth["positions"][:, 1]
        share = np.clip((original_y - SOLE_Y) / SOLE_Y, 0, 1)
        share = share * share * (3 - 2 * share)
        wrapped = np.c_[wrapped[:, 0], original_y * (1 - share) + wrapped[:, 1] * share, wrapped[:, 2]]
    clear_body = without_dropped_bones(mb.load_body(tuple(CLEAR_BODY.split(",")))) if CLEAR_BODY else hr3
    clear_samples = mb.sample_surface(clear_body.positions, clear_body.triangles) if CLEAR_BODY else hr3_samples
    dominant = clear_body.joints[np.arange(len(clear_body.joints)), clear_body.weights.argmax(1)]
    poke_normals = mb.vertex_normals(clear_body.positions, clear_body.triangles)
    poke_mask = np.array([not any(clear_body.bones[j].startswith(b) for b in NO_POKE_BONES) for j in dominant])
    neck_height = rest_hr3[names.index("j_kubi")][1, 3] - NECK_MARGIN
    poke_mask &= clear_body.positions[:, 1] < neck_height  # the neck's cut end cap faces up; a push there flares the collar
    poke_mask &= (clear_body.positions[:, 1] >= POKE_Y[0]) & (clear_body.positions[:, 1] <= POKE_Y[1])
    poke_mask &= np.abs(poke_normals[:, 1]) < VERTICAL_LIMIT  # same for any cut end facing up or down, like the waist edge of the torso skin
    final = clearance_pass(wrapped, clear_samples, cloth["triangles"], poke_rays(clear_body, poke_mask, poke_normals, DENSE_PUSH), poke_rays(clear_body, poke_mask, poke_normals, True))
    signed, _ = signed_clearance(final, clear_samples)
    print(f"final clearance mm p1/p5/p50 {np.percentile(signed * 1000, 1):.1f} {np.percentile(signed * 1000, 5):.1f} {np.percentile(signed * 1000, 50):.1f}; under skin {np.count_nonzero(signed < 0)}")

    frames, start = [], 0
    for prim, count in zip(cloth["prims"], cloth["counts"]):
        old = cloth["positions"][start:start + count]
        new = final[start:start + count]
        triangles = glb_raw.read_accessor(outfit_doc, outfit_blob, prim["indices"]).astype("i8").reshape(-1, 3)
        normals = glb_raw.read_accessor(outfit_doc, outfit_blob, prim["attributes"]["NORMAL"]).astype("f8")
        tangents = glb_raw.read_accessor(outfit_doc, outfit_blob, prim["attributes"]["TANGENT"]).astype("f8")
        frames.append(rotate_frames(old, new, triangles, normals, tangents))
        start += count
    override = synced_weights(final, cloth, hr3, hr3_samples, names) if WSYNC else None
    if W_INPAINT:
        near, facing, far, waist = (float(x) for x in W_INPAINT.split(","))
        settings = wi.InpaintSettings(near / 1000, facing, far / 1000, waist)
        start_joints, start_weights = override if override is not None else (cloth["joints"], cloth["weights"].astype("f8"))
        override = wi.inpainted_weights(final, cloth["triangles"], start_joints, start_weights, clear_body, clear_samples, names, parents, settings)
    race_3x3 = table.blend(names, cloth["joints"], cloth["weights"])[:, :3, :3]
    path = write_output(shell_doc, shell_blob, outfit_doc, outfit_blob, cloth, final, frames, out_name, override, race_3x3)
    np.savez(OUT_DIR / (Path(out_name).stem + "_debug.npz"), final=final, placed=placed_cloth, wrapped=wrapped, tri=cloth["triangles"], moved_body=moved_body, placed_body=placed_body)
    print("wrote", path)


if __name__ == "__main__":
    main()
