"""Short-lived, local-only data adapter for the Omarchy popup.

No provider hooks, login, refresh, or generation calls belong here. The caller
runs snapshot() asynchronously when opened/refreshed. History is streamed up to
its opening size; the limits below bound memory and work even for malformed logs.
Agent changes use the controller's existing backed-up apply/revert operations.
"""
from datetime import datetime, timedelta, timezone
import json
import math
import os
from pathlib import Path
import stat
import sys
import time

from .core import Error, text

MAX_LINE = 1024 * 1024
MAX_JSON = 8 * 1024 * 1024
MAX_SCAN_BYTES = 512 * 1024 * 1024
MAX_SCAN_SECONDS = 15
MAX_PROVIDERS = 256
MAX_ITEMS = 4096
MAX_QUOTA_ROWS = 256
UNKNOWN_PROVIDER = "__unknown__"
OTHER_PROVIDER = "__other__"


def _label(value, limit=180):
    return text(value)[:limit] if isinstance(value, str) else ""


def _id(value):
    if (not isinstance(value, str) or not value or len(value) > 512
            or value != value.strip() or value.startswith("-")
            or any(ord(c) < 32 or ord(c) == 127 for c in value)):
        return None
    return value


def _number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return value if 0 <= value <= 2 ** 53 - 1 and math.isfinite(value) else None


def _count(value):
    value = _number(value)
    return int(value) if value is not None and int(value) == value else None


def _reject_constant(_value):
    raise ValueError("Non-finite JSON number")


def _json(raw):
    return json.loads(raw, parse_constant=_reject_constant)


def _open_regular(path):
    flags = os.O_RDONLY | getattr(os, "O_NONBLOCK", 0)
    fd = os.open(path, flags)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise OSError("Local data source is not a regular file")
        return os.fdopen(fd, "rb")
    except BaseException:
        os.close(fd)
        raise


def _read_json(path, limit=MAX_JSON):
    with _open_regular(path) as stream:
        data = stream.read(limit + 1)
    if len(data) > limit:
        raise ValueError("Local JSON exceeds the read limit")
    return _json(data)


def _directory(client):
    config = getattr(client, "config", None) or os.environ.get("ZCALLD_CONFIG")
    if config:
        return Path(config).expanduser().absolute().parent
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg:
        if not Path(xdg).is_absolute():
            raise Error("XDG_CONFIG_HOME must be absolute.")
        return Path(xdg) / "zcalld"
    if sys.platform == "win32":
        root = os.environ.get("APPDATA")
        if not root:
            raise Error("APPDATA is not set.")
        return Path(root) / "zcalld"
    home = Path.home()
    return home / ("Library/Application Support/zcalld"
                   if sys.platform == "darwin" else ".config/zcalld")


def _local(client, argv, scope, errors):
    try:
        result = client.call(argv, timeout=8)
        if not isinstance(result, dict):
            raise ValueError("Invalid controller object")
        return result
    except (Error, OSError, ValueError, TypeError, RecursionError):
        # Do not copy arbitrary diagnostics, paths, header values or credentials
        # from a third-party adapter into the desktop JSON response.
        errors.append({"scope": scope, "message": "Could not read local " + scope + "."})
        return {}


def _rows(value, field):
    rows = value.get(field)
    return [row for row in rows[:MAX_ITEMS] if isinstance(row, dict)] if isinstance(rows, list) else []


def _catalog(provider_data, route_data, group_data):
    groups = []
    for row in _rows(group_data, "groups"):
        name = _id(row.get("name"))
        if name:
            members = row.get("members")
            strategy = row.get("mode") or row.get("routing")
            groups.append({"id": name, "label": _label(name), "strategy": _label(strategy) or None,
                           "members_count": len(members) if isinstance(members, list) else None})
    group_ids = {row["id"] for row in groups}
    providers = {}
    for row in _rows(provider_data, "providers"):
        name = _id(row.get("name"))
        if name:
            providers[name] = {"id": name, "label": _label(name)}
    routes, route_provider, prefix_targets = [], {}, {}
    for row in _rows(route_data, "routes"):
        name, provider = _id(row.get("name")), _id(row.get("provider"))
        if not name:
            continue
        is_group = name in group_ids
        routes.append({"id": name, "label": _label(name), "provider": provider,
                       "kind": "group" if is_group else "direct"})
        # A group's configured fallback provider is not evidence that a request
        # used it. Only the selected concrete route can identify new log rows.
        if not is_group and provider:
            route_provider[name] = provider
            if "/" in name:
                prefix_targets.setdefault(name.split("/", 1)[0], set()).add(provider)
    aliases = {prefix: next(iter(targets)) for prefix, targets in prefix_targets.items()
               if len(targets) == 1 and prefix not in {"group", "auto"}}
    aliases.update({key: key for key in providers})
    for provider in providers:
        prefixes = sorted(key for key, target in aliases.items() if target == provider and key != provider)
        if len(prefixes) == 1:
            providers[provider]["label"] = _label(prefixes[0])
    return providers, routes, groups, aliases, route_provider


