<div align="center">

# SemanticScript

**A programming language where the *meaning* is the source code.**

Effects, authority, failure modes, cleanup, memory, and timing aren't comments or
conventions — they're first-class rows the compiler checks and an agent can grep.
One flat grammar. No hidden control flow. Built to be read and written by humans
*and* AI.

`v0.4.0-beta.1` · compiles to native via LLVM · ships an MCP server + 49 agent tools

[Quickstart](docs/getting-started.md) · [Language Guide](docs/LANGUAGE.md) · [Examples](examples/) · [Apps](apps/) · [Changelog](CHANGELOG.md)

</div>

---

## The big idea

Most languages let you *write* `fetch()` anywhere and *hope* the reviewer notices
it touches the network. SemanticScript makes you **declare** it — and then proves
you did:

```
main effect write console.stdout      # this operation writes to stdout…
main uses stdoutWriter                 # …under this capability…

stdoutWriter is capability
stdoutWriter grants write console.stdout   # …which is the only thing it's allowed to do.
```

If an operation performs an effect it didn't declare, or uses a capability that
doesn't grant that effect, the source lane reports it. `check --strict` is the
CI-style gate; the default `check` still exits 0 for warning-only findings and
tells you how many warnings were not enforced. The contract — *what can this code
touch, how can it fail, what must it clean up* — lives in the source, not in your
head. That's what makes a program legible to a reviewer, a linter, or an agent
before running it.

Every line is the same shape:

```
<subject>  <predicate>  <payload>
```

No braces, no nesting, no verb families to special-case. A program is a flat tape
of rows. Tools `grep` it, patch single rows, and validate one grammar.

---

## Hello, world

```
HelloWorld is project
HelloWorld target console
HelloWorld entry main

main is operation
main out ExitCode
main effect write console.stdout
main uses stdoutWriter
main purpose "Write a greeting and return an exit code"

main let greeting immutable String "hello world"
main do writeHello
main branch ifError writeHello goto failed
main return 0
main at failed return 1

writeHello is call
writeHello in main
writeHello invokes console.writeLine
writeHello arg text String greeting
writeHello catch writeError ConsoleWriteError

stdoutWriter is capability
stdoutWriter grants write console.stdout

ConsoleWriteError is error
ConsoleWriteError purpose "A console write failed"
ExitCode is alias
ExitCode for Int32
```

```sh
semanticscript run hello.sem
# hello world
```

Notice everything the operation does is *visible on its face*: it returns an
`ExitCode`, it writes to stdout, it does so under a named capability, the write
can fail with a typed error, and there's an explicit failure path. No surprises
hiding in a called function three files away.

---

## Core concepts in 60 seconds

**Entities** open with `<name> is <kind>` and are described by the rows that
follow. The kinds are the vocabulary of the language:

| Kind | What it is |
|---|---|
| `project` / `module` | the build manifest and its namespaces |
| `operation` | a function — with declared inputs, outputs, effects, and authority |
| `call` | one invocation inside an operation (its own rows: args, output, catch) |
| `capability` | a grant: the *only* effects an operation holding it may perform |
| `error` | a named, typed failure value |
| `alias` / `type` / `record` / `enum` | the type vocabulary |

**Operations declare their whole contract.** Inputs, output arity, typed
failure surface (`raises`), side effects, authority, heap use, and async-ness
are all rows:

```
addTwo is operation
addTwo in left Int64
addTwo in right Int64
addTwo out Int64
addTwo memory heap no            # makes no heap allocations
addTwo async no                  # runs to completion synchronously
addTwo invariant "Pure arithmetic; performs no effects"
addTwo do sumCall
addTwo return sumValue

sumCall is call
sumCall in addTwo
sumCall invokes math.addInt64
sumCall arg left Int64 left
sumCall arg right Int64 right
sumCall out sumValue Int64
```

