"""Put Magical Sakura's muscled body normal and the Sutured bandages under the Unholy glow tattoo, keeping its 3D bumps and glow.

    python3 glow_normal_merge.py            (writes builds/_unholy/*.tex and previews; about a minute)

How Dawntrail skin glow works (checked on Unholy and Magical Sakura): the body normal map's red and green hold the surface
direction (muscles, tattoo bumps), its alpha holds the glow mask, and the material switches skin.shpk to its emissive skin type
(key 380CAED0 = 72E697CD) with a glow colour constant. So the glow survives as long as the alpha and the material stay.

Everything here uses the Bibo+ UV layout, so layers line up texel for texel. Layers, bottom to top, each added with
reoriented normal mapping (tilts the detail by the surface under it, so abs keep their shape under a tattoo line):
  1. body:    Magical Sakura's no-glow Bibo+ body normal (BODY_NORMAL, 4096, read from the .pmp; checked free of tattoo detail).
              The user chose it over Dionys normal_smooth+buff, which has almost no abs (DIONYS_NORMAL, still usable).
  2. tattoo:  Unholy loose "normal transparent_blue .png", weighted by its alpha (same direction convention as the game)
  3. bandage: Sutured "Bibo+_Normal_DirectX.png", green flipped (measured against its height map), weighted by the colour alpha
Blue is copied from Unholy's shipped normal, alpha is Unholy's glow mask byte for byte (255 for the no-glow 3D option).

Colour: Unholy's shipped colour textures carry Unholy's own base skin, painted for the Bibo+ chest, which looks wrong on the
flat Dionys chest and hides Dionys' painted muscle shading. So the colour is rebuilt like Magical Sakura does it: the Dionys skin
(DIONYS_DIFFUSE, the user's "Bubblegum & Freckles") with Unholy's loose transparent tattoo layer on top (straight alpha), and the
bandage colour (premultiplied in the file, un-premultiplied here) on top of that for the "cloth" versions.

Outputs (builds/_unholy/):
  norm_glow.tex         3D + glow, bandage bumps only (bandage colour off: tattoo stays visible and glows)
  norm_3d.tex           same, alpha 255, for the "3d effect" option without glow
  norm_glow_cloth.tex   bandage colour on: under the cloth the tattoo bumps and glow are hidden
  diffuse_dionys_black_neck.tex, diffuse_dionys_no_neck.tex               Dionys skin + Unholy tattoo
  diffuse_dionys_cloth_black_neck.tex, diffuse_dionys_cloth_no_neck.tex   the same with the bandage colour on top
"""
import sys
import zipfile
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage

sys.path.insert(0, str(Path(__file__).resolve().parent))
import tex_io  # noqa: E402

Image.MAX_IMAGE_PIXELS = None
SIZE = 4096
HERE = Path(__file__).resolve().parent
OUT = HERE.parent / "builds" / "_unholy"
UNHOLY_MOD = Path("/mnt/STORAGE/Penumbra/Unholy_dt_glow_3d_bibo/chara")
UNHOLY_LOOSE = Path("/home/you/Downloads/Telegram Desktop/Unholy - Tahoni/Unholy/Loose Files")
DIONYS_NORMAL = Path("/mnt/STORAGE/Penumbra/Dionys V1.4.0/Dionys/Textures/Skin/Normals/normal_smooth+buff.tex")
SAKURA_PMP = Path("/home/you/Downloads/Telegram Desktop/Skin Mods/Magical Sakura life-4K Glow.pmp")
SAKURA_BODY = "Sakura life/Update-7-2/chara/MID/Alphas/bplus-7-2-doppel-alpha-MID-off.tex"  # the "glow off" normal: body only
BODY_NORMAL = "sakura"  # "sakura" or "dionys"
DIONYS_DIFFUSE = Path("/mnt/STORAGE/Penumbra/Dionys V1.4.0/Dionys/Textures/Skin/Diffuse_freckles/Bubblegum/mid_smooth_freckles_bubblegum.tex")
TATTOO_LAYERS = {"black_neck": "transparent with neck.png", "no_neck": "transparent no neck.png"}  # matched against Unholy's shipped colours
BANDAGE = Path("/home/you/Downloads/Telegram Desktop/Skin Mods/Bandages [Bibo+] - Sutured/Bandage [Bibo+]/Overlays Both - Copy")
# Unholy's 3D layer also carries a broad, soft tilt as strong as the abs (measured), which drowned the body's muscles.
# Only the fine relief is kept: the layer minus its own blur (texels; features much wider than this count as broad).
TATTOO_DETAIL_SIGMA = 10.0
# Skin areas of the body's UV layout; outside them (the gaps between pieces) the layers carry stretched-stripe junk that
# would bleed into seams in the smaller mips. Every Dionys body part is rasterised so all its options are covered.
DIONYS_MODELS = Path("/mnt/STORAGE/Penumbra/Dionys V1.4.0/Dionys/Models")
ISLAND_GROW = 6  # texels of padding kept around each skin area


