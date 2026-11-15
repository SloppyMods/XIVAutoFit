"""Build "Mother Moon Glow - Head [Miqo'te F]": a small Penumbra mod that makes the head match the Mother Moon body at the neck.
Source mods and collections are only read; nothing is written under /mnt/STORAGE/Penumbra or ~/.xlcore.

    python3 mothermoon_face.py            build builds/_mothermoon_face/ (refuses if its mod/ folder already exists)
    python3 mothermoon_face.py --update   rebuild, keeping the mod's Identifier
    python3 mothermoon_face.py --face 0101 --no-render   other Miqo'te F face id / skip the Blender pictures

Step 1 (read only) reads SloppyMods's Penumbra collections, finds the collections with a Mother Moon Glow copy enabled, and works out which
face colour texture, normal and skin material really win for the face (default 0101, Keeper face 1) and which SATSU option is
selected, plus any other mod mapping those paths. Result: winning.json. If the winning files cannot be identified or read, the
script exits non-zero and builds nothing.

Step 2 measures the seam (seam.json): the head's neck ring colour against the body's skin just below it (builds/_mothermoon/diffuse.tex
through the body UVs), and the skin material constants of head and body.

Step 3 builds the new face colour texture (the neck shifted to the body's skin colour, faded out up the neck along the 3D surface
under the jaw, as in face_black_neck.py), the head skin materials (the face material with only the body's wet-look constants moved:
plain, Wet skin, Wet subtle, Wet strong) and the mod folder, then renders before/after pictures in Blender.
"""
import argparse
import hashlib
import json
import struct
import subprocess
import sys
import types
import uuid
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

sys.dont_write_bytecode = True  # importing the helpers must not write tools/__pycache__/
sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402

import face_black_neck as fbn  # noqa: E402  (neck_weight, main_piece: the surface-following fade)
import mdl_read  # noqa: E402
import mothermoon_package as mmp  # noqa: E402  (WET_CONSTANTS, WET_STRENGTHS, material readers; not edited)
import tex_io  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
MAIN = Path("/home/you/Projects/ffxiv-tools/XIVAutoFit")
BODY_BUILD = ROOT / "builds" / "_mothermoon"
OUT = ROOT / "builds" / "_mothermoon_face"
MOD = OUT / "mod"
PENUMBRA = Path("/mnt/STORAGE/Penumbra")
COLLECTIONS = Path.home() / ".xlcore" / "pluginConfigs" / "Penumbra" / "collections"
SATSU = "[SATSU] Alphinaud_For_Miqo'te_Females"
BODY_MDL = PENUMBRA / "[HS] Bibo+ (Bibo+ Base Install)/files/breasts - small clothes/nude - small/chara/equipment/e0000/model/c0201e0000_top.mdl"
BODY_RACE = "c0201"  # Miqo'te F's body is the c0201 (Midlander shape) Bibo+ body
MM_COPY = "Mother Moon Glow ["
MM_GROUP = "Mother Moon"
DEFAULT_FACE = "0101"  # SloppyMods: Keeper face 1 (Glamourer designs, memory note of the shark teeth job)
FADE_LEN = 0.025  # metres of surface over which the shift fades out, ending at the jaw line of face_black_neck.py
RING_BAND = 0.04  # the neck ring = open-edge vertices up to this far above the lowest one
BODY_BAND = 0.045  # body skin is sampled this far below the ring
PATCH = 2  # texture sampling radius around a vertex (5x5 median)
STEP_LIMIT = 2.0  # neck colour step (0..255) above which a role copy "still shows a step"
MOD_NAME = "Mother Moon Glow - Head [Miqo'te F]"
PREFIX = "mothermoonhead_"
TEX_LOCAL = f"{PREFIX}face_base.tex"
ID_SPACE = uuid.UUID("c3d1a6e4-52b7-4f08-9a1d-7e6b0f94d2a3")
GROUP_NAME = "Wet look"
OPTION_NAMES = ("Wet skin", "Wet subtle", "Wet strong")  # same names as the body mod; bits 0, 1, 2
OPTION_DESCRIPTIONS = (
    "The body's wet skin look on the head: its glisten kept, its extra brightening turned down to a balanced level. Off: the plain face material.",
    "Only with Wet skin on: the glisten with the extra brightening taken out completely. Wins over Wet strong.",
    "Only with Wet skin on: more of Sakura's brightening left in (about three quarters of the way back). Ignored if Wet subtle is on.",
)
VARIANTS = ("plain",) + tuple(mmp.WET_STRENGTHS)  # plain, wetsubtle, wet, wetstrong


def fail(message: str) -> None:
    sys.exit(f"mothermoon_face: {message}")


