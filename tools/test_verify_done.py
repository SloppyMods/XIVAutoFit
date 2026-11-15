"""Tests for verify_done.py. Stdlib unittest only; every fixture lives in a temporary directory.

    python3 tools/test_verify_done.py
"""
import contextlib
import hashlib
import io
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import verify_done  # noqa: E402


class VerifyDoneTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.folder = self.root / "done_dionys"
        self.folder.mkdir()
        self.handoff = self.root / "HANDOFF.md"

    def tearDown(self):
        self.tmp.cleanup()

    def add(self, name: str, data: bytes) -> str:
        (self.folder / name).write_bytes(data)
        return hashlib.sha256(data).hexdigest()[:8]

    def run_tool(self, handoff_text: str, argv: list[str] | None = None) -> tuple[int, list[str], str]:
        self.handoff.write_text(handoff_text, encoding="utf-8")
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = verify_done.main(argv or [str(self.folder), "--handoff", str(self.handoff)])
        return code, out.getvalue().splitlines(), err.getvalue()

    def test_ok(self):
        h = self.add("A.glb", b"a")
        code, lines, _ = self.run_tool(f"- `done_dionys/A.glb` [{h}] checked\n")
        self.assertEqual(lines, ["A.glb: OK"])
        self.assertEqual(code, 0)

    def test_mismatch(self):
        h = self.add("A.glb", b"a")
        code, lines, _ = self.run_tool("- `done_dionys/A.glb` [deadbeef]\n")
        self.assertEqual(lines, [f"A.glb: MISMATCH (recorded deadbeef, actual {h})"])
        self.assertEqual(code, 1)

    def test_mismatch_last_of_several_records(self):
        h = self.add("A.glb", b"a")
        code, lines, _ = self.run_tool(f"- `done_dionys/A.glb` [{h}]\n- later `done_dionys/A.glb` [deadbeef]\n")
        self.assertEqual(lines, [f"A.glb: MISMATCH (recorded deadbeef, actual {h}; last of 2 records)"])
        self.assertEqual(code, 1)

    def test_last_record_wins_when_ok(self):
        h = self.add("A.glb", b"a")
        code, lines, _ = self.run_tool(f"- `done_dionys/A.glb` [deadbeef]\n- `done_dionys/A.glb` [{h}]\n")
        self.assertEqual(lines, ["A.glb: OK"])
        self.assertEqual(code, 0)

    def test_not_recorded(self):
        self.add("A.glb", b"a")
        code, lines, _ = self.run_tool("nothing here\n")
        self.assertEqual(lines, ["A.glb: NOT RECORDED"])
        self.assertEqual(code, 1)

    def test_missing(self):
        h = self.add("A.glb", b"a")
        code, lines, _ = self.run_tool(f"`done_dionys/A.glb` [{h}]\n`done_dionys/Z.glb` [12345678]\n"
                                       "`x/done_dionys/B.glb` [12345678] and `done_dionys/B.glb`\n")
        self.assertEqual(lines, ["A.glb: OK", "B.glb: MISSING", "Z.glb: MISSING"])
        self.assertEqual(code, 1)

    def test_bare_or_other_folder_name_not_flagged(self):
        h = self.add("A.glb", b"a")
        code, lines, _ = self.run_tool(f"`done_dionys/A.glb` [{h}]\nGone.glb [12345678]\n`done/Other.glb` [12345678]\n")
        self.assertEqual(lines, ["A.glb: OK"])
        self.assertEqual(code, 0)

    def test_hash_styles(self):
        h1 = self.add("A.glb", b"a")
        h2 = self.add("B.glb", b"b")
        h3 = self.add("C.glb", b"c")
        h4 = self.add("D.glb", b"d")
        text = (f"`done_dionys/A.glb` [{h1}]\n"
                f"done_dionys/B.glb ({h2}...)\n"
                f"`done_dionys/C.glb` ({h3}\u2026)\n"
                f"copied to `done_dionys/D.glb`, sha256 {h4}\u2026\n")
        code, lines, _ = self.run_tool(text)
        self.assertEqual(lines, ["A.glb: OK", "B.glb: OK", "C.glb: OK", "D.glb: OK"])
        self.assertEqual(code, 0)

    def test_uppercase_hex_and_long_hash(self):
        h = self.add("A.glb", b"a")
        full = hashlib.sha256(b"a").hexdigest().upper()
        self.assertTrue(full.startswith(h.upper()))
        code, lines, _ = self.run_tool(f"`done_dionys/A.glb` [{full}]\n")
        self.assertEqual(lines, ["A.glb: OK"])
        self.assertEqual(code, 0)

    def test_two_pairs_on_one_line(self):
        h1 = self.add("A.glb", b"a")
        h2 = self.add("B.glb", b"b")
        code, lines, _ = self.run_tool(f"`done_dionys/A.glb`, sha256 {h1}\u2026; then `done_dionys/B.glb` sha256 {h2}\u2026\n")
        self.assertEqual(lines, ["A.glb: OK", "B.glb: OK"])
        self.assertEqual(code, 0)

    def test_name_without_following_hash_gets_no_record(self):
        h = self.add("B.glb", b"b")
        self.add("A.glb", b"a")
        code, lines, _ = self.run_tool(f"`done_dionys/A.glb` (= `done_dionys/B.glb`, sha256 {h}\u2026)\n")
        self.assertEqual(lines, ["A.glb: NOT RECORDED", "B.glb: OK"])
        self.assertEqual(code, 1)

    def test_hex_inside_name_is_not_a_hash(self):
        self.add("c0201e6083_top.glb", b"a")
        code, lines, _ = self.run_tool("built `c0201e6083_top.glb` from /mt_c0201b0001_b.mtrl\n")
        self.assertEqual(lines, ["c0201e6083_top.glb: NOT RECORDED"])
        self.assertEqual(code, 1)

    def test_empty_folder_exits_zero(self):
        code, lines, _ = self.run_tool("nothing\n")
        self.assertEqual(lines, [])
        self.assertEqual(code, 0)

    def test_folder_not_a_directory_exits_two(self):
        self.handoff.write_text("", encoding="utf-8")
        code, lines, err = self.run_tool("", [str(self.root / "nope"), "--handoff", str(self.handoff)])
        self.assertEqual(code, 2)
        self.assertEqual(lines, [])
        self.assertTrue(err.strip())

    def test_handoff_missing_exits_two(self):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = verify_done.main([str(self.folder), "--handoff", str(self.root / "nope.md")])
        self.assertEqual(code, 2)
        self.assertTrue(err.getvalue().strip())


if __name__ == "__main__":
    unittest.main()
