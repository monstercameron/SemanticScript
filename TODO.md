# SemanticScript 1.0 Release TODO

This file tracks the release-readiness gaps found in the 2026-05-18 project
review. A task is only done when the linked command or artifact is clean.

## P0 - Todo Web Native Webserver Effort

- [x] Add a granular root TODO section for the Todo Web native webserver work.
- [x] Preserve existing release TODO items without marking unrelated work done.
- [x] Keep the Todo Web effort scoped away from unrelated dirty app files.
- [x] Review current `webServer`, `serverHost`, `serverPort`, and `route`
      parser support.
- [x] Review current `target webServer` codegen behavior.
- [x] Review current opaque input handling for `HttpRequest`.
- [x] Review current type lowering for `HttpRequest` and `HttpResponse`.
- [x] Review the native HTTP adapter ABI in `sem_http_runtime.h`.
- [x] Review the default runtime adapter implementation in
      `sem_http_runtime.c`.
- [x] Review native executable linking in `semsc.py`.
- [x] Add LLVM type support for `HttpRequest`.
- [x] Add LLVM type support for `HttpResponse`.
- [x] Preserve `HttpRequest` route-handler inputs in the webserver ABI.
- [x] Preserve `HttpResponse` route-handler inputs in the webserver ABI.
- [x] Keep ordinary opaque dependency inputs skipped outside the web ABI.
- [x] Detect routed `webServer` declarations during no-entry codegen.
- [x] Collect route handler operation names before declaring user op functions.
- [x] Validate that route handlers declare `HttpRequest` then `HttpResponse`.
- [x] Validate that route handlers return `CSignedInt32` / i32.
- [x] Emit a real native `main` for routed webserver programs.
- [x] Emit an in-memory route table from `route` metadata.
- [x] Emit native server config from `serverHost`, `serverPort`, and routes.
- [x] Emit handler function pointers into the route table.
- [x] Declare `ss_http_server_run` in generated LLVM.
- [x] Call `ss_http_server_run` from generated `main`.
- [x] Lower `http.responseText` to `ss_http_response_text`.
- [x] Lower `http.requestMethod` to `ss_http_request_method`.
- [x] Lower `http.requestPath` to `ss_http_request_path`.
- [x] Preserve content type defaulting in the runtime adapter.
- [x] Link `sem_http_runtime.c` automatically for routed webserver executables.
- [x] Link Winsock automatically for routed webserver executables on Windows.
- [x] Replace the runtime stub backend with a blocking HTTP/1.1 socket backend.
- [x] Validate route tables before binding a socket.
- [x] Bind the configured server host.
- [x] Bind the configured server port.
- [x] Listen with a fixed connection backlog.
- [x] Accept client connections in a blocking loop.
- [x] Parse the HTTP request line.
- [x] Extract request method.
- [x] Extract request path.
- [x] Strip query strings before exact-route matching.
- [x] Match route methods case-insensitively.
- [x] Match route paths exactly.
- [x] Dispatch matched routes to generated SemanticScript handlers.
- [x] Pass `SSHttpRequest` into handlers.
- [x] Pass `SSHttpResponse` into handlers.
- [x] Send handler-written text responses.
- [x] Send `400 bad request` for malformed request lines.
- [x] Send `404 not found` for missing routes.
- [x] Send `500 handler failed` for handler status failures.
- [x] Send `500 handler did not write a response` for empty handler responses.
- [x] Emit `Content-Type`.
- [x] Emit `Content-Length`.
- [x] Emit `Connection: close`.
- [x] Close client sockets after each response.
- [x] Update runtime CMake to link Winsock on Windows.
- [x] Update native HTTP runtime docs for the new fallback backend.
- [x] Update native HTTP language docs for real native `main` support.
- [x] Update Todo Web to use a less collision-prone local port.
- [x] Add a Todo Web HTTP test harness.
- [x] Test Todo Web parse and compiler lint.
- [x] Test Todo Web standalone linter summary.
- [x] Test Todo Web LLVM IR emission.
- [x] Inspect emitted IR for the route handler signature.
- [x] Inspect emitted IR for `ss_http_response_text`.
- [x] Inspect emitted IR for `ss_http_server_run`.
- [x] Test native executable emission.
- [x] Test server startup from the native executable.
- [x] Test `GET /` returns HTTP 200.
- [x] Test `GET /` returns the TaskForge Web HTML shell.
- [x] Test `GET /?sample=1` still routes to `/`.
- [x] Test `GET /missing` returns HTTP 404.
- [x] Test 404 body is `not found`.
- [x] Test headers include `Content-Type`.
- [x] Test headers include correct `Content-Length`.
- [x] Test the server through Python `http.client`.
- [x] Test the server through external `curl.exe`.
- [x] Test runtime CMake build after socket backend changes.
- [x] Run compiler unit tests after codegen changes.

## P0 - Release Validation Must Be Green

- [x] Fix `python SemanticScript\tests\compare.py`.
  - [x] Fix `string_analyzer.sscript` parity: JS reports `characters: 104`
        and SemanticScript reports `characters: 101`; top-word ordering also
        differs (`favors` vs `semanticscript` in the fifth slot).
- [x] Decide how to treat the 30 expected-failure feature tests before 1.0.
  - [x] Scope 1.0 to the Python reference compiler.
  - [x] Remove the stale compiler-stage xfail workflow from the active tree.

## P1 - Agent Product Contract Parity

This section tracks the highest-value gaps found during the Zerolang comparison.
The goal is not to copy their syntax or implementation. The goal is to make
SemanticScript feel like one coherent, inspectable, repairable product for
agents: one obvious tool surface, version-matched rules, stable JSON contracts,
diagnostics that explain how to recover, and release checks that prove those
contracts do not drift.

The platform thesis to validate is:

```text
high-context source format
+ deterministic compiler/linter
+ JSON diagnostics
+ repair plans
+ source slicing
+ patch application
+ runnable examples
+ tight docs/skills for agents
```

If SemanticScript already has better repair geometry in the source, then the
tooling has to prove it moment-to-moment. The winning loop is one where the
agent never has to guess.

### Agent-First Tooling Pass - 2026-05-23

These items came directly from
`experiments/agent-first-tooling-research/README.md` and were implemented as a
first-pass agent contract in `SemanticScript/tools/sem.py`.

- [x] Add `sem version --json` and `sem --version --json`.
      The CLI now emits a machine-readable tool/version/runtime/syntax payload
      instead of only human text.

- [x] Add `sem check --json`.
      The wrapper now emits `sem.check.v1` with project facts, diagnostics,
      summary counts, unresolved references, runtime flags, and a target-
      readiness contract instead of requiring agents to scrape prose.

- [x] Add version-matched built-in skills through `sem skills list|get`.
      The first pass serves repository-backed skill payloads for language core,
      effects/capabilities, graph/slice workflows, TaskForge patterns, SQLite
      patterns, HTTP/HTML patterns, and patch/repair guidance.

- [x] Add `sem explain CODE` with JSON support.
      The first pass indexes current docs and linter tests so diagnostic codes
      are discoverable through one machine-readable explainer surface.

- [x] Add `sem graph --kind ... --json`.
      Implemented graph kinds: `summary`, `calls`, `effects`, `capabilities`,
      `auth`, `routes`, `dataflow`, `types`, and `ownership`.

- [x] Add structured readiness reporting.
      `sem readiness --json` now reports requested targets, required runtime
      adapters, missing adapters, blocking toolchain checks, partial toolchain
      checks, and a supported/partial/blocked status. `sem check --json` now
      embeds the same readiness contract instead of a placeholder.

- [x] Add `sem size --json`.
      The first pass reports source footprint, operation/call/route counts, and
      retained helper-family counts so agents can inspect artifact pressure
      without dropping straight into LLVM or backend internals.

- [x] Add `sem slice --json`.
      Implemented operation, route, symbol, effect, capability, and type
      anchors with neighborhood payloads that include semantic facts, callers,
      routes, and related docs/tests when discoverable.

- [x] Add `sem fix --plan --json`.
      The first pass generates structured reviewable repair plans from current
      diagnostics, including inline authority insertion for capability-coverage
      gaps and metadata-row insertion templates for missing purpose/invariant
      rows.

- [x] Add `sem patch --dry-run|--apply`.
      Patch application now consumes structured plan JSON, applies typed edits,
      rejects stale plans when target files drift, runs formatter normalization
      on apply, and returns a machine-readable verification payload.

- [x] Add `sem dev --json`.
      The first pass emits a watch-plan style contract with watched files,
      rerun actions, restart hints, interface fingerprints, trace intent, and
      target readiness facts for multi-step agent loops.

- [x] Add `sem test --json`.
      The first pass discovers SemanticScript `*.test.sem` / `*.test.sscript`
      files plus Python app harnesses, runs them through a structured result
      contract, and supports skipping Python harness execution when needed.

- [x] Add focused CLI contract tests for the new agent surfaces.
      `SemanticScript/tests/test_sem_cli.py` now covers check payloads, graph,
      slice, readiness, size, dev, skills, explain, fix-plan generation, test,
      patch application, and version JSON behavior.
      `SemanticScript/tests/test_command_contracts.py` now covers the actual
      subprocess command contracts for version, doctor, readiness, skills,
      check, explain, graph, slice, fix, patch, size, dev, and test.

- [x] Add explicit next-step guidance to the core JSON contracts.
      `sem check`, `sem readiness`, `sem explain`, `sem fix --plan`, `sem patch`,
      and `sem test` now return `nextCommands` entries so an agent can follow
      the local repair loop from the tool payload itself.

- [x] Make `sem check --json` the non-negotiable source of truth for structured
      diagnostics.
      This is table stakes. Every serious compiler or linter failure that an
      agent is expected to respond to should surface through one stable JSON
      contract with code, severity, message, span, expected/actual facts, and
      repair metadata.
  - [x] Add a canonical schema example to the CLI docs and tests, including
        fields equivalent to:
        `code`, `severity`, `message`, `span.file`, `span.line`,
        `span.column`, `expected`, `actual`, and `repair.id`.
  - [x] Fail command-contract tests on prose-only regressions or missing
        machine-readable repair hints.

- [x] Add version-matched agent skills served by the local toolchain.
      `sem skills list` and `sem skills get NAME` should expose the exact
      language, diagnostics, stdlib, build, testing, and package guidance that
      matches the compiler currently being used. This removes guesswork for
      agents and prevents stale docs from silently steering edits against the
      wrong binary or syntax contract.
  - [x] Define the canonical skill names:
        `sem`, `sem-agent`, `sem-language`, `sem-diagnostics`,
        `sem-stdlib`, `sem-builds`, `sem-packages`, and `sem-testing`.
  - [ ] If skills move to generated or embedded payloads, add release
        validation that fails when the shipped skill content is stale.
  - [x] Document the workflow in `docs/agents.md` and `README.md`: agents load
        the matching skill from the same `sem` binary that will check or build
        the project.

- [x] Make the agent-facing CLI contract obvious and stable.
      The public workflow should be readable as:
      `sem check --json`, `sem graph --json`, `sem slice --json`,
      `sem context --json`, `sem symbols --json`, `sem inspect-ir`,
      `sem size --json`, `sem explain CODE`, and
      `sem fix --plan --json`. Each command should have a crisp purpose,
      versioned JSON, and copyable examples in one CLI reference page.
  - [ ] Lock the ownership boundary between the primary retrieval surfaces
        (`graph`, `slice`) and the lower-level public fallbacks
        (`context`, `symbols`, `inspect-ir`).
  - [x] Add `sem size --json` or an equivalent command that explains retained
        runtime helpers, artifact budgets, profile policy, and optimization
        hints without requiring users to inspect LLVM IR.
  - [x] Add `sem explain CODE` as the human and JSON entry point for compiler
        and linter diagnostic codes.

- [ ] Unify compiler and linter diagnostics around repair metadata.
      Extend the existing `sem.check.v1` diagnostic shape until compiler
      diagnostics and `semlint` diagnostics share one common
      agent contract: stable code, severity, source span, expected/actual facts,
      rule text, help text, fix safety, repair id, related spans, and links to
      `sem explain`. Agents should be able to triage from JSON without scraping
      terminal prose or guessing whether a fix is local, behavior-preserving,
      API-changing, or requires human review.
  - [ ] Fully align compiler and linter fields inside `sem.check.v1`,
        including safety labels, related spans, and explain coverage.
  - [ ] Add fix-safety labels across compiler and linter output:
        `format-only`, `behavior-preserving`, `local-edit`, `api-changing`,
        `target-changing`, and `requires-human-review`.
  - [ ] Map existing `SS####` linter codes and compiler/backend failures into
        `sem explain` entries with canonical repair descriptions.

- [x] Add typed repair-plan support.
      `sem fix --plan --json PATH` should propose reviewable repairs without
      editing files. The first milestone can be plan-only for high-confidence
      failures such as unknown import, missing capability proof, unchecked
      fallible call, formatting drift, target capability mismatch, and obvious
      typo-class unknown names. The feature is valuable only if every proposed
      edit names its safety level and evidence.
      The output shape should be explicit enough to drive a later patch step:
      `diagnostic`, `repair`, `safe`, `file`, `insert_after_line`,
      `replace_range`, and exact emitted text.
  - [x] Implement plan-only output before any `--apply` behavior.
  - [x] Add negative tests proving risky repairs are labeled
        `requires-human-review` instead of auto-applicable.
  - [ ] Surface repair plans through the VS Code extension as quick-fix
        previews once the CLI contract is stable.

- [x] Add `sem slice` as the semantic-neighborhood retrieval tool.
      This is the most important differentiator if we want to beat compact
      languages on agent reliability. Agents rarely need the whole repo; they
      need the right semantic neighborhood with direct links to callers,
      callees, effects, capabilities, invariants, error paths, tests, and docs.
  - [x] Support operation-focused retrieval such as
        `sem slice --operation createTodoHandler --json`.
  - [x] Support route, symbol, effect, and capability retrieval such as
        `--route POST:/api/todos`, `--symbol serverPortNumber`,
        `--effect database`, and `--capability session.user`.
  - [x] Define one stable JSON shape containing at least:
        operation, inputs, outputs, effects, capabilities, called operations,
        callers, types, error paths, invariants, tests, and related docs.

- [x] Add `sem graph --json` as a first-class architecture map.
      The point is to hand agents a map instead of forcing them to reverse-
      engineer architecture from grep. The initial kinds should cover the
      surfaces most relevant to repair work: calls, effects, capabilities,
      routes, auth, types, and dataflow.
  - [x] Add graph kinds for `calls`, `effects`, `routes`, `auth`, and
        `dataflow`.
  - [x] Ensure `sem graph --kind ... --json` is contract-tested, not just
        documented.

- [x] Add `sem patch` for safe patch application and verification.
      `sem fix --plan --json` should propose; `sem patch` should apply or
      preview exactly those machine-readable edits. The CLI should support both
      dry runs and real application, followed by `sem check` and `sem test`
      verification in the happy path.
  - [x] Add `sem patch --dry-run PLAN.json`.
  - [x] Add `sem patch --apply PLAN.json`.
  - [x] Reject patch plans whose target file or context no longer matches.

- [x] Add command-contract tests for the agent JSON surface.
      Release validation should assert the shape and key fields of every JSON
      command that agents consume. These tests should fail on accidental schema
      drift, missing fields, prose-only regressions, changed version strings,
      unstable target facts, and lost diagnostic repair metadata.
  - [x] Add `SemanticScript/tests/test_command_contracts.py` or an equivalent
        focused harness.
  - [ ] Snapshot `sem --version --json`, `sem doctor --json`,
        `sem context --json`, `sem symbols --json`, `sem inspect-ir`,
        `sem lint --format json`, `sem size --json`, `sem explain --json`,
        `sem fix --plan --json`, `sem slice --json`, and
        `sem graph --kind ... --json`.
  - [x] Wire command-contract tests into CI and focused release validation.

- [x] Make `sem explain SSxxxx` a teaching surface, not just a code lookup.
      Diagnostics should explain what the rule means, why it matters, valid and
      invalid examples, safe repairs, and related diagnostics. This is how the
      toolchain teaches the agent the language instead of forcing it to guess.
  - [x] Return both text and JSON forms.
  - [ ] Expand curated coverage beyond the first-pass `SS####` and `SSRUN001`
        entries so compiler/backend diagnostics, examples, and severity
        metadata have the same depth.

- [x] Promote target readiness and capability facts to a first-class contract.
      SemanticScript already models effects, capabilities, runtimes, and build
      profiles, but agents need one direct answer to "will this build for this
      target and why?" Add a structured target-readiness report that separates
      source validity from backend availability, runtime adapter support,
      required capabilities, missing toolchains, and expected artifact shape.
  - [x] Add target readiness to `sem check --json` or a dedicated
        `sem targets --json` / `sem readiness --json` command.
  - [ ] Include runtime adapter facts for HTTP, SQLite, JSON, bcrypt, GUI,
        native async, and native HTTP client support.
  - [ ] Add repair guidance for choosing a supported target, installing a
        missing toolchain, or moving code behind a target-specific boundary.

- [x] Tighten the public README around the product path.
      The README should lead with install, check, run, inspect, repair, and
      validate before deeper philosophy. SemanticScript's philosophy is a
      strength, but first-time users and agents need the shortest path from
      checkout to useful compiler facts.
  - [x] Add a compact "Agent Workflow Interfaces" section with the canonical
        JSON and repair commands.
  - [x] Add a concise top-level sem-first quick path before the long philosophy
        sections so the first usable workflow is visible immediately.
  - [x] Ensure the representative README command set is copyable from a fresh
        checkout and has matching CI or release-validation coverage.

- [x] Treat `sem fmt` as mandatory platform infrastructure.
      A verbose language needs a formatter more than a compact one. Agent output
      has to normalize perfectly so diffs stay semantic and repair plans have
      stable landing zones.
  - [x] Make formatter behavior part of the public CLI contract.
        `sem fmt --check` is now part of the documented sem-first loop and has
        subprocess contract coverage.
  - [ ] Add formatter drift checks to the same command-contract discipline as
        the JSON tools.

- [x] Move the stable `sem` command-contract validation path into CI.
      The current release process documents several app, native runtime, and
      packaging checks as manual. Convert the stable checks into automated jobs
      so the repository proves its public contract continuously, not only during
      release preparation.
  - [x] Add CI coverage for `sem.py` command contracts and keep VS Code
        extension behavior in the same focused validation path.
  - [ ] Keep genuinely environment-specific checks documented as manual, but
        require each skipped check to print a reason in release validation.
  - [ ] Add a small benchmark smoke that records build time, run time, artifact
        size, and output-match facts without making noisy performance claims.

- [ ] Define a concrete release artifact story.
      Users should not have to infer whether SemanticScript is a source checkout,
      a Python tool, a release archive, or a future version manager. The first
      artifact can remain conservative, but it should be named, checksummed,
      documented, and validated with the same commands agents will use after
      installation.
  - [ ] Add a release manifest generator that records tool versions, commit,
        artifacts, checksums, validation commands, skipped checks, and known
        limitations.
  - [ ] Add a smoke test for installing or unpacking the release archive and
        running `sem --version`, `sem skills list`, `sem check`, and
        `sem doctor --json` outside the source checkout.
  - [ ] Decide when a Python package wrapper or native launcher becomes part of
        the public contract instead of a future note.

- [ ] Reduce visible compatibility and experiment sprawl in the public surface.
      The repo can keep experiments, but the default path should describe one
      current syntax, one formatter style, one package layout, and one agent
      workflow. Legacy aliases, partial rows, and research surfaces should be
      discoverable without looking like equal choices for new production code.
  - [ ] Mark legacy syntax paths as transitional in the CLI and docs.
  - [ ] Move experiment-only guidance out of first-read public docs.
  - [ ] Add a release-hygiene check for tracked local app data, stale generated
        files, and public docs that advertise unsupported syntax as executable.

## P1 - Weakness Research From External Review

This section turns the external platform review into concrete research work.
The goal is to improve SemanticScript's weak spots without throwing away the
source-level advantages that make it strong for long-session agent maintenance.
The key question is not "how do we look more like zerolang?" It is "which
parts of our current design are pulling real weight, which parts are ceremony,
and which platform gaps are making the language feel weaker than it is?"

- [ ] Research where SemanticScript's explicitness is genuinely reducing
      hallucination risk versus where it is only increasing row count.
      The current design may overfit to context-maximizing source shape. We
      need evidence for which rows are paying for themselves in real editing
      sessions and which rows mostly create consistency burden.
  - [ ] Build a measurement pass over real app code that reports rows per
        operation, rows per call, metadata density, and repeated declaration
        patterns across `apps/` and serious `experiments/`.
  - [ ] Identify the top 20 repeated row clusters that appear together often
        enough to justify research into a more compact but still explicit form.
  - [ ] Compare edit traces on representative tasks: one pass using the current
        full tape, another using hand-compressed equivalent source, and record
        which semantic mistakes become easier or harder.

- [ ] Research stale-metadata risk in the semantic tape.
      SemanticScript's biggest theoretical failure mode is authoritative-looking
      purpose, invariant, security, timing, or capability rows that drift away
      from executable behavior. If we cannot detect that drift, explicit source
      context becomes a trust hazard instead of a safety feature.
  - [ ] Inventory which metadata rows are compiler-enforced, strict-lint
        enforced, standalone-linter-only, or completely narrative today.
  - [ ] Add a "metadata drift" audit checklist for operations whose comments
        claim auth scope, cleanup, route guarantees, trust boundaries, or user
        isolation without a matching executable proof edge.
  - [ ] Research whether some narrative rows should become structured contracts
        with machine-checkable predicates rather than free-text annotations.
  - [ ] Add candidate lint families for metadata drift, with examples such as:
        invariant mentions session user but there is no session input; purpose
        says create todo but the operation calls update paths; moduleDoesNotOwn
        says no SQL but the operation declares database effects.

- [ ] Research compact forms for high-frequency safe patterns.
      The review is right that SemanticScript can feel ceremonious in the small.
      We should study where compact syntax would improve flow without collapsing
      back into opaque expression soup.
  - [ ] Evaluate compact forms for the most common checked-call pattern:
        `call` + `argument*` + `run` + `bind` + `branch error`.
  - [ ] Evaluate compact forms for common local-storage boilerplate, especially
        typed literals and single-use temporaries.
  - [ ] Reject any compact form that hides side effects, failure paths,
        ownership, or capability boundaries. The point is less ceremony, not
        fewer semantics.
  - [ ] In parallel, research command-driven canonical code generation as an
        alternative to syntax compression:
        `sem new operation ... --template ...`,
        `sem add call ...`, and `sem add error-path ...`.

- [ ] Research the executable-vs-refined surface split as a platform weakness.
      The review called out a real risk: users need `SYNTAX.md` to know whether
      a row is executable, partial, metadata-only, sync fallback, or future
      design. That weakens trust in the language and makes the product feel
      less coherent than it should.
  - [ ] Design a first-class support-status report that answers, for any row or
        target family, whether it is implemented, partial, parse-only,
        metadata-only, or proposed.
  - [ ] Add a CLI path for surfacing that answer directly from the toolchain
        instead of forcing users into docs archaeology.
  - [ ] Research whether the public language surface should narrow to one
        smaller "current executable SemanticScript" profile for 1.x.
  - [ ] Evaluate whether the public status taxonomy should be:
        `implemented`, `lint-only`, `metadata-only`, `planned`, and
        `deprecated`, with machine-readable output.

- [ ] Research small-program ergonomics and first-time readability.
      The review is also right that humans still matter. If tiny examples feel
      bloated or alien, we lose contributors before they experience the large-
      app auditability advantages.
  - [ ] Build a first-30-minutes onboarding script and measure how many steps a
        new contributor needs to install, check, run, lint, inspect, and modify
        a minimal program.
  - [ ] Compare `tiny.sem`, `hello.sem`, `taskforge-tui`, and one TaskForge Web
        route against equivalent zerolang examples for line count, concept
        count, and repair-loop steps.
  - [ ] Add a "minimum pleasant program" target and treat regressions in that
        experience as product bugs, not just documentation issues.

- [ ] Research whether business invariants should have stronger source shape.
      SemanticScript is strongest when the code makes auth scope, SQL scoping,
      resource cleanup, cookie policy, and user-isolation rules impossible to
      miss. We should push on that advantage rather than assume the current
      free-text rows are enough.
  - [ ] Identify the TaskForge and auction-arena invariants we most want agents
        to preserve: session-derived user IDs, auth gates, row ownership, route
        cleanup, and response/body guarantees.
  - [ ] Research dedicated invariant verbs or typed contract rows for the
        highest-value app rules that currently live only in prose.
  - [ ] Compare whether those rules are easier to preserve than in a compact
        static language with only diagnostics and tests.

- [ ] Research platform cohesion gaps that make the language underperform.
      Some of the score gap is not about syntax at all. It is about install
      path, command coherence, packaging, stdlib discoverability, target story,
      and how complete the day-to-day loop feels.
  - [ ] Audit every public command and doc page for whether it helps the user
        complete the loop: install, learn, write, inspect, repair, test, build,
        ship.
  - [ ] Inventory where the current workflow requires knowing internal file
        names like `semsc.py`, `semlint.py`, or specific docs instead of using
        one obvious `sem` surface.
  - [ ] Research whether some existing product gaps are better fixed by
        de-emphasizing subsurfaces rather than adding more commands.

- [ ] Research package, stdlib, and target-story trustworthiness.
      The review judged SemanticScript weaker on package workflow, install
      polish, target readiness, and stdlib breadth. Some of that is feature
      gap, but some of it is presentation and contract clarity.
  - [ ] Measure how far a user can get building a non-trivial app using only
        documented `standard.*` modules and `sem` commands, without reading
        compiler internals.
  - [ ] Identify which stdlib modules are truly app-ready, which are preview,
        and which only exist as declared surface area.
  - [ ] Research whether target/runtime readiness should be framed as a
        capability matrix, a support tier matrix, or both.

- [ ] Research reliability posture as part of product feel.
      The external review scored us behind on testing and CI because some of
      our best validation lives in app harnesses, manual notes, or broad test
      files rather than one crisp reliability surface.
  - [ ] Inventory which important guarantees are tested only indirectly through
        giant integration scripts or ad hoc manual steps.
  - [ ] Carve out smaller named reliability contracts: command contracts,
        runtime smoke, app smoke, target smoke, metadata drift, and benchmark
        smoke.
  - [ ] Research how much of the current broad `test_compiler.py` surface should
        become more searchable contract suites with narrower failure meaning.
  - [ ] Build an agent benchmark suite around a broken TaskForge app with
        seeded bugs: auth bug, SQL user-scope bug, missing error branch, wrong
        HTML escaping, wrong JSON field, missing capability, wrong effect,
        missing cleanup, bad route contract, and type mismatch.
  - [ ] Decide the scoreboard for that benchmark:
        pass rate, tokens used, repair attempts, semantic regressions, and
        time to green, with zerolang and a compact-language baseline.

- [ ] Produce a written design memo on the "platform vs source format" split.
      The review's core claim is plausible: SemanticScript may already be the
      better anti-hallucination source format while still being the weaker full
      platform. We should document that split cleanly, decide which side we are
      optimizing next, and avoid mixing research goals.
  - [ ] Write one memo that names SemanticScript's protected strengths:
        local semantic context, edit locality, effect/capability visibility,
        auditability, and explicit failure paths.
  - [ ] Write one memo that names the platform weaknesses to remove:
        ceremony budget, stale metadata risk, public workflow fragmentation,
        install/package friction, and support-surface ambiguity.
  - [ ] Use those memos to gate future syntax work: no new surface should land
        unless it either strengthens the protected source advantages or closes a
        measured platform weakness.
  - [ ] Record the working priority explicitly: pause novel syntax refinement
        until the tool loop is strong enough to test whether the current syntax
        already beats compact languages on agent reliability.

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
  - [x] SemanticScript-written compiler excluded from 1.0.
  - [x] VS Code extension support.
  - [x] Refined syntax support.
  - [x] Web/HTTP runtime support.

## P1 - Compiler / Stdlib Boundary Hardening

This section tracks the 2026-05-22 review concern that too much semantic,
business, or library behavior has moved into `SemanticScript/compiler/semsc.py`
instead of living in `SemanticScript/std/**` or `SemanticScript/runtime/**`.
The compiler may parse, validate, lower documented primitives, and select link
inputs. Public API contracts, domain policy, and reusable behavior should live
in standard-library modules or native runtime adapters.

- [x] Classify every compiler-owned intrinsic surface by ownership.
  - [x] Inventory all dotted call-target branches in `semsc.py`:
        `json.*`, `html.hydrate.*`, `http.*`, `sqlite.*`, `gui.*`,
        `bcrypt.*`, `pointer.*`, `math.*`, `console.*`, and `c.*`.
  - [x] For each target family, mark the owning layer:
        compiler syntax, standard-library contract, native runtime ABI,
        app-level helper, or temporary bootstrap shim.
  - [x] Add the ownership table to `docs/toolchain/compiler.md`.
  - [x] Add a short "do not add business logic here" note to
        `SemanticScript/compiler/README.md`.
  - [x] Confirm `SemanticScript/std/README.md` matches the ownership table.
  - [x] Add a review checklist item requiring new compiler target branches to
        name their stdlib/runtime owner and tests.

