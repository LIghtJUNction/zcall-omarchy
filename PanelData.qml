import QtQuick
import Quickshell.Io

// Finite local subprocesses only. No polling, shell strings, or provider calls.
Item {
    id: root
    required property string entryPath
    property string configPath: ""
    property bool active: false
    property string period: "today"
    property string provider: "all"
    property var snapshot: null
    property string errorText: ""
    property string noticeText: ""
    property bool actionSucceeded: false
    readonly property bool busy: reading
    readonly property bool actionBusy: writing
    property bool reading: false
    property bool writing: false
    property bool pending: false
    property string requestedPeriod: ""
    property string requestedProvider: ""
    property int refreshSerial: 0

    onActiveChanged: if (active) refresh()

    function baseCommand() {
        var result = [entryPath]
        if (configPath !== "") result.push("--config", configPath)
        return result
    }
    function refresh() {
        if (!active) return
        if (busy || actionBusy) { pending = true; return }
        pending = false
        requestedPeriod = period
        requestedProvider = provider
        errorText = ""
        reader.command = baseCommand().concat(["panel", "snapshot", "--period", period, "--provider", provider])
        reader.hasStarted = false
        reading = true
        reader.running = true
    }
    function filter(nextPeriod, nextProvider) {
        if (period === nextPeriod && provider === nextProvider) return
        period = nextPeriod
        provider = nextProvider
        refresh()
    }
    function readFinished(code) {
        var outdated = requestedPeriod !== period || requestedProvider !== provider
        if (!outdated) {
            try {
                if (code !== 0 || readOutput.text.length > 2097152) throw new Error("snapshot")
                var value = JSON.parse(readOutput.text)
                if (!value || value.schema_version !== 1 || !value.status || !Array.isArray(value.agents)
                    || !Array.isArray(value.routes) || !value.usage || !value.quota)
                    throw new Error("schema")
                snapshot = value
                refreshSerial += 1
                errorText = ""
            } catch (_) { errorText = "snapshot_failed" }
        }
        reading = false
        if ((pending || outdated) && active) Qt.callLater(refresh)
    }
    function perform(name, payload) {
        if (actionBusy || busy || (name !== "agent.route" && name !== "agent.revert")) return
        noticeText = ""
        errorText = ""
        actionSucceeded = false
        writer.command = baseCommand().concat(["panel", "action", name, "--payload", JSON.stringify(payload)])
        writer.hasStarted = false
        writing = true
        writer.running = true
    }
    function actionFinished(code) {
        writing = false
        try {
            if (code !== 0 || writeOutput.text.length > 65536) throw new Error("action")
            var result = JSON.parse(writeOutput.text)
            if (!result || result.ok !== true) {
                noticeText = result && typeof result.error === "string" ? result.error.slice(0, 280) : "action_failed"
            } else {
                actionSucceeded = true
                noticeText = result.agent_restart_required ? "agent_saved" : "action_saved"
                pending = true
            }
        } catch (_) { noticeText = "action_failed" }
        if (pending && active) Qt.callLater(refresh)
    }

    Process {
        id: reader
        property bool hasStarted: false
        running: false
        onStarted: hasStarted = true
        onRunningChanged: {
            if (!running && !hasStarted && root.reading)
                Qt.callLater(function() { if (!reader.running && !reader.hasStarted && root.reading) root.readFinished(1) })
        }
        stdout: StdioCollector { id: readOutput; waitForEnd: true }
        stderr: StdioCollector { waitForEnd: true }
        onExited: function(exitCode) { Qt.callLater(function() { root.readFinished(exitCode) }) }
    }
    Process {
        id: writer
        property bool hasStarted: false
        running: false
        onStarted: hasStarted = true
        onRunningChanged: {
            if (!running && !hasStarted && root.writing)
                Qt.callLater(function() { if (!writer.running && !writer.hasStarted && root.writing) root.actionFinished(1) })
        }
        stdout: StdioCollector { id: writeOutput; waitForEnd: true }
        stderr: StdioCollector { waitForEnd: true }
        onExited: function(exitCode) { Qt.callLater(function() { root.actionFinished(exitCode) }) }
    }
}
