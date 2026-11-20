#!/usr/bin/env python3
"""Render the actual panel with synthetic data in an isolated Quickshell process.

No controller is executed. Existing Omarchy/plugin/settings files are not changed.
The short-lived preview uses a separate Wayland window and closes after capture.
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output', type=Path, required=True)
parser.add_argument('--width', type=int, default=560)
parser.add_argument('--height', type=int, default=680)
parser.add_argument('--language', choices=['en', 'zh', 'zh-CN', 'zh-TW'], default='en')
parser.add_argument('--plugin-language', choices=['', 'en', 'zh-CN', 'zh-TW'], default='')
parser.add_argument('--theme', choices=['current', 'dark', 'light'], default='current')
args = parser.parse_args()
if not 320 <= args.width <= 900 or not 400 <= args.height <= 1000:
    parser.error('Preview dimensions are outside the supported fixture bounds.')
SHELL = Path(os.environ.get('OMARCHY_PATH', '/usr/share/omarchy')) / 'shell'
binary = shutil.which('quickshell')
display = os.environ.get('WAYLAND_DISPLAY', '')
runtime_base = Path(os.environ.get('XDG_RUNTIME_DIR', '/run/user/' + str(os.getuid())))
display_path = Path(display) if display.startswith('/') else runtime_base / display
if not binary or not display or not display_path.exists() or not (SHELL / 'Ui/Panel.qml').exists():
    raise SystemExit('An installed Omarchy 4.5 shell and a Wayland display are required.')
output = args.output.resolve()
output.mkdir(parents=True, exist_ok=True)
fixture = json.loads((ROOT / 'tests/fixtures/panel.json').read_text())
original_theme = Path.home() / '.local/state/omarchy/current/theme'
with tempfile.TemporaryDirectory(prefix='zcall-panel-preview-') as directory:
    temporary = Path(directory)
    for name in ('Ui', 'Commons'):
        (temporary / name).symlink_to(SHELL / name, target_is_directory=True)
    runtime = temporary / 'runtime'
    runtime.mkdir(mode=0o700)
    theme = temporary / '.local/state/omarchy/current/theme'
    theme.mkdir(parents=True)
    if args.theme == 'current':
        for name in ('colors.toml', 'shell.toml'):
            source = original_theme / name
            if source.is_file():
                shutil.copyfile(source, theme / name)
    else:
        foreground, background, accent = ('#262b32', '#fafbfc', '#4e657d') if args.theme == 'light' else ('#e2e6eb', '#171b20', '#a4bacd')
        (theme / 'colors.toml').write_text(f'foreground = "{foreground}"\nbackground = "{background}"\naccent = "{accent}"\n')
    # Omarchy's public locale resolver reads these saved settings. Environment
    # also provides an ordinary fallback when the host has no saved language.
    locale = 'zh_CN.UTF-8' if args.language == 'zh' else 'en_US.UTF-8'
    language_file = temporary / '.config/omarchy/language'
    language_file.parent.mkdir(parents=True, exist_ok=True)
    language_file.write_text(args.language + '\n')
    qml = '''
import QtQuick
import QtQuick.Window
import Quickshell
import Quickshell.Wayland
import qs.Commons as Commons
ShellRoot {
    id: shell
    property var tested: null
    property int stage: 0
    property var names: ["usage", "agents", "routing", "quota", "empty", "error"]
    QtObject {
        id: source
        property var snapshot: FIXTURE
        property string period: "today"
        property string provider: "all"
        property bool busy: false
        property bool actionBusy: false
        property string actionName: ""
        property string errorText: ""
        property string noticeText: ""
        property bool actionSucceeded: false
        property int calls: 0
        function refresh() { calls += 1 }
        function filter(p, v) { period = p; provider = v; calls += 1 }
        function perform(name, payload) { calls += 1; noticeText = "agent_saved"; actionSucceeded = true }
    }
    PanelWindow {
        id: window
        visible: true
        implicitWidth: WIDTH
        implicitHeight: HEIGHT
        exclusionMode: ExclusionMode.Ignore
        WlrLayershell.namespace: "zcall-isolated-preview"
        WlrLayershell.layer: WlrLayer.Overlay
        color: Commons.Color.popups.background
        Rectangle {
            id: canvas
            anchors.fill: parent
            color: Commons.Color.popups.background
            Item { id: holder; anchors.fill: parent; anchors.margins: 16 }
        }
    }
    function checkLayout(node) {
        if (String(node.objectName).indexOf("tab-") === 0) {
            var point = node.mapToItem(shell.tested, 0, 0)
            if (point.x < -1 || point.x + node.width > shell.tested.width + 1 || node.width < 35) {
                console.error("QML Error: tab exceeds panel bounds " + node.objectName)
                Qt.exit(3)
            }
        }
        if (node.children) for (var i = 0; i < node.children.length; i++) checkLayout(node.children[i])
    }
    Component.onCompleted: {
        var component = Qt.createComponent(SOURCE)
        if (component.status !== Component.Ready) { console.error(component.errorString()); Qt.quit(); return }
        shell.tested = component.createObject(holder, {width:holder.width, height:holder.height, dataSource:source, brandIcon:ICON, languageOverride:PLUGIN_LANGUAGE, surfaceInset:16})
        if (!shell.tested) { console.error(component.errorString()); Qt.quit(); return }
        shell.tested.chooseAgent(source.snapshot.agents[0])
        shell.tested.forceActiveFocus()
        capture.start()
    }
    Timer {
        id: capture
        interval: 250
        onTriggered: {
            if (!shell.tested || !shell.tested.width || !shell.tested.height) { console.error("Panel has no content"); Qt.quit(); return }
            shell.checkLayout(shell.tested)
            canvas.grabToImage(function(result) {
                if (!result.saveToFile(OUTPUT + "/" + shell.names[shell.stage] + ".png")) { console.error("Capture failed"); Qt.quit(); return }
                shell.stage += 1
                if (shell.stage === 1) shell.tested.tab = 0
                else if (shell.stage === 2) shell.tested.tab = 3
                else if (shell.stage === 3) shell.tested.tab = 1
                else if (shell.stage === 4) { source.snapshot = null; source.busy = true }
                else if (shell.stage === 5) { source.busy = false; source.errorText = "snapshot_failed" }
                else { console.info("ZCALL_PANEL_CAPTURE_READY"); Qt.quit(); return }
                capture.start()
            })
        }
    }
}
'''
    replacements = {
        'FIXTURE': json.dumps(fixture),
        'SOURCE': json.dumps((ROOT / 'PanelContent.qml').as_uri()),
        'ICON': json.dumps((ROOT / 'assets' / ('mark-light.svg' if args.theme == 'light' else 'mark-dark.svg')).as_uri()),
        'OUTPUT': json.dumps(str(output)), 'PLUGIN_LANGUAGE': json.dumps(args.plugin_language), 'WIDTH': str(args.width), 'HEIGHT': str(args.height),
    }
    for name, value in replacements.items():
        qml = qml.replace(name, value)
    (temporary / 'shell.qml').write_text(qml)
    environment = os.environ.copy()
    environment.update(HOME=str(temporary), XDG_CONFIG_HOME=str(temporary / '.config'),
                       XDG_STATE_HOME=str(temporary / '.local/state'), XDG_CACHE_HOME=str(temporary / '.cache'),
                       XDG_RUNTIME_DIR=str(runtime), WAYLAND_DISPLAY=str(display_path),
                       QT_QPA_PLATFORM='wayland', QT_QPA_PLATFORMTHEME='generic', QT_STYLE_OVERRIDE='Fusion',
                       QT_QUICK_BACKEND='software', LANG=locale, LC_ALL=locale, OMARCHY_PATH=str(SHELL.parent))
    result = subprocess.run([binary, '--path', str(temporary), '--no-color'], env=environment,
                            capture_output=True, text=True, timeout=20)
    text = result.stdout + result.stderr
    (output / 'preview.log').write_text(text)
    if result.returncode or 'ZCALL_PANEL_CAPTURE_READY' not in text or any(marker in text for marker in ('ERROR qml:', 'QML Error:', 'TypeError:', 'ReferenceError:', 'Unable to assign')):
        raise SystemExit(text)
    print(json.dumps({'screenshots': 6, 'width': args.width, 'height': args.height,
                      'synthetic_data': True, 'controller_calls': 0, 'output': str(output)}))
