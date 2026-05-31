# Single-Executable Toolchain Packaging

SemanticScript can ship its Python tooling as a single Windows executable with
PyInstaller onefile mode. This is the release path used by
`.github/workflows/release.yml`.

## Recommendation

Use PyInstaller for the release executable.

- It supports Windows onefile builds now, without rewriting the compiler or CLI.
- It can bundle Python modules, llvmlite support files, docs used by `sem
  skills`, the standard library, and runtime/vendor folders without bundling app
  demo source trees.
- The project can keep the existing Python entry points for development while
  release CI publishes a single `semanticscript-sem-windows-x64-<TAG>.exe`.

The committed spec is `packaging/pyinstaller/sem.spec`; the launcher is
`packaging/pyinstaller/sem_launcher.py`.

## Build

```powershell
python -m pip install pyinstaller==6.20.0
python -m PyInstaller --noconfirm --clean packaging/pyinstaller/sem.spec
```

The output is:

```text
dist\sem.exe
```

## Embedded Metadata

The PyInstaller spec writes a Windows VERSIONINFO resource into `sem.exe`.
`FileDescription` identifies the executable as the SemanticScript CLI and MCP
server. `Comments` carries the minimum MCP bootstrap instruction:

```text
MCP stdio server: run sem.exe mcp.
MCP client config: command sem.exe; args ["mcp"]; cwd project root.
Load project docs: agent_docs path dot.
Then load versioned skills: skills_get names sem-start sem sem-agent sem-syntax.
Then call help path . and docs_search for API/capability/type/syntax/runtime discovery.
```

The same resource also includes machine-readable custom string entries:

```text
McpServerCommand=sem.exe mcp
McpServerTransport=stdio
McpClientConfig={"command":"sem.exe","args":["mcp"],"cwd":"<project-root>"}
```

Windows Explorer usually shows the standard fields, while tools using
`version.dll` `VerQueryValue` can read the custom MCP keys.

Release CI copies that file to:

```text
release-artifacts\semanticscript-sem-windows-x64-<TAG>.exe
```

and records the SHA-256 checksum in the generated release manifest.

## Main-Branch Artifact Builds

`.github/workflows/compiler-exe.yml` builds the same PyInstaller executable on
every push to `main`, which is the normal result of merging a PR. It also builds
the local VS Code extension package. The workflow validates the executable with
`version`, `skills list`, `check`, and `fmt --check`, then uploads GitHub
Actions artifacts named `semanticscript-sem-windows-x64`,
`semanticscript-vscode-vsix`, and `semanticscript-merge-release-manifest`
containing:

```text
semanticscript-sem-windows-x64-main-<SHORT_SHA>.exe
semanticscript-vscode-main-<SHORT_SHA>.vsix
semanticscript-merge-release-manifest-main-<SHORT_SHA>.json
```

The same workflow creates or updates a GitHub prerelease tagged
`main-<SHORT_SHA>` and attaches those three files as downloadable release
assets. These merge prereleases are build handoff artifacts, not stable public
version releases.

Tagged releases still use `.github/workflows/release.yml`, rename the executable
and VSIX with the release tag, generate the stable release manifest and
checksums, and attach the compiler executable plus VSIX to the GitHub Release for
the matching `v*` tag.

## Validation

The release workflow validates the executable with commands that exercise the
public CLI, bundled docs/skills, formatter, linter, compiler parse/check path,
LLVM IR emission, and JIT run path:

```powershell
.\dist\sem.exe version --json
.\dist\sem.exe skills list --json
.\dist\sem.exe skills get taskforge-web-patterns --json
.\dist\sem.exe check --json SemanticScript\tests\agent_cli_demo.test.sem
.\dist\sem.exe fmt --check SemanticScript\tests\agent_cli_demo.test.sem
.\dist\sem.exe lint SemanticScript\tests\tiny.sem -- --summary
.\dist\sem.exe emit-ir SemanticScript\tests\agent_cli_demo.test.sem --quiet
.\dist\sem.exe run SemanticScript\tests\agent_cli_demo.test.sem
```

## Runtime Behavior

PyInstaller onefile embeds the bundled folders inside the executable. At
runtime, PyInstaller extracts that payload into a temporary `_MEI...` directory
and runs from there. The user still downloads and launches one `.exe`, but the
process requires writable temp space. The temporary directory is removed on
normal exit. If a process is killed or the host shuts down during execution,
stale `_MEI*` directories can remain in the system temp directory. Preview and
remove stale extraction directories with:

```powershell
sem clean --pyinstaller-temp
sem clean --pyinstaller-temp --force
```

`sem version --json` exposes this packaging status under `packaging`: release
artifacts are currently PyInstaller onefile Windows executables, not a
self-hosted native compiler binary.

The launcher also handles subprocess calls shaped like:

```text
sem.exe <embedded-path>\SemanticScript\compiler\semsc.py ...
```

This matters because the existing `sem` CLI delegates to compiler, formatter,
linter, syntax-migration, and benchmark entry points by script path. In the
frozen executable, `packaging/pyinstaller/sem_launcher.py` detects those embedded
script paths and dispatches to the corresponding imported module instead of
requiring a separate Python interpreter or source checkout.

## Alternatives Considered

Nuitka can produce performant binaries, but onefile builds are more sensitive to
native dependency packaging and usually require more project-specific tuning for
llvmlite and data folders.

PyOxidizer can embed Python resources deeply, but its packaging model is a
larger migration and is less direct for this repository's current script-based
toolchain.

For this release, PyInstaller is the lowest-risk path because it preserves the
existing Python tooling and turns release packaging into a CI concern.

## Release Discovery

Use `sem self latest --json` to resolve the current release-channel artifact.
The command queries the GitHub releases API and sorts matching releases by
`published_at`; it does not rely on `/releases/latest`, which does not cover the
main-channel prerelease handoff artifacts.

```powershell
sem self latest --channel prerelease --json
sem self download --channel prerelease --output .\sem.exe
sem self update --channel prerelease
```

`sem self update` stages the replacement executable next to the current
executable as `sem.exe.new`. On Windows the running executable is locked, so the
payload includes the explicit replacement command to run after `sem` exits.

The standard release channel currently publishes a Windows x64 `sem.exe`, the
VSIX, manifests, and the MCP bundle. Linux and macOS source/toolchain validation
run in CI, and application cross-builds can use Zig as documented in
`docs/toolchain/compiler.md`; prebuilt Linux/macOS `sem` release binaries are
not part of the current distribution channel.
