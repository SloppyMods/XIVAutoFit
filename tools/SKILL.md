---
name: ffxiv-body-joint-transplant
description: Add body-mod-only geometry (e.g. Doll Body 2 metallic joints) to outfits that were not made for it, using Penumbra glTF export, Blender and Penumbra glTF import. Use for "joints invisible under clothes", "add Doll joints to this outfit", "body mod meshes missing on gear". Not for plain texture or tint fixes.
---

# FFXIV body-mod geometry transplant (Doll Body 2 joints)

Tested 2026-10-24 on Avalanche Brawler's Top (works), Halfgloves (works after fixes), Bottoms (skipped: stockings cover the knees). Never tested in game by Claude; the user tests.

## Why it happens

Doll Body 2 joints are separate meshes on `/mt_c0201b0001_DOLL.mtrl` (textures `dolljoints_*`). Gear that covers a body slot replaces the body mesh, so the joints vanish. The outfit `.mdl` has no `DOLL` meshes, so a `.mtrl`-only fix does nothing. The joints must be added to the outfit model.

## Hard rules learned

- Export with Penumbra: mod -> Advanced Editing -> Models -> load the `.mdl` -> **Export to glTF**. Do NOT use Meddle exports for geometry. Meddle exports at the character's own skeleton scale (about 4-8% off, Customize+ off does not fix it); importing that gave a floating head. Meddle is fine for previews only.
- Penumbra glTF: node names are `mesh M.S`. One material per mesh group M. Sub-meshes S share it. Attributes (`atr_ude`, `atr_hij`, `atr_nek`...) live in node `extras`. Extra material = extra mesh group (new M).
- Import: **Keep current materials OFF**. **Keep current attributes**: ON only for the first Avalanche top (Meddle-derived file, no attributes); for Penumbra-export merges that change mesh layout (body-swap, renumbered groups) it is unverified/likely harmful, because Penumbra copies the old model's attributes by position. Try OFF first for body-swap files (user testing 2026-10-24: top Golem skin missing with ON). Import overwrites the mod's `.mdl`; back up first. Proteus retarget files were overwritten once and had to be regenerated with Proteus.
- Export error "same key already added /mt_c0201b0001_b.mtrl": model lists the material twice. Rename the second entry temporarily, export, then discard the rename.
- Export error "Tried to build skinned vertex but no bone mappings": tick Generate Missing Bones; if it persists try a different model variant.
- Source joints must match the outfit's body size/shape (top: Smallclothes Body XS - Inverted; legs: Smooth - Sexless; hands: Hands/Smallclothes DOLL).

- Chest flatness, every top and full-body piece (rule added 2026-11-03 after e0753, where the user saw cups standing off the Doll chest): the Doll chest is flat, and the fit (`fit_to_ref.py`) only pushes cloth out of the skin, never in, so cloth made for a Bibo bust keeps its bulge. After the fit, run `blender -b -P chest_flat.py -- <build.glb> -` and read the `GAP` lines for the cloth over the chest. If `min` is above about 5 mm at z 1.20-1.34 (e0753 before: 8.6 to 10.9 mm at the bust peak), pull the cloth in with `blender -b -P chest_flat.py -- <in.glb> <out.glb> 2.5`, setting `CFMESH` to the chest cloth's mesh names; if it is already near the clearance (the suit in e6083 hides a flat chest), leave it. The medians stay a few mm above `min` because a cup is a shell, so judge by `min` and `p10`. Confirmed on e0753 only (cups at least 2.5 mm off the skin, no skin through cloth, other meshes unmoved), not yet tried in game; the 5 mm threshold is a first guess to tune. It pulls front cloth only inside the panel |x| below 0.19 and z 1.14-1.38, and it assumes the skin is `mesh 0.*`.

## Process

