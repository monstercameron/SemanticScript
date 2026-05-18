# SemanticScript Rebranding TODO

Goal: rebrand the language and toolchain from AgentScript to SemanticScript.
Final state: the text `AgentScript`, `agentscript`, `AGENTSCRIPT`, `Agent Script`,
legacy `.as` source extensions, `ascc`, `aslint`, and `aslint2` should not exist
anywhere in tracked repo content or tracked file names. The only allowed
remaining `AgentScript` occurrence is the external repository/root folder name
if the repo itself is not renamed.

Canonical target names:

- Language: `SemanticScript`
- Source extensions: `.sscript` canonical, `.sem` accepted alias
- Compiler CLI: `semsc`
- Linter CLI: `semlint`
- Internal IR/source model phrase: `semantic tape`
- Python implementation package/directory: `SemanticScript/`
- Standard library directory: `stdlib_sem/`
- Example source directory: `sem/`
- VS Code extension directory: `vscode-semanticscript/`
- VS Code language id: `semanticscript`
- VS Code grammar scope: `source.semanticscript`
- VS Code settings namespace: `semanticScript.*`

Important note for this file: this TODO necessarily contains legacy names while
the migration is in progress. The final cleanup phase includes either deleting
this file or rewriting it so it no longer contains any legacy brand text.

## Phase 0 - Preflight and Guardrails

- [ ] Confirm the target source extension policy:
  - [ ] `.sscript` is the primary documented extension.
  - [ ] `.sem` is accepted by compiler, linter, editor tooling, tests, and docs.
  - [ ] `.as` is removed before final completion, not kept as a public alias.
- [ ] Confirm the repo folder itself may remain named `AgentScript`.
- [ ] Preserve current user work before bulk renames:
  - [ ] Review `git status --short`.
  - [ ] Note existing modified files before migration starts.
  - [ ] Avoid reverting unrelated user changes.
- [ ] Decide whether to do a single atomic rename commit or staged commits:
  - [ ] Commit 1: compiler/linter support for `.sscript` and `.sem`.
  - [ ] Commit 2: file and directory renames.
  - [ ] Commit 3: docs and VS Code extension rebrand.
  - [ ] Commit 4: final legacy-string cleanup and verification.
- [ ] Before renaming tracked files on Windows, use `git mv` for case/path changes.
- [ ] Delete or regenerate ignored build outputs before final scans:
  - [ ] `SemanticScript/tests/sem_compiler_build/`
  - [ ] `SemanticScript/tests/feature_coverage/build/`
  - [ ] `SemanticScript/bootstrap/bootstrap_general.ll`
  - [ ] Any stale `.exe`, `.ll`, `.vsix`, `__pycache__`, or `.pyc` files.

## Phase 1 - Naming Contract

- [ ] Replace all product-language wording:
  - [ ] `AgentScript` -> `SemanticScript`
  - [ ] `agentscript` -> `semanticscript`
  - [ ] `AGENTSCRIPT` -> `SEMANTICSCRIPT`
  - [ ] `Agent Script` -> `SemanticScript`
- [ ] Replace source-model wording:
  - [ ] `program tape` -> `semantic tape`
  - [ ] `command tape` -> `semantic tape`
  - [ ] `line tape` -> `semantic tape` where it names the language model.
  - [ ] Keep ordinary "line-oriented" wording only where it describes syntax.
- [ ] Replace compiler naming:
  - [ ] `ascc.py` -> `semsc.py`
  - [ ] `ascc` CLI program string -> `semsc`
  - [ ] `ASCC_CLANG` -> `SEMSC_CLANG`
  - [ ] `ASCC_TRACEBACK` -> `SEMSC_TRACEBACK`
  - [ ] `ascc:` stderr/status prefix -> `semsc:`
- [ ] Replace linter naming:
  - [ ] `aslint.py` -> `semlint.py`
  - [ ] `aslint2.py` -> decide and implement one of:
    - [ ] Rename to `semlint2.py` for a direct structured-linter equivalent.
    - [ ] Fold into `semlint.py --engine structured` and remove separate file.
  - [ ] `aslint` CLI program string -> `semlint`
  - [ ] `aslint2` CLI program string -> `semlint2` or structured `semlint`.
  - [ ] `aslint:` stderr/status prefix -> `semlint:`
  - [ ] `aslint2:` stderr/status prefix -> `semlint2:` or `semlint:`
- [ ] Replace internal abbreviations:
  - [ ] `AS-written compiler` -> `SemanticScript-written compiler`.
  - [ ] `AS source` -> `SemanticScript source`.
  - [ ] `AS program` -> `SemanticScript program`.
  - [ ] `AS_INPUT` env var -> `SEMANTIC_SCRIPT_INPUT` or `SEMSCRIPT_INPUT`.
  - [ ] Decide and use one env var consistently; recommended: `SEMANTIC_SCRIPT_INPUT`.
- [ ] Replace generated artifact names:
  - [ ] `as_compiler_build` -> `sem_compiler_build`.
  - [ ] `as_compiler_parity.py` -> `sem_compiler_parity.py`.
  - [ ] `AS-compiler parity` output -> `SemanticScript-compiler parity`.

## Phase 2 - Directory and File Renames

- [ ] Rename implementation directory:
  - [ ] `AgentScript/` -> `SemanticScript/`
- [ ] Rename root language spec:
  - [ ] `AgentScript.md` -> `SemanticScript.md`
- [ ] Rename source directories:
  - [ ] `SemanticScript/as/` -> `SemanticScript/sem/`
  - [ ] `SemanticScript/stdlib_as/` -> `SemanticScript/stdlib_sem/`
  - [ ] `SemanticScript/as_python/` -> `SemanticScript/sem_python/`
- [ ] Rename VS Code extension directory:
  - [ ] `vscode-agentscript/` -> `vscode-semanticscript/`
- [ ] Rename compiler/linter files:
  - [ ] `SemanticScript/compiler/ascc.py` -> `SemanticScript/compiler/semsc.py`
  - [ ] `SemanticScript/linter/aslint.py` -> `SemanticScript/linter/semlint.py`
  - [ ] `SemanticScript/linter/aslint2.py` -> `SemanticScript/linter/semlint2.py` or remove after merge.
  - [ ] `SemanticScript/linter/test_aslint2.py` -> `SemanticScript/linter/test_semlint2.py` or equivalent.
- [ ] Rename test harnesses:
  - [ ] `SemanticScript/tests/as_compiler_parity.py` -> `SemanticScript/tests/sem_compiler_parity.py`
  - [ ] `SemanticScript/tests/as_compiler_build/` -> `SemanticScript/tests/sem_compiler_build/`
- [ ] Rename every source fixture extension:
  - [ ] `*.as` -> `*.sscript` for canonical project-owned source files.
  - [ ] Add separate `.sem` smoke fixtures for extension alias coverage.
  - [ ] Remove all tracked `.as` files before final completion.
- [ ] Rename VS Code grammar file:
  - [ ] `vscode-semanticscript/syntaxes/agentscript.tmLanguage.json` -> `vscode-semanticscript/syntaxes/semanticscript.tmLanguage.json`
- [ ] Rename packaged VSIX expectations:
  - [ ] `agentscript-vscode-*.vsix` -> `semanticscript-vscode-*.vsix` if any packaged artifact is intentionally produced.
  - [ ] Keep packaged `.vsix` files ignored.

## Phase 3 - Compiler Implementation

### `SemanticScript/compiler/semsc.py`

- [ ] Update module docstring title from `ascc - the AgentScript compiler` to `semsc - the SemanticScript compiler`.
- [ ] Update all docstring references to the root spec path:
  - [ ] `../spec/AgentScript.md`
  - [ ] `../AST.md`
  - [ ] new path should mention `SemanticScript.md` and `AST.md`.
- [ ] Update parser/source terminology:
  - [ ] `AgentScript language` -> `SemanticScript language`
  - [ ] `AgentScript program` -> `SemanticScript program`
  - [ ] `AgentScript source` -> `SemanticScript source`
  - [ ] `program tape`, `line tape`, `command tape` -> `semantic tape`.
- [ ] Update default LLVM module name:
  - [ ] `agentscript_module` -> `semanticscript_module`
- [ ] Update import resolution:
  - [ ] Replace hardcoded `+ ".as"` with extension-aware lookup.
  - [ ] Search `.sscript` first.
  - [ ] Search `.sem` second.
  - [ ] Do not search `.as` in final state.
  - [ ] Update comments explaining dotted import mapping.
  - [ ] Confirm `stdlib_sem/` is used instead of `stdlib_as/`.
- [ ] Update CLI parser:
  - [ ] `prog="ascc"` -> `prog="semsc"`
  - [ ] Description says `SemanticScript compiler`.
  - [ ] Source help says `.sscript or .sem source file`.
  - [ ] Version output says `semsc <version>`.
- [ ] Update env vars:
  - [ ] `ASCC_CLANG` -> `SEMSC_CLANG`
  - [ ] `ASCC_TRACEBACK` -> `SEMSC_TRACEBACK`