An operation with no `effect` rows is provably pure — the linter knows it, and so
does any agent reading it.

**Calls are first-class rows, not buried expressions.** Every invocation names
what it `invokes`, its `arg`s, where its result is bound (`out`), and which
errors it may `catch`. You can read the entire call graph without parsing
expressions.

**Failure is data.** Errors are declared entities; operations branch on them
explicitly (`branch ifError <call> goto <label>`); there are no invisible
exceptions unwinding through your stack. Use `operation raises ErrorType` to
document an operation's possible errors, and use call-site `catch` plus
`branch ifError` to handle a specific fallible call.

> Full grammar, every predicate, and every entity kind: **[docs/LANGUAGE.md](docs/LANGUAGE.md)**.

---

## Why it reads well for AI agents

SemanticScript was designed assuming an agent — not just a human — would author,
review, and refactor it. That shows up across the toolchain:

- **One grammar to patch.** Every fact is an addressable `subject predicate
  payload` row. An agent adds a route, an effect, or a cleanup by *appending a
  row*, not by reformatting a block.
- **A built-in MCP server.** `semanticscript mcp` speaks JSON-RPC over stdio:
  `check`, `docs`, `graph`, `skills`, `search`, and more, each returning a
  stable, versioned `sem.<tool>.v1` JSON envelope.
- **50 structured CLI tools** for retrieval and reasoning — `semanticscript
  search "add a route"` does relevance-ranked retrieval across the diagnostics,
  skills, task templates, and spec; `explain SS1502` describes any diagnostic;
  `targets --signature TARGET` shows builtin arg slots/types; `reserved-words`
  lists the exact reserved-name set; `query effects <file>` extracts a
  program's effect set; `fix --plan` emits a repair plan whose `planUsable`
  field says whether `patch` can apply it.
- **Self-describing diagnostics.** 170 diagnostics, each with a tier, a summary,
  what was found, and a suggested fix.

The result: an agent can answer "what does this touch, how can it fail, where do
I add X" from the source alone.

Capabilities are a static source contract, not a runtime sandbox. Removing a
`uses` row does not revoke a live OS permission; it changes what the source
checker can authorize. A passing `check` means parse, lint, and LLVM lowering
passed; it does not mean "this program has been executed, tested, native-linked,
or sandboxed."

---

## What you can build

The toolchain JIT-runs programs and builds native executables; the runtime ships
real seams for sqlite, HTTP (winsock), JSON, bcrypt, structured logging, async,
events, and a headless widget tree. Worked, tested apps live in [`apps/`](apps/):

- 🌐 **JSON REST APIs** — a `webServer` entity lowers to a real route table; the
  `taskforge-web` app runs a full register → login → create → list round-trip
  against **sqlite + bcrypt + json + logging**.
- 🖥️ **Console & TUI apps** — an interactive TODO TUI renders, edits, and saves
  under a scripted keystroke stream.
- 🔌 **Network clients** — a self-contained HTTP-GET client over winsock.
- ⚡ **Async pipelines** — `async start/join/poll/cancel`, channels, timeouts,
  and graceful shutdown (see the `async_*` examples).
- 🧩 **Event-driven & GUI smoke runtimes** — in-process pub/sub and a headless
  control tree you can drive non-interactively.
- 🕸️ **WebAssembly** — `semanticscript wasm app.sem -o app.wasm` emits a module
  plus a CommonJS runner.

…and 180+ small, single-purpose [`examples/`](examples/) covering arithmetic, bit
ops, collections, closures, capabilities, conversions, and control flow — each
one runs and asserts its own result.

---

## Quickstart

```sh
git clone https://github.com/monstercameron/SemanticScript.git
cd SemanticScript
python -m pip install -r requirements.txt          # chiefly llvmlite (bundles LLVM)

# alias the compiler for convenience
alias semanticscript='python semanticscript/compiler/semanticscript.py'   # bash/zsh

semanticscript check examples/add_two.sem --json       # static diagnostics
semanticscript check examples/add_two.sem --strict     # stricter source gate
semanticscript run examples/hello_world.sem            # -> hello world
semanticscript build examples/add_two.sem -o add       # native executable
```

