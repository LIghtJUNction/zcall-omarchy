import qs.Ui as Ui
import qs.Commons

Ui.Button {
    property string label: ""
    // Shared shell controls may choose AutoText. Neutralize markup on input.
    text: label.replace(/</g, "‹").replace(/>/g, "›").slice(0, 180)
    radius: Style.space(10)
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
