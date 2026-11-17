# Runs inside Blender: puts cc_kit on the path and executes the pack script.
import os
import runpy
import sys

sys.path.insert(0, os.environ["CC_LIB"])
import cc_kit  # noqa: E402

if os.environ.get("CC_NO_PREVIEW"):
    _run = cc_kit.run
    cc_kit.run = lambda pack, preview=True, textures=True, **kw: _run(pack, False, textures, **kw)
runpy.run_path(os.environ["CC_SCRIPT"], run_name="__main__")