- [x] Move high-level JSON codec behavior out of ad hoc compiler lowering.
  - [x] Treat `json.stringify.<TypeName>` and `json.parse.<TypeName>` as
        `standard.json` / native JSON runtime behavior, not Python-side codec
        logic in `semsc.py`.
  - [x] Replace the current `json.encode.String` lowering that emits
        `snprintf("\"%s\"")`; it does not escape quotes, backslashes,
        newlines, tabs, carriage returns, or control bytes.
  - [x] Replace the current primitive parse lowerings that use `atoll`,
        `atof`, and `strcmp("true")`; malformed JSON must produce a
        `JsonDecodeError`, not a successful `0`, `0.0`, or `false`.
  - [x] Remove or quarantine `mark_high_level_json_success()` for parse paths
        until the lowering has a real runtime status value.
  - [x] Route primitive stringification through the native JSON builder or a
        dedicated runtime function with byte-exact escaping.
  - [x] Route primitive parsing through the native JSON document parser or a
        dedicated runtime function with strict token validation and trailing
        junk rejection.
  - [x] Keep record stringify/parse as generated glue only: field walking may
        be compiler-generated, but escaping, parsing, capacity enforcement, and
        status mapping must come from the JSON runtime.
  - [x] Add negative compiler/runtime tests for `json.stringify.String` with
        `"`, `\`, `\n`, `\r`, `\t`, and byte `0x01`.
  - [x] Add negative tests for `json.parse.I64` on `""`, `"abc"`, `"1x"`,
        `"1.5"`, `true`, `null`, and overflow-sized integers.
  - [x] Add negative tests for `json.parse.Bool` on `"falsex"`, `"0"`,
        `"TRUE"`, `null`, and empty input.
  - [x] Add negative tests for `json.parse.F64` on malformed and trailing-junk
        numbers.
  - [x] Keep the native JSON health demo as the byte-for-byte escaping oracle,
        and add a SemanticScript executable smoke that reaches the same paths
        through `json.stringify.<TypeName>`.
  - [x] Update `docs/language/json-crud.md`, `SYNTAX.md`, and
        `docs/reference/compatibility.md` after the runtime-backed behavior is
        in place.

- [x] Remove app-specific response-helper names from compiler strictness.
  - [x] Delete `writeJsonOkResponse`, `writeErrorJsonResponse`, and
        `writeJsonResponse` from `_STRICT_RESPONSE_WRITER_TARGETS`.
  - [x] Make `http.responseText`, `http.responseBytes`,
        `http.responseSseEvent`, `http.responseFile`, and declared
        `responseBodyForwarder` rows the only recognized response-body writer
        sources.
  - [x] Confirm `apps/taskforge-web/main.sem` keeps explicit
        `responseBodyForwarder` rows for its JSON response wrappers.
  - [x] Add a strict negative test proving an operation named
        `writeJsonOkResponse` is not trusted unless it actually forwards the
        declared body argument.
  - [x] Add a strict positive test proving a differently named wrapper works
        when it declares and honors `responseBodyForwarder`.
  - [x] Update SS3614 / SS3603 diagnostics so examples mention declared
        forwarders instead of app-specific helper names.

- [x] Split runtime-binding ABI shims from domain behavior.
  - [x] Audit `_RUNTIME_BINDING_MAP` and separate pure ABI bindings
        (`runtime.cstring.compare`, `runtime.cstring.byteLength`,
        `runtime.memory.copyBytes`) from policy-bearing behaviors.
  - [x] Move `retryPolicy.delayForAttempt` behavior out of `semsc.py`; the
        fixed `50 * (attempt + 1)` rule belongs in a standard retry module or
        runtime adapter that can read policy fields.
  - [x] Move `metrics.computeIncrementI64` out of compiler special cases unless
        it is just a normal `math.addI64` stdlib wrapper.
  - [x] Replace `metricsLock.acquire` / `metricsLock.release` sentinel returns
        with real stdlib/runtime behavior, or reject executable lowering until
        a lock runtime exists.
  - [x] Replace `scheduler.sleep` returning zero with a real runtime sleep
        path, or reject executable lowering and keep the row parse-only.
  - [x] Decide whether `runtime.calendar.isLeapYear*` is a stdlib operation
        implemented in SemanticScript, a native runtime function, or a true
        compiler intrinsic; document the decision.
  - [x] Add tests that refined-syntax demo behavior does not depend on hidden
        compiler constants after the move.
  - [x] Update `docs/optimization-guide.md` so synchronous fallbacks are
        described as temporary compatibility behavior, not hidden semantics.

- [x] Stop duplicating stdlib type/enum surfaces in parser startup.
  - [x] Remove unconditional `_register_builtin_sqlite_surface(prog)` from
        `parse()` once callers import `standard.sqlite` explicitly.
  - [x] Remove unconditional `_register_builtin_json_surface(prog)` from
        `parse()` once callers import `standard.json` explicitly.
  - [x] Decide whether `MiddlewareControl` is a language/runtime ABI enum or a
        `standard.http` export, then place its source of truth accordingly.
  - [x] Update standalone compiler smoke tests so they import the needed
        standard modules rather than relying on hidden parser preloads.
  - [x] Add drift tests that compare `std/json/main.sem` enum/type constants
        against native JSON ABI constants.
  - [x] Add drift tests that compare `std/sqlite/main.sem` enum/type constants
        against `sem_sqlite_runtime.h`.
  - [x] If a small built-in bootstrap surface remains, generate it from the
        standard module files or a shared contract table rather than duplicating
        literals by hand in `semsc.py`.

- [x] Make native runtime link policy data-driven.
  - [x] Remove the duplicate `_program_uses_bcrypt_runtime` and
        `_native_bcrypt_link_inputs` definitions from `semsc.py`.
  - [x] Create one native-runtime registry table for target family, call-target
        set or predicate, source files, include paths, libraries, and platform
        flags.
  - [x] Make `_native_runtime_link_inputs()` consume the registry instead of a
        hand-maintained list of collector functions.
  - [x] Include `native_http`, `native_sqlite`, `native_json`,
        `native_terminal`, `native_bcrypt`, `native_gui`, and the
        `standard.net` native HTTP client entry that links `native_async`.
  - [x] Add a regression test that fails on duplicate runtime collector
        definitions.
  - [x] Add a regression test that every `standard.<module>` advertising a
        compiler/runtime-owned intrinsic namespace has either executable
        lowering, explicit parse-only status, or an unsupported-target
        diagnostic.

- [x] Align the new `standard.net` / `native_async` surface with compiler
      support before advertising it as executable.
  - [x] Decide whether `net.fetch*` is proposed, parse-only, partial, or
        lowered in the current release scope.
  - [x] If parse-only, change `std/net/main.sem`, `std/README.md`, and
        `SYNTAX.md` wording so it does not imply executable compiler support.
        Not selected: the current branch has prototype lowering.
  - [x] If lowered, add `net.fetch*` call-target dispatch in `semsc.py` and
        link `SemanticScript/runtime/native_async/sem_async_runtime.c`.
  - [x] Add feature tests for unsupported `net.fetch*` targets so failures are
        intentional diagnostics, not generic `unsupported call target`.
        Not applicable while `net.fetch*` is lowered; current coverage checks
        IR lowering and runtime link inputs instead.
  - [x] Add native async runtime CMake / health-demo coverage to release
        validation if the runtime enters the release scope.

## P1 - Strict Syntax Hardening

This section turns the syntax research summarized under `research/` into
implementation-sized tasks. The
goal is to make recurring bug classes fail in the compiler itself, without
requiring a separate linter invocation.

### Strict Executable Mode

- [x] Decide the source row for strict mode.
  - [x] Prefer `languageMode strictExecutable` unless a better existing
        versioning row should own the setting.
  - [x] Decide whether strict mode belongs in source files, `build.sem`, or
        both.
  - [x] Decide whether strict mode is inherited by imported modules.
  - [x] Decide whether `languageVersion PROJECT "1.0"` implies strict mode in
        the future.
  - [x] Document the initial rollout as opt-in, not default.
- [x] Add parser support for `languageMode NAME`.
  - [x] Store language modes on `Program`.
  - [x] Reject duplicate incompatible language modes.
  - [x] Accept `strictExecutable`.
  - [x] Accept `refinedSyntax` for research files that intentionally use
        metadata-only rows.
  - [x] Reject unknown language-mode values with a parse diagnostic.
  - [x] Add syntax inventory rows for `languageMode strictExecutable`.
  - [x] Add syntax inventory rows for `languageMode refinedSyntax`.
- [x] Close the executable grammar when strict mode is active.
  - [x] Reject unknown lowercase top-level verbs in strict mode.
  - [x] Reject unknown lowercase operation-body verbs in strict mode.
  - [x] Keep typed comments and group anchors parseable in strict mode.
  - [x] Keep explicitly documented metadata-only rows parseable in strict
        mode only when they are in the allowed strict metadata set.
  - [x] Keep permissive parsing for non-strict refined examples.
  - [x] Add a clear diagnostic that tells users to add
        `languageMode refinedSyntax` only for research/metadata files.
- [x] Add strict-mode compiler tests.
  - [x] Negative test: misspelled lowercase top-level verb fails without
        `--lint`.
  - [x] Negative test: misspelled lowercase operation-body verb fails without
        `--lint`.
  - [x] Positive test: documented strict metadata row parses.
  - [x] Positive test: `languageMode refinedSyntax` preserves permissive
        metadata parsing.

### Shared Contract Tables

- [ ] Extract built-in call target signatures into a shared module.
  - [ ] Include math targets.
  - [ ] Include pointer targets.
  - [ ] Include C/libc targets or references to `libc_registry.py`.
  - [ ] Include native HTTP targets.
  - [ ] Include native GUI targets.
  - [ ] Include SQLite targets.
  - [ ] Include JSON runtime targets.
  - [ ] Make both `semsc.py` and `semlint.py` consume the same source of
        truth where practical.
- [ ] Add a shared fallibility table.
  - [ ] Mark heap allocation calls as fallible.
  - [ ] Mark file-open calls as fallible.
  - [ ] Mark native HTTP response writers as fallible.
  - [ ] Mark SQLite open/exec/prepare/bind/step/reset/finalize/close calls as
        fallible.
  - [ ] Mark checked arithmetic calls as fallible.
  - [ ] Mark infallible math calls as infallible.
  - [ ] Mark explicit status-return calls whose failures are status values,
        not `Result`, so they can require `bind value` or `ignore value`.
- [ ] Add a shared ownership table.
  - [ ] Mark `c.malloc`, `c.calloc`, and successful `c.realloc` outputs as
        owned heap buffers.
  - [ ] Mark `sqlite.openDatabase` success output as an owned SQLite database.
  - [ ] Mark `sqlite.prepareStatement` success output as an owned SQLite
        statement.
  - [ ] Mark cleanup targets for each owned resource.
  - [ ] Record whether cleanup is allowed by explicit call, `defer`, or both.
- [ ] Add drift tests for shared tables.
  - [ ] Verify linter and compiler agree on built-in signatures.
  - [ ] Verify linter and compiler agree on fallible targets.
  - [ ] Verify linter and compiler agree on owned-resource producers.

### Checked Fallible Calls

- [x] Design the checked call syntax.
  - [x] Confirm `runChecked CALL ok VALUE TYPE error ERROR TYPE else LABEL`
        is the preferred shape.
  - [x] Decide whether `runChecked` should create the ok/error binds itself.
        Current lowering creates both bindings from the call result/error value.
  - [x] Decide whether `runChecked` replaces or coexists with `run`,
        `bind ok`, `bind error`, and `branch error`.
        Decision: it coexists with the explicit checked pattern.
  - [x] Decide whether `runChecked` may target calls with no success value.
        Decision for this shape: use the explicit checked pattern with
        `ignore void`; a compact void-success form remains future syntax.
  - [x] Decide whether `runChecked` may target status-return calls.
        Current compiler accepts it for explicit-disposition fallible targets;
        response-writer coverage is tracked below.
  - [x] Decide whether `ignore ok` is still legal for checked calls.
        Decision: yes, for the explicit checked pattern.
- [x] Add parser support for `runChecked`.
  - [x] Add `runChecked` to body verb tables.
  - [x] Validate minimum arity.
  - [x] Validate keyword positions such as `ok`, `error`, and `else`.
  - [x] Preserve source line information for generated diagnostics.
- [ ] Add compiler validation for fallible targets in strict mode.
  - [x] Reject plain `run` for known fallible targets in strict mode.
  - [x] Reject plain `run` for Result-shaped SQLite prepare in strict mode.
  - [x] Require `runChecked` or an explicitly accepted checked pattern
        for every known fallible target.
  - [x] Accept the checked pattern for Result-shaped fallible calls.
  - [x] Reject unchecked explicit-disposition targets such as heap allocation
        and native HTTP response writers.
  - [ ] Reject `bind error` without a corresponding branch in strict mode.
  - [ ] Reject `branch error` on targets that the shared table marks
        infallible.
  - [ ] Reject fallible calls whose success value is used before the error
        branch is established.
  - [x] Ensure diagnostics point at the `run` line and the original `call`
        line.
- [x] Lower `runChecked`.
  - [x] Emit the same call lowering as `run`.
  - [x] Bind the success value on the fallthrough path.
  - [x] Bind the error value on the error path.
  - [x] Emit the branch to the declared failure label.
  - [x] Preserve existing `defer` behavior on both paths.
- [ ] Migrate app examples after the syntax exists.
  - [ ] Convert `apps/taskforge-web` heap allocations to `runChecked`.
  - [ ] Convert `apps/taskforge-web` SQLite bootstrap calls to `runChecked`.
  - [ ] Convert native HTTP response writes in sample apps to `runChecked`
        where appropriate.
  - [ ] Keep legacy examples only where they deliberately document old syntax.
- [ ] Add compiler tests for checked calls.
  - [x] Negative test: `c.malloc` with plain `run` fails in strict mode.
  - [x] Negative test: SQLite prepare with plain `run` fails in strict mode.
  - [x] Negative test: HTTP response write with ignored status fails in strict
        mode.
  - [x] Positive test: `runChecked` heap allocation compiles.
  - [ ] Positive test: `runChecked` SQLite prepare compiles.
  - [ ] Positive test: `runChecked` HTTP response write compiles.

### Owned Resources And Cleanup

- [ ] Design owned binding syntax.
  - [ ] Confirm `bind owned VALUE TYPE CALL cleanup TARGET` for infallible
        owned producers.
  - [ ] Confirm `bind ok owned VALUE TYPE CALL cleanup TARGET` for fallible
        owned producers.
  - [ ] Decide whether cleanup args are implicit from the owned value or
        explicitly listed.
  - [ ] Decide how ownership transfer is represented.
  - [ ] Decide whether `returnOwned` or `transferOwned` is needed.
  - [ ] Decide how owned values interact with `defer`.
- [ ] Add parser support for owned binding rows.
  - [ ] Add `bind owned`.
  - [ ] Add `bind ok owned`.
  - [ ] Validate `cleanup TARGET` arity.
  - [ ] Validate that the call target is in the ownership table.
  - [ ] Validate that the cleanup target matches the owned resource kind.
- [x] Add conservative compiler ownership validation.
  - [x] Reject returning from an operation while an owned value is live.
  - [x] Reject branching to a label that can return while an owned value is
        live and unreleased.
  - [x] Treat a matching explicit cleanup call as release.
  - [x] Treat a matching lowered `defer` as release where the backend actually
        emits it on that path.
  - [ ] Reject cleanup calls that consume a value after ownership transfer.
  - [x] Reject double cleanup of the same owned value in strict mode.
- [ ] Add SQLite ownership coverage.
  - [x] Model `sqlite.openDatabase` as producing owned `SqliteDatabase`.
  - [x] Model `sqlite.closeDatabase` as releasing `SqliteDatabase`.
  - [x] Model `sqlite.prepareStatement` as producing owned `SqliteStatement`.
  - [x] Model `sqlite.finalizeStatement` as releasing `SqliteStatement`.
  - [x] Check schema/bootstrap failure paths after database acquisition.
  - [x] Check statement failure paths after prepare succeeds.
- [ ] Add C heap ownership coverage.
  - [x] Model `c.malloc` as producing owned heap memory.
  - [x] Model `c.calloc` as producing owned heap memory.
  - [x] Model successful `c.realloc` as producing owned heap memory.
  - [x] Model `c.free` as releasing heap memory.
  - [x] Check return paths after heap acquisition.
  - [x] Check failure paths between heap acquisition and cleanup.
- [ ] Add ownership tests.
  - [x] Negative test: `sqlite.openDatabase` followed by schema failure
        without close fails in strict mode.
  - [x] Negative test: `sqlite.prepareStatement` without finalize fails in
        strict mode.
  - [x] Negative test: `c.malloc` without `c.free` fails in strict mode.
  - [x] Negative test: double `c.free` fails in strict mode.
  - [x] Positive test: explicit cleanup label compiles.
  - [x] Positive test: lowered `defer` cleanup compiles when supported.

### Nullable And Non-Null Values

- [ ] Add nullable ABI aliases.
  - [ ] Add `NullableCNullTerminatedByteString`.
  - [ ] Add `NullableCOpaqueMemoryAddress`.
  - [ ] Decide whether nullable aliases are first-class type constructors or
        named aliases only.
  - [x] Document which built-in call targets can return nullable values.
- [x] Update native HTTP request-reader contracts.
  - [x] Mark `http.requestHeader` as returning nullable text.
  - [x] Mark `http.requestQueryParam` as returning nullable text.
  - [x] Mark `http.requestBodyText` as nullable if absent body remains a
        possible runtime result.
  - [x] Mark multipart part text readers as nullable.
  - [x] Mark multipart part bytes readers as nullable.
  - [x] Keep `http.requestMethod` and `http.requestPath` non-null.
- [ ] Add non-null refinement syntax.
  - [ ] Add `requireNonNull OUT TYPE INPUT else LABEL`.
  - [ ] Decide whether the syntax should include an error binding.
  - [ ] Decide whether `requireNonNull` is allowed for all nullable pointer
        types or only text/body types.
  - [ ] Lower `requireNonNull` to `pointer.isNull` plus branch.
  - [ ] Bind the non-null value only on the success path.
- [ ] Enforce non-null response writer inputs.
  - [ ] Require `http.responseText` body to be non-null text.
  - [ ] Require `http.responseSseEvent` event and data to be non-null text.
  - [ ] Require `http.responseBytes` body to be non-null bytes when length is
        non-zero.
  - [ ] Reject direct nullable request-reader outputs passed to response
        writers.
  - [ ] Reject wrappers that erase nullable input without refinement.
- [ ] Add nullable tests.
  - [ ] Negative test: nullable request body passed directly to
        `http.responseText` fails.
  - [ ] Negative test: nullable header passed directly to `http.responseText`
        fails.
  - [ ] Positive test: `requireNonNull` then response write compiles.
  - [ ] Positive test: missing nullable value branches to explicit 400/404
        response path.

### Response Forwarding Contracts

- [ ] Decide final forwarding syntax.
  - [ ] Consider extending `input OP NAME TYPE forwardTo TARGET.ARG`.
  - [ ] Consider adding `forwardInput OP NAME to TARGET.ARG`.
  - [ ] Decide whether existing `responseBodyForwarder OP NAME` remains as a
        compatibility alias.
  - [ ] Decide whether forwarding contracts are required only in strict mode
        or always for response wrappers.
- [ ] Add parser support for the final forwarding contract.
  - [ ] Validate that the owning operation exists.
  - [ ] Validate that the input exists.
  - [ ] Validate that the target call argument is a known response-body slot.
  - [ ] Store forwarding facts on the operation contract.
- [ ] Add compiler validation for response wrappers.
  - [ ] Detect operations that pass an input directly to `http.responseText`
        body.
  - [ ] Detect operations that pass an input directly to `http.responseBytes`
        body.
  - [ ] Detect operations that pass an input directly to
        `http.responseSseEvent` event or data.
  - [ ] Reject missing forwarding contracts in strict mode.
  - [ ] Propagate nullable-body checks through forwarding contracts.
  - [ ] Propagate trust-boundary checks through forwarding contracts where
        available.
- [ ] Add forwarding tests.
  - [ ] Negative test: wrapper forwards response body without contract.
  - [ ] Negative test: wrapper declares wrong forwarded input.
  - [ ] Positive test: wrapper declares forwarding contract and compiles.
  - [ ] Positive test: transitive nullable body still requires
        `requireNonNull`.

### Capacity-Bounded Mutations

- [ ] Replace ambiguous row-count mutation contracts.
  - [ ] Identify all fixed-capacity row/list mutators in apps and stdlib.
  - [ ] Decide whether they return `Result RowCount RowCapacityError`.
  - [ ] Decide whether they return a closed `RowMutationStatus` enum plus
        output row count.
  - [ ] Decide whether unchanged row count is ever a valid success result.
  - [ ] Update syntax docs for capacity-bounded mutation contracts.
- [ ] Add compiler checks for strict capacity mutators.
  - [ ] Reject raw row-count outputs from operations marked as
        capacity-bounded mutators in strict mode.
  - [ ] Require call sites to branch on `Result` error or status enum before
        cursor movement.
  - [ ] Require dirty-state mutation only on the applied branch.
  - [ ] Require cursor movement only on the applied branch.
- [ ] Migrate `experiments/kilo-port`.
  - [ ] Convert `insertEmptyRowAt` to the selected strict result shape.
  - [ ] Convert `splitRowAt` to the selected strict result shape.
  - [ ] Update caller branches to use the new result/status.
  - [ ] Keep the existing linter rule as a migration warning for non-strict
        code.
- [ ] Add capacity-mutation tests.
  - [ ] Negative test: unchecked raw row count fails in strict mode.
  - [ ] Negative test: cursor moves before capacity branch fails.
  - [ ] Negative test: dirty flag set before capacity branch fails.
  - [ ] Positive test: full-buffer branch returns without cursor movement.
  - [ ] Positive test: applied branch updates cursor and dirty state.

### GUI Event Mutation Boundaries

- [ ] Define strict GUI effect-conflict rules.
  - [ ] Treat `read gui.control.listBox.selection` plus
        `write gui.control.listBox.items` as conflicting in one event handler.
  - [ ] Decide whether the conflict applies to all list boxes or only the same
        list box when handle identity can be tracked.
  - [ ] Decide whether setup/build operations are exempt.
  - [ ] Decide whether a specific opt-in mode such as
        `operationMode reconcileListItems` is allowed.
- [ ] Add compiler validation for GUI handlers.
  - [ ] Identify operations registered via `gui.controlOnEvent`.
  - [ ] Read declared effects on those handler operations.
  - [ ] Reject conflicting selection-read/list-item-write effects in strict
        mode.
  - [ ] Reject direct `gui.listBoxSelectedIndex` and
        `gui.listBoxAppendItem` calls in one handler when effects are missing
        or insufficient.
  - [ ] Preserve the linter rule for non-strict code.
- [ ] Add GUI boundary tests.
  - [ ] Negative test: complete-selected handler also appends list item.
  - [ ] Negative test: handler omits effects but calls both targets.
  - [ ] Positive test: setup handler appends items without selection read.
  - [ ] Positive test: selection handler updates status text only.
  - [ ] Positive test: explicit reconciliation mode compiles if the mode is
        accepted.

### Explicit ABI Conversions

- [ ] Define strict conversion policy.
  - [ ] Require explicit numeric conversions before width changes in strict
        mode.
  - [ ] Require explicit pointer conversions before pointer/int crossings in
        strict mode.
  - [ ] Decide which existing ABI coercions remain allowed for opaque runtime
        handles.
  - [ ] Decide whether return-position coercions are rejected or only warned
        during migration.
- [ ] Remove implicit conversions in strict mode.
  - [ ] Reject `CSignedInt32` passed to `math.addI64`.
  - [ ] Reject `CSignedInt32` passed to C varargs expecting a 64-bit format
        unless explicitly widened.
  - [ ] Reject GUI i64 values passed to i32 GUI args unless explicitly
        narrowed.
  - [ ] Reject pointer values passed through integer slots without explicit
        conversion.
  - [ ] Reject integer values passed to pointer args except documented null
        constants.
- [ ] Add conversion helper targets where missing.
  - [ ] Ensure signed i32 to signed i64 conversion is available.
  - [ ] Ensure signed i64 to signed i32 conversion is available.
  - [ ] Decide whether unsigned conversions need separate targets.
  - [ ] Decide whether pointer-to-int and int-to-pointer conversions should be
        named language operations or forbidden outside runtime code.
- [ ] Add explicit conversion tests.
  - [ ] Negative test: `snprintf` byte count added to i64 cursor without
        widening fails.
  - [ ] Positive test: widened `snprintf` byte count compiles.
  - [ ] Negative test: GUI i64 dimension passed to i32 argument fails in strict
        mode.
  - [ ] Positive test: explicit narrowing compiles when allowed.
  - [ ] Negative test: pointer/int crossing fails without explicit conversion.

### Web Route And Middleware Schemas

- [ ] Move route method validation into the compiler.
  - [x] Reject unsupported route methods without requiring `semlint`.
  - [x] Keep the allowed method set in one shared table.
  - [x] Include `GET`, `HEAD`, `POST`, `PUT`, `PATCH`, `DELETE`, and
        `OPTIONS`.
  - [ ] Decide whether lowercase source methods normalize or fail.
  - [x] Add diagnostics that point to the `route` row.
- [ ] Move middleware ABI validation into the compiler.
  - [x] Require middleware output `MiddlewareControl`.
  - [x] Reject bare `CSignedInt32` middleware output in strict mode.
  - [x] Require middleware handler input names and types to match the native
        ABI.
  - [ ] Validate short-circuit response expectations where possible.
- [ ] Move route handler naming/type validation earlier.
  - [x] Require route handler input names `request` and `response` in strict
        mode.
  - [x] Require route handler input types `HttpRequest` and `HttpResponse`.
  - [ ] Require route handler output `CSignedInt32` or the future strict HTTP
        result type if introduced.
  - [ ] Point diagnostics to both the `route` row and handler operation
        header.
- [ ] Enforce route coverage contracts.
  - [ ] Require timeout coverage for each route unless an opt-out row exists.
  - [ ] Require middleware coverage for each route unless an opt-out row
        exists.
  - [ ] Reject malformed opt-out rows in strict mode.
  - [ ] Decide whether coverage checks are target-specific to webserver builds
        or always active when `webServer` rows exist.
- [ ] Add web schema tests.
  - [x] Negative test: invalid method fails without `--lint`.
  - [x] Negative test: middleware returns bare `CSignedInt32`.
  - [x] Negative test: route handler has wrong input names.
  - [ ] Negative test: route missing timeout without opt-out.
  - [x] Positive test: valid middleware and handler shape compiles.
  - [ ] Positive test: explicit timeout/middleware opt-outs compile.

### Documentation And Tooling Follow-through

- [x] Update language docs after each strict syntax change.
  - [x] Update `SYNTAX.md`.
  - [x] Update `docs/language/lexical-model.md`.
  - [x] Update `docs/language/operations-dataflow.md`.
  - [x] Update `docs/language/errors-effects-capabilities.md`.
  - [x] Update `docs/language/memory-state.md`.
  - [x] Update `docs/language/native-http-api.md`.
  - [x] Update `docs/optimization-guide.md`.
- [x] Update toolchain docs.
  - [x] Document strict mode in `docs/toolchain/compiler.md`.
  - [x] Document which linter rules graduated to compiler errors.
  - [x] Document migration commands and expected diagnostics.
  - [x] Update agent workflow docs so agents run compiler negative tests, not
        only semlint.
- [ ] Update linter behavior after compiler hardening.
  - [ ] Keep linter rules for non-strict source.
  - [ ] Avoid duplicate diagnostics when the compiler already blocks the same
        strict-mode source.
  - [ ] Add fix candidates that migrate legacy patterns to strict syntax.
  - [ ] Keep aggressive targeted rules for app review and editor feedback.
- [ ] Update VS Code tooling.
  - [x] Add highlighting for `languageMode`.
  - [x] Add highlighting for `runChecked`.
  - [x] Add highlighting for owned-binding candidate rows.
  - [x] Add highlighting for `requireNonNull`.
  - [ ] Add highlighting for the final response-forwarding syntax.
  - [x] Add hover docs for each new strict syntax row.
- [ ] Add migration coverage.
  - [ ] Add strict-mode parse/build coverage for at least one console app.
  - [ ] Add strict-mode parse/build coverage for one webserver app.
  - [ ] Add strict-mode parse/build coverage for one GUI app if GUI remains in
        scope.
  - [ ] Add strict-mode parse/build coverage for one SQLite-using app.
  - [ ] Add a non-strict compatibility test so existing refined examples still
        parse.

## P1 - Declarative Windows GUI Target

This section tracks the declarative Windows desktop GUI surface. The design
goal is an English-aligned application graph in source, with Win32 handles,
message loops, `HWND`, `WPARAM`, and `LPARAM` hidden behind a native runtime
adapter the same way `HttpRequest` / `HttpResponse` hide HTTP runtime state.

Boundary decision after implementation review: keep `semsc.py` as a thin
bridge. `standard.gui` owns public GUI vocabulary, aliases, capabilities,
closed token sets, and semantic contracts; semlint owns rich misuse
diagnostics; the native GUI runtime owns platform behavior. The compiler may
accept `targetRuntime windowsGui`, lower explicit `gui.*` calls from ordinary
operation bodies, and link the native adapter. It must not build GUI
application graphs from custom top-level GUI keywords.

Design pivot: the row-centric `guiApplication` / `guiWindow` / `guiButton`
checklists below are retained as historical design notes only. The committed
surface is now `entry console main` plus `standard.gui` function calls.

### Completed MVP

- [x] Added `targetRuntime PROJECT windowsGui` to compiler build-tape
      validation.
- [x] Added `targetRuntime PROJECT windowsGui` to semlint build-tape
      validation.
- [x] Kept `entry windowsGui` out of the first committed executable surface.
- [x] Converted `apps/desktop-window-smoke` to `entry console main` plus standard
      `operation` / `call` / `argument` / `run` syntax.
- [x] Added `standard.gui` as the canonical contract module.
- [x] Added GUI type aliases, enums, capabilities, token constants, and runtime
      target constants to `std/gui/main.sem`.
- [x] Added lightweight GUI awareness to semlint and VS Code syntax tooling.
- [x] Added a native Win32 GUI runtime adapter with a backend-neutral
      `ss_gui_*` ABI.
- [x] Added the compiler link hook for the native GUI adapter.
- [x] Added a minimal `apps/desktop-window-smoke` sample.
- [x] Built `apps/desktop-window-smoke/build/desktop_window_smoke.exe`.
- [x] Verified the executable renders a Windows top-level window titled
      `Desktop Window Smoke` and exits `0` after the window is closed.

### GUI Target And Entry Model

- [x] Add `target windowsGui` to the syntax inventory.
- [x] Add `targetRuntime PROJECT windowsGui` to the build-tape enum.
- [x] Keep `entry windowsGui OPERATION` out of the committed surface for the
      first version.
- [x] Document that `target windowsGui` selects the GUI link/runtime bridge
      while source still declares a normal entry operation.
- [x] Reject no-entry `target windowsGui` codegen with guidance to use
      `entry console main` and `gui.*` calls.
- [x] Reject `entry windowsGui ...` with a diagnostic that points users to
      `entry console main` and `gui.applicationRun`.
- [x] Allow `targetRuntime windowsGui` build tapes that declare
      `entry console`.
- [ ] Decide whether `target windowsGui` may coexist with `target console` in
      one source, or reject mixed executable targets.
- [x] Define that closing the `guiApplicationMainWindow` ends the GUI message
      loop by default.
- [ ] Define how `guiApplicationOnExit` runs after the message loop exits.
- [ ] Define whether `guiApplicationOnExit` may cancel process exit or is
      cleanup-only.
- [x] Define default exit status when the main window closes cleanly.
- [x] Define exit status behavior when a GUI event handler returns non-zero.
- [x] Add `windowsGui` support to compiler build-tape validation.
- [x] Add `windowsGui` support to standalone linter build-tape validation.

### Committed Function Surface Follow-ups

- [x] Move executable GUI construction to `standard.gui` function targets.
- [x] Lower `gui.applicationCreate`, `gui.windowCreate`,
      `gui.textLabelCreate`, `gui.textBoxCreate`, `gui.buttonCreate`,
      `gui.listBoxCreate`, `gui.windowAddControl`,
      `gui.applicationSetMainWindow`, and `gui.applicationRun`.
- [x] Keep GUI source on normal `operation` / `call` / `argument` / `run` syntax.
- [x] Remove compiler code that discovers and lowers `guiApplication` /
      `guiWindow` metadata graphs.
- [x] Treat GUI keyword rows as non-standard in semlint.
- [ ] Add standard-library wrappers for platform-neutral layout policies before
      adding Linux/macOS backends.
- [x] Add event registration functions in `standard.gui` before adding handler
      dispatch.
- [ ] Add accessibility and sizing helper functions in `standard.gui` instead
      of adding new parser verbs.

### Syntax Naming And Shape

Resolution: the committed executable GUI surface is `entry console main` plus
`standard.gui` function targets. The row-centric names below are reserved
historical design notes only; if top-level GUI declaration rows are revived,
they must keep this naming shape. `importModule standard.gui as gui` remains
accepted during the compatibility window, but `importModule gui standard.gui`
is the preferred source shape.

- [x] Use `guiApplication APP`, not bare `application APP`, to avoid future
      collisions with web, mobile, package, or process concepts.
- [x] Use `guiWindow WINDOW`, not bare `window WINDOW`, so grep results are
      scoped to the GUI surface.
- [x] Use per-kind control declarators such as `guiButton CONTROL` and
      `guiTextBox CONTROL`, not `guiControl CONTROL KIND`.
- [x] Do not use `label CONTROL`; `label NAME` already owns control-flow
      labels. Use `guiTextLabel CONTROL`.
- [x] Keep every GUI verb lower camelCase.
- [x] Keep every GUI symbol value lower camelCase.
- [x] Keep every GUI opaque type PascalCase with a `Gui` prefix.
- [x] Keep all runtime call targets under the `gui.*` namespace.
- [x] Add `standard.gui` as the canonical import module for GUI contracts.
- [x] Reserve `importModule gui standard.gui` as the preferred GUI import
      shape.
- [x] Decide whether legacy `importModule standard.gui as gui` remains accepted
      during the compatibility window.
- [x] Add all committed GUI rows to `SYNTAX.md` with `Partial` status until
      parser, validation, codegen, and runtime are complete.
- [x] Add GUI verbs to `docs/reference/verb-index.md`.
- [x] Add GUI target notes to `docs/language/program-structure.md`.
- [x] Add GUI build-tape notes to `docs/language/project-layout-build-sem.md`.

### Application Rows

- [ ] Add parser support for `guiApplication APP`.
- [ ] Add parser support for `guiApplicationTitle APP "text"`.
- [ ] Add parser support for `guiApplicationIcon APP ICON_GROUP`.
- [ ] Add parser support for `guiApplicationMainWindow APP WINDOW`.
- [ ] Add parser support for `guiApplicationOnExit APP OPERATION`.
- [ ] Store GUI application rows in a dedicated `Program.gui_applications`
      index.
- [ ] Reject duplicate `guiApplication APP` rows.
- [ ] Reject duplicate singleton rows for one application title.
- [ ] Reject duplicate singleton rows for one application icon.
- [ ] Reject duplicate singleton rows for one application main window.
- [ ] Reject duplicate singleton rows for one application exit handler.
- [ ] Validate that `guiApplicationMainWindow` names a declared `guiWindow`.
- [ ] Validate that the main window belongs to the same application.
- [ ] Validate that `guiApplicationOnExit` names a declared operation.
- [ ] Validate the `guiApplicationOnExit` operation output contract.
- [ ] Decide whether `guiApplicationIcon` accepts only icon groups with
      `iconRole applicationPrimary` or any declared icon group.
- [ ] Reuse existing icon registry validation for GUI application icons.

### Window Rows

- [ ] Add parser support for `guiWindow WINDOW`.
- [ ] Add parser support for `guiWindowApplication WINDOW APP`.
- [ ] Add parser support for `guiWindowTitle WINDOW "text"`.
- [ ] Add parser support for `guiWindowWidth WINDOW PIXELS`.
- [ ] Add parser support for `guiWindowHeight WINDOW PIXELS`.
- [ ] Add parser support for `guiWindowMinimumWidth WINDOW PIXELS`.
- [ ] Add parser support for `guiWindowMinimumHeight WINDOW PIXELS`.
- [ ] Add parser support for
      `guiWindowLayout WINDOW verticalStack|horizontalStack|grid|absolute`.
- [ ] Add parser support for `guiWindowResizable WINDOW yes|no`.
- [ ] Add parser support for `guiWindowEvent WINDOW EVENT OPERATION`.
- [ ] Store GUI window rows in a dedicated `Program.gui_windows` index.
- [ ] Reject duplicate `guiWindow WINDOW` rows.
- [ ] Reject a `guiWindowApplication` that names an unknown application.
- [ ] Reject a `guiWindowTitle` row that names an unknown window.
- [ ] Reject width, height, and minimum-size rows with non-integer values.
- [ ] Reject width, height, and minimum-size rows with zero or negative values.
- [ ] Reject a minimum width larger than the initial window width.
- [ ] Reject a minimum height larger than the initial window height.
- [ ] Reject unknown `guiWindowLayout` values.
- [ ] Auto-register a `GuiWindowLayout` enum for
      `verticalStack`, `horizontalStack`, `grid`, and `absolute`.
- [ ] Reject unknown `guiWindowResizable` boolean tokens.
- [ ] Define default `guiWindowResizable` behavior when the row is omitted.
- [ ] Define default layout behavior when `guiWindowLayout` is omitted.
- [ ] Decide whether multiple windows per application are supported in the
      first implementation or parsed as future metadata.

### Control Declarators

- [ ] Add parser support for `guiButton CONTROL`.
- [ ] Add parser support for `guiTextBox CONTROL`.
- [ ] Add parser support for `guiListBox CONTROL`.
- [ ] Add parser support for `guiCheckBox CONTROL`.
- [ ] Add parser support for `guiMenuItem CONTROL`.
- [ ] Add parser support for `guiStatusBar CONTROL`.
- [ ] Add parser support for `guiTextLabel CONTROL`.
- [ ] Store controls in a dedicated `Program.gui_controls` index keyed by
      control symbol.
- [ ] Record each control's declared kind.
- [ ] Reject duplicate control symbols across all GUI control declarator kinds.
- [ ] Reject control symbols that collide with declared windows,
      applications, operations, constants, or storage bindings.
- [ ] Define each declarator as a typed compile-time handle constant:
      `guiButton addTodoButton` creates `addTodoButton : GuiButton`.
- [ ] Define `guiTextBox newTaskTitleTextBox` as
      `newTaskTitleTextBox : GuiTextBox`.
- [ ] Define `guiListBox visibleTodosListBox` as
      `visibleTodosListBox : GuiListBox`.
- [ ] Define `guiWindow todoAppMainWindow` as
      `todoAppMainWindow : GuiWindow`.
- [ ] Decide whether all control handles also subtype or alias a common
      `GuiControl` type.
- [ ] Ensure generated compile-time GUI handles can be passed as values to
      `gui.*` runtime calls.

### Generic Control Rows

- [ ] Add parser support for `guiControlWindow CONTROL WINDOW`.
- [ ] Add parser support for `guiControlEnabled CONTROL yes|no`.
- [ ] Add parser support for `guiControlVisible CONTROL yes|no`.
- [ ] Add parser support for `guiControlTabIndex CONTROL N`.
- [ ] Add parser support for `guiControlAccessibleName CONTROL "text"`.
- [ ] Add parser support for `guiControlEvent CONTROL EVENT OPERATION`.
- [ ] Reject generic control rows that name an unknown control.
- [ ] Reject `guiControlWindow` rows that name an unknown window.
- [ ] Reject controls without a `guiControlWindow` row.
- [ ] Reject duplicate `guiControlWindow` rows for one control.
- [ ] Reject duplicate `guiControlTabIndex` rows for one control.
- [ ] Reject duplicate `guiControlAccessibleName` rows for one control.
- [ ] Reject invalid yes/no values for enabled and visible rows.
- [ ] Define default enabled behavior when `guiControlEnabled` is omitted.
- [ ] Define default visible behavior when `guiControlVisible` is omitted.
- [ ] Reject negative tab-index values.
- [ ] Warn on duplicate tab-index values within one window.
- [ ] Warn when interactive controls omit `guiControlAccessibleName`.
- [ ] Decide whether `guiControlAccessibleName` defaults from visible text for
      buttons, check boxes, and labels.

### Kind-Specific Control Rows

- [ ] Add parser support for `guiButtonText BUTTON "text"`.
- [ ] Add parser support for `guiButtonIsDefault BUTTON yes|no`.
- [ ] Add parser support for `guiTextBoxPlaceholder TEXTBOX "text"`.
- [ ] Add parser support for `guiTextBoxMaxLength TEXTBOX N`.
- [ ] Add parser support for
      `guiListBoxSelectionMode LISTBOX single|multiple`.
- [ ] Add parser support for `guiCheckBoxChecked CHECKBOX yes|no`.
- [ ] Add parser support for `guiTextLabelText LABEL "text"`.
- [ ] Reject `guiButtonText` for non-button controls.
- [ ] Reject `guiButtonIsDefault` for non-button controls.
- [ ] Reject `guiTextBoxPlaceholder` for non-text-box controls.
- [ ] Reject `guiTextBoxMaxLength` for non-text-box controls.
- [ ] Reject `guiListBoxSelectionMode` for non-list-box controls.
- [ ] Reject `guiCheckBoxChecked` for non-check-box controls.
- [ ] Reject `guiTextLabelText` for non-text-label controls.
- [ ] Reject text-box max length values less than one.
- [ ] Define max length default behavior when the row is omitted.
- [ ] Auto-register a `GuiListBoxSelectionMode` enum for `single` and
      `multiple`.
- [ ] Reject unknown list-box selection mode values.
- [ ] Decide whether buttons may omit `guiButtonText`.
- [ ] Decide whether text labels may omit `guiTextLabelText`.
- [ ] Add diagnostics for controls that are declared but visually empty.

### Event Model

- [x] Add a built-in `GuiEventKind` enum, or equivalent closed token set, for
      GUI event rows.
- [x] Include `click` in the committed event set.
- [x] Include `valueChanged` in the committed event set.
- [x] Include `selectionChanged` in the committed event set.
- [x] Include `enterPressed` in the committed event set.
- [x] Include `keyPressed` in the committed event set.
- [x] Include `focusGained` in the committed event set.
- [x] Include `focusLost` in the committed event set.
- [x] Include `closeRequested` in the committed event set.
- [x] Include `resized` in the committed event set.
- [x] Include `shown` in the committed event set.
- [x] Include `hidden` in the committed event set.
- [ ] Validate allowed control events by control kind.
- [ ] Validate allowed window events by window kind.
- [x] Allow `guiButton` to handle `click`.
- [x] Allow `guiButton` to handle `focusGained` and `focusLost`.
- [x] Allow `guiTextBox` to handle `valueChanged`, `enterPressed`,
      `keyPressed`, `focusGained`, and `focusLost`.
- [x] Allow `guiListBox` to handle `selectionChanged`, `focusGained`, and
      `focusLost`.
- [x] Allow `guiCheckBox` to handle `valueChanged`, `click`, `focusGained`,
      and `focusLost`.
- [x] Allow `guiWindow` to handle `closeRequested`, `resized`, `shown`, and
      `hidden`.
- [ ] Reject `selectionChanged` on buttons.
- [ ] Reject `click` on list boxes unless a future design explicitly supports
      item activation.
- [ ] Reject `closeRequested` on controls.
- [ ] Reject unknown event tokens.
- [ ] Reject event rows whose handler operation is missing.
- [ ] Reject duplicate event handlers for the same target/event pair unless
      ordered event pipelines are designed.
- [ ] Decide whether event handler order is source-order or intentionally
      unsupported for the first version.

### Handler ABI

- [x] Auto-register `GuiSession` as an opaque handler input type.
- [x] Auto-register `GuiEvent` as an opaque handler input type.
- [x] Auto-register `GuiWindow` as an opaque declarative handle type.
- [x] Auto-register `GuiControl` as an opaque common control handle type if a
      common supertype is adopted.
- [x] Auto-register `GuiButton`.
- [x] Auto-register `GuiTextBox`.
- [x] Auto-register `GuiListBox`.
- [x] Auto-register `GuiCheckBox`.
- [x] Auto-register `GuiMenuItem`.
- [x] Auto-register `GuiStatusBar`.
- [x] Auto-register `GuiTextLabel`.
- [x] Define GUI handler operations as
      `input HANDLER session GuiSession`,
      `input HANDLER event GuiEvent`,
      and `output HANDLER CSignedInt32`.
- [ ] Reject GUI event handlers with missing `GuiSession` input.
- [ ] Reject GUI event handlers with missing `GuiEvent` input.
- [ ] Reject GUI event handlers with extra native ABI inputs.
- [ ] Reject GUI event handlers whose output is not `CSignedInt32`.
- [x] Define that handler return `0` means handled successfully.
- [x] Define non-zero handler returns as runtime-level event failure.
- [ ] Decide whether non-zero handler returns close the window, log and
      continue, or trap in dev builds.
- [x] Preserve `GuiSession` and `GuiEvent` as ABI parameters for GUI handlers,
      like `HttpRequest` and `HttpResponse` are preserved for route handlers.
- [x] Continue dropping ordinary opaque dependency inputs outside the GUI and
      HTTP ABIs.

### Runtime Call Surface

- [x] Add `gui.textBoxText`.
- [x] Add `gui.textBoxSetText`.
- [x] Add `gui.listBoxSelectedIndex`.
- [x] Add `gui.listBoxAppendItem`.
- [x] Add `gui.listBoxClear`.
- [x] Add `gui.windowClose`.
- [ ] Add `gui.eventKeyCode`.
- [ ] Add `gui.eventSelectedIndex`.
- [ ] Add `gui.eventWindowWidth`.
- [ ] Add `gui.eventWindowHeight`.
- [ ] Add `gui.eventCancelClose` or explicitly defer cancellable close events.
- [x] Define required args for every `gui.*` runtime call.
- [x] Require `session GuiSession` on every GUI runtime call that touches
      live GUI state.
- [x] Define whether declarative handles are passed as `control`, `button`,
      `textBox`, `listBox`, or kind-specific argument names.
- [x] Reject passing a `GuiButton` handle to `gui.textBoxText`.
- [x] Reject passing a `GuiTextBox` handle to `gui.listBoxAppendItem`.
- [x] Lower declarative GUI handle symbols to runtime control IDs or handles.
- [x] Define the lifetime of strings returned by `gui.textBoxText`.
- [x] Define whether returned GUI strings are copied, borrowed, or valid only
      until the next GUI runtime call.
- [x] Define list-box item encoding as null-terminated UTF-8 or a future
      UTF-16 aware string type.
- [x] Decide whether the MVP runtime stores UTF-8 internally and converts to
      UTF-16 at the Win32 boundary.
- [x] Add source-of-truth comments so `semsc.py`, `semlint.py`, `SYNTAX.md`,
      and `standard.gui` stay aligned on `gui.*` target names.

### Effects And Capabilities

- [x] Define `gui.control.textBox.text read`.
- [x] Define `gui.control.textBox.text write`.
- [x] Define `gui.control.listBox.items read`.
- [x] Define `gui.control.listBox.items write`.
- [x] Define `gui.control.listBox.selection read`.
- [x] Define `gui.control.checkBox.checked read`.
- [x] Define `gui.control.checkBox.checked write`.
- [x] Define `gui.window write`.
- [x] Define `gui.event read`.
- [x] Define `gui.event.close write` if close cancellation is supported.
- [x] Add reusable `standard.gui` capability declarations such as
      `guiTextBoxReader`, `guiTextBoxWriter`, and `guiListBoxWriter`.
- [x] Ensure existing effect/capability coverage checks work unchanged for
      hierarchical GUI paths.
- [x] Add lint tests proving `gui.control.textBox.text read` is covered by
      `capability guiTextBoxReader gui.control.textBox.text read`.
- [ ] Add lint tests proving a coarse capability such as
      `gui.control read` covers narrower read paths only if hierarchical
      coverage semantics intentionally allow it.
- [ ] Warn on overbroad GUI capabilities in exported module APIs.
- [ ] Decide whether GUI event registration rows require capabilities or only
      handler bodies require capabilities.

### Compiler Parser And Program Model

- [ ] Add GUI model classes or dictionaries to `Program`.
- [ ] Add parse handlers for all committed `guiApplication*` rows.
- [ ] Add parse handlers for all committed `guiWindow*` rows.
- [ ] Add parse handlers for all committed GUI control declarator rows.
- [ ] Add parse handlers for all committed `guiControl*` rows.
- [ ] Add parse handlers for all committed kind-specific control rows.
- [ ] Preserve source line numbers for every GUI declaration.
- [ ] Preserve raw text for diagnostics and future docs generation.
- [ ] Add conflict checks for duplicate declarations during parse.
- [ ] Add post-parse validation for cross-reference checks that require the
      whole Program.
- [ ] Add GUI declarations to compiler parse-only success coverage.
- [ ] Add GUI declarations to compiler JSON diagnostics if diagnostics are
      expanded to include source spans for validation errors.

### Compiler Codegen

- [ ] Detect `target windowsGui` with a validated `guiApplication` during
      no-entry codegen.
- [ ] Collect GUI event handler operation names before declaring user op
      functions.
- [x] Preserve `GuiSession` and `GuiEvent` handler inputs in the ABI.
- [ ] Declare all GUI event handler functions before emitting the GUI entry.
- [x] Compile non-handler helper operations as normal user ops.
- [ ] Emit a native GUI application config table.
- [ ] Emit one config record for the application title and icon.
- [ ] Emit one config record for each window.
- [ ] Emit one config record for each control.
- [ ] Emit one config record for each event edge.
- [x] Encode control kind in a stable runtime enum.
- [x] Encode event kind in a stable runtime enum.
- [ ] Emit handler function pointers in the event-edge table.
- [ ] Declare `ss_gui_application_run` in generated LLVM.
- [ ] Emit `main` or `WinMain` bridge code that calls
      `ss_gui_application_run`.
- [x] Decide whether the LLVM entry symbol remains `main` with `-mwindows`, or
      whether codegen emits a dedicated `WinMain` wrapper.
- [x] Add Windows subsystem linker support for GUI executables.
- [ ] Pass `-mwindows` through clang for Windows GUI builds when using the GNU
      driver mode.
- [ ] Pass the MSVC-linker equivalent `/SUBSYSTEM:WINDOWS` when clang is in
      MSVC driver mode if `-mwindows` is not sufficient.
- [x] Ensure console executables do not accidentally inherit GUI subsystem
      flags.
- [x] Link the GUI runtime source automatically for `target windowsGui`.
- [x] Link `user32` automatically on Windows GUI builds.
- [x] Link `gdi32` automatically on Windows GUI builds.
- [x] Link `comctl32` automatically if common controls are used.
- [ ] Link `shell32` only if shell icon or file-dialog helpers are added.
- [ ] Keep Linux/macOS builds parse-only or fail with a clear unsupported
      target diagnostic until non-Windows GUI backends exist.

### Native Win32 Runtime Adapter

- [x] Add `SemanticScript/runtime/native_win32_gui/`.
- [x] Add `sem_win32_gui_runtime.h`.
- [x] Add `sem_win32_gui_runtime.c`.
- [x] Add `CMakeLists.txt` for the native GUI runtime.
- [x] Define stable C ABI structs for application config.
- [x] Define stable C ABI structs for window config.
- [x] Define stable C ABI structs for control config.
- [x] Define stable C ABI structs for event-edge config.
- [x] Define a stable handler function pointer type:
      `int32_t (*)(SSGuiSession *, SSGuiEvent *)`.
- [x] Implement `ss_gui_application_run`.
- [x] Register a Win32 window class.
- [x] Create the main window from generated config.
- [x] Create child controls from generated config.
- [x] Implement `verticalStack` layout.
- [x] Implement `horizontalStack` layout.
- [x] Stub or explicitly reject `grid` layout until implemented.
- [x] Stub or explicitly reject `absolute` layout until implemented.
- [x] Handle `WM_COMMAND` for button clicks.
- [x] Handle text-box enter key dispatch.
- [x] Handle list-box selection changes.
- [x] Handle `WM_CLOSE` as `closeRequested`.
- [x] Handle `WM_SIZE` as `resized`.
- [x] Dispatch events to generated SemanticScript handler function pointers.
- [x] Create and pass a runtime-owned `SSGuiSession` token.
- [x] Create and pass a runtime-owned `SSGuiEvent` token.
- [x] Map declarative control IDs to `HWND` values in the session.
- [x] Implement `ss_gui_text_box_text`.
- [x] Implement `ss_gui_text_box_set_text`.
- [x] Implement `ss_gui_list_box_selected_index`.
- [x] Implement `ss_gui_list_box_append_item`.
- [x] Implement `ss_gui_list_box_clear`.
- [x] Implement `ss_gui_window_close`.
- [x] Implement `ss_gui_event_key_code`.
- [x] Implement `ss_gui_event_selected_index`.
- [x] Implement `ss_gui_event_window_width`.
- [x] Implement `ss_gui_event_window_height`.
- [x] Implement or defer `ss_gui_event_cancel_close`.
- [x] Define thread affinity: all GUI runtime calls must happen on the GUI
      thread unless future dispatch helpers are added.
- [x] Define memory ownership for strings returned from the runtime.
- [x] Define error codes for missing controls, wrong control kinds, allocation
      failures, and Win32 API failures.
- [x] Add runtime health demo that opens a window and exits cleanly.

### Native Win32 Modernization Pass

- [x] Keep the committed GUI surface as `entry console main` plus
      `standard.gui` `gui.*` calls; do not revive historical top-level
      `guiApplication` / `guiWindow` / `guiButton` rows for this pass.
- [x] Add a Windows GUI application manifest that requests Common Controls v6
      for compiler-generated `windowsGui` executables.
- [x] Initialize Common Controls before the Win32 GUI runtime registers or
      creates windows and controls.
- [x] Link `comctl32` automatically for `windowsGui` compiler builds and the
      native GUI runtime CMake target.
- [x] Apply the system message font to runtime-created controls instead of
      leaving them on the raw Win32 default font.
- [x] Scale default GUI padding, gaps, and control heights by the owning
      window DPI.
- [x] Apply best-effort DWM frame attributes for rounded corners and
      Mica-capable Windows 11 chrome when the host OS supports them.
- [x] Verify the Win32 GUI runtime build after modernization changes.
- [x] Verify `apps/desktop-window-smoke` still parses/checks after
      modernization changes.

### Native WinUI 3 Backend

- [x] Research WinUI 3 / Windows App SDK requirements from primary Microsoft
      documentation.
- [x] Record that WinUI 3 is delivered through Windows App SDK, not as a small
      plain-C GUI library.
- [x] Record that the native SemanticScript backend should be a C++/WinRT
      adapter exporting the existing `ss_gui_*` C ABI.
- [x] Record that unpackaged WinUI 3 apps require Windows App SDK runtime
      initialization through bootstrapper support such as
      `MddBootstrapInitialize2` / `MddBootstrapShutdown` unless package/project
      auto-initialization is used.
- [x] Record deployment prerequisites: Windows App SDK runtime deployment,
      Visual C++ Redistributable, WinUI/C++ tooling, and `.winmd` metadata.
- [x] Add `SemanticScript/runtime/native_winui3_gui/` as the backend scaffold.
- [x] Add a WinUI 3 backend contract header that reuses the existing shared
      GUI C ABI.
- [x] Add a WinUI 3 backend CMake scaffold that is intentionally disabled until
      Windows App SDK / C++/WinRT package integration exists.
- [x] Add build-tape support for selecting `guiBackend PROJECT win32|winui3`,
      defaulting to `win32` for compatibility.
- [x] Add compiler diagnostics that reject `guiBackend winui3` until the
      Windows App SDK build toolchain is available.
- [x] Reject C# / XAML app sidecars as the WinUI path; app UI source must stay
      in SemanticScript, and WinUI belongs behind the native backend adapter.
- [ ] Add a C++/WinRT implementation of `ss_gui_application_create`,
      `ss_gui_window_create`, control builders, event registration, and
      `ss_gui_application_run_builder`.
- [ ] Map `verticalStack` and `horizontalStack` to WinUI `StackPanel` layouts.
- [ ] Map labels, text boxes, buttons, check boxes, and list boxes to real
      WinUI controls instead of classic Win32 child windows.
- [ ] Implement WinUI event dispatch to `SSGuiHandler` callbacks on the UI
      thread.
- [ ] Implement text-box, list-box, label, event, and window runtime calls
      against WinUI objects.
- [ ] Decide packaged, packaged-with-external-location, or unpackaged deployment
      for SemanticScript WinUI executables.
- [ ] Teach `--emit-exe` or a companion build path to compile/link C++/WinRT
      with Windows App SDK packages.
- [ ] Make the existing Hello GUI smoke app run through `guiBackend winui3`
      using the unchanged `standard.gui` `gui.*` source API.
- [ ] Add CI-safe checks that can validate the WinUI backend is present without
      requiring an interactive desktop session.

### Standard Library Module

- [x] Add `SemanticScript/std/gui/main.sem`.
- [x] Relay `standard.gui` from `SemanticScript/std/module.sem`.
- [x] Add module metadata for `standard.gui`.
- [x] Add type aliases for `GuiSession`.
- [x] Add type aliases for `GuiEvent`.
- [x] Add type aliases for `GuiWindow`.
- [x] Add type aliases for `GuiControl` if adopted.
- [x] Add type aliases for every committed control handle type.
- [x] Add capability declarations for the committed GUI effect paths.
- [x] Add constants for GUI module version metadata.
- [x] Add documentation comments explaining that `gui.*` targets are
      compiler/runtime-owned intrinsics.
- [x] Add import example using `importModule gui standard.gui`.

### Linter And Editor Tooling

- [ ] Add GUI verbs to standalone linter arity tables.
- [x] Add GUI closed enum values to linter validation.
- [ ] Add diagnostics for missing `guiApplicationMainWindow`.
- [ ] Add diagnostics for controls missing `guiControlWindow`.
- [ ] Add diagnostics for invalid control-kind-specific rows.
- [ ] Add diagnostics for invalid event-kind/control-kind combinations.
- [ ] Add diagnostics for missing or malformed GUI handler ABI inputs.
- [ ] Add diagnostics for missing GUI handler output contract.
- [x] Add diagnostics for GUI runtime calls missing required `session` args.
- [x] Add `gui.*` runtime call signatures to semlint's built-in call table.
- [x] Add `gui.*` effect requirements to semlint's effect table.
- [ ] Add VS Code grammar highlighting for GUI declaration verbs.
- [ ] Add VS Code hover descriptions for GUI declaration verbs.
- [ ] Add VS Code document symbol grouping for GUI applications, windows,
      controls, and event edges.
- [ ] Add snippets only after the surface stabilizes.

### Tests And Samples

- [ ] Add parser tests for the minimum GUI application shape.
- [ ] Add parser tests for every application row.
- [ ] Add parser tests for every window row.
- [ ] Add parser tests for every control declarator row.
- [ ] Add parser tests for every generic control row.
- [ ] Add parser tests for every kind-specific control row.
- [ ] Add parse-failure tests for duplicate GUI applications.
- [ ] Add parse-failure tests for duplicate controls.
- [ ] Add validation tests for missing main window.
- [ ] Add validation tests for missing control window.
- [ ] Add validation tests for invalid event/control combinations.
- [ ] Add validation tests for malformed GUI handler ABI.
- [ ] Add compiler IR tests proving GUI handler params are preserved.
- [ ] Add compiler IR tests proving `ss_gui_application_run` is declared.
- [ ] Add compiler IR tests proving GUI config tables are emitted.
- [ ] Add linker tests proving Windows GUI builds include subsystem flags.
- [ ] Add linker tests proving `user32` and `gdi32` link args are added.
- [x] Add a smoke sample under `apps/desktop-window-smoke`.
- [ ] Add a future TaskForge GUI sample only after the hello sample
      proves the base runtime.
- [ ] Add a runtime health test that opens and closes a window on Windows CI
      if the runner supports desktop interaction.
- [ ] Add a headless compile-only fallback test for CI environments that
      cannot open desktop windows.
- [x] Add docs explaining how to run GUI smoke tests locally on Windows.

### Documentation And Release Scope

- [ ] Add a GUI language doc under `docs/language/`.
- [ ] Add a native GUI runtime doc under `docs/toolchain/` or
      `SemanticScript/runtime/native_win32_gui/README.md`.
- [ ] Update `README.md` support matrix once the surface is implemented or
      explicitly preview.
- [ ] Update `docs/README.md` with links to GUI language/runtime docs.
- [ ] Update `docs/agents.md` with compact GUI syntax guidance.
- [ ] Update `docs/optimization-guide.md` with GUI effect/capability examples.
- [ ] Decide whether declarative Windows GUI support is in 1.0 scope,
      post-1.0 preview scope, or experimental-only scope.
- [ ] Mark every GUI row in `SYNTAX.md` with honest implementation status.
- [ ] Add migration guidance if early names change before the committed
      syntax freezes.

## P1 - Full 1.0 Product Surface Gap Backlog

This section tracks the larger "complete product surface" gaps. These are not
all blockers for the scoped 1.0 release unless the release definition changes
from "honest scoped compiler/tooling release" to "complete language/runtime
product".

### Compiler And Language Strictness

- [x] Decide whether a SemanticScript-written compiler is a 1.0 requirement.
  - [x] Keep documenting `semsc.py` as the production 1.0 compiler.
  - [x] Remove the unmaintained SemanticScript-written compiler path from the
        active tree.
- [x] Replace unknown/missing operation output fallback-to-`i32` with a stricter
      diagnostic for release-mode builds, or document the fallback as a scoped
      compiler compatibility behavior.
- [x] Add module namespace enforcement beyond import inlining and metadata.
  - [x] Validate `module NAME` as a dotted namespace.
  - [x] Reject conflicting module declarations in one resolved source.
  - [x] Detect duplicate operation names across imported modules.
  - [x] Detect ambiguous unqualified references when imports expose the same
        symbol.
  - [x] Define whether `importModule X as Y` creates a real namespace boundary.
- [x] Add runtime capability/authority enforcement, or explicitly keep
      capability enforcement as linter/spec-only for 1.0.
  - [x] Add strict lint/compiler diagnostics for missing capability or inline
        authority coverage.
  - [x] Document runtime authority enforcement as out of scope for scoped 1.0.
  - [x] Decide how capability tokens are represented in generated binaries.
  - [x] Decide whether authority failures are compile-time errors, runtime
        traps, or typed runtime errors.
  - [x] Add tests proving unauthorized runtime effects cannot execute if runtime
        enforcement is in scope.
- [ ] Audit refined syntax rows that are parser/linter-only and ensure each one
      is marked metadata, synchronous fallback, partial, or implemented.

### Native HTTP / Webserver Completeness

- [x] Add request body APIs.
  - [x] Add source-level call targets for reading request body text and length.
  - [x] Preserve body lifetime and size limits in the native adapter.
  - [x] Add POST tests that inspect actual body content.
- [x] Add request header APIs.
  - [x] Add source-level call targets for header lookup.
  - [x] Preserve header names and values in the native adapter.
  - [x] Add case-insensitive header lookup tests.
- [x] Add response header APIs.
  - [x] Add source-level call targets for setting headers.
  - [x] Add tests for `Allow`, `Content-Type`, and custom middleware headers.
- [x] Add query parameter APIs.
  - [x] Preserve raw query string while still matching routes by path.
  - [x] Add source-level call target for simple query parameter lookup.
  - [x] Add decoding/validation rules for repeated and missing params.
- [x] Add path parameter routing such as `/todos/:todoId`.
  - [x] Define route precedence between exact routes and parameter routes.
  - [x] Add tests for path parameter extraction.
  - [x] Add tests for invalid parameter routes.
- [x] Execute `routeMiddleware` metadata in the native runtime.
  - [x] Define one path-scoped middleware slot before the route handler.
  - [x] Define non-zero middleware status as a request failure.
  - [x] Add tests proving middleware can inspect request state and set headers.
- [x] Keep `routeTimeout` metadata-only for the scoped HTTP/1.1 runtime.
  - [x] Parse `routeTimeout` rows as route metadata.
  - [x] Enforce route-timeout coverage/opt-out drift through semlint instead
        of unsafe blocking-handler preemption.
- [x] Add persistent web app state/storage helpers.
  - [x] Define safe mutable process state for request handlers using
        process-lifetime module state.
  - [x] Add tests for sequential request state changes.
- [x] Add first-class HTML/SSX server template syntax.
  - [x] Add `html template NAME` declarations for named server-rendered HTML
        values.
  - [x] Infer template holes from bare names and dotted record-field paths in
        the template body; hydrate calls provide those root names with normal
        `argument` rows.
  - [x] Add `html body template TEMPLATE` syntax islands that parse following indented
        HTML/SSX lines until the next column-0 SemanticScript line.
  - [x] Keep `html body template` as the only indentation-sensitive syntax exception;
        normal SemanticScript remains flat and line-oriented.
  - [x] Allow JSX-like tags, attributes, fragments, and dynamic holes inside
        `html body template` only.
  - [x] Restrict dynamic holes to hydrate-call values inferred from the
        template body.
  - [x] Reject arbitrary calls, mutation, request reads, and hidden state reads
        inside HTML dynamic holes.
  - [x] Type-check dynamic holes by core HTML sink context: text nodes, quoted
        attributes, class values, URL attributes, fragments, and full documents.
  - [x] Escape `HtmlText` during hydration for text and attribute sinks.
  - [x] Define first-class HTML trust types such as `HtmlText`, `HtmlClass`,
        `SafeUrl`, `HtmlFragment`, `HtmlTrustedFragment`, and `HtmlDocument`.
  - [x] Lower template hydration through generated targets such as
        `html.hydrate.TodoPageTemplate`.
  - [x] Add `standard.html` as the official standard-library import module for
        first-class HTML templates.
  - [x] Resolve `standard.html` through `SemanticScript/std/html/main.sem`.
  - [x] Use the canonical `importModule html standard.html` form in the demo app.
  - [x] Add `standard.http` and `standard.json` metadata modules for the
        compiler-owned `http.*` and `json.*` intrinsic namespaces.
  - [x] Resolve `standard.http` and `standard.json` through
        `SemanticScript/std/http/main.sem` and `SemanticScript/std/json/main.sem`.
  - [x] Add `<module>/main.sem` canonical entries for every C-derived stdlib module.
  - [x] Add `SemanticScript/std/module.sem` as the top-level `standard` relay.
  - [x] Add `http.responseHtml` as the explicit HTML response writer with
        `text/html; charset=utf-8` content type behavior.
  - [x] Add compiler diagnostics for malformed HTML islands, unknown
        unknown HTML holes, and mismatched component/template arguments.
  - [x] Add compiler diagnostics for unsafe dynamic HTML sinks covered by the
        core context checker.
  - [x] Add formatter and VS Code grammar support for `html template`,
        `html body template`, inferred holes, and embedded SSX syntax.
  - [x] Add docs explaining why HTML symbols are a narrow grammar-island
        exception to the normal no-brace/no-angle/no-indentation rules.
  - [x] Add webserver tests proving hydrated HTML responses preserve escaping,
        content type, content length, and route-handler failure behavior.
- [x] Harden HTML/SSX server template sink analysis beyond the current narrow
      parser.
  - [x] Extend HTML sink-context checks to boolean attributes and a whole-island
        tag/attribute scanner instead of the prior narrow context scan.
  - [x] Add compiler diagnostics for unsafe dynamic HTML sinks covered by the
        hardened tag/attribute scanner.
  - [x] Add semlint checks proving untrusted request/query/header/body data
        cannot flow into HTML without an explicit escape or trust conversion.
- [x] Add static-file serving helper.
  - [x] Define root directory safety and path traversal behavior.
  - [x] Add MIME/content-length tests.

### Data, Codec, And Collection Runtime

- [x] (superseded) Implement real JSON codec runtime for records.
  - All JSON record-codec, encode/decode, and runtime work — including the
    `json.encode.RecordTypeName` / `json.decode.RecordTypeName` lowerings,
    required-field/unknown-field/limit enforcement, and the malformed/missing/
    escaping test matrix — is now owned end-to-end by the
    `### Native JSON CRUD API And jsonBody Literal` section below. Do not add
    new JSON-handling bullets here; extend that section instead.
