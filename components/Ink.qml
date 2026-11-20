pragma Singleton
import QtQuick
import qs.Commons as Commons
import qs.Commons

// Application-local Ink palette from oh-my-ztty. The shell chooses light/dark;
// its global theme, fonts and other plugins are never changed.
QtObject {
    readonly property bool dark: (Commons.Color.popups.background.r * 0.2126
        + Commons.Color.popups.background.g * 0.7152
        + Commons.Color.popups.background.b * 0.0722) < 0.5
    readonly property color background: dark ? "#161412" : "#f5f0e8"
    readonly property color surface: dark ? "#201c18" : "#ece4d9"
    readonly property color text: dark ? "#e8ded2" : "#322a24"
    readonly property color muted: dark ? "#a3978b" : "#74685e"
    readonly property color border: dark ? "#383029" : "#d8cabb"
    readonly property color accent: dark ? "#d4a373" : "#885527"
    readonly property color selected: dark ? "#45382e" : "#e8d5bd"
    readonly property color urgent: dark ? "#e59a91" : "#a34135"
    readonly property string fontFamily: "JetBrainsMono Nerd Font"
    readonly property int body: Style.space(13)
    readonly property int caption: Style.space(11)
}
