"""Command-line entry for the Omarchy front end."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

from . import install, backend, desktop
from .core import Client, Error, READ_ACTIONS, SERVICE_ACTIONS
from .ui import Cancel, UI


SECTIONS = {"menu", "service", "gui", *[row[0] for row in install.SECTIONS],
            *["service." + action for action in SERVICE_ACTIONS]}


def launch(root, section, config=None):
    if section == "gui":
        if not config and desktop.open_gui():
            return
        section = "menu"
    if section not in SECTIONS:
        raise Error("Unknown menu section.")
    if section == "menu" and not config and install.menu_is_installed():
        command = shutil.which("omarchy-menu")
        if command:
            os.execv(command, [command, "summon", "zcall"])
    terminal = shutil.which("omarchy-launch-terminal")
    if not terminal:
        raise Error("Omarchy's terminal launcher is unavailable. Run zcall-omarchy menu in a terminal.")
    arguments = [terminal, str(root / "bin/zcall-omarchy")]
    if config:
        arguments += ["--config", config]
    arguments += ["menu", section]
    os.execv(terminal, arguments)


def show_panel(root, config=None):
    """Use the registered native panel; keep terminal access when unavailable."""
    command = shutil.which("omarchy-shell")
    if command and not config:
        try:
            result = subprocess.run([command, "shell", "summon", "lightjunction.zcall", "{}"],
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=4, check=False, text=True)
            if result.returncode == 0 and result.stdout.strip() == "ok":
                return
        except (OSError, subprocess.TimeoutExpired):
            pass
    launch(root, "menu", config)


def doctor(root, config):
    tools = {name: shutil.which(name) for name in
             ["zcalld", "gum", "omarchy-menu", "omarchy-launch-terminal", "omarchy-plugin-validate"]}
    version = None
    command = shutil.which("omarchy-version")
    if command:
        try:
            version = subprocess.run([command], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                     timeout=5, check=False).stdout.decode().strip()
        except (OSError, subprocess.TimeoutExpired):
            pass
    result = {"frontend_version": (root / "VERSION").read_text().strip(),
              "omarchy_version": version, "tools": tools,
              "menu_installed": install.menu_is_installed(),
              "plugin_id": "lightjunction.zcall", "background_process": False}
    try:
        result["gateway"] = Client(config).action("status")
    except Error as error:
        result["gateway_error"] = str(error)
    return result


def main(root):
    parser = argparse.ArgumentParser(prog="zcall-omarchy",
        description="Native Omarchy panel and controls for zcalld; no extra daemon.")
    parser.add_argument("--config", help="Use a specific zcalld configuration")
    parser.add_argument("--version", action="version", version=(root / "VERSION").read_text().strip())
    sub = parser.add_subparsers(dest="command")
    for name in ("open", "menu"):
        p = sub.add_parser(name, help="Open the desktop menu" if name == "open" else "Run terminal forms")
        p.add_argument("section", nargs="?", default="menu", choices=sorted(SECTIONS))
    sub.add_parser("show", help="Open the native bar panel, with terminal fallback")
    panel = sub.add_parser("panel", help="Bounded local JSON interface for the native panel")
    panels = panel.add_subparsers(dest="panel_command", required=True)
    p = panels.add_parser("snapshot")
    p.add_argument("--period", choices=["today", "7d", "30d", "all"], default="today")
    p.add_argument("--provider", default="all")
    p = panels.add_parser("action")
    p.add_argument("name", choices=["agent.route", "agent.revert", "quota.refresh"])
    p.add_argument("--payload", required=True)
    p = sub.add_parser("action", help="Run one existing controller action and print its JSON result")
    p.add_argument("name", choices=sorted({*READ_ACTIONS, *["service." + x for x in SERVICE_ACTIONS]}))
    for name in ("install", "uninstall"):
        p = sub.add_parser(name, help="Preview or apply the isolated menu integration")
        group = p.add_mutually_exclusive_group()
        group.add_argument("--apply", action="store_true")
        group.add_argument("--plan", action="store_true", help="Default: show changes without writing")
    sub.add_parser("doctor", help="Inspect local capabilities without a generation request")
    args = parser.parse_args()
    try:
        if args.command in (None, "show"):
            show_panel(root, args.config)
            return 0
        if args.command == "open":
            launch(root, args.section, args.config)
            return 0
        if args.command == "menu":
            UI(Client(args.config)).run(args.section)
            return 0
        if args.command == "panel":
            client = Client(args.config)
            if args.panel_command == "snapshot":
                value = backend.snapshot(client, args.period, args.provider)
            else:
                if len(args.payload.encode()) > 4096:
                    raise Error("Panel action payload is too large.")
                try:
                    payload = json.loads(args.payload)
                except ValueError:
                    raise Error("Panel action payload must be a JSON object.") from None
                value = backend.action(client, args.name, payload)
        elif args.command == "action":
            value = Client(args.config).action(args.name)
        elif args.command == "doctor":
            value = doctor(root, args.config)
        elif args.command == "install":
            value = install.install(root / "bin/zcall-omarchy", args.apply)
        elif args.command == "uninstall":
            value = install.uninstall(args.apply)
        else:
            parser.error("unknown command")
        print(json.dumps(value, ensure_ascii=False, indent=2))
        return 0
    except (Cancel, KeyboardInterrupt):
        return 0
    except (Error, OSError) as error:
        print("zcall-omarchy: " + str(error), file=sys.stderr)
        return 1
