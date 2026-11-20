import QtQuick
import qs.Commons as Commons
import qs.Commons
import "."

Item {
    id: root
    property var buckets: []
    property string metric: "tokens"
    property string emptyText: ""
    property string partialLabel: ""
    property string unknownText: ""
    readonly property bool hasValues: buckets.some(function(row) { return amount(row) !== null })
    function amount(row) {
        var value = row[metric]
        if (metric === "cost_usd" && (value === null || value === undefined))
            return row.priced_requests > 0 && typeof row.known_cost_usd === "number" ? row.known_cost_usd : null
        return typeof value === "number" && isFinite(value) ? value : null
    }
    onBucketsChanged: hoveredLabel = ""
    onMetricChanged: hoveredLabel = ""
    property string hoveredLabel: ""
    readonly property real maximum: {
        var highest = 0
        for (var i = 0; i < buckets.length; ++i) {
            var n = amount(buckets[i])
            if (typeof n === "number" && isFinite(n)) highest = Math.max(highest, n)
        }
        return highest
    }
    readonly property var tickIndexes: {
        var count = Math.min(5, buckets.length)
        var values = []
        for (var i = 0; i < count; ++i)
            values.push(i === count - 1 ? buckets.length - 1 : Math.floor(buckets.length * i / Math.max(1, count - 1)))
        return values
    }
    function tickLabel(index) {
        var label = String(buckets[index].label)
        return /^\d{4}-\d{2}-\d{2}$/.test(label) ? label.slice(5) : label
    }
    implicitHeight: Style.space(144)
    function compact(n) {
        if (n === null || n === undefined || !isFinite(Number(n))) return "—"
        if (metric === "cost_usd") return "$" + Commons.I18n.formatNumber(n, 2)
        var suffix = n >= 1000000000 ? "B" : n >= 1000000 ? "M" : n >= 1000 ? "k" : ""
        var unit = suffix === "B" ? 1000000000 : suffix === "M" ? 1000000 : suffix === "k" ? 1000 : 1
        return Commons.I18n.formatNumber(n / unit, suffix ? 1 : 0) + suffix
    }
    Label { width: parent.width; text: root.hoveredLabel || root.compact(root.hasValues ? root.maximum : null); font.pixelSize: Ink.caption; opacity: 0.65 }
    Item {
        id: plot
        anchors { left: parent.left; right: parent.right; top: parent.top; bottom: parent.bottom; topMargin: Style.space(25); bottomMargin: Style.space(23) }
        Repeater {
            model: 3
            Rectangle {
                required property int index
                x: 0; y: plot.height * index / 2
                width: plot.width; height: 1
                color: Qt.alpha(Ink.text, 0.08)
            }
        }
        Row {
            anchors.fill: parent
            spacing: root.buckets.length > 70 ? Style.space(1) : Style.space(3)
            Repeater {
                model: root.buckets
                Item {
                    id: slot
                    required property var modelData
                    required property int index
                    width: Math.max(1, (plot.width - (root.buckets.length - 1) * parent.spacing) / Math.max(1, root.buckets.length))
                    height: plot.height
                    readonly property real amount: root.amount(modelData) || 0
                    Rectangle {
                        anchors.bottom: parent.bottom
                        width: parent.width
                        height: slot.amount > 0 && root.maximum > 0 ? Math.max(2, plot.height * slot.amount / root.maximum) : 0
                        radius: Math.min(Style.space(2), width / 3)
                        color: Ink.accent
                        opacity: hover.containsMouse ? 1 : 0.72
                    }
                    MouseArea {
                        id: hover
                        anchors.fill: parent
                        hoverEnabled: true
                        onEntered: root.hoveredLabel = String(slot.modelData.label).slice(0, 60) + " · " + root.compact(root.amount(slot.modelData)) + (root.metric === "cost_usd" && slot.modelData.unpriced_requests > 0 ? " · " + root.partialLabel : "")
                        onExited: root.hoveredLabel = ""
                    }
                }
            }
        }
        Label { anchors.centerIn: parent; visible: root.maximum <= 0; text: root.hasValues ? root.emptyText : root.unknownText; font.pixelSize: Ink.caption; opacity: 0.65 }
    }
    Repeater {
        model: root.tickIndexes
        Label {
            required property var modelData
            required property int index
            anchors.bottom: parent.bottom
            x: Math.max(0, Math.min(root.width - implicitWidth, root.width * index / Math.max(1, root.tickIndexes.length - 1) - implicitWidth / 2))
            text: root.tickLabel(modelData)
            font.pixelSize: Style.space(10)
            opacity: 0.5
        }
    }
}
