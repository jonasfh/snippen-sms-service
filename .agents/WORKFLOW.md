# Agent Workflow Guidelines

## GitHub Issue Workflow

All changes made to the project MUST be based on a GitHub issue. If a task or instruction is given without an associated issue, create a GitHub issue containing the details of the work to be done (`gh issue create`) before starting.

Once a GitHub issue is identified or created, follow this workflow:

1. **Preparation**:
   - Start in `main` branch and pull latest: `git pull origin main`.
   - Verify GitHub authentication: `gh auth status` (Note: `gh` CLI commands require network access; use `BypassSandbox: true` if standard sandbox blocks network connections).
   - Read issue details using JSON mode or view: `gh issue view <id> --json title,body`.
2. **Branching**:
   - Create/use branch following pattern: `gh-issue/<id>` (e.g. `gh-issue/1`), based off `main`.
3. **Implementation**:
   - Resolve the issue using Python 3.12 standards.
   - Create/update tests and run linting and tests (`pytest`, `ruff check .`).
   - Update documentation (`README.md`, `DEV_README.md`, `docs/`) for any new features, endpoints, or data models implemented.
4. **Submission & Commit Messages**:
   - Commit changed files.
   - **Commit Message**: Issue commits MUST start with `(#<id>)`, e.g., `(#1) Fixed xxx...`. Make separate commits for different issue numbers. General repo updates not tied to an issue do not require the header.
   - **Commit Suggestion**: ALWAYS suggest a commit message as plain text in a copy-pasteable code block. Focus on the problem solved in the header, with rationale in the body.
   - Push branch: `git push origin gh-issue/<id>`.
   - Create Pull Request: `gh pr create --body "Closes #<id>" --title "(#<id>) <Issue Title>"`.
5. **Issue Status**:
   - Add implementation notes and summary to the GitHub issue (`gh issue comment <id> --body "..."`).
6. **Merging Pull Requests**:
   - When instructed to merge, check PR status (`gh pr checks <id>`).
   - Merge cleanly: `gh pr merge <id> --rebase --delete-branch`.

## Versioning & Changelog

- **Version Bump**: Bump version in `pyproject.toml` and `src/snippen_sms/__init__.py` for functional changes.
- **CHANGELOG.md**: Every version bump must have an entry in `CHANGELOG.md` under `## [X.Y.Z] - YYYY-MM-DD`.

## Environment Adaptation & Troubleshooting

- **Tool Execution Options**:
  - `gh` CLI commands require network access. Run with `BypassSandbox: true` if network errors occur.
  - Execute Python tests and linting via `pytest` and `ruff`. If local host environment is missing dependencies, use Docker or venv.
- **Feedback & Rule Improvements**: If an agent discovers new platform constraints, API changes, or non-obvious workspace paths, update `AGENTS.md` and relevant `.agents/` files immediately.

## Dependabot & Security Alerts Workflow

- Refer to alerts using full GitHub URLs, e.g., `https://github.com/jonasfh/snippen-sms-service/security/dependabot/<alert_id>`.
- Use branches like `dep-<ids>-fix-dependabot-issues` or `sec-<ids>-fix-code-scanning-issues`.
