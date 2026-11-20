import copy
from datetime import datetime, timezone
import io
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
import time
import tracemalloc
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))
from zcall_omarchy import backend
from zcall_omarchy.core import Client, Error

NOW = datetime(2026, 11, 20, 12, tzinfo=timezone.utc).timestamp()


class FakeClient:
    def __init__(self, directory):
        self.config = str(directory / "config.conf")
        self.calls = []
        self.data = {
            ("status",): {"healthy": True, "service": "active", "version": "0.2.4",
                          "socket": "/private/path", "error": "PRIVATE-CANARY"},
            ("privacy", "show"): {"enabled": True, "runtime_state": "not_checked"},
            ("plugins", "quota", "list"): {"schema_version": 1, "local_only": True, "accounts": [], "readings": []},
            ("providers", "list"): {"providers": [
                {"name": "p-alpha", "base_url": "https://secret.invalid/?key=PRIVATE-CANARY"},
                {"name": "p-beta"}]},
            ("routes", "list"): {"routes": [
                {"name": "alpha/model", "provider": "p-alpha", "model": "underlying"},
                {"name": "beta/model", "provider": "p-beta", "model": "underlying"},
                {"name": "group/fast", "provider": "p-alpha", "model": "underlying"}]},
            ("groups", "list"): {"groups": [{"name": "group/fast", "mode": "fallback",
                                             "members": ["alpha/model", "beta/model"],
                                             "prompt": "PRIVATE-CANARY"}]},
            ("agents", "list"): {"agents": [
                {"name": "gemini", "installed": True, "configured": True,
                 "writable": True, "route": "alpha/model", "path": "/private/path"},
                {"name": "cursor", "installed": True, "configured": False,
                 "writable": False, "route": None}]},
        }

    def call(self, argv, timeout=90):
        self.calls.append(list(argv))
        key = tuple(argv)
        value = self.data.get(key, {"ok": True, "backup": "/private/path"})
        if isinstance(value, Exception):
            raise value
        return copy.deepcopy(value)


class Fixture(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="zpanel-")
        self.base = Path(self.temporary.name).resolve()
        self.environment = patch.dict(os.environ, {
            "HOME": str(self.base), "XDG_CONFIG_HOME": str(self.base / ".config"),
            "XDG_STATE_HOME": str(self.base / ".local/state"), "TZ": "UTC"})
        self.environment.start()
        if hasattr(time, "tzset"):
            time.tzset()
        self.directory = self.base / "gateway"
        self.directory.mkdir()
        self.client = FakeClient(self.directory)
        self.clock = patch.object(backend.time, "time", return_value=NOW)
        self.clock.start()

    def tearDown(self):
        self.clock.stop()
        self.environment.stop()
        if hasattr(time, "tzset"):
            time.tzset()
        self.temporary.cleanup()

    def history(self, rows):
        with (self.directory / "usage.jsonl").open("wb") as output:
            for row in rows:
                output.write(json.dumps(row).encode() + b"\n")

    def legacy(self, **overrides):
        result = {"t": "2026-11-20T10:00:00Z", "provider": "alpha",
                  "in": 100, "out": 20, "cache_read": 30, "cache_write": 10, "status": 200}
        result.update(overrides)
        return result

    def native(self, **overrides):
        result = {"time": NOW - 3600, "model": "group/fast", "upstream": "beta/model",
                  "input_tokens": 60, "output_tokens": 10, "status": 200}
        result.update(overrides)
        return result

    def saved(self, filename, value):
        path = self.directory / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(json.dumps(value).encode())

    def snap(self, period="today", provider="all"):
        return backend.snapshot(self.client, period, provider)


