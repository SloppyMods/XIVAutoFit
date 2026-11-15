#!/usr/bin/env python3
"""One mod for both Big Belt pad rings, with every size and side: elbows on the Brilliant Egg Ring (a0013), knees on the
Vibrant Egg Ring (a0014). No Blender, no library mods needed: it reads the saved ring builds.

Each ring gets one single-choice group that lists every size + side pair ("1.5 mm - Left" ...). Penumbra cannot combine a
separate Size group and Side group on the same model path (one group would simply win), so each pair is its own .mdl and each
option points the ring's four model paths (c0101/c0201, _rir/_ril) at exactly one of them. Works on either finger.

Sizes: elbow original (v1.1), 1.5 mm (v1.3, confirmed in game) and 3 mm (new, made from v1.1 with the same open_around_limb
that makes 1.5 mm); knee original (v1.1), 4 mm (v1.3, confirmed in game) and e0584 (Falconer stockings fit).
Sides: +x in the .mdl is the character's left (see pads_sides.py).

Usage: pads_all.py <out dir>      (run from tools/)
"""
import json, sys, zipfile
from pathlib import Path

from pads_sides import side_submeshes
from pads_to_ring import COLORSETS, PARTS, check_only_positions_moved, cut, open_around_limb, parse

BUILDS = Path(__file__).resolve().parent.parent / 'builds'
NAME, PMP, VERSION = '[Cry] Big Belt Pads (Rings) All', 'BigBelt_Pads_Rings_All.pmp', '1.5.0'
SIDES = (('Left', 1), ('Right', -1), ('Both', 0))
# per ring: (label, file stem, source .pmp, extra opening in mm on top of that source); the default is size index 1, side Both
RINGS = (
    dict(key='elbow', ring='a0013', group='Elbow pads (Brilliant Egg Ring)', sizes=(
        ('Original', 'orig', 'ring_v1.1/BigBelt_ElbowPads_Ring.pmp', 0.0),
        ('1.5 mm', 'open1p5', 'ring_v1.3/BigBelt_ElbowPads_Ring.pmp', 0.0),
        ('3 mm', 'open3', 'ring_v1.1/BigBelt_ElbowPads_Ring.pmp', 3.0))),
    dict(key='knee', ring='a0014', group='Knee pads (Vibrant Egg Ring)', sizes=(
        ('Original', 'orig', 'ring_v1.1/BigBelt_KneePads_Ring.pmp', 0.0),
        ('4 mm', 'open4', 'ring_v1.3/BigBelt_KneePads_Ring.pmp', 0.0),
        ('e0584 stockings', 'e0584', 'ring_e0584/BigBelt_KneePads_Ring_e0584.pmp', 0.0))),
)
DEFAULT_SIZE, DEFAULT_SIDE = 1, 2


def read_pmp(rel: str) -> dict[str, bytes]:
    with zipfile.ZipFile(BUILDS / rel) as z:
        return {name: z.read(name) for name in z.namelist()}


def size_model(ring: dict, rel: str, extra_mm: float) -> bytes:
    mdl = read_pmp(rel)['files/model/pads.mdl']
    if not extra_mm: return mdl
    part = next(p for p in PARTS if p['key'] == ring['key'])
    mesh = parse(mdl)['meshes'][0]
    opened = open_around_limb(mdl, 0, range(mesh[3], mesh[3] + mesh[4]), part['axis_point'], part['axis_dir'], extra_mm)
    check_only_positions_moved(mdl, opened)
    return opened


