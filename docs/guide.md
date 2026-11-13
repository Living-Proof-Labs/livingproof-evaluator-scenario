# Guides

## Install from source

Use Python 3.12 and uv, then run `uv sync --locked` in the checkout.
This is a development source installation. No released development image is
provided; no container quickstart or published package availability is claimed.
Task 3.54.0 exposes the contributor commands.

## Evaluate the stored fixture

From the repository root, create the caller-supplied thresholds and run:

```sh
printf '%s\n' '{"time_limit":30,"lateral_limit":0.5,"half_width":1,"fall_height":0.3}' > artifacts-thresholds.json
uv run --locked python -m livingproof_evaluator_scenario \
  tests/fixtures/run-43159586597/stock/manifest.json \
  --thresholds artifacts-thresholds.json --out artifacts/example-results \
  --started-at 2026-11-13T00:00:00Z --completed-at 2026-11-13T00:00:00Z
```

Expected output is three paths, `artifacts/example-results/stock-seed-01.json`
through `stock-seed-03.json`. Each JSON document contains four scenario steps.
These illustrative thresholds demonstrate the interface, not a capability
contract or a claim that the robot passes. Use thresholds from the contract
appropriate to your own evidence.

Successful writing exits zero even when a step verdict is `FAIL` or
`INCONCLUSIVE`. Argument errors exit 2. An unknown evidence or observation
format prints `ERROR` and exits 1. Malformed JSON or a missing file can raise
an exception and exit nonzero. Use `--help` to inspect the actual required
inputs. The input is a `livingproof-hallway-evidence/2.0.0` manifest, not an
MCAP file or a Gherkin feature. A neutral input format is not defined yet.
