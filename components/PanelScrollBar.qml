import QtQuick
import QtQuick.Controls as Controls
import qs.Commons
import "."
Controls.ScrollBar {
    id: root
    contentItem: Rectangle {
        implicitWidth: Style.space(4)
        implicitHeight: Style.space(4)
        radius: Style.space(2)
        color: Ink.muted
        opacity: root.pressed ? 0.8 : root.active ? 0.5 : 0.22
    }
    background: Item {}
}
