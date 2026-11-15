# Fitting outfits to bodies: process and procedures (summary, 2026-11-09, amended after review)

A one-file summary of how XIVAutoFit fits FFXIV outfits onto custom bodies. It covers Doll Body 2 (female), HR3 Chubby (male, Roegadyn and Midlander) and Dionys 1.4.0 (female, AFAB doll legs, no piercings).

**Sources.** The master thread wrote it from `tools/SKILL.md`, `tools/HANDOFF.md`, `builds/_male/RECIPE.txt`, `builds/_male/hr3_study_findings.md`, `builds/_male/hr3_study_review.md` and `builds/_dionys/dionys_study_findings.md`. Where this file and those disagree, those files are the source.

**Amendments.** It was amended on 2026-11-09 after an adversarial review (`builds/_review/fitting_process_review.md`); findings are cited as (F1)…(F11). Rules marked **(rule only)** are not yet enforced by the scripts; section 9 lists the script changes still owed.

**Almost nothing below has been confirmed in game.** The user tests in game, and Claude never does.

## 1. The goal and the parts

An outfit `.mdl` that covers a body slot replaces the body mesh under it. So the outfit must carry the right skin (and, for Doll Body 2, the metallic joints). Its cloth must also sit outside that skin in every pose, with no visible gaps, tears or skin poking through.

**How the scripts run** (F7):
- The Blender scripts run headless (`blender -b -P <script>`).
- `male_fit.py`, `male_exposed.py` and `dionys_exposed.py` are plain `python3` and need no Blender.
- Male work runs from `builds/_male/` and calls `../../tools/<script>`.

**Pipeline:**

1. **Export** the outfit `.mdl` from Penumbra (mod > Advanced Editing > Models > Export to glTF).
   - Use the original mod export every time, never a Meddle export. Meddle uses the character's own skeleton scale, which is 4-8% off.
   - **Snapshot every export** into `builds/<body>/export_<outfit>/` before using it. Exports in `~/Downloads` get overwritten by later exports; this already made the Thunderdome recipes impossible to rerun (`HANDOFF.md:204`). (F7)
2. **Inspect** with `list_meshes.py`.
   - Meshes are named `mesh M.S`, with one material per group M. Attributes are in the node extras.
   - Check every group whose material is `UNKNOWN`: it is skin on some outfits and cloth on others (see section 5).
3. **Body swap** with `transplant_body.py`.
   - It drops the outfit's old skin by material (`DROPMAT`) and adds the target body's skin. It also adds the Doll joints with `JOINTMAT=DOLL`; use `NOJOINTS=1` for Dionys and HR3.
   - It copies materials and attributes. `BODY2` adds a second body part (legs, feet).
   - **Give every body and reference path as an absolute path.** Relative paths are resolved against `EXPORTDIR`. That defaults to `~/Documents/Meddle`, which holds an old Golem top (`transplant_body.py:5,9`). (F7)
4. **Fit** the cloth to the new skin:
   - female bodies: `fit_to_ref.py` pushes cloth out of the skin to a clearance, smooths it, and moves nearby layers together;
   - male HR3: `male_fit.py` with env options (section 5).
5. **Chest flatten** tops on a flat chest (Doll Body 2): `chest_flat.py`, then often a second `fit_to_ref.py`. Dionys does not chest-flatten by default (section 5).
6. **Weights**: copy skin bone weights onto nearby cloth (`MFWSYNC`, `MFWSYNCSAFE`, `dionys_weights.py`), following the weight rules in section 3.
   - `transplant_body.py`'s `WSYNC` is different. It copies **cloth weights onto the skin and joints**, with no distance cap and no limb filter (`transplant_body.py:244,272-287`).
   - Use `WSYNC` only for the Doll-joint case it was made for (`WSYNC=1 WSYNCJ=1`, joints only). (F5)
7. **Score and look** (section 4): exposed-skin area (`male_exposed.py`, `dionys_exposed.py`) over simulated poses, the extra checks in section 4, and renders. (F10)
   - `render_views.py` renders the rest pose only, with cyan skin only when given a 5th argument.
   - `dionys_render.py` renders poses.
   - `render_male.py` renders the rest pose only, with tan skin.
8. **Deliver**: copy the final `.glb` to the outfit's `done*/` folder with a hash. The user imports it in Penumbra. (F9)
   - **Score the delivered file itself**, not an intermediate. Boots0507 was scored on the `_wt` file instead (`HANDOFF.md:255`).

