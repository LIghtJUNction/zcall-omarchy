#!/usr/bin/env python3
"""Run local checks. Native zcalld integration is opt-in via ZCALLD_TEST_BINARY."""
import ast
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
version = (ROOT / "VERSION").read_text().strip()
manifest = json.loads((ROOT / "manifest.json").read_text())
if not re.fullmatch(r"(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)", version):
    raise SystemExit("VERSION must be a numeric semantic version.")
if manifest["version"] != version or manifest["id"] != "lightjunction.zcall":
    raise SystemExit("Plugin manifest and VERSION are inconsistent.")
for directory in ("lib", "scripts", "tests"):
    for path in (ROOT / directory).rglob("*.py"):
        ast.parse(path.read_text(), filename=str(path))
subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"],
               cwd=ROOT, check=True)
validator = shutil.which("omarchy-plugin-validate")
if validator:
    subprocess.run([validator, str(ROOT)], cwd=ROOT, check=True)
else:
    print("Omarchy validator unavailable; validate on an installed Omarchy host before release.")
print("Source, version, controller and installation checks passed.")