class SnapshotTests(Fixture):
    def test_real_legacy_and_native_token_semantics_and_provider_mapping(self):
        self.history([self.legacy(cost=0.05), self.native(status=503, cost_usd=0.02)])
        value = self.snap()
        total = value["usage"]["totals"]
        self.assertEqual((total["requests"], total["failures"]), (2, 1))
        self.assertEqual((total["tokens"], total["input_tokens"], total["output_tokens"]),
                         (230, 200, 30))
        self.assertAlmostEqual(total["cost_usd"], 0.07)
        self.assertIsNone(total["cache_hit_ratio"])
        rows = {row["id"]: row for row in value["usage"]["providers"]}
        self.assertEqual(rows["p-alpha"]["tokens"], 160)
        self.assertEqual(rows["p-beta"]["tokens"], 70)
        self.assertEqual(sum(row["tokens"] for row in value["usage"]["buckets"]), 230)
        self.assertEqual(len(value["usage"]["buckets"]), 24)
        self.assertEqual(value["routing"]["groups"][0]["members_count"], 2)

    def test_absent_prices_and_native_cache_are_unknown_not_zero(self):
        self.history([self.legacy(credits=99), self.native()])
        total = self.snap()["usage"]["totals"]
        self.assertIsNone(total["cost_usd"])
        self.assertIsNone(total["cached_tokens"])
        self.assertIsNone(total["cache_hit_ratio"])
        self.assertEqual(total["priced_requests"], 0)
        self.history([self.legacy(cost=0.0)])
        total = self.snap()["usage"]["totals"]
        self.assertEqual(total["cost_usd"], 0.0)
        self.assertAlmostEqual(total["cache_hit_ratio"], 30 / 140)

    def test_partial_price_coverage_does_not_claim_full_cost(self):
        self.history([self.legacy(cost=1.25), self.native()])
        value = self.snap()["usage"]
        self.assertIsNone(value["totals"]["cost_usd"])
        self.assertEqual(value["totals"]["known_cost_usd"], 1.25)
        self.assertEqual(value["totals"]["priced_requests"], 1)
        self.assertIn("Some requests remain unpriced", value["message"])

    def test_provider_and_local_calendar_filters(self):
        self.history([self.legacy(), self.native(),
                      self.legacy(t="2026-11-14T01:00:00Z"),
                      self.legacy(t="2026-11-13T23:59:59Z"),
                      self.native(time=NOW + 10)])
        self.assertEqual(self.snap()["usage"]["totals"]["requests"], 2)
        value = self.snap("7d", "p-alpha")
        self.assertEqual(value["usage"]["totals"]["requests"], 2)
        self.assertEqual(len(value["usage"]["buckets"]), 7)
        self.assertEqual(value["filters"]["start_date"], "2026-11-14")
        self.assertEqual(self.snap("30d")["usage"]["totals"]["requests"], 4)
        self.assertEqual(self.snap("all")["usage"]["totals"]["requests"], 4)

    def test_explicit_timezone_offsets_use_local_calendar(self):
        self.history([self.legacy(t="2026-11-20T00:10:00+02:00"),
                      self.legacy(t="2026-11-19T23:10:00-02:00")])
        value = self.snap()
        self.assertEqual(value["usage"]["totals"]["requests"], 1)
        self.assertEqual(value["usage"]["buckets"][1]["requests"], 1)

    def test_missing_history_is_unknown_and_existing_empty_log_is_zero(self):
        value = self.snap()
        self.assertEqual(value["usage"]["state"], "unavailable")
        self.assertIsNone(value["usage"]["totals"]["requests"])
        self.assertEqual(value["quota"]["state"], "unavailable")
        self.history([])
        self.assertEqual(self.snap()["usage"]["totals"]["requests"], 0)

    def test_group_fallback_is_not_claimed_as_actual_provider(self):
        self.history([self.native(upstream="")])
        rows = self.snap()["usage"]["providers"]
        self.assertEqual(rows[0]["id"], backend.UNKNOWN_PROVIDER)

    def test_bad_long_and_append_tail_records_are_bounded_and_reported(self):
        path = self.directory / "usage.jsonl"
        good = json.dumps(self.native()).encode() + b"\n"
        path.write_bytes(good + b"not-json\n" + b"x" * (backend.MAX_LINE + 100)
                         + b"\n" + good + b'{"time":')
        result = self.snap()["usage"]
        self.assertEqual(result["state"], "partial")
        self.assertEqual(result["totals"]["requests"], 2)
        self.assertEqual((result["scan"]["invalid"], result["scan"]["oversized"],
                          result["scan"]["incomplete"]), (1, 1, 1))

    def test_invalid_timestamp_and_nonfinite_or_large_numbers_never_crash(self):
        self.history([self.native(time="not-a-date"),
                      self.native(input_tokens=10 ** 400),
                      self.native(cost_usd=True)])
        value = self.snap()["usage"]
        self.assertTrue(value["scan"]["partial"])
        self.assertEqual(value["scan"]["unknown_time"], 1)
        self.assertEqual(value["totals"]["requests"], 2)
        self.assertIsNone(value["totals"]["tokens"])
        self.assertIsNone(value["totals"]["cost_usd"])

    def test_scan_byte_limit_is_visible_not_a_complete_chart(self):
        raw = json.dumps(self.native()).encode() + b"\n"
        (self.directory / "usage.jsonl").write_bytes(raw * 10)
        with patch.object(backend, "MAX_SCAN_BYTES", len(raw) * 3):
            value = self.snap()["usage"]
        self.assertEqual(value["totals"]["requests"], 3)
        self.assertTrue(value["scan"]["limited"])
        self.assertEqual(value["state"], "partial")

    def test_snapshot_does_not_follow_concurrently_appended_records(self):
        path = self.directory / "usage.jsonl"
        raw = json.dumps(self.native()).encode() + b"\n"
        path.write_bytes(raw)
        original_fstat = backend.os.fstat
        seen = [False]
        def capture(fd):
            st = original_fstat(fd)
            if stat.S_ISREG(st.st_mode) and st.st_size == len(raw) and not seen[0]:
                seen[0] = True
                # First fstat only validates regularity; append after the second
                # call below is the snapshot boundary we want to exercise.
            elif stat.S_ISREG(st.st_mode) and st.st_size == len(raw) and seen[0]:
                with path.open("ab") as out:
                    out.write(raw)
            return st
        with patch.object(backend.os, "fstat", side_effect=capture):
            result = self.snap()["usage"]
        self.assertEqual(result["totals"]["requests"], 1)
        self.assertEqual(path.stat().st_size, len(raw) * 2)

    def test_large_history_has_bounded_working_memory(self):
        # 64 MiB is read, parsed, and counted; only one 64-KiB row is resident.
        row = self.native()
        row["ignored_private_text"] = "x" * 65536
        raw = json.dumps(row).encode() + b"\n"
        path = self.directory / "usage.jsonl"
        with path.open("wb") as output:
            for _ in range(1024):
                output.write(raw)
        tracemalloc.start()
        try:
            with patch.object(backend, "MAX_SCAN_SECONDS", 60):
                value = self.snap()["usage"]
            _, peak = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()
        self.assertEqual(value["totals"]["requests"], 1024)
        self.assertLess(peak, 4 * 1024 * 1024)
        self.assertGreater(value["scan"]["bytes"], 64 * 1024 * 1024)

    def test_cardinality_and_all_time_chart_are_bounded(self):
        self.history([self.legacy(provider="historical-" + str(i)) for i in range(300)]
                     + [self.legacy(t=f"{year}-01-01T00:00:00Z") for year in range(1800, 2026)])
        value = self.snap("all")["usage"]
        self.assertLessEqual(len(value["providers"]), backend.MAX_PROVIDERS + 1)
        self.assertLessEqual(len(value["buckets"]), 121)
        self.assertTrue(value["scan"]["provider_overflow"])
        self.assertEqual(value["buckets"][0]["label"], "Earlier")

    def test_snapshot_whitelists_fields_and_never_calls_provider_hooks(self):
        self.history([self.legacy(error="PRIVATE-CANARY", providerAccount="PRIVATE-CANARY",
                                  body="PRIVATE-CANARY")])
        value = self.snap()
        encoded = json.dumps(value)
        self.assertNotIn("PRIVATE-CANARY", encoded)
        self.assertNotIn("/private/path", encoded)
        self.assertEqual(self.client.calls, [["status"], ["providers", "list"], ["routes", "list"],
                                             ["groups", "list"], ["agents", "list"], ["privacy", "show"],
                                             ["plugins", "quota", "list"]])
        self.assertFalse(value["routing"]["can_set_default"])
        self.assertIsNone(value["routing"]["default_route"])
        self.assertEqual(value["status"]["privacy_runtime_state"], "not_checked")
        self.assertFalse(value["agents"][1]["editable"])

    def test_controller_failure_is_partial_static_and_does_not_leak_diagnostic(self):
        self.client.data[("providers", "list")] = Error("PRIVATE-CANARY")
        self.history([])
        value = self.snap()
        self.assertIn("providers", [row["scope"] for row in value["errors"]])
        self.assertNotIn("PRIVATE-CANARY", json.dumps(value))
        self.assertTrue(value["status"]["healthy"])

    def test_invalid_filters_are_rejected_before_cli(self):
        for period, provider in [("yesterday-ish", "all"), ("today", "--config"), ("today", "bad\n")]:
            with self.assertRaises(Error):
                self.snap(period, provider)
        self.assertEqual(self.client.calls, [])

    def test_malformed_owned_state_does_not_abort_snapshot(self):
        path = self.directory / "agents/applied.json"
        path.parent.mkdir()
        path.write_bytes(b"[" * 1500 + b"0" + b"]" * 1500)
        self.history([])
        value = self.snap()
        self.assertFalse(value["agents"][0]["revertible"])
        self.assertEqual(value["status"]["healthy"], True)

    def test_configured_usage_path_is_honored(self):
        archive = self.directory / "nested/selected.jsonl"
        archive.parent.mkdir()
        archive.write_bytes(json.dumps(self.native()).encode() + b"\n")
        self.client.data[("groups", "list")]["usage_file"] = "nested/selected.jsonl"
        self.assertEqual(self.snap()["usage"]["totals"]["requests"], 1)