- [ ] Update all status/error prefixes:
  - [ ] `ascc: cannot read source file`
  - [ ] `ascc: parse error`
  - [ ] `ascc: parse OK`
  - [ ] `ascc: codegen error`
  - [ ] `ascc: wrote LLVM IR`
  - [ ] `ascc: wrote executable`
  - [ ] `ascc: compile OK`
- [ ] Update `emit_executable` comments and errors:
  - [ ] `AgentScript IR` -> `SemanticScript IR`
  - [ ] `AgentScript runtime` -> `SemanticScript runtime`
- [ ] Update linter messages emitted by compiler lint:
  - [ ] Any mention of `AgentScript` in diagnostic text.
  - [ ] Any mention of `AS` in diagnostic text when it means the language.
- [ ] Update comments around refined syntax:
  - [ ] `refined_syntax_example.as` -> current `.sscript` path.
- [ ] Add tests for both accepted extensions:
  - [ ] Compile a `.sscript` fixture.
  - [ ] Compile a `.sem` fixture.
  - [ ] Verify missing `.as` fixture is not accidentally accepted.

### `SemanticScript/compiler/libc_registry.py`

- [ ] Update file docstring:
  - [ ] `AgentScript call target` -> `SemanticScript call target`
  - [ ] `AgentScript alias` -> `SemanticScript alias`
  - [ ] `AgentScript source code` -> `SemanticScript source code`
- [ ] Update comments:
  - [ ] `AgentScript-facing camelCase aliases`
  - [ ] `AgentScript programs invoke`
  - [ ] `AgentScript accessor`
- [ ] Update CLI/demo output:
  - [ ] `AgentScript libc registry` -> `SemanticScript libc registry`
- [ ] Confirm no filename changes are needed beyond parent directory rename.

## Phase 4 - Linter Implementation

### `SemanticScript/linter/semlint.py`

- [ ] Update module docstring:
  - [ ] `Standalone AgentScript linter` -> `Standalone SemanticScript linter`
  - [ ] `AgentScript line tape` -> `SemanticScript semantic tape`
- [ ] Update collection logic:
  - [ ] `path.rglob("*.as")` -> include `*.sscript` and `*.sem`
  - [ ] Remove final `.as` matching support.
  - [ ] Glob pattern filtering should accept both canonical extensions.
- [ ] Update diagnostic messages:
  - [ ] `unknown AgentScript verb`
  - [ ] `AgentScript context-maxxing`
  - [ ] `AgentScript's flat line-tape model`
  - [ ] Any other `AgentScript`, `agentscript`, or `AS` language references.
- [ ] Update CLI parser:
  - [ ] `prog="aslint"` -> `prog="semlint"`
  - [ ] Description says `Lint SemanticScript .sscript and .sem files`
  - [ ] Version output says `semlint <version>`
  - [ ] Paths help says `SemanticScript files, directories, or glob patterns`
- [ ] Update no-match message:
  - [ ] `aslint: no .as files matched` -> `semlint: no .sscript or .sem files matched`
- [ ] Rename or update internal constants only if user-facing:
  - [ ] Keep diagnostic code families stable unless deliberately rebranding codes.
  - [ ] Decide whether `AS####` diagnostic codes become `SS####` or remain as stable legacy codes temporarily.
  - [ ] Final state should not leave `AS####` if it counts as legacy brand.

### `SemanticScript/linter/semlint2.py` or structured linter equivalent

- [ ] Update module docstring:
  - [ ] `Refined AgentScript linter` -> `Structured SemanticScript linter`
  - [ ] `aslint.py stays as the stable surface` -> `semlint.py stays as the stable surface`
  - [ ] `AS-form` -> `SemanticScript-form`
- [ ] Update imports:
  - [ ] `from aslint import ...` -> `from semlint import ...`
- [ ] Update known verb set names if user-facing:
  - [ ] `KNOWN_AGENT_SCRIPT_VERBS` -> `KNOWN_SEMANTIC_SCRIPT_VERBS`
- [ ] Update comments and diagnostics:
  - [ ] `AgentScript's descriptive-identifier rule`
  - [ ] `AS surface`
  - [ ] `AS arg-type`
  - [ ] `AS4101`, `AS0101`, etc. if diagnostic-code prefix is renamed.
- [ ] Update as-record renderer:
  - [ ] Header should say `SemanticScript diagnostic records`.
  - [ ] Remove `as-record` output mode or rename to `sem-record`.
  - [ ] If kept, final state must not contain `as-record`.
- [ ] Update path collection:
  - [ ] Include `.sscript` and `.sem`.
  - [ ] Remove `.as`.
- [ ] Update CLI parser:
  - [ ] `prog="aslint2"` -> `prog="semlint2"` or structured `semlint`.
  - [ ] Description says `Structured SemanticScript linter`.
  - [ ] No-match message says `.sscript or .sem`.
- [ ] Update tests and expected outputs for renamed codes/output labels.

### `SemanticScript/linter/test_semlint2.py`

- [ ] Rename test file from `test_aslint2.py`.
- [ ] Update docstring and command examples.
- [ ] Rename temporary fixture:
  - [ ] `fixture.as` -> `fixture.sscript`
  - [ ] Add one `fixture.sem` test case.
- [ ] Update imports and subprocess commands:
  - [ ] `aslint2.py` -> `semlint2.py` or structured `semlint`.
- [ ] Update any expected text containing `AgentScript`, `aslint`, `.as`, or `AS####`.

### `SemanticScript/linter/__init__.py`

- [ ] Update package docstring:
  - [ ] `AgentScript standalone linter package` -> `SemanticScript standalone linter package`

### `SemanticScript/linter/README.md`

- [ ] Rewrite title to `# SemanticScript Linter`.
- [ ] Replace every command:
  - [ ] `python AgentScript/linter/aslint.py AgentScript/as/fizzbuzz.as`
  - [ ] new command should use `SemanticScript/linter/semlint.py SemanticScript/sem/fizzbuzz.sscript`
- [ ] Document `.sscript` and `.sem` inputs.
- [ ] Remove all final references to legacy CLI names.

## Phase 5 - Source File Extension Migration

### Canonical source extension rules

- [ ] Rename all tracked language source files from `.as` to `.sscript`.
- [ ] Add at least one `.sem` fixture in tests to prove alias support.
- [ ] Do not leave any tracked `.as` files.
- [ ] Update every string reference to file names inside code, docs, tests, and comments.
- [ ] Update dotted import resolver expectations and fixture comments.
- [ ] Update any text that says `.agentscript`; remove the extension from final public docs unless explicitly kept as a non-legacy alias. Recommended: remove it.

### Current `.as` inventory to migrate

- [ ] Rename all files under `SemanticScript/sem/` after directory rename:
  - [ ] `async_workflow.as`
  - [ ] `async_workflow_refined.as`
  - [ ] `complex_checkout_saga.as`
  - [ ] `countdown.as`
  - [ ] `countdown_refined.as`
  - [ ] `counterintuitive_closure_capture.as`
  - [ ] `counterintuitive_closure_capture_refined.as`
  - [ ] `counterintuitive_coercion.as`
  - [ ] `counterintuitive_event_loop.as`
  - [ ] `counterintuitive_mutation.as`
  - [ ] `counterintuitive_numbers.as`
  - [ ] `counterintuitive_this_binding.as`
  - [ ] `esoteric_church_encoding.as`
  - [ ] `esoteric_church_encoding_refined.as`
  - [ ] `esoteric_reactive_proxy.as`
  - [ ] `esoteric_self_referential.as`
  - [ ] `esoteric_stack_language.as`
  - [ ] `esoteric_trampoline.as`
  - [ ] `esoteric_trampoline_refined.as`
  - [ ] `event_workflow.as`
  - [ ] `event_workflow_refined.as`
  - [ ] `factorial.as`
  - [ ] `factorial_refined.as`
  - [ ] `file_inventory.as`
  - [ ] `fizzbuzz.as`
  - [ ] `fizzbuzz_refined.as`
  - [ ] `hello.as`
  - [ ] `hello_refined.as`
  - [ ] `hello_via_c_printf.as`
  - [ ] `hello_via_c_printf_refined.as`
  - [ ] `hello_via_helper.as`
  - [ ] `hello_via_helper_refined.as`
  - [ ] `hello_world.as`
  - [ ] `hello_world_refined.as`
  - [ ] `inventory_manager.as`
  - [ ] `json_order_summary.as`
  - [ ] `number_stats.as`
  - [ ] `refined_syntax_demo.as`
  - [ ] `simple_calculator.as`
  - [ ] `simple_calculator_refined.as`
  - [ ] `smoke_c_classifiers.as`
  - [ ] `smoke_c_classifiers_refined.as`
  - [ ] `smoke_c_io.as`
  - [ ] `smoke_c_io_refined.as`
  - [ ] `smoke_c_math.as`
  - [ ] `smoke_c_math_refined.as`
  - [ ] `smoke_c_string.as`
  - [ ] `smoke_c_string_refined.as`
  - [ ] `smoke_camelcase_libc.as`
  - [ ] `smoke_camelcase_libc_refined.as`
  - [ ] `stdlib_import_smoke.as`
  - [ ] `stdlib_import_smoke_buffers.as`
  - [ ] `stdlib_import_smoke_metadata.as`
  - [ ] `stdlib_import_smoke_runtime.as`
  - [ ] `stdlib_sanity_check.as`
  - [ ] `string_analyzer.as`
  - [ ] `sum_of_squares.as`
  - [ ] `sum_of_squares_refined.as`
  - [ ] `syntax_sample_web_server.as`
  - [ ] `todos_list.as`
  - [ ] `webserver_console.as`
  - [ ] `webserver_console_refined.as`