1. Penumbra-export the outfit `.mdl` and the Doll Body 2 smallclothes `.mdl` for the same slot into `~/Documents/Meddle/` (`c0201e6258_<slot>.glb`, `c0201e0000_<slot>.glb`).
2. Run, sandbox on, output under the project (home Documents is read-only to Claude):
   `blender -b -P ~/Projects/ffxiv-tools/XIVAutoFit/tools/transplant.py -- <outfit.glb> <joints.glb> <out.glb> <mode> <keep>`
   - `<mode>` `0`: no trim. `>0`: delete joint vertices within that many metres of the outfit cloth (hands: 0.010 too aggressive on the knuckle caps, 0.006 leaves slivers). `-1`: delete finger knuckle caps (per finger keep the 4 outermost components, hands only).
   - `<keep>`: drop outfit meshes with group index >= keep (use 2 for the old 3-LOD glove export; 99 keeps all).
   - Env `FIXL=1 FATTEN=<mm> SHRINK=<mm>`: snap the left glove to the mirrored right glove, widen it, thin the left bare fingers (gloves asymmetry). Final gloves used `FIXL=1 FATTEN=1.5 SHRINK=1`, mode `-1`, keep `99`.
3. Preview before asking the user: `blender -b -P .../preview_render.py -- <out.glb> <png>` (joints red, cloth dark, skin tan; hand view; edit the camera for legs) and read the PNG.
4. User imports in Penumbra (rules above) and screenshots the result. Fix from the screenshot; do not guess.

## Findings per slot

- Top: Doll joints are 3 `DOLL` sub-meshes; added as mesh group 3. Worked first try with Penumbra exports.
- Gloves: the first outfit export had 3 near-identical mesh pairs (LOD copies, <0.5 mm apart); keeping all caused z-fighting. Re-exporting from the modded/resolved glove gave one clean copy. Joint knuckle caps poke through the cuffs: remove them. The wrist dome (`n_hte` bone) was left in.
- Left glove finger stubs were smaller than the right (about 2 mm mean, up to 9 mm), so left skin broke through. Mirror-snap plus widen fixed it.
- Legs: stockings cover the knees; joints invisible or slivers. Skip unless the user wants new geometry.

## Notes

- Joint skeleton (168 bones) is a subset of the outfit skeleton (455 or 168); the script checks this.
- Two copies of `mt_c0201b0001_DOLL.mtrl` (Doll Body mod and Avalanche Top mod) are identical (same MD5); no mod conflict there.
- Penumbra mod root on this machine: `/run/media/SloppyMods/DATA/Penumbra`.
- MeddleTools (Blender add-on) only imports Meddle exports for previews; it does not write `.mdl`.

## Outfits with their own coarse skin (body-swap mode)

If the outfit's skin meshes (`mt_c0201b0001_a`) are low-poly arm/torso tubes, the Doll joints sit inside them and nothing shows (e.g. `c0201e0888_top`). Use `transplant_body.py -- <outfit.glb> <doll_smallclothes.glb> <out.glb>`: drops the outfit's `mt_c0201b0001_*` meshes, adds the Doll skin as group 0 (`/mt_c0201b0001_b.mtrl`), keeps the cloth as group 1, joints as the next group. Elbow joints then show on bare arms; chest joints stay under the cloth. Check the neck in game (outfit `atr_nek`/`atr_lod` skin parts are dropped).

`pads_to_ring.py` cuts gear pads directly from a mod's `.mdl` into a ring `.pmp` without Blender (see `HANDOFF.md`). Elbow/knee pad accessories (ring-slot items like `c0201a0013_rir`): `scale_pads.py -- <in.glb> <out.glb> <scale> [elbows_only]` scales pads about the elbow bone and can drop the knee pads.

User-confirmed in game: elbow pads at scale 1.08 (`elbows_only`) fit the Doll arms; 1.15 was too big.

## Body-swap env options (`transplant_body.py`)

`JOINTMAT=cut,gem` joint material tokens (Golem; default `DOLL`). `MATFIX="UNKNOWN=/mt_x.mtrl"` rename materials Penumbra exported as UNKNOWN (use the name from the outfit `.mdl`). `PUSH=<mm> PUSHMESH="mesh 1.0"` push cloth out of the skin (only on a simple inner garment; on detailed pants it tears the straps). `HEM=<mm> HEMMESH HEMPASS HEMZ` pull a shirt hem forward of the stomach (can rag belt straps). `SHRINKIN=<mm> ZLO ZHI` pull Golem skin and joints inside full-length pants (fixes skin poking through the butt/knees; worked on Atlas camo pants). Golem Body (Test4): joints are `cut`+`gem`; full-length pants hide them.