class QuotaTests(Fixture):
    def cache(self, windows, **extra):
        quota = {"provider": "alpha", "name": "Alpha", "user": "PRIVATE-ACCOUNT",
                 "windows": windows, **extra}
        self.saved("quotas.json", {"PRIVATE-ACCOUNT": {"at": "2026-11-20T10:00:00Z", "quota": quota}})

    def test_cached_percent_is_explicitly_dated_and_never_refreshed(self):
        self.cache([{"name": "Daily", "used": 75, "resetsAt": "2026-11-21T00:00:00Z"}])
        value = self.snap()["quota"]
        self.assertEqual(value["state"], "cached")
        self.assertEqual(value["rows"][0]["remaining_percent"], 25)
        self.assertEqual(value["rows"][0]["cached_at"], "2026-11-20T10:00:00+00:00")
        self.assertNotIn("PRIVATE-ACCOUNT", json.dumps(value))
        self.assertIn("does not contact providers", value["message"])

    def test_expired_text_unlimited_balance_and_missing_are_not_full_allowance(self):
        self.cache([{"used": 10, "resetsAt": "2026-11-20T11:00:00Z"},
                    {"used": 0, "text": True}, {"used": 0, "unlimited": True},
                    {"used": 0, "balance": 4}, {}, {"used": 150}])
        value = self.snap()["quota"]
        self.assertTrue(all(row["remaining_percent"] is None for row in value["rows"]))
        self.assertEqual(value["rows"][0]["last_known_percent"], 90)
        self.assertTrue(value["rows"][0]["expired"])

    def test_provider_filter_and_bad_cache_are_explicit(self):
        self.cache([{"used": 20}])
        self.assertEqual(self.snap(provider="p-beta")["quota"]["rows"], [])
        (self.directory / "quotas.json").write_bytes(b"not-json")
        value = self.snap()["quota"]
        self.assertEqual(value["state"], "unavailable")
        self.assertIn("could not be read", value["message"])