## 2. Hard rules

- **Import** through Penumbra's importer only, with **Keep current attributes OFF** and **Keep current materials OFF**.
  - Back up the mod first.
  - Reload Mods before editing a mod.
- **Import target**: the `.mdl` the collection actually loads. (F9)
  - Check it by comparing cloth positions against the installed `.mdl` files. On the Dionys pilots, the mod already held our last Doll import.
  - If a target was not checked, report it as "target unverified". The Dionys batch targets still are (`HANDOFF.md:234`).
- **After every import**, hash every `.mdl` the mod option holds and compare with the backup. Only the intended file may have changed. One import already landed on the wrong two models (`HANDOFF.md:185`). (F9)
- **Race paths**: the game loads by displayed race (`c0201` Midlander female, `c0101` Midlander male, `c0901` Roegadyn male).
  - Penumbra swaps by path, so a mod needs an entry for each race path. The EQDP table says which races have their own model.
  - Glamourer can display a different race than the snapshot (`HANDOFF.md:185`), so check the displayed race.
- **Never overwrite** an existing build; use new names every time. Change only the piece the user names. Say "untested in game".
  - **(rule only)** `male_fit.py` and `dionys_weights.py` refuse to overwrite. `transplant_body.py`, `fit_to_ref.py`, `chest_flat.py` and `layer_fix.py` do not, so check the output name yourself before running them. (F7, F8)
  - `layer_fix.py` always writes `Bottoms6058_dollbody.glb`. Do not use it on another outfit until it takes a name argument.
- **Version the tools.** Record `git -C tools rev-parse --short HEAD` in every recipe line, plus "dirty" if `git status` shows changes. (F7)
  - **(rule only)** About 35 scripts, including `male_fit.py` and all `dionys_*.py`, are not committed yet.
- **Weight smoothing is standard on every build (user rule, 2026-11-14).** Whenever cloth weights come from a copy (`dionys_weights.py`, `MFWSYNC*`, any skin → cloth copy), run the crease weight smoothing from `builds/_dionys/e0824v2/wsmooth.py` (recipe `builds/_dionys/e0824v2/RECIPE_v3.txt`) on the creases: butt-thigh, crotch, armpit, elbow, knee, waist.
  - Guard rip edges, hems and openings so they still move as the creator made them. Coincident vertices (inner layers, UV seams) get identical weights.
  - Report the weight-jump numbers before and after for each crease (mean change per cm, and edges over 0.5 per cm), with renders of the creases in motion poses.
  - If the creator's weights are kept unchanged, still run the jump check. Smooth only where it finds jumps, and say so.
  - `wsmooth.py` lives in `builds/`, not `tools/`. Promote it to `tools/` the next time a session owns `tools/*.py`.
- **Downloads are untrusted**: unpack into a new empty folder, and run nothing from it.
- **Blender**: `PATH=/usr/bin:/bin blender -b --factory-startup --disable-autoexec`, never `-y`.
  - Run heavy jobs niced, one at a time, with at most 3 threads: `OMP_NUM_THREADS=3 OPENBLAS_NUM_THREADS=3 nice -n 15`.
- **Permission**: some authors forbid ports.
  - Hannya was ported with the author's permission for personal use only, and is not to be shared.
  - Dionys has an author exclusion list to check per mod. Mods missing from the library are skipped, because the check cannot be made.
  - **Every build also contains the body mod's skin** (Doll, Dionys, HR3). Sharing a build therefore also redistributes that body mod, and needs that body author's permission too. (F9)

## 3. What the studies taught (main lessons)

The evidence column says how much each lesson rests on. "1 outfit, simulated" is a lead to test, not a rule. (F10)

