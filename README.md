# livingproof-evaluator-scenario

Deterministic scenario evaluator for Living Proof Labs robot capability specifications.

This repository will hold a generic Gherkin step vocabulary over observables and world places, and a runner that reads MCAP through an observation binding. Spec authors write no code. Scenarios are written in Gherkin. Example steps include:

- the base enters place X within N seconds
- the base lateral offset from the centerline stays within N meters
- no body has contact with X
- the base height stays above P% of nominal

The observable vocabulary, binding format and evaluator contract live in [livingproof-evaluator](https://github.com/Living-Proof-Labs/livingproof-evaluator). Feature files live in [robot-capability-specs](https://github.com/Living-Proof-Labs/robot-capability-specs). World places live in [livingproof-worlds](https://github.com/Living-Proof-Labs/livingproof-worlds).

## Status

Design, no code yet. The agreed design is in the [Living Proof Evaluator Skill — Feature Proposal](https://app.notion.com/p/414e1aa44c2981e0b8b2fcb28f47ea40).

## License

[Apache-2.0](LICENSE).
