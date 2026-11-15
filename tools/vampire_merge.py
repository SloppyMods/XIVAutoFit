"""Vampire Heartbeat (Tahoni, 2024) on the Dionys body with Sakura abs, Sutured bandage folds and a Dawntrail-native glow.

    python3 vampire_merge.py            (writes builds/_vampire/*.tex, render PNGs and glow.json; about a minute)

Same formula as glow_normal_merge.py (Unholy), whose helpers this imports unchanged. Differences:
  - The mod predates Dawntrail: its glow is a separate emissive texture for the Atramentum Luminis plugin. Dawntrail skin glows
    from the normal map's alpha instead, times one colour in the material. The emissive PNG is a single hue (red) times a
    brightness, so the brightness becomes the alpha (scaled so the brightest texel is 255, shared by both neck versions) and
    hue x peak becomes g_EmissiveColor, written to glow.json for vampire_package.py.
  - No 3D layer ships with it, so the normal's red/green are Sakura's body plus the bandage folds; blue is Sakura's own.
  - Two neck versions, each a matching (colour layer, emissive) pair, checked against the installed black-neck mod.

Outputs (builds/_vampire/):
  norm_3d.tex                         no glow: alpha 255
  norm_glow_<neck>.tex                glow mask in alpha
  norm_glow_cloth_<neck>.tex          bandage colour on: glow hidden under the cloth (red/green are the same as above)
  diffuse_<neck>.tex, diffuse_cloth_<neck>.tex   Dionys skin + Vampire tattoo layer (+ bandage colour)
"""
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
import glow_normal_merge as base  # noqa: E402
import tex_io  # noqa: E402

Image.MAX_IMAGE_PIXELS = None
OUT = base.HERE.parent / "builds" / "_vampire"
PNGS = Path("/home/you/Downloads/Telegram Desktop/Vampre Heartbeat [Bibo+] - Tahoni/Vampre Heartbeat [Bibo+]/PNGs")
NECKS = {  # neck -> (colour layer, emissive); pairs matched against the installed black-neck mod's textures
    "black_neck": ("transparent_black_neck.png", "with_black_neck.png"),
    "normal_neck": ("Bibo_Base_color.png", "Bibo_Emissive.png"),
}
HUE_SPREAD_LIMIT = 0.02  # the emissive must be one colour for a single g_EmissiveColor to reproduce it


def emissive_rgb(name: str) -> np.ndarray:
    return base.load_png(PNGS / name)[..., :3].astype("f4") / 255


def glow_colour(emissives: list[np.ndarray]) -> tuple[np.ndarray, float]:
    """The emissive's single hue (max channel 1) and the brightest texel's brightness, over every neck version."""
    hues, peak = [], 0.0
    for rgb in emissives:
        brightness = rgb.max(-1)
        lit = brightness > 8 / 255
        hues.append(rgb[lit] / brightness[lit, None])
        peak = max(peak, float(brightness.max()))
    hue = np.concatenate(hues)
    spread = hue.std(0).max()
    print(f"emissive hue {np.round(hue.mean(0), 3)}, spread {spread:.4f}, peak brightness {peak * 255:.0f}/255")
    assert spread < HUE_SPREAD_LIMIT, "emissive has several colours; one g_EmissiveColor cannot reproduce it"
    return hue.mean(0), peak


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    islands = base.skin_islands()
    body = base.body_normal()
    sakura = tex_io.read_bgra(str(base.OUT / "sakura_body_normal.tex"))  # cached by body_normal()
    band_rgb, band_alpha = base.straight_colour("bandage colour", base.load_png(base.BANDAGE / "Bibo+_Base_color.png"))
    band_normal = base.load_png(base.BANDAGE / "Bibo+_Normal_DirectX.png")
    band_xy = base.to_xy(band_normal[..., 0], band_normal[..., 1], green_down=True) * (band_alpha * islands)[..., None]
    height = base.load_png(base.BANDAGE / "Bibo+_Height.png")[..., 0].astype("f4") / 255
    folds = base.reoriented(body, band_xy)
    red_green = base.from_xy(folds)

    emissives = {neck: emissive_rgb(pair[1]) for neck, pair in NECKS.items()}
    hue, peak = glow_colour(list(emissives.values()))
    colour = hue * peak
    (OUT / "glow.json").write_text(json.dumps({"g_EmissiveColor": [round(float(c), 4) for c in colour]}))

    skin = np.asarray(Image.fromarray(base.decode_bc_tex(base.DIONYS_DIFFUSE)).resize((base.SIZE, base.SIZE), Image.BICUBIC))
    skin_rgb = skin[..., :3].astype("f4") / 255
    outputs = {"norm_3d": np.dstack([red_green, sakura[..., 2], np.full(red_green.shape[:2], 255, "u1")])}
    for neck, (layer_name, _) in NECKS.items():
        mask = np.clip(np.rint(emissives[neck].max(-1) / peak * 255), 0, 255).astype("u1")
        rebuilt = colour[None, None, :] * mask[..., None].astype("f4") / 255
        print(f"{neck}: colour x mask reproduces the emissive within {np.abs(rebuilt - emissives[neck]).max() * 255:.2f}/255")
        cloth_mask = np.rint(mask.astype("f4") * (1 - band_alpha)).astype("u1")
        outputs[f"norm_glow_{neck}"] = np.dstack([red_green, sakura[..., 2], mask])
        outputs[f"norm_glow_cloth_{neck}"] = np.dstack([red_green, sakura[..., 2], cloth_mask])
        ink_rgb, ink_alpha = base.straight_colour(f"tattoo {neck}", base.load_png(PNGS / layer_name))
        inked = base.over(skin_rgb, ink_rgb, ink_alpha)
        outputs[f"diffuse_{neck}"] = np.dstack([base.to_bytes(inked), skin[..., 3]])
        outputs[f"diffuse_cloth_{neck}"] = np.dstack([base.to_bytes(base.over(inked, band_rgb, band_alpha)), skin[..., 3]])
        bare = (ink_alpha == 0) & (band_alpha == 0)
        print(f"{neck}: colour identical to the Dionys skin where there is no tattoo or bandage: {np.array_equal(outputs[f'diffuse_cloth_{neck}'][bare], skin[bare])}")
        print(f"{neck}: glow under full cloth {int(cloth_mask[band_alpha > 0.99].max())} (want 0); glowing texels hidden by cloth {int(((mask > 0) & (band_alpha > 0.99)).sum())}")

    for name, rgba in outputs.items():
        tex_io.write_bgra(str(OUT / f"{name}.tex"), rgba)
        assert np.array_equal(tex_io.read_bgra(str(OUT / f"{name}.tex")), rgba), name
    print("all .tex files read back identical")
    free = band_alpha == 0
    print(f"outside the bandage, red/green identical to Sakura's body: {np.array_equal(red_green[free], sakura[free][..., :2])}; blue identical: {np.array_equal(outputs['norm_3d'][..., 2], sakura[..., 2])}")
    inner = base.ndimage.binary_erosion(band_alpha > 0.9, iterations=4)
    base.slope_check("bandage bumps", folds, body, height, inner)

    render = OUT / "render"
    render.mkdir(exist_ok=True)
    for name in ("diffuse_black_neck", "norm_glow_black_neck", "diffuse_cloth_black_neck", "norm_glow_cloth_black_neck"):
        Image.fromarray(outputs[name]).save(render / f"{name}.png", compress_level=1)


if __name__ == "__main__":
    main()
