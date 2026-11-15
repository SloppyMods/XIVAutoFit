#!/usr/bin/env python3
"""Cut armor pads out of two gear .mdl files and package them together as one ring mod (.pmp). No Blender, no Penumbra import.

The elbow and knee pads go in one model with two meshes, because each set has its own material. The same model file goes
on both fingers (_rir and _ril), so the ring shows both sets on either hand.
The vertices keep the bone weights the gear's author gave them, but each pad and its sleeve are pushed straight out from the
limb's center line by a fixed distance (open_mm), so they fit over stockings or tight sleeves. A fixed distance keeps the pad's
thickness and relief, which a scale would not.
Material and texture game paths are renamed to the ring's own folder, so the mod does not need or conflict with the
original gear mods. The renames keep every string the same length, so the .mtrl needs no other edits.

Usage: pads_to_ring.py [out dir]             cut from the gear mods in the Penumbra library
       pads_to_ring.py <out dir> --from <unopened .pmp>   open the pads of a v1.1 combined mod; no library needed
"""
import json, math, struct, sys, zipfile
from pathlib import Path

PENUMBRA = Path('/mnt/STORAGE/Penumbra')
OUT = Path(__file__).resolve().parent.parent / 'builds'
GLOVES = PENUMBRA / '[Cry] Big Belt Gloves [Gen3][Doll][AB][DT]'
LEGS = PENUMBRA / '[Cry] Big Belt Leggings [Gen3][Doll][AB][DT]'

RING, RING_NAME = 13, 'Brilliant Egg Ring'
NAME, PMP = '[Cry] Big Belt Pads (Ring)', 'BigBelt_Pads_Ring.pmp'
VERSION, UNOPENED_VERSION = '1.3.0', '1.1.0'
# axis_point and axis_dir: the limb's center line on the +x side (.mdl coordinates, Y-up), fitted to the Doll skin and joints
# around the pad. The -x side uses the mirror image, so both sides move the same.
PARTS = (
    dict(key='elbow', open_mm=1.5, axis_point=(0.311, 1.159, -0.03), axis_dir=(-0.691, 0.722, -0.009), source=GLOVES, model='Model/Doll Body - Arms In FIle/chara/equipment/e6116/model/c0201e6116_glv.mdl',
         mesh=1, submeshes=(3, 7, 8, 11),   # pads and straps, atr_gv_a (one arm) and atr_gv_b (other arm)
         old_prefix='chara/equipment/e6116/texture/c0201e6116_glv_', letter='a', tex_tail='',
         colorsets='Colorsets/{}/chara/equipment/e6116/material/v0001/mt_c0201e6116_glv_a.mtrl',
         textures={'n': 'Pattern/Leather Belt/chara/equipment/e6116/texture/c0201e6116_glv_n.tex',       # the user's current
                   'm': 'Pattern/Holo Belt/chara/equipment/e6116/texture/c0201e6116_glv_m.tex',           # Pattern setting
                   'n_id': 'Pattern/Ornate Belt/chara/equipment/e6116/texture/c0201e6116_glv_n_id.tex'}),
    dict(key='knee', open_mm=4.0, axis_point=(0.077, 0.52, 0.02), axis_dir=(0.048, -0.974, -0.22), source=LEGS, model='Model/Doll - Legs In File/chara/equipment/e9102/model/c0201e9102_sho.mdl',
         mesh=1, submeshes=(3, 6, 8, 11),   # pads and straps, atr_sv_a (one leg) and atr_sv_b (other leg)
         old_prefix='chara/equipment/e9102/texture/c0201e9102_sho_b_', letter='b', tex_tail='b_',
         colorsets='Colorsets/{}/chara/equipment/e9102/material/v0001/mt_c0201e9102_sho_b.mtrl',
         textures={'n': 'Patterns/Ornate Belt/chara/equipment/e9102/texture/c0201e9102_sho_b_n.tex',
                   'm': 'Patterns/Ornate Belt/chara/equipment/e9102/texture/c0201e9102_sho_b_m.tex',
                   'n_id': 'Patterns/Ornate Belt/chara/equipment/e9102/texture/c0201e9102_sho_b_n_id.tex'}),
)
COLORSETS = ('PBRCS - Gold', 'PBRCS - Silver', 'PBRCS - Black')
MATERIAL_RACE = 'c0101'   # every accessory model in the library names its materials c0101, whatever race the model file is for
MODEL_RACES = ('c0101', 'c0201')   # c0101 is the game's own model for this ring, so the pads load even if a race fallback misses c0201