class ActionTests(Fixture):
    def test_apply_delegates_exact_argv_without_shell_or_service_restart(self):
        result = backend.action(self.client, "agent.route", {"agent": "gemini", "route": "alpha/model"})
        self.assertTrue(result["ok"])
        self.assertTrue(result["agent_restart_required"])
        self.assertEqual(self.client.calls[-1], ["agents", "apply", "gemini", "--route", "alpha/model"])
        self.assertFalse(any(call[0] == "service" for call in self.client.calls))
        self.assertNotIn("/private/path", json.dumps(result))

    def test_readonly_unknown_option_payload_and_global_default_never_mutate(self):
        for action, payload in [
                ("agent.route", {"agent": "cursor", "route": "alpha/model"}),
                ("agent.route", {"agent": "gemini", "route": "unknown"}),
                ("agent.route", {"agent": "--config", "route": "alpha/model"}),
                ("agent.route", {"agent": "gemini", "route": "alpha/model", "force": True}),
                ("route.default", {"route": "alpha/model"}),
                ("agent.revert", {"agent": "gemini"})]:
            self.assertFalse(backend.action(self.client, action, payload)["ok"])
        self.assertFalse(any("apply" in call or "revert" in call for call in self.client.calls))

    def test_revert_uses_owned_backup_without_force(self):
        self.saved("agents/applied.json", {"gemini": {"backup": "/private/backup", "route": "alpha/model"}})
        self.assertTrue(self.snap()["agents"][0]["revertible"])
        result = backend.action(self.client, "agent.revert", {"agent": "gemini"})
        self.assertTrue(result["ok"])
        self.assertEqual(self.client.calls[-1], ["agents", "revert", "gemini"])
        self.assertNotIn("--force", self.client.calls[-1])

    def test_cli_refusal_is_not_reported_as_success_or_raw_error(self):
        key = ("agents", "apply", "gemini", "--route", "alpha/model")
        self.client.data[key] = Error("PRIVATE-CANARY")
        result = backend.action(self.client, "agent.route", {"agent": "gemini", "route": "alpha/model"})
        self.assertFalse(result["ok"])
        self.assertNotIn("PRIVATE-CANARY", json.dumps(result))


