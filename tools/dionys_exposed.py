"""Score a Dionys build: fail it if a piercing is present, then measure how much skin shows through the cloth, by true area, in motion.

    python3 -I dionys_exposed.py <build.glb> [more]

This reuses the area scoring in `male_exposed.py`. What differs from that script: the skin is the build's own `b0001_bibo` mesh, the skeleton is
the build's own, the default poses cover both legs and arms, and the waist line is at a female body's height (XPWAIST, 1.03 m).
Poses are simulated bone turns, not game animation. A score cannot see a thin slit, so always look at a render as well.

Env: XPPOSES and XPSPACE, XPREACH, XPFRONT, XPREGIONS, XPEXTRA as in `male_exposed.py`.
XPDOLL=1 scores a Doll Body 2 build instead: the skin is `b0001_b.mtrl` and the Doll joints (material containing XPJOINTMAT, DOLL)
count as skin; Doll materials are then not refused. XPFULLBODY=<reference .glb> with XPEXTRA=1 also reports reference skin missing from the build.
"""
import os
import site
import sys
from pathlib import Path

sys.path.append(site.getusersitepackages())  # python -I leaves out the user site, which holds scipy
sys.path.insert(0, str(Path(__file__).resolve().parent))
import glb_raw  # noqa: E402
import male_exposed as mx  # noqa: E402

SKIN_SUFFIX = "b0001_bibo.mtrl"
FORBIDDEN = ("piercing", "unknown", "doll")  # no piercing, no untraced mesh, no leftover Doll joint or skin material
POSES = "stand,walk,run,bend,twist,arms_up,arms_forward,squat,lunge,sit"


def forbidden_materials(prims: list[dict]) -> list[tuple[str, str]]:
    """(mesh, material) of every primitive whose material must not appear in a Dionys build."""
    return [(p["name"], p["material"]) for p in prims if any(word in p["material"].lower() for word in FORBIDDEN)]


def score_file(path: str) -> bool:
    """Print the score for one build; False when a forbidden material stops it."""
    doc, blob = glb_raw.load(path)
    prims = glb_raw.primitives(doc)
    doll = bool(int(os.environ.get("XPDOLL", "0")))
    joint_token = os.environ.get("XPJOINTMAT", "DOLL")
    bad = [b for b in forbidden_materials(prims) if not (doll and "doll" in b[1].lower() and "piercing" not in b[1].lower())]
    if bad:
        print(f"{Path(path).name}: REFUSED, forbidden materials {bad}")
        return False
    is_skin = (lambda m: m.endswith("b0001_b.mtrl") or joint_token in m) if doll else (lambda m: m.endswith(SKIN_SUFFIX))
    skin = mx.merged_glb(doc, blob, [p for p in prims if is_skin(p["material"])])
    cloth = mx.merged_glb(doc, blob, [p for p in prims if "b0001" not in p["material"] and not (doll and joint_token in p["material"])])
    mx.score(Path(path).name, cloth, skin, mx.load_skeleton(path))
    if mx.xe.enabled() and os.environ.get("XPFULLBODY"):
        ref_doc, ref_blob = glb_raw.load(os.environ["XPFULLBODY"])
        ref = mx.merged_glb(ref_doc, ref_blob, [p for p in glb_raw.primitives(ref_doc) if is_skin(p["material"])])
        missing = mx.xe.missing_numbers(skin.positions, skin.triangles, ref.positions, ref.triangles, cloth.positions, cloth.triangles, 0.006, 0.2)
        print(f"{Path(path).name}: missing skin cm2 seen {missing['missing_seen']:.0f}, under cloth {missing['missing_under_cloth']:.0f}")
    return True


def main() -> None:
    os.environ.setdefault("XPPOSES", POSES)
    os.environ.setdefault("XPWAIST", "1.03")
    results = [score_file(path) for path in sys.argv[1:]]
    sys.exit(0 if all(results) else 1)


if __name__ == "__main__":
    main()