HEADER_SIZE, DECL_SIZE, MODEL_HEADER_SIZE, LOD_SIZE, MESH_SIZE, SUBMESH_SIZE = 68, 136, 56, 60, 36, 16
MODEL_HEADER = '<fHHHHHHHHHBBHBBffHHBBBBHHH6x'
FIELDS = ('radius meshes attrs subs mats bones btables shapes shape_meshes shape_values lods flags1 elem_ids '
          'terrain_meshes flags2 clip shadow_clip culling terrain_subs flags3 bg_change bg_crest unk bone_total u8 u9').split()
LOD = '<HHffHHHHHHHHIIIIIIII'
MESH = '<HxxIHHHHI3I3BB'
SUBMESH = '<IIIHH'


def read_cstr(block, offset):
    return block[offset:block.index(b'\0', offset)].decode()


def parse(data):
    """Read the parts of a version 6 .mdl this tool needs. Stops with a clear error on any layout it does not handle."""
    version, _, _, mesh_count, _ = struct.unpack_from('<IIIHH', data, 0)
    if version != 0x1000006: sys.exit(f'unsupported .mdl version {version:#x}')
    vertex_start = struct.unpack_from('<I', data, 16)[0]
    index_start = struct.unpack_from('<I', data, 28)[0]
    pos = HEADER_SIZE
    decls = [data[pos + DECL_SIZE * i:pos + DECL_SIZE * (i + 1)] for i in range(mesh_count)]
    pos += DECL_SIZE * mesh_count
    _, string_size = struct.unpack_from('<HxxI', data, pos); pos += 8
    strings = data[pos:pos + string_size]; pos += string_size
    head = dict(zip(FIELDS, struct.unpack_from(MODEL_HEADER, data, pos))); pos += MODEL_HEADER_SIZE
    for field in ('shapes', 'elem_ids', 'terrain_meshes', 'terrain_subs'):
        if head[field]: sys.exit(f'model has {field}; this tool does not handle them')
    if head['flags2'] & 0x10: sys.exit('model has extra LODs; this tool does not handle them')
    lods = [struct.unpack_from(LOD, data, pos + LOD_SIZE * i) for i in range(3)]; pos += LOD_SIZE * 3
    meshes = [struct.unpack_from(MESH, data, pos + MESH_SIZE * i) for i in range(head['meshes'])]; pos += MESH_SIZE * head['meshes']
    pos += 4 * head['attrs']
    submeshes = [struct.unpack_from(SUBMESH, data, pos + SUBMESH_SIZE * i) for i in range(head['subs'])]; pos += SUBMESH_SIZE * head['subs']
    material_offsets = struct.unpack_from(f"<{head['mats']}I", data, pos); pos += 4 * head['mats']
    bone_offsets = struct.unpack_from(f"<{head['bones']}I", data, pos); pos += 4 * head['bones']
    tables = [struct.unpack_from('<HH', data, pos + 4 * i) for i in range(head['btables'])]
    tables_start = pos; pos += 4 * head['btables']
    table_data = {}
    for i, (offset, count) in enumerate(tables):      # offset counts 4-byte units from this table's own (offset, count) entry
        table_data[i] = struct.unpack_from(f'<{count}H', data, tables_start + 4 * i + 4 * offset)
    tail = data[vertex_start - 32 * (4 + head['bones']):vertex_start]   # 4 model bounding boxes, then one box per bone
    if struct.unpack_from('<f', tail, 12)[0] != 1.0: sys.exit('layout check failed: no bounding box where expected')
    return dict(decls=decls, strings=strings, head=head, lods=lods, meshes=meshes, submeshes=submeshes,
                materials=[read_cstr(strings, o) for o in material_offsets], bones=[read_cstr(strings, o) for o in bone_offsets],
                tables=table_data, tail=tail, vertex_start=vertex_start, index_start=index_start)


def raised_cosine(x, half):
    """1 at x = 0, fading smoothly to 0 at x = +-half."""
    return 0.5 * (1 + math.cos(math.pi * x / half)) if abs(x) < half else 0.0


def bump_mm(along, angle, bumps):
    """Extra push at this spot on the limb. Each bump is (peak mm, angle, half width, distance along the center line in mm, half width)."""
    return sum(peak * raised_cosine((angle - a + 180) % 360 - 180, a_half) * raised_cosine(along * 1000 - t, t_half) for peak, a, a_half, t, t_half in bumps)


