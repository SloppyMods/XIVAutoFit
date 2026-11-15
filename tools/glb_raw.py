"""Minimal raw .glb reader and writer that never goes through Blender.

The writer keeps every accessor of the shell file and appends new ones, and always records fresh min/max for the accessors
it adds, because Penumbra's glTF loader rejects a file whose stored min/max do not match its data.
"""
import copy
import json
import struct

import numpy as np

COMPONENT = {5120: "b", 5121: "B", 5122: "h", 5123: "H", 5125: "I", 5126: "f"}
COUNT = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}
DIVISOR = {5121: 255.0, 5123: 65535.0, 5120: 127.0, 5122: 32767.0}


def load(path: str) -> tuple[dict, bytes]:
    data = open(path, "rb").read()
    if data[:4] != b"glTF":
        raise ValueError(f"{path} is not a .glb")
    json_size = struct.unpack("<I", data[12:16])[0]
    doc = json.loads(data[20:20 + json_size])
    offset = 20 + json_size
    bin_size = struct.unpack("<I", data[offset:offset + 4])[0]
    return doc, data[offset + 8:offset + 8 + bin_size]


def _raw(doc: dict, blob: bytes, accessor: dict) -> np.ndarray:
    view = doc["bufferViews"][accessor["bufferView"]]
    kind = np.dtype("<" + COMPONENT[accessor["componentType"]])
    components = COUNT[accessor["type"]]
    start = view.get("byteOffset", 0) + accessor.get("byteOffset", 0)
    stride = view.get("byteStride") or kind.itemsize * components
    if stride == kind.itemsize * components:
        return np.frombuffer(blob, kind, accessor["count"] * components, start).reshape(accessor["count"], components)
    field = np.dtype({"names": ["v"], "formats": [(kind, (components,))], "offsets": [0], "itemsize": stride})
    return np.frombuffer(blob, field, accessor["count"], start)["v"]


def read_accessor(doc: dict, blob: bytes, index: int) -> np.ndarray:
    """Accessor data as stored, including sparse accessors. Integer attributes stay raw (not normalized)."""
    accessor = doc["accessors"][index]
    if "bufferView" in accessor and "sparse" not in accessor:
        return _raw(doc, blob, accessor)
    kind = np.dtype("<" + COMPONENT[accessor["componentType"]])
    components = COUNT[accessor["type"]]
    base = _raw(doc, blob, accessor).copy() if "bufferView" in accessor else np.zeros((accessor["count"], components), kind)
    sparse = accessor.get("sparse")
    if sparse:
        ind = sparse["indices"]
        view = doc["bufferViews"][ind["bufferView"]]
        where = np.frombuffer(blob, np.dtype("<" + COMPONENT[ind["componentType"]]), sparse["count"], view.get("byteOffset", 0) + ind.get("byteOffset", 0))
        val = sparse["values"]
        view = doc["bufferViews"][val["bufferView"]]
        data = np.frombuffer(blob, kind, sparse["count"] * components, view.get("byteOffset", 0) + val.get("byteOffset", 0))
        base[where.astype(int)] = data.reshape(sparse["count"], components)
    return base


def primitives(doc: dict) -> list[dict]:
    """One record per primitive: its node name, material, attribute accessor map and the node/mesh it lives in."""
    out = []
    for node_index, node in enumerate(doc["nodes"]):
        if "mesh" not in node:
            continue
        mesh = doc["meshes"][node["mesh"]]
        for prim_index, prim in enumerate(mesh["primitives"]):
            out.append(dict(name=node.get("name") or mesh.get("name"), node=node_index, mesh=node["mesh"], prim=prim_index,
                            material=doc["materials"][prim["material"]]["name"], attributes=prim["attributes"], indices=prim["indices"],
                            extras=node.get("extras") or mesh.get("extras"), skin=node.get("skin")))
    return out


def joint_matrices(doc: dict, blob: bytes, skin: int = 0) -> tuple[list[str], np.ndarray]:
    """Joint names and rest-pose world matrices (bone to model space) of a skin."""
    entry = doc["skins"][skin]
    names = [doc["nodes"][i].get("name") for i in entry["joints"]]
    inverse = read_accessor(doc, blob, entry["inverseBindMatrices"]).reshape(-1, 4, 4).transpose(0, 2, 1).astype("f8")
    return names, np.linalg.inv(inverse)


def joint_parents(doc: dict, skin: int = 0) -> list[int]:
    """For each joint, the index of its nearest joint ancestor, or -1."""
    parent_of = {child: i for i, node in enumerate(doc["nodes"]) for child in node.get("children", [])}
    joints = doc["skins"][skin]["joints"]
    node_to_joint = {node: i for i, node in enumerate(joints)}
    out = []
    for node in joints:
        current = node
        found = -1
        while current in parent_of:
            current = parent_of[current]
            if current in node_to_joint:
                found = node_to_joint[current]
                break
        out.append(found)
    return out


class GlbWriter:
    """Copies a shell .glb and adds accessors or swaps primitives. Call save() once."""

    def __init__(self, doc: dict, blob: bytes):
        self.doc = copy.deepcopy(doc)
        self.blob = bytearray(blob)

    def add_accessor(self, data: np.ndarray, component: int, kind: str, normalized: bool = False) -> int:
        array = np.asarray(data, np.dtype("<" + COMPONENT[component]))
        while len(self.blob) % 4:
            self.blob.append(0)
        start = len(self.blob)
        self.blob += array.tobytes()
        self.doc["bufferViews"].append({"buffer": 0, "byteOffset": start, "byteLength": array.nbytes})
        accessor = {"bufferView": len(self.doc["bufferViews"]) - 1, "componentType": component, "count": len(array), "type": kind}
        if normalized:
            accessor["normalized"] = True
        values = array.astype("f8").reshape(len(array), -1)
        accessor["min"] = [float(v) for v in values.min(0)]
        accessor["max"] = [float(v) for v in values.max(0)]
        if component == 5126:  # keep float bounds exact: the loader compares against the stored float32 values
            accessor["min"] = [float(np.float32(v)) for v in array.reshape(len(array), -1).min(0)]
            accessor["max"] = [float(np.float32(v)) for v in array.reshape(len(array), -1).max(0)]
        self.doc["accessors"].append(accessor)
        return len(self.doc["accessors"]) - 1

    def copy_accessor(self, source_doc: dict, source_blob: bytes, index: int) -> int:
        accessor = source_doc["accessors"][index]
        return self.add_accessor(read_accessor(source_doc, source_blob, index), accessor["componentType"], accessor["type"], accessor.get("normalized", False))

    def save(self, path: str) -> None:
        self.doc["buffers"][0]["byteLength"] = len(self.blob)
        text = json.dumps(self.doc, separators=(",", ":")).encode()
        text += b" " * (-len(text) % 4)
        blob = bytes(self.blob) + b"\0" * (-len(self.blob) % 4)
        total = 12 + 8 + len(text) + 8 + len(blob)
        with open(path, "xb") as handle:  # "x" refuses to overwrite an existing build
            handle.write(struct.pack("<4sII", b"glTF", 2, total))
            handle.write(struct.pack("<I4s", len(text), b"JSON") + text)
            handle.write(struct.pack("<I4s", len(blob), b"BIN\0") + blob)
