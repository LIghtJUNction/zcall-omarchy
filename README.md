# zcall for Omarchy

A native bar panel for the [zcalld](https://github.com/LIghtJUNction/zcalld) local AI gateway. Click the bar icon to see agents, saved account limits, usage and routes. Select an agent and a model or group, then apply the change directly in the panel.

The panel uses Omarchy's theme, keyboard focus and popup positioning. It reads local data when opened or refreshed; it has no polling loop or separate background service. Closing it leaves the gateway running. The independent desktop GUI is optional.

## Four views

| View | What it shows and does |
| --- | --- |
| **Agents** | Installed clients, their saved gateway route, an explicit **Apply** action and recovery of owned changes. Detection-only adapters remain read-only. |
| **Limits** | Saved quota readings and an explicit **Update** button for accounts that support quota queries. Missing or expired readings remain unavailable. Opening the view does not contact providers. |
| **Usage** | Today, 7 days, 30 days or all history; provider filtering; token, request, cost and cache summaries; a native bar chart and provider rows. |
| **Routing** | Existing route groups and their strategies. Choose a model or group and apply it to a particular agent. There is no invented global-default setting. |

**Refresh local data** rereads the local snapshot. It does not ask providers for a new quota reading. Usage is calculated from the existing history file with bounded working memory. A partial scan is labelled. Costs use recorded amounts or saved model prices and show how many requests could be priced. A partial known amount is labelled as such; an estimate is not a provider bill. Unknown prices, cache splits and unsupported billing tiers remain unpriced. “Today” uses the local calendar day; 7 and 30 days include today.

The top-right **Open** button focuses the optional desktop GUI if it is already running, or launches it with a bounded startup lock. When the GUI is absent, it opens the full controls. The **More** menu opens the existing terminal controls for service management, providers, accounts, library, privacy, plugins, logs and updates. Right-clicking the bar icon opens those full controls directly.

## Install the native panel

Requirements are Omarchy **4.5**, Python **3.11+**, and zcalld **0.2+**. Python uses only its standard library. Omarchy supplies Quickshell, the UI components, the configured terminal and `gum`. The optional `zcalld-compat` package provides the backend's community, OAuth, privacy and advanced-routing capabilities. Explicit quota updates require its quota capability (available from **0.1.6**); older helpers retain saved readings and show how to enable updates.

Register the frontend through Omarchy's Git plugin manager:

```sh
omarchy plugin add https://github.com/LIghtJUNction/zcall-omarchy --yes
omarchy plugin enable lightjunction.zcall --section right
```

Enabling the plugin adds a widget through Omarchy's own bar configuration. It retains other widget entries and keybindings. The panel follows the current theme and display language, with English, Simplified Chinese and Traditional Chinese strings. Its optional `language` setting overrides only this plugin (`en`, `zh-CN` or `zh-TW`). The native popup handles outside-click dismissal, other open panels and the available screen edges.

### Arch package and terminal menu

The AUR package adds the command and application launcher. The optional menu installer adds a separate **Zcall** section to Omarchy's normal menu:

```sh
yay -S zcall-omarchy
zcall-omarchy install --plan
zcall-omarchy install --apply
```

Package installation owns `/usr/share/zcall-omarchy`, the command at `/usr/bin/zcall-omarchy`, the desktop launcher and the MIT license. It does not edit a home directory from a package hook. The native bar plugin and the menu extension are independently removable; installing the package alone does not silently enable a widget.

```sh
zcall-omarchy show            # Native panel; terminal fallback if it is unavailable
zcall-omarchy open            # Full terminal/menu controls
zcall-omarchy open providers
zcall-omarchy open library
```

For exact registration, preview, backup and removal steps, see [installation](docs/INSTALLATION.md).

## Use the panel

- **Left click** opens or closes the panel. **Right click** opens full controls.
- **Tab / Shift+Tab** move focus between controls; **Enter / Space** activate a focused button.
- **Ctrl+Tab / Ctrl+Shift+Tab** switch the four views. **Ctrl+R** refreshes local data. **Escape** dismisses the current menu or closes the panel.
- In **Agents**, choose **Change**, select a route and press **Apply**. The saved agent configuration changes through zcalld's existing adapter. Reload or restart that agent when prompted; the panel does not restart it or the gateway.
- **Revert** requires a second explicit confirmation and delegates to the backend's ownership checks. It does not force an overwrite of user edits.
- In **Limits**, **Update** queries only the selected supported account. It never falls back to another account. A timeout preserves the saved reading and offers a clear retry action. Closing the panel lets the submitted update finish; it does not restart or repeat it.

The usage and quota views are snapshots. They are not a live monitor, a billing statement or proof that every configured provider is currently reachable. Provider filtering includes identities present in historical usage or cached quotas, so its options are not a count of currently configured providers.

## Full controls

The existing terminal forms remain available for detailed work:

| Area | Operations |
| --- | --- |
| Service | Health, start, stop, restart, enable and disable the user service |
| Providers and models | Endpoints, protocols, private API keys, model catalog, aliases and group configuration |
| Library | MCP servers, instructions and skills; agent bindings; preview, apply and revert |
| Privacy and plugins | Privacy settings; pinned community extensions; MCP endpoint settings |
| Accounts | Import, select, enable, disable and remove accounts through the backend's account store |
| Logs and updates | Local service journal and explicit update checks or installation |

API keys are entered without terminal echo and passed through standard input. They do not become command arguments or new environment variables. Detailed library changes first show the backend's dry-run result. Unsupported adapters and ownership conflicts remain visible errors.

The frontend does not implement provider transport, OAuth refresh, masking or agent-file rewriting. Those remain in zcalld and its optional plugins.

## Scripts and custom configurations

The panel's local JSON boundary is also available for inspection:

```sh
zcall-omarchy panel snapshot --period 7d --provider all
zcall-omarchy panel action agent.route --payload '{"agent":"codex","route":"daily"}'
zcall-omarchy panel action agent.revert --payload '{"agent":"codex"}'
# Use an opaque account ID returned by the local snapshot:
zcall-omarchy panel action quota.refresh --payload '{"account":"ACCOUNT_ID"}'
zcall-omarchy action status
zcall-omarchy --config /path/to/config.conf action models
```

Actions are explicit mutations. Snapshot reads do not send generation requests or refresh real provider accounts. `ZCALLD_CONFIG`, `ZCALLD_BIN`, or `--config` select the backend configuration and executable. A custom `--config` passed to `show` opens the terminal controller rather than reusing a panel bound to another configuration. The bar plugin also accepts an optional `config` setting.

## Remove or recover

```sh
zcall-omarchy uninstall --plan
zcall-omarchy uninstall --apply
omarchy plugin remove lightjunction.zcall --yes
sudo pacman -R zcall-omarchy
```

Remove the menu integration before deleting its package or checkout. If that menu has not changed since installation, uninstall restores the original bytes and permissions. If unrelated entries were added later, it removes only its unchanged marked block. An edited Zcall block is preserved for review.

The private ownership record lives under `$XDG_STATE_HOME/zcall-omarchy`, normally `~/.local/state/zcall-omarchy`. Keep it until uninstall or recovery completes. Removing either frontend entry leaves gateway accounts, agent settings and service state independent.

## Development and releases

```sh
python3 scripts/check.py
ZCALLD_TEST_BINARY=/absolute/path/to/zcalld python3 scripts/check.py
python3 scripts/validate-qml.py
python3 scripts/validate-panel-state.py
python3 scripts/preview-panel.py --output /tmp/zcall-panel-preview --theme dark
python3 scripts/bump.py patch
```

The native checks use installed Omarchy modules. The preview renders synthetic data in a separate, short-lived Wayland window and does not execute the controller. The lifecycle check uses a fake subprocess to verify lazy loading, rapid filter changes, action completion after closing and error handling. See [validation](docs/VALIDATION.md) and [integration contracts](docs/INTEGRATION.md).

Routine CI is manual. The **Bump version** workflow supports patch, minor and major versions, then explicitly dispatches the release workflow. Formal releases check the portable tests and publish a source archive, checksums and the standard AUR recipe. Existing tags are not overwritten. See [releasing](docs/RELEASING.md).

## License

MIT. Omarchy and zcalld are separate projects with their own licenses.
