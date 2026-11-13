# Verification

`task test` runs the existing pytest suite. It includes stored G1 fixture parity
and result serialization tests. A passing test can confirm detection of a failed
capability; test success and robot capability verdicts are separate.

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
