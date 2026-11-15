"""Unit test for restore_attrs.py on tiny synthetic glb files.  python3 -m unittest tools/test_restore_attrs.py"""
import json
import os
import struct
import sys
import tempfile
import unittest

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import glb_raw  # noqa: E402
import restore_attrs  # noqa: E402


def write_glb(path, meshes, joint_names):
    """meshes: list of (name, material, extras, {attr: (array, componentType, type, normalized)}, indices)."""
    doc = {"asset": {"version": "2.0"}, "scene": 0, "scenes": [{"nodes": []}], "nodes": [], "meshes": [],
           "materials": [], "accessors": [], "bufferViews": [], "buffers": [{"byteLength": 0}], "skins": []}
    blob = bytearray()

    def acc(arr, comp, kind, norm=False):
        arr = np.asarray(arr, np.dtype("<" + glb_raw.COMPONENT[comp]))
        while len(blob) % 4:
            blob.append(0)
        doc["bufferViews"].append({"buffer": 0, "byteOffset": len(blob), "byteLength": arr.nbytes})
        blob.extend(arr.tobytes())
        a = {"bufferView": len(doc["bufferViews"]) - 1, "componentType": comp, "count": len(arr), "type": kind}
        if norm:
            a["normalized"] = True
        if comp == 5126:
            a["min"] = [float(v) for v in arr.reshape(len(arr), -1).min(0)]
            a["max"] = [float(v) for v in arr.reshape(len(arr), -1).max(0)]
        doc["accessors"].append(a)
        return len(doc["accessors"]) - 1

    joints = []
    for nm in joint_names:
        doc["nodes"].append({"name": nm})
        joints.append(len(doc["nodes"]) - 1)
    doc["scenes"][0]["nodes"] += joints
    ibm = acc(np.tile(np.eye(4, dtype="f4").ravel(), (len(joints), 1)), 5126, "MAT4")
    doc["skins"].append({"joints": joints, "inverseBindMatrices": ibm})
    for name, material, extras, attrs, indices in meshes:
        doc["materials"].append({"name": material})
        prim = {"attributes": {k: acc(*v) for k, v in attrs.items()}, "indices": acc(indices, 5123, "SCALAR"),
                "material": len(doc["materials"]) - 1}
        doc["meshes"].append({"name": name, "primitives": [prim]})
        node = {"name": name, "mesh": len(doc["meshes"]) - 1, "skin": 0}
        if extras is not None:
            node["extras"] = extras
        doc["nodes"].append(node)
        doc["scenes"][0]["nodes"].append(len(doc["nodes"]) - 1)
    doc["buffers"][0]["byteLength"] = len(blob)
    text = json.dumps(doc).encode()
    text += b" " * (-len(text) % 4)
    blob += b"\0" * (-len(blob) % 4)
    with open(path, "wb") as f:
        f.write(struct.pack("<4sII", b"glTF", 2, 12 + 8 + len(text) + 8 + len(blob)))
        f.write(struct.pack("<I4s", len(text), b"JSON") + text)
        f.write(struct.pack("<I4s", len(blob), b"BIN\0") + bytes(blob))


def read(path):
    doc, blob = glb_raw.load(path)
    out = {}
    for r in glb_raw.primitives(doc):
        out[r["name"]] = ({k: glb_raw.read_accessor(doc, blob, v) for k, v in r["attributes"].items()},
                          doc["nodes"][r["node"]].get("extras"), [doc["nodes"][j]["name"] for j in doc["skins"][r["skin"]]["joints"]])
    return out


class RestoreAttrsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        d = self.tmp.name
        rng = np.random.default_rng(1)
        n = 6
        pos = rng.random((n, 3)).astype("f4")
        nrm = np.tile([0, 0, 1], (n, 1)).astype("f4")
        uv = rng.random((n, 2)).astype("f4")
        tan = np.tile([0, 1, 0, -1], (n, 1)).astype("f4")
        j0 = np.tile([0, 1, 2, 3], (n, 1))
        j1 = np.tile([4, 0, 0, 0], (n, 1))
        w0 = np.tile([0.4, 0.3, 0.15, 0.1], (n, 1)).astype("f4")
        w1 = np.tile([0.05, 0, 0, 0], (n, 1)).astype("f4")
        col0 = np.tile([65535, 0, 0, 65535], (n, 1))
        col1 = np.tile([0, 65535, 0, 65535], (n, 1))
        idx = np.arange(n)
        src_names = ["j_a", "j_b", "j_c", "j_d", "j_e"]
        self.src = os.path.join(d, "src.glb")
        write_glb(self.src, [("mesh 0.0", "/mt_a.mtrl", {"atr_tv_a": True}, {
            "POSITION": (pos, 5126, "VEC3"), "NORMAL": (nrm, 5126, "VEC3"), "TANGENT": (tan, 5126, "VEC4"),
            "TEXCOORD_0": (uv, 5126, "VEC2"), "TEXCOORD_1": (uv * 0.5, 5126, "VEC2"),
            "_FFXIV_COLOR_0": (col0, 5123, "VEC4", True), "_FFXIV_COLOR_1": (col1, 5123, "VEC4", True),
            "JOINTS_0": (j0, 5123, "VEC4"), "JOINTS_1": (j1, 5123, "VEC4"),
            "WEIGHTS_0": (w0, 5126, "VEC4"), "WEIGHTS_1": (w1, 5126, "VEC4")}, idx)], src_names)
        # built: vertices reordered, joint order differs, weights = renormalised top 4 except vertex 0 (changed)
        order = np.array([3, 1, 4, 0, 5, 2])
        built_names = ["j_e", "j_d", "j_c", "j_b", "j_a"]
        remap = {i: built_names.index(nm) for i, nm in enumerate(src_names)}
        bj = np.vectorize(remap.get)(j0[order])
        bw = (w0[order] / w0[order].sum(1, keepdims=True)).astype("f4")
        bw[0] = [0.7, 0.3, 0, 0]
        self.order = order
        self.built = os.path.join(d, "built.glb")
        write_glb(self.built, [("mesh 0.0", "/mt_a.mtrl.001", None, {
            "POSITION": (pos[order] + [0.002, 0, 0], 5126, "VEC3"), "NORMAL": (nrm[order], 5126, "VEC3"),
            "TEXCOORD_0": (uv[order], 5126, "VEC2"), "COLOR_0": (col0[order], 5123, "VEC4", True),
            "JOINTS_0": (bj, 5123, "VEC4"), "WEIGHTS_0": (bw, 5126, "VEC4")}, idx)], built_names)
        self.src_tan = tan

    def tearDown(self):
        self.tmp.cleanup()

    def test_restore(self):
        out = os.path.join(self.tmp.name, "out.glb")
        self.assertEqual(restore_attrs.main([self.built, self.src, out]), 0)
        attrs, extras, joint_names = read(out)["mesh 0.0"]
        # no TANGENT although the source has one: Penumbra must compute its own (export tangent is 90 deg off)
        self.assertNotIn("TANGENT", attrs)
        # colours under source names
        np.testing.assert_array_equal(attrs["_FFXIV_COLOR_1"][:, 1], 65535)
        self.assertIn("COLOR_0", attrs)
        # TEXCOORD_1 copied in built order
        self.assertIn("TEXCOORD_1", attrs)
        # 8 influences restored for vertices 1..5, kept for vertex 0
        w = np.concatenate([attrs["WEIGHTS_0"], attrs["WEIGHTS_1"]], 1)
        j = np.concatenate([attrs["JOINTS_0"], attrs["JOINTS_1"]], 1)
        self.assertEqual(int((w[1:] > 0).sum(1).min()), 5)
        self.assertEqual(int((w[0] > 0).sum()), 2)
        names = {joint_names[j[1, i]]: w[1, i] for i in range(8) if w[1, i] > 0}
        self.assertAlmostEqual(names["j_e"], 0.05, places=5)
        self.assertAlmostEqual(names["j_a"], 0.4, places=5)
        # atr restored
        self.assertEqual(extras, {"atr_tv_a": True})
        # POSITION untouched
        np.testing.assert_allclose(attrs["POSITION"][:, 0], read(self.built)["mesh 0.0"][0]["POSITION"][:, 0])

    def test_built_tangent_is_dropped(self):
        with_tan = os.path.join(self.tmp.name, "built_tan.glb")
        d, b = glb_raw.load(self.built)
        w = glb_raw.GlbWriter(d, b)
        w.doc["meshes"][0]["primitives"][0]["attributes"]["TANGENT"] = w.add_accessor(self.src_tan, 5126, "VEC4")
        w.save(with_tan)
        self.assertIn("TANGENT", read(with_tan)["mesh 0.0"][0])
        out = os.path.join(self.tmp.name, "out_tan.glb")
        self.assertEqual(restore_attrs.main([with_tan, self.src, out]), 0)
        doc, _ = glb_raw.load(out)
        self.assertFalse(any("TANGENT" in p["attributes"] for p in glb_raw.primitives(doc)))

    def test_refuse_bad_match_and_overwrite(self):
        far = os.path.join(self.tmp.name, "far.glb")
        d, b = glb_raw.load(self.built)
        w = glb_raw.GlbWriter(d, b)
        prim = w.doc["meshes"][0]["primitives"][0]
        uv = glb_raw.read_accessor(d, b, prim["attributes"]["TEXCOORD_0"]) + 0.37  # no equal UV, positions 2 mm off
        prim["attributes"]["TEXCOORD_0"] = w.add_accessor(uv, 5126, "VEC2")
        w.save(far)
        out = os.path.join(self.tmp.name, "out2.glb")
        self.assertEqual(restore_attrs.main([far, self.src, out]), 1)
        self.assertFalse(os.path.exists(out))
        self.assertEqual(restore_attrs.main(["--force", far, self.src, out]), 0)
        self.assertEqual(restore_attrs.main([self.built, self.src, out]), 2)  # exists: never overwrite


if __name__ == "__main__":
    unittest.main()
