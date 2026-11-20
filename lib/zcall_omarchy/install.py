"""Own one marked menu block; leave other entries, comments and key bindings alone."""
import base64
import contextlib
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import stat
import subprocess
import tempfile

from .core import Error

BEGIN = "\n  // BEGIN zcall-omarchy v1\n"
END = "  // END zcall-omarchy v1\n"
LIMIT = 1024 * 1024
SECTIONS = (
    ("status", "Status", "Gateway health and configured routes"),
    ("providers", "Providers", "Endpoints, protocols and private API keys"),
    ("models", "Models and routes", "Catalog, aliases and model groups"),
    ("agents", "Agents", "Configure or revert an installed AI client"),
    ("library", "Library", "MCP servers, shared instructions and skills"),
    ("privacy", "Privacy", "Secret and personal information filtering"),
    ("plugins", "Community plugins", "Install, configure and manage extensions"),
    ("accounts", "Accounts", "Manage the existing provider account store"),
    ("usage", "Usage", "Local token and request totals"),
    ("logs", "Logs", "Recent user-service journal"),
    ("updates", "Updates", "Check or apply zcalld updates"),
)


def paths():
    home = Path.home()
    return (home / ".config/omarchy/extensions/omarchy-menu.jsonc",
            Path(os.environ.get("XDG_STATE_HOME", home / ".local/state")) / "zcall-omarchy/install.json")


def digest(value):
    return hashlib.sha256(value).hexdigest()


def pairs(values):
    result = {}
    for key, value in values:
        if key in result:
            raise Error("Menu JSONC contains a duplicate key.")
        result[key] = value
    return result


def parse_jsonc(source):
    # Omarchy documents whole-line comments and trailing commas. Do not
    # silently accept additional syntax that its own menu would reject.
    source = "".join(line for line in source.splitlines(keepends=True)
                     if not line.lstrip().startswith("//"))
    result = []
    quoted = escaped = False
    for index, char in enumerate(source):
        if quoted:
            result.append(char)
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                quoted = False
            continue
        if char == '"':
            quoted = True
        if char == ",":
            look = index + 1
            while look < len(source) and source[look].isspace():
                look += 1
            if look < len(source) and source[look] in "}]":
                continue
        result.append(char)
    try:
        value = json.loads("".join(result), object_pairs_hook=pairs)
    except (ValueError, UnicodeDecodeError):
        raise Error("The existing Omarchy menu is not valid documented JSONC; no changes were made.") from None
    if not isinstance(value, dict):
        raise Error("The Omarchy menu must be an object.")
    return value


def read_file(path, default=None):
    if path.is_symlink():
        raise Error(f"Refusing to replace a symlink: {path}")
    if not path.exists():
        return default
    if not path.is_file() or path.stat().st_size > LIMIT:
        raise Error(f"Expected a regular file of at most 1 MiB: {path}")
    return path.read_bytes()


def records():
    menu, journal = paths()
    data = read_file(menu, b"{}\n")
    raw = read_file(journal)
    record = None
    if raw is not None:
        try:
            record = json.loads(raw)
        except ValueError:
            raise Error("The private installation record is invalid.") from None
        if record.get("schema") != 1 or record.get("menu") != str(menu):
            raise Error("The installation record belongs to a different menu.")
    return menu, journal, data, record


def decoded(data):
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        raise Error("The menu must use UTF-8.") from None


def prior_bytes(record):
    value = record.get("before")
    try:
        return None if value is None else base64.b64decode(value, validate=True)
    except (ValueError, TypeError):
        raise Error("The private installation backup is invalid.") from None


def remove_owned(source, record):
    if not record:
        if BEGIN in source or END in source:
            raise Error("A managed menu block exists without its ownership record.")
        return source
    block = record.get("block", "")
    if (not isinstance(block, str) or not block.startswith(BEGIN) or not block.endswith(END)
            or source.count(block) != 1 or source.count(BEGIN) != 1 or source.count(END) != 1):
        # A write may have been interrupted after journaling but before the
        # atomic menu replacement. It is safe only if the old bytes remain.
        old = prior_bytes(record)
        if source.encode() == (old if old is not None else b"{}\n"):
            return source
        raise Error("The Zcall block was edited or moved unexpectedly; no user edits were removed.")
    parse_jsonc(source)
    result = source.replace(block, "", 1)
    # An originally empty menu can gain a new entry after our block. Its
    # separating comma would become a leading comma when we remove the block.
    # Remove only that now-unused structural byte; retain every new entry.
    if not parse_jsonc(decoded(prior_bytes(record) or b"{}\n")):
        first = False
        offset = 0
        for line in result.splitlines(keepends=True):
            if line.lstrip().startswith("//"):
                offset += len(line)
                continue
            for index, char in enumerate(line):
                if char.isspace():
                    continue
                if not first and char == "{":
                    first = True
                    continue
                if first and char == ",":
                    position = offset + index
                    return result[:position] + result[position + 1:]
                return result
            offset += len(line)
    return result


