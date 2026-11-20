"""Small argv/JSON boundary. No provider transport or persistent controller state."""
import json
import os
from pathlib import Path
import shutil
import subprocess


class Error(Exception):
    pass


READ_ACTIONS = {
    "status": ["status"],
    "providers": ["providers", "list"],
    "models": ["models"],
    "routes": ["routes", "list"],
    "groups": ["groups", "list"],
    "agents": ["agents", "list"],
    "privacy": ["privacy", "show"],
    "plugins": ["plugins", "list"],
    "accounts": ["accounts", "list"],
    "usage": ["usage", "summary"],
    "library": ["library", "list"],
    "library.targets": ["library", "targets"],
    "library.mcp": ["library", "mcp", "list"],
    "library.instructions": ["library", "instructions", "list"],
    "library.skills": ["library", "skills", "list"],
    "plugins.mcp": ["plugins", "mcp", "show"],
    "update.check": ["update", "check"],
}
SERVICE_ACTIONS = {"start", "stop", "restart", "enable", "disable"}


def text(value):
    """Strip terminal control characters from externally supplied labels."""
    return "".join(c for c in str(value) if c.isprintable())[:180]


class Client:
    def __init__(self, config=None, binary=None):
        self.config = str(Path(config).expanduser()) if config else os.environ.get("ZCALLD_CONFIG")
        self.binary = binary or os.environ.get("ZCALLD_BIN") or shutil.which("zcalld")
        if not self.binary:
            raise Error("zcalld is not installed or is missing from PATH.")

    def argv(self, arguments):
        # Global options are supplied only by this boundary, never an identifier.
        if any(str(value) in {"--config", "-c", "--json"} or chr(0) in str(value) for value in arguments):
            raise Error("An argument conflicts with the controller's global options.")
        result = [str(self.binary), *map(str, arguments), "--json"]
        if self.config:
            result += ["--config", self.config]
        return result

    def call(self, arguments, secret=None, timeout=90):
        if secret is not None:
            if not secret or len(secret.encode()) > 16384 or any(ord(c) < 32 or ord(c) == 127 for c in secret):
                raise Error("API key must be one nonempty line of at most 16 KiB.")
            if "--api-key-stdin" not in arguments:
                raise Error("Private input requires the zcalld --api-key-stdin operation.")
        try:
            result = subprocess.run(
                self.argv(arguments), input=(secret + "\n").encode() if secret is not None else b"",
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout, check=False)
        except (OSError, subprocess.TimeoutExpired) as error:
            raise Error("zcalld could not complete the operation: " + type(error).__name__) from None
        if len(result.stdout) > 16 * 1024 * 1024 or len(result.stderr) > 65536:
            raise Error("zcalld returned more output than this screen can display.")
        if result.returncode:
            # A credential operation never echoes a downstream diagnostic that
            # could contain its private stdin, even if a future CLI regresses.
            if secret is not None:
                raise Error("The provider credential could not be saved. Check its name, URL and protocol.")
            detail = result.stderr.decode(errors="replace").strip()
            raise Error(text(detail) or f"zcalld exited with status {result.returncode}.")
        try:
            value = json.loads(result.stdout)
        except (ValueError, UnicodeDecodeError):
            # Some old releases do not implement the JSON controller.
            raise Error("This action requires zcalld's JSON management CLI (0.2 or newer).") from None
        def contains_private(item):
            if isinstance(item, str):
                return secret in item
            if isinstance(item, list):
                return any(contains_private(child) for child in item)
            if isinstance(item, dict):
                return any(contains_private(key) or contains_private(child) for key, child in item.items())
            return False
        if secret is not None and contains_private(value):
            raise Error("The controller returned private input; output was withheld.")
        return value

    def action(self, name):
        if name in READ_ACTIONS:
            return self.call(READ_ACTIONS[name])
        if name.startswith("service.") and name[8:] in SERVICE_ACTIONS:
            return self.call(["service", name[8:]], timeout=100)
        raise Error("Unknown action.")

    def provider(self, name, base_url, protocol, secret=None, edit=False):
        arguments = ["providers", "edit" if edit else "add", name,
                     "--base-url", base_url, "--protocol", protocol]
        if secret is not None:
            arguments.append("--api-key-stdin")
        return self.call(arguments, secret=secret)

    def route(self, name, provider, model):
        return self.call(["routes", "set", name, "--provider", provider, "--model", model])

    def agent(self, name, route):
        return self.call(["agents", "apply", name, "--route", route])

    def attached(self, arguments):
        """Operations such as package updates keep the terminal for sudo prompts."""
        try:
            result = subprocess.run(self.argv(arguments), check=False)
        except OSError:
            raise Error("Could not launch zcalld.") from None
        if result.returncode:
            raise Error(f"Operation exited with status {result.returncode}.")
