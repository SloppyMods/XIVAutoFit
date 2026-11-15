#!/usr/bin/env python3
"""Build the Big Belt pads as two separate ring mods: elbows on one ring, knees on another.

Reuses the cutting code and part list in pads_to_ring.py (which builds a single combined mod). The same model file goes on
both fingers (_rir and _ril), so the two mods can be worn at once, one ring on each hand.

Usage: pads_to_two_rings.py [out dir] [elbow mm] [knee mm]      cut from the gear mods in the Penumbra library
       pads_to_two_rings.py <out dir> --from <unopened knee .pmp> [--fit <name in KNEE_FITS>]   open a v1.1 knee ring; no library needed
"""
import json, sys, zipfile
from pathlib import Path

from pads_to_ring import COLORSETS, MATERIAL_RACE, OUT, PARTS, UNOPENED_VERSION, check_only_positions_moved, cut, model_redirects, open_around_limb, parse, retarget_material

MODS = {
    'elbow': dict(ring=13, ring_name='Brilliant Egg Ring', name='[Cry] Big Belt Elbow Pads (Ring)', pmp='BigBelt_ElbowPads_Ring.pmp', gear='Gloves'),
    'knee': dict(ring=14, ring_name='Vibrant Egg Ring', name='[Cry] Big Belt Knee Pads (Ring)', pmp='BigBelt_KneePads_Ring.pmp', gear='Leggings'),
}
VERSION = '1.3.0'
# Knee rings made for one outfit's stockings. Its own name, so it installs beside the general ring instead of replacing it.
# bumps: see open_around_limb. These keep the front and outer side at the usual 4 mm and follow the raised back of the knee.
KNEE_FITS = {
    'e0584': dict(open_mm=4.0, bumps=((9.5, 175, 58, -25, 110), (6.0, 216, 60, 37, 80)), version='1.3.0-e0584',
                  name='[Cry] Big Belt Knee Pads (Ring) e0584', pmp='BigBelt_KneePads_Ring_e0584.pmp',
                  note=' Fitted to the e0584 Falconer stockings, which stand further out at the back of the knee. Use the plain ring with other outfits; it shares this ring, so enable only one.'),
}


def build(part, out_dir, open_mm):
    mod = MODS[part['key']]
    ring = f"a{mod['ring']:04d}"
    pmp = out_dir / mod['pmp']
    if pmp.exists(): sys.exit(f'{pmp} already exists; refusing to overwrite')
    material_name = f"mt_{MATERIAL_RACE}{ring}_rir_{part['letter']}.mtrl"
    model_data = open_around_limb((part['source'] / part['model']).read_bytes(), part['mesh'], part['submeshes'], part['axis_point'], part['axis_dir'], open_mm)
    source = (model_data, part['mesh'], part['submeshes'], '/' + material_name)
    mdl, verts, tris = cut([source])

    files = {'files/model/pads.mdl': mdl}
    default_files = model_redirects(ring)
    tex_prefix = f"chara/accessory/{ring}/texture/{MATERIAL_RACE}{ring}_rir_{part['tex_tail']}"
    for suffix, texture in part['textures'].items():
        arc = f'files/textures/{suffix}.tex'
        files[arc] = (part['source'] / texture).read_bytes()
        default_files[f'{tex_prefix}{suffix}.tex'] = arc.replace('/', '\\')

    options = []
    for name in COLORSETS:
        arc = f"files/colorsets/{name.replace(' ', '').lower()}/{material_name}"
        files[arc] = retarget_material((part['source'] / part['colorsets'].format(name)).read_bytes(), part['old_prefix'], tex_prefix)
        options.append({'Name': name, 'Description': '', 'Priority': 0, 'FileSwaps': {}, 'Manipulations': [],
                        'Files': {f'chara/accessory/{ring}/material/v0001/{material_name}': arc.replace('/', '\\')}})

    # Egg rings only have a male (c0101) model in the game. These entries (EQDP) tell it to load a female model for this ring.
    manips = [{'Type': 'Eqdp', 'Manipulation': {'Gender': 'Female', 'Race': 'Midlander', 'SetId': mod['ring'], 'Slot': slot, 'Entry': entry}}
              for slot, entry in (('RFinger', 192), ('LFinger', 768))]
    meta = {'FileVersion': 4, 'Name': mod['name'], 'Author': 'Yaelle Cry (ring cut: SloppyMods + Claude)', 'Version': VERSION, 'Website': 'https://ko-fi.com/yaellecry',
            'Description': f"Doll Body {part['key']} pads from the Big Belt set, on the {mod['ring_name']} (either finger). "
                           f"Hide the original pads with Toggles > No Armor Either in the Big Belt {mod['gear']} mod.", 'ModTags': [],
            'DefaultData': {'Files': default_files, 'FileSwaps': {}, 'Manipulations': manips},
            'Groups': [{'Type': 'Single', 'Name': 'Colorset', 'Description': '', 'Priority': 0, 'DefaultSettings': 0, 'Options': options}]}

    out_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(pmp, 'w', zipfile.ZIP_DEFLATED) as z:
        z.writestr('meta.json', json.dumps(meta, indent=2))
        for arc, blob in files.items(): z.writestr(arc, blob)
    print(f"built {pmp}: {verts} verts, {tris} tris, opened {open_mm} mm, ring {ring} ({mod['ring_name']}), .mdl {len(mdl)} bytes")


