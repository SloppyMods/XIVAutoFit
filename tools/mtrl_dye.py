"""Make a copy of a Dawntrail-format .mtrl dyeable, changing nothing but its dye table.

    python3 mtrl_dye.py <in.mtrl> <out.mtrl>

Every colorset row gets the same dye entry, because some materials pick their row from a flat texture and the file alone cannot
show which row the game uses. The dye table is only read while a dye is applied, so the undyed look stays the same.
An existing output file is never overwritten.
"""
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import mtrl_read as mr  # noqa: E402

DYE_TEMPLATE = 422  # the template this outfit's own pants already use
DYE_CHANNEL = 0  # the item's first dye slot
DIFFUSE_ONLY = 0x1  # the dye may change a row's colour, but not its shine
TEMPLATE_SHIFT, CHANNEL_SHIFT = 16, 27
DYE_ENTRY = (DYE_TEMPLATE << TEMPLATE_SHIFT) | (DYE_CHANNEL << CHANNEL_SHIFT) | DIFFUSE_ONLY


def dyed_copy(source: str, target: str) -> mr.Material:
    material = mr.read_material(source)
    if not (material.is_dawntrail and material.has_table and material.has_dye_table):
        sys.exit(f"{source}: needs a Dawntrail colorset with a dye table")
    data = bytearray(Path(source).read_bytes())
    for row in range(material.rows):
        struct.pack_into("<I", data, material.dye_offset + 4 * row, DYE_ENTRY)
    with open(target, "xb") as handle:
        handle.write(data)
    return mr.read_material(target)


def main() -> None:
    source, target = sys.argv[1:3]
    result = dyed_copy(source, target)
    original, changed = Path(source).read_bytes(), Path(target).read_bytes()
    table_start, table_end = result.dye_offset, result.dye_offset + 4 * result.rows
    outside = sum(1 for i, (a, b) in enumerate(zip(original, changed)) if a != b and not table_start <= i < table_end)
    print(f"{Path(target).name}: {mr.dyed_row_count(result)} of {result.rows} rows take dye, bytes changed outside the dye table: {outside}, same size: {len(original) == len(changed)}")


if __name__ == "__main__":
    main()
