# Security Policy

## Supported Versions

This repository is pre-1.0. Security fixes are applied to the active default
branch unless a release branch is explicitly announced.

## Reporting a Vulnerability

Do not open a public issue for an active vulnerability. Use the repository's
private security advisory flow when available. If private advisories are not
enabled, contact the maintainers through the existing project coordination
channel and include:

- affected file, tool, or release candidate
- steps to reproduce
- expected impact
- whether generated artifacts or package outputs are affected

TODO: add a dedicated security contact before the first public release.

## Dependency Handling

Python dependencies are declared in `requirements.txt`. Keep the dependency set
small and review changes to compiler/runtime packages carefully because CI and
release validation install from this file.

Do not publish release artifacts until the license TODO in `CONTRIBUTING.md` and
`RELEASE.md` is resolved.