def limb_angle(radial, direction, side):
    """Degrees around the limb for a vector straight out from the center line: 0 front (+z in .mdl coordinates), 90 outer side, 180 back."""
    def unit(v):
        length = math.sqrt(sum(a * a for a in v))
        return [a / length for a in v]
    def dot(a, b):
        return sum(x * y for x, y in zip(a, b))
    def without(v, along):   # v with its part along a unit vector removed
        amount = dot(v, along)
        return [a - amount * b for a, b in zip(v, along)]
    front = unit(without((0, 0, 1), direction))
    outer = unit(without(without((side, 0, 0), direction), front))
    return math.degrees(math.atan2(dot(radial, outer), dot(radial, front))) % 360


def open_around_limb(data, mesh, submeshes, axis_point, axis_dir, mm, bumps=()):
    """Return a copy of the .mdl with these submeshes' vertices moved mm straight out from the limb's center line.
    bumps add a smooth extra push at one spot on the limb, for cloth that stands further out there. Angles: 0 front, 90 outer side,
    180 back, 270 inner side, mirrored for the -x limb. Vertices at the same spot move the same, so a pad keeps its thickness and relief."""
    if not mm and not bumps: return data
    model = parse(data)
    mesh_info = model['meshes'][mesh]
    first_vertex, stride = model['vertex_start'] + mesh_info[7], mesh_info[10]   # position is the first 3 floats of stream 0
    used = set()
    for s in submeshes:
        index_offset, index_count = model['submeshes'][s][:2]
        used.update(struct.unpack_from(f'<{index_count}H', data, model['index_start'] + 2 * index_offset))
    length = math.sqrt(sum(a * a for a in axis_dir))
    out = bytearray(data)
    for v in used:
        at = first_vertex + stride * v
        pos = struct.unpack_from('<3f', data, at)
        side = 1 if pos[0] > 0 else -1
        point = (side * axis_point[0], axis_point[1], axis_point[2])
        direction = (side * axis_dir[0] / length, axis_dir[1] / length, axis_dir[2] / length)
        rel = [p - c for p, c in zip(pos, point)]
        along = sum(r * d for r, d in zip(rel, direction))
        radial = [r - along * d for r, d in zip(rel, direction)]
        distance = math.sqrt(sum(r * r for r in radial))
        push = mm
        if bumps: push = mm + bump_mm(along, limb_angle(radial, direction, side), bumps)
        struct.pack_into('<3f', out, at, *(p + push / 1000 * r / distance for p, r in zip(pos, radial)))
    return bytes(out)


def take_mesh(data, model, keep_mesh, keep_subs):
    """Copy the chosen submeshes of one mesh, keeping only the vertices they use."""
    mesh = model['meshes'][keep_mesh]
    first_sub, sub_count, table_index, vertex_offsets, strides, stream_count = mesh[3], mesh[4], mesh[5], mesh[7:10], mesh[10:13], mesh[13]
    if not all(first_sub <= s < first_sub + sub_count for s in keep_subs): sys.exit('submesh is not in the chosen mesh')
    remap, indices, subs = {}, [], []
    for s in keep_subs:
        index_offset, index_count = model['submeshes'][s][:2]
        subs.append((len(indices), index_count))
        for old in struct.unpack_from(f'<{index_count}H', data, model['index_start'] + 2 * index_offset):
            indices.append(remap.setdefault(old, len(remap)))
    if len(remap) > 0xFFFF: sys.exit('too many vertices for a 16-bit index')
    streams = []
    for i in range(stream_count):
        source = model['vertex_start'] + vertex_offsets[i]
        streams.append(b''.join(data[source + strides[i] * old:source + strides[i] * (old + 1)] for old in remap))
    return dict(remap=remap, indices=indices, subs=subs, streams=streams, strides=strides, stream_count=stream_count,
                table=model['tables'][table_index], bones=model['bones'], decl=model['decls'][keep_mesh])


def merge_boxes(tails):
    """Grow the first two model bounding boxes to cover every source model. Each box is min xyzw then max xyzw."""
    out = bytearray(tails[0][:32 * 4])
    for box in (0, 1):
        values = [struct.unpack_from('<8f', t, 32 * box) for t in tails]
        low = [min(v[i] for v in values) for i in range(3)]
        high = [max(v[i + 4] for v in values) for i in range(3)]
        struct.pack_into('<8f', out, 32 * box, *low, 1.0, *high, 1.0)
    return bytes(out)


