"""Check delivered .glb files against the short sha256 prefixes recorded in HANDOFF.md.

Plain Python 3.10+, no Blender. Read-only: it hashes every .glb directly in one folder and prints one status line per
file, then a MISSING line for each file HANDOFF places in that folder that is not there.

    python3 tools/verify_done.py ~/Downloads/APDoll-full-r2/done_dionys [--handoff PATH]

Exit 0 when every file is OK and nothing is MISSING, 1 otherwise, 2 when the folder or HANDOFF file does not exist.
"""
import argparse
import hashlib
import re
import sys
from pathlib import Path

NAME = re.compile(r"[^\s`'\"()\[\],;]+")
HASH = re.compile(r"(?<![0-9A-Za-z_])[0-9a-fA-F]{8,}(?![0-9A-Za-z_])")


def short_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()[:8]


def parse_handoff(text: str) -> tuple[dict[str, list[str]], list[str]]:
    """Return (base name -> recorded prefixes in file order, every written name with its directories)."""
    records: dict[str, list[str]] = {}
    written: list[str] = []
    for line in text.splitlines():
        names = [m for m in NAME.finditer(line) if m.group().endswith(".glb")]
        written += [m.group() for m in names]
        hashes = [m for m in HASH.finditer(line)
                  if not any(n.start() <= m.start() < n.end() for n in names)]
        for i, name in enumerate(names):
            limit = names[i + 1].start() if i + 1 < len(names) else len(line)
            found = next((h for h in hashes if name.end() <= h.start() < limit), None)
            if found:
                base = name.group().rsplit("/", 1)[-1]
                records.setdefault(base, []).append(found.group()[:8].lower())
    return records, written


def check(folder: Path, handoff: Path) -> tuple[list[str], bool]:
    records, written = parse_handoff(handoff.read_text(encoding="utf-8"))
    lines = []
    ok = True
    disk = sorted(p for p in folder.glob("*.glb") if p.is_file())
    for path in disk:
        actual = short_hash(path)
        recorded = records.get(path.name)
        if not recorded:
            lines.append(f"{path.name}: NOT RECORDED")
            ok = False
        elif recorded[-1] == actual:
            lines.append(f"{path.name}: OK")
        else:
            note = f"; last of {len(recorded)} records" if len(recorded) > 1 else ""
            lines.append(f"{path.name}: MISMATCH (recorded {recorded[-1]}, actual {actual}{note})")
            ok = False
    present = {p.name for p in disk}
    missing = set()
    for name in written:
        parts = name.split("/")
        if len(parts) >= 2 and parts[-2] == folder.name and parts[-1] not in present:
            missing.add(parts[-1])
    for name in sorted(missing):
        lines.append(f"{name}: MISSING")
        ok = False
    return lines, ok


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("folder", type=Path)
    parser.add_argument("--handoff", type=Path, default=Path(__file__).resolve().parent / "HANDOFF.md")
    args = parser.parse_args(argv)
    folder = args.folder.resolve()
    if not folder.is_dir():
        print(f"not a directory: {args.folder}", file=sys.stderr)
        return 2
    if not args.handoff.is_file():
        print(f"HANDOFF file not found: {args.handoff}", file=sys.stderr)
        return 2
    lines, ok = check(folder, args.handoff)
    for line in lines:
        print(line)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