You need **Python 3.12** and, for native builds and the native runtime,
**clang** (or `zig cc`) on `PATH`. Pure console/compute programs JIT-run without
a C compiler. Full setup, project layout, and editor integration:
**[docs/getting-started.md](docs/getting-started.md)**.

---

## The toolchain

| Command | What it does |
|---|---|
| `run` | JIT-compile and execute a file or project directory |
| `build` / `wasm` | native executable / WebAssembly module + runner |
| `check` / `lint` | static parse+lint diagnostics; default allows warning-only success, `--strict` promotes T3 warnings |
| `verify` | one-shot check + discovered tests + run proof; use when "green means runnable" matters |
| `fmt` | canonical row formatting (`--check` for CI, `-w`/`--write` to update a file) |
| `fix` / `patch` | emit a repair plan; `patch` applies only plans with `planUsable:true` |
| `graph` / `query` / `symbols` / `deps` | call graph, effect/dimension queries, symbol & dependency views |
| `targets --signature` / `reserved-words` | discover builtin call signatures and reserved names |
| `docs` / `explain` / `search` / `skills` | semantic docs, diagnostic lookup, ranked retrieval, agent skills |
| `mcp` | run the MCP stdio server for agent integration |

`semanticscript --help` lists all 50 commands.

Use `check` to prove the source contract and that the compiler can lower it to
LLVM IR, then `verify`, `run`, `test`, or `build` to prove runtime behavior. The
`sem.check.v1` envelope says this explicitly: it includes
`lane: "static-source"`, `canCompile`, `compileProof`, warning counts, the active
strict policy, and replayable next commands for run/build verification.
`verify --strict <path>` packages the common check+test+run gate behind one
`sem.verify.v1` envelope.

---

## Project status

**Beta (`0.4.0-beta.1`).** The language, compiler, runtime, and toolchain are
feature-complete for the supported surface and heavily tested:

- ✅ 188 example programs run green (400+ assertions); 1,000+ pytest cases; the
  full CLI surface, the MCP server, and seven end-to-end apps are each gated in
  CI.
- ⚠️ **Validated on Windows/ARM64.** Linux/macOS binaries build but are not yet
  test-matrix-verified.
- ⚠️ **Distribution** is a frozen single-file binary (no `pip` package yet); the
  tagged release pipeline is wired but unproven on a tag.
- 🚧 Network/registry commands (`download`/`update`/`self`/…) are deferred — they
  need a package registry that doesn't exist yet. The offline dependency tooling
  (`deps`, `repin` with MVS + lockfile) is in place.

See [CHANGELOG.md](CHANGELOG.md) for the full pre-release gap list and
[docs/ROADMAP.md](docs/ROADMAP.md) for the path to 1.0.

---

## Documentation

- 🚀 **[Getting Started](docs/getting-started.md)** — install, first program, project layout
- 📖 **[Language Guide](docs/LANGUAGE.md)** — the complete grammar and every entity kind
- 🔤 **[Grammar](docs/GRAMMAR.md)** · 🗺️ **[Roadmap](docs/ROADMAP.md)** · 🔐 **[Security Matrix](docs/security-matrix.md)**
- 🧪 **[examples/](examples/)** and **[apps/](apps/)** — runnable, tested programs
- 📝 **[CONTRIBUTING.md](CONTRIBUTING.md)** · **[CHANGELOG.md](CHANGELOG.md)**

## License

See [LICENSE](LICENSE). Third-party attributions (SQLite, libuv, crypt_blowfish,
llvmlite/LLVM, CPython) are in [THIRD_PARTY_LICENSES.md](THIRD_PARTY_LICENSES.md).
