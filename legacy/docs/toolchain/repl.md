# Snippet Eval (`sem eval`)

`sem eval` JIT-runs a SemanticScript snippet (or a full program) without
hand-writing the project shell. It is the fast inner loop for agents that want
to execute a few rows and read the result as structured JSON, and it powers the
`eval` MCP tool.

It does not invent a second runtime: a snippet is wrapped in the minimal console
program shape, written to a temporary file, and compiled + JIT-executed by the
reference compiler (`semsc.py --run`). The payload is `sem.eval.v1`.

## Usage

```powershell
# Inline rows
python SemanticScript\tools\sem.py eval --code "storage local immutable n Int64 42`ncall p console.writeIntegerLine`nargument p value Int64 n`nrun p"

# A snippet or full-program file
python SemanticScript\tools\sem.py eval PATH

# From stdin
type SNIPPET.txt | python SemanticScript\tools\sem.py eval -

# Human-readable instead of JSON
python SemanticScript\tools\sem.py eval --human --code "<rows>"
```

JSON is the default output. `--human` prints program stdout plus a one-line
status. Other flags: `--show-source` (include the wrapped program),
`--max-output-bytes N` (default 65536, must be >= 1), `--timeout SECONDS`
(default 30, must be >= 1 — the wall-clock bound is a safety control for a
surface that runs arbitrary compiled code).

## Snippet contract

A snippet is a sequence of **operation-body rows** — `storage local`, `call` /
`argument` / `run`, `bind` / `ignore` / `branch` / `label` / `makeError`,
`set`, `jump`, `return`, and the like. The wrapper builds a `project` /
`target console` / `runtime native 1` / `module` / `entry console main` header
and an `operation main` around them.

These **module-level declarations are hoisted** above `operation main` so a
snippet can bring its own context: `import`, `error`, `errorCase`, `record`,
`field`, `enum`, `enumCase`, `capability`, `type`, `alias`, `sharedState`, and
`storage module`.

When the snippet references `console.`, the wrapper adds the stdout effect
(`effect main write console.stdout` + `authority main write console.stdout`) so
prints work with no ceremony. It does **not** generate error handling for the
snippet's own fallible calls — an un-disposed `console.writeLine` produces an
advisory note (SS3106), which is informational and does not stop the run.

If no top-level `return` is present, the wrapper appends a success return
(`ExitCode 0`).

### Full programs

A snippet that declares its own `project`, `operation`, or `entry` is treated as
a complete program and compiled verbatim (`mode: "program"`, `lineOffset: 0`).
Use full-program input when you need operation metadata the snippet wrapper does
not generate — non-stdout effects, custom output types, `async`, multiple
operations, and so on.

A full program with **no `entry` row** compiles in *library mode*: the compiler
builds a stub `main` that returns 0, so nothing the author wrote runs. This is
flagged (`libraryMode: true`, advisory note `SSEVAL001`, and a `nextCommands`
entry) so an empty exit-0 result is never silently mistaken for a successful
run.

## Non-strict execution

`eval` runs in **non-strict** mode. A program with strict-blocking linter notes
(for example deprecated rows the backend still tolerates) is still executed, and
the notes are reported rather than treated as fatal. Execution is only refused
when codegen genuinely fails. Diagnostics are grouped by origin:

- `notes.linter` — agent-safety and style findings from the linter.
- `notes.compiler` — parser/codegen findings from the compiler probe.

The merged, sorted stream is also available as `diagnostics`. For wrapped
snippets each diagnostic span gains `wrappedLine` (line in the generated program)
and, when it falls in the body, `snippetLine` (best-effort snippet-relative
line); `lineOffset` is the number of generated header lines.

## Outcome (`status` and `ok`)

`ok` means the eval harness compiled and ran the program to completion — it is
**not** the program's exit code. Read `execution.exitCode` for that, and
`status` for the classification:

| status          | meaning                                                        |
| --------------- | -------------------------------------------------------------- |
| `ok`            | ran to completion, exit code 0                                 |
| `nonzero-exit`  | ran to completion, program chose a non-zero exit code          |
| `crashed`       | launched but never returned (runtime fault in the JIT)         |
| `compile-failed`| codegen failed; see `output.stderr` and `notes`                |
| `native-runtime-unavailable` | refused before launch because the snippet calls a native runtime adapter not linked by eval |
| `timeout`       | abandoned after `--timeout` seconds                            |
| `input-error`   | the snippet/path could not be read                             |

"Ran to completion" is detected from a metrics sentinel the compiler emits only
after `cmain()` returns normally (see below). A crash is distinguished from a
compile failure by the abnormal-termination signal — a negative exit code
(POSIX signal) or an NTSTATUS-style Windows code — rather than by guessing from
output.

For non-`ok` outcomes the payload carries `nextCommands` (e.g. `sem check` /
`sem fix` for `compile-failed`, a larger `--timeout` for `timeout`), following
the same machine-facing convention as other `sem` surfaces.

`sem eval` is the JIT runner, not the native target pipeline. It refuses obvious
native-runtime adapter calls such as `sqlite.*`, `http.*`, `bcrypt.*`, `json.*`,
`net.*`, `event.*`, and `gui.*` before launch with
`status: "native-runtime-unavailable"` and `execution.ran: false`. Build those
programs with `sem build ... -- --emit-exe` instead.

`sem test --json` reports this split explicitly for `.test.sem` files. Each
semantic result includes `sourceCheck`, `jitExecution`, `nativeExecution`, and
`runtimeCoverage`; the top-level `coverageSummary` counts source checks, JIT
contract attempts, and native runtime harness attempts separately. Test files
whose metadata says they are built and run as a native exe are not JIT-run first;
`sem test` builds the executable, runs it when supported, or reports
`runtimeHarnessStatus: "unsupported"` with the native build reason instead of
classifying a JIT crash as a semantic assertion failure.

## Execution metrics

When the program runs to completion, `execution` carries:

- `timing.executeNs` / `executeUs` — **execution only** (the JIT'd `cmain()`
  call), measured inside the compiler process. This is the honest "how fast did
  the program run" number.
- `timing.totalNs` / `totalUs` — wall clock for the whole hop (Python startup +
  compile + JIT + execute), and `timing.compileNs` = total − execute.
- `memory.peakWorkingSetBytes` / `peakWorkingSetKib` with a `source`
  (`GetProcessMemoryInfo` on Windows, `getrusage` on POSIX, or `unavailable`).
  This is the **whole-process** peak (compiler + JIT + program), a proxy for
  program memory, not a program-only heap figure.

`output` reports captured streams as both a string and a line array
(`stdout` / `stdoutLines`, `stderr` / `stderrLines`), a `byteCount` (the true
pre-cap size), and `truncated` when the byte cap was hit.

### The `--run-metrics` compiler flag

`semsc.py --run --run-metrics` times only program execution, captures the peak
working set, and prints a single `__SEM_RUN_METRICS__ {json}` line to stderr
before exiting. Program stdout is left untouched. `sem eval` strips and parses
this line; it never leaks into the reported streams.

The sentinel embeds a per-run nonce supplied via the `SEM_RUN_METRICS_NONCE`
environment variable. `sem eval` generates a fresh nonce per run and accepts
only a sentinel whose nonce matches, which rejects accidental look-alikes and
casual spoofing; unauthenticated look-alike lines are preserved as the program
output they are. This is best-effort telemetry, not a security boundary — `eval`
runs arbitrary native code, and a determined program could read the nonce from
its environment and forge a line. Only the cosmetic metrics would be affected.

## Security

`eval` JIT-compiles and runs arbitrary native code. Over the MCP HTTP transport
that is remote code execution for any client that can reach the bind address —
keep the server on a loopback host unless the network is trusted. The stdio
transport (the default) is in-process and not network-reachable.
