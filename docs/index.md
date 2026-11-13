# Scenario evaluator

The deterministic scenario evaluator checks stored hallway observations for
Living Proof Labs robot capability verification. Start with the [guide](guide.md)
to evaluate a checked-in evidence fixture, or inspect the generated
[command, API and Task reference](reference.md).

The current implementation provides four hallway checks: reaching the exit,
lateral offset, wall contact and base height. It writes one
`livingproof-evaluator-result/1.1.0` document per trial. It does not grade a run
or edit a bundle. Descriptor findings remain empty. The generic Gherkin
vocabulary and MCAP runner are not implemented yet.

The evaluator contract belongs to
[livingproof-evaluator](https://github.com/Living-Proof-Labs/livingproof-evaluator),
capability feature files to
[robot-capability-specs](https://github.com/Living-Proof-Labs/robot-capability-specs),
and world places to
[livingproof-worlds](https://github.com/Living-Proof-Labs/livingproof-worlds).
These are source links; find available rendered manuals through
[Documentation home](https://docs.livingprooflabs.com/).

[Source](https://github.com/Living-Proof-Labs/livingproof-evaluator-scenario) ·
[Help / report an issue](https://github.com/Living-Proof-Labs/livingproof-evaluator-scenario/issues) ·
[License](license.md) · [Version and source](version.md)