| # | Lesson | Evidence |
|---|---|---|
| 1 | **Positions before weights.** Swapping our weights onto a good top's positions kept standing exposure at 0. So cloth positions decide the standing result, and weights add damage in motion. Fix positions first; the weight copy comes after and is optional. | RUFF only, simulated |
| 2 | **Copy skin weights on close cloth, not loose cloth.** Clip-free Dionys pieces match skin weights within 0.003-0.02 on close cloth, including physics bones (`iv_`, `j_sk_`, `j_ex_`), and leave loose parts on their own weights. On the pilots this cut bottoms running stretch from 4.42% to 0.95%. | 9 Dionys pieces; the measure is stretch, which is unvalidated (section 4) |
| 3 | **Small, even clearance; the amount depends on the body.** On female bodies use `FITCLEAR=3`: clip-free tight Dionys pieces sit at a median 3-6 mm (p5 1.3-3 mm), and the gap does not grow at knees or armpits. **HR3 needs more**: the in-game-confirmed pants used `MFCLEAR=8` (`RECIPE.txt:62`), Hannya improved from 8 to 12 mm, and e6066 v8 used 12 mm. Raising clearance alone does not fix exposure through coarse triangles. | Female: 9 Dionys pieces. Male: 1 in-game, 2 simulated |
| 4 | **Cap how far cloth moves.** The user has twice rejected cloth moved far off the body. `MFFINISHMAX` caps the finish step. The main push in `male_fit.py` is still uncapped: 11 RUFF hem vertices moved over 30 mm, max 145.6. | 2 user rejections |
| 5 | **Dense rays for coarse triangles: try only in the finish step and only on outward cloth** (`MFDENSEPOKE`). They helped RUFF. They changed nothing on Hannya, and in the main push or on layered outfits they made things worse. | RUFF helped, Hannya did not |
| 6 | **Fix crossed layers per surface**, against each surface's own nearest skin (`MFUNCROSS`). A version without that rule swapped a sleeve and the torso. | RUFF and Hannya, simulated |
| 7 | **Start from the original export**, not from an earlier body's build, so one body's pushes don't carry over. Edits made only in a Doll build (e0810 open cuffs, e0553 armband removed, e6083 lace lift) must be repeated by hand per outfit. | Recorded cases |
| 8 | **Find which body an export already uses by measuring its skin against the devkit**, never by file name. A match is 0.00 mm median and p95; other bodies differ by 1.2 mm or more. | Dionys pilots |
| 9 | **Move cloth rather than delete skin.** Removing hidden skin is technically optional (6 of 9 clip-free Dionys pieces remove it), but the user prefers moving cloth. On e6120 v7, `MFCULLCOVER` left a hole visible at the front waist (`RECIPE.txt:60`). Delete skin only when the user asks. | User preference plus 1 in-game result |

**Weight rules** (F2, F5):
- **The weight source must be the skin the game draws.** `MFWSYNC` copies from `HR3BODY`, not from `SKINMDL` (`male_fit.py:662,708`), and `HR3BODY` defaults to Chubby + **Underwear SFW** legs.
  - Whenever `SKINMDL` names another legs option (for example Flaccid M), set `HR3BODY=<top.mdl>,<same legs .mdl as SKINMDL>`.
  - Otherwise the cloth follows a body the game does not draw.
- **Never copy across limbs.** On HR3, `MFWSYNCX=0` (copy at all heights and widths) is allowed only together with `MFWSYNCSAFE=1`.
  - Without it, the copy takes the nearest skin on any limb; the tool itself says "hips get worse" (`male_fit.py:11`, `:511`).
- **Watch the limb boundary.** `dionys_weights.py` copies or skips each vertex with a hard switch (`:108`) and keeps only 4 bones (`:25`).
  - So at the crotch and armpits, neighbouring vertices can end up on different weights. Check those regions in the posed renders.

## 4. How a build is judged

- **Primary score**: exposed skin area in cm² over simulated poses.
  - Tops: stand, bend, twist, arms up, arms forward.
  - Bottoms: stand, walk, run, lunge, squat, sit.
- **Reference ranges** come from clip-free **female Dionys** pieces: about 0-16 cm² standing, up to 67 in a deep sit. (F10)
  - There is no male reference range yet. Compare a male build against the original outfit on its original body.
- **What the exposed score cannot see** (F3, `male_exposed.py:117-125`). A point counts only when cloth lies up to 15 mm behind the skin. So:
  - a **gap or tear** with no cloth behind it scores 0 (Dwn6045 scored 0 with a crotch gap);
  - **missing skin** scores *better*, because there is less skin to expose (pants v3 had a hole and scored lower than v8);
  - skin **more than 15 mm through** the cloth is not counted (the Thunderdome wrap tips were 15.8 mm in);
  - any triangle counts as cover, even one facing inward;
  - **Doll joints are not scored**: `dionys_exposed.py` refuses Doll files, and `fitcheck.py` measures the rest pose only.