def entries(entry):
    def action(section):
        # Omarchy's fixed action field is a shell command. Only our trusted
        # executable path and a constant action are quoted into it.
        return shlex.join([str(entry), "open", section])
    result = {"zcall": {"icon": "Z", "label": "Zcall", "description": "Local AI gateway"}}
    result["zcall.service"] = {"label": "Service", "description": "Control the user gateway"}
    for verb, label in (("start", "Start"), ("restart", "Restart"), ("stop", "Stop"),
                        ("enable", "Start at login"), ("disable", "Disable login start")):
        result["zcall.service." + verb] = {"label": label, "action": action("service." + verb)}
    for key, label, description in SECTIONS:
        result["zcall." + key] = {"label": label, "description": description, "action": action(key)}
    return result


def proposed(entry):
    menu, journal, data, record = records()
    base = remove_owned(decoded(data), record)
    existing = parse_jsonc(base)
    if any(key == "zcall" or key.startswith("zcall.") for key in existing):
        raise Error("The zcall menu namespace already belongs to another entry; no changes were made.")
    closing = base.rfind("}")
    if closing < 0:
        raise Error("The menu root has no closing brace.")
    prefix, suffix = base[:closing], base[closing:]
    clean_prefix = "".join(line for line in prefix.splitlines(keepends=True)
                           if not line.lstrip().startswith("//")).rstrip()
    separator = "  ,\n" if existing and not clean_prefix.endswith(",") else ""
    rows = entries(entry)
    def encode_row(value):
        encoded = json.dumps(value, ensure_ascii=False)
        # Omarchy 4.5 strips trailing commas with a regex, including comma
        # sequences inside strings. Escape only our generated values so shell
        # paths such as "workspace,}/bin" survive its actual JSONC parser.
        return re.sub(r",(?=\s*[}\]])", lambda _: r"\u002c", encoded)
    content = ",\n".join("  " + json.dumps(key) + ": " + encode_row(value)
                          for key, value in rows.items()) + "\n"
    block = BEGIN + separator + content + END
    updated = (prefix + block + suffix).encode()
    parse_jsonc(decoded(updated))
    before = base.encode() if menu.exists() else None
    if record and prior_bytes(record) is None and before == b"{}\n":
        before = None
    item = {"schema": 1, "menu": str(menu), "block": block,
            "before": base64.b64encode(before).decode() if before is not None else None,
            "mode": stat.S_IMODE(menu.stat().st_mode) if menu.exists() else 0o600,
            "after_sha256": digest(updated)}
    plan = {"action": "install", "changed": updated != data,
            "menu": str(menu), "record": str(journal), "entry_count": len(rows),
            "menu_entries": list(rows), "addition": block,
            "key_bindings_changed": False, "bar_layout_changed": False}
    return plan, updated, item


def atomic(path, data, mode=0o600):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor, name = tempfile.mkstemp(prefix="." + path.name + ".", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as output:
            os.fchmod(output.fileno(), mode)
            output.write(data)
            output.flush()
            os.fsync(output.fileno())
        os.replace(name, path)
    finally:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(name)


@contextlib.contextmanager
def locked():
    _, journal = paths()
    journal.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor = os.open(journal.with_suffix(".lock"), os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        yield
    finally:
        os.close(descriptor)


def refresh():
    binary = shutil.which("omarchy-menu")
    if not binary:
        return False
    try:
        result = subprocess.run([binary, "refresh"], stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, timeout=4, check=False)
        return result.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def install(entry, apply=False):
    if not apply:
        return proposed(entry)[0]
    with locked():
        plan, updated, record = proposed(entry)
        menu, journal = paths()
        if plan["changed"]:
            # Save the small private recovery record first. A crash before the
            # second replace is recognizable by the untouched original bytes.
            atomic(journal, (json.dumps(record, indent=2) + "\n").encode())
            atomic(menu, updated, record["mode"])
        elif not journal.exists():
            atomic(journal, (json.dumps(record, indent=2) + "\n").encode())
    plan.pop("addition")
    plan["applied"] = True
    plan["menu_refreshed"] = refresh()
    return plan


def uninstall(apply=False):
    def prepare():
        menu, journal, data, record = records()
        if not record:
            return {"action": "uninstall", "changed": False, "menu": str(menu)}, None, None
        source = decoded(data)
        base = remove_owned(source, record)
        parse_jsonc(base)
        if digest(data) == record["after_sha256"] or data == (prior_bytes(record) or b"{}\n"):
            restored = prior_bytes(record)
        else:
            restored = base.encode()
        return {"action": "uninstall", "changed": True, "menu": str(menu),
                "unrelated_entries_preserved": True}, restored, record
    if not apply:
        return prepare()[0]
    with locked():
        plan, restored, record = prepare()
        if record:
            menu, journal = paths()
            if restored is None:
                menu.unlink(missing_ok=True)
            else:
                atomic(menu, restored, record["mode"])
            journal.unlink()
    plan["applied"] = True
    plan["menu_refreshed"] = refresh()
    return plan


def menu_is_installed():
    try:
        _, _, data, record = records()
        return bool(record and isinstance(record.get("block"), str)
                    and data.count(record["block"].encode()) == 1)
    except (Error, OSError):
        return False
