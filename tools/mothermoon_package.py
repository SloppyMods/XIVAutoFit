"""Assemble (or update) the Mother Moon Glow Penumbra mod folder from the textures in builds/_mothermoon. Source mods are only read.

    python3 mothermoon_package.py            create builds/_mothermoon/mod (refuses if it already exists)
    python3 mothermoon_package.py --update   replace this script's own files and meta.json in it, keeping its Identifier

Nothing is installed into Penumbra: copy the finished folder yourself (see the report / meta Description).

One Combining group "Mother Moon" with toggles Glow (bit 0), Bandage colour (bit 1) and, when wet.json says the Sakura wet look
could be carried, Wet skin (bit 2) plus two strength toggles, Wet subtle (bit 3) and Wet strong (bit 4), then Limb glow (bit 5: with Glow on, the half-strength sleeve glow normals norm_limbglow* replace norm_glow*; ignored while Glow is off). Container index = bitmask. Ids come from uuid5 on names, so Penumbra keeps the user's choices
across updates.
  - Glow on maps an emissive-type material per race (c0201 Mother Moon's own glowset, c0401/c1801 the Unholy-derived ones), each
    with only g_EmissiveColor (shader constant 0x38A64362) set from glow.json. Glow off maps the same materials with the colour
    set to black, so that Magical Sakura's own body material cannot win those paths when Sakura is also enabled.
  - Wet skin on maps Sakura's own per-race `_1_bibo` material instead, with its `chara/bibo_{race}_sakura_{base,norm,mask}.tex`
    paths mapped to this mod's colour, normal and a copy of the mask the body already uses (Bibo+ Base Install's mid mask, Dionys
    multi_base for high and viera). Sakura's own mask is never shipped. Only g_EmissiveColor and the constants classified in
    WET_CONSTANTS change: "gloss" constants stay Sakura's; "brighten"/"unclear" ones with action "reduce" move from the plain
    material's value towards Sakura's by the strength's fraction (WET_STRENGTHS). Values are overwritten in place, so the file
    layout (keys, constant table) stays Sakura's.
  - Wet strength: Wet skin alone is the balanced look; Wet subtle (bit 3) or Wet strong (bit 4) on top pick another strength.
    Without Wet skin the two are ignored. If both are ticked, Wet subtle wins.
  - Gen2 / vanilla gear (c0201 only): every container also maps chara/human/c0201/obj/body/b0001/texture/c0201b0001_{base,norm}.tex
    to the Gen2 textures (gen2_*.tex, built by `mothermoon_merge.py --gen2`, record in gen2.json) and the Gen2 skin material
    mt_c0201b0001_a.mtrl to Mother Moon's own Gen2 glow material (only g_EmissiveColor set, black when Glow is off). Wet skin maps
    Sakura's Gen2 wet material (`_1_a`) there instead, the same way as the Bibo+ one, with its sakura_base/norm textures mapped to the
    Gen2 colour and normal and its sakura_mask a file swap to the game's plain skin mask (never Sakura's own mask).
"""
import json
import shutil
import struct
import sys
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path

sys.dont_write_bytecode = True  # importing the helpers must not write tools/__pycache__/
sys.path.insert(0, str(Path(__file__).resolve().parent))
import vampire_package  # noqa: E402  (patch_emissive only; this file's own constants are below)

