const repoUrl = "https://github.com/monstercameron/SemanticScript";
const docsUrl = `${repoUrl}/tree/main/docs`;

const proofPoints = [
  {
    label: "Reference compiler",
    value: "LLVM now",
    detail:
      "Python compiler parses .sscript and .sem, resolves modules, emits LLVM IR through llvmlite, JIT-runs, and links native executables with clang.",
  },
  {
    label: "Agent interface",
    value: "JSON loops",
    detail:
      "The sem wrapper exposes version, skills, check, graph, slice, explain, fix-plan, patch, readiness, dev, size, and test payloads for reliable agent work.",
  },
  {
    label: "Application surface",
    value: "Real demos",
    detail:
      "TaskForge Web, TaskForge TUI, HTTP runtime gauntlet, HTML template lab, GUI smoke fixtures, and a Kilo editor stress port exercise app-level code.",
  },
  {
    label: "Native adapters",
    value: "Small edges",
    detail:
      "Implemented and preview HTTP, SQLite, JSON, bcrypt, HTML, terminal, GUI, async/event, and outbound network work stay behind explicit standard-library and runtime boundaries.",
  },
];

const quickstartCommands = `python -m pip install -r requirements.txt -c constraints.txt
python SemanticScript\\tools\\sem.py --version --json
python SemanticScript\\tools\\sem.py check --json SemanticScript\\tests\\agent_cli_demo.test.sem
python SemanticScript\\tools\\sem.py test --json SemanticScript\\tests\\agent_cli_demo.test.sem --skip-python-harnesses`;

const notReadyItems = [
  "Package registry and dependency fetching are still future work.",
  "Full language-server, generated-docs, installer, and version-manager workflows are not done.",
  "Record JSON codecs, outbound standard.net, async/event topology, H2O/HTTP/2, and WinUI 3 remain preview or partial surfaces.",
  "The benchmark harness is useful, but the math microbenchmark currently misses the 90% of C gate.",
];

const valueProps = [
  "Patches target rows instead of nested expression trees.",
  "Diffs reveal changed effects, failure paths, routes, storage, and capabilities.",
  "Agents can retrieve one operation, route, capability, or failure path and still have the context needed to edit it.",
  "The compiler can erase source redundancy; reviewers and tools keep the redundant facts that make maintenance safer.",
];

const mechanics = [
  {
    title: "Operations carry their review packet",
    copy:
      "Purpose, effects, memory, async behavior, invariants, and authority live at the operation boundary before the implementation details begin.",
    code: `operation createTodoHandler
input operation createTodoHandler request HttpRequest
input operation createTodoHandler response HttpResponse
output operation createTodoHandler Int32
effect createTodoHandler read http.request.body
effect createTodoHandler readWrite database
effect createTodoHandler write http.response
memory createTodoHandler heap auto
async createTodoHandler no
purpose operation createTodoHandler "Create one todo owned by the authenticated session user."
invariant operation createTodoHandler "The user id comes from the session, never request JSON."`,
  },
  {
    title: "Calls are named dataflow",
    copy:
      "A call has an identity. Each argument edge is addressable. Success and failure bind as data instead of disappearing into ambient exception control.",
    code: `call openDatabaseCall sqlite.openDatabase
argument openDatabaseCall path String databasePath
argument openDatabaseCall mode SqliteOpenMode readWriteCreateSqliteOpenMode
run openDatabaseCall
bind ok openedDatabase SqliteDatabase openDatabaseCall
bind error openDatabaseError SqliteOpenFailure openDatabaseCall
branch error source openDatabaseCall target openDatabaseFailed
defer closeDatabaseDefer sqlite.closeDatabase openedDatabase`,
  },
  {
    title: "Routes are source facts",
    copy:
      "Route tables are greppable, diffable, lintable records rather than framework side effects hidden in callbacks.",
    code: `webServer taskForgeWebServer
serverHost taskForgeWebServer "127.0.0.1"
serverPort taskForgeWebServer 18090
route taskForgeWebServer GET "/" homePageHandler
route taskForgeWebServer POST "/api/auth/register" registerHandler
route taskForgeWebServer GET "/api/todos" listTodosHandler
route taskForgeWebServer POST "/api/todos/:id/complete" completeTodoHandler
route taskForgeWebServer GET "*" notFoundPageHandler`,
  },
];

