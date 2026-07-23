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

## Run a repository-local custom scorer

A custom suite stores only its scorer identity:

```json
{"type":"custom","scorer_id":"domain-rubric","scorer_version":"1.0"}
```

Register reviewed repository code separately in the workflow:

```yaml
- uses: JarJarBeatyourattitude/evalt-action@v1
  with:
    suite: evalt.json
    custom-scorer-id: domain-rubric
    custom-scorer-version: "1.0"
    custom-scorer-executable: python3
    custom-scorer-arguments-json: '["tools/score.py"]'
    custom-scorer-timeout-seconds: "5"
    custom-scorer-max-input-bytes: "8388608"
    custom-scorer-max-output-bytes: "65536"
```

The arguments input is parsed as a JSON string array and forwarded as literal argv.
There is no shell. A downloaded suite cannot supply or override the executable. The
scorer receives strict JSON on stdin, must return one bounded score object on stdout,
and does not inherit provider credentials by default. Only run custom scorers from
trusted branches; they are executable repository code.

## Send a signed aggregate decision

Pass a GitHub Actions secret to send one content-free `ci.gate.pass`,
`ci.gate.fail`, or `ci.gate.error` event:

```yaml
- uses: JarJarBeatyourattitude/evalt-action@v1
  with:
    suite: evalt.json
    webhook-url: https://alerts.example.com/evalt
    webhook-secret: ${{ secrets.EVALT_WEBHOOK_SECRET }}
    webhook-destination-id: incident-pipeline
    webhook-required: "true"
```

The event contains only an opaque route reference, gate status, suite hash, measured
quality, and regression/cost/latency deltas. It omits the destination URL, secret,
prompts, cases, images, outputs, reasons, scorer identity/code, and provider
credentials. Evalt signs the exact body, uses a stable idempotency key, rejects
redirects and non-public addresses by default, retries within explicit bounds, and
writes an aggregate delivery audit. `webhook-delivered` and `webhook-event-id` are
available as Action outputs.

`webhook-include-route-name` and `webhook-allow-private-network` are explicit,
off-by-default reductions of the privacy and network boundary. Use them only when the
destination is authorized and trusted.

## Inputs that change the decision

| Input | Default | Meaning |
| --- | --- | --- |
| `suite` | `evalt.json` | Versioned Evalt suite and hard tournament budget. |
| `optimize` | `true` | Run the tournament; `false` gates an existing result offline. |
| `baseline` | empty | Earlier result from the identical frozen suite; enables regression gating. |
| `library-root` | empty | Optional private local evidence-library directory used when `suite` or `baseline` is an immutable `@name` reference. |
| `evalt-version` | `0.10.32` | Exact package version. Mutable `latest` installs are rejected; the current default is the version-pinned wheel served by Evalt's hosted download. |
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
| `custom-scorer-id` | empty | Trusted local scorer ID required by a custom suite. |
| `custom-scorer-version` | empty | Exact local scorer contract version. |
| `custom-scorer-executable` | empty | Direct executable; never selected by the suite or run through a shell. |
| `custom-scorer-arguments-json` | `[]` | JSON array of literal argv items. |
| `custom-scorer-timeout-seconds` | `10` | Per-case local scorer deadline, maximum 300 seconds. |
| `custom-scorer-max-input-bytes` | `8388608` | Maximum serialized request size per case; raise explicitly for embedded image fixtures, up to 64 MiB. |
| `custom-scorer-max-output-bytes` | `65536` | Maximum scorer stdout or stderr size per case, up to 1 MiB. |
| `webhook-url` | empty | Explicit HTTPS destination for one signed aggregate gate event. |
| `webhook-secret` | empty | Signing secret supplied from GitHub Actions secrets; never written to Evalt artifacts. |
| `webhook-destination-id` | `github` | Opaque local label retained in the delivery audit. |
| `webhook-audit` | `.evalt/webhook-deliveries.jsonl` | Aggregate local delivery audit. |
| `webhook-timeout-seconds` | `5` | Per-attempt HTTPS timeout, maximum 30 seconds. |
| `webhook-max-attempts` | `3` | Bounded attempts from 1 through 5. |
| `webhook-required` | `false` | Return Action error when the configured event cannot be delivered. |
| `webhook-include-route-name` | `false` | Include the route label instead of only an opaque reference. |
| `webhook-allow-private-network` | `false` | Permit a private/local destination; weakens the default SSRF boundary. |

The action exposes `status`, `selected-model`, `route-version`,
`final-test-pass-rate`, `case-regressions`, `quality-delta-pp`,
`cost-per-1000-successful-calls-usd`, `webhook-delivered`,
`webhook-event-id`, and all three evidence
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
