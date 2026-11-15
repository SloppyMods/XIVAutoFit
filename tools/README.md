# tools: Blender scripts for fitting outfits onto the Doll Body 2

## Overview
Headless Blender (`bpy`) scripts that take an outfit exported from Penumbra as `.glb`, swap its skin for the Doll Body 2
skin, add the Doll's metallic joints, and move the cloth so it does not clip. Two scripts (`pads_to_ring.py`,
`pads_to_two_rings.py`) are plain Python with no Blender: they cut pads out of gear `.mdl` files and package a `.pmp` ring mod.
Status per outfit lives in [HANDOFF.md](./HANDOFF.md); build options and per-slot lessons live in [SKILL.md](./SKILL.md).

## Interface
All Blender scripts run as `blender -b -P <script>.py -- <args>`. Prefix with `PATH=/usr/bin:/bin` so a `mise` Python does not break Blender.
For the build scripts, the output name is a bare filename and the script writes it into `../builds/`. The render scripts and ring packers take a path or out dir instead.

**Build (write a `.glb`)**
- `transplant_body.py <outfit.glb> <doll part.glb> <out.glb>`: the main script. Swaps skin and adds joints. Configured by
  environment variables (full list in [SKILL.md](./SKILL.md)): `EXPORTDIR`, `DROPMAT`, `DROPMESH`, `JOINTMAT`, `MATFIX`, `KEEP`,
  `FIT*` (cloth fitting), `HEM*`, `SKINBACK`, `SKINCARVE`, `NOJOINTS`, and others.
- `transplant.py <outfit.glb> <joints.glb> <out.glb> [thr] [keep]`: transplants joints from a separate model; `keep` drops mesh groups >= keep. Env: `FIXL`, `FATTEN`, `SHRINK`. Reads inputs from `~/Documents/Meddle/` unless given an absolute path.
- `wrap_to_body.py <doll build.glb> <original export.glb> <out.glb>`: moves each cloth vertex by the gap between the Doll surface and the original body, so designed gaps stay the same size. Env: `WRAPFADE`, `WRAPSIGMA`, `WRAPMAX`, `WRAPSHOULDER`, `WRAPSPLITZ`, `WRAPPIERCE`.
- `fit_to_ref.py <outfit.glb> <reference body.glb> <out.glb>`: pushes cloth clear of a body the outfit does not contain (long boots over legs from the bottoms). Env: `FITCLEAR`, `FITR`, `FITDEEP`, `FITZMIN`, `FITPASSES`, `FITSIGMA`, `FITSMOOTH`, `FITSPLITZ`.
- `mirror_accessory.py <in.glb> <out.glb>`: copies a one-sided accessory across x=0, flips faces, swaps `_r`/`_l` bone weights, and joins the copy into the same mesh.
- `retarget_hands.py <outfit> <doll> <out> <keep>`: per side (`_l`, `_r`), fits a scale, rotation and shift (SVD) from the outfit's hand and finger bones to the Doll's, applies it to that side's vertices, drops vertex groups for bones the Doll lacks, re-parents the meshes to the Doll armature, and deletes the outfit armature. Meshes in groups >= `keep` are dropped.
- `scale_pads.py <src> <out> <scale> [elbows_only]`: scales pad meshes about their arm bone.
- `layer_fix.py <gap> <sf> <dg> <dz> <bg> <bb>`: one-off fix for the Bottoms6058 build (reads `Bottoms6058_base.glb`, writes `Bottoms6058_dollbody.glb`).

**Measure and render (read a `.glb`, print or write images)**
- `fitcheck.py <glb>`: signed distance in mm from each cloth mesh to the skin; negative means cloth is inside the skin.
- `skin_poke.py <glb>`: finds skin that pokes through cloth, which `fitcheck.py` cannot see.
- `clearance.py <glb>`, `measure_gap.py <out> <ref> <mesh names>`, `measure_overlap.py <glb>`: other distance and overlap reports. `measure_gap.py` only matches reference materials starting `/mt_c0201b0001_b`.
- `list_meshes.py <glb>`, `skel_diff.py <a.glb> <b.glb>`: inspect meshes and bone positions.
- `analyze_joint_components.py`: takes no arguments; always opens `~/Documents/Meddle/c0201e0000_glv.glb` and prints the joint pieces.
- `render_views.py <glb> <prefix> [zc] [scale] [cyan]`, `preview_render.py <src> <png>`: Workbench renders (front, back, side, chest).

**Ring mods (no Blender)**
- `pads_to_ring.py [out dir]` or `<out dir> --from <.pmp>`: cuts elbow and knee pads from the Big Belt gear and packs one `.pmp`. `--from` only accepts a `.pmp` at version `1.1.0` (`UNOPENED_VERSION`) and exits otherwise, so pads are never pushed out twice. Main symbols: `parse`, `cut`, `take_mesh`, `merge_boxes`, `check`, `open_around_limb` (with `raised_cosine`, `bump_mm`, `limb_angle`), `retarget_material`, `model_redirects`, `check_only_positions_moved`, `build`, `reopen_from_pmp`, and the constants `PARTS`, `COLORSETS`, `VERSION`, `UNOPENED_VERSION`, `OUT`.
- `pads_to_two_rings.py [out dir] [elbow mm] [knee mm]` or `<out dir> --from <knee .pmp> [--fit <name>]`: the same pads as two rings. Defines `MODS`, `KNEE_FITS`, `VERSION`, its own `build(part, out_dir, amount)` and `reopen_knee_from_pmp`; imports the cutting helpers from `pads_to_ring.py`. Give both mm amounts or neither.

**Docs**
- [HANDOFF.md](./HANDOFF.md): status per outfit, folders, user rules.
- [SKILL.md](./SKILL.md): every build option and the lessons per slot.

## Invariants
- Run headless inside Blender; the Blender scripts read their arguments after the `--` separator.
- Build output goes to `../builds/` (gitignored, 1.3 GB); build scripts take a bare output filename, not a path. Renders go to the given prefix or path; ring packers go to the given out dir.
- The Blender scripts that edit an outfit delete any `Icosphere*` object before exporting.
- Meshes are named `mesh <group>.<submesh>`; group 0 is skin, groups 1 and up are cloth, and a material containing `DOLL` marks a joint. Several scripts rely on this naming.
- `fitcheck.py` only measures cloth vertices; always follow it with `skin_poke.py` for skin showing through.
- `pads_to_ring.py` keeps renamed game paths the same length, so the `.mtrl` needs no other edits. It moves positions only (`check_only_positions_moved`).
- Only one session at a time changes these scripts (see the project `AGENTS.md`).
- Several scripts hardcode absolute paths (`/home/you/...`, `/mnt/STORAGE/Penumbra`, `~/Documents/Meddle`). Only `transplant_body.py` takes the export folder from `EXPORTDIR` (default `~/Documents/Meddle`). The `transplant_body.py` options listed above are a subset; [SKILL.md](./SKILL.md) is the reference, and the script's own source is authoritative.

## Side Effects
- Writes `.glb` files into `../builds/`, `.pmp` zips into `../builds/` (or the given out dir), and `.png` renders to the prefix or path given. Existing files of the same name are overwritten.
- Reads Penumbra mod folders under `/mnt/STORAGE/Penumbra` and exports under `EXPORTDIR` or `~/Documents/Meddle`.
- Resets the Blender scene with `read_factory_settings` on each run, so nothing carries between runs.

## Verification
- There is no automated test suite. Check a build with `PATH=/usr/bin:/bin blender -b -P fitcheck.py -- ../builds/<name>.glb`, then `skin_poke.py`, then try it in game.