const benchmarkRows = [
  { name: "arith", c: "51", semantic: "50", percent: "102.0%", status: "passed" },
  { name: "memset", c: "226", semantic: "230", percent: "98.3%", status: "passed" },
  { name: "math", c: "47", semantic: "57", percent: "82.5%", status: "needs optimizer work" },
  { name: "strlen", c: "0", semantic: "0", percent: "too fast", status: "inconclusive" },
];

const docs = [
  ["Start here", `${repoUrl}#start-here`, "Install, scaffold, check, and test with the sem wrapper."],
  ["Language theory", `${repoUrl}/blob/main/docs/semantic-script.md`, "The context-maxxing thesis, root laws, and boundary rules."],
  ["Agent workflows", `${repoUrl}/blob/main/docs/toolchain/agent-workflows.md`, "The stable check, graph, slice, fix, patch, and test loop."],
  ["Compiler", `${repoUrl}/blob/main/docs/toolchain/compiler.md`, "Current parser, LLVM, JIT, native executable, strictness, and build behavior."],
  ["Syntax inventory", `${repoUrl}/blob/main/docs/reference/syntax-inventory.md`, "Implementation status for committed, partial, and proposed rows."],
  ["Compatibility", `${repoUrl}/blob/main/docs/reference/compatibility.md`, "The 1.0 support boundary and preview/future surfaces."],
];

