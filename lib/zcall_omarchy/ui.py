"""On-demand terminal forms, using Omarchy's existing gum installation."""
import getpass
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

from .core import Client, Error, SERVICE_ACTIONS, text
from .library import LibraryScreens


class Cancel(Exception):
    pass


class UI:
    def __init__(self, client):
        self.client = client
        self.gum = shutil.which("gum")
        if not self.gum:
            raise Error("Omarchy's gum utility is required for interactive forms.")

    def choose(self, title, choices):
        if not choices:
            raise Error("No matching entries are configured.")
        rows = {f"{index + 1:02d}  {text(label)}": key
                for index, (key, label) in enumerate(choices)}
        result = subprocess.run([self.gum, "choose", "--header", title, "--", *rows],
                                stdout=subprocess.PIPE, check=False)
        if result.returncode:
            raise Cancel()
        value = result.stdout.decode().strip()
        if value not in rows:
            raise Cancel()
        return rows[value]

    def input(self, title, value="", optional=False):
        result = subprocess.run([self.gum, "input", "--header", title, "--value", str(value)],
                                stdout=subprocess.PIPE, check=False)
        if result.returncode:
            raise Cancel()
        result = result.stdout.decode().strip()
        if not result and not optional:
            raise Cancel()
        return result

    def confirm(self, question):
        return subprocess.run([self.gum, "confirm", question, "--affirmative", "Apply",
                               "--negative", "Cancel", "--default=false"], check=False).returncode == 0

    def show(self, title, value):
        print("\n" + title + "\n")
        print(json.dumps(value, ensure_ascii=False, indent=2) if isinstance(value, (dict, list)) else value)
        try:
            input("\nEnter to return · Ctrl-C to close ")
        except (EOFError, KeyboardInterrupt):
            raise Cancel() from None

    def changed(self, result):
        if isinstance(result, dict) and result.get("restart_required") is True:
            if self.confirm("Configuration saved. Restart zcalld now to apply it?"):
                result = {"saved": result, "service": self.client.action("service.restart")}
        self.show("Saved", result)

    def items(self, action, field, key="name", predicate=None):
        data = self.client.action(action)
        rows = data.get(field, []) if isinstance(data, dict) else data
        rows = [row for row in rows if isinstance(row, dict) and (predicate is None or predicate(row))]
        chosen = self.choose(field.title(), [
            (index, str(row.get(key, "")) + (" · disabled" if row.get("enabled") is False else ""))
            for index, row in enumerate(rows)])
        return rows[chosen]

    def submenu(self, title, actions):
        while True:
            selected = self.choose(title, [(key, label) for key, (label, _) in actions.items()]
                                   + [("back", "Back")])
            if selected == "back":
                return
            try:
                actions[selected][1]()
            except Cancel:
                pass
            except Error as error:
                self.show("Could not complete the action", str(error))

    def run(self, section="menu"):
        if not sys.stdin.isatty() or not sys.stdout.isatty():
            raise Error("Interactive forms need a terminal. Use 'open' to launch Omarchy's terminal.")
        sections = {
            "status": ("Status", lambda: self.show("Gateway", self.client.action("status"))),
            "service": ("Service", self.service),
            "providers": ("Providers", self.providers),
            "models": ("Models and routes", self.models),
            "agents": ("Agents", self.agents),
            "privacy": ("Privacy", self.privacy),
            "library": ("Library · MCP, instructions and skills", lambda: LibraryScreens(self).run()),
            "plugins": ("Community plugins", self.plugins),
            "accounts": ("Accounts", self.accounts),
            "usage": ("Usage", lambda: self.show("Local usage", self.client.action("usage"))),
            "logs": ("Logs", self.logs),
            "updates": ("Updates", self.updates),
        }
        if section.startswith("service.") and section[8:] in SERVICE_ACTIONS:
            self.service_action(section[8:])
        elif section == "menu":
            self.submenu("Zcall · local AI gateway", sections)
        elif section in sections:
            sections[section][1]()
        else:
            raise Error("Unknown menu section.")

    def service_action(self, action):
        if action in {"stop", "restart", "disable"} and not self.confirm(
                f"{action.title()} the zcalld user service?"):
            raise Cancel()
        self.show("Service", self.client.action("service." + action))

    def service(self):
        self.submenu("Zcall service", {
            action: (label, lambda action=action: self.service_action(action))
            for action, label in [("start", "Start"), ("restart", "Restart"), ("stop", "Stop"),
                                  ("enable", "Start at login"), ("disable", "Disable login start")]
        })

    def provider_edit(self, editing=False, key_only=False):
        item = self.items("providers", "providers") if editing else {}
        name = item.get("name") or self.input("Provider name")
        if not editing and any(p.get("name") == name for p in self.client.action("providers").get("providers", [])):
            raise Error("That provider already exists. Choose Edit provider.")
        url = item.get("base_url", "") if key_only else self.input("HTTP(S) base URL", item.get("base_url", ""))
        protocol = item.get("protocol", "chat") if key_only else self.choose("Protocol", [
            (p, p) for p in ["chat", "responses", "anthropic", "gemini", "completions", "interactions"]])
        prompt = "New API key (blank keeps the current key): " if editing else "API key (blank for no key): "
        secret = getpass.getpass(prompt) or None
        if key_only and secret is None:
            raise Cancel()
        self.changed(self.client.provider(name, url, protocol, secret=secret, edit=editing))

    def provider_remove(self):
        item = self.items("providers", "providers")
        name = item["name"]
        routes = self.client.action("routes").get("routes", [])
        count = sum(route.get("provider") == name for route in routes)
        if self.confirm(f"Remove {text(name)} and its {count} route(s)?"):
            self.changed(self.client.call(["providers", "remove", name]))

    def provider_read(self, action):
        item = self.items("providers", "providers")
        self.show("Provider " + action, self.client.call(["providers", action, item["name"]]))

    def providers(self):
        self.submenu("Providers", {
            "list": ("Show providers", lambda: self.show("Providers", self.client.action("providers"))),
            "add": ("Add provider", self.provider_edit),
            "edit": ("Edit endpoint and protocol", lambda: self.provider_edit(True)),
            "key": ("Change private API key", lambda: self.provider_edit(True, True)),
            "models": ("Discover provider models", lambda: self.provider_read("models")),
            "test": ("Test provider", lambda: self.provider_read("test")),
            "remove": ("Remove provider and routes", self.provider_remove),
        })

    def catalog(self):
        catalog = self.client.action("models")
        rows = catalog.get("data", [])
        selected = self.choose("Public model catalog", [(i, row.get("id", "")) for i, row in enumerate(rows)])
        self.show(rows[selected].get("id", "Model"), rows[selected])

    def route_edit(self):
        name = self.input("Public route name")
        provider = self.items("providers", "providers")["name"]
        model = self.input("Upstream model ID")
        self.changed(self.client.route(name, provider, model))

    def route_remove(self):
        route = self.items("routes", "routes")
        if self.confirm("Remove public route " + text(route["name"]) + "?"):
            self.changed(self.client.call(["routes", "remove", route["name"]]))

    def group_file(self):
        name = self.input("Public group name, such as group/work")
        filename = self.input("Group definition JSON file")
        self.changed(self.client.call(["groups", "set", name, "--file", str(Path(filename).expanduser().resolve())]))

    def models(self):
        self.submenu("Models and routes", {
            "catalog": ("Browse model capabilities", self.catalog),
            "routes": ("Show configured routes", lambda: self.show("Routes", self.client.action("routes"))),
            "set": ("Add or edit route", self.route_edit),
            "remove": ("Remove route", self.route_remove),
            "groups": ("Show model groups", lambda: self.show("Groups", self.client.action("groups"))),
            "group-file": ("Set a group from JSON", self.group_file),
        })

    def agent_apply(self):
        agent = self.items("agents", "agents", predicate=lambda row: row.get("writable") is True)
        route = self.items("routes", "routes")["name"]
        if self.confirm(f"Configure {text(agent['name'])} to use {text(route)} via zcalld?"):
            self.show("Agent configured", self.client.agent(agent["name"], route))

    def agent_revert(self):
        agent = self.items("agents", "agents", predicate=lambda row: row.get("route"))
        if self.confirm("Restore the managed backup for " + text(agent["name"]) + "?"):
            self.show("Agent restored", self.client.call(["agents", "revert", agent["name"]]))

    def agents(self):
        self.submenu("Agents", {
            "list": ("Detected clients and adapter support", lambda: self.show("Agents", self.client.action("agents"))),
            "apply": ("Select an agent and model route", self.agent_apply),
            "revert": ("Revert a managed agent change", self.agent_revert),
        })

    def privacy(self):
        def change(mode):
            if mode == "off" and not self.confirm("Disable privacy filtering for new requests?"):
                raise Cancel()
            self.changed(self.client.call(["privacy", "set", mode]))
        self.submenu("Privacy", {
            "show": ("Current settings and binding", lambda: self.show("Privacy", self.client.action("privacy"))),
            "secrets": ("Filter secrets", lambda: change("secrets")),
            "personal": ("Filter secrets and personal information", lambda: change("personal")),
            "off": ("Disable filtering", lambda: change("off")),
        })

    def plugin_install(self, update=False):
        if update:
            name = self.items("plugins", "plugins")["name"]
            arguments = ["plugins", "update", name]
        else:
            source = self.input("Community Git URL, npm package, or local source")
            name = self.input("Plugin name")
            arguments = ["plugins", "install", source, "--name", name]
        revision = self.input("Pinned Git revision (optional for npm/local)", optional=True)
        version = self.input("Pinned npm version (optional for Git/local)", optional=True)
        checksum = self.input("Expected SHA-256 (use the source's published checksum)", optional=True)
        for key, value in [("--revision", revision), ("--version", version), ("--sha256", checksum)]:
            if value:
                arguments += [key, value]
        if self.confirm(("Update " if update else "Install ") + text(name) + " using these pinned source settings?"):
            self.changed(self.client.call(arguments, timeout=180))

    def plugin_action(self, action):
        name = self.items("plugins", "plugins")["name"]
        arguments = ["plugins", action, name]
        if action == "config":
            arguments += ["--file", str(Path(self.input("Plugin configuration JSON file")).expanduser().resolve())]
        if action == "remove" and not self.confirm("Remove community plugin " + text(name) + "?"):
            raise Cancel()
        self.changed(self.client.call(arguments))

    def plugins(self):
        self.submenu("Community plugins", {
            "list": ("Installed plugins", lambda: self.show("Plugins", self.client.action("plugins"))),
            "install": ("Install a pinned community source", self.plugin_install),
            "update": ("Update a pinned community source", lambda: self.plugin_install(True)),
            "enable": ("Enable plugin", lambda: self.plugin_action("enable")),
            "disable": ("Disable plugin", lambda: self.plugin_action("disable")),
            "config": ("Configure from a private JSON file", lambda: self.plugin_action("config")),
            "providers": ("Show plugin providers", lambda: self.show("Providers", self.client.call(["plugins", "providers"]))),
            "mcp-show": ("Show gateway MCP tools", lambda: self.show("MCP", self.client.action("plugins.mcp"))),
            "mcp-enable": ("Enable gateway MCP tools", lambda: self.changed(self.client.call(["plugins", "mcp", "enable"]))),
            "mcp-disable": ("Disable gateway MCP tools", lambda: self.changed(self.client.call(["plugins", "mcp", "disable"]))),
            "runtime": ("Configure installed compatibility runtime", lambda: self.changed(self.client.call(["plugins", "runtime", "configure"]))),
            "remove": ("Remove plugin", lambda: self.plugin_action("remove")),
        })

    def account_action(self, action):
        account = self.items("accounts", "accounts", key="id")
        if action == "remove" and not self.confirm("Remove account " + text(account["id"]) + "?"):
            raise Cancel()
        self.changed(self.client.call(["accounts", action, account["id"]]))

    def account_import(self):
        provider = self.input("Provider ID")
        filename = str(Path(self.input("Private account import JSON file")).expanduser().resolve())
        self.changed(self.client.call(["accounts", "import", "--provider", provider, "--file", filename]))

    def accounts(self):
        self.submenu("Provider accounts", {
            "list": ("Show accounts and refresh ownership", lambda: self.show("Accounts", self.client.action("accounts"))),
            "import": ("Import a private account file", self.account_import),
            "use": ("Select account", lambda: self.account_action("use")),
            "enable": ("Enable account", lambda: self.account_action("enable")),
            "disable": ("Disable account", lambda: self.account_action("disable")),
            "remove": ("Remove account", lambda: self.account_action("remove")),
        })

    def logs(self):
        command = shutil.which("journalctl")
        if not command:
            raise Error("journalctl is not installed.")
        subprocess.run([command, "--user", "--unit", "zcalld.service", "--no-pager",
                        "--lines", "150", "--output", "short-iso"], check=False)
        self.show("Recent service log", "The view is bounded to 150 records and has no background follower.")

    def updates(self):
        def apply():
            candidate = self.client.action("update.check")
            print(json.dumps(candidate, indent=2, ensure_ascii=False))
            if self.confirm("Apply this zcalld update using its configured installer?"):
                self.client.attached(["update", "apply"])
                self.show("Update completed", self.client.action("status"))
        self.submenu("Updates", {
            "check": ("Check zcalld release", lambda: self.show("Available release", self.client.action("update.check"))),
            "apply": ("Review and apply zcalld update", apply),
            "frontend": ("How to update this Omarchy plugin", lambda: self.show("Frontend updates",
                "Git plugin: omarchy plugin update lightjunction.zcall\n"
                "Arch package: update zcall-omarchy using your AUR helper.\n"
                "Run zcall-omarchy install --apply after an update to refresh only its owned menu rows.")),
        })