HERE = Path(__file__).resolve().parent
BUILD = HERE.parent / "builds" / "_mothermoon"
NEW_MOD = BUILD / "mod"
MM_PMP = Path("/home/you/Downloads/Telegram Desktop/Skin Mods/Mother Moon/Mother Moon.pmp")
MM_MATERIAL = "chara/mt_c0201b0001_bibo_glowset.mtrl"
UNHOLY_MATERIALS = {
    "c0401": Path("/mnt/STORAGE/Penumbra/Unholy Glow 3D [Dionys + Sakura Abs + Bandages]/chara/mt_c0401b0001_bibo.mtrl"),
    "c1801": Path("/mnt/STORAGE/Penumbra/Unholy Glow 3D [Dionys + Sakura Abs + Bandages]/chara/mt_c1801b0001_bibo_e.mtrl"),
}
MASK_SOURCES = {  # the body mask SloppyMods's character resolves today -> local file name in the mod
    "mid": (Path("/mnt/STORAGE/Penumbra/[HS] Bibo+ (Bibo+ Base Install)/files/common/2/bibo_mid_mask.tex"), "mask_mid"),
    "high": (Path("/mnt/STORAGE/Penumbra/Dionys V1.4.0/Dionys/Textures/Skin/Multi/multi_base.tex"), "mask_multi"),
    "viera": (Path("/mnt/STORAGE/Penumbra/Dionys V1.4.0/Dionys/Textures/Skin/Multi/multi_base.tex"), "mask_multi"),
}
ID_SPACE = uuid.UUID("5b8e2c71-94d3-4a60-8f1e-c2a7d3e90b46")
PREFIX = "mothermoon_"
RACES = {"c0201": "mid", "c0401": "high", "c1801": "viera"}  # race code -> texture race
TEXTURES = ("norm_3d", "norm_3d_cloth", "norm_glow", "norm_glow_cloth", "diffuse", "diffuse_cloth")
GEN2_TEXTURES = tuple(f"gen2_{name}" for name in TEXTURES)  # built by mothermoon_merge.py --gen2
LIMB_TEXTURES = ("norm_limbglow", "norm_limbglow_cloth") + tuple(f"gen2_norm_limbglow{tail}" for tail in ("", "_cloth"))  # half-strength sleeve glow twins
GEN2_MATERIAL = "chara/mt_c0201b0001_a_glowset.mtrl"  # in Mother Moon.pmp
GEN2_CODE = "c0201"  # the only race the Gen2 set is built for
GEN2_DIR = f"chara/human/{GEN2_CODE}/obj/body/b0001"
GEN2_PLAIN_MASK = "chara/common/texture/skin_mask.tex"  # the plain body mask Sakura's Gen2 wet material gets (a file swap)
GROUP_NAME = "Mother Moon"
OPTION_NAMES = ("Glow", "Bandage colour", "Wet skin", "Wet subtle", "Wet strong", "Limb glow")
OPTION_DESCRIPTIONS = (
    "Mother Moon's cyan glow on the tattoo. Off: no glow (abs, bandage folds and the tattoo stay).",
    "Paints the light grey Sutured bandages on and hides the tattoo and its glow under the cloth.",
    "Magical Sakura's wet skin look (its glisten kept, its extra brightening turned down to a balanced level). Off: the plain Mother Moon skin material.",
    "Only with Wet skin on: the wet glisten with the extra brightening taken out completely (the glints stay, the light-on-you lift goes). Wins over Wet strong.",
    "Only with Wet skin on: the wet glisten with more of Sakura's brightening left in (about three quarters of the way back to Sakura's).",
    "Half-strength glow on the dark arm and leg sleeves, only while Glow is on.",
)
# Wet variants: local file prefix and the share of Sakura's brightening (the distance from the plain value to Sakura's) kept.
WET_STRENGTHS = {"wetsubtle": 0.0, "wet": 0.4, "wetstrong": 0.75}
# Sakura's `_1_bibo` material against the plain glow material: the ten constants that differ, named by CRC32 (init 0, no final xor,
# which reproduces g_MaterialParameter 0x64D12851 and g_EmissiveColor 0x38A64362) against the strings in Penumbra.GameData.dll and
# the id table in skin.shpk. Roles are read from the names, not from the shader code: nothing here is confirmed in game.
WET_CONSTANTS = {
    "59BDA0B1": ("g_ShaderID", "unclear", "reduce", "Sakura sets it to 16.6 (mid) or 11.9 (high, viera) against the plain 1.0, a per-race strength-like value whose effect is not documented; moved with the brighteners so Wet subtle goes back to the plain value."),
    "4255F2F4": ("g_TileIndex", "gloss", "keep", "Picks the tiled micro-normal layer (63 to 21); the fine tiled bumps catch light as small sharp glints, not as a lift of the whole skin."),
    "2E60B071": ("g_TileScale", "gloss", "keep", "How densely the micro-normal tiles repeat (200 to about 60 and 51); it shapes the glints, it adds no light."),
    "5351646E": ("g_ShadowPosOffset", "brighten", "reduce", "Shifts where shadows are sampled; Sakura's -9.8 against the plain 0.35 lets the skin lose its self-shadowing, which reads as light shining on it."),
    "00A680BC": ("g_ToonSpecIndex", "gloss", "keep", "Toon specular lookup row, 0.0, which the skin.shpk default also is, so it changes nothing visible; kept as Sakura's."),
    "800EE35F": ("g_SheenRate", "brighten", "reduce", "How strong the soft sheen layer is (8.9, the plain material and the shader default have none): a broad grazing-angle glow over the whole skin, the most likely source of the lit-from-the-front look."),
    "1F264897": ("g_SheenTintRate", "brighten", "reduce", "How much the sheen is tinted (1.0 mid, 1.7 high and viera, none in the plain material); only matters while the sheen is on, so it follows g_SheenRate."),
    "F490F76E": ("g_SheenAperture", "gloss", "keep", "Width of the sheen lobe (8.8, a narrow one): with the rate turned down it leaves only a tight faint highlight, which is the glisten."),
    "12C6AC9F": ("g_TileAlpha", "gloss", "keep", "Strength of the tiled micro-normal (0.4); controls the glints, adds no light."),
    "39551220": ("g_TextureMipBias", "gloss", "keep", "-1.2 samples textures sharper so the fine detail stays crisp; it is not a light."),
}
WET_KEY = ("D2777173", "GetDecalColor", "GetDecalColorAlpha", "keep", "Shader key (hash of GetDecalColor, value GetDecalColorAlpha) that chooses how the decal layer is blended; no brightening in it, and removing a key changes the file layout, so it stays Sakura's.")
DISPLAY_NAME = "Mother Moon Glow [Dionys + Sakura Abs + Bandages]"
DESCRIPTION = (
    "Mother Moon tattoo by Millwood, on the Dionys \"Bubblegum & Freckles\" skin, with Magical Sakura's muscled abs normal and "
    "the Sutured bandages.\n\n"
    "Options (toggles):\n"
    "- Glow: Mother Moon's cyan glow. Off keeps the tattoo colour, abs and bandage folds without glowing.\n"
    "- Bandage colour: paints the light grey bandages on and hides the tattoo and its glow under the cloth.\n"
    "- Limb glow: the dark arm and leg sleeves glow softly at about half strength. On by default; it only matters while Glow is on.\n"
    "{wet_line}"
    "\nForearms and shins: gloves and boots draw those, not the body mesh. Gear whose skin sits on the Bibo+ material "
    "(mt_c*b0001_bibo.mtrl, for example the Muse+ Emperor's New Gloves) takes the tattoo colour through the chara/bibo_* "
    "textures. Vanilla gloves and boots draw their skin from the older Gen2 material (mt_c0201b0001_a.mtrl, "
    "c0201b0001_base/norm.tex, a smaller 1024x2048 layout), and this mod now covers that for Midlander, Miqo'te and Elezen "
    "bodies (c0201) only. On all of that skin you get Mother Moon's own Gen2 tattoo and glow, Sakura's Gen2 abs normal and the "
    "wet strengths (Sakura's Gen2 wet material). The Dionys skin colour, the Sutured folds and the bandage colour are added only "
    "where the Gen2 layout is the same as the right half of the Bibo+ one (most of the arms, legs and torso). The hands and "
    "fingers, feet, chest and a few small areas are laid out differently, so there the Gen2 skin keeps the Muse+ colour, with no "
    "bandages. Give this mod a higher priority than Muse+ too, which ships the same Gen2 material and texture paths. Highlander, Roegadyn and Viera Gen2 skin (c0401, c1801) and Gen3 gear (mt_c*b0001_b.mtrl) are not "
    "covered.\n"
    "\nGlow colour: change it in Penumbra > Advanced Editing > Materials > g_EmissiveColor.\n\n"
    "Works for Midlander, Miqo'te, Elezen, Highlander, Roegadyn and Viera only.\n\n"
    "In the same collection, disable the original Mother Moon, \"Unholy Glow 3D\" and \"Vampire Heartbeat Glow\" mods, since they "
    "set the same files. Give this mod a higher priority than Magical Sakura (or disable Sakura's body options): Sakura sets the "
    "same body materials and chara/bibo_*_sakura_* textures, and the mod with the higher priority wins them."
)
WET_LINE = (
    "- Wet skin: Magical Sakura's wet skin look. Only the material settings come along; the glisten stays and Sakura's extra "
    "brightening (the \"light is on you\" look) is turned down to a balanced level.\n"
    "- Wet subtle / Wet strong: pick a strength on top of Wet skin (ignored while Wet skin is off). Subtle takes the extra "
    "brightening out completely, strong leaves about three quarters of Sakura's in. If both are ticked, subtle wins. "
    "Try them in game and keep the one that looks right.\n"
)


