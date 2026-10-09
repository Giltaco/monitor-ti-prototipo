import json
import tempfile
import unittest
from pathlib import Path

from monitor_ti.collector import Collector
from monitor_ti.core import DEFAULTS, DiskTrend, Observation, RuleEngine, Store, load_config, rate


class MonitoringTests(unittest.TestCase):
    def setUp(self):
        self.config = dict(DEFAULTS, recovery_s=5)
        self.engine = RuleEngine(self.config)

    def observation(self, value, hold=10):
        return Observation("test", value, hold, "Prueba", {"present": value}, "Revisar")

    def ts(self, second):
        return f"2026-10-09T00:00:{second:02d}.000+00:00"

    def test_rates_require_two_valid_samples_and_detect_reset(self):
        self.assertIsNone(rate(100, None, 5))
        self.assertEqual(rate(300, 100, 5), 40)
        self.assertIsNone(rate(20, 100, 5))
        self.assertIsNone(rate(100, 100, 0))
        self.assertEqual(rate(100, 100, 5), 0)

    def test_transient_peak_does_not_open_incident(self):
        self.assertEqual(self.engine.evaluate([self.observation(True)], 0, self.ts(0)), [])
        self.assertEqual(self.engine.evaluate([self.observation(False)], 8, self.ts(8)), [])
        self.assertEqual(self.engine.evaluate([self.observation(True)], 10, self.ts(10)), [])
        self.assertEqual(self.engine.evaluate([self.observation(True)], 19, self.ts(19)), [])

    def test_sustained_incident_is_single_and_requires_recovery_window(self):
        self.engine.evaluate([self.observation(True)], 0, self.ts(0))
        opened = self.engine.evaluate([self.observation(True)], 10, self.ts(10))
        self.assertEqual(len(opened), 1)
        original_id = opened[0][1]["id"]
        self.assertEqual(opened[0][1]["first_signal_ts"], self.ts(0))
        self.assertEqual(self.engine.evaluate([self.observation(True)], 15, self.ts(15)), [])
        self.assertEqual(self.engine.evaluate([self.observation(False)], 20, self.ts(20)), [])
        recovered = self.engine.evaluate([self.observation(False)], 25, self.ts(25))
        self.assertEqual(recovered[0][0], "recovered")
        self.assertEqual(recovered[0][1]["id"], original_id)

    def test_unknown_data_does_not_falsely_recover_an_incident(self):
        self.engine.evaluate([self.observation(True, hold=0)], 0, self.ts(0))
        self.engine.evaluate([self.observation(False)], 1, self.ts(1))
        self.engine.evaluate([self.observation(None)], 20, self.ts(20))
        self.assertIn("test", self.engine.active)
        self.assertEqual(self.engine.active["test"]["quality"], "unknown")
        self.assertEqual(self.engine.evaluate([self.observation(False)], 21, self.ts(21)), [])
        self.assertEqual(self.engine.evaluate([self.observation(False)], 26, self.ts(26))[0][0], "recovered")

    def test_hysteresis_keeps_cpu_warning_between_thresholds(self):
        def sample(value):
            return {"cpu_percent": value, "ram": {}, "disk": {}, "cpu_temperature": {}}
        initial = next(o for o in self.engine.observations(sample(95)) if o.key == "cpu")
        initial.hold_s = 0
        self.engine.evaluate([initial], 0, self.ts(0))
        middle = next(o for o in self.engine.observations(sample(85)) if o.key == "cpu")
        self.assertTrue(middle.triggered)
        cool = next(o for o in self.engine.observations(sample(75)) if o.key == "cpu")
        self.assertFalse(cool.triggered)

    def test_disk_forecast_needs_history_and_does_not_predict_with_flat_space(self):
        trend = DiskTrend()
        for i in range(20):
            estimate = trend.update(i * 10, 2 ** 30 - i * 1024 * 100)
        self.assertIsNone(estimate["hours_to_full"])
        for i in range(20, 40):
            estimate = trend.update(i * 10, 2 ** 30 - i * 1024 * 100)
        self.assertGreater(estimate["hours_to_full"], 0)
        self.assertAlmostEqual(estimate["loss_bytes_s"], 10240, places=1)
        flat = DiskTrend()
        for i in range(40):
            result = flat.update(i * 10, 2 ** 30)
        self.assertIsNone(result["hours_to_full"])
        self.assertIsNone(trend.update(410, None)["hours_to_full"])
        self.assertEqual(len(trend.points), 0)

    def test_http_detection_retains_first_failed_probe_timestamp(self):
        sample = {"cpu_percent": None, "ram": {}, "disk": {}, "service":
                  {"ok": False, "consecutive_failures": 3, "first_failure_ts": self.ts(0)}}
        obs = next(o for o in self.engine.observations(sample) if o.key == "service")
        change = self.engine.evaluate([obs], 10, self.ts(10))
        self.assertEqual(change[0][1]["first_signal_ts"], self.ts(0))

    def test_healthy_but_slow_service_opens_degradation_incident(self):
        config = dict(DEFAULTS, service_latency_warn_ms=500, service_latency_clear_ms=300,
                      service_latency_hold_s=4, recovery_s=2)
        engine = RuleEngine(config)
        sample = {"cpu_percent": None, "ram": {}, "disk": {},
                  "service": {"ok": True, "latency_ms": 750, "consecutive_failures": 0}}
        slow = next(o for o in engine.observations(sample) if o.key == "service_latency")
        self.assertEqual(engine.evaluate([slow], 0, self.ts(0)), [])
        opened = engine.evaluate([slow], 4, self.ts(4))
        self.assertEqual(opened[0][1]["rule_key"], "service_latency")
        self.assertEqual(opened[0][1]["severity"], "warning")

    def test_store_distinguishes_attention_recovery_and_restart(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "test.sqlite3"
            store = Store(path)
            changes = self.engine.evaluate([self.observation(True, 0)], 0, self.ts(0))
            sample = {"timestamp": self.ts(0), "device_id": "test"}
            store.save(sample, changes, 24 * 365)
            iid = changes[0][1]["id"]
            store.mark(iid)
            store.mark(iid, action=True, note="Revisar servicio")
            item = store.incidents()[0]
            self.assertEqual(item["status"], "open")
            self.assertIsNone(item["recovered_ts"])
            self.assertIsNotNone(item["action_ts"])
            self.assertIsNotNone(item["acknowledged_ts"])
            store.close()
            after_restart = Store(path)
            interrupted = after_restart.incidents()[0]
            self.assertEqual(interrupted["status"], "interrupted")
            self.assertIsNone(interrupted["recovered_ts"])
            after_restart.close()

    def test_live_collector_returns_real_serializable_metrics_without_esp32(self):
        collector = Collector(dict(DEFAULTS), "integration-test")
        sample = collector.read()
        self.assertEqual(sample["source"], "real/psutil")
        self.assertGreater(sample["ram"]["total_bytes"], 0)
        self.assertGreater(sample["disk"]["total_bytes"], 0)
        self.assertIsNone(sample["cpu_percent"])
        self.assertIsNone(sample["cpu_per_core_percent"])
        self.assertIn("cpu_frequency", sample)
        self.assertIn("availability", sample)
        self.assertTrue(all("kind" in nic and "is_vpn_like" in nic for nic in sample["interfaces"]))
        self.assertIsNone(sample["service"])
        json.dumps(sample, allow_nan=False)

    def test_interface_classification_is_explicit(self):
        self.assertEqual(Collector.interface_kind("Loopback Pseudo-Interface 1"), "loopback")
        self.assertEqual(Collector.interface_kind("WireGuard Tunnel"), "vpn_o_tunel")
        self.assertEqual(Collector.interface_kind("Wi-Fi"), "wifi")

    def test_config_rejects_invalid_values(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "bad.json"
            for value in ({"interval_s": 0}, {"cpu_warn_percent": 999}, {"unknown": True}, {"expected_processes": "notepad.exe"}, {"retention_hours": -1},
                          {"temperature_provider": "inventado"}, {"service_latency_warn_ms": 100, "service_latency_clear_ms": 200}):
                path.write_text(json.dumps(value), encoding="utf-8")
                with self.assertRaises(ValueError):
                    load_config(path)


if __name__ == "__main__":
    unittest.main()
