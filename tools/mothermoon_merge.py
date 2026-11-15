"""Mother Moon (Millwood) on the Dionys body with Sakura abs, Sutured bandage folds and its own Dawntrail glow, plus the Sakura wet look.

    python3 mothermoon_merge.py            (writes builds/_mothermoon/*.tex, previews, glow.json, wet.json; about a minute)
    python3 mothermoon_merge.py --gen2     (writes only the Gen2/vanilla set: gen2_*.tex, preview_gen2_*.png, gen2.json; never the Bibo+ files)

Same formula as vampire_merge.py (Vampire Heartbeat) and glow_normal_merge.py (Unholy), whose helpers this imports unchanged.
Differences:
  - Colour: Mother Moon ships no transparent tattoo layer (its colour textures have the author's own base skin baked in), so the
    four tattoo layers are read out of the author's GIMP file (moonbibo.xcf, read by the small reader below) and composited over
    the Dionys skin in linear light, which is how the author's file composites. The XCF's own base layer is left out.
  - Glow: Mother Moon's normal is already Dawntrail-native (alpha = glow mask), so the mask and the glow colour are used as shipped.
  - Normal: red/green are Sakura's body plus the Sutured folds, exactly as vampire_merge.py builds them (Mother Moon has no 3D
    relief to carry). Blue is min(Sakura, Mother Moon): the author paints the tattoo into the normal's blue channel.
  - The 2048 Mother Moon data is repeated 2x into the 4096 layout, one channel at a time (never through Pillow's RGBA mode).
  - Stop conditions are asserted before anything is written: the XCF layers, the XCF reproducing the shipped colour, and Mother
    Moon's normal lining up with Sakura's (same Bibo+ UV layout at half the resolution).
  - wet.json records what makes Sakura's body look wet (see investigate_wet) for mothermoon_package.py.

Outputs (builds/_mothermoon/):
  norm_3d.tex, norm_3d_cloth.tex              no glow: alpha 255 (cloth: tattoo marking hidden under the bandage)
  norm_glow.tex, norm_glow_cloth.tex          glow mask in alpha (cloth: marking and glow hidden under the bandage)
  diffuse.tex, diffuse_cloth.tex              Dionys skin + Mother Moon tattoo layers (+ bandage colour)
  glow.json, wet.json, preview_*.png, render/ (full-size PNG inputs for render_glow.py)

--gen2 (vanilla gloves and boots: skin on mt_c0201b0001_a.mtrl, the 1024 x 2048 Gen2 layout, built at 2048 x 4096):
  The Gen2 layout is the right half of the Bibo+ layout for most of the body (measured, not assumed: see layout_scores and pick_half), but the
  hands, feet and chest are laid out differently. The "agreement area" is where Sakura's Gen2 and Bibo+ normals have identical
  red/green. Only inside it are Dionys skin and the Sutured bandages carried across; elsewhere the Gen2 colour is the Muse+ Gen2 skin
  the character wears today. Flat normals match whatever the layout, so on flat texels the colour also has to agree and the bandage
  needs real agreement close by (carry_masks). Mother Moon's own Gen2 tattoo (moongen2.xcf) and glow (mm4gen2glow) go on everywhere.
  gen2_norm_3d.tex, gen2_norm_3d_cloth.tex, gen2_norm_glow.tex, gen2_norm_glow_cloth.tex, gen2_diffuse.tex, gen2_diffuse_cloth.tex,
  preview_gen2_{diffuse,diffuse_cloth,glow_mask,normal}.png and gen2.json (the layout measurement and build record).
"""
import json
import struct
import sys
import tempfile
import zipfile
from pathlib import Path

import numpy as np
from PIL import Image

sys.dont_write_bytecode = True  # importing the helpers must not write tools/__pycache__/
sys.path.insert(0, str(Path(__file__).resolve().parent))
import glow_normal_merge as base  # noqa: E402
import tex_io  # noqa: E402

Image.MAX_IMAGE_PIXELS = None
OUT = base.HERE.parent / "builds" / "_mothermoon"
MM_DIR = Path("/home/you/Downloads/Telegram Desktop/Skin Mods/Mother Moon")
PMP = MM_DIR / "Mother Moon.pmp"
XCF = MM_DIR / "DIY Kit-20261113T220316Z-1-001/DIY Kit/moonbibo.xcf"
SAKURA_MOD = Path("/mnt/STORAGE/Penumbra/Magical Sakura life-4K Glow 7.5.1 (2)")
SAKURA_MATERIALS = SAKURA_MOD / "Sakura life/Univeral/Mid,hight,Vera,auras"  # Glow Version 1 ("ON Normal"), the one SloppyMods has enabled
SAKURA_MASK = SAKURA_MOD / "Sakura life/Update-7-2/chara/MID/bplus-7-2-doppel-Multi-MID.tex"  # main option container 226
BIBO_MID_MASK = Path("/mnt/STORAGE/Penumbra/[HS] Bibo+ (Bibo+ Base Install)/files/common/2/bibo_mid_mask.tex")
DIONYS_MULTI = Path("/mnt/STORAGE/Penumbra/Dionys V1.4.0/Dionys/Textures/Skin/Multi/multi_base.tex")
UNHOLY_GLOW_MATERIALS = {  # race code -> Unholy-derived glow material (Mother Moon ships its own c0201 only)
    "c0401": Path("/mnt/STORAGE/Penumbra/Unholy Glow 3D [Dionys + Sakura Abs + Bandages]/chara/mt_c0401b0001_bibo.mtrl"),
    "c1801": Path("/mnt/STORAGE/Penumbra/Unholy Glow 3D [Dionys + Sakura Abs + Bandages]/chara/mt_c1801b0001_bibo_e.mtrl"),
}
RACES = {"c0201": "mid", "c0401": "high", "c1801": "viera"}
EMISSIVE_ID = 0x38A64362
SKIN_TYPE_KEY, GLOW_TYPE_VALUE = 0x380CAED0, 0x72E697CD
LAYER_NAMES = ["Body Light", "Arm/Leg Sparkles", "Arms/Legs Dark", "sparklenails", "Bibo Smooth_D.png"]  # top first
XCF_MODE_NORMAL = 28
XCF_PRECISION_BYTES = {150: 1, 250: 2}  # GIMP precision code (non-linear) -> bytes per channel
COLOUR_MEAN_LIMIT, COLOUR_NEAR_LIMIT, COLOUR_NEAR_SHARE = 1.0, 16, 0.99  # XCF composite vs the shipped colour, /255
UV_CORRELATION_LIMIT = 0.4
LIMB_GLOW_LEVEL = 112  # glow alpha (of 255) on a fully painted dark arm/leg sleeve: about 44% strength (112/255); the one knob, both layouts
BANDAGE_GREY = 170  # mean R, G and B of the bandage over fully covered cloth (cream before); the fold shading is kept around it
LIMB_RECORD = OUT / "limbglow.json"
ILLUSION = Path("/mnt/STORAGE/Penumbra/[ST] Illusion - Tattoo/Normal Options")
ILLUSION_PAIRS = {"Softer Pores": ("Softer Pores [GLOW]", "Softer Pores +Hands [GLOW]"), "Ancient Markings": ("Ancient Markings [GLOW]", "Ancient Markings +Hands [GLOW]")}
ILLUSION_RISE = 32  # +Hands alpha higher than the plain option's by more than this (of 255) marks the hand and finger islands
LUMA = np.array([0.2126, 0.7152, 0.0722], "f4")

