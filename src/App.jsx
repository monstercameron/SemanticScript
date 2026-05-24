import { Marked, Renderer } from "marked";

const repoUrl = "https://github.com/monstercameron/SemanticScript";
const docsUrl = `${repoUrl}/tree/main/docs`;
const benchmarksUrl = `${repoUrl}/tree/main/SemanticScript/bench`;

const escapeHtml = (value) =>
  String(value).replace(/[&<>"']/g, (char) => {
    const entities = {
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      '"': "&quot;",
      "'": "&#39;",
    };
    return entities[char];
  });

const normalizeLanguage = (value) =>
  String(value || "text")
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9_-]/g, "-");

const semanticKeywords = new Set([
  "all",
  "async",
  "auto",
  "condition",
  "error",
  "false",
  "heap",
  "immutable",
  "local",
  "module",
  "mutable",
  "no",
  "ok",
  "operation",
  "read",
  "readWrite",
  "source",
  "target",
  "true",
  "value",
  "void",
  "write",
  "yes",
]);

const semanticVerbs = new Set([
  "argument",
  "async",
  "bind",
  "branch",
  "call",
  "defer",
  "effect",
  "input",
  "invariant",
  "memory",
  "output",
  "purpose",
  "route",
  "run",
  "serverHost",
  "serverPort",
  "useCapability",
  "webServer",
]);

function classifySemanticToken(token, isFirstToken) {
  if (isFirstToken && semanticVerbs.has(token)) {
    return "sem-token sem-verb";
  }

  if (/^"(?:[^"\\]|\\.)*"$/.test(token)) {
    return "sem-token sem-string";
  }

  if (/^-?\d+(?:\.\d+)?$/.test(token)) {
    return "sem-token sem-number";
  }

  if (/^[A-Z][A-Za-z0-9]*(?:\.[A-Z][A-Za-z0-9]*)?$/.test(token)) {
    return "sem-token sem-type";
  }

  if (token.includes(".") || token.includes("/api/") || token.includes(":")) {
    return "sem-token sem-path";
  }

  if (semanticKeywords.has(token)) {
    return "sem-token sem-keyword";
  }

  return "sem-token";
}

function highlightSemanticScript(source) {
  return source
    .split("\n")
    .map((line) => {
      if (line.trimStart().startsWith("#")) {
        return `<span class="sem-comment">${escapeHtml(line)}</span>`;
      }

      let seenToken = false;
      return line.replace(/(\s+|"(?:[^"\\]|\\.)*"|[^\s"]+)/g, (part) => {
        if (/^\s+$/.test(part)) {
          return part;
        }

        const className = classifySemanticToken(part, !seenToken);
        seenToken = true;
        return `<span class="${className}">${escapeHtml(part)}</span>`;
      });
    })
    .join("\n");
}

const codeRenderer = new Renderer();
codeRenderer.code = ({ text, lang }) => {
  const language = normalizeLanguage(lang);
  const highlighted = language === "semanticscript" ? highlightSemanticScript(text) : escapeHtml(text);
  return `<pre class="markedPre language-${language}"><code class="language-${language}">${highlighted}</code></pre>`;
};

const markedCode = new Marked({
  async: false,
  gfm: true,
  renderer: codeRenderer,
});

function CodeBlock({ children, language = "semanticscript", className = "" }) {
  const code = String(children).trimEnd();
  const markdown = `\`\`\`${language}\n${code}\n\`\`\``;
  const html = String(markedCode.parse(markdown, { async: false }));

  return (
    <div
      className={`markedSnippet marked-${normalizeLanguage(language)} ${className}`.trim()}
      dangerouslySetInnerHTML={{ __html: html }}
    />
  );
}

const proofPoints = [
  {
    label: "Public status",
    value: "0.0.1 pre-release",
    detail:
      "No stable public release has shipped yet. The README, roadmap, compatibility doc, and syntax inventory are the source of truth for what is ready.",
  },
  {
    label: "Reference compiler",
    value: "LLVM + sem.exe",
    detail:
      "The source compiler parses .sscript and .sem, emits LLVM IR, JIT-runs, links native executables, and can be packaged into a single-file Windows sem.exe.",
  },
  {
    label: "Tooling contract",
    value: "Python or exe",
    detail:
      "The sem CLI exposes validation, graph/slice retrieval, repair planning, patching, readiness checks, and test orchestration from either source Python or the packaged executable.",
  },
  {
    label: "Runtime demos",
    value: "Curated apps",
    detail:
      "TaskForge TUI, HTML Template Lab, HTTP Runtime Gauntlet, TaskForge Web, TaskForge API Client, and GUI smoke fixtures exercise real app surfaces.",
  },
];

const quickstartCommands = `python -m pip install -r requirements.txt -c constraints.txt
python SemanticScript\\tools\\sem.py --version --json
python SemanticScript\\tools\\sem.py check --json SemanticScript\\tests\\agent_cli_demo.test.sem
python SemanticScript\\tools\\sem.py test --json SemanticScript\\tests\\agent_cli_demo.test.sem --skip-python-harnesses`;

