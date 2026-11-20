import qs.Ui as Ui
import qs.Commons
import "."

Ui.Button {
    id: root
    property string label: ""
    // Shared shell controls may choose AutoText. Neutralize markup on input.
    text: label.replace(/</g, "‹").replace(/>/g, "›").slice(0, 180)
    radius: Style.space(6)
    foreground: selected ? Ink.accent : Ink.text
    accent: Ink.accent
    fontFamily: Ink.fontFamily
    fontSize: Ink.body
    tooltipBackground: Ink.surface
    tooltipForeground: Ink.text
    tooltipBorder: Ink.border
    color: selected ? Ink.selected : hot || activeFocus ? Ink.surface : "transparent"
    borderSpec: Border.flat(activeFocus ? Ink.accent : "transparent", 1)
    focusable: true
    onActiveFocusChanged: {
        if (!activeFocus) return
        for (var holder = parent; holder; holder = holder.parent) {
            if ("contentY" in holder && "contentHeight" in holder && "contentItem" in holder) {
                var point = mapToItem(holder.contentItem, 0, 0)
                if (point.y < holder.contentY) holder.contentY = Math.max(0, point.y)
                else if (point.y + height > holder.contentY + holder.height)
                    holder.contentY = Math.max(0, Math.min(holder.contentHeight - holder.height, point.y + height - holder.height))
                break
            }
        }
    }
    horizontalPadding: Style.space(10)
    verticalPadding: Style.space(7)
}
