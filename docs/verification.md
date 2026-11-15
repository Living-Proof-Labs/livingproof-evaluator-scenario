# Verification

`task test` runs the existing pytest suite. It includes stored G1 fixture parity,
result serialization tests, and a check that each result `write_run` emits
validates against the livingproof-evaluator v1.0.0 result schema (commit
`9b865bc530a09d763e62cf602b35b5bb57232c0b`). Those schema files are byte copies
under `tests/fixtures/livingproof-evaluator-v1.0.0/`, and `PROVENANCE.json`
there records each file's sha256. A passing test can confirm detection of a
failed capability; test success and robot capability verdicts are separate.

The result schema requires `evaluator.version` to be semantic versioning.
A commit that is a release tag produces a version such as `1.2.0`, and the
written document validates. Any other commit produces a hatch-vcs development
version such as `1.2.1.dev1`. `descriptor.version` is plain text and accepts
that string. The schema rejects it in `evaluator.version`. The test treats
that single mismatch as this known development-version case, and checks that
the same document validates when the version is a semantic version. The
thresholds input does not change the version. Stored G1 and real-run result
files are not rewritten. Parity compares assessments and step verdicts, which
do not include `inputs`, and those verdicts stay the same. Adding the
thresholds reference to those historical files would make them different
documents from the run that stored them.

[Verify workflow and results](https://github.com/Living-Proof-Labs/livingproof-evaluator-scenario/actions/workflows/verify.yml)
publishes JUnit evidence for amd64 and arm64. Consult the exact run and revision;
this manual does not assert that an unobserved run passed. No software line
coverage is measured or claimed here.

`task docs:build` generates command help, public function signatures/docstrings,
Task summaries and source identity, then builds the manual with the pinned shared
brand. `task docs:verify` checks local rendered links/fragments and brand inclusion.
These checks do not establish external link availability or live site usability.

## Publication

The Docs workflow builds pull requests with read-only permissions and retains the
site for 14 days. A separate deployment job publishes only successful main builds. Immediately before
publishing, it reads the current main commit from GitHub and rejects a stale
candidate or failed lookup. Workflow concurrency serializes main deployments.
Repository Pages must use GitHub Actions and the `github-pages` environment must
allow main. Setting or changing these controls requires the owner's action-time
authorization. This change does not enable Pages or change security settings.

The intended route is
`https://docs.livingprooflabs.com/livingproof-evaluator-scenario/`.
A ready workflow is not proof of a live site. After an authorized merge and
successful deployment, verify its actual URL, `build.json` source revision,
README journey, navigation, deep links, search and desktop/mobile/keyboard use
before advertising a live manual or adding it to the organization directory.