const localCompilerCommands = `python -m pip install -r requirements.txt -c constraints.txt
python -m pip install pyinstaller==6.20.0
python -m PyInstaller --noconfirm --clean packaging/pyinstaller/sem.spec
.\\dist\\sem.exe version --json
.\\dist\\sem.exe check --json SemanticScript\\tests\\agent_cli_demo.test.sem`;

const notReadyItems = [
  "No stable public release has been published yet; the current public status is 0.0.1 pre-release.",
  "TaskForge Web is a preview proof point, not a polished product; GET /api/todos/:id is intentionally still a documented 501 gap.",
  "Package fetching, registry workflow, language server, generated docs, installer/version manager, H2O/HTTP/2, WinUI 3, and top-level declarative GUI rows remain future or preview work.",
  "Record JSON codecs and outbound standard.net are documented partial or experimental surfaces unless a narrower inventory row says otherwise.",
];

const statusFacts = [
  ["Release status", "0.0.1 pre-release", "No stable public release has been published yet."],
  ["Syntax inventory", "362 implemented / 93 partial", "Reported by sem.version.v1 after rebasing onto main."],
  ["Benchmark harness", "4 cases / 0 failures", "Fresh local C-baseline run after the rebase."],
  ["Packaging path", "PyInstaller sem.exe", "Local onefile compiler builds through packaging/pyinstaller/sem.spec."],
  ["Merge artifact", "main builds sem.exe", "Every PR merge to main now produces a validated Windows compiler artifact."],
];

