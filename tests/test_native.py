"""Optional integration with a real zcalld binary and a disposable HOME."""
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))
from zcall_omarchy.core import Client, Error

BINARY = os.environ.get("ZCALLD_TEST_BINARY")


@unittest.skipUnless(BINARY, "Set ZCALLD_TEST_BINARY to run actual CLI integration")
class NativeController(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="zcall-omarchy-native-")
        self.home = Path(self.temp.name)
        self.directory = self.home / ".config/zcalld"
        self.directory.mkdir(parents=True)
        self.config = self.directory / "config.conf"
        self.config.write_text("[server]\nlisten = 127.0.0.1:39415\nunix_socket = none\n"
                               "[provider fixture]\nbase_url = http://127.0.0.1:1/v1\n"
                               "protocol = chat\nauth = none\n"
                               "[route fixture/model]\nprovider = fixture\nmodel = model\n")
        prefixes = ("ZCALLD_", "CODEX_", "XDG_", "CLAUDE_", "COPILOT_", "OPENCODE_",
                    "PI_", "OMP_", "OMO_", "SENPI_", "GROK_", "DSH_", "QWEN_")
        env = {key: value for key, value in os.environ.items() if not key.startswith(prefixes)}
        env.update(HOME=str(self.home), USERPROFILE=str(self.home),
                   XDG_CONFIG_HOME=str(self.home / ".config"),
                   XDG_STATE_HOME=str(self.home / ".local/state"),
                   APPDATA=str(self.home / ".config"),
                   LOCALAPPDATA=str(self.home / "AppData/Local"))
        self.env = patch.dict(os.environ, env, clear=True)
        self.env.start()
        self.client = Client(config=self.config, binary=Path(BINARY).resolve())

    def tearDown(self):
        self.env.stop()
        self.temp.cleanup()

    def write(self, relative, text):
        path = self.home / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        return path

    def test_provider_stdin_and_route_catalog(self):
        secret = 'fixture-key-"quoted"-\\slash'
        self.client.provider("added", "http://127.0.0.1:1/v1", "responses", secret)
        listed = self.client.action("providers")
        self.assertNotIn(secret, json.dumps(listed))
        self.assertIn("added", [item["name"] for item in listed["providers"]])
        credentials = self.directory / "credentials"
        self.assertEqual(credentials.stat().st_mode & 0o777, 0o600)
        encoded = next(line.split("=", 1)[1] for line in credentials.read_text().splitlines()
                       if line and not line.startswith("#"))
        self.assertEqual(json.loads(encoded), secret)
        self.client.route("workspace/model", "added", "upstream-model")
        routes = self.client.action("routes")["routes"]
        selected = next(item for item in routes if item["name"] == "workspace/model")
        self.assertEqual((selected["provider"], selected["model"]), ("added", "upstream-model"))
        self.assertIn("workspace/model", [item["id"] for item in self.client.action("models")["data"]])

    def test_library_preview_apply_conflict_and_revert(self):
        source = self.write("shared.md", "Shared fixture instruction\n")
        target = self.write(".claude/CLAUDE.md", "Keep personal instructions\n")
        original = target.read_bytes()
        self.client.call(["library", "instructions", "set", "default", "--file", source,
                          "--agents", "claude"])
        args = ["library", "apply", "--agent", "claude", "--kind", "instructions"]
        preview = self.client.call([*args, "--dry-run"])
        self.assertTrue(preview["dry_run"])
        self.assertEqual(target.read_bytes(), original)
        self.client.call(args)
        managed = target.read_bytes()
        self.assertIn(b"Shared fixture instruction", managed)
        self.assertIn(b"Keep personal instructions", managed)
        target.write_bytes(managed.replace(b"Shared fixture instruction", b"Manual user change"))
        edited = target.read_bytes()
        with self.assertRaises(Error):
            self.client.call(["library", "revert", "--agent", "claude", "--kind", "instructions"])
        self.assertEqual(target.read_bytes(), edited)
        target.write_bytes(managed)
        self.client.call(["library", "revert", "--agent", "claude", "--kind", "instructions"])
        # The backend preserves separator whitespace outside its owned block.
        self.assertEqual(target.read_text().strip(), original.decode().strip())

    def test_private_mcp_listing_and_unrelated_server_survive_revert(self):
        secret = "private-mcp-fixture"
        source = self.write("mcp.json", json.dumps({
            "name": "fixture", "transport": "stdio", "command": "echo",
            "args": ["never executed"], "env": {"TOKEN": secret}, "agents": ["claude"]}))
        target = self.write(".claude.json", '{"mcpServers":{"personal":{"command":"true"}},"keep":7}')
        self.client.call(["library", "mcp", "set", "--file", source])
        self.assertNotIn(secret, json.dumps(self.client.action("library.mcp")))
        self.client.call(["library", "apply", "--agent", "claude", "--kind", "mcp"])
        state = json.loads(target.read_text())
        self.assertEqual(state["mcpServers"]["fixture"]["env"]["TOKEN"], secret)
        self.client.call(["library", "revert", "--agent", "claude", "--kind", "mcp"])
        self.assertEqual(json.loads(target.read_text()), {
            "mcpServers": {"personal": {"command": "true"}}, "keep": 7})


if __name__ == "__main__":
    unittest.main(verbosity=2)
