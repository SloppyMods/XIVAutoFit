"""chest_flat.py for Dionys builds: the same tool with the Dionys skin material (`/mt_c0201b0001_bibo.mtrl`).

    PATH=/usr/bin:/bin blender -b --factory-startup --disable-autoexec -P chest_flat_dionys.py -- <in.glb> <out.glb|-> [clearance_mm] [maxpull_mm]

Arguments and every CF* option are chest_flat.py's (the Dionys batch uses CFFIELD=1 CFWRAP=<export>). Replaces
builds/_dionys/chest_flat_dionys.py, a sed copy that differed in that one material name. Refuses to overwrite an existing output.
"""
import os
import runpy
from pathlib import Path

os.environ.setdefault("CFSKINMAT", "/mt_c0201b0001_bibo.mtrl")
runpy.run_path(str(Path(__file__).resolve().parent / "chest_flat.py"), run_name="__main__")