- **Required extra checks** cover those blind spots. Until scripts exist for them, do them by render and measurement, and say in the report how each was done.
  1. **Skin completeness.** The drawn skin must cover the same regions as the full body piece for that slot. Look for holes, especially from the hips to the upper thigh on Underwear SFW (`HANDOFF.md:187`).
  2. **See-through.** Render the posed build (walk, run, squat, sit) over a contrasting background. Background showing through the cloth is a gap.
  3. **Deep pokes.** Also run the score with `XPREACH=0.03`. Points that appear only at the larger reach are pokes deeper than 15 mm.
  4. **Doll joints.** In posed renders, count joints showing through cloth as exposure.
  5. **Crotch centre line.** Below the hip line, both fit tools split left and right at x=0: `fit_to_ref.py:125,146` below `FITSPLITZ`, and `male_fit.py:125,171,251` below `MFHIPY` (1.12 m). After every bottoms fit, check the centre seam for creases, sinking or gaps. (F6)
- **Diagnostics, not pass/fail**: poke counts, crossed-layer counts and edge stretch. Clip-free pieces can show large values on these (up to 2,722 pokes, 3,523 crossed layers, 5.57% stretch). (F4)
  - The pants v3/v8 pair does **not** show that stretch is useless. Their cloth was nearly the same (median 1.4 mm apart); the difference was in the skin. So stretch is unvalidated, not refuted.
  - Report stretch per region (crotch, hips, armpits), and look at any region clearly worse than the original outfit.
- **Always render.** Scores cannot see slits at cuffs and hems, a cape notch, or a design meant to show skin.
- **Check where a bad score sits before acting.**
  - 263-264 cm² above 1.2 m on leg models is the top cap of the leg skin, hidden by the jacket.
  - The male score splits at `XPWAIST` (1.30 m), so look at the waist seam in renders too.
- **Test any change on a second outfit**, to avoid overfitting to one.
- **Physics.** The e6120 pants tests were run with physics off (`hr3_study_findings.md:209`). Until the user tests with physics on, treat `iv_` weight changes (`MFSKINNOIV`) as unconfirmed for physics-on play. (F11)
- The user's screenshots outrank every measurement.

## 5. Per body: recipes in use

In every recipe, write every path as an absolute path and record the tools commit (section 2).

### Doll Body 2 (female, joints)

- **Body swap**: `DROPMAT=bibo JOINTMAT=DOLL EXPORTDIR=<exports>`.
  - Tops use the Doll top, and bottoms use the Doll dwn.
  - Full bodies also take `BODY2=<abs path to dwn> NIP=1`.
- **Fit**: `FITCLEAR=2-3 FITR=15 FITDEEP=12 FITPASSES=4 FITSIGMA=6 FITSMOOTH=2`, with `FITSPLITZ=0` for tops or `0.84` for bottoms.
  - Tops also took `FITZMIN=1.0` in recorded runs (`HANDOFF.md:75`).
  - Coarse cloth may need `FITPOKE`/`FITPOKEZ` (`SKILL.md:107`).
- **Chest flatten check** on every top (`chest_flat.py`): flatten if the `min` gap is above about 5 mm at z 1.20-1.34.
- **Layered garments**: `layer_fix.py`, only on Bottoms6058 until it takes file names (section 2).
- **Boots over pants**: fit to the pants as the reference.
- **Joints poking through cloth in poses**: `WSYNC=1 WSYNCJ=1` with a z band (`SKILL.md:97`). Check the result in posed renders (section 4).

### HR3 Chubby (male)

Run `male_fit.py` from `builds/_male/`, always with `HR3BODY` matching `SKINMDL` (section 3).

- **Bottoms (reference recipe)**: e6120 pants v8 (build v18, `RECIPE.txt:62`). This is the only HR3 recipe confirmed in game.
  ```
  MFSKINNOIV=1 MFCLEARBODY="$HTOP,$HFM" MFDROPBONES=iv_ochinko,iv_kougan,iv_funyachin,iv_kintama MFFINISH=3 MFWSYNC=45 MFWSYNCX=0 MFPOKE=30 MFPOKEY=0.42,1.12 MFPASSES=9 MFFUR=30 MFCLEAR=8 SKINMDL="$HFM"
  ```
  - For new builds, add `MFWSYNCSAFE=1` (because `MFWSYNCX=0` is used, section 3) and `HR3BODY="$HTOP,$HFM"`.
  - v8 itself ran without those two, so a build with them is a new, untested variant.