- [x] Implement generic `codec` runtime or keep it as explicit metadata-only
      syntax for 1.0.
- [ ] Implement typed collection runtime for `TaskList.append`, `TaskMap.get`,
      and related collection operations.
  - [ ] Define allocation ownership for list/map storage.
  - [ ] Define bounds and missing-key behavior.
  - [ ] Add tests for append/get/update failure paths.
- [ ] Replace dotted-target zero-result fallback for partial collection/codec
      calls with diagnostics when a source claims runtime behavior.
  - [x] Add semlint diagnostics for record JSON codec, generic codec, and
        typed collection runtime fallbacks.

### Native JSON CRUD API And jsonBody Literal

This section turns the JSON refinement design into implementation-sized tasks.
The goal is a native CRUD surface over a mutable parsed JSON tree, a column-0
`jsonBody NAME` indented-island literal that lowers to a compile-time-validated
constant, and typed `json.stringify.<TypeName>` / `json.parse.<TypeName>` entry
points that wrap the existing builder/finder runtime so handlers stop hand-rolling
JSON through `c.snprintf` format templates. Honor the `feedback_verify_impld_claims`
rule: nothing here promotes a SYNTAX.md row to `Impl'd` without a feature_test that
would fail under a no-op lowering.

#### standard.json Types, Error, And Enum