## Golem top recipe (NOT confirmed: the SKINBACK build has not been tried in game as of 2026-10-24; an earlier FIT=12 build had belly cracks in the user's screenshot, and the user later said an earlier change fixed it without saying which)

Inputs: `c0201e0888_top.glb` (outfit) and `c0201e0000_top.glb` (Golem smallclothes chest), both Penumbra exports. Imported with Keep current attributes OFF.

`SKINBACK=10 FITWSYNC=1 NIP=1 FIT=12 FITLAYER=0.02 FITX0=0.06 FITX1=0.09 FITZ0=1.28 FITZ1=1.33 FITHZ=1.15 FITHX0=0.13 FITHX1=0.16 JOINTMAT=cut,gem blender -b -P transplant_body.py -- c0201e0888_top.glb c0201e0000_top.glb Top0888_golem.glb`

Lessons (unconfirmed where noted): (1) the fit must be limited to the central inner-shirt panel; the whole cloth mesh also holds the vest, so a global push drags the vest forward. (2) `SKINBACK` (pull the Golem belly skin back 10 mm) was my fix for the cracks in the screenshot; UNTESTED; rest-pose measurements said the hem was already outside the skin, but the game showed jagged intersections because the surfaces were only a few mm apart. (3) When measurements and the user's screenshot disagree, trust the screenshot and add margin on the skin side. (4) Golem skin includes a nipple mesh (`NIP=1` drops it). Legs for the same set: `FT=1.07 FB=1.10 SHRINKIN=6 ZHI=1.12 DMAX=0.08 WSYNC=1 MATFIX="UNKNOWN=/mt_c0101e0376_dwn_b.mtrl" JOINTMAT=cut,gem` on the Atlas camo pants (c0201e0376_dwn); user said legs "better", butt weight issue addressed with WSYNC.

## Export and output folders (2026-10-25)

User sends exports to `/home/you/Downloads/APDoll-full-r2` (set `EXPORTDIR` for the tool; default is `~/Documents/Meddle`). Finished files go in its `done/` subfolder. The sandbox cannot write under Downloads, so build into `XIVAutoFit/builds/` first, then copy the finished file with `cp` run outside the sandbox (the user asked for this folder explicitly). Do not run the `.py` scripts that came in that folder (downloaded).

Check delivered files against `HANDOFF.md` with `python3 tools/verify_done.py ~/Downloads/APDoll-full-r2/done_dionys` (read-only): one line per `.glb` (`OK`, `MISMATCH`, `NOT RECORDED`), then `MISSING` for files HANDOFF places in that folder that are not there.

## Gloves (2026-10-25)

