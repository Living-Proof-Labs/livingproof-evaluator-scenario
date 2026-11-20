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
The same directory also contains `thresholds.json`. These illustrative
thresholds demonstrate the interface, not a capability contract or a claim
that the robot passes. Use thresholds from the contract appropriate to your
own evidence.

## Limits recorded on each result

Each result's `inputs` list cites the observation, the manifest, and the
limits that were graded. The limits citation is the evaluator contract's
input reference: `role`, `uri`, and `sha256`, and no other fields. The role
is `thresholds`. The URI is `thresholds.json`. The sha256 is the digest of
that file.

`thresholds.json` is written in the output directory, next to the trial
results. Copying that directory keeps the bytes the digest names. A later
step that appends each result document onto a bundle keeps the `thresholds`
reference, because the reference is inside the result.

The file is canonical JSON: object keys sorted, no insignificant whitespace,
UTF-8, and one trailing newline. It holds the exact limits that were graded,
under the parameter file's names (`half_width` is stored as `exit_segment`).
Keys the grader ignores are left out, so the same limits produce the same
bytes whatever order or extra keys the caller used. Two different limits
produce two different digests.

When the parameter document is the vendored copy of
`robot-capability-specs` `v2.2.0`
`specs/scenarios/walk-hallway/parameters.json`, the file also records that
repository, tag, commit, path, and the parameter file's sha256. A different
parameter document has no known tag or commit, so the file records only the
sha256 of that document's canonical JSON.

The result format stays `livingproof-evaluator-result/1.1.0`. The contract
allows any slug as an input role, so a `thresholds` entry is a valid result.
Results written before this entry remain valid. A reader that does not use
the role can ignore it. Step verdicts are unchanged. Stored results from
earlier runs are left as they were recorded: their step verdicts do not
include this input, and re-grading those observations does not change the
verdicts.

A release tag sets `evaluator.version` to a semantic version such as
`1.2.0`, which the result schema accepts. On any other commit the installed
version is a development string such as `1.2.1.dev1`. `descriptor.version`
is plain text and accepts that string. The schema's rule for
`evaluator.version` does not. That development string is what the package
version already was before the thresholds input. The check is described in
[Verification](verification.md).

Successful writing exits zero even when a step verdict is `FAIL` or
`INCONCLUSIVE`. Argument errors exit 2. An unknown evidence or observation
format prints `ERROR` and exits 1. Malformed JSON or a missing file can raise
an exception and exit nonzero. Use `--help` to inspect the actual required
inputs. The input is a `livingproof-hallway-evidence/2.0.0` manifest, not an
MCAP file or a Gherkin feature. A neutral input format is not defined yet.

## Grading a run's media

`python -m livingproof_evaluator_scenario.media MANIFEST MEDIA OUT --world WORLD --identity ID` reads
each trial's MCAP through its merged observation binding (`media.json` 2.1.0 lists both files) and
writes one result per trial, with `media/thresholds.json`.

- Limits come from the run manifest only: its world, robot profile, configuration profile and
  `plan.command_speed`, through the scenario parameter file's formulas. A limit the manifest cannot
  give is missing, and the step that needs it is `NOT_EVALUATED` with reason `missing_threshold`.
  No default and no verifier value stands in.
- Each result carries `evaluator.id` and `evaluator.version`, and an input with role `evaluator`:
  its `uri` is `ID` (a commit or an image digest) and its `sha256` is the digest of this package's
  source.
- A recording or binding that is not the file `media.json` lists is refused, and nothing is written.
