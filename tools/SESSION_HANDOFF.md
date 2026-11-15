# XIVAutoFit master handoff (2026-11-10)

State when the old master handed over. Rules are in `tools/MASTER_PROMPT.md`. The per-outfit record is in `tools/HANDOFF.md`. The process is described in `tools/FITTING_PROCESS.md`. Nothing below is tested in game, and nothing is committed.

## What happened since 2026-11-09

1. **Dionys batch built.** 25 files are in `~/Downloads/APDoll-full-r2/done_dionys/`, recorded in `tools/HANDOFF.md` ("Dionys batch" sections). Still to do:
   - **Import targets:** most are unverified against installed mods. Unknown size options: Top6120, Dwn6175, Dwn6187, the e6066 pair; two mods ship e0256; e6258 has no `c0201` model.
   - **Look at in game first:** Dwn0052 (157 cm² sitting), Dwn6045 (bare patches despite a score of 0), the Dwn6141 and Dwn6258 hip patches, and Top0753 (17k crossed layers).
   - **Skipped by the user:** e0453, e0553, e0799, e6058, e6153, e6159, e0634, e0707, e9102 (not in the library, so the author check can't be done).
2. **Process written up and attacked.**
   - `tools/FITTING_PROCESS.md` is the one-file process summary. The review session later amended it with every finding and added section 9.
   - A read-only adversarial Fable review is in `builds/_review/fitting_process_review.md`, with 11 findings.
   - Top points:
     - The only in-game tear was on the e6120 pants, not Hannya. Hannya has never been imported.
     - HR3 weights came from a different legs body than the drawn skin.
     - The exposed-area score can't see tears, missing skin, deep pokes or Doll joints.
     - The scripts aren't in git, so builds can't be tied to a code version.
     - Several lessons rest on one outfit.
3. **Script fixes applied (section 9, items 2-8).** Done by session `local_5a92cf80-ba7d-421e-8fe1-703d5bd95e79`, checked by the master against a pre-change snapshot (`/tmp/claude-1000/-home-SloppyMods-Projects-ffxiv-tools-XIVAutoFit/a7970443-7a3c-41a9-a512-26810ef6338b/scratchpad/tools_before/`, temporary).
   - **Changed:** `transplant_body.py`, `fit_to_ref.py`, `chest_flat.py`, `layer_fix.py`, `male_fit.py`, `dionys_weights.py`, `male_exposed.py`, `dionys_exposed.py`.
   - **New:** `exposure_extra.py`, `chest_flat_dionys.py`, `strip_leg_skin.py`. All compile.
   - **New options**, all off by default (spot-checked):
     - `FITMIDX` and `MFMIDX`: centre band at x=0.
     - `WSAMELIMB` and `WBONES`: Dionys weight copy.
     - `XPEXTRA`, `XPFULLBODY` and `XPDOLL`: extra exposure numbers.
   - **Reproducibility:**
     - The Hannya pants rebuilt byte-identical.
     - The in-game-confirmed v18 pants rebuild byte-identical with `MFWSYNCLEGACY=1`.
   - **New refusals:**
     - Existing outputs are never overwritten.
     - A missing `EXPORTDIR` with relative paths stops the run.
     - `male_fit.py` refuses mismatched `SKINMDL`/`HR3BODY` legs, and `MFWSYNCX=0` without `MFWSYNCSAFE=1`.
     - Old recipes at `builds/_male/RECIPE.txt` lines 27, 29, 35, 47, 52, 57, 62 and 66 now need `MFWSYNCLEGACY=1` to rerun.
   - **Measured:** `MFMIDX=5` on the Hannya pants moved 95 of 1,479 vertices (max 19.2 mm), cut crotch-seam stretch from 1.79x to 1.53x, and left 0 vertices under the skin.
   - **Item 4 is only partly done:** a centre band, not a smooth blend.
   - **Item 1 (commit `tools/`) is open** and waits for the user.
   - Per-item numbers: `builds/_review/process_fixes_report.md`. Byte-identical reruns with no options set: Hannya pants, Top6083b, Top0824 weights, the Dionys chest-flatten wrapper, `strip_leg_skin.py` vs the delivered Boots0507, and v18 with `MFWSYNCLEGACY=1`; exposure scripts print identical text. `WSAMELIMB=1 WBONES=8` on Top0824: 50 more boundary vertices take skin weights. **Item 6 numbers (`XPEXTRA=1`) were still running at handover**; ask session `local_5a92cf80-ba7d-421e-8fe1-703d5bd95e79` for them.
4. **Open Brain removed** from the user's Claude setup (2026-11-10): the session-start search, the plugin entry, and both `~/.claude/hooks` scripts. OpenViking is the only vault now. Backup: `~/.claude/settings.json.bak-openbrain-2026-11-09`.

## Lessons for the master

- **Duplicate worker:** two sessions were once started for the same script fixes, one by the master and one by the review session. Before starting a session that edits `tools/*.py`, check `list_sessions` for one already doing it, and tell child sessions not to start their own workers.
- **Stopping sessions:** the master is not allowed to stop sessions (`stop_session` is blocked). Use SendMessage to tell a worker to stand down, or ask the user to press Stop.
- **Notes are not proof:** a worker's note can say "finished" while a background job is still running. Check the files and running processes before reporting.

## Waiting on the user

- Commit `tools/` (item 1): yes or no.
- Whether to turn any new opt-in option on by default, after seeing `process_fixes_report.md`.
- In-game tests: Dionys batch, Hannya v2 (not imported), vest `Top6116_hr3_v5.glb`, tattoo bandage folds, female fits, the a0001 cloak.
- Open question from the review: did the e6120 pants v6/v7 tests include walking or running?
- On hold: e6120 pants rebuild, `[Cry] Doll Body 2` load failures.

## Sessions (idle)

| name | id | what |
|---|---|---|
| script-fixes-owed-by-fit | `local_5a92cf80-ba7d-421e-8fe1-703d5bd95e79` | applied the section 9 fixes; wrote the report; item 6 numbers pending |
| process-review | `local_de0328d8-9c5c-4061-acb9-5a72788b1e73` | the read-only review; started the fix session |
| process-fixes | `local_e1726ba3-6416-4fae-b214-d229c3478dcc` | stood down, edited nothing; made the pre-change snapshot |
| dionys-refits | `local_c17b5d5a-a961-4b7b-86aa-6f80040653f1` | Dionys study and pilots |
| tbse-to-hr3 | `local_e2e31e2c-5b4b-4f69-8887-83feceb30ea3` | male HR3 fits |
| tattoo-tbse-to-hr3 | `local_b008e302-0365-453b-9400-08bc61606aed` | tattoo transfer |

A newer master thread may also exist (started from `tools/MASTER_PROMPT.md` on 2026-11-09). It ran the Dionys batch with its own workers (team `xivautofit-dionys`).