@unittest.skipUnless(os.environ.get("ZCALLD_TEST_BINARY"), "Set ZCALLD_TEST_BINARY for isolated actual CLI actions")
class NativeActionTests(Fixture):
    def test_actual_cli_apply_revert_and_user_edit_protection_in_private_home(self):
        binary = os.environ["ZCALLD_TEST_BINARY"]
        config = self.directory / "config.conf"
        config.write_text("[server]\nlisten=127.0.0.1:1\n[provider fixture]\n"
                          "base_url=http://127.0.0.1:1\nprotocol=chat\nauth=none\n"
                          "[route fixture-model]\nprovider=fixture\nmodel=local-only\n")
        settings = self.base / ".gemini/settings.json"
        settings.parent.mkdir()
        original = b'{\n  "theme":"personal", "unknown":{"preserve":true}\n}\n'
        settings.write_bytes(original)
        client = Client(config=config, binary=binary)
        minimal = {"HOME": str(self.base), "XDG_CONFIG_HOME": str(self.base / ".config"),
                   "XDG_STATE_HOME": str(self.base / ".local/state"), "PATH": "/usr/bin:/bin",
                   "TMPDIR": str(self.base), "LANG": "C.UTF-8"}
        with patch.dict(os.environ, minimal, clear=True):
            applied = backend.action(client, "agent.route", {"agent": "gemini", "route": "fixture-model"})
            self.assertTrue(applied["ok"], applied)
            self.assertNotEqual(settings.read_bytes(), original)
            reverted = backend.action(client, "agent.revert", {"agent": "gemini"})
            self.assertTrue(reverted["ok"], reverted)
            self.assertEqual(settings.read_bytes(), original)
            self.assertTrue(backend.action(client, "agent.route",
                                          {"agent": "gemini", "route": "fixture-model"})["ok"])
            edited = settings.read_bytes() + b"\n "
            settings.write_bytes(edited)
            denied = backend.action(client, "agent.revert", {"agent": "gemini"})
            self.assertFalse(denied["ok"])
            self.assertEqual(settings.read_bytes(), edited)


