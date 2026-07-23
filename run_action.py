from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from typing import Any, Mapping, Sequence


PINNED_VERSION = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+(?:[A-Za-z0-9_.+!-]*)?$")
CURRENT_HOSTED_VERSION = "0.10.28"


def _bool(name: str, default: str) -> bool:
    raw = os.environ.get(name, default).strip().lower()
    if raw not in {"true", "false"}:
        raise ValueError(f"{name} must be true or false, not {raw!r}")
    return raw == "true"


def _optional_number(name: str, *, integer: bool = False) -> str | None:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return None
    try:
        value = int(raw) if integer else float(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be a number") from exc
    if value <= 0:
        raise ValueError(f"{name} must be greater than zero")
    return str(value)


def _nonnegative_number(
    name: str, default: str, *, integer: bool = False
) -> int | float:
    raw = os.environ.get(name, default).strip()
    try:
        value = int(raw) if integer else float(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be a non-negative number") from exc
    if value < 0:
        raise ValueError(f"{name} must be a non-negative number")
    return value


def _optional_nonnegative_number(name: str) -> float | None:
    if not os.environ.get(name, "").strip():
        return None
    return float(_nonnegative_number(name, ""))


@dataclass(frozen=True)
class Settings:
    suite: Path
    result: Path
    baseline: Path | None
    optimize: bool
    version: str
    min_pass_rate: float
    max_cost_per_success: str | None
    require_complete_coverage: bool
    max_regressions: int
    max_quality_drop_pp: float
    max_cost_increase_pct: float | None
    max_p90_increase_ms: float | None
    fixed_prompt: bool
    max_parallel_models: str | None
    max_parallel_scenarios: str | None
    request_timeout_seconds: str | None
    html_report: Path
    junit_report: Path

    @classmethod
    def from_environment(cls) -> "Settings":
        version = os.environ.get("EVALT_ACTION_VERSION", CURRENT_HOSTED_VERSION).strip()
        if not PINNED_VERSION.fullmatch(version):
            raise ValueError(f"evalt-version must be an exact release such as {CURRENT_HOSTED_VERSION}")
        try:
            min_pass_rate = float(os.environ.get("EVALT_ACTION_MIN_PASS_RATE", "0.95"))
        except ValueError as exc:
            raise ValueError("min-pass-rate must be a number from 0 through 1") from exc
        if not 0 <= min_pass_rate <= 1:
            raise ValueError("min-pass-rate must be a number from 0 through 1")
        settings = cls(
            suite=Path(os.environ.get("EVALT_ACTION_SUITE", "evalt.json")),
            result=Path(os.environ.get("EVALT_ACTION_RESULT", "evalt-result.json")),
            baseline=(
                Path(os.environ["EVALT_ACTION_BASELINE"].strip())
                if os.environ.get("EVALT_ACTION_BASELINE", "").strip()
                else None
            ),
            optimize=_bool("EVALT_ACTION_OPTIMIZE", "true"),
            version=version,
            min_pass_rate=min_pass_rate,
            max_cost_per_success=_optional_number("EVALT_ACTION_MAX_COST_PER_SUCCESS"),
            require_complete_coverage=_bool(
                "EVALT_ACTION_REQUIRE_COMPLETE_COVERAGE", "true"
            ),
            max_regressions=int(
                _nonnegative_number(
                    "EVALT_ACTION_MAX_REGRESSIONS", "0", integer=True
                )
            ),
            max_quality_drop_pp=float(
                _nonnegative_number("EVALT_ACTION_MAX_QUALITY_DROP_PP", "0")
            ),
            max_cost_increase_pct=_optional_nonnegative_number(
                "EVALT_ACTION_MAX_COST_INCREASE_PCT"
            ),
            max_p90_increase_ms=_optional_nonnegative_number(
                "EVALT_ACTION_MAX_P90_INCREASE_MS"
            ),
            fixed_prompt=_bool("EVALT_ACTION_FIXED_PROMPT", "false"),
            max_parallel_models=_optional_number(
                "EVALT_ACTION_MAX_PARALLEL_MODELS", integer=True
            ),
            max_parallel_scenarios=_optional_number(
                "EVALT_ACTION_MAX_PARALLEL_SCENARIOS", integer=True
            ),
            request_timeout_seconds=_optional_number(
                "EVALT_ACTION_REQUEST_TIMEOUT_SECONDS"
            ),
            html_report=Path(
                os.environ.get("EVALT_ACTION_HTML_REPORT", "evalt-report.html")
            ),
            junit_report=Path(
                os.environ.get("EVALT_ACTION_JUNIT_REPORT", "evalt-junit.xml")
            ),
        )
        if settings.baseline is None and (
            settings.max_regressions != 0
            or settings.max_quality_drop_pp != 0
            or settings.max_cost_increase_pct is not None
            or settings.max_p90_increase_ms is not None
        ):
            raise ValueError(
                "Baseline regression inputs require the baseline input."
            )
        return settings


def _evalt(*args: str) -> list[str]:
    return [sys.executable, "-m", "evalt", *args]


def install_target(version: str) -> str:
    if version == CURRENT_HOSTED_VERSION:
        return f"https://evalt.onrender.com/python-sdk/dist/evalt-{version}-py3-none-any.whl"
    return f"evalt=={version}"


def optimize_command(settings: Settings) -> list[str]:
    command = _evalt(
        "optimize",
        str(settings.suite),
        "--output",
        str(settings.result),
        "--html-report",
        str(settings.html_report),
        "--junit-report",
        str(settings.junit_report),
    )
    if settings.fixed_prompt:
        command.append("--fixed-prompt")
    if settings.max_parallel_models:
        command.extend(["--max-parallel-models", settings.max_parallel_models])
    if settings.max_parallel_scenarios:
        command.extend(["--max-parallel-scenarios", settings.max_parallel_scenarios])
    if settings.request_timeout_seconds:
        command.extend(["--request-timeout", settings.request_timeout_seconds])
    return command


def gate_command(settings: Settings) -> list[str]:
    command = _evalt(
        "check",
        str(settings.result),
        "--min-pass-rate",
        str(settings.min_pass_rate),
        "--json",
    )
    if settings.max_cost_per_success:
        command.extend(["--max-cost-per-success", settings.max_cost_per_success])
    if settings.require_complete_coverage:
        command.append("--require-complete-coverage")
    if settings.baseline is not None:
        command.extend(
            [
                "--baseline",
                str(settings.baseline),
                "--max-regressions",
                str(settings.max_regressions),
                "--max-quality-drop-pp",
                str(settings.max_quality_drop_pp),
            ]
        )
        if settings.max_cost_increase_pct is not None:
            command.extend(
                ["--max-cost-increase-pct", str(settings.max_cost_increase_pct)]
            )
        if settings.max_p90_increase_ms is not None:
            command.extend(
                ["--max-p90-increase-ms", str(settings.max_p90_increase_ms)]
            )
    return command


def _run(command: Sequence[str], *, capture: bool = False) -> subprocess.CompletedProcess[str]:
    print("+ " + " ".join(command), flush=True)
    return subprocess.run(
        list(command),
        check=False,
        text=True,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.PIPE if capture else None,
    )


def _winner(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    winner = payload.get("winner") or payload.get("selected") or payload.get("report") or payload
    if isinstance(winner, Mapping) and isinstance(winner.get("selected"), Mapping):
        winner = winner["selected"]
    return winner if isinstance(winner, Mapping) else {}


def _route_version(
    payload: Mapping[str, Any], winner: Mapping[str, Any]
) -> str:
    """Return an explicit route package ID without inventing one for suite-only runs."""

    for candidate in (
        payload.get("route_version"),
        payload.get("current_package_id"),
        winner.get("route_version"),
        winner.get("current_package_id"),
    ):
        value = str(candidate or "").strip()
        if value:
            return value
    return ""


def _number(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _write_output(name: str, value: object) -> None:
    path = os.environ.get("GITHUB_OUTPUT")
    if not path:
        return
    with Path(path).open("a", encoding="utf-8") as handle:
        handle.write(f"{name}={value}\n")


def _write_summary(
    settings: Settings,
    *,
    status: str,
    payload: Mapping[str, Any] | None = None,
    gate: Mapping[str, Any] | None = None,
    error: str | None = None,
) -> None:
    """Write a concise, content-free GitHub decision summary."""

    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not path:
        return
    payload = payload or {}
    gate = gate or {}
    winner = _winner(payload)
    quality = _number(
        winner.get("holdout_pass_rate")
        if winner.get("holdout_pass_rate") is not None
        else winner.get("pass_rate")
    )
    cost = winner.get("estimated_cost_per_successful_call_usd")
    model = str(winner.get("model") or "No qualified route")
    spend = _number(
        payload.get("total_provider_spend_usd") or payload.get("provider_spend_usd")
    )
    lines = [
        "# Evalt performance gate",
        "",
        f"**{status}** — `{model}` on the frozen final test.",
        "",
        "| Evidence | Measured |",
        "| --- | ---: |",
        f"| Final-test pass rate | {quality:.1%} |",
        f"| Required pass rate | {settings.min_pass_rate:.1%} |",
        f"| Production cost / 1,000 successful calls | {'—' if cost is None else f'${_number(cost) * 1000:.6f}'} |",
        f"| Tournament provider spend | ${spend:.6f} |",
        f"| Coverage | {str(gate.get('coverage_complete', payload.get('coverage_complete', 'unknown')))} |",
        "",
        f"[JSON result]({settings.result}) · [HTML evidence]({settings.html_report}) · JUnit: `{settings.junit_report}`",
    ]
    baseline_gate = gate.get("baseline_gate")
    if isinstance(baseline_gate, Mapping):
        delta = baseline_gate.get("quality_delta_percentage_points")
        cost_delta = baseline_gate.get("cost_increase_percent")
        p90_delta = baseline_gate.get("p90_increase_ms")
        lines.extend(
            [
                "",
                "## Frozen baseline",
                "",
                "| Decision evidence | Measured |",
                "| --- | ---: |",
                f"| Comparable suite contract | {'yes' if baseline_gate.get('comparable_contract') else 'no'} |",
                f"| Quality delta | {'—' if delta is None else f'{_number(delta):+.3f} pp'} |",
                f"| Case regressions | {int(_number(baseline_gate.get('regressions')))} / {settings.max_regressions} allowed |",
                f"| Missing candidate cases | {int(_number(baseline_gate.get('missing_cases')))} |",
                f"| Production cost increase | {'—' if cost_delta is None else f'{_number(cost_delta):+.3f}%'} |",
                f"| p90 latency increase | {'—' if p90_delta is None else f'{_number(p90_delta):+.3f} ms'} |",
            ]
        )
        baseline_failures = baseline_gate.get("failures") or []
        if baseline_failures:
            lines.extend(
                ["", "### Why the candidate was rejected", ""]
                + [f"- {item}" for item in baseline_failures]
            )
    absolute_gate = gate.get("absolute_gate")
    if isinstance(absolute_gate, Mapping) and absolute_gate.get("failures"):
        lines.extend(
            ["", "## Absolute gate failures", ""]
            + [f"- {item}" for item in absolute_gate["failures"]]
        )
    if error:
        lines.extend(["", "## Why it stopped", "", error])
    lines.extend(
        [
            "",
            "> This result applies to the versioned suite in this run. It is not a universal model ranking.",
            "",
        ]
    )
    with Path(path).open("a", encoding="utf-8") as handle:
        handle.write("\n".join(lines))


def main() -> int:
    settings: Settings | None = None
    payload: Mapping[str, Any] = {}
    try:
        settings = Settings.from_environment()
        install = _run(
            [
                sys.executable,
                "-m",
                "pip",
                "install",
                "--disable-pip-version-check",
                install_target(settings.version),
            ]
        )
        if install.returncode:
            raise RuntimeError(f"Installing Evalt {settings.version} failed")

        validation = _run(_evalt("validate", str(settings.suite)))
        if validation.returncode:
            raise RuntimeError(
                "Suite validation failed before any Evalt provider request was started"
            )

        if settings.optimize:
            optimization = _run(optimize_command(settings))
            if optimization.returncode:
                raise RuntimeError(
                    f"The budget-capped tournament stopped with exit code {optimization.returncode}"
                )
        else:
            if not settings.result.is_file():
                raise RuntimeError(
                    f"optimize=false requires an existing result at {settings.result}"
                )
            report = _run(
                _evalt(
                    "report",
                    str(settings.result),
                    "--html",
                    str(settings.html_report),
                    "--junit",
                    str(settings.junit_report),
                    "--title",
                    "Evalt CI result",
                )
            )
            if report.returncode:
                raise RuntimeError("Generating the offline reports failed")

        with settings.result.open(encoding="utf-8") as handle:
            loaded = json.load(handle)
        if not isinstance(loaded, Mapping):
            raise RuntimeError("The Evalt result must be a JSON object")
        payload = loaded

        gate_process = _run(gate_command(settings), capture=True)
        if gate_process.stdout:
            print(gate_process.stdout, end="")
        if gate_process.stderr:
            print(gate_process.stderr, end="", file=sys.stderr)
        try:
            gate = json.loads(gate_process.stdout or "{}")
        except json.JSONDecodeError:
            gate = {}
        winner = _winner(payload)
        quality = _number(
            winner.get("holdout_pass_rate")
            if winner.get("holdout_pass_rate") is not None
            else winner.get("pass_rate")
        )
        cost = winner.get("estimated_cost_per_successful_call_usd")
        status = (
            "PASS"
            if gate_process.returncode == 0
            else "FAIL"
            if gate_process.returncode == 1
            else "ERROR"
        )
        _write_output("status", status)
        _write_output("selected-model", winner.get("model") or "")
        _write_output("route-version", _route_version(payload, winner))
        _write_output("final-test-pass-rate", quality)
        baseline_gate = gate.get("baseline_gate")
        if not isinstance(baseline_gate, Mapping):
            baseline_gate = {}
        _write_output("case-regressions", baseline_gate.get("regressions", ""))
        _write_output(
            "quality-delta-pp",
            baseline_gate.get("quality_delta_percentage_points", ""),
        )
        _write_output(
            "cost-per-1000-successful-calls-usd",
            "" if cost is None else _number(cost) * 1000,
        )
        _write_output("result", settings.result)
        _write_output("html-report", settings.html_report)
        _write_output("junit-report", settings.junit_report)
        _write_summary(settings, status=status, payload=payload, gate=gate)
        return gate_process.returncode
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as error:
        print(f"evalt-action: {error}", file=sys.stderr)
        _write_output("status", "ERROR")
        if settings is not None:
            _write_summary(settings, status="ERROR", payload=payload, error=str(error))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