# Gen2 / vanilla (mt_c0201b0001_a.mtrl)
GEN2_XCF = MM_DIR / "DIY Kit-20261113T220316Z-1-001/DIY Kit/moongen2.xcf"
GEN2_MATERIAL = "chara/mt_c0201b0001_a_glowset.mtrl"
SAKURA_UPDATE = SAKURA_MOD / "Sakura life/Update-7-2/chara/MID/Alphas"
SAKURA_GEN2_NORMAL = SAKURA_UPDATE / "gen2-7-2-leer-alpha-MID.tex"
SAKURA_BIBO_NORMAL = SAKURA_UPDATE / "bplus-7-2-doppel-alpha-MID-off.tex"
SAKURA_GEN2_WET = SAKURA_MATERIALS / "mt_c0201b0001_1_a.mtrl"
MUSE_GEN2_BASE = Path("/mnt/STORAGE/Penumbra/[HS] Muse+ (YAS)/files/Bibo Materials/Install/chara/human/c0201/obj/body/b0001/texture/c0201b0001_base.tex")
GEN2_LAYER_NAMES = ["Body Light", "Arms/Legs Light", "Arms/legs dark", "Background"]  # top first; the first three are the tattoo
GEN2_TEXTURE_NAMES = ("norm_3d", "norm_3d_cloth", "norm_glow", "norm_glow_cloth", "diffuse", "diffuse_cloth")
GEN2_LIMB_NAMES = ("norm_limbglow", "norm_limbglow_cloth")
GEN2_COLOUR_MEAN_LIMIT, GEN2_COLOUR_NEAR_SHARE = 4.5, 0.93  # Gen2 limits (the Bibo+ ones, 1.0 and 99%, do not transfer: Muse+ is only an approximate base)
GEN2_ALIGN_SHIFTS = (-16, -12, -8, -4, 4, 8, 12, 16)  # texels at 1024 x 2048, both directions
GEN2_ALIGN_MARGIN, GEN2_ALIGN_MIN = 0.02, 0.15  # zero-offset correlation must beat the median shifted one by this much, and reach this
LAYOUT_MIN_SCORE, LAYOUT_MIN_LEAD = 0.25, 2.0  # a half must match this share of texels, and lead the runner-up this many times
SPECK_CORE_DEPTH, HOLE_MAX = 4, 8  # agreement clean-up: drop areas too small to hold a depth-4 core; fill disagreeing holes up to this many texels
FLAT_TOLERANCE = 2  # Sakura Gen2 red/green within this of 128: a flat normal, so identical normals there prove nothing about the layout
COLOUR_DIFFER_LIMIT, COLOUR_DIFFER_RADIUS, COLOUR_DIFFER_MARGIN = 16, 4, 8  # flat texels: Muse+ vs Dionys /255, local mean over a 9-texel box, grown 8 texels
DIONYS_RELIEF_LIMIT, RELIEF_OPENING, RELIEF_MARGIN = 4, 3, 24  # Dionys normal red/green > 4 from 128 where Sakura's Gen2 is flat: a sculpted
# Dionys island (genitals) the Gen2 layout lacks; blobs that survive a depth-3 opening (not thin island rims), grown 24 texels (at 1024 x 2048)
BANDAGE_REACH, BANDAGE_EVIDENCE_MIN = 8, 5000  # bandage pieces only within 8 texels of real (non-flat) agreement that forms a patch of at
# least 5000 texels (the hand islands hold only chance-match specks, which must not get bandage flakes)
BANDAGE_CLOSE = 16  # then fill what that area encloses and close gaps up to this many texels wide, inside the colour area (no holes in the wraps)
SKIN_FEATHER = 12  # Dionys fades into the Muse+ skin over this many texels inside its area


# ---------------------------------------------------------------- small readers
def tex_bytes_to_rgba(data: bytes) -> np.ndarray:
    """Top mip of a B8G8R8A8 .tex held in memory, as (h, w, 4) RGBA."""
    _, fmt, width, height, _, _ = struct.unpack_from("<IIHHHH", data)
    assert fmt == tex_io.FORMAT_BGRA8, hex(fmt)
    return np.frombuffer(data, "u1", width * height * 4, tex_io.HEADER_SIZE).reshape(height, width, 4)[..., [2, 1, 0, 3]]


def parse_mtrl(data: bytes) -> dict:
    """Dawntrail .mtrl: shader, texture paths, shader keys and constants (same layout as vampire_package.patch_emissive)."""
    _ver, _size, data_size, string_size, shader_off, tex_count, uv_count, set_count, extra = struct.unpack_from("<IHHHHBBBB", data, 0)
    offsets = [struct.unpack_from("<H", data, 16 + 4 * i)[0] for i in range(tex_count)]
    pos = 16 + 4 * (tex_count + uv_count + set_count)
    strings = data[pos:pos + string_size]

    def text(offset: int) -> str:
        return strings[offset:strings.index(b"\0", offset)].decode()

    pos += string_size + extra + data_size
    _list, key_count, const_count, sampler_count = struct.unpack_from("<HHHH", data, pos)
    keys_start = pos + 12
    keys = dict(struct.unpack_from("<II", data, keys_start + 8 * i) for i in range(key_count))
    consts_start = keys_start + 8 * key_count
    values = consts_start + 8 * const_count + 12 * sampler_count
    consts = {}
    for i in range(const_count):
        cid, offset, size = struct.unpack_from("<IHH", data, consts_start + 8 * i)
        consts[cid] = tuple(struct.unpack_from(f"<{size // 4}f", data, values + offset))
    return {"shader": text(shader_off), "textures": [text(o) for o in offsets], "keys": keys, "consts": consts}