- [x] Add `type JsonDocument COpaqueMemoryAddress` to
      `SemanticScript/std/json/main.sem` with `exportType standard.json JsonDocument`.
  - [x] Add a `typeInvariant JsonDocument` stating the handle is created by
        `json.createDocument` / `json.createEmptyDocument` and freed via
        `defer json.destroyDocument`; backing buffer grows up to `capacityBytes`
        and surfaces `JsonAccessError.CapacityExceeded` past that bound.
- [x] Add `type JsonCursor CSignedInt64` with `exportType standard.json JsonCursor`.
  - [x] Add a `typeInvariant JsonCursor` documenting the stable-index contract
        and the structural-mutation invalidation list
        (`removeObjectField`, `removeArrayElementAt`, `clearObject`, `clearArray`,
        `setObjectFieldObject`, `setObjectFieldArray`,
        `insertArrayElement*`, `replaceArrayElement*` when the new value is a
        container) — cross-reference SYNTAX.md:446 sqlite column-pointer lifetime.
- [x] Add `type JsonPath CNullTerminatedByteString` with
      `exportType standard.json JsonPath`.
  - [x] Add a `typeInvariant JsonPath` pinning the grammar: `.fieldName` object
        steps, `[index]` array steps, anything else returns
        `JsonAccessError.MalformedPath`.
- [x] Add the `JsonValueKind` enum in `SemanticScript/std/json/main.sem`.
  - [x] Declare `enum JsonValueKind repr CSignedInt32`.
  - [x] Declare cases `objectJsonValueKind 0`, `arrayJsonValueKind 1`,
        `stringJsonValueKind 2`, `integerJsonValueKind 3`,
        `doubleJsonValueKind 4`, `booleanJsonValueKind 5`,
        `nullJsonValueKind 6` using the descriptive-suffix convention.
  - [x] Auto-register the enum in `SemanticScript/compiler/semsc.py`'s built-in
        enum table the same way `SqliteColumnType` is registered.
- [x] Add the `JsonAccessError` declaration in `SemanticScript/std/json/main.sem`.
  - [x] Declare `error JsonAccessError`.
  - [x] Declare `errorCase JsonAccessError PathNotFound CSignedInt32`.
  - [x] Declare `errorCase JsonAccessError WrongType CSignedInt32`.
  - [x] Declare `errorCase JsonAccessError IndexOutOfRange CSignedInt32`.
  - [x] Declare `errorCase JsonAccessError FieldNameTooLong CSignedInt32`.
  - [x] Declare `errorCase JsonAccessError DocumentNotMutable CSignedInt32`.
  - [x] Declare `errorCase JsonAccessError CapacityExceeded CSignedInt32`.
  - [x] Declare `errorCase JsonAccessError MalformedPath CSignedInt32`.
  - [x] Declare `errorCase JsonAccessError ScratchTooSmall CSignedInt32`.
  - [x] Add `exportError standard.json JsonAccessError`.
- [x] Add `JsonEncodeError` and `JsonDecodeError` declarations in the same file.
  - [x] `JsonEncodeError` cases: `CapacityExceeded`, `WrongType`,
        `OutputBufferTooSmall`, each carrying `CSignedInt32`.
  - [x] `JsonDecodeError` cases: `UnexpectedToken`, `MissingRequired`,
        `WrongType`, `Oversize`, `Truncated`, `EscapeMalformed`,
        each carrying `CSignedInt32`.

#### Native JSON Document Runtime

- [x] Add the `SSJsonDocument` opaque struct to
      `SemanticScript/runtime/native_json/sem_json_runtime.h`.
  - [x] Hold a growable node table indexed by `int64_t` cursors so cursors
        survive non-structural mutations.
  - [x] Hold a capacity-bounded text arena for owned string values.
  - [x] Track `capacity_bytes` / `bytes_used` for `CapacityExceeded` checks.
- [x] Add `SSJsonNodeKind` matching `JsonValueKind` integer values exactly so
      the lowering can forward `cursor_kind` without a translation table.
- [x] Add `SS_JSON_OK = 0` and one `SS_JSON_ERR_*` constant per
      `JsonAccessError` case in `sem_json_runtime.h`; map 1:1 to the error
      case ordinals.
- [x] Implement `ss_json_document_create_from_text(const char *json_text,
      int64_t capacity_bytes, SSJsonDocument **out)` in
      `SemanticScript/runtime/native_json/sem_json_runtime.c`.
  - [ ] Reuse the RFC-8259-aware tokenizer that backs the existing finder API.
  - [x] Reject malformed input with the matching `SS_JSON_ERR_*` code; never
        leak a half-built document on failure.
- [x] Implement `ss_json_document_create_empty(int64_t capacity_bytes,
      int32_t root_kind, SSJsonDocument **out)` accepting only
      `objectJsonValueKind` / `arrayJsonValueKind` as roots.
- [x] Implement `ss_json_document_destroy(SSJsonDocument *document)` freeing
      the node table and arena; tolerate NULL.
- [x] Implement `ss_json_document_serialize(SSJsonDocument *document,
      char *scratch, int64_t scratch_capacity, const char **out)`.
  - [x] Reuse the builder's RFC 8259 `\uXXXX` escape path so output matches
        the SYNTAX.md:448 escape policy exactly.
  - [x] Return `SS_JSON_ERR_SCRATCH_TOO_SMALL` when output would overflow
        the scratch; never truncate silently.
- [x] Implement `ss_json_document_length(SSJsonDocument *document)` returning
      the byte count the next serialize will emit, mirroring
      `json.builderLength`.
- [x] Implement `ss_json_document_root(SSJsonDocument *document)` returning
      cursor 0 (always defined).
- [x] Implement `ss_json_navigate_object_field(SSJsonDocument *document,
      int64_t cursor, const char *field_name, int64_t *out)`.
  - [x] Return `SS_JSON_ERR_WRONG_TYPE` when the cursor's node is not an
        object.
  - [x] Return `SS_JSON_ERR_PATH_NOT_FOUND` when the field is absent.
- [x] Implement `ss_json_navigate_array_element(SSJsonDocument *document,
      int64_t cursor, int64_t index, int64_t *out)` with
      `SS_JSON_ERR_INDEX_OUT_OF_RANGE` outside `[0, array_length)` and
      `SS_JSON_ERR_WRONG_TYPE` for non-arrays.
- [x] Implement `ss_json_cursor_parent(SSJsonDocument *document,
      int64_t cursor, int64_t *out)` returning `SS_JSON_ERR_PATH_NOT_FOUND`
      for the root.
- [x] Implement `ss_json_cursor_at_path(SSJsonDocument *document,
      const char *path, int64_t *out)`.
  - [x] Parse segments left-to-right: `.fieldName` for object steps,
        `[index]` for array steps; reject anything else with
        `SS_JSON_ERR_MALFORMED_PATH`.
  - [x] Reuse the per-step navigators internally so error codes from a
        mid-path failure match what the user would see if they walked the
        cursor manually.
- [x] Implement `ss_json_cursor_kind` returning the `JsonValueKind` integer
      directly.
- [x] Implement `ss_json_cursor_is_null` returning 1 for `null` and 0 for any
      other kind (no error path).
- [x] Implement `ss_json_cursor_int64(document, cursor, missing_default,
      out)` matching the `findInt64` `missingDefault` contract from
      SYNTAX.md:449 — total function, no error code.
- [x] Implement `ss_json_cursor_double` and `ss_json_cursor_bool` with the
      same `missing_default` propagation.
- [x] Implement `ss_json_cursor_string(document, cursor, scratch,
      scratch_capacity, out)`.
  - [x] Un-escape standard JSON escapes plus `\uXXXX` for BMP code points
        into the scratch buffer (reuse the `findString` algorithm).
  - [x] Return `SS_JSON_ERR_WRONG_TYPE` for non-strings,
        `SS_JSON_ERR_SCRATCH_TOO_SMALL` when the unescaped value plus NUL
        does not fit.
- [x] Implement `ss_json_cursor_array_length` /
      `ss_json_cursor_object_field_count` with `SS_JSON_ERR_WRONG_TYPE` on
      kind mismatch.
- [x] Implement `ss_json_cursor_object_field_name_at(document, cursor, index,
      scratch, scratch_capacity, out)` copying the field name into scratch.
- [x] Implement `ss_json_cursor_object_field_value_at(document, cursor,
      index, out)` returning the child cursor.
- [x] Implement `ss_json_set_object_field_string`,
      `ss_json_set_object_field_int64`, `ss_json_set_object_field_double`,
      `ss_json_set_object_field_bool`, `ss_json_set_object_field_null`.
  - [x] Overwrite an existing field in place when the field name matches.
  - [x] Append a new field record when the name is absent.
  - [x] Return `SS_JSON_ERR_WRONG_TYPE` on a non-object cursor,
        `SS_JSON_ERR_FIELD_NAME_TOO_LONG` past the per-document field-name
        bound, `SS_JSON_ERR_CAPACITY_EXCEEDED` when the arena cannot fit
        the new bytes within `capacity_bytes`.
- [x] Implement `ss_json_set_object_field_object` /
      `ss_json_set_object_field_array` returning the new child cursor.
- [x] Implement `ss_json_set_object_field_json_text` parsing the supplied
      sub-document, type-validating it, and grafting it under the named
      field.
- [x] Implement `ss_json_append_array_element_*` for string, int64, double,
      bool, null, object, array, and json_text variants; append at
      `array_length`; return the new element cursor for containers.
- [x] Implement `ss_json_insert_array_element_*` for the same variants;
      shift later elements one slot; reject `index > array_length` with
      `SS_JSON_ERR_INDEX_OUT_OF_RANGE`.
- [x] Implement `ss_json_replace_array_element_*` overwriting one slot in
      place; invalidate descendant cursors of the replaced slot when the
      new value is a container.
- [x] Implement `ss_json_remove_object_field` returning `0` when removed and
      `1` when the field was absent (matches the design's documented
      semantics).
- [x] Implement `ss_json_remove_array_element_at` shifting later elements
      down one slot.
- [x] Implement `ss_json_clear_object` and `ss_json_clear_array` removing
      every field/element while preserving the cursor's kind.
- [x] Document the cursor invalidation contract in `sem_json_runtime.h`
      next to each mutator so the C-side comments match the SemanticScript
      `typeInvariant JsonCursor`.
- [x] Extend `_native_json_link_inputs` in
      `SemanticScript/compiler/semsc.py` to pull in `sem_json_runtime.c`
      whenever any `json.*` document call appears (the existing builder
      trigger already covers this, but document the additional symbols).

#### Compiler Lowering (semsc.py)

- [x] Register `json.createDocument` in the `json.*` dispatch table in
      `SemanticScript/compiler/semsc.py`.
  - [x] Allocate the out-pointer slot in the function's entry block,
        pre-initialized to NULL, exactly like `sqlite.openDatabase`.
  - [x] Stash the slot on `call["handle_slot"]` so the matching
        `defer json.destroyDocument` re-loads the handle at every exit.
  - [x] Populate `call["result"]` / `call["error_value"]` /
        `call["error_cond"]` so `bind ok` / `bind error` / `branch error`
        fall through unchanged.
- [x] Register `json.createEmptyDocument` with the same handle-slot
      machinery.
- [x] Add `json.destroyDocument` to `_NATIVE_DEFER_DISPATCH` alongside
      `json.destroyBuilder` so `defer json.destroyDocument userDocument`
      compiles to a real call at every cleanup site, including failure
      labels.
- [x] Register `json.serializeDocument` returning
      `Result JsonText JsonAccessError`.
- [x] Register `json.documentLength` returning a plain `CSignedInt64`.
- [x] Register `json.documentRoot` returning a plain `JsonCursor` (root is
      always defined, no error path).
- [x] Register `json.objectFieldAt`, `json.arrayElementAt`,
      `json.cursorParent`, `json.cursorAtPath` returning
      `Result JsonCursor JsonAccessError`.
- [x] Register the cursor readers (`cursorKind`, `cursorIsNull`,
      `cursorInt64`, `cursorDouble`, `cursorBool`, `cursorString`,
      `cursorArrayLength`, `cursorObjectFieldCount`,
      `cursorObjectFieldNameAt`, `cursorObjectFieldValueAt`) with the
      bind shape documented in the design table.
- [x] Register the mutator calls (`setObjectField*`, `appendArrayElement*`,
      `insertArrayElement*`, `replaceArrayElement*`, `removeObjectField`,
      `removeArrayElementAt`, `clearObject`, `clearArray`) returning
      `CSignedInt32` status with `ignore ok` + `bind error CSignedInt32` +
      `branch error`, matching the existing `json.field*` shape.
- [x] Add `json.document.tree` to the effect-axis validator so
      `effect OP read json.document.tree` and
      `effect OP write json.document.tree` parse and route through semlint
      as a real axis, parallel to `gui.control.textBox.text`.
- [x] Resolve `useCapability OP <name>` for the two heap capabilities the
      design uses (`jsonDocumentAllocateCapability heap allocate`,
      `jsonDocumentFreeCapability heap free`) without introducing a new
      capability bucket — they remain user-named heap capabilities.

#### jsonBody Indented-Island Literal

- [x] Add parser support for `jsonBody NAME` at column 0 in
      `SemanticScript/compiler/semsc.py`.
  - [x] Recognize indented lines that follow as one raw-text island,
        terminated at the next non-empty column-0 SemanticScript line — the
        same termination rule used by `html body template` (SYNTAX.md).
  - [x] Capture the island bytes verbatim, preserving inner whitespace
        inside JSON string literals.
  - [x] Bind the island to the most recently declared
        `storage local|module immutable NAME TYPE` row that has no inline
        value; reject orphan `jsonBody NAME` rows with a parse diagnostic.
  - [x] Reject `jsonBody` rows whose target storage type is neither
        `JsonText` nor a declared `record` type with a parse diagnostic
        that names the offending type.
- [x] Validate the island as JSON at compile time.
  - [x] Parse with a strict RFC 8259 tokenizer that rejects trailing
        commas, comments, unquoted keys, and non-UTF-8 bytes.
  - [x] Emit a diagnostic citing the column-0 island name and the in-island
        line+column of the offending byte.
- [ ] Type-check the parsed literal against the declared storage type.
  - [x] `JsonText`: store the canonicalized JSON bytes as a
        `CNullTerminatedByteString` constant.
  - [x] `record`: enforce every required field is present, every type
        matches, no unknown keys are present, and nested record literals
        recurse through the same rule.
  - [x] Honor `recordFieldJsonName` overrides when mapping JSON keys to
        record fields.
  - [x] Honor `recordFieldJsonOmitWhen empty|null|false|zero` so omitted
        fields default to the configured policy without runtime branching.
  - [ ] Emit one diagnostic per failure naming the offending field, the
        expected type, and the actual JSON kind.
- [ ] Lower the typed literal to a constant in the emitted module.
  - [x] `JsonText`: emit a static null-terminated byte array exactly like
        an inline `"..."` storage value.
  - [x] Record-typed: lower to the compiler's flattened record constant
        representation so `fieldGet` and record stringify read the literal
        without a runtime parse.
  - [ ] Record-typed: emit a typed struct constant whose layout matches
        the record's emitted struct so no runtime parse runs.
- [x] Update `SemanticScript/linter/semlint.py` to walk `jsonBody` islands
      and surface the same parse/type diagnostics that `semsc.py` emits,
      so `ascc --lint --parse-only` reports them without a full compile.
- [x] Update `vscode-semanticscript/syntaxes/semanticscript.tm-language.json`
      to highlight the `jsonBody NAME` row and JSON-token the island lines.
- [x] Update `vscode-semanticscript/extension.js` symbol/hover support to
      treat `jsonBody NAME` as a value-producing declaration that resolves
      to the prior storage row.
- [x] Add a semfmt pass for `jsonBody` islands so formatting preserves
      indentation, mirroring the `html body template` exception flagged in
      `feedback_semfmt_strips_htmlbody`.
  - [x] Add a regression test that runs semfmt on a file containing
        `jsonBody` and asserts the JSON island still parses afterward.

#### json.stringify.<TypeName> And json.parse.<TypeName>

- [x] Add `json.stringify.<TypeName>` dispatch in
      `SemanticScript/compiler/semsc.py`.
  - [x] For primitive `TypeName` (I64, Bool, F64, String,
        width-specific C ABI integers) reuse the existing
        `json.encode.<Primitive>` lowering at SYNTAX.md:428.
  - [x] For record `TypeName` generate a field-by-field encoder that walks
        `recordField` + `recordFieldJsonName` + `recordFieldJsonOmitWhen`
        and emits native document mutator calls; promotes the SYNTAX.md:430
        Partial row toward `Impl'd`.
  - [x] Map native document statuses from record stringify onto the
        `JsonEncodeError` case ordinals before exposing `bind error`.
  - [x] For `JsonText` perform an identity copy through scratch with a
        length check so pre-built bodies can flow through a typed
        pipeline without escaping twice.
  - [x] Surface `bind ok JsonText` / `bind error JsonEncodeError` at the
        call site.
- [x] Add `json.parse.<TypeName>` dispatch in `semsc.py`.
  - [x] Primitive: reuse `json.decode.<Primitive>` at SYNTAX.md:429.
  - [x] Primitive aliases report call success through the typed error slot
        instead of treating the decoded primitive payload as an error code.
  - [x] Record: generate a field-by-field decoder that validates required
        fields, type-checks each field, and applies `omit-when` defaults.
  - [x] Map missing/wrong-field record parse failures onto the
        `JsonDecodeError` case ordinals before exposing `bind error`.
  - [x] `JsonText`: validate JSON syntax and pass bytes through unchanged.
- [x] Add `recordFieldJsonOmitWhen` parser support if not already present;
      accept `empty`, `null`, `false`, `zero` policies.
- [x] Update SYNTAX.md:428 / :429 / :430 rows to cross-reference
      `json.stringify.<TypeName>` and `json.parse.<TypeName>` as the
      recommended high-level entry points.

#### semlint Rules

- [x] Add `SS3620 unguardedJsonAccess` to `SemanticScript/linter/semlint.py`.
  - [x] Flag any operation that consumes a `bind ok JsonCursor` from a
        fallible navigator without a `branch error` between the `run`
        and the first use of the cursor.
  - [x] Treat `json.documentRoot` as exempt (cannot fail).
  - [x] Add unit coverage in
        `SemanticScript/linter/test_semlint.py`.
- [x] Add `SS3621 staleJsonCursor`.
  - [x] Track `JsonCursor` bindings across the operation body and warn
        when a cursor is read after a structural mutator on its document
        (full mutator list per the `typeInvariant JsonCursor` row).
  - [x] Surface a fix-it hint suggesting a fresh `objectFieldAt` /
        `arrayElementAt` / `cursorAtPath` call.
  - [x] Add unit coverage with each structural-mutator case.
- [x] Add `SS3622 malformedJsonPath`.
  - [x] Parse every `JsonPath` literal at lint time and flag unmatched
        `[`, empty `.` segments, unescaped dots inside field names, and
        non-numeric array indices.
  - [x] Block compilation when the literal is statically malformed so the
        diagnostic fires before the runtime sees the path.
- [x] Add `SS3623 unescapedJsonStringInterpolation`.
  - [x] Flag `c.snprintf` format strings that contain `%s` inside JSON
        string content (heuristic: surrounded by `"` and embedded in a
        literal that includes `{` / `:` / `,`).
  - [x] Recommend `json.stringify.<TypeName>` or
        `json.serializeDocument` as the safe replacement.
- [x] Re-run `python SemanticScript/linter/test_semlint.py` after each new
      rule to confirm zero regressions.

#### SYNTAX.md Rows

- [x] Add a row for the new `standard.json` types
      (`JsonDocument`, `JsonCursor`, `JsonPath`) mirroring SYNTAX.md:447.
- [x] Add a row for `JsonValueKind` next to `SqliteColumnType`.
- [x] Add a row for `JsonAccessError`, `JsonEncodeError`, `JsonDecodeError`.
- [x] Add a row for the document lifecycle calls (`json.createDocument`,
      `json.createEmptyDocument`, `json.destroyDocument`,
      `json.serializeDocument`, `json.documentLength`,
      `json.documentRoot`).
- [x] Add a row for the navigation calls (`json.objectFieldAt`,
      `json.arrayElementAt`, `json.cursorParent`, `json.cursorAtPath`).
- [x] Add a row grouping the cursor readers.
- [x] Add a row grouping the object mutators.
- [x] Add a row grouping the array mutators.
- [x] Add a row grouping the delete calls.
- [x] Add a row for `jsonBody NAME` describing the indented-island contract,
      noting it as the second indentation-sensitive exception after
      `html body template`.
- [x] Add a row for `json.stringify.<TypeName>` and `json.parse.<TypeName>`
      as the high-level typed entry points.
- [ ] Promote SYNTAX.md:430 from `Partial` to `Impl'd` once the record
      codec generator is live; verify with a feature_test per
      `feedback_verify_impld_claims`.

#### Feature Tests

- [x] Add `SemanticScript/tests/feature/<NNN>_json_document_round_trip.sscript`
      exercising `createDocument` → cursor walk → mutator →
      `serializeDocument`; assert the recovered text equals an expected
      literal, deep-audit pattern from `json_runtime_smoke.sscript`.
- [x] Add a feature test for `createEmptyDocument` that builds a tree
      from scratch and serializes it; assert byte-for-byte equality with
      a known literal.
- [ ] Add one feature test per navigator covering both success and the
      typed-error paths (`PathNotFound`, `WrongType`, `IndexOutOfRange`).
- [ ] Add one feature test per cursor reader, including the
      `missingDefault` propagation path for numeric/bool readers and the
      `ScratchTooSmall` path for `cursorString`.
- [ ] Add one feature test per mutator asserting the post-mutation
      serialization equals an expected literal, then re-reading the
      mutated field to confirm round-trip.
- [ ] Add a feature test for `clearObject` / `clearArray` confirming kind
      preservation and zero length post-clear.
- [ ] Add a feature test for `JsonAccessError.CapacityExceeded` that
      intentionally undersizes the document and asserts the typed error
      reaches a `return error`.
- [ ] Add an adversarial test parallel to
      `json_runtime_adversarial.sscript` covering deep nesting up to the
      documented bound, control bytes in strings, full RFC 8259 escape
      coverage, and pathological `JsonPath` inputs.
- [ ] Add a `jsonBody` feature test with four cases:
  - [ ] One literal bound to `JsonText`.
  - [ ] One literal bound to a record covering every primitive field type.
  - [ ] One literal that intentionally fails record type-check; assert
        the diagnostic names the offending field.
  - [ ] One literal that intentionally fails JSON syntax; assert the
        diagnostic cites the in-island offset.
- [ ] Add `json.stringify` / `json.parse` round-trip tests, one per
      primitive and one per record codec; each deep-audit asserts the
      lowered behavior cannot be a no-op.
  - [x] `json.stringify.I64` feature coverage emits and prints the JSON
        decimal text through the high-level alias.
  - [x] `json.stringify.Bool` feature coverage emits and prints both JSON
        boolean tokens through the high-level alias.
  - [x] `json.stringify.String` feature coverage emits and prints quoted
        ASCII JSON string text through the high-level alias.
  - [x] `json.parse.I64` feature coverage parses a literal JSON integer
        through the high-level alias.
  - [x] `json.parse.Bool` feature coverage parses literal `true` and
        `false` tokens and drives observable control flow.
  - [x] Add a regression feature test for parsing a negative integer through
        `json.parse.I64` so `branch error` cannot mistake the decoded value
        for an error status.
- [x] Confirm JSON compiler feature cases are covered by the maintained
      reference-compiler tests with zero expected-failure metadata.

#### Documentation

- [x] Update `docs/reference/verb-index.md` with every new `json.*` verb.
- [x] Update `docs/language/operations-dataflow.md` with the end-to-end
      CRUD example matching the design's `renameFirstTodoHandler` flow.
- [x] Add `docs/language/json-crud.md` describing the document lifecycle,
      cursor invalidation contract, path grammar, and stringify/parse
      typed entry points; link from `docs/language/README.md`.
- [x] Update `CHANGELOG.md` with one entry per landed batch
      (types, runtime, lowering, jsonBody, stringify/parse, semlint).
- [x] Update `SemanticScript/std/README.md` JSON section to reference the
      new types/errors/enum and the high-level entry points.

#### App Migration (taskforge-web)

- [x] Replace the static success bodies in `apps/taskforge-web/main.sem`
      (`healthBodyJson`, `versionBodyJson`, `logoutResponseBody`,
      `deleteOkBody`, `completeOkBody`, `uncompleteOkBody`) with
      `storage local immutable NAME JsonText` rows backed by
      `jsonBody NAME` islands.
- [ ] Replace `userResponseFormat`, `meResponseFormat`,
      `loginResponseFormat`, `createResponseFormat`, and `listRowFormat`
      with record-typed codecs invoked via `json.stringify.<TypeName>`.
- [x] Replace the streaming list serializer at
      `apps/taskforge-web/main.sem:2200-2380` with a single
      `json.createEmptyDocument` + `appendArrayElementObject` loop +
      `json.serializeDocument` pipeline so the unescaped `%s` title bug
      in `listRowFormat` goes away by construction.
- [ ] Replace the per-field `bodyMissing` / `usernameMissing` /
      `passwordMissing` error responses with one `JsonDecodeError` switch
      in front of `json.parse.LoginRequest` and
      `json.parse.RegisterRequest`.
- [x] Run `python apps/taskforge-web/scripts/test_taskforge_web.py` after
      each migration step to confirm response shapes remain byte-stable.

#### Removal Of Pre-CRUD JSON Surfaces

Once the new surface lands the existing user-facing JSON calls become dead
weight and the project must end with exactly one way to handle JSON. The
underlying C runtime helpers can stay as internal primitives that the new
lowerings reuse — every removal below is at the **language surface**, not
in `sem_json_runtime.c`. Each removal must be paired with equivalent
coverage under the new surface so this is a strict refactor with zero
behavior regressions.

- [ ] Remove the user-facing builder calls from the `json.*` dispatch table
      in `SemanticScript/compiler/semsc.py`.
  - [ ] `json.createBuilder`, `json.destroyBuilder`, `json.finishBuilder`,
        `json.builderLength`.
  - [ ] `json.objectOpen`, `json.objectClose`, `json.arrayOpen`,
        `json.arrayClose`.
  - [ ] `json.fieldInt64`, `json.fieldDouble`, `json.fieldBool`,
        `json.fieldString`, `json.fieldNull`.
  - [ ] `json.elementInt64`, `json.elementDouble`, `json.elementBool`,
        `json.elementString`, `json.elementNull`.
  - [x] Add `SS3624 deprecatedJsonBuilderCall` in
        `SemanticScript/linter/semlint.py` so any lingering source emits a
        block-compile diagnostic with a fix-it pointing at
        `json.stringify.<TypeName>` or `json.createEmptyDocument` +
        `appendArrayElement*`.
  - [ ] Drop `json.destroyBuilder` from `_NATIVE_DEFER_DISPATCH` once no
        user source references it; keep the C symbol as an internal helper
        the new mutator family reuses.
- [ ] Remove the user-facing finder calls from the `json.*` dispatch table.
  - [ ] `json.findString`, `json.findInt64`, `json.findDouble`,
        `json.findBool`, `json.hasField`.
  - [x] Add `SS3625 deprecatedJsonFinderCall` recommending
        `json.createDocument` + `json.cursorAtPath` + `json.cursor*` as
        the replacement.
- [ ] Remove the user-facing primitive encode/decode shortcuts from the
      `json.*` dispatch table.
  - [ ] Delete the `json.encode.<Primitive>` dispatch path
        (current SYNTAX.md:428).
  - [ ] Delete the `json.decode.<Primitive>` dispatch path
        (current SYNTAX.md:429).
  - [ ] Route internal callers through `json.stringify.<Primitive>` /
        `json.parse.<Primitive>` so there is one public spelling and the
        primitive-vs-record dispatch lives in exactly one switch.
- [ ] Remove the user-facing record encode/decode shortcuts.
  - [ ] Delete the `json.encode.RecordTypeName` dispatch path.
  - [ ] Delete the `json.decode.RecordTypeName` dispatch path.
  - [ ] Mark SYNTAX.md:430 as removed with a one-line pointer to the new
        `json.stringify.<TypeName>` / `json.parse.<TypeName>` rows.
