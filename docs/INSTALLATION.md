# Installing the two Omarchy entry points

The menu extension and the bar widget are separate integrations. Installing the menu does not silently change the bar. The bar opens a native panel; detailed management uses the same on-demand CLI controller.

## 1. Package, application launcher and menu

Install zcalld 0.2 or newer, then install the `zcall-omarchy` Arch package. Its desktop entry makes **Zcall** visible in the ordinary application launcher.

```sh
yay -S zcall-omarchy
zcall-omarchy install --plan
zcall-omarchy install --apply
```

The reviewed menu plan adds 18 entries in the `zcall` namespace to `~/.config/omarchy/extensions/omarchy-menu.jsonc`. They cover status, five service actions, providers, models, agents, library, privacy, community plugins, accounts, usage, logs and updates. The plan displays the exact generated JSONC block.

Installed actions use the stable package entry `/usr/share/zcall-omarchy/bin/zcall-omarchy`. The private ownership record is `$XDG_STATE_HOME/zcall-omarchy/install.json`, normally `~/.local/state/zcall-omarchy/install.json`, with mode 0600. The existing menu namespace is checked before writing. No keybinding, bar layout, gateway service or agent setting is changed by this installer.

Open **Zcall** in the normal Omarchy menu. The same submenu can be opened with `omarchy-menu summon zcall`.

To reverse only the menu integration:

```sh
zcall-omarchy uninstall --plan
zcall-omarchy uninstall --apply
```

Keep the package until this step is complete. Uninstalling restores an untouched original menu byte for byte, or removes the unchanged managed block while retaining later unrelated entries. It refuses to discard edits inside the managed block.

## 2. Official Git plugin and bar button

Use Omarchy's installed plugin manager:

```sh
omarchy plugin add https://github.com/LIghtJUNction/zcall-omarchy --yes
omarchy plugin enable lightjunction.zcall --section right
```

The first command installs the Git checkout under `~/.config/omarchy/plugins/lightjunction.zcall` and registers its `manifest.json`. The manifest declares a single `bar-widget` entry point, `BarWidget.qml`. It does not replace Omarchy's bar.

The enable command adds the widget to the right-hand section through Omarchy's shell IPC. **This step does change bar configuration:** the installed Omarchy 4.5 implementation persists it in `~/.config/omarchy/shell.json`, under `bar.layout.right`. Its configuration writer serializes JSON, so formatting may change. Existing widget entries and the selected bar remain semantically in place. Back up that file before a coordinated desktop installation if an exact pre-install copy is needed.

Left-click toggles the native Agent / Limits / Usage / Routing panel. Right-click opens full terminal controls. The panel uses Omarchy’s popup positioning and reads a local snapshot when opened or manually refreshed. Closing it does not stop zcalld. It works without the separate menu extension.

The optional widget settings are `config` (an absolute zcalld configuration path) and `language` (`en`, `zh-CN` or `zh-TW`). With no language override, labels follow Omarchy. Changing this plugin setting does not change the desktop language.

Inspect the installed plugin with Omarchy's normal plugin catalog. If the running shell has not completed a rescan, allow it to finish before enabling the new ID; do not modify the shell JSON by hand to bypass registration.

To disable the button while keeping the checkout:

```sh
omarchy plugin disable lightjunction.zcall
```

To remove its registration and checkout through the official manager:

```sh
omarchy plugin remove lightjunction.zcall --yes
```

These operations change the bar through Omarchy's own configuration handling. They do not remove the separate menu extension or application-launcher entry.

## Final removal

Remove the menu block and the optional Git plugin first, then remove the frontend package:

```sh
sudo pacman -R zcall-omarchy
```

The zcalld backend, its accounts, library and agent configuration remain independent.

## Source of the integration contract

This implementation follows the [Omarchy shell plugin documentation](https://github.com/omacom/omarchy/blob/quattro/docs/omarchy-shell.md) and the actual installed Omarchy 4.5 scripts `omarchy-plugin-add`, `omarchy-plugin-enable`, `omarchy-plugin-disable`, `omarchy-plugin-remove` and `PluginRegistry.qml`. The initial validation record distinguishes isolated checks from a live desktop installation.