def stable_id(*names: str) -> str:
    return str(uuid.uuid5(ID_SPACE, "/".join(names)))


def local_path(name: str) -> str:
    return f"chara\\{PREFIX}{name}"


def material_local(kind: str, code: str) -> str:
    return f"{kind}_mt_{code}.mtrl"


def wet_variant(mask: int) -> str:
    """Which wet material a container uses: subtle (bit 3) wins over strong (bit 4); neither ticked is the balanced one."""
    return "wetsubtle" if mask & 8 else "wetstrong" if mask & 16 else "wet"


def container_files(mask: int, wet_available: bool, gen2_wet: bool) -> dict:
    glow, bandage, wet, limb = bool(mask & 1), bool(mask & 2), wet_available and bool(mask & 4), bool(mask & 32)
    wet_kind = wet_variant(mask)
    diffuse = "diffuse_cloth" if bandage else "diffuse"
    glow_name = "norm_limbglow" if limb else "norm_glow"  # Limb glow only changes anything while Glow is on
    normal = (f"{glow_name}_cloth" if bandage else glow_name) if glow else ("norm_3d_cloth" if bandage else "norm_3d")
    files = {}
    for code, race in RACES.items():
        files[f"chara/bibo_{race}_base.tex"] = local_path(f"{diffuse}.tex")
        files[f"chara/bibo_{race}_norm.tex"] = local_path(f"{normal}.tex")
        material_game_path = f"chara/human/{code}/obj/body/b0001/material/v0001/mt_{code}b0001_bibo.mtrl"
        if wet:
            files[f"chara/bibo_{race}_sakura_base.tex"] = local_path(f"{diffuse}.tex")
            files[f"chara/bibo_{race}_sakura_norm.tex"] = local_path(f"{normal}.tex")
            files[f"chara/bibo_{race}_sakura_mask.tex"] = local_path(f"{MASK_SOURCES[race][1]}.tex")
            files[material_game_path] = local_path(material_local(f"{wet_kind}_glow" if glow else f"{wet_kind}_off", code))
        else:  # the plain material is always mapped, so Sakura's body material never wins here; black when Glow is off
            files[material_game_path] = local_path(material_local("glow" if glow else "off", code))
    # Gen2 / vanilla gear (c0201 only): the Gen2 colour and normal are always mapped, like chara/bibo_mid_base.tex
    files[f"{GEN2_DIR}/texture/{GEN2_CODE}b0001_base.tex"] = local_path(f"gen2_{diffuse}.tex")
    files[f"{GEN2_DIR}/texture/{GEN2_CODE}b0001_norm.tex"] = local_path(f"gen2_{normal}.tex")
    gen2_material_game_path = f"{GEN2_DIR}/material/v0001/mt_{GEN2_CODE}b0001_a.mtrl"
    if wet and gen2_wet:
        files[f"{GEN2_DIR}/texture/{GEN2_CODE}b0001_sakura_base.tex"] = local_path(f"gen2_{diffuse}.tex")
        files[f"{GEN2_DIR}/texture/{GEN2_CODE}b0001_sakura_norm.tex"] = local_path(f"gen2_{normal}.tex")
        files[gen2_material_game_path] = local_path(material_local(f"gen2_{wet_kind}_glow" if glow else f"gen2_{wet_kind}_off", GEN2_CODE))
    else:  # the plain Gen2 material is always mapped (black when Glow is off), so Sakura's cannot win the path
        files[gen2_material_game_path] = local_path(material_local("gen2_glow" if glow else "gen2_off", GEN2_CODE))
    return files


