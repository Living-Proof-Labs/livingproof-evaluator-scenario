# livingproof-evaluator-scenario

**Start here: documentation** — [manual source](docs/index.md).
Publication is pending; this link does not claim a live deployment.

Deterministic scenario evaluator for Living Proof Labs robot capability specifications.

This repository will hold a generic Gherkin step vocabulary over observables and world places, and a runner that reads MCAP through an observation binding. Spec authors write no code. Scenarios are written in Gherkin. Example steps include:

- the base enters place X within N seconds
- the base lateral offset from the centerline stays within N meters
- no body has contact with X
- the base height stays above P% of nominal

The observable vocabulary, binding format and evaluator contract live in [livingproof-evaluator](https://github.com/Living-Proof-Labs/livingproof-evaluator). Feature files live in [robot-capability-specs](https://github.com/Living-Proof-Labs/robot-capability-specs). World places live in [livingproof-worlds](https://github.com/Living-Proof-Labs/livingproof-worlds).

## What is here

`livingproof_evaluator_scenario.checks` grades each step in the scenario parameter file (`measure`, `fail_when`, and `limit`). The caller passes the resolved limits. Resolving a limit, distance to the route, and an exit crossing use `livingproof-scenario-parameters` from [robot-capability-specs](https://github.com/Living-Proof-Labs/robot-capability-specs) v2.2.0, installed from that tag. `livingproof_evaluator_scenario.result.trial_result` writes one `livingproof-evaluator-result/1.1.0` document per trial, with the descriptor title `Scenario`, the purpose "Checks each step of the scenario against the limits in its spec.", and the subset-legal icon. Findings are empty in this slice. Already-recorded evidence in the frozen `livingproof-hallway-evidence/2.0.0` format stays readable. A neutral input format is not defined yet, and any other format is an error. The Gherkin vocabulary and the MCAP runner are still to come. The agreed design is in the [Living Proof Evaluator Skill — Feature Proposal](https://app.notion.com/p/414e1aa44c2981e0b8b2fcb28f47ea40).

`evaluator.version` and `descriptor.version` are the installed package version. hatch-vcs reads it from the git tag. Before the first tag that version is a development version such as `0.1.dev1`. Semantic-release tags `v1.0.0` from the `feat:` commit and does not rewrite a version in this file.

## Develop

Requires Python 3.12 and [uv](https://docs.astral.sh/uv/). [Task](https://taskfile.dev) 3.54.0 runs the same commands continuous integration runs. This repository has no published development image yet.

```sh
uv sync --locked
task check
task test
```

## License

[Apache-2.0](LICENSE).
