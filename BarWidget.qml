import QtQuick
import Quickshell
import qs.Ui as Ui
import qs.Commons as Commons

Ui.BarWidget {
    id: root
    moduleName: "lightjunction.zcall"
    implicitWidth: button.implicitWidth
    implicitHeight: button.implicitHeight
    property alias gatewayPanel: gateway
    readonly property bool opened: gateway.opened
    property alias popoutSwitching: gateway.popoutSwitching
    property alias popoutSwitchClosing: gateway.popoutSwitchClosing
    function open() { gateway.open() }
    function close() { gateway.close() }
    function toggle() { gateway.toggle() }
    function closeForPopoutSwitch() { gateway.closeForPopoutSwitch() }
    readonly property url markSource: Qt.resolvedUrl((Commons.Color.popups.background.r * 0.2126 + Commons.Color.popups.background.g * 0.7152 + Commons.Color.popups.background.b * 0.0722) > 0.5 ? "assets/mark-light.svg" : "assets/mark-dark.svg")
    readonly property string entryPath: decodeURIComponent(Qt.resolvedUrl("bin/zcall-omarchy").toString().replace(/^file:\/\//, ""))

    function launch(section) {
        gateway.close()
        var command = [entryPath]
        if (typeof settings.config === "string" && settings.config !== "")
            command.push("--config", settings.config)
        Quickshell.execDetached(command.concat(["open", section]))
    }

    Ui.BarIconButton {
        id: button
        anchors.fill: parent
        bar: root.bar
        iconComponent: Component {
            Image { source: root.markSource; sourceSize.width: 32; sourceSize.height: 32; fillMode: Image.PreserveAspectFit }
        }
        onPressed: function(mouseButton) {
            if (mouseButton === Qt.LeftButton) gateway.toggle()
            else if (mouseButton === Qt.RightButton) root.launch("menu")
        }
    }

    GatewayPanel {
        id: gateway
        anchorItem: button
        popupOwner: root
        bar: root.bar
        settings: root.settings
        entryPath: root.entryPath
        brandIcon: root.markSource
        onLaunchSection: function(section) { root.launch(section) }
    }
}