- [ ] Rename all files under `SemanticScript/sem/feature_tests/` from `.as` to `.sscript`.
  - [ ] Include `_modules/helper_lib.as`.
  - [ ] Keep `_modules/*.txt` names unless their contents contain legacy brand text.
  - [ ] Update every `# expect.xfail` command example inside feature tests.
  - [ ] Update literal source paths when they point to `.as`.
  - [ ] Run a final inventory command to verify zero `.as` remains in this tree.
- [ ] Rename all benchmark source files:
  - [ ] `SemanticScript/bench/bench_arith.as`
  - [ ] `SemanticScript/bench/bench_math.as`
  - [ ] `SemanticScript/bench/bench_memset.as`
  - [ ] `SemanticScript/bench/bench_strlen.as`
- [ ] Rename all bootstrap sources:
  - [ ] `SemanticScript/bootstrap/bootstrap.as`
  - [ ] `SemanticScript/bootstrap/bootstrap2.as`
  - [ ] `SemanticScript/bootstrap/bootstrap3.as`
  - [ ] `SemanticScript/bootstrap/bootstrap4.as`
  - [ ] `SemanticScript/bootstrap/bootstrap5.as`
  - [ ] `SemanticScript/bootstrap/bootstrap6.as`
  - [ ] `SemanticScript/bootstrap/bootstrap_general.as`
  - [ ] `SemanticScript/bootstrap/exit_code_probe.as`
  - [ ] `SemanticScript/bootstrap/input.as`
  - [ ] `SemanticScript/bootstrap/input3.as`
  - [ ] `SemanticScript/bootstrap/input4.as`
  - [ ] `SemanticScript/bootstrap/input5.as`
  - [ ] `SemanticScript/bootstrap/input6.as`
- [ ] Rename all standard library sources under `SemanticScript/stdlib_sem/`:
  - [ ] `array.as`
  - [ ] `assert.as`
  - [ ] `bit.as`
  - [ ] `bit.test.as`
  - [ ] `bool.as`
  - [ ] `bool.test.as`
  - [ ] `char.as`
  - [ ] `compare.as`
  - [ ] `compare.test.as`
  - [ ] `constants.as`
  - [ ] `convert.as`
  - [ ] `convert.test.as`
  - [ ] `ctype.as`
  - [ ] `errno.as`
  - [ ] `errno_more.as`
  - [ ] `inttypes.as`
  - [ ] `iso646.as`
  - [ ] `iso646.test.as`
  - [ ] `limits.as`
  - [ ] `math.as`
  - [ ] `math.test.as`
  - [ ] `math_float.as`
  - [ ] `memory.as`
  - [ ] `numeric.as`
  - [ ] `numeric.test.as`
  - [ ] `process.as`
  - [ ] `random.as`
  - [ ] `signal.as`
  - [ ] `signal_more.as`
  - [ ] `sort.as`
  - [ ] `stddef.as`
  - [ ] `stdio.as`
  - [ ] `stdlib.as`
  - [ ] `stdlib.test.as`
  - [ ] `string.as`
  - [ ] `time.as`
- [ ] Rename test fixture:
  - [ ] `SemanticScript/tests/tiny.as` -> `SemanticScript/tests/tiny.sscript`
- [ ] Add alias extension fixture:
  - [ ] `SemanticScript/tests/tiny.sem`
  - [ ] This should be a minimal valid program used only to verify `.sem` support.

## Phase 6 - Root Documentation

### `README.md`

- [ ] Change heading from `# AgentScript` to `# SemanticScript`.
- [ ] Replace all product wording with `SemanticScript`.
- [ ] Replace "flat, line-oriented, high-context program tape" wording with `semantic tape`.
- [ ] Update current/proposed syntax section:
  - [ ] `Current executable AgentScript` -> `Current executable SemanticScript`
  - [ ] `compiler/ascc.py` -> `compiler/semsc.py`
  - [ ] `linter/aslint.py` -> `linter/semlint.py`
  - [ ] `experiments/refined_syntax_example.as` -> current `.sscript` file or remove stale experiments reference.
- [ ] Update repository layout block:
  - [ ] `AgentScript.md` -> `SemanticScript.md`
  - [ ] `AgentScript/` -> `SemanticScript/`
  - [ ] `compiler/ascc.py` -> `compiler/semsc.py`
  - [ ] `linter/aslint.py` -> `linter/semlint.py`
  - [ ] `as/` -> `sem/`
  - [ ] `stdlib_as/` -> `stdlib_sem/`
  - [ ] `as_python/` -> `sem_python/`
  - [ ] `vscode-agentscript/` -> `vscode-semanticscript/`
- [ ] Update every command in Quick Start:
  - [ ] `cd AgentScript` -> `cd SemanticScript`
  - [ ] `python compiler/ascc.py --version` -> `python compiler/semsc.py --version`
  - [ ] `.as` examples -> `.sscript`
  - [ ] `python linter/aslint.py` -> `python linter/semlint.py`
- [ ] Update VS Code Extension section:
  - [ ] `.as` and `.agentscript` -> `.sscript` and `.sem`
  - [ ] `aslint.py` or `aslint2.py` -> `semlint.py` or `semlint2.py`
  - [ ] `agentscript-vscode-*.vsix` -> `semanticscript-vscode-*.vsix`
- [ ] Update Documentation Map.
- [ ] Remove all final legacy strings from examples and prose.

### `SemanticScript.md`

- [ ] Rename file from `AgentScript.md`.
- [ ] Change heading to `# SemanticScript`.
- [ ] Update opening blockquote to define SemanticScript.
- [ ] Replace every legacy brand mention.
- [ ] Replace all source-model phrases with `semantic tape` where appropriate:
  - [ ] `program tape`
  - [ ] `command tape`
  - [ ] `linear tape`
  - [ ] `contract tape`
  - [ ] `dependency interface tape`
- [ ] Update final summary quote to say SemanticScript and semantic tape.
- [ ] Review sections that compare against Node/Python and ensure the new brand reads naturally.
- [ ] Search the file for:
  - [ ] `AgentScript`
  - [ ] `agentscript`
  - [ ] `AGENTSCRIPT`
  - [ ] `.as`
  - [ ] `ascc`
  - [ ] `aslint`

### `SYNTAX.md`

- [ ] Change heading to `# SemanticScript Syntax Inventory`.
- [ ] Update compiler coverage note:
  - [ ] `SemanticScript/compiler/semsc.py`
  - [ ] `SemanticScript/bootstrap/bootstrap_general.sscript`
- [ ] Replace all `.as` file references with `.sscript`.
- [ ] Replace `stdlib_as` with `stdlib_sem`.
- [ ] Replace `ascc.py` with `semsc.py`.
- [ ] Verify syntax table examples still intentionally show language syntax, not file paths.

### `CHANGELOG.md`

- [ ] Add top unreleased entry for the rebrand.
- [ ] Decide historical policy:
  - [ ] Option A: keep old history but final brand rule fails.
  - [ ] Option B: rewrite old entries to SemanticScript terminology so final brand rule passes.
  - [ ] Required by user target: choose Option B or move old changelog to external release notes outside tracked repo.
- [ ] Rewrite every historic `AgentScript` occurrence to `SemanticScript`.
- [ ] Rewrite tool names in historical entries:
  - [ ] `ascc.py` -> `semsc.py`
  - [ ] `aslint.py` -> `semlint.py`
  - [ ] `aslint2.py` -> `semlint2.py` or structured-linter name.
  - [ ] `.as` -> `.sscript`
  - [ ] `stdlib_as` -> `stdlib_sem`
  - [ ] `vscode-agentscript` -> `vscode-semanticscript`
- [ ] Update commit subject text only if preserving exact historical names is not required.

### `.gitignore`

- [ ] Update ignored paths:
  - [ ] `AgentScript/tests/as_compiler_build/` -> `SemanticScript/tests/sem_compiler_build/`
  - [ ] `AgentScript/tests/feature_coverage/build/` -> `SemanticScript/tests/feature_coverage/build/`
  - [ ] `AgentScript/bootstrap/bootstrap_general.ll` -> `SemanticScript/bootstrap/bootstrap_general.ll`
