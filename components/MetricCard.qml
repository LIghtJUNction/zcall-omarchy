import QtQuick
import qs.Commons as Commons
import qs.Commons

Rectangle {
    id: root
    property string title: ""
    property string value: "—"
    property string detail: ""
    implicitHeight: Style.space(88)
    radius: Style.space(11)
    color: Qt.alpha(Commons.Color.popups.text, 0.045)
    border.width: 1
    border.color: Qt.alpha(Commons.Color.popups.text, 0.065)
    Column {
        anchors.fill: parent
        anchors.margins: Style.space(11)
        spacing: Style.space(5)
        Label { width: parent.width; text: root.title; font.pixelSize: Style.font.caption; opacity: 0.68 }
        Label { width: parent.width; text: root.value; font.pixelSize: Style.space(22); fontSizeMode: Text.Fit; minimumPixelSize: Style.space(13); font.weight: Font.DemiBold }
        Label { width: parent.width; text: root.detail; font.pixelSize: Style.space(10); opacity: 0.58 }
    }
}