def cut(sources):
    """Return a new .mdl with one mesh per source (data, mesh index, submeshes, material), with all attributes dropped."""
    models = [parse(s[0]) for s in sources]
    pieces = [take_mesh(s[0], m, s[1], s[2]) for s, m in zip(sources, models)]

    bone_names, bone_boxes = [], []
    for piece, model in zip(pieces, models):
        for b in piece['table']:
            name = model['bones'][b]
            if name not in bone_names:
                bone_names.append(name)
                bone_boxes.append(model['tail'][32 * (4 + b):32 * (5 + b)])
    if any(len(p['table']) > 64 for p in pieces): sys.exit('a bone table is over the 64 bone limit')
    tail = merge_boxes([m['tail'] for m in models]) + b''.join(bone_boxes)

    vertex_block, index_block, new_meshes, new_subs, new_map, tables = b'', b'', [], [], [], []
    for i, piece in enumerate(pieces):
        start_index = len(index_block) // 2
        stream_at = [0, 0, 0]
        for s, stream in enumerate(piece['streams']):
            stream_at[s] = len(vertex_block)
            vertex_block += stream
        first_sub = len(new_subs)
        for at, count in piece['subs']:
            new_subs.append((start_index + at, count, 0, len(new_map), len(piece['table'])))   # mask 0 = no attributes, always drawn
            new_map.extend(range(len(piece['table'])))                                          # each submesh may use the whole bone table
        new_meshes.append((len(piece['remap']), len(piece['indices']), i, first_sub, len(piece['subs']), i, start_index,
                           *stream_at, *piece['strides'], piece['stream_count']))
        index_block += struct.pack(f"<{len(piece['indices'])}H", *piece['indices'])
        index_block += b'\0' * (-len(index_block) % 16)   # the game expects 16-byte aligned index data
        tables.append([bone_names.index(piece['bones'][b]) for b in piece['table']])

    materials = [s[3] for s in sources]
    names = [b + '\0' for b in bone_names] + [m + '\0' for m in materials]
    string_block = ''.join(names).encode()
    string_block += b'\0' * (-len(string_block) % 4)
    offsets, at = [], 0
    for n in names: offsets.append(at); at += len(n.encode())
    bone_offsets, material_offsets = offsets[:len(bone_names)], offsets[len(bone_names):]

    # Table entries are (offset, count), the offset in 4-byte units from the entry itself. An odd-length table is padded
    # to a 4-byte boundary, and the header's bone total counts that padding (checked against the models in the library).
    bone_table, table_data = b'', b''
    for i, table in enumerate(tables):
        bone_table += struct.pack('<HH', len(tables) - i + len(table_data) // 4, len(table))
        table_data += struct.pack(f'<{len(table)}H', *table)
        table_data += b'\0' * (-len(table_data) % 4)
    bone_table += table_data
    bone_map_block = struct.pack(f'<I{len(new_map)}H', 2 * len(new_map), *new_map)

    mesh_count = len(pieces)
    head = dict(models[0]['head'], radius=max(m['head']['radius'] for m in models), meshes=mesh_count, attrs=0, subs=len(new_subs),
                mats=mesh_count, bones=len(bone_names), btables=mesh_count, bone_total=len(table_data) // 2, lods=1)

    def body(lod0):
        out = bytearray()
        out += struct.pack('<HxxI', len(names), len(string_block)) + string_block
        out += struct.pack(MODEL_HEADER, *(head[f] for f in FIELDS))
        out += lod0 + b'\0' * (LOD_SIZE * 2)
        for m in new_meshes: out += struct.pack(MESH, *m)
        for s in new_subs: out += struct.pack(SUBMESH, *s)
        out += struct.pack(f'<{mesh_count}I', *material_offsets)
        out += struct.pack(f'<{len(bone_offsets)}I', *bone_offsets)
        out += bone_table + bone_map_block
        pad = -(HEADER_SIZE + DECL_SIZE * mesh_count + len(out) + 1 + len(tail)) % 16
        out += bytes([pad]) + b'\0' * pad
        out += tail
        return bytes(out)

    vertex_block += b'\0' * (-len(vertex_block) % 16)
    triangles = len(new_subs) and sum(c for _, c in (s[:2] for s in new_subs)) // 3
    old_lod = models[0]['lods'][0]
    def make_lod(vertex_at, index_at):   # same field values the source models carry
        return struct.pack(LOD, 0, mesh_count, old_lod[2], old_lod[3], mesh_count, 0, mesh_count, 0, 0, 0, mesh_count, 0, 0, index_at, 0, 0,
                           len(vertex_block), len(index_block), vertex_at, index_at)

    runtime = len(body(make_lod(0, 0)))
    vertex_at = HEADER_SIZE + DECL_SIZE * mesh_count + runtime
    index_at = vertex_at + len(vertex_block)
    runtime_block = body(make_lod(vertex_at, index_at))
    header = struct.pack('<IIIHH3I3I3I3IBBBB', 0x1000006, DECL_SIZE * mesh_count, runtime, mesh_count, mesh_count, vertex_at, 0, 0, index_at, 0, 0,
                         len(vertex_block), 0, 0, len(index_block), 0, 0, 1, 1, 0, 0)
    mdl = header + b''.join(p['decl'] for p in pieces) + runtime_block + vertex_block + index_block
    check(mdl, sources, pieces, materials)
    return mdl, sum(len(p['remap']) for p in pieces), triangles


def check(mdl, sources, pieces, materials):
    """Read the new model back and compare it to the sources, so a bad layout stops here instead of crashing the game."""
    model = parse(mdl)
    if model['materials'] != materials: sys.exit('check failed: materials')
    for i, (source, piece) in enumerate(zip(sources, pieces)):
        mesh = model['meshes'][i]
        if mesh[2] != i or mesh[5] != i: sys.exit('check failed: mesh does not point at its own material and bone table')
        got = [model['bones'][b] for b in model['tables'][i]]
        if got != [piece['bones'][b] for b in piece['table']]: sys.exit(f'check failed: bone table {i} changed')
        at = model['vertex_start'] + mesh[7]
        if mdl[at:at + len(piece['streams'][0])] != piece['streams'][0]: sys.exit(f'check failed: vertices of mesh {i} changed')
        indices = []
        for s in range(mesh[3], mesh[3] + mesh[4]):
            offset, count = model['submeshes'][s][:2]
            indices += struct.unpack_from(f'<{count}H', mdl, model['index_start'] + 2 * offset)
        if indices != piece['indices'] or max(indices) >= mesh[0]: sys.exit(f'check failed: indices of mesh {i}')


def retarget_material(data, old_prefix, new_prefix):
    if len(old_prefix) != len(new_prefix): sys.exit('renames must keep string length')
    if old_prefix.encode() not in data: sys.exit(f'{old_prefix} is not in the material')
    return data.replace(old_prefix.encode(), new_prefix.encode())


def model_redirects(ring):
    return {f'chara/accessory/{ring}/model/{race}{ring}_{side}.mdl': 'files\\model\\pads.mdl' for race in MODEL_RACES for side in ('rir', 'ril')}


def build(out_dir):
    ring = f'a{RING:04d}'
    pmp = out_dir / PMP
    if pmp.exists(): sys.exit(f'{pmp} already exists; refusing to overwrite')
    sources = [(open_around_limb((p['source'] / p['model']).read_bytes(), p['mesh'], p['submeshes'], p['axis_point'], p['axis_dir'], p['open_mm']),
                p['mesh'], p['submeshes'], f"/mt_{MATERIAL_RACE}{ring}_rir_{p['letter']}.mtrl") for p in PARTS]
    mdl, verts, tris = cut(sources)

    files = {'files/model/pads.mdl': mdl}
    default_files = model_redirects(ring)
    options = {name: {} for name in COLORSETS}
    for p in PARTS:
        tex_prefix = f"chara/accessory/{ring}/texture/{MATERIAL_RACE}{ring}_rir_{p['tex_tail']}"
        for suffix, source in p['textures'].items():
            arc = f"files/textures/{p['key']}_{suffix}.tex"
            files[arc] = (p['source'] / source).read_bytes()
            default_files[f'{tex_prefix}{suffix}.tex'] = arc.replace('/', '\\')
        material_name = f"mt_{MATERIAL_RACE}{ring}_rir_{p['letter']}.mtrl"
        for name in COLORSETS:
            arc = f"files/colorsets/{name.replace(' ', '').lower()}/{material_name}"
            files[arc] = retarget_material((p['source'] / p['colorsets'].format(name)).read_bytes(), p['old_prefix'], tex_prefix)
            options[name][f'chara/accessory/{ring}/material/v0001/{material_name}'] = arc.replace('/', '\\')

    # Egg rings only have a male (c0101) model in the game. These entries (EQDP) tell it to load a female model for this ring.
    manips = [{'Type': 'Eqdp', 'Manipulation': {'Gender': 'Female', 'Race': 'Midlander', 'SetId': RING, 'Slot': slot, 'Entry': entry}}
              for slot, entry in (('RFinger', 192), ('LFinger', 768))]
    # Penumbra 1.7 reads the file list from meta.json (DefaultData, Groups) and ignores a default_mod.json.
    meta = {'FileVersion': 4, 'Name': NAME, 'Author': 'Yaelle Cry (ring cut: SloppyMods + Claude)', 'Version': VERSION, 'Website': 'https://ko-fi.com/yaellecry',
            'Description': f'Doll Body elbow and knee pads from the Big Belt set, together on the {RING_NAME} (either finger). '
                           'Hide the original pads with Toggles > No Armor Either in the Big Belt Gloves and Leggings mods.', 'ModTags': [],
            'DefaultData': {'Files': default_files, 'FileSwaps': {}, 'Manipulations': manips},
            'Groups': [{'Type': 'Single', 'Name': 'Colorset', 'Description': '', 'Priority': 0, 'DefaultSettings': 0,
                        'Options': [{'Name': name, 'Description': '', 'Priority': 0, 'Files': mapped, 'FileSwaps': {}, 'Manipulations': []}
                                    for name, mapped in options.items()]}]}

    out_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(pmp, 'w', zipfile.ZIP_DEFLATED) as z:
        z.writestr('meta.json', json.dumps(meta, indent=2))
        for arc, blob in files.items(): z.writestr(arc, blob)
    print(f'built {pmp}: {verts} verts, {tris} tris, ring {ring} ({RING_NAME}), .mdl {len(mdl)} bytes')


def check_only_positions_moved(old, new):
    """Read the opened model back: putting the old positions back must give the old file, byte for byte."""
    model = parse(new)
    restored = bytearray(new)
    for mesh in model['meshes']:
        first_vertex, stride = model['vertex_start'] + mesh[7], mesh[10]
        for v in range(mesh[0]):
            at = first_vertex + stride * v
            restored[at:at + 12] = old[at:at + 12]
    if bytes(restored) != old: sys.exit('check failed: something other than vertex positions changed')


def reopen_from_pmp(old_pmp, out_dir):
    """Write a copy of an unopened combined .pmp with its pads opened and its version bumped. Every other file is copied as it is."""
    pmp = out_dir / PMP
    if pmp.exists(): sys.exit(f'{pmp} already exists; refusing to overwrite')
    with zipfile.ZipFile(old_pmp) as z:
        files = {name: z.read(name) for name in z.namelist()}
    meta = json.loads(files['meta.json'])
    if meta['Version'] != UNOPENED_VERSION: sys.exit(f"{old_pmp} is version {meta['Version']}, not {UNOPENED_VERSION}; opening it again would push the pads out twice")
    old = files['files/model/pads.mdl']
    meshes = parse(old)['meshes']
    if len(meshes) != len(PARTS): sys.exit(f'expected {len(PARTS)} meshes, found {len(meshes)}')
    new = old
    for i, part in enumerate(PARTS):   # one mesh per part, in PARTS order; each mesh's submeshes hold that limb's pads and sleeves
        new = open_around_limb(new, i, range(meshes[i][3], meshes[i][3] + meshes[i][4]), part['axis_point'], part['axis_dir'], part['open_mm'])
    check_only_positions_moved(old, new)
    files['files/model/pads.mdl'] = new
    files['meta.json'] = json.dumps(dict(meta, Version=VERSION), indent=2).encode()
    out_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(pmp, 'w', zipfile.ZIP_DEFLATED) as z:
        for name, blob in files.items(): z.writestr(name, blob)
    print(f"built {pmp}: opened {[p['open_mm'] for p in PARTS]} mm from {old_pmp}")


if __name__ == '__main__':
    args = sys.argv[1:]
    if len(args) == 3 and args[1] == '--from': reopen_from_pmp(Path(args[2]), Path(args[0]))
    elif len(args) <= 1: build(Path(args[0]) if args else OUT)
    else: sys.exit(__doc__)