- [ ] Remove the obsolete public exports from
      `SemanticScript/std/json/main.sem`.
  - [ ] Drop `exportType standard.json JsonBuilder`; keep `JsonBuilder` as
        an internal-only alias the runtime header uses.
  - [ ] Drop `exportConstant standard.json defaultJsonBuilderCapacityBytes`
        if no surviving public call references it.
  - [ ] Audit every other `JsonFieldName` / `JsonStringValue` /
        `JsonScratchBuffer` export and remove ones that no surviving
        public call still uses.
- [ ] Delete the corresponding SYNTAX.md rows.
  - [ ] Rewrite row 447 to list only the surviving aliases
        (`JsonText`, `JsonScratchBuffer`, `JsonCapacityBytes`,
        `JsonDocument`, `JsonCursor`, `JsonPath`).
  - [ ] Delete row 448 (builder call surface) — replaced by the new
        document-lifecycle + mutator rows.
  - [ ] Delete row 449 (finder call surface) — replaced by the new cursor
        reader rows.
  - [ ] Delete rows 428/429/430 — replaced by `json.stringify.<TypeName>`
        and `json.parse.<TypeName>` rows.
- [ ] Migrate or delete the legacy JSON runtime tests.
  - [x] `SemanticScript/tests/json_runtime_smoke.sscript`: port every
        assertion to the new CRUD surface.
  - [x] `SemanticScript/tests/json_runtime_adversarial.sscript`: same
        treatment.
  - [ ] `SemanticScript/runtime/native_json/health_demo.c`: delete if its
        coverage is now redundant with the new `ss_json_document_*` unit
        tests, otherwise rewrite to exercise the document surface.
- [x] Update VS Code extension surfaces.
  - [x] Remove the deprecated `json.*` call names from
        `vscode-semanticscript/extension.js` symbol/hover tables.
  - [x] Remove deprecated highlights from
        `vscode-semanticscript/syntaxes/semanticscript.tm-language.json`.
- [ ] Update `docs/reference/verb-index.md` to delete every removed
      `json.*` verb entry.
- [x] Rewrite `docs/optimization-guide.md` JSON sections around
      `json.stringify.<TypeName>` and `json.serializeDocument` so the
      stack-allocated-buffer guidance migrates to the new surface.
- [ ] Replace every legacy call site in the repository.
  - [ ] Grep for `json\.(createBuilder|destroyBuilder|finishBuilder|`
        `builderLength|objectOpen|objectClose|arrayOpen|arrayClose|`
        `field(Int64|Double|Bool|String|Null)|`
        `element(Int64|Double|Bool|String|Null)|`
        `findString|findInt64|findDouble|findBool|hasField|`
        `encode\.|decode\.)` and migrate every match to the new surface.
  - [ ] Confirm the grep returns zero hits in `apps/`,
        `SemanticScript/tests/`, `SemanticScript/std/`, `docs/`, and
        `vscode-semanticscript/` before marking removal complete.
- [ ] Audit the rest of this file.
  - [ ] Re-run `grep -ni "json" TODO.md` and confirm every JSON-handling
        bullet lives under
        `### Native JSON CRUD API And jsonBody Literal`.
  - [ ] Delete any orphan JSON bullet found elsewhere and replace it with
        a one-line pointer to this section.

#### Aggressive Testing And Edge Case Coverage

Every test below must follow the deep-audit pattern
(`feedback_verify_impld_claims`): each case asserts a semantic outcome that
would fail under a no-op lowering, not just that the call returns OK. Place
the new tests under `SemanticScript/sem/feature_tests/` and wire them through
the maintained reference-compiler test path before marking a batch complete.

- [ ] Add `SemanticScript/sem/feature_tests/<NNN>_json_document_tokenizer_edges.sscript`
      covering JSON tokenizer corner cases.
  - [ ] Empty object `{}` parses to a zero-field root and serializes
        identically.
  - [ ] Empty array `[]` parses to a zero-element root and serializes
        identically.
  - [ ] Mixed whitespace (spaces, tabs, LF, CR) between every token
        parses to the same tree as the no-whitespace input.
  - [ ] UTF-8 BOM (`EF BB BF`) at the start of input is rejected with
        `JsonAccessError.UnexpectedToken`.
  - [ ] Every standard escape (`\"`, `\\`, `\/`, `\b`, `\f`, `\n`, `\r`,
        `\t`) survives parse + serialize byte-for-byte.
  - [ ] `\uXXXX` for BMP code points round-trips.
  - [ ] Surrogate pair `😀` decodes to one non-BMP character
        and re-serializes to the same surrogate pair.
  - [ ] Lone high surrogate `\uD83D` (no low follow-up) is rejected with
        `EscapeMalformed`.
  - [ ] Lone low surrogate `\uDE00` is rejected with `EscapeMalformed`.
  - [ ] Raw control byte (0x00-0x1F) inside a string literal is rejected.
  - [ ] Trailing comma in an object is rejected.
  - [ ] Trailing comma in an array is rejected.
  - [ ] `//` line comment is rejected.
  - [ ] `/* block comment */` is rejected.
  - [ ] Single-quoted string is rejected.
  - [ ] Unquoted object key is rejected.
  - [ ] Leading zero `05` is rejected.
  - [ ] Plus-signed integer `+5` is rejected.
  - [ ] Hex integer `0x5` is rejected.
  - [ ] Trailing `.` on a float (`5.`) is rejected.
  - [ ] Leading `.` on a float (`.5`) is rejected.
  - [ ] Scientific notation `1e10`, `1E-5`, `1.5e+2` parses correctly.
  - [ ] `NaN`, `Infinity`, `-Infinity` are rejected (RFC 8259 forbids).
  - [ ] Duplicate object keys: confirm the documented last-wins policy
        and assert `SS3626 duplicateJsonObjectKey` fires in semlint.
- [ ] Add boundary/precision tests.
  - [ ] `i64` max (9223372036854775807) round-trips through stringify +
        parse.
  - [ ] `i64` min (-9223372036854775808) round-trips.
  - [ ] `i64` overflow (one past max in source) returns the documented
        atoll-fallback value; pin the choice in SYNTAX.md.
  - [ ] `f64` smallest positive subnormal round-trips within documented
        precision.
  - [ ] `f64` largest finite (`1.7976931348623157e+308`) round-trips.
  - [ ] `-0.0` is distinguishable from `0.0` after round-trip.
  - [ ] 1 MiB string value fits under a 2 MiB `capacity_bytes`.
  - [ ] 1 MiB string under a 512 KiB `capacity_bytes` returns
        `CapacityExceeded`.
  - [ ] Field name at exactly the `FieldNameTooLong` boundary succeeds.
  - [ ] Field name one byte past the boundary returns
        `FieldNameTooLong`.
- [ ] Add nesting-depth tests.
  - [ ] Object nested to the documented bound (currently 16) parses +
        serializes.
  - [ ] Object nested one past the bound is rejected with the
        `JsonAccessError.NestingTooDeep` case (add the case to the error
        enum and the C status table if not already present).
  - [ ] Array nested to the bound parses + serializes.
  - [ ] Array nested one past the bound is rejected.
  - [ ] Mixed object/array nesting to the bound parses + serializes.
- [ ] Add cursor stability tests.
  - [ ] Cursor to `todos[0]` survives `setObjectFieldInt64` on a
        sibling.
  - [ ] Cursor to `todos[0].title` survives a primitive-overwrite on
        the same string (in-place update).
  - [ ] Cursor to `todos[0]` is invalidated by `removeArrayElementAt
        todos 0`; using it triggers `SS3621 staleJsonCursor`.
  - [ ] Cursor to `todos[1]` is invalidated by `insertArrayElement* todos
        0 ...` (shifted-position case).
  - [ ] Cursor to any object field is invalidated by `clearObject` on
        the parent.
  - [ ] Cursor to any array element is invalidated by `clearArray` on
        the parent.
  - [ ] Cursor invalidation propagates through nested containers
        (clear grandparent → all descendants stale).
- [ ] Add mutator semantic tests.
  - [ ] `setObjectFieldString` on a present field overwrites in place
        and preserves key order.
  - [ ] `setObjectFieldString` on an absent field appends and preserves
        existing field order.
  - [ ] `setObjectField*` on a non-object cursor returns `WrongType`.
  - [ ] `appendArrayElement*` on a non-array cursor returns
        `WrongType`.
  - [ ] `insertArrayElement*` at `index == length` appends without
        error.
  - [ ] `insertArrayElement*` at `index > length` returns
        `IndexOutOfRange`.
  - [ ] `insertArrayElement*` at negative index returns
        `IndexOutOfRange`.
  - [ ] `replaceArrayElement*` at out-of-range index returns
        `IndexOutOfRange`.
  - [ ] `removeObjectField` of an absent field returns `1` (status,
        not error).
  - [ ] `removeArrayElementAt` of out-of-range index returns
        `IndexOutOfRange`.
  - [ ] `clearObject` on an already-empty object is a no-op success.
  - [ ] `clearArray` on an already-empty array is a no-op success.
  - [ ] `setObjectFieldJsonText` rejects a syntactically malformed
        sub-document with `UnexpectedToken` and does not partially
        graft.
- [ ] Add path edge case tests.
  - [ ] Empty path `""` returns the root cursor or `MalformedPath` —
        pin the choice in SYNTAX.md and assert it.
  - [ ] `.field` works on a root object.
  - [ ] `[0]` works on a root array.
  - [ ] `.field[0].sub` (three steps) resolves correctly.
  - [ ] `[10][20]` resolves a nested-array lookup.
  - [ ] Unmatched `[` returns `MalformedPath`.
  - [ ] Empty `.` segment returns `MalformedPath`.
  - [ ] Non-numeric index `[abc]` returns `MalformedPath`.
  - [ ] Negative index `[-1]` returns `MalformedPath`
        (negative indexing not supported — pin the contract).
  - [ ] Missing object field returns `PathNotFound` carrying the failing
        segment index in the error payload.
  - [ ] Out-of-range array index returns `IndexOutOfRange`.
- [ ] Add capacity / scratch / OOM tests.
  - [ ] `createDocument` with `capacityBytes` smaller than the input
        text returns `CapacityExceeded` and does not allocate a
        partial document.
  - [ ] `createEmptyDocument` with `capacityBytes == 0` returns
        `CapacityExceeded` on first mutation.
  - [ ] `setObjectFieldString` that would push the arena past
        `capacity_bytes` returns `CapacityExceeded` and leaves the
        document unchanged (transactional mutation).
  - [ ] `serializeDocument` with `scratch_capacity` one byte short of
        the serialized length returns `ScratchTooSmall`.
  - [ ] `cursorString` with `scratch_capacity` one byte short of the
        unescaped value plus NUL returns `ScratchTooSmall`.
  - [ ] `destroyDocument` on NULL does not crash.
  - [ ] Double-destroy is caught by a debug assert and does not
        corrupt heap.
  - [ ] Defer cleanup runs `destroyDocument` exactly once per exit
        path — verify under valgrind in CI.
- [ ] Add `jsonBody` literal edge case tests
      (`SemanticScript/tests/feature/<NNN>_json_body_*`).
  - [ ] Empty island after `jsonBody NAME` is rejected with
        `parseDiagnosticEmptyJsonBody`.
  - [ ] Two `jsonBody` rows targeting the same `storage` name are
        rejected with `duplicateJsonBodyBinding`.
  - [ ] `jsonBody` row whose target storage already has an inline value
        is rejected with `jsonBodyTargetAlreadyValued`.
  - [ ] `jsonBody` row with no matching storage row is rejected with
        `orphanJsonBody`.
  - [ ] `jsonBody` row whose storage type is neither `JsonText` nor a
        declared record is rejected with `jsonBodyUnsupportedType`.
  - [ ] Record-typed island with a missing required field surfaces a
        diagnostic naming the field.
  - [ ] Record-typed island with an extra unknown key is rejected.
  - [ ] Record-typed island with a wrong-typed field surfaces a
        diagnostic naming the expected vs actual JSON kind.
  - [ ] `recordFieldJsonName` override is honored when the JSON key
        differs from the record field identifier.
  - [ ] `recordFieldJsonOmitWhen empty` accepts an absent string field
        and defaults to `""`.
  - [ ] `recordFieldJsonOmitWhen null` accepts an explicit JSON `null`.
  - [ ] `recordFieldJsonOmitWhen false` accepts an absent bool field
        and defaults to `false`.
  - [ ] `recordFieldJsonOmitWhen zero` accepts an absent numeric field
        and defaults to `0`.
  - [ ] Nested record literal inside an outer record literal type-checks
        recursively.
  - [ ] Multi-line island with deeply nested objects parses identically
        after `semfmt`.
- [ ] Add `json.stringify` / `json.parse` round-trip tests.
  - [ ] Stringify and re-parse for every primitive type
        (I64, Bool, F64, String, width-specific C integers, F32).
  - [ ] Stringify and re-parse for a record with every primitive field
        type at once.
  - [ ] Stringify and re-parse for a record carrying an array-of-records
        field.
  - [ ] Stringify a record with `recordFieldJsonOmitWhen` fields and
        confirm omitted keys are absent from output.
  - [ ] Stringify a string containing every standard escape and a
        non-BMP character; re-parse equals the original byte-for-byte.
  - [ ] Stringify the empty string; re-parse equals the empty string.
  - [ ] Parse with an unknown key surfaces
        `JsonDecodeError.UnknownKey` when the codec's policy is strict,
        or is ignored when lenient — pin the per-codec policy in
        `jsonCodec` metadata.
  - [ ] Parse with a missing required key surfaces `MissingRequired`
        naming the field.
  - [ ] Parse with a wrong-typed value surfaces `WrongType` naming the
        field.
  - [ ] Parse a record whose JSON keys use `recordFieldJsonName`
        overrides decodes correctly.
- [ ] Add single-thread concurrency-shape tests.
  - [ ] Two `JsonDocument` handles open at once, each with its own
        cursor, do not alias trees.
  - [ ] Multi-document defer order runs cleanup in reverse declaration
        order and frees both arenas.
  - [ ] A cursor produced from `documentA` and passed against
        `documentB` is rejected with
        `JsonAccessError.CursorForeignToDocument` (add the error case
        if not already present).
- [ ] Add performance baseline tests.
  - [ ] Document with 10,000 fields opens, walks, and serializes inside
        a per-call wall-clock budget published in
        `docs/optimization-guide.md`.
  - [ ] Array with 10,000 elements appends inside budget.
  - [ ] Nesting at exactly the documented bound serializes inside
        budget.
  - [ ] Repeated `setObjectFieldString` on the same key 1,000 times
        does not leak the arena: heap bytes-used returns to baseline
        after a `clearObject`.
- [ ] Add cross-platform byte-equality tests.
  - [ ] Serialize the same document on Windows + Linux CI; assert
        byte-for-byte equality.
  - [ ] LF / CRLF inside a JSON string literal survives parse +
        serialize unchanged on both platforms.
  - [ ] File I/O round-trip (write serialized output to disk, read
        back, re-parse, structural equality) on both platforms.
- [x] Add semlint rule edge case tests in
      `SemanticScript/linter/test_semlint.py`.
  - [x] `SS3620 unguardedJsonAccess` fires when a cursor is used
        before `branch error`.
  - [x] `SS3620` is silent when the cursor comes from
        `json.documentRoot` (exempt path).
  - [x] `SS3621 staleJsonCursor` fires once per structural mutator
        when the cursor is used after.
  - [x] `SS3621` is silent when a fresh cursor is rebound after the
        mutator.
  - [x] `SS3622 malformedJsonPath` fires for the malformed-path corpus
        used above.
  - [x] `SS3622` is silent for a syntactically valid path even when the
        path would resolve to a missing field at runtime (lint is
        syntactic, not semantic).
  - [x] `SS3623 unescapedJsonStringInterpolation` fires for the
        `listRowFormat`-style heuristic.
  - [x] `SS3623` is silent for an `snprintf` outside any JSON context
        (false-positive guard).
  - [x] `SS3624 deprecatedJsonBuilderCall` and
        `SS3625 deprecatedJsonFinderCall` fire on the legacy call
        names from the removal section and block compilation.
- [ ] Add fuzz coverage.
  - [ ] Add `SemanticScript/tests/fuzz/json_document_fuzz.py` that
        drives random JSON inputs through `createDocument`; assert no
        crash, no leak, and round-trip equality where parse succeeds.
  - [ ] Add an output-side fuzzer that emits random typed values
        through `json.stringify` and re-parses through `json.parse`;
        assert round-trip equality.
  - [ ] Run each fuzzer for a fixed wall-clock budget in CI and fail
        on any non-zero exit from the driver.
  - [ ] Seed the corpus with the malformed-surrogate, deep-nesting,
        big-string, and full-escape cases above.
- [ ] Add memory-safety coverage.
  - [ ] Run the maintained native/runtime feature suite under
        `valgrind --leak-check=full` on Linux CI and assert zero leaks.
  - [ ] Run the full suite under AddressSanitizer on supported
        platforms and assert no errors.
  - [ ] Add a leak regression test: create 1,000 documents in a tight
        loop, destroy each via `defer`, assert heap usage returns to
        baseline within a documented tolerance.
- [ ] Add migration regression coverage.
  - [ ] Diff every assertion in `json_runtime_smoke.sscript` against
        the equivalent assertion in the new feature tests; confirm
        zero coverage gaps before deleting the legacy test.
  - [ ] Same diff against `json_runtime_adversarial.sscript`.
  - [ ] `python apps/taskforge-web/scripts/test_taskforge_web.py` passes
        identically before and after the app migration, with
        byte-stable response bodies; archive the pre/post diff in the
        CHANGELOG entry for the migration.

### Concurrency, Async, And State Runtime

- [x] Decide whether a real scheduler/event loop is in scope for 1.0.
  - [x] If yes, implement scheduler-backed `start`, `await`, groups, and worker
        pools. Not selected for scoped 1.0; synchronous lowering remains the
        1.0 behavior.
  - [x] If no, keep synchronous lowering documented and tested.
- [x] Plan and prototype the post-1.0 libuv async runtime experiment.
  - [x] Record the experiment direction: use libuv as the portable event loop,
        timer, async DNS, and worker-pool backend.
  - [x] Keep 1.0 synchronous lowering unchanged while the libuv runtime is
        developed behind an opt-in build/runtime flag.
  - [x] Name the opt-in surface, such as `runtimeBackend PROJECT libuv` or
        `asyncRuntime PROJECT libuv`.
  - [x] Decide whether the flag belongs in `build.sem`, CLI flags, or both.
        Current prototype uses `asyncRuntime PROJECT libuv` in build tape.
  - [x] Add a feature gate so generated code never assumes libuv symbols unless
        the async runtime backend is selected.
  - [x] Define the first supported program classes: console program first,
        native webserver handler later.
  - [x] Define the unsupported cases for the experiment, including GUI message
        loops, long-lived streaming responses, and nested event-loop runs.
  - [x] Document that `await` pauses the current operation and yields to the
        runtime; it does not keep the same C stack frame executing.
  - [x] Document the lowering model as continuation frames plus a resume
        function per async operation.
  - [x] Define a runtime-owned `SSAsyncLoop` wrapper around `uv_loop_t`.
  - [x] Define a runtime-owned `SSFuture` or `SSAsyncTask` handle with status,
        result pointer, error code, cancellation flag, and continuation list.
  - [x] Define an operation frame ABI for generated async functions.
  - [x] Define frame allocation and cleanup ownership.
  - [x] Define how ordinary local variables are spilled from the C stack into
        the async frame before an `await`.
  - [x] Define how `defer`, `deferLog`, and `deferAwaitLog` run when an async
        frame returns normally, returns an error, or is cancelled.
  - [x] Define how `timeout CALL DURATION` attaches a libuv timer to a future.
  - [x] Define how `cancelOn CALL TOKEN` maps to future cancellation.
  - [x] Define how `select` waits on multiple futures or timer tokens.
  - [x] Define how `taskGroup`, `startInGroup`, and `awaitGroup` aggregate
        child futures.
  - [x] Define how worker-pool work maps to `uv_queue_work`.
  - [x] Decide whether CPU work and blocking I/O share the libuv default thread
        pool or use a SemanticScript-owned worker pool.
  - [x] Define an environment variable or build setting for worker-pool size.
        Current prototype uses libuv's `UV_THREADPOOL_SIZE`.
  - [x] Add runtime initialization and shutdown functions:
        `ss_async_loop_init`, `ss_async_loop_run`, `ss_async_loop_stop`, and
        `ss_async_loop_destroy`.
  - [x] Add a small native health demo under
        `SemanticScript/runtime/native_async/health_demo.c`.
  - [x] Prove a libuv timer can resume a suspended SemanticScript frame.
  - [x] Prove two started timers can complete out of order and resume the
        correct frames.
  - [ ] Prove cancellation closes timer/work handles without leaking memory.
  - [ ] Add diagnostics when an async operation is lowered without selecting an
        async runtime backend.
  - [x] Add diagnostics when an `await` target was never started.
  - [x] Add diagnostics when a started future is neither awaited, cancelled, nor
        explicitly detached.
  - [x] Add docs explaining why nested `uv_run` inside route handlers is not the
        production model.
- [x] Replace single-thread mutex no-op semantics with runtime locking, or keep
      them documented as single-thread fallback only.
- [x] Implement cross-process shared state, or explicitly scope `sharedState`
      to same-process globals for 1.0.
- [x] Add runtime guard-token ownership enforcement, or keep guard tokens as
      linter/spec contracts for 1.0.
- [x] Add tests that concurrency/time/cleanup docs match actual lowering.

## P1 - Project Layout, Build Tape, Modules, Imports, And Exports

This section captures the post-discussion direction for project structure:
no TOML manifest, `build.sem` as the project/build/comptime surface,
`main.sem` as the default executable entry, build-owned module registry,
module-owned import/export contracts, colocated `*.test.sem` files, Go-style
dependency fetching, and SemanticScript-native export/import contracts.

### Parallel Workstream Split For 6 Agents

Use these ownership boundaries when running this effort with six simultaneous
agents. Each workstream should update its owned files only, record completed
items in this section, and leave integration notes for the final coordinator.

#### Agent 1 - Build Tape And Project Discovery

Owned scope: `build.sem` grammar, project-root discovery, build configuration
validation, and compiler project-mode entry.

- [x] Define and implement the build-tape parser surface.
  - [x] Add parser support for `buildProject`.
  - [x] Add parser support for `modulePath`.
  - [x] Add parser support for `languageVersion`.
  - [x] Add parser support for `projectVersion`.
  - [x] Add parser support for `projectLicense`.
  - [x] Add parser support for `sourceRoot`.
  - [x] Add parser support for `mainFile`.
  - [x] Add parser support for `mainOperation`.
  - [x] Add parser support for `testPattern`.
  - [x] Add parser support for `dependency`.
  - [x] Add parser support for `dependencySource`.
  - [x] Add parser support for `dependencyIntegrity`.
  - [x] Add parser support for `buildProfile`.
  - [x] Add parser support for `optLevel`.
  - [x] Add parser support for `runtimeChecks`.
  - [x] Add parser support for `persistLlvmIr`.
  - [x] Add parser support for `nativeOutput`.
  - [x] Add parser support for `targetRuntime`.
  - [x] Reserve but do not execute `comptimeOperation`.
- [ ] Implement build project discovery.
  - [x] Search current directory and ancestors for `build.sem`.
  - [x] Support single-file mode when no `build.sem` exists.
  - [ ] Reject ambiguous nested project roots with a source-located diagnostic.
  - [x] Preserve source locations for every build-tape row.
- [ ] Implement build-tape validation.
  - [x] Require one active `buildProject`.
  - [x] Validate singleton rows.
  - [x] Validate source roots.
  - [x] Validate target runtime choices.
  - [x] Validate `mainFile` / `mainOperation` requirements per target.
  - [ ] Validate dependency aliases and module paths.
  - [ ] Validate release builds do not use floating dependency refs without a
        lock.
- [ ] Wire project mode into compiler/build flow.
  - [x] Add compiler project-mode entrypoint.
  - [x] Pass build profile from `build.sem` into existing compiler options.
  - [x] Pass runtime checks from `build.sem` into existing compiler options.
  - [x] Pass LLVM IR persistence from `build.sem` into existing compiler
        options.
  - [x] Resolve native output from `build.sem`.
  - [x] Add focused tests for valid and invalid build tapes.
- [x] Agent 1 handoff notes.
  - [x] Document public parser/validation helpers for Agent 2 and Agent 6.
  - [x] List any build verbs intentionally parser-only for 1.x.

#### Agent 2 - Build-Owned Modules And Entry Rules

Owned scope: folder-owned module model declared in `build.sem`, root/main entry
resolution, and module metadata validation.

- [ ] Implement folder-module discovery.
  - [ ] Detect folders containing production `.sem` files.
  - [ ] Require each production source folder to be registered with
        `registerModule` in `build.sem`.
  - [x] Treat `*.test.sem` as test files, not production module triggers by
        themselves.
  - [ ] Normalize folder paths across Windows and POSIX.
- [ ] Enforce folder/module consistency.
  - [ ] Validate `moduleFolder MODULE_PATH PATH_TEXT`.
  - [ ] Validate folder module path equals root module path plus folder path
        unless explicit override is designed.
  - [ ] Reject conflicting module rows in `build.sem`.
  - [ ] Reject source files that declare a module different from the
        `build.sem` folder contract.
  - [ ] Decide and implement whether source files may repeat the exact folder
        module row for local context.
- [ ] Implement module metadata checks.
  - [x] Parse `modulePurpose`.
  - [x] Parse `moduleOwns`.
  - [x] Parse `moduleDoesNotOwn`.
  - [x] Parse `moduleDependency`.
  - [x] Parse `moduleWarning`.
  - [x] Parse `moduleInvariant`.
  - [x] Parse `moduleSecurity`.
  - [x] Parse `moduleObservability`.
  - [ ] Require `modulePurpose` for folder modules.
  - [ ] Warn when ownership context is missing.
  - [ ] Warn when declared module dependencies are unused.
  - [ ] Warn when used module dependencies are not declared.
- [ ] Implement entry rules.
  - [ ] Default to `main.sem` when `mainFile` is omitted.
  - [ ] Default to `operation main` when `mainOperation` is omitted.
  - [ ] Reject ambiguous multiple app entries.
  - [ ] Reject executable entry requirements for library targets.
  - [ ] Validate webserver target entry ambiguity.
- [ ] Add module/entry tests.
  - [ ] Missing module contract rows in `build.sem`.
  - [ ] Conflicting module declaration.
  - [ ] Root plus folder module happy path.
  - [ ] Default `main.sem` and `operation main`.
  - [ ] Explicit main file and operation.
  - [ ] Library target with no main.
  - [ ] Webserver target with ambiguous servers.
- [x] Agent 2 handoff notes.
  - [x] Document module index API for Agent 3 and Agent 4.
  - [x] List any migration compatibility assumptions for Agent 6.

#### Agent 3 - Export Contract Tape

Owned scope: exports as public semantic contracts, contract extraction, export
validation, and diagnostics for public API quality.

- [x] Implement export rows.
  - [x] Add `exportType MODULE_PATH TYPE_NAME`.
  - [x] Add `exportError MODULE_PATH ERROR_TYPE`.
  - [x] Add `exportOperation MODULE_PATH OPERATION_NAME`.
  - [x] Add `exportCapability MODULE_PATH CAPABILITY_NAME`.
  - [x] Add `exportConstant MODULE_PATH CONSTANT_NAME`.
  - [x] Decide `exportRecord` / `exportEnum` are redundant; use `exportType`
        for aliases, records, and enums.
- [x] Enforce export visibility rules.
  - [x] Treat symbols as private unless exported.
  - [x] Restrict export rows to module source files.
  - [x] Require exported symbols to belong to the same registered module.
  - [x] Reject unknown exports.
  - [x] Reject duplicate exports.
  - [x] Reject mutable module storage exports.
  - [x] Reject local/shared state exports.
  - [x] Allow immutable module storage through `exportConstant`.
- [x] Build exported operation contracts.
  - [x] Extract inputs.
  - [x] Extract outputs.
  - [x] Extract effects.
  - [x] Extract capability or authority coverage.
  - [x] Extract failure types and error cases.
  - [x] Extract async/timing metadata.
  - [x] Extract memory metadata.
  - [x] Preserve source locations for every exported contract edge.
- [x] Build exported type/error/capability contracts.
  - [x] Extract record fields and invariants for exported record types.
  - [x] Extract enum cases for exported enum types.
  - [x] Extract error cases for exported error types.
  - [x] Extract capability effect path and access mode.
  - [x] Extract constant type and value/trust metadata.
- [x] Add export quality diagnostics.
  - [x] Warn when exported operations lack `purpose`.
  - [x] Warn when exported operations have hidden or undeclared effects.
  - [x] Warn when exported operations wrap dependency behavior without
        ownership/purpose context.
  - [x] Warn when exported names are overly generic.
- [x] Add export tests.
  - [x] Exported operation happy path.
  - [x] Private symbol rejected from external module.
  - [x] Exported immutable constant accepted.
  - [x] Mutable storage export rejected.
  - [x] Exported error cases visible to consumers.
  - [x] Exported capability visible to consumers.
- [x] Agent 3 handoff notes.
  - [x] Document contract tape shape for Agent 4 and Agent 5.
  - [x] Document export diagnostics for Agent 6 docs.

#### Agent 4 - Imports, Qualified Names, And Singular Imports

Owned scope: module imports, qualified access, singular import aliases, shadowing
rules, and imported contract lookup.

- [ ] Refine module import syntax.
  - [x] Decide compatibility path for current `importModule DOTTED.PATH [as
        ALIAS]`.
  - [x] Define preferred `importModule ALIAS MODULE_PATH` shape if adopted.
  - [ ] Require aliases for external dependency modules.
  - [x] Reject alias collisions.
  - [x] Reject imports not reachable from `build.sem`.
- [x] Implement qualified references.
  - [x] Resolve `moduleAlias.operationName` call targets.
  - [x] Resolve `moduleAlias.TypeName` type references.
  - [x] Resolve `moduleAlias.ErrorType` error references.
  - [x] Resolve `moduleAlias.CapabilityName` capability references.
  - [x] Reject qualified access to private symbols.
  - [x] Reject qualified access to mutable storage.
  - [x] Preserve qualified source names in diagnostics.
- [x] Implement singular import rows.
  - [x] Add `importOperation LOCAL_NAME MODULE_ALIAS EXPORTED_OPERATION`.
  - [x] Add `importType LOCAL_NAME MODULE_ALIAS EXPORTED_TYPE`.
  - [x] Add `importError LOCAL_NAME MODULE_ALIAS EXPORTED_ERROR`.
  - [x] Add `importCapability LOCAL_NAME MODULE_ALIAS EXPORTED_CAPABILITY`.
  - [x] Add `importConstant LOCAL_NAME MODULE_ALIAS EXPORTED_CONSTANT`.
  - [x] Reject wildcard imports.
  - [x] Reject implicit singular imports.
- [x] Enforce alias and shadowing rules.
  - [x] Reject singular imports that shadow local declarations.
  - [x] Reject singular imports that shadow other imports.
  - [x] Reject ambiguous unqualified references.
  - [x] Warn when many singular imports from one module reduce clarity.
  - [x] Warn when local alias hides provider domain context.
- [x] Carry imported contracts through call checking.
  - [x] Imported operation calls use exported input contract.
  - [x] Imported operation calls use exported output contract.
  - [x] Imported operation calls expose exported effect contract.
  - [x] Imported types carry record/enum metadata.
  - [x] Imported errors carry error cases.
  - [x] Imported capabilities carry effect path/access metadata.
- [x] Add import tests.
  - [x] Qualified operation call happy path.
  - [x] Qualified type/error/capability references.
  - [x] Singular operation/type/error/capability/constant imports.
  - [x] Private symbol rejected.
  - [x] Alias collision rejected.
  - [x] Wildcard import rejected.
  - [x] Import cycle rejected.
