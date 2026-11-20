import QtQuick
import Quickshell
import qs.Ui

BarWidget {
  id: root
  moduleName: "lightjunction.zcall"

  implicitWidth: button.implicitWidth
  implicitHeight: button.implicitHeight

  function launch(section) {
    var entry = decodeURIComponent(Qt.resolvedUrl("bin/zcall-omarchy").toString().replace(/^file:\/\//, ""))
    Quickshell.execDetached([entry, "open", section])
  }

  BarIconButton {
    id: button
    anchors.fill: parent
    bar: root.bar
    text: "Z"
    onPressed: function(button) {
      root.launch(button === Qt.RightButton ? "status" : "menu")
    }
  }
}
