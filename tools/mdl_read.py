"""Read-only parser for FFXIV version 6 .mdl files: positions, triangles, bones and weights of the first level of detail.

Used by the male-body fitting scripts to read reference bodies and gear straight from the Penumbra library, with no game
tools. It never writes anything. Unlike the cutter in pads_to_ring.py it accepts models with shape keys, skipping them.
"""
import struct
from dataclasses import dataclass

import numpy as np

HEADER_SIZE, DECL_SIZE, MODEL_HEADER_SIZE, LOD_SIZE, MESH_SIZE, SUBMESH_SIZE = 68, 136, 56, 60, 36, 16
MODEL_HEADER = "<fHHHHHHHHHBBHBBffHHBBBBHHH6x"
FIELDS = ("radius meshes attrs subs mats bones btables shapes shape_meshes shape_values lods flags1 elem_ids "
          "terrain_meshes flags2 clip shadow_clip culling terrain_subs flags3 bg_change bg_crest unk bone_total u8 u9").split()
LOD = "<HHffHHHHHHHHIIIIIIII"
MESH = "<HxxIHHHHI3I3BB"
SUBMESH = "<IIIHH"
USAGE_POSITION, USAGE_WEIGHTS, USAGE_INDICES, USAGE_NORMAL, USAGE_UV, USAGE_TANGENT, USAGE_COLOR = 0, 1, 2, 3, 4, 6, 7
# vertex element type -> (numpy format, component count, divide by)
TYPES = {1: ("<f4", 2, 1.0), 2: ("<f4", 3, 1.0), 3: ("<f4", 4, 1.0), 13: ("<f2", 2, 1.0), 5: ("u1", 4, 1.0), 8: ("u1", 4, 255.0), 14: ("<f2", 4, 1.0),
         16: ("u1", 8, 255.0), 17: ("u1", 8, 1.0)}


@dataclass(frozen=True)
class MdlMesh:
    material: str
    positions: np.ndarray  # (n, 3) float64, model space (Y up)
    triangles: np.ndarray  # (m, 3) int64
    joints: np.ndarray  # (n, k) int64, indices into MdlModel.bones
    weights: np.ndarray  # (n, k) float64, each row sums to 1 where the vertex is weighted
    uv: np.ndarray  # (n, 2) float64, first texture coordinate set
    normals: np.ndarray  # (n, 3)
    tangents: np.ndarray  # (n, 4) raw 0..1 as stored
    colors: np.ndarray  # (n, 4) raw 0..1
    uvs: tuple[np.ndarray, ...]  # every UV element as stored, in file order
    submeshes: tuple[tuple[int, int, tuple[str, ...]], ...]  # (first index, index count, attribute names), relative to this mesh


@dataclass(frozen=True)
class MdlModel:
    bones: tuple[str, ...]
    meshes: tuple[MdlMesh, ...]


def _cstr(block: bytes, offset: int) -> str:
    return block[offset:block.index(b"\0", offset)].decode()


def _elements(decl: bytes) -> list[tuple[int, int, int, int, int]]:
    """A declaration is a list of 8-byte (stream, offset, type, usage, usage index) entries ended by stream 255."""
    out = []
    for i in range(0, len(decl), 8):
        stream, offset, kind, usage, usage_index = struct.unpack_from("<BBBBB", decl, i)
        if stream == 255:
            break
        out.append((stream, offset, kind, usage, usage_index))
    return out


def _read(data: bytes, base: int, stride: int, count: int, offset: int, kind: int) -> np.ndarray:
    if kind not in TYPES:
        raise ValueError(f"unhandled vertex element type {kind}")
    fmt, components, divisor = TYPES[kind]
    field = np.dtype({"names": ["v"], "formats": [(fmt, (components,))], "offsets": [offset], "itemsize": stride})
    return np.frombuffer(data, field, count, base)["v"].astype("f8") / divisor


