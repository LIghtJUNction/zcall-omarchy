#!/usr/bin/env python3
"""Load the real widget with installed Omarchy modules in an isolated shell."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SHELL = Path(os.environ.get("OMARCHY_PATH", "/usr/share/omarchy")) / "shell"
binary = shutil.which("quickshell")
if not binary or not (SHELL / "Ui/BarWidget.qml").is_file():
    raise SystemExit("Install Omarchy 4.5 and Quickshell for this integration check.")
with tempfile.TemporaryDirectory(prefix="zcall-omarchy-qml-") as directory:
    temporary = Path(directory)
    for name in ("Ui", "Commons"):
        (temporary / name).symlink_to(SHELL / name, target_is_directory=True)
    runtime = temporary / "runtime"
    runtime.mkdir(mode=0o700)
    source = json.dumps((ROOT / "BarWidget.qml").as_uri())
    (temporary / "shell.qml").write_text("""
import QtQuick
import Quickshell
ShellRoot {
  property var tested: null
  Component.onCompleted: {
    var component = Qt.createComponent(SOURCE)
    if (component.status !== Component.Ready) {
      console.error(component.errorString())
      Qt.exit(2)
      return
    }
    tested = component.createObject(null)
    if (!tested || tested.moduleName !== "lightjunction.zcall") {
      console.error("Zcall widget did not instantiate")
      Qt.exit(3)
    }
  }
  Timer {
    interval: 350
    running: true
    onTriggered: {
      if (!tested || tested.implicitWidth <= 0 || tested.implicitHeight <= 0) {
        console.error("Zcall widget has no usable dimensions")
        Qt.exit(4)
      } else {
        console.info("ZCALL_OMARCHY_WIDGET_READY")
        tested.destroy()
        Qt.quit()
      }
    }
  }
}
""".replace("SOURCE", source))
    environment = os.environ.copy()
    environment.update(HOME=str(temporary), XDG_CONFIG_HOME=str(temporary / ".config"),
                       XDG_STATE_HOME=str(temporary / ".local/state"),
                       XDG_CACHE_HOME=str(temporary / ".cache"),
                       XDG_RUNTIME_DIR=str(runtime), QT_QPA_PLATFORM="offscreen",
                       QT_QPA_PLATFORMTHEME="generic", QT_STYLE_OVERRIDE="Fusion",
                       QT_QUICK_BACKEND="software", OMARCHY_PATH=str(SHELL.parent))
    result = subprocess.run([binary, "--path", str(temporary), "--no-color"],
                            env=environment, capture_output=True, text=True, timeout=15)
    output = result.stdout + result.stderr
    if result.returncode or "ZCALL_OMARCHY_WIDGET_READY" not in output:
        raise SystemExit(output)
    print("Actual Omarchy BarWidget loaded with nonzero dimensions; isolated shell exited.")
