# CLEANING CREW — Qwen art kit

Public kit for the AI 3D artist of the Roblox game CLEANING CREW (Dark Realism style).
Only art tooling lives here: no game code.

| File | What |
|---|---|
| `QWEN_PROMPT.md` | the task: workflow, token rules, `cc_kit` API, technical standard, style, quality bar, packs V1–V7 |
| `lib/cc_kit.py` | Blender 5.2 library: shapes, materials, procedural PBR, checks, FBX export, preview, per-asset close-ups |
| `lib/EXAMPLE_build_quality.py` | the quality reference (dumpster, lamp post) |
| `lib/run_qwen.py`, `RUN.bat` | run a pack script in headless Blender: `python lib/run_qwen.py out/build_V1.py` |
| `refs/` | style references and the reference close-ups |
| `FIRST_MESSAGE.md` | the whole first message to paste into Qwen (prompt + example + V1 task) |
| `NEXT_MESSAGES.md` | templates for report / fixes / next pack |
| `packs/` | detailed pack specs (V1 …) |
| `HOW_TO.md` | the owner's step-by-step (Russian) |

Units: 1 Blender unit = 1 Roblox stud, Z up, front faces -Y, pivot at the bottom centre.