def _agents(data, directory):
    try:
        applied = _read_json(directory / "agents/applied.json")
        if not isinstance(applied, dict):
            applied = {}
    except (OSError, ValueError, TypeError, RecursionError):
        applied = {}
    result = []
    for row in _rows(data, "agents"):
        name = _id(row.get("name"))
        if not name:
            continue
        saved = applied.get(name)
        revertible = isinstance(saved, dict) and isinstance(saved.get("backup"), str) and bool(saved["backup"])
        configured = row.get("configured") is True
        editable = row.get("writable") is True
        detail = ("Configuration points at this gateway; traffic is not verified."
                  if configured else "Not configured for this gateway.")
        if not editable:
            detail += " Detection only; this adapter cannot write its configuration."
        result.append({"id": name, "name": _label(name), "installed": row.get("installed") is True,
                       "configured": configured, "editable": editable, "route": _id(row.get("route")),
                       "revertible": revertible, "detail": detail})
    return result


def _timestamp(value):
    try:
        if isinstance(value, str) and len(value) <= 80:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
            # Both actual formats use explicit zones/epoch seconds. Do not
            # silently invent a timezone for a malformed imported timestamp.
            return dt.timestamp() if dt.tzinfo is not None else None
        number = _number(value)
        if number is not None:
            # The native routing plugin writes UNIX seconds, not milliseconds.
            datetime.fromtimestamp(number, timezone.utc)
            return float(number)
    except (ValueError, OverflowError, OSError):
        pass
    return None


class _Window:
    def __init__(self, period, now):
        if period not in {"today", "7d", "30d", "all"}:
            raise Error("Unknown date period.")
        self.period, self.now = period, now
        current = datetime.fromtimestamp(now).astimezone()
        self.today = current.date()
        self.start = None if period == "all" else self.today - timedelta(days={"today": 0, "7d": 6, "30d": 29}[period])
        self.first_month = self.today.year * 12 + self.today.month - 1 - 119

    def bucket(self, at):
        if at > self.now:
            return None
        local = datetime.fromtimestamp(at).astimezone()
        if self.start is not None and local.date() < self.start:
            return None
        if self.period == "today":
            return local.strftime("%H:00")
        if self.period != "all":
            return local.strftime("%Y-%m-%d")
        month = local.year * 12 + local.month - 1
        return "Earlier" if month < self.first_month else local.strftime("%Y-%m")

    def labels(self):
        if self.period == "today":
            return [f"{hour:02d}:00" for hour in range(24)]
        if self.start is not None:
            return [(self.start + timedelta(days=offset)).isoformat()
                    for offset in range((self.today - self.start).days + 1)]
        return []


def _metrics(row):
    native = "input_tokens" in row or "output_tokens" in row
    incoming = _count(row.get("input_tokens" if native else "in"))
    outgoing = _count(row.get("output_tokens" if native else "out"))
    cached = None
    if native:
        cached = _count(row.get("cache_read_tokens"))
    else:
        # Magpie's in excludes cache reads/writes; its persisted numeric cache
        # fields are 0 on misses. Old omitted fields have the upstream's zero
        # default, but cache hit coverage remains unknown when fields are absent.
        read = _count(row.get("cache_read", 0))
        write = _count(row.get("cache_write", 0))
        if incoming is not None and read is not None and write is not None:
            incoming += read + write
        else:
            incoming = None
        if "cache_read" in row and row.get("cache_unknown") is not True:
            cached = read
    if row.get("cache_unknown") is True:
        cached = None
    tokens = incoming + outgoing if incoming is not None and outgoing is not None else None
    status = _count(row.get("status"))
    failed = int(status >= 400) if status is not None else None
    cost = _number(row.get("cost_usd"))
    if cost is None and not native:
        # Magpie OwnCost is explicitly documented as USD, not plan credits.
        cost = _number(row.get("cost"))
    return {"input_tokens": incoming, "output_tokens": outgoing, "tokens": tokens,
            "cached_tokens": cached, "failures": failed, "cost_usd": cost}