def body_normal() -> np.ndarray:
    """The base body normal as (h, w, 2) directions at SIZE."""
    if BODY_NORMAL == "dionys":
        dionys = decode_bc_tex(DIONYS_NORMAL)
        return upscale(to_xy(dionys[..., 0], dionys[..., 1]))
    copy = OUT / "sakura_body_normal.tex"
    if not copy.exists():
        with zipfile.ZipFile(SAKURA_PMP) as archive:
            copy.write_bytes(archive.read(SAKURA_BODY))
    sakura = tex_io.read_bgra(str(copy))
    assert sakura.shape[:2] == (SIZE, SIZE), sakura.shape
    return clip_unit(to_xy(sakura[..., 0], sakura[..., 1]))


def decode_bc_tex(path: Path) -> np.ndarray:
    """Top mip of a BC-compressed .tex as uint8 RGBA, through a temporary .dds that Pillow decodes."""
    dds = OUT / (path.stem + ".dds")
    tex_io.tex_to_dds(str(path), str(dds))
    with Image.open(dds) as image:
        rgba = np.asarray(image.convert("RGBA"))
    dds.unlink()
    return rgba


def to_xy(red: np.ndarray, green: np.ndarray, green_down: bool = False) -> np.ndarray:
    """8-bit red/green to a direction (x right, y up) in [-1, 1], the game's convention."""
    x = red.astype("f4") / 127.5 - 1
    y = green.astype("f4") / 127.5 - 1
    return np.stack([x, -y if green_down else y], -1)


def from_xy(xy: np.ndarray) -> np.ndarray:
    return np.clip(np.rint((xy + 1) * 127.5), 0, 255).astype("u1")


def clip_unit(xy: np.ndarray) -> np.ndarray:
    """Keep x,y inside the unit circle so z = sqrt(1 - x^2 - y^2) exists."""
    length = np.linalg.norm(xy, axis=-1, keepdims=True)
    return xy / np.maximum(length / 0.9999, 1)


def reoriented(base: np.ndarray, detail: np.ndarray) -> np.ndarray:
    """Reoriented normal mapping on (h, w, 2) direction arrays; returns the (h, w, 2) result."""
    base, detail = clip_unit(base), clip_unit(detail)
    bz = np.sqrt(np.maximum(1 - (base**2).sum(-1), 0))
    dz = np.sqrt(np.maximum(1 - (detail**2).sum(-1), 0))
    t = np.concatenate([base, (bz + 1)[..., None]], -1)
    u = np.concatenate([-detail, dz[..., None]], -1)
    n = t * ((t * u).sum(-1, keepdims=True) / t[..., 2:]) - u
    return n[..., :2] / np.maximum(np.linalg.norm(n, axis=-1, keepdims=True), 1e-9)


def upscale(xy: np.ndarray) -> np.ndarray:
    channels = [np.asarray(Image.fromarray(np.ascontiguousarray(xy[..., c]), "F").resize((SIZE, SIZE), Image.BICUBIC)) for c in range(2)]
    return clip_unit(np.stack(channels, -1))


