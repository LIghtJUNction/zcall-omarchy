"""Base-price estimates from a saved local gateway model catalog.

Prices are decimal USD per token, as exported by Magpie's OpenRouterPricing.
This is not an invoice: historical rows are evaluated at the saved base prices,
without inventing provider discounts, service tiers or unknown cache splits.
"""
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import math
import re


_DECIMAL = re.compile(r"(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?\Z")
_STANDARD = (None, "", "auto", "default", "standard")


def _price(value):
    if not isinstance(value, str) or len(value) > 80 or not _DECIMAL.fullmatch(value):
        return None
    try:
        number = Decimal(value)
        return number if number.is_finite() and 0 <= number <= Decimal("1000000") else None
    except InvalidOperation:
        return None


def _count(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return int(value) if 0 <= value <= 2 ** 53 - 1 and math.isfinite(value) and int(value) == value else None


class Prices:
    def __init__(self, data=None, routes=(), aliases=None, updated_at=None):
        self.prices, self.routes, self.aliases = {}, {}, aliases or {}
        self.info = {"source": "saved_model_catalog", "updated_at": updated_at,
                     "estimate": True, "priced_models": 0,
                     "message": "Saved base prices only; estimates are not provider invoices or historical tariffs."}
        for route in routes:
            if isinstance(route, dict) and isinstance(route.get("name"), str):
                self.routes[route["name"]] = route
        rows = data.get("data", data.get("models", [])) if isinstance(data, dict) else []
        if not isinstance(rows, list):
            rows = []
        for row in rows[:4096]:
            if not isinstance(row, dict) or not isinstance(row.get("id"), str):
                continue
            raw = row.get("pricing")
            if not isinstance(raw, dict):
                continue
            prices = {name: _price(raw.get(name)) for name in
                      ("prompt", "completion", "input_cache_read", "input_cache_write")}
            if prices["prompt"] is not None and prices["completion"] is not None:
                # Duplicate catalog IDs are ambiguous, even if prices agree now.
                self.prices[row["id"]] = None if row["id"] in self.prices else prices
        self.info["priced_models"] = sum(value is not None for value in self.prices.values())

    def _find(self, model, provider):
        if not isinstance(model, str) or not model:
            return None
        candidates = [provider + "/" + model, model] if provider else [model]
        for name in dict.fromkeys(candidates):
            if name not in self.prices or self.prices[name] is None:
                continue
            route = self.routes.get(name, {})
            actual = route.get("provider")
            if provider and actual and self.aliases.get(provider, provider) != actual:
                continue
            return name, self.prices[name]
        return None

    def estimate(self, row):
        native = "input_tokens" in row or "output_tokens" in row
        if row.get("cache_unknown") is True:
            return None, "cache_breakdown_missing"
        if any(row.get(key) not in _STANDARD for key in ("tier_sent", "tier_served", "tier_asked")):
            return None, "service_tier_unknown"
        if row.get("cache_write_1h", 0) not in (None, 0):
            return None, "one_hour_cache_price_missing"
        if native:
            incoming = _count(row.get("input_tokens"))
            outgoing = _count(row.get("output_tokens"))
            read = _count(row.get("cache_read_tokens"))
            write = _count(row.get("cache_write_tokens"))
            if read is None or write is None:
                return None, "cache_breakdown_missing"
            if incoming is not None:
                incoming -= read + write
                if incoming < 0:
                    return None, "invalid_token_counts"
        else:
            incoming = _count(row.get("in"))
            outgoing = _count(row.get("out"))
            read = _count(row.get("cache_read", 0))
            write = _count(row.get("cache_write", 0))
        if any(value is None for value in (incoming, outgoing, read, write)):
            return None, "token_counts_missing"
        if incoming + read + write > 200000:
            return None, "context_tier_price_missing"
        provider = row.get("provider") if isinstance(row.get("provider"), str) else ""
        model = row.get("upstream") if native and row.get("upstream") else row.get("model")
        found = self._find(model, provider)
        if found is None:
            return None, "model_price_missing"
        name, prices = found
        served = row.get("served")
        # Exact public/upstream names are authoritative. No fuzzy matching of
        # similar model families, dated versions or different providers.
        if isinstance(served, str) and served:
            equivalent = {model, name}
            upstream = self.routes.get(name, {}).get("model")
            if isinstance(upstream, str):
                equivalent.add(upstream)
            if provider and name.startswith(provider + "/"):
                equivalent.add(name[len(provider) + 1:])
            if served not in equivalent:
                actual = self._find(served, provider)
                if actual is None:
                    return None, "served_model_price_missing"
                _, prices = actual
        parts = ((incoming, "prompt"), (outgoing, "completion"),
                 (read, "input_cache_read"), (write, "input_cache_write"))
        if any(count and prices[key] is None for count, key in parts):
            return None, "cache_price_missing"
        total = sum((Decimal(count) * prices[key] for count, key in parts if count), Decimal(0))
        return (total, None) if total <= Decimal(2 ** 53 - 1) else (None, "cost_out_of_range")


def load(directory, read_json, routes, aliases):
    path = directory / "model-catalog.json"
    try:
        data = read_json(path)
        modified = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat()
        return Prices(data, routes, aliases, modified)
    except (OSError, ValueError, TypeError, RecursionError, OverflowError):
        result = Prices(routes=routes, aliases=aliases)
        result.info["message"] = "No usable saved model prices; recorded USD amounts remain available."
        return result