def reopen_knee_from_pmp(old_pmp, out_dir, fit_name=None):
    """Write a copy of an unopened knee .pmp with its pads opened. Every other file is copied as it is."""
    part = next(p for p in PARTS if p['key'] == 'knee')
    fit = KNEE_FITS[fit_name] if fit_name else dict(open_mm=part['open_mm'], bumps=(), version=VERSION, name=MODS['knee']['name'], pmp=MODS['knee']['pmp'], note='')
    pmp = out_dir / fit['pmp']
    if pmp.exists(): sys.exit(f'{pmp} already exists; refusing to overwrite')
    with zipfile.ZipFile(old_pmp) as z:
        files = {name: z.read(name) for name in z.namelist()}
    meta = json.loads(files['meta.json'])
    if meta['Version'] != UNOPENED_VERSION: sys.exit(f"{old_pmp} is version {meta['Version']}, not {UNOPENED_VERSION}; opening it again would push the pads out twice")
    old = files['files/model/pads.mdl']
    mesh = parse(old)['meshes'][0]
    new = open_around_limb(old, 0, range(mesh[3], mesh[3] + mesh[4]), part['axis_point'], part['axis_dir'], fit['open_mm'], fit['bumps'])
    check_only_positions_moved(old, new)
    files['files/model/pads.mdl'] = new
    files['meta.json'] = json.dumps(dict(meta, Name=fit['name'], Version=fit['version'], Description=meta['Description'] + fit['note']), indent=2).encode()
    out_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(pmp, 'w', zipfile.ZIP_DEFLATED) as z:
        for name, blob in files.items(): z.writestr(name, blob)
    print(f"built {pmp}: opened {fit['open_mm']} mm plus {len(fit['bumps'])} bumps from {old_pmp}, version {fit['version']}")


if __name__ == '__main__':
    if '--from' in sys.argv:
        args = sys.argv[1:]
        if len(args) == 3 and args[1] == '--from': reopen_knee_from_pmp(Path(args[2]), Path(args[0]))
        elif len(args) == 5 and args[1] == '--from' and args[3] == '--fit' and args[4] in KNEE_FITS: reopen_knee_from_pmp(Path(args[2]), Path(args[0]), args[4])
        else: sys.exit(__doc__)
        sys.exit()
    if len(sys.argv) not in (1, 2, 4): sys.exit(__doc__)
    out_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else OUT
    amounts = {'elbow': float(sys.argv[2]), 'knee': float(sys.argv[3])} if len(sys.argv) == 4 else {p['key']: p['open_mm'] for p in PARTS}
    for part in PARTS: build(part, out_dir, amounts[part['key']])
