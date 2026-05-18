# SemanticScript 1.0 Release TODO

This file tracks the release-readiness gaps found in the 2026-05-18 project
review. A task is only done when the linked command or artifact is clean.

## P0 - Release Validation Must Be Green

- [x] Fix `python SemanticScript\tests\compare.py`.
  - [x] Fix `string_analyzer.sscript` parity: JS reports `characters: 104`
        and SemanticScript reports `characters: 101`; top-word ordering also
        differs (`favors` vs `semanticscript` in the fifth slot).
- [x] Fix `python SemanticScript\tests\sem_compiler_parity.py`.
  - [x] Fix `string_analyzer.sscript` parity under `bootstrap_general`.
  - [x] Fix `webserver_console.sscript` long-running parity under
        `bootstrap_general`.
- [x] Fix unexpected failures in `python SemanticScript\tests\feature_coverage.py`.
  - [x] `121_cross_file_import.sscript`: emitted IR contains
        `%addSevenCall_res = add i64 35, %`.
  - [x] `88_string_byte_scan_loop.sscript`: expected `14\n`, actual `17\n`.
  - [x] `89_pointer_returning_recursion.sscript`: expected `ipt\n`, actual
        `script\n`.
  - [x] `92_c_fopen_fclose.sscript`: expected `opened\n` and exit `0`, actual
        empty stdout and exit `1`.
- [x] Decide how to treat the 30 `expect.xfail` feature tests before 1.0.
  - [ ] Either close the bootstrap gaps and remove the xfail markers.
  - [x] Or explicitly scope 1.0 to the Python reference compiler and document
        `bootstrap_general.sscript` as experimental/self-hosting progress.

## P1 - Runtime And Syntax Scope

- [x] Resolve or explicitly defer the 7 `Partial` rows in `SYNTAX.md`.
  - [x] `codec NAME [ATTRS...]`.
  - [x] `jsonCodec NAME`.
  - [x] `webServer NAME`.
  - [x] `route SERVER METHOD PATH HANDLER`.
  - [x] `collectionOperation COLLECTION.OP`.
  - [x] `json.encode.RecordTypeName` / `json.decode.RecordTypeName`.
  - [x] `TaskList.append` / `TaskMap.get`.
- [x] Make the 1.0 support matrix explicit:
  - [x] Python reference compiler support.
  - [x] Self-hosting/bootstrap support.
  - [x] VS Code extension support.
  - [x] Refined syntax support.
  - [x] Web/HTTP runtime support.

## P1 - Packaging, Install, And CI

- [x] Add dependency metadata for Python tooling.
  - [x] Document Python version requirements.
  - [x] Document `llvmlite` requirement.
  - [x] Document `clang` / `SEMSC_CLANG` requirement.
- [x] Add a repeatable release validation entrypoint.
  - [x] CI workflow or script for compiler unit tests.
  - [x] CI workflow or script for stdlib tests.
  - [x] CI workflow or script for semlint2 tests.
  - [x] CI workflow or script for extension syntax check.
  - [x] CI workflow or script for parity/feature coverage once green.
- [x] Add release process documentation.
  - [x] Required local commands.
  - [x] Artifact cleanup rules.
  - [x] Version bump rules.
  - [x] VSIX packaging rule.
- [ ] Decide license before publishing.
  - [ ] Add root `LICENSE`.
  - [ ] Align `vscode-semanticscript/package.json` license.
- [ ] Decide VS Code publisher/marketplace identity.
  - [ ] Replace `publisher: semanticscript-local` if publishing externally.
  - [ ] Align extension version with release plan.

## P2 - Documentation Cleanup

- [x] Remove stale `experiments/` references from current docs.
  - [x] `README.md`.
  - [x] `SYNTAX.md`.
  - [x] `SemanticScript/AST.md`.
  - [x] `docs/toolchain/vscode-extension.md`.
  - [x] `SemanticScript/compiler/semsc.py` comments if they refer to deleted
        paths rather than current refined examples.
- [x] Fix stale documentation map entries.
  - [x] Replace `SemanticScript/CHANGELOG.md` with root `CHANGELOG.md`.
  - [x] Remove references to retired `experiments/whatsneeded.md`.
  - [x] Remove references to retired `experiments/refined_syntax_graph.md`.
- [x] Fix bad linter command examples.
  - [x] Replace `SemanticScript/as` with a real path such as
        `SemanticScript/sem`.
- [x] Fix grammar issues found during review.
  - [x] `An SemanticScript file` -> `A SemanticScript file`.
- [x] Update docs for recently added compiler flags.
  - [x] `--build-profile dev|prod`.
  - [x] `--runtime-checks off|traps|panic`.
  - [x] `--persist-llvm-ir auto|yes|no`.
  - [x] `SSRUN001` runtime panic output.
  - [x] `SSOK000` / `SSOK001` success output.

## P2 - Repository Hygiene

- [ ] Get to a release-clean worktree before tagging.
  - [ ] Commit or intentionally discard modified source/docs.
  - [ ] Commit or intentionally remove untracked README/doc files.
  - [x] Keep generated `.exe`, `.ll`, `__pycache__`, `todos.json`, and `.vsix`
        artifacts ignored and out of source control.
- [x] Run legacy-name scans before release.
  - [x] Confirm no `AgentScript` branding remains except the repository folder
        name or intentionally documented local paths.
  - [x] Confirm no stale `experiments/` paths remain after docs cleanup.

## P3 - Nice-To-Have Before 1.0

- [x] Add `SECURITY.md`.
- [x] Add `CONTRIBUTING.md`.
- [x] Add a top-level release checklist command block in `README.md`.
- [ ] Decide whether the duplicate top-level `python/` and `samples/python/`
      folders should both remain.
- [ ] Decide whether `.sem` mirror files under `SemanticScript/sem/` should be
      tracked as alias fixtures or generated artifacts.