def container_swaps(mask: int, wet_available: bool, gen2_wet: bool) -> dict:
    """File swaps: Sakura's Gen2 wet material samples a mask of its own, which is swapped to the game's plain skin mask."""
    if wet_available and gen2_wet and mask & 4:
        return {f"{GEN2_DIR}/texture/{GEN2_CODE}b0001_sakura_mask.tex": GEN2_PLAIN_MASK}
    return {}


def container_entry(mask: int, wet_available: bool, gen2_wet: bool) -> dict:
    entry = {"Name": container_name(mask, wet_available), "Files": container_files(mask, wet_available, gen2_wet)}
    swaps = container_swaps(mask, wet_available, gen2_wet)
    if swaps:
        entry["FileSwaps"] = swaps
    return entry


def container_name(mask: int, wet_available: bool) -> str:
    names = OPTION_NAMES
    parts = [n.lower() for i, n in enumerate(names) if mask & (1 << i)]
    return " + ".join(parts) if parts else "none"


def build_meta(identifier: str, wet_available: bool, gen2_wet: bool) -> dict:
    names, descriptions = OPTION_NAMES, OPTION_DESCRIPTIONS
    return {
        "FileVersion": 4,
        "Identifier": identifier,
        "LastWrite": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.0000000Z"),
        "Name": DISPLAY_NAME,
        "Author": "Millwood (edit: Dionys skin, Sakura abs, Sutured bandages)",
        "Description": DESCRIPTION.format(wet_line=WET_LINE if wet_available else ""),
        "Version": "1.3",
        "Website": "",
        "ModTags": [],
        "DefaultData": {"Files": {}},
        "Groups": [
            {
                "Type": "Combining",
                "Id": stable_id(GROUP_NAME),
                "Name": GROUP_NAME,
                "Description": f"Toggle {', '.join(names[:-1])} and {names[-1]} independently.",
                "Priority": 0,
                "DefaultSettings": 1 | 4 | 32,  # Glow on, Bandage colour off, Wet skin on, Limb glow on
                "Options": [{"Id": stable_id(GROUP_NAME, n), "Name": n, "Description": d} for n, d in zip(names, descriptions)],
                "Containers": [container_entry(m, wet_available, gen2_wet) for m in range(2 ** len(names))],
            }
        ],
    }


