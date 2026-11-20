#!/usr/bin/env python3
"""Exercise installed Omarchy popup APIs with a disposable offline backend."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SHELL = Path(os.environ.get("OMARCHY_PATH", "/usr/share/omarchy")) / "shell"
binary = shutil.which("quickshell")
if not binary or not (SHELL / "Ui/BarWidget.qml").is_file():
    raise SystemExit("Install Omarchy 4.5 and Quickshell for this integration check.")
display = os.environ.get("WAYLAND_DISPLAY", "")
base = os.environ.get("XDG_RUNTIME_DIR", "/run/user/" + str(os.getuid()))
display_path = Path(display) if display.startswith("/") else Path(base) / display
if not display or not display_path.exists():
    raise SystemExit("An active Wayland display is required for the native popup check.")

QML = r'''
import QtQuick
import QtTest
import Quickshell
import qs.Ui as Ui
ShellRoot {
  id: harness
  property var tested: null
  property var popup: null
  property int stage: 0
  property int ticks: 0
  property int edgeIndex: 0
  property string edge: ["top", "bottom", "left", "right"][edgeIndex]
  property bool vertical: edge === "left" || edge === "right"
  function find(node, name) {
    if (node.objectName === name) return node
    if (node.children) for (var i = 0; i < node.children.length; i++) {
      var match = find(node.children[i], name)
      if (match) return match
    }
    return null
  }
  function focused(node) {
    if (node.activeFocus) return true
    if (node.children) for (var i = 0; i < node.children.length; i++) if (focused(node.children[i])) return true
    return false
  }
  function tabTo(node) {
    for (var i = 0; i < 35 && !focused(node); i++) keyboard.keyClick(Qt.Key_Tab)
    if (!focused(node)) fail("keyboard cannot reach native selector")
  }
  function activate(node) {
    if (!node || !node.visible || !node.enabled) { fail("action control unavailable"); return }
    node.forceActiveFocus()
    keyboard.keyClick(Qt.Key_Return)
  }
  function fail(message) { console.error("POPUP_CHECK: " + message); Qt.exit(2) }
  Ui.PluginBarApi {
    id: api
    pluginId: "lightjunction.zcall"; moduleName: pluginId
    position: harness.edge; vertical: harness.vertical; barSize: 48
    _requestPopout: function(owner) {
      if (owner !== harness.tested) harness.fail("coordinator owner must be the host widget")
      activePopout = owner
    }
    _releasePopout: function(owner) { if (activePopout === owner) activePopout = null }
    _moduleWidgets: function(id) { return [harness.tested] }
  }
  PanelWindow {
    id: strip
    screen: Quickshell.screens[0]; color: "transparent"
    exclusionMode: ExclusionMode.Ignore
    anchors.top: harness.edge === "top" || harness.vertical
    anchors.bottom: harness.edge === "bottom" || harness.vertical
    anchors.left: harness.edge === "left" || !harness.vertical
    anchors.right: harness.edge === "right" || !harness.vertical
    implicitWidth: 48; implicitHeight: 48
  }
  TestCase { id: keyboard; when: false }
  Component.onCompleted: {
    var component = Qt.createComponent(SOURCE)
    if (component.status !== Component.Ready) { fail(component.errorString()); return }
    tested = component.createObject(strip.contentItem, {bar: api, settings: {language: "en"}})
    if (!tested || typeof tested.open !== "function" || typeof tested.close !== "function" || tested.opened !== false) {
      fail("host open/close/opened interface missing"); return
    }
    tested.width = tested.implicitWidth; tested.height = tested.implicitHeight
    tested.x = Qt.binding(function() { return harness.vertical ? 0 : strip.width - tested.width })
    tested.y = Qt.binding(function() { return harness.vertical ? strip.height - tested.height : 0 })
    tested.gatewayPanel.dataSource.entryPath = BACKEND
    for (var i = 0; i < tested.gatewayPanel.data.length; i++) {
      var child = tested.gatewayPanel.data[i]
      if ("cardTarget" in child) popup = child
    }
    if (!popup || popup.coordinatorKey !== tested || tested.gatewayPanel.manageIpc)
      fail("popup must use the top-level owner and focused-screen host IPC")
  }
  Timer {
    interval: 100; repeat: true; running: true
    onTriggered: {
      if (++harness.ticks > 100) { harness.fail("native popup timed out at stage " + harness.stage); return }
      var widget = harness.tested
      if (!widget || !harness.popup) return
      var source = widget.gatewayPanel.dataSource
      var view = widget.gatewayPanel.loadedContent
      if (harness.stage === 0) {
        if (source.busy || source.snapshot || view) { harness.fail("closed panel read or eagerly loaded content"); return }
        widget.open(); harness.stage = 1
      } else if (harness.stage === 1) {
        if (!view || source.busy || !source.snapshot || !view.activeFocus) return
        keyboard.parent = view
        var rect = harness.popup.cardTarget
        if (!widget.opened || rect.width <= 0 || rect.height <= 0 || rect.x < -1 || rect.y < -1
            || rect.x + rect.width > harness.popup.width + 1 || rect.y + rect.height > harness.popup.height + 1) {
          harness.fail("popup escaped the screen on " + harness.edge); return
        }
        if (api.activePopout !== widget || harness.popup.screen !== strip.screen) {
          harness.fail("popup lost the anchor screen or host owner"); return
        }
        if (harness.edgeIndex === 0) {
          var before = view.tab
          keyboard.keyClick(Qt.Key_Tab, Qt.ControlModifier)
          if (view.tab !== (before + 1) % 4) { harness.fail("Ctrl+Tab did not switch tabs"); return }
          keyboard.keyClick(Qt.Key_R, Qt.ControlModifier)
          harness.stage = 2
        } else harness.stage = 3
      } else if (harness.stage === 2) {
        if (source.busy) return
        keyboard.keyClick(Qt.Key_Tab, Qt.ControlModifier | Qt.ShiftModifier)
        var provider = harness.find(view, "usage-provider-select")
        harness.tabTo(provider)
        keyboard.keyClick(Qt.Key_Return)
        harness.stage = 10
      } else if (harness.stage === 10) {
        var selector = harness.find(view, "usage-provider-select")
        if (!selector.popupOpen) return
        keyboard.keyClick(Qt.Key_Escape)
        if (!widget.opened) { harness.fail("selector Escape closed the whole panel"); return }
        harness.activate(harness.find(view, "tab-agents"))
        harness.stage = 11
      } else if (harness.stage === 11) {
        harness.activate(harness.find(view, "agent-choice-codex"))
        if (view.agentId !== "codex") { harness.fail("agent row did not select its editor"); return }
        harness.tabTo(harness.find(view, "agent-route-select"))
        keyboard.keyClick(Qt.Key_Return)
        harness.stage = 12
      } else if (harness.stage === 12) {
        if (!harness.find(view, "agent-route-select").popupOpen) return
        var text = "writing"
        for (var i = 0; i < text.length; i++) keyboard.keyClick(text[i])
        harness.stage = 13
      } else if (harness.stage === 13) {
        keyboard.keyClick(Qt.Key_Down)
        keyboard.keyClick(Qt.Key_Return)
        harness.stage = 14
      } else if (harness.stage === 14) {
        if (harness.find(view, "agent-route-select").popupOpen) return
        if (view.routeId !== "writing") { harness.fail("searchable route selection did not select the model"); return }
        harness.activate(harness.find(view, "agent-apply"))
        harness.stage = 15
      } else if (harness.stage === 15) {
        if (source.busy || source.actionBusy || source.noticeText !== "agent_saved") return
        harness.activate(harness.find(view, "agent-revert"))
        if (!view.confirmRevert || source.actionBusy) { harness.fail("revert must confirm before writing"); return }
        harness.activate(harness.find(view, "agent-revert"))
        harness.stage = 16
      } else if (harness.stage === 16) {
        if (source.busy || source.actionBusy || source.noticeText !== "agent_saved") return
        harness.activate(harness.find(view, "tab-quota"))
        harness.stage = 17
      } else if (harness.stage === 17) {
        harness.activate(harness.find(view, "quota-refresh-fixture:alpha"))
        harness.stage = 18
      } else if (harness.stage === 18) {
        if (source.busy || source.actionBusy || source.noticeText !== "quota_updated") return
        harness.activate(harness.find(view, "quota-refresh-fixture:gamma"))
        harness.stage = 19
      } else if (harness.stage === 19) {
        if (source.actionBusy) return
        if (source.noticeText !== "quota_error_timeout" || source.busy) {
          harness.fail("quota failure must show an actionable category without automatic retry"); return
        }
        harness.stage = 3
      } else if (harness.stage === 3) {
        keyboard.keyClick(Qt.Key_Escape)
        if (widget.opened) { harness.fail("Escape did not close the native panel"); return }
        if (harness.edgeIndex === 3) {
          console.info("ZCALL_OMARCHY_POPUP_READY"); Qt.quit(); return
        }
        harness.edgeIndex++; harness.stage = 4
      } else if (harness.stage === 4) {
        widget.open(); harness.stage = 1
      }
    }
  }
}
'''

with tempfile.TemporaryDirectory(prefix="zcall-omarchy-qml-") as directory:
    temporary = Path(directory)
    for name in ("Ui", "Commons"):
        (temporary / name).symlink_to(SHELL / name, target_is_directory=True)
    runtime = temporary / "runtime"
    runtime.mkdir(mode=0o700)
    fixture = json.loads((ROOT / "tests/fixtures/panel.json").read_text())
    backend, calls = temporary / "backend", temporary / "calls.jsonl"
    backend.write_text(
        "#!" + str(Path(sys.executable).resolve()) + "\n"
        "import json,sys,time\nfrom pathlib import Path\n"
        "with Path(" + repr(str(calls)) + ").open('a') as f:f.write(json.dumps(sys.argv[1:])+'\\n')\n"
        "args=sys.argv[1:]\n"
        "if args[:2]==['panel','action']:\n"
        " time.sleep(0.08)\n"
        " payload=json.loads(args[args.index('--payload')+1])\n"
        " result={'ok':False,'error_code':'timeout','error':'not-for-display-canary'} if payload.get('account')=='fixture:gamma' else {'ok':True,'agent_restart_required':args[2].startswith('agent.')}\n"
        " print(json.dumps(result))\n"
        "else:print(" + repr(json.dumps(fixture)) + ")\n"
    )
    backend.chmod(0o700)
    (temporary / "shell.qml").write_text(
        QML.replace("SOURCE", json.dumps((ROOT / "BarWidget.qml").as_uri())).replace("BACKEND", json.dumps(str(backend))))
    env = os.environ.copy()
    env.update(HOME=str(temporary), XDG_CONFIG_HOME=str(temporary / ".config"),
               XDG_STATE_HOME=str(temporary / ".local/state"), XDG_CACHE_HOME=str(temporary / ".cache"),
               XDG_RUNTIME_DIR=str(runtime), QT_QPA_PLATFORM="wayland", WAYLAND_DISPLAY=str(display_path),
               QT_QPA_PLATFORMTHEME="generic", QT_STYLE_OVERRIDE="Fusion",
               QT_QUICK_BACKEND="software", OMARCHY_PATH=str(SHELL.parent))
    result = subprocess.run([binary, "--path", str(temporary), "--no-color"],
                            env=env, capture_output=True, text=True, timeout=18)
    output = result.stdout + result.stderr
    if result.returncode or "ZCALL_OMARCHY_POPUP_READY" not in output:
        raise SystemExit(output)
    if any(marker in output for marker in ("TypeError:", "ReferenceError:", "Unable to assign", "QML Error")):
        raise SystemExit(output)
    recorded = [json.loads(row) for row in calls.read_text().splitlines()]
    expected = ["panel", "snapshot", "--period", "today", "--provider", "all"]
    reads = [row for row in recorded if row[:2] == ["panel", "snapshot"]]
    actions = [(row[2], json.loads(row[4])) for row in recorded if row[:2] == ["panel", "action"]]
    if reads != [expected] * 8 or actions != [
        ("agent.route", {"agent": "codex", "route": "writing"}),
        ("agent.revert", {"agent": "codex"}),
        ("quota.refresh", {"account": "fixture:alpha"}),
        ("quota.refresh", {"account": "fixture:gamma"}),
    ]:
        raise SystemExit("Unexpected controller calls: " + repr(recorded))
    print("Native popup: four edges, host owner, keyboard selector/search/Apply/Revert/quota/Escape, reopen focus; eight offline snapshots, four explicit fake actions, no retries.")
