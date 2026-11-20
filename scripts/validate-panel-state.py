#!/usr/bin/env python3
"""Exercise real QML subprocess lifecycle with a fake, local-only controller."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
binary = shutil.which('quickshell')
if not binary:
    raise SystemExit('Quickshell is required for the asynchronous panel check.')
with tempfile.TemporaryDirectory(prefix='zcall-panel-state-') as directory:
    temporary = Path(directory)
    runtime = temporary / 'runtime'
    runtime.mkdir(mode=0o700)
    fixture = json.loads((ROOT / 'tests/fixtures/panel.json').read_text())
    (temporary / 'fixture.json').write_text(json.dumps(fixture))
    entry = temporary / 'controller'
    entry.write_text('#!' + str(Path(sys.executable).resolve()) + '\n' + '''import json,sys,time
from pathlib import Path
root=Path(__file__).parent
args=sys.argv[1:]
with (root/'calls.jsonl').open('a') as file: file.write(json.dumps(args)+'\\n')
if args[:2]==['panel','snapshot']:
 time.sleep(.20)
 value=json.loads((root/'fixture.json').read_text())
 value['filters']={'period':args[3],'provider':args[5]}
 print(json.dumps(value))
elif args[:2]==['panel','action']:
 time.sleep(.06)
 print(json.dumps({'ok':True,'agent_restart_required':False}))
else: sys.exit(2)
''')
    entry.chmod(0o700)
    compile(entry.read_text(), str(entry), 'exec')
    qml = '''
import QtQuick
import Quickshell
ShellRoot {
    id: root
    property var source: null
    property int ticks: 0
    property int stage: 0
    property int changed: 0
    property bool failed: false
    function fail(message) { failed = true; console.error(message); Qt.quit() }
    Component.onCompleted: {
        var component = Qt.createComponent(SOURCE)
        if (component.status !== Component.Ready) { fail(component.errorString()); return }
        source = component.createObject(null, {entryPath:ENTRY})
        if (!source) { fail(component.errorString()); return }
        watch.start()
    }
    Timer {
        id: watch
        interval: 30
        repeat: true
        onTriggered: {
            root.ticks += 1
            if (root.ticks > 180) { root.fail("Panel state deadline: " + JSON.stringify({stage:root.stage,active:root.source.active,busy:root.source.busy,serial:root.source.refreshSerial,error:root.source.errorText})); return }
            if (root.stage === 0 && root.ticks === 3) {
                if (root.source.busy || root.source.snapshot !== null) { root.fail("Closed panel executed a read"); return }
                root.source.active = true
                root.stage = 1
            } else if (root.stage === 1 && root.source.busy) {
                root.source.filter("7d", "unselected")
                root.source.filter("30d", "all")
                root.stage = 2
            } else if (root.stage === 2 && !root.source.busy && root.source.refreshSerial === 1) {
                if (root.source.snapshot.filters.period !== "30d") { root.fail("Stale filter response replaced the latest choice"); return }
                root.source.perform("quota.refresh", {account:"fixture:opaque"})
                root.source.active = false
                root.stage = 3
            } else if (root.stage === 3 && !root.source.actionBusy) {
                if (!root.source.actionSucceeded || root.source.noticeText !== "quota_updated") { root.fail("Closing discarded the explicit action result"); return }
                root.changed = root.ticks
                root.stage = 4
            } else if (root.stage === 4 && root.ticks - root.changed > 10) {
                if (root.source.busy || root.source.refreshSerial !== 1) { root.fail("Closed panel kept refreshing"); return }
                root.source.entryPath = MISSING
                root.source.active = true
                root.changed = root.ticks
                root.stage = 5
            } else if (root.stage === 5 && root.ticks - root.changed > 10) {
                if (root.source.busy || root.source.errorText !== "snapshot_failed") { root.fail("Missing controller did not reach an error state"); return }
                root.source.destroy()
                console.info("ZCALL_PANEL_STATE_READY")
                Qt.quit()
            }
        }
    }
}
'''
    qml = qml.replace('SOURCE', json.dumps((ROOT / 'PanelData.qml').as_uri())).replace('ENTRY', json.dumps(str(entry))).replace('MISSING', json.dumps(str(temporary / 'missing-controller')))
    (temporary / 'shell.qml').write_text(qml)
    environment = os.environ.copy()
    environment.update(HOME=str(temporary), XDG_CONFIG_HOME=str(temporary / '.config'),
                       XDG_STATE_HOME=str(temporary / '.state'), XDG_CACHE_HOME=str(temporary / '.cache'),
                       XDG_RUNTIME_DIR=str(runtime), QT_QPA_PLATFORM='offscreen',
                       QT_QPA_PLATFORMTHEME='generic', QT_QUICK_BACKEND='software')
    result = subprocess.run([binary, '--path', str(temporary), '--no-color'], env=environment,
                            capture_output=True, text=True, timeout=10)
    text = result.stdout + result.stderr
    if result.returncode or 'ZCALL_PANEL_STATE_READY' not in text:
        raise SystemExit(text + '\nCALLS: ' + ((temporary / 'calls.jsonl').read_text() if (temporary / 'calls.jsonl').exists() else 'none'))
    calls = [json.loads(line) for line in (temporary / 'calls.jsonl').read_text().splitlines()]
    expected = [['panel', 'snapshot', '--period', 'today', '--provider', 'all'],
                ['panel', 'snapshot', '--period', '30d', '--provider', 'all'],
                ['panel', 'action', 'quota.refresh', '--payload', '{"account":"fixture:opaque"}']]
    if calls != expected:
        raise SystemExit('Unexpected controller call sequence: ' + repr(calls))
    print('Real QML lifecycle passed: lazy open, latest-filter wins, explicit action once, close without polling, missing-controller error.')