- [ ] Update scratch pattern:
  - [ ] `.tmp_*.as` -> `.tmp_*.sscript`
  - [ ] Add `.tmp_*.sem`
- [ ] Confirm no ignored path contains legacy names.

## Phase 7 - Developer Documentation Files

### `docs/README.md`

- [ ] Heading: `# SemanticScript Developer Documentation`.
- [ ] Replace source paths:
  - [ ] `AgentScript/compiler/ascc.py` -> `SemanticScript/compiler/semsc.py`
  - [ ] `AgentScript/linter/aslint.py` -> `SemanticScript/linter/semlint.py`
  - [ ] `AgentScript/linter/aslint2.py` -> `SemanticScript/linter/semlint2.py` or final structured-linter path.
- [ ] Update doc map descriptions for compiler/linter.
- [ ] Update examples path:
  - [ ] `AgentScript/as/feature_tests/` -> `SemanticScript/sem/feature_tests/`
- [ ] Remove all final legacy text.

### `docs/agents.md`

- [ ] Heading: `# SemanticScript agents.md`.
- [ ] Update first summary line:
  - [ ] `AgentScript = flat semantic tape` -> `SemanticScript = semantic tape`.
- [ ] Replace references to truth files:
  - [ ] `ascc.py` -> `semsc.py`
  - [ ] `aslint2.py` -> `semlint2.py` or structured-linter name.
- [ ] Update command block:
  - [ ] `python AgentScript/compiler/ascc.py file.as --parse-only`
  - [ ] `python AgentScript/compiler/ascc.py file.as --run`
  - [ ] `python AgentScript/compiler/ascc.py file.as --emit-ir out.ll`
  - [ ] `python AgentScript/compiler/ascc.py file.as --emit-exe out.exe`
  - [ ] `python AgentScript/linter/aslint.py file.as --format json --fail-on none`
  - [ ] `python AgentScript/linter/aslint2.py file.as --format human`
  - [ ] `python AgentScript/linter/aslint2.py file.as --format json`
  - [ ] `python AgentScript/linter/aslint2.py file.as --tier T3 --code AS0101`
- [ ] Replace command block with `SemanticScript`, `semsc.py`, `semlint.py`, `.sscript`.
- [ ] Update maintainer workflow steps.
- [ ] Rename diagnostic-code examples if `AS####` becomes `SS####`.

### `docs/language/README.md`

- [ ] Replace language name.
- [ ] Replace `program tape` with `semantic tape`.
- [ ] Update executable/refined descriptions.
- [ ] Update paths:
  - [ ] `AgentScript/compiler/ascc.py`
  - [ ] `AgentScript/as/`
  - [ ] `AgentScript/as/feature_tests/`
- [ ] Update examples that mention `AgentScript` inside string literals.

### `docs/language/program-structure.md`

- [ ] Replace language name.
- [ ] Replace `.as` import examples with `.sscript`.
- [ ] Update import resolution path:
  - [ ] `standard/string.as` -> `standard/string.sscript`
  - [ ] `AgentScript/stdlib_as/` -> `SemanticScript/stdlib_sem/`
- [ ] Update `ascc.py` to `semsc.py`.

### `docs/language/lexical-model.md`

- [ ] Update tokenizer reference:
  - [ ] `AgentScript/compiler/ascc.py` -> `SemanticScript/compiler/semsc.py`
- [ ] Replace language name.
- [ ] Confirm examples use `.sscript` where file names appear.
- [ ] Replace "not AgentScript syntax" wording.

### `docs/language/types-values.md`

- [ ] Replace language name.
- [ ] Update `ascc.py` references.
- [ ] Update table heading `AgentScript type names` -> `SemanticScript type names`.

### `docs/language/operations-dataflow.md`

- [ ] Replace all language names.
- [ ] Replace source-model terminology with `semantic tape`.
- [ ] Update file extension references if any.

### `docs/language/errors-effects-capabilities.md`

- [ ] Replace all language names.
- [ ] Update `aslint2.py` references.
- [ ] Update linter name to final `semlint` naming.

### `docs/language/memory-state.md`

- [ ] Replace all language names.
- [ ] Update linter references.
- [ ] Update source model terms.

### `docs/language/concurrency-time-cleanup.md`

- [ ] Replace all language names.
- [ ] Update `aslint2.py` references.
- [ ] Confirm examples still describe actual compiler behavior.

### `docs/language/records-codecs-boundaries.md`

- [ ] Replace linter references:
  - [ ] `aslint2.py` -> `semlint2.py` or structured-linter name.
- [ ] Replace all language names.

### `docs/reference/call-targets.md`

- [ ] Replace path:
  - [ ] `AgentScript/compiler/libc_registry.py` -> `SemanticScript/compiler/libc_registry.py`
- [ ] Replace language name.
- [ ] Update "AgentScript-legal camelCase" phrasing.

### `docs/reference/maintenance.md`

- [ ] Replace all language names.
- [ ] Update maintenance checklist:
  - [ ] `AgentScript/compiler/ascc.py`
  - [ ] `AgentScript/as/feature_tests/`
  - [ ] `AgentScript/linter/aslint2.py`
  - [ ] `AgentScript/linter/aslint.py`
- [ ] Update test commands:
  - [ ] `python AgentScript/compiler/ascc.py AgentScript/as/feature_tests/<case>.as --parse-only`
  - [ ] `python AgentScript/linter/aslint2.py AgentScript/as/feature_tests/<case>.as --format human`
  - [ ] `cd AgentScript`
- [ ] Replace `.as` with `.sscript`.

### `docs/reference/verb-index.md`

- [ ] Search and replace all language names.
- [ ] Update any file extension/tooling references.
- [ ] Confirm generated verb list is still accurate after naming changes.

### `docs/toolchain/compiler.md`

- [ ] Heading remains `# Reference Compiler` unless product name is in prose.
- [ ] Replace reference compiler path:
  - [ ] `AgentScript/compiler/ascc.py` -> `SemanticScript/compiler/semsc.py`
- [ ] Replace all command examples:
  - [ ] `python compiler/ascc.py --version`
  - [ ] `python compiler/ascc.py as/fizzbuzz.as --parse-only`
  - [ ] `python compiler/ascc.py as/fizzbuzz.as --lint`
  - [ ] `python compiler/ascc.py as/fizzbuzz.as --run`
  - [ ] `python compiler/ascc.py as/fizzbuzz.as --emit-ir fizzbuzz.ll`
  - [ ] `python compiler/ascc.py as/fizzbuzz.as --emit-optimized-ir fizzbuzz.opt.ll --run`
  - [ ] `python compiler/ascc.py as/fizzbuzz.as --emit-exe fizzbuzz.exe`
- [ ] Update env vars:
  - [ ] `ASCC_CLANG`
  - [ ] `ASCC_TRACEBACK`
- [ ] Update parse pipeline terminology to `semantic tape`.
- [ ] Update import resolution to `.sscript` and `.sem`.
- [ ] Update feature test path.

### `docs/toolchain/linter.md`

- [ ] Replace title/prose with SemanticScript.
- [ ] Replace linter paths:
  - [ ] `AgentScript/linter/aslint.py`
  - [ ] `AgentScript/linter/aslint2.py`
- [ ] Replace commands with `semlint.py` and `.sscript`.
- [ ] Rename `aslint2 tiers` heading.
- [ ] Rename `as-record` output if applicable.
- [ ] Update VS Code settings namespace:
  - [ ] `agentScript.linter.engine` -> `semanticScript.linter.engine`
- [ ] Update final paragraph about refined syntax.

### `docs/toolchain/vscode-extension.md`

- [ ] Replace extension directory:
  - [ ] `vscode-agentscript/` -> `vscode-semanticscript/`
- [ ] Replace language registration:
  - [ ] `.as and .agentscript` -> `.sscript and .sem`
- [ ] Update settings examples:
  - [ ] `agentScript.segmentColors.enabled`
  - [ ] `agentScript.segmentColors.colorMode`
  - [ ] `agentScript.linter.enabled`
  - [ ] `agentScript.linter.engine`
  - [ ] `agentScript.linter.run`
  - [ ] `agentScript.linter.pythonPath`
  - [ ] `agentScript.linter.path`
  - [ ] `agentScript.linter.skipFutureSyntax`
- [ ] Update local development path:
  - [ ] `cd vscode-agentscript`
  - [ ] `../AgentScript/as/countdown.as`
  - [ ] `../AgentScript/as/feature_tests/147_worker_pool_submit_work_runs.as`
  - [ ] `../experiments/refined_syntax_example.as`
- [ ] Update grammar file name:
  - [ ] `syntaxes/agentscript.tmLanguage.json`
- [ ] Update package command docs.

### `python/README.md`

- [ ] Replace any language name references.
- [ ] Confirm this directory is still needed or fold into `samples/python/`.

### `samples/python/README.md`

- [ ] Replace any language name references.
- [ ] Confirm sample-oracle wording uses SemanticScript.