def read_xcf(path: Path) -> list[dict]:
    """GIMP XCF v011+ (64-bit offsets), RLE tiles, 16-bit (250) or 8-bit (150) non-linear: layers top first, each
    {name, type, props, mask, pixels = float32 (h, w, channels) in [0, 1]}."""
    d = path.read_bytes()
    assert d[:9] == b"gimp xcf " and d[9:13] >= b"v011", "not a 64-bit-offset XCF"
    width, height, _base_type, precision = struct.unpack_from(">IIII", d, 14)
    assert precision in XCF_PRECISION_BYTES, f"expected 8-bit (150) or 16-bit (250) non-linear, got {precision}"
    sample_bytes = XCF_PRECISION_BYTES[precision]

    def props(p: int) -> tuple[dict, int]:
        out = {}
        while True:
            kind, length = struct.unpack_from(">II", d, p)
            p += 8
            out[kind] = d[p:p + length]
            p += length
            if kind == 0:
                return out, p

    image_props, p = props(30)
    assert image_props[17][0] == 1, "expected RLE compression"
    pointers = []
    while (value := struct.unpack_from(">Q", d, p)[0]) != 0:
        pointers.append(value)
        p += 8

    def rle_tile(pos: int, count: int, bpp: int) -> np.ndarray:
        planes = []
        for _ in range(bpp):
            out = bytearray()
            while len(out) < count:
                v = d[pos]
                pos += 1
                if v >= 128:  # literal run
                    n = 256 - v
                    if n == 128:
                        n = (d[pos] << 8) | d[pos + 1]
                        pos += 2
                    out += d[pos:pos + n]
                    pos += n
                else:  # repeated byte
                    n = v + 1
                    if n == 128:
                        n = (d[pos] << 8) | d[pos + 1]
                        pos += 2
                    out += bytes([d[pos]]) * n
                    pos += 1
            planes.append(np.frombuffer(bytes(out[:count]), "u1"))
        return np.stack(planes, -1)

    layers = []
    for lp in pointers:
        _lw, _lh, layer_type, name_len = struct.unpack_from(">IIII", d, lp)
        name = d[lp + 16:lp + 16 + name_len - 1].decode()
        layer_props, q = props(lp + 16 + name_len)
        hierarchy, mask = struct.unpack_from(">QQ", d, q)
        _hw, _hh, bpp = struct.unpack_from(">III", d, hierarchy)
        level = struct.unpack_from(">Q", d, hierarchy + 12)[0]
        lw, lh = struct.unpack_from(">II", d, level)
        tiles, r = [], level + 8
        while (value := struct.unpack_from(">Q", d, r)[0]) != 0:
            tiles.append(value)
            r += 8
        raw = np.zeros((lh, lw, bpp), "u1")
        across = (lw + 63) // 64
        for i, tp in enumerate(tiles):
            y0, x0 = divmod(i, across)
            y0, x0 = y0 * 64, x0 * 64
            th, tw = min(64, lh - y0), min(64, lw - x0)
            raw[y0:y0 + th, x0:x0 + tw] = rle_tile(tp, th * tw, bpp).reshape(th, tw, bpp)
        if sample_bytes == 2:
            words = raw.reshape(lh, lw, bpp // 2, 2).astype(np.uint16)
            pixels = ((words[..., 0] << 8) | words[..., 1]).astype(np.float32) / 65535
        else:
            pixels = raw.astype(np.float32) / 255
        layers.append({"name": name, "type": layer_type, "props": layer_props, "mask": mask, "pixels": pixels})
    return layers


def decode_bc(path: Path, folder: Path) -> np.ndarray:
    """Top mip of a BC-compressed .tex as uint8 RGBA, through a temporary .dds in `folder` (never builds/_unholy)."""
    dds = folder / (path.stem + ".dds")
    tex_io.tex_to_dds(str(path), str(dds))
    with Image.open(dds) as image:
        return np.asarray(image.convert("RGBA"))


# ---------------------------------------------------------------- colour maths
def to_linear(c: np.ndarray) -> np.ndarray:
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def to_srgb(c: np.ndarray) -> np.ndarray:
    return np.where(c <= 0.0031308, c * 12.92, 1.055 * np.power(np.clip(c, 0, None), 1 / 2.4) - 0.055)


def composite_linear(bottom_srgb: np.ndarray, layers_bottom_first: list[dict]) -> np.ndarray:
    """Straight-alpha 'over' of RGBA layers onto an opaque sRGB colour, done in linear light; returns sRGB in [0, 1]."""
    result = to_linear(bottom_srgb)
    for layer in layers_bottom_first:
        rgba = layer["pixels"]
        alpha = rgba[..., 3:4]
        result = result * (1 - alpha) + to_linear(rgba[..., :3]) * alpha
    return np.clip(to_srgb(result), 0, 1)


def double(channels: np.ndarray) -> np.ndarray:
    """2048 -> 4096 by repeating each texel 2x2, per channel (exact; no Pillow RGBA resize that would premultiply)."""
    return np.repeat(np.repeat(channels, 2, axis=0), 2, axis=1)


# ---------------------------------------------------------------- limb glow and grey bandages
def limb_glow(glow: np.ndarray, layer_alpha: np.ndarray, band_alpha: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """(limb, limb_cloth) glow alpha: max(plain glow, LIMB_GLOW_LEVEL x the sleeve layer's alpha), hidden under the bandage like the plain one."""
    limb = np.maximum(glow, np.rint(LIMB_GLOW_LEVEL * double(layer_alpha).astype("f8")).astype("u1"))
    return limb, np.rint(limb.astype("f4") * (1 - band_alpha)).astype("u1")


def grey_bandage(band_rgb: np.ndarray, band_alpha: np.ndarray) -> np.ndarray:
    """The bandage colour recoloured neutral: each texel's luminance (straight colour) scaled so that fully covered cloth averages
    BANDAGE_GREY. The scale comes from the whole PNG, so both layouts share it; the fold shading is kept at 0.84x contrast."""
    luminance = band_rgb @ LUMA
    scale = BANDAGE_GREY / 255 / float(luminance[band_alpha >= 0.999].mean())
    return np.repeat(np.clip(luminance * scale, 0, 1)[..., None], 3, axis=-1)


def update_limb_record(**parts) -> None:
    """Merge parts into limbglow.json (the Bibo+ and Gen2 runs each add their own)."""
    def merge(old: dict, new: dict) -> dict:
        return {**old, **{k: merge(old.get(k, {}), v) if isinstance(v, dict) else v for k, v in new.items()}}

    record = merge(json.loads(LIMB_RECORD.read_text(encoding="utf-8")) if LIMB_RECORD.exists() else {}, parts)
    record["level"] = LIMB_GLOW_LEVEL
    record.setdefault("bandage", {})["grey"] = BANDAGE_GREY
    LIMB_RECORD.write_text(json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8")


def sleeve_record(layer_alpha: np.ndarray, name: str) -> dict:
    return {"layer": name, "share": round(float((layer_alpha > 0).mean()), 4), "full_share": round(float((layer_alpha >= 0.999).mean()), 4)}


def bandage_colours(tag: str, band_rgb: np.ndarray, band_png_alpha: np.ndarray, plain: np.ndarray, cloth: np.ndarray) -> dict:
    """Mean colour (0-255) over fully covered cloth (PNG alpha 1 and the cloth differs from the plain colour): the PNG's cream, and the texture."""
    covered = (band_png_alpha >= 0.999) & (plain[..., :3] != cloth[..., :3]).any(-1)
    return {"before": {tag: [round(float(v), 2) for v in (band_rgb[covered] * 255).mean(0)]}, "after": {tag: [round(float(v), 2) for v in cloth[..., :3][covered].mean(0)]}}


def reference_record(pairs: dict) -> dict:
    hands = [p["hands_alpha_median"] for p in pairs.values()]
    verdict = (f"+Hands lifts the hand and finger islands from nothing (plain median {max(p['plain_alpha_median'] for p in pairs.values()):.0f}) to a median of {min(hands):.0f} to {max(hands):.0f} of 255, "
               f"about {sum(hands) / len(hands) / 2.55:.0f}%: it sits near half (the finger block alone is nearer 127, the hands lower). "
               f"Built at {LIMB_GLOW_LEVEL} (about 44%) on a fully painted sleeve, scaled by the layer's own opacity at the edges.")
    return {"pairs": pairs, "verdict": verdict}


def measure_illusion() -> dict:
    """What the Illusion Tattoo '+Hands [GLOW]' option does to the glow alpha. Read only; alpha only, both at 2048 (the plain 4096 one is
    averaged down 2x2); the hand and finger islands are the texels where +Hands is higher by more than ILLUSION_RISE."""
    pairs = {}
    scratch_ctx = tempfile.TemporaryDirectory(prefix="illusion-")  # outside the workdir
    scratch = Path(scratch_ctx.name)
    for name, (plain_dir, hands_dir) in ILLUSION_PAIRS.items():
        alpha = {}
        for tag, folder in (("plain", plain_dir), ("hands", hands_dir)):
            path = ILLUSION / folder / "chara" / "bibo_mid_norm.tex"
            alpha[tag] = decode_bc(path, scratch)[..., 3].astype("f4")
            scratch_file = scratch / "bibo_mid_norm.dds"
            scratch_file.unlink(missing_ok=True)
        plain = alpha["plain"]
        if plain.shape[0] == 2 * alpha["hands"].shape[0]:
            plain = plain.reshape(plain.shape[0] // 2, 2, plain.shape[1] // 2, 2).mean((1, 3))
        assert plain.shape == alpha["hands"].shape, (name, plain.shape, alpha["hands"].shape)
        islands = alpha["hands"] - plain > ILLUSION_RISE
        pairs[name] = {"texels": int(islands.sum()), "plain_alpha_median": float(np.median(plain[islands])), "hands_alpha_median": float(np.median(alpha["hands"][islands]))}
        print(f"Illusion {name}: {pairs[name]}")
    scratch_ctx.cleanup()
    return pairs


# ---------------------------------------------------------------- stop conditions
def stop(message: str) -> None:
    sys.exit(f"BLOCKED, nothing written: {message}")


def check_layers(layers: list[dict]) -> None:
    names = [layer["name"] for layer in layers]
    if names != LAYER_NAMES:
        stop(f"XCF layers are {names}, expected {LAYER_NAMES}")
    for index, layer in enumerate(layers):
        props, name = layer["props"], layer["name"]
        want_channels = 4 if index < 4 else 3
        mode = struct.unpack(">I", props[7])[0]
        opacity = struct.unpack(">f", props[33])[0]
        visible = struct.unpack(">I", props[8])[0]
        offset = struct.unpack(">ii", props[15])
        if layer["pixels"].shape != (2048, 2048, want_channels) or mode != XCF_MODE_NORMAL or opacity != 1.0 or not visible or offset != (0, 0) or layer["mask"]:
            stop(f"XCF layer {name!r}: shape {layer['pixels'].shape}, mode {mode}, opacity {opacity}, visible {visible}, offset {offset}, mask {layer['mask']}; want Normal, opaque, visible, (0, 0), no mask")


def check_reproduction(layers: list[dict], shipped_rgb: np.ndarray) -> tuple[float, float]:
    """The author's five layers in linear light must reproduce the shipped moonbibo.tex."""
    everything = composite_linear(layers[4]["pixels"], layers[3::-1])
    diff = np.abs(everything * 255 - shipped_rgb.astype("f4"))
    mean, near = float(diff.mean()), float((diff.max(-1) <= COLOUR_NEAR_LIMIT).mean())
    print(f"XCF (all five layers, linear light) vs the pmp's moonbibo.tex: mean abs diff {mean:.3f}/255, {near * 100:.2f}% of texels within {COLOUR_NEAR_LIMIT}/255")
    if mean > COLOUR_MEAN_LIMIT or near < COLOUR_NEAR_SHARE:
        stop(f"the XCF does not reproduce the shipped colour: mean {mean:.3f}/255 (<= {COLOUR_MEAN_LIMIT}), within {COLOUR_NEAR_LIMIT}/255 {near * 100:.2f}% (>= {COLOUR_NEAR_SHARE * 100:.0f}%)")
    return mean, near


def check_layout(mm_normal: np.ndarray) -> tuple[float, float]:
    """Mother Moon's red/green must correlate with Sakura's body normal at 2048 (the same Bibo+ UV layout at half the size)."""
    sakura_half = tex_io.read_mip(str(base.OUT / "sakura_body_normal.tex"), 1)
    corr = tuple(float(np.corrcoef(mm_normal[..., c].ravel().astype("f4"), sakura_half[..., c].ravel().astype("f4"))[0, 1]) for c in range(2))
    print(f"Mother Moon normal vs Sakura's body normal at 2048: red {corr[0]:.3f}, green {corr[1]:.3f}")
    if not all(np.isfinite(c) and c >= UV_CORRELATION_LIMIT for c in corr):  # a flat channel gives NaN, which must stop too
        stop(f"Mother Moon's normal red/green correlate {corr[0]:.3f}/{corr[1]:.3f} with Sakura's at 2048 (want >= {UV_CORRELATION_LIMIT}); not the same UV layout")
    return corr


# ---------------------------------------------------------------- the wet look
def investigate_wet(glowset: dict, folder: Path) -> dict:
    """Compare Sakura's three `_1_bibo` body materials and its mask with what Mother Moon / Unholy ship, and say whether the wet
    look can ride on the material alone (the mod then clones Sakura's material with only g_EmissiveColor changed)."""
    plain = {"c0201": glowset}
    for code, path in UNHOLY_GLOW_MATERIALS.items():
        plain[code] = parse_mtrl(path.read_bytes())
    evidence, materials, usable = [], {}, True
    for code, race in RACES.items():
        source = SAKURA_MATERIALS / f"mt_{code}b0001_1_bibo.mtrl"
        sakura = parse_mtrl(source.read_bytes())
        ref = plain[code]
        wanted = [f"chara/bibo_{race}_sakura_{kind}.tex" for kind in ("base", "norm", "mask")]
        ok = sakura["shader"] == "skin.shpk" and sakura["keys"].get(SKIN_TYPE_KEY) == GLOW_TYPE_VALUE and EMISSIVE_ID in sakura["consts"] and sakura["textures"] == wanted
        usable = usable and ok
        extra_keys = {f"{k:08X}={v:08X}": "extra key" for k, v in sakura["keys"].items() if ref["keys"].get(k) != v}
        changed = {f"{k:08X}": f"{[round(x, 2) for x in ref['consts'][k]]} -> {[round(x, 2) for x in v]}" for k, v in sakura["consts"].items() if k != EMISSIVE_ID and k in ref["consts"] and ref["consts"][k] != v}
        added = {f"{k:08X}": [round(x, 2) for x in v] for k, v in sakura["consts"].items() if k not in ref["consts"]}
        evidence.append(f"{code} ({race}): Sakura {source.name} vs {'Mother Moon glowset' if code == 'c0201' else 'Unholy-derived glow material'}: extra keys {sorted(extra_keys)}; constants changed {changed}; constants added {added}; textures {sakura['textures']}; emissive-type skin.shpk: {ok}")
        materials[code] = {"source": str(source)}
    def load(path: Path) -> np.ndarray:
        compressed = tex_io.read_header(str(path))[0] != tex_io.FORMAT_BGRA8
        return decode_bc(path, folder) if compressed else tex_io.read_bgra(str(path))

    masks = {"Bibo+ Base Install bibo_mid_mask": load(BIBO_MID_MASK), "Dionys multi_base": load(DIONYS_MULTI), "Sakura bplus-7-2-doppel-Multi-MID": load(SAKURA_MASK)}
    stats = {name: [f"{img[..., c].mean():.1f}+-{img[..., c].std():.1f}" for c in range(3)] for name, img in masks.items()}
    gap = np.abs(masks["Bibo+ Base Install bibo_mid_mask"].astype("f4") - masks["Dionys multi_base"])[..., :3].mean((0, 1))
    evidence.append(f"mask texture mean+-std in R/G/B (Sakura's is 4096 B8G8R8A8, the body masks are 2048 BC7): {stats}; Bibo+ Base mid mask vs Dionys multi_base, mean abs difference per channel: {[round(float(v), 2) for v in gap]}/255 (the same body mask)")
    evidence.append("Sakura's mask carries its snake/cherry-blossom tattoo in R, G and B (std ~50 against ~0 for the body masks), so it is not shipped.")
    summary = (
        "Sakura's per-race `_1_bibo` body materials differ from Mother Moon's/Unholy's glow materials in an extra shader key "
        "D2777173=584265DD and in changed/extra constants (see evidence); Sakura's mask texture also differs from the plain body mask. "
        "Carried as a separate 'Wet skin' toggle through the material only: Sakura's `_1_bibo` material is cloned with only "
        "g_EmissiveColor changed, its three texture paths mapped to this mod's colour, normal and the body's current mask. "
        "Whatever part of the wet look lives in Sakura's own mask (tattoo-patterned, shifted levels) is not carried, by design. "
        "Untested in game." if usable else
        "Sakura's materials do not have the expected shape, so the wet look is not carried over.")
    mask = ("Mid: copy of Bibo+ Base Install's bibo_mid_mask.tex; high and viera: copy of Dionys multi_base.tex. This is the mask the "
            "job spec measured for SloppyMods's Default collection (Dionys 'Smooth & Buff' maps multi_base for Highlander/Viera, Bibo+ Base "
            "Install supplies mid); the collection files were not re-read by this script. The two differ by under 1/255 on average. "
            "Sakura's own mask is not shipped.")
    result = {"carried": usable, "summary": summary, "evidence": evidence, "mask": mask}
    if usable:
        result["materials"] = materials
    return result


# ---------------------------------------------------------------- Gen2 / vanilla: which half of the Bibo+ layout
def half_candidates(bibo: np.ndarray) -> dict:
    """The four ways a Gen2-layout texture could be cut out of a Bibo+-layout one (half the width)."""
    w = bibo.shape[1] // 2
    left, right = bibo[:, :w], bibo[:, w:]
    return {"right": right, "left": left, "right_mirrored": right[:, ::-1], "left_mirrored": left[:, ::-1]}


def layout_scores(gen2: np.ndarray, bibo: np.ndarray, channels: int) -> dict:
    """Share of texels where the Gen2 file equals each candidate half exactly, over the first `channels` channels."""
    scores = {}
    for name, half in half_candidates(bibo).items():
        assert half.shape[:2] == gen2.shape[:2], (name, half.shape, gen2.shape)
        same = (gen2[..., :channels].astype(np.int16) == half[..., :channels]).all(-1)
        scores[name] = round(float(same.mean()), 4)
    return scores


def pick_half(pairs: dict) -> tuple[str | None, str]:
    """The candidate that wins on every pair (clearly: enough texels and a clear lead), or None with the reason."""
    winners = {}
    for pair, scores in pairs.items():
        ranked = sorted(scores, key=scores.get, reverse=True)
        best, second = ranked[0], ranked[1]
        if scores[best] < LAYOUT_MIN_SCORE or scores[best] < LAYOUT_MIN_LEAD * scores[second]:
            return None, f"{pair}: best candidate {best} {scores[best]:.3f} is not clearly ahead of {second} {scores[second]:.3f}"
        winners[pair] = best
    if len(set(winners.values())) != 1:
        return None, f"the pairs disagree: {winners}"
    return next(iter(winners.values())), ""


def agreement_area(sakura_gen2: np.ndarray, sakura_half: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """(raw, area): raw is where Sakura's two normals have identical red/green; area is raw without the specks (agreeing areas too
    small to hold a depth-SPECK_CORE_DEPTH core, which are chance matches inside differently laid-out islands) and with the tiny
    disagreeing holes (up to HOLE_MAX texels) filled. The area is never narrower than raw less its specks."""
    raw = (sakura_gen2[..., :2] == sakura_half[..., :2]).all(-1)
    core = base.ndimage.binary_erosion(raw, iterations=SPECK_CORE_DEPTH, border_value=1)
    labels, count = base.ndimage.label(raw)
    keep = np.zeros(count + 1, bool)
    keep[np.unique(labels[core])] = True
    keep[0] = False
    area = keep[labels]
    holes, count = base.ndimage.label(~area)
    small = np.zeros(count + 1, bool)
    small[1:] = base.ndimage.sum(~area, holes, range(1, count + 1)) <= HOLE_MAX
    return raw, area | small[holes]


def carry_masks(area: np.ndarray, raw: np.ndarray, sakura_gen2: np.ndarray, muse: np.ndarray, dionys_half: np.ndarray, dionys_normal_half: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """(skin_weight, colour_area, bandage_area) at 2048 x 4096. Flat normals match whatever the layout, so on flat texels the area
    only carries Dionys colour where the Muse+ and Dionys skins look alike (both plain skin or padding); where they differ (toenails,
    nipple art in differently laid-out islands), or where the Dionys normal is sculpted (its genital island), the Muse+ skin stays. Bandage pieces need real, non-flat agreement close by.
    skin_weight is the Dionys share: 1 deep inside colour_area, fading to 0 at its edge over SKIN_FEATHER texels."""
    flat = (np.abs(sakura_gen2[..., :2].astype(np.int16) - 128) <= FLAT_TOLERANCE).all(-1)
    diff = double(np.abs(muse[..., :3].astype(np.int16) - dionys_half[..., :3]).max(-1)).astype("f4")
    local = base.ndimage.uniform_filter(diff, 2 * COLOUR_DIFFER_RADIUS + 1)
    flat_half = flat.reshape(flat.shape[0] // 2, 2, flat.shape[1] // 2, 2).all((1, 3))
    relief = (np.abs(dionys_normal_half[..., :2].astype(np.int16) - 128).max(-1) > DIONYS_RELIEF_LIMIT) & flat_half
    relief = base.ndimage.binary_dilation(base.ndimage.binary_opening(relief, iterations=RELIEF_OPENING), iterations=RELIEF_MARGIN)
    differ = base.ndimage.binary_dilation((local > COLOUR_DIFFER_LIMIT) | (diff > 2 * COLOUR_DIFFER_LIMIT), iterations=COLOUR_DIFFER_MARGIN) | double(relief)
    colour_area = area & ~(flat & differ)
    evidence = raw & ~flat
    labels, count = base.ndimage.label(evidence)
    keep = np.zeros(count + 1, bool)
    keep[1:] = base.ndimage.sum(evidence, labels, range(1, count + 1)) >= BANDAGE_EVIDENCE_MIN
    bandage_area = colour_area & base.ndimage.binary_dilation(keep[labels], iterations=BANDAGE_REACH)
    closed = base.ndimage.binary_closing(np.pad(bandage_area, BANDAGE_CLOSE), iterations=BANDAGE_CLOSE)[BANDAGE_CLOSE:-BANDAGE_CLOSE, BANDAGE_CLOSE:-BANDAGE_CLOSE]
    bandage_area = colour_area & base.ndimage.binary_fill_holes(closed | bandage_area)
    skin_weight = np.clip(base.ndimage.distance_transform_edt(colour_area) / SKIN_FEATHER, 0, 1).astype("f4")
    return skin_weight, colour_area, bandage_area


def box_share(mask: np.ndarray, rows: tuple[float, float], cols: tuple[float, float]) -> float:
    h, w = mask.shape
    return round(float(mask[int(rows[0] * h):int(rows[1] * h), int(cols[0] * w):int(cols[1] * w)].mean()), 4)


# ---------------------------------------------------------------- Gen2 / vanilla: stop conditions
def check_gen2_layers(layers: list[dict]) -> None:
    names = [layer["name"] for layer in layers]
    if names != GEN2_LAYER_NAMES:
        stop(f"moongen2.xcf layers are {names}, expected {GEN2_LAYER_NAMES}")
    for layer in layers:
        props, name = layer["props"], layer["name"]
        mode = struct.unpack(">I", props[7])[0]
        opacity = struct.unpack(">f", props[33])[0]
        visible = struct.unpack(">I", props[8])[0]
        offset = struct.unpack(">ii", props[15])
        if layer["pixels"].shape != (2048, 1024, 4) or mode != XCF_MODE_NORMAL or opacity != 1.0 or not visible or offset != (0, 0) or layer["mask"]:
            stop(f"moongen2.xcf layer {name!r}: shape {layer['pixels'].shape}, mode {mode}, opacity {opacity}, visible {visible}, offset {offset}, mask {layer['mask']}; want 2048 x 1024 RGBA, Normal, opaque, visible, (0, 0), no mask")
    if float(layers[3]["pixels"][..., 3].max()) != 0.0:
        stop("moongen2.xcf Background layer is not fully transparent (it was expected to hold no base skin)")


def check_gen2_reproduction(layers: list[dict], muse_rgb: np.ndarray, shipped_rgb: np.ndarray) -> dict:
    """The three tattoo layers in linear light over the Muse+ Gen2 skin must reproduce Mother Moon's shipped moongen2.tex."""
    everything = composite_linear(muse_rgb.astype("f4") / 255, layers[2::-1])
    diff = np.abs(everything * 255 - shipped_rgb.astype("f4"))
    mean, near = float(diff.mean()), float((diff.max(-1) <= COLOUR_NEAR_LIMIT).mean())
    print(f"XCF (three tattoo layers over the Muse+ Gen2 skin, linear light) vs the pmp's moongen2.tex: mean abs diff {mean:.3f}/255, {near * 100:.2f}% of texels within {COLOUR_NEAR_LIMIT}/255")
    if mean > GEN2_COLOUR_MEAN_LIMIT or near < GEN2_COLOUR_NEAR_SHARE:
        stop(f"the Gen2 XCF layers do not reproduce the shipped Gen2 colour: mean {mean:.3f}/255 (<= {GEN2_COLOUR_MEAN_LIMIT}), within {COLOUR_NEAR_LIMIT}/255 {near * 100:.2f}% (>= {GEN2_COLOUR_NEAR_SHARE * 100:.0f}%)")
    return {"mean": round(mean, 3), "within16": round(near, 4), "limit_mean": GEN2_COLOUR_MEAN_LIMIT, "limit_within16": GEN2_COLOUR_NEAR_SHARE}


def check_gen2_alignment(mm_normal: np.ndarray, sakura_half: np.ndarray) -> dict:
    """MoonGen2Normal and Sakura's Gen2 normal are different sculpts, so their correlation is low; what must hold is that it peaks
    at zero offset: higher than the median over shifts of 4 to 16 texels (both directions) by GEN2_ALIGN_MARGIN."""
    def standard(img: np.ndarray) -> np.ndarray:
        img = img[..., :2].astype("f4")
        return (img - img.mean((0, 1))) / img.std((0, 1))

    a, b = standard(mm_normal), standard(sakura_half)
    zero = float((a * b).mean())  # mean of the red and green correlations
    shifted = [float((a * np.roll(b, (dy, dx), axis=(0, 1))).mean()) for dy in GEN2_ALIGN_SHIFTS for dx in GEN2_ALIGN_SHIFTS]
    median, best = float(np.median(shifted)), float(max(shifted))
    print(f"MoonGen2Normal vs Sakura's Gen2 normal at 1024 x 2048: red/green correlation {zero:.3f} at zero offset; shifts of 4 to 16 texels: median {median:.3f}, max {best:.3f}")
    if not zero >= GEN2_ALIGN_MIN or zero < median + GEN2_ALIGN_MARGIN:
        stop(f"Mother Moon's Gen2 normal does not line up with Sakura's: zero-offset correlation {zero:.3f}, shifted median {median:.3f} (want >= {GEN2_ALIGN_MIN} and >= median + {GEN2_ALIGN_MARGIN})")
    return {"test": "zero-offset peak: MoonGen2Normal vs Sakura Gen2 normal (mip 1), mean red/green correlation against shifts of 4 to 16 texels",
            "zero_offset": round(zero, 4), "shifted_median": round(median, 4), "shifted_max": round(best, 4), "shifts": len(shifted),
            "limit_min": GEN2_ALIGN_MIN, "limit_margin": GEN2_ALIGN_MARGIN}


def gen2_wet(plain_glowset: dict) -> dict:
    """Can Sakura's Gen2 wet material (`_1_a`) be carried like the Bibo+ one? It must have the shape of her `_1_bibo` material
    (same shader, keys and constants) and sample c0201b0001_sakura_{base,norm,mask}.tex."""
    bibo = parse_mtrl((SAKURA_MATERIALS / "mt_c0201b0001_1_bibo.mtrl").read_bytes())
    sakura = parse_mtrl(SAKURA_GEN2_WET.read_bytes())
    wanted = [f"chara/human/c0201/obj/body/b0001/texture/c0201b0001_sakura_{kind}.tex" for kind in ("base", "norm", "mask")]
    problems = []
    if sakura["shader"] != "skin.shpk" or sakura["keys"].get(SKIN_TYPE_KEY) != GLOW_TYPE_VALUE:
        problems.append("not the emissive-type skin.shpk")
    if sakura["keys"] != bibo["keys"] or set(sakura["consts"]) != set(bibo["consts"]) or EMISSIVE_ID not in sakura["consts"]:
        problems.append("its keys or constants differ from her _1_bibo material")
    if sakura["textures"] != wanted:
        problems.append(f"it samples {sakura['textures']}")
    if not set(plain_glowset["consts"]) <= set(sakura["consts"]):
        problems.append("it lacks constants of the plain Gen2 material")
    if problems:
        return {"carried": False, "reason": f"Sakura's {SAKURA_GEN2_WET.name} cannot be carried like the Bibo+ wet material: {'; '.join(problems)}."}
    return {"carried": True, "source": str(SAKURA_GEN2_WET),
            "evidence": "Same skin.shpk, shader keys and 12 constants as her mt_c0201b0001_1_bibo.mtrl; it samples c0201b0001_sakura_{base,norm,mask}.tex. The mod maps the colour and normal to its Gen2 set and the mask to the plain Gen2 body mask."}


# ---------------------------------------------------------------- Gen2 / vanilla: the build
def shaded_tall(xy: np.ndarray, width: int = 1024) -> Image.Image:
    """base.shaded() for a texture twice as tall as wide (same light)."""
    z = np.sqrt(np.maximum(1 - (xy**2).sum(-1), 0))
    light = np.array([-0.5, 0.5, 0.7], "f4")
    light /= np.linalg.norm(light)
    value = np.clip(xy[..., 0] * light[0] + xy[..., 1] * light[1] + z * light[2], 0, 1)
    return Image.fromarray((value * 255).astype("u1")).resize((width, 2 * width), Image.LANCZOS)


def write_gen2_record(record: dict) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "gen2.json").write_text(json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8")


def gen2_main() -> None:
    """Build the Gen2 set. Writes only gen2_*.tex, preview_gen2_*.png and gen2.json under builds/_mothermoon/ (and a scratch folder
    there that is removed again); the Bibo+ files are never touched."""
    with zipfile.ZipFile(PMP) as archive:
        mm_bibo = tex_bytes_to_rgba(archive.read("chara/moonbibo.tex"))
        mm_gen2 = tex_bytes_to_rgba(archive.read("chara/moongen2.tex"))
        mm_gen2_normal = tex_bytes_to_rgba(archive.read("chara/MoonGen2Normal.tex"))
        mm_gen2_glow = tex_bytes_to_rgba(archive.read("chara/mm4gen2glow.tex"))
        glowset = parse_mtrl(archive.read(GEN2_MATERIAL))
    for name, img, shape in (("moonbibo", mm_bibo, (2048, 2048, 4)), ("moongen2", mm_gen2, (2048, 1024, 4)), ("MoonGen2Normal", mm_gen2_normal, (2048, 1024, 4)), ("mm4gen2glow", mm_gen2_glow, (2048, 1024, 4))):
        assert img.shape == shape, (name, img.shape)
    print(f"mm4gen2glow vs MoonGen2Normal, red/green/blue max difference: {int(np.abs(mm_gen2_glow[..., :3].astype(int) - mm_gen2_normal[..., :3]).max())}")
    sakura_gen2 = tex_io.read_bgra(str(SAKURA_GEN2_NORMAL))
    sakura_bibo = tex_io.read_bgra(str(base.OUT / "sakura_body_normal.tex"))  # byte-identical to SAKURA_BIBO_NORMAL
    assert sakura_gen2.shape == (4096, 2048, 4) and sakura_bibo.shape == (4096, 4096, 4), (sakura_gen2.shape, sakura_bibo.shape)

    # 1. Measure the layout before anything is written: which half of the Bibo+ layout is the Gen2 layout?
    pairs = {"mother_moon_colour": layout_scores(mm_gen2, mm_bibo, 3), "sakura_normal": layout_scores(sakura_gen2, sakura_bibo, 2)}
    for pair, scores in pairs.items():
        print(f"Gen2 vs each half of the Bibo+ layout, {pair}: {scores}")
    chosen, why_not = pick_half(pairs)
    if chosen is None:
        write_gen2_record({"blocked": f"no half of the Bibo+ layout is the Gen2 layout: {why_not}", "scores": pairs})
        stop(f"no half of the Bibo+ layout is the Gen2 layout ({why_not}); only builds/_mothermoon/gen2.json was written")
    half, mirrored = chosen.split("_")[0], chosen.endswith("_mirrored")
    assert half == "right" and not mirrored, f"this build is written for the plain right half, the measurement says {chosen}"
    bibo_cols = slice(2048, 4096)
    raw, area = agreement_area(sakura_gen2, sakura_bibo[:, bibo_cols])
    shares = {"share": round(float(area.mean()), 4), "glove_box": box_share(area, (0.01, 0.24), (0.57, 0.99)), "shin_band": box_share(area, (0.6, 1.0), (0.0, 1.0))}
    print(f"agreement area: raw {raw.mean() * 100:.2f}% of texels, cleaned {shares['share'] * 100:.2f}%; glove box {shares['glove_box'] * 100:.1f}%, shin band {shares['shin_band'] * 100:.1f}%")

    # 2. Stop conditions (asserted before any output is written)
    layers = read_xcf(GEN2_XCF)
    check_gen2_layers(layers)
    OUT.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".tmp-", dir=OUT) as scratch_name:
        scratch = Path(scratch_name)
        muse = decode_bc(MUSE_GEN2_BASE, scratch)
        dionys = decode_bc(base.DIONYS_DIFFUSE, scratch)
        dionys_normal = decode_bc(base.DIONYS_NORMAL, scratch)
    assert dionys_normal.shape == (2048, 2048, 4), dionys_normal.shape
    assert muse.shape == (2048, 1024, 4) and dionys.shape == (2048, 2048, 4), (muse.shape, dionys.shape)
    reproduction = check_gen2_reproduction(layers, muse[..., :3], mm_gen2[..., :3])
    alignment = check_gen2_alignment(mm_gen2_normal, tex_io.read_mip(str(SAKURA_GEN2_NORMAL), 1))
    wet = gen2_wet(glowset)

    # 3. Bandage pieces of the Bibo+ build (right half), kept only where the layouts really agree (see carry_masks)
    islands = base.skin_islands()
    band_rgb, band_alpha = base.straight_colour("bandage colour", base.load_png(base.BANDAGE / "Bibo+_Base_color.png"))
    cream_rgb = band_rgb[:, 2048:]
    band_rgb = grey_bandage(band_rgb, band_alpha)
    png_alpha = band_alpha[:, 2048:]
    band_normal = base.load_png(base.BANDAGE / "Bibo+_Normal_DirectX.png")
    band_xy = base.to_xy(band_normal[..., 0], band_normal[..., 1], green_down=True) * (band_alpha * islands)[..., None]
    skin_weight, colour_area, bandage_area = carry_masks(area, raw, sakura_gen2, muse, dionys[:, 1024:], dionys_normal[:, 1024:])
    band_rgb, band_alpha, band_xy = band_rgb[:, bibo_cols], band_alpha[:, bibo_cols] * bandage_area, band_xy[:, bibo_cols] * bandage_area[..., None]
    carry = {"colour_share": round(float(colour_area.mean()), 4), "bandage_share": round(float(bandage_area.mean()), 4),
             "colour_glove_box": box_share(colour_area, (0.01, 0.24), (0.57, 0.99)), "bandage_glove_box": box_share(bandage_area, (0.01, 0.24), (0.57, 0.99))}
    print(f"carried: Dionys colour on {carry['colour_share'] * 100:.2f}% of texels, bandage pieces on {carry['bandage_share'] * 100:.2f}%; glove box {carry['colour_glove_box'] * 100:.1f}% / {carry['bandage_glove_box'] * 100:.1f}%")
    del islands, band_normal

    # Normals: Sakura's Gen2 red/green + the folds; blue = min(Sakura, Mother Moon); alpha = Mother Moon's Gen2 glow mask
    body = base.clip_unit(base.to_xy(sakura_gen2[..., 0], sakura_gen2[..., 1]))
    folds = base.reoriented(body, band_xy)
    red_green = base.from_xy(folds)
    sakura_blue = sakura_gen2[..., 2]
    blue = np.minimum(sakura_blue, double(mm_gen2_glow[..., 2]))
    glow = double(mm_gen2_glow[..., 3])
    cloth_blue = np.rint(blue.astype("f4") * (1 - band_alpha) + sakura_blue.astype("f4") * band_alpha).astype("u1")
    cloth_glow = np.rint(glow.astype("f4") * (1 - band_alpha)).astype("u1")
    sleeve = layers[2]["pixels"][..., 3]  # "Arms/legs dark"
    limb, cloth_limb = limb_glow(glow, sleeve, band_alpha)
    opaque = np.full(red_green.shape[:2], 255, "u1")
    outputs = {
        "norm_3d": np.dstack([red_green, blue, opaque]),
        "norm_3d_cloth": np.dstack([red_green, cloth_blue, opaque]),
        "norm_glow": np.dstack([red_green, blue, glow]),
        "norm_glow_cloth": np.dstack([red_green, cloth_blue, cloth_glow]),
        "norm_limbglow": np.dstack([red_green, blue, limb]),
        "norm_limbglow_cloth": np.dstack([red_green, cloth_blue, cloth_limb]),
    }

    # Colour: Dionys skin (right half, texel for texel) deep inside the colour area, fading in linear light into the Muse+ Gen2 skin
    # at its edge (no hard seam) and outside it, then the three Gen2 tattoo layers on top in linear light (bottom to top: Arms/legs
    # dark, Arms/Legs Light, Body Light)
    dionys_skin, muse_skin = double(dionys[:, 1024:]), double(muse)
    weight = skin_weight[..., None]
    blended = to_linear(dionys_skin[..., :3].astype("f4") / 255) * weight + to_linear(muse_skin[..., :3].astype("f4") / 255) * (1 - weight)
    skin_alpha = np.where(colour_area, dionys_skin[..., 3], muse_skin[..., 3])
    del dionys_skin, muse_skin, weight
    tattoo = [{"pixels": double(layer["pixels"])} for layer in layers[2::-1]]
    inked = composite_linear(to_srgb(blended), tattoo)
    outputs["diffuse"] = np.dstack([base.to_bytes(inked), skin_alpha])
    outputs["diffuse_cloth"] = np.dstack([base.to_bytes(base.over(inked, band_rgb, band_alpha)), skin_alpha])

    for name in GEN2_TEXTURE_NAMES + GEN2_LIMB_NAMES:
        tex_io.write_bgra(str(OUT / f"gen2_{name}.tex"), outputs[name])
        assert np.array_equal(tex_io.read_bgra(str(OUT / f"gen2_{name}.tex")), outputs[name]), name
    print("all gen2_*.tex files read back identical")

    update_limb_record(sleeve={"gen2": sleeve_record(sleeve, "Arms/legs dark")}, bandage=bandage_colours("gen2", cream_rgb, png_alpha, outputs["diffuse"], outputs["diffuse_cloth"]))
    free = band_alpha == 0
    print(f"outside the bandage, red/green identical to Sakura's Gen2 body: {np.array_equal(red_green[free], sakura_gen2[free][..., :2])}")
    print(f"glow under full cloth {int(cloth_glow[band_alpha == 1].max())} (want 0); glowing texels hidden by cloth {int(((glow > 0) & (band_alpha == 1)).sum())}")

    # Previews, twice as tall as wide
    for name, image in (("diffuse", Image.fromarray(outputs["diffuse"][..., :3]).resize((1024, 2048), Image.LANCZOS)),
                        ("diffuse_cloth", Image.fromarray(outputs["diffuse_cloth"][..., :3]).resize((1024, 2048), Image.LANCZOS)),
                        ("glow_mask", Image.fromarray(glow).resize((1024, 2048))), ("limbglow_mask", Image.fromarray(limb).resize((1024, 2048))), ("normal", shaded_tall(folds))):
        image.save(OUT / f"preview_gen2_{name}.png")

    write_gen2_record({
        "half": half, "mirrored": mirrored, "scores": pairs,
        "plain_half_holds": bool(raw.mean() >= 0.99),
        "agreement": {"recipe": "texels where Sakura's Gen2 body normal (gen2-7-2-leer-alpha-MID) and the right half of her Bibo+ body normal (bplus-7-2-doppel-alpha-MID-off) have identical red and green; "
                                f"agreeing areas too small to hold a depth-{SPECK_CORE_DEPTH} core are dropped as chance matches, disagreeing holes of up to {HOLE_MAX} texels are filled",
                      **shares, "raw_share": round(float(raw.mean()), 4),
                      "carry_recipe": f"flat normals (red/green within {FLAT_TOLERANCE} of 128) match whatever the layout, so they are not evidence on their own: on flat texels the "
                                      f"Dionys colour is carried only where the Muse+ Gen2 skin and the Dionys right half look alike (9-texel local mean difference <= {COLOUR_DIFFER_LIMIT}/255 "
                                      f"and no texel > {2 * COLOUR_DIFFER_LIMIT}/255) and the Dionys normal has no sculpted blob there (red/green > {DIONYS_RELIEF_LIMIT} from 128 after a depth-{RELIEF_OPENING} opening, grown {2 * RELIEF_MARGIN} texels: a Dionys-only island), kept {COLOUR_DIFFER_MARGIN} texels clear of a difference); bandage colour, folds and the cloth "
                                      f"glow cut-out are carried only within {BANDAGE_REACH} texels of real (non-flat) agreement patches of at least {BANDAGE_EVIDENCE_MIN} texels, then whatever that encloses or gaps up to {BANDAGE_CLOSE} texels wide (still inside the colour area); the Dionys skin fades into the Muse+ skin over "
                                      f"{SKIN_FEATHER} texels at the edge of its area",
                      **carry},
        "fallback": "Muse+ Gen2 skin colour (c0201b0001_base.tex, the skin the character wears today) with Mother Moon's Gen2 tattoo on top; normal red/green is Sakura's Gen2 body normal without bandage folds. Inside the agreement area it also fills the flat-normal texels where the Muse+ and Dionys art differ, so where the art measurably differs (toenails, genital and nipple art, bandage edges on the hands) the Muse+ skin stays; faint shading differences under 16/255 can remain at the edges of the left-strip islands.",
        "missing": "Outside the agreement area: the Dionys skin colour, the bandage colour and the bandage folds. That is the hand and finger islands, the foot island, the chest and nipple area and the Gen2-only islands in the left strip; there the Gen2 skin keeps the Muse+ colour and plain Sakura Gen2 body normal, with only the tattoo and glow. The bandage also stops at flat padding that is far from real agreement, so the hands get no bandage outlines.",
        "stop_checks": {"layers": [layer["name"] for layer in layers], "reproduction": reproduction, "alignment": alignment},
        "races": ["c0201"], "race_evidence": {},
        "wet": wet,
    })
    print(f"wet look carried for Gen2: {wet['carried']}; wrote gen2.json")


def main() -> None:
    with zipfile.ZipFile(PMP) as archive:
        shipped = tex_bytes_to_rgba(archive.read("chara/moonbibo.tex"))
        mm_glow = tex_bytes_to_rgba(archive.read("chara/mm4biboglow.tex"))
        mm_normal = tex_bytes_to_rgba(archive.read("chara/MoonBiboNormal.tex"))
        glowset = parse_mtrl(archive.read("chara/mt_c0201b0001_bibo_glowset.mtrl"))
    for name, img in (("moonbibo", shipped), ("mm4biboglow", mm_glow), ("MoonBiboNormal", mm_normal)):
        assert img.shape == (2048, 2048, 4), (name, img.shape)
    print(f"mm4biboglow vs MoonBiboNormal, red/green/blue max difference: {int(np.abs(mm_glow[..., :3].astype(int) - mm_normal[..., :3]).max())}")

    body = base.body_normal()  # reads builds/_unholy/sakura_body_normal.tex (written only if missing)
    sakura = tex_io.read_bgra(str(base.OUT / "sakura_body_normal.tex"))
    layers = read_xcf(XCF)
    check_layers(layers)
    mean, near = check_reproduction(layers, shipped[..., :3])
    corr = check_layout(mm_normal)

    # Every stop condition has passed: from here on, writes go only under builds/_mothermoon/ (temporary .dds files included)
    OUT.mkdir(parents=True, exist_ok=True)
    folder_ctx = tempfile.TemporaryDirectory(prefix=".tmp-", dir=OUT)
    scratch = Path(folder_ctx.name)

    colour = [round(float(v), 4) for v in glowset["consts"][EMISSIVE_ID]]
    dionys = decode_bc(base.DIONYS_DIFFUSE, scratch)
    assert dionys.shape == (2048, 2048, 4), dionys.shape

    (OUT / "glow.json").write_text(json.dumps({"g_EmissiveColor": colour}), encoding="utf-8")
    print(f"glow colour {colour} (Mother Moon's g_EmissiveColor)")

    islands = base.skin_islands()
    band_rgb, band_alpha = base.straight_colour("bandage colour", base.load_png(base.BANDAGE / "Bibo+_Base_color.png"))
    cream_rgb = band_rgb
    band_rgb = grey_bandage(band_rgb, band_alpha)
    band_normal = base.load_png(base.BANDAGE / "Bibo+_Normal_DirectX.png")
    band_xy = base.to_xy(band_normal[..., 0], band_normal[..., 1], green_down=True) * (band_alpha * islands)[..., None]
    height = base.load_png(base.BANDAGE / "Bibo+_Height.png")[..., 0].astype("f4") / 255
    folds = base.reoriented(body, band_xy)
    red_green = base.from_xy(folds)

    # Normals: Sakura red/green + folds; blue = min(Sakura, Mother Moon); alpha = Mother Moon's glow mask
    sakura_blue = sakura[..., 2]
    blue = np.minimum(sakura_blue, double(mm_glow[..., 2]))
    glow = double(mm_glow[..., 3])
    cloth_blue = np.rint(blue.astype("f4") * (1 - band_alpha) + sakura_blue.astype("f4") * band_alpha).astype("u1")
    cloth_glow = np.rint(glow.astype("f4") * (1 - band_alpha)).astype("u1")
    sleeve = layers[2]["pixels"][..., 3]  # "Arms/Legs Dark"
    limb, cloth_limb = limb_glow(glow, sleeve, band_alpha)
    opaque = np.full(red_green.shape[:2], 255, "u1")
    outputs = {
        "norm_3d": np.dstack([red_green, blue, opaque]),
        "norm_3d_cloth": np.dstack([red_green, cloth_blue, opaque]),
        "norm_glow": np.dstack([red_green, blue, glow]),
        "norm_glow_cloth": np.dstack([red_green, cloth_blue, cloth_glow]),
        "norm_limbglow": np.dstack([red_green, blue, limb]),
        "norm_limbglow_cloth": np.dstack([red_green, cloth_blue, cloth_limb]),
    }

    # Colour: Dionys skin + the four tattoo layers (bottom to top: sparklenails, Arms/Legs Dark, Arm/Leg Sparkles, Body Light)
    inked = double(composite_linear(dionys[..., :3].astype("f4") / 255, layers[3::-1]).astype("f4"))
    skin_alpha = double(dionys[..., 3])
    outputs["diffuse"] = np.dstack([base.to_bytes(inked), skin_alpha])
    outputs["diffuse_cloth"] = np.dstack([base.to_bytes(base.over(inked, band_rgb, band_alpha)), skin_alpha])

    for name, rgba in outputs.items():
        tex_io.write_bgra(str(OUT / f"{name}.tex"), rgba)
        assert np.array_equal(tex_io.read_bgra(str(OUT / f"{name}.tex")), rgba), name
    print("all .tex files read back identical")

    update_limb_record(
        formula="limb alpha = max(plain glow alpha, rint(LIMB_GLOW_LEVEL x the sleeve layer's alpha)), the layer ('Arms/Legs Dark' / 'Arms/legs dark') repeated 2 x 2 with no blur; red, green and blue are the plain twin's. "
                "Cloth twin = rint(limb alpha x (1 - bandage alpha)) (Gen2: bandage alpha already includes bandage_area), exactly like norm_glow_cloth.",
        sleeve={"bibo": sleeve_record(sleeve, "Arms/Legs Dark")},
        reference={"folder": str(ILLUSION), "recipe": f"chara/bibo_mid_norm.tex of each option, alpha only, at 2048 (the plain 4096 BC7 file averaged down 2 x 2; the +Hands file is already 2048); compared on the texels where +Hands is higher than the plain option by more than {ILLUSION_RISE} (the hand and finger islands)",
                   **reference_record(measure_illusion())},
        bandage={"recipe": f"luminance of the straight Sutured colour (Rec.709 weights) scaled so that fully covered cloth averages {BANDAGE_GREY}, written to R, G and B: neutral grey, fold shading kept at about 0.84x contrast; edges use the same straight colour; band_alpha untouched",
                 **bandage_colours("bibo", cream_rgb, band_alpha, outputs["diffuse"], outputs["diffuse_cloth"])})
    wet = investigate_wet(glowset, scratch)
    (OUT / "wet.json").write_text(json.dumps(wet, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"wet look carried: {wet['carried']}")

    # Checks printed for the report
    free = band_alpha == 0
    print(f"outside the bandage, red/green identical to Sakura's body: {np.array_equal(red_green[free], sakura[free][..., :2])}")
    marked = double(mm_glow[..., 2]) <= 16
    print(f"markings: {marked.mean() * 100:.1f}% of texels have Mother Moon blue <= 16; of those, output blue <= 40 in {(blue[marked] <= 40).mean() * 100:.2f}%")
    print(f"glow under full cloth {int(cloth_glow[band_alpha == 1].max())} (want 0); glowing texels hidden by cloth {int(((glow > 0) & (band_alpha == 1)).sum())}")
    inner = base.ndimage.binary_erosion(band_alpha > 0.9, iterations=4)
    base.slope_check("bandage bumps", folds, body, height, inner)
    print(f"XCF reproduction: mean {mean:.3f}/255, within 16/255 {near * 100:.2f}%; UV correlation red {corr[0]:.3f}, green {corr[1]:.3f}")

    # Previews and full-size inputs for tools/render_glow.py
    Image.fromarray(outputs["diffuse"][..., :3]).resize((1024, 1024), Image.LANCZOS).save(OUT / "preview_diffuse.png")
    Image.fromarray(outputs["diffuse_cloth"][..., :3]).resize((1024, 1024), Image.LANCZOS).save(OUT / "preview_diffuse_cloth.png")
    Image.fromarray(glow).resize((1024, 1024)).save(OUT / "preview_glow_mask.png")
    Image.fromarray(limb).resize((1024, 1024)).save(OUT / "preview_limbglow_mask.png")
    base.shaded(folds).save(OUT / "preview_normal.png")
    render = OUT / "render"
    render.mkdir(exist_ok=True)
    for name in ("diffuse", "diffuse_cloth", "norm_glow", "norm_glow_cloth"):
        Image.fromarray(outputs[name]).save(render / f"{name}.png", compress_level=1)
    folder_ctx.cleanup()


if __name__ == "__main__":
    gen2_main() if "--gen2" in sys.argv[1:] else main()