def load_png(path: Path) -> np.ndarray:
    with Image.open(path) as image:
        return np.asarray(image.convert("RGBA"))


def straight_colour(name: str, colour: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """A transparent colour layer as straight (not premultiplied) RGB in [0, 1] plus alpha; detects which form the file uses
    by whether soft edges look like the solid colour before or after dividing by alpha."""
    rgb, alpha = colour[..., :3].astype("f4") / 255, colour[..., 3].astype("f4") / 255
    solid = rgb[alpha > 0.99].mean(0)
    edge = (alpha > 0.15) & (alpha < 0.5)
    unpremultiplied = (rgb[edge] / alpha[edge, None]).mean(0)
    premultiplied = bool(np.abs(unpremultiplied - solid).mean() < np.abs(rgb[edge].mean(0) - solid).mean())
    print(f"{name}: solid {np.round(solid * 255)}, edge as stored {np.round(rgb[edge].mean(0) * 255)}, edge / alpha {np.round(unpremultiplied * 255)} -> premultiplied: {premultiplied}")
    if premultiplied:
        rgb = np.where(alpha[..., None] > 0, np.clip(rgb / np.maximum(alpha[..., None], 1e-6), 0, 1), 0)
    return rgb, alpha


def over(base: np.ndarray, rgb: np.ndarray, alpha: np.ndarray) -> np.ndarray:
    """Straight-alpha 'over': the layer on top of base, both RGB in [0, 1]."""
    return base * (1 - alpha[..., None]) + rgb * alpha[..., None]


def to_bytes(rgb: np.ndarray) -> np.ndarray:
    return np.clip(np.rint(rgb * 255), 0, 255).astype("u1")


def slope_check(name: str, result_xy: np.ndarray, before_xy: np.ndarray, height: np.ndarray, area: np.ndarray) -> None:
    """Raised bandage detail must tilt away from the slope: x change against dH/dcol negative, y change against dH/drow positive."""
    grad_row, grad_col = np.gradient(ndimage.gaussian_filter(height, 1.5))
    change = result_xy - before_xy
    cx = np.corrcoef(change[..., 0][area], grad_col[area])[0, 1]
    cy = np.corrcoef(change[..., 1][area], grad_row[area])[0, 1]  # y is up and rows go down, so raised detail gives a positive value
    print(f"{name}: corr(x change, dH/dcol) {cx:+.3f} (want -), corr(y change as G, dH/drow) {cy:+.3f} (want +)")
    assert cx < 0 < cy, f"{name}: bandage bumps point the wrong way"


def shaded(xy: np.ndarray, size: int = 1024) -> Image.Image:
    """Grey preview lit from the upper left, so muscles, tattoo bumps and bandage folds are visible."""
    z = np.sqrt(np.maximum(1 - (xy**2).sum(-1), 0))
    light = np.array([-0.5, 0.5, 0.7], "f4")
    light /= np.linalg.norm(light)
    value = np.clip(xy[..., 0] * light[0] + xy[..., 1] * light[1] + z * light[2], 0, 1)
    return Image.fromarray((value * 255).astype("u1")).resize((size, size), Image.LANCZOS)


def skin_islands() -> np.ndarray:
    """Texels covered by the body's skin triangles in UV space (game v: 0 at the top row), grown by ISLAND_GROW."""
    import mdl_read  # local: only needed here
    from PIL import ImageDraw

    canvas = Image.new("L", (SIZE, SIZE), 0)
    draw = ImageDraw.Draw(canvas)
    models = sorted(DIONYS_MODELS.rglob("*.mdl"))
    for path in models:
        try:
            meshes = mdl_read.read_mdl(str(path)).meshes
        except ValueError as error:  # some accessory models use a layout mdl_read does not know; they hold no body skin
            print(f"skipped unreadable model {path.relative_to(DIONYS_MODELS)}: {error}")
            continue
        for mesh in meshes:
            if "b0001_bibo.mtrl" not in mesh.material:
                continue
            corners = mesh.uv[mesh.triangles] * SIZE  # (n, 3, 2)
            for triangle in corners:
                draw.polygon([tuple(p) for p in triangle], fill=255)
    islands = ndimage.binary_dilation(np.asarray(canvas) > 0, iterations=ISLAND_GROW)
    print(f"skin areas from {len(models)} Dionys models: {islands.mean():.3f} of the texture")
    return islands


def fine_relief(xy: np.ndarray, weight: np.ndarray) -> np.ndarray:
    """The layer's directions minus their own weighted blur, times the weight: small tattoo relief only, no broad tilt.
    The blur only averages texels inside the layer (normalised convolution), so its edges do not pick up the transparent area."""
    spread = ndimage.gaussian_filter(weight, TATTOO_DETAIL_SIGMA)
    broad = np.stack([ndimage.gaussian_filter(xy[..., c] * weight, TATTOO_DETAIL_SIGMA) for c in range(2)], -1) / np.maximum(spread, 1e-4)[..., None]
    return (xy - broad) * weight[..., None]


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    shipped = tex_io.read_bgra(str(UNHOLY_MOD / "viera_normals3.tex"))  # Unholy "3d and GLOW" normal for mid, high, viera
    shipped_3d = tex_io.read_bgra(str(UNHOLY_MOD / "viera_normals1.tex"))
    assert np.array_equal(shipped[..., :3], shipped_3d[..., :3]), "Unholy's 3D and 3D+glow normals should differ only in alpha"

    body = body_normal()

    tattoo = load_png(UNHOLY_LOOSE / "normal transparent_blue .png")
    islands = skin_islands()
    tattoo_weight = tattoo[..., 3].astype("f4") / 255 * islands
    tattoo_full = to_xy(tattoo[..., 0], tattoo[..., 1]) * tattoo_weight[..., None]  # as shipped, for the checks
    tattoo_xy = fine_relief(to_xy(tattoo[..., 0], tattoo[..., 1]), tattoo_weight)

    band_rgb, band_alpha = straight_colour("bandage colour", load_png(BANDAGE / "Bibo+_Base_color.png"))
    band_normal = load_png(BANDAGE / "Bibo+_Normal_DirectX.png")
    band_xy = to_xy(band_normal[..., 0], band_normal[..., 1], green_down=True) * (band_alpha * islands)[..., None]
    height = load_png(BANDAGE / "Bibo+_Height.png")[..., 0].astype("f4") / 255

    with_tattoo = reoriented(body, tattoo_xy)
    plain = reoriented(with_tattoo, band_xy)  # bandage bumps on top, tattoo still underneath
    covered = reoriented(body, tattoo_xy * (1 - band_alpha[..., None]))
    cloth = reoriented(covered, band_xy)  # cloth hides the tattoo bumps

    outputs = {}
    for name, xy, alpha in (
        ("norm_glow", plain, shipped[..., 3]),
        ("norm_3d", plain, np.full(shipped.shape[:2], 255, "u1")),
        ("norm_glow_cloth", cloth, np.rint(shipped[..., 3].astype("f4") * (1 - band_alpha)).astype("u1")),
    ):
        rgba = np.dstack([from_xy(xy), shipped[..., 2], alpha])
        tex_io.write_bgra(str(OUT / f"{name}.tex"), rgba)
        outputs[name] = rgba

    dionys_skin = decode_bc_tex(DIONYS_DIFFUSE)
    skin = np.asarray(Image.fromarray(dionys_skin).resize((SIZE, SIZE), Image.BICUBIC))
    skin_rgb = skin[..., :3].astype("f4") / 255
    for neck, layer_name in TATTOO_LAYERS.items():
        ink_rgb, ink_alpha = straight_colour(f"tattoo {neck}", load_png(UNHOLY_LOOSE / layer_name))
        inked = over(skin_rgb, ink_rgb, ink_alpha)
        for name, rgb in ((f"diffuse_dionys_{neck}", inked), (f"diffuse_dionys_cloth_{neck}", over(inked, band_rgb, band_alpha))):
            rgba = np.dstack([to_bytes(rgb), skin[..., 3]])
            tex_io.write_bgra(str(OUT / f"{name}.tex"), rgba)
            outputs[name] = rgba
        bare = (ink_alpha == 0) & (band_alpha == 0)
        print(f"diffuse {neck}: identical to the Dionys skin where there is no tattoo or bandage: {np.array_equal(outputs[f'diffuse_dionys_cloth_{neck}'][bare], skin[bare])}")

    # Checks
    glow = outputs["norm_glow"]
    print(f"glow alpha identical to Unholy: {np.array_equal(glow[..., 3], shipped[..., 3])}; blue identical: {np.array_equal(glow[..., 2], shipped[..., 2])}")
    body_bytes = from_xy(body)
    free = (tattoo[..., 3] == 0) & (band_alpha == 0)
    off = np.abs(glow[..., :2].astype(int) - body_bytes.astype(int))[free]
    print(f"outside tattoo and bandage, red/green vs the {BODY_NORMAL} body normal: max difference {off.max()}, mean {off.mean():.3f}")
    inner = ndimage.binary_erosion(band_alpha > 0.9, iterations=4)
    slope_check("bandage bumps", plain, with_tattoo, height, inner)
    ink = tattoo[..., 3] > 200
    change = to_xy(glow[..., 0], glow[..., 1]) - body
    print(f"tattoo bumps: corr(change, fine relief) x {np.corrcoef(change[..., 0][ink], tattoo_xy[..., 0][ink])[0, 1]:+.3f}, y {np.corrcoef(change[..., 1][ink], tattoo_xy[..., 1][ink])[0, 1]:+.3f} (want +)")
    # Fine relief kept: high-pass of the result vs high-pass of the shipped layer, inside the ink
    high = lambda a: a - ndimage.gaussian_filter(a, TATTOO_DETAIL_SIGMA)
    inner = ink & ndimage.binary_erosion(islands, iterations=20)
    out_xy = to_xy(glow[..., 0], glow[..., 1])
    for c, axis in ((0, "x"), (1, "y")):
        fine = np.corrcoef(high(out_xy[..., c])[inner], high(tattoo_full[..., c])[inner])[0, 1]
        broad = np.corrcoef(ndimage.gaussian_filter(out_xy[..., c], 12)[inner], ndimage.gaussian_filter(body[..., c], 12)[inner])[0, 1]
        print(f"under the ink, {axis}: fine relief vs Unholy's {fine:+.3f} (want high), broad shape vs body (abs) {broad:+.3f} (want high)")
    hidden = band_alpha > 0.99
    print(f"cloth version: glow under full cloth {int(outputs['norm_glow_cloth'][..., 3][hidden].max())} (want 0); glow texels removed: {int(((shipped[..., 3] > 0) & hidden).sum())}")
    for name, rgba in outputs.items():
        assert np.array_equal(tex_io.read_bgra(str(OUT / f"{name}.tex")), rgba), name
    print("all .tex files read back identical")

    # Previews: whole map, then the abs/tattoo area and a bandaged hand, before (Unholy as shipped) and after
    shaded(to_xy(shipped[..., 0], shipped[..., 1])).save(OUT / "preview_unholy_shipped.png")
    shaded(plain).save(OUT / "preview_new.png")
    shaded(cloth).save(OUT / "preview_new_cloth.png")
    Image.fromarray(shipped[..., 3]).resize((1024, 1024)).save(OUT / "preview_glow_mask.png")
    Image.fromarray(outputs["diffuse_dionys_cloth_black_neck"][..., :3]).resize((1024, 1024), Image.LANCZOS).save(OUT / "preview_diffuse_cloth.png")
    render = OUT / "render"  # full-size PNGs for render_glow.py
    render.mkdir(exist_ok=True)
    for name in ("diffuse_dionys_black_neck", "diffuse_dionys_cloth_black_neck", "norm_glow", "norm_glow_cloth"):
        Image.fromarray(outputs[name]).save(render / f"fix_{name}.png", compress_level=1)


if __name__ == "__main__":
    main()