- [x] Agent 4 handoff notes.
  - [x] Document import resolution API for Agent 5 dependency cache work.
  - [x] Document compatibility edge cases for Agent 6 migration docs.

#### Agent 5 - Dependency Fetching, Cache, Locking, And Cross-Module Authority

Owned scope: Go-style dependency fetching, `.semcache/`, lock behavior,
dependency contract loading, and cross-module effect/capability propagation.

- [ ] Define dependency fetch model.
  - [x] Add `sem get MODULE_PATH@VERSION_OR_REF` design notes.
  - [x] Define `sem get` as a tool-driver command, not a compiler backend
        phase.
  - [x] Define `sem build` dependency preparation order: parse `build.sem`,
        resolve/fetch/cache dependencies, load dependency contracts, then call
        `semsc`.
  - [x] Define whether direct `semsc build.sem` may fetch from the network or
        must remain validation/compile-only.
  - [x] Define the source-level fetch API names: keep build-time dependency
        fetch as `dependencyFetch`; reserve runtime HTTP client calls for a
        separate `standard.net` / `net.fetch*` surface.
  - [x] Support GitHub module paths first.
  - [x] Define GitHub archive URL construction from `OWNER/REPO REF`.
  - [x] Define GitHub API calls needed to resolve a tag or branch to an exact
        commit.
  - [x] Decide whether GitHub fetching uses anonymous HTTPS first and optional
        token auth later.
  - [x] Keep grammar generic enough for non-GitHub Git paths.
  - [x] Support local path dependencies.
  - [x] Support pinned tags.
  - [x] Support pinned commits.
  - [x] Distinguish immutable refs (`commit:<sha>`) from mutable refs
        (`main`, branch names, moving tags).
  - [ ] Reject floating branches in release builds unless explicitly allowed.
  - [x] Define a dev-only override for intentionally floating dependency refs.
  - [x] Define diagnostics when `dependencyFetch` exists without a matching
        `dependency` row.
- [ ] Implement dependency preparation before compile.
  - [ ] Add a dependency preparation module under the tooling layer, not inside
        LLVM/codegen.
  - [ ] Parse the active `buildProject` and collect `dependency`,
        `dependencyFetch`, `dependencyCache`, `dependencyLock`, and
        `dependencyIntegrity` rows.
  - [ ] Normalize dependency aliases and reject duplicate aliases before any
        network access.
  - [ ] Resolve local/path dependencies without network access.
  - [ ] Resolve GitHub dependencies through archive download or GitHub API.
  - [ ] Resolve generic HTTPS archive dependencies through direct download.
  - [ ] Materialize fetched sources into cache before compiler import
        resolution.
  - [ ] Return a structured dependency-resolution report for agent logs.
  - [ ] Ensure dependency preparation is idempotent for unchanged lock/cache
        state.
- [ ] Implement `.semcache/` behavior.
  - [x] Store cloned dependencies outside source roots.
  - [x] Define default project cache path as `.semcache/` beside `build.sem`.
  - [x] Define exact cache directory layout for GitHub dependencies.
  - [x] Store GitHub archive downloads under a content-addressed blob path.
  - [x] Store extracted dependency source under a resolved-commit path.
  - [x] Store local/path dependency entries as references, not copied source,
        unless vendoring is explicitly requested later.
  - [x] Keep `.semcache/` ignored by git.
  - [x] Never mutate cached dependency source during normal builds.
  - [x] Treat cached dependency source as read-only after extraction.
  - [x] Write downloads to a temp file and atomically move them into cache.
  - [x] Use per-dependency lock files to avoid two builds writing the same
        cache entry at once.
  - [x] Detect cache corruption.
  - [x] Recompute archive checksum before trusting a cached archive.
  - [x] Recompute extracted tree checksum or manifest hash before trusting a
        cached source tree.
  - [x] Delete or quarantine corrupt cache entries instead of compiling them.
  - [ ] Support cache refresh through explicit update commands.
  - [x] Make normal builds reuse cache and lock data without refreshing.
  - [ ] Add a clear diagnostic when cache is missing and network is disabled.
- [ ] Define and implement lock data.
  - [x] Decide between `sem.lock`, `build.lock.sem`, or another SemanticScript
        lock tape.
  - [x] Define `sem.lock` as a SemanticScript tape, not TOML/JSON/YAML.
  - [x] Define top-level lock identity rows such as `lockProject`,
        `lockGeneratedBy`, and `lockFormatVersion`.
  - [x] Define one locked dependency block per dependency alias.
  - [x] Record module path.
  - [x] Record requested version/ref.
  - [x] Record resolved commit.
  - [x] Record checksum.
  - [x] Record dependency module root.
  - [x] Record transitive dependencies.
  - [x] Record fetch kind (`github`, `http`, or `local`).
  - [x] Record source URL or GitHub `OWNER/REPO`.
  - [x] Record archive URL used for the fetch.
  - [x] Record archive SHA-256.
  - [x] Record extracted source tree digest.
  - [x] Record dependency `build.sem` path inside the cached source.
  - [x] Record dependency language version and module path from its build tape.
  - [x] Record lock timestamp only if it will not break reproducible diffs; if
        it is included, keep it in a clearly non-semantic metadata row.
  - [x] Make locked builds avoid network access.
  - [ ] In prod/release profile, require lock rows before any remote fetch.
  - [x] Fail if a locked dependency resolves to different bytes than the lock
        checksum.
  - [x] Fail if a locked GitHub dependency resolves to a different commit.
  - [x] Add a `--locked` or equivalent mode that forbids lock mutation.
  - [x] Add an update mode that is explicitly allowed to mutate `sem.lock`.
- [ ] Load dependency contract tapes.
  - [ ] Read dependency `build.sem`.
  - [ ] Read dependency module registry rows from `build.sem`.
  - [ ] Read dependency module-source export rows and exported contract tape.
  - [ ] Support resolving registered dependency modules from the cached source
        root.
  - [ ] Merge dependency export contract indexes into import resolution without
        treating dependency private symbols as local project symbols.
  - [ ] Reject dependencies missing required module metadata.
  - [ ] Reject dependencies whose `modulePath` does not match the requested
        dependency module path.
  - [ ] Reject dependencies whose registered module source cannot be selected
        deterministically.
  - [ ] Surface dependency diagnostics with dependency source paths.
  - [ ] Include dependency alias, module path, requested ref, resolved commit,
        and cache path in diagnostics.
  - [ ] Ensure dependency diagnostics render cleanly in `--format agent`.
- [ ] Implement cross-module effect and authority propagation.
  - [x] Caller diagnostics cite imported operation effects.
  - [x] Caller declares effects triggered by imported calls.
  - [ ] Caller proves capability or authority coverage.
  - [ ] Imported capabilities preserve hierarchy.
  - [ ] Warn on broad capability re-export without rationale.
  - [x] Ensure file/network/database/observability effects do not disappear
        through wrappers.
- [ ] Add dependency/effect tests.
  - [ ] Local path dependency.
  - [ ] Local path dependency resolves without touching network.
  - [x] GitHub tag/commit dependency if network tests are allowed.
  - [ ] GitHub archive URL is constructed correctly.
  - [ ] GitHub tag resolves to exact commit.
  - [ ] GitHub commit ref skips mutable-ref resolution.
  - [ ] HTTPS archive dependency downloads and verifies checksum.
  - [ ] Locked build avoids network.
  - [ ] Locked prod build fails when lock is missing.
  - [ ] Locked build fails on checksum mismatch.
  - [ ] Cached archive corruption is detected.
  - [ ] Cached extracted tree corruption is detected.
  - [ ] Missing dependency `build.sem`.
  - [ ] Missing dependency module contract rows in `build.sem`.
  - [ ] Dependency `modulePath` mismatch diagnostic.
  - [ ] Dependency registered module source missing diagnostic.
  - [ ] Imported operation with filesystem effect.
  - [x] Missing caller effect diagnostic.
  - [ ] Missing caller capability diagnostic.
- [x] Agent 5 handoff notes.
  - [x] Document lock format for Agent 6 docs.
  - [x] Document cache/authority APIs for final integration.

#### Agent 6 - Tests, Migration, Docs, VS Code, And Integration Harness

Owned scope: user-facing docs, migration guidance, colocated `*.test.sem`
behavior, VS Code syntax/tooling updates, and integration tests spanning all
workstreams.

- [ ] Define colocated test semantics.
  - [x] `*.test.sem` belongs to the same folder module as sibling source.
  - [x] Exclude `*.test.sem` from normal production builds.
  - [x] Include `*.test.sem` in `sem test`.
  - [x] Decide same-folder private symbol access for tests.
  - [x] Reject test files with conflicting module declarations.
  - [x] Ensure test-only helpers are excluded from production exports.
- [x] Update documentation.
  - [x] Update root `README.md` project layout section.
  - [x] Update `docs/language/program-structure.md`.
  - [x] Update `SYNTAX.md` rows for new verbs.
  - [x] Update `docs/reference/verb-index.md`.
  - [x] Add build/module/import/export examples.
  - [x] Document no-TOML/no-sidecar-manifest decision.
  - [x] Document migration from current `importModule` behavior.
- [ ] Update examples.
  - [x] Add minimal console project using `build.sem` and `main.sem`.
  - [ ] Add multi-module project with module registry in `build.sem` and
        contracts in module source files.
  - [ ] Add library export/import sample.
  - [ ] Add singular import sample.
  - [ ] Add dependency sample using a local path dependency.
  - [ ] Add colocated test sample.
- [x] Update VS Code extension.
  - [x] Highlight build-tape verbs.
  - [x] Highlight module metadata verbs.
  - [x] Highlight export/import verbs.
  - [x] Add hover text for new verbs.
  - [x] Add completions for new verbs.
  - [x] Add document symbols for `buildProject`, `module`, exports, and
        imports.
  - [x] Add linter/diagnostic support when new diagnostics exist.
- [ ] Add migration checks.
  - [ ] Audit existing `module` rows.
  - [ ] Audit existing `importModule` rows.
  - [ ] Identify samples needing `build.sem`.
  - [ ] Identify stdlib modules needing relay entries in `std/module.sem`.
  - [ ] Add staged compatibility warnings before hard errors.
- [ ] Build integration harness.
  - [x] End-to-end console project build.
  - [ ] End-to-end web project build.
  - [x] End-to-end module import/export build.
  - [x] End-to-end singular import build.
  - [ ] End-to-end colocated test run.
  - [ ] End-to-end dependency cache/lock run using local path dependency.
  - [x] VS Code extension `npm run check`.
- [x] Agent 6 handoff notes.
  - [x] Summarize changed docs and examples.
  - [x] Summarize compatibility warnings users will see.
  - [x] Provide final integration checklist for coordinator.

### Source Layout Contract

- [x] Define the canonical project layout in the language docs.
  - [x] Document `build.sem` as the required project build tape.
  - [x] Document `main.sem` as the default executable source entry file.
  - [x] Document `*.sem` as normal source files.
  - [x] Document `*.test.sem` as colocated test source files.
  - [x] Document that module folders are registered in `build.sem` and module
        contracts live in module source files.
  - [x] Document that separate `module.sem` files are intentionally not part of
        the application project model; `std/module.sem` is the library relay exception.
  - [x] Document `build/` as ignored build output.
  - [x] Document `.semcache/` as ignored dependency/build cache.
  - [x] Document that TOML/YAML/JSON manifests are intentionally not part of
        the SemanticScript project model.
- [x] Add a project layout section to `README.md`.
  - [x] Show a minimal console app tree.
  - [x] Show a native web app tree.
  - [x] Show a multi-module library tree.
  - [x] Show colocated `*.test.sem` files beside the modules they test.
- [x] Add a project layout section to `docs/language/program-structure.md`.
  - [x] Explain how root source files differ from folder modules.
  - [x] Explain how `main.sem` and `build.sem` interact.
  - [x] Explain how tests are discovered from `*.test.sem`.
  - [x] Explain how generated artifacts stay outside source control.
- [ ] Add examples under `apps/` or `SemanticScript/sem/feature_tests/`.
  - [x] Minimal `build.sem` plus `main.sem` console sample.
  - [ ] Multi-folder module sample with every module registered in `build.sem`.
  - [ ] Webserver sample using `build.sem`, `main.sem`, and folder modules.
  - [ ] Library sample with exports and import consumers.
  - [ ] Tests using `*.test.sem` next to the source folder they validate.

### `build.sem` Build Tape

- [x] Define the `build.sem` grammar as SemanticScript source, not a sidecar
      config format.
  - [x] Add `buildProject PROJECT_NAME`.
  - [x] Add `modulePath PROJECT_NAME MODULE_PATH`.
  - [x] Add `languageVersion PROJECT_NAME VERSION_TEXT`.
  - [x] Add `projectVersion PROJECT_NAME VERSION_TEXT`.
  - [x] Add `projectLicense PROJECT_NAME LICENSE_TEXT`.
  - [x] Add `sourceRoot PROJECT_NAME PATH_TEXT`.
  - [x] Add `mainFile PROJECT_NAME PATH_TEXT`.
  - [x] Add `mainOperation PROJECT_NAME OPERATION_NAME`.
  - [x] Add `testPattern PROJECT_NAME GLOB_TEXT`.
  - [x] Add `dependency PROJECT_NAME ALIAS MODULE_PATH VERSION_OR_REF`.
  - [x] Add `dependencySource PROJECT_NAME ALIAS SOURCE_KIND SOURCE_TEXT`.
  - [x] Add `dependencyIntegrity PROJECT_NAME ALIAS INTEGRITY_TEXT`.
  - [x] Add `buildProfile PROJECT_NAME dev|prod`.
  - [x] Add `optLevel PROJECT_NAME 0|1|2|3`.
  - [x] Add `runtimeChecks PROJECT_NAME off|traps|panic`.
  - [x] Add `persistLlvmIr PROJECT_NAME auto|yes|no`.
  - [x] Add `nativeOutput PROJECT_NAME PATH_TEXT`.
  - [x] Add `targetRuntime PROJECT_NAME nativeExe|webServer|library`.
  - [x] Reserve `comptimeOperation PROJECT_NAME OPERATION_NAME` for 2.0.
- [x] Decide whether `build.sem` accepts only build verbs or the full language.
  - [x] If restricted, reject executable body rows in `build.sem`.
  - [ ] If full language, define which rows execute at compile time.
  - [x] Document that 1.x treats `build.sem` as declarative build tape.
  - [x] Document that 2.0 can widen this into comptime execution.
- [ ] Implement `build.sem` discovery.
  - [x] Search current directory and ancestors for `build.sem`.
  - [ ] Stop at repository root if detectable.
  - [ ] Emit a clear diagnostic when multiple candidate project roots compete.
  - [x] Support single-file mode when no `build.sem` exists.
  - [x] Never silently create `build.sem`.
- [ ] Implement `build.sem` parsing.
  - [x] Add parser rows for every current build-tape verb.
  - [x] Preserve source locations for build diagnostics.
  - [ ] Reject unknown build-tape verbs with a suggestion.
  - [x] Reject missing project names.
  - [x] Reject duplicate `buildProject` names in one build file.
  - [x] Reject duplicate singleton rows such as `modulePath`, `mainFile`, and
        `mainOperation` unless overriding is explicitly designed.
  - [x] Validate paths without requiring referenced files to exist until the
        project discovery pass.
- [ ] Implement build-tape validation.
  - [x] Require exactly one `buildProject` for normal project builds.
  - [x] Require `modulePath`.
  - [x] Require `languageVersion` or define a default.
  - [x] Require `sourceRoot` or default to `"."`.
  - [x] Require `mainFile` only for executable targets.
  - [x] Require `mainOperation` or default to `main`.
  - [ ] Require dependency aliases to be valid identifiers.
  - [ ] Require dependency module paths to be canonical.
  - [ ] Require dependency versions/refs to be pinned for release builds.
  - [ ] Reject network dependency refs in prod/release builds unless locked.
- [ ] Integrate `build.sem` with `semsc.py`.
  - [x] Add `semsc.py build.sem --project-build` or equivalent project mode.
  - [x] Make `sem build` call compiler project mode once the `sem` driver
        exists.
  - [x] Resolve all source roots before parsing application modules.
  - [x] Resolve build profile from `build.sem`.
  - [x] Resolve runtime checks from `build.sem`.
  - [x] Resolve LLVM IR persistence from `build.sem`.
  - [x] Resolve native output path from `build.sem`.
  - [x] Emit diagnostics in terms of `build.sem` rows when build config fails.
- [ ] Add build-tape tests.
  - [x] Minimal valid `build.sem`.
  - [x] Missing `modulePath`.
  - [ ] Duplicate `mainFile`.
  - [ ] Invalid dependency alias.
  - [ ] Invalid module path.
  - [x] Missing `main.sem`.
  - [ ] Missing `operation main`.
  - [ ] Webserver target with route handlers.
  - [ ] Library target with no `main.sem`.

### `main.sem` Entry Rules

- [x] Define default executable entry behavior.
  - [x] If `mainFile` is omitted, look for `main.sem`.
  - [x] If `mainOperation` is omitted, look for `operation main`.
  - [x] Require explicit build rows when more than one plausible entry exists.
  - [x] Reject accidental entry operations in library-only targets.
- [ ] Define root module behavior for `main.sem`.
  - [x] Declare the root module in `build.sem`.
  - [x] Decide whether `main.sem` may repeat the root module row for local
        context.
  - [x] If repetition is allowed, require exact match with `build.sem`.
  - [ ] If repetition is not allowed, lint against source-level module rows in
        project mode.
  - [x] Document the chosen rule with examples.
- [x] Define webserver entry behavior.
  - [x] Allow `main.sem` to declare the primary `webServer`.
  - [x] Allow `build.sem` to select a webserver target.
  - [x] Require exactly one routed webserver when target is `webServer` and no
        explicit server is selected.
  - [x] Reject multiple webservers without an explicit selection row.
  - [x] Validate route handlers after imports and module resolution.
- [ ] Add entry tests.
  - [ ] Default `main.sem` plus `operation main`.
  - [ ] Explicit `mainFile`.
  - [ ] Explicit `mainOperation`.
  - [ ] Missing main file.
  - [ ] Missing main operation.
  - [ ] Multiple candidate entries.
  - [ ] Webserver target with one server.
  - [ ] Webserver target with ambiguous servers.

### Folder-Owned Modules

- [ ] Make folders hard module boundaries.
  - [ ] Every folder containing production `.sem` files must be declared in
        `build.sem`.
  - [ ] Every production `.sem` file in a folder belongs to that folder's
        module.
  - [ ] Reject multiple module declarations for the same folder in `build.sem`.
  - [ ] Reject source files whose `module` row conflicts with the folder module
        declared in `build.sem`.
  - [ ] Decide whether source files may repeat the folder `module` row for
        local context.
  - [ ] If repetition is allowed, require exact match.
  - [ ] If repetition is not allowed, lint against duplicate module rows in
        source files.
- [x] Define module path mapping.
  - [x] Root `modulePath` from `build.sem` defines the project module path.
  - [x] Folder module path must equal root module path plus folder path unless
        an explicit override row exists.
  - [x] Reject `..` path escapes in `moduleFolder`.
  - [x] Normalize slash direction across Windows and POSIX.
  - [x] Preserve case-sensitivity rules in docs.
  - [x] Decide whether folder names with hyphens map to module path segments.
- [x] Add build-owned folder module metadata rows.
  - [x] Add `moduleFolder MODULE_PATH PATH_TEXT`.
  - [x] Add `modulePurpose MODULE_PATH TEXT`.
  - [x] Add `moduleOwns MODULE_PATH TEXT`.
  - [x] Add `moduleDoesNotOwn MODULE_PATH TEXT`.
  - [x] Add `moduleDependency MODULE_PATH DEPENDENCY_ALIAS`.
  - [x] Add `moduleWarning MODULE_PATH TEXT`.
  - [x] Add `moduleInvariant MODULE_PATH TEXT`.
  - [x] Add `moduleSecurity MODULE_PATH TEXT`.
  - [x] Add `moduleObservability MODULE_PATH TEXT`.
- [ ] Enforce minimum module context.
  - [ ] Require `modulePurpose` for every folder module.
  - [ ] Require at least one `moduleOwns` or an explicit no-ownership rationale.
  - [ ] Warn when `moduleDoesNotOwn` is missing for public modules.
  - [ ] Warn when a module imports dependencies not listed by
        `moduleDependency`.
  - [ ] Warn when `moduleDependency` lists unused dependencies.
- [ ] Add module boundary tests.
  - [ ] Folder with missing module rows in `build.sem`.
  - [ ] Folder with conflicting module paths.
  - [ ] Root path plus folder path happy case.
  - [ ] Path normalization on Windows-style paths.
  - [ ] Duplicate module declarations.
  - [ ] Module metadata diagnostics.

### Exports As Public Semantic Contracts

- [x] Define export rows in module source files.
  - [x] Add `exportType MODULE_PATH TYPE_NAME`.
  - [x] Add `exportError MODULE_PATH ERROR_TYPE`.
  - [x] Add `exportOperation MODULE_PATH OPERATION_NAME`.
  - [x] Add `exportCapability MODULE_PATH CAPABILITY_NAME`.
  - [x] Add `exportConstant MODULE_PATH CONSTANT_NAME`.
  - [x] Decide `exportRecord` is redundant with `exportType`.
  - [x] Decide `exportEnum` is redundant with `exportType`.
- [ ] Define export visibility rules.
  - [x] Symbols are private unless exported.
  - [x] Export rows may only appear in module source files.
  - [x] Exported symbols must be declared in the same registered module.
  - [ ] Exported operations must have complete `input` and `output` contracts.
  - [x] Exported operations must declare all effects.
  - [x] Exported operations with effects must prove capability or authority
        coverage.
  - [x] Exported operations should have `purpose`.
  - [ ] Exported operations should have `warning` when they expose nullable,
        unsafe, or external runtime behavior.
  - [ ] Exported types should have invariants where useful.
  - [ ] Exported constants must be immutable module storage.
  - [x] Reject export of mutable module storage.
  - [x] Reject export of local storage.
  - [x] Reject export of shared state values directly.
  - [x] Require mutation to cross modules through exported operations.
- [x] Build a module contract tape.
  - [x] Extract exported operation inputs.
  - [x] Extract exported operation outputs.
  - [x] Extract exported operation effects.
  - [x] Extract exported operation capability requirements.
  - [x] Extract exported operation failure types.
  - [x] Extract exported operation async/timing metadata.
  - [x] Extract exported operation memory metadata.
  - [x] Extract exported type/record fields.
  - [x] Extract exported enum and error cases.
  - [x] Extract exported constants and literal trust metadata.
  - [x] Preserve source locations for every exported contract edge.
- [ ] Validate exports.
  - [x] Reject unknown exported symbols.
  - [x] Reject duplicate exports.
  - [ ] Reject export cycles if a public facade imports and re-exports itself.
  - [x] Warn when exported operation names are too generic.
  - [ ] Warn when exported symbols have no module ownership context.
  - [x] Warn when exported operations hide dependencies through wrapper names
        without purpose explaining the abstraction.
- [x] Add export tests.
  - [x] Exported operation happy path.
  - [x] Unknown exported operation.
  - [x] Exported private mutable state rejected.
  - [x] Exported immutable constant accepted.
  - [x] Exported error cases available to consumers.
  - [x] Exported capability available to consumers.
  - [x] Contract tape includes effects and failures.

### Module Imports And Qualified Calls

- [x] Define canonical module import syntax.
  - [x] Keep current `importModule DOTTED.PATH [as ALIAS]` for 1.x
        compatibility.
  - [x] Prefer `importModule ALIAS MODULE_PATH` for new project modules if the
        grammar can migrate without ambiguity.
  - [x] Document aliases as local source names, not package identities.
  - [x] Require aliases for external dependencies.
  - [x] Reject alias collisions with local declarations.
  - [x] Reject imports of modules not reachable from `build.sem`.
- [x] Define qualified name usage.
  - [x] Allow `moduleAlias.operationName` call targets.
  - [x] Allow `moduleAlias.TypeName` type references.
  - [x] Allow `moduleAlias.ErrorType` error references.
  - [x] Allow `moduleAlias.CapabilityName` capability references only where
        capability imports are legal.
  - [x] Reject qualified access to non-exported symbols.
  - [x] Reject qualified access to mutable storage.
  - [x] Preserve qualified names in diagnostics.
- [ ] Implement module import resolution.
  - [x] Resolve same-project registered modules.
  - [ ] Resolve dependency modules from `.semcache/`.
  - [x] Resolve standard-library modules.
  - [ ] Reject imports that bypass `build.sem` dependency declarations.
  - [ ] Reject ambiguous module paths.
  - [ ] Cache resolved contract tapes.
  - [x] Preserve source location of import rows for diagnostics.
- [ ] Add import diagnostics.
  - [x] Unknown module path.
  - [x] Unknown alias.
  - [x] Duplicate alias.
  - [x] Import cycle.
  - [ ] Imported module lacks module contract rows in `build.sem`.
  - [ ] Imported module has no exports.
  - [x] Imported symbol exists but is private.
  - [ ] Imported operation contract has undeclared effects.
- [ ] Add import tests.
  - [x] Qualified call to exported operation.
  - [x] Qualified type reference.
  - [x] Qualified error reference.
  - [x] Private symbol rejected.
  - [x] Alias collision rejected.
  - [x] Import cycle rejected.
  - [x] Standard-library import.
  - [ ] Dependency import from cache.

### Singular Imports

- [x] Define singular import rows.
  - [x] Add `importOperation LOCAL_NAME MODULE_ALIAS EXPORTED_OPERATION`.
  - [x] Add `importType LOCAL_NAME MODULE_ALIAS EXPORTED_TYPE`.
  - [x] Add `importError LOCAL_NAME MODULE_ALIAS EXPORTED_ERROR`.
  - [x] Add `importCapability LOCAL_NAME MODULE_ALIAS EXPORTED_CAPABILITY`.
  - [x] Add `importConstant LOCAL_NAME MODULE_ALIAS EXPORTED_CONSTANT`.
  - [x] Explicitly reject wildcard imports.
  - [x] Explicitly reject implicit singular imports by capitalization or naming.
- [x] Define singular import semantics.
  - [x] Singular imports create local aliases only.
  - [x] Singular imports do not change the provider module's contract.
  - [x] Singular operation imports bring the full operation contract.
  - [x] Singular type imports bring related record/enum layout metadata.
  - [x] Singular error imports bring exported error cases.
  - [x] Singular capability imports bring effect path and access metadata.
  - [x] Singular constant imports bring immutable value/type metadata.
  - [x] Singular imports must not shadow local declarations.
  - [x] Singular imports must not shadow other imports.
  - [x] Singular imports should be linted when they make the source less clear
        than qualified names.
- [x] Add singular import lint guidance.
  - [x] Prefer qualified calls for most module usage.
  - [x] Allow singular imports for central domain operations used repeatedly.
  - [x] Allow singular imports for facade modules that intentionally re-export
        public API.
  - [x] Warn when a file imports many singular operations from the same module.
  - [x] Warn when singular local alias hides the provider domain.
  - [x] Require rationale for aliasing two different modules into similar local
        names.
- [x] Add singular import tests.
  - [x] Singular operation import happy path.
  - [x] Singular type import happy path.
  - [x] Singular error import happy path.
  - [x] Singular capability import happy path.
  - [x] Singular constant import happy path.
  - [x] Unknown exported symbol rejected.
  - [x] Shadowing local symbol rejected.
  - [x] Wildcard import rejected.

### Cross-Module Effects And Capabilities

- [ ] Preserve effect contracts across module calls.
  - [ ] Caller diagnostics should cite imported operation effects.
  - [ ] Caller must declare matching effects when imported operation effects
        escape through the call boundary.
  - [ ] Caller must use a capability or authority covering its declared effect.
  - [ ] Callee capability requirements should not be silently satisfied by the
        provider module once called from another module unless the contract says
        so.
  - [ ] Decide whether imported operations require caller capability proof,
        callee capability proof, or both.
- [ ] Define capability exports.
  - [ ] Exported capabilities are authority names, not runtime tokens by
        default.
  - [x] Imported capability aliases must preserve effect path and access mode.
  - [ ] Hierarchical capability coverage works across modules.
  - [ ] Narrow imported capabilities should remain narrow.
  - [ ] Reject broad capability re-export without a rationale.
- [ ] Define dependency effect propagation.
  - [ ] External dependency effects in a provider module must appear in exported
        operation contracts if the exported operation can trigger them.
  - [ ] Wrapper/facade modules may narrow or rename effects only with explicit
        metadata explaining the boundary.
  - [x] Observability effects must cross module boundaries like other effects.
  - [x] Network/file/database effects must never disappear through import.
- [ ] Add cross-module effect tests.
  - [ ] Imported operation with console effect.
  - [ ] Imported operation with filesystem effect.
  - [ ] Imported operation with HTTP response effect.
  - [ ] Imported operation with broad provider capability and narrow caller
        effect.
  - [x] Missing caller effect diagnostic.
  - [ ] Missing caller capability diagnostic.
  - [ ] Re-exported broad capability warning.

### Dependency Fetching And Cache

- [ ] Define Go-style module fetching.
  - [x] Add `sem get MODULE_PATH@VERSION_OR_REF`.
  - [x] Keep `sem get` in the SemanticScript tool driver layer so real network
        IO does not couple directly to LLVM/codegen.
  - [x] Define `sem build` dependency-prep order before invoking `semsc`.
  - [x] Decide whether bare `semsc build.sem` is allowed to fetch or only
        validates dependency rows and compiles already-resolved sources.
  - [x] Define agent-readable fetch logs with alias, module path, requested ref,
        resolved commit, cache path, lock path, and failure reason.
  - [x] Support GitHub module paths.
  - [x] Resolve GitHub `OWNER/REPO REF` to a deterministic archive URL.
  - [x] Resolve GitHub tags and branches through API metadata before download.
  - [x] Support anonymous GitHub fetch first.
  - [x] Add optional GitHub token support later without storing tokens in
        `build.sem` or `sem.lock`.
  - [x] Support generic Git URLs later without making GitHub special in the
        language grammar.
  - [x] Support local path dependencies for development.
  - [x] Support pinned tags.
  - [x] Support pinned commits.
  - [x] Classify refs as immutable commit pins, mutable tags, mutable branches,
        or local paths.
  - [ ] Reject floating branches in release builds unless explicitly allowed.
- [x] Define build-time fetch API boundaries.
  - [x] Treat `dependencyFetch` as the build-time dependency API.
  - [x] Reserve runtime outbound HTTP calls for the separate `standard.net`
        API, currently `net.fetchText` / `net.fetchBytes`.
  - [x] Do not let runtime HTTP client naming collide with server-side
        `http.request*` and `http.response*` APIs.
  - [x] Define capability paths for future runtime fetch calls, such as
        `network.http.client read/write`.
  - [x] Require any future runtime fetch wrapper to export effects the same way
        dependency-imported operations do.
- [ ] Implement dependency resolution phase.
  - [ ] Add a resolver that reads `build.sem` dependency rows into structured
        dependency request records.
  - [ ] Validate alias uniqueness and source/fetch/integrity coverage before
        touching disk or network.
  - [ ] Resolve local path dependencies directly from disk.
  - [ ] Resolve GitHub dependencies through archive download as the first
        implementation strategy.
  - [ ] Decide whether to support `git clone` later for submodules and unusual
        refs.
  - [ ] Resolve HTTPS archive dependencies through direct download.
  - [ ] Verify downloaded bytes before extraction.
  - [ ] Extract into a temporary directory, verify extracted source, then
        atomically move into cache.
  - [ ] Return dependency roots to import resolution as read-only source roots.
