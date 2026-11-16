"""Запускает скрипт пакета Qwen в Blender (фоном) и показывает отчёт.

    python run_qwen.py <путь к build_V1.py> [--res 1600] [--tex 512] [--no-preview]

Результат: out/<имя скрипта без build_>/ — FBX, tex/, preview.png, report.txt, .blend.
Строки REPORT/CHECK из report.txt отправляются Qwen обратно.
"""

import os
import subprocess
import sys

BLENDER = os.environ.get("CC_BLENDER", r"D:\blender.exe")
LIB = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(LIB)


def main():
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        return 1
    script = os.path.abspath(args[0])
    pack = os.path.splitext(os.path.basename(script))[0].replace("build_", "")
    out = os.path.join(ROOT, "out", pack)
    os.makedirs(out, exist_ok=True)
    env = dict(os.environ, CC_OUT=out, CC_SCRIPT=script, CC_LIB=LIB)
    if "--res" in args:
        env["CC_RES"] = args[args.index("--res") + 1]
    if "--tex" in args:
        env["CC_TEX"] = args[args.index("--tex") + 1]
    boot = os.path.join(LIB, "_boot.py")
    cmd = [BLENDER, "-b", "--factory-startup", "--python-exit-code", "1", "--python", boot]
    if "--no-preview" in args:
        env["CC_NO_PREVIEW"] = "1"
    proc = subprocess.run(cmd, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace")
    report = os.path.join(out, "report.txt")
    if os.path.exists(report) and os.path.getmtime(report) >= os.path.getmtime(script):
        print(open(report, encoding="utf-8").read())
    else:
        print("НЕТ ОТЧЁТА — скрипт упал. Хвост лога Blender:")
        print("\n".join((proc.stdout + proc.stderr).splitlines()[-40:]))
    return proc.returncode


if __name__ == "__main__":
    sys.exit(main())
