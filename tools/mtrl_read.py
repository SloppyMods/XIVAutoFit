"""Read an FFXIV .mtrl file far enough to say whether it can be dyed. Read-only.

    python3 mtrl_read.py <file.mtrl> [more]

A material's colorset is a table of rows, each row being one colour band on the model. A dye table is a second table with
one entry per colorset row, saying which dye template the row uses and which of its colours the dye may change.
"""
import struct
import sys
from dataclasses import dataclass
from pathlib import Path

HEADER = struct.Struct("<IHHHHBBBB")
HAS_TABLE, HAS_DYE_TABLE = 0x4, 0x8
LEGACY_TABLE_BYTES = 512
ROW_HALFFLOATS_NEW = 32
LEGACY_DYE_BYTES = 32


@dataclass(frozen=True)
class Material:
    version: int
    shader: str
    textures: tuple[str, ...]
    has_table: bool
    has_dye_table: bool
    rows: int
    dye_rows: tuple[int, ...]  # one raw entry per colorset row, empty without a dye table
    is_dawntrail: bool
    table_offset: int
    dye_offset: int


def _text(strings: bytes, offset: int) -> str:
    return strings[offset:strings.index(0, offset)].decode()


def read_material(path: str) -> Material:
    data = Path(path).read_bytes()
    version, _, data_size, string_size, shader_offset, tex_count, uv_count, set_count, extra_size = HEADER.unpack_from(data)
    position = HEADER.size
    tex_offsets = [struct.unpack_from("<H", data, position + 4 * i)[0] for i in range(tex_count)]
    position += 4 * (tex_count + uv_count + set_count)
    strings = data[position:position + string_size]
    position += string_size
    extra = data[position:position + extra_size]
    position += extra_size
    flags = struct.unpack_from("<I", extra)[0] if len(extra) >= 4 else 0
    has_table, has_dye = bool(flags & HAS_TABLE), bool(flags & HAS_DYE_TABLE)
    width_log, height_log = (flags >> 4) & 0xF, (flags >> 8) & 0xF
    is_dawntrail = width_log > 0 and height_log > 0
    rows = 1 << height_log if is_dawntrail else 16
    table_bytes = (1 << width_log) * rows * 2 * 4 if is_dawntrail else LEGACY_TABLE_BYTES
    if not has_table:
        rows, table_bytes = 0, 0
    if table_bytes > data_size:
        raise ValueError(f"{path}: colorset of {table_bytes} bytes does not fit in {data_size} bytes of data")
    dye_offset = position + table_bytes
    dye_rows: tuple[int, ...] = ()
    if has_dye:
        kind = "<I" if is_dawntrail else "<H"
        size = struct.calcsize(kind)
        dye_rows = tuple(struct.unpack_from(kind, data, dye_offset + size * i)[0] for i in range(rows))
    return Material(version, _text(strings, shader_offset), tuple(_text(strings, o) for o in tex_offsets), has_table, has_dye, rows, dye_rows,
                    is_dawntrail, position, dye_offset)


def dyed_row_count(material: Material) -> int:
    """Rows whose dye entry lets a dye change at least one colour."""
    mask = 0x7FF if material.is_dawntrail else 0x1F
    return sum(1 for row in material.dye_rows if row & mask)


def main() -> None:
    for path in sys.argv[1:]:
        m = read_material(path)
        print(f"{Path(path).name}: shader {m.shader}, {'dawntrail' if m.is_dawntrail else 'legacy'} table, colorset {m.has_table} ({m.rows} rows), "
              f"dye table {m.has_dye_table}, rows that take dye {dyed_row_count(m)}")
        for texture in m.textures:
            print(f"   {texture}")
        if m.dye_rows:
            print("   dye entries:", " ".join(f"{row:x}" for row in m.dye_rows))


if __name__ == "__main__":
    main()
