"""Make (or update) the Vampire Heartbeat Glow Penumbra mod from the textures in builds/_vampire. Source mods are only read.

    python3 vampire_package.py            create NEW_MOD (refuses if it exists)
    python3 vampire_package.py --update   replace this script's own files and meta.json in NEW_MOD, keeping its Identifier

One Combining group "Vampire Heartbeat" with three toggles: Glow (bit 0), Black neck (bit 1), Bandage colour (bit 2).
Container index = bitmask. Glow on also swaps in three Unholy-derived materials whose g_EmissiveColor (shader constant
0x38A64362) is set from builds/_vampire/glow.json; nothing else in those materials changes. Ids come from uuid5 on names,
so Penumbra keeps the user's choices across updates.
"""
import json
import shutil
import struct
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
BUILD = HERE.parent / "builds" / "_vampire"
MATERIAL_SOURCE = Path("/mnt/STORAGE/Penumbra/Unholy_dt_glow_3d_bibo/chara")
NEW_MOD = Path("/mnt/STORAGE/Penumbra/Vampire Heartbeat Glow [Dionys + Sakura Abs + Bandages]")
ID_SPACE = uuid.UUID("c7a41d52-3e8b-4f06-9b2a-61d0e5f8a734")
EMISSIVE_CONSTANT_ID = 0x38A64362
RACES = ("mid", "high", "viera")
NECKS = ("black_neck", "normal_neck")
TEXTURES = (
    ["norm_3d"]
    + [f"{kind}_{neck}" for kind in ("norm_glow", "norm_glow_cloth", "diffuse", "diffuse_cloth") for neck in NECKS]
)
# source material in Unholy -> (file in the mod, game path)
MATERIALS = {
    "mt_c0201b0001_bibo.mtrl": ("chara/vampire_mt_c0201.mtrl", "chara/human/c0201/obj/body/b0001/material/v0001/mt_c0201b0001_bibo.mtrl"),
    "mt_c0401b0001_bibo.mtrl": ("chara/vampire_mt_c0401.mtrl", "chara/human/c0401/obj/body/b0001/material/v0001/mt_c0401b0001_bibo.mtrl"),
    "mt_c1801b0001_bibo_e.mtrl": ("chara/vampire_mt_c1801.mtrl", "chara/human/c1801/obj/body/b0001/material/v0001/mt_c1801b0001_bibo.mtrl"),
}
GROUP_NAME = "Vampire Heartbeat"
OPTION_NAMES = ("Glow", "Black neck", "Bandage colour")
OPTION_DESCRIPTIONS = (
    "Heartbeat glow on the tattoo. Off: no glow and no glow materials (abs and bandage folds stay).",
    "Dionys skin with the black neck tattoo. Off: the normal (plain) neck.",
    "Paints the Sutured bandages on and hides the glow under the cloth. Also covers the red glowing hands.",
)
DISPLAY_NAME = "Vampire Heartbeat Glow [Dionys + Sakura Abs + Bandages]"
DESCRIPTION = (
    "Vampire Heartbeat tattoo by Tahoni, on the Dionys body with Magical Sakura's muscled abs normal and "
    "the Sutured bandages.\n\n"
    "Options (toggles):\n"
    "- Glow: the heartbeat glow. Off keeps the tattoo colour, abs and bandage folds without glowing.\n"
    "- Black neck: Dionys skin with the black neck tattoo instead of the normal neck.\n"
    "- Bandage colour: paints the bandages on and hides the glow under the cloth. This also covers the red glowing hands.\n\n"
    "Glow colour: change it in Penumbra > Advanced Editing > Materials > g_EmissiveColor.\n\n"
    "Works for Midlander, Miqo'te, Elezen, Highlander, Roegadyn and Viera only.\n\n"
    "In the same collection, disable the old \"Glow Vampire Heartbeat_with black neck\" mod and the "
    "\"Unholy Glow 3D\" mod, since they set the same files."
)


def stable_id(*names: str) -> str:
    return str(uuid.uuid5(ID_SPACE, "/".join(names)))