- A glove export can hold the left and right glove as two separate mesh groups with the same material (`c0201e0634_glv`: groups 1 and 2, x<0 and x>0). They are not LOD copies. Check bounding boxes before using `KEEP`; build with `KEEP=99 DROPMAT=UNKNOWN JOINTMAT=DOLL`. User confirmed in game: both hands good.
- Male-only gloves (`c0101e*`, mod ships no `c0201` model) are **parked** (user decision 2026-10-25) — do not rebuild unless asked. `retarget_hands.py` refits a male glove onto the Doll hand bones (similarity fit per hand, rebinds to the Doll armature), but the in-game result was shredded. Suspected cause, untested: Penumbra converts male models to female at runtime, so a female-space glove imported into the `c0101` path is converted twice. Both untried escapes are recorded in `HANDOFF.md` (import into a `c0201e0218_glv` path added in Penumbra, or build in male space).
- A Penumbra export with `Generate Missing Bones` returns the full 450-bone skeleton; vertex positions were unchanged (2.6 mm mean vs my build).
- Rendered "shards" on `c0101e0218` were flowers, ribbons and leaves (the glove's real design), not corruption. Compare against the TexTools viewer before diagnosing geometry.
- TexTools on this machine (Wine prefix `~/ffxiv-textools-linux/prefix`): settings in `AppData/Local/FFXIV_TexTools/*/3.1.1.7/user.config`; its `E:` drive is the NTFS DATA disk and may be unmounted. Paths now point at `Z:\home\SloppyMods\Textools`, `Z:\home\SloppyMods\TTModPacks`, `Z:\mnt\fedora\Penumbra`.

## Session 2026-10-25 (tops, pants, gloves round 2)

- Fit/push mesh names (`FITMESH`, `PUSHMESH`) must match the name AFTER renumbering when the cloth sits in a group that gets renumbered (e.g. top e0453: source `mesh 0.2` is `mesh 1.2` at fit time). A name mismatch silently does nothing; check the printed `fitfast`/`push` lines. `FITFAST` did nothing on that top; `PUSH=8 PUSHMESH="mesh 1.2"` worked (min clearance 8 mm).
- `PUSHZ=lo,hi` limits `PUSH` to a height band (added). A band that includes pockets crumples them; keep it below pocket height.
- Gloves with cloth sitting 0-3 mm off the Doll hand: `PUSH=7 PUSHMESH="mesh 1.0,mesh 1.1"` gave a clean fit (e0707).
- Layered garments in one mesh (denim over black shorts in e6058 mesh 1.0): `layer_fix.py` splits loose parts by connectivity, pushes the outer layer off the inner one (BVH), shrinks the waist by height ramp and pushes belt pieces out. Args: `hemGap mm, waistScale, denimGap mm, denimZmax, beltGap mm, beltOffBody mm`. Reads `Bottoms6058_base.glb`, writes `Bottoms6058_dollbody.glb` in `XIVAutoFit/builds/` (edit names inside for other outfits). `clearance.py -- <glb>` prints signed cloth-to-skin mm per cloth mesh.
- Per-vertex restore from the source mesh by nearest vertex tears layered parts; do not. Vertex counts of a mesh differ by 1 between fitted and unfitted builds, so index blending fails too.
- Armband removal: delete the vertices of that part in the source glb (check it with a colored render first), then build. Top0553 armband = meshes 3.1, 3.2.
- Renders cannot show texture colors; a "black" complaint can be a dye/texture issue (user fixed the shorts belt by dyeing).
- Penumbra can re-export a mod `.mdl`; exported with `Generate Missing Bones` it has the full 450-bone skeleton.
- Skip the Doll build for full-cover bottoms (e.g. e0799 baggy cargo pants): no skin or joints show, so the original model is better and avoids clipping. User reimported the original instead (2026-10-25). Check coverage in a render before building.
- Body-and-legs top (e6120, user confirmed good 2026-10-25): `DROPMAT=bibo,UNKNOWN BODY2=<Doll dwn.glb> NIP=1 JOINTMAT=DOLL`; Penumbra's `UNKNOWN` was `/mt_c0201b0001_bibopube.mtrl` (checked by grepping the mod's `.mdl`). Torso push: `PUSH=9 PUSHX=0.18 PUSHZ=0.95,1.45 PUSHMESH=<big jacket/shirt meshes>`. `PUSHX` limits PUSH to |x| (keeps sleeves and elbow joints unchanged).
- `PUSH` now moves seam-duplicate vertices (same position) together. Before this, jackets cracked open at UV seams.
- `~/Documents/Meddle/c0201e0000_top.glb` is the old Golem top (cut/gem joints). The Doll top is `/home/you/Downloads/APDoll-full-r2/c0201e0000_top.glb`. Check the joint material (DOLL vs cut/gem) before reusing an old file.
- Adding Doll joints to the original outfit with its own bibo skin buries them inside the skin (`Doll_joints_all.glb` via the `mj` merge, `transplant.py`): not worth it; use the body swap.
- Joints sticking out of cloth in poses (shoulder joints on e6120): `WSYNC=1 WSYNCJ=1 WZLO=1.2 WZHI=1.45` copies cloth bone weights to the Doll joints only (`WSYNCJ` = joints only, skin untouched). `SHRINKIN` with `SHRINKJ` exposed a sliver of joint at a thin collar in the render; do not use it for shoulders. Unconfirmed in game.
- If `blender -b` fails with `No module named 'math'`, a `mise` Python is first in `PATH` (2026-10-25). Run with `PATH=/usr/bin:/bin`.
- `JSX=0.8 JSMESH="mesh 6.0"` narrows the chest/shoulder joint piece side to side (about x=0) so its tips stay inside the jacket (added for e6120, unconfirmed).
- e6120 final recipe (2026-10-25): `DROPJ="mesh 6.0"` (new: removes joint pieces by name; the shoulder/collar joint was not visible anyway), `PUSH=9 PUSHX=0.12 PUSHZ=0.95,1.30 PUSHMESH="mesh 3.0,mesh 5.0"`. Pushing meshes 1.1/1.2/2.1/4.1, or a band above z=1.30 or wider than x=0.12, tears the shoulder pad into a spike (checked with a close-up render of x 0.15, z 1.33). `SKINCARVE` (carve skin under cloth) is in the script but gave bad results; do not use.
- Always close-up render pads, pockets and collars after a push; the full-body render hides tears.
- Piercings (e0861, 2026-10-26): a body-slot export can carry `/mt_c0201b0001_piercings.mtrl` meshes (navel). Penumbra exports them as `UNKNOWN`; set `MATFIX="UNKNOWN=/mt_c0201b0001_piercings.mtrl"`. The script now exempts `piercings` from the "drop every `/mt_c0201b0001_*` mesh" skin rule, so they survive as a cloth group. They are modelled for another body and sit inside the Doll belly: `PIERCEY=<mm>` shifts them forward (6 mm cleared it). Grep the mod's `.mdl` with `strings` to read the real material names; Penumbra's mod folder is whatever `ModDirectory` says in `~/.xlcore/pluginConfigs/Penumbra/config/penumbra.json` (it was `E:\Penumbra` = `/run/media/SloppyMods/DATA/Penumbra` on 2026-10-26, not `/mnt/fedora`).
- Ripped jeans (`c0201e0824_dwn`, 2026-10-25): the outfit's own `mesh 0.0` (`bibo`) had the entire lower butt and solid-jeans region cut out (884 verts vs Doll's 1460). Morphing the full Doll `mesh 0.0` against that partial mesh with `find_nearest` yanked the Doll lower-butt vertices onto the rim of the hole (`z=0.77..0.85`), creating a diagonal ridge that poked out of the butt both standing and when bent over (plus a 25% `j_asi_a_r` vs `j_kosi` bone-weight mismatch). Fix: (1) **before** morphing, delete all covered butt/hip faces of Doll `mesh 0.0` (`z=0.785..0.955` on the left leg, `z=0.80..0.955` on the back right leg, `z=0.83..0.955` on the front right leg, plus any face `>8 mm` from `orig_s0`), leaving only the waist and the thigh-rip backing sleeves; (2) morph the remaining vertices 3.5 mm inside `orig_s0`; (3) barycentrically transfer bone weights (`WSYNC`) from `mesh 1.0`'s triangles onto `mesh 0.0` in `z=0.71..0.98`; (4) always call `bpy.ops.wm.read_factory_settings(use_empty=True)` between loading a reference glb and loading the build glb so Blender does not append `.001` to material names.
- Layered/decal trim meshes over a fitted bodice (`c0201e0256_top`, 2026-10-25): `mesh 3.0` (`_top_d.mtrl`, glowing red emissive lines) sits only 0.13–0.16 mm outside `mesh 1.0` (`_top_b.mtrl`, the base bodysuit), and `mesh 2.0` (`_top_c.mtrl`, black trim) overlays it. Running `FIT=2.5` independently on `mesh 1.0,mesh 2.0,mesh 3.0` pushes all three toward the same 2.5 mm skin-clearance surface, which pushes `mesh 1.0` further than `mesh 3.0` and buries the glowing red lines inside the cloth (650/1908 vertices went negative). Fix: fit `mesh 1.0` only (`FITMESH="mesh 1.0"`) and pass `FITFOLLOW="mesh 2.0,mesh 3.0"` so follower meshes receive the exact barycentric triangle displacement from `mesh 1.0` in memory before export — preserving the 0.15 mm layer offset verbatim (`neg<0: 101/1917`, identical to the original export). Also use `FITZ0=1.27 FITZ1=1.31 FITBZ0=1.44 FITBZ1=1.46` so the front stops below the chest cutout/necklace/collar while the back reaches the base of the collar, plus `BODY2=~/Documents/Meddle/c0201e0000_dwn.glb NIP=1 SHRINKIN=5 ZLO=0.81 ZHI=1.06` because `e0256_top` replaces both top and legs (its bibo skin spans neck to ankle) and the Doll butt would otherwise poke through the back of the shorts.
- e6120 back (final): `PUSH=9 PUSHX=0.08 PUSHZ=0.95,1.44 PUSHMESH="mesh 3.0,mesh 5.0" DROPJ="mesh 6.0"`; user: "looks good". Narrow (|x|<=0.08) but tall push covers the spine without tearing the shoulder pad. See `HANDOFF.md` for the full status and open items.
- Brawler e6258 (untested in game): for a body-tight outfit made for another body, use `wrap_to_body.py`, finish with `fit_to_ref.py`, and check with `skin_poke.py` as well as `fitcheck.py`. When two meshes share one `UNKNOWN` material, `DROPMESH` removes one by name and `MATFIX` names the other. See `HANDOFF.md` for the recipe.
- Bodysuit e6083 (untested in game): when two source groups share one `UNKNOWN` material and both must stay, `GROUPMAT="1=/mt_a.mtrl;2=/mt_b.mtrl"` names them per group (`transplant_body.py`; take the names from the `.mdl`). Coarse cloth can cut through a rounded body while every cloth vertex is clear, so `fitcheck.py` passes and `skin_poke.py` does not. `FITPOKE=<mm>` in `fit_to_ref.py` also pushes any cloth triangle a skin vertex comes through, and `FITPOKEZ=<m>` limits that to skin above a height; set it above the leg openings, because without it the hem crumples. Both are off by default. After a large fit, check thin overlays such as lacing, which can sink into the moved cloth.
- Full-leg bodysuit e6213 (untested in game): when tight cloth covers the legs, sync the legs as well as the chest. `WBANDS="zlo,zhi,xmax;..."` adds weight-sync bands with their own x limits, `WSYNCSRC="mesh 2.0"` copies from the suit only (otherwise a hidden jacket or sash can be the nearest cloth), and `WSYNCTRI=1` blends the nearest triangle's corners instead of copying one vertex. All three are off by default. Measured on bent poses, this removed the knee poke in a squat and the belly joint poke when bending or twisting; the hip ray count in a squat rose (160 to 268), though renders of that pose show no skin. Read `[Toggles]` as a bitmask over option positions, so you know which pieces the user sees; here the worn jacket lives on the earrings slot, so a fit that moves the suit can break through a jacket it never touched.

