import { Marked, Renderer } from "marked";

const repoUrl = "https://github.com/monstercameron/SemanticScript";
const releasesUrl = `${repoUrl}/releases`;
const docsUrl = `${repoUrl}/tree/main/docs`;
const compilerDocsUrl = `${repoUrl}/blob/main/docs/toolchain/compiler.md`;
const llvmInstallUrl = `${repoUrl}/blob/main/docs/toolchain/llvm-compiler-install.md`;
const compatibilityUrl = `${repoUrl}/blob/main/docs/reference/compatibility.md`;
const syntaxInventoryUrl = `${repoUrl}/blob/main/docs/reference/syntax-inventory.md`;
const singleExeUrl = `${repoUrl}/blob/main/docs/reference/single-executable-toolchain.md`;

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

const releaseInstallCommands = `$InstallDir = "$env:LOCALAPPDATA\\Programs\\SemanticScript"
New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null
Copy-Item ".\\semanticscript-sem-windows-x64-main-<SHORT_SHA>.exe" "$InstallDir\\sem.exe"
& "$InstallDir\\sem.exe" version --json
code --install-extension ".\\semanticscript-vscode-main-<SHORT_SHA>.vsix"`;

const cliLoopCommands = `sem version --json
sem doctor
sem skills list --json
sem check --json PATH
sem graph --kind summary --json PATH
sem slice --operation NAME --json PATH
sem fix --plan --json PATH
sem patch --dry-run --json PLAN.json
sem test --json PATH`;

const sourceCheckoutCommands = `python -m pip install -r requirements.txt -c constraints.txt
python SemanticScript\\tools\\sem.py --version --json
python SemanticScript\\tools\\sem.py check --json SemanticScript\\tests\\agent_cli_demo.test.sem
python SemanticScript\\tests\\run_suite.py ci-fast`;

const operationExample = `operation createTodoHandler
input operation createTodoHandler request HttpRequest
input operation createTodoHandler response HttpResponse
output operation createTodoHandler Int32
effect createTodoHandler read http.request.body
effect createTodoHandler readWrite database
effect createTodoHandler write http.response
useCapability createTodoHandler httpRequestReader
useCapability createTodoHandler sqliteDatabaseReadWriter
memory createTodoHandler heap auto
async createTodoHandler no
purpose operation createTodoHandler "Create a todo owned by the authenticated session user."
invariant operation createTodoHandler "The user id comes from the session, never from request JSON."`;

const routeExample = `webServer taskForgeWebServer
serverHost taskForgeWebServer "127.0.0.1"
serverPort taskForgeWebServer 18090
route taskForgeWebServer GET "/" homePageHandler
route taskForgeWebServer POST "/api/auth/register" registerHandler
route taskForgeWebServer GET "/api/todos" listTodosHandler
route taskForgeWebServer POST "/api/todos/:id/complete" completeTodoHandler
route taskForgeWebServer GET "*" notFoundPageHandler`;

const crashExample = `sem run --explain-crash PATH --json

schemaVersion: sem.crash.v0
suspectedCategory: nativeFault
diagnostic: SSRUN002
callStack: operation frames
lastSite: operation, call, source line`;

const factCards = [
  ["Release channel", "main-<SHA> prereleases", "Each main merge publishes a Windows sem.exe, VSIX, and manifest."],
  ["Version", "0.0.1 pre-release", "No stable public release has shipped yet."],
  ["Syntax inventory", "362 implemented / 93 partial", "Reported by sem.version.v1 in the current toolchain."],
  ["Compiler backend", "LLVM + clang", "Parses .sem/.sscript, emits IR, JIT-runs, and links native executables."],
  ["Editor", "Local VSIX", "VS Code syntax, semantic tokens, hovers, and diagnostics are packaged per release."],
];

const pipeline = [
  ["Parse", "Line-oriented .sem and .sscript files become operation and project records."],
  ["Resolve", "Imports, stdlib roots, build.sem declarations, external literals, and module registrations are expanded."],
  ["Check", "Compiler checks and semlint expose diagnostics as human text or machine JSON."],
  ["Lower", "Supported rows emit LLVM IR, native runtime calls, route tables, resources, and typed return flow."],
  ["Run or link", "The compiler JIT-runs entry console programs or calls clang for native executables."],
  ["Package", "CI builds sem.exe, VSIX, and a checksum manifest for every main merge prerelease."],
];

const supportRows = [
  ["Compiler and CLI", "Supported pre-release", "sem check, graph, slice, fix, patch, test, build, run, doctor."],
  ["LLVM/native exe", "Supported with host LLVM", "Install clang or set SEMSC_CLANG for emit-exe/build paths."],
  ["Native HTTP server", "Preview, release-tested", "Routed HTTP/1.1 server with explicit request/response ABI."],
  ["SQLite/JSON/bcrypt/runtime adapters", "Working adapters", "Native runtime sources are linked when compiler-owned call targets require them."],
  ["Windows GUI", "Preview / partial", "Win32 smoke path is active; WinUI 3 scaffold is recognized but not link-ready."],
  ["Outbound standard.net", "Experimental", "libcurl/libuv path exists but is not part of the stable support boundary."],
];

