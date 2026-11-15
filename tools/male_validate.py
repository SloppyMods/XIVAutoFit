"""Strict checks on a .glb before handing it to Penumbra: accessor bounds, finite values, sane normals, primitive and vertex counts.

    python3 male_validate.py <file.glb> [more ...]
"""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import glb_raw  # noqa: E402

VERTEX_LIMIT = 38000


def main() -> int:
    worst = 0
    for path in sys.argv[1:]:
        doc, blob = glb_raw.load(path)
        failures = 0
        for i, accessor in enumerate(doc["accessors"]):
            data = glb_raw.read_accessor(doc, blob, i).astype("f8").reshape(accessor["count"], -1)
            if not np.isfinite(data).all():
                print(f"  FAIL accessor {i}: non-finite values")
                failures += 1
            if "min" in accessor:
                low, high = np.array(accessor["min"]), np.array(accessor["max"])
                if (data.min(0) < low - 1e-9).any() or (data.max(0) > high + 1e-9).any():
                    print(f"  FAIL accessor {i}: stored min/max do not contain the data")
                    failures += 1
        prims = glb_raw.primitives(doc)
        total = 0
        for prim in prims:
            attributes = prim["attributes"]
            count = doc["accessors"][attributes["POSITION"]]["count"]
            total += count
            indices = glb_raw.read_accessor(doc, blob, prim["indices"]).astype("i8")
            if indices.min() < 0 or indices.max() >= count:
                print(f"  FAIL {prim['name']}: index out of range")
                failures += 1
            if len(indices) % 3:
                print(f"  FAIL {prim['name']}: index count not a multiple of 3")
                failures += 1
            normals = glb_raw.read_accessor(doc, blob, attributes["NORMAL"]).astype("f8")
            deviation = np.abs(np.linalg.norm(normals, axis=1) - 1).max()
            if deviation > 0.01:
                print(f"  FAIL {prim['name']}: normals not unit length ({deviation:.4f})")
                failures += 1
            tangents = glb_raw.read_accessor(doc, blob, attributes["TANGENT"]).astype("f8")
            if not set(np.unique(tangents[:, 3])) <= {1.0, -1.0}:
                print(f"  FAIL {prim['name']}: tangent w not +-1")
                failures += 1
            for name in ("JOINTS_0", "JOINTS_1"):
                if name in attributes:
                    joints = glb_raw.read_accessor(doc, blob, attributes[name]).astype("i8")
                    if joints.max() >= len(doc["skins"][0]["joints"]):
                        print(f"  FAIL {prim['name']}: {name} out of range")
                        failures += 1
            weights = np.c_[*[glb_raw.read_accessor(doc, blob, attributes[n]).astype("f8") for n in ("WEIGHTS_0", "WEIGHTS_1") if n in attributes]]
            if np.abs(weights.sum(1) - 1).max() > 0.02:
                print(f"  FAIL {prim['name']}: weights do not sum to 1")
                failures += 1
        print(f"{Path(path).name}: {len(prims)} primitives, {total} vertices (limit {VERTEX_LIMIT}), failures {failures}")
        for prim in prims:
            print(f"   {prim['name']:10s} {doc['accessors'][prim['attributes']['POSITION']]['count']:6d} {prim['material']} {sorted(k for k in (prim['extras'] or {}))}")
        worst = max(worst, failures)
    return 1 if worst else 0


if __name__ == "__main__":
    sys.exit(main())
