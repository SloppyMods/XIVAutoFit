"""Make (or update) a Penumbra mod from Unholy plus the textures glow_normal_merge.py built. The original Unholy mod is only read.

    python3 glow_normal_package.py            create NEW_MOD (refuses if it exists)
    python3 glow_normal_package.py --update   replace this script's own files and meta.json in NEW_MOD, keeping its Identifier

meta.json is rebuilt from Unholy's each time:
  - Bump/GLOW: Midlander, Elezen, Miqo'te, Highlander, Roegadyn, Viera (and scaleless Au Ra, which share the same body
    normal) use the merged normals; Au Ra with scales keep Unholy's own. Defaults to "3d and GLOW _ all except scaleless aura".
  - Colour for those races: the Dionys skin with Unholy's tattoo layer instead of Unholy's own base skin (black neck / no neck).
  - "Bandage colour" (priority 95, above the neck group's 90): paints the bandages on, hiding the tattoo and its glow under the cloth.
Materials are Unholy's, unchanged, so the emissive skin type and glow colour stay as they were. Ids are derived from names so
Penumbra keeps the user's choices across updates.
"""
import json
import shutil
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
BUILD = HERE.parent / "builds" / "_unholy"
SOURCE_MOD = Path("/mnt/STORAGE/Penumbra/Unholy_dt_glow_3d_bibo")
NEW_MOD = Path("/mnt/STORAGE/Penumbra/Unholy Glow 3D [Dionys Buff + Bandages]")
ID_SPACE = uuid.UUID("5b0c2f6e-9a51-4c1e-8d7e-3f0a6c2b9d41")
NEW_FILES = {  # file in builds/_unholy -> path inside the mod
    "norm_glow.tex": "chara/unholy_body_band_glow_norm.tex",
    "norm_3d.tex": "chara/unholy_body_band_3d_norm.tex",
    "norm_glow_cloth.tex": "chara/unholy_body_cloth_glow_norm.tex",
    "diffuse_dionys_black_neck.tex": "chara/dionys_skin_unholy_black_neck.tex",
    "diffuse_dionys_no_neck.tex": "chara/dionys_skin_unholy_no_neck.tex",
    "diffuse_dionys_cloth_black_neck.tex": "chara/dionys_skin_unholy_cloth_black_neck.tex",
    "diffuse_dionys_cloth_no_neck.tex": "chara/dionys_skin_unholy_cloth_no_neck.tex",
}
OBSOLETE = (  # written by earlier versions of this script
    "chara/viera_diffuse1_cloth.tex",
    "chara/viera_diffuse_cloth.tex",
    "chara/dionys_buff_band_glow_norm.tex",
    "chara/dionys_buff_band_3d_norm.tex",
    "chara/dionys_buff_cloth_glow_norm.tex",
)
DISPLAY_NAME = "Unholy Glow 3D [Dionys + Sakura Abs + Bandages]"  # Penumbra shows this; the folder keeps its name so settings stay
RACES = ("mid", "high", "viera")
NORMAL_SWAPS = {
    "chara\\viera_normals3.tex": "chara\\unholy_body_band_glow_norm.tex",
    "chara\\viera_normals1.tex": "chara\\unholy_body_band_3d_norm.tex",
}
COLOUR_SWAPS = {
    "chara\\viera_diffuse1.tex": "chara\\dionys_skin_unholy_black_neck.tex",
    "chara\\viera_diffuse.tex": "chara\\dionys_skin_unholy_no_neck.tex",
}
BUFF_NORMALS = {f"chara/bibo_{race}_norm.tex" for race in RACES}
SCALELESS_NORMALS = {"chara/bibo_raen_norm.tex", "chara/bibo_xaela_norm.tex"}
COLOURS = {f"chara/bibo_{race}_base.tex" for race in RACES}


def stable_id(*names: str) -> str:
    return str(uuid.uuid5(ID_SPACE, "/".join(names)))


