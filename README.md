# Evalt Action

Run a versioned Evalt performance suite in GitHub Actions, fail the job when its frozen
quality contract is missed, and keep the JSON, HTML, and JUnit evidence.

Evalt does more than compare a matrix you chose. It searches prompt, few-shot, model,
provider, and supported reasoning configurations under the suite's hard test budget,
then selects the lowest-cost measured route that clears the approved quality floor.

## Five-minute gate

Commit an `evalt.json` suite, add `OPENROUTER_API_KEY` as a repository Actions secret,
and create `.github/workflows/evalt.yml`:

```yaml
name: Evalt

on:
  pull_request:
  workflow_dispatch:

permissions:
  contents: read

jobs:
  performance-gate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7
      - name: Find the cheapest route that passes
        id: evalt
        uses: JarJarBeatyourattitude/evalt-action@v1
        env:
          OPENROUTER_API_KEY: ${{ secrets.OPENROUTER_API_KEY }}
        with:
          suite: evalt.json
          min-pass-rate: "0.95"
      - uses: actions/upload-artifact@v7
        if: always()
        with:
          name: evalt-evidence
          path: |
            evalt-result.json
            evalt-report.html
            evalt-junit.xml
```

The suite—not this workflow—contains `max_optimization_cost_usd`. That one value caps
target calls, prompt improvement, and judging across the tournament. The action never
extends it silently.

## Gate a saved result without spending

Use this mode when another job produced the result or when you want a deterministic
release gate:

```yaml
- uses: JarJarBeatyourattitude/evalt-action@v1
  with:
    suite: evalt.json
    result: evalt-result.json
    optimize: "false"
    min-pass-rate: "0.98"
    require-complete-coverage: "true"
```

`optimize: "false"` performs suite validation, report generation, and the gate locally.
It starts no provider request and does not require an API key.

## Reject regressions against a frozen baseline

Point `baseline` at an earlier result from the identical suite contract:

```yaml
- uses: JarJarBeatyourattitude/evalt-action@v1
  with:
    suite: evalt.json
    result: candidate.json
    baseline: baseline.json
    optimize: "false"
    max-regressions: "0"
    max-quality-drop-pp: "0"
    max-cost-increase-pct: "10"
    max-p90-increase-ms: "250"
```

The Action fails closed if either suite hash is missing or changed. By default it also
rejects every newly failing or missing frozen case and any aggregate quality drop. The
job summary shows only decision metrics and case IDs; private case content stays in the
local result artifacts.

## Inputs that change the decision

| Input | Default | Meaning |
| --- | --- | --- |
| `suite` | `evalt.json` | Versioned Evalt suite and hard tournament budget. |
| `optimize` | `true` | Run the tournament; `false` gates an existing result offline. |
| `baseline` | empty | Earlier result from the identical frozen suite; enables regression gating. |
| `evalt-version` | `0.10.29` | Exact package version. Mutable `latest` installs are rejected; the current default is the version-pinned wheel served by Evalt's hosted download. |
| `min-pass-rate` | `0.95` | Required frozen final-test accuracy. |
| `max-cost-per-success` | empty | Optional USD ceiling for one successful production call. |
| `require-complete-coverage` | `true` | Reject unfinished decision-relevant coverage. |
| `max-regressions` | `0` | Previously passing frozen cases allowed to fail. |
| `max-quality-drop-pp` | `0` | Aggregate final-test quality drop allowed, in percentage points. |
| `max-cost-increase-pct` | empty | Optional production-cost increase limit versus baseline. |
| `max-p90-increase-ms` | empty | Optional p90 latency increase limit versus baseline. |
| `fixed-prompt` | `false` | Disable rewrites and few-shot search. |
| `max-parallel-models` | suite value | Override model-lane parallelism. |
| `max-parallel-scenarios` | suite value | Override case-execution parallelism. |
| `request-timeout-seconds` | suite value | One provider-response deadline, not tournament duration. |

The action exposes `status`, `selected-model`, `route-version`,
`final-test-pass-rate`, `case-regressions`, `quality-delta-pp`,
`cost-per-1000-successful-calls-usd`, and all three evidence
paths as outputs. `route-version` is intentionally empty for a suite-only result and
is populated only when the result artifact contains an explicit qualified route
package ID. The same summary appears on the GitHub Actions run.

## Secret safety

- The provider key is an environment secret, never an action input or command argument.
- Evalt requires Zero Data Retention and denies provider data collection on OpenRouter
  requests.
- GitHub does not pass ordinary repository secrets to workflows triggered from forks.
  Do not change an untrusted `pull_request` workflow to `pull_request_target` merely to
  expose a provider key. Review forked changes or run the gate with `workflow_dispatch`
  on trusted code.
- Pin this action to `@v1` or an immutable release tag. The action itself pins the Evalt
  package version and rejects `latest`.

## What the result proves

A pass means the selected configuration cleared this versioned suite at the configured
threshold and coverage rule. It is not a universal model ranking or a guarantee about
future inputs. Review `evalt-report.html` and keep the JSON result with the deployment
that used it.

The [Evalt SDK](https://github.com/JarJarBeatyourattitude/evalt) and this action are MIT
licensed. Documentation is at [evalt.dev/docs](https://evalt.dev/docs/).
