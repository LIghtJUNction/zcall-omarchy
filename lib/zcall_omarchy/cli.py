"""Command-line entry for the Omarchy front end."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

from . import install
from .core import Client, Error, READ_ACTIONS, SERVICE_ACTIONS
from .ui import Cancel, UI


SECTIONS = {"menu", "service", *[row[0] for row in install.SECTIONS],
            *["service." + action for action in SERVICE_ACTIONS]}


def launch(root, section, config=None):
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
        description="Omarchy menus for the existing zcalld CLI; no extra daemon.")
    parser.add_argument("--config", help="Use a specific zcalld configuration")
    parser.add_argument("--version", action="version", version=(root / "VERSION").read_text().strip())
    sub = parser.add_subparsers(dest="command")
    for name in ("open", "menu"):
        p = sub.add_parser(name, help="Open the desktop menu" if name == "open" else "Run terminal forms")
        p.add_argument("section", nargs="?", default="menu", choices=sorted(SECTIONS))
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
        if args.command in (None, "open"):
            launch(root, getattr(args, "section", "menu"), args.config)
            return 0
        if args.command == "menu":
            UI(Client(args.config)).run(args.section)
            return 0
        if args.command == "action":
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