## Phase 8 - Implementation Docs Inside `SemanticScript/`

### `SemanticScript/AST.md`

- [ ] Replace all language names.
- [ ] Update source extension references.
- [ ] Update compiler/linter command examples.
- [ ] Update paths from `as/` to `sem/`.
- [ ] Replace `program tape` or `line tape` with `semantic tape`.
- [ ] Update any generated IR/module examples that include legacy names.

### `SemanticScript/bootstrap/README.md`

- [ ] Replace heading with `# SemanticScript bootstrap chain`.
- [ ] Replace all file names:
  - [ ] `bootstrap<n>.as` -> `bootstrap<n>.sscript`
  - [ ] `input<n>.as` -> `input<n>.sscript`
  - [ ] `bootstrap_general.as` -> `bootstrap_general.sscript`
- [ ] Replace compiler:
  - [ ] `compiler/ascc.py` -> `compiler/semsc.py`
- [ ] Replace `AS-written compiler` phrasing.
- [ ] Update support tables listing sample source files.
- [ ] Update LLVM module IDs if they include legacy brand:
  - [ ] `AgentScriptStage3SelfHosted`
  - [ ] `AgentScriptStage4SelfHosted`
  - [ ] `AgentScriptStage5SelfHosted`
  - [ ] `AgentScriptStage6SelfHosted`
- [ ] Update final deliverables section.

### `SemanticScript/stdlib_sem/README.md`

- [ ] Rename directory from `stdlib_as`.
- [ ] Replace language name.
- [ ] Replace `.as` module references with `.sscript`.
- [ ] Update smoke-test command examples.
- [ ] Confirm every module listed in the README exists after file rename.

### `SemanticScript/sem_python/README.md`

- [ ] Rename directory from `as_python`.
- [ ] Replace language name.
- [ ] Update any path references.

## Phase 9 - Bootstrap Source and Generated IR

### Bootstrap Python runner

- [ ] `SemanticScript/bootstrap/run_bootstrap_chain.py`
  - [ ] Update docstring title/prose to SemanticScript.
  - [ ] Rename `ASCC` variable to `SEMSC`.
  - [ ] Update compiler path to `compiler/semsc.py`.
  - [ ] Update stage descriptions:
    - [ ] `bootstrap.as` -> `bootstrap.sscript`
    - [ ] `input.as` -> `input.sscript`
    - [ ] All stage input names.
  - [ ] Update `compile_as` function name to `compile_semanticscript` or similar.
  - [ ] Update every `step(...)` message.
  - [ ] Update file reads for input fixtures.
  - [ ] Update final success message.

### Bootstrap `.sscript` source files

- [ ] `SemanticScript/bootstrap/bootstrap.sscript`
- [ ] `SemanticScript/bootstrap/bootstrap2.sscript`
- [ ] `SemanticScript/bootstrap/bootstrap3.sscript`
- [ ] `SemanticScript/bootstrap/bootstrap4.sscript`
- [ ] `SemanticScript/bootstrap/bootstrap5.sscript`
- [ ] `SemanticScript/bootstrap/bootstrap6.sscript`
- [ ] `SemanticScript/bootstrap/bootstrap_general.sscript`
- [ ] `SemanticScript/bootstrap/exit_code_probe.sscript`
- [ ] `SemanticScript/bootstrap/input.sscript`
- [ ] `SemanticScript/bootstrap/input3.sscript`
- [ ] `SemanticScript/bootstrap/input4.sscript`
- [ ] `SemanticScript/bootstrap/input5.sscript`
- [ ] `SemanticScript/bootstrap/input6.sscript`
- [ ] For each file above:
  - [ ] Replace legacy brand strings in comments and string literals unless they are part of an intentional test fixture.
  - [ ] Replace `.as` string literals with `.sscript`.
  - [ ] Replace env var strings `AS_INPUT` with final input env var.
  - [ ] Update any emitted module IDs containing legacy brand.

### Bootstrap `.ll` reference artifacts

- [ ] Decide whether tracked `.ll` reference artifacts remain tracked.
- [ ] If retained, update contents:
  - [ ] `SemanticScript/bootstrap/hello_self.ll`
  - [ ] `SemanticScript/bootstrap/stage2_hello.ll`
  - [ ] `SemanticScript/bootstrap/stage3.ll`
  - [ ] `SemanticScript/bootstrap/stage4.ll`
  - [ ] `SemanticScript/bootstrap/stage5.ll`
  - [ ] `SemanticScript/bootstrap/stage6.ll`
- [ ] Replace LLVM module IDs and comments containing legacy brand.
- [ ] Regenerate artifacts with `semsc` if needed.

## Phase 10 - Tests and Test Harnesses

### `SemanticScript/tests/test_compiler.py`

- [ ] Update docstring title/prose.
- [ ] Update import:
  - [ ] `import ascc` -> `import semsc`
- [ ] Update `COMPILER_DIR` usage to `semsc.py`.
- [ ] Update test labels:
  - [ ] `Running ascc`
  - [ ] `compile: hello.as`
  - [ ] all bootstrap labels mentioning `.as` or old compiler.
- [ ] Update fixture paths:
  - [ ] `ROOT / "as" / "hello.as"` -> `ROOT / "sem" / "hello.sscript"`
  - [ ] `BOOTSTRAP_DIR / f"{stage_basename}.as"` -> `.sscript`
  - [ ] all `input<n>.as` reads -> `.sscript`
- [ ] Update temp output replacement:
  - [ ] `.replace(".as", ".ll")` -> `.replace(".sscript", ".ll")`
  - [ ] `.replace(".as", ".exe")` -> `.replace(".sscript", ".exe")`
- [ ] Fix stale JS oracle path currently pointing at `PROJECT_ROOT / "javascript"` if samples now live under `samples/javascript`.
- [ ] Add explicit tests:
  - [ ] `.sscript` compile path.
  - [ ] `.sem` compile path.
  - [ ] `.as` rejection or absence.

### `SemanticScript/tests/test_stdlib.py`

- [ ] Update docstring.
- [ ] Rename `ASCC` variable to `SEMSC`.
- [ ] Update compiler path to `semsc.py`.
- [ ] Rename `STDLIB_DIR` target to `stdlib_sem`.
- [ ] Update `OK_PROGRAMS` list:
  - [ ] Every `.as` entry -> `.sscript`
  - [ ] Every `.test.as` companion rule -> `.test.sscript`
- [ ] Update comments around companion tests.
- [ ] Update `EXPECTED_STDIO_OUTPUT`:
  - [ ] `"Hello, AgentScript stdlib!\n"` -> SemanticScript.
- [ ] Update final output text if it mentions old names.

### `SemanticScript/tests/compare.py`

- [ ] Update docstring.
- [ ] Update compiler path:
  - [ ] `compiler/ascc.py` -> `compiler/semsc.py`
- [ ] Update source directory:
  - [ ] `AgentScript/as/<as>.as` -> `SemanticScript/sem/<name>.sscript`
- [ ] Rename variable names if user-facing:
  - [ ] `as_basename` -> `sem_basename` where practical.
- [ ] Update every program tuple from `.as` to `.sscript`.
- [ ] Confirm JS oracle path uses `samples/javascript/`.

### `SemanticScript/tests/sem_compiler_parity.py`

- [ ] Rename from `as_compiler_parity.py`.
- [ ] Update docstring and output title.
- [ ] Rename variables:
  - [ ] `AS_DIR` -> `SEM_DIR`
  - [ ] `ASCC` -> `SEMSC`
  - [ ] `AS_INPUT` -> final input env var.
  - [ ] `compile_via_as` -> `compile_via_semanticscript`.
- [ ] Update build dir:
  - [ ] `as_compiler_build` -> `sem_compiler_build`
- [ ] Update every program tuple from `.as` to `.sscript`.
- [ ] Update file replacement logic.
- [ ] Confirm JS oracle path uses `samples/javascript/`.

### `SemanticScript/tests/feature_coverage.py`

- [ ] Update docstring:
  - [ ] `AS language features`
  - [ ] `AS-written compiler`
  - [ ] `as/feature_tests/`
  - [ ] `ascc.py`
- [ ] Rename variables:
  - [ ] `ASCC` -> `SEMSC`
  - [ ] `BOOTSTRAP_GENERAL` path -> `bootstrap_general.sscript`
  - [ ] `TEST_DIR` -> `ROOT / "sem" / "feature_tests"`
  - [ ] `AS_INPUT` -> final input env var.
- [ ] Rename function:
  - [ ] `compile_via_as_compiler` -> `compile_via_semanticscript_compiler`
- [ ] Update test discovery:
  - [ ] `TEST_DIR.glob("*.as")` -> `*.sscript`
  - [ ] Add explicit `.sem` extension smoke elsewhere.
- [ ] Update output details:
  - [ ] `as-compile failed` -> `semanticscript-compile failed` or `semsc failed`.

### `SemanticScript/tests/stdout_blocking.js`

