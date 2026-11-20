# Omarchy integration contract

zcall-omarchy is a second front end for zcalld. It owns panel and menu presentation and delegates gateway state to the zcalld CLI. It does not open a network listener, create a service, poll provider accounts or implement provider transport.

## Verified platform

The initial integration was inspected against the installed Arch package `omarchy 4.5.0-3`. The package version comes from `pacman -Q omarchy`; its legacy source `version` file is not used as the compatibility check.

The inspected official interfaces are:

| Interface | Use |
| --- | --- |
| Root `manifest.json`, schemaVersion 1 | Discover a third-party Git plugin |
| `qs.Ui.BarWidget` and `BarIconButton` | Reuse the desktop's widget layout, theme and interaction |
| `qs.Ui.Panel` and `KeyboardPanel` | Native popup ownership, keyboard focus, dismissal and screen bounds |
| `qs.Commons.Translations`, `Color` and `Style` | Theme and translated labels, with a plugin-only language override |
| `omarchy-hyprland-focus-app` | Focus an existing optional GUI before starting one |
| `omarchy plugin add/enable/disable/remove` | Let Omarchy manage the optional bar entry |
| `omarchy-menu summon ROUTE` | Open the built-in menu at the Zcall route |
| `~/.config/omarchy/extensions/omarchy-menu.jsonc` | Add isolated `zcall.*` menu rows |
| `omarchy-launch-terminal COMMAND...` | Open interactive forms and detailed output in the configured terminal |
| `gum` | Choose entries, confirm a concrete change and collect nonsecret fields |
| `zcalld ... --json` | Read and modify gateway configuration through its existing controller |

The plugin ID is `lightjunction.zcall`. It declares a bar widget, with no service entry point and no polling timer. Left-click opens the native panel; right-click opens the existing full controls. It does not replace `omarchy.menu`, change default key bindings, or install an autostart process.

## Installation boundaries

The official Git installation remains available:

```sh
omarchy plugin add https://github.com/LIghtJUNction/zcall-omarchy.git
omarchy plugin enable lightjunction.zcall --section right
```

The independent menu installer adds only its marked `zcall.*` rows. It must preserve unrelated JSONC entries and comments, reject an existing conflicting namespace, preview its exact managed addition, and remove only that owned block during uninstall. User changes made after installation must survive removal.

The bar plugin and menu extension can be removed independently. Normal package installation places the controller under standard system paths; it never edits another user's home directory from a package hook.

## Controller boundaries

Every child process is invoked with an argument list, not a constructed shell command. API keys are collected without echo and passed only through the zcalld `--api-key-stdin` pipe. They are never placed in argv, environment variables, menu actions, installer state, or logs.

Read-only screens use existing JSON commands. Provider edits, route edits, privacy settings and community plugin operations use their existing CLI commands. Agent configuration is changed only after the user selects the agent and route and confirms the concrete action. An unsupported/detect-only agent remains viewable without inventing a provider adapter.

The panel runs finite, asynchronous local subprocesses when opened, refreshed or explicitly applied. Rapid filter changes coalesce to the newest choice; older output cannot replace it. Closing the panel does not cancel a submitted agent change or start another read. An already-running finite read can finish. The terminal controller exits when closed. Detailed error output belongs in that terminal; the bar does not retain raw credentials or request content.

## Sources

- [Official shell and plugin reference](https://github.com/omacom/omarchy/blob/quattro/docs/omarchy-shell.md)
- [Official menu extension sample](https://github.com/omacom/omarchy/blob/quattro/config/omarchy/extensions/omarchy-menu.jsonc)
- [Official plugin validator](https://github.com/omacom/omarchy/blob/quattro/bin/omarchy-plugin-validate)
- [Official menu launcher](https://github.com/omacom/omarchy/blob/quattro/bin/omarchy-menu)
- [zcalld controller source](https://github.com/LIghtJUNction/zcalld/blob/main/src/control.rs)

Implementation and validation results are recorded separately; this document describes the verified integration surface and ownership boundaries.

## Local panel boundary

The panel snapshot command returns schema version 1. It contains whitelisted
status, provider filter choices, agents, routes, groups, usage aggregates and
cached quota readings. Raw account files, request messages, API keys and provider
URLs are not forwarded to QML.

The agent.route and agent.revert actions validate current capabilities before
delegating to the existing controller. They do not restart an agent or gateway.
No automatic retry follows a failed mutation.

Every dynamic Text uses PlainText. Labels passed into shared shell controls are
also neutralized before presentation. The panel keeps a bounded number of local
rows and chart buckets; the backend streams usage history rather than loading
the complete log into memory.

The optional GUI activation uses Omarchy's focus helper with the exact zcall
window identity, followed by a private runtime flock during bounded startup.
This prevents repeated clicks from creating simultaneous launches. It adds no
persistent lock holder; a missing GUI falls back to the full controls.
