"""Library screens delegate ownership, conflict detection and rollback to zcalld."""
import json
from pathlib import Path


class LibraryScreens:
    def __init__(self, ui):
        self.ui = ui
        self.client = ui.client

    def target(self, kind):
        rows = self.client.action("library.targets").get("targets", [])
        rows = [row for row in rows if not row.get("error")
                and (kind == "all" or row.get(kind) is True)]
        return self.ui.choose("Target agent", [(row["agent"], row["agent"]) for row in rows])

    def apply(self, kind="all", reverting=False):
        target = self.target(kind)
        arguments = ["library", "revert" if reverting else "apply", "--agent", target, "--kind", kind]
        preview = self.client.call([*arguments, "--dry-run"])
        print(json.dumps(preview, ensure_ascii=False, indent=2))
        verb = "Revert" if reverting else "Apply"
        if self.ui.confirm(f"{verb} these {preview.get('changed_files', 0)} file change(s) for {target}?"):
            self.ui.show("Library updated", self.client.call(arguments))

    def item(self, kind):
        return self.ui.items("library." + kind, "sets" if kind == "instructions" else kind,
                             "id" if kind == "instructions" else "name")

    def show(self, kind, content=False):
        item = self.item(kind)
        name = item["id" if kind == "instructions" else "name"]
        action = "read" if kind == "skills" and content else "show"
        self.ui.show(kind.title(), self.client.call(["library", kind, action, name]))

    def state(self, kind, action):
        if kind == "instructions" and action in {"enable", "disable"}:
            arguments = ["library", kind, action, "--agent", self.target(kind)]
        else:
            item = self.item(kind)
            name = item["id" if kind == "instructions" else "name"]
            arguments = ["library", kind, action, name]
            if action == "remove" and not self.ui.confirm(f"Remove {name} from the library?"):
                return
        self.ui.show("Library setting saved", self.client.call(arguments))

    def assign(self, kind):
        if kind == "instructions":
            data = self.client.action("library.instructions")
            arguments = ["library", kind, "assign"]
        else:
            data = self.item(kind)
            arguments = ["library", kind, "assign", data["name"]]
        available = self.client.action("library.targets").get("targets", [])
        print("Supported targets: " + ", ".join(row["agent"] for row in available if row.get(kind)))
        agents = self.ui.input("Agent IDs, comma-separated; empty unassigns",
                               ",".join(data.get("agents") or []), optional=True)
        self.ui.show("Bindings saved", self.client.call([*arguments, "--agents", agents]))

    def import_file(self, kind):
        name = self.ui.input("Entry name" if kind == "mcp" else "Instruction set ID")
        filename = str(Path(self.ui.input("Private JSON file" if kind == "mcp"
                                         else "Instruction text file")).expanduser().resolve())
        self.ui.show("Library saved", self.client.call(["library", kind, "set", name, "--file", filename]))

    def install_skill(self):
        name = self.ui.input("Skill name")
        directory = str(Path(self.ui.input("Reviewed skill directory containing SKILL.md")).expanduser().resolve())
        self.ui.show("Skill installed", self.client.call(["library", "skills", "install", name, "--dir", directory]))

    def kind(self, kind):
        actions = {
            "list": ("Show library entries", lambda: self.ui.show(kind.title(), self.client.action("library." + kind))),
            "show": ("Show entry", lambda: self.show(kind)),
            "enable": ("Enable", lambda: self.state(kind, "enable")),
            "disable": ("Disable", lambda: self.state(kind, "disable")),
            "assign": ("Bind to agents", lambda: self.assign(kind)),
            "apply": ("Preview and apply to an agent", lambda: self.apply(kind)),
            "revert": ("Preview and revert managed agent files", lambda: self.apply(kind, True)),
        }
        if kind == "skills":
            actions.update({
                "install": ("Install a reviewed local directory", self.install_skill),
                "read": ("Read SKILL.md", lambda: self.show(kind, True)),
                "update": ("Update from its recorded local source", lambda: self.state(kind, "update")),
                "remove": ("Remove skill", lambda: self.state(kind, "remove")),
            })
        else:
            actions["set"] = ("Add or edit from a file", lambda: self.import_file(kind))
            if kind == "instructions":
                actions["use"] = ("Select the active instruction set", lambda: self.state(kind, "use"))
            else:
                actions["remove"] = ("Remove MCP entry", lambda: self.state(kind, "remove"))
        self.ui.submenu(kind.title(), actions)

    def run(self):
        self.ui.submenu("Library · MCP, instructions and skills", {
            "summary": ("Overview", lambda: self.ui.show("Library", self.client.action("library"))),
            "mcp": ("MCP servers", lambda: self.kind("mcp")),
            "instructions": ("Shared instructions", lambda: self.kind("instructions")),
            "skills": ("Skills", lambda: self.kind("skills")),
            "targets": ("Supported target capabilities", lambda: self.ui.show("Targets", self.client.action("library.targets"))),
            "apply": ("Preview and apply all bound resources", self.apply),
            "revert": ("Preview and revert all managed resources", lambda: self.apply(reverting=True)),
        })