- [ ] Search for legacy brand strings.
- [ ] Update comments if needed.

### `SemanticScript/tests/tiny.sscript` and `tiny.sem`

- [ ] Rename `tiny.as`.
- [ ] Update content if it contains legacy strings.
- [ ] Add `.sem` variant for alias coverage.

## Phase 11 - Benchmarks

### `SemanticScript/bench/run_benchmarks.py`

- [ ] Update compiler path and names:
  - [ ] `ascc.py` -> `semsc.py`
  - [ ] `ASCC_CLANG` -> `SEMSC_CLANG`
- [ ] Update source file extensions:
  - [ ] `bench_arith.as` -> `bench_arith.sscript`
  - [ ] `bench_math.as` -> `bench_math.sscript`
  - [ ] `bench_memset.as` -> `bench_memset.sscript`
  - [ ] `bench_strlen.as` -> `bench_strlen.sscript`
- [ ] Update output labels and comments.

### Benchmark source files

- [ ] `SemanticScript/bench/bench_arith.sscript`
- [ ] `SemanticScript/bench/bench_math.sscript`
- [ ] `SemanticScript/bench/bench_memset.sscript`
- [ ] `SemanticScript/bench/bench_strlen.sscript`
- [ ] For each benchmark source:
  - [ ] Replace legacy brand strings.
  - [ ] Update any comments with old compiler or extension names.
- [ ] C benchmark files:
  - [ ] Search `bench_arith.c`, `bench_math.c`, `bench_memset.c`, `bench_qsort.c`, `bench_strlen.c`, `probe_clocks.c` for old brand text.

## Phase 12 - Standard Library Source and Smoke Tests

- [ ] Rename directory `stdlib_as` -> `stdlib_sem`.
- [ ] Rename every module to `.sscript`.
- [ ] For every module below:
  - [ ] Search content for `AgentScript`, `agentscript`, `AGENTSCRIPT`.
  - [ ] Search content for `.as`, `ascc`, `aslint`, `AS_INPUT`.
  - [ ] Update comments and string literals.
  - [ ] Verify `importModule` references still resolve after extension-aware import changes.

Files:

- [ ] `SemanticScript/stdlib_sem/array.sscript`
- [ ] `SemanticScript/stdlib_sem/assert.sscript`
- [ ] `SemanticScript/stdlib_sem/bit.sscript`
- [ ] `SemanticScript/stdlib_sem/bit.test.sscript`
- [ ] `SemanticScript/stdlib_sem/bool.sscript`
- [ ] `SemanticScript/stdlib_sem/bool.test.sscript`
- [ ] `SemanticScript/stdlib_sem/char.sscript`
- [ ] `SemanticScript/stdlib_sem/compare.sscript`
- [ ] `SemanticScript/stdlib_sem/compare.test.sscript`
- [ ] `SemanticScript/stdlib_sem/constants.sscript`
- [ ] `SemanticScript/stdlib_sem/convert.sscript`
- [ ] `SemanticScript/stdlib_sem/convert.test.sscript`
- [ ] `SemanticScript/stdlib_sem/ctype.sscript`
- [ ] `SemanticScript/stdlib_sem/errno.sscript`
- [ ] `SemanticScript/stdlib_sem/errno_more.sscript`
- [ ] `SemanticScript/stdlib_sem/inttypes.sscript`
- [ ] `SemanticScript/stdlib_sem/iso646.sscript`
- [ ] `SemanticScript/stdlib_sem/iso646.test.sscript`
- [ ] `SemanticScript/stdlib_sem/limits.sscript`
- [ ] `SemanticScript/stdlib_sem/math.sscript`
- [ ] `SemanticScript/stdlib_sem/math.test.sscript`
- [ ] `SemanticScript/stdlib_sem/math_float.sscript`
- [ ] `SemanticScript/stdlib_sem/memory.sscript`
- [ ] `SemanticScript/stdlib_sem/numeric.sscript`
- [ ] `SemanticScript/stdlib_sem/numeric.test.sscript`
- [ ] `SemanticScript/stdlib_sem/process.sscript`
- [ ] `SemanticScript/stdlib_sem/random.sscript`
- [ ] `SemanticScript/stdlib_sem/signal.sscript`
- [ ] `SemanticScript/stdlib_sem/signal_more.sscript`
- [ ] `SemanticScript/stdlib_sem/sort.sscript`
- [ ] `SemanticScript/stdlib_sem/stddef.sscript`
- [ ] `SemanticScript/stdlib_sem/stdio.sscript`
- [ ] `SemanticScript/stdlib_sem/stdlib.sscript`
- [ ] `SemanticScript/stdlib_sem/stdlib.test.sscript`
- [ ] `SemanticScript/stdlib_sem/string.sscript`
- [ ] `SemanticScript/stdlib_sem/time.sscript`

## Phase 13 - Example and Smoke Source Files

- [ ] Rename directory `sem/` after moving from `as/`.
- [ ] For every file below:
  - [ ] Rename `.as` to `.sscript`.
  - [ ] Replace legacy brand strings in comments.
  - [ ] Replace legacy brand strings in user-visible output unless a test explicitly validates old output.
  - [ ] Update any self-referential path or command examples.

Files:

- [ ] `SemanticScript/sem/async_workflow.sscript`
- [ ] `SemanticScript/sem/async_workflow_refined.sscript`
- [ ] `SemanticScript/sem/complex_checkout_saga.sscript`
- [ ] `SemanticScript/sem/countdown.sscript`
- [ ] `SemanticScript/sem/countdown_refined.sscript`
- [ ] `SemanticScript/sem/counterintuitive_closure_capture.sscript`
- [ ] `SemanticScript/sem/counterintuitive_closure_capture_refined.sscript`
- [ ] `SemanticScript/sem/counterintuitive_coercion.sscript`
- [ ] `SemanticScript/sem/counterintuitive_event_loop.sscript`
- [ ] `SemanticScript/sem/counterintuitive_mutation.sscript`
- [ ] `SemanticScript/sem/counterintuitive_numbers.sscript`
- [ ] `SemanticScript/sem/counterintuitive_this_binding.sscript`
- [ ] `SemanticScript/sem/esoteric_church_encoding.sscript`
- [ ] `SemanticScript/sem/esoteric_church_encoding_refined.sscript`
- [ ] `SemanticScript/sem/esoteric_reactive_proxy.sscript`
- [ ] `SemanticScript/sem/esoteric_self_referential.sscript`
- [ ] `SemanticScript/sem/esoteric_stack_language.sscript`
- [ ] `SemanticScript/sem/esoteric_trampoline.sscript`
- [ ] `SemanticScript/sem/esoteric_trampoline_refined.sscript`
- [ ] `SemanticScript/sem/event_workflow.sscript`
- [ ] `SemanticScript/sem/event_workflow_refined.sscript`
- [ ] `SemanticScript/sem/factorial.sscript`
- [ ] `SemanticScript/sem/factorial_refined.sscript`
- [ ] `SemanticScript/sem/file_inventory.sscript`
- [ ] `SemanticScript/sem/fizzbuzz.sscript`
- [ ] `SemanticScript/sem/fizzbuzz_refined.sscript`
- [ ] `SemanticScript/sem/hello.sscript`
- [ ] `SemanticScript/sem/hello_refined.sscript`
- [ ] `SemanticScript/sem/hello_via_c_printf.sscript`
- [ ] `SemanticScript/sem/hello_via_c_printf_refined.sscript`
- [ ] `SemanticScript/sem/hello_via_helper.sscript`
- [ ] `SemanticScript/sem/hello_via_helper_refined.sscript`
- [ ] `SemanticScript/sem/hello_world.sscript`
- [ ] `SemanticScript/sem/hello_world_refined.sscript`
- [ ] `SemanticScript/sem/inventory_manager.sscript`
- [ ] `SemanticScript/sem/json_order_summary.sscript`
- [ ] `SemanticScript/sem/number_stats.sscript`
- [ ] `SemanticScript/sem/refined_syntax_demo.sscript`
- [ ] `SemanticScript/sem/simple_calculator.sscript`
- [ ] `SemanticScript/sem/simple_calculator_refined.sscript`
- [ ] `SemanticScript/sem/smoke_c_classifiers.sscript`
- [ ] `SemanticScript/sem/smoke_c_classifiers_refined.sscript`
- [ ] `SemanticScript/sem/smoke_c_io.sscript`
- [ ] `SemanticScript/sem/smoke_c_io_refined.sscript`
- [ ] `SemanticScript/sem/smoke_c_math.sscript`
- [ ] `SemanticScript/sem/smoke_c_math_refined.sscript`
- [ ] `SemanticScript/sem/smoke_c_string.sscript`
- [ ] `SemanticScript/sem/smoke_c_string_refined.sscript`
- [ ] `SemanticScript/sem/smoke_camelcase_libc.sscript`
- [ ] `SemanticScript/sem/smoke_camelcase_libc_refined.sscript`
- [ ] `SemanticScript/sem/stdlib_import_smoke.sscript`
- [ ] `SemanticScript/sem/stdlib_import_smoke_buffers.sscript`
- [ ] `SemanticScript/sem/stdlib_import_smoke_metadata.sscript`
- [ ] `SemanticScript/sem/stdlib_import_smoke_runtime.sscript`
- [ ] `SemanticScript/sem/stdlib_sanity_check.sscript`
- [ ] `SemanticScript/sem/string_analyzer.sscript`
- [ ] `SemanticScript/sem/sum_of_squares.sscript`
- [ ] `SemanticScript/sem/sum_of_squares_refined.sscript`
- [ ] `SemanticScript/sem/syntax_sample_web_server.sscript`
- [ ] `SemanticScript/sem/todos_list.sscript`
- [ ] `SemanticScript/sem/webserver_console.sscript`
- [ ] `SemanticScript/sem/webserver_console_refined.sscript`

