# Security Policy

## Supported Versions

Security fixes are applied to the active default branch unless a release branch
is explicitly announced.

## Reporting a Vulnerability

Do not open a public issue for an active vulnerability. Use the repository's
private security advisory flow. If private advisories are not enabled, contact
the maintainers through the existing project coordination channel and include:

- affected file, tool, or release candidate
- steps to reproduce
- expected impact
- whether generated artifacts or package outputs are affected

## Dependency Handling

Python dependencies are declared in `requirements.txt`. Keep the dependency set
small and review changes to compiler/runtime packages carefully because CI and
release validation install from this file.

Before publishing release artifacts, confirm the root `LICENSE` and package
metadata still identify the intended MIT distribution terms, and preserve
third-party notices for bundled dependencies.
