import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import shlex
import shutil
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))
from zcall_omarchy import install, cli
from zcall_omarchy.core import Client, Error
from zcall_omarchy.library import LibraryScreens
from zcall_omarchy.ui import UI, Cancel


class Home(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="zcall-omarchy-test-")
        self.home = Path(self.temp.name)
        self.env = patch.dict(os.environ, {"HOME": str(self.home),
            "XDG_CONFIG_HOME": str(self.home / ".config"),
            "XDG_STATE_HOME": str(self.home / ".local/state")})
        self.env.start()
        self.refresh = patch.object(install, "refresh", return_value=True)
        self.refresh.start()

    def tearDown(self):
        self.refresh.stop()
        self.env.stop()
        self.temp.cleanup()

    def menu(self, source):
        menu, _ = install.paths()
        menu.parent.mkdir(parents=True, exist_ok=True)
        menu.write_text(source)
        menu.chmod(0o640)
        return menu


class MenuTransaction(Home):
    def test_preview_writes_nothing_and_uninstall_restores_exact_original(self):
        original = '{\n  // my note stays\n  "personal": {"label": "x,} URL://keep"},\n}\n'
        menu = self.menu(original)
        plan = install.install(ROOT / "bin/zcall-omarchy")
        self.assertTrue(plan["changed"])
        self.assertIn("zcall.library", plan["menu_entries"])
        self.assertEqual(menu.read_text(), original)
        self.assertFalse(install.paths()[1].exists())
        install.install(ROOT / "bin/zcall-omarchy", True)
        after = menu.read_bytes()
        self.assertIn(b"// my note stays", after)
        self.assertEqual(install.parse_jsonc(menu.read_text())["personal"]["label"], "x,} URL://keep")
        self.assertEqual(install.paths()[1].stat().st_mode & 0o777, 0o600)
        self.assertFalse(install.install(ROOT / "bin/zcall-omarchy", True)["changed"])
        self.assertEqual(menu.read_bytes(), after)
        install.uninstall(True)
        self.assertEqual(menu.read_text(), original)
        self.assertEqual(menu.stat().st_mode & 0o777, 0o640)

    def test_uninstall_keeps_entries_added_after_install(self):
        menu = self.menu('{"personal": {"label":"Keep"}}\n')
        install.install(ROOT / "bin/zcall-omarchy", True)
        source = menu.read_text()
        closing = source.rfind("}")
        source = "// later user note\n" + source[:closing] + ',\n"new": {"label":"Later"}\n' + source[closing:]
        menu.write_text(source)
        install.uninstall(True)
        self.assertTrue(menu.read_text().startswith("// later user note"))
        self.assertEqual(set(install.parse_jsonc(menu.read_text())), {"personal", "new"})

    def test_uninstall_empty_original_preserves_a_later_entry(self):
        install.install(ROOT / "bin/zcall-omarchy", True)
        menu = install.paths()[0]
        source = menu.read_text()
        closing = source.rfind("}")
        menu.write_text(source[:closing] + ',\n"later":{"label":"User entry"}\n' + source[closing:])
        install.uninstall(True)
        self.assertEqual(install.parse_jsonc(menu.read_text()),
                         {"later": {"label": "User entry"}})

    def test_conflicting_namespace_and_duplicate_keys_are_rejected_without_writes(self):
        for original in ['{"zcall":{"label":"Mine"}}\n', '{"x":1,"x":2}\n']:
            menu = self.menu(original)
            with self.assertRaises(Error):
                install.install(ROOT / "bin/zcall-omarchy", True)
            self.assertEqual(menu.read_text(), original)
            self.assertFalse(install.paths()[1].exists())

    def test_user_edit_inside_owned_block_is_not_discarded(self):
        menu = self.menu("{}\n")
        install.install(ROOT / "bin/zcall-omarchy", True)
        changed = menu.read_text().replace("Local AI gateway", "My private menu")
        menu.write_text(changed)
        with self.assertRaises(Error):
            install.uninstall(True)
        self.assertEqual(menu.read_text(), changed)

    def test_interrupted_write_can_be_reverted_from_private_journal(self):
        original = '{"personal":{"label":"Keep"}}\n'
        menu = self.menu(original)
        atomic = install.atomic
        def fail_menu(path, data, mode=0o600):
            if path == menu:
                raise OSError("fixture interrupted write")
            return atomic(path, data, mode)
        with patch.object(install, "atomic", side_effect=fail_menu):
            with self.assertRaises(OSError):
                install.install(ROOT / "bin/zcall-omarchy", True)
        self.assertEqual(menu.read_text(), original)
        install.uninstall(True)
        self.assertEqual(menu.read_text(), original)
        self.assertFalse(install.paths()[1].exists())

    def test_new_install_uninstall_removes_only_the_created_menu(self):
        menu, _ = install.paths()
        install.install(ROOT / "bin/zcall-omarchy", True)
        self.assertTrue(menu.exists())
        install.uninstall(True)
        self.assertFalse(menu.exists())

    def test_generated_actions_survive_actual_omarchy_jsonc_parser(self):
        model = Path("/usr/share/omarchy/shell/plugins/menu/MenuModel.js")
        node = shutil.which("node")
        if not model.is_file() or not node:
            self.skipTest("Installed Omarchy menu parser and Node are optional")
        entry = self.home / "odd ,} , ] '$ ; space" / "bin/zcall-omarchy"
        plan = install.install(entry)
        generated = "{" + plan["addition"] + "}"
        script = ("const m=require(process.argv[1]);"
                  "const fs=require('fs');"
                  "process.stdout.write(m.stripJsonc(fs.readFileSync(0,'utf8')))")
        result = subprocess.run([node, "-e", script, str(model)], input=generated.encode(),
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
        rows = json.loads(result.stdout)
        self.assertEqual(shlex.split(rows["zcall.status"]["action"]),
                         [str(entry), "open", "status"])
        self.assertEqual(shlex.split(rows["zcall.library"]["action"]),
                         [str(entry), "open", "library"])

    def test_symlink_menu_is_not_replaced(self):
        target = self.home / "external.json"
        target.write_text("{}\n")
        menu, _ = install.paths()
        menu.parent.mkdir(parents=True)
        menu.symlink_to(target)
        with self.assertRaises(Error):
            install.install(ROOT / "bin/zcall-omarchy")
        self.assertEqual(target.read_text(), "{}\n")
        self.assertTrue(menu.is_symlink())


class ControllerBoundary(Home):
    def setUp(self):
        super().setUp()
        self.log = self.home / "child.json"
        self.binary = self.home / "zcalld-fixture"
        self.binary.write_text("#!" + sys.executable + "\n" + """
import json,os,sys
from pathlib import Path
secret=sys.stdin.read().rstrip("\\n")
Path(os.environ["FIXTURE_LOG"]).write_text(json.dumps({"argv":sys.argv[1:],"stdin":secret,
 "secret_in_environment":bool(secret) and any(secret in value for value in os.environ.values())}))
mode=os.environ.get("FIXTURE_MODE","ok")
if mode=="stderr":
 print(secret,file=sys.stderr);sys.exit(1)
print(json.dumps({"echo":secret} if mode=="echo" else {"ok":True}))
""")
        self.binary.chmod(0o755)
        self.flags = patch.dict(os.environ, {"FIXTURE_LOG": str(self.log), "FIXTURE_MODE": "ok"})
        self.flags.start()
        self.client = Client(config=self.home / "config with spaces.conf", binary=self.binary)

    def tearDown(self):
        self.flags.stop()
        super().tearDown()

    def test_api_key_uses_only_private_stdin(self):
        secret = 'fixture-key-"quote"-\\slash'
        self.client.provider("fixture", "https://example.invalid/v1", "chat", secret)
        observed = json.loads(self.log.read_text())
        self.assertEqual(observed["stdin"], secret)
        self.assertFalse(observed["secret_in_environment"])
        self.assertNotIn(secret, json.dumps(observed["argv"]))
        self.assertIn("--api-key-stdin", observed["argv"])

    def test_private_echo_or_failure_diagnostic_is_withheld(self):
        secret = 'fixture-"quote"-\\slash'
        for mode in ["echo", "stderr"]:
            with patch.dict(os.environ, {"FIXTURE_MODE": mode}):
                with self.assertRaises(Error) as caught:
                    self.client.provider("fixture", "https://example.invalid", "chat", secret)
                self.assertNotIn(secret, str(caught.exception))
                self.assertEqual(json.loads(self.log.read_text())["stdin"], secret)

    def test_argument_metacharacters_are_literal_and_global_options_are_rejected(self):
        sentinel = self.home / "must-not-exist"
        model = f"model; touch {sentinel}"
        self.client.route("fixture/alias", "fixture", model)
        self.assertIn(model, json.loads(self.log.read_text())["argv"])
        self.assertFalse(sentinel.exists())
        for value in ["--config", "-c", "--json", "bad\0value"]:
            with self.assertRaises(Error):
                self.client.route(value, "fixture", "model")

    def test_cancelled_provider_form_does_not_write(self):
        with patch("zcall_omarchy.ui.shutil.which", return_value="/fixture/gum"):
            ui = UI(Mock())
        ui.input = Mock(side_effect=Cancel)
        with self.assertRaises(Cancel):
            ui.provider_edit()
        ui.client.provider.assert_not_called()

    def test_open_uses_native_terminal_argv_without_a_shell(self):
        with patch("zcall_omarchy.cli.shutil.which", return_value="/fixture/terminal"), \
             patch("zcall_omarchy.cli.os.execv", side_effect=RuntimeError("fixture exec")) as execute:
            with self.assertRaises(RuntimeError):
                cli.launch(ROOT, "status", "/tmp/config with spaces")
        self.assertEqual(execute.call_args.args[1], ["/fixture/terminal", str(ROOT / "bin/zcall-omarchy"),
                                                   "--config", "/tmp/config with spaces", "menu", "status"])


class LibraryFlow(unittest.TestCase):
    def test_cancelled_apply_only_requests_a_preview(self):
        ui = Mock()
        ui.client.action.return_value = {"targets": [{"agent": "codex", "instructions": True}]}
        ui.choose.return_value = "codex"
        ui.client.call.return_value = {"changed_files": 1, "paths": ["/fixture/AGENTS.md"]}
        ui.confirm.return_value = False
        with contextlib.redirect_stdout(io.StringIO()):
            LibraryScreens(ui).apply("instructions")
        self.assertEqual(ui.client.call.call_count, 1)
        self.assertIn("--dry-run", ui.client.call.call_args.args[0])

    def test_conflict_prevents_confirmation_and_apply(self):
        ui = Mock()
        ui.client.action.return_value = {"targets": [{"agent": "codex", "mcp": True}]}
        ui.choose.return_value = "codex"
        ui.client.call.side_effect = Error("user edited a managed entry")
        with self.assertRaises(Error):
            LibraryScreens(ui).apply("mcp", reverting=True)
        self.assertEqual(ui.client.call.call_count, 1)
        ui.confirm.assert_not_called()


if __name__ == "__main__":
    unittest.main(verbosity=2)
