import QtQuick
import QtQuick.Layouts
import QtQuick.Controls as Controls
import qs.Ui as Ui
import qs.Commons as Commons
import qs.Commons
import "components" as C

FocusScope {
    id: root
    required property var dataSource
    property url brandIcon: ""
    property string languageOverride: ""
    property int tab: 2
    property bool moreOpen: false
    property string chartMetric: "tokens"
    property string agentId: ""
    property string routeId: ""
    property bool confirmRevert: false
    readonly property var snapshot: dataSource.snapshot
    readonly property var gatewayState: snapshot ? snapshot.status : ({})
    readonly property var usage: snapshot ? snapshot.usage : ({})
    readonly property var totals: usage.totals || ({})
    readonly property var quota: snapshot ? snapshot.quota : ({})
    readonly property var agents: snapshot ? snapshot.agents : []
    readonly property var routes: snapshot ? snapshot.routes : []
    readonly property var groups: snapshot && snapshot.routing ? snapshot.routing.groups || [] : []
    readonly property var selectedAgent: agents.find(function(row) { return row.id === root.agentId }) || null
    readonly property bool editing: dataSource.busy || dataSource.actionBusy
    signal closeRequested()
    signal launchSection(string section)

    Commons.Translations {
        id: strings
        directory: Qt.resolvedUrl("i18n")
        property string selectedLanguage: ["en", "zh", "zh-CN", "zh-TW"].indexOf(root.languageOverride) >= 0 ? root.languageOverride : ""
        languageFile.path: selectedLanguage ? catalogPath(selectedLanguage) : (language !== "en" ? catalogPath(language) : "")
        baseFile.path: {
            var code = selectedLanguage || language
            var base = code.split("-")[0]
            return base !== code && base !== "en" ? catalogPath(base) : ""
        }
    }
    function t(key) { return strings.t(key) }
    function safe(value) { return String(value === null || value === undefined ? "" : value).replace(/</g, "‹").replace(/>/g, "›").slice(0, 180) }
    function number(value, decimals) {
        if (typeof value !== "number" || !isFinite(value)) return "—"
        return Commons.I18n.formatNumber(value, decimals || 0)
    }
    function compact(value) {
        if (typeof value !== "number" || !isFinite(value)) return "—"
        var unit = value >= 1000000000 ? 1000000000 : value >= 1000000 ? 1000000 : value >= 1000 ? 1000 : 1
        var suffix = unit === 1000000000 ? "B" : unit === 1000000 ? "M" : unit === 1000 ? "k" : ""
        return number(value / unit, suffix ? 1 : 0) + suffix
    }
    function money(value) { return typeof value === "number" && isFinite(value) ? "$" + number(value, 2) : "—" }
    function percent(value) { return typeof value === "number" && isFinite(value) ? number(value * 100, 1) + "%" : "—" }
    function providerOptions() {
        return [{value:"all", label:t("all_providers")}].concat((snapshot ? snapshot.providers : []).map(function(row) { return {value:row.id, label:safe(row.label)} }))
    }
    function routeOptions() {
        return routes.map(function(row) { return {value:row.id, label:safe(row.label || row.id), description:safe(row.kind === "group" ? t("group") : row.provider)} })
    }
    function agentOptions() {
        return agents.filter(function(row) { return row.editable && (row.installed || row.configured) }).map(function(row) { return {value:row.id, label:safe(row.name)} })
    }
    function chooseAgent(row) {
        agentId = row.id
        routeId = row.route || ""
        confirmRevert = false
    }
    function notice(value) { return ["agent_saved","action_saved","action_failed"].indexOf(value) >= 0 ? t(value) : value }
    function changeTab(index) { tab = index; moreOpen = false; confirmRevert = false }

    Keys.onPressed: function(event) {
        if (event.key === Qt.Key_Escape) {
            if (moreOpen || confirmRevert) { moreOpen = false; confirmRevert = false }
            else closeRequested()
            event.accepted = true
        } else if ((event.modifiers & Qt.ControlModifier) && event.key === Qt.Key_R) {
            dataSource.refresh(); event.accepted = true
        } else if ((event.modifiers & Qt.ControlModifier) && event.key === Qt.Key_Tab) {
            changeTab((tab + ((event.modifiers & Qt.ShiftModifier) ? 3 : 1)) % 4); event.accepted = true
        }
    }

    ColumnLayout {
        objectName: "panel-layout"
        anchors.fill: parent
        spacing: Style.space(12)

        RowLayout {
            Layout.fillWidth: true
            spacing: Style.space(9)
            Image { source: root.brandIcon; visible: source.toString() !== ""; sourceSize.width: 24; sourceSize.height: 24; Layout.preferredWidth: Style.space(22); Layout.preferredHeight: Style.space(22); fillMode: Image.PreserveAspectFit }
            C.Label { visible: root.brandIcon.toString() === ""; text: "‹›"; font.pixelSize: Style.space(20) }
            ColumnLayout {
                Layout.fillWidth: true
                spacing: Style.space(1)
                C.Label { Layout.fillWidth: true; text: "zcall"; font.pixelSize: Style.space(19); font.weight: Font.DemiBold }
                C.Label { Layout.fillWidth: true; text: root.dataSource.busy ? root.t("refreshing") : root.gatewayState.healthy === true ? root.t("running") : root.gatewayState.healthy === false ? root.t("unavailable") : root.t("local_gateway"); font.pixelSize: Style.space(10); opacity: 0.6 }
            }
            C.PanelButton { label: "↻"; fontSize: Style.space(17); tooltipText: root.t("refresh"); enabled: !root.editing; onClicked: root.dataSource.refresh() }
            C.PanelButton { label: "↗"; fontSize: Style.space(17); tooltipText: root.t("open_desktop"); onClicked: root.launchSection("gui") }
            C.PanelButton { label: "…"; fontSize: Style.space(17); tooltipText: root.t("more"); selected: root.moreOpen; onClicked: root.moreOpen = !root.moreOpen }
        }

        Flow {
            visible: root.moreOpen
            Layout.fillWidth: true
            spacing: Style.space(5)
            Repeater {
                model: ["service","providers","accounts","library","privacy","plugins","logs","updates"]
                C.PanelButton {
                    required property string modelData
                    label: root.t(modelData)
                    fontSize: Style.font.caption
                    onClicked: root.launchSection(modelData)
                }
            }
        }

        RowLayout {
            Layout.fillWidth: true
            spacing: Style.space(3)
            Repeater {
                model: ["agents","quota","usage","routing"]
                C.PanelButton {
                    required property string modelData
                    required property int index
                    Layout.fillWidth: true
                    objectName: "tab-" + modelData
                    Layout.minimumWidth: 0
                    Layout.preferredWidth: 1
                    label: root.t(modelData)
                    selected: root.tab === index
                    onClicked: root.changeTab(index)
                }
            }
        }

        Rectangle { Layout.fillWidth: true; implicitHeight: 1; color: Qt.alpha(Commons.Color.popups.text, 0.12) }

        C.Label {
            visible: root.dataSource.errorText !== "" || root.dataSource.noticeText !== ""
            Layout.fillWidth: true
            text: root.dataSource.errorText ? root.t("snapshot_failed") : root.notice(root.dataSource.noticeText)
            color: root.dataSource.actionSucceeded && !root.dataSource.errorText ? Commons.Color.popups.text : Commons.Color.urgent
            font.pixelSize: Style.font.caption
            wrapMode: Text.WordWrap
            maximumLineCount: 3
        }

        Item {
            visible: !root.snapshot
            Layout.fillWidth: true
            Layout.fillHeight: true
            C.Label { anchors.centerIn: parent; width: parent.width; horizontalAlignment: Text.AlignHCenter; wrapMode: Text.WordWrap; text: root.dataSource.busy ? root.t("loading") : root.t("no_snapshot"); opacity: 0.65 }
        }

        StackLayout {
            visible: !!root.snapshot
            Layout.fillWidth: true
            Layout.fillHeight: true
            currentIndex: root.tab

            Flickable {
                id: agentScroll
                contentWidth: width
                contentHeight: agentColumn.implicitHeight
                clip: true
                boundsBehavior: Flickable.StopAtBounds
                flickableDirection: Flickable.VerticalFlick
                Controls.ScrollBar.vertical: Controls.ScrollBar { policy: Controls.ScrollBar.AsNeeded }
                Column {
                    id: agentColumn
                    width: parent.width - Style.space(8)
                    spacing: Style.space(8)
                    C.Label { width: parent.width; text: root.t("agent_intro"); font.pixelSize: Style.font.caption; wrapMode: Text.WordWrap; opacity: 0.65 }
                    C.Label { visible: !agentRows.count; width: parent.width; text: root.t("agents_empty"); wrapMode: Text.WordWrap; opacity: 0.65 }
                    Repeater {
                        id: agentRows
                        model: root.agents.filter(function(row) { return row.installed || row.configured })
                        Rectangle {
                            id: agentRow
                            required property var modelData
                            width: agentColumn.width
                            implicitHeight: Style.space(73)
                            radius: Style.space(10)
                            color: root.agentId === modelData.id ? Qt.alpha(Commons.Color.accent, 0.1) : Qt.alpha(Commons.Color.popups.text, 0.025)
                            border.width: root.agentId === modelData.id ? 1 : 0
                            border.color: Qt.alpha(Commons.Color.accent, 0.5)
                            RowLayout {
                                anchors.fill: parent
                                anchors.margins: Style.space(11)
                                spacing: Style.space(10)
                                ColumnLayout {
                                    Layout.fillWidth: true
                                    spacing: Style.space(5)
                                    C.Label { Layout.fillWidth: true; text: agentRow.modelData.name; font.weight: Font.DemiBold }
                                    C.Label { Layout.fillWidth: true; text: agentRow.modelData.route || (agentRow.modelData.configured ? root.t("configured") : root.t("not_configured")); font.pixelSize: Style.font.caption; opacity: 0.6 }
                                }
                                C.PanelButton { visible: agentRow.modelData.editable; label: root.t("change"); enabled: !root.editing; onClicked: root.chooseAgent(agentRow.modelData) }
                                C.Label { visible: !agentRow.modelData.editable; text: root.t("detect_only"); font.pixelSize: Style.space(10); opacity: 0.55 }
                            }
                        }
                    }
                }
            }

            Flickable {
                id: quotaScroll
                contentWidth: width
                contentHeight: quotaColumn.implicitHeight
                clip: true
                boundsBehavior: Flickable.StopAtBounds
                flickableDirection: Flickable.VerticalFlick
                Controls.ScrollBar.vertical: Controls.ScrollBar { policy: Controls.ScrollBar.AsNeeded }
                Column {
                    id: quotaColumn
                    width: parent.width - Style.space(8)
                    spacing: Style.space(14)
                    Ui.Dropdown { width: parent.width; label: root.t("provider"); showLabel: false; value: root.dataSource.provider; options: root.providerOptions(); onChanged: function(value) { root.dataSource.filter(root.dataSource.period, value) } }
                    C.Label { width: parent.width; text: root.t("quota_local"); font.pixelSize: Style.font.caption; wrapMode: Text.WordWrap; opacity: 0.65 }
                    Column {
                        visible: !(root.quota.rows || []).length
                        width: parent.width
                        topPadding: Style.space(28)
                        spacing: Style.space(10)
                        C.Label { width: parent.width; text: root.t("quota_empty"); font.pixelSize: Style.space(17); font.weight: Font.Medium }
                        C.Label { width: parent.width; text: root.t("quota_empty_detail"); font.pixelSize: Style.font.caption; wrapMode: Text.WordWrap; opacity: 0.65 }
                    }
                    Repeater {
                        model: root.quota.rows || []
                        Column {
                            id: quotaRow
                            required property var modelData
                            width: quotaColumn.width
                            spacing: Style.space(7)
                            RowLayout { width: parent.width; C.Label { Layout.fillWidth: true; text: quotaRow.modelData.label; font.weight: Font.Medium } C.Label { text: typeof quotaRow.modelData.remaining_percent === "number" ? root.number(quotaRow.modelData.remaining_percent, 0) + "%" : "—" } }
                            Rectangle {
                                width: parent.width; height: Style.space(4); radius: 2; color: Qt.alpha(Commons.Color.popups.text, 0.08)
                                Rectangle { height: parent.height; radius: parent.radius; width: typeof quotaRow.modelData.remaining_percent === "number" ? parent.width * Math.max(0, Math.min(100, quotaRow.modelData.remaining_percent)) / 100 : 0; color: Commons.Color.accent; opacity: 0.75 }
                            }
                            C.Label { width: parent.width; text: quotaRow.modelData.reset_label || quotaRow.modelData.detail || root.t("unknown"); font.pixelSize: Style.font.caption; wrapMode: Text.WordWrap; opacity: 0.6 }
                        }
                    }
                }
            }

            Flickable {
                id: usageScroll
                contentWidth: width
                contentHeight: usageColumn.implicitHeight
                clip: true
                boundsBehavior: Flickable.StopAtBounds
                flickableDirection: Flickable.VerticalFlick
                Controls.ScrollBar.vertical: Controls.ScrollBar { policy: Controls.ScrollBar.AsNeeded }
                Column {
                    id: usageColumn
                    width: parent.width - Style.space(8)
                    spacing: Style.space(14)
                    RowLayout {
                        width: parent.width
                        spacing: Style.space(3)
                        Repeater {
                            model: ["today","7d","30d","all"]
                            C.PanelButton { required property string modelData; Layout.fillWidth: true; label: root.t(modelData); selected: root.dataSource.period === modelData; fontSize: Style.font.caption; onClicked: root.dataSource.filter(modelData, root.dataSource.provider) }
                        }
                    }
                    Ui.Dropdown { width: parent.width; label: root.t("provider"); showLabel: false; value: root.dataSource.provider; options: root.providerOptions(); onChanged: function(value) { root.dataSource.filter(root.dataSource.period, value) } }
                    C.Label { width: parent.width; visible: root.usage.state === "partial" || root.usage.state === "unavailable"; text: root.usage.state === "partial" ? root.t("usage_partial") : root.t("usage_unavailable"); font.pixelSize: Style.font.caption; wrapMode: Text.WordWrap; opacity: 0.65 }
                    GridLayout {
                        width: parent.width
                        columns: width >= Style.space(440) ? 4 : 2
                        columnSpacing: Style.space(8)
                        rowSpacing: Style.space(8)
                        C.MetricCard { Layout.fillWidth: true; Layout.preferredWidth: 1; title: root.t("tokens"); value: root.compact(root.totals.tokens); detail: root.compact(root.totals.input_tokens) + " ↑  " + root.compact(root.totals.output_tokens) + " ↓" }
                        C.MetricCard { Layout.fillWidth: true; Layout.preferredWidth: 1; title: root.t("requests"); value: root.number(root.totals.requests); detail: root.t("failed_count").arg(root.number(root.totals.failures)) }
                        C.MetricCard { Layout.fillWidth: true; Layout.preferredWidth: 1; title: root.t("cost"); value: root.money(root.totals.cost_usd); detail: root.totals.cost_usd === null ? root.t("not_recorded") : root.t("recorded_usd") }
                        C.MetricCard { Layout.fillWidth: true; Layout.preferredWidth: 1; title: root.t("cache"); value: root.percent(root.totals.cache_hit_ratio); detail: root.compact(root.totals.cached_tokens) + " " + root.t("tokens_lower") }
                    }
                    RowLayout {
                        width: parent.width
                        C.Label { Layout.fillWidth: true; text: root.t("activity"); font.weight: Font.DemiBold }
                        Repeater {
                            model: ["tokens","requests","cost_usd"]
                            C.PanelButton { required property string modelData; label: root.t(modelData === "cost_usd" ? "cost" : modelData); selected: root.chartMetric === modelData; fontSize: Style.space(10); horizontalPadding: Style.space(7); verticalPadding: Style.space(4); onClicked: root.chartMetric = modelData }
                        }
                    }
                    C.UsageChart { width: parent.width; buckets: root.usage.buckets || []; metric: root.chartMetric; emptyText: root.chartMetric === "cost_usd" && root.totals.cost_usd === null ? root.t("not_recorded") : root.t("no_activity") }
                    C.Label { width: parent.width; text: root.t("by_provider"); font.weight: Font.DemiBold }
                    C.Label { width: parent.width; visible: !(root.usage.providers || []).length; text: root.t("no_usage"); opacity: 0.6; font.pixelSize: Style.font.caption }
                    Repeater {
                        model: root.usage.providers || []
                        Column {
                            id: providerRow
                            required property var modelData
                            width: usageColumn.width
                            spacing: Style.space(6)
                            RowLayout { width: parent.width; C.Label { Layout.fillWidth: true; text: providerRow.modelData.label; font.weight: Font.Medium } C.Label { text: root.compact(providerRow.modelData.tokens) + "  ·  " + root.money(providerRow.modelData.cost_usd); font.pixelSize: Style.font.caption } }
                            Rectangle {
                                width: parent.width; height: Style.space(3); radius: 1; color: Qt.alpha(Commons.Color.popups.text, 0.06)
                                Rectangle { width: root.totals.tokens > 0 ? parent.width * Math.min(1, providerRow.modelData.tokens / root.totals.tokens) : 0; height: parent.height; radius: 1; color: Commons.Color.accent; opacity: 0.55 }
                            }
                            C.Label { width: parent.width; text: root.t("provider_detail").arg(root.number(providerRow.modelData.requests)).arg(root.number(providerRow.modelData.failures)).arg(root.percent(providerRow.modelData.cache_hit_ratio)); font.pixelSize: Style.space(10); opacity: 0.55 }
                        }
                    }
                }
            }

            Flickable {
                id: routingScroll
                contentWidth: width
                contentHeight: routingColumn.implicitHeight
                clip: true
                boundsBehavior: Flickable.StopAtBounds
                flickableDirection: Flickable.VerticalFlick
                Controls.ScrollBar.vertical: Controls.ScrollBar { policy: Controls.ScrollBar.AsNeeded }
                Column {
                    id: routingColumn
                    width: parent.width - Style.space(8)
                    spacing: Style.space(12)
                    C.Label { width: parent.width; text: root.t("routing_intro"); font.pixelSize: Style.font.caption; wrapMode: Text.WordWrap; opacity: 0.65 }
                    RowLayout { width: parent.width; C.Label { Layout.fillWidth: true; text: root.t("routes_count").arg(root.routes.length); font.weight: Font.DemiBold } C.PanelButton { label: root.t("manage"); fontSize: Style.font.caption; onClicked: root.launchSection("models") } }
                    Repeater {
                        model: root.groups
                        Rectangle {
                            id: groupRow
                            required property var modelData
                            width: routingColumn.width
                            implicitHeight: Style.space(62)
                            radius: Style.space(10)
                            color: Qt.alpha(Commons.Color.popups.text, 0.025)
                            RowLayout {
                                anchors.fill: parent; anchors.margins: Style.space(10)
                                ColumnLayout {
                                    Layout.fillWidth: true
                                    spacing: Style.space(4)
                                    C.Label { Layout.fillWidth: true; text: groupRow.modelData.label; font.weight: Font.Medium }
                                    C.Label { Layout.fillWidth: true; text: root.t("group_detail").arg(groupRow.modelData.strategy).arg(groupRow.modelData.members_count); font.pixelSize: Style.font.caption; opacity: 0.6 }
                                }
                                C.PanelButton { label: root.t("select"); fontSize: Style.font.caption; onClicked: root.routeId = groupRow.modelData.id }
                            }
                        }
                    }
                    C.Label { width: parent.width; visible: !root.groups.length; text: root.t("groups_empty"); font.pixelSize: Style.font.caption; opacity: 0.6 }
                }
            }
        }

        ColumnLayout {
            visible: !!root.snapshot && (root.tab === 0 || root.tab === 3)
            Layout.fillWidth: true
            Layout.minimumWidth: 0
            spacing: Style.space(8)
            Rectangle { Layout.fillWidth: true; implicitHeight: 1; color: Qt.alpha(Commons.Color.popups.text, 0.12) }
            C.Label {
                visible: root.tab === 0
                Layout.fillWidth: true
                text: root.selectedAgent ? root.t("configure_agent").arg(root.selectedAgent.name) : root.t("choose_agent_above")
                font.weight: root.selectedAgent ? Font.DemiBold : Font.Normal
                font.pixelSize: Style.font.caption
                opacity: root.selectedAgent ? 0.9 : 0.6
            }
            Ui.Dropdown {
                visible: root.tab === 3
                Layout.fillWidth: true
                label: root.t("agent")
                value: root.agentId
                options: root.agentOptions()
                activeFocusOnTab: true
                onChanged: function(value) { var selected = root.agents.find(function(row) { return row.id === value }); if (selected) root.chooseAgent(selected) }
            }
            Ui.SearchableDropdown {
                objectName: "agent-route-select"
                Layout.minimumWidth: 0
                visible: root.tab === 3 || !!root.selectedAgent
                activeFocusOnTab: true
                Layout.fillWidth: true
                label: root.t("route")
                value: root.routeId
                options: root.routeOptions()
                placeholderText: root.t("search_routes")
                emptyText: root.t("routes_empty")
                enabled: !root.editing && !!root.routes.length
                onChanged: function(value) { root.routeId = value; root.confirmRevert = false }
            }
            RowLayout {
                visible: root.tab === 3 || !!root.selectedAgent
                Layout.fillWidth: true
                C.Label { Layout.fillWidth: true; text: root.confirmRevert ? root.t("confirm_revert") : root.t("apply_note"); wrapMode: Text.WordWrap; maximumLineCount: 2; font.pixelSize: Style.space(10); opacity: 0.62 }
                C.PanelButton { visible: !!root.selectedAgent && root.selectedAgent.revertible; label: root.confirmRevert ? root.t("confirm") : root.t("revert"); enabled: !root.editing; onClicked: { if (root.confirmRevert) { root.dataSource.perform("agent.revert", {agent:root.agentId}); root.confirmRevert = false } else root.confirmRevert = true } }
                C.PanelButton { label: root.dataSource.actionBusy ? root.t("saving") : root.t("apply"); selected: true; enabled: !root.editing && !!root.selectedAgent && root.selectedAgent.editable && root.routeId !== "" && root.routes.some(function(row) { return row.id === root.routeId }); onClicked: { root.confirmRevert = false; root.dataSource.perform("agent.route", {agent:root.agentId,route:root.routeId}) } }
            }
        }

        RowLayout {
            Layout.fillWidth: true
            C.Label { Layout.fillWidth: true; text: root.snapshot ? root.t("local_snapshot") + (root.gatewayState.version ? " · " + root.gatewayState.version : "") : root.t("local_snapshot"); font.pixelSize: Style.space(10); opacity: 0.5 }
            C.PanelButton { label: root.t("close"); fontSize: Style.font.caption; verticalPadding: Style.space(4); onClicked: root.closeRequested() }
        }
    }
}
