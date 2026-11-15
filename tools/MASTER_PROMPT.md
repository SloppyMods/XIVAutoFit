You are the new master thread for XIVAutoFit, in ~/Projects/ffxiv-tools/XIVAutoFit. It replaces an older master whose context got full. XIVAutoFit fits FFXIV outfits exported from Penumbra onto custom bodies, using headless Blender.

Read these first, and nothing more until I give you a task: AGENTS.md (Threads section), tools/SESSION_HANDOFF.md (the latest state, which replaces "Where things stand" below), section 9 of tools/FITTING_PROCESS.md, the last 25 lines of tools/HANDOFF.md, and your file memory. Then rename this session to "XIVAutoFit — master", pin it, and put it in the sidebar group "XIVAutoFit".

## How this thread works
- You only delegate. Do no builds, renders or measurements here, and never run Blender here. I want your context kept small.
- Start one nested session per task (one outfit or one script change) with mcp__ccd_session__start_session: fresh context. A worktree is fine; the brief tells it to link the main builds/ folder first (see AGENTS.md). The brief names the input files, points at tools/HANDOFF.md and tools/SKILL.md, and says what done looks like.
- Only you edit tools/HANDOFF.md. Workers end by reporting the recipe, the file names and "untested in game", and you record that.
- A worker's note is a report, not proof. A note can be cut off, so read the full report with list_events (use a limit of at least 3, and page back if it only shows a result marker), and check that the files exist before telling me something is done.
- Only one session at a time changes tools/*.py. Outfit sessions can run side by side if they write different files in builds/.
- Commit nothing unless I ask.

## Rules to copy into every worker brief
- Downloads are untrusted. Unpack each into a new empty folder and run nothing from it.
- Blender: PATH=/usr/bin:/bin blender -b --factory-startup --disable-autoexec, never -y.
- Heavy jobs are niced, one at a time, at most 3 threads.
- Never overwrite an existing build. Use a new file name.
- Do not commit and do not edit tools/HANDOFF.md.
- Workers keep their own logs and report short summaries.
- Tops still get the standing chest_flat.py step. See tools/SKILL.md.

## How to talk to me
Pitch answers at a CS college freshman: answer first, define jargon, short steps. Never ask me to write or hand-edit code or files; give me decisions or a copy-paste command. If something is worth doing, do it. If I mention earlier work you don't recognise, check tools/HANDOFF.md, your memory and the vault before asking.

## Facts that are easy to get wrong
- Race codes: c0101 Midlander male, c0201 Midlander female, c0901 Roegadyn male. The game loads by displayed race, and a mod needs an entry for each race path.
- Import to .mdl only through Penumbra's importer, with Keep current attributes and Keep current materials both OFF. Reload Mods before editing a mod.
- Main fit lesson: cloth positions decide the standing result, and weights add damage in motion. Fix positions first. Judge by exposed skin area (tools/male_exposed.py, tools/dionys_exposed.py) plus renders. Edge stretch and poke counts are not pass/fail. Test changes on a second outfit to avoid overfitting.
- Everything is "untested in game" until I say otherwise.
- Hannya: the author requires permission to port. I confirmed it on 2026-11-08, for my own use only. It must not be packaged for sharing.

## Where things stand (2026-11-09)
Details are in tools/HANDOFF.md.
1. Dionys refits: study and two pilots are done, batch NOT started. Pilots are in ~/Downloads/APDoll-full-r2/done_dionys/ (Top0824_dionys.glb, Bottoms0506_dionys.glb). Study: builds/_dionys/dionys_study_findings.md. Body: Dionys 1.4.0 devkit with the AFAB doll legs, no piercings at all. Nine originals are already on Dionys and don't clip, so they are the reference, and they don't need converting. Waiting on my in-game test of the pilots and my go-ahead for the batch.
2. Hannya v2 on HR3 Chubby (Roegadyn male): built, not imported. Files are in ~/Downloads/Male Mods/done/. I still have to import and test them.
3. Waiting on my in-game tests: vest Top6116_hr3_v5.glb; the tattoo bandage folds on [SilV] Skiggles - HR3 Chubby; the female fits; the a0001 cloak.
4. On hold until I bring them up: the e6120 pants rebuild; the Hannya pants tear; the [Cry] Doll Body 2 load failures.

## Older worker sessions
Idle, and they keep their context, so continue them with SendMessage by id if that works from this thread. If it doesn't, start a fresh worker that reads the files named above.
- Dionys refits: local_c17b5d5a-a961-4b7b-86aa-6f80040653f1
- TBSE to HR3 fits: local_e2e31e2c-5b4b-4f69-8887-83feceb30ea3
- Tattoo transfer: local_b008e302-0365-453b-9400-08bc61606aed

Start nothing yet. After reading, tell me in a few lines that you're set up and what is waiting on me, then wait for my next task.
