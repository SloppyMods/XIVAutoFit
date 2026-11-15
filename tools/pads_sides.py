#!/usr/bin/env python3
"""Add a "Side: Left / Right / Both" option to a v1.3 Big Belt pad ring mod (elbow or knee). No Blender, no library mods needed.

Toggle method: one model per option. Each option points the ring's four model game paths (c0101/c0201, _rir/_ril) at its own .mdl,
so it works the same on either finger. "Both" is the v1.3 pads.mdl, byte for byte. "Left" and "Right" are cut from it with
pads_to_ring.cut, keeping their vertices (already opened in v1.3) unchanged.

Sides, checked from the bone weights: the +x half of the .mdl is weighted only to *_l bones (j_ude_b_l, j_asi_*_l), so +x is the
character's left. In both v1.3 models submeshes 0 and 1 (pad, strap) are the left limb and 2 and 3 the right.

Usage: pads_sides.py <out dir> <v1.3 elbow or knee .pmp, or a fit like the e0584 knee> [...]
"""
import json, struct, sys, zipfile
from pathlib import Path

from pads_to_ring import cut, parse

SOURCE_VERSION, VERSION = '1.3.0', '1.4.0'
SIDES = (('Left', 'files/model/pads_left.mdl', 1), ('Right', 'files/model/pads_right.mdl', -1), ('Both', 'files/model/pads.mdl', 0))
DEFAULT_SIDE = 2   # Both
NAME_SUFFIX = ' Sides'   # its own mod name, so it installs beside v1.3 instead of replacing it


def side_submeshes(mdl: bytes) -> dict[int, tuple[int, ...]]:
    """Group mesh 0's submeshes by limb (+1 left, -1 right) from the x sign of their vertices; stop if a submesh crosses x = 0."""
    model = parse(mdl)
    if len(model['meshes']) != 1: sys.exit('expected a one-mesh pad model')
    mesh = model['meshes'][0]
    first_vertex, stride = model['vertex_start'] + mesh[7], mesh[10]
    groups: dict[int, list[int]] = {1: [], -1: []}
    for s in range(mesh[3], mesh[3] + mesh[4]):
        index_offset, index_count = model['submeshes'][s][:2]
        used = set(struct.unpack_from(f'<{index_count}H', mdl, model['index_start'] + 2 * index_offset))
        signs = {1 if struct.unpack_from('<f', mdl, first_vertex + stride * v)[0] > 0 else -1 for v in used}
        if len(signs) != 1: sys.exit(f'submesh {s} has vertices on both sides')
        groups[signs.pop()].append(s)
    if not groups[1] or not groups[-1]: sys.exit('model does not have both a left and a right half')
    return {k: tuple(v) for k, v in groups.items()}


def build(source_pmp: Path, out_dir: Path) -> None:
    with zipfile.ZipFile(source_pmp) as z:
        files = {name: z.read(name) for name in z.namelist()}
    meta = json.loads(files['meta.json'])
    # 1.3.0 or a fitted variant of it such as 1.3.0-e0584; the fit label carries over to the new version
    base, dash, fit = meta['Version'].partition('-')
    if base != SOURCE_VERSION: sys.exit(f"{source_pmp} is version {meta['Version']}, not {SOURCE_VERSION} or a fit of it")
    version = VERSION + dash + fit
    pmp = out_dir / source_pmp.name.replace('.pmp', '_Sides.pmp')
    if pmp.exists(): sys.exit(f'{pmp} already exists; refusing to overwrite')

    both = files['files/model/pads.mdl']
    material = parse(both)['materials'][0]
    halves = side_submeshes(both)
    for _, arc, sign in SIDES:
        if sign: files[arc] = cut([(both, 0, halves[sign], material)])[0]   # cut() reads its result back and checks the vertices

    defaults = meta['DefaultData']['Files']
    model_paths = [path for path in defaults if path.endswith('.mdl')]
    if len(model_paths) != 4: sys.exit(f'expected 4 model paths, found {len(model_paths)}')
    for path in model_paths: del defaults[path]   # the Side option maps the models now
    options = [{'Name': name, 'Description': '', 'Priority': 0, 'FileSwaps': {}, 'Manipulations': [],
                'Files': {path: arc.replace('/', '\\') for path in model_paths}} for name, arc, _ in SIDES]
    side_group = {'Type': 'Single', 'Name': 'Side', 'Description': 'Which limb shows its pad and strap.', 'Priority': 0,
                  'DefaultSettings': DEFAULT_SIDE, 'Options': options}
    shares = 'the plain v1.3 mod' if not fit else f'the plain and {fit} v1.3 mods'
    meta.update(Name=meta['Name'] + NAME_SUFFIX, Version=version, Groups=[side_group] + meta['Groups'],
                Description=meta['Description'] + f' Side picks the left limb, the right limb or both. Shares its ring with {shares}; enable only one.')
    files['meta.json'] = json.dumps(meta, indent=2).encode()

    out_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(pmp, 'w', zipfile.ZIP_DEFLATED) as z:
        for name, blob in files.items(): z.writestr(name, blob)
    print(f'built {pmp}: left submeshes {halves[1]}, right {halves[-1]}, version {version}')


if __name__ == '__main__':
    if len(sys.argv) < 3: sys.exit(__doc__)
    for source in sys.argv[2:]: build(Path(source), Path(sys.argv[1]))