const limits = [
  "The project is 0.0.1 pre-release; compatibility is documented but not stable.",
  "Some refined syntax is accepted for tools and docs but does not lower to runtime behavior.",
  "Native executable builds require a host C toolchain, preferably LLVM/clang.",
  "Package registry, version manager, language server, H2O/HTTP/2, and WinUI 3 runtime are future or preview work.",
  "The GitHub Pages site is an overview; exact support status lives in the compatibility and syntax inventory docs.",
];

const docLinks = [
  ["README", repoUrl, "Release install, quickstart, repository map, and current status."],
  ["Compiler", compilerDocsUrl, "CLI flags, parse pipeline, import resolution, codegen modes, runtime diagnostics."],
  ["LLVM install", llvmInstallUrl, "Windows, macOS, and Linux clang setup for native executable builds."],
  ["Compatibility", compatibilityUrl, "Supported, preview, partial, and future surfaces."],
  ["Syntax inventory", syntaxInventoryUrl, "Implemented and partial row inventory with current status."],
  ["Single executable", singleExeUrl, "PyInstaller onefile release path and merge prerelease artifacts."],
];

function App() {
  return (
    <main>
      <section className="hero" id="top">
        <nav className="nav" aria-label="Primary navigation">
          <a href="#install">Install</a>
          <a href="#compiler">Compiler</a>
          <a href="#cli">CLI</a>
          <a href="#runtime">Runtime</a>
          <a href="#docs">Docs</a>
        </nav>

        <div className="heroGrid">
          <div className="heroCopy">
            <p className="eyebrow">SemanticScript 0.0.1 pre-release</p>
            <h1>Agent-readable source, compiled through LLVM.</h1>
            <p className="lead">
              SemanticScript is an application language and toolchain for codebases that need
              explicit operation contracts, machine-readable diagnostics, retrievable semantic
              slices, and native compilation. The project publishes Windows `sem.exe` prereleases,
              a VS Code VSIX, and source-checkout tooling from the same repository.
            </p>
            <div className="ctaRow">
              <a className="button primary" href={releasesUrl}>
                Download release assets
              </a>
              <a className="button ghost" href={repoUrl}>
                View repository
              </a>
              <a className="button ghost" href={compilerDocsUrl}>
                Compiler docs
              </a>
            </div>
          </div>

          <aside className="heroPanel" aria-label="Technical summary">
            <div className="panelLabel">Current toolchain</div>
            <CodeBlock language="text">{`sem.exe
  parse/check/fmt/lint
  graph/slice/fix/patch
  emit LLVM IR
  JIT run
  clang-linked native exe
  VS Code extension package`}</CodeBlock>
            <p>
              The release path is intentionally concrete: every main merge builds and validates a
              downloadable compiler executable, extension package, and manifest.
            </p>
          </aside>
        </div>

        <div className="factStrip" aria-label="Current project facts">
          {factCards.map(([label, value, detail]) => (
            <article className="factCard" key={label}>
              <p>{label}</p>
              <strong>{value}</strong>
              <span>{detail}</span>
            </article>
          ))}
        </div>
      </section>

      <section className="section" id="install">
        <div className="sectionHeader">
          <p className="eyebrow">Install path</p>
          <h2>Use releases first. Use Python when developing the repo.</h2>
          <p>
            The public path is the GitHub Releases page. Download the newest{" "}
            <code>main-&lt;SHORT_SHA&gt;</code> prerelease, install the Windows{" "}
            <code>sem.exe</code>, install the VSIX if you use VS Code, and run{" "}
            <code>sem doctor</code> before native executable builds.
          </p>
        </div>
        <div className="compareGrid">
          <article className="compareCard strongCard">
            <h3>Release install</h3>
            <p>
              Main-channel release assets are generated by CI and include SHA-256 digests in the
              manifest. This is the path the README now presents first.
            </p>
            <CodeBlock language="powershell">{releaseInstallCommands}</CodeBlock>
          </article>
          <article className="compareCard">
            <h3>Source checkout workflow</h3>
            <p>
              Compiler, linter, formatter, runtime, and docs contributors should still use Python
              from the checkout so tests exercise local source changes.
            </p>
            <CodeBlock language="powershell">{sourceCheckoutCommands}</CodeBlock>
          </article>
        </div>
      </section>

      <section className="section" id="compiler">
        <div className="sectionHeader">
          <p className="eyebrow">Compiler architecture</p>
          <h2>The language is a tape of addressable facts.</h2>
          <p>
            Operations declare inputs, outputs, effects, capabilities, memory behavior, async
            behavior, purpose, invariants, calls, bindings, and failure branches as rows. This gives
            tools stable edit targets before lowering removes redundancy.
          </p>
        </div>
        <article className="mechanicCard">
          <div>
            <h3>Operation contract example</h3>
            <p>
              A reviewer or agent can inspect what a handler reads, writes, allocates, authorizes,
              and promises without reconstructing intent from nested framework code.
            </p>
          </div>
          <CodeBlock>{operationExample}</CodeBlock>
        </article>
        <div className="pipelineGrid" aria-label="Compiler pipeline">
          {pipeline.map(([title, copy]) => (
            <article className="pipelineCard" key={title}>
              <h3>{title}</h3>
              <p>{copy}</p>
            </article>
          ))}
        </div>
      </section>

      <section className="section" id="cli">
        <div className="sectionHeader">
          <p className="eyebrow">CLI contract</p>
          <h2>`sem` is the stable workflow surface.</h2>
          <p>
            The wrapper exposes the project operations agents and maintainers need: validation,
            graph retrieval, operation slices, explanations, repair plans, dry-run patches, tests,
            release checks, and environment diagnostics.
          </p>
        </div>
        <CodeBlock language="powershell" className="commandBlock">{cliLoopCommands}</CodeBlock>
        <div className="workflowRail" aria-label="SemanticScript workflow">
          {[
            "doctor",
            "check",
            "graph",
            "slice",
            "explain",
            "fix",
            "patch",
            "test",
          ].map((step, index) => (
            <div className="workflowStep" key={step}>
              <span>{String(index + 1).padStart(2, "0")}</span>
              <p>{step}</p>
            </div>
          ))}
        </div>
      </section>

      <section className="section" id="runtime">
        <div className="sectionHeader">
          <p className="eyebrow">Runtime surfaces</p>
          <h2>Native paths are explicit and scoped.</h2>
          <p>
            SemanticScript is not presenting every parsed row as production runtime support. The
            compatibility boundary distinguishes implemented compiler behavior, preview adapters,
            partial syntax, and future work.
          </p>
        </div>
        <div className="compareGrid">
          <article className="compareCard strongCard">
            <h3>Route metadata lowers to dispatch</h3>
            <p>
              Routed `target webServer` programs emit native HTTP/1.1 dispatch with explicit handler
              ABI and source-visible route facts.
            </p>
            <CodeBlock>{routeExample}</CodeBlock>
          </article>
          <article className="compareCard">
            <h3>Crash diagnostics are structured</h3>
            <p>
              `SSRUN001` and `SSRUN002` diagnostics expose panic/native-fault context to `sem run
              --explain-crash`, including operation call stack and last semantic site when available.
            </p>
            <CodeBlock language="text">{crashExample}</CodeBlock>
          </article>
        </div>
        <div className="supportTable tableWrap">
          <table>
            <thead>
              <tr>
                <th>Surface</th>
                <th>Status</th>
                <th>Technical note</th>
              </tr>
            </thead>
            <tbody>
              {supportRows.map(([surface, status, note]) => (
                <tr key={surface}>
                  <td>{surface}</td>
                  <td>{status}</td>
                  <td>{note}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="section" id="limits">
        <aside className="notReadyCard" aria-label="Known limits">
          <div>
            <p className="eyebrow">Known limits</p>
            <h2>Relevant because it is explicit.</h2>
            <p>
              The site should not oversell the project. These are the important caveats before
              depending on the current prerelease.
            </p>
          </div>
          <ul>
            {limits.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </aside>
      </section>

      <section className="section docs" id="docs">
        <div className="sectionHeader compact">
          <p className="eyebrow">Technical docs</p>
          <h2>Use the site as the index, not the source of truth.</h2>
          <p>
            Exact behavior belongs in the repository docs and compiler tests. Start here, then drill
            into the files that own each support boundary.
          </p>
        </div>
        <div className="docsGrid">
          {docLinks.map(([title, href, copy]) => (
            <a className="docCard" href={href} key={title}>
              <h3>{title}</h3>
              <p>{copy}</p>
            </a>
          ))}
        </div>
      </section>

      <section className="section closing" id="next">
        <div className="closingCard">
          <p className="eyebrow">Current next step</p>
          <h2>Download the release build or inspect the compiler.</h2>
          <p>
            If you want to use the toolchain, start with the release assets. If you want to verify or
            extend the language, start with the compiler docs, syntax inventory, and release
            validation suite.
          </p>
          <div className="ctaRow">
            <a className="button primary" href={releasesUrl}>
              Open releases
            </a>
            <a className="button ghost" href={docsUrl}>
              Read docs
            </a>
          </div>
        </div>
      </section>
    </main>
  );
}

export default App;
