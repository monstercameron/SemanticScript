# Reference Docs

Reference-oriented documentation for call targets, verb schemas, and maintenance
rules.

## Contents

- `call-targets.md` lists built-in targets, domain methods, user operations, and current low-level `c.*` calls.
- `syntax-inventory.md` lists the complete syntax surface and implementation status table.
- `install-policy.md` defines the initial archive install shape and future version-manager plan.
- `verb-index.md` indexes language verbs and line shapes.
- `maintenance.md` describes how to keep language, compiler, linter, docs, and editor support aligned.
- `modularization-triage-plan.md` defines the staged plan for splitting
  oversized implementation files and migrating `release-backlog.md` into issues.
- `package-management.md` defines package layout, dependency syntax, and registry deferral policy.
- `release-hygiene.md` defines release repository-state, package-metadata, and mirror-file policies.
- `compatibility.md` defines the public SemanticScript 1.0 compatibility contract.

## Current Status

Active reference layer. It should stay factual and close to implementation
behavior, with broader explanations living in `docs/language/`.

## Maintenance

Update these files when call targets, verbs, or cross-tool maintenance rules
change.