- **Tops (simulated only, on RUFF and Hannya)**: `MFWSYNC=60 SKINMDL=...` plus:
  - close single-layer top: `MFFINISH=3 MFFINISHMAX=15 MFDENSEPOKE=6 MFUNCROSS=2`, and `MFCLEAR=5` or more;
  - layered or caped outfit: the same, without `MFDENSEPOKE`;
  - tight top (torso median gap under about 10 mm): also `MFWSYNCX=0 MFWSYNCSAFE=1`, after positions.
- **Measuring a top**: measure it against the torso alone, because the pants' waist skin overlaps it (`tbse-to-hr3.md:42`).

### Dionys 1.4.0 (female, no joints)

- **Body**: `tools/dionys_body.py` builds it.
- **Body swap**: `transplant_body.py` with `DROPMAT=bibo JOINTMAT=NOJOINTMATERIAL NOJOINTS=1`, from the original export, using absolute paths to `builds/_dionys/dionys_{top,dwn}.glb`. (F9)
  - Add `UNKNOWN` to `DROPMAT` **only after `list_meshes.py` shows the `UNKNOWN` group is the Bibo skin**.
  - It was cloth in e0511 group 3 and e6108 groups 1-6 (`HANDOFF.md:242`). Name such groups with `GROUPMAT` instead.
- **Fit**: `fit_to_ref.py` at `FITCLEAR=3` with the standard values above, then `dionys_weights.py`.
- **Check**: `dionys_exposed.py` (it refuses files with piercing, `UNKNOWN` or Doll material) and `dionys_render.py` (`RENDER_POSES=<poses.json>`).
- **Chest flatten**: none by default. The batch ran without it ("lumpy cups; user-approved choice", `HANDOFF.md:232`).
  - If the user asks for one, use `builds/_dionys/chest_flat_dionys.py` with `CFFIELD=1 CFWRAP=<export>`, then a second fit.
  - That script is not in `tools/` yet.
- **Boots**: add `BODY2=<abs>/builds/_dionys/dionys_dwn.glb` to the foot reference, then remove the leg skin from the output.
  - There is no kept script for the removal yet (section 9).
  - Score the file after the removal.

## 6. Session workflow

- One master thread delegates. It never runs Blender and is the only one that edits `tools/HANDOFF.md`.
- One nested worker session runs per outfit or script change, with `use_worktree: false` (because `builds/` is not in git).
- Only one session at a time edits `tools/*.py`.
- Each worker reports:
  - the recipe, with absolute paths and the tools commit;
  - the files and their hashes;
  - which section-4 extra checks were done, and how;
  - "untested in game".
- The master checks that the files exist and records the report.
- The user imports and tests. The master records the in-game result, including whether physics was on and whether the user moved (walk, run, sit).

## 7. Known open problems

- **e6120 TBSE Weaponsmith pants, done v3 (build v5)**: the one in-game tear on record ("cloth stretches or tears" in motion, plus "a hole"). It was not on Hannya (F1).
  - Likely cause: mostly the hole in the skin (Underwear SFW without its underwear mesh) showing as a void through cloth gaps. The same cloth later showed skin at the butt and belt (v6).
  - Fixed in v8 by full skin, clearance against the drawn skin and `MFSKINNOIV`.
  - Unconfirmed: whether the v6 and v7 tests included movement.
- **Hannya pants**: never imported, so untested. The simulated crotch stretch while running is 30.8x (`HANDOFF.md:218`).
- **RUFF top**: 32 cm² on the chest standing, against 0 on the custom reference. Slits at the cuffs and hem.
- **HR3 belly**: the offset is unexplained.
- **Simulated poses** are not game animation. `XPLAG=0.5` is a guess at the `n_hkata` twist share.
- **Hannya cape**: the notch is not fixed.
- **Crotch centre line**: the x=0 split in both fit tools is a likely contributor to the crotch problems (Dionys 3.9 mm under the skin, Hannya stretch, Dwn6045 gap). (F6)
- **Dionys**:
  - 7 bottoms vertices sit up to 3.9 mm under the skin at the crotch seam.
  - e6258 has no `c0201` model in the library.
  - Several size options and import targets are unconfirmed.
  - Boots0507 was scored before the leg skin was removed.

