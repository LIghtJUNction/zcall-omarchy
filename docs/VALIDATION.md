# Validation record

## Native panel (0.2)

The final local controller gate passed **73 tests with no skips**, including installed zcalld operations inside disposable homes.

The panel uses the installed Omarchy 4.5 `Ui.Panel`, `Ui.KeyboardPanel`, dropdowns and theme modules. The isolated native check opens the actual widget on each of the four bar edges and verifies that the card stays within its anchor screen. It checks the top-level host owner, lazy loading, Ctrl+Tab, Ctrl+R, Escape and focus after closing and reopening. The keyboard path opens a provider selector, searches and applies an Agent route, confirms Revert, updates one synthetic quota, and handles a second synthetic quota timeout. Four opens, manual refresh and successful writes execute exactly eight snapshots and four explicit fake actions, without retries. This checks the native host contract; it is not a claim of a manual multi-monitor desktop trial.

A separate process-lifecycle fixture verifies that a closed panel does not read data, rapid filter changes keep the latest result, an explicit action is submitted once, closing does not repeat or cancel an already submitted quota update, and a missing executable produces an error. No timer polls the gateway.

The actual QML content has been rendered with synthetic data at 560×680 and 360×580 logical pixels, in dark and light themes, with Simplified and Traditional Chinese overrides. The narrow preview asserts that all four tabs remain inside the panel. Names and messages use plain text. Agent selection has one route picker and explicit Apply/Revert controls; the backend tests run those operations against an installed zcalld binary in disposable homes, including refusal to overwrite user edits.

GUI activation tests cover focusing an existing window, the private bounded startup lock, safe argv, missing-GUI terminal fallback and rejection of an unsafe lock directory. These tests do not open or change a user's running GUI.

```sh
ZCALLD_TEST_BINARY=/absolute/path/to/zcalld python3 -B scripts/check.py
python3 -B scripts/validate-panel-state.py
python3 -B scripts/validate-qml.py
python3 -B scripts/preview-panel.py --output /tmp/zcall-preview --theme dark --plugin-language zh-CN
python3 -B scripts/preview-panel.py --output /tmp/zcall-narrow --theme light --width 360 --height 580 --plugin-language zh-TW
```

The popup and preview checks require a live Wayland display and installed Omarchy modules. They start a separate short-lived test surface, use temporary configuration directories, and never install a widget or call a real provider. The portable release workflow runs the Python tests and official manifest validation when available; it does not stand in for these native desktop checks.

## Initial menu frontend (0.1)

The initial frontend implementation was validated on the development machine with Omarchy **4.5.0-3**. The tests use disposable homes and do not modify the active Magpie service, provider accounts or agent files.

## Checked behavior

- **23 tests passed:** private stdin, no shell interpretation of arguments, cancellation, menu ownership conflicts, interrupted-install recovery, exact original-menu restoration and preservation of later unrelated menu entries.
- The generated actions passed the **installed Omarchy MenuModel.js parser**, including paths with spaces, quotes and comma-plus-brace characters. This matters because its trailing-comma handling uses a regular expression.
- The **official omarchy-plugin-validate command passed** for this repository.
- The real **Quickshell executable instantiated BarWidget.qml** using the installed Omarchy Ui and Commons modules. The isolated offscreen process checked nonzero dimensions and exited. It did not modify the running desktop shell or install a bar item.
- Three of the 23 tests used the actual zcalld release binary: provider-key persistence through stdin and route/catalog updates; instruction preview, application, edited-block refusal and revert; private MCP listing and preservation of an unrelated MCP server on revert.

Four additional fixtures use actual temporary Git remotes: failed-check rollback, confirmed failed-push rollback, retained publication after a lost acknowledgement, and refusal to overwrite an existing tag.

The frontend's menu transaction restores original bytes when the installed file is otherwise unchanged. Library operations delegate their ownership rules to zcalld: the backend removes the managed instruction block and preserves user text and surrounding separator whitespace. These are distinct contracts.

## What this does not claim

The initial gate does not claim a live user-desktop installation, a visual review of every terminal form, or a gateway inference benchmark. It does not send provider-generation requests or refresh real OAuth accounts. Integration smoke tests run in temporary homes; service mutation commands are covered at the argv boundary and are left to the reviewed installation.

## Reproduce

```sh
python3 scripts/check.py
ZCALLD_TEST_BINARY=/absolute/path/to/zcalld python3 scripts/check.py
python3 scripts/validate-qml.py
```

Without a real binary, the three native integration tests report skips. Without an installed Omarchy parser, its parser-specific test reports a skip. The QML check requires Omarchy and Quickshell and fails clearly when they are missing.

The source release workflow rechecks the portable frontend tests. Local native results and the supported Omarchy interface are documented separately so a successful portable workflow is not mistaken for native desktop execution.