class SavedPricingTests(Fixture):
    def prices(self, **overrides):
        price = {"prompt": "0.000002", "completion": "0.000008",
                 "input_cache_read": "0.0000002", "input_cache_write": "0.0000025"}
        price.update(overrides)
        self.saved("model-catalog.json", {"data": [
            {"id": "alpha/model", "pricing": price},
            {"id": "beta/model", "pricing": price}]})

    def test_saved_per_token_prices_split_cache_and_do_not_add_reasoning_twice(self):
        self.prices()
        self.history([self.legacy(model="model", reasoning=999)])
        value = self.snap()["usage"]
        self.assertAlmostEqual(value["totals"]["cost_usd"], 0.000391)
        self.assertEqual(value["totals"]["cost_basis"], "saved_prices")
        self.assertEqual(value["totals"]["estimated_requests"], 1)
        self.assertEqual(value["pricing"]["priced_models"], 2)
        self.assertIsNotNone(value["pricing"]["updated_at"])
        self.assertIn("not provider invoices", value["message"])

    def test_recorded_amount_has_priority_including_zero(self):
        self.prices()
        self.history([self.legacy(model="model", cost=0), self.legacy(model="model")])
        value = self.snap()["usage"]["totals"]
        self.assertEqual(value["cost_basis"], "mixed")
        self.assertEqual((value["recorded_requests"], value["estimated_requests"]), (1, 1))
        self.assertAlmostEqual(value["known_cost_usd"], 0.000391)

    def test_native_missing_cache_breakdown_preserves_partial_price_coverage(self):
        self.prices()
        self.history([self.legacy(model="model"), self.native()])
        value = self.snap()["usage"]
        total = value["totals"]
        self.assertIsNone(total["cost_usd"])
        self.assertEqual((total["priced_requests"], total["unpriced_requests"]), (1, 1))
        self.assertAlmostEqual(total["known_cost_usd"], 0.000391)
        self.assertEqual(total["unpriced_reasons"], {"cache_breakdown_missing": 1})
        self.assertEqual(value["providers"][0]["priced_requests"], 1)

    def test_native_complete_cache_fields_use_total_input_semantics(self):
        self.prices()
        self.history([self.native(cache_read_tokens=20, cache_write_tokens=10)])
        total = self.snap()["usage"]["totals"]
        self.assertAlmostEqual(total["cost_usd"], 30 * .000002 + 10 * .000008 + 20 * .0000002 + 10 * .0000025)

    def test_complex_or_unknown_costs_are_not_silently_estimated(self):
        self.prices()
        cases = [({"cache_unknown": True}, "cache_breakdown_missing"),
                 ({"cache_write_1h": 10}, "one_hour_cache_price_missing"),
                 ({"tier_sent": "priority"}, "service_tier_unknown"),
                 ({"tier_served": {"bad": True}}, "service_tier_unknown"),
                 ({"in": 210000}, "context_tier_price_missing"),
                 ({"served": "another-unknown-model"}, "served_model_price_missing")]
        for extra, reason in cases:
            with self.subTest(reason=reason):
                self.history([self.legacy(model="model", **extra)])
                total = self.snap()["usage"]["totals"]
                self.assertIsNone(total["known_cost_usd"])
                self.assertEqual(total["unpriced_reasons"], {reason: 1})

    def test_explicit_upstream_name_is_not_misclassified_as_swapped(self):
        self.prices()
        self.history([self.legacy(model="model", served="underlying")])
        self.assertEqual(self.snap()["usage"]["totals"]["priced_requests"], 1)

    def test_missing_cache_price_is_unknown_only_when_that_cache_is_used(self):
        self.prices(input_cache_read=None)
        self.history([self.legacy(model="model")])
        self.assertIsNone(self.snap()["usage"]["totals"]["known_cost_usd"])
        self.history([self.legacy(model="model", cache_read=0)])
        self.assertEqual(self.snap()["usage"]["totals"]["priced_requests"], 1)

    def test_invalid_duplicate_price_and_unreadable_catalog_do_not_erase_recorded_cost(self):
        for catalog in [b"bad", json.dumps({"data": [{"id": "alpha/model", "pricing": {"prompt": "NaN", "completion": "1"}}]}).encode(),
                        json.dumps({"data": [{"id": "alpha/model", "pricing": {"prompt": "1", "completion": "1"}}] * 2}).encode()]:
            (self.directory / "model-catalog.json").write_bytes(catalog)
            self.history([self.legacy(model="model", cost=1.25), self.legacy(model="model")])
            total = self.snap()["usage"]["totals"]
            self.assertEqual(total["known_cost_usd"], 1.25)
            self.assertEqual(total["priced_requests"], 1)


