## README.md

- Says the default exports folder is `~/Downloads/APDoll-full-r2/` ("or `EXPORTDIR`"). In code, `transplant_body.py` defaults `EXPORTDIR` to `~/Documents/Meddle`; the Downloads path only appears in the example command in `AGENTS.md`. `transplant.py` and `scale_pads.py` hardcode `~/Documents/Meddle/` with no override.
- Invariant "Scripts write only into `builds/`" is too broad. `render_views.py` writes `<prefix>_<view>.png` and `preview_render.py` writes to the `png` argument, both to wherever the caller points. `pads_to_ring.py` and `pads_to_two_rings.py` write to a caller-given `[out dir]` (default `builds/`).
- Global Side Effects says `.png` files go into `builds/`; that only holds if the caller passes a `builds/` path.
- The "output argument is a bare filename" rule is stated globally but does not apply to the render scripts or the ring packers.
- Not documented: the Blender scripts delete any object named `Icosphere*` before exporting (`transplant.py`, `retarget_hands.py`, `scale_pads.py`, `mirror_accessory.py`).

## tools/README.md

- `retarget_hands.py` is described as "moves hand bone weights onto the Doll armature". The code does not touch weights that way. For each side (`_l`, `_r`) it fits a scale + rotation + translation (SVD) from the outfit's hand/finger bone heads to the Doll's, applies it to that side's vertices, deletes vertex groups for bones the Doll lacks, re-parents the meshes to the Doll armature, and deletes the outfit armature. It also drops meshes in groups >= `keep`.
- Side Effects says renders are written to `../builds/`; `render_views.py` and `preview_render.py` write to the prefix/path argument instead.
- Invariant "Scripts take a bare output filename" is wrong for `render_views.py`, `preview_render.py`, and the two ring packers (`[out dir]`).
- `transplant.py` is called "older joint-only transplant", and `[thr]`/`[keep]` are not explained. The code shows `keep` drops mesh groups >= keep; `thr` is not described, and "older" is an inference not stated in the code.
- Hardcoded inputs are described only generally. Specifically undocumented: `analyze_joint_components.py` takes no arguments and always opens `~/Documents/Meddle/c0201e0000_glv.glb`; `measure_gap.py` matches only materials starting `/mt_c0201b0001_b`; `scale_pads.py` reads its source from `~/Documents/Meddle/`; `layer_fix.py` reads `Bottoms6058_base.glb` and writes `Bottoms6058_dollbody.glb`.
- `pads_to_ring.py --from` only accepts a `.pmp` whose `Version` is exactly `1.1.0` (`UNOPENED_VERSION`) and exits otherwise, to avoid pushing pads out twice. Not stated.
- Public symbols of `pads_to_ring.py` omit `VERSION`, `UNOPENED_VERSION`, `read_cstr`, `raised_cosine`, `bump_mm`, `limb_angle`, `take_mesh`, `merge_boxes`, `check`. `pads_to_two_rings.py` defines its own `build(part, out_dir, amount)` and `reopen_knee_from_pmp`, neither listed (it imports only the cutting helpers from `pads_to_ring.py`).
- The `transplant_body.py` env list is partial. Undocumented in the README (the "and others" points at `SKILL.md`, which was not re-checked): `BODY2`, `CLEAR*`, `DMAX`, `DROPJ`, `EXTRAJ`, `FB`, `FT`, `HEM2`, `HR1`, `HR2`, `HEMPASS`, `HEMZ`, `JSMESH`, `JSX`, `NIP`, `PIERCEY`, `PUSH*`, `SBX`/`SBZ*`, `SCMESH`/`SCX`/`SCY`, `SHRINKIN`, `WSYNC`, `WXMAX`, `WZHI`/`WZLO`, `XMAX`, `ZHI`/`ZLO`, and the `FIT*` family beyond `FIT`.
- `fit_to_ref.py`, `wrap_to_body.py`, `skin_poke.py`, `fitcheck.py`, `mirror_accessory.py`, and the `pads_to_two_rings.py` argument forms match their docstrings and code; no drift found.