def patch_emissive(data: bytes, colour: list) -> bytes:
    """Return the Dawntrail .mtrl with only g_EmissiveColor's three floats replaced."""
    if len(colour) != 3:
        raise ValueError("g_EmissiveColor needs three floats")
    _version, _file_size, data_set_size, string_table_size, _shader_name, tex_count, uv_count, colorset_count, additional = struct.unpack_from("<IHHHHBBBB", data, 0)
    pos = 16 + 4 * (tex_count + uv_count + colorset_count) + string_table_size + additional + data_set_size
    _list_size, key_count, constant_count, sampler_count = struct.unpack_from("<HHHH", data, pos)
    keys_start = pos + 12
    constants_start = keys_start + key_count * 8
    value_block = constants_start + constant_count * 8 + sampler_count * 12
    for i in range(constant_count):
        const_id, offset, size = struct.unpack_from("<IHH", data, constants_start + i * 8)
        if const_id == EMISSIVE_CONSTANT_ID:
            if size != 12:
                raise ValueError(f"g_EmissiveColor has size {size}, expected 12")
            out = bytearray(data)
            struct.pack_into("<3f", out, value_block + offset, *colour)
            return bytes(out)
    raise ValueError("material has no g_EmissiveColor constant")


def container_files(mask: int) -> dict:
    glow, black, bandage = bool(mask & 1), bool(mask & 2), bool(mask & 4)
    neck = "black_neck" if black else "normal_neck"
    diffuse = f"diffuse_cloth_{neck}" if bandage else f"diffuse_{neck}"
    if not glow:
        normal = "norm_3d"
    else:
        normal = f"norm_glow_cloth_{neck}" if bandage else f"norm_glow_{neck}"
    files = {}
    for race in RACES:
        files[f"chara/bibo_{race}_base.tex"] = f"chara\\vampire_{diffuse}.tex"
        files[f"chara/bibo_{race}_norm.tex"] = f"chara\\vampire_{normal}.tex"
    if glow:
        for local, game in MATERIALS.values():
            files[game] = local.replace("/", "\\")
    return files


def container_name(mask: int) -> str:
    parts = [n.lower() for i, n in enumerate(OPTION_NAMES) if mask & (1 << i)]
    return " + ".join(parts) if parts else "none"


def build_meta(identifier: str) -> dict:
    return {
        "FileVersion": 4,
        "Identifier": identifier,
        "LastWrite": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.0000000Z"),
        "Name": DISPLAY_NAME,
        "Author": "Tahoni (edit: Dionys skin, Sakura abs, Sutured bandages)",
        "Description": DESCRIPTION,
        "Version": "1.0",
        "Website": "",
        "ModTags": [],
        "DefaultData": {"Files": {}},
        "Groups": [
            {
                "Type": "Combining",
                "Id": stable_id(GROUP_NAME),
                "Name": GROUP_NAME,
                "Description": "Toggle Glow, Black neck and Bandage colour independently.",
                "Priority": 0,
                "DefaultSettings": 3,
                "Options": [
                    {"Id": stable_id(GROUP_NAME, n), "Name": n, "Description": d}
                    for n, d in zip(OPTION_NAMES, OPTION_DESCRIPTIONS)
                ],
                "Containers": [{"Name": container_name(m), "Files": container_files(m)} for m in range(8)],
            }
        ],
    }


def main() -> None:
    update = "--update" in sys.argv[1:]
    if NEW_MOD.exists() and not update:
        raise SystemExit(f"{NEW_MOD} already exists; run with --update to replace this script's files in it")
    colour = json.loads((BUILD / "glow.json").read_text(encoding="utf-8"))["g_EmissiveColor"]
    if update:
        identifier = json.loads((NEW_MOD / "meta.json").read_text(encoding="utf-8-sig"))["Identifier"]
    else:
        identifier = str(uuid.uuid4())
    (NEW_MOD / "chara").mkdir(parents=True, exist_ok=True)
    for name in TEXTURES:
        shutil.copyfile(BUILD / f"{name}.tex", NEW_MOD / f"chara/vampire_{name}.tex")
    for source, (local, _game) in MATERIALS.items():
        (NEW_MOD / local).write_bytes(patch_emissive((MATERIAL_SOURCE / source).read_bytes(), colour))
    meta = build_meta(identifier)
    (NEW_MOD / "meta.json").write_text(json.dumps(meta, indent="\t", ensure_ascii=False), encoding="utf-8")
    print(f"{'updated' if update else 'wrote'} {NEW_MOD} (Identifier {identifier})")


if __name__ == "__main__":
    main()