- [x] Define `.semcache/`.
  - [x] Store cloned dependencies outside source roots.
  - [x] Use `.semcache/` beside `build.sem` as the default project-local cache.
  - [x] Define cache subfolders for source archives, extracted trees, temp
        downloads, and per-alias metadata.
  - [x] Use content-addressed archive filenames to avoid ref-name collisions.
  - [x] Use resolved commits in extracted tree paths for GitHub dependencies.
  - [x] Keep local path dependencies as external references rather than cached
        copies during normal dev builds.
  - [x] Keep `.semcache/` ignored by git.
  - [x] Support user-global cache later if useful.
  - [x] Support project-local cache for reproducible experiments.
  - [x] Do not modify cached dependency sources during normal builds.
  - [x] Write cache entries atomically.
  - [x] Add lock files or equivalent process coordination for concurrent builds.
  - [x] Rehash cached archives before reuse.
  - [x] Rehash extracted source trees before reuse.
  - [x] Quarantine corrupt cache entries and emit a repair command suggestion.
- [x] Define lockfile behavior without TOML.
  - [x] Decide whether lock data lives in `sem.lock`, `build.lock.sem`, or
        another SemanticScript tape file.
  - [x] Define `sem.lock` as the canonical SemanticScript lock tape.
  - [x] Define lock header rows: `lockProject`, `lockFormatVersion`,
        `lockGeneratedBy`, and optional non-semantic metadata.
  - [x] Define locked dependency rows for alias, module path, requested ref,
        resolved commit, fetch kind, source URL, archive URL, archive checksum,
        extracted tree digest, and dependency root.
  - [x] Record module path.
  - [x] Record requested version/ref.
  - [x] Record resolved commit.
  - [x] Record checksum.
  - [x] Record dependency module root.
  - [x] Record transitive dependencies.
  - [x] Make normal builds use locked versions without hitting the network.
  - [x] Add locked mode that fails if `sem.lock` is missing or stale.
  - [x] Add update mode that may rewrite `sem.lock`.
  - [x] Fail if remote source bytes or resolved commits disagree with lock
        data.
  - [x] Keep lock diffs stable and reviewable by sorting dependencies
        deterministically.
- [ ] Implement dependency update flows.
  - [ ] `sem get` adds or updates dependency rows in `build.sem`.
  - [ ] `sem get` fetches dependency source into `.semcache/`.
  - [ ] `sem get` writes or updates the matching `sem.lock` rows.
  - [ ] `sem get` validates the dependency's `build.sem` before accepting it.
  - [ ] `sem mod tidy` removes unused dependency rows.
  - [ ] `sem mod tidy` keeps lock rows only for reachable dependencies.
  - [ ] `sem update ALIAS` updates one dependency.
  - [ ] `sem update ALIAS` preserves version constraints when possible.
  - [ ] `sem update` updates all dependencies within allowed constraints.
  - [ ] `sem update` refuses floating release updates without an explicit flag.
  - [ ] `sem vendor` copies dependencies into a vendored tree if that workflow
        is later accepted.
- [ ] Integrate fetched dependencies with module imports.
  - [ ] Locate dependency `build.sem` under each cached dependency root.
  - [ ] Read dependency `registerModule` rows from cached `build.sem`.
  - [ ] Resolve dependency module source files from the cached root.
  - [ ] Build dependency export contract tapes from cached module sources.
  - [ ] Allow project modules to import dependency modules by registered module
        path and alias.
  - [ ] Prevent dependency private symbols from leaking into project imports.
  - [ ] Include dependency source paths in linter and compiler diagnostics.
- [ ] Add dependency fetch tests.
  - [ ] Local path dependency.
  - [ ] Local path dependency does not use network.
  - [x] GitHub tag dependency.
  - [x] GitHub commit dependency.
  - [ ] GitHub archive download happy path.
  - [ ] GitHub tag-to-commit resolution happy path.
  - [ ] GitHub branch rejected in prod/release locked mode.
  - [ ] HTTPS archive download happy path.
  - [ ] HTTPS archive rejects plain `http://`.
  - [ ] Missing repository diagnostic.
  - [ ] Missing `build.sem` diagnostic.
  - [ ] Missing module contract rows in `build.sem` diagnostic.
  - [ ] Lockfile prevents network access during build.
  - [ ] Missing lock fails in locked mode.
  - [ ] Stale lock fails in locked mode.
  - [ ] Checksum mismatch fails before extraction.
  - [ ] Cache corruption diagnostic.
  - [ ] Dependency import resolves from cache.
  - [ ] Dependency import diagnostics cite cached source file paths.

### Runtime HTTP Client And Fetch API

- [x] Add a libuv-backed HTTP fetcher experiment path.
  - [x] Record the working architecture: libuv owns scheduling, timers,
        cancellation wakeups, and worker dispatch; libcurl owns HTTP, HTTPS,
        redirects, DNS/TLS behavior for the MVP fetcher.
  - [x] Keep the source-level public API backend-neutral, using
        `standard.net` / `net.fetchText` / `net.fetchBytes` over any
        libuv/libcurl-specific names.
  - [x] Add a `standard.net` module or extend `standard.http` with a clearly
        client-side namespace that cannot collide with server-side
        `http.request*` and `http.response*`.
  - [x] Define the minimal source sample that the experiment must compile:
        `start fetchCall`, do local work, `await fetchCall`, then bind the
        response body.
  - [x] Define the expected runtime trace for that sample: fetch starts, local
        work runs, operation yields at `await`, event loop runs other ready
        work, fetch completion resumes the operation after `await`.
  - [x] Add an experiment app under `experiments/libuv-fetcher/`.
  - [x] Add `experiments/libuv-fetcher/main.sem` with a single
        `GET https://example.com/` text fetch.
  - [x] Add `experiments/libuv-fetcher/two_fetches.sem` that starts two
        fetches before awaiting either one.
  - [x] Add `experiments/libuv-fetcher/timeout.sem` that proves timeout
        metadata reaches the runtime.
  - [x] Add `experiments/libuv-fetcher/cancel.sem` once cancellation is wired.
        Current source carries cancellation metadata; hard backend interruption
        remains runtime-specific follow-up work.
  - [x] Add a generated-C sketch or checked-in fixture that shows the expected
        continuation-frame shape for `start` / `await`.
  - [x] Add docs in the experiment README explaining that the current compiler
        still lowers `start` synchronously unless the libuv backend flag is
        selected.
  - [x] Add a tiny local test HTTP server for deterministic fetch tests.
  - [x] Avoid external network dependency in CI by default; use
        `https://example.com/` only for a manual smoke command.
  - [x] Add a test mode that fetches from `127.0.0.1` over plain HTTP for local
        deterministic behavior.
  - [ ] Add an HTTPS fixture or controlled local TLS server before requiring
        HTTPS CI coverage.
  - [x] Track manual smoke commands in the experiment README.
  - [x] Add a cleanup checklist for temporary files, sockets, loop handles,
        futures, response bodies, and libcurl easy handles.
- [x] Define the runtime fetcher scope separately from build-time dependency
      fetching.
  - [x] Keep `dependencyFetch` as build-time source acquisition.
  - [x] Define runtime fetch as compiled-program behavior that lowers to native
        runtime calls.
  - [x] Require runtime fetch calls to work without Python tooling at program
        execution time.
  - [x] Decide the public namespace: use `standard.net` / `net.fetch*`, which
        cannot be confused with server-side `http.request*` and
        `http.response*`.
  - [x] Define MVP target as blocking HTTP/1.1 plus HTTPS, not HTTP/2.
  - [x] Defer HTTP/2 client support until TLS/ALPN and backend-library choices
        are settled.
- [ ] Design runtime fetch call targets.
  - [x] Add source-level request construction.
        Implemented as a backend-neutral `HttpGetRequest` record built with
        `new` / `fieldSet`, not as a public `http.clientRequest` handle.
  - [x] Add simple text fetch target.
        Implemented as backend-neutral `net.fetchText`.
  - [x] Add binary fetch target.
        Implemented as backend-neutral `net.fetchBytes`.
  - [ ] Add request-header syntax to `HttpGetRequest` or a future request
        builder API.
  - [x] Add request method support for GET.
  - [ ] Add request method support for POST.
  - [ ] Add request method support for PUT/PATCH/DELETE later.
  - [ ] Add request body text support.
  - [ ] Add request body bytes support.
  - [x] Add per-request timeout argument.
  - [x] Add max response body size argument.
  - [x] Add optional redirect policy argument.
        Implemented as `HttpGetRequest.policy.redirectLimit`.
  - [x] Add response status reader.
  - [x] Add response header reader.
  - [x] Add response body text reader.
  - [x] Add response body bytes reader.
  - [x] Add response body length reader.
  - [x] Add explicit response cleanup/free call if response memory is owned by
        the caller.
- [ ] Define source-level types for runtime fetch.
  - [x] Add or document `HttpGetRequest`.
  - [x] Add or document `HttpClientResponse` / `HttpTextResponse`.
  - [ ] Add or document generic `HttpMethod`.
        Current MVP encodes GET through the `HttpGetRequest` record.
  - [x] Add or document `HttpClientStatusCode`.
  - [ ] Add or document client-side `HttpHeaderName`.
  - [ ] Add or document client-side `HttpHeaderValue`.
  - [x] Add or document `Url`.
  - [x] Add or document `NetworkTimeoutMilliseconds`.
  - [x] Add or document `ResponseBodyLimitBytes`.
  - [x] Decide whether URLs are plain `CNullTerminatedByteString` in MVP or a
        trusted/sanitized domain type.
- [ ] Define runtime fetch effects and capabilities.
  - [x] Add canonical capability path `network.http.client`.
  - [x] Decide whether outbound request effects use `read`, `write`, or both.
  - [x] Require operations that perform outbound fetch to declare
        `effect OP write network.http.client` or the chosen equivalent.
  - [ ] Require operations that read response data to declare the matching
        response read effect if fetch and response inspection are separated.
  - [x] Add linter checks so runtime fetch wrappers cannot hide network
        effects.
  - [x] Ensure exported runtime-fetch wrappers carry effect edges in their
        public contract tape.
  - [x] Ensure imported runtime-fetch wrappers trigger `SS2542`-style caller
        effect propagation.
  - [ ] Add diagnostics that suggest reusable capabilities for
        `network.http.client`.
- [ ] Choose the native runtime backend.
  - [ ] Compare a small custom HTTP/1.1 client against libcurl.
  - [ ] Compare OS TLS APIs against OpenSSL/LibreSSL/BoringSSL.
  - [x] Decide that the async scheduler experiment uses libuv rather than
        custom epoll/kqueue/IOCP code.
  - [x] Decide that the HTTP fetcher experiment starts with libcurl rather than
        hand-rolled HTTP parsing and TLS.
  - [ ] Decide whether the production MVP uses libcurl for DNS, TLS,
        redirects, and HTTP parsing.
  - [x] Decide whether to vendor libcurl under `third_party/curl`, require a
        system/package-manager libcurl, or support both.
  - [x] Decide whether to vendor libuv under `third_party/libuv`, require a
        system/package-manager libuv, or support both.
  - [x] If libcurl is used, define minimum supported version.
  - [x] If libuv is used, define minimum supported version.
  - [ ] If a custom client is used, define DNS, socket, TLS, parser, redirect,
        and proxy boundaries explicitly.
  - [x] Keep the SemanticScript ABI small even if the backend library is large.
  - [x] Avoid exposing backend-library structs in generated SemanticScript ABI.
- [x] Add third-party dependency integration for libuv and libcurl.
  - [x] Add `third_party/libuv` as a pinned submodule or documented external
        dependency.
  - [x] Add libuv upstream URL, license, pin, and release-review row to
        `third_party/README.md`.
  - [x] Add `third_party/curl` as a pinned submodule or documented external
        dependency if production builds should not rely on system libcurl.
  - [x] Add libcurl upstream URL, license, pin, and release-review row to
        `third_party/README.md` if vendored.
  - [x] Add CMake discovery for libuv.
  - [x] Add CMake `FetchContent` fallback for pinned libuv when no system
        package is installed.
  - [x] Add CMake discovery for libcurl.
  - [x] Add CMake `FetchContent` fallback for pinned libcurl when no system
        package is installed.
  - [x] Add Windows dependency notes for libuv, libcurl, TLS backend, and DLL
        discovery.
  - [x] Add Linux dependency notes for libuv, libcurl, OpenSSL/CA bundle, and
        pkg-config.
  - [x] Add macOS dependency notes for libuv, libcurl, Secure Transport or
        OpenSSL, and Homebrew/system-library behavior.
  - [x] Add `sem doctor` checks for selected libuv/libcurl backend availability.
  - [x] Add an explicit no-network build mode so CI can compile the runtime
        without performing fetches.
- [x] Implement native runtime client ABI.
  - [x] Add `sem_http_client_*` declarations to the runtime header.
  - [x] Add request allocation/init function.
  - [x] Add request header setter.
  - [x] Add request body setter for text.
  - [x] Add request body setter for bytes.
  - [x] Add blocking execute/fetch function.
  - [x] Add response status getter.
  - [x] Add response header getter.
  - [x] Add response body text getter.
  - [x] Add response body bytes getter.
  - [x] Add response body length getter.
  - [x] Add response cleanup/free function.
  - [x] Return structured status codes from every runtime function.
  - [x] Keep all runtime-owned pointers valid until explicit cleanup or until
        the documented operation lifetime ends.
- [x] Implement native async fetch ABI over libuv.
  - [x] Add `SemanticScript/runtime/native_async/sem_async_runtime.h`.
  - [x] Add `SemanticScript/runtime/native_async/sem_async_runtime.c`.
  - [x] Add `SemanticScript/runtime/native_async/CMakeLists.txt`.
  - [x] Add `SemanticScript/runtime/native_http_client/sem_http_client_runtime.h`
        or a backend-neutral client header name.
  - [x] Add `SemanticScript/runtime/native_http_client/sem_http_client_runtime.c`.
  - [x] Add a future handle type such as `SSHttpFetchFuture`.
  - [x] Add `ss_http_client_fetch_text_start` that schedules work and returns a
        future handle.
  - [x] Add `ss_http_client_fetch_text_await` only for console/program-loop MVP
        experiments, with a note that production lowering should resume
        continuations instead of nested-running the loop.
  - [x] Add `ss_http_client_fetch_is_ready` so source-level wait sets can poll
        fetch futures without blocking on one specific call.
  - [x] Add `ss_http_client_fetch_status` to read the HTTP status code after
        completion.
  - [x] Add `ss_http_client_fetch_body_text` to read the buffered body after
        completion.
  - [x] Add `ss_http_client_fetch_error_code` for transport/runtime failures.
  - [x] Add `ss_http_client_fetch_free` to release future, response body, and
        backend handles.
  - [x] Use `uv_queue_work` plus libcurl easy API for the first experiment.
  - [x] Ensure the worker callback never touches generated SemanticScript frame
        state directly.
  - [x] Ensure the after-work callback runs on the libuv loop thread and marks
        the future ready.
  - [x] Add timeout support with `uv_timer_t`.
  - [x] Add cancellation bookkeeping before attempting hard cancellation of
        in-flight libcurl easy transfers.
  - [x] Add body-size enforcement in the write callback before reallocating.
  - [x] Add redirect-count enforcement through libcurl options.
  - [x] Add TLS verification enabled by default.
  - [ ] Add a compile-time diagnostic when libcurl was built without HTTPS
        support.
  - [x] Add a future migration note for replacing the worker-pool MVP with
        libcurl `multi_socket` integration.
  - [ ] Add a second-stage prototype that drives libcurl `multi_socket` through
        `uv_poll_t` instead of blocking a worker thread per fetch.
  - [ ] Compare worker-pool MVP behavior against `multi_socket` behavior for
        concurrent fetch count, cancellation latency, and memory ownership.
- [ ] Add compiler lowering for runtime fetch calls.
  - [x] Register runtime fetch call signatures in the compiler builtin surface.
  - [x] Register runtime fetch call signatures in semlint builtin signature
        tables.
  - [x] Lower typed `HttpGetRequest` record arguments to the native runtime
        fetch helper.
  - [ ] Lower header setters to the native runtime function.
  - [ ] Lower body setters to the native runtime function.
  - [x] Lower execute/fetch calls to the native runtime function.
  - [x] Lower typed `HttpTextResponse` record construction so `fieldGet`
        exposes response status and body from `net.fetchText`.
  - [x] Lower response cleanup/free calls to native runtime functions.
        Implemented as `net.freeTextBody` -> `ss_http_client_free_string`.
  - [x] Lower async `start fetchCall` to a future-start native call when the
        selected runtime backend is libuv.
  - [x] Lower source-level `await WAIT_SET` / `case CALL LABEL` / `done LABEL`
        blocks to readiness polling over fetch futures and generic
        user-operation futures.
  - [x] Make wait-set `case` selection the actual await/materialization point
        so handlers bind the selected call directly instead of awaiting it
        again.
  - [x] Reject double completion of the same future, including handler-side
        `await CALL` after `case CALL LABEL` and the same call appearing in a
        later wait set.
  - [x] Null consumed future slots after await so stale pointers cannot be
        reused by later waits.
  - [x] Record wait-set poll failures and route them through an unconsumed case
        instead of spinning forever on event-loop errors.
  - [ ] Lower `await fetchCall` to a continuation yield/resume point instead of
        a no-op when the selected runtime backend is libuv.
  - [ ] Spill live locals into an async operation frame before the generated
        yield point.
  - [ ] Generate a resume switch state for each `await`.
  - [ ] Generate cleanup blocks that free completed fetch futures on all return
        paths.
  - [x] Keep existing synchronous `start` / `await` lowering as the default
        backend until the libuv experiment is explicitly selected.
  - [x] Add provenance entries for generated async runtime symbols.
  - [ ] Add agent-readable compiler diagnostics for unsupported runtime fetch
        call targets.
  - [x] Keep runtime fetch target names synchronized across `semsc.py`,
        `semlint.py`, `SYNTAX.md`, and docs.
- [ ] Define TLS behavior.
  - [ ] Require HTTPS support for the runtime fetch MVP.
  - [ ] Decide platform TLS provider per OS.
  - [ ] Decide certificate trust-store behavior on Windows.
  - [ ] Decide certificate trust-store behavior on macOS.
  - [ ] Decide certificate trust-store behavior on Linux.
  - [x] Add diagnostic for TLS backend not available at link/runtime.
  - [x] Add option to reject insecure TLS by default.
  - [ ] Decide whether development builds can opt into insecure TLS for local
        test servers.
  - [ ] Ensure TLS errors map to typed SemanticScript errors.
- [ ] Define URL, redirect, and protocol rules.
  - [x] Reject unsupported schemes before network access.
  - [x] Support `https://` in MVP.
  - [ ] Decide whether `http://` is allowed for localhost/dev only or allowed
        generally with warning.
  - [x] Define max redirect count.
  - [ ] Define whether POST redirects preserve method/body.
  - [ ] Reject redirects from HTTPS to HTTP by default.
  - [ ] Define header-size limit.
  - [ ] Define status-line parsing limit.
  - [x] Define response body-size limit.
  - [x] Define timeout behavior for DNS, connect, TLS handshake, write, and
        response read.
- [ ] Define runtime fetch error model.
  - [ ] Add `HttpClientError` error domain.
  - [ ] Add DNS failure case.
  - [ ] Add connect failure case.
  - [ ] Add timeout case.
  - [ ] Add TLS handshake failure case.
  - [ ] Add certificate validation failure case.
  - [ ] Add invalid URL case.
  - [ ] Add unsupported scheme case.
  - [ ] Add request body too large case.
  - [ ] Add response body too large case.
  - [ ] Add malformed response case.
  - [ ] Add redirect limit exceeded case.
  - [ ] Decide whether non-2xx HTTP status is a transport success or typed
        application-level failure.
- [ ] Define memory ownership for runtime fetch.
  - [x] Decide whether simple `fetchText` copies body into runtime-owned memory
        or caller-owned heap memory.
  - [x] Add explicit cleanup rule for response bodies.
  - [ ] Add linter diagnostic for missing cleanup if cleanup is explicit.
  - [x] Ensure response header values have documented lifetime.
  - [x] Ensure response body bytes have documented lifetime.
  - [ ] Prevent use-after-free of response-owned pointers where the linter can
        prove it.
  - [x] Add max allocation guard before reading response body.
- [ ] Define blocking, async, and webserver interaction.
  - [x] Allow blocking runtime fetch in console programs for MVP.
  - [x] State explicitly that async plumbing is not required for the first
        runtime fetch MVP.
  - [x] Define blocking fetch as a synchronous native runtime call that owns the
        socket/TLS operation until it returns a response or error.
  - [x] Require every blocking fetch call to carry an explicit timeout value.
  - [ ] Reject or warn on blocking fetch calls that rely on an infinite/default
        timeout.
  - [ ] Define per-phase timeout defaults when the user supplies one aggregate
        timeout.
  - [x] Define max response body size as mandatory for blocking fetch helpers.
  - [x] Decide whether blocking fetch may be used in `main` and ordinary console
        operations with only an effect/capability proof.
  - [ ] Define warning when a native webserver handler performs blocking
        runtime fetch without timeout.
  - [ ] Require timeout/cancellation metadata for runtime fetch inside
        webserver handlers.
  - [ ] Add a linter rule that detects `net.fetch*` / future HTTP-client calls
        inside operations bound by `route` or `routeMiddleware`.
  - [ ] Add a linter rule that webserver-bound operations using blocking fetch
        must have a timeout row or a timeout argument on the fetch call.
  - [ ] Add a linter rule that webserver-bound operations using blocking fetch
        must declare the outbound network effect.
  - [ ] Add a linter rule that webserver-bound operations using blocking fetch
        should document backpressure/concurrency risk with `warning` or
        `invariant`.
  - [ ] Decide whether blocking fetch in webserver handlers is WARNING-only in
        dev and ERROR in prod/release build profiles.
  - [ ] Define runtime behavior when blocking fetch times out inside a handler:
        return typed error to handler, emit 500, or trap depending on the
        handler's error contract.
  - [ ] Define whether middleware is allowed to short-circuit after a failed
        outbound fetch.
  - [ ] Decide whether runtime fetch can be used inside middleware.
  - [ ] Add a gauntlet route that deliberately exercises blocking fetch through
        a local loopback server once runtime fetch exists.
  - [ ] Add a webserver test proving one blocking fetch pins the current
        single-threaded server loop until timeout/response.
  - [x] Add docs warning that current native webserver adapter is blocking and
        single-threaded.
  - [x] Defer async/event-loop integration until the native server adapter has
        an async story.
  - [x] Define future async fetch shape with `start`, `await`, `timeout`, and
        `cancelOn`.
  - [x] Define future async fetch as nonblocking runtime work, not just a
        blocking call hidden behind `start`.
  - [x] Define whether async fetch uses a worker-thread pool, nonblocking
        sockets, or platform event loops.
  - [ ] Define the MVP async backend options: select/poll, epoll/kqueue, IOCP,
        or a portable library.
  - [ ] Define how DNS resolution works in async mode.
  - [ ] Define how TLS handshakes are driven in async mode.
  - [ ] Define how cancellation interrupts connect, TLS handshake, request
        write, and response read phases.
  - [ ] Define how response body streaming works without buffering the entire
        body.
  - [ ] Define async fetch result ownership after `await`.
  - [ ] Define event-loop ownership for console programs.
  - [ ] Define event-loop ownership for native webserver programs.
  - [ ] Define whether the native webserver must become event-loop based before
        async fetch is allowed inside handlers.
  - [ ] Define how async fetch interacts with existing `taskGroup`,
        `startInGroup`, `awaitGroup`, `timeout`, and `cancelOn` rows.
  - [x] Add future tests for two concurrent async fetches completing out of
        order.
  - [x] Add positive, negative, edge-case, and generated fuzz-style coverage
        for `await WAIT_SET` / `case CALL LABEL` / `done LABEL` lowering and
        lint diagnostics.
  - [x] Add regression coverage for case-owned materialization, handler-side
        double-await rejection, repeated-call wait-set rejection, future-slot
        nulling, and generated IR that records event-loop poll failures.
  - [ ] Add runtime-level fault injection coverage for event-loop poll failures.
  - [ ] Add future tests for cancellation during DNS/connect/TLS/read.
- [ ] Define linker and distribution behavior.
  - [ ] Add platform-specific linker flags for the chosen HTTP/TLS backend.
  - [ ] Add Windows linker flags and DLL discovery rules.
  - [ ] Add macOS linker flags and framework/library rules.
  - [ ] Add Linux linker flags and package dependency notes.
  - [x] Add `sem doctor` checks for runtime fetch prerequisites.
  - [ ] Add build-profile behavior for statically linked versus dynamically
        linked HTTP client runtime.
  - [ ] Document how generated executables discover runtime client libraries.
- [ ] Add runtime fetch documentation and examples.
  - [x] Add `docs/language/native-http-client-api.md`.
  - [x] Add `SYNTAX.md` rows for runtime fetch call targets.
  - [x] Add `docs/toolchain/compiler.md` linker/runtime notes.
  - [ ] Add optimization-guide notes for agent-readable fetch errors.
  - [x] Add a minimal console `GET https://example.com` sample.
  - [ ] Add a JSON API fetch sample.
  - [ ] Add a POST body sample.
  - [ ] Add a timeout failure sample.
  - [ ] Add a TLS failure documentation example.
- [ ] Add runtime fetch tests.
  - [ ] Unit-test compiler lowering for every fetch call target.
    - [x] `net.fetchText` typed `HttpGetRequest` -> `HttpTextResponse`
          lowering.
    - [ ] `net.fetchBytes` lowering.
    - [ ] `net.freeTextBody` cleanup lowering.
  - [ ] Unit-test semlint builtin signature coverage.
  - [ ] Unit-test missing network capability diagnostic.
  - [ ] Unit-test imported fetch-wrapper effect propagation.
  - [x] Integration-test HTTP GET against a local test server.
  - [ ] Integration-test HTTPS GET against a controlled test server or fixture.
  - [ ] Integration-test request headers.
  - [x] Integration-test response headers.
  - [ ] Integration-test POST text body.
  - [ ] Integration-test binary response body.
  - [x] Integration-test timeout behavior.
  - [ ] Integration-test redirect policy.
  - [x] Integration-test max body-size failure.
  - [x] Repeat the real libuv/libcurl local fetch health demo enough times to
        catch obvious event-loop, timer, and cleanup flakiness.
  - [x] Add a native benchmark harness for the real libuv/libcurl async fetch
        path.
  - [x] Benchmark sustained local async fetch throughput with every response
        status, body, and length verified.
  - [x] Refine the public `standard.net` text-fetch API around typed
        request/response records instead of raw timeout/body-limit arguments.
  - [ ] Integration-test response cleanup under sanitizer or leak-check mode
        when available.

### Tests And `*.test.sem`

- [ ] Define colocated test file behavior.
  - [x] `*.test.sem` belongs to the same folder module as sibling source.
  - [x] Test files may access public exports by default.
  - [x] Decide whether tests may access private symbols in their same folder
        module.
  - [x] Reject test files that declare a different module path.
  - [x] Exclude `*.test.sem` from normal module-source selection.
  - [x] Include `*.test.sem` in `sem test`.
- [x] Define test import behavior.
  - [x] Tests can import sibling folder modules through normal imports.
  - [x] Tests can import dependency modules declared in `build.sem`.
  - [x] Tests can define test-only helper operations.
  - [x] Test-only helpers are not exported into production contract tape.
- [ ] Add test discovery diagnostics.
  - [ ] Test file without sibling module.
  - [ ] Test file outside `sourceRoot`.
  - [ ] Test file with wrong module declaration.
  - [ ] Test file accidentally included in production build.
- [ ] Add test layout tests.
  - [ ] Sibling `foo.test.sem` happy path.
  - [ ] Nested module test happy path.
  - [ ] Private symbol access decision enforced.
  - [ ] Test-only helper excluded from exports.

### Migration From Current Import/Module Behavior

- [ ] Audit existing `module` rows.
  - [ ] List files with source-level `module` rows that should move to
        `build.sem`.
  - [ ] Identify modules that can become build-owned folder modules unchanged.
  - [ ] Identify samples needing a root `build.sem`.
  - [ ] Identify stdlib modules needing relay entries in `std/module.sem`.
- [ ] Audit existing `importModule` usage.
  - [ ] List current import paths.
  - [ ] Decide compatibility period for `importModule DOTTED.PATH [as ALIAS]`.
  - [ ] Add migration diagnostics that suggest the new form.
  - [ ] Avoid breaking current `.sscript` / `.sem` tests before migration is
        staged.
- [ ] Add compatibility rules.
  - [x] Single-file scripts can keep old import behavior temporarily.
  - [x] Project builds through `build.sem` use registered module resolution.
  - [ ] Linter can warn on old form before compiler rejects it.
  - [x] Docs clearly mark filesystem/std-lib fallback as compatibility behavior.
- [ ] Add migration tests.
  - [x] Legacy single-file import still works during compatibility window.
  - [x] New project import works.
  - [ ] Mixed old/new imports produce clear diagnostics.
  - [ ] Migration suggestions include exact replacement rows.

## P1 - Developer Tooling Roadmap For A Real Language

This section tracks the toolchain needed for SemanticScript to feel like a
complete language instead of a set of implementation scripts. These are not all
required for the scoped 1.0 release, but they should guide the post-1.0 tooling
order.

### `semfmt` Formatter

- [x] Create a formatter entrypoint named `semfmt`.
  - [x] Decide whether `semfmt` lives under `SemanticScript/tools/`,
        `SemanticScript/formatter/`, or as a `sem fmt` subcommand wrapper.
  - [x] Add command help with examples for `.sscript` and `.sem` files.
  - [x] Support formatting one file.
  - [x] Support formatting multiple explicit files.
  - [x] Support recursive project formatting with include/exclude globs.
  - [x] Add `--check` mode for CI that exits non-zero on formatting drift.
  - [x] Add `--diff` mode that prints a unified diff without writing files.
  - [x] Add `--stdin-file-name` support for editor integrations.
- [ ] Make formatting parser-aware instead of regex-only.
  - [ ] Reuse the compiler/linter tokenizer or extract a shared tokenizer.
  - [ ] Preserve comments exactly unless indentation is intentionally adjusted.
  - [x] Preserve blank lines where they separate logical sections.
  - [x] Preserve quoted strings and escape sequences byte-for-byte.
  - [x] Preserve unknown/proposed verbs instead of deleting or rewriting them.
- [x] Define canonical row layout rules.
  - [x] Canonicalize one space between tokens.
  - [x] Trim trailing whitespace.
  - [x] Keep comments after code separated by at least two spaces if inline
        comments are allowed.
  - [x] Keep top-level declaration rows unindented.
  - [x] Decide whether operation body rows remain unindented or gain logical
        indentation in formatted output.
  - [x] Define maximum line length and whether long strings are never wrapped.
  - [x] Define how long metadata strings should be wrapped, if at all.
- [x] Define canonical ordering rules where safe.
  - [x] Decide whether formatter may reorder metadata rows.
  - [x] Keep operation metadata rows in source order; do not reorder to
        `purpose`, `input`, `output`, `effect`, `useCapability`, warnings, then
        invariants.
  - [x] Never reorder executable body rows unless a proof exists that behavior
        is unchanged.
  - [x] Never reorder route rows unless route precedence rules make ordering
        irrelevant.
- [ ] Add formatter configuration.
  - [x] Define formatter settings in `build.sem` or a future SemanticScript
        settings tape, not TOML.
  - [ ] Support line width.
  - [ ] Support newline mode.
  - [x] Support quote-preservation only, not quote-style rewrites.
  - [x] Document defaults as the canonical project style.
- [ ] Add formatter tests.
  - [x] Golden-format tests for small syntax examples.
  - [x] Golden-format tests for webserver apps.
  - [x] Golden-format tests for comments and blank lines.
  - [x] Golden-format tests for quoted strings with escaped characters.
  - [x] Idempotence tests: formatting twice produces byte-identical output.
  - [x] Safety tests: formatted source parses to the same high-level semantic
        tape as the original.
  - [ ] Fuzz tests for tokenizer/formatter round-tripping.
