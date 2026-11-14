# SemanticScript Roadmap

This page is the public status and roadmap summary. Detailed engineering backlog
items should live in GitHub issues or project boards, not in this reference doc.

## Current Status

SemanticScript is `0.0.1` pre-release software. The repository has a working
compiler, linter, formatter, `sem` CLI, VS Code extension, native runtime
adapters, and curated demos, but no stable public release has been published.

## Release Readiness Goals

- Keep `main` protected with required PRs, strict CI, and conversation
  resolution.
- Keep GitHub Actions green on the exact release commit.
- Publish a first tagged release only after the release manifest, VSIX artifact,
  and any executable artifact policy are verified.
- Choose a real VS Code Marketplace publisher before public Marketplace
  distribution.
- Keep the root README short and point detailed language/tooling material into
  `docs/`.
- Keep security reporting private and documented.

## Demo Status

| Demo | Status | Notes |
| --- | --- | --- |
| `apps/taskforge-tui/` | Maintained showcase | Console todo app with JSON persistence. |
| `apps/html-template-lab/` | Maintained showcase | Compact HTML template demo. |
| `apps/http-runtime-gauntlet/` | Maintained runtime harness | Native HTTP regression target. |
| `apps/taskforge-web/` | Preview | Demonstrates native HTTP, SQLite, bcrypt, sessions, HTML, and JSON APIs; not positioned as a polished product. |
| `apps/desktop-window-smoke/` | Smoke fixture | Minimal Windows GUI build smoke. |

## Backlog Policy

The old release backlog has been archived at
[docs/archive/release-backlog-2026-05-18.md](../archive/release-backlog-2026-05-18.md).
Do not add new detailed checklist work there. Convert actionable work into
GitHub issues, then link the issue from this roadmap only when it changes public
status or release scope.
