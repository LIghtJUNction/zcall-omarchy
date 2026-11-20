import QtQuick
import qs.Commons
import "."

Rectangle {
    id: root
    property string title: ""
    property string value: "—"
    property string detail: ""
    implicitHeight: Style.space(88)
    radius: Style.space(6)
    color: Ink.surface
    border.width: 1
    border.color: Ink.border
    Column {
        anchors.fill: parent
        anchors.margins: Style.space(11)
        spacing: Style.space(5)
        Label { width: parent.width; text: root.title; font.pixelSize: Ink.caption; color: Ink.muted }
        Label { width: parent.width; text: root.value; font.pixelSize: Style.space(22); fontSizeMode: Text.Fit; minimumPixelSize: Style.space(13); font.weight: Font.DemiBold }
        Label { width: parent.width; text: root.detail; font.pixelSize: Style.space(10); color: Ink.muted }
    }
}
