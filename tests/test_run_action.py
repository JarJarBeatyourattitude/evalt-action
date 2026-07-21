from __future__ import annotations

import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from run_action import Settings, gate_command, optimize_command  # noqa: E402


class ActionContractTests(unittest.TestCase):
    def settings(self, **overrides: str) -> Settings:
        values = {
            "EVALT_ACTION_SUITE": "evalt.json",
            "EVALT_ACTION_RESULT": "out/result.json",
            "EVALT_ACTION_OPTIMIZE": "true",
            "EVALT_ACTION_VERSION": "0.9.1",
            "EVALT_ACTION_MIN_PASS_RATE": "0.97",
            "EVALT_ACTION_MAX_COST_PER_SUCCESS": "0.002",
            "EVALT_ACTION_REQUIRE_COMPLETE_COVERAGE": "true",
            "EVALT_ACTION_FIXED_PROMPT": "true",
            "EVALT_ACTION_MAX_PARALLEL_MODELS": "24",
            "EVALT_ACTION_MAX_PARALLEL_SCENARIOS": "48",
            "EVALT_ACTION_REQUEST_TIMEOUT_SECONDS": "900",
            "EVALT_ACTION_HTML_REPORT": "out/report.html",
            "EVALT_ACTION_JUNIT_REPORT": "out/junit.xml",
        }
        values.update(overrides)
        with patch.dict(os.environ, values, clear=True):
            return Settings.from_environment()

    def test_optimization_preserves_budget_in_suite_and_forwards_runtime_levers(self):
        command = optimize_command(self.settings())
        self.assertEqual(command[:4], [sys.executable, "-m", "evalt", "optimize"])
        self.assertIn("--fixed-prompt", command)
        self.assertEqual(command[command.index("--max-parallel-models") + 1], "24")
        self.assertEqual(command[command.index("--max-parallel-scenarios") + 1], "48")
        self.assertEqual(command[command.index("--request-timeout") + 1], "900.0")
        self.assertNotIn("OPENROUTER_API_KEY", " ".join(command))
        self.assertFalse(any("budget" in part for part in command))

    def test_gate_uses_same_quality_coverage_and_cost_contract(self):
        command = gate_command(self.settings())
        self.assertEqual(command[command.index("--min-pass-rate") + 1], "0.97")
        self.assertEqual(command[command.index("--max-cost-per-success") + 1], "0.002")
        self.assertIn("--require-complete-coverage", command)
        self.assertIn("--json", command)

    def test_mutable_or_shell_shaped_versions_are_rejected(self):
        for version in ("latest", "0.9.1; echo secret", "../0.9.1"):
            with self.subTest(version=version), patch.dict(
                os.environ, {"EVALT_ACTION_VERSION": version}, clear=True
            ):
                with self.assertRaisesRegex(ValueError, "exact release"):
                    Settings.from_environment()

    def test_action_metadata_never_accepts_a_provider_key_input(self):
        metadata = (ROOT / "action.yml").read_text(encoding="utf-8")
        inputs = metadata.split("outputs:", 1)[0]
        self.assertNotIn("openrouter-api-key", inputs.lower())
        self.assertIn("actions/setup-python@v7", metadata)

    def test_offline_fixture_paths_are_real(self):
        fixture = ROOT / "tests" / "fixtures"
        self.assertTrue((fixture / "evalt.json").is_file())
        self.assertTrue((fixture / "evalt-result.json").is_file())


if __name__ == "__main__":
    unittest.main()
