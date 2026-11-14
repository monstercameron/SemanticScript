import { useEffect, useState } from "react";
import { Marked, Renderer } from "marked";
import semanticLogoCard from "../docs/assets/semanticscript-logo-card.png";
import semanticMascot from "../docs/assets/semanticscript-mascot.png";

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

const genericKeywords = {
  javascript: new Set([
    "async",
    "await",
    "const",
    "function",
    "return",
    "true",
    "false",
    "null",
    "let",
    "var",
    "if",
    "else",
    "for",
    "while",
    "new",
    "import",
    "from",
  ]),
  c: new Set([
    "const",
    "double",
    "for",
    "if",
    "int",
    "long",
    "return",
    "size_t",
    "void",
    "while",
  ]),
  json: new Set(["true", "false", "null"]),
  llvm: new Set([
    "define",
    "declare",
    "entry",
    "br",
    "call",
    "ret",
    "load",
    "store",
    "add",
    "sub",
    "mul",
    "icmp",
    "private",
    "unnamed_addr",
    "constant",
  ]),
  powershell: new Set(["python", "sem.exe", "clang", "node"]),
  python: new Set([
    "class",
    "def",
    "return",
    "from",
    "import",
    "for",
    "in",
    "if",
    "else",
    "elif",
    "raise",
    "with",
    "as",
    "None",
    "True",
    "False",
  ]),
};

