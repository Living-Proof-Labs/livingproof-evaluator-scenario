# Contribute

Open a focused draft pull request with the problem, change and verification.
Use Python 3.12, uv and Task 3.54.0: `task setup`, `task check`, `task test`.
For the manual, run `task docs:setup`, `task docs:build`, `task docs:verify`.
Independent review is required before merge; changed user-run instructions need
the verification agent's evidence at the candidate revision.

The repository continues to adopt
[collaboration-guidelines v7.8.2](https://github.com/Living-Proof-Labs/collaboration-guidelines/blob/v7.8.2/AGENTS.md).
This documentation change additionally follows the
[documentation recipe at v7.10.8](https://github.com/Living-Proof-Labs/collaboration-guidelines/blob/v7.10.8/docs/documentation-recipe.md)
and consumes that release's digest-checked brand. It does not upgrade the release
workflow or the repository-wide baseline. The recipe/brand release resolves to
`e8686269446bc727a57a1b9d41f5903542c4ecdb`.

Local limits: no published development image, maintained historical manual,
coverage report or executable Gherkin runner. Existing Python tests remain the
canonical result evidence. Current documentation-home and related-source links
are the bounded navigation exception to version pinning; executable dependencies
and shared guidance remain pinned. No security reporting destination is
established in this repository; do not put sensitive reports in public issues.

[Help / report an issue](https://github.com/Living-Proof-Labs/livingproof-evaluator-scenario/issues)
