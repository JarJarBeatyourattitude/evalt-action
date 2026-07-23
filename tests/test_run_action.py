from __future__ import annotations

import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from run_action import Settings, _route_version, _write_summary, gate_command, install_target, optimize_command  # noqa: E402


class ActionContractTests(unittest.TestCase):
    def settings(self, **overrides: str) -> Settings:
        values = {
            "EVALT_ACTION_SUITE": "evalt.json",
            "EVALT_ACTION_RESULT": "out/result.json",
            "EVALT_ACTION_BASELINE": "out/baseline.json",
            "EVALT_ACTION_LIBRARY_ROOT": ".evalt/private-library",
            "EVALT_ACTION_OPTIMIZE": "true",
            "EVALT_ACTION_VERSION": "0.10.32",
            "EVALT_ACTION_MIN_PASS_RATE": "0.97",
            "EVALT_ACTION_MAX_COST_PER_SUCCESS": "0.002",
            "EVALT_ACTION_REQUIRE_COMPLETE_COVERAGE": "true",
            "EVALT_ACTION_MAX_REGRESSIONS": "1",
            "EVALT_ACTION_MAX_QUALITY_DROP_PP": "0.5",
            "EVALT_ACTION_MAX_COST_INCREASE_PCT": "10",
            "EVALT_ACTION_MAX_P90_INCREASE_MS": "250",
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
        self.assertEqual(
            Path(command[command.index("--library-root") + 1]),
            Path(".evalt/private-library"),
        )
        self.assertNotIn("OPENROUTER_API_KEY", " ".join(command))
        self.assertFalse(any("budget" in part for part in command))

    def test_gate_uses_same_quality_coverage_and_cost_contract(self):
        command = gate_command(self.settings())
        self.assertEqual(command[command.index("--min-pass-rate") + 1], "0.97")
        self.assertEqual(command[command.index("--max-cost-per-success") + 1], "0.002")
        self.assertIn("--require-complete-coverage", command)
        self.assertIn("--json", command)
        self.assertEqual(
            Path(command[command.index("--baseline") + 1]),
            Path("out/baseline.json"),
        )
        self.assertEqual(command[command.index("--max-regressions") + 1], "1")
        self.assertEqual(command[command.index("--max-quality-drop-pp") + 1], "0.5")
        self.assertEqual(command[command.index("--max-cost-increase-pct") + 1], "10.0")
        self.assertEqual(command[command.index("--max-p90-increase-ms") + 1], "250.0")
        self.assertEqual(
            Path(command[command.index("--library-root") + 1]),
            Path(".evalt/private-library"),
        )

    def test_custom_scorer_is_forwarded_as_literal_argv(self):
        command = optimize_command(self.settings(
            EVALT_ACTION_CUSTOM_SCORER_ID="domain-rubric",
            EVALT_ACTION_CUSTOM_SCORER_VERSION="1.0",
            EVALT_ACTION_CUSTOM_SCORER_EXECUTABLE="python3",
            EVALT_ACTION_CUSTOM_SCORER_ARGUMENTS_JSON='["tools/score.py","--strict"]',
            EVALT_ACTION_CUSTOM_SCORER_TIMEOUT_SECONDS="12",
            EVALT_ACTION_CUSTOM_SCORER_MAX_INPUT_BYTES="16777216",
            EVALT_ACTION_CUSTOM_SCORER_MAX_OUTPUT_BYTES="131072",
        ))
        self.assertEqual(
            command[command.index("--custom-scorer-id") + 1], "domain-rubric"
        )
        self.assertEqual(
            command[command.index("--custom-scorer-version") + 1], "1.0"
        )
        self.assertEqual(
            command[command.index("--custom-scorer-executable") + 1], "python3"
        )
        self.assertIn("--custom-scorer-arg=tools/score.py", command)
        self.assertIn("--custom-scorer-arg=--strict", command)
        self.assertEqual(
            command[command.index("--custom-scorer-timeout") + 1], "12.0"
        )
        self.assertEqual(
            command[command.index("--custom-scorer-max-input-bytes") + 1],
            "16777216",
        )
        self.assertEqual(
            command[command.index("--custom-scorer-max-output-bytes") + 1],
            "131072",
        )

    def test_partial_or_non_array_custom_scorer_inputs_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "must be set together"):
            self.settings(EVALT_ACTION_CUSTOM_SCORER_ID="domain-rubric")
        with self.assertRaisesRegex(ValueError, "JSON array of strings"):
            self.settings(
                EVALT_ACTION_CUSTOM_SCORER_ID="domain-rubric",
                EVALT_ACTION_CUSTOM_SCORER_VERSION="1.0",
                EVALT_ACTION_CUSTOM_SCORER_EXECUTABLE="python3",
                EVALT_ACTION_CUSTOM_SCORER_ARGUMENTS_JSON='{"path":"score.py"}',
            )

    def test_webhook_requires_a_url_and_secret_pair_and_redacts_repr(self):
        with self.assertRaisesRegex(ValueError, "must be set together"):
            self.settings(EVALT_ACTION_WEBHOOK_URL="https://hooks.example.test/evalt")
        configured = self.settings(
            EVALT_ACTION_WEBHOOK_URL="https://hooks.example.test/evalt",
            EVALT_ACTION_WEBHOOK_SECRET="fixture-secret-at-least-16-bytes",
            EVALT_ACTION_WEBHOOK_DESTINATION_ID="incident-pipeline",
            EVALT_ACTION_WEBHOOK_REQUIRED="true",
            EVALT_ACTION_WEBHOOK_MAX_ATTEMPTS="4",
        )
        self.assertTrue(configured.webhook_required)
        self.assertEqual(configured.webhook_max_attempts, 4)
        self.assertEqual(configured.webhook_destination_id, "incident-pipeline")
        self.assertNotIn("fixture-secret", repr(configured))

    def test_baseline_tolerances_are_rejected_without_nonnegative_numbers(self):
        for name, value in (
            ("EVALT_ACTION_MAX_REGRESSIONS", "-1"),
            ("EVALT_ACTION_MAX_QUALITY_DROP_PP", "-0.1"),
            ("EVALT_ACTION_MAX_COST_INCREASE_PCT", "-0.01"),
        ):
            with self.subTest(name=name), self.assertRaises(ValueError):
                self.settings(**{name: value})

    def test_baseline_tolerances_require_a_baseline_input(self):
        with self.assertRaisesRegex(ValueError, "require the baseline"):
            self.settings(EVALT_ACTION_BASELINE="")

    def test_mutable_or_shell_shaped_versions_are_rejected(self):
        for version in ("latest", "0.9.4; echo secret", "../0.9.4"):
            with self.subTest(version=version), patch.dict(
                os.environ, {"EVALT_ACTION_VERSION": version}, clear=True
            ):
                with self.assertRaisesRegex(ValueError, "exact release"):
                    Settings.from_environment()

    def test_current_release_installs_the_exact_hosted_wheel(self):
        self.assertEqual(
            install_target("0.10.32"),
            "https://evalt.onrender.com/python-sdk/dist/evalt-0.10.32-py3-none-any.whl",
        )
        self.assertEqual(install_target("0.10.16"), "evalt==0.10.16")

    def test_action_metadata_never_accepts_a_provider_key_input(self):
        metadata = (ROOT / "action.yml").read_text(encoding="utf-8")
        inputs = metadata.split("outputs:", 1)[0]
        self.assertNotIn("openrouter-api-key", inputs.lower())
        self.assertIn("actions/setup-python@v7", metadata)
        self.assertIn("route-version:", metadata)
        self.assertIn("baseline:", inputs)
        self.assertIn("library-root:", inputs)
        self.assertIn("custom-scorer-executable:", inputs)
        self.assertIn("webhook-secret:", inputs)
        self.assertIn("webhook-delivered:", metadata)
        self.assertIn("EVALT_ACTION_WEBHOOK_SECRET", metadata)
        self.assertIn("case-regressions:", metadata)

    def test_route_version_output_is_explicit_and_empty_for_suite_only_results(self):
        self.assertEqual(
            _route_version(
                {"route_version": "rv_" + "a" * 20},
                {"model": "openai/example"},
            ),
            "rv_" + "a" * 20,
        )
        self.assertEqual(
            _route_version(
                {"winner": {"model": "openai/example"}},
                {"model": "openai/example"},
            ),
            "",
        )

    def test_job_summary_makes_baseline_decision_clear_without_case_content(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "summary.md"
            payload = {
                "winner": {
                    "model": "fixture/model",
                    "holdout_pass_rate": 0.96,
                    "estimated_cost_per_successful_call_usd": 0.0002,
                    "cases": [{"output": "PRIVATE_OUTPUT"}],
                }
            }
            gate = {
                "baseline_gate": {
                    "comparable_contract": True,
                    "quality_delta_percentage_points": -1.0,
                    "regressions": 1,
                    "missing_cases": 0,
                    "cost_increase_percent": 5.0,
                    "p90_increase_ms": 25,
                    "failures": ["1 frozen case regression exceeds allowed 0"],
                }
            }
            with patch.dict(
                os.environ, {"GITHUB_STEP_SUMMARY": str(target)}, clear=False
            ):
                _write_summary(
                    self.settings(),
                    status="FAIL",
                    payload=payload,
                    gate=gate,
                )
            rendered = target.read_text(encoding="utf-8")
            self.assertIn("## Frozen baseline", rendered)
            self.assertIn("| Case regressions | 1 / 1 allowed |", rendered)
            self.assertIn("Why the candidate was rejected", rendered)
            self.assertNotIn("PRIVATE_OUTPUT", rendered)
            self.assertNotIn("â", rendered)

    def test_job_summary_preserves_a_measured_zero_quality(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "summary.md"
            with patch.dict(
                os.environ, {"GITHUB_STEP_SUMMARY": str(target)}, clear=False
            ):
                _write_summary(
                    self.settings(),
                    status="FAIL",
                    payload={
                        "winner": {
                            "model": "fixture/model",
                            "holdout_pass_rate": 0.0,
                            "pass_rate": 1.0,
                        }
                    },
                    gate={},
                )
            rendered = target.read_text(encoding="utf-8")
            self.assertIn("| Final-test pass rate | 0.0% |", rendered)

    def test_offline_fixture_paths_are_real(self):
        fixture = ROOT / "tests" / "fixtures"
        self.assertTrue((fixture / "evalt.json").is_file())
        self.assertTrue((fixture / "evalt-result.json").is_file())


if __name__ == "__main__":
    unittest.main()