class _Totals:
    FIELDS = ("tokens", "input_tokens", "output_tokens", "cached_tokens", "failures", "cost_usd")

    def __init__(self):
        self.requests = 0
        self.sums = {key: 0 for key in self.FIELDS}
        self.known = {key: 0 for key in self.FIELDS}

    def add(self, values):
        self.requests += 1
        for key in self.FIELDS:
            value = values[key]
            if value is not None:
                self.sums[key] += value
                self.known[key] += 1

    def value(self):
        result = {key: self.sums[key] if self.known[key] == self.requests else None for key in self.FIELDS}
        result["requests"] = self.requests
        incoming, cached = result["input_tokens"], result["cached_tokens"]
        result["cache_hit_ratio"] = cached / incoming if incoming and cached is not None and cached <= incoming else None
        result["priced_requests"] = self.known["cost_usd"]
        result["known_cost_usd"] = self.sums["cost_usd"] if self.known["cost_usd"] else None
        result["known_tokens"] = self.sums["tokens"] if self.known["tokens"] else None
        result["token_requests"] = self.known["tokens"]
        return result


def _provider(row, aliases, route_provider):
    actual = _id(row.get("provider"))
    if actual:
        return aliases.get(actual, actual)
    selected = _id(row.get("upstream"))
    public = _id(row.get("model"))
    return route_provider.get(selected) or route_provider.get(public) or UNKNOWN_PROVIDER


def _history(path, window, provider_filter, providers, aliases, route_provider):
    totals, by_provider = _Totals(), {}
    buckets = {label: _Totals() for label in window.labels()}
    scan = {"bytes": 0, "records": 0, "matched": 0, "invalid": 0, "oversized": 0,
            "incomplete": 0, "unknown_time": 0, "partial": False, "limited": False,
            "provider_overflow": False, "snapshot_bytes": 0}
    result = {"state": "unavailable", "message": "No local usage history is available.",
              "totals": {**totals.value(), **{key: None for key in _Totals.FIELDS},
                         "requests": None}, "buckets": [], "providers": [], "scan": scan}
    try:
        stream = _open_regular(path)
    except FileNotFoundError:
        return result
    except OSError:
        result["message"] = "Local usage history could not be read."
        return result
    deadline = time.monotonic() + MAX_SCAN_SECONDS
    with stream:
        size = os.fstat(stream.fileno()).st_size
        scan["snapshot_bytes"] = size
        remaining = min(size, MAX_SCAN_BYTES)
        if size > remaining:
            scan["limited"] = True
        while remaining > 0:
            if time.monotonic() >= deadline:
                scan["limited"] = True
                break
            raw = stream.readline(min(MAX_LINE + 1, remaining))
            if not raw:
                scan["partial"] = remaining > 0
                break
            remaining -= len(raw)
            scan["bytes"] += len(raw)
            if len(raw) > MAX_LINE:
                scan["oversized"] += 1
                while not raw.endswith(b"\n") and remaining:
                    raw = stream.readline(min(65536, remaining))
                    if not raw:
                        break
                    remaining -= len(raw)
                    scan["bytes"] += len(raw)
                    if time.monotonic() >= deadline:
                        scan["limited"] = True
                        break
                if scan["limited"]:
                    break
                continue
            if not raw.endswith(b"\n"):
                # A writer may still be appending this record. It is neither
                # parsed nor counted until a future explicit snapshot.
                scan["incomplete"] += 1
                continue
            try:
                row = _json(raw)
            except (ValueError, UnicodeDecodeError, RecursionError):
                scan["invalid"] += 1
                continue
            if not isinstance(row, dict):
                scan["invalid"] += 1
                continue
            scan["records"] += 1
            at = _timestamp(row.get("time") if "time" in row else row.get("t"))
            if at is None:
                scan["unknown_time"] += 1
                continue
            try:
                label = window.bucket(at)
            except (ValueError, OverflowError, OSError):
                scan["unknown_time"] += 1
                continue
            if label is None:
                continue
            identity = _provider(row, aliases, route_provider)
            if provider_filter != "all" and identity != provider_filter:
                continue
            values = _metrics(row)
            totals.add(values)
            buckets.setdefault(label, _Totals()).add(values)
            if identity not in by_provider and len(by_provider) >= MAX_PROVIDERS:
                identity = OTHER_PROVIDER
                scan["provider_overflow"] = True
            by_provider.setdefault(identity, _Totals()).add(values)
            scan["matched"] += 1
    scan["partial"] = scan["partial"] or any(scan[key] for key in
        ("invalid", "oversized", "incomplete", "unknown_time", "limited", "provider_overflow"))
    result["totals"] = totals.value()
    result["buckets"] = [{"label": label, **buckets[label].value()} for label in
                         sorted(buckets, key=lambda label: (label != "Earlier", label))]
    for identity, aggregate in by_provider.items():
        label = providers.get(identity, {}).get("label") or (
            "Unknown provider" if identity == UNKNOWN_PROVIDER else
            "Other providers" if identity == OTHER_PROVIDER else _label(identity))
        result["providers"].append({"id": identity, "label": label, **aggregate.value()})
    result["providers"].sort(key=lambda row: (-row["requests"], row["label"]))
    result["state"] = "partial" if scan["partial"] else "ready"
    notes = []
    if scan["partial"]:
        notes.append("Some history was skipped or limited; totals and chart cover only the records read.")
    if totals.requests and totals.known["cost_usd"] < totals.requests:
        notes.append("USD cost is unknown for unpriced requests; no price is estimated.")
    if totals.requests and totals.known["tokens"] < totals.requests:
        notes.append("Some requests do not report token counts.")
    if not totals.requests:
        notes.append("No recorded requests match this date and provider filter.")
    result["message"] = " ".join(notes)
    return result