def ring_parts(ring: dict) -> tuple[dict[str, bytes], dict[str, str], list, dict, dict]:
    """Files, default files, EQDP entries, Side+Size group and colorset files for one ring."""
    first = read_pmp(ring['sizes'][0][2])
    meta = json.loads(first['meta.json'])
    for _, _, rel, _ in ring['sizes'][1:]:   # every size must share textures and colorsets, or one set would be wrong for it
        other = read_pmp(rel)
        if any(other[n] != first[n] for n in first if n.startswith(('files/textures/', 'files/colorsets/'))): sys.exit(f'{rel}: textures differ')
    files, defaults = {}, {}
    for path, arc in meta['DefaultData']['Files'].items():
        if path.endswith('.mdl'): continue
        new_arc = f"files/{ring['key']}/{arc.replace(chr(92), '/').removeprefix('files/')}"
        files[new_arc] = first[arc.replace('\\', '/')]
        defaults[path] = new_arc.replace('/', '\\')
    model_paths = [p for p in meta['DefaultData']['Files'] if p.endswith('.mdl')]
    if len(model_paths) != 4: sys.exit(f"{ring['key']}: expected 4 model paths")

    options = []
    for label, stem, rel, extra in ring['sizes']:
        both = size_model(ring, rel, extra)
        material = parse(both)['materials'][0]
        halves = side_submeshes(both)
        for side, sign in SIDES:
            arc = f"files/{ring['key']}/model/{stem}_{side.lower()}.mdl"
            files[arc] = both if not sign else cut([(both, 0, halves[sign], material)])[0]   # cut() reads its result back
            options.append({'Name': f'{label} - {side}', 'Description': '', 'Priority': 0, 'FileSwaps': {}, 'Manipulations': [],
                            'Files': {p: arc.replace('/', '\\') for p in model_paths}})
    group = {'Type': 'Single', 'Name': ring['group'], 'Description': 'Pad size, and which limb shows its pad and strap.', 'Priority': 0,
             'DefaultSettings': DEFAULT_SIZE * len(SIDES) + DEFAULT_SIDE, 'Options': options}

    colorsets = {}
    for option in meta['Groups'][0]['Options']:
        for path, arc in option['Files'].items():
            new_arc = f"files/{ring['key']}/{arc.replace(chr(92), '/').removeprefix('files/')}"
            files[new_arc] = first[arc.replace('\\', '/')]
            colorsets.setdefault(option['Name'], {})[path] = new_arc.replace('/', '\\')
    return files, defaults, meta['DefaultData']['Manipulations'], group, colorsets


def build(out_dir: Path) -> None:
    pmp = out_dir / PMP
    if pmp.exists(): sys.exit(f'{pmp} already exists; refusing to overwrite')
    files, defaults, manips, groups, colorsets = {}, {}, [], [], {name: {} for name in COLORSETS}
    for ring in RINGS:
        f, d, m, g, c = ring_parts(ring)
        files.update(f); defaults.update(d); manips += m; groups.append(g)
        for name in COLORSETS: colorsets[name].update(c[name])
    groups.append({'Type': 'Single', 'Name': 'Colorset', 'Description': 'Metal colour for both rings.', 'Priority': 0, 'DefaultSettings': 0,
                   'Options': [{'Name': name, 'Description': '', 'Priority': 0, 'Files': colorsets[name], 'FileSwaps': {}, 'Manipulations': []}
                               for name in COLORSETS]})
    meta = {'FileVersion': 4, 'Name': NAME, 'Author': 'Yaelle Cry (ring cut: SloppyMods + Claude)', 'Version': VERSION, 'Website': 'https://ko-fi.com/yaellecry',
            'Description': 'Doll Body elbow and knee pads from the Big Belt set: elbows on the Brilliant Egg Ring, knees on the Vibrant Egg Ring '
                           '(either finger each). Pick a size and side per ring. Replaces every earlier Big Belt pad ring mod; disable those. '
                           'Hide the original pads with Toggles > No Armor Either in the Big Belt Gloves and Leggings mods.', 'ModTags': [],
            'DefaultData': {'Files': defaults, 'FileSwaps': {}, 'Manipulations': manips}, 'Groups': groups}
    out_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(pmp, 'w', zipfile.ZIP_DEFLATED) as z:
        z.writestr('meta.json', json.dumps(meta, indent=2))
        for name, blob in files.items(): z.writestr(name, blob)
    print(f'built {pmp}: {sum(n.endswith(".mdl") for n in files)} models, version {VERSION}')


if __name__ == '__main__':
    if len(sys.argv) != 2: sys.exit(__doc__)
    build(Path(sys.argv[1]))
