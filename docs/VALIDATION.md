# Validation record

The initial frontend implementation was validated on the development machine with Omarchy **4.5.0-3**. The tests use disposable homes and do not modify the active Magpie service, provider accounts or agent files.

## Checked behavior

- **19 tests passed:** private stdin, no shell interpretation of arguments, cancellation, menu ownership conflicts, interrupted-install recovery, exact original-menu restoration and preservation of later unrelated menu entries.
- The generated actions passed the **installed Omarchy MenuModel.js parser**, including paths with spaces, quotes and comma-plus-brace characters. This matters because its trailing-comma handling uses a regular expression.
- The **official omarchy-plugin-validate command passed** for this repository.
- The real **Quickshell executable instantiated BarWidget.qml** using the installed Omarchy Ui and Commons modules. The isolated offscreen process checked nonzero dimensions and exited. It did not modify the running desktop shell or install a bar item.
- Three of the 19 tests used the actual zcalld release binary: provider-key persistence through stdin and route/catalog updates; instruction preview, application, edited-block refusal and revert; private MCP listing and preservation of an unrelated MCP server on revert.

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