## HR3 male tops: what the study of modder files taught us (2026-11-09)

Full data: `builds/_male/hr3_study_findings.md`, review: `builds/_male/hr3_study_review.md`. **Nothing here has been tested in game.** Simulated poses only, with one custom author (RUFF) and one vanilla conversion (e6259) as references. All new options are off by default; with none set, `male_fit.py` cloth positions match the old builds (0.0 mm on Top6025 and Hannya). The one always-on change: skin tags now come from `SKINMDL` when a shell skin piece is reused.

**Position before weights.** Swapping our weights onto the custom top's positions leaves standing exposure at 0, so positions decide standing; our weights add the damage in motion (bend 73, arms_up 281).

**Recipes, added to the usual `MFWSYNC=60 SKINMDL=...`:**
- Close-fitting single-layer top: `MFFINISH=3 MFFINISHMAX=15 MFDENSEPOKE=6 MFUNCROSS=2`, with `MFCLEAR=5` or more.
- Layered outfit with loose or capes pieces: `MFFINISH=3 MFFINISHMAX=15 MFUNCROSS=2`. No dense rays: they enlarged a cape notch on Hannya.
- Tight top (torso median gap under about 10 mm): also `MFWSYNCX=0 MFWSYNCSAFE=1`, after positions. Check arm poses. It gave nothing on Hannya.