def _quotas(directory, provider_filter, providers, aliases, now):
    result = {"state": "unavailable", "message": "No local quota cache is available. No online refresh was made.", "rows": []}
    try:
        saved = _read_json(directory / "quotas.json")
    except FileNotFoundError:
        return result
    except (OSError, ValueError, TypeError, RecursionError):
        result["message"] = "Local quota cache could not be read. No online refresh was made."
        return result
    if not isinstance(saved, dict):
        result["message"] = "Local quota cache has an unsupported format."
        return result
    for index, stored in enumerate(saved.values()):
        if not isinstance(stored, dict) or not isinstance(stored.get("quota"), dict):
            continue
        quota = stored["quota"]
        identity = _id(quota.get("provider"))
        if not identity:
            continue
        identity = aliases.get(identity, identity)
        if provider_filter != "all" and identity != provider_filter:
            continue
        label = providers.get(identity, {}).get("label") or _label(quota.get("name")) or _label(identity)
        at = _timestamp(stored.get("at") or quota.get("readAt") or quota.get("asOf"))
        cached_at = datetime.fromtimestamp(at, timezone.utc).isoformat() if at is not None else None
        windows = quota.get("windows")
        if not isinstance(windows, list):
            windows = []
        if not windows:
            windows = [{}]  # Cache exists, but no numeric allowance is known.
        for number, row in enumerate(windows):
            if not isinstance(row, dict):
                continue
            used = _number(row.get("used"))
            remaining = None
            if (used is not None and used <= 100 and row.get("text") is not True
                    and row.get("unlimited") is not True and row.get("balance") is None
                    and not quota.get("error")):
                remaining = 100 - used
            reset = _timestamp(row.get("resetsAt"))
            if reset is None and at is not None and _number(row.get("resetSecs")):
                reset = at + row["resetSecs"]
            expired = reset is not None and reset <= now
            detail = "Cached reading; current allowance has not been queried."
            if cached_at:
                detail += " Sampled " + datetime.fromtimestamp(at).astimezone().strftime("%Y-%m-%d %H:%M") + "."
            if expired:
                detail += " Its reset time has passed."
            if row.get("unlimited") is True:
                detail += " This cached window reports no limit."
            elif row.get("text") is True or row.get("balance") is not None:
                detail += " This cache has no percentage allowance."
            result["rows"].append({
                "id": f"quota-{index}-{number}", "provider": identity,
                "label": label + (" · " + _label(row["name"]) if isinstance(row.get("name"), str) else ""),
                "remaining_percent": None if expired else remaining,
                "last_known_percent": remaining, "detail": detail, "cached_at": cached_at,
                "expired": expired, "reset_label": datetime.fromtimestamp(reset).astimezone().strftime("%m-%d %H:%M")
                    if reset is not None else None})
            if len(result["rows"]) == MAX_QUOTA_ROWS:
                result["state"] = "partial"
                result["message"] = "Local cached quotas only; additional rows were omitted."
                return result
    if result["rows"]:
        result["state"] = "cached"
        result["message"] = "Saved quota readings only. Refresh rereads local files and does not contact providers."
    return result


