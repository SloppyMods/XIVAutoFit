#!/usr/bin/env bash
# The repo's checks. Exit 0 only when the branch is fit to review.
#
# The gate runs this script from the main checkout with the job's worktree as
# the working directory. Keep it fast, deterministic and non-interactive: no
# watch modes, no prompts, nothing that rewrites files.
#
# This project is Blender scripts with no test suite, and full Blender builds
# take minutes and need the gitignored builds/ folder. So the check is that
# every script in tools/ parses as Python (without writing .pyc files).
set -euo pipefail

python3 - <<'PY'
import pathlib, sys
bad = 0
files = sorted(pathlib.Path("tools").glob("*.py"))
if not files:
    print("no tools/*.py found; run from the repo root", file=sys.stderr)
    sys.exit(1)
for f in files:
    try:
        compile(f.read_text(encoding="utf-8"), str(f), "exec")
    except SyntaxError as e:
        print(f"{f}:{e.lineno}: {e.msg}", file=sys.stderr)
        bad += 1
print(f"checked {len(files)} scripts, {bad} with syntax errors")
sys.exit(1 if bad else 0)
PY