**Score with `male_exposed.py` and a render, not poke counts.** The custom RUFF top the user reports working scores the same poke count as our RUFF build (126 vs 127 at 15 mm), but 0 vs 169 cm2 exposed. Scores cannot see small slits at cuffs and hems or a cape notch: always look at a render. Default poses include arms; `XPLAG=0.5` imitates `n_hkata` twist (real share unknown); `XPREGIONS=1` lists body regions.

Exposed skin cm2 above the waist, then crossed layers (cloth layers truly passed through each other):

| build | stand | bend | twist | arms_up | arms_forward | crossed |
|---|---|---|---|---|---|---|
| RUFF as built (`Top6025_hr3_final3`) | 169 | 203 | 343 | 199 | 700 | 40 |
| RUFF new positions (`Top6025_r25`) | 32 | 46 | 135 | 41 | 457 | 7 |
| + torso weight copy (`Top6025_r26`) | 32 | 32 | 32 | 45 | 259 | 7 |
| Custom HR3 RUFF (target) | 0 | 0 | 0 | 1 | 164 | 9 |
| Hannya as built (`Hannya_top_hr3_v2`) | 41 | 38 | 40 | 45 | 260 | 125 |
| Hannya new, no dense (`Hannya_r15`) | 30 | 28 | 30 | 31 | 236 | 16 |