def retarget(files: dict, scaleless: bool) -> dict:
    """Same file map with the merged normals and Dionys-skin colours where they apply."""
    out = {}
    for game_path, local in files.items():
        if game_path in BUFF_NORMALS or (scaleless and game_path in SCALELESS_NORMALS):
            local = NORMAL_SWAPS.get(local, local)
        if game_path in COLOURS:
            local = COLOUR_SWAPS.get(local, local)
        out[game_path] = local
    return out


def retarget_group(group: dict) -> dict:
    options = [{**o, "Files": retarget(o.get("Files", {}), "scaleless" in o["Name"].lower())} for o in group["Options"]]
    extra = {"DefaultSettings": 2} if group["Name"].startswith("Bump/GLOW") else {}  # "3d and GLOW _ all except scaleless aura"
    return {**group, **extra, "Options": options}


def bandage_group() -> dict:
    name = "Bandage colour"

    def on(label: str, colour: str) -> dict:
        files = {}
        for race in RACES:
            files[f"chara/bibo_{race}_base.tex"] = f"chara\\{colour}"
            files[f"chara/bibo_{race}_norm.tex"] = "chara\\unholy_body_cloth_glow_norm.tex"
        return {"Id": stable_id(name, label), "Name": label, "Description": "", "Files": files}

    return {
        "Type": "Single",
        "Id": stable_id(name),
        "Name": name,
        "Description": "Off: the bandages only add their folds to the normal map; the tattoo stays visible and glows on the bandaged skin.\n"
        "On: paints the Sutured bandages on top and hides the tattoo's bumps and glow under the cloth. Uses the 3D + GLOW normal, "
        "so pick it together with '3d and GLOW _ all except scaleless'. Midlander, Elezen, Miqo'te, Highlander, Roegadyn, Viera only.",
        "Priority": 95,
        "Options": [
            {"Id": stable_id(name, "off"), "Name": "Off - bandage folds only", "Description": "", "Files": {}},
            on("On - black neck", "dionys_skin_unholy_cloth_black_neck.tex"),
            on("On - no neck", "dionys_skin_unholy_cloth_no_neck.tex"),
        ],
    }


def build_meta(identifier: str) -> dict:
    meta = json.loads((SOURCE_MOD / "meta.json").read_text(encoding="utf-8-sig"))
    default = meta.get("DefaultData", {})
    return {
        **meta,
        "Identifier": identifier,
        "Name": DISPLAY_NAME,
        "LastWrite": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.0000000Z"),
        "Description": "Unholy by Tahoni on the Dionys body: Magical Sakura's muscled body normal (abs) and Dionys 'Bubblegum & Freckles' skin, "
        "with the Sutured bandage folds, under the tattoo's fine 3D relief. Glow is unchanged (normal alpha + Unholy's materials). "
        "Au Ra with scales keep Unholy's own textures.\n\n" + meta.get("Description", ""),
        "DefaultData": {**default, "Files": retarget(default.get("Files", {}), False)},
        "Groups": [retarget_group(g) for g in meta["Groups"]] + [bandage_group()],
    }


def main() -> None:
    update = "--update" in sys.argv[1:]
    if NEW_MOD.exists() and not update:
        raise SystemExit(f"{NEW_MOD} already exists; run with --update to replace this script's files in it")
    if update:
        identifier = json.loads((NEW_MOD / "meta.json").read_text(encoding="utf-8"))["Identifier"]
    else:
        shutil.copytree(SOURCE_MOD, NEW_MOD, ignore=shutil.ignore_patterns("*.bak"))
        identifier = str(uuid.uuid4())
    for build_name, mod_path in NEW_FILES.items():
        shutil.copyfile(BUILD / build_name, NEW_MOD / mod_path)
    for old in OBSOLETE:
        (NEW_MOD / old).unlink(missing_ok=True)
    meta = build_meta(identifier)
    (NEW_MOD / "meta.json").write_text(json.dumps(meta, indent="\t", ensure_ascii=False), encoding="utf-8")
    print(f"{'updated' if update else 'wrote'} {NEW_MOD} (Identifier {identifier})")


if __name__ == "__main__":
    main()