const codeTokenPattern =
  /(\/\/.*|#.*|"(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*'|`(?:[^`\\]|\\.)*`|-{1,2}[A-Za-z][\w-]*|%[A-Za-z_.$][\w.$-]*|@[A-Za-z_.$][\w.$-]*|\b\d+(?:\.\d+)?\b|\b[A-Za-z_$][\w$.-]*\b|[{}()[\],.:=])/g;

function classifyGenericToken(token, language) {
  if (token.startsWith("//") || token.startsWith("#")) {
    return "code-token code-comment";
  }

  if (/^["'`]/.test(token)) {
    return "code-token code-string";
  }

  if (/^-{1,2}[A-Za-z]/.test(token)) {
    return "code-token code-flag";
  }

  if (/^[@%][A-Za-z_.$]/.test(token)) {
    return "code-token code-symbol";
  }

  if (/^\d/.test(token)) {
    return "code-token code-number";
  }

  if (genericKeywords[language]?.has(token)) {
    return "code-token code-keyword";
  }

  if (/^[A-Z][A-Za-z0-9_$]*$/.test(token)) {
    return "code-token code-type";
  }

  if (token.includes(".") || token.includes("\\") || token.includes("/")) {
    return "code-token code-path";
  }

  if (/^[{}()[\],.:=]$/.test(token)) {
    return "code-token code-punctuation";
  }

  return "code-token";
}

function highlightGeneric(source, language) {
  let highlighted = "";
  let cursor = 0;

  for (const match of source.matchAll(codeTokenPattern)) {
    highlighted += escapeHtml(source.slice(cursor, match.index));
    highlighted += `<span class="${classifyGenericToken(match[0], language)}">${escapeHtml(match[0])}</span>`;
    cursor = match.index + match[0].length;
  }

  return highlighted + escapeHtml(source.slice(cursor));
}

function highlightCode(source, language) {
  if (language === "semanticscript") {
    return highlightSemanticScript(source);
  }

  if (["c", "javascript", "json", "llvm", "powershell", "python"].includes(language)) {
    return highlightGeneric(source, language);
  }

  return escapeHtml(source);
}

const codeRenderer = new Renderer();
codeRenderer.code = ({ text, lang }) => {
  const language = normalizeLanguage(lang);
  const highlighted = highlightCode(text, language);
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

const releaseCommands = `.\\sem.exe version --json
.\\sem.exe skills get sem sem-agent --json
.\\sem.exe check --json SemanticScript\\tests\\agent_cli_demo.test.sem
.\\sem.exe graph --kind summary --json SemanticScript\\tests\\agent_cli_demo.test.sem
.\\sem.exe test --json SemanticScript\\tests\\agent_cli_demo.test.sem`;

const compilerPipeline = `SemanticScript source rows
  -> parser + AST records
  -> semantic validation and linter diagnostics
  -> lowering into LLVM IR
  -> LLVM optimization / JIT / object emission
  -> native executable or sem.exe command result`;

const llvmIrSnippet = `define i32 @main() {
entry:
  %total = call i64 @ss_math_add_i64(i64 %subtotal, i64 %tax)
  %ok = icmp sgt i64 %total, 0
  br i1 %ok, label %return_ok, label %return_error
return_ok:
  ret i32 0
return_error:
  ret i32 1
}`;

const statusFacts = [
  ["Release artifact", "single sem.exe", "Release builds package the compiler and public tool surfaces into one Windows executable."],
  ["Reference compiler", "LLVM IR prototype backend", "The compiler lowers explicit source rows into LLVM IR so the prototype can reuse LLVM optimization, JIT, and native codegen paths."],
  ["Tooling", "sem.exe JSON contract", "Agents and humans use the same check, graph, slice, fix, patch, readiness, and test surfaces."],
  ["Apps", "Curated runtime demos", "TaskForge, HTTP, GUI, HTML, and API-client examples exercise concrete application edges."],
];

const sourceProperties = [
  ["Flat record tape", "One line is one semantic record. The first token is the verb, so edits have stable row-level targets."],
  ["Explicit authority", "Effects, capabilities, memory behavior, cleanup, and failure paths are data instead of hidden framework behavior."],
  ["Tool-readable slices", "The CLI can retrieve operation, route, capability, and failure neighborhoods without loading the whole project."],
  ["Compiler-owned redundancy", "The source stays descriptive for review; the compiler lowers away repetition in the executable path."],
];

const syntaxRationaleRows = [
  ["Verb-first records", "The first token declares the row shape, so the remaining slots have a narrower prediction space."],
  ["Named semantic edges", "Call names, argument names, bind names, and branch labels repeat the local contract instead of hiding it in nesting."],
  ["Low grammar switching", "No infix expressions, brace scopes, comma calls, implicit async, or exceptions means fewer competing parse modes."],
  ["Attention anchors", "Effects, capabilities, failures, and memory policy stay adjacent to the operation that owns them."],
];

const syntaxRationaleCode = `operation createTodo
effect createTodo read http.request.body
effect createTodo write http.response
useCapability createTodo httpRequestReader
call decodeCall json.decodeTodoRequest
argument decodeCall source RawJson requestBody
run decodeCall
bind ok todo TodoCreateRequest decodeCall
bind error decodeError JsonDecodeError decodeCall
branch error source decodeCall target invalidJson`;

const mechanics = [
  {
    title: "Operation boundary",
    copy:
      "The operation declares inputs, outputs, effects, authority, memory policy, async behavior, intent, and invariants before calls begin.",
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
    title: "Named dataflow",
    copy:
      "Calls, arguments, run records, success bindings, error bindings, and branches are separate facts that can be searched and patched.",
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
    title: "Route inventory",
    copy:
      "Routes are explicit records. The handler graph is available to lint, slice, and review without reconstructing framework registration.",
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

const algorithmBenchmarkRows = [
  {
    name: "fib_recursive",
    stress: "call / recursion",
    checksum: "63245986",
    c: "1.00x",
    semantic: "1.16x",
    javascript: "3.87x",
    python: "83.7x",
  },
  {
    name: "collatz",
    stress: "integer branches",
    checksum: "131434424",
    c: "1.00x",
    semantic: "0.98x",
    javascript: "8.75x",
    python: "65.1x",
  },
  {
    name: "sieve",
    stress: "byte-array writes",
    checksum: "5957320",
    c: "1.00x",
    semantic: "1.00x",
    javascript: "1.41x",
    python: "5.54x",
  },
  {
    name: "mandelbrot",
    stress: "float compute",
    checksum: "61930405",
    c: "1.00x",
    semantic: "0.98x",
    javascript: "1.04x",
    python: "48.2x",
  },
];

const benchmarkMethodFacts = [
  ["Workload", "same algorithm, same checksum"],
  ["Metric", "median of 9 measured runs"],
  ["Scale", "slowdown vs C; lower is faster"],
  ["Compiled pair", "C and SemanticScript both reach LLVM / clang O2"],
];

const benchmarkSnippets = [
  {
    language: "c",
    label: "C / clang O2",
    note: "Native baseline walks each composite multiple.",
    code: `for (long long multiple = candidate * candidate;
     multiple <= limit;
     multiple += candidate) {
  sieve[multiple] = 0;
}`,
  },
  {
    language: "semanticscript",
    label: "SemanticScript",
    note: "The same mark step as addressable call records.",
    code: `label markLoopBody
call markCompositeCall pointer.storeByte
argument markCompositeCall buffer OpaquePointer sieveBuffer
argument markCompositeCall offset Int64 currentMultipleIndex
argument markCompositeCall value Int32 compositeCellMarker
run markCompositeCall`,
  },
  {
    language: "javascript",
    label: "JavaScript / Node",
    note: "Typed array loop, wrapped so V8 optimizes the hot path.",
    code: `for (let multiple = candidate * candidate;
     multiple <= limit;
     multiple += candidate) {
  sieve[multiple] = 0
}`,
  },
  {
    language: "python",
    label: "Python / CPython",
    note: "Uses the idiomatic C-level bulk slice for the same mark pass.",
    code: `first = candidate * candidate
count = (limit - first) // candidate + 1
sieve[first::candidate] = b"\\x00" * count`,
  },
];

const docs = [
  ["Overview", `${repoUrl}/blob/main/docs/overview.md`, "Compact public overview of the language, toolchain, runtime areas, and status."],
  ["Quickstart", `${repoUrl}#quickstart`, "Use the release sem.exe surface to inspect version info, check fixtures, retrieve graph data, and run tests."],
  ["Roadmap", `${repoUrl}/blob/main/docs/reference/roadmap.md`, "Pre-release status, demo status, release readiness goals, and backlog policy."],
  ["Agent workflows", `${repoUrl}/blob/main/docs/toolchain/agent-workflows.md`, "The stable check, graph, slice, fix, patch, and test loop."],
  ["Syntax inventory", `${repoUrl}/blob/main/docs/reference/syntax-inventory.md`, "Implementation status for committed, partial, and proposed rows."],
  ["Compatibility", `${repoUrl}/blob/main/docs/reference/compatibility.md`, "The 1.0 support boundary and preview/future surfaces."],
  ["Single executable", `${repoUrl}/blob/main/docs/reference/single-executable-toolchain.md`, "How release builds package the compiler and toolchain into one sem.exe artifact."],
  ["Benchmarks", benchmarksUrl, "C smoke baselines plus cross-language algorithm references for optimizer and backend investigation."],
];

const workflowSteps = [
  ["01", "skills get", "Load repo-matched agent rules before editing source rows."],
  ["02", "check", "Separate compiler errors, linter diagnostics, and warnings."],
  ["03", "graph / slice", "Retrieve the smallest source neighborhood that explains the change."],
  ["04", "fix --plan", "Generate candidate edits without mutating the tree."],
  ["05", "patch", "Preview and apply the reviewed plan with stale-file protection."],
  ["06", "test", "Run behavior harnesses only after semantic preflight is clean."],
];

function SectionHeader({ eyebrow, title, children, compact = false }) {
  return (
    <div className={`sectionHeader ${compact ? "compact" : ""}`.trim()}>
      <p className="eyebrow">{eyebrow}</p>
      <h2>{title}</h2>
      <p>{children}</p>
    </div>
  );
}

function ThemeToggle({ theme, onToggle }) {
  return (
    <button
      className="themeToggle"
      type="button"
      aria-label={`Switch to ${theme === "dark" ? "light" : "dark"} mode`}
      aria-pressed={theme === "dark"}
      onClick={onToggle}
    >
      <span className="toggleTrack" aria-hidden="true">
        <span className="toggleThumb" />
      </span>
      <span>{theme === "dark" ? "Dark" : "Light"}</span>
    </button>
  );
}

function getInitialTheme() {
  if (typeof window === "undefined") {
    return "light";
  }

  const storedTheme = window.localStorage.getItem("semanticscript-theme");
  if (storedTheme === "light" || storedTheme === "dark") {
    return storedTheme;
  }

  return window.matchMedia?.("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

function App() {
  const [theme, setTheme] = useState(getInitialTheme);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    window.localStorage.setItem("semanticscript-theme", theme);
  }, [theme]);

  const toggleTheme = () => {
    setTheme((currentTheme) => (currentTheme === "dark" ? "light" : "dark"));
  };

  return (
    <main>
      <section className="hero" id="top">
        <nav className="nav" aria-label="Primary navigation">
          <a className="navBrand" href="#top" aria-label="SemanticScript home">
            <img src={semanticLogoCard} alt="" />
            <span>SemanticScript</span>
          </a>
          <a href="#status">Status</a>
          <a href="#source-model">Source model</a>
          <a href="#syntax-rationale">Syntax</a>
          <a href="#workflow">Workflow</a>
          <a href="#evidence">Evidence</a>
          <a href="#docs">Docs</a>
          <ThemeToggle theme={theme} onToggle={toggleTheme} />
        </nav>

        <div className="heroGrid">
          <div className="heroCopy">
            <p className="eyebrow">SemanticScript / 0.0.1 pre-release</p>
            <h1>Semantic source rows for agent-maintained software.</h1>
            <p className="lead">
              SemanticScript is a compiled application language where dataflow, failures, effects,
              memory, cleanup, routes, and authority are explicit source records. The design goal is
              practical: make code changes easier to retrieve, audit, patch, and compile.
            </p>
            <div className="ctaRow">
              <a className="button primary" href={`${repoUrl}#quickstart`}>
                Run the quickstart
              </a>
              <a className="button ghost" href={repoUrl}>
                View repository
              </a>
            </div>
          </div>

          <aside className="heroPanel" aria-label="SemanticScript command surface">
            <div className="mascotBadge" aria-label="SemanticScript mascot watching the tool output">
              <img src={semanticMascot} alt="SemanticScript mascot with code brackets" />
              <span>agent view</span>
            </div>
            <div className="panelHeader">
              <span>sem.check.v1</span>
              <strong>source lane</strong>
            </div>
            <CodeBlock language="json">{`{
  "status": "ok",
  "surface": "SemanticScript/tests/agent_cli_demo.test.sem",
  "compiler": "pass",
  "linter": "pass",
  "next": ["graph", "slice", "test"]
}`}</CodeBlock>
            <div className="terminalMeta">
              <span>parser</span>
              <span>linter</span>
              <span>graph</span>
              <span>patch</span>
            </div>
          </aside>
        </div>
      </section>

      <section className="section status" id="status">
        <SectionHeader eyebrow="Current state" title="Pre-release toolchain, explicit status.">
          The project should be evaluated as a working research compiler and toolchain, not a stable
          public language release. The page now keeps that boundary visible instead of overselling.
        </SectionHeader>
        <div className="statusGrid">
          {statusFacts.map(([label, value, detail]) => (
            <article className="statusCard" key={label}>
              <p>{label}</p>
              <strong>{value}</strong>
              <span>{detail}</span>
            </article>
          ))}
        </div>
      </section>

      <section className="section commandSection" id="quickstart">
        <div className="commandGrid">
          <article className="commandIntro">
            <p className="eyebrow">Release verification path</p>
            <h2>Start from the shipped `sem.exe` surface.</h2>
            <p>
              Release builds produce a single Windows compiler/toolchain executable. The public
              workflow should verify source state, graph shape, and harness behavior through that
              executable before dropping into development internals.
            </p>
          </article>
          <CodeBlock language="powershell">{releaseCommands}</CodeBlock>
        </div>

        <div className="commandGrid alternate compilerGrid">
          <article className="commandIntro">
            <p className="eyebrow">Reference compiler path</p>
            <h2>LLVM IR is the prototype boundary, not the language model.</h2>
            <p>
              The source compiler owns parsing, AST construction, semantic checks, and lowering from
              explicit rows into LLVM IR. LLVM then supplies mature optimization, JIT execution, and
              native object/executable generation while the project is still proving the language and
              tool contract.
            </p>
          </article>
          <div className="compilerCodeStack">
            <CodeBlock language="text">{compilerPipeline}</CodeBlock>
            <CodeBlock language="llvm">{llvmIrSnippet}</CodeBlock>
          </div>
        </div>
      </section>

      <section className="section sourceModel" id="source-model">
        <SectionHeader eyebrow="Source model" title="A program as a typed operations log.">
          The language rejects expression syntax, implicit async, ambient exceptions, and hidden
          runtime authority. That makes the source longer, but it also makes the important facts
          easier to address by line, verb, symbol, route, and operation.
        </SectionHeader>
        <div className="propertyGrid">
          {sourceProperties.map(([title, copy]) => (
            <article className="propertyCard" key={title}>
              <h3>{title}</h3>
              <p>{copy}</p>
            </article>
          ))}
        </div>
      </section>

      <section className="section syntaxRationale" id="syntax-rationale">
        <SectionHeader eyebrow="Syntax rationale" title="A source shape tuned for model attention.">
          SemanticScript treats syntax as retrieval structure. The research direction is to reduce
          grammar ambiguity and token surprise so agents have clearer next-token priors and fewer
          opportunities to invent hidden behavior during edits.
        </SectionHeader>
        <div className="rationaleGrid">
          <article className="rationaleLead">
            <h3>Lower perplexity is a design aim, not a published benchmark claim.</h3>
            <p>
              The flat tape keeps row roles explicit, repeats names where they carry context, and
              avoids expression forms that force a model to infer hidden control flow. The goal is
              practical: make the likely next token clearer, reduce hallucinated arguments or
              branches, and keep source slices legible inside limited attention windows.
            </p>
          </article>
          <CodeBlock language="semanticscript" className="rationaleCode">
            {syntaxRationaleCode}
          </CodeBlock>
        </div>
        <div className="rationaleRows" aria-label="Syntax rationale properties">
          {syntaxRationaleRows.map(([title, copy]) => (
            <article className="rationaleCard" key={title}>
              <h3>{title}</h3>
              <p>{copy}</p>
            </article>
          ))}
        </div>
      </section>

      <section className="section proofExample" id="risk">
        <SectionHeader eyebrow="Risk retrieval" title="The useful primitive is an auditable neighborhood.">
          A normal service handler spreads route registration, auth source, body parsing, database
          mutation, response writes, and failure behavior across framework defaults. SemanticScript
          keeps those contracts in rows that graph, slice, lint, and patch tools can target.
        </SectionHeader>
        <div className="compareGrid">
          <article className="compareCard">
            <h3>Conventional service handler</h3>
            <p>
              The contract is compact for authors but expensive for tools to reconstruct before a
              change. Hidden defaults become part of the edit risk.
            </p>
            <CodeBlock language="javascript">{`app.post("/api/todos", async (req, res) => {
  const user = sessionUser(req)
  const body = validateTodo(req.body)
  await db.insertTodo(user.id, body.title)
  res.status(201).json({ ok: true })
})`}</CodeBlock>
          </article>

          <article className="compareCard emphasis">
            <h3>SemanticScript edit target</h3>
            <p>
              The route row, effect rows, invariant, capabilities, call records, and failure labels are
              stable patch targets. A slice can retrieve the relevant neighborhood before editing.
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

      <section className="section mechanics" id="mechanics">
        <SectionHeader eyebrow="Mechanics" title="Longer source, smaller edit uncertainty.">
          A retrieved operation can explain what it reads, writes, allocates, awaits, trusts, and
          returns without relying on framework side effects or surrounding prose.
        </SectionHeader>
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

      <section className="section workflow" id="workflow">
        <SectionHeader eyebrow="Agent workflow" title="The sem wrapper is the public contract.">
          Engineers and agents should use the same loop: load repo-matched rules, prove source
          state, retrieve the smallest useful graph slice, create a reviewable plan, patch, format,
          check, and only then run behavior harnesses.
        </SectionHeader>
        <div className="workflowRail" aria-label="SemanticScript workflow">
          {workflowSteps.map(([number, title, copy]) => (
            <div className="workflowStep" key={title}>
              <span>{number}</span>
              <strong>{title}</strong>
              <p>{copy}</p>
            </div>
          ))}
        </div>
        <CodeBlock language="powershell" className="commandBlock">{`.\\sem.exe version --json
.\\sem.exe skills get sem sem-agent --json
.\\sem.exe check --json PATH
.\\sem.exe graph --kind summary --json PATH
.\\sem.exe slice --operation NAME --json PATH
.\\sem.exe fix --plan --json PATH
.\\sem.exe patch --dry-run --json plan.json
.\\sem.exe test --json PATH`}</CodeBlock>
      </section>

      <section className="section evidence" id="evidence">
        <SectionHeader eyebrow="Evidence" title="One benchmark family, four runtimes." compact>
          The algorithm harness keeps C, SemanticScript, JavaScript, and Python side by side. Each
          program computes the same checksum and reports only its timed compute region, so the table
          stays useful without turning this page into a benchmark report.
        </SectionHeader>

        <article className="benchmarkCard">
          <div className="benchmarkTopline">
            <div>
              <h3>Cross-language algorithm medians</h3>
              <p>
                Windows 11, clang 22.1.4, Node v25, CPython 3.10.11. Values are slowdown relative
                to C, using median of 9 measured runs after 2 warm-ups.
              </p>
            </div>
            <a className="inlineLink" href={benchmarksUrl}>
              Benchmark source
            </a>
          </div>

          <div className="benchmarkMethodGrid" aria-label="Benchmark method facts">
            {benchmarkMethodFacts.map(([label, value]) => (
              <div className="benchmarkMethod" key={label}>
                <span>{label}</span>
                <strong>{value}</strong>
              </div>
            ))}
          </div>

          <div className="tableWrap benchmarkTableWrap">
            <table className="benchmarkTable">
              <thead>
                <tr>
                  <th>Algorithm</th>
                  <th>Stress</th>
                  <th>C</th>
                  <th>SemanticScript</th>
                  <th>JavaScript</th>
                  <th>Python</th>
                  <th>Checksum</th>
                </tr>
              </thead>
              <tbody>
                {algorithmBenchmarkRows.map((row) => (
                  <tr key={row.name}>
                    <td data-label="Algorithm">
                      <code>{row.name}</code>
                    </td>
                    <td data-label="Stress">{row.stress}</td>
                    <td data-label="C">{row.c}</td>
                    <td data-label="SemanticScript" className="semanticResult">{row.semantic}</td>
                    <td data-label="JavaScript">{row.javascript}</td>
                    <td data-label="Python">{row.python}</td>
                    <td data-label="Checksum">{row.checksum}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <p className="benchmarkNote">
            Read this as prototype backend signal: C and SemanticScript are the compiled pair, while
            Node and CPython keep mainstream dynamic runtime behavior in frame.
          </p>
        </article>

        <article className="snippetPanel">
          <div className="snippetPanelHeader">
            <div>
              <h3>Sieve mark pass, same workload</h3>
              <p>
                Sieve to 2,000,000 repeated 40 times. These are the hot composite-marking snippets
                from the four checked sources.
              </p>
            </div>
            <span>checksum 5957320</span>
          </div>
          <div className="snippetGrid">
            {benchmarkSnippets.map((snippet) => (
              <article className="snippetCard" key={snippet.label}>
                <div className="snippetMeta">
                  <strong>{snippet.label}</strong>
                  <span>{snippet.note}</span>
                </div>
                <CodeBlock language={snippet.language} className="compactCode">
                  {snippet.code}
                </CodeBlock>
              </article>
            ))}
          </div>
        </article>
      </section>

      <section className="section docs" id="docs">
        <SectionHeader eyebrow="Documentation map" title="Use the website as an index, not the spec." compact>
          The linked repository docs remain the source of truth for command behavior, syntax support,
          release status, and compatibility boundaries.
        </SectionHeader>
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
          <p className="eyebrow">Fit</p>
          <h2>For codebases where future edits need explicit context.</h2>
          <p>
            SemanticScript is for engineers who want application code with explicit contracts,
            diffable risk, retrievable semantic neighborhoods, native compilation, and a packaged
            compiler path. It is early, but the maintenance problem it targets is concrete.
          </p>
          <div className="ctaRow">
            <a className="button primary" href={docsUrl}>
              Read the docs
            </a>
            <a className="button ghost" href={`${repoUrl}/issues`}>
              Open issues
            </a>
          </div>
        </div>
      </section>
    </main>
  );
}

export default App;
