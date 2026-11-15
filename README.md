# XIVAutoFit Blueprint

## System Overview
Fits outfits onto the FFXIV Doll Body 2. It takes an outfit exported from Penumbra, swaps its skin for the Doll Body 2 skin,
adds the Doll's metallic joints, fits the cloth so nothing clips, and writes a `.glb` the user imports back into Penumbra.
It runs headless in Blender. The project is a set of scripts plus notes; there is no application or package.

Flow: outfit exports (in practice `~/Downloads/APDoll-full-r2/`, passed to the scripts through `EXPORTDIR`) → `tools/` scripts → `builds/` (every build) → `~/Downloads/APDoll-full-r2/done/` (finished files, copied by hand).

Start with [tools/HANDOFF.md](./tools/HANDOFF.md), then [tools/SKILL.md](./tools/SKILL.md). Routing is in [CONTEXT.md](./CONTEXT.md);
agent rules (nested sessions, one writer of `tools/*.py` at a time) are in [AGENTS.md](./AGENTS.md).

## Subdirectories & System Boundaries
- `tools`: [./tools/README.md](./tools/README.md) - the Blender scripts (`transplant_body.py` is the main one), measure and render helpers, the ring-mod packers, and the HANDOFF and SKILL notes.
- `builds`: generated output (about 1.3 GB of `.glb` files, previews, intermediates). Gitignored, so it has no contract and is not documented here.

## Global Invariants
- The Blender build scripts write only into `builds/`; their output argument is a bare filename. The render scripts write PNGs to the prefix or path they are given, and the ring packers write to an optional out dir (default `builds/`).
- The Blender scripts delete any object named `Icosphere*` before exporting.
- `builds/` is not in git, so recipes and fit references depend on earlier builds already being on disk. Do not use git worktrees.
- Run Blender with `PATH=/usr/bin:/bin` so a `mise` Python does not break it.
- Nested sessions do not edit `tools/HANDOFF.md`; the master session records recipes there.

## Global Side Effects
- Reads outfit exports from `EXPORTDIR` (default `~/Documents/Meddle`; the usual value is `~/Downloads/APDoll-full-r2/`) and Penumbra mods from `/mnt/STORAGE/Penumbra`. `transplant.py` and `scale_pads.py` always read `~/Documents/Meddle/`.
- Writes `.glb` and `.pmp` files into `builds/`, plus `.png` renders wherever the caller points them.

## System Verification
- No automated tests. Run `cd tools && PATH=/usr/bin:/bin blender -b -P fitcheck.py -- ../builds/<name>.glb`, then `skin_poke.py`, then check in game.