## 8. Inconsistencies in the sources (checked by the review)

- **Mod root**: `tools/SKILL.md:47` says `/run/media/SloppyMods/DATA/Penumbra`, while `tools/HANDOFF.md` and recent work use `/mnt/STORAGE/Penumbra`. The truth is `ModDirectory` in `penumbra.json`. Confirmed.
- **Old Process section**: the "Process" section of `tools/SKILL.md` describes the old `transplant.py` flow. Those exports were Penumbra exports in a folder named `~/Documents/Meddle/`, not Meddle exports. The live hazard is that `transplant_body.py` still defaults `EXPORTDIR` to that folder (section 1).
- **Keep current attributes**: `tools/SKILL.md:18` used ON only for one Meddle-derived file. That is history and does not conflict with the OFF rule.
- **Dionys chest flatten**: `tools/SKILL.md:172` includes it, but the batch ran without it, and running without it is now the default (section 5).
- **Boots0507 leg-skin removal**: it used a scratchpad script that was not kept, so it cannot be repeated as recorded. The delivered file was also never scored.

## 9. Script changes (status 2026-11-10)

Items 2-8 landed on 2026-11-10 (untested in game, not committed). With none of the new options set, every changed script gives the same output as before, byte for byte where a rerun was made; details and numbers in `builds/_review/process_fixes_report.md`. The "(rule only)" items above that match items 2, 3, 7 and 8 are now enforced by the scripts.

1. **Open, waits for the user:** commit `tools/`, then record the commit in each recipe.
2. **Done.** `transplant_body.py`, `fit_to_ref.py`, `chest_flat.py`, `layer_fix.py` refuse an existing output before loading anything. `layer_fix.py -- <6 numbers> [in.glb] [out.glb]` (bare names in `builds/`; still shaped for e6058, exits if `mesh 1.0`/`mesh 1.3` are missing). `male_fit.py` now also checks its output before fitting, not only at the end.
3. **Done (refuse, not a new weight source).** With `MFWSYNC` on, `male_fit.py` refuses when `SKINMDL` is a legs `_dwn.mdl` missing from `HR3BODY`, and refuses `MFWSYNCX=0` without `MFWSYNCSAFE=1`. `MFWSYNCLEGACY=1` turns both into warnings, only to rebuild a recorded recipe (it rebuilt v18 byte for byte). Recipes that now need it: `builds/_male/RECIPE.txt` lines 27, 29, 35, 47, 52, 57, 62, 66.
4. **Partly done:** an opt-in centre band, not a smooth blend. `FITMIDX=<mm>` (`fit_to_ref.py`, below `FITSPLITZ`) and `MFMIDX=<mm>` (`male_fit.py`, below `MFHIPY`): cloth within that distance of x=0 counts for both sides. Default 0 = the old hard split.
5. **Done, opt-in.** `dionys_weights.py`: `WSAMELIMB=1` copies from the nearest skin on the vertex's own limb instead of keeping its own weights, so the copy fades over WNEAR/WFAR rather than switching per vertex; `WBONES=<n>` bone limit (4), above 4 the export keeps all influences.
6. **Done, opt-in, extra numbers only.** `XPEXTRA=1` in `male_exposed.py` and `dionys_exposed.py` (code in `exposure_extra.py`) prints per pose: exposed area with only outward-facing cover, deep pokes (cloth behind deeper than XPREACH, up to XPDEEP 0.06 m), and skin covered at rest that one of 8 cameras sees in the pose; with `XPFULLBODY=<reference>` also reference skin missing from the build. `dionys_exposed.py XPDOLL=1` scores Doll Body 2 builds, Doll joints (XPJOINTMAT, DOLL) as skin. The existing exposed number is unchanged.
7. **Done.** `tools/chest_flat_dionys.py` (wrapper that runs `chest_flat.py` with the new `CFSKINMAT=/mt_c0201b0001_bibo.mtrl`; same arguments, `<in> <out|->`). `tools/strip_leg_skin.py -- <in> <out>` keeps only the skin meshes in `LSKEEP` (default `mesh 0.0`, the foot).
8. **Done.** `transplant_body.py` exits when `EXPORTDIR` is unset or empty and the outfit, body or `BODY2` path is relative. There is no `~/Documents/Meddle` fallback any more.
