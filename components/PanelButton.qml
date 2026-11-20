import qs.Ui as Ui
import qs.Commons

Ui.Button {
    property string label: ""
    // Shared shell controls may choose AutoText. Neutralize markup on input.
    text: label.replace(/</g, "‹").replace(/>/g, "›").slice(0, 180)
    radius: Style.space(10)
    focusable: true
    horizontalPadding: Style.space(10)
    verticalPadding: Style.space(7)
}