function App() {
  return (
    <main>
      <section className="hero" id="top">
        <nav className="nav" aria-label="Primary navigation">
          <a href="#proof-example">Proof</a>
          <a href="#mechanics">Mechanics</a>
          <a href="#evidence">Evidence</a>
          <a href="#workflow">Workflow</a>
          <a href="#docs">Docs</a>
        </nav>

        <div className="heroGrid">
          <div className="heroCopy">
            <p className="eyebrow">Agent-first application language</p>
            <h1>Make agent edits smaller, safer, and reviewable.</h1>
            <p className="lead">
              SemanticScript is a compiled application language built around a flat semantic
              tape. Every executable row is a named, checkable fact: calls, arguments, effects,
              failures, memory behavior, authority, routes, and cleanup become addressable source.
            </p>
            <div className="ctaRow">
              <a className="button primary" href={`${repoUrl}#start-here`}>
                Start with the sem loop
              </a>
              <a className="button ghost" href={repoUrl}>
                View repository
              </a>
            </div>
          </div>

          <aside className="heroPanel" aria-label="Core thesis">
            <div className="panelLabel">Core bet</div>
            <pre>{`Do not minimize source.
Maximize recoverable context.`}</pre>
            <p>
              Terse source makes agents reconstruct hidden meaning before every edit. SemanticScript
              spends source text so the next correct edit is easier to infer, verify, and review.
            </p>
          </aside>
        </div>

        <article className="quickstartCard" aria-label="Try SemanticScript in two minutes">
          <div>
            <p className="eyebrow">Try in 2 minutes</p>
            <h2>Prove the green path before reading the manifesto.</h2>
            <p>
              These commands install the Python dependencies, inspect tool/runtime feature flags,
              parse and lint the green fixture, then run the semantic test lane. In this worktree,
              `check` returned `status: "ok"` and `test` returned `status: "passed"`.
            </p>
          </div>
          <pre>{quickstartCommands}</pre>
        </article>
      </section>

      <section className="section sell" id="sell">
        <div className="sectionHeader">
          <p className="eyebrow">The sell</p>
          <h2>The source is already a fact table.</h2>
          <p>
            SemanticScript is not trying to make developers type less. It is trying to make
            consequential software easier to audit and patch after agents become part of the
            maintenance path.
          </p>
        </div>
        <div className="valueGrid">
          {valueProps.map((item) => (
            <article className="valueCard" key={item}>
              <span />
              <p>{item}</p>
            </article>
          ))}
        </div>
      </section>

      <section className="section proofExample" id="proof-example">
        <div className="sectionHeader">
          <p className="eyebrow">Differentiated proof</p>
          <h2>The useful primitive is not English syntax. It is retrievable risk.</h2>
          <p>
            A normal handler makes reviewers and agents infer which request fields are trusted, which
            resources are touched, and where failures escape. SemanticScript puts those facts in rows
            that graph, slice, lint, and patch tools can address directly.
          </p>
        </div>
        <div className="compareGrid">
          <article className="compareCard mutedCard">
            <h3>Conventional service handler</h3>
            <p>
              The route, auth source, body parsing, database mutation, response write, and failure
              behavior may be split across decorators, middleware, framework defaults, and nested
              expressions. An agent has to reconstruct the contract before editing.
            </p>
            <pre>{`app.post("/api/todos", async (req, res) => {
  const user = sessionUser(req)
  const body = validateTodo(req.body)
  await db.insertTodo(user.id, body.title)
  res.status(201).json({ ok: true })
})`}</pre>
          </article>

          <article className="compareCard strongCard">
            <h3>SemanticScript edit target</h3>
            <p>
              The route row, effect rows, invariant, capabilities, call records, and failure labels are
              stable patch targets. `sem slice --route POST:/api/todos --json apps\\taskforge-web`
              can retrieve the relevant neighborhood before an edit.
            </p>
            <pre>{`route taskForgeWebServer POST "/api/todos" createTodoHandler
effect createTodoHandler read http.request.body
effect createTodoHandler readWrite database
effect createTodoHandler write http.response
invariant operation createTodoHandler "The user id comes from the session, never request JSON."
useCapability createTodoHandler httpRequestReader
useCapability createTodoHandler sqliteDatabaseReadWriter`}</pre>
          </article>
        </div>
      </section>

      <section className="section proof" id="prototype">
        <div className="sectionHeader compact">
          <p className="eyebrow">Current prototype</p>
          <h2>Not just syntax notes.</h2>
          <p>
            The repository contains a working compiler/toolchain, runnable app demos, native runtime
            adapters, a VS Code extension, and public compatibility docs. Some surfaces are still
            partial, but the core loop is executable and inspectable today.
          </p>
        </div>
        <div className="proofGrid">
          {proofPoints.map((point) => (
            <article className="proofCard" key={point.label}>
              <p className="proofValue">{point.value}</p>
              <h3>{point.label}</h3>
              <p>{point.detail}</p>
            </article>
          ))}
        </div>
        <aside className="notReadyCard" aria-label="Not ready yet">
          <div>
            <p className="eyebrow">Not ready yet</p>
            <h3>Early, but intentionally scoped.</h3>
          </div>
          <ul>
            {notReadyItems.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </aside>
      </section>

      <section className="section mechanics" id="mechanics">
        <div className="sectionHeader">
          <p className="eyebrow">Prototype mechanics</p>
          <h2>Longer source, smaller edit uncertainty.</h2>
          <p>
            The surface rejects expression soup, implicit exceptions, framework magic, and hidden
            async. The reward is local reasoning: a single retrieved operation can explain what it
            reads, writes, allocates, awaits, trusts, and returns.
          </p>
        </div>
        <div className="mechanicStack">
          {mechanics.map((item) => (
            <article className="mechanicCard" key={item.title}>
              <div>
                <h3>{item.title}</h3>
                <p>{item.copy}</p>
              </div>
              <pre>{item.code}</pre>
            </article>
          ))}
        </div>
      </section>

      <section className="section theory" id="theory">
        <div className="split">
          <div>
            <p className="eyebrow">Theory</p>
            <h2>Context maxxing is an engineering constraint.</h2>
          </div>
          <div className="theoryCopy">
            <p>
              Conventional languages compress meaning into nesting, scope, inference, exceptions,
              object shape, framework convention, and runtime behavior. That compression is pleasant
              while writing code and expensive while repairing it.
            </p>
            <p>
              SemanticScript flips the tradeoff: expand intent into named rows, make hidden behavior
              illegal by default, and let compilers remove redundancy after tools and reviewers have
              used it.
            </p>
          </div>
        </div>
        <div className="lawGrid">
          {[
            "Every executable line does one semantic thing.",
            "Failure is explicit dataflow.",
            "Cleanup lives next to acquisition.",
            "Async is structured, bounded, and cancellable.",
            "Types encode intent, trust, memory, and layout.",
            "Control flow is graphable.",
          ].map((law) => (
            <p key={law}>{law}</p>
          ))}
        </div>
      </section>

      <section className="section evidence" id="evidence">
        <div className="sectionHeader compact">
          <p className="eyebrow">Research and benchmarks</p>
          <h2>Current validation, openly scoped.</h2>
          <p>
            The research notes ask what a language should look like when the primary reader,
            debugger, and maintainer is an AI agent. The benchmark harness checks whether the
            explicit source shape can still lower toward native C performance without hiding gaps.
          </p>
        </div>

        <div className="evidenceGrid">
          <article className="researchCard">
            <h3>Design research signals accepted into the language</h3>
            <ul>
              <li>Explicit local context, descriptive names, and variant words help agents recover facts.</li>
              <li>Raw perplexity wins are filtered through greppability, patchability, auditability, and compiler ownership.</li>
              <li>Verb-led rows stayed competitive after syntax arena tests for compliance, locality, patch, search, and modality.</li>
              <li>Sigils, anonymous facts, object-like fact blocks, and dotted fact markers were rejected when they made long-lived source harder to own.</li>
            </ul>
          </article>

          <article className="benchmarkCard">
            <div className="benchmarkIntro">
              <h3>Fresh local microbenchmark run</h3>
              <p>
                `python SemanticScript\\bench\\run_benchmarks.py --json`, 7 measured runs, clang
                O2, clock ticks. These are smoke numbers, not publication-grade claims.
              </p>
            </div>
            <div className="tableWrap">
              <table>
                <thead>
                  <tr>
                    <th>Case</th>
                    <th>C median ticks</th>
                    <th>Semantic median ticks</th>
                    <th>Of C</th>
                    <th>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {benchmarkRows.map((row) => (
                    <tr key={row.name}>
                      <td>{row.name}</td>
                      <td>{row.c}</td>
                      <td>{row.semantic}</td>
                      <td>{row.percent}</td>
                      <td>{row.status}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="benchmarkNote">
              Honest read: arith and memset are close to C in this run, strlen is too small for the
              clock probe, and math currently misses the 90% gate. The useful thing is the harness:
              performance regressions are visible instead of rhetorical.
            </p>
          </article>
        </div>
      </section>

      <section className="section workflow" id="workflow">
        <div className="sectionHeader">
          <p className="eyebrow">How the project should work</p>
          <h2>The sem wrapper is the stable agent contract.</h2>
          <p>
            Engineers and agents should use the same loop: load repo-matched rules, prove source
            state, retrieve the smallest useful graph slice, explain diagnostics, generate a reviewable
            repair plan, patch, format, check, and only then run behavior harnesses.
          </p>
        </div>
        <div className="workflowRail" aria-label="SemanticScript workflow">
          {[
            "skills get",
            "check",
            "graph / slice",
            "explain",
            "fix --plan",
            "patch",
            "fmt / check",
            "test / dev",
          ].map((step, index) => (
            <div className="workflowStep" key={step}>
              <span>{String(index + 1).padStart(2, "0")}</span>
              <p>{step}</p>
            </div>
          ))}
        </div>
        <pre className="commandBlock">{`python SemanticScript\\tools\\sem.py --version --json
python SemanticScript\\tools\\sem.py skills get sem sem-agent --json
python SemanticScript\\tools\\sem.py check --json PATH
python SemanticScript\\tools\\sem.py graph --kind summary --json PATH
python SemanticScript\\tools\\sem.py slice --operation NAME --json PATH
python SemanticScript\\tools\\sem.py fix --plan --json PATH
python SemanticScript\\tools\\sem.py patch --dry-run --json plan.json
python SemanticScript\\tools\\sem.py test --json PATH`}</pre>
      </section>

      <section className="section docs" id="docs">
        <div className="sectionHeader compact">
          <p className="eyebrow">High-level documentation map</p>
          <h2>Where engineers should drill in.</h2>
          <p>
            The website is the pitch. The linked repository docs are the source of truth for exact
            command behavior, syntax support, and compatibility boundaries.
          </p>
        </div>
        <div className="docsGrid">
          {docs.map(([title, href, copy]) => (
            <a className="docCard" href={href} key={title}>
              <h3>{title}</h3>
              <p>{copy}</p>
            </a>
          ))}
        </div>
      </section>

      <section className="section closing" id="interest">
        <div className="closingCard">
          <p className="eyebrow">Who should care</p>
          <h2>Use this if your next codebase will be edited by agents anyway.</h2>
          <p>
            SemanticScript is for engineers who want app code with explicit contracts, diffable risk,
            retrievable semantic neighborhoods, and native compilation. The project is early, but it
            is pointed at a real maintenance problem rather than a decorative syntax experiment.
          </p>
          <div className="ctaRow">
            <a className="button primary" href={docsUrl}>
              Read the docs
            </a>
            <a className="button ghost" href={`${repoUrl}/issues`}>
              Challenge the design
            </a>
          </div>
        </div>
      </section>
    </main>
  );
}

export default App;