class ExplicitQuotaTests(Fixture):
    def metadata(self, **overrides):
        row = {"id": "quota#opaque", "provider": "alpha", "label": "Fixture account",
               "enabled": True, "can_refresh": True, "reason": "", "cached_at": "2026-11-20T10:00:00Z"}
        row.update(overrides)
        self.client.data[("plugins", "quota", "list")] = {
            "schema_version": 1, "local_only": True, "accounts": [row],
            "readings": [{"account": "quota#opaque", "at": "2026-11-20T10:00:00Z",
                          "windows": [{"name": "Daily", "used": 25}], "auth": "PRIVATE-CANARY"}]}

    def test_snapshot_reads_only_local_capabilities_and_cache(self):
        self.metadata()
        quota = self.snap()["quota"]
        self.assertTrue(quota["accounts"][0]["can_refresh"])
        self.assertEqual(quota["rows"][0]["remaining_percent"], 75)
        self.assertNotIn("PRIVATE-CANARY", json.dumps(quota))
        self.assertFalse(any("refresh" in args or "invoke" in args for args in self.client.calls))

    def test_old_helper_keeps_imported_cache_and_marks_refresh_unavailable(self):
        self.saved("quotas.json", {"old": {"at": "2026-11-20T10:00:00Z", "quota": {
            "provider": "alpha", "windows": [{"used": 10}]}}})
        self.client.data[("plugins", "quota", "list")] = Error("unknown command PRIVATE-CANARY")
        value = self.snap()["quota"]
        self.assertEqual(value["rows"][0]["remaining_percent"], 90)
        self.assertFalse(value["refresh_available"])
        self.assertIn("0.1.6", value["message"])
        self.assertNotIn("PRIVATE-CANARY", json.dumps(value))

    def test_explicit_refresh_targets_one_eligible_account_without_secret_input(self):
        self.metadata()
        result = backend.action(self.client, "quota.refresh", {"account": "quota#opaque"})
        self.assertTrue(result["ok"])
        self.assertEqual(self.client.calls, [["plugins", "quota", "list"],
            ["plugins", "quota", "refresh", "--account", "quota#opaque"]])
        self.assertFalse(result["restart_required"])

    def test_disabled_unsupported_and_invalid_payload_do_not_refresh(self):
        for extra in [{"enabled": False}, {"can_refresh": False, "reason": "unsupported"}]:
            self.metadata(**extra)
            self.client.calls.clear()
            self.assertFalse(backend.action(self.client, "quota.refresh", {"account": "quota#opaque"})["ok"])
            self.assertFalse(any("refresh" in args for args in self.client.calls))
        self.client.calls.clear()
        self.assertFalse(backend.action(self.client, "quota.refresh", {"account": "--config"})["ok"])
        self.assertEqual(self.client.calls, [])

    def test_refresh_errors_never_forward_raw_provider_diagnostic(self):
        self.metadata()
        self.client.data[("plugins", "quota", "refresh", "--account", "quota#opaque")] = {
            "ok": False, "error": "PRIVATE-CANARY", "token": "PRIVATE-CANARY"}
        value = backend.action(self.client, "quota.refresh", {"account": "quota#opaque"})
        self.assertFalse(value["ok"])
        self.assertEqual(value["error_code"], "provider_error")
        self.assertNotIn("PRIVATE-CANARY", json.dumps(value))


if __name__ == "__main__":
    unittest.main()