- [ ] Integrate formatter into editors and CI.
  - [ ] Add VS Code `DocumentFormattingEditProvider`.
  - [ ] Add format-on-save documentation.
  - [x] Add CI `semfmt --check` once formatting is stable.
  - [x] Add release checklist item requiring formatter clean output.

### `sem` Project Command Driver

- [x] Create a single daily-use command named `sem`.
  - [x] Decide implementation language for the first driver.
  - [x] Make the driver work from PowerShell on Windows.
  - [x] Make the driver work from POSIX shells.
  - [x] Add `sem --version`.
  - [x] Add `sem --help`.
  - [x] Add useful non-zero exit codes for scripting.
- [x] Wrap compiler commands.
- [x] Add `sem build`.
  - [x] Add `sem run`.
  - [x] Add `sem check` for parse, lint, and type/codegen validation.
  - [x] Add `sem emit-ir`.
  - [x] Add `sem clean` for ignored local build artifacts.
  - [x] Pass through `--build-profile dev|prod`.
  - [x] Pass through `--runtime-checks off|traps|panic`.
  - [x] Pass through `--persist-llvm-ir auto|yes|no`.
  - [x] Pass through `--opt-level`.
- [ ] Wrap quality tools.
  - [x] Add `sem lint`.
  - [x] Add `sem lint --engine semlint`.
  - [x] Add `sem lint --engine semlint`.
  - [x] Add `sem fmt`.
  - [x] Add `sem fmt --check`.
  - [x] Add `sem test`.
  - [ ] Add `sem doc`.
  - [x] Add `sem explain`.
  - [x] Add `sem bench`.
  - [x] Add `sem doctor`.
- [x] Add project discovery.
  - [x] Discover the nearest `build.sem`.
  - [x] Fall back to single-file mode when no build tape exists.
  - [x] Resolve source roots from `build.sem`.
  - [x] Resolve build output directories from `build.sem`.
  - [x] Resolve default entrypoints from `build.sem`.
  - [x] Resolve target runtime settings from `build.sem`.
- [ ] Add project templates.
  - [ ] Add `sem new console`.
  - [ ] Add `sem new web`.
  - [ ] Add `sem new library`.
  - [ ] Add `sem new package`.
  - [ ] Add template tests proving generated projects build.
- [x] Add toolchain environment checks.
  - [x] `sem doctor` checks Python version.
  - [x] `sem doctor` checks `llvmlite`.
  - [x] `sem doctor` checks clang or `SEMSC_CLANG`.
  - [x] `sem doctor` checks Node.js when VS Code extension tooling is needed.
  - [x] `sem doctor` checks native HTTP runtime build prerequisites.
  - [x] `sem doctor` prints concrete fix commands where possible.
- [ ] Add driver tests.
  - [ ] Unit-test argument parsing.
  - [ ] Test single-file build.
  - [x] Test build-tape-based build.
  - [ ] Test `sem check` failure reporting.
  - [ ] Test PowerShell examples.
  - [ ] Test POSIX examples in CI if a POSIX runner is available.

### `build.sem` Project Build Tape

- [x] Define the project build tape schema.
  - [x] Project name.
  - [x] Project version.
  - [x] License field.
  - [x] Source roots.
  - [x] Default entry operation.
  - [x] Build profiles.
  - [x] Runtime target.
  - [x] Native HTTP settings.
  - [x] Test roots.
  - [x] Formatter settings.
  - [x] Linter settings.
  - [x] Documentation output settings.
  - [x] LLVM build flags.
  - [x] Compiler-managed build folder settings.
- [x] Implement build-tape parsing.
  - [x] Add strict diagnostics for malformed project build rows.
  - [x] Add strict diagnostics for unknown top-level keys.
  - [x] Add strict diagnostics for missing required fields.
  - [x] Add path normalization on Windows and POSIX.
  - [x] Add tests for relative and absolute paths.
- [x] Integrate project build tapes with existing tools.
  - [x] `semsc.py` can accept a `build.sem`-driven build through `sem build`.
  - [x] `semlint.py` can lint a `build.sem` project.
  - [x] VS Code extension can discover project settings from `build.sem`.
  - [x] Future language server can use `build.sem` as the workspace root.
- [x] Document the project build tape.
  - [x] Add a minimal console app `build.sem` example.
  - [x] Add a native webserver `build.sem` example.
  - [x] Add a library/package `build.sem` example.
  - [x] Add a schema reference table.

### `semls` Language Server

- [ ] Create a language server entrypoint named `semls`.
  - [ ] Decide whether to implement JSON-RPC directly or use an LSP library.
  - [ ] Define startup options.
  - [ ] Define workspace-root discovery through `build.sem`.
  - [ ] Support single-file mode.
  - [ ] Add structured logging for LSP failures.
- [ ] Move VS Code-only intelligence into reusable language services.
  - [ ] Extract tokenizer and symbol index into shared code.
  - [ ] Extract hover generation into shared code.
  - [ ] Extract completion data into shared code.
  - [ ] Extract diagnostics conversion into shared code.
  - [ ] Keep the VS Code extension as a thin client once `semls` is stable.
- [ ] Implement core LSP features.
  - [ ] `textDocument/didOpen`.
  - [ ] `textDocument/didChange`.
  - [ ] `textDocument/didSave`.
  - [ ] `textDocument/hover`.
  - [ ] `textDocument/definition`.
  - [ ] `textDocument/references`.
  - [ ] `textDocument/documentSymbol`.
  - [ ] `workspace/symbol`.
  - [ ] `textDocument/completion`.
  - [ ] `textDocument/semanticTokens/full`.
  - [ ] `textDocument/formatting` backed by `semfmt`.
  - [ ] `textDocument/codeAction`.
  - [ ] `textDocument/rename` after symbol resolution is reliable.
- [ ] Implement diagnostics.
  - [ ] Run parser diagnostics incrementally.
  - [ ] Run `semlint.py` or equivalent stable diagnostics.
  - [ ] Run `semlint.py` structured diagnostics.
  - [ ] Debounce diagnostics on type.
  - [ ] Cancel stale diagnostics for older document versions.
  - [ ] Map diagnostic codes to `sem explain` documentation.
  - [ ] Add quick fixes where the edit is obvious and low-risk.
- [ ] Implement project awareness.
  - [ ] Resolve imports.
  - [ ] Build a cross-file symbol index.
  - [ ] Detect duplicate exported names.
  - [ ] Detect ambiguous unqualified references.
  - [ ] Support go-to-definition across imported files.
  - [ ] Support find-references across imported files.
- [ ] Add language-server tests.
  - [ ] Protocol-level tests for initialize/shutdown.
  - [ ] Hover snapshot tests.
  - [ ] Completion snapshot tests.
  - [ ] Definition/reference tests.
  - [ ] Diagnostic debounce/cancellation tests.
  - [ ] Workspace import-resolution tests.

### `sem test` Test Runner

- [ ] Define first-class SemanticScript test conventions.
  - [x] Decide test file naming rules.
  - [ ] Decide whether test operations use metadata or naming conventions.
  - [ ] Decide how fixtures are referenced.
  - [ ] Decide how expected failures are declared.
- [ ] Implement test discovery.
  - [ ] Discover tests from `build.sem` / `testPattern`.
  - [ ] Discover tests from default `tests/` roots.
  - [x] Support explicit file selection.
  - [ ] Support explicit test name filtering.
  - [ ] Support tags.
- [ ] Support test kinds.
  - [ ] Parse-only tests.
  - [ ] Lint-clean tests.
  - [ ] Compile-success tests.
  - [ ] Compile-fail tests with expected diagnostic codes.
  - [ ] Runtime-success tests.
  - [ ] Runtime-fail tests with expected crash/error output.
  - [ ] Golden stdout tests.
  - [ ] Golden stderr tests.
  - [ ] HTTP route tests.
  - [ ] Multipart upload tests.
  - [ ] SSE response tests.
  - [ ] Timeout/metadata tests.
- [ ] Add test output formats.
  - [ ] Human-readable console output.
  - [x] JSON output for agents and CI.
  - [ ] JUnit XML for CI systems.
  - [ ] Snapshot update mode for golden tests.
- [ ] Add test isolation.
  - [ ] Use temporary build directories.
  - [ ] Allocate non-conflicting local ports for web tests.
  - [ ] Kill child processes on timeout.
  - [ ] Clean generated executables and IR after each test unless debugging.
- [ ] Add test runner tests.
  - [x] Test discovery.
  - [x] Test success/failure exit codes.
  - [ ] Test compile-fail matching.
  - [ ] Test golden-output diff rendering.
  - [ ] Test webserver lifecycle cleanup.

### `semdoc` Documentation Generator

- [ ] Create a documentation generator entrypoint named `semdoc`.
  - [ ] Support `sem doc` as the primary user-facing wrapper.
  - [ ] Support Markdown output.
  - [ ] Support HTML output later if needed.
  - [ ] Support JSON output for agents.
- [ ] Extract source-level documentation.
  - [ ] Operations.
  - [ ] Inputs and outputs.
  - [ ] Effects.
  - [ ] Capabilities and authorities.
  - [ ] Records and fields.
  - [ ] Enums and error variants.
  - [ ] Web servers and route tables.
  - [ ] Route middleware and timeout metadata.
  - [ ] Warnings, invariants, security notes, and observability notes.
- [ ] Add cross-linking.
  - [ ] Link operation references to operation sections.
  - [ ] Link route handlers to operation sections.
  - [ ] Link capability uses to capability declarations.
  - [ ] Link diagnostic codes to `sem explain`.
- [ ] Add docs quality checks.
  - [ ] Warn when public operations lack `purpose`.
  - [ ] Warn when route handlers lack response behavior notes.
  - [ ] Warn when warnings/invariants reference missing operations or calls.
  - [ ] Warn when documented effects do not match declared effects.
- [ ] Add docs generator tests.
  - [ ] Snapshot generated docs for a console app.
  - [ ] Snapshot generated docs for a web app.
  - [ ] Snapshot generated docs for HTTP gauntlet.
  - [ ] Test broken references become diagnostics.

### `sem explain` Error Explainer

- [x] Create a first-pass error explainer entrypoint.
  - [x] Support `sem explain CODE`.
  - [ ] Support explaining compiler diagnostic codes.
  - [x] Support explaining `semlint.py` rules.
  - [x] Support explaining `semlint.py` diagnostic codes.
  - [x] Support explaining runtime panic codes such as `SSRUN001`.
- [x] Create a first-pass diagnostic knowledge base.
  - [x] Store code title.
  - [x] Store short explanation.
  - [x] Store why agents usually trigger it.
  - [x] Store common fixes.
  - [ ] Store bad/fixed source examples.
  - [x] Store related spec/doc links.
  - [ ] Store severity and category.
- [ ] Integrate explain output into tools.
  - [ ] Compiler diagnostics include `Run: sem explain CODE`.
  - [x] Linter diagnostics include explain links in JSON output.
  - [ ] VS Code hovers/code actions can open explain docs.
  - [ ] Language server diagnostics include `codeDescription` links.
- [ ] Add tests.
  - [ ] Every compiler diagnostic code has an explanation.
  - [ ] Every semlint diagnostic code has an explanation.
  - [ ] Examples in explanations parse or intentionally fail as documented.

### Agent Observability, Trace, Crash, And Debug Tooling

- [x] Treat this surface as machine-readable agent tooling, not human debugger UI.
  - [x] Prefer deterministic JSON/JSONL artifacts over prose.
  - [x] Include `schemaVersion`, tool version, source fingerprint, build fingerprint,
        build profile, runtime-check mode, LLVM target triple, and artifact paths.
  - [x] Keep optional human text as a view over structured data, never as the
        only output.
  - [x] Keep LLVM IR, optimized LLVM IR, trace maps, crash reports, profiles,
        and benchmark reports cross-linkable by stable ids.

- [x] Define source-to-runtime trace metadata.
  - [x] Map semantic tape rows to source file/line/column.
  - [x] Map generated LLVM blocks back to operation and call names.
  - [x] Map native runtime failures back to SemanticScript route/handler names.
  - [x] Emit a trace-map sidecar with stable `siteId` values for operations,
        calls, branches, returns, routes, handlers, runtime symbols, and link inputs.
  - [x] Preserve imported-source origins instead of only reporting the flattened
        resolved stream.
  - [x] Include source row text and redaction metadata so agents can patch near
        the right source without leaking sensitive values.
- [x] Add agent-oriented IR inspection.
  - [x] Add `sem inspect-ir`.
  - [x] Support JSON output by default.
  - [x] Show the source operation that produced each LLVM function.
  - [x] Show generated LLVM basic blocks by function.
  - [x] Show native ABI signatures for HTTP handlers.
  - [x] Show linked runtime source files and link args.
  - [x] Include trace-map ids in the IR inspection output.
- [x] Add trace execution mode.
  - [x] Add `sem run --trace`.
  - [x] Support JSONL output for streaming traces.
  - [x] Add trace output for operation entry/exit.
  - [x] Add trace output for call execution.
  - [x] Add trace output for branch decisions.
  - [x] Add trace output for returned values where safe.
  - [x] Include monotonic sequence ids and monotonic timestamps.
  - [x] Include operation/call/site ids matching the trace-map sidecar.
  - [x] Redact values from paths marked sensitive by future metadata.
- [x] Add agent profiling mode.
  - [x] Add `sem run --profile --json`.
  - [x] Aggregate hot operations, hot calls, branch frequencies, runtime external
        calls, startup time, wall time, and HTTP request counts where applicable.
  - [x] Keep profile summaries separate from exhaustive traces so agents can
        optimize without measuring trace overhead as application cost.
- [x] Add crash explanation mode.
  - [x] Add `sem run --explain-crash`.
  - [x] Run crashing programs in a subprocess so LLVM traps do not kill the tool
        driver.
  - [x] Support JSON output for agent triage.
  - [x] Capture runtime panic code.
  - [x] Capture SemanticScript stack/operation context.
  - [x] Capture direction message that hints at the likely fix.
  - [x] Capture build profile and runtime-check mode.
  - [x] Attach the last N trace events when trace data is available.
  - [x] Emit suspected category and fix candidates for agent patch planning.
  - [x] Keep prod profile output minimal by default.
- [x] Add optimization-loop integration.
  - [x] Define the agent loop: inspect IR, capture baseline profile/bench,
        patch source, run check/tests, re-profile/re-bench, compare artifacts.
  - [x] Preserve artifact indexes so agents can compare before/after runs.
  - [x] Report benchmark/profile deltas in stable JSON fields.
- [x] Add minimal debugger plan.
  - [x] Keep source-level semantic traces as the first release debugger surface.
  - [x] Defer LLDB/GDB integration until source representation, trace ids, and
        value representation are stable.
  - [x] Define breakpoint syntax if source-level breakpoints are added.
  - [x] Define watch/expression support only after value representation is
        stable.
  - [x] Document where native debugger integration adds value for LLVM backend
        failures versus where semantic trace data is better for agents.

### REPL And Scratch Runner

- [ ] Decide whether a REPL fits SemanticScript's file/operation model.
  - [ ] If yes, define how scratch operations are wrapped.
  - [ ] If no, document `sem scratch` as the supported interactive workflow.
- [ ] Add `sem scratch`.
  - [ ] Create a temporary source file.
  - [ ] Insert a minimal operation scaffold.
  - [ ] Compile/run the scratch file.
  - [ ] Preserve scratch files on failure for debugging.
- [ ] Add `sem run-snippet`.
  - [ ] Accept source from stdin.
  - [ ] Accept a named entry operation.
  - [ ] Print compiler/linter diagnostics with source snippets.
- [ ] Add tests for scratch/snippet workflows.

### `sem bench` Benchmark Tool

- [x] Create a benchmark entrypoint.
  - [x] Support `sem bench`.
  - [ ] Support `build.sem`-discovered benchmarks.
  - [ ] Support explicit benchmark files.
  - [x] Support warmup iterations.
  - [x] Support measured iterations.
  - [x] Support JSON output.
- [ ] Track benchmark dimensions.
  - [ ] Compile time.
  - [ ] Native executable size.
  - [x] Runtime duration.
  - [ ] Peak memory if practical.
  - [ ] HTTP requests per second for webserver benchmarks.
  - [ ] Startup latency for native webserver binaries.
- [ ] Add baseline benchmarks.
  - [ ] Console hello world.
  - [x] Numeric loop.
  - [x] String scanning.
  - [ ] JSON encode/decode once implemented.
  - [ ] TaskForge Web HTML shell route.
  - [ ] HTTP Runtime Gauntlet route matrix.
- [ ] Add benchmark guardrails.
  - [x] Store baselines outside normal source unless intentionally committed.
  - [x] Add tolerance thresholds.
  - [x] Avoid flaky wall-clock assertions in normal CI.
  - [x] Provide local comparison reports.

### Fuzzing And Property Testing

- [ ] Add parser fuzzing.
  - [ ] Fuzz token streams.
  - [ ] Fuzz quoted strings and escape sequences.
  - [ ] Fuzz comments and blank lines.
  - [ ] Assert parser never crashes.
  - [ ] Assert diagnostics stay source-located.
- [ ] Add formatter fuzzing.
  - [ ] Fuzz format round-trips.
  - [ ] Assert formatter is idempotent.
  - [ ] Assert formatted source still parses.
- [ ] Add linter fuzzing.
  - [ ] Fuzz operation/call graphs.
  - [ ] Fuzz route metadata.
  - [ ] Fuzz capability/effect paths.
  - [ ] Assert linter emits bounded diagnostics without exceptions.
- [ ] Add compiler fuzzing.
  - [ ] Generate small well-typed programs.
  - [ ] Generate expected-invalid programs.
  - [ ] Assert compiler never throws uncaught Python exceptions.
  - [ ] Assert invalid programs produce structured diagnostics.
- [ ] Add HTTP runtime fuzzing.
  - [ ] Fuzz request lines.
  - [ ] Fuzz headers.
  - [ ] Fuzz query strings.
  - [ ] Fuzz multipart boundaries.
  - [ ] Fuzz large bodies within configured limits.
  - [ ] Assert runtime returns controlled 4xx/5xx responses instead of
        crashing.
- [ ] Integrate fuzzing carefully.
  - [ ] Add short deterministic fuzz smoke tests to CI.
  - [ ] Add long fuzz jobs for manual/nightly runs.
  - [ ] Persist failure seeds.
  - [ ] Add minimization instructions.

### Package, Module, And Registry Tooling

- [x] Define package layout conventions.
  - [x] Source root.
  - [x] Test root.
  - [x] Generated output root.
  - [x] Documentation output root.
  - [x] Native runtime configuration root.
- [x] Define dependency syntax in `build.sem` or a SemanticScript lock/build
      tape.
  - [x] Local path dependencies.
  - [x] Git dependencies.
  - [x] Versioned registry dependencies later.
  - [x] Dependency feature flags later if needed.
- [ ] Add dependency resolution.
  - [x] Lockfile design.
  - [x] Reproducible dependency graph.
  - [ ] Clear diagnostics for missing dependencies.
  - [ ] Clear diagnostics for conflicting versions.
- [ ] Add package validation.
  - [ ] License present.
  - [ ] README present.
  - [ ] Public operations documented.
  - [ ] Tests pass.
  - [ ] No generated artifacts included.
- [x] Defer registry implementation until local/package workflow is stable.
  - [x] Document registry requirements.
  - [x] Define package signing or checksum expectations.
  - [x] Define ownership/namespace rules.

### Installer And Version Manager

- [x] Decide install strategy.
  - [x] Single archive download.
  - [x] Python package wrapper.
  - [x] Native launcher.
  - [x] Platform package managers later.
- [x] Create `semup` or equivalent version manager plan.
  - [x] Install a named SemanticScript version.
  - [x] Update to latest stable.
  - [x] Select active version per user.
  - [x] Select active version per project.
  - [x] Print installed versions.
- [ ] Add Windows support.
  - [ ] PowerShell installer script.
  - [ ] PATH setup instructions.
  - [ ] Toolchain detection.
  - [ ] Uninstall instructions.
- [ ] Add POSIX support.
  - [ ] Shell installer script.
  - [ ] PATH setup instructions.
  - [ ] Toolchain detection.
  - [ ] Uninstall instructions.
- [ ] Add release artifact checks.
  - [x] Checksums.
  - [x] Signature plan if needed.
  - [ ] Smoke test installed `sem`.
  - [ ] Smoke test installed VS Code extension package separately.

### Agent-Focused Tooling

- [x] Add machine-readable project context output.
  - [x] `sem context --json` summarizes project roots, entrypoints, tools, and
        supported syntax.
  - [x] Include compiler version.
  - [x] Include linter version.
  - [x] Include runtime feature flags.
  - [x] Include known xfail/deferred features.
- [x] Add machine-readable symbol graph output.
  - [x] `sem symbols --json`.
  - [x] Include operations, calls, inputs, outputs, effects, and routes.
  - [x] Include source locations.
  - [x] Include unresolved references.
- [ ] Add agent-safe fix suggestions.
  - [ ] Diagnostics should include minimal fix direction.
  - [ ] Diagnostics should distinguish safe automatic edits from human review
        edits.
  - [ ] Avoid suggestions that require broad refactors unless explicitly marked.
- [x] Add docs for agent workflows.
  - [x] How to run the fast validation set.
  - [x] How to inspect route/effect/capability graphs.
  - [x] How to safely update generated docs.
  - [x] How to avoid touching ignored build artifacts.

### Release, Packaging, And Repository Policy

- [x] Add MIT root `LICENSE`.
- [x] Align `vscode-semanticscript/package.json` license with root `LICENSE`.
- [ ] Decide VS Code publisher identity before marketplace publishing.
- [x] Align VS Code extension version with the release plan.
- [ ] Get to a release-clean worktree before tagging.
  - [ ] Commit or intentionally discard modified source/docs.
  - [ ] Commit or intentionally remove untracked README/doc files.
  - [x] Confirm generated `.exe`, `.ll`, `__pycache__`, `todos.json`, and
        `.vsix` artifacts are ignored and absent from source control.
- [x] Decide whether duplicate top-level `python/` and `python/`
      folders should both remain.
- [x] Decide whether `.sem` mirror files under `SemanticScript/sem/` should be
      tracked alias fixtures or generated artifacts.
- [x] Run and record aggressive validation before any 1.0 tag.
  - [x] Compiler unit tests.
  - [x] Standalone linter tests.
  - [x] Structured linter tests.
  - [x] Feature coverage tests.
  - [x] Bootstrap parity tests.
  - [x] Native HTTP webserver tests.
  - [x] Runtime CMake build.
  - [x] VS Code extension syntax/package checks.

### Initial Release Hardening Gaps

These items were identified after comparing the current release checklist,
`TODO.md`, release docs, and repository state. They are release-polish and
release-trust tasks that were either absent from this file or too implicit to
assign cleanly.

- [x] Define a single release version policy.
  - [x] Decide whether all first-party tools should share the same release
        version for the initial public release.
  - [x] Decide whether `semsc`, `semlint`, `semfmt`, `sem`, and the VS Code
        extension are independently versioned components or one product
        version.
  - [x] Record the decision in `RELEASE.md`.
  - [x] Record the decision in `docs/reference/release-hygiene.md`.
  - [x] Add a release version matrix listing each public command/package and
        its version.
  - [x] Include `SemanticScript/compiler/semsc.py`.
  - [x] Include `SemanticScript/linter/semlint.py`.
  - [x] Include `SemanticScript/formatter/semfmt.py`.
  - [x] Include `SemanticScript/tools/sem.py`.
  - [x] Include `vscode-semanticscript/package.json`.
  - [x] Align stale docs that still mention old VSIX versions.
  - [x] Update `README.md` if it references an older
        `semanticscript-vscode-*.vsix` artifact.
  - [x] Update `docs/reference/release-hygiene.md` if it references an older
        extension version.
  - [x] Add a simple release check that prints all tool versions.
  - [x] Decide whether mismatched tool versions fail a release check or are
        allowed when documented in the matrix.

- [ ] Add a real security contact before public release.
  - [ ] Replace the `TODO` contact placeholder in `SECURITY.md`.
  - [ ] Decide the reporting channel: email address, GitHub security advisory,
        private issue tracker, or another maintained channel.
  - [ ] Document expected acknowledgement timing.
  - [ ] Document expected fix/disclosure timing.
  - [ ] Document which versions are supported for security fixes.
  - [ ] Confirm the contact can receive reports before tagging a public
        release.
  - [x] Add a release checklist item that fails if `SECURITY.md` still contains
        a public-release contact placeholder.

- [ ] Add a third-party license and SBOM review.
  - [x] Inventory every directory under `third_party/`.
  - [x] Record upstream project name for each vendored dependency.
  - [x] Record upstream URL for each vendored dependency.
  - [x] Record pinned revision, release tag, or source acquisition date.
  - [x] Record license for `third_party/h2o`.
  - [x] Record license for `third_party/sqlite`.
  - [x] Preserve upstream license files in packaged source archives.
  - [x] Decide whether to add a root `NOTICE` file.
  - [x] Decide whether to add a machine-readable SBOM file.
  - [ ] If adding an SBOM, choose a format such as SPDX or CycloneDX.
  - [x] Document which release artifacts include third-party code.
  - [x] Document whether source-only releases and binary releases have
        different notice requirements.
  - [ ] Run a basic vulnerability review for vendored dependencies.
  - [ ] Record known CVE exceptions or "none known at release time" in release
        notes.
  - [x] Add a release checklist item that requires third-party license/SBOM
        review before tagging.

- [ ] Verify generated artifacts are removed from Git history.
  - [x] Define which historical artifacts are disallowed in repository history.
  - [x] Include generated `.exe` files.
  - [x] Include generated `.ll` files.
  - [x] Include generated `.bc`, `.obj`, `.o`, `.pdb`, `.res`, `.rc`, and
        native build folders.
  - [x] Include packaged `.vsix` files if the release policy keeps VSIX
        artifacts outside Git.
  - [x] Include local app data such as `todos.json`.
  - [x] Add a non-destructive history scan command to `RELEASE.md`.
  - [x] Run the history scan against all branches intended for release.
  - [x] Decide whether history rewriting is required before the first public
        push/tag.
  - [ ] If rewriting history, document the exact tool and command used.
  - [x] Prefer `git filter-repo` or another repeatable non-interactive tool for
        any required history rewrite.
  - [ ] Verify rewritten history still contains required source, docs, and test
        fixtures.
  - [x] Verify current `.gitignore` catches the same artifact classes after the
        history scrub.
  - [x] Record the final history-scan result in release notes.

- [ ] Make CI enforce the full release checklist.
  - [x] Compare `.github/workflows/ci.yml` against `RELEASE.md`.
  - [x] Add CI coverage for `SemanticScript/formatter/test_semfmt.py` if not
        already enforced.
  - [x] Add CI coverage for `SemanticScript/tests/test_compiler.py`.
  - [x] Add CI coverage for `SemanticScript/tests/test_stdlib.py`.
  - [x] Add CI coverage for `SemanticScript/tests/compare.py`.
  - [x] Add CI coverage for `SemanticScript/tests/sem_alias_parity.py`.
  - [ ] Add CI coverage for `apps/http-runtime-gauntlet/scripts/test_http_runtime_gauntlet.py`.
  - [ ] Add CI coverage for `apps/taskforge-web/scripts/test_taskforge_web.py`.
  - [ ] Add CI coverage for `apps/http-runtime-gauntlet/scripts/test_http_runtime_gauntlet.py`.
  - [ ] Add CI coverage for the native HTTP runtime CMake build where the
        runner toolchain supports it.
  - [ ] Add CI coverage for the native JSON runtime CMake build if it remains
        in the release scope.
  - [ ] Add CI coverage for the native SQLite runtime CMake build if it remains
        in the release scope.
  - [x] Add CI coverage for `npm --prefix vscode-semanticscript run check`.
  - [ ] Add optional CI coverage for `npm --prefix vscode-semanticscript run
        package:vsix` without uploading the artifact by default.
  - [ ] Run native executable tests on Windows CI, not only Linux.
  - [x] Run at least parse/lint/tooling checks on Linux CI.
  - [x] Document any release validation commands that intentionally remain
        manual.
  - [x] Add a release checklist item requiring CI green on the exact release
        commit.

- [x] Define the public 1.0 compatibility contract.
  - [x] Write down what `languageVersion PROJECT "1.0"` guarantees.
  - [x] Define which syntax rows are stable for 1.0.
  - [x] Define which syntax rows are preview, partial, metadata-only, or
        subject to change.
  - [x] Define whether `.sscript` and `.sem` have equal long-term support.
  - [x] Define whether `.sscript` remains canonical and `.sem` remains an alias.
  - [x] Define compatibility guarantees for `build.sem`.
  - [x] Define compatibility guarantees for module/import/export rows.
  - [x] Define compatibility guarantees for native HTTP APIs.
  - [x] Define compatibility guarantees for JSON runtime APIs currently in
        scope.
  - [x] Define compatibility guarantees for VS Code syntax highlighting and
        extension configuration keys.
  - [x] Define the deprecation process for syntax that changes after 1.0.
  - [x] Define whether future compiler versions warn before rejecting old 1.0
        syntax.
  - [x] Add the compatibility contract to `README.md` or a dedicated docs page.
  - [x] Link the compatibility contract from `RELEASE.md`.
  - [x] Link the compatibility contract from `SYNTAX.md`.

- [ ] Add a release artifact manifest.
  - [x] Define a manifest filename and location for each release.
  - [ ] Record release tag.
  - [ ] Record release commit SHA.
  - [ ] Record release date.
  - [ ] Record tool versions.
  - [ ] Record Python version used for release validation.
  - [ ] Record Node.js version used for VS Code extension validation.
  - [ ] Record clang/LLVM version used for native executable validation.
  - [ ] Record operating systems used for validation.
  - [ ] Record exact validation commands run.
  - [ ] Record skipped validation commands and the reason.
  - [ ] Record generated release artifacts such as source archive and VSIX.
  - [ ] Record artifact checksums.
  - [ ] Record whether signatures were generated.
  - [ ] Record known deferred features from `TODO.md`.
  - [ ] Record known deferred limitations.
  - [x] Add a release checklist item requiring the manifest before tagging.
  - [x] Decide whether manifests are committed, attached to GitHub releases, or
        both.

## P1 - Packaging, Install, And CI

- [x] Add dependency metadata for Python tooling.
  - [x] Document Python version requirements.
  - [x] Document `llvmlite` requirement.
  - [x] Document `clang` / `SEMSC_CLANG` requirement.
- [x] Add a repeatable release validation entrypoint.
  - [x] CI workflow or script for compiler unit tests.
  - [x] CI workflow or script for stdlib tests.
  - [x] CI workflow or script for semlint tests.
  - [x] CI workflow or script for extension syntax check.
  - [x] CI workflow or script for parity/feature coverage once green.
- [x] Add release process documentation.
  - [x] Required local commands.
  - [x] Artifact cleanup rules.
  - [x] Version bump rules.
  - [x] VSIX packaging rule.
- [x] Decide license before publishing.
  - [x] Use MIT for first-party source, docs, samples, and tooling.
  - [x] Add root `LICENSE`.
  - [x] Align `vscode-semanticscript/package.json` license.
- [x] Decide VS Code publisher/marketplace identity.
  - [x] Keep `publisher: semanticscript-local` for the initial local VSIX
        release; replace it only before publishing externally.
  - [x] Align extension version with release plan.

## P2 - Documentation Cleanup

- [x] Remove stale `experiments/` references from current docs.
  - [x] `README.md`.
  - [x] `SYNTAX.md`.
  - [x] `docs/ast.md`.
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
- [x] Decide whether the duplicate top-level `python/` and `python/`
      folders should both remain.
- [x] Decide whether `.sem` mirror files under `SemanticScript/sem/` should be
      tracked as alias fixtures or generated artifacts.