const valueProps = [
  "Patches target rows instead of nested expression trees.",
  "Diffs reveal changed effects, failure paths, routes, storage, and capabilities.",
  "Agents can retrieve one operation, route, capability, or failure path and still have the context needed to edit it.",
  "The compiler can erase source redundancy; reviewers and tools keep the facts that make maintenance safer.",
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
useCapability createTodoHandler httpRequestReader
useCapability createTodoHandler httpResponseWriter
useCapability createTodoHandler sqliteDatabaseReadWriter
memory createTodoHandler heap auto
async createTodoHandler no
purpose operation createTodoHandler "Create one todo owned by the authenticated session user."
invariant operation createTodoHandler "The user id comes from the session, never from request JSON."`,
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
  { name: "arith", c: "45", semantic: "45", percent: "100.0%", status: "passed" },
  { name: "memset", c: "179", semantic: "179", percent: "100.0%", status: "passed" },
  { name: "math", c: "39", semantic: "40", percent: "97.5%", status: "passed" },
  { name: "strlen", c: "0", semantic: "0", percent: "too fast", status: "inconclusive" },
];

const docs = [
  ["Overview", `${repoUrl}/blob/main/docs/overview.md`, "Compact public overview of the language, toolchain, runtime areas, and status."],
  ["Quickstart", `${repoUrl}#quickstart`, "Install dependencies, check the green fixture, scaffold a project, and run CI lanes."],
  ["Roadmap", `${repoUrl}/blob/main/docs/reference/roadmap.md`, "Pre-release status, demo status, release readiness goals, and backlog policy."],
  ["Agent workflows", `${repoUrl}/blob/main/docs/toolchain/agent-workflows.md`, "The stable check, graph, slice, fix, patch, and test loop."],
  ["Syntax inventory", `${repoUrl}/blob/main/docs/reference/syntax-inventory.md`, "Implementation status for committed, partial, and proposed rows."],
  ["Compatibility", `${repoUrl}/blob/main/docs/reference/compatibility.md`, "The 1.0 support boundary and preview/future surfaces."],
  ["Single executable", `${repoUrl}/blob/main/docs/reference/single-executable-toolchain.md`, "PyInstaller onefile packaging path for a future sem.exe release artifact."],
  ["Benchmarks", benchmarksUrl, "Small C baseline comparisons for optimizer and backend performance investigation."],
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
            <p className="eyebrow">0.0.1 pre-release - agent-first application language</p>
            <h1>Make agent edits smaller, safer, and reviewable.</h1>
            <p className="lead">
              SemanticScript is a compiled application language built around explicit,
              line-addressable source records. Operations name effects, capabilities, storage,
              memory behavior, failure paths, runtime edges, and review intent directly in source.
              You can run it from a checkout today or package the compiler/toolchain as `sem.exe`.
            </p>
            <div className="ctaRow">
              <a className="button primary" href={`${repoUrl}#quickstart`}>
                Start with the sem loop
              </a>
              <a className="button ghost" href={repoUrl}>
                View repository
              </a>
            </div>
          </div>

          <aside className="heroPanel" aria-label="Core thesis">
            <div className="panelLabel">Core bet</div>
            <CodeBlock language="text">{`Do not minimize source.
Maximize recoverable context.`}</CodeBlock>
            <p>
              Terse source makes agents reconstruct hidden meaning before every edit. SemanticScript
              spends source text so the next correct edit is easier to infer, verify, and review.
            </p>
          </aside>
        </div>

        <article className="quickstartCard" aria-label="Try SemanticScript in two minutes">
          <div>
            <p className="eyebrow">Try in 2 minutes</p>
            <h2>Prove the source checkout path before reading the manifesto.</h2>
            <p>
              These commands install the Python dependencies, inspect tool/runtime feature flags,
              parse and lint the green fixture, then run the semantic test lane. In this worktree,
              `check` returned `status: "ok"` and `test` returned `status: "passed"`.
            </p>
          </div>
          <CodeBlock language="powershell">{quickstartCommands}</CodeBlock>
        </article>

        <article className="compilerCard" aria-label="Build the compiler executable locally">
          <div>
            <p className="eyebrow">Compiler executable</p>
            <h2>Python is the dev path, not the only path.</h2>
            <p>
              The repo includes a PyInstaller spec and launcher that bundle the compiler, sem CLI,
              docs, skills, stdlib, runtime folders, and llvmlite support into `dist\sem.exe`. Tagged
              GitHub Releases publish the same style of Windows compiler artifact, and every PR merge
              to `main` now builds a fresh validated artifact.
            </p>
          </div>
          <CodeBlock language="powershell">{localCompilerCommands}</CodeBlock>
        </article>

        <div className="factStrip" aria-label="Current repository facts from main">
          {statusFacts.map(([label, value, detail]) => (
            <article className="factCard" key={label}>
              <p>{label}</p>
              <strong>{value}</strong>
              <span>{detail}</span>
            </article>
          ))}
        </div>
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
            <CodeBlock language="javascript">{`app.post("/api/todos", async (req, res) => {
  const user = sessionUser(req)
  const body = validateTodo(req.body)
  await db.insertTodo(user.id, body.title)
  res.status(201).json({ ok: true })
})`}</CodeBlock>
          </article>

          <article className="compareCard strongCard">
            <h3>SemanticScript edit target</h3>
            <p>
              The route row, effect rows, invariant, capabilities, call records, and failure labels are
              stable patch targets. `sem slice --route POST:/api/todos --json apps\taskforge-web`
              can retrieve the relevant neighborhood before an edit.
            </p>
            <CodeBlock>{`route taskForgeWebServer POST "/api/todos" createTodoHandler
effect createTodoHandler read http.request.body
effect createTodoHandler readWrite database
effect createTodoHandler write http.response
invariant operation createTodoHandler "The user id comes from the session, never request JSON."
useCapability createTodoHandler httpRequestReader
useCapability createTodoHandler sqliteDatabaseReadWriter`}</CodeBlock>
          </article>
        </div>
      </section>

      <section className="section proof" id="prototype">
        <div className="sectionHeader compact">
          <p className="eyebrow">Current prototype</p>
          <h2>Pre-release, but not vaporware.</h2>
          <p>
            The repository contains a working compiler, linter, formatter, sem CLI, PyInstaller
            compiler packaging, VS Code extension, native runtime adapters, release definitions, and
            curated app demos. Some rows are partial, and the compatibility docs say exactly where.
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
              <CodeBlock>{item.code}</CodeBlock>
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
              dynamic dispatch, global state, and ambient runtime behavior. That compression is
              pleasant while writing code and expensive while repairing it.
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
            "Every executable row does one semantic thing.",
            "Failure is typed dataflow, not ambient exception control.",
            "Cleanup lives near acquisition.",
            "Effects and runtime authority are declared, not inferred.",
            "Types encode intent, trust, memory, and layout.",
            "Routes, SQL, JSON, HTML, and native runtime boundaries are source facts.",
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
                `python SemanticScript\bench\run_benchmarks.py --json`, 7 measured runs, clang
                O2, clock ticks. These are smoke numbers for optimizer/backend work, not
                publication-grade claims.
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
              Current read: arith, memset, and math pass the harness gate in this run; strlen is too
              small for the clock probe and stays inconclusive. The important engineering asset is the
              harness: backend performance regressions become visible and repeatable.
            </p>
            <a className="inlineLink" href={benchmarksUrl}>
              Inspect the benchmark sources and runner
            </a>
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
        <CodeBlock language="powershell" className="commandBlock">{`python SemanticScript\\tools\\sem.py --version --json
python SemanticScript\\tools\\sem.py skills get sem sem-agent --json
python SemanticScript\\tools\\sem.py check --json PATH
python SemanticScript\\tools\\sem.py graph --kind summary --json PATH
python SemanticScript\\tools\\sem.py slice --operation NAME --json PATH
python SemanticScript\\tools\\sem.py fix --plan --json PATH
python SemanticScript\\tools\\sem.py patch --dry-run --json plan.json
python SemanticScript\\tools\\sem.py test --json PATH`}</CodeBlock>
      </section>

      <section className="section docs" id="docs">
        <div className="sectionHeader compact">
          <p className="eyebrow">High-level documentation map</p>
          <h2>Where engineers should drill in.</h2>
          <p>
            The website is the pitch. The linked repository docs are the source of truth for exact
            command behavior, syntax support, release status, and compatibility boundaries.
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
            retrievable semantic neighborhoods, native compilation, a packaged compiler path, and
            visible performance work. The project is early, but it is pointed at a real maintenance
            problem rather than a decorative syntax experiment.
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
