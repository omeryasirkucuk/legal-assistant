# Project instructions

- Increment the version according to Semantic Versioning when a change warrants a release.
- After every code change, update `CHANGELOG.md`, `CHANGELOG.local.md`, and `README.md`. Keep README commands, examples, and descriptions in sync with the code.
- For tasks that affect a CLI, verify that the relevant CLI is installed and up to date in the local development environment before and after making changes.
- Commit task changes with a meaningful message and push them to the GitHub repository.
- Deploy completed work to [Folonto Legal](https://legal.folonto.com) by default. Skip production deployment only when the user explicitly asks to skip it for that task. Use the `codex/folonto-deployment` branch and follow its [deployment runbook](https://github.com/omeryasirkucuk/legal-assistant/blob/codex/folonto-deployment/docs/DEPLOYMENT.md). For changes that affect the running application, apply the release in production and verify the public health and readiness endpoints along with the behavior changed by the task.