def material_slots(data: bytes) -> dict:
    """Dawntrail .mtrl -> {constant id (8 hex digits): (absolute offset of its floats, float count)}."""
    _version, _file_size, data_set_size, string_table_size, _shader_name, tex_count, uv_count, colorset_count, additional = struct.unpack_from("<IHHHHBBBB", data, 0)
    pos = 16 + 4 * (tex_count + uv_count + colorset_count) + string_table_size + additional + data_set_size
    _list_size, key_count, constant_count, sampler_count = struct.unpack_from("<HHHH", data, pos)
    constants_start = pos + 12 + key_count * 8
    value_block = constants_start + constant_count * 8 + sampler_count * 12
    slots = {}
    for i in range(constant_count):
        const_id, offset, size = struct.unpack_from("<IHH", data, constants_start + i * 8)
        slots[f"{const_id:08X}"] = (value_block + offset, size // 4)
    return slots


def material_values(data: bytes) -> dict:
    return {cid: list(struct.unpack_from(f"<{count}f", data, offset)) for cid, (offset, count) in material_slots(data).items()}


def wet_material(sakura: bytes, plain: bytes, kept: float) -> bytes:
    """Sakura's material with every 'reduce' constant moved from the plain value (0 when the plain material lacks it) towards
    Sakura's, keeping the share `kept` of the distance. Floats are overwritten in place; nothing else in the file changes."""
    slots, plain_values = material_slots(sakura), material_values(plain)
    out = bytearray(sakura)
    for cid, (_name, _role, action, _why) in WET_CONSTANTS.items():
        if action == "keep":
            continue
        offset, count = slots[cid]
        sakura_values = struct.unpack_from(f"<{count}f", sakura, offset)
        plain_floats = plain_values.get(cid, [0.0] * count)
        struct.pack_into(f"<{count}f", out, offset, *(p + kept * (v - p) for p, v in zip(plain_floats, sakura_values)))
    return bytes(out)


def material_files(colour: list, wet: dict, gen2_wet: dict) -> dict:
    """local file name -> .mtrl bytes. Every material is its source with only g_EmissiveColor replaced; the wet ones also have the
    WET_CONSTANTS 'reduce' constants moved (see wet_material). The Gen2 ones (names start with gen2_) are for mt_c0201b0001_a.mtrl."""
    with zipfile.ZipFile(MM_PMP) as archive:
        glow = {"c0201": archive.read(MM_MATERIAL)}
        gen2_plain = archive.read(GEN2_MATERIAL)
    glow.update({code: path.read_bytes() for code, path in UNHOLY_MATERIALS.items()})
    files = {material_local("glow", code): vampire_package.patch_emissive(data, colour) for code, data in glow.items()}
    files.update({material_local("off", code): vampire_package.patch_emissive(data, [0.0, 0.0, 0.0]) for code, data in glow.items()})
    if wet["carried"]:
        for code in RACES:
            sakura = Path(wet["materials"][code]["source"]).read_bytes()
            for kind, kept in WET_STRENGTHS.items():
                data = wet_material(sakura, glow[code], kept)
                files[material_local(f"{kind}_glow", code)] = vampire_package.patch_emissive(data, colour)
                files[material_local(f"{kind}_off", code)] = vampire_package.patch_emissive(data, [0.0, 0.0, 0.0])
    files[material_local("gen2_glow", GEN2_CODE)] = vampire_package.patch_emissive(gen2_plain, colour)
    files[material_local("gen2_off", GEN2_CODE)] = vampire_package.patch_emissive(gen2_plain, [0.0, 0.0, 0.0])
    if wet["carried"] and gen2_wet["carried"]:
        sakura = Path(gen2_wet["source"]).read_bytes()
        for kind, kept in WET_STRENGTHS.items():
            data = wet_material(sakura, gen2_plain, kept)
            files[material_local(f"gen2_{kind}_glow", GEN2_CODE)] = vampire_package.patch_emissive(data, colour)
            files[material_local(f"gen2_{kind}_off", GEN2_CODE)] = vampire_package.patch_emissive(data, [0.0, 0.0, 0.0])
    return files


def classified_wet(wet: dict) -> dict:
    """wet.json with the constants classification, the shader key and the summary this script applies."""
    out = dict(wet)
    out["constants"] = {cid: {"name": n, "role": r, "action": a, "why": w} for cid, (n, r, a, w) in WET_CONSTANTS.items()}
    key_id, key_name, value_name, action, why = WET_KEY
    out["shader_key"] = {key_id: {"name": key_name, "value": value_name, "action": action, "why": why}}
    out["strengths"] = {
        "share_of_sakura_brightening_kept": WET_STRENGTHS,
        "options": {"wet": "Wet skin alone", "wetsubtle": "Wet skin + Wet subtle (wins over strong)", "wetstrong": "Wet skin + Wet strong"},
        "note": "reduce constants = plain value + share * (Sakura value - plain value); the plain value is 0 when the plain material lacks the constant.",
    }
    out["summary"] = (
        "Sakura's per-race `_1_bibo` body materials differ from Mother Moon's/Unholy's glow materials in the shader key "
        "GetDecalColor=GetDecalColorAlpha and ten constants (see `constants`; names found by hashing candidate names the way the game does and "
        "matching them against skin.shpk's own constant table). They are split into glisten (g_TileIndex, g_TileScale, g_TileAlpha, "
        "g_SheenAperture, g_ToonSpecIndex, g_TextureMipBias: kept as Sakura's) and brightening (g_SheenRate, g_SheenTintRate, "
        "g_ShadowPosOffset, plus g_ShaderID whose effect is unclear: moved back towards the plain material by the strength's share). "
        "The split comes from the constant names, not from the shader code, so glisten and light may not separate cleanly: this is the "
        "closest compromise and three strengths (Wet subtle, Wet skin, Wet strong) are offered so one in-game look can settle it. The wet toggle still "
        "goes through the material only: Sakura's mask is not shipped (the body's own mask copy is mapped instead), by design. Untested in game."
    )
    return out


def main() -> None:
    update = "--update" in sys.argv[1:]
    if NEW_MOD.exists() and not update:
        raise SystemExit(f"{NEW_MOD} already exists; run with --update to replace this script's files in it")
    colour = json.loads((BUILD / "glow.json").read_text(encoding="utf-8"))["g_EmissiveColor"]
    wet = classified_wet(json.loads((BUILD / "wet.json").read_text(encoding="utf-8")))
    (BUILD / "wet.json").write_text(json.dumps(wet, indent=2, ensure_ascii=False), encoding="utf-8")
    wet_available = bool(wet["carried"])
    if not wet_available:
        raise SystemExit("wet.json says the wet look is not carried; the option bits (Limb glow is bit 5) assume the five original options")
    gen2 = json.loads((BUILD / "gen2.json").read_text(encoding="utf-8"))  # written by mothermoon_merge.py --gen2
    if gen2.get("blocked") or gen2.get("races") != [GEN2_CODE]:
        raise SystemExit(f"gen2.json is blocked or lists races {gen2.get('races')}; this script maps {GEN2_CODE} only: {gen2.get('blocked', '')}")
    gen2_wet = bool(gen2["wet"]["carried"])
    materials = material_files(colour, wet, gen2["wet"])
    if update:
        identifier = json.loads((NEW_MOD / "meta.json").read_text(encoding="utf-8-sig"))["Identifier"]
    else:
        identifier = str(uuid.uuid4())
    meta = build_meta(identifier, wet_available, gen2_wet)
    wanted = {f"{PREFIX}{name}.tex" for name in TEXTURES + GEN2_TEXTURES + LIMB_TEXTURES} | {f"{PREFIX}{name}" for name in materials}
    if wet_available:
        wanted |= {f"{PREFIX}{local}.tex" for _source, local in MASK_SOURCES.values()}
    (NEW_MOD / "chara").mkdir(parents=True, exist_ok=True)
    for stale in (NEW_MOD / "chara").glob(f"{PREFIX}*"):  # --update: drop this script's files that no longer apply
        if stale.name not in wanted:
            stale.unlink()
    for name in TEXTURES + GEN2_TEXTURES + LIMB_TEXTURES:
        shutil.copyfile(BUILD / f"{name}.tex", NEW_MOD / "chara" / f"{PREFIX}{name}.tex")
    for name, data in materials.items():
        (NEW_MOD / "chara" / f"{PREFIX}{name}").write_bytes(data)
    if wet_available:
        for source, local in MASK_SOURCES.values():
            shutil.copyfile(source, NEW_MOD / "chara" / f"{PREFIX}{local}.tex")
    (NEW_MOD / "meta.json").write_text(json.dumps(meta, indent="\t", ensure_ascii=False), encoding="utf-8")
    print(f"{'updated' if update else 'wrote'} {NEW_MOD} (Identifier {identifier})")


if __name__ == "__main__":
    main()