## Phase 14 - Feature Test Source Files

- [ ] Rename every `SemanticScript/sem/feature_tests/*.as` to `.sscript`.
- [ ] Rename `SemanticScript/sem/feature_tests/_modules/helper_lib.as` to `.sscript`.
- [ ] Update `121_cross_file_import` comments and import paths.
- [ ] Update every `# expect.xfail` command example from `ascc.py THIS_FILE` to `semsc.py THIS_FILE`.
- [ ] Update every `THIS_FILE` example extension if literal names are included.
- [ ] Replace legacy brand text in string literals where it affects expected output:
  - [ ] `59_pointer_isnull`
  - [ ] `88_string_byte_scan_loop`
  - [ ] `89_pointer_returning_recursion`
  - [ ] Any other feature fixture containing `agentscript`.
- [ ] Update test harness expected stdout if output text changes.
- [ ] Run full feature coverage after migration.
- [ ] Verify inventory:
  - [ ] `rg --files SemanticScript/sem/feature_tests -g "*.as"` returns no files.
  - [ ] `rg -n "AgentScript|agentscript|AGENTSCRIPT|ascc|aslint|\\.as\\b" SemanticScript/sem/feature_tests` returns no matches.

## Phase 15 - VS Code Extension Rebrand

### `vscode-semanticscript/package.json`

- [ ] Rename package:
  - [ ] `"name": "agentscript-vscode"` -> `"name": "semanticscript-vscode"`
- [ ] Update display:
  - [ ] `"displayName": "AgentScript"` -> `"displayName": "SemanticScript"`
- [ ] Update description:
  - [ ] `.as files` -> `.sscript and .sem files`
- [ ] Update publisher if desired:
  - [ ] `agentscript-local` -> `semanticscript-local`
- [ ] Update activation events:
  - [ ] `onLanguage:agentscript` -> `onLanguage:semanticscript`
  - [ ] `onCommand:agentscript.toggleSegmentColors` -> `onCommand:semanticscript.toggleSegmentColors`
  - [ ] `onCommand:agentscript.runLinter` -> `onCommand:semanticscript.runLinter`
- [ ] Update language contribution:
  - [ ] `id: agentscript` -> `semanticscript`
  - [ ] aliases: `SemanticScript`, `semanticscript`
  - [ ] extensions: `.sscript`, `.sem`
- [ ] Update grammar contribution:
  - [ ] `language: semanticscript`
  - [ ] `scopeName: source.semanticscript`
  - [ ] `path: ./syntaxes/semanticscript.tmLanguage.json`
- [ ] Update commands:
  - [ ] `semanticscript.toggleSegmentColors`
  - [ ] `SemanticScript: Toggle Segment Colors`
  - [ ] `semanticscript.runLinter`
  - [ ] `SemanticScript: Run Linter`
- [ ] Update configuration title.
- [ ] Update settings namespace:
  - [ ] `agentScript.segmentColors.enabled` -> `semanticScript.segmentColors.enabled`
  - [ ] `agentScript.segmentColors.colorMode` -> `semanticScript.segmentColors.colorMode`
  - [ ] `agentScript.linter.enabled` -> `semanticScript.linter.enabled`
  - [ ] `agentScript.linter.engine` -> `semanticScript.linter.engine`
  - [ ] `agentScript.linter.run` -> `semanticScript.linter.run`
  - [ ] `agentScript.linter.pythonPath` -> `semanticScript.linter.pythonPath`
  - [ ] `agentScript.linter.path` -> `semanticScript.linter.path`
  - [ ] `agentScript.linter.skipFutureSyntax` -> `semanticScript.linter.skipFutureSyntax`
- [ ] Update linter engine enum:
  - [ ] `aslint` -> `semlint`
  - [ ] `aslint2` -> `semlint2` or final structured engine name.
- [ ] Rename every semantic token id:
  - [ ] `agentscriptDeclarationVerb` -> `semanticscriptDeclarationVerb`
  - [ ] `agentscriptContextVerb` -> `semanticscriptContextVerb`
  - [ ] `agentscriptActionVerb` -> `semanticscriptActionVerb`
  - [ ] `agentscriptControlVerb` -> `semanticscriptControlVerb`
  - [ ] `agentscriptRoleSuffix` -> `semanticscriptRoleSuffix`
  - [ ] `agentscriptPrimitiveTarget` -> `semanticscriptPrimitiveTarget`
  - [ ] `agentscriptGeneratedTarget` -> `semanticscriptGeneratedTarget`
  - [ ] `agentscriptDomainTarget` -> `semanticscriptDomainTarget`
  - [ ] `agentscriptErrorVariant` -> `semanticscriptErrorVariant`
  - [ ] `agentscriptSchemaValue` -> `semanticscriptSchemaValue`
  - [ ] `agentscriptOpaqueInput` -> `semanticscriptOpaqueInput`
  - [ ] `agentscriptDeclaredName` -> `semanticscriptDeclaredName`
  - [ ] `agentscriptConstName` -> `semanticscriptConstName`
  - [ ] `agentscriptMutableName` -> `semanticscriptMutableName`
  - [ ] `agentscriptCallObject` -> `semanticscriptCallObject`
  - [ ] `agentscriptArgumentName` -> `semanticscriptArgumentName`
  - [ ] `agentscriptLabelName` -> `semanticscriptLabelName`
  - [ ] `agentscriptEffectPath` -> `semanticscriptEffectPath`
- [ ] Update token color scope names:
  - [ ] `.agentscript` -> `.semanticscript`
  - [ ] `type:agentscript` -> `type:semanticscript`
  - [ ] `namespace:agentscript` -> `namespace:semanticscript`
  - [ ] `variable:agentscript` -> `variable:semanticscript`
  - [ ] `string:agentscript` -> `string:semanticscript`
  - [ ] `number:agentscript` -> `number:semanticscript`
  - [ ] `comment:agentscript` -> `comment:semanticscript`
- [ ] Update configuration defaults:
  - [ ] `[agentscript]` -> `[semanticscript]`

### `vscode-semanticscript/extension.js`

- [ ] Rename language id checks:
  - [ ] `document.languageId === 'agentscript'` -> `semanticscript`
  - [ ] `{ language: 'agentscript' }` -> `semanticscript`
- [ ] Rename commands:
  - [ ] `agentscript.runLinter`
  - [ ] `agentscript.toggleSegmentColors`
- [ ] Rename settings reads:
  - [ ] `agentScript.segmentColors`
  - [ ] `agentScript.linter`
- [ ] Rename all token type strings from `agentscript*` to `semanticscript*`.
- [ ] Rename linter engine defaults:
  - [ ] `aslint` -> `semlint`
  - [ ] `aslint2` -> `semlint2` or final structured engine.
- [ ] Rename linter script selection:
  - [ ] `aslint.py` -> `semlint.py`
  - [ ] `aslint2.py` -> `semlint2.py`
- [ ] Update linter discovery paths:
  - [ ] `AgentScript/linter` -> `SemanticScript/linter`
- [ ] Update diagnostic collection name:
  - [ ] `aslint` -> `semlint`
- [ ] Update diagnostic sources:
  - [ ] `aslint`
  - [ ] `aslint2`
- [ ] Update hover text:
  - [ ] `Generated AgentScript target`
  - [ ] `operationBody kind for normal explicit AgentScript source tape`
  - [ ] `AgentScript role suffixes`
  - [ ] `AgentScript verb:`
  - [ ] `not current executable AgentScript`
- [ ] Update status bar text:
  - [ ] `AgentScript future syntax`
  - [ ] `AgentScript lint`
  - [ ] `AgentScript lint failed`
  - [ ] `AgentScript lint clean`
- [ ] Update user messages:
  - [ ] `Open an AgentScript file to run the linter.`
  - [ ] `AgentScript segment colors enabled/disabled.`
  - [ ] Linter not found message referencing `agentScript.linter.path`.
- [ ] Update markdown code fences:
  - [ ] `appendCodeblock(..., 'agentscript')` -> `semanticscript`