def read_mdl(path: str) -> MdlModel:
    data = open(path, "rb").read()
    version, _, _, _, mesh_count = struct.unpack_from("<IIIHH", data, 0)
    if version != 0x1000006:
        raise ValueError(f"{path}: unsupported .mdl version {version:#x}")
    pos = HEADER_SIZE
    decls = [_elements(data[pos + DECL_SIZE * i:pos + DECL_SIZE * (i + 1)]) for i in range(mesh_count)]
    pos += DECL_SIZE * mesh_count
    _, string_size = struct.unpack_from("<HxxI", data, pos)
    pos += 8
    strings = data[pos:pos + string_size]
    pos += string_size
    head = dict(zip(FIELDS, struct.unpack_from(MODEL_HEADER, data, pos)))
    pos += MODEL_HEADER_SIZE
    pos += head["elem_ids"] * 32
    lods = [struct.unpack_from(LOD, data, pos + LOD_SIZE * i) for i in range(3)]
    pos += LOD_SIZE * 3
    if head["flags2"] & 0x10:
        pos += LOD_SIZE * 3
    meshes = [struct.unpack_from(MESH, data, pos + MESH_SIZE * i) for i in range(head["meshes"])]
    pos += MESH_SIZE * head["meshes"]
    attribute_offsets = struct.unpack_from(f"<{head['attrs']}I", data, pos)
    pos += 4 * head["attrs"] + 16 * head["terrain_meshes"]
    raw_submeshes = [struct.unpack_from(SUBMESH, data, pos + SUBMESH_SIZE * i) for i in range(head["subs"])]
    pos += SUBMESH_SIZE * head["subs"] + 12 * head["terrain_subs"]
    material_offsets = struct.unpack_from(f"<{head['mats']}I", data, pos)
    pos += 4 * head["mats"]
    bone_offsets = struct.unpack_from(f"<{head['bones']}I", data, pos)
    pos += 4 * head["bones"]
    tables_start = pos
    tables = [struct.unpack_from("<HH", data, tables_start + 4 * i) for i in range(head["btables"])]
    table_data = [struct.unpack_from(f"<{count}H", data, tables_start + 4 * i + 4 * offset) for i, (offset, count) in enumerate(tables)]
    bones = tuple(_cstr(strings, o) for o in bone_offsets)
    attributes = [_cstr(strings, o) for o in attribute_offsets]
    materials = [_cstr(strings, o) for o in material_offsets]
    lod0 = lods[0]
    first, count_meshes = lod0[0], lod0[1]
    vertex_base, index_base = lod0[18], lod0[19]
    out = []
    for i in range(first, first + count_meshes):
        n, n_index, material, _, _, table, start, offsets_a, offsets_b, offsets_c, st_a, st_b, st_c, _ = meshes[i]
        offsets, strides = (offsets_a, offsets_b, offsets_c), (st_a, st_b, st_c)
        by_usage: dict[int, tuple[int, int, int]] = {}
        for stream, offset, kind, usage, _ in decls[i]:
            by_usage.setdefault(usage, (stream, offset, kind))  # first of each usage: UV set 0, blend set 0
        stream, offset, kind = by_usage[USAGE_POSITION]
        positions = _read(data, vertex_base + offsets[stream], strides[stream], n, offset, kind)[:, :3]
        triangles = np.frombuffer(data, "<u2", n_index, index_base + start * 2).astype("i8").reshape(-1, 3)
        stream, offset, kind = by_usage[USAGE_WEIGHTS]
        weights = _read(data, vertex_base + offsets[stream], strides[stream], n, offset, kind)
        stream, offset, kind = by_usage[USAGE_INDICES]
        local = _read(data, vertex_base + offsets[stream], strides[stream], n, offset, kind).astype("i8")
        lookup = np.array(table_data[table], "i8")
        stream, offset, kind = by_usage[USAGE_UV]
        uv = _read(data, vertex_base + offsets[stream], strides[stream], n, offset, kind)[:, :2]
        uvs = tuple(_read(data, vertex_base + offsets[stream_e], strides[stream_e], n, offset_e, kind_e)
                    for stream_e, offset_e, kind_e, usage, _ in decls[i] if usage == USAGE_UV)
        stream, offset, kind = by_usage[USAGE_NORMAL]
        normals = _read(data, vertex_base + offsets[stream], strides[stream], n, offset, kind)[:, :3]
        stream, offset, kind = by_usage[USAGE_TANGENT]
        tangents = _read(data, vertex_base + offsets[stream], strides[stream], n, offset, kind)
        stream, offset, kind = by_usage[USAGE_COLOR]
        colors = _read(data, vertex_base + offsets[stream], strides[stream], n, offset, kind)
        submesh_first, submesh_count = meshes[i][3], meshes[i][4]
        subs = tuple((raw[0] - start, raw[1], tuple(name for bit, name in enumerate(attributes) if raw[2] >> bit & 1))
                     for raw in raw_submeshes[submesh_first:submesh_first + submesh_count])
        out.append(MdlMesh(materials[material], positions, triangles, lookup[local], weights, uv, normals, tangents, colors, uvs, subs))
    return MdlModel(bones, tuple(out))