With `XPLAG=0.5`, arms_up / arms_forward: RUFF as built 224 / 302, r26 52 / 130, custom 4 / 31.
Percent of edges stretched over 1.5x, RUFF as built vs r26: bend 0.50 to 0.71, twist 0.49 to 0.89, arms_up 4.28 to 3.33. Stretch is reported only: it did not separate the known-bad pants v3 from known-good v8 (running 1,290 vs 1,283 edges).
Cloth moved from old RUFF: median 1.5 mm, 95% under 9.2 mm, but 11 vertices over 30 mm (max 145.6) near the hem, from the main pushes and not capped.

**What each change does:**
- `MFFINISH` lifts what the last blur pushed back under the clearance. RUFF was built without it (380 vertices under skin).
- `MFFINISHMAX` caps finish moves (uncapped about 100 mm, dragging hems and inner walls). The user has rejected cloth moved far off the body twice.
- `MFDENSEPOKE` adds rays from dense skin points in finish rounds only, catching coarse triangles with clear corners. Only cloth facing outward is lifted, because lifting folded inner layers caused cuff and collar slits. RUFF standing went from 118 to about 32.
- `MFUNCROSS` moves an outer-facing vertex past a body-facing layer just in front of it. Judged per surface against its own nearest skin: a first version without that rule swapped surfaces that only face each other (sleeve against torso).
- `MFWSYNCSAFE` with `MFWSYNCX=0`: torso skin-weight copy with 8 bone slots, keeping `j_sk_`/`j_ex_` bones, from same-limb skin only. RUFF twist 135 to 32. It costs bend and twist stretch (above).

**Tried and dropped:**
- Dense rays in the main wide-radius pushes (`MFDENSEPUSH=1`, kept off): Hannya arms_up 45 to 214.
- Dense rays on layered outfits: cape notch grew.
- Leaving inner walls out of the pushes: no measurable gain. Removed.
- Same-limb filter on poke rays: no help on Hannya, RUFF twist worse (79 to 100). Removed.
- Raising clearance alone: leaves exposure through coarse triangles.
- Weight copy alone: no effect standing (169 before and after).

**Limits and open questions:**
- Poses are not game animation.
- RUFF stays at 32 cm2 standing (chest), custom is 0. Its positions could not be reached: custom's vertices sit far from ours on the shared mesh, and its normal offset or sliding alone made things far worse (1571 and 993 cm2 standing), so the two cannot be tested apart.
- Small slits remain at RUFF's cuff and hem.
- The pants tear (done v3, "stretches or tears", vs v8, "looks good") is not explained by stretch or exposed area, and pants were not rebuilt. Not covered.

## Dionys conversions: what the clip-free originals taught us (2026-11-09)

Full data: `builds/_dionys/dionys_study_findings.md`. Measured on 9 original exports whose skin is exactly the Dionys body, which the user reports as clip-free in game. **Our two pilots built from these lessons are untested in game.**