- [ ] Update extension regexes or extension checks:
  - [ ] `.as`
  - [ ] `.agentscript`
  - [ ] replace with `.sscript` and `.sem`
- [ ] Run `node --check extension.js`.

### `vscode-semanticscript/syntaxes/semanticscript.tmLanguage.json`

- [ ] Rename file from `agentscript.tmLanguage.json`.
- [ ] Update grammar `name` to `SemanticScript`.
- [ ] Update `scopeName` to `source.semanticscript`.
- [ ] Replace every TextMate scope suffix:
  - [ ] `.agentscript` -> `.semanticscript`
- [ ] Confirm no legacy scope names remain.

### `vscode-semanticscript/language-configuration.json`

- [ ] Search for legacy names.
- [ ] Update if any comment/language labels exist.

### `vscode-semanticscript/README.md`

- [ ] Heading: `# SemanticScript VS Code Extension`.
- [ ] Replace `.as` and `.agentscript` with `.sscript` and `.sem`.
- [ ] Replace extension settings namespace.
- [ ] Replace linter names and paths.
- [ ] Replace local install path:
  - [ ] `%USERPROFILE%\.vscode\extensions\agentscript-vscode`
- [ ] Replace command palette names.
- [ ] Replace development examples.
- [ ] Replace packaged artifact name.

## Phase 16 - Sample Oracles and Non-Language Code

### `samples/javascript/`

- [ ] Search every JS sample for legacy brand text.
- [ ] Update user-visible strings that say `AgentScript` or `agentscript`.
- [ ] Update expected outputs in tests to match changed sample strings.
- [ ] Files known to check:
  - [ ] `string-analyzer.js`
  - [ ] `todos-list.js`
  - [ ] Any oracle paired with a source file whose output string changes.

### `samples/python/`

- [ ] Search every Python sample for legacy brand text.
- [ ] Update README and comments.
- [ ] Update any output strings only if tests rely on them.

### top-level `python/`

- [ ] Search every Python comparison file for legacy brand text.
- [ ] Decide whether this duplicate old comparison directory should remain.
- [ ] If retained, update README and all references.

## Phase 17 - Internal Literal and Output String Changes

- [ ] Update source string literals that intentionally include old brand:
  - [ ] `Hello, AgentScript stdlib!` -> `Hello, SemanticScript stdlib!`
  - [ ] `Hello, AgentScript!` -> `Hello, SemanticScript!`
  - [ ] `AgentScript favors explicit context...` -> `SemanticScript favors explicit context...`
  - [ ] `agentscript: 1` -> `semanticscript: 1`
  - [ ] `AGENTSCRIPT_DEFINITELY_NOT_SET_X` -> `SEMANTICSCRIPT_DEFINITELY_NOT_SET_X`
  - [ ] `hello, agentscript` -> `hello, semanticscript`
  - [ ] `agentscript` pointer/string fixtures -> `semanticscript`
- [ ] For every literal change, update expected stdout or expected pointer offsets.
- [ ] Pay special attention to tests where string length or offset changes:
  - [ ] `stringByteLength("agentscript") == 11` must become correct for `semanticscript` length.
  - [ ] Feature tests that search for a character by offset must be recalculated.
  - [ ] Any expected top-word count must change from `agentscript` to `semanticscript`.

## Phase 18 - Generated and Ignored Artifact Cleanup

- [ ] Delete stale generated outputs that can contain legacy strings:
  - [ ] `AgentScript/tests/as_compiler_build/`
  - [ ] `AgentScript/tests/feature_coverage/build/`
  - [ ] `AgentScript/bootstrap/bootstrap_general.ll`
  - [ ] Any local `.exe` files produced by bootstrap/tests.
  - [ ] Any packaged `agentscript-vscode-*.vsix`.
- [ ] Regenerate needed reference `.ll` files after rebrand.
- [ ] Confirm `.gitignore` ignores the new generated paths.
- [ ] Confirm no generated legacy artifact is tracked.

## Phase 19 - Verification Commands

- [ ] Compiler version:
  - [ ] `cd SemanticScript`
  - [ ] `python compiler/semsc.py --version`
- [ ] Compiler parse:
  - [ ] `python compiler/semsc.py sem/fizzbuzz.sscript --parse-only`
  - [ ] `python compiler/semsc.py tests/tiny.sem --parse-only`
- [ ] Compiler run:
  - [ ] `python compiler/semsc.py sem/fizzbuzz.sscript --run`
- [ ] Emit IR:
  - [ ] `python compiler/semsc.py sem/fizzbuzz.sscript --emit-ir fizzbuzz.ll`
- [ ] Emit executable:
  - [ ] `python compiler/semsc.py sem/fizzbuzz.sscript --emit-exe fizzbuzz.exe`
- [ ] Linter:
  - [ ] `python linter/semlint.py sem/fizzbuzz.sscript --summary`
  - [ ] `python linter/semlint.py tests/tiny.sem --summary`
- [ ] Structured linter, if retained:
  - [ ] `python linter/semlint2.py sem/fizzbuzz.sscript --format json`
  - [ ] `python linter/semlint2.py sem/fizzbuzz.sscript --format agent`
- [ ] Main tests:
  - [ ] `python tests/compare.py`
  - [ ] `python tests/sem_compiler_parity.py`
  - [ ] `python tests/test_compiler.py`
  - [ ] `python tests/test_stdlib.py`
  - [ ] `python tests/feature_coverage.py`
  - [ ] `python bootstrap/run_bootstrap_chain.py`
- [ ] VS Code extension:
  - [ ] `cd ../vscode-semanticscript`
  - [ ] `npm run check`
  - [ ] `npx --yes @vscode/vsce package`

## Phase 20 - Final Legacy-String and File-Name Gates

Run these from the repository root after all renames and content edits.
All commands must report no unexpected matches.

- [ ] Content scan for legacy language brand:
  - [ ] `rg -n "AgentScript|agentscript|AGENTSCRIPT|Agent Script" --glob "!.git/**"`
- [ ] Content scan for old tools:
  - [ ] `rg -n "\\bascc\\b|\\baslint\\b|\\baslint2\\b|ASCC_|AS_INPUT" --glob "!.git/**"`
- [ ] Content scan for old extensions:
  - [ ] `rg -n "\\.as\\b|\\.agentscript\\b|source\\.agentscript|agentScript\\." --glob "!.git/**"`
- [ ] File-name scan for legacy language brand:
  - [ ] `rg --files | rg "AgentScript|agentscript|AGENTSCRIPT|vscode-agentscript"`
- [ ] File-name scan for old tool names:
  - [ ] `rg --files | rg "ascc|aslint|as_compiler|stdlib_as|as_python"`
- [ ] File-name scan for old source extensions:
  - [ ] `rg --files -g "*.as" -g "*.agentscript"`
- [ ] Verify expected new source extensions:
  - [ ] `rg --files -g "*.sscript"`
  - [ ] `rg --files -g "*.sem"`
- [ ] Verify expected new package names:
  - [ ] `rg -n "SemanticScript|semanticscript|SEMANTICSCRIPT" README.md SemanticScript.md SYNTAX.md docs SemanticScript vscode-semanticscript`
- [ ] Verify `TODO.md` itself no longer violates the final brand rule:
  - [ ] Either delete `TODO.md` after completion, or rewrite it as a completed SemanticScript migration note with no legacy terms.
- [ ] Verify the only remaining old brand occurrence is the external repo/root folder name, not tracked content or tracked file names.

## Phase 21 - Final Documentation Acceptance

- [ ] `README.md` presents SemanticScript as the only language name.
- [ ] `SemanticScript.md` is the root spec and uses `semantic tape`.
- [ ] `SYNTAX.md` names `semsc` as the compiler source of truth.
- [ ] `docs/toolchain/compiler.md` documents `semsc`.
- [ ] `docs/toolchain/linter.md` documents `semlint`.
- [ ] `docs/toolchain/vscode-extension.md` documents `.sscript`, `.sem`, and `semanticScript.*`.
- [ ] `CHANGELOG.md` contains a rebrand entry and no old brand string.
- [ ] VS Code package metadata displays SemanticScript only.
- [ ] No public command or setting uses legacy naming.
- [ ] No tracked `.as` or `.agentscript` source files remain.

## Phase 22 - Final Code Acceptance

- [ ] Compiler accepts `.sscript`.
- [ ] Compiler accepts `.sem`.
- [ ] Compiler does not require `.as` anywhere.
- [ ] Linter accepts `.sscript`.
- [ ] Linter accepts `.sem`.
- [ ] Linter does not require `.as` anywhere.
- [ ] Dotted imports resolve `.sscript` and `.sem`.
- [ ] Standard library imports resolve from `stdlib_sem/`.
- [ ] Tests pass with renamed files and paths.
- [ ] Bootstrap chain works with renamed input files.
- [ ] VS Code syntax highlighting activates for `.sscript` and `.sem`.
- [ ] VS Code linter integration calls `semlint`.
- [ ] Final scans prove the legacy brand no longer exists in repo content or tracked names.
