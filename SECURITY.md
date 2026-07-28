# Security Policy

## Supported versions

LocalForge is pre-release software. Security fixes target the latest commit on the default
branch until the first stable release line is published.

## Reporting a vulnerability

Do not open a public issue for vulnerabilities involving command execution, sandbox escape,
path traversal, secret exposure, provider credentials, or unsafe Git operations. Use GitHub's
private vulnerability reporting for this repository. If it is unavailable, contact the
maintainer privately through the address listed on the maintainer's GitHub profile.

Include the affected version, minimal reproduction, impact, and any suggested mitigation.
Never include real secrets or third-party private source code.

## Security boundaries

LocalForge executes model-proposed actions. Treat model output, imported PRDs, repository
content, skills, and external tool output as untrusted input.

Default expectations:

- bind the API to localhost unless an authenticated reverse proxy is configured;
- keep host-shell execution disabled for untrusted projects;
- prefer disposable Docker workspaces;
- keep `.env` and credentials outside artifacts and prompts;
- require human review before merge;
- use conservative network and filesystem policies;
- inspect third-party skills before enabling them.

No autonomy or sandbox mode is a guarantee against malicious input. Run LocalForge with the
least OS and repository privileges needed for the task.