**Find which outfits are already on a body by measuring the skin against the devkit, not by file name.** A real match is 0.00 mm median and p95; other bodies are 1.2 mm or more. `Top6022_Epsilon_Dionys_dollbody.glb` is Doll skin despite its name.

**What the clip-free pieces do:**
- Close cloth copies the skin's bone weights (0.003 to 0.02 weight difference; our Doll tops 0.09 to 0.26), including physics bones (`iv_`): cloth and skin carry the same share. Dionys skin has `iv_` weights at hips and chest, so cloth needs them. Loose parts keep their own weights.
- Gap on tight pieces: p5 1.3 to 3 mm, median 3 to 6 mm, about even: it does not grow at knees or armpits (rank correlation with body stretch -0.39 to -0.11 on 7 of 9). No need for a big clearance.
- Removing hidden skin is optional: 6 of 9 do, 3 of 9 keep almost all of it, all clip-free.

**Scores that mislead on clip-free pieces:** poke count (up to 2,722), crossed layers (up to 3,523), stretch (up to 5.57%). Exposed area is the best we have but is not 0 on them: up to 16 cm2 standing at hems, 67 in a deep sit. Compare against those, and always render.

**Recipe** (`tools/dionys_body.py` for the body, then, from `tools/`, the existing swap and fit): `DROPMAT=bibo,UNKNOWN JOINTMAT=NOJOINTMATERIAL NOJOINTS=1` with `transplant_body.py` from the **original export** (same or better than the Doll fit), then `fit_to_ref.py` at `FITCLEAR=3`, then for bust-shaped tops a `CFFIELD=1 CFWRAP=<export>` chest flatten and a second `fit_to_ref.py` (the flatten pushed the bra's lower edge up to 9 mm under the skin until that pass), and finally `dionys_weights.py`. Check with `dionys_exposed.py`, which refuses any file with a piercing, `UNKNOWN` or Doll material, and `dionys_render.py` (it needs `RENDER_POSES=<poses.json>`, because Blender's Python cannot import `male_check`; dump `male_check.POSES` to JSON first).

Import over the model the collection actually loads, and check by comparing cloth positions against the installed `.mdl` files: on the pilots the mod's model already held our last Doll import, so it matched that build 100% and the fresh export only 97%.

**Measured on the pilots:** weight copy cut bottoms running stretch 4.42% to 0.95%, thigh gap shrink in motion 5.8 to 0.8 mm, and matched `iv_` share exactly (10.17%). The old `Top0824_flat` FIT settings did nothing on Dionys (median chest gap 17.5 to 17.7 mm).

## Dionys AMAB bottoms (user-confirmed 2026-11-12, Trigun e6175)

- Dionys bottoms are AMAB. Check each new export is the mod's AMAB option (it usually has a crotch bulge pouch); tell the user if it is AFAB.
- Keep the creator's AMAB skin and the bulge pouch. Never flatten it with `crotch_pull`. The user's accepted fix lowered the crotch gusset (mesh 1.0, up to 24 mm straight down, fading to 0 by h 0.92 front, |x| < 0.10), giving about 3 cm of room under the bulge.
- UNCONFIRMED (contradicted 2026-11-12: the user's version showed no holes with the original texture): skin spots that appear only when the camera zooms out may be alpha-test holes (normal map blue channel on character.shpk, threshold 0.5) whose lower mips turn into solid holes, not clearance. Check the masks before raising clearance; 5/7/9 mm did nothing on e6175.
- A glb exported from Penumbra and re-imported loses the model's `atr_*` attributes, which breaks attribute toggles in the mod (belt, chains, straps, knee/shin skin). Restore them from the creator mdl when delivering.
- When a mod ships its own Dionys option, keep the CREATOR'S skin in the bottoms model instead of swapping in builds/_dionys/dionys_dwn.glb. On e6175 our swapped skin made two skin spots show at the hips (user A/B test 2026-11-12); the creator skin did not.
- Dionys reference bodies are the user's in-game exports in builds/_dionys/ingame/ (ingame_top/glv/dwn/sho.glb), not the devkit-based builds/_dionys/dionys_*.glb. Strip non-skin extras (pubes, underwear) from ingame_dwn before use.
