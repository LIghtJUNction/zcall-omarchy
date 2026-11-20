import QtQuick
import qs.Ui as Ui
import qs.Commons
import "components" as C

Ui.Panel {
    id: root
    required property Item anchorItem
    required property string entryPath
    property var popupOwner: root
    property url brandIcon: ""
    readonly property var loadedContent: popup.loadedContent
    property alias dataSource: backendSource
    signal launchSection(string section)
    moduleName: "lightjunction.zcall"
    manageIpc: false

    PanelData {
        id: backendSource
        entryPath: root.entryPath
        configPath: root.setting("config", "")
        active: root.opened
    }

    Ui.KeyboardPanel {
        id: popup
        anchorItem: root.anchorItem
        owner: root.popupOwner
        bar: root.bar
        open: root.opened
        focusTarget: popup.loadedContent
        padding: Style.space(20)
        borderSpec: Border.flat(C.Ink.border, 1)
        contentWidth: popup.fittedContentWidth(Style.space(560))
        contentHeight: popup.cappedContentHeight(Style.space(680))
        content: PanelContent {
            anchors.fill: parent
            dataSource: backendSource
            surfaceInset: popup.padding + 1
            brandIcon: root.brandIcon
            languageOverride: root.setting("language", "")
            onCloseRequested: root.close()
            onLaunchSection: function(section) { root.launchSection(section) }
        }
    }
}
