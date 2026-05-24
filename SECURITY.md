# Security Policy

## Supported Versions

Security fixes are applied to the active default branch unless a release branch
is explicitly announced.

## Reporting a Vulnerability

Do not open a public issue with vulnerability details.

Use GitHub's private reporting flow when available:

1. Open the repository on GitHub.
2. Go to **Security**.
3. Choose **Report a vulnerability** or **Advisories**.
4. Submit a private security advisory draft with the details below.

If the private advisory flow is unavailable, email
`mr.e.cameron+semanticscript-security@gmail.com` with the subject
`SemanticScript security report`. If email is unavailable, open a public issue
that only asks maintainers to enable private vulnerability reporting; do not
include exploit details, affected paths, logs, proof-of-concept code, or
reproduction steps in that issue.

Expected response targets:

- acknowledgement within 5 business days
- initial triage within 10 business days
- coordinated fix or mitigation plan for confirmed high-impact issues before
  public disclosure

In the private report, include:

- affected file, tool, or release candidate
- steps to reproduce
- expected impact
- whether generated artifacts or package outputs are affected
- any temporary mitigation you have already tested

## Dependency Handling

Python dependencies are declared in `requirements.txt`. Keep the dependency set
small and review changes to compiler/runtime packages carefully because CI and
release validation install from this file.

Before publishing release artifacts, confirm the root `LICENSE` and package
metadata still identify the intended MIT distribution terms, and preserve
third-party notices for bundled dependencies.
