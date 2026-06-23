# Branch Protection Guidelines

LocalForge OS expects `main` to be protected in hosted Git repositories.

Required rules:

- Require pull requests before merging into `main`.
- Require at least one approval.
- Require the CI workflow to pass.
- Block direct pushes to `main`.
- Keep branch deletion disabled unless an operator explicitly approves cleanup.

The PR Factory mirrors these requirements in generated `pr.md` artifacts so local
PR review state stays aligned with protected branch policy.