def read_json(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


# ---------------------------------------------------------------- step 1: what wins in SloppyMods's collections

def target_paths(face: str) -> dict:
    base = f"chara/human/c0801/obj/face/f{face}"
    return {
        "colour_texture": f"{base}/texture/c0801f{face}_fac_base.tex",
        "normal": f"{base}/texture/c0801f{face}_fac_norm.tex",
        "mask": f"{base}/texture/c0801f{face}_fac_mask.tex",
        "skin_material": f"{base}/material/mt_c0801f{face}_fac_a.mtrl",
        "model": f"{base}/model/c0801f{face}_fac.mdl",
    }


def load_collections() -> dict:
    found = {}
    for path in sorted(COLLECTIONS.glob("*.json")):
        data = read_json(path)
        if "Id" in data and "Settings" in data:
            found[data["Id"]] = data
    if not found:
        fail(f"no Penumbra collections found in {COLLECTIONS}")
    return found


class Mods:
    """Parsed mods from /mnt/STORAGE/Penumbra: default files and groups (inline in meta.json, or the older group_*.json files)."""

    def __init__(self):
        self.cache = {}

    def get(self, name: str):
        if name not in self.cache:
            self.cache[name] = self._load(name)
        return self.cache[name]

    @staticmethod
    def _load(name: str):
        folder = PENUMBRA / name
        if not (folder / "meta.json").is_file():
            return None
        meta = read_json(folder / "meta.json")
        if "Groups" in meta or "DefaultData" in meta or meta.get("FileVersion", 0) >= 4:  # groups inline in meta.json
            return {"default": meta.get("DefaultData") or {}, "groups": meta.get("Groups", []), "meta": meta}
        default = read_json(folder / "default_mod.json") if (folder / "default_mod.json").is_file() else {}
        groups = [read_json(p) for p in sorted(folder.glob("group_*.json"))]
        return {"default": default, "groups": groups, "meta": meta}


def selected_containers(group: dict, value: int) -> list:
    kind = group.get("Type")
    options, containers = group.get("Options", []), group.get("Containers", [])
    if kind == "Single":
        return [options[value]] if 0 <= value < len(options) else []
    if kind == "Multi":
        chosen = [o for i, o in enumerate(options) if value >> i & 1]
        return sorted(chosen, key=lambda o: o.get("Priority", 0))
    if kind == "Combining":
        return [containers[value]] if 0 <= value < len(containers) else []
    return []


def mod_files(mod: dict, settings: dict) -> tuple[dict, dict]:
    """(game path lower -> (mod file, how it is picked), selected option names per group) for one mod under one collection setting."""
    files, picked = {}, {}
    for path, local in (mod["default"].get("Files") or {}).items():
        files[path.lower()] = (local, "default files")
    for path, local in (mod["default"].get("FileSwaps") or {}).items():
        files[path.lower()] = (local, "default swap")
    for group in sorted(mod["groups"], key=lambda g: g.get("Priority", 0)):
        value = settings.get(group["Name"], group.get("DefaultSettings", 0))
        chosen = selected_containers(group, value)
        picked[group["Name"]] = [c.get("Name") for c in chosen]
        for part in chosen:
            for path, local in (part.get("Files") or {}).items():
                files[path.lower()] = (local, f"group {group['Name']} / {part.get('Name')}")
            for path, local in (part.get("FileSwaps") or {}).items():
                files[path.lower()] = (local, f"group {group['Name']} / {part.get('Name')} (swap)")
    return files, picked


def layers(collections: dict, cid: str, depth: int = 0) -> list:
    """[(depth, collection name, settings)]: the collection itself, then what it inherits (lower priority than anything of its own)."""
    data = collections[cid]
    out = [(depth, data["Name"], data["Settings"])]
    for parent in data.get("Inheritance", []):
        if parent in collections:
            out += layers(collections, parent, depth + 1)
    return out


def enabled_mods(collections: dict, cid: str) -> list:
    """[(rank, collection name, mod dir, entry)] for every enabled mod, an explicit entry in a nearer layer shadowing farther ones."""
    seen, out = set(), []
    for rank, name, settings in layers(collections, cid):
        for mod, entry in settings.items():
            if mod in seen:
                continue
            seen.add(mod)
            if entry.get("Enabled"):
                out.append((rank, name, mod, entry))
    return out


def decode_copy(mod: dict, entry: dict) -> dict:
    group = next((g for g in mod["groups"] if g["Name"] == MM_GROUP), None)
    if group is None:
        return {"error": "no 'Mother Moon' group in the copy"}
    mask = (entry.get("Settings") or {}).get(MM_GROUP, group.get("DefaultSettings", 0))
    names = [o["Name"] for o in group["Options"]]
    on = [n for i, n in enumerate(names) if mask >> i & 1]
    wet = "Wet skin" in on
    variant = ("wetsubtle" if "Wet subtle" in on else "wetstrong" if "Wet strong" in on else "wet") if wet else "plain"
    container = group["Containers"][mask] if mask < len(group["Containers"]) else {}
    diffuse = (container.get("Files") or {}).get("chara/bibo_mid_base.tex")
    return {"setting": mask, "toggles_on": on, "wet_variant": variant, "diffuse_file": diffuse,
            "wet_ignored": [n for n in ("Wet subtle", "Wet strong") if n in on and not wet]}


def candidates(mods: Mods, collections: dict, cid: str, paths: dict) -> dict:
    """Every enabled mod mapping one of the paths: {role: [candidate, ...]} best first (nearer layer, then higher priority)."""
    lowered = {role: p.lower() for role, p in paths.items()}
    found = {role: [] for role in paths}
    for rank, cname, mod_dir, entry in enabled_mods(collections, cid):
        mod = mods.get(mod_dir)
        if mod is None:
            continue
        files, picked = mod_files(mod, entry.get("Settings") or {})
        for role, low in lowered.items():
            if low in files:
                local, how = files[low]
                found[role].append({"mod": mod_dir, "mod_priority": entry.get("Priority", 0), "layer": rank, "layer_collection": cname,
                                    "file": local, "how": how, "options": picked})
    for role in found:
        found[role].sort(key=lambda c: (c["layer"], -c["mod_priority"]))
    return found


def resolve(face: str) -> dict:
    collections, mods = load_collections(), Mods()
    paths = target_paths(face)
    out = {"face": face, "game_paths": paths, "collections": {}, "mother_moon_copies": [], "missing_mods": [], "other_collections": {}}
    for cid, data in collections.items():
        copies = [(m, e) for _r, _n, m, e in enabled_mods(collections, cid) if MM_COPY in m]
        for _r, _n, mod_dir, _e in enabled_mods(collections, cid):
            if mods.get(mod_dir) is None and mod_dir not in out["missing_mods"]:
                out["missing_mods"].append(mod_dir)
        cands = candidates(mods, collections, cid, paths)
        if not copies:  # collections without a Mother Moon copy: only note head mods other than SATSU
            extra = {role: [c["mod"] for c in found if c["mod"] != SATSU] for role, found in cands.items()}
            if any(extra.values()):
                out["other_collections"][data["Name"]] = extra
            continue
        out["collections"][data["Name"]] = {
            "id": cid, "inherits": [collections[p]["Name"] for p in data.get("Inheritance", []) if p in collections],
            "winners": {role: (c[0] if c else None) for role, c in cands.items()},
            "all_candidates": {role: [dict(x, wins=i == 0) for i, x in enumerate(c)] for role, c in cands.items()},
        }
        for mod_dir, entry in copies:
            mod = mods.get(mod_dir)
            info = decode_copy(mod, entry) if mod else {"error": "mod folder missing"}
            out["mother_moon_copies"].append(dict(info, collection=data["Name"], copy_dir=mod_dir, copy_name=mod["meta"].get("Name") if mod else None))
    if not out["collections"]:
        fail("no collection has a Mother Moon Glow copy enabled; cannot tell which face files win")
    return out


def pick_winners(info: dict) -> dict:
    """The winning mod file per role, if every collection agrees on it; the disagreements and non-SATSU winners are listed."""
    picked, notes = {}, []
    for role in ("colour_texture", "normal", "mask", "skin_material", "model"):
        votes = Counter()
        for cname, col in info["collections"].items():
            w = col["winners"][role]
            if w is None:
                notes.append(f"{role}: no mod maps it in collection {cname}")
                continue
            votes[(w["mod"], w["file"])] += 1
        if not votes:
            fail(f"no winning file for the face {role} ({info['game_paths'][role]}) in any collection")
        (mod, local), count = votes.most_common(1)[0]
        picked[role] = {"game_path": info["game_paths"][role], "mod": mod, "file": local, "collections_agreeing": count,
                        "collections_total": len(info["collections"])}
        if len(votes) > 1:
            notes.append(f"{role}: collections disagree: {[(m, f, n) for (m, f), n in votes.items()]}")
        if mod != SATSU:
            notes.append(f"{role}: winner is {mod}, not the SATSU mod")
    return {"winning": picked, "notes": notes}


def satsu_options(info: dict, face: str) -> dict:
    """Per collection where SATSU wins the colour texture: the group of this face and the option selected in it."""
    out = {}
    for cname, col in info["collections"].items():
        w = col["winners"]["colour_texture"]
        if w and w["mod"] == SATSU:
            for group, chosen in w["options"].items():
                if group.lower().startswith(f"face {int(face)} "):
                    out[cname] = {"group": group, "option": chosen[0] if chosen else None}
    return out


def overriding_mods(info: dict) -> list:
    """Mods other than SATSU that map the head paths, with what they do to the winner in each collection."""
    seen = {}
    for cname, col in info["collections"].items():
        for role, cands in col["all_candidates"].items():
            for c in cands:
                if c["mod"] != SATSU:
                    row = seen.setdefault((c["mod"], role), {"mod": c["mod"], "role": role, "collections": []})
                    row["collections"].append({"collection": cname, "wins": c["wins"], "mod_priority": c["mod_priority"]})
    return list(seen.values())


def satsu_file(winning: dict, role: str) -> Path:
    item = winning[role]
    if item["mod"] != SATSU:
        fail(f"the winning {role} comes from {item['mod']}, not the SATSU mod: {item['file']}")
    path = PENUMBRA / item["mod"] / item["file"].replace("\\", "/")
    if not path.is_file():
        fail(f"the winning {role} file is missing: {path}")
    return path


def geometry_model(info: dict, winning: dict, face: str, satsu_opts: dict) -> tuple[Path, dict]:
    """The model whose UVs and positions drive the fade: the winning one if tools/mdl_read.py can read it, else the SATSU option's original."""
    wanted = PENUMBRA / winning["model"]["mod"] / winning["model"]["file"].replace("\\", "/")
    report = {"winning_model": str(wanted)}
    try:
        mdl_read.read_mdl(str(wanted))
        report["used"] = str(wanted)
        return wanted, report
    except Exception as error:  # the shark-teeth models are not readable by mdl_read
        report["winning_model_unreadable"] = f"{type(error).__name__}: {error}"
    chosen = next(iter(satsu_opts.values()))
    original = PENUMBRA / SATSU / chosen["group"].lower() / chosen["option"].lower() / f"chara/human/c0801/obj/face/f{face}/model/c0801f{face}_fac.mdl"
    if not original.is_file():
        fail(f"the winning model is unreadable and there is no original at {original}")
    report["used"] = str(original)
    report["why"] = "same SATSU face and option, the model before the shark teeth were grafted on; the neck is untouched by that graft"
    return original, report


# ---------------------------------------------------------------- step 2: measuring the seam

def face_mesh(model: Path):
    return next(m for m in mdl_read.read_mdl(str(model)).meshes if "fac_a" in m.material)


def neck_ring(mesh) -> np.ndarray:
    """Vertex indices of the neck's open bottom edge (open-edge vertices of the head piece, up to RING_BAND above the lowest)."""
    pos, tris = mesh.positions, mesh.triangles[fbn.main_piece(mesh.positions, mesh.triangles)]
    _, weld = np.unique(np.round(pos, 5), axis=0, return_inverse=True)
    weld = weld.ravel()
    edges = Counter()
    for tri in tris:
        for a, b in ((0, 1), (1, 2), (2, 0)):
            edges[tuple(sorted((weld[tri[a]], weld[tri[b]])))] += 1
    open_ids = {v for edge, n in edges.items() if n == 1 for v in edge}
    open_idx = np.array([i for i in range(len(pos)) if weld[i] in open_ids])
    low = pos[open_idx, 1].min()
    return open_idx[pos[open_idx, 1] <= low + RING_BAND]


def patch_median(texture: np.ndarray, uv: np.ndarray) -> np.ndarray:
    height, width = texture.shape[:2]
    out = []
    for u, v in uv:
        x, y = int(np.clip(u * width, 0, width - 1)), int(np.clip(v * height, 0, height - 1))
        block = texture[max(y - PATCH, 0):y + PATCH + 1, max(x - PATCH, 0):x + PATCH + 1, :3]
        out.append(np.median(block.reshape(-1, 3), 0))
    return np.array(out)


def ring_colour(texture: np.ndarray, mesh, ring: np.ndarray) -> np.ndarray:
    """Median colour of the head's neck ring in a face colour texture (per-vertex 5x5 medians, then the median over the ring)."""
    return np.median(patch_median(texture, mesh.uv[ring]), 0)


def body_skin_colour(texture: np.ndarray, body, ring_y: float) -> tuple[np.ndarray, int]:
    """Median skin colour of the body just under the ring: neck vertices in a band below it, tattoo ink (blue-ish) left out."""
    pos = body.positions
    uv = body.uv.copy()
    uv[:, 1] %= 1.0  # the body's v runs -1..0
    chosen = np.where((pos[:, 1] > ring_y - BODY_BAND) & (pos[:, 1] < ring_y) & (np.abs(pos[:, 0]) < 0.1))[0]
    colours = patch_median(texture, uv[chosen])
    skin = colours[(colours[:, 0] >= colours[:, 1]) & (colours[:, 1] >= colours[:, 2]) & (colours[:, 0] - colours[:, 2] >= 25)]
    if len(skin) < 5:
        fail(f"only {len(skin)} skin-coloured body samples under the neck ring; cannot measure the body colour")
    return np.median(skin, 0), len(skin)


def mean_abs(a, b) -> float:
    return float(np.abs(np.asarray(a, float) - np.asarray(b, float)).mean())


def copy_necks(info: dict, body, ring_y: float, built: np.ndarray) -> None:
    """Add the neck skin colour of each role copy (the diffuse its toggles map) and its step against the colour this mod is built for."""
    cache = {}
    for item in info["mother_moon_copies"]:
        local = item.get("diffuse_file")
        if not local:
            continue
        path = PENUMBRA / item["copy_dir"] / local.replace("\\", "/")
        if path not in cache:
            cache[path] = body_skin_colour(tex_io.read_bgra(str(path)), body, ring_y)[0]
        item["neck_skin_colour"] = [float(v) for v in cache[path]]
        item["neck_step_vs_built"] = mean_abs(cache[path], built)
        item["still_shows_step"] = item["neck_step_vs_built"] > STEP_LIMIT


def material_table(face_plain: bytes, mid_sakura: bytes, body_plain: bytes, out_face: dict) -> dict:
    face, sakura, body = mmp.material_values(face_plain), mmp.material_values(mid_sakura), mmp.material_values(body_plain)
    table = {}
    for cid, (name, role, action, _why) in mmp.WET_CONSTANTS.items():
        table[cid] = {"name": name, "role": role, "action": action, "face_plain": face.get(cid), "body_plain": body.get(cid),
                      "sakura_wet": sakura.get(cid), "in_face_material": cid in face}
        for variant, data in out_face.items():
            table[cid][f"face_{variant}"] = mmp.material_values(data).get(cid)
    return table


# ---------------------------------------------------------------- step 3: the texture, the materials, the mod

def build_weights(model: Path) -> tuple[np.ndarray, int]:
    fbn.MODEL = str(model)  # face_black_neck.neck_weight reads the face model from this module constant
    args = types.SimpleNamespace(cutoff=1.395, slope=-0.3, ramp=FADE_LEN, chin_z=0.08, chin_dip=0.012, ear_x=0.07)
    weight, count = fbn.neck_weight(args)
    return weight * weight * (3 - 2 * weight), count  # smoothstep: no kink where the fade starts and ends


def shift_texture(source: np.ndarray, weight: np.ndarray, delta: np.ndarray) -> np.ndarray:
    out = source.copy()
    moved = source[..., :3].astype(np.float32) + weight[..., None] * delta.astype(np.float32)
    out[..., :3] = np.clip(np.rint(moved), 0, 255).astype("u1")
    return out


def check_texture(path: Path, source: np.ndarray, out: np.ndarray, weight: np.ndarray) -> dict:
    back = tex_io.read_bgra(str(path))
    changed = np.any(out != source, axis=-1)
    expect = ((back.astype(np.uint32).reshape(back.shape[0] // 2, 2, back.shape[1] // 2, 2, 4).sum((1, 3)) + 2) // 4).astype("u1")
    return {
        "texels_with_weight": int((weight > 0).sum()), "texels_changed": int(changed.sum()),
        "outside_fade_identical": bool(np.array_equal(out[weight <= 0], source[weight <= 0])),
        "alpha_identical": bool(np.array_equal(out[..., 3], source[..., 3])),
        "readback_identical": bool(np.array_equal(back, out)),
        "mip1_exact": bool(np.array_equal(tex_io.read_mip(str(path), 1), expect)),
        "mip_count": tex_io.read_header(str(path))[3],
    }


def wet_face_material(face: bytes, sakura: bytes, kept: float) -> bytes:
    """The face material with only the body's wet-look constants moved, in place: 'keep' constants take Sakura's value, 'reduce' ones
    move from the face's own value towards Sakura's by the share `kept`. Constants the face material lacks are not added."""
    slots, sakura_slots = mmp.material_slots(face), mmp.material_slots(sakura)
    out = bytearray(face)
    for cid, (_name, _role, action, _why) in mmp.WET_CONSTANTS.items():
        if cid not in slots or slots[cid][1] != sakura_slots[cid][1]:
            continue
        offset, count = slots[cid]
        own = struct.unpack_from(f"<{count}f", face, offset)
        theirs = struct.unpack_from(f"<{count}f", sakura, sakura_slots[cid][0])
        values = theirs if action == "keep" else tuple(p + kept * (s - p) for p, s in zip(own, theirs))
        struct.pack_into(f"<{count}f", out, offset, *values)
    return bytes(out)


def stable_id(*names: str) -> str:
    return str(uuid.uuid5(ID_SPACE, "/".join(names)))


def variant_for(mask: int) -> str:
    """Same rule as the body mod: Wet skin on picks a wet material (Wet subtle wins over Wet strong); without it, the plain one."""
    if not mask & 1:
        return "plain"
    return "wetsubtle" if mask & 2 else "wetstrong" if mask & 4 else "wet"


def container_name(mask: int) -> str:
    return " + ".join(n.lower() for i, n in enumerate(OPTION_NAMES) if mask >> i & 1) or "none"


def default_mask(info: dict) -> tuple[int, dict]:
    """Default toggles: the most common effective wet setting among the role copies (a tie goes to the wetter one)."""
    order = {"plain": 0, "wet": 1, "wetsubtle": 2, "wetstrong": 3}
    votes = Counter(c["wet_variant"] for c in info["mother_moon_copies"] if "wet_variant" in c)
    chosen = max(votes, key=lambda v: (votes[v], order[v])) if votes else "plain"
    return {"plain": 0, "wet": 1, "wetsubtle": 3, "wetstrong": 5}[chosen], dict(votes)


def description(info: dict, winning: dict, face: str) -> str:
    others = sorted({r["mod"] for r in overriding_mods(info)} | {m for col in info["other_collections"].values() for mods in col.values() for m in mods})
    lines = [
        f"Head half of the Mother Moon look for Miqo'te F face {face} (SATSU Alphinaud). Maps only the face colour texture and the face "
        "skin material.\n",
        f"Colour: the neck skin of {SATSU}'s face texture is shifted to the Mother Moon body's skin colour at the seam and fades out up "
        "the neck, ending under the jaw. Face, ears and the alpha channel are untouched.",
        "Wet look: Wet skin / Wet subtle / Wet strong give the head the same wet-skin settings as the body mod (Wet subtle wins over "
        "Wet strong; both only count with Wet skin on). Off: the plain face material. No glow is added to the head.\n",
        f"Priority: this mod must sit at a HIGHER priority than {SATSU} in the collection (that mod supplies the face colour and material "
        "it replaces), or the SATSU files win.",
    ]
    if others:
        lines.append("Other mods in your collections that map the same head paths (keep them at a lower priority than this mod, or off): " + ", ".join(others) + ".")
    else:
        lines.append("No other mod in your Mother Moon collections maps these head paths.")
    lines.append("Built for the un-recoloured Mother Moon body (neck skin from its diffuse texture).")
    return "\n".join(lines)


def build_mod(info: dict, winning: dict, face: str, update: bool, tex_bytes: bytes, materials: dict) -> str:
    identifier = read_json(MOD / "meta.json")["Identifier"] if update and (MOD / "meta.json").is_file() else str(uuid.uuid4())
    (MOD / "chara").mkdir(parents=True, exist_ok=True)
    wanted = {TEX_LOCAL} | {f"{PREFIX}{v}_{Path(winning['skin_material']['game_path']).name}" for v in VARIANTS}
    for stale in (MOD / "chara").glob(f"{PREFIX}*"):
        if stale.name not in wanted:
            stale.unlink()
    (MOD / "chara" / TEX_LOCAL).write_bytes(tex_bytes)
    material_name = Path(winning["skin_material"]["game_path"]).name
    for variant, data in materials.items():
        (MOD / "chara" / f"{PREFIX}{variant}_{material_name}").write_bytes(data)
    paths = winning
    colour_game, material_game = paths["colour_texture"]["game_path"], paths["skin_material"]["game_path"]
    default_files = {colour_game: f"chara\\{TEX_LOCAL}"}
    containers = [{"Name": container_name(m), "Files": {material_game: f"chara\\{PREFIX}{variant_for(m)}_{material_name}"}, "FileSwaps": {}, "Manipulations": []}
                  for m in range(2 ** len(OPTION_NAMES))]
    mask, _votes = default_mask(info)
    group = {
        "Version": 0, "Name": GROUP_NAME, "Description": f"Toggle {', '.join(OPTION_NAMES[:-1])} and {OPTION_NAMES[-1]} independently.",
        "Priority": 0, "Image": "", "Page": 0, "Type": "Combining", "Id": stable_id(GROUP_NAME), "DefaultSettings": mask,
        "Options": [{"Id": stable_id(GROUP_NAME, n), "Name": n, "Description": d} for n, d in zip(OPTION_NAMES, OPTION_DESCRIPTIONS)],
        "Containers": containers,
    }
    meta = {
        "FileVersion": 3, "Identifier": identifier, "LastWrite": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.0000000Z"),
        "Name": MOD_NAME, "Author": "Mother Moon head match (edit of the SATSU Alphinaud face)", "Description": description(info, winning, face),
        "Image": "", "Version": "1.0", "Website": "", "ModTags": ["Miqote", "Face", "Skin"],
    }
    (MOD / "meta.json").write_text(json.dumps(meta, indent="\t", ensure_ascii=False), encoding="utf-8")
    (MOD / "default_mod.json").write_text(json.dumps({"Name": None, "Description": None, "Image": None, "Files": default_files,
                                                      "FileSwaps": {}, "Manipulations": []}, indent="\t"), encoding="utf-8")
    for old in MOD.glob("group_*.json"):
        old.unlink()
    (MOD / "group_001_wet look.json").write_text(json.dumps(group, indent="\t", ensure_ascii=False), encoding="utf-8")
    return identifier


def verify_mod() -> dict:
    """Every file path the mod maps exists inside the mod folder; the three wet options and the Identifier are there."""
    meta, default = read_json(MOD / "meta.json"), read_json(MOD / "default_mod.json")
    group = read_json(next(MOD.glob("group_*.json")))
    mapped = list((default.get("Files") or {}).values())
    for container in group["Containers"]:
        mapped += list((container.get("Files") or {}).values())
    missing = sorted({m for m in mapped if not (MOD / m.replace("\\", "/")).is_file()})
    return {"mapped_paths": len(mapped), "missing": missing, "identifier": meta["Identifier"], "options": [o["Name"] for o in group["Options"]],
            "default_setting": group["DefaultSettings"]}


# ---------------------------------------------------------------- pictures

RENDER_SCRIPT = '''"""Blender: render the SATSU face plus the Mother Moon body's neck, front and side. Written by mothermoon_face.py (a copy of
builds/_face/render_face.py with the body added). blender -b -P render_head_neck.py -- <prefix> <face.png> <body.png> <face.mdl> <body.mdl> <flat_normal.png>"""
import math, os, sys
sys.path.insert(0, "%(tools)s")
os.environ.setdefault("GLOW_STRENGTH", "0")
import bpy, render_glow as rg
prefix, face_png, body_png, face_mdl, body_mdl, normal = sys.argv[sys.argv.index("--") + 1:][:6]
bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene
sc.render.engine = "CYCLES"; sc.cycles.device = "CPU"; sc.cycles.samples = 24; sc.cycles.use_denoising = False
w = bpy.data.worlds.new("w"); w.use_nodes = True
w.node_tree.nodes["Background"].inputs[0].default_value = (0.2, 0.2, 0.22, 1); w.node_tree.nodes["Background"].inputs[1].default_value = 0.6
sc.world = w
rg.SKIN_MATCH = "fac_a"; rg.add_body(face_mdl, rg.skin(face_png, normal))
rg.SKIN_MATCH = "b0001_bibo"; rg.add_body(body_mdl, rg.skin(body_png, normal))
rg.sun(math.radians(75), math.radians(20), 3.0); rg.sun(math.radians(255), math.radians(-30), 1.5)
sc.render.resolution_x = sc.render.resolution_y = 900
cam = bpy.data.objects.new("c", bpy.data.cameras.new("c")); sc.collection.objects.link(cam); sc.camera = cam
cam.data.type = "ORTHO"; cam.data.ortho_scale = 0.24
Z = 1.42
views = {"front": ((0, -4, Z), (math.pi/2, 0, 0)), "side": ((4, 0, Z), (math.pi/2, 0, math.pi/2))}
for n, (loc, rot) in views.items():
    cam.location = loc; cam.rotation_euler = rot
    sc.render.filepath = f"{prefix}_{n}.png"; bpy.ops.render.render(write_still=True)
'''


def save_png(rgba: np.ndarray, path: Path, size: tuple | None = None) -> None:
    image = Image.fromarray(np.ascontiguousarray(rgba[..., :3]))
    image.resize(size, Image.LANCZOS).save(path) if size else image.save(path)


def evidence(source: np.ndarray, out: np.ndarray, weight: np.ndarray) -> None:
    save_png(source, OUT / "face_before.png")
    save_png(out, OUT / "face_after.png")
    pair = Image.new("RGB", (1024, 1024))
    pair.paste(Image.fromarray(np.ascontiguousarray(source[..., :3])).resize((512, 1024)), (0, 0))
    pair.paste(Image.fromarray(np.ascontiguousarray(out[..., :3])).resize((512, 1024)), (512, 0))
    pair.save(OUT / "before_after.png")
    Image.fromarray((weight * 255).astype("u1")).resize((512, 1024)).save(OUT / "fade_mask.png")
    shown = np.ascontiguousarray(source[..., :3]).astype(np.float32)
    mask = weight > 0
    shown[mask] = shown[mask] * 0.45 + np.array([255, 0, 0]) * 0.55 * weight[mask][:, None] + np.array([255, 160, 0]) * 0.55 * (1 - weight[mask][:, None])
    Image.fromarray(shown.astype("u1")).resize((512, 1024)).save(OUT / "mask_over_texture.png")


def render_pictures(source: np.ndarray, out: np.ndarray, body_tex: np.ndarray, face_mdl: Path) -> list:
    script = OUT / "render_head_neck.py"
    script.write_text(RENDER_SCRIPT % {"tools": str(Path(__file__).resolve().parent)})
    Image.new("RGB", (4, 4), (128, 128, 255)).save(OUT / "flat_normal.png")
    save_png(body_tex, OUT / "body_diffuse.png", (2048, 2048))
    pictures = []
    for label, texture in (("before", source), ("after", out)):
        save_png(texture, OUT / f"face_{label}.png")
        command = ["blender", "-b", "-P", str(script), "--", str(OUT / f"render_{label}"), str(OUT / f"face_{label}.png"), str(OUT / "body_diffuse.png"),
                   str(face_mdl), str(BODY_MDL), str(OUT / "flat_normal.png")]
        run = subprocess.run(command, capture_output=True, text=True, env={"PATH": "/usr/bin:/bin", "HOME": str(Path.home())})
        if run.returncode != 0:
            print(f"render {label} failed:\n{run.stdout[-1500:]}\n{run.stderr[-1500:]}")
            continue
        pictures += [f"render_{label}_front.png", f"render_{label}_side.png"]
    return pictures


# ---------------------------------------------------------------- main

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--face", default=DEFAULT_FACE)
    parser.add_argument("--update", action="store_true")
    parser.add_argument("--no-render", action="store_true")
    args = parser.parse_args()
    if MOD.exists() and not args.update:
        fail(f"{MOD} already exists; run with --update to rebuild it (the Identifier is kept)")

    info = resolve(args.face)
    picked = pick_winners(info)
    winning = picked["winning"]
    texture_path, normal_path = satsu_file(winning, "colour_texture"), satsu_file(winning, "normal")
    material_path = satsu_file(winning, "skin_material")
    try:
        source = np.array(tex_io.read_bgra(str(texture_path)))
        mmp.material_values(material_path.read_bytes())
    except Exception as error:
        fail(f"cannot read the winning face files: {type(error).__name__}: {error}")
    satsu_opts = satsu_options(info, args.face)
    if not satsu_opts:
        fail("could not find the selected SATSU option in any collection")
    model, model_report = geometry_model(info, winning, args.face, satsu_opts)
    mesh = face_mesh(model)
    ring = neck_ring(mesh)
    ring_y = float(mesh.positions[ring, 1].mean())

    body = mdl_read.read_mdl(str(BODY_MDL)).meshes[0]
    body_tex = tex_io.read_bgra(str(BODY_BUILD / "diffuse.tex"))
    target, body_n = body_skin_colour(body_tex, body, ring_y)
    edge = ring_colour(source, mesh, ring)
    before = mean_abs(edge, target)
    weight, tri_count = build_weights(model)
    delta = target - edge
    out = shift_texture(source, weight, delta)
    after_edge = ring_colour(out, mesh, ring)
    after = mean_abs(after_edge, target)
    copy_necks(info, body, ring_y, target)

    OUT.mkdir(parents=True, exist_ok=True)
    out_tex = OUT / "face_base_neck.tex"
    tex_io.write_bgra(str(out_tex), out)
    checks = check_texture(out_tex, source, out, weight)

    face_bytes = material_path.read_bytes()
    sakura = Path(read_json(BODY_BUILD / "wet.json")["materials"][BODY_RACE]["source"]).read_bytes()
    materials = {"plain": face_bytes}
    materials.update({kind: wet_face_material(face_bytes, sakura, kept) for kind, kept in mmp.WET_STRENGTHS.items()})
    body_plain = (BODY_BUILD / "mod" / "chara" / f"mothermoon_glow_mt_{BODY_RACE}.mtrl").read_bytes()
    table = material_table(face_bytes, sakura, body_plain, materials)
    absent = [v["name"] for v in table.values() if not v["in_face_material"]]

    mask, votes = default_mask(info)
    stale = [m for m in info["missing_mods"] if any(k in m.lower() for k in ("reborn", "face", "satsu", "alphinaud"))]
    if stale:
        picked["notes"].append(f"enabled in a collection but the mod folder does not exist (so it cannot override anything): {stale}")
    wet_ignored = [c["collection"] for c in info["mother_moon_copies"] if c.get("wet_ignored")]
    if wet_ignored:
        picked["notes"].append(f"Wet subtle / Wet strong ticked without Wet skin (the body ignores them, so the body is plain) in: {wet_ignored}")
    winning_json = {
        "face": args.face, "face_evidence": "SloppyMods uses Keeper face 1 (face 101): his Glamourer designs and the shark-teeth job note; --face changes it",
        "winning": winning, "satsu_option_selected": satsu_opts, "overriding_mods": overriding_mods(info), "notes": picked["notes"],
        "colour_texture_file": str(texture_path), "normal_file": str(normal_path), "skin_material_file": str(material_path),
        "colour_texture_sha1": hashlib.sha1(texture_path.read_bytes()).hexdigest(), "geometry_model": model_report,
        "reborn_c0801f0002_fac_base_wins": any(w["file"].lower().endswith("c0801f0002_fac_base.tex") and w["mod"] != SATSU for w in winning.values()),
        "note_file_name": "the SATSU file is itself named c0801f0002_fac_base.tex (inside the SATSU mod: common\\34); it is not Reborn's file",
        "other_collections_with_head_mods": info["other_collections"], "missing_mods_in_collections": info["missing_mods"], "role_copy_default_votes": votes, "default_setting": mask,
        "mother_moon_copies": info["mother_moon_copies"], "collections": info["collections"],
    }
    (OUT / "winning.json").write_text(json.dumps(winning_json, indent=2, ensure_ascii=False), encoding="utf-8")

    normal_check = normal_alpha(normal_path, mesh, ring, body, ring_y)
    seam = {
        "before_avg_diff": round(before, 3), "after_avg_diff": round(after, 3),
        "unit": "mean absolute difference over R, G, B, in steps of 255, head neck ring colour against the body skin just under it",
        "head_ring_colour_before": [float(v) for v in edge], "head_ring_colour_after": [float(v) for v in after_edge],
        "body_skin_colour": [float(v) for v in target], "shift_applied": [float(v) for v in delta],
        "ring_vertices": int(len(ring)), "ring_y_mean": round(ring_y, 4), "body_skin_samples": body_n,
        "fade": {"length_m": FADE_LEN, "triangles": tri_count, "shape": "smoothstep along the surface, 1 at the ring, 0 at the jaw line (cutoff 1.395, slope -0.3, as face_black_neck.py)"},
        "texture_check": checks, "normal_check": normal_check, "material_constants": table, "face_constants_missing": absent,
        "role_copies_neck": [{k: c.get(k) for k in ("collection", "copy_dir", "toggles_on", "neck_skin_colour", "neck_step_vs_built", "still_shows_step")}
                             for c in info["mother_moon_copies"]],
    }
    (OUT / "seam.json").write_text(json.dumps(seam, indent=2, ensure_ascii=False), encoding="utf-8")

    identifier = build_mod(info, winning, args.face, args.update, out_tex.read_bytes(), materials)
    mod_check = verify_mod()
    evidence(source, out, weight)
    pictures = [] if args.no_render else render_pictures(source, out, body_tex, model)
    report(args, winning, seam, mod_check, identifier, pictures, picked["notes"])
    if mod_check["missing"] or not all(v for k, v in checks.items() if k.endswith(("identical", "exact"))):
        fail("a check failed; see seam.json and the output above")


def normal_alpha(normal_path: Path, mesh, ring: np.ndarray, body, ring_y: float) -> dict:
    """Is the glow (the normal map's alpha) cut off at the neck? Alpha of the body's glow normal under the ring vs the face normal at the ring."""
    out = {"note": "report only; the face normal map is left untouched"}
    try:
        glow = tex_io.read_bgra(str(BODY_BUILD / "norm_glow.tex"))
        uv = body.uv.copy()
        uv[:, 1] %= 1.0
        pick = np.where((body.positions[:, 1] > ring_y - BODY_BAND) & (body.positions[:, 1] < ring_y) & (np.abs(body.positions[:, 0]) < 0.1))[0]
        samples = patch_median(glow[..., 3:4].repeat(3, -1), uv[pick])
        out["body_glow_alpha_under_ring_mean"] = float(samples[:, 0].mean())
        out["body_glow_alpha_under_ring_max"] = float(samples[:, 0].max())
        face_norm = tex_io.read_bgra(str(normal_path))
        out["face_normal_alpha_at_ring_mean"] = float(patch_median(face_norm[..., 3:4].repeat(3, -1), mesh.uv[ring])[:, 0].mean())
    except Exception as error:
        out["error"] = f"{type(error).__name__}: {error}"
    return out


def report(args, winning, seam, mod_check, identifier, pictures, notes) -> None:
    print(f"face {args.face}: colour {winning['colour_texture']['mod']} / {winning['colour_texture']['file']}")
    print(f"seam: before {seam['before_avg_diff']}, after {seam['after_avg_diff']} (0..255 steps); shift {seam['shift_applied']}")
    print(f"texture check: {seam['texture_check']}")
    print(f"mod: {MOD} (Identifier {identifier}); mapped {mod_check['mapped_paths']} paths, missing {mod_check['missing']}")
    print("pictures:", pictures or "none")
    for note in notes:
        print("note:", note)
    print(f'install: cp -r "{MAIN / "builds/_mothermoon_face/mod"}" "{PENUMBRA / MOD_NAME}"   (untested in game)')


if __name__ == "__main__":
    main()