def snapshot(client, period="today", provider="all"):
    """Return a whitelisted snapshot; do not forward raw CLI or history records."""
    if provider != "all" and not _id(provider):
        raise Error("Invalid provider filter.")
    now = time.time()
    window, directory, errors = _Window(period, now), _directory(client), []
    status = _local(client, ["status"], "status", errors)
    provider_data = _local(client, ["providers", "list"], "providers", errors)
    route_data = _local(client, ["routes", "list"], "routes", errors)
    group_data = _local(client, ["groups", "list"], "routing", errors)
    agent_data = _local(client, ["agents", "list"], "agents", errors)
    privacy = _local(client, ["privacy", "show"], "privacy", errors)
    providers, routes, groups, aliases, route_provider = _catalog(provider_data, route_data, group_data)
    provider = aliases.get(provider, provider)
    usage_path = directory / "usage.jsonl"
    # groups list exposes the actual optional routing writer's configured path.
    # A relative override follows the daemon's configuration directory.
    configured_path = group_data.get("usage_file")
    if isinstance(configured_path, str) and configured_path:
        usage_path = Path(configured_path)
        if not usage_path.is_absolute():
            usage_path = directory / usage_path
    usage = _history(usage_path, window, provider, providers, aliases, route_provider)
    quotas = _quotas(directory, provider, providers, aliases, now)
    for row in usage["providers"] + quotas["rows"]:
        identity = row.get("provider", row["id"])
        if identity not in providers and len(providers) < MAX_PROVIDERS:
            providers[identity] = {"id": identity, "label": row["label"]}
    if usage["state"] in {"partial", "unavailable"}:
        errors.append({"scope": "usage", "message": usage["message"]})
    return {
        "schema_version": 1, "generated_at": datetime.fromtimestamp(now, timezone.utc).isoformat(),
        "filters": {"period": period, "provider": provider, "timezone": "local",
                    "start_date": window.start.isoformat() if window.start else None,
                    "end_date": window.today.isoformat()},
        "status": {"healthy": status.get("healthy") if isinstance(status.get("healthy"), bool) else None,
                   "service": _label(status.get("service"), 64) or "unknown",
                   "version": _label(status.get("version"), 64) or None,
                   # This is a saved preference, not proof of a running hook.
                   "privacy_enabled": privacy.get("enabled") if isinstance(privacy.get("enabled"), bool) else None,
                   "privacy_runtime_state": _label(privacy.get("runtime_state"), 64) or "not_checked"},
        "providers": sorted(providers.values(), key=lambda row: row["label"]),
        "agents": _agents(agent_data, directory), "routes": routes,
        "routing": {"default_route": None, "can_set_default": False, "groups": groups},
        "usage": usage, "quota": quotas, "errors": errors}


def action(client, name, payload):
    """Invoke one supported, explicit agent edit through the existing controller."""
    failure = {"ok": False, "error": "Unsupported panel action."}
    if name not in {"agent.route", "agent.revert"}:
        return failure
    expected = {"agent", "route"} if name == "agent.route" else {"agent"}
    if not isinstance(payload, dict) or set(payload) != expected:
        return {"ok": False, "error": "Invalid action payload."}
    agent = _id(payload.get("agent"))
    route = _id(payload.get("route")) if name == "agent.route" else None
    if not agent or (name == "agent.route" and not route):
        return {"ok": False, "error": "Invalid agent or route identifier."}
    errors = []
    agent_data = _local(client, ["agents", "list"], "agents", errors)
    agents = _agents(agent_data, _directory(client))
    selected = next((row for row in agents if row["id"] == agent), None)
    if errors or selected is None:
        return {"ok": False, "error": "The selected agent is not available."}
    if not selected["editable"]:
        return {"ok": False, "error": "This agent supports detection only."}
    if name == "agent.route":
        routes = _local(client, ["routes", "list"], "routes", errors)
        if errors or route not in {_id(row.get("name")) for row in _rows(routes, "routes")}:
            return {"ok": False, "error": "The selected route is not configured."}
        argv = ["agents", "apply", agent, "--route", route]
    else:
        if not selected["revertible"]:
            return {"ok": False, "error": "This agent has no managed change to revert."}
        argv = ["agents", "revert", agent]
    try:
        result = client.call(argv, timeout=90)
    except (Error, OSError, ValueError, TypeError):
        return {"ok": False, "error": "The controller refused the agent change. Existing edits were not forced; check the CLI for details."}
    if not isinstance(result, dict) or result.get("ok") is not True:
        return {"ok": False, "error": "The controller did not confirm the agent change."}
    return {"ok": True, "error": None, "action": name,
            "message": "Agent configuration saved. Restart or reload that agent to use the saved configuration.",
            "agent_restart_required": True,
            "restart_required": result.get("restart_required") is True}
