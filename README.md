# Zcall for Omarchy

Zcall for Omarchy opens zcalld controls from the Omarchy menu and an optional bar button. It uses the existing terminal for forms and calls the zcalld JSON management CLI. It adds no controller service or polling process.

The gateway remains [zcalld](https://github.com/LIghtJUNction/zcalld). This repository is its second frontend and can also be installed independently. The desktop GUI is optional.

## What you can do

| Screen | Operations |
| --- | --- |
| Status and service | Inspect health; start, stop, restart, enable or disable the user service |
| Providers | Add or edit endpoints and protocols; enter API keys privately; list upstream models |
| Models | Browse the catalog; create aliases; configure model groups from JSON |
| Agents | Apply a gateway route through a supported adapter; revert owned changes |
| Library | Manage MCP servers, instruction sets and skills; bind agents; preview, apply and revert |
| Privacy | Inspect the active filter; select off, secrets or personal-information filtering |
| Plugins | Install pinned community extensions; configure, enable, disable or remove them; manage the MCP endpoint |
| Accounts | Import account files; select, enable, disable or remove existing accounts |
| Usage, logs and updates | Inspect local totals and recent service logs; check or apply gateway updates |

The frontend uses the backend's existing validation and ownership rules. It does not implement provider HTTP requests, account refresh, privacy filtering or agent-file rewriting.

## Requirements

- Omarchy **4.5**, including Quickshell and `gum`.
- Python **3.11 or newer**, using its standard library only.
- zcalld **0.2 or newer**, which provides the JSON management commands.
- Optional: `zcalld-compat` for the backend's community, OAuth, privacy and advanced routing features.

The integration was checked against the installed Omarchy **4.5.0-3** package. It uses the [documented Quickshell plugin and menu-extension contracts](https://github.com/omacom/omarchy/blob/quattro/docs/omarchy-shell.md), not the older Walker menu.

## Install

### Arch package

```sh
yay -S zcall-omarchy
zcall-omarchy install --plan
zcall-omarchy install --apply
```

The package owns files under `/usr/share/zcall-omarchy`, a command at `/usr/bin/zcall-omarchy`, the desktop launcher and its MIT license. Package installation does not edit your home directory.

The second command shows the exact menu addition before the third writes it. The installer adds a `zcall` section to `~/.config/omarchy/extensions/omarchy-menu.jsonc` and saves a small private ownership record under `$XDG_STATE_HOME/zcall-omarchy` (normally `~/.local/state/zcall-omarchy`). It leaves existing menu entries, key bindings and the bar layout in place.

After installation, open **Zcall** in Omarchy's menu, launch **Zcall** from the application launcher, or run:

```sh
zcall-omarchy open
zcall-omarchy open providers
zcall-omarchy open library
```

### Optional native bar button

Omarchy's plugin manager installs the same repository through its normal Git plugin interface:

```sh
omarchy plugin add https://github.com/LIghtJUNction/zcall-omarchy --yes
omarchy plugin enable lightjunction.zcall --section right
```

The button uses Omarchy's existing bar styling. Left-click opens the controls; right-click opens status. Without a menu extension it opens the terminal controller directly. This Git installation does not require the Arch frontend package, but still needs Python, gum and zcalld.

The button has no status timer. Status is queried when opened, so the badge does not imply that the gateway is currently healthy.

### Source checkout

```sh
git clone https://github.com/LIghtJUNction/zcall-omarchy
cd zcall-omarchy
./bin/zcall-omarchy doctor
./bin/zcall-omarchy install --plan
./bin/zcall-omarchy install --apply
```

Keep this checkout at its installed path, or uninstall its menu entries before moving it. The package installation uses a stable path and avoids this requirement.

For the separate menu and official bar registration steps, see [installation and removal](docs/INSTALLATION.md).

## Daily use

Forms open in Omarchy's configured terminal. Cancel before the final apply step to leave configuration unchanged. Destructive service actions ask for confirmation. A saved configuration that needs a restart offers that action separately.

API keys are read with terminal echo disabled and passed to zcalld through standard input. They do not become command arguments or newly created environment variables. Account and MCP imports use local files; the frontend never prints their raw contents. Backend errors from a credential write are withheld if they could echo the private input.

Library application first displays the backend's concrete dry-run result. Apply and revert refuse ownership conflicts; there is no force-overwrite button. Agent provider setup is explicit and separate from library application.

For scripts, selected read operations return JSON:

```sh
zcall-omarchy action status
zcall-omarchy action providers
zcall-omarchy action library.targets
zcall-omarchy --config /path/to/config.conf action models
```

`ZCALLD_CONFIG` and `ZCALLD_BIN` can select a different configuration and executable. The menu installer does not store either variable or copy credentials.

## Remove or recover

Preview and remove only this frontend's menu entries:

```sh
zcall-omarchy uninstall --plan
zcall-omarchy uninstall --apply
```

If the menu has not changed since installation, uninstall restores the original bytes and permissions. If unrelated entries were added later, it removes only its unchanged marked block. If the Zcall block itself was edited, it stops and retains both the file and the private record for review.

An interrupted install can be rerun or uninstalled using that record. Do not delete the record first. Removing menu entries does not stop zcalld or change its accounts and agent settings.

Remove the optional bar integration through Omarchy, then remove the Arch package if installed:

```sh
omarchy plugin remove lightjunction.zcall
sudo pacman -R zcall-omarchy
```

## Development and releases

```sh
python3 scripts/check.py
ZCALLD_TEST_BINARY=/absolute/path/to/zcalld python3 scripts/check.py
python3 scripts/validate-qml.py
python3 scripts/bump.py patch
```

The checks cover private stdin, argument boundaries, cancellation, menu conflicts, interrupted writes and uninstall. Optional tests exercise a real zcalld binary in disposable homes. The QML check loads the widget with installed Omarchy components in an isolated offscreen shell.

Routine CI is manual. GitHub's Bump version workflow also supports patch, minor and major releases and explicitly dispatches the release job. A version tag runs the formal release workflow, produces a source archive and checksums, and publishes the standard AUR recipe when repository secrets are configured. See [releasing](docs/RELEASING.md) and [validation](docs/VALIDATION.md).

## License

MIT. Omarchy and zcalld remain separate projects with their own licenses.
