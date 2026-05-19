"""
semsc - the SemanticScript compiler.

Implements a faithful subset of the SemanticScript language (per
../SemanticScript.md and AST.md). Compiles SemanticScript semantic tape to
LLVM IR via llvmlite, then either JIT-executes via MCJIT or writes the IR to a
.ll file.

Top-level verbs:
  project, target, runtime, entry, module
  type            type alias                (`type CountdownValue I64`)
  error           error category            (`error MainError`)
  errorCase       error variant             (`errorCase MainError ConsoleWriteFailed ConsoleWriteError`)
  dependency      dependency declaration   (parsed, ignored by codegen)

Operation header verbs (parsed, ignored by codegen):
  input, output, effect, memory, async,
  purpose, invariant, warning

Body verbs:
  Decls:     const, var
  Calls:     call, arg, timeout, cancelOn, run, start, await
  Bind:      bind, bindOk, bindError
  Errors:    makeError
  Mutation:  set
  Control:   label, branch, branchIf, branchIfError
  Returns:   returnOk, returnError, returnValue

`bind` is for infallible calls; `bindOk`+`bindError`+`branchIfError` is for
fallible calls. `branchIf cond label` jumps to `label` on true and falls
through on false (per spec §4: one semantic thing per line).

External call targets:
  console.writeLine          -> puts(i8*)                 -> i32 (negative on failure)
  console.writeIntegerLine   -> printf("%lld\n", i64)     -> i32 (negative on failure)
  math.addI64                -> i64 (a + b)
  math.subtractI64           -> i64 (a - b)              (alias: math.subI64)
  math.multiplyI64           -> i64 (a * b)              (alias: math.mulI64)
  math.divideI64             -> i64 (a sdiv b)           (alias: math.divI64)
  math.moduloI64             -> i64 (a srem b)           (alias: math.modI64)
  math.equalI64              -> i1                        (alias: math.eqI64)
  math.notEqualI64           -> i1                        (alias: math.neI64)
  math.lessThanI64           -> i1                        (alias: math.ltI64)
  math.lessThanOrEqualI64    -> i1                        (alias: math.leI64)
  math.greaterThanI64        -> i1                        (alias: math.gtI64)
  math.greaterThanOrEqualI64 -> i1                        (alias: math.geI64)
"""

import argparse
import ctypes
import json
import os
import re
import sys
from dataclasses import dataclass, field
from llvmlite import ir
import llvmlite.binding as llvm

# Make sibling-module imports work when the compiler is invoked by path.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import libc_registry

__version__ = "1.0.0"


# ============================================================
# Diagnostics
# ============================================================

@dataclass
class DiagnosticSpan:
    path: str
    line: int = 0
    column: int = 1
    raw: str = ""
    role: str = "primary"

    def to_json(self):
        return {
            "path": self.path,
            "line": self.line,
            "column": self.column,
            "raw": self.raw,
            "role": self.role,
        }


@dataclass
class DiagnosticFrame:
    kind: str
    operation: str = ""
    call_name: str = ""
    call_target: str = ""
    span: DiagnosticSpan = None
    note: str = ""

    def to_json(self):
        return {
            "kind": self.kind,
            "operation": self.operation,
            "callName": self.call_name,
            "callTarget": self.call_target,
            "span": self.span.to_json() if self.span else None,
            "note": self.note,
        }


@dataclass
class CompilerDiagnostic:
    code: str
    phase: str
    message: str
    severity: str = "error"
    primary: DiagnosticSpan = None
    semantic_stack: list = field(default_factory=list)
    lowering_trace: list = field(default_factory=list)
    direction: str = ""
    suggested_fixes: list = field(default_factory=list)
    backend_excerpt: str = ""
    agent_hint: str = ""

    def to_json(self):
        return {
            "schema": "semsc.diagnostic.v1",
            "code": self.code,
            "phase": self.phase,
            "severity": self.severity,
            "message": self.message,
            "blocksCompile": True,
            "primary": self.primary.to_json() if self.primary else None,
            "semanticStack": [frame.to_json() for frame in self.semantic_stack],
            "loweringTrace": list(self.lowering_trace),
            "direction": self.direction,
            "suggestedFixes": list(self.suggested_fixes),
            "backendExcerpt": self.backend_excerpt,
            "agentHint": self.agent_hint,
        }

    def render_agent(self) -> str:
        lines = [
            f"error {self.code}: {self.message}",
            f"phase: {self.phase}",
            "agent_log:",
            "  schema: semsc.diagnostic.v1",
            f"  severity: {self.severity}",
            "  blocks_compile: yes",
        ]
        if self.primary:
            lines.append(
                f"  primary: {self.primary.path}:{self.primary.line}:{self.primary.column}"
            )
        if self.semantic_stack:
            lines.append("")
            lines.append("SemanticScript stack:")
            for index, frame in enumerate(self.semantic_stack, start=1):
                span = frame.span
                loc = (f"{span.path}:{span.line}:{span.column}"
                       if span else "<unknown>")
                lines.append(f"  {index}. {loc}")
                if frame.operation:
                    lines.append(f"     operation {frame.operation}")
                if frame.call_name or frame.call_target:
                    call_bits = " ".join(
                        bit for bit in (frame.call_name, frame.call_target) if bit)
                    lines.append(f"     call {call_bits}")
                if span and span.raw:
                    lines.append(f"     source: {span.raw.strip()}")
                if frame.note:
                    lines.append(f"     note: {frame.note}")
        if self.lowering_trace:
            lines.append("")
            lines.append("Lowering trace:")
            for step in self.lowering_trace:
                lines.append(f"  - {step}")
        if self.direction:
            lines.append("")
            lines.append("Direction:")
            lines.extend(f"  {line}" for line in self.direction.splitlines())
        if self.suggested_fixes:
            lines.append("")
            lines.append("Suggested fixes:")
            for index, fix in enumerate(self.suggested_fixes, start=1):
                lines.append(f"  {index}. {fix}")
        if self.agent_hint:
            lines.append("")
            lines.append("Agent hint:")
            lines.extend(f"  {line}" for line in self.agent_hint.splitlines())
        if self.backend_excerpt:
            lines.append("")
            lines.append("Backend excerpt:")
            for line in self.backend_excerpt.rstrip().splitlines()[:12]:
                lines.append(f"  {line}")
        lines.append("")
        lines.append("Debug: rerun with SEMSC_TRACEBACK=1 for the internal Python traceback.")
        return "\n".join(lines)

    def render(self, fmt: str = "agent") -> str:
        if fmt == "json":
            return json.dumps(self.to_json(), indent=2)
        if fmt == "raw":
            return self.backend_excerpt or self.message
        return self.render_agent()


class CompilerDiagnosticError(Exception):
    def __init__(self, diagnostic: CompilerDiagnostic):
        super().__init__(diagnostic.message)
        self.diagnostic = diagnostic


class CompilerProvenance:
    def __init__(self, prog):
        self.prog = prog
        self.externals = {}       # llvm/c symbol -> list[DiagnosticFrame]
        self.call_edges = {}      # caller operation -> list[(callee, frame)]

    def span(self, lineno: int, role: str = "primary") -> DiagnosticSpan:
        path = self.prog.source_path or "<source>"
        raw = self.prog.source_lines.get(lineno, "")
        return DiagnosticSpan(path=path, line=lineno or 0, column=1, raw=raw, role=role)

    def frame_from_call(self, call, kind: str = "SemanticScript call",
                        note: str = "") -> DiagnosticFrame:
        return DiagnosticFrame(
            kind=kind,
            operation=call.get("operation", ""),
            call_name=call.get("name", ""),
            call_target=call.get("target", ""),
            span=self.span(call.get("line", 0), role="callSite"),
            note=note,
        )

    def record_external(self, symbol: str, call) -> None:
        if not symbol or not call:
            return
        frame = self.frame_from_call(call)
        self.externals.setdefault(symbol, []).append(frame)

    def record_call_edge(self, caller: str, callee: str, call) -> None:
        if not caller or not callee:
            return
        self.call_edges.setdefault(caller, []).append(
            (callee, self.frame_from_call(call, kind="SemanticScript call edge")))

    def entry_operation(self) -> str:
        if self.prog.entry and len(self.prog.entry) >= 2:
            return self.prog.entry[1]
        return ""

    def path_to_operation(self, target_operation: str):
        entry = self.entry_operation()
        if not entry or not target_operation or entry == target_operation:
            return []
        queue = [(entry, [])]
        seen = {entry}
        while queue:
            op_name, path = queue.pop(0)
            for callee, frame in self.call_edges.get(op_name, []):
                if callee in seen:
                    continue
                next_path = path + [frame]
                if callee == target_operation:
                    return next_path
                seen.add(callee)
                queue.append((callee, next_path))
        return []

    def _backend_excerpt(self, stderr: str) -> str:
        lines = [line for line in stderr.strip().splitlines() if line.strip()]
        # Prefer ERROR lines over benign deprecation warnings: pluck out
        # the actual error band so the excerpt is useful even when MSVC
        # buries it under fopen() noise.
        error_lines = [
            ln for ln in lines
            if ("error:" in ln.lower()
                or "undefined" in ln.lower()
                or "unresolved" in ln.lower()
                or "fatal" in ln.lower())
        ]
        if error_lines:
            return "\n".join(error_lines[:24])
        return "\n".join(lines[:24])

    def explain_backend_error(self, stderr: str, cmd=None) -> CompilerDiagnostic:
        undefined = re.search(r"undefined symbol:\s*([A-Za-z_][A-Za-z0-9_]*)", stderr)
        if undefined:
            symbol = undefined.group(1)
            frames = list(self.externals.get(symbol, []))
            semantic_stack = []
            if frames:
                primary_frame = frames[0]
                semantic_stack.append(primary_frame)
                semantic_stack.extend(self.path_to_operation(primary_frame.operation))
                primary = primary_frame.span
                call_target = primary_frame.call_target or f"c.{symbol}"
                direction = (
                    f"`{call_target}` lowered to raw LLVM external `@{symbol}`, "
                    "but the selected native toolchain did not provide that "
                    "symbol at link time."
                )
            else:
                primary = None
                direction = (
                    f"The generated LLVM IR referenced external `@{symbol}`, "
                    "but no SemanticScript call-site provenance was recorded "
                    "for that symbol. Add provenance at the lowering site for "
                    "this external."
                )
            fixes = [
                "Prefer a portable SemanticScript/runtime path for this call target.",
                "Add a platform-specific lowering or alias in the compiler's libc registry.",
                "Verify SEMSC_CLANG and the selected C runtime if the symbol should exist.",
            ]
            return CompilerDiagnostic(
                code="SSBE001",
                phase="backend.link",
                message=f"undefined external symbol `{symbol}`",
                primary=primary,
                semantic_stack=semantic_stack,
                lowering_trace=[
                    f"SemanticScript call target -> LLVM external @{symbol}",
                    "LLVM IR -> clang",
                    "clang/lld -> native executable link",
                    f"backend reported missing symbol `{symbol}`",
                ],
                direction=direction,
                suggested_fixes=fixes,
                backend_excerpt=self._backend_excerpt(stderr),
                agent_hint=(
                    "Start from the first SemanticScript stack frame. If the "
                    "call target begins with `c.`, inspect libc_registry.py "
                    "and platform-specific C runtime availability before "
                    "changing user source."
                ),
            )
        return CompilerDiagnostic(
            code="SSBE999",
            phase="backend.link",
            message="native backend failed to compile generated LLVM IR",
            backend_excerpt=self._backend_excerpt(stderr),
            direction=(
                "The backend did not expose a recognized error shape. Inspect "
                "the backend excerpt, then rerun with --emit-ir and "
                "SEMSC_TRACEBACK=1 if source provenance is missing."
            ),
            suggested_fixes=[
                "Run with --emit-ir to inspect the generated LLVM.",
                "Check SEMSC_CLANG and the native linker configuration.",
            ],
        )


# ============================================================
# Tokenizer
# ============================================================

def tokenize_line(line: str):
    stripped = line.strip()
    if not stripped:
        return []
    if stripped.startswith("#"):
        return ["#", stripped[1:].strip()]
    tokens = []
    i = 0
    n = len(stripped)
    while i < n:
        c = stripped[i]
        if c.isspace():
            i += 1
            continue
        if c == '"':
            j = i + 1
            buf = []
            while j < n and stripped[j] != '"':
                if stripped[j] == "\\" and j + 1 < n:
                    nxt = stripped[j + 1]
                    buf.append({"n": "\n", "t": "\t", "r": "\r",
                                "\\": "\\", '"': '"', "0": "\0"}.get(nxt, nxt))
                    j += 2
                else:
                    buf.append(stripped[j])
                    j += 1
            if j >= n:
                raise SyntaxError(f"unterminated string: {stripped!r}")
            tokens.append(("str", "".join(buf)))
            i = j + 1
        else:
            j = i
            while j < n and not stripped[j].isspace():
                j += 1
            tokens.append(stripped[i:j])
            i = j
    return tokens


def _unwrap(tok):
    if isinstance(tok, tuple) and tok and tok[0] == "str":
        return tok[1]
    return tok


def _bool_token_to_int(value):
    """Coerce one of the Bool literal tokens (`true`/`false`/`yes`/`no`,
    or the numeric strings/values 1/0) into the integer 0 or 1. Used by
    the `var`/`storage` initializer paths when a const of type Bool flows
    in as a string token from the parser."""
    if isinstance(value, str):
        lowered = value.lower()
        if lowered in ("true", "yes", "1"):
            return 1
        if lowered in ("false", "no", "0"):
            return 0
        try:
            return 1 if int(lowered) != 0 else 0
        except (TypeError, ValueError):
            return 0
    try:
        return 1 if int(value) != 0 else 0
    except (TypeError, ValueError):
        return 0


# ============================================================
# AST
# ============================================================

class Operation:
    def __init__(self, name, decl_line=0):
        self.name = name
        self.decl_line = decl_line
        self.lines = []          # list of (verb, args, srcline)
        # Operation-local const declarations. The resolver consults this
        # before falling back to prog.consts so a const declared inside
        # one operation cannot accidentally shadow or leak into another.
        self.consts = {}         # name -> (type, value)
        # Comments attached to this operation (typed-comment annotations).
        self.typed_comments = [] # list[(kind, text, lineno)]


class Record:
    def __init__(self, name):
        self.name = name
        self.layout = None        # "row" | "column" | "packed" | None
        self.align = None         # int | None
        self.fields = []          # list[(field_name, field_type)]


class Enum:
    def __init__(self, name):
        self.name = name
        self.repr = None          # underlying repr type, if declared
        self.cases = []           # list[(case_name, value_or_none)]


class WebServer:
    def __init__(self, name):
        self.name = name
        self.host = None
        self.port = None
        self.routes = []          # list[(method, path, handler_op)]
        self.middleware = []      # list[(route_name, middleware_op)]
        self.timeouts = {}        # route_name -> duration_value


class HtmlTemplate:
    def __init__(self, name, decl_line=0):
        self.name = name
        self.decl_line = decl_line
        self.args = []            # list[(arg_name, arg_type, lineno)]
        self.body_lines = []      # list[(body_text_without_base_indent, lineno)]
        self.body_line = 0


class Program:
    def __init__(self):
        self.source_path = ""
        self.source_lines = {}        # line -> raw source text in parsed stream
        # ---- declarations relevant to codegen ----
        self.project_name = None
        self.module_name = None
        self.module_line = 0
        self.targets = []
        self.entry = None
        # ---- project metadata (lowered to OS-native formats at emit-exe time) ----
        # Standard fields map to Windows VERSIONINFO StringFileInfo entries when
        # `--emit-exe` runs on Windows with a resource compiler available; other
        # platforms still parse and store the values for future tooling.
        # Keys: "version", "publisher", "description", "copyright",
        # "productName", "internalName", "originalFilename", "trademark",
        # "comments". Arbitrary user-supplied fields go into custom_metadata.
        self.project_metadata = {}        # field_name -> string value
        self.custom_metadata = {}         # arbitrary user key -> string value (insertion-ordered)
        # ---- icon registry (declared in source / build.sem; lowered to native formats) ----
        # Maximum explicitness: one row per fact. `iconRoleDefinition` names
        # the role taxonomy, `icon` declares a group, `iconImage` declares a
        # named image entity, and `iconImage*` rows attach each property of
        # that image. Compiler walks these at emit-exe to build platform
        # icons. See SYNTAX.md for the row schemas.
        self.icon_role_definitions = {}   # role_token -> description text
        self.icon_groups = {}             # group_name -> dict(role, purpose, line)
        self.icon_images = {}             # image_name -> dict(group, path, format, width, height, scale, depth, platform, purpose, line)
        self.consts = {}              # name -> (type, value)
        # Module-scope mutable storage (`storage module mutable` and
        # `sharedState <scope> mutable`). Tracked separately from consts so
        # codegen can emit a real LLVM global with load/store semantics
        # while keeping const-style name resolution for the initial value.
        self.mutable_globals = {}     # name -> (type, raw_initial_value)
        self.type_aliases = {}        # alias -> underlying typename
        self.errors = {}              # err_type_name -> list[(variant_name, underlying_cause_type)]
        self.operations = {}          # name -> Operation
        self.current_op = None

        # ---- richer-surface storage (parsed; codegen treats as metadata) ----
        self.records = {}             # name -> Record
        self.enums = {}                # name -> Enum
        self.web_servers = {}          # name -> WebServer
        self.html_templates = {}       # name -> HtmlTemplate
        self.type_metadata = {}        # type_name -> {invariant: [...], trust:..., memory:..., layout:..., representation:...}
        self.capabilities = {}         # name -> {effect_path, access}
        self.codecs = {}               # name -> {kind, schema, unknownFields, ...}
        self.validators = {}           # name -> {input, output, guarantees}
        self.policies = {}             # name -> attrs dict
        self.resources = {}            # name -> attrs dict
        self.guarantees = {}           # target_name -> list[str]
        self.hard_metadata = {}        # target_name -> dict[kind] -> list[str]
        self.named_failures = {}       # operation_name -> list[(failure_name, text)]
        self.test_covers = []          # list[(test_name, target_name)]
        self.imports = []              # list[(module_path, alias)]
        self.import_aliases = {}        # alias -> module_path
        self.singular_imports = []      # list[(kind, local_name, module_alias, exported_name)]
        self.exports = {                # kind -> module_path -> set(symbol)
            "operation": {},
            "type": {},
            "error": {},
            "capability": {},
            "constant": {},
        }
        self.operation_aliases = {}     # source call target -> internal op name
        self.modes = []                # list[str]  -- e.g. ["capturedOutputReplay"]
        # Module-scope `# group NAME` / `# endGroup NAME` anchors collected from
        # source order so the linter can pair them and warn on imbalance.
        self.module_group_anchors = []  # list[("group"|"endGroup", name, lineno)]
        # Typed comments per spec §7. `# rationale: …`, `# invariant: …`,
        # `# warning: …`, `# failure: …`, `# security: …`, `# timing: …`,
        # `# memory: …`, `# concurrency: …`, `# observability: …`,
        # `# dependency: …`, `# test: …`, `# todo: …`, `# agent: …`.
        # Attached to the most recent operation if one is active, otherwise
        # collected at module scope so tooling and linters can read them.
        self.module_typed_comments = []  # list[(kind, text, lineno)]


# ---- verb dispatch tables ----

# Body verbs whose lines codegen consumes directly.
BODY_VERBS_CODEGEN = {
    "input", "output", "effect", "memory", "async",
    "purpose", "invariant", "warning",
    "label", "const", "var", "set",
    "call", "arg", "timeout", "cancelOn", "run", "start", "await",
    "bind", "bindOk", "bindError", "ignoreOk", "ignoreValue",
    "makeError",
    "branch", "branchIf", "branchIfError",
    "returnOk", "returnError", "returnValue", "returnVoid",
}

# Body verbs the parser stores into op.lines but codegen treats as metadata.
# These exist so a richer program can be written, parsed, and inspected
# without the codegen pass tripping over verbs whose runtime semantics are
# defined by the spec but not yet implemented by this compiler.
# `*_SOFT` verbs are pure metadata. Codegen safely skips them because
# they do not change the program's runtime behavior — they only annotate
# the AST for tooling, linters, agent context, and §8 hard-metadata
# indexes.
BODY_VERBS_RESERVED_SOFT = {
    "guarantee", "failure", "security", "timing", "observability",
    "memoryAllocationSource",
    "useCapability",
    "importModule",
    # `precondition OP "text"` — structured form of "Caller guarantees X"
    # text that was historically written into `invariant` prose. Carries
    # the caller-side proof obligation without claiming the body enforces
    # it. Metadata-only at codegen; linters and agents read it to check
    # call sites and to render the operation contract for review.
    "precondition",
    # `pinsNullBodyFailurePath OP "rationale"` — explicit opt-in to the
    # native HTTP adapter's null-body 500 contract. Replaces a stringly-
    # typed marker phrase that used to live inside `warning OP "..."`
    # text. semsc treats it as metadata; semlint SS3603 reads it as the
    # canonical opt-out. See SYNTAX.md#pinsNullBodyFailurePath.
    "pinsNullBodyFailurePath",
    # `responseBodyForwarder OP bodyArgName` — declares that an operation
    # forwards its `bodyArgName` input straight into an http.response*
    # writer (or another forwarder), making it part of the transitive
    # response-body-writer set. Replaces a `body` arg-name string match.
    "responseBodyForwarder",
    # `rationale CALL "text"` — operation-body counterpart to the
    # `# rationale:` typed comment; explicitly attaches a rationale to a
    # specific call site so SS3603 (and other rules) can cite it without
    # relying on comment proximity. See SYNTAX.md#rationale.
    "rationale",
}

# `*_HARD` verbs are spec-defined runtime features (cleanup, structured
# concurrency, channels, locks, worker pools, intervals, record I/O).
# The codegen does not yet lower them, so silently dropping them would
# materially change behavior — that is illegal under spec §2 law 5
# ("hidden behavior is illegal by default"). The codegen refuses to
# compile any program that uses one, with a message pointing to the
# spec section. Use `--parse-only` to inspect the AST of such a program.
BODY_VERBS_RESERVED_HARD = {
    # spec §13 — cleanup / defer
    "defer", "deferLog", "deferAwaitLog", "deferWhenExitLog",
    # spec §20 — structured concurrency / task groups
    "taskGroup", "startInGroup", "awaitGroup",
    "bindGroupError", "branchIfGroupError",
    # spec §22 — channels, locks, worker pools
    "send", "receive", "branchIfChannelClosed",
    "lock", "unlock",
    "workerPool", "work", "workArg", "submitWork", "awaitWork",
    # spec §23 — typed time / intervals
    "interval", "startInterval", "awaitIntervalTick",
    # spec §20 — race / select
    "select", "selectCase", "runSelect", "branchSelected",
    # spec §21 — record I/O
    "new", "fieldGet", "fieldSet",
    # policy attachment runs at codegen
    "useRetry",
}

BODY_VERBS_RESERVED = BODY_VERBS_RESERVED_SOFT | BODY_VERBS_RESERVED_HARD

BODY_VERBS = BODY_VERBS_CODEGEN | BODY_VERBS_RESERVED


# Closed set of recognized `mode` declarations. See AST.md §10.
_KNOWN_MODES = {
    "capturedOutputReplay",
}

_MODULE_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)*$")
_HTML_ARG_REFERENCE_RE = re.compile(r"\{\s*htmlArg\.([A-Za-z_][A-Za-z0-9_]*)\s*\}")
_HTML_BRACE_CONTENT_RE = re.compile(r"\{([^{}\n]*)\}")
_HTML_RAW_TEXT_RE = re.compile(
    r"<(style|script)\b[^>]*>.*?</\1\s*>",
    re.IGNORECASE | re.DOTALL,
)
_HTML_ATTR_VALUE_PREFIX_RE = re.compile(
    r"([A-Za-z_:][A-Za-z0-9_:.-]*)\s*=\s*([\"'])[^\"']*$")
_HTML_URL_ATTRS = {
    "action",
    "formaction",
    "href",
    "poster",
    "src",
}
_HTML_TRUST_TYPES = {
    "HtmlText",
    "HtmlClass",
    "SafeUrl",
    "HtmlFragment",
    "HtmlTrustedFragment",
    "HtmlDocument",
}
_HTML_HYDRATE_PREFIX = "html.hydrate."

# Top-level verbs that map 1:1 to Windows VERSIONINFO StringFileInfo entries.
# Each verb takes one quoted-string argument. The ordering here also drives
# the order entries are written into the generated .rc file.
_PROJECT_METADATA_VERBS = (
    "version",
    "publisher",
    "description",
    "copyright",
    "productName",
    "internalName",
    "originalFilename",
    "trademark",
    "comments",
)

# Version literal must be 1-4 dotted unsigned integers. Windows VERSIONINFO
# wants exactly 4 components in FIXEDFILEINFO; missing parts are zero-padded
# at .rc generation time.
_PROJECT_VERSION_RE = re.compile(r"^\d+(\.\d+){0,3}$")

_BUILD_TAPE_PROJECT_VERBS = frozenset({
    "modulePath", "languageVersion", "projectVersion", "projectLicense",
    "sourceRoot", "mainFile", "mainOperation", "testPattern", "testRoot",
    "targetRuntime", "buildProfile", "runtimeChecks", "persistLlvmIr",
    "nativeOutput", "keepResources", "resourcesDir",
    "nativeHttpHost", "nativeHttpPort",
    "formatterSetting", "linterSetting", "docsOutput",
    "optLevel", "emitLlvmIr", "llvmIrOutput",
    "emitOptimizedLlvmIr", "optimizedLlvmIrOutput",
    "buildDir", "buildRoot", "buildFolderName",
    "cpuBaseline", "cpuTune", "cpuFeature", "cpuFeatureCheck",
    "registerModule",
    "dependency", "dependencySource", "dependencyFetch",
    "dependencyCache", "dependencyLock", "dependencyIntegrity",
    "comptimeOperation",
    # buildConstant PROJECT NAME TYPE VALUE — hoist a compile-time
    # constant into the program. Equivalent to declaring `storage
    # module immutable NAME TYPE VALUE` at the top of the program,
    # but visible to every imported module (so build.sem can be the
    # single source of truth for shared config like host/port/paths).
    # Type must be one of the standard primitives; VALUE is a quoted
    # string for textual types and a bare numeric literal for int /
    # float types.
    "buildConstant",
})

_BUILD_TAPE_SINGLETON_VERBS = frozenset({
    "modulePath", "languageVersion", "projectVersion", "projectLicense",
    "sourceRoot", "mainFile", "mainOperation", "targetRuntime",
    "buildProfile", "runtimeChecks", "persistLlvmIr", "nativeOutput",
    "keepResources", "resourcesDir", "nativeHttpHost", "nativeHttpPort",
    "docsOutput", "optLevel", "emitLlvmIr", "llvmIrOutput",
    "emitOptimizedLlvmIr", "optimizedLlvmIrOutput",
    "buildDir", "buildRoot", "buildFolderName", "comptimeOperation",
    "cpuBaseline", "cpuTune", "cpuFeatureCheck",
    "dependencyCache", "dependencyLock",
})

_BUILD_TAPE_REQUIRED_VERBS = frozenset({
    "modulePath", "languageVersion", "projectVersion", "projectLicense",
    "sourceRoot", "targetRuntime", "buildProfile", "runtimeChecks",
    "persistLlvmIr", "optLevel",
})

_BUILD_TAPE_PATH_VERBS = frozenset({
    "sourceRoot", "mainFile", "testPattern", "testRoot", "nativeOutput",
    "resourcesDir", "docsOutput", "llvmIrOutput",
    "optimizedLlvmIrOutput", "buildDir", "buildRoot",
    "dependencyCache", "dependencyLock",
})

_BUILD_TAPE_MIN_ARITY = {
    "dependency": 4,
    "dependencySource": 3,
    "dependencyFetch": 4,
    "dependencyCache": 2,
    "dependencyLock": 2,
    "dependencyIntegrity": 3,
    "cpuFeature": 3,
    "formatterSetting": 3,
    "linterSetting": 3,
    "registerModule": 3,
    "buildConstant": 4,
}

_BUILD_TAPE_CHOICES = {
    "targetRuntime": {"nativeExe", "webServer", "windowsGui", "library"},
    "buildProfile": {"dev", "prod"},
    "runtimeChecks": {"off", "traps", "panic"},
    "persistLlvmIr": {"auto", "yes", "no"},
    "keepResources": {"yes", "no", "true", "false", "on", "off", "1", "0"},
    "emitLlvmIr": {"auto", "yes", "no"},
    "emitOptimizedLlvmIr": {"yes", "no"},
    "cpuBaseline": {
        "generic", "native",
        "x86_64_v1", "x86_64_v2", "x86_64_v3", "x86_64_v4",
        "arm64_generic", "arm64_v8_2",
    },
    "cpuFeatureCheck": {"auto", "off", "warn", "require"},
}

_CPU_FEATURE_STATES = frozenset({"on", "off"})
_CPU_FEATURE_RE = re.compile(r"^[A-Za-z0-9_.-]+$")
_DEPENDENCY_SOURCE_KINDS = frozenset({"local", "path", "github", "http"})
_DEPENDENCY_FETCH_KINDS = frozenset({"github", "http"})


def _is_https_url(value: str) -> bool:
    return value.startswith("https://") and " " not in value and len(value) > len("https://")


def _github_owner_repo_is_valid(value: str) -> bool:
    if value.startswith("github.com/"):
        value = value[len("github.com/"):]
    parts = value.split("/")
    return len(parts) >= 2 and all(parts[:2]) and not any(part in {".", ".."} for part in parts[:2])


def _dependency_source_kind(args):
    if len(args) >= 4:
        return args[2], args[3:]
    if len(args) >= 3:
        source_text = str(_unwrap(args[2]))
        if source_text.startswith(("https://", "http://")):
            return "http", args[2:3]
        if source_text.startswith("github.com/"):
            return "github", args[2:3]
        return "local", args[2:3]
    return "", ()


def _dependency_integrity_is_strong(value: str) -> bool:
    lowered = value.lower()
    if lowered.startswith("sha256:"):
        digest = lowered[len("sha256:"):]
        return len(digest) == 64 and all(char in "0123456789abcdef" for char in digest)
    if lowered.startswith("commit:"):
        commit = lowered[len("commit:"):]
        return 7 <= len(commit) <= 40 and all(char in "0123456789abcdef" for char in commit)
    return False

_CPU_BASELINE_FEATURES = {
    "generic": frozenset(),
    "native": frozenset(),
    "x86_64_v1": frozenset(),
    "x86_64_v2": frozenset({
        "sse3", "ssse3", "sse4.1", "sse4.2", "popcnt", "cx16", "sahf",
    }),
    "x86_64_v3": frozenset({
        "sse3", "ssse3", "sse4.1", "sse4.2", "popcnt", "cx16", "sahf",
        "avx", "avx2", "bmi", "bmi2", "f16c", "fma", "lzcnt", "movbe",
        "xsave",
    }),
    "x86_64_v4": frozenset({
        "sse3", "ssse3", "sse4.1", "sse4.2", "popcnt", "cx16", "sahf",
        "avx", "avx2", "bmi", "bmi2", "f16c", "fma", "lzcnt", "movbe",
        "xsave", "avx512f", "avx512bw", "avx512cd", "avx512dq", "avx512vl",
    }),
    "arm64_generic": frozenset(),
    "arm64_v8_2": frozenset({"v8.2a"}),
}

_CPU_BASELINE_CLANG_MARCH = {
    "generic": None,
    "native": "native",
    "x86_64_v1": "x86-64",
    "x86_64_v2": "x86-64-v2",
    "x86_64_v3": "x86-64-v3",
    "x86_64_v4": "x86-64-v4",
    "arm64_generic": "armv8-a",
    "arm64_v8_2": "armv8.2-a",
}

# Recognised icon role tokens. The taxonomy is fixed so a typo can't
# silently declare a new role no emitter knows about.
_ICON_ROLES_RECOGNIZED = frozenset({
    "applicationPrimary",
    "applicationSecondary",
    "documentType",
    "cursor",
    "notification",
    "splash",
})

# Recognised image-format tokens for iconImageFormat. Matches SYNTAX.md.
_ICON_IMAGE_FORMATS = frozenset({"png", "ico"})

# Recognised colour-depth tokens for iconImageDepth. Matches SYNTAX.md.
_ICON_IMAGE_DEPTHS = frozenset({"bits8", "bits24", "bits32"})

# Recognised platform tokens for iconImagePlatform. `any` means the image
# is consumed by every platform that has an emitter; the three explicit
# tokens limit the image to a single platform's lowering pass. The
# `macos` spelling matches the SYNTAX.md row and the user-facing vocab.
_ICON_IMAGE_PLATFORMS = frozenset({"any", "windows", "macos", "linux"})

# Verb -> property name in the icon_images[name] dict.
_ICON_IMAGE_PROPERTY_VERBS = {
    "iconImageGroup":    "group",
    "iconImagePath":     "path",
    "iconImageFormat":   "format",
    "iconImageWidth":    "width",
    "iconImageHeight":   "height",
    "iconImageScale":    "scale",
    "iconImageDepth":    "depth",
    "iconImagePlatform": "platform",
    "iconImagePurpose":  "purpose",
}


def _register_builtin_middleware_control_enum(prog: Program) -> None:
    """Pre-register the native HTTP ABI's `MiddlewareControl` enum so
    every parsed program can reference its cases without declaring the
    enum itself. The dispatcher in `sem_http_runtime.c` interprets
    middleware return values according to this enum:

      - `continueMiddlewareControl`     == 0 → call the route handler
      - `shortCircuitMiddlewareControl` == 1 → skip handler; send the
        middleware-written response as the final reply

    The enum is `repr CSignedInt32` because middleware operations
    return through the same i32 user-op ABI as handlers. Programs may
    redeclare `enum MiddlewareControl …` (the existing enum-registry
    code will overwrite); doing so is a footgun and tripped by
    semlint SS3611 `redeclaredBuiltinEnum` separately.

    The case names are intentionally verbose (`…MiddlewareControl`
    suffix) so they read as full role identifiers at use sites
    instead of bare `continue` / `shortCircuit` which would collide
    with future control-flow verbs.
    """
    en = Enum("MiddlewareControl")
    en.repr = "CSignedInt32"
    en.cases.append(("continueMiddlewareControl", 0))
    en.cases.append(("shortCircuitMiddlewareControl", 1))
    prog.enums["MiddlewareControl"] = en
    # Register the two case names as integer consts so `returnValue
    # continueMiddlewareControl` (and the shortCircuit counterpart)
    # resolve through the normal const-name path used by every other
    # operation body. Type is the enum NAME (not the repr) so the
    # `_check_result_contract` linter compares apples-to-apples when a
    # middleware op declares `output OP MiddlewareControl`. Codegen
    # resolves `MiddlewareControl` → `CSignedInt32` → i32 via
    # `llvm_type_for`'s enum-repr unwrap, so the i32 user-op return
    # slot still accepts the value without a cast.
    prog.consts["continueMiddlewareControl"] = ("MiddlewareControl", 0)
    prog.consts["shortCircuitMiddlewareControl"] = ("MiddlewareControl", 1)


def _register_builtin_sqlite_surface(prog: Program) -> None:
    """Pre-register the `standard.sqlite` built-in enum / type surface so
    callers can reference `inMemorySqliteOpenMode`, `rowSqliteStepResult`,
    etc., without redeclaring them. The case values are hand-aligned with
    the `SS_SQLITE_*` constants in `sem_sqlite_runtime.h`; mismatched
    values would surface as a wrong-flag handed to sqlite3_open_v2() or a
    misclassified step result, so any change here MUST be paired with a
    matching change to the C ABI header.

    Verbose case names (`inMemorySqliteOpenMode` instead of bare
    `inMemory`) follow the existing MiddlewareControl convention: the
    suffix carries the enum role so reading a use site does not require
    looking up which enum the bare token belongs to.

    `SqliteRowId` is registered as a type alias to `CSignedInt64` so
    `lastInsertRowId` results bind to a descriptive role-typed value
    instead of a generic integer.
    """
    open_mode_enum = Enum("SqliteOpenMode")
    open_mode_enum.repr = "CSignedInt32"
    # Values are the OR'd combinations of SS_SQLITE_OPEN_READONLY (1),
    # READWRITE (2), CREATE (4), MEMORY (8) from sem_sqlite_runtime.h.
    open_mode_enum.cases.append(("readOnlySqliteOpenMode", 1))
    open_mode_enum.cases.append(("readWriteSqliteOpenMode", 2))
    open_mode_enum.cases.append(("readWriteCreateSqliteOpenMode", 6))
    open_mode_enum.cases.append(("inMemorySqliteOpenMode", 14))
    prog.enums["SqliteOpenMode"] = open_mode_enum
    prog.consts["readOnlySqliteOpenMode"] = ("SqliteOpenMode", 1)
    prog.consts["readWriteSqliteOpenMode"] = ("SqliteOpenMode", 2)
    prog.consts["readWriteCreateSqliteOpenMode"] = ("SqliteOpenMode", 6)
    prog.consts["inMemorySqliteOpenMode"] = ("SqliteOpenMode", 14)

    step_result_enum = Enum("SqliteStepResult")
    step_result_enum.repr = "CSignedInt32"
    step_result_enum.cases.append(("rowSqliteStepResult", 100))
    step_result_enum.cases.append(("doneSqliteStepResult", 101))
    prog.enums["SqliteStepResult"] = step_result_enum
    prog.consts["rowSqliteStepResult"] = ("SqliteStepResult", 100)
    prog.consts["doneSqliteStepResult"] = ("SqliteStepResult", 101)

    column_type_enum = Enum("SqliteColumnType")
    column_type_enum.repr = "CSignedInt32"
    column_type_enum.cases.append(("integerSqliteColumnType", 1))
    column_type_enum.cases.append(("floatSqliteColumnType", 2))
    column_type_enum.cases.append(("textSqliteColumnType", 3))
    column_type_enum.cases.append(("blobSqliteColumnType", 4))
    column_type_enum.cases.append(("nullSqliteColumnType", 5))
    prog.enums["SqliteColumnType"] = column_type_enum
    prog.consts["integerSqliteColumnType"] = ("SqliteColumnType", 1)
    prog.consts["floatSqliteColumnType"] = ("SqliteColumnType", 2)
    prog.consts["textSqliteColumnType"] = ("SqliteColumnType", 3)
    prog.consts["blobSqliteColumnType"] = ("SqliteColumnType", 4)
    prog.consts["nullSqliteColumnType"] = ("SqliteColumnType", 5)

    # Descriptive alias for the i64 rowid the native ABI returns from
    # ss_sqlite_database_last_insert_rowid. Keeps role information on
    # the binding instead of leaving a bare CSignedInt64.
    prog.type_aliases["SqliteRowId"] = "CSignedInt64"

    # Each Result-returning sqlite.* call surfaces its failure leg as a
    # role-typed alias over the i32 status code the C ABI actually returns
    # (SS_SQLITE_ERR_* from sem_sqlite_runtime.h). Aliasing to
    # CSignedInt32 lets bindError consume the value with no extra
    # conversion, while still keeping a distinct AS-level name per phase
    # so error domains in user code stay legible. The eight names match
    # the eight Result-returning entry points in the runtime header.
    for failure_alias in (
        "SqliteDatabaseOpenFailure",
        "SqliteDatabaseCloseFailure",
        "SqliteDatabaseExecFailure",
        "SqliteStatementPrepareFailure",
        "SqliteStatementBindFailure",
        "SqliteStatementStepFailure",
        "SqliteStatementResetFailure",
        "SqliteStatementFinalizeFailure",
    ):
        prog.type_aliases[failure_alias] = "CSignedInt32"


def _parse_import_module_args(args):
    if not args:
        return "", None, "malformed"
    if len(args) >= 3 and args[1] == "as":
        return args[0], args[2], "module-as-alias"
    if len(args) == 2 and args[1] != "as":
        return args[1], args[0], "alias-module"
    return args[0], None, "module-only"


_EXPORT_VERB_KIND = {
    "exportOperation": "operation",
    "exportType": "type",
    "exportError": "error",
    "exportCapability": "capability",
    "exportConstant": "constant",
}

_SINGULAR_IMPORT_VERB_KIND = {
    "importOperation": "operation",
    "importType": "type",
    "importError": "error",
    "importCapability": "capability",
    "importConstant": "constant",
}


def _exported_symbols_for(prog: Program, module_path: str, kind: str):
    return prog.exports.get(kind, {}).get(module_path, set())


def _finalize_import_aliases(prog: Program) -> None:
    for module_path, alias in prog.imports:
        if not alias:
            continue
        prog.import_aliases[alias] = module_path
        for operation_name in _exported_symbols_for(prog, module_path, "operation"):
            prog.operation_aliases[f"{alias}.{operation_name}"] = operation_name
        for type_name in _exported_symbols_for(prog, module_path, "type"):
            if type_name in prog.type_aliases:
                prog.type_aliases.setdefault(f"{alias}.{type_name}", prog.type_aliases[type_name])
            else:
                prog.type_aliases.setdefault(f"{alias}.{type_name}", [type_name])
        for error_name in _exported_symbols_for(prog, module_path, "error"):
            if error_name in prog.errors:
                prog.errors.setdefault(f"{alias}.{error_name}", prog.errors[error_name])
            prog.type_aliases.setdefault(f"{alias}.{error_name}", [error_name])
        for capability_name in _exported_symbols_for(prog, module_path, "capability"):
            if capability_name in prog.capabilities:
                prog.capabilities.setdefault(
                    f"{alias}.{capability_name}", dict(prog.capabilities[capability_name]))
        for const_name in _exported_symbols_for(prog, module_path, "constant"):
            if const_name in prog.consts:
                prog.consts.setdefault(f"{alias}.{const_name}", prog.consts[const_name])

    for kind, local_name, module_alias, exported_name in prog.singular_imports:
        if "*" in (local_name, module_alias, exported_name):
            raise SyntaxError(
                f"{kind} import: wildcard imports are not supported; import one exported symbol")
        module_path = prog.import_aliases.get(module_alias)
        if module_path is None:
            raise SyntaxError(
                f"{kind} import: unknown module alias `{module_alias}`")
        if exported_name not in _exported_symbols_for(prog, module_path, kind):
            raise SyntaxError(
                f"{kind} import: `{module_alias}.{exported_name}` is not exported")
        if kind == "operation":
            prog.operation_aliases[local_name] = exported_name
        elif kind == "type":
            if exported_name in prog.type_aliases:
                prog.type_aliases.setdefault(local_name, prog.type_aliases[exported_name])
            else:
                prog.type_aliases.setdefault(local_name, [exported_name])
        elif kind == "error":
            if exported_name in prog.errors:
                prog.errors.setdefault(local_name, prog.errors[exported_name])
            prog.type_aliases.setdefault(local_name, [exported_name])
        elif kind == "capability":
            if exported_name in prog.capabilities:
                prog.capabilities.setdefault(local_name, dict(prog.capabilities[exported_name]))
        elif kind == "constant":
            if exported_name in prog.consts:
                prog.consts.setdefault(local_name, prog.consts[exported_name])


def parse(source: str) -> Program:
    prog = Program()
    _register_builtin_middleware_control_enum(prog)
    _register_builtin_sqlite_surface(prog)
    active_html_template = None
    active_html_base_indent = None
    lines = list(enumerate(source.splitlines(), start=1))
    index = 0

    def _finish_html_body():
        nonlocal active_html_template, active_html_base_indent
        active_html_template = None
        active_html_base_indent = None

    while index < len(lines):
        lineno, raw = lines[index]
        index += 1
        prog.source_lines[lineno] = raw

        if active_html_template is not None:
            if raw.strip() and raw[0].isspace():
                indent = len(raw) - len(raw.lstrip(" \t"))
                if active_html_base_indent is None:
                    active_html_base_indent = indent
                trim_count = min(active_html_base_indent, indent)
                active_html_template.body_lines.append(
                    (raw[trim_count:], lineno))
                continue
            if not raw.strip():
                active_html_template.body_lines.append(("", lineno))
                continue
            # A non-empty column-0 line ends the HTML syntax island and is
            # immediately reprocessed as normal SemanticScript. This keeps
            # `htmlBody` as the only indentation-sensitive exception.
            _finish_html_body()

        toks = tokenize_line(raw)
        if not toks:
            continue
        if toks[0] == "#":
            body = toks[1] if len(toks) > 1 else ""
            # Preserve `# group NAME` / `# endGroup NAME` anchors so the
            # linter can pair them (spec §7: groups are attention anchors).
            anchor = _parse_group_anchor(body)
            if anchor is not None:
                kind, name = anchor
                entry = (kind, name, lineno)
                if prog.current_op is not None:
                    prog.current_op.lines.append(("__groupAnchor__", entry, lineno))
                else:
                    prog.module_group_anchors.append(entry)
                continue
            # Preserve typed semantic comments per spec §7. These are
            # first-class context attached to the most recent operation.
            typed = _parse_typed_comment(body)
            if typed is not None:
                kind, text = typed
                if prog.current_op is not None:
                    prog.current_op.typed_comments.append((kind, text, lineno))
                    prog.current_op.lines.append(
                        ("__typedComment__", (kind, text), lineno))
                else:
                    prog.module_typed_comments.append((kind, text, lineno))
            continue
        verb = toks[0]
        args = toks[1:]
        try:
            handle_top(prog, verb, args, lineno)
            if verb == "htmlBody":
                if not args:
                    raise SyntaxError("htmlBody requires: htmlBody TEMPLATE")
                active_html_template = prog.html_templates.get(args[0])
                if active_html_template is None:
                    raise SyntaxError(f"htmlBody references unknown htmlTemplate: {args[0]}")
                active_html_base_indent = None
        except SyntaxError:
            raise
        except Exception as e:
            raise SyntaxError(f"line {lineno}: {e}\n  >> {raw}") from e
    _finish_html_body()
    _finalize_import_aliases(prog)
    return prog


def _is_build_tape_path(source_path: str) -> bool:
    return os.path.basename(str(source_path)).lower() in ("build.sem", "build.sscript")


def _looks_like_build_tape(source: str) -> bool:
    for raw in source.splitlines():
        toks = tokenize_line(raw)
        if toks and toks[0] == "buildProject":
            return True
    return False


def _normalize_build_tape_path(source_path: str, path_text: str,
                               source_root_text: str = None) -> str:
    base_dir = os.path.dirname(os.path.abspath(source_path))
    if source_root_text:
        root = _unwrap(source_root_text)
        if root and not os.path.isabs(str(root)):
            base_dir = os.path.abspath(os.path.join(base_dir, str(root)))
        elif root:
            base_dir = os.path.abspath(str(root))
    raw_path = str(_unwrap(path_text))
    if os.path.isabs(raw_path):
        return os.path.abspath(raw_path)
    return os.path.abspath(os.path.join(base_dir, raw_path))


def _validate_build_tape_source(source: str, source_path: str) -> None:
    """Strict build.sem validation for rows that affect project tooling.

    The normal SemanticScript parser accepts many future rows as metadata so
    examples stay parseable. A build tape is different: it is the project
    contract, so malformed project rows should fail before imports/codegen.
    """
    build_projects = []
    rows_by_project = {}
    singleton_seen = {}
    source_roots = {}
    target_runtime_by_project = {}
    allowed_non_project_verbs = (
        {"buildProject", "project", "target", "runtime", "entry", "importModule",
         "moduleFolder"}
        | set(_PROJECT_METADATA_VERBS)
        | {
            "metadata",
            "iconRoleDefinition", "icon", "iconRole", "iconPurpose",
            "iconImage", "iconImageGroup", "iconImagePath", "iconImageFormat",
            "iconImageWidth", "iconImageHeight", "iconImageScale",
            "iconImageDepth", "iconImagePlatform", "iconImagePurpose",
        }
    )

    for lineno, raw in enumerate(source.splitlines(), start=1):
        toks = tokenize_line(raw)
        if not toks or toks[0] == "#":
            continue
        verb = toks[0]
        args = toks[1:]
        if verb == "buildProject":
            if len(args) < 1:
                raise SyntaxError(f"line {lineno}: buildProject requires: buildProject PROJECT")
            build_projects.append(args[0])
            continue
        if verb == "project":
            if len(args) < 1:
                raise SyntaxError(f"line {lineno}: project requires: project NAME")
            continue
        if verb not in _BUILD_TAPE_PROJECT_VERBS:
            if verb not in allowed_non_project_verbs:
                raise SyntaxError(
                    f"line {lineno}: unknown build-tape row `{verb}`")
            continue
        minimum_arity = _BUILD_TAPE_MIN_ARITY.get(verb, 2)
        if len(args) < minimum_arity:
            raise SyntaxError(
                f"line {lineno}: {verb} requires at least {minimum_arity} "
                "argument(s)")
        project_name = args[0]
        rows_by_project.setdefault(project_name, set()).add(verb)
        if verb in _BUILD_TAPE_SINGLETON_VERBS:
            key = (project_name, verb)
            if key in singleton_seen:
                previous_line = singleton_seen[key]
                raise SyntaxError(
                    f"line {lineno}: duplicate `{verb}` for project "
                    f"`{project_name}`; first declared on line {previous_line}")
            singleton_seen[key] = lineno
        if verb in _BUILD_TAPE_CHOICES:
            value = str(_unwrap(args[1]))
            if value not in _BUILD_TAPE_CHOICES[verb]:
                raise SyntaxError(
                    f"line {lineno}: {verb} value `{value}` is invalid; "
                    f"expected one of {sorted(_BUILD_TAPE_CHOICES[verb])}")
        if verb == "cpuTune":
            value = str(_unwrap(args[1]))
            if not _CPU_FEATURE_RE.match(value):
                raise SyntaxError(
                    f"line {lineno}: cpuTune value `{value}` must be a CPU "
                    "name token such as generic, native, or alderlake")
        if verb == "cpuFeature":
            feature_name = str(_unwrap(args[1]))
            feature_state = str(_unwrap(args[2])) if len(args) >= 3 else ""
            if not _CPU_FEATURE_RE.match(feature_name):
                raise SyntaxError(
                    f"line {lineno}: cpuFeature name `{feature_name}` is invalid")
            if feature_state not in _CPU_FEATURE_STATES:
                raise SyntaxError(
                    f"line {lineno}: cpuFeature state `{feature_state}` is "
                    "invalid; expected on or off")
        if verb == "optLevel":
            try:
                opt_level = int(str(_unwrap(args[1])))
            except (TypeError, ValueError):
                raise SyntaxError(f"line {lineno}: optLevel must be an integer 0..3")
            if opt_level < 0 or opt_level > 3:
                raise SyntaxError(f"line {lineno}: optLevel must be in range 0..3")
        if verb == "nativeHttpPort":
            try:
                port = int(str(_unwrap(args[1])))
            except (TypeError, ValueError):
                raise SyntaxError(f"line {lineno}: nativeHttpPort must be an integer")
            if port <= 0 or port > 65535:
                raise SyntaxError(f"line {lineno}: nativeHttpPort must be 1..65535")
        if verb == "buildFolderName":
            folder_name = str(_unwrap(args[1]))
            normalized = folder_name.replace("\\", os.sep).replace("/", os.sep)
            if (os.path.isabs(normalized)
                    or os.path.dirname(normalized)
                    or normalized in ("", ".", "..")):
                raise SyntaxError(
                    f"line {lineno}: buildFolderName must be one folder name, not a path")
        if verb == "dependencySource":
            kind, payload = _dependency_source_kind(args)
            if kind not in _DEPENDENCY_SOURCE_KINDS:
                raise SyntaxError(
                    f"line {lineno}: dependencySource kind `{kind}` is invalid; "
                    "expected local, path, github, or http")
            if kind == "http":
                url = str(_unwrap(payload[0])) if payload else ""
                if not _is_https_url(url):
                    raise SyntaxError(
                        f"line {lineno}: dependencySource http requires an https URL")
            if kind == "github":
                repo = str(_unwrap(payload[0])) if payload else ""
                if not _github_owner_repo_is_valid(repo):
                    raise SyntaxError(
                        f"line {lineno}: dependencySource github requires OWNER/REPO")
        if verb == "dependencyFetch":
            fetch_kind = str(_unwrap(args[2]))
            if fetch_kind not in _DEPENDENCY_FETCH_KINDS:
                raise SyntaxError(
                    f"line {lineno}: dependencyFetch kind `{fetch_kind}` is invalid; "
                    "expected github or http")
            if fetch_kind == "http":
                url = str(_unwrap(args[3])) if len(args) >= 4 else ""
                if not _is_https_url(url):
                    raise SyntaxError(
                        f"line {lineno}: dependencyFetch http requires an https URL")
            if fetch_kind == "github":
                repo = str(_unwrap(args[3])) if len(args) >= 4 else ""
                ref = str(_unwrap(args[4])) if len(args) >= 5 else ""
                if not _github_owner_repo_is_valid(repo) or not ref:
                    raise SyntaxError(
                        f"line {lineno}: dependencyFetch github requires OWNER/REPO REF")
        if verb == "dependencyIntegrity":
            integrity = str(_unwrap(args[2]))
            if not _dependency_integrity_is_strong(integrity):
                raise SyntaxError(
                    f"line {lineno}: dependencyIntegrity must be sha256:<64 hex> "
                    "or commit:<7-40 hex>")
        if verb == "sourceRoot":
            source_roots[project_name] = args[1]
        if verb == "targetRuntime":
            target_runtime_by_project[project_name] = str(_unwrap(args[1]))
        if verb in _BUILD_TAPE_PATH_VERBS:
            root_for_project = source_roots.get(project_name)
            _normalize_build_tape_path(source_path, args[1], root_for_project)
        if verb == "registerModule":
            root_for_project = source_roots.get(project_name)
            _normalize_build_tape_path(source_path, args[2], root_for_project)

    if len(build_projects) != 1:
        raise SyntaxError(
            f"build.sem requires exactly one buildProject row; found {len(build_projects)}")
    project_name = build_projects[0]
    project_rows = rows_by_project.get(project_name, set())
    missing_rows = sorted(_BUILD_TAPE_REQUIRED_VERBS - project_rows)
    if missing_rows:
        raise SyntaxError(
            f"buildProject `{project_name}` is missing required row(s): "
            + ", ".join(missing_rows))
    for other_project in sorted(rows_by_project):
        if other_project != project_name:
            raise SyntaxError(
                f"build tape row targets `{other_project}`, but active "
                f"buildProject is `{project_name}`")
    target_runtime = target_runtime_by_project.get(project_name)
    if target_runtime in ("nativeExe", "webServer", "windowsGui") and "mainFile" not in project_rows:
        raise SyntaxError(
            f"buildProject `{project_name}` targetRuntime `{target_runtime}` "
            "requires mainFile PROJECT \"PATH\"")
    if target_runtime == "nativeExe" and "mainOperation" not in project_rows:
        raise SyntaxError(
            f"buildProject `{project_name}` targetRuntime `nativeExe` "
            "requires mainOperation PROJECT OPERATION")


def _parse_group_anchor(comment_body: str):
    """If a comment body opens with `group NAME` or `endGroup NAME`, return
    the parsed kind+name. Otherwise return None."""
    parts = comment_body.split()
    if not parts:
        return None
    kind = parts[0]
    if kind not in ("group", "endGroup"):
        return None
    if len(parts) < 2:
        return None
    return (kind, parts[1])


# Spec §7 — typed semantic comments. The kind prefix must be followed
# by a colon. The body after the colon is the freeform context. Recognized
# kinds match the spec's enumeration.
_TYPED_COMMENT_KINDS = {
    "rationale", "invariant", "warning", "agent",
    "memory", "concurrency", "timing", "failure",
    "security", "dependency", "observability", "test", "todo",
}


def _parse_typed_comment(comment_body: str):
    """If a comment body is `<kind>: <text>` where kind is a recognized
    typed-comment kind, return `(kind, text)`. Otherwise return None."""
    if ":" not in comment_body:
        return None
    kind, _, text = comment_body.partition(":")
    kind = kind.strip()
    if kind not in _TYPED_COMMENT_KINDS:
        return None
    return (kind, text.strip())


def handle_top(prog: Program, verb: str, args, lineno: int):
    # ===== always-allowed top-level decls =====
    if verb == "project":
        prog.project_name = args[0]
        return
    if verb == "target":
        prog.targets.append(args[0])
        return
    if verb == "runtime":
        return
    if verb == "module":
        if not args:
            raise SyntaxError("module requires: module DOTTED_NAME")
        module_name = args[0]
        if not _MODULE_NAME_RE.match(module_name):
            raise SyntaxError(
                f"module: `{module_name}` is not a valid dotted SemanticScript namespace")
        if prog.module_name is not None and prog.module_name != module_name:
            raise SyntaxError(
                f"module: conflicting module declarations `{prog.module_name}` "
                f"(line {prog.module_line}) and `{module_name}`")
        prog.module_name = module_name
        prog.module_line = lineno
        return
    if verb == "mode":
        # mode NAME — declares an honest classification of the program's
        # algorithm. The closed set of supported values is documented in
        # AST.md §10:
        #   capturedOutputReplay  the program's stdout is a transcript captured
        #                         from a sibling implementation rather than the
        #                         output of a re-run algorithm in SemanticScript
        # Unknown mode names are rejected so a typo cannot quietly disable
        # the trust-boundary marker required by spec §2 law 19.
        if not args:
            raise SyntaxError("mode requires: mode NAME")
        if args[0] not in _KNOWN_MODES:
            raise SyntaxError(
                f"mode: `{args[0]}` is not a known mode value; expected one of "
                f"{sorted(_KNOWN_MODES)}")
        prog.modes.append(args[0])
        return
    if verb == "entry":
        prog.entry = (args[0], args[1])
        return

    # ----- project metadata lowered to OS-native formats at emit time -----
    if verb in _PROJECT_METADATA_VERBS:
        if not args:
            raise SyntaxError(f"{verb} requires: {verb} \"value\"")
        value = _unwrap(args[0])
        if not isinstance(value, str):
            raise SyntaxError(
                f"{verb} requires a quoted string value; got {value!r}")
        if verb == "version" and not _PROJECT_VERSION_RE.match(value):
            raise SyntaxError(
                f"version: `{value}` is not a valid 4-part version number "
                f"(expected dotted form like `1.0.0.0` or `1.2.3`)")
        prog.project_metadata[verb] = value
        return
    if verb == "metadata":
        if len(args) < 2:
            raise SyntaxError("metadata requires: metadata \"key\" \"value\"")
        key = _unwrap(args[0])
        value = _unwrap(args[1])
        if not isinstance(key, str) or not key:
            raise SyntaxError("metadata: key must be a non-empty quoted string")
        if not isinstance(value, str):
            raise SyntaxError("metadata: value must be a quoted string")
        prog.custom_metadata[key] = value
        return

    # ----- icon registry (build-time assets lowered to OS-native formats) -----
    if verb == "iconRoleDefinition":
        if len(args) < 2:
            raise SyntaxError("iconRoleDefinition requires: iconRoleDefinition ROLE \"text\"")
        role = args[0]
        if role not in _ICON_ROLES_RECOGNIZED:
            raise SyntaxError(
                f"iconRoleDefinition: `{role}` is not a recognised role token; "
                f"expected one of {sorted(_ICON_ROLES_RECOGNIZED)}")
        prog.icon_role_definitions[role] = _unwrap(args[1])
        return
    if verb == "icon":
        if not args:
            raise SyntaxError("icon requires: icon GROUP_NAME")
        group_name = args[0]
        if group_name in prog.icon_groups:
            raise SyntaxError(f"icon: group `{group_name}` already declared")
        prog.icon_groups[group_name] = {
            "role": None, "purpose": None, "line": lineno,
        }
        return
    if verb == "iconRole":
        if len(args) < 2:
            raise SyntaxError("iconRole requires: iconRole GROUP ROLE")
        group_name, role = args[0], args[1]
        if group_name not in prog.icon_groups:
            raise SyntaxError(f"iconRole: unknown icon group `{group_name}`")
        prog.icon_groups[group_name]["role"] = role
        return
    if verb == "iconPurpose":
        if len(args) < 2:
            raise SyntaxError("iconPurpose requires: iconPurpose GROUP \"text\"")
        group_name = args[0]
        if group_name not in prog.icon_groups:
            raise SyntaxError(f"iconPurpose: unknown icon group `{group_name}`")
        prog.icon_groups[group_name]["purpose"] = _unwrap(args[1])
        return
    if verb == "iconImage":
        if not args:
            raise SyntaxError("iconImage requires: iconImage IMAGE_NAME")
        image_name = args[0]
        if image_name in prog.icon_images:
            raise SyntaxError(f"iconImage: image `{image_name}` already declared")
        prog.icon_images[image_name] = {
            "group": None, "path": None, "format": None,
            "width": None, "height": None, "scale": 1,
            "depth": "bits32", "platform": "any", "purpose": None,
            "line": lineno,
        }
        return
    if verb in _ICON_IMAGE_PROPERTY_VERBS:
        if len(args) < 2:
            raise SyntaxError(f"{verb} requires: {verb} IMAGE_NAME VALUE")
        image_name = args[0]
        if image_name not in prog.icon_images:
            raise SyntaxError(f"{verb}: unknown iconImage `{image_name}`")
        property_key = _ICON_IMAGE_PROPERTY_VERBS[verb]
        raw_value = args[1]
        if property_key in ("path", "purpose"):
            value = _unwrap(raw_value)
            if not isinstance(value, str):
                raise SyntaxError(f"{verb}: value must be a quoted string")
        elif property_key in ("width", "height", "scale"):
            try:
                value = int(raw_value)
            except (TypeError, ValueError):
                raise SyntaxError(
                    f"{verb}: value must be a positive integer; got {raw_value!r}")
            if value <= 0:
                raise SyntaxError(f"{verb}: value must be positive")
        elif property_key == "format":
            if raw_value not in _ICON_IMAGE_FORMATS:
                raise SyntaxError(
                    f"iconImageFormat: `{raw_value}` not in "
                    f"{sorted(_ICON_IMAGE_FORMATS)}")
            value = raw_value
        elif property_key == "depth":
            if raw_value not in _ICON_IMAGE_DEPTHS:
                raise SyntaxError(
                    f"iconImageDepth: `{raw_value}` not in "
                    f"{sorted(_ICON_IMAGE_DEPTHS)}")
            value = raw_value
        elif property_key == "platform":
            if raw_value not in _ICON_IMAGE_PLATFORMS:
                raise SyntaxError(
                    f"iconImagePlatform: `{raw_value}` not in "
                    f"{sorted(_ICON_IMAGE_PLATFORMS)}")
            value = raw_value
        elif property_key == "group":
            value = raw_value
            if value not in prog.icon_groups:
                raise SyntaxError(
                    f"iconImageGroup: unknown icon group `{value}`")
        else:
            value = raw_value
        prog.icon_images[image_name][property_key] = value
        return

    # ----- dependency contract -----
    if verb in ("dependency", "dependencyEffect", "dependencyExports",
                "dependencyFunction", "dependencyFunctionInput",
                "dependencyFunctionOutput", "dependencyFunctionEffect",
                "dependencyFunctionAsync"):
        return
    if verb == "importModule":
        # Compatibility:
        #   importModule DOTTED.PATH [as ALIAS]
        # Preferred project form:
        #   importModule ALIAS DOTTED.PATH
        module_path, alias, _syntax = _parse_import_module_args(args)
        prog.imports.append((module_path, alias))
        if alias:
            prog.import_aliases[alias] = module_path
        return
    if verb in _EXPORT_VERB_KIND:
        if len(args) < 2:
            raise SyntaxError(f"{verb} requires: {verb} MODULE_PATH SYMBOL")
        kind = _EXPORT_VERB_KIND[verb]
        prog.exports.setdefault(kind, {}).setdefault(args[0], set()).add(args[1])
        return
    if verb in _SINGULAR_IMPORT_VERB_KIND:
        if len(args) < 3:
            raise SyntaxError(
                f"{verb} requires: {verb} LOCAL_NAME MODULE_ALIAS EXPORTED_NAME")
        prog.singular_imports.append((
            _SINGULAR_IMPORT_VERB_KIND[verb],
            args[0],
            args[1],
            args[2],
        ))
        return

    # ----- type universe -----
    if verb == "type":
        if len(args) < 2:
            raise SyntaxError("type requires: type ALIAS UNDERLYING_TYPE [EXTRA_ARGS…]")
        # Spec §5 allows parameterized type expressions like
        # `type EmailAddress SmallString 254` and
        # `type CreateCustomerResult Result Customer CreateCustomerError`.
        # Store the FULL tail so the type's parameters survive lookup;
        # callers that want the bare head call `resolve_alias` (which
        # returns the head token after chain resolution) and callers that
        # want the full expression read `prog.type_aliases[name]` directly.
        prog.type_aliases[args[0]] = list(args[1:])
        return
    if verb in ("typeInvariant", "typeRepresentation", "typeTrust",
                "typeMemory", "typeLayout"):
        # All record type-level metadata under a single map indexed by type
        if not args:
            raise SyntaxError(f"{verb} requires a target type name")
        meta = prog.type_metadata.setdefault(args[0], {})
        key = verb[4:].lower() if verb != "typeInvariant" else "invariant"
        # typeInvariant is multi-valued, the rest are scalar latest-wins
        if verb == "typeInvariant":
            meta.setdefault("invariant", []).append(_unwrap(args[1]) if len(args) > 1 else "")
        else:
            meta[key] = [_unwrap(t) for t in args[1:]]
        return

    # ----- error type universe -----
    if verb == "error":
        prog.errors.setdefault(args[0], [])
        return
    if verb == "errorCase":
        if len(args) < 2:
            raise SyntaxError("errorCase requires: errorCase ERRTYPE VARIANT [CAUSE]")
        cause = args[2] if len(args) > 2 else None
        prog.errors.setdefault(args[0], []).append((args[1], cause))
        return

    # ----- records / fields -----
    if verb == "record":
        rec = Record(args[0])
        i = 1
        while i < len(args):
            key = args[i]
            if key == "layout" and i + 1 < len(args):
                rec.layout = args[i + 1]
                i += 2
            elif key == "align" and i + 1 < len(args):
                rec.align = int(args[i + 1])
                i += 2
            else:
                i += 1
        prog.records[rec.name] = rec
        return
    if verb == "field":
        # field RECORD_NAME FIELD_NAME FIELD_TYPE
        if len(args) < 3:
            raise SyntaxError("field requires: field RECORD_NAME FIELD_NAME FIELD_TYPE")
        rec = prog.records.get(args[0])
        if rec is None:
            raise SyntaxError(f"field references unknown record: {args[0]}")
        rec.fields.append((args[1], args[2]))
        return

    # ----- enums -----
    if verb == "enum":
        en = Enum(args[0])
        if len(args) >= 3 and args[1] == "repr":
            en.repr = args[2]
        prog.enums[en.name] = en
        return
    if verb == "enumCase":
        if len(args) < 2:
            raise SyntaxError("enumCase requires: enumCase ENUM CASE [VALUE]")
        en = prog.enums.get(args[0])
        if en is None:
            raise SyntaxError(f"enumCase references unknown enum: {args[0]}")
        value = _unwrap(args[2]) if len(args) > 2 else None
        en.cases.append((args[1], value))
        return

    # ----- web servers -----
    if verb == "webServer":
        ws = WebServer(args[0])
        prog.web_servers[ws.name] = ws
        return
    if verb == "serverHost":
        prog.web_servers[args[0]].host = _unwrap(args[1])
        return
    if verb == "serverPort":
        prog.web_servers[args[0]].port = int(args[1])
        return
    if verb == "route":
        # route SERVER METHOD PATH HANDLER_OPERATION
        if len(args) < 4:
            raise SyntaxError("route requires: route SERVER METHOD PATH HANDLER_OPERATION")
        ws = prog.web_servers.get(args[0])
        if ws is None:
            raise SyntaxError(f"route references unknown webServer: {args[0]}")
        ws.routes.append((args[1], _unwrap(args[2]), args[3]))
        return
    if verb == "routeTimeout":
        ws = prog.web_servers[args[0]]
        ws.timeouts[args[1]] = args[2]
        return
    if verb == "routeMiddleware":
        ws = prog.web_servers[args[0]]
        ws.middleware.append((args[1], args[2]))
        return
    if verb in ("routeTimeoutOptOut", "routeMiddlewareOptOut"):
        # `routeTimeoutOptOut SERVER PATH "rationale"` /
        # `routeMiddlewareOptOut SERVER PATH "rationale"` — declares that
        # a route deliberately omits the cross-cutting timeout /
        # middleware contract. semsc accepts as metadata; semlint SS3604
        # uses it to suppress the coverage-drift diagnostic. Stored under
        # the server's hard_metadata bucket so tooling can inspect it.
        if len(args) < 2:
            raise SyntaxError(
                f"{verb} requires: {verb} SERVER PATH \"rationale\"")
        prog.hard_metadata.setdefault(args[0], {}).setdefault(verb, []).append(
            tuple(_unwrap(t) for t in args[1:]))
        return

    # ----- first-class HTML / SSX templates -----
    if verb == "htmlTemplate":
        if not args:
            raise SyntaxError("htmlTemplate requires: htmlTemplate NAME")
        name = args[0]
        if name in prog.html_templates:
            raise SyntaxError(f"htmlTemplate: template `{name}` already declared")
        prog.html_templates[name] = HtmlTemplate(name, lineno)
        return
    if verb == "htmlArg":
        if len(args) < 3:
            raise SyntaxError("htmlArg requires: htmlArg TEMPLATE ARG_NAME TYPE")
        template_name, arg_name, arg_type = args[0], args[1], args[2]
        template = prog.html_templates.get(template_name)
        if template is None:
            raise SyntaxError(
                f"htmlArg references unknown htmlTemplate: {template_name}")
        if any(existing_name == arg_name for existing_name, _typ, _line in template.args):
            raise SyntaxError(
                f"htmlArg: template `{template_name}` already declares `{arg_name}`")
        template.args.append((arg_name, arg_type, lineno))
        return
    if verb == "htmlBody":
        if not args:
            raise SyntaxError("htmlBody requires: htmlBody TEMPLATE")
        template_name = args[0]
        template = prog.html_templates.get(template_name)
        if template is None:
            raise SyntaxError(f"htmlBody references unknown htmlTemplate: {template_name}")
        if template.body_line:
            raise SyntaxError(
                f"htmlBody: template `{template_name}` already declares a body")
        template.body_line = lineno
        template.body_lines = []
        return

    # ----- codecs / validators / mappers / boundaries / adapters -----
    if verb in ("codec", "validator", "mapper", "adapter", "boundary", "jsonCodec"):
        # All of these have the shape `verb NAME [attrs…]`. We index them by
        # name and keep their raw arg tail so tooling can read the contract.
        bucket = {
            "codec": prog.codecs, "jsonCodec": prog.codecs,
            "validator": prog.validators,
        }.get(verb, prog.policies)
        bucket[args[0]] = {"kind": verb, "attrs": args[1:]}
        return
    if verb in ("schema", "unknownFields", "guarantee", "input", "output", "purpose"):
        # These continue an abstraction declaration started earlier OR
        # (for `input`/`output`/`purpose`) belong to an operation header.
        if verb in ("purpose", "input", "output") and prog.current_op is not None:
            # Spec §9 ownership: each header line's first arg names the
            # operation it belongs to. Reject if it doesn't match.
            if args and args[0] != prog.current_op.name:
                raise SyntaxError(
                    f"{verb}: owner `{args[0]}` does not match current "
                    f"operation `{prog.current_op.name}` (spec §9 — header "
                    f"lines must reference their own operation by name "
                    f"for checkability)")
            prog.current_op.lines.append((verb, args, lineno))
            return
        # Attach to whatever named abstraction was declared most recently.
        # For simplicity we just hard-record under hard_metadata.
        if not args:
            raise SyntaxError(f"{verb} requires a target name")
        prog.hard_metadata.setdefault(args[0], {}).setdefault(verb, []).extend(
            [_unwrap(t) for t in args[1:]])
        return

    # ----- policies -----
    if verb in ("policy", "retryPolicy", "errorPolicy", "timeoutBudget"):
        prog.policies[args[0]] = {"kind": verb, "attrs": args[1:]}
        return

    # ----- resources -----
    if verb == "resource":
        prog.resources[args[0]] = {"attrs": args[1:]}
        return
    if verb in ("resourceKey", "resourceValue", "resourceKind"):
        r = prog.resources.setdefault(args[0], {})
        r[verb] = args[1:]
        return

    # ----- capabilities / authority -----
    if verb == "capability":
        # capability NAME EFFECT_PATH ACCESS
        if len(args) < 3:
            raise SyntaxError("capability requires: capability NAME EFFECT_PATH ACCESS")
        prog.capabilities[args[0]] = {"effect": args[1], "access": args[2]}
        return
    if verb == "authority":
        # authority OPERATION EFFECT_PATH ACCESS  (top-level grant form)
        if len(args) < 3:
            raise SyntaxError("authority requires: authority TARGET EFFECT_PATH ACCESS")
        prog.hard_metadata.setdefault(args[0], {}).setdefault(
            "authority", []).append(" ".join(args[1:]))
        return

    # ----- buildConstant: hoist a build-tape value into the program
    # `buildConstant PROJECT NAME TYPE VALUE` registers VALUE under
    # NAME on prog.consts, making it visible to every imported module
    # exactly as if a `storage module immutable NAME TYPE VALUE` row
    # had been declared at the top of the program. The PROJECT arg
    # exists for parity with the other build-tape rows (the build-
    # tape pre-pass uses it to associate the row with the active
    # buildProject); the codegen path only cares about (NAME, TYPE,
    # VALUE). Standard build-tape verb — not a language extension. -----
    if verb == "buildConstant":
        if len(args) < 4:
            raise SyntaxError(
                "buildConstant requires: buildConstant PROJECT NAME TYPE VALUE")
        const_name = args[1]
        const_type = args[2]
        raw_value = _unwrap(args[3])
        # Numeric vs string discrimination: if the unwrap left the
        # value bare (no surrounding quotes in source), it was a
        # numeric / identifier literal — keep as-is for emit_const_value.
        # Quoted strings come back as plain Python strings already.
        prog.consts[const_name] = (const_type, raw_value)
        return

    # ----- mutex / shared / channel (top-level concurrency primitives) -----
    if verb in ("mutex", "shared", "channel"):
        prog.hard_metadata.setdefault(args[0], {})["kind"] = verb
        prog.hard_metadata[args[0]]["attrs"] = args[1:]
        return

    # ----- hard metadata applicable to top-level OR operation -----
    if verb in ("failure", "security", "timing", "observability"):
        if prog.current_op is not None:
            prog.current_op.lines.append((verb, args, lineno))
            return
        if not args:
            raise SyntaxError(f"{verb} requires a target name")
        prog.hard_metadata.setdefault(args[0], {}).setdefault(verb, []).extend(
            [_unwrap(t) for t in args[1:]])
        return
    if verb == "testCovers":
        if len(args) < 2:
            raise SyntaxError("testCovers requires: testCovers TEST_NAME TARGET_NAME")
        prog.test_covers.append((args[0], args[1]))
        return

    # ----- operations -----
    if verb == "operation":
        op = Operation(args[0], decl_line=lineno)
        prog.operations[args[0]] = op
        prog.current_op = op
        return

    # ----- const can appear both top-level and inside an operation -----
    if verb == "const":
        if len(args) < 3:
            raise SyntaxError("const requires: const NAME TYPE VALUE")
        name = args[0]
        typ = args[1]
        value = _unwrap(args[2])
        # Scope the const: declarations inside an operation body live in
        # that operation's local symbol table, NOT in the global map.
        # This prevents accidental cross-operation visibility and matches
        # the AST distinction between top-level Const and body ConstStmt.
        if prog.current_op is not None:
            prog.current_op.consts[name] = (typ, value)
            prog.current_op.lines.append((verb, args, lineno))
        else:
            prog.consts[name] = (typ, value)
        return

    # ===== inside-an-operation verbs =====
    if verb in BODY_VERBS:
        if prog.current_op is None:
            raise SyntaxError(f"{verb} appears outside any operation")
        # Spec §9 — operation header lines (input/output/effect/memory/async/
        # purpose/invariant/warning + hard-metadata kinds) include the
        # owning operation's name as the first arg so each line is
        # independently checkable. Enforce that the name matches.
        if verb in HEADER_VERBS_WITH_OWNERSHIP and args:
            if args[0] != prog.current_op.name:
                raise SyntaxError(
                    f"{verb}: owner `{args[0]}` does not match current "
                    f"operation `{prog.current_op.name}` (spec §9 — header "
                    f"lines must reference their own operation by name "
                    f"for checkability)")
        prog.current_op.lines.append((verb, args, lineno))
        return

    # ===== refined-syntax / experimental verbs =====
    # The refined-syntax surface in sem/refined_syntax_demo.sscript
    # adds many declarative verbs (section, runtimeBinding*, collectionOp*,
    # group*, recordBuilder/recordSet/recordBuild*, jsonCodec*, retry*,
    # listType/sliceType/arrayType/mapType/smallList*, domainLiteral*,
    # trustBoundary*, sharedState*, dependencyPath/Failure, intrinsicName,
    # storage, literal/literalBytes/literalDigest/literalPreview/...). We
    # accept them as metadata so the file can be parsed, linted, and
    # codegen'd into a runnable stub. A few have semantic meaning carried
    # over from older verbs (storage = const-with-scope; domainLiteral =
    # typed literal binding; sharedState = process-level zero-initialized
    # state). Register those as consts so downstream `arg <call> <name>`
    # references resolve. The rest are stored under prog.hard_metadata.
    if verb == "storage" and len(args) >= 4:
        # `storage <scope> <mutability> NAME TYPE [VALUE]` — `module immutable`
        # is the common case and maps directly onto the existing const form.
        # We accept any scope/mutability for parse-cleanliness. Scope routes
        # the binding: `module` stays at top-level even when current_op is
        # set (operations later in the file would otherwise capture it).
        # `module mutable` is additionally registered in prog.mutable_globals
        # so codegen emits a real LLVM global with load/store semantics.
        scope = args[0]
        mutability = args[1] if len(args) > 1 else None
        name, typ = args[2], args[3]
        value = _unwrap(args[4]) if len(args) > 4 else 0
        if scope == "module":
            prog.consts[name] = (typ, value)
            if mutability == "mutable":
                prog.mutable_globals[name] = (typ, value)
        elif prog.current_op is not None:
            prog.current_op.consts[name] = (typ, value)
            prog.current_op.lines.append((verb, args, lineno))
        else:
            prog.consts[name] = (typ, value)
        return
    if verb == "domainLiteral" and len(args) >= 3:
        # `domainLiteral NAME TYPE VALUE` is structurally a const with a
        # typed value bound at the trust boundary. Always module-scope —
        # used by operations that may be parsed later in the file.
        name, typ = args[0], args[1]
        value = _unwrap(args[2])
        prog.consts[name] = (typ, value)
        return
    if verb == "sharedState" and len(args) >= 4:
        # `sharedState <scope> <mutability> NAME TYPE [INITIAL]`. We model
        # shared state as a const for initial-value lookups; when declared
        # `mutable` it additionally becomes a real LLVM module global so
        # codegen emits load/store for `set sharedState` / read references.
        mutability = args[1]
        name, typ = args[2], args[3]
        value = _unwrap(args[4]) if len(args) > 4 else 0
        prog.consts[name] = (typ, value)
        if mutability == "mutable":
            prog.mutable_globals[name] = (typ, value)
        return
    if verb == "literal" and len(args) >= 2:
        # `literal NAME TYPE` declares a typed literal whose bytes live in
        # an external asset (see literalBytes/literalDigest/literalSource).
        # Stub it as an empty-string const so name references resolve.
        prog.consts[args[0]] = (args[1], "")
        return

    # Catch-all for any other lowercase-leading verb that looks like a
    # declarative-metadata line. This is intentionally permissive so the
    # refined-syntax surface (~100 new verbs) is accepted without each
    # needing its own handler. The line is stored under hard_metadata
    # keyed by the first arg (the declared name) for tooling indexing.
    if verb and verb[0].islower():
        if prog.current_op is not None:
            prog.current_op.lines.append((verb, args, lineno))
            return
        if args:
            prog.hard_metadata.setdefault(args[0], {}).setdefault(
                verb, []).append([_unwrap(t) for t in args[1:]])
        return

    raise SyntaxError(f"line {lineno}: unknown verb: {verb!r}")


# Verbs that carry the operation name as their first arg for §9 checkability.
HEADER_VERBS_WITH_OWNERSHIP = {
    "input", "output", "effect", "memory", "async",
    "memoryAllocationSource",
    "purpose", "invariant", "warning", "precondition",
    "guarantee", "failure", "security", "timing", "observability",
    # `pinsNullBodyFailurePath OP "rationale"` — first arg is the owning
    # operation; spec §9 ownership rule applies for checkability.
    "pinsNullBodyFailurePath",
    # `responseBodyForwarder OP bodyArgName` — first arg is the owning
    # operation that forwards its body input.
    "responseBodyForwarder",
}


# ============================================================
# Type universe
# ============================================================

I1 = ir.IntType(1)
I8 = ir.IntType(8)
I16 = ir.IntType(16)
I32 = ir.IntType(32)
I64 = ir.IntType(64)
F32 = ir.FloatType()
F64 = ir.DoubleType()
I8P = ir.IntType(8).as_pointer()
VOID = ir.VoidType()


# Implicit operation-input symbols whose value never flows into computation
# (spec §16 — the `console` dependency, the request token, the clock, etc.).
# At a user-defined operation's call site these are dropped from the LLVM
# parameter list so the call signature only carries data values.
OPAQUE_INPUTS = {
    "console", "environment", "process",
    "httpRequest", "databaseClient", "clock",
}


def resolve_alias(prog: Program, name: str) -> str:
    """Walk the type-alias chain and return the head token of the final
    type expression. For a single-token alias like `type ExitCode I32`,
    returns the underlying primitive name. For a parameterized alias like
    `type EmailAddress SmallString 254` or
    `type CreateCustomerResult Result Customer CreateCustomerError`,
    returns the HEAD (`SmallString`, `Result`) — the parameter tail is
    preserved in `prog.type_aliases[name]` for callers that need it."""
    seen = set()
    while name in prog.type_aliases and name not in seen:
        seen.add(name)
        next_target = prog.type_aliases[name]
        # Backward compat: an older revision stored single-token aliases as
        # bare strings rather than 1-element lists. Accept both shapes.
        if isinstance(next_target, list):
            if not next_target:
                break
            if len(next_target) == 1:
                name = next_target[0]
                continue
            # Parameterized alias — head is the type constructor.
            return next_target[0]
        # legacy bare-string alias
        name = next_target
    return name


def resolve_alias_full(prog: Program, name: str) -> list:
    """Return the full type-expression token list after chain resolution.
    For `type EmailAddress SmallString 254`, returns `["SmallString", "254"]`.
    For `type ExitCode I32`, returns `["I32"]`. For an unaliased primitive,
    returns `[name]`."""
    seen = set()
    while name in prog.type_aliases and name not in seen:
        seen.add(name)
        next_target = prog.type_aliases[name]
        if isinstance(next_target, list):
            if len(next_target) == 1:
                name = next_target[0]
                continue
            return list(next_target)
        name = next_target
    return [name]


def enum_repr_type(prog: Program, name: str) -> str | None:
    enum = prog.enums.get(name)
    if enum is None:
        return None
    return enum.repr or "CSignedInt32"


def enum_case_values(prog: Program) -> dict:
    values = {}
    for enum_name, enum in prog.enums.items():
        next_value = 0
        for case_name, raw_value in enum.cases:
            if raw_value is None:
                case_value = next_value
            else:
                try:
                    case_value = int(raw_value)
                except (TypeError, ValueError):
                    # Keep lowering deterministic for metadata-like enum
                    # values; a linter pass can reject non-integer repr cases
                    # when an enum is used as a runtime value.
                    case_value = next_value
            values[case_name] = (enum_name, case_value)
            next_value = case_value + 1
    return values


def llvm_type_for(prog: Program, typename: str):
    typename = resolve_alias(prog, typename)
    enum_repr = enum_repr_type(prog, typename)
    if enum_repr is not None:
        return llvm_type_for(prog, enum_repr)
    # C-stdlib alignment: every C scalar type has a spec-compliant
    # SemanticScript alias whose name carries signedness, width, ABI role, or
    # encoding contract (spec §6 names-must-carry-local-intent, §10
    # types-encode-intent). The short forms (CInt / CDouble / CSize / …)
    # are retained as backward-compatible aliases for older programs but
    # new code should prefer the spec-compliant names listed first.
    #
    # i64 — every 64-bit-wide C type
    if typename in (
        # canonical SemanticScript names
        "I64", "CSignedInt64", "CUnsignedInt64",
        "CByteCount", "CSignedByteCount", "CAddressOffset",
        "CUnixSecondsSinceEpoch", "CCpuClockTicks",
        "CFileByteOffset", "CMaxSignedInt", "CMaxUnsignedInt",
        "DurationMilliseconds", "MonotonicMilliseconds", "UtcMilliseconds",
        # legacy short forms
        "CLong", "CLongLong", "CSize", "CSsize", "CPtrdiff",
        "CTime", "CClock", "COff", "CIntmax", "CUintmax",
    ):
        return I64
    # i32 — every 32-bit-wide C type
    if typename in (
        "I32", "ExitCode",
        "CSignedInt32", "CUnsignedInt32",
        "CInt", "CUint",
    ):
        return I32
    # i16
    if typename in (
        "I16",
        "CSignedInt16", "CUnsignedInt16",
        "CShort", "CUshort",
    ):
        return I16
    # i8
    if typename in (
        "I8",
        "CSignedByte", "CUnsignedByte",
        "CChar", "CSchar", "CUchar", "CByte",
    ):
        return I8
    if typename == "Bool":
        return I1
    # IEEE float
    if typename in ("F32", "CFloat32", "CFloat"):
        return F32
    if typename in ("F64", "CFloat64", "CDouble"):
        return F64
    # i8* — every pointer-shaped C type carries an explicit role name
    if typename in (
        "String", "CNullTerminatedByteString", "CString",
        "HtmlText", "HtmlClass", "SafeUrl",
        "HtmlFragment", "HtmlTrustedFragment", "HtmlDocument",
        "HtmlTemplate",
    ):
        return I8P
    if typename in (
        "VoidPtr", "COpaqueMemoryAddress", "CFileHandle",
        "CDecomposedTimeAddress", "CSetjmpRegisterBuffer",
        "CVoidPtr", "CFile", "CFilePtr", "CTm", "CTmPtr", "CJmpBuf",
    ):
        return I8P
    if typename in ("HttpRequest", "HttpResponse", "GuiSession", "GuiEvent"):
        return I8P
    if typename in (
        "GuiApplication", "GuiWindow", "GuiControl", "GuiButton",
        "GuiTextBox", "GuiListBox", "GuiCheckBox", "GuiMenuItem",
        "GuiStatusBar", "GuiTextLabel",
    ):
        return I8P
    # Opaque handles for the native sqlite runtime — the C ABI in
    # `sem_sqlite_runtime.h` exposes both as `void *` typedefs and never
    # lets generated code dereference them, so lowering as `i8*` is the
    # correct shape (parallel to HttpRequest / HttpResponse above).
    if typename in ("SqliteDatabase", "SqliteStatement"):
        return I8P
    # Opaque handle for the native JSON builder runtime
    # (sem_json_runtime.h). The AS source allocates one of these via
    # json.createBuilder, threads it through field writers, and frees
    # via `defer json.destroyBuilder`. Generated code never
    # dereferences the handle directly — same opaque-pointer contract
    # as HttpRequest / SqliteDatabase.
    if typename == "JsonBuilder":
        return I8P
    return None


def llvm_type_for_or_void(prog: Program, typename: str):
    """Like llvm_type_for but also accepts 'Void' / 'CVoid' as the void type."""
    if typename in ("Void", "CVoid"):
        return VOID
    return llvm_type_for(prog, typename)


@dataclass
class OutputContract:
    line: int
    tokens: list
    ok_type: str = ""
    llvm_type: object = None
    problem: str = ""
    message: str = ""


def _operation_output_contract(prog: Program, op: Operation) -> OutputContract:
    """Return the lowerable success type declared by an operation output line."""
    for verb, args, lineno in op.lines:
        if verb != "output" or not args or args[0] != op.name:
            continue
        tokens = args[1:]
        if not tokens:
            return OutputContract(
                lineno, tokens, problem="malformedOutputContract",
                message=(
                    f"malformedOutputContract: operation `{op.name}` has an "
                    "empty output contract; expected `output OP TYPE` or "
                    "`output OP Result OK ERROR`"))
        if tokens[0] == "Result":
            if len(tokens) < 3:
                return OutputContract(
                    lineno, tokens, problem="malformedOutputContract",
                    message=(
                        f"malformedOutputContract: operation `{op.name}` "
                        "declares `Result` output without both OK and ERROR "
                        "types"))
            ok_type = tokens[1]
        else:
            ok_type = tokens[0]

        resolved_ok = resolve_alias(prog, ok_type)
        if resolved_ok in ("Void", "CVoid"):
            return OutputContract(lineno, tokens, ok_type=ok_type, llvm_type=I32)
        llty = llvm_type_for(prog, ok_type)
        if llty is None:
            return OutputContract(
                lineno, tokens, ok_type=ok_type, problem="unknownOutputType",
                message=(
                    f"unknownOutputType: operation `{op.name}` declares output "
                    f"type `{ok_type}`, but semsc cannot lower it to a known "
                    "SemanticScript/LLVM type"))
        return OutputContract(lineno, tokens, ok_type=ok_type, llvm_type=llty)

    line = op.decl_line or (op.lines[0][2] if op.lines else 0)
    return OutputContract(
        line, [], problem="missingOutputContract",
        message=(
            f"missingOutputContract: operation `{op.name}` has no output "
            f"contract; add `output {op.name} TYPE` or "
            f"`output {op.name} Result OK ERROR`"))


# ============================================================
# Call targets
# ============================================================

# normalize math/console targets to a canonical name
_TARGET_ALIASES = {
    "math.subI64":  "math.subtractI64",
    "math.mulI64":  "math.multiplyI64",
    "math.divI64":  "math.divideI64",
    "math.modI64":  "math.moduloI64",
    "math.eqI64":   "math.equalI64",
    "math.neI64":   "math.notEqualI64",
    "math.ltI64":   "math.lessThanI64",
    "math.leI64":   "math.lessThanOrEqualI64",
    "math.gtI64":   "math.greaterThanI64",
    "math.geI64":   "math.greaterThanOrEqualI64",
    "console.writeInteger": "console.writeIntegerLine",
    # Refined-syntax / STDLIB_RENAME long forms map back to the V0
    # short forms so the existing call-target dispatch fires correctly.
    "math.convertSignedInt64ToFloat64": "math.intToFloat",
    "math.convertFloat64ToSignedInt64": "math.floatToInt",
    "math.convertSignedInt32ToSignedInt64": "math.signExtendCSignedInt32ToCSignedInt64",
    "math.convertSignedInt64ToSignedInt32": "math.truncateCSignedInt64ToCSignedInt32",
}

_BINOP_TO_LLVM = {
    "math.addI64":      "add",
    "math.subtractI64": "sub",
    "math.multiplyI64": "mul",
    "math.divideI64":   "sdiv",
    "math.moduloI64":   "srem",
}

# Floating-point binary ops keep their operands at their declared width (F64 by
# default). The dispatcher distinguishes these from the integer set so it does
# not coerce double values down to i64.
_FBINOP_TO_LLVM = {
    "math.addF64":      "fadd",
    "math.subtractF64": "fsub",
    "math.multiplyF64": "fmul",
    "math.divideF64":   "fdiv",
}

_FCMP_TO_LLVM = {
    "math.equalF64":              "==",
    "math.notEqualF64":           "!=",
    "math.lessThanF64":           "<",
    "math.lessThanOrEqualF64":    "<=",
    "math.greaterThanF64":        ">",
    "math.greaterThanOrEqualF64": ">=",
}

# C macro-only math classifiers — `c.isnan(x)`, etc. — are defined as macros in
# <math.h> rather than externs. They lower to native LLVM FP comparisons so
# the SemanticScript surface matches the spec without link-time surprises across libc
# implementations.
_MATH_CLASSIFIERS = {
    "c.isnan", "c.isinf", "c.isfinite", "c.isnormal",
    "c.signbit", "c.fpclassify",
}

_CMP_TO_LLVM = {
    "math.equalI64":              "==",
    "math.notEqualI64":           "!=",
    "math.lessThanI64":           "<",
    "math.lessThanOrEqualI64":    "<=",
    "math.greaterThanI64":        ">",
    "math.greaterThanOrEqualI64": ">=",
}

_CMP_I32_TO_LLVM = {
    "math.equalCSignedInt32":              "==",
    "math.notEqualCSignedInt32":           "!=",
    "math.lessThanCSignedInt32":           "<",
    "math.lessThanOrEqualCSignedInt32":    "<=",
    "math.greaterThanCSignedInt32":        ">",
    "math.greaterThanOrEqualCSignedInt32": ">=",
}


# Domain-typed methods. A call target of the form `TypeName.methodName`
# (where TypeName is a user-declared type alias) lowers to the primitive
# below based on the alias's underlying type. This preserves domain context
# in source (`CountdownValue.subtractPositiveStep` rather than
# `math.subtractI64`) while reusing the existing primitive dispatch.
_DOMAIN_METHOD_TO_F64_PRIMITIVE = {
    "add":              "math.addF64",
    "subtract":         "math.subtractF64",
    "multiply":         "math.multiplyF64",
    "divide":           "math.divideF64",
    "equal":            "math.equalF64",
    "notEqual":         "math.notEqualF64",
    "lessThan":         "math.lessThanF64",
    "lessThanOrEqual":  "math.lessThanOrEqualF64",
    "greaterThan":      "math.greaterThanF64",
    "greaterThanOrEqual": "math.greaterThanOrEqualF64",
}


_DOMAIN_METHOD_TO_I64_PRIMITIVE = {
    # infallible (use plain `bind`)
    "add":                  "math.addI64",
    "addPositiveStep":      "math.addI64",
    "subtract":             "math.subtractI64",
    "subtractStep":         "math.subtractI64",
    "subtractPositiveStep": "math.subtractI64",
    "multiply":             "math.multiplyI64",
    "multiplyByStep":       "math.multiplyI64",
    "multiplyByCounter":    "math.multiplyI64",
    "divide":               "math.divideI64",
    "modulo":               "math.moduloI64",
    "moduloBy":             "math.moduloI64",
    "equal":                "math.equalI64",
    "notEqual":             "math.notEqualI64",
    "lessThan":             "math.lessThanI64",
    "lessThanOrEqual":      "math.lessThanOrEqualI64",
    "greaterThan":          "math.greaterThanI64",
    "greaterThanOrEqual":   "math.greaterThanOrEqualI64",
    "square":               "math.multiplyI64",
    # fallible (use bindOk + bindError + branchIfError)
    "checkedMultiply":           "math.checkedMultiplyI64",
    "checkedMultiplyByCounter":  "math.checkedMultiplyI64",
    "checkedMultiplyByStep":     "math.checkedMultiplyI64",
}


# Domain methods for CSignedInt32-repr types and enums. Mirrors the I64
# table; used when `TypeName.methodName` resolves to a CSignedInt32-shaped
# alias or to an enum with `repr CSignedInt32`. Supports equality and
# ordered comparison on int32-shaped enum cases like SaveTodosStatus.
_DOMAIN_METHOD_TO_I32_PRIMITIVE = {
    "equal":                "math.equalCSignedInt32",
    "notEqual":             "math.notEqualCSignedInt32",
    "lessThan":             "math.lessThanCSignedInt32",
    "lessThanOrEqual":      "math.lessThanOrEqualCSignedInt32",
    "greaterThan":          "math.greaterThanCSignedInt32",
    "greaterThanOrEqual":   "math.greaterThanOrEqualCSignedInt32",
}


# ============================================================
# Codegen
# ============================================================

class Codegen:
    def __init__(self, prog: Program, runtime_checks: str = "off"):
        self.prog = prog
        self.runtime_checks = runtime_checks
        self.module = ir.Module(name=prog.project_name or "semanticscript_module")
        self.module.triple = llvm.get_default_triple()
        self.provenance = CompilerProvenance(prog)
        self.strings = {}
        self._next_str_id = 0
        self._next_html_buffer_id = 0
        self._web_route_handler_names = set()
        self._declare_externals()

    def _declare_externals(self):
        # `puts` and `printf` are declared lazily, on first reference (see
        # `_get_puts` / `_get_printf`). The lazy declaration lets an
        # SemanticScript program define its OWN user-operation called `puts`
        # (e.g. an SemanticScript-native stdio.sscript that bottoms out through c.putchar)
        # without colliding with the compiler's libc glue. The first call
        # that actually needs the libc symbol gets it declared then.
        self._puts = None
        self._printf = None
        self._llvm_trap = None
        self._win_get_std_handle = None
        self._win_write_file = None
        self._posix_write = None
        # LLVM signed-multiply-with-overflow intrinsic. Produces a literal
        # struct { i64 product, i1 overflowOccurred }. Used to lower checked
        # multiplication call targets so callers can branchIfError on the
        # overflow bit instead of silently wrapping.
        overflow_struct_ty = ir.LiteralStructType([I64, I1])
        smul_overflow_ty = ir.FunctionType(overflow_struct_ty, [I64, I64])
        self.smul_overflow_i64 = ir.Function(
            self.module, smul_overflow_ty, name="llvm.smul.with.overflow.i64")
        # On-demand cache for c.* libc declarations. Populated lazily so a
        # program that calls only c.printf doesn't drag every libc external
        # into its IR.
        self._libc_funcs = {}
        self._http_runtime_funcs = {}
        # Cache for stdio stream globals (stdin / stdout / stderr).
        self._libc_streams = {}
        # Mutable module-scope globals: emitted at compile() entry, looked
        # up by name from resolve()/set inside every operation body.
        self._mutable_globals = {}

    @property
    def puts(self):
        """Lazily declare the libc puts extern. Skipped if the program
        already defines a user-operation named `puts` (in that case
        console.writeLine etc. will pick up the SemanticScript-native one through the
        user-op dispatch path, not through self.puts)."""
        if self._puts is None:
            self._puts = ir.Function(self.module, ir.FunctionType(I32, [I8P]),
                                     name="puts")
        return self._puts

    @property
    def printf(self):
        if self._printf is None:
            self._printf = ir.Function(self.module,
                                       ir.FunctionType(I32, [I8P], var_arg=True),
                                       name="printf")
        return self._printf

    @property
    def llvm_trap(self):
        if self._llvm_trap is None:
            for fn in self.module.functions:
                if fn.name == "llvm.trap":
                    self._llvm_trap = fn
                    break
            if self._llvm_trap is None:
                self._llvm_trap = ir.Function(
                    self.module, ir.FunctionType(ir.VoidType(), []),
                    name="llvm.trap")
        return self._llvm_trap

    @property
    def win_get_std_handle(self):
        if self._win_get_std_handle is None:
            self._win_get_std_handle = ir.Function(
                self.module, ir.FunctionType(I8P, [I32]),
                name="GetStdHandle")
        return self._win_get_std_handle

    @property
    def win_write_file(self):
        if self._win_write_file is None:
            self._win_write_file = ir.Function(
                self.module,
                ir.FunctionType(I32, [I8P, I8P, I32, I32.as_pointer(), I8P]),
                name="WriteFile")
        return self._win_write_file

    @property
    def posix_write(self):
        if self._posix_write is None:
            self._posix_write = ir.Function(
                self.module, ir.FunctionType(I64, [I32, I8P, I64]),
                name="write")
        return self._posix_write

    def _safe_block_name(self, raw: str) -> str:
        cleaned = re.sub(r"[^A-Za-z0-9_.]+", "_", raw or "runtime_check")
        return cleaned[:80] or "runtime_check"

    def _runtime_panic_lines(self, call, reason: str):
        path = self.prog.source_path or "<source>"
        line = call.get("line", 0)
        raw = self.prog.source_lines.get(line, "").strip()
        call_bits = ""
        if call.get("name") and call.get("target"):
            call_bits = f"{call['name']} -> {call['target']}"
        elif call.get("name") or call.get("target"):
            call_bits = call.get("name") or call.get("target")
        lines = [
            "error SSRUN001: SemanticScript runtime panic",
            "--------------------------------------------",
            "status: trapped before undefined behavior",
            f"reason: {reason}",
            "",
            "Location:",
            f"  file: {path}",
            f"  line: {line}",
        ]
        if call.get("operation"):
            lines.append(f"  operation: {call['operation']}")
        if call_bits:
            lines.append(f"  call: {call_bits}")
        if raw:
            lines.extend([
                "",
                "Source:",
                f"  {line} | {raw}",
            ])
        lines.extend([
            "",
            "Direction:",
            "  Inspect the source row above.",
        ])
        return lines

    def _emit_runtime_panic_write(self, builder, text: str):
        text_with_newline = text + "\n"
        ptr = self._i8p(builder, text_with_newline)
        byte_count = len(text_with_newline.encode("utf-8"))
        triple = (self.module.triple or "").lower()
        if "windows" in triple or "win32" in triple or "msvc" in triple:
            # STD_ERROR_HANDLE is (DWORD)-12. Use kernel32 directly instead
            # of C stdio so panic diagnostics stay close to the emitted IR.
            handle = builder.call(
                self.win_get_std_handle, [ir.Constant(I32, -12)],
                name="panicStderr")
            bytes_written = builder.alloca(I32, name="panicBytesWritten")
            builder.call(self.win_write_file, [
                handle,
                ptr,
                ir.Constant(I32, byte_count),
                bytes_written,
                ir.Constant(I8P, None),
            ])
            return
        builder.call(self.posix_write, [
            ir.Constant(I32, 2),
            ptr,
            ir.Constant(I64, byte_count),
        ])

    def _emit_runtime_failure(self, builder, call, reason: str):
        if self.runtime_checks == "panic":
            self._emit_runtime_panic_write(
                builder, "\n".join(self._runtime_panic_lines(call, reason)))
        builder.call(self.llvm_trap, [])
        builder.unreachable()

    def _emit_runtime_check(self, builder, failed_cond, call, reason: str):
        if self.runtime_checks == "off":
            return
        if builder.block.is_terminated:
            return
        safe_name = self._safe_block_name(call.get("name") or reason)
        panic_bb = builder.function.append_basic_block(f"panic_{safe_name}")
        ok_bb = builder.function.append_basic_block(f"after_panic_check_{safe_name}")
        builder.cbranch(failed_cond, panic_bb, ok_bb)
        builder.position_at_end(panic_bb)
        self._emit_runtime_failure(builder, call, reason)
        builder.position_at_end(ok_bb)

    def _emit_null_pointer_check(self, builder, pointer_value, call, reason: str):
        if self.runtime_checks == "off":
            return
        if not isinstance(pointer_value.type, ir.PointerType):
            return
        failed = builder.icmp_unsigned(
            "==", pointer_value, ir.Constant(pointer_value.type, None),
            name=f"{self._safe_block_name(call.get('name'))}_isNull")
        self._emit_runtime_check(builder, failed, call, reason)

    # Attribute groups applied to libc declarations so the LLVM optimizer can
    # treat them as nearly-pure functions. Without these the JIT cannot hoist
    # repeated math calls across a loop or vectorize them, which leaves
    # SemanticScript several times slower than clang -O2 on math-heavy code.
    # Function attributes recognized by llvmlite's IR builder. Matches the
    # effective semantics of clang's `-fno-math-errno` (math functions can
    # be treated as truly pure for optimization purposes).
    _LIBC_MATH_PURE = ("nounwind", "readnone")
    _LIBC_MEMORY_PURE = ("nounwind", "readonly")
    _LIBC_NOUNWIND = ("nounwind",)

    def _attrs_for(self, name: str):
        # math.h functions: pure modulo errno writes; mark willreturn+nofree
        # so loop-invariant code motion can hoist them.
        if name in libc_registry.MATH:
            return self._LIBC_MATH_PURE
        # ctype functions are pure (table lookups, no I/O).
        if name in libc_registry.CTYPE or name in libc_registry.WCTYPE:
            return self._LIBC_MEMORY_PURE
        # string-read functions (strlen, strcmp, memcmp, …) only read memory.
        if name in {"strlen", "strnlen_s", "strcmp", "strncmp", "strchr",
                    "strrchr", "strspn", "strcspn", "strpbrk", "strstr",
                    "memcmp", "memchr"}:
            return self._LIBC_MEMORY_PURE
        # Everything else is nounwind by C convention but may have side effects.
        return self._LIBC_NOUNWIND

    def _libc_func(self, semantic_name: str):
        """Return an LLVM Function for libc <semantic_name>, declaring it on
        demand. The SemanticScript-facing name may be the C symbol itself (printf,
        strlen, malloc) or a camelCase alias (alignedAlloc, threadCreate,
        mutexLock, …) that maps to an underscored C symbol. The dispatcher
        consults `libc_registry.resolve_c_symbol` to translate.

        If the module already has a function by the resolved C symbol
        (e.g. `printf` is pre-declared by _declare_externals for the
        writeIntegerLine path), reuse the existing declaration."""
        if semantic_name in self._libc_funcs:
            return self._libc_funcs[semantic_name]
        # Translate SemanticScript-facing camelCase to the underscored C symbol per
        # spec §5 (only `.`/`"`/`#`/`/` are SemanticScript punctuation; foreign symbol
        # names that contain `_` are exposed through aliases).
        c_symbol = libc_registry.resolve_c_symbol(semantic_name)
        # Reuse any existing LLVM extern with the target C symbol name.
        for existing in self.module.functions:
            if existing.name == c_symbol:
                self._libc_funcs[semantic_name] = existing
                return existing
        # Signature lookup: try SemanticScript-facing name first, then the C symbol.
        sig = libc_registry.ALL_FUNCTIONS.get(semantic_name)
        if sig is None:
            sig = libc_registry.ALL_FUNCTIONS.get(c_symbol)
        if sig is None:
            raise ValueError(f"unknown c.* function: c.{semantic_name}")
        ret_typ, param_typs, var_args = sig
        llvm_ret = llvm_type_for_or_void(self.prog, ret_typ)
        if llvm_ret is None:
            raise ValueError(f"unsupported return type `{ret_typ}` for c.{semantic_name}")
        llvm_params = []
        for ptyp in param_typs:
            ll = llvm_type_for(self.prog, ptyp)
            if ll is None:
                raise ValueError(f"unsupported param type `{ptyp}` for c.{semantic_name}")
            llvm_params.append(ll)
        fnty = ir.FunctionType(llvm_ret, llvm_params, var_arg=var_args)
        # Use the C symbol as the LLVM extern name so the linker resolves
        # to the actual libc function (not the SemanticScript-facing camelCase form).
        fn = ir.Function(self.module, fnty, name=c_symbol)
        for attr in self._attrs_for(c_symbol):
            fn.attributes.add(attr)
        self._libc_funcs[semantic_name] = fn
        return fn

    def _runtime_func(self, name: str, ret_ty, param_tys):
        if name in self._http_runtime_funcs:
            return self._http_runtime_funcs[name]
        for existing in self.module.functions:
            if existing.name == name:
                self._http_runtime_funcs[name] = existing
                return existing
        fn = ir.Function(self.module, ir.FunctionType(ret_ty, param_tys), name=name)
        self._http_runtime_funcs[name] = fn
        return fn

    def _coerce_for_libc(self, builder, value, target_typ_name: str):
        """Coerce an SSA value to match a libc parameter's declared type."""
        target_ll = llvm_type_for(self.prog, target_typ_name)
        if target_ll is None:
            return value
        if value.type == target_ll:
            return value
        # int -> wider/narrower int
        if isinstance(value.type, ir.IntType) and isinstance(target_ll, ir.IntType):
            if value.type.width < target_ll.width:
                return builder.sext(value, target_ll)
            if value.type.width > target_ll.width:
                return builder.trunc(value, target_ll)
        # int -> pointer (treat as conversion via inttoptr for null-style args)
        if isinstance(value.type, ir.IntType) and isinstance(target_ll, ir.PointerType):
            return builder.inttoptr(value, target_ll)
        # pointer -> pointer (bitcast)
        if isinstance(value.type, ir.PointerType) and isinstance(target_ll, ir.PointerType):
            return builder.bitcast(value, target_ll)
        # int -> float
        if isinstance(value.type, ir.IntType) and isinstance(target_ll, (ir.FloatType, ir.DoubleType)):
            return builder.sitofp(value, target_ll)
        # float -> int
        if isinstance(value.type, (ir.FloatType, ir.DoubleType)) and isinstance(target_ll, ir.IntType):
            return builder.fptosi(value, target_ll)
        # float -> float (width change)
        if isinstance(value.type, ir.FloatType) and isinstance(target_ll, ir.DoubleType):
            return builder.fpext(value, target_ll)
        if isinstance(value.type, ir.DoubleType) and isinstance(target_ll, ir.FloatType):
            return builder.fptrunc(value, target_ll)
        return value

    def _emit_math_classifier(self, builder, classifier: str, x, name: str):
        """Lower a <math.h> classifier macro to LLVM operations.

        These C macros are spec-required to behave as if they had been
        implemented with native FP introspection — the libc has no extern
        for them on most platforms, so the only portable lowering is to
        emit the equivalent LLVM ops.
        """
        if classifier == "isnan":
            # Unordered compare with self: NaN is the only value that
            # compares unordered against itself.
            result_bool = builder.fcmp_unordered("uno", x, x, name=name + "_uno")
            return builder.zext(result_bool, I32)
        if classifier == "isinf":
            # |x| == inf
            inf = ir.Constant(F64, float("inf"))
            abs_x = builder.call(self._llvm_fabs_f64(), [x], name=name + "_abs")
            eq = builder.fcmp_ordered("==", abs_x, inf, name=name + "_eq")
            return builder.zext(eq, I32)
        if classifier == "isfinite":
            # |x| < inf  (also rules out NaN because NaN < anything is false)
            inf = ir.Constant(F64, float("inf"))
            abs_x = builder.call(self._llvm_fabs_f64(), [x], name=name + "_abs")
            lt = builder.fcmp_ordered("<", abs_x, inf, name=name + "_lt")
            return builder.zext(lt, I32)
        if classifier == "isnormal":
            # |x| is finite AND |x| >= DBL_MIN (normal positive). This is the
            # spec definition: normal floats are non-zero, finite, and not
            # subnormal. DBL_MIN = 2^-1022.
            dbl_min = ir.Constant(F64, 2.2250738585072014e-308)
            inf = ir.Constant(F64, float("inf"))
            abs_x = builder.call(self._llvm_fabs_f64(), [x], name=name + "_abs")
            lt_inf = builder.fcmp_ordered("<", abs_x, inf, name=name + "_lt_inf")
            ge_min = builder.fcmp_ordered(">=", abs_x, dbl_min, name=name + "_ge_min")
            both = builder.and_(lt_inf, ge_min, name=name + "_both")
            return builder.zext(both, I32)
        if classifier == "signbit":
            # Read the sign bit by reinterpreting the double as i64.
            i64_bits = builder.bitcast(x, I64, name=name + "_bits")
            shifted = builder.lshr(i64_bits, ir.Constant(I64, 63),
                                    name=name + "_shift")
            return builder.trunc(shifted, I32)
        if classifier == "fpclassify":
            # Returns FP_INFINITE, FP_NAN, FP_NORMAL, FP_SUBNORMAL, FP_ZERO.
            # Implementation-defined integer values; we use the MSVC values
            # (1, 2, -1, -2, 0). The result is computed by chained selects.
            FP_NAN, FP_INFINITE, FP_ZERO, FP_SUBNORMAL, FP_NORMAL = 2, 1, 0, -2, -1
            inf = ir.Constant(F64, float("inf"))
            zero = ir.Constant(F64, 0.0)
            dbl_min = ir.Constant(F64, 2.2250738585072014e-308)
            abs_x = builder.call(self._llvm_fabs_f64(), [x], name=name + "_abs")
            is_nan = builder.fcmp_unordered("uno", x, x, name=name + "_uno")
            is_inf = builder.fcmp_ordered("==", abs_x, inf, name=name + "_inf")
            is_zero = builder.fcmp_ordered("==", x, zero, name=name + "_zero")
            is_subnormal = builder.fcmp_ordered("<", abs_x, dbl_min,
                                                 name=name + "_sub")
            result_normal = ir.Constant(I32, FP_NORMAL)
            result_subnorm = builder.select(is_subnormal,
                ir.Constant(I32, FP_SUBNORMAL), result_normal,
                name=name + "_sel_sub")
            result_zero = builder.select(is_zero, ir.Constant(I32, FP_ZERO),
                result_subnorm, name=name + "_sel_zero")
            result_inf = builder.select(is_inf, ir.Constant(I32, FP_INFINITE),
                result_zero, name=name + "_sel_inf")
            return builder.select(is_nan, ir.Constant(I32, FP_NAN),
                result_inf, name=name + "_sel_nan")
        raise ValueError(f"unknown math classifier: {classifier}")

    def _llvm_fabs_f64(self):
        """Get-or-declare the LLVM `llvm.fabs.f64` intrinsic."""
        for fn in self.module.functions:
            if fn.name == "llvm.fabs.f64":
                return fn
        fnty = ir.FunctionType(F64, [F64])
        return ir.Function(self.module, fnty, name="llvm.fabs.f64")

    def _promote_for_vararg(self, builder, value):
        """C variadic ABI: integer args < int are promoted to int; float is
        promoted to double. Apply the same promotion here so call-site types
        match what printf/scanf expect."""
        if isinstance(value.type, ir.IntType) and value.type.width < 32:
            return builder.sext(value, I32)
        if isinstance(value.type, ir.FloatType):
            return builder.fpext(value, F64)
        return value

    def _libc_stream(self, name: str):
        """Return the i8* SSA value of a libc stdio stream global."""
        if name in self._libc_streams:
            return self._libc_streams[name]
        # On MSVC the streams are accessed via __acrt_iob_func(stream_id);
        # the simplest portable mapping is to declare the symbol as a
        # `FILE*` global and let the linker resolve it. llvmlite emits
        # external globals when no initializer is set.
        gv = ir.GlobalVariable(self.module, I8P, name=f"as_{name}")
        gv.linkage = "external"
        self._libc_streams[name] = gv
        return gv

    # ---------- string interning ----------
    def _make_str_global(self, text: str) -> ir.GlobalVariable:
        if text in self.strings:
            return self.strings[text]
        data = bytearray(text.encode("utf-8")) + b"\0"
        arr_ty = ir.ArrayType(ir.IntType(8), len(data))
        gv = ir.GlobalVariable(self.module, arr_ty, name=f".str.{self._next_str_id}")
        self._next_str_id += 1
        gv.linkage = "internal"
        gv.global_constant = True
        gv.initializer = ir.Constant(arr_ty, data)
        self.strings[text] = gv
        return gv

    def _i8p(self, builder: ir.IRBuilder, text: str):
        gv = self._make_str_global(text)
        zero = ir.Constant(I32, 0)
        return builder.gep(gv, [zero, zero], inbounds=True)

    def _html_mask_raw_text_elements(self, body: str) -> str:
        chars = list(body)
        for match in _HTML_RAW_TEXT_RE.finditer(body):
            for index in range(match.start(), match.end()):
                chars[index] = " "
        return "".join(chars)

    def _validate_html_dynamic_holes(self, template: HtmlTemplate, body: str):
        masked = self._html_mask_raw_text_elements(body)
        html_arg_spans = {
            (match.start(), match.end())
            for match in _HTML_ARG_REFERENCE_RE.finditer(masked)
        }
        for match in _HTML_BRACE_CONTENT_RE.finditer(masked):
            if (match.start(), match.end()) in html_arg_spans:
                continue
            content = match.group(1).strip()
            if not content:
                continue
            raise ValueError(
                f"htmlBody {template.name}: dynamic hole `{{{content}}}` "
                "must reference declared htmlArg.NAME")

    def _html_hole_context(self, body: str, hole_start: int):
        last_lt = body.rfind("<", 0, hole_start)
        last_gt = body.rfind(">", 0, hole_start)
        if last_lt <= last_gt:
            return "text", None
        tag_prefix = body[last_lt + 1:hole_start]
        attr_match = _HTML_ATTR_VALUE_PREFIX_RE.search(tag_prefix)
        if attr_match:
            return "attribute", attr_match.group(1).lower()
        return "tag", None

    def _validate_html_arg_context(self, template: HtmlTemplate, arg_name: str,
                                   type_name: str, context_kind: str,
                                   attr_name):
        resolved = (
            type_name if type_name in _HTML_TRUST_TYPES
            else resolve_alias(self.prog, type_name)
        )
        if context_kind == "tag":
            raise ValueError(
                f"htmlBody {template.name}: htmlArg `{arg_name}` cannot "
                "hydrate HTML tag syntax; dynamic holes must be text content "
                "or quoted attribute values")
        if context_kind == "text":
            if resolved in ("HtmlClass", "SafeUrl"):
                raise ValueError(
                    f"htmlBody {template.name}: htmlArg `{arg_name}` has "
                    f"type `{type_name}` and cannot hydrate text content")
            return
        if context_kind != "attribute":
            return
        if resolved in ("HtmlFragment", "HtmlTrustedFragment", "HtmlDocument"):
            raise ValueError(
                f"htmlBody {template.name}: htmlArg `{arg_name}` has "
                f"type `{type_name}` and cannot hydrate attribute `{attr_name}`")
        if attr_name == "class" and resolved != "HtmlClass":
            raise ValueError(
                f"htmlBody {template.name}: class attribute htmlArg "
                f"`{arg_name}` requires HtmlClass, got `{type_name}`")
        if attr_name in _HTML_URL_ATTRS and resolved != "SafeUrl":
            raise ValueError(
                f"htmlBody {template.name}: `{attr_name}` attribute htmlArg "
                f"`{arg_name}` requires SafeUrl, got `{type_name}`")

    def _html_arg_escape_mode(self, type_name: str, context_kind: str):
        resolved = (
            type_name if type_name in _HTML_TRUST_TYPES
            else resolve_alias(self.prog, type_name)
        )
        if context_kind == "text" and resolved in (
            "HtmlFragment", "HtmlTrustedFragment", "HtmlDocument",
        ):
            return "raw"
        if context_kind == "attribute":
            return "attribute"
        if resolved in ("HtmlText", "String", "CNullTerminatedByteString", "CString"):
            return "text"
        return "raw"

    def _html_template_parts_and_args(self, template: HtmlTemplate):
        if not template.body_lines:
            raise ValueError(
                f"htmlBody {template.name}: template has no body lines")
        arg_types = {name: typ for name, typ, _line in template.args}
        parts = []
        body = "\n".join(line for line, _lineno in template.body_lines)
        if template.body_lines:
            body += "\n"
        masked_body = self._html_mask_raw_text_elements(body)
        self._validate_html_dynamic_holes(template, body)
        cursor = 0
        for match in _HTML_ARG_REFERENCE_RE.finditer(masked_body):
            static_text = body[cursor:match.start()]
            if static_text:
                parts.append(("static", static_text, None, None))
            arg_name = match.group(1)
            if arg_name not in arg_types:
                raise ValueError(
                    f"htmlBody {template.name}: unknown htmlArg `{arg_name}`")
            context_kind, attr_name = self._html_hole_context(body, match.start())
            self._validate_html_arg_context(
                template, arg_name, arg_types[arg_name], context_kind, attr_name)
            parts.append(("arg", arg_name, context_kind, attr_name))
            cursor = match.end()
        tail_text = body[cursor:]
        if tail_text:
            parts.append(("static", tail_text, None, None))
        return parts, arg_types

    def _html_arg_as_cstring(self, builder, value, arg_name: str, type_name: str):
        resolved = resolve_alias(self.prog, type_name)
        if resolved not in (
            "HtmlText", "HtmlClass", "SafeUrl",
            "HtmlFragment", "HtmlTrustedFragment", "HtmlDocument",
            "String", "CNullTerminatedByteString", "CString",
        ):
            raise ValueError(
                f"htmlArg `{arg_name}` has type `{type_name}`; "
                "html.hydrate requires a string-shaped HTML value type")
        if isinstance(value.type, ir.IntType):
            return builder.inttoptr(value, I8P)
        if isinstance(value.type, ir.PointerType) and value.type != I8P:
            return builder.bitcast(value, I8P)
        return value

    def _emit_html_append_static(self, builder, write_ptr, limit_ptr,
                                 text: str, name_hint: str):
        if not text:
            return write_ptr
        return self._emit_html_append_cstring(
            builder, write_ptr, self._i8p(builder, text), limit_ptr, name_hint)

    def _emit_html_append_cstring(self, builder, write_ptr, source_ptr,
                                  limit_ptr, name_hint: str):
        fn = builder.function
        entry_block = builder.block
        loop_block = fn.append_basic_block(f"{name_hint}_copy")
        byte_block = fn.append_basic_block(f"{name_hint}_byte")
        done_block = fn.append_basic_block(f"{name_hint}_done")
        one = ir.Constant(I64, 1)
        zero_byte = ir.Constant(I8, 0)

        builder.branch(loop_block)
        builder.position_at_end(loop_block)
        src_phi = builder.phi(I8P, name=f"{name_hint}_src")
        dst_phi = builder.phi(I8P, name=f"{name_hint}_dst")
        src_phi.add_incoming(source_ptr, entry_block)
        dst_phi.add_incoming(write_ptr, entry_block)
        ch = builder.load(src_phi, name=f"{name_hint}_ch")
        done = builder.icmp_unsigned("==", ch, zero_byte, name=f"{name_hint}_is_end")
        dst_offset = builder.ptrtoint(dst_phi, I64, name=f"{name_hint}_dst_addr")
        limit_offset = builder.ptrtoint(limit_ptr, I64, name=f"{name_hint}_limit_addr")
        at_limit = builder.icmp_unsigned(
            ">=", dst_offset, limit_offset, name=f"{name_hint}_at_limit")
        should_stop = builder.or_(done, at_limit, name=f"{name_hint}_stop")
        builder.cbranch(should_stop, done_block, byte_block)

        builder.position_at_end(byte_block)
        builder.store(ch, dst_phi)
        next_src = builder.gep(src_phi, [one], name=f"{name_hint}_next_src")
        next_dst = builder.gep(dst_phi, [one], name=f"{name_hint}_next_dst")
        builder.branch(loop_block)
        src_phi.add_incoming(next_src, byte_block)
        dst_phi.add_incoming(next_dst, byte_block)

        builder.position_at_end(done_block)
        return dst_phi

    def _emit_html_append_escaped_cstring(self, builder, write_ptr, source_ptr,
                                          limit_ptr, name_hint: str,
                                          escape_quotes: bool):
        fn = builder.function
        entry_block = builder.block
        loop_block = fn.append_basic_block(f"{name_hint}_escape_copy")
        done_block = fn.append_basic_block(f"{name_hint}_escape_done")
        normal_block = fn.append_basic_block(f"{name_hint}_escape_byte")
        checks = [
            (ord("&"), "amp", "&amp;"),
            (ord("<"), "lt", "&lt;"),
            (ord(">"), "gt", "&gt;"),
        ]
        if escape_quotes:
            checks.append((ord('"'), "quot", "&quot;"))
        check_blocks = [
            fn.append_basic_block(f"{name_hint}_escape_check_{suffix}")
            for _byte, suffix, _entity in checks
        ]
        entity_blocks = [
            fn.append_basic_block(f"{name_hint}_escape_{suffix}")
            for _byte, suffix, _entity in checks
        ]
        one = ir.Constant(I64, 1)
        zero_byte = ir.Constant(I8, 0)

        builder.branch(loop_block)
        builder.position_at_end(loop_block)
        src_phi = builder.phi(I8P, name=f"{name_hint}_escape_src")
        dst_phi = builder.phi(I8P, name=f"{name_hint}_escape_dst")
        src_phi.add_incoming(source_ptr, entry_block)
        dst_phi.add_incoming(write_ptr, entry_block)
        ch = builder.load(src_phi, name=f"{name_hint}_escape_ch")
        done = builder.icmp_unsigned("==", ch, zero_byte,
                                     name=f"{name_hint}_escape_is_end")
        dst_offset = builder.ptrtoint(dst_phi, I64,
                                      name=f"{name_hint}_escape_dst_addr")
        limit_offset = builder.ptrtoint(limit_ptr, I64,
                                        name=f"{name_hint}_escape_limit_addr")
        at_limit = builder.icmp_unsigned(
            ">=", dst_offset, limit_offset, name=f"{name_hint}_escape_at_limit")
        should_stop = builder.or_(done, at_limit, name=f"{name_hint}_escape_stop")
        builder.cbranch(should_stop, done_block, check_blocks[0])

        for index, (byte_value, suffix, entity_text) in enumerate(checks):
            builder.position_at_end(check_blocks[index])
            is_match = builder.icmp_unsigned(
                "==", ch, ir.Constant(I8, byte_value),
                name=f"{name_hint}_escape_is_{suffix}")
            next_block = entity_blocks[index]
            fallback_block = (
                check_blocks[index + 1]
                if index + 1 < len(check_blocks)
                else normal_block
            )
            builder.cbranch(is_match, next_block, fallback_block)

            builder.position_at_end(entity_blocks[index])
            escaped_write_ptr = self._emit_html_append_static(
                builder, dst_phi, limit_ptr, entity_text,
                f"{name_hint}_escape_{suffix}_entity")
            entity_end_block = builder.block
            next_src = builder.gep(
                src_phi, [one], name=f"{name_hint}_escape_{suffix}_next_src")
            builder.branch(loop_block)
            src_phi.add_incoming(next_src, entity_end_block)
            dst_phi.add_incoming(escaped_write_ptr, entity_end_block)

        builder.position_at_end(normal_block)
        builder.store(ch, dst_phi)
        next_src = builder.gep(src_phi, [one], name=f"{name_hint}_escape_next_src")
        next_dst = builder.gep(dst_phi, [one], name=f"{name_hint}_escape_next_dst")
        builder.branch(loop_block)
        src_phi.add_incoming(next_src, normal_block)
        dst_phi.add_incoming(next_dst, normal_block)

        builder.position_at_end(done_block)
        return dst_phi

    def _emit_html_hydrate(self, builder, call_name, call, template: HtmlTemplate,
                           arg_val_named):
        parts, arg_types = self._html_template_parts_and_args(template)
        # One global buffer per hydrate call site. This is intentionally simple
        # and inspectable for the first feature slice: the pointer remains valid
        # after a render helper returns, while later calls to the same helper may
        # overwrite that helper's buffer.
        buffer_size = 65536
        static_byte_count = sum(
            len(value_text.encode("utf-8"))
            for kind, value_text, _context_kind, _attr_name in parts
            if kind == "static"
        )
        if static_byte_count >= buffer_size:
            raise ValueError(
                f"htmlBody {template.name}: static HTML is {static_byte_count} "
                f"bytes, exceeding hydrate buffer capacity {buffer_size - 1}")
        for required_arg in arg_types:
            if required_arg not in call["args"]:
                raise ValueError(
                    f"{call_name}: missing required arg `{required_arg}` "
                    f"for htmlTemplate `{template.name}`")
        for provided_arg in call["args"]:
            if provided_arg not in arg_types:
                raise ValueError(
                    f"{call_name}: arg `{provided_arg}` is not declared by "
                    f"htmlTemplate `{template.name}`")
        array_ty = ir.ArrayType(I8, buffer_size)
        buffer_name = f"as.htmlbuf.{self._next_html_buffer_id}.{call_name}"
        self._next_html_buffer_id += 1
        html_buffer = ir.GlobalVariable(self.module, array_ty, name=buffer_name)
        html_buffer.linkage = "internal"
        html_buffer.global_constant = False
        html_buffer.initializer = ir.Constant(array_ty, bytearray(buffer_size))
        zero = ir.Constant(I32, 0)
        buffer_ptr = builder.gep(html_buffer, [zero, zero], inbounds=True)
        limit_ptr = builder.gep(
            buffer_ptr, [ir.Constant(I64, buffer_size - 1)],
            name=f"{call_name}_html_limit")
        write_ptr = buffer_ptr
        arg_index = 0
        for part_index, (kind, value_text, context_kind, _attr_name) in enumerate(parts):
            if kind == "static":
                write_ptr = self._emit_html_append_static(
                    builder, write_ptr, limit_ptr, value_text,
                    f"{call_name}_{part_index}_static")
                continue
            arg_name = value_text
            value = self._html_arg_as_cstring(
                builder, arg_val_named(arg_name), arg_name, arg_types[arg_name])
            escape_mode = self._html_arg_escape_mode(
                arg_types[arg_name], context_kind)
            if escape_mode == "raw":
                write_ptr = self._emit_html_append_cstring(
                    builder, write_ptr, value, limit_ptr,
                    f"{call_name}_{arg_index}_{arg_name}")
            else:
                write_ptr = self._emit_html_append_escaped_cstring(
                    builder, write_ptr, value, limit_ptr,
                    f"{call_name}_{arg_index}_{arg_name}",
                    escape_quotes=(escape_mode == "attribute"))
            arg_index += 1
        builder.store(ir.Constant(I8, 0), write_ptr)
        call["result"] = buffer_ptr

    # ---------- module-scope mutable globals ----------
    def _emit_mutable_globals(self):
        """Emit an LLVM module-global for each `storage module mutable` or
        `sharedState <scope> mutable` declared at program scope. The
        initializer is folded from the declared raw value (or the const it
        references). resolve() inside _compile_body checks self._mutable_globals
        before prog.consts so a read of NAME becomes a load of the global,
        and the `set module` / `set sharedState` handler routes through
        store. Cross-op visibility comes for free because the LLVM global
        is module-scope."""
        prog = self.prog
        for name, (typ_name, raw_value) in prog.mutable_globals.items():
            llty = llvm_type_for(prog, typ_name)
            if llty is None:
                continue
            # Resolve a const-name initializer through prog.consts one level
            # deep so `storage module mutable A I64 zeroCount` works when
            # zeroCount is itself a declared const.
            init_value = raw_value
            if isinstance(init_value, str) and init_value in prog.consts:
                _, inner = prog.consts[init_value]
                init_value = inner
            if isinstance(llty, ir.IntType):
                try:
                    initializer = ir.Constant(llty, int(init_value))
                except (TypeError, ValueError):
                    initializer = ir.Constant(llty, 0)
            elif isinstance(llty, (ir.FloatType, ir.DoubleType)):
                try:
                    initializer = ir.Constant(llty, float(init_value))
                except (TypeError, ValueError):
                    initializer = ir.Constant(llty, 0.0)
            elif isinstance(llty, ir.PointerType):
                initializer = ir.Constant(llty, None)
            else:
                initializer = ir.Constant(llty, None)
            gv = ir.GlobalVariable(self.module, llty, name=f"as.global.{name}")
            gv.linkage = "internal"
            gv.global_constant = False
            gv.initializer = initializer
            self._mutable_globals[name] = gv

    def _require_operation_output_contract(self, op: Operation) -> OutputContract:
        contract = _operation_output_contract(self.prog, op)
        if contract.problem:
            raise ValueError(contract.message)
        return contract

    # ---------- entry ----------
    def compile(self):
        # Emit mutable module globals first so any operation body that
        # reads or writes one sees the LLVM global already in scope.
        self._emit_mutable_globals()
        # When `target webServer` is declared with no explicit `entry` line,
        # the program's entry points are its `route` handlers, not a main()
        # operation. We don't yet host an HTTP runtime, but we still emit
        # every handler as an LLVM function and a stub `int main() { return 0; }`
        # so the program links and the AST/tooling pass sees the real bodies.
        # Programs without an `entry` line are libraries / declarative
        # showcases (`target webServer` route handlers, the refined-syntax
        # surface, stdlib mirrors). Compile every operation as a callable
        # function and emit a stub `int main() { return 0; }` so the program
        # links and tooling can inspect each operation's IR.
        if self.prog.entry is None:
            if self._is_windows_gui_program():
                raise NotImplementedError(
                    "target windowsGui now uses standard SemanticScript entry "
                    "syntax: declare `entry console main` and call `gui.*` "
                    "functions from standard.gui. The compiler does not build "
                    "GUI application graphs from custom keywords.")
            self._compile_webserver_program()
            return self.module
        mode, opname = self.prog.entry
        if mode != "console":
            raise NotImplementedError(
                f"entry mode `{mode}` is spec-defined (see spec §17 for "
                f"webServer, §16 for console) but no runtime backend has "
                f"been wired into this compiler beyond `entry console`. "
                f"The parser accepts `webServer` / `route` / handler "
                f"operations so a sample can be authored, lint-checked, "
                f"and indexed by tooling. Use `--parse-only` to verify "
                f"the AST of an `entry {mode}` program.")
        if opname not in self.prog.operations:
            raise ValueError(f"entry references unknown operation: {opname}")
        self._require_operation_output_contract(self.prog.operations[opname])

        # ---- pass 1: pre-declare every non-main user operation as an LLVM
        # function prototype, so any operation can call any other regardless
        # of source order. The signature is `i32 op(params...)` where params
        # come from `input` lines minus opaque-dependency symbols (the
        # `console`/`process`/etc. inputs documented by §16 but not carried
        # at the LLVM ABI boundary).
        # An operation named `main` that ISN'T the entry would collide with
        # the LLVM `@main` we emit for the entry — that happens whenever
        # importModule pulls in a std module whose smoke-test op is
        # called `main`. Skip those: each imported `main` is the module's
        # own smoke test and unreachable from outside anyway.
        self._user_ops = {}  # opName -> {"fn": LLVMFn, "params": [(pname, llty, ptype_name)]}
        for name, op in self.prog.operations.items():
            if name == opname:
                continue
            if name == "main":
                continue
            self._declare_user_op(op)

        # ---- pass 2: compile each non-main op's body into its prototype.
        for name, op in self.prog.operations.items():
            if name == opname:
                continue
            if name == "main":
                continue
            self._compile_user_op(op)

        # ---- pass 3: compile main with the void signature `i32 @main()`.
        self._compile_main(self.prog.operations[opname])
        return self.module

    def _is_windows_gui_program(self) -> bool:
        return (
            "windowsGui" in self.prog.targets
            or _build_metadata_value(self.prog, "targetRuntime") == "windowsGui"
        )

    # ---------- user-defined operations ----------
    def _declare_user_op(self, op: Operation):
        """Walk the operation's `input` lines, drop opaque-dep params, build
        the LLVM function prototype, and record it for later call-site lookup.

        The return type is derived from the operation's `output` line:
            output OPNAME Result OK_TYPE ERR_TYPE     -> OK_TYPE
            output OPNAME OK_TYPE                     -> OK_TYPE
        Current 1.0 behavior rejects missing, malformed, or unknown output
        contracts before LLVM lowering.
        If OK_TYPE is `Void` (the spec's no-value success leg), we fall back
        to i32 because the LLVM ABI still needs a concrete return slot — the
        i32 then carries a sentinel zero. If the output line is missing or
        the OK type isn't a known SemanticScript type alias, we also use i32 (backward
        compatible with pre-typed user-ops).

        1.0 strictness note: that legacy fallback is now guarded by
        _require_operation_output_contract; missing, malformed, or unknown
        output contracts are rejected before lowering."""
        params = []  # list of (pname, llvm_type, source_type_name)
        contract = self._require_operation_output_contract(op)
        return_type = contract.llvm_type
        return_type_name = contract.ok_type
        for verb, args, _ln in op.lines:
            if verb == "output":
                continue
            if verb != "input" or len(args) < 3:
                continue
            _owner_op_name, pname, ptype = args[0], args[1], args[2]
            preserve_web_handle = (
                op.name in self._web_route_handler_names
                and ptype in ("HttpRequest", "HttpResponse")
            )
            if pname in OPAQUE_INPUTS and not preserve_web_handle:
                continue
            llty = llvm_type_for(self.prog, ptype)
            if llty is None:
                # Unknown PascalCase type → also treated as opaque and skipped.
                continue
            params.append((pname, llty, ptype))
        fnty = ir.FunctionType(return_type, [pt[1] for pt in params])
        fn = ir.Function(self.module, fnty, name=op.name)
        for i, (pname, _, _) in enumerate(params):
            fn.args[i].name = pname
        self._user_ops[op.name] = {
            "fn": fn,
            "params": params,
            "return_type": return_type,
            "return_type_name": return_type_name,
        }

    # Refined-syntax operations marked `operationBody NAME runtimeBinding`
    # delegate to a libc/runtime primitive named on the `runtimeBinding`
    # line. Mapping the spec-shaped binding name to the actual libc symbol
    # gives those operations real semantics — `compareCString` runs strcmp,
    # `stringByteLength` runs strlen, etc. — instead of returning zero.
    _RUNTIME_BINDING_MAP = {
        "runtime.cstring.compare":         ("strcmp",  "i32_from_two_i8p"),
        "runtime.cstring.byteLength":      ("strlen",  "i64_from_i8p"),
        "runtime.cstring.validateNullTerminated":
                                            ("strlen",  "i64_from_i8p"),
        "runtime.memory.copyBytes":        ("memcpy",  "i8p_from_dst_src_n"),
        "runtime.text.validateUtf8":       ("strlen",  "i64_from_i8p"),
        "runtime.calendar.isLeapYearAsCInt": (None, "leap_year_i32"),
        "runtime.calendar.isLeapYearBool":   (None, "leap_year_i1"),
        # Metrics counter increment: signature is (runtime, current, step) →
        # current + step. The runtime arg is opaque; the real work is i64
        # arithmetic over the remaining two operands.
        "metrics.computeIncrementI64":       (None, "add_arg1_arg2_i64"),
        # Retry-policy delay calculator: signature is (policy, attemptIndex)
        # → DurationMilliseconds. Without policy-field introspection in this
        # compiler, lower to a simple linear-backoff stub: 50 * (attempt+1)
        # milliseconds. Gives the program well-typed, sensible-shape values
        # rather than always-zero.
        "retryPolicy.delayForAttempt":       (None, "linear_backoff_50ms"),
        # Metrics lock acquire/release: opaque guard tokens. Acquire returns
        # 1 (a non-null token); release returns 0 (success). Both are i64.
        "metricsLock.acquire":               (None, "const_one_i64"),
        "metricsLock.release":               (None, "const_zero"),
        # Scheduler sleep: synchronous no-op returning 0.
        "scheduler.sleep":                   (None, "const_zero"),
    }

    # Refined-syntax operations marked `operationBody NAME intrinsic` lower
    # to real arithmetic IR. The `intrinsicName NAME arithmetic.X` line
    # picks which IR pattern to emit.
    _INTRINSIC_MAP = {
        "arithmetic.addI64":           ("add",  "i64"),
        "arithmetic.subtractI64":      ("sub",  "i64"),
        "arithmetic.multiplyI64":      ("mul",  "i64"),
        "arithmetic.divideI64":        ("sdiv", "i64"),
        "arithmetic.moduloI64":        ("srem", "i64"),
        "arithmetic.equalI64":         ("==",   "i1"),
        "arithmetic.notEqualI64":      ("!=",   "i1"),
        "arithmetic.lessThanI64":      ("<",    "i1"),
        "arithmetic.lessThanOrEqualI64": ("<=", "i1"),
        "arithmetic.greaterThanI64":   (">",    "i1"),
        "arithmetic.greaterThanOrEqualI64": (">=", "i1"),
        "arithmetic.greaterThanOrEqualCByteCount": (">=", "i1"),
        "arithmetic.equalCSignedInt32": ("==",  "i1"),
    }

    def _compile_user_op(self, op: Operation):
        info = self._user_ops[op.name]
        fn = info["fn"]
        entry_bb = fn.append_basic_block("entry")
        builder = ir.IRBuilder(entry_bb)
        initial_binds = {pname: fn.args[i]
                         for i, (pname, _, _) in enumerate(info["params"])}
        # Refined-syntax shortcut: if the operation's body is just a
        # `runtimeBinding NAME TARGET` line and TARGET maps to a libc call,
        # emit that call directly and return — bypassing the no-op walk.
        if self._try_emit_runtime_binding(op, fn, builder):
            return
        if self._try_emit_intrinsic(op, fn, builder):
            return
        self._compile_body(op, fn, builder, initial_binds=initial_binds)

    def _try_emit_intrinsic(self, op: Operation, fn, builder) -> bool:
        # Look for `intrinsicName NAME arithmetic.X`. Body becomes the
        # appropriate LLVM arithmetic instruction over the two params.
        target = None
        for verb, args, _ln in op.lines:
            if verb == "intrinsicName" and len(args) >= 2:
                target = args[1]
                break
        mapping = self._INTRINSIC_MAP.get(target)
        if mapping is None:
            return False
        opcode, _shape = mapping
        params = list(fn.args)
        if len(params) < 2:
            return False
        left, right = params[0], params[1]
        rty = fn.function_type.return_type
        if opcode in ("add", "sub", "mul", "sdiv", "srem"):
            method = {"add": builder.add, "sub": builder.sub,
                      "mul": builder.mul, "sdiv": builder.sdiv,
                      "srem": builder.srem}[opcode]
            res = method(left, right)
            if res.type != rty:
                if isinstance(rty, ir.IntType):
                    if rty.width < res.type.width:
                        res = builder.trunc(res, rty)
                    elif rty.width > res.type.width:
                        res = builder.sext(res, rty)
            builder.ret(res)
            return True
        # comparison: emit icmp
        res = builder.icmp_signed(opcode, left, right)
        if rty == I1:
            builder.ret(res)
        elif isinstance(rty, ir.IntType):
            builder.ret(builder.zext(res, rty))
        else:
            builder.ret(ir.Constant(rty, 0))
        return True

    def _try_emit_runtime_binding(self, op: Operation, fn, builder) -> bool:
        target = None
        for verb, args, _ln in op.lines:
            if verb == "runtimeBinding" and len(args) >= 2:
                target = args[1]
                break
        mapping = self._RUNTIME_BINDING_MAP.get(target)
        if mapping is None:
            return False
        libc_name, shape = mapping
        rty = fn.function_type.return_type
        params = list(fn.args)
        if shape == "i32_from_two_i8p" and len(params) >= 2:
            fty = ir.FunctionType(I32, [I8P, I8P])
            extern = self.module.globals.get(libc_name) or ir.Function(
                self.module, fty, name=libc_name)
            res = builder.call(extern, [params[0], params[1]])
            if rty == I32:
                builder.ret(res)
            elif isinstance(rty, ir.IntType):
                if rty.width > 32:
                    builder.ret(builder.sext(res, rty))
                else:
                    builder.ret(builder.trunc(res, rty))
            else:
                builder.ret(ir.Constant(rty, 0))
            return True
        if shape == "i64_from_i8p" and len(params) >= 1:
            fty = ir.FunctionType(I64, [I8P])
            extern = self.module.globals.get(libc_name) or ir.Function(
                self.module, fty, name=libc_name)
            res = builder.call(extern, [params[0]])
            if rty == I64:
                builder.ret(res)
            elif isinstance(rty, ir.IntType):
                if rty.width < 64:
                    builder.ret(builder.trunc(res, rty))
                else:
                    builder.ret(builder.sext(res, rty))
            else:
                builder.ret(ir.Constant(rty, 0))
            return True
        if shape == "linear_backoff_50ms":
            # 50 * (attempt + 1). The opaque policy input is dropped, so
            # attemptIndex is the last param.
            attempt = params[-1]
            if isinstance(attempt.type, ir.IntType) and attempt.type.width != 64:
                attempt = (builder.sext if attempt.type.width < 64
                           else builder.trunc)(attempt, I64)
            plus_one = builder.add(attempt, ir.Constant(I64, 1))
            res = builder.mul(plus_one, ir.Constant(I64, 50))
            if isinstance(rty, ir.IntType):
                if rty.width != 64:
                    res = (builder.trunc if rty.width < 64
                           else builder.sext)(res, rty)
                builder.ret(res)
            else:
                builder.ret(ir.Constant(rty, 0))
            return True
        if shape == "const_one_i64":
            if isinstance(rty, ir.IntType):
                builder.ret(ir.Constant(rty, 1))
            elif isinstance(rty, ir.PointerType):
                # Materialize a non-null sentinel pointer (inttoptr 1).
                ptr = builder.inttoptr(ir.Constant(I64, 1), rty)
                builder.ret(ptr)
            else:
                builder.ret(ir.Constant(rty, 0))
            return True
        if shape == "const_zero":
            if isinstance(rty, ir.PointerType):
                builder.ret(ir.Constant(rty, None))
            elif isinstance(rty, (ir.FloatType, ir.DoubleType)):
                builder.ret(ir.Constant(rty, 0.0))
            else:
                builder.ret(ir.Constant(rty, 0))
            return True
        if shape == "add_arg1_arg2_i64" and len(params) >= 2:
            # The MetricsRuntime opaque input is dropped at the ABI by
            # _declare_user_op, so the LLVM signature exposes (current, step).
            left, right = params[-2], params[-1]
            for v in (left, right):
                if isinstance(v.type, ir.IntType) and v.type.width != 64:
                    pass  # caller-side coercion already done; trust types
            res = builder.add(left, right)
            if isinstance(rty, ir.IntType):
                if rty.width != res.type.width:
                    res = (builder.sext if rty.width > res.type.width
                           else builder.trunc)(res, rty)
                builder.ret(res)
            else:
                builder.ret(ir.Constant(rty, 0))
            return True
        if shape in ("leap_year_i32", "leap_year_i1") and len(params) >= 1:
            # is_leap = (y%4 == 0 && y%100 != 0) || (y%400 == 0)
            year = params[0]
            mod4 = builder.srem(year, ir.Constant(I64, 4))
            mod100 = builder.srem(year, ir.Constant(I64, 100))
            mod400 = builder.srem(year, ir.Constant(I64, 400))
            zero = ir.Constant(I64, 0)
            div4 = builder.icmp_signed("==", mod4, zero)
            div100 = builder.icmp_signed("!=", mod100, zero)
            div400 = builder.icmp_signed("==", mod400, zero)
            ordinary = builder.and_(div4, div100)
            is_leap = builder.or_(ordinary, div400)
            if shape == "leap_year_i1":
                if rty == I1:
                    builder.ret(is_leap)
                elif isinstance(rty, ir.IntType):
                    builder.ret(builder.zext(is_leap, rty))
                else:
                    builder.ret(ir.Constant(rty, 0))
            else:
                # i32 form: leap → 1, else 0
                res = builder.zext(is_leap, I32)
                if rty == I32:
                    builder.ret(res)
                elif isinstance(rty, ir.IntType):
                    if rty.width > 32:
                        builder.ret(builder.sext(res, rty))
                    else:
                        builder.ret(builder.trunc(res, rty))
                else:
                    builder.ret(ir.Constant(rty, 0))
            return True
        if shape == "i8p_from_dst_src_n" and len(params) >= 3:
            fty = ir.FunctionType(I8P, [I8P, I8P, I64])
            extern = self.module.globals.get(libc_name) or ir.Function(
                self.module, fty, name=libc_name)
            # Coerce the third arg (byteCount) to i64 if needed.
            count = params[2]
            if isinstance(count.type, ir.IntType) and count.type.width != 64:
                count = builder.sext(count, I64) if count.type.width < 64 else builder.trunc(count, I64)
            res = builder.call(extern, [params[0], params[1], count])
            if isinstance(rty, ir.PointerType):
                builder.ret(res)
            elif isinstance(rty, ir.IntType):
                builder.ret(builder.ptrtoint(res, rty))
            else:
                builder.ret(ir.Constant(rty, 0))
            return True
        # Unknown shape — fall back to the default no-op body.
        return False

    # ---------- main operation ----------
    def _compile_main(self, op: Operation):
        fnty = ir.FunctionType(I32, [])
        fn = ir.Function(self.module, fnty, name="main")
        entry_bb = fn.append_basic_block("entry")
        builder = ir.IRBuilder(entry_bb)
        self._compile_body(op, fn, builder, initial_binds={})

    def _compile_webserver_program(self):
        # Compile every operation as a callable function (handlers + helpers).
        # Routed webServer programs now emit a native HTTP runtime entrypoint;
        # declarative/library files without routes keep the historic stub main.
        self._user_ops = {}
        active_servers = [
            server for server in self.prog.web_servers.values()
            if server.routes
        ]
        self._web_route_handler_names = {
            handler for server in active_servers
            for _method, _path, handler in server.routes
        }
        self._web_route_handler_names.update({
            middleware for server in active_servers
            for _path, middleware in server.middleware
        })
        for name, op in self.prog.operations.items():
            self._declare_user_op(op)
        for name, op in self.prog.operations.items():
            self._compile_user_op(op)

        if active_servers:
            if len(active_servers) > 1:
                raise ValueError(
                    "target webServer currently supports one routed webServer per executable")
            self._emit_webserver_main(active_servers[0])
            return

        fnty = ir.FunctionType(I32, [])
        fn = ir.Function(self.module, fnty, name="main")
        entry_bb = fn.append_basic_block("entry")
        builder = ir.IRBuilder(entry_bb)
        builder.ret(ir.Constant(I32, 0))

    def _validate_web_route_handler(self, server_name: str, method: str, path: str, handler_name: str):
        if handler_name not in self.prog.operations:
            raise ValueError(
                f"route {server_name} {method} {path}: handler `{handler_name}` is not defined")
        op_info = self._user_ops.get(handler_name)
        if op_info is None:
            raise ValueError(
                f"route {server_name} {method} {path}: handler `{handler_name}` was not compiled")

        param_types = [ptype for _pname, _llty, ptype in op_info["params"]]
        if param_types != ["HttpRequest", "HttpResponse"]:
            raise ValueError(
                f"route {server_name} {method} {path}: handler `{handler_name}` must declare "
                "`input HANDLER request HttpRequest`, `input HANDLER response HttpResponse`, "
                "and no extra native ABI parameters")
        if op_info["return_type"] != I32:
            raise ValueError(
                f"route {server_name} {method} {path}: handler `{handler_name}` must return CSignedInt32")

    def _emit_webserver_main(self, server: WebServer):
        if server.host is None:
            raise ValueError(f"webServer `{server.name}` is missing serverHost")
        if server.port is None:
            raise ValueError(f"webServer `{server.name}` is missing serverPort")
        for method, path, handler_name in server.routes:
            self._validate_web_route_handler(server.name, method, path, handler_name)
        middleware_by_path = {}
        for path, middleware_name in server.middleware:
            route_path = _unwrap(path)
            self._validate_web_route_handler(server.name, "MIDDLEWARE", route_path, middleware_name)
            middleware_by_path[route_path] = middleware_name

        handler_fnty = ir.FunctionType(I32, [I8P, I8P])
        handler_ptr_ty = handler_fnty.as_pointer()
        route_ty = ir.LiteralStructType([I8P, I8P, handler_ptr_ty, handler_ptr_ty])
        # Trailing field is the optional `not_found_handler` function
        # pointer (NULL when the program didn't declare routeNotFound).
        config_ty = ir.LiteralStructType(
            [I8P, I16, route_ty.as_pointer(), I64, handler_ptr_ty])
        server_run = self._runtime_func("ss_http_server_run", I32, [config_ty.as_pointer()])

        fnty = ir.FunctionType(I32, [])
        fn = ir.Function(self.module, fnty, name="main")
        entry_bb = fn.append_basic_block("entry")
        builder = ir.IRBuilder(entry_bb)

        route_count = len(server.routes)
        routes_ty = ir.ArrayType(route_ty, route_count)
        routes_slot = builder.alloca(routes_ty, name="ss_routes")
        zero_i32 = ir.Constant(I32, 0)

        for index, (method, path, handler_name) in enumerate(server.routes):
            route_ptr = builder.gep(
                routes_slot,
                [zero_i32, ir.Constant(I32, index)],
                inbounds=True,
                name=f"ss_route_{index}"
            )
            method_ptr = self._i8p(builder, method.upper())
            path_ptr = self._i8p(builder, path)
            handler_fn = self._user_ops[handler_name]["fn"]
            handler_ptr = handler_fn
            middleware_ptr = ir.Constant(handler_ptr_ty, None)
            middleware_name = middleware_by_path.get(path)
            if middleware_name is not None:
                middleware_ptr = self._user_ops[middleware_name]["fn"]
                if middleware_ptr.type != handler_ptr_ty:
                    middleware_ptr = builder.bitcast(middleware_ptr, handler_ptr_ty)
            if handler_ptr.type != handler_ptr_ty:
                handler_ptr = builder.bitcast(handler_ptr, handler_ptr_ty)

            builder.store(method_ptr, builder.gep(
                route_ptr, [zero_i32, zero_i32], inbounds=True))
            builder.store(path_ptr, builder.gep(
                route_ptr, [zero_i32, ir.Constant(I32, 1)], inbounds=True))
            builder.store(handler_ptr, builder.gep(
                route_ptr, [zero_i32, ir.Constant(I32, 2)], inbounds=True))
            builder.store(middleware_ptr, builder.gep(
                route_ptr, [zero_i32, ir.Constant(I32, 3)], inbounds=True))

        config_slot = builder.alloca(config_ty, name="ss_server_config")
        first_route_ptr = builder.gep(routes_slot, [zero_i32, zero_i32], inbounds=True)
        builder.store(self._i8p(builder, server.host), builder.gep(
            config_slot, [zero_i32, zero_i32], inbounds=True))
        builder.store(ir.Constant(I16, int(server.port)), builder.gep(
            config_slot, [zero_i32, ir.Constant(I32, 1)], inbounds=True))
        builder.store(first_route_ptr, builder.gep(
            config_slot, [zero_i32, ir.Constant(I32, 2)], inbounds=True))
        builder.store(ir.Constant(I64, route_count), builder.gep(
            config_slot, [zero_i32, ir.Constant(I32, 3)], inbounds=True))

        # not_found_handler slot — populated by convention: if the app
        # declared a route at the wildcard path "*", use its handler as
        # the dispatcher's fallback. Keeps the compiler thin — no
        # special verb needed; the app just writes
        # `route SERVER GET "*" myNotFoundHandler` and the runtime
        # pulls it out of the route table at config-build time.
        nf_ptr = ir.Constant(handler_ptr_ty, None)
        for _method, _path, handler_name in server.routes:
            if _path == "*":
                nf_fn = self._user_ops[handler_name]["fn"]
                nf_ptr = nf_fn
                if nf_ptr.type != handler_ptr_ty:
                    nf_ptr = builder.bitcast(nf_ptr, handler_ptr_ty)
                break
        builder.store(nf_ptr, builder.gep(
            config_slot, [zero_i32, ir.Constant(I32, 4)], inbounds=True))

        rc = builder.call(server_run, [config_slot], name="ss_http_server_status")
        builder.ret(rc)

    # ---------- shared body compilation ----------
    def _compile_body(self, op: Operation, fn, builder, initial_binds: dict):
        prog = self.prog

        labels = {}        # name -> BasicBlock
        calls = {}         # callName -> {target, args, result, error_value, error_cond}
        binds = dict(initial_binds)  # bind-name -> SSA value (or alloca pointer for vars)
        # bind-name -> entry-block alloca slot for handles that need to be
        # re-loaded at later use sites (defer cleanup). See bindOk handling
        # below and the sqlite.openDatabase / sqlite.prepareStatement
        # dispatchers in _emit_run for the producer side.
        bind_slots = {}
        var_types = {}     # var-name -> LLVM type
        is_var = set()     # set of mutable var names

        # Pre-create blocks for every label in source order
        for verb, args, _ln in op.lines:
            if verb == "label":
                labels[args[0]] = fn.append_basic_block(args[0])

        SENTINEL = object()
        opaque_inputs = OPAQUE_INPUTS

        def make_call(call_name, target, lineno):
            return {
                "name": call_name,
                "operation": op.name,
                "line": lineno,
                "target": target,
                "args": {},
                "arg_lines": {},
                "result": None,
                "error_value": None,
                "error_cond": None,
            }

        def get_block(name):
            if name not in labels:
                labels[name] = fn.append_basic_block(name)
            return labels[name]

        def emit_const_value(typ, raw):
            llty = llvm_type_for(prog, typ)
            resolved = resolve_alias(prog, typ)
            enum_cases = enum_case_values(prog)
            if enum_repr_type(prog, resolved) is not None and isinstance(raw, str):
                enum_case = enum_cases.get(raw)
                if enum_case is not None and enum_case[0] == resolved:
                    raw = enum_case[1]
            # Refined-syntax `storage module immutable A I64 B` lets `B` be
            # the name of another const rather than a literal. Recursively
            # resolve up to a small depth to avoid pathological cycles.
            if isinstance(raw, str) and raw in prog.consts:
                inner_typ, inner_val = prog.consts[raw]
                if isinstance(inner_val, str) and inner_val in prog.consts:
                    raw = prog.consts[inner_val][1]
                else:
                    raw = inner_val
            # Any type that lowers to the i8* pointer shape (the canonical
            # spec-compliant `CNullTerminatedByteString`, the legacy
            # `CString`/`String`, or any user alias that resolves to one of
            # these) and whose const value is a literal string gets the
            # interned-i8-array treatment. The check is on the LLVM type so
            # future pointer-shaped aliases don't need a special case.
            if llty == I8P and isinstance(raw, str):
                return self._i8p(builder, raw)
            if llty is None:
                raise ValueError(f"unsupported const type: {typ}")
            if isinstance(llty, ir.IntType):
                if llty.width == 1:
                    if isinstance(raw, str):
                        if raw.lower() in ("true", "yes"):
                            return ir.Constant(I1, 1)
                        if raw.lower() in ("false", "no"):
                            return ir.Constant(I1, 0)
                    try:
                        return ir.Constant(I1, int(bool(int(raw))))
                    except (TypeError, ValueError):
                        return ir.Constant(I1, 0)
                try:
                    return ir.Constant(llty, int(raw))
                except (TypeError, ValueError):
                    # Last-resort stub: zero. Refined-syntax may bind a
                    # const-typed slot to a name that can't be resolved
                    # statically; emit zero rather than crash codegen.
                    return ir.Constant(llty, 0)
            if isinstance(llty, (ir.FloatType, ir.DoubleType)):
                try:
                    return ir.Constant(llty, float(raw))
                except (TypeError, ValueError):
                    return ir.Constant(llty, 0.0)
            raise ValueError(f"unsupported const type: {typ}")

        def resolve(tok):
            if isinstance(tok, str):
                stripped = tok.lstrip("-")
                if stripped.isdigit():
                    return ir.Constant(I64, int(tok))
                # Float literal: contains a '.' and the rest is digits/sign/e.
                if "." in tok or "e" in tok or "E" in tok:
                    try:
                        return ir.Constant(F64, float(tok))
                    except ValueError:
                        pass
            if tok in is_var:
                return builder.load(binds[tok], name=f"{tok}_load")
            if tok in binds:
                return binds[tok]
            # Operation-local consts take precedence over module-global
            # consts (spec scope law). Falls through to prog.consts only
            # if not locally declared.
            if tok in op.consts:
                typ, val = op.consts[tok]
                return emit_const_value(typ, val)
            # Module-scope mutable globals (`storage module mutable`,
            # `sharedState <scope> mutable`) take precedence over prog.consts
            # so a reference reads the current LLVM-global value rather than
            # the frozen initializer recorded in consts.
            if tok in self._mutable_globals:
                gv = self._mutable_globals[tok]
                return builder.load(gv, name=f"{tok}_load")
            if tok in prog.consts:
                typ, val = prog.consts[tok]
                return emit_const_value(typ, val)
            enum_case = enum_case_values(prog).get(tok)
            if enum_case is not None:
                enum_name, enum_value = enum_case
                return emit_const_value(enum_name, enum_value)
            if tok in opaque_inputs:
                return SENTINEL
            raise ValueError(f"unresolved symbol: {tok!r}")

        # ---- defer registry ----
        # Collect every `defer*` definition and `deferRunOn` policy once up
        # front, then maintain an active-defer stack while lowering body rows.
        # A cleanup is only emitted on a path that has executed its defer row.
        # That matters for handles produced by fallible calls: a failure branch
        # before `defer statementFinalize ...` cannot legally load/finalize the
        # statement value because it does not dominate that branch.
        defers = []
        defer_by_name = {}
        for verb, args, _ln in op.lines:
            if verb in ("defer", "deferLog", "deferAwaitLog") and len(args) >= 2:
                d = {"name": args[0], "target": args[1],
                     "args": list(args[2:]), "run_on": set()}
                defers.append(d)
                defer_by_name[args[0]] = d
            elif verb == "deferWhenExitLog" and len(args) >= 3:
                d = {"name": args[0], "target": args[2],
                     "args": list(args[3:]), "run_on": set()}
                defers.append(d)
                defer_by_name[args[0]] = d
            elif verb == "deferRunOn" and len(args) >= 2:
                d = defer_by_name.get(args[0])
                if d is not None:
                    d["run_on"].add(args[1])
        for d in defers:
            if not d["run_on"]:
                d["run_on"] = {"all"}
        active_defers = []
        label_defer_snapshots = {}

        def _merge_defer_snapshots(existing, incoming):
            incoming_names = {d["name"] for d in incoming}
            return [d for d in existing if d["name"] in incoming_names]

        def record_label_defers(label_name, incoming):
            snapshot = list(incoming)
            if label_name in label_defer_snapshots:
                label_defer_snapshots[label_name] = _merge_defer_snapshots(
                    label_defer_snapshots[label_name], snapshot)
            else:
                label_defer_snapshots[label_name] = snapshot

        # ---- useRetry registry ----
        # Map call name -> policy name. The retry loop wraps `run CALL` so
        # each error-marked failure causes the call to retry, up to the
        # policy's `retryMaxAttempts`. Without an explicit attempts value,
        # we default to 3 — the spec's standard fallback for retry-policy
        # declarations that omit the bound.
        retry_attachments = {}
        for verb, args, _ln in op.lines:
            if verb == "useRetry" and len(args) >= 2:
                retry_attachments[args[0]] = args[1]

        # ---- worker pool work items ----
        # `work NAME target OP` declares a callable work item; `workArg
        # WORK ARG VALUE` binds one positional arg; `submitWork WORK POOL`
        # emits a real call (sync direct-dispatch under single-thread
        # lowering). The bind for `awaitWork WORK` reads the call's result
        # SSA if any. We register each work item under a synthetic call
        # name so _emit_run can dispatch through the standard pipeline.
        work_items = {}
        for verb, args, _ln in op.lines:
            if verb == "work" and len(args) >= 3 and args[1] == "target":
                work_name, target_op = args[0], args[2]
                work_items[work_name] = {"target": target_op, "args": {}}
            elif verb == "workArg" and len(args) >= 3:
                work_name, arg_name, value_name = args[0], args[1], args[2]
                work_items.setdefault(work_name,
                                      {"target": None, "args": {}})
                work_items[work_name]["args"][arg_name] = value_name

        # ---- channel slots ----
        # `send CHANNEL VALUE` / `receive OUT TYPE CHANNEL` in single-thread
        # execution collapse to a single-slot register pass: every `send`
        # writes the resolved value into one alloca per channel; every
        # `receive` reads from the same slot. Allocate up front so both
        # writes and reads see the same SSA pointer. A future multi-thread
        # channel runtime would replace these slots with a real queue.
        channel_slots = {}
        for verb, args, _ln in op.lines:
            if verb == "send" and args:
                channel_slots.setdefault(args[0], None)
            elif verb == "receive" and len(args) >= 3:
                channel_slots.setdefault(args[2], None)
        for channel_name in list(channel_slots.keys()):
            with builder.goto_entry_block():
                slot = builder.alloca(I64, name=f"channel_{channel_name}")
            builder.store(ir.Constant(I64, 0), slot)
            channel_slots[channel_name] = slot

        def _max_attempts_for(policy_name):
            meta = self.prog.hard_metadata.get(policy_name, {})
            entries = meta.get("retryMaxAttempts") or []
            for row in entries:
                if row:
                    raw = row[0]
                    if isinstance(raw, str) and raw in self.prog.consts:
                        _, val = self.prog.consts[raw]
                        try:
                            return max(1, int(val))
                        except (TypeError, ValueError):
                            pass
                    try:
                        return max(1, int(raw))
                    except (TypeError, ValueError):
                        continue
            return 3

        def _defer_runs_on(run_on, exit_path):
            if "all" in run_on or "always" in run_on:
                return True
            return exit_path in run_on

        # Native cleanup targets that a `defer` row can route to. Each
        # entry is (runtime symbol, return type, param types). All of
        # these accept a single opaque-pointer handle and return an int
        # status; the status is intentionally discarded at defer time
        # (a cleanup error would happen on the wrong thread of control
        # to recover from). Without this table, `defer ... sqlite.*`
        # would silently drop — see emit_defers below.
        _NATIVE_DEFER_DISPATCH = {
            "sqlite.closeDatabase": (
                "ss_sqlite_database_close", I32, [I8P]),
            "sqlite.finalizeStatement": (
                "ss_sqlite_statement_finalize", I32, [I8P]),
            "sqlite.resetStatement": (
                "ss_sqlite_statement_reset", I32, [I8P]),
            # json.destroyBuilder returns void in the C ABI but our
            # defer machinery wants a uniform i32 status shape; map
            # the return type as VOID and the defer-site call will
            # ignore the result regardless. The free() inside the
            # native impl runs unconditionally on a non-NULL handle.
            "json.destroyBuilder": (
                "ss_json_builder_destroy", VOID, [I8P]),
        }

        def emit_defers(exit_path, active=None):
            if active is None:
                active = active_defers
            for d in reversed(active):
                if not _defer_runs_on(d["run_on"], exit_path):
                    continue
                target = d["target"]
                native_dispatch = _NATIVE_DEFER_DISPATCH.get(target)
                if native_dispatch is not None:
                    symbol, ret_ty, param_tys = native_dispatch
                    fn = self._runtime_func(symbol, ret_ty, param_tys)
                    arg_vals = []
                    for arg_name, target_ty in zip(d["args"], param_tys):
                        # Prefer re-loading from the entry-block slot the
                        # producer dispatcher stashed via call["handle_slot"]
                        # — the SSA value bound by bindOk lives in the
                        # producer's local block and would not dominate the
                        # defer site. Falling back to the SSA `resolve()`
                        # path is kept for inputs that aren't sqlite handles.
                        slot = bind_slots.get(arg_name)
                        if slot is not None:
                            v = builder.load(
                                slot, name=f"{d['name']}_{arg_name}_reload")
                        else:
                            try:
                                v = resolve(arg_name)
                            except ValueError:
                                v = ir.Constant(target_ty, 0)
                            if v is SENTINEL:
                                v = ir.Constant(target_ty, 0)
                        if (isinstance(target_ty, ir.PointerType)
                                and isinstance(v.type, ir.IntType)):
                            v = builder.inttoptr(v, target_ty)
                        arg_vals.append(v)
                    while len(arg_vals) < len(param_tys):
                        arg_vals.append(
                            ir.Constant(param_tys[len(arg_vals)], 0))
                    builder.call(fn, arg_vals)
                    continue
                fn_entry = self._user_ops.get(target)
                if fn_entry is None:
                    # Non-user-op target (libc, dotted external, etc.).
                    # No runtime route yet; leave the cleanup as metadata.
                    continue
                target_fn = fn_entry["fn"]
                param_lltys = [p[1] for p in fn_entry["params"]]
                arg_vals = []
                for arg_name, target_ty in zip(d["args"], param_lltys):
                    slot = bind_slots.get(arg_name)
                    if slot is not None:
                        v = builder.load(
                            slot, name=f"{d['name']}_{arg_name}_reload")
                    else:
                        try:
                            v = resolve(arg_name)
                        except ValueError:
                            v = ir.Constant(target_ty, 0)
                        if v is SENTINEL:
                            v = ir.Constant(target_ty, 0)
                    if v.type != target_ty:
                        if (isinstance(v.type, ir.IntType)
                                and isinstance(target_ty, ir.IntType)):
                            if v.type.width < target_ty.width:
                                extend = (builder.zext if v.type.width == 1
                                          else builder.sext)
                                v = extend(v, target_ty)
                            else:
                                v = builder.trunc(v, target_ty)
                        elif (isinstance(target_ty, ir.PointerType)
                                and isinstance(v.type, ir.IntType)):
                            v = builder.inttoptr(v, target_ty)
                    arg_vals.append(v)
                while len(arg_vals) < len(param_lltys):
                    arg_vals.append(ir.Constant(param_lltys[len(arg_vals)], 0))
                builder.call(target_fn, arg_vals)

        for verb, args, _ln in op.lines:
            # ----- metadata: ignored at codegen -----
            if verb in ("input", "output", "effect", "memory", "async",
                        "purpose", "invariant", "warning"):
                continue

            if verb == "label":
                label_name = args[0]
                target_bb = labels[label_name]
                if not builder.block.is_terminated:
                    record_label_defers(label_name, active_defers)
                    builder.branch(target_bb)
                builder.position_at_end(target_bb)
                active_defers = list(
                    label_defer_snapshots.get(label_name, active_defers))
                continue

            if verb == "const":
                continue

            if verb == "var":
                # var NAME TYPE INITIAL_VALUE
                # INITIAL_VALUE may be a literal OR the name of a previously
                # declared const, so a domain start value can be expressed once
                # and referenced from its initialization. The latter form is
                # the recommended SemanticScript style.
                name, typ_name = args[0], args[1]
                raw = _unwrap(args[2])
                llty = llvm_type_for(prog, typ_name)
                if llty is None:
                    raise ValueError(f"var: unsupported type {typ_name}")
                with builder.goto_entry_block():
                    slot = builder.alloca(llty, name=name)
                resolved_typ = resolve_alias(prog, typ_name)
                # Initializer resolution:
                # 1. const symbol -> use its declared value (operation-local
                #    consts take precedence over module-global ones)
                # 2. string literal for String -> intern it
                # 3. numeric literal -> coerce to declared type
                const_source = None
                if isinstance(raw, str):
                    if raw in op.consts:
                        const_source = op.consts[raw]
                    elif raw in prog.consts:
                        const_source = prog.consts[raw]
                if const_source is not None:
                    const_typ, const_val = const_source
                    const_ll = llvm_type_for(prog, const_typ)
                    if const_ll == I8P and isinstance(const_val, str):
                        init = self._i8p(builder, const_val)
                    elif resolve_alias(prog, const_typ) == "Bool":
                        # Use the var's declared LLVM width — when the var
                        # is I64 / Bool / etc., we want the init to match
                        # the alloca so the store typechecks.
                        bool_int = _bool_token_to_int(const_val)
                        if isinstance(llty, ir.IntType):
                            init = ir.Constant(llty, bool_int)
                        elif isinstance(llty, (ir.FloatType, ir.DoubleType)):
                            init = ir.Constant(llty, float(bool_int))
                        else:
                            init = ir.Constant(I1, bool_int)
                    elif isinstance(llty, (ir.FloatType, ir.DoubleType)):
                        init = ir.Constant(llty, float(const_val))
                    else:
                        init = ir.Constant(llty, int(const_val))
                elif llty == I8P and isinstance(raw, str):
                    init = self._i8p(builder, raw)
                elif resolved_typ == "Bool":
                    init = ir.Constant(llty if isinstance(llty, ir.IntType)
                                       else I1, _bool_token_to_int(raw))
                elif isinstance(llty, (ir.FloatType, ir.DoubleType)):
                    init = ir.Constant(llty, float(raw))
                else:
                    init = ir.Constant(llty, int(raw))
                builder.store(init, slot)
                binds[name] = slot
                var_types[name] = llty
                is_var.add(name)
                continue

            if verb == "set":
                # Refined syntax: `set <scope> NAME VALUE [...]` where scope
                # is `local`, `module`, or `sharedState`. Legacy form is
                # `set NAME VALUE`. Distinguish by checking whether args[0]
                # is a known scope keyword.
                scope_prefixed = bool(args and args[0] in
                                       ("local", "module", "sharedState"))
                if scope_prefixed:
                    name, value_name = args[1], args[2]
                else:
                    name, value_name = args[0], args[1]
                # Module-scope mutable globals: route the store through the
                # LLVM global. Owner / guard authority is accepted as metadata
                # but not enforced — surfacing it requires real ownership
                # tracking, which the spec leaves as future work.
                if (scope_prefixed and args[0] in ("module", "sharedState")
                        and name in self._mutable_globals):
                    gv = self._mutable_globals[name]
                    gv_ty = gv.type.pointee
                    new_val = resolve(value_name)
                    if new_val.type != gv_ty:
                        if (isinstance(new_val.type, ir.IntType)
                                and isinstance(gv_ty, ir.IntType)):
                            if new_val.type.width < gv_ty.width:
                                extend = (builder.zext if new_val.type.width == 1
                                          else builder.sext)
                                new_val = extend(new_val, gv_ty)
                            else:
                                new_val = builder.trunc(new_val, gv_ty)
                    builder.store(new_val, gv)
                    continue
                if name not in is_var:
                    # Refined-syntax `set local NAME VALUE` may refer to a
                    # storage-local that wasn't surfaced as a var in this
                    # compiler's model. Treat as a no-op so the program
                    # still compiles.
                    if scope_prefixed:
                        continue
                    raise ValueError(f"set: {name} is not a var")
                new_val = resolve(value_name)
                slot = binds[name]
                if new_val.type != var_types[name]:
                    if isinstance(new_val.type, ir.IntType) and isinstance(var_types[name], ir.IntType):
                        if new_val.type.width < var_types[name].width:
                            # Bool / i1 should always zero-extend so `true`
                            # widens to 1, not -1. Other narrow ints
                            # sign-extend per spec convention.
                            extend = (builder.zext if new_val.type.width == 1
                                      else builder.sext)
                            new_val = extend(new_val, var_types[name])
                        else:
                            new_val = builder.trunc(new_val, var_types[name])
                builder.store(new_val, slot)
                continue

            if verb == "call":
                call_name, target = args[0], args[1]
                target = _TARGET_ALIASES.get(target, target)
                # `result`      : value bound by bindOk / bind
                # `error_value` : value bound by bindError (defaults to result)
                # `error_cond`  : i1 used by branchIfError (default: result < 0)
                calls[call_name] = make_call(call_name, target, _ln)
                continue

            # Refined-syntax `recordBuild NAME BUILDER` registers a call
            # whose `run` materializes the record from the builder's
            # `recordSet` lines. We don't lower record construction yet
            # (no struct types), so target the synthetic name `record.build`
            # — `_emit_run`'s external-module fallback emits a zero result
            # so the surrounding bind chain still compiles.
            if verb == "recordBuild" and len(args) >= 2:
                call_name = args[0]
                calls[call_name] = make_call(call_name, "record.build", _ln)
                continue

            if verb == "arg":
                call_name, arg_name, value_name = args[0], args[1], args[2]
                calls[call_name]["args"][arg_name] = value_name
                calls[call_name]["arg_lines"][arg_name] = _ln
                continue

            if verb in ("timeout", "cancelOn"):
                continue

            if verb == "run":
                call_name = args[0]
                policy_name = retry_attachments.get(call_name)
                if policy_name is None:
                    self._emit_run(builder, call_name, calls,
                                   resolve, opaque_inputs, SENTINEL)
                    continue
                # Retry loop: alloca an attempt counter; loop up to
                # `retryMaxAttempts` times; exit on success or attempt
                # exhaustion. The call's `result` SSA — read by later
                # `bind`/`branchIfError` — must dominate the exit block,
                # so we materialize each attempt's result into a slot and
                # rebind call["result"] to a load at the exit block. The
                # error-cond is recomputed at each attempt's body block.
                max_attempts = _max_attempts_for(policy_name)
                fn_blk = builder.function
                retry_top = fn_blk.append_basic_block(f"retry_top_{call_name}")
                retry_body = fn_blk.append_basic_block(f"retry_body_{call_name}")
                retry_inc = fn_blk.append_basic_block(f"retry_inc_{call_name}")
                retry_exit = fn_blk.append_basic_block(f"retry_exit_{call_name}")
                with builder.goto_entry_block():
                    attempt_slot = builder.alloca(
                        I64, name=f"{call_name}_attempt")
                builder.store(ir.Constant(I64, 0), attempt_slot)
                builder.branch(retry_top)
                builder.position_at_end(retry_top)
                cur_attempt = builder.load(attempt_slot)
                cond = builder.icmp_signed(
                    "<", cur_attempt, ir.Constant(I64, max_attempts))
                builder.cbranch(cond, retry_body, retry_exit)
                builder.position_at_end(retry_body)
                self._emit_run(builder, call_name, calls,
                               resolve, opaque_inputs, SENTINEL)
                call_obj = calls[call_name]
                result_ssa = call_obj.get("result")
                result_slot = None
                if result_ssa is not None:
                    # Allocate once on the first iteration we see a result.
                    # Reuse builder.goto_entry_block so the alloca dominates
                    # both retry_body (write) and retry_exit (read).
                    with builder.goto_entry_block():
                        result_slot = builder.alloca(
                            result_ssa.type, name=f"{call_name}_retry_result")
                    builder.store(result_ssa, result_slot)
                err_cond = call_obj.get("error_cond")
                if err_cond is None and result_ssa is not None:
                    if isinstance(result_ssa.type, ir.IntType):
                        zero = ir.Constant(result_ssa.type, 0)
                        err_cond = builder.icmp_signed(
                            "<", result_ssa, zero,
                            name=f"{call_name}_retry_isErr")
                    else:
                        err_cond = ir.Constant(I1, 0)
                if err_cond is None:
                    # No result and no error condition — treat as success.
                    builder.branch(retry_exit)
                else:
                    builder.cbranch(err_cond, retry_inc, retry_exit)
                builder.position_at_end(retry_inc)
                next_attempt = builder.add(
                    builder.load(attempt_slot), ir.Constant(I64, 1))
                builder.store(next_attempt, attempt_slot)
                builder.branch(retry_top)
                builder.position_at_end(retry_exit)
                if result_slot is not None:
                    # Replace the in-body SSA with a load that dominates
                    # everything downstream of the retry. Clear error_cond
                    # because a recomputation would reference the in-body
                    # SSA value, which doesn't dominate this block.
                    call_obj["result"] = builder.load(
                        result_slot, name=f"{call_name}_retry_final")
                    call_obj["error_cond"] = None
                continue

            if verb in ("start", "await"):
                # synchronous fallback for this implementation level
                if verb == "await":
                    self._emit_run(builder, args[0], calls, resolve, opaque_inputs, SENTINEL)
                continue

            if verb in ("bindOk", "bind"):
                value_name, _type_name, call_name = args[0], args[1], args[2]
                binds[value_name] = calls[call_name]["result"]
                # Native dispatch handlers that produce a handle via an
                # out-pointer (sqlite.openDatabase, sqlite.prepareStatement)
                # stash the entry-block alloca on call["handle_slot"]. We
                # parallel-register the slot under the bind name so a later
                # `defer ... sqlite.closeDatabase BIND_NAME` can re-load
                # the handle at the defer site instead of trying to reuse
                # the original load's SSA across basic-block boundaries.
                slot = calls[call_name].get("handle_slot")
                if slot is not None:
                    bind_slots[value_name] = slot
                continue

            if verb == "bindError":
                value_name, _type_name, call_name = args[0], args[1], args[2]
                call = calls[call_name]
                # Prefer the explicit error value if the call recorded one
                # (e.g. checked arithmetic exposes an overflow flag); otherwise
                # fall back to the call's primary result.
                binds[value_name] = call["error_value"] if call["error_value"] is not None else call["result"]
                continue

            if verb == "ignoreOk":
                # ignoreOk CALL_NAME TYPE
                # Explicitly acknowledges the success leg of CALL_NAME and
                # discards its value. The line exists so the source carries
                # the fact that the success value is intentionally unused
                # (rather than silently dropped by the absence of a bindOk).
                if len(args) < 2:
                    raise SyntaxError("ignoreOk requires: ignoreOk CALL_NAME TYPE")
                continue

            if verb == "ignoreValue":
                # ignoreValue CALL_NAME TYPE
                # Infallible analogue of ignoreOk: acknowledges that an
                # infallible call's value is intentionally discarded. The line
                # carries the discard fact so it is not hidden behavior.
                if len(args) < 2:
                    raise SyntaxError("ignoreValue requires: ignoreValue CALL_NAME TYPE")
                continue

            # SOFT reserved verbs are pure metadata — codegen drops them
            # because they cannot change runtime behavior.
            if verb in BODY_VERBS_RESERVED_SOFT:
                continue

            # Cleanup, structured-concurrency, and policy-attachment verbs
            # don't yet have a runtime backend in this compiler, but they
            # produce side-effects in the AST that downstream IR may depend
            # on (e.g. a `bindGroupError` defines a name used in later
            # `branchIfGroupError`; a `new` defines a record var referenced
            # by later fieldGet/fieldSet/arg). Treat each as a structural
            # no-op that registers a zero-valued bind where needed, so the
            # surrounding IR continues to compile. A future runtime can
            # replace these stubs with real concurrent + record semantics.
            # `useRetry CALL POLICY` is collected in the pre-pass above
            # (retry_attachments); at this point in source order it has no
            # standalone effect — the retry loop is emitted at `run CALL`.
            if verb == "useRetry":
                continue
            if verb == "startInGroup" and args:
                # `startInGroup CALL GROUP` — under synchronous taskGroup
                # lowering, this is equivalent to `run CALL`. The work
                # happens immediately on the same thread; `awaitGroup`
                # below is a no-op because the call has already returned.
                if args[0] in calls:
                    self._emit_run(builder, args[0], calls,
                                   resolve, opaque_inputs, SENTINEL)
                continue
            if verb == "submitWork" and args:
                # `submitWork WORK POOL` — synchronous worker-pool lowering:
                # the work runs immediately on the same thread via _emit_run
                # against a synthetic call registered from the `work`/`workArg`
                # pre-pass. Result is stashed in calls[synth_call_name] so a
                # subsequent `awaitWork WORK` can read it.
                work_name = args[0]
                work_def = work_items.get(work_name)
                if (work_def is not None
                        and work_def.get("target") in self._user_ops):
                    synth_call_name = f"_workSubmit__{work_name}"
                    calls[synth_call_name] = make_call(
                        synth_call_name, work_def["target"], _ln)
                    calls[synth_call_name]["args"].update(dict(work_def["args"]))
                    self._emit_run(builder, synth_call_name, calls,
                                   resolve, opaque_inputs, SENTINEL)
                    # Stash under both the work name and the synth name so
                    # `awaitWork WORK` can find the result by either route.
                    work_def["_synth_call_name"] = synth_call_name
                continue
            if verb == "awaitWork" and args:
                # Direct-dispatch lowering: work already ran during
                # submitWork. Bind the work name to the call's result SSA
                # so downstream references resolve to the real value (not a
                # zero stub).
                work_name = args[0]
                work_def = work_items.get(work_name)
                if work_def is not None:
                    synth_call_name = work_def.get("_synth_call_name")
                    if synth_call_name is not None:
                        result = calls[synth_call_name].get("result")
                        if result is not None:
                            binds[work_name] = result
                            continue
                binds[work_name] = ir.Constant(I64, 0)
                continue
            if verb in ("defer", "deferLog", "deferAwaitLog",
                        "deferWhenExitLog"):
                d = defer_by_name.get(args[0]) if args else None
                if d is not None and d not in active_defers:
                    active_defers.append(d)
                continue
            if verb in ("taskGroup", "awaitGroup",
                        "branchIfGroupError",
                        # Channels, locks (spec §22): synchronous-only
                        # no-op lowering. `send`/`receive` are accepted as
                        # name-defining verbs below; `lock`/`unlock` and
                        # `branchIfChannelClosed` drop.
                        "lock", "unlock", "branchIfChannelClosed",
                        # Worker pools (spec §22): declarative.
                        "workerPool", "work", "workArg",
                        # Intervals (spec §23): declarative; drop.
                        "interval", "startInterval",
                        # Select (spec §20 race): declarative; drop.
                        "select", "selectCase", "runSelect"):
                continue
            if verb == "send" and len(args) >= 2:
                # `send CHANNEL VALUE` — single-thread queue pass: store
                # the resolved value into the channel's slot so a matching
                # `receive` later in the body sees it.
                channel_name, value_name = args[0], args[1]
                slot = channel_slots.get(channel_name)
                if slot is not None:
                    try:
                        v = resolve(value_name)
                    except ValueError:
                        v = ir.Constant(I64, 0)
                    if v is SENTINEL:
                        v = ir.Constant(I64, 0)
                    if v.type != I64:
                        if isinstance(v.type, ir.IntType):
                            if v.type.width < 64:
                                v = (builder.zext if v.type.width == 1
                                     else builder.sext)(v, I64)
                            else:
                                v = builder.trunc(v, I64)
                        elif isinstance(v.type, ir.PointerType):
                            v = builder.ptrtoint(v, I64)
                    builder.store(v, slot)
                continue
            if verb == "send":
                continue
            if verb == "receive" and len(args) >= 3:
                # `receive OUT TYPE CHANNEL` — single-thread queue pass:
                # load from the channel's slot into OUT so the value sent
                # earlier in the body flows through.
                out_name, _type_name, channel_name = args[0], args[1], args[2]
                slot = channel_slots.get(channel_name)
                if slot is not None:
                    binds[out_name] = builder.load(slot, name=f"{out_name}_recv")
                else:
                    binds[out_name] = ir.Constant(I64, 0)
                continue
            if verb == "receive" and len(args) >= 2:
                # Short-form `receive OUT CHANNEL` (rare): register OUT as
                # a zero bind so later references resolve.
                binds[args[0]] = ir.Constant(I64, 0)
                continue
            if verb == "awaitWork" and len(args) >= 1:
                # `awaitWork WORK` — register WORK as zero bind.
                binds[args[0]] = ir.Constant(I64, 0)
                continue
            if verb == "awaitIntervalTick" and len(args) >= 1:
                # `awaitIntervalTick NAME` — no-op (synchronous fallthrough).
                continue
            if verb == "branchSelected" and len(args) >= 3:
                # `branchSelected NAME BRANCH LABEL` — always falls through
                # (the no-op select runs no branches), so jump straight to
                # the success continuation. Same shape as branchIfGroupError.
                continue
            if verb == "bindGroupError" and len(args) >= 2:
                binds[args[0]] = ir.Constant(I64, 0)
                continue
            if verb == "new" and len(args) >= 1:
                binds[args[0]] = ir.Constant(I64, 0)
                continue
            if verb == "fieldGet" and len(args) >= 1:
                binds[args[0]] = ir.Constant(I64, 0)
                continue
            if verb == "fieldSet":
                continue

            # HARD reserved verbs are spec-defined runtime features. The
            # codegen does not lower them yet, and silently dropping them
            # would violate spec §2 law 5 ("hidden behavior is illegal by
            # default"). Refuse to compile, naming the spec section.
            if verb in BODY_VERBS_RESERVED_HARD:
                raise NotImplementedError(
                    f"line {_ln}: verb `{verb}` is spec-defined but "
                    f"not yet lowered to LLVM IR by this compiler. The "
                    f"compiler refuses to silently drop its semantics "
                    f"(spec §2 law 5: hidden behavior is illegal by default). "
                    f"Use `--parse-only` to verify the AST of a program "
                    f"that uses this verb without compiling.")

            # `# group …` / `# endGroup …` anchors are preserved as
            # zero-op AST entries by the parser; the linter pairs them.
            if verb == "__groupAnchor__":
                continue
            # Typed comments (`# rationale: …`, `# warning: …`, etc.) are
            # carried as AST entries for tooling; codegen skips them.
            if verb == "__typedComment__":
                continue

            if verb == "makeError":
                # makeError NAME ERRTYPE.VARIANT [SOURCE_VALUE]
                name = args[0]
                qualified = args[1]
                if "." not in qualified:
                    raise ValueError(f"makeError requires ERRTYPE.VARIANT, got {qualified!r}")
                errtype, variant = qualified.split(".", 1)
                variants = prog.errors.get(errtype)
                if variants is None:
                    raise ValueError(f"undeclared error type: {errtype}")
                idx = None
                for i, (vname, _cause) in enumerate(variants):
                    if vname == variant:
                        idx = i + 1   # 1-based: variant 1 -> exit code 1
                        break
                if idx is None:
                    raise ValueError(f"unknown error variant: {qualified}")
                # The error value is represented at runtime as an i32 exit code
                # derived deterministically from the declared variant index.
                binds[name] = ir.Constant(I32, idx)
                continue

            if verb == "branchIfError":
                call_name, fail_label = args[0], args[1]
                call = calls[call_name]
                err_cond = call["error_cond"]
                if err_cond is None:
                    # Default convention:
                    #   - integer return  -> negative value means failure (icmp slt result, 0)
                    #   - pointer return  -> NULL means failure (icmp eq result, null)
                    result = call["result"]
                    if isinstance(result.type, ir.PointerType):
                        nullptr = ir.Constant(result.type, None)
                        err_cond = builder.icmp_unsigned("==", result, nullptr, name=f"{call_name}_isErr")
                    else:
                        zero = ir.Constant(result.type, 0)
                        err_cond = builder.icmp_signed("<", result, zero, name=f"{call_name}_isErr")
                cont = builder.function.append_basic_block(f"after_{call_name}")
                record_label_defers(fail_label, active_defers)
                builder.cbranch(err_cond, get_block(fail_label), cont)
                builder.position_at_end(cont)
                continue

            if verb == "branchIf":
                # Two valid forms:
                #   branchIf BOOL_VALUE TRUE_LABEL          (fall through on false)
                #   branchIf BOOL_VALUE TRUE_LABEL FALSE_LABEL  (legacy)
                if len(args) == 2:
                    cond_name, t_label = args[0], args[1]
                    cond_val = resolve(cond_name)
                    if cond_val.type != I1:
                        cond_val = builder.icmp_signed("!=", cond_val, ir.Constant(cond_val.type, 0))
                    cont = builder.function.append_basic_block(f"after_branchIf_{cond_name}")
                    record_label_defers(t_label, active_defers)
                    builder.cbranch(cond_val, get_block(t_label), cont)
                    builder.position_at_end(cont)
                else:
                    cond_name, t_label, f_label = args[0], args[1], args[2]
                    cond_val = resolve(cond_name)
                    if cond_val.type != I1:
                        cond_val = builder.icmp_signed("!=", cond_val, ir.Constant(cond_val.type, 0))
                    record_label_defers(t_label, active_defers)
                    record_label_defers(f_label, active_defers)
                    builder.cbranch(cond_val, get_block(t_label), get_block(f_label))
                    dead = builder.function.append_basic_block(f"after_branchIf_{cond_name}")
                    builder.position_at_end(dead)
                    active_defers = []
                continue

            if verb == "branch":
                record_label_defers(args[0], active_defers)
                builder.branch(get_block(args[0]))
                dead = builder.function.append_basic_block(f"after_branch_{args[0]}")
                builder.position_at_end(dead)
                active_defers = []
                continue

            if verb == "returnVoid":
                # `returnVoid` is the explicit "no caller-actionable value"
                # return form for operations declared `output OP Void` /
                # `output OP CVoid`. The user-op ABI still uses an i32 return
                # slot (see `_operation_output_contract` for the Void → I32
                # mapping), so codegen emits a zero sentinel — but the source
                # says exactly what it means, instead of forcing a fake
                # `returnValue zeroSentinel` line that asks readers to
                # understand the ABI quirk on their own. Rejected on
                # non-Void outputs so the verb cannot become a backdoor
                # around the result-contract checker.
                if args:
                    raise ValueError(
                        f"returnVoid: line {_ln}: takes no arguments "
                        f"(found {len(args)}). Use `returnValue NAME` for "
                        f"operations that produce a typed value."
                    )
                output_contract = _operation_output_contract(self.prog, op)
                resolved_ok = resolve_alias(self.prog, output_contract.ok_type) \
                    if output_contract.ok_type else ""
                if resolved_ok not in ("Void", "CVoid"):
                    declared = output_contract.ok_type or "<missing output>"
                    raise ValueError(
                        f"returnVoid: line {_ln}: operation `{op.name}` "
                        f"declares `output {op.name} {declared}` — use "
                        f"`returnValue NAME` for non-Void outputs. "
                        f"`returnVoid` is only legal when output is `Void`."
                    )
                emit_defers("returnVoid")
                target_type = fn.function_type.return_type
                if isinstance(target_type, ir.IntType):
                    builder.ret(ir.Constant(target_type, 0))
                else:
                    # Defensive: the Void → i32 mapping is the documented
                    # lowering; if a future ABI change made Void return a
                    # different shape, this branch keeps codegen honest by
                    # zero-initialising whatever the new shape is.
                    builder.ret(ir.Constant(target_type, None))
                dead = builder.function.append_basic_block("after_returnVoid")
                builder.position_at_end(dead)
                continue

            if verb in ("returnOk", "returnError", "returnValue"):
                emit_defers(verb)
                val = resolve(args[0])
                if val is SENTINEL:
                    raise ValueError(f"{verb}: cannot return opaque input")
                target_type = fn.function_type.return_type
                if val.type != target_type:
                    # Integer-to-integer: sext or trunc as appropriate.
                    if (isinstance(val.type, ir.IntType)
                            and isinstance(target_type, ir.IntType)):
                        if val.type.width < target_type.width:
                            val = builder.sext(val, target_type)
                        elif val.type.width > target_type.width:
                            val = builder.trunc(val, target_type)
                    # Pointer-to-pointer of different pointee types: bitcast.
                    elif (isinstance(val.type, ir.PointerType)
                            and isinstance(target_type, ir.PointerType)):
                        val = builder.bitcast(val, target_type)
                    # Float-to-float: extend/truncate.
                    elif (isinstance(val.type, (ir.FloatType, ir.DoubleType))
                            and isinstance(target_type, (ir.FloatType, ir.DoubleType))):
                        if isinstance(target_type, ir.DoubleType) and isinstance(val.type, ir.FloatType):
                            val = builder.fpext(val, target_type)
                        elif isinstance(target_type, ir.FloatType) and isinstance(val.type, ir.DoubleType):
                            val = builder.fptrunc(val, target_type)
                    # Int-to-float / float-to-int (e.g. external-module
                    # call returned an i64 stub that needs to flow into a
                    # CFloat64 return slot, or vice versa).
                    elif (isinstance(val.type, ir.IntType)
                            and isinstance(target_type, (ir.FloatType, ir.DoubleType))):
                        val = builder.sitofp(val, target_type)
                    elif (isinstance(val.type, (ir.FloatType, ir.DoubleType))
                            and isinstance(target_type, ir.IntType)):
                        val = builder.fptosi(val, target_type)
                    # Int↔pointer at return position.
                    elif (isinstance(val.type, ir.IntType)
                            and isinstance(target_type, ir.PointerType)):
                        val = builder.inttoptr(val, target_type)
                    elif (isinstance(val.type, ir.PointerType)
                            and isinstance(target_type, ir.IntType)):
                        val = builder.ptrtoint(val, target_type)
                    # Otherwise: fall through; llvmlite will complain if the
                    # mismatch is genuinely irreconcilable, which is what we
                    # want for surfacing source-level type errors.
                builder.ret(val)
                continue

            # Refined-syntax verbs that define a name visible to later
            # bind/return references. `declareFailure NAME ErrorType.Variant`
            # is the refined-syntax analogue of `makeError`: it produces a
            # named failure value. Register the name as a zero bind so
            # later `returnError NAME` resolves.
            if verb == "declareFailure" and args:
                binds[args[0]] = ir.Constant(I64, 0)
                continue
            # `recordBuilder NAME RecordType` / `recordSet BUILDER FIELD VALUE`
            # / `recordBuildFailure CALL ErrorVariant` — declarative steps
            # consumed by `recordBuild` (which we registered as a call).
            if verb in ("recordBuilder", "recordSet", "recordBuildFailure"):
                continue
            # `storage <scope> <mutability> NAME TYPE [VALUE]` inside an
            # operation body. The `local mutable` form is the only one that
            # actually mutates: promote it to a real alloca so subsequent
            # `set local NAME VALUE` lines emit real stores and later
            # references emit loads. Other scopes/mutabilities (e.g.
            # `local immutable`) stay as op-local consts.
            if verb == "storage" and len(args) >= 5:
                scope, mutability = args[0], args[1]
                name = args[2]
                typ_name = args[3]
                raw_value = _unwrap(args[4])
                if scope == "local" and mutability == "mutable":
                    llty = llvm_type_for(prog, typ_name)
                    if llty is not None:
                        # Resolve the initializer first (while the const
                        # tables don't yet contain this name), so an
                        # initializer referring to another const, var, or
                        # literal works the same as `var`.
                        if isinstance(raw_value, str):
                            try:
                                init = resolve(raw_value)
                            except ValueError:
                                init = emit_const_value(typ_name, raw_value)
                        else:
                            init = emit_const_value(typ_name, raw_value)
                        with builder.goto_entry_block():
                            slot = builder.alloca(llty, name=name)
                        if init.type != llty:
                            if (isinstance(init.type, ir.IntType)
                                    and isinstance(llty, ir.IntType)):
                                if init.type.width < llty.width:
                                    extend = (builder.zext if init.type.width == 1
                                              else builder.sext)
                                    init = extend(init, llty)
                                else:
                                    init = builder.trunc(init, llty)
                        builder.store(init, slot)
                        binds[name] = slot
                        var_types[name] = llty
                        is_var.add(name)
                        # Don't record in op.consts: future references must
                        # go through the alloca's load path, not a stale
                        # initial-value const.
                        continue
                op.consts[args[2]] = (args[3], raw_value)
                continue
            if verb == "storage" and len(args) >= 4:
                op.consts[args[2]] = (args[3], _unwrap(args[4]) if len(args) > 4 else 0)
                continue

            # Refined-syntax / experimental verbs that have no executable
            # behavior at the IR level: metadata-only annotations, header
            # extensions, and declarative attachment lines. Treat as silent
            # no-ops so an operation body that mixes them with real code
            # still compiles. (The parser already stored them on op.lines
            # for tooling.)
            if verb.startswith(("group", "memory", "runtime", "intrinsic",
                                 "dependency", "guard", "shared",
                                 "trust", "type", "record", "collection",
                                 "list", "slice", "array", "smallList",
                                 "map", "json", "retry", "literal",
                                 "domain", "operationBody",
                                 "section", "defer")):
                continue
            if verb == "read" and args and args[0] in ("sharedState", "local", "module"):
                # Refined-syntax storage read:
                #   read <scope> NAME TYPE BACKING [protectedBy GUARD …]
                # Binds NAME to the current value of BACKING. We don't yet
                # enforce the guard, but the bind makes later references
                # resolve to the BACKING const's value.
                if len(args) >= 4:
                    try:
                        binds[args[1]] = resolve(args[3])
                    except ValueError:
                        binds[args[1]] = ir.Constant(I64, 0)
                continue
            if verb in ("read", "write"):
                # Stray effect-style verbs (e.g. `read inputText` from the
                # refined-syntax `effect` shorthand) — accept as metadata.
                continue

            raise ValueError(f"codegen unhandled verb: {verb}")

        if not builder.block.is_terminated:
            # Fall-through return — emit a zero of the function's declared
            # return type. For refined-syntax operations whose body is all
            # no-ops (runtimeBinding / intrinsic / dependencyPath), this
            # gives the linker a well-typed `ret` instruction.
            emit_defers("fallthrough")
            rty = fn.function_type.return_type
            if isinstance(rty, ir.PointerType):
                builder.ret(ir.Constant(rty, None))
            elif isinstance(rty, (ir.FloatType, ir.DoubleType)):
                builder.ret(ir.Constant(rty, 0.0))
            else:
                builder.ret(ir.Constant(rty, 0))

    def _diagnostic_for_call_error(self, error: Exception, call) -> CompilerDiagnostic:
        message = str(error)
        frame = self.provenance.frame_from_call(call)
        direction = (
            "The compiler failed while lowering this call to LLVM IR. Inspect "
            "the call row, its arg rows, and the target operation or builtin "
            "signature before changing unrelated source."
        )
        if "unresolved symbol" in message:
            direction = (
                "One of this call's argument values does not resolve in the "
                "current operation. Check the `arg` rows for typos, missing "
                "const/var/bind declarations, or values that were declared "
                "inside another operation."
            )
        elif "missing" in message and "arg" in message:
            direction = (
                "The call target expects an argument that is absent at this "
                "call site. Add the missing `arg` row or rename the existing "
                "arg to match the target input."
            )
        elif "unsupported c.* target" in message:
            direction = (
                "This `c.*` call target has no libc registry signature. Add "
                "a signature or SemanticScript-facing alias in libc_registry.py, "
                "or replace the call with a supported target."
            )
        return CompilerDiagnostic(
            code="SSCG002",
            phase="codegen.call-lowering",
            message=message,
            primary=frame.span,
            semantic_stack=[frame],
            lowering_trace=[
                "SemanticScript call row -> call object",
                "call target + arg rows -> LLVM IRBuilder emission",
                "lowering stopped before native backend",
            ],
            direction=direction,
            suggested_fixes=[
                "Inspect every `arg` row attached to this call name.",
                "Confirm the call target's required inputs and supported types.",
                "Run with --diagnostics-format json if an agent should consume this mechanically.",
            ],
            agent_hint=(
                "Patch the SemanticScript source or the compiler lowering rule. "
                "Do not edit generated LLVM IR; it is an output artifact."
            ),
        )

    # ---------- run dispatch ----------
    def _emit_run(self, builder, call_name, calls, resolve, opaque_inputs, SENTINEL):
        call = calls.get(call_name, {
            "name": call_name,
            "operation": "",
            "line": 0,
            "target": "",
        })
        try:
            return self._emit_run_impl(
                builder, call_name, calls, resolve, opaque_inputs, SENTINEL)
        except CompilerDiagnosticError:
            raise
        except Exception as e:
            raise CompilerDiagnosticError(
                self._diagnostic_for_call_error(e, call)) from e

    def _emit_run_impl(self, builder, call_name, calls, resolve, opaque_inputs, SENTINEL):
        call = calls[call_name]
        source_target = call["target"]
        target = _TARGET_ALIASES.get(source_target, source_target)
        target = self.prog.operation_aliases.get(target, target)
        qualified_parts = source_target.split(".", 1)
        if (len(qualified_parts) == 2
                and qualified_parts[0] in self.prog.import_aliases
                and _exported_symbols_for(
                    self.prog,
                    self.prog.import_aliases[qualified_parts[0]],
                    "operation")
                and source_target not in self.prog.operation_aliases):
            raise ValueError(
                f"{call_name}: qualified import target `{source_target}` is "
                "not an exported operation")

        # Lower domain-typed methods (`TypeName.methodName`) to the underlying
        # primitive based on the type alias's resolution chain. This keeps the
        # source-level call advertising domain context while reusing the
        # primitive dispatch below. Enum names also dispatch through here:
        # `SaveTodosStatus.equal` resolves the enum's repr type and picks the
        # matching width's primitive (CSignedInt32 → math.equalCSignedInt32,
        # CSignedInt64 → math.equalI64), so callers compare enum values
        # without leaking the underlying integer width into source.
        if (target not in _BINOP_TO_LLVM and target not in _CMP_TO_LLVM
                and target not in _CMP_I32_TO_LLVM
                and target not in _FBINOP_TO_LLVM and target not in _FCMP_TO_LLVM
                and target not in ("console.writeLine", "console.writeIntegerLine",
                                   "console.writeFloatLine")
                and not target.startswith("c.")
                and "." in target):
            type_part, method_part = target.split(".", 1)
            enum_repr = enum_repr_type(self.prog, type_part)
            if enum_repr is not None:
                # Enum dispatch — pick the primitive for the declared repr.
                if enum_repr in ("CSignedInt64", "I64"):
                    primitive = _DOMAIN_METHOD_TO_I64_PRIMITIVE.get(method_part)
                else:
                    primitive = _DOMAIN_METHOD_TO_I32_PRIMITIVE.get(method_part)
                if primitive is not None:
                    target = primitive
                    call["target"] = primitive
                    call["domain_method"] = method_part
            else:
                underlying = resolve_alias(self.prog, type_part)
                primitive = _DOMAIN_METHOD_TO_I64_PRIMITIVE.get(method_part)
                if primitive is not None and underlying == "I64":
                    target = primitive
                    call["target"] = primitive
                    call["domain_method"] = method_part
                elif method_part in _DOMAIN_METHOD_TO_I32_PRIMITIVE and underlying in ("I32", "CSignedInt32"):
                    target = _DOMAIN_METHOD_TO_I32_PRIMITIVE[method_part]
                    call["target"] = target
                    call["domain_method"] = method_part
                elif method_part in _DOMAIN_METHOD_TO_F64_PRIMITIVE and underlying in ("F64", "CDouble"):
                    target = _DOMAIN_METHOD_TO_F64_PRIMITIVE[method_part]
                    call["target"] = target
                    call["domain_method"] = method_part

        def arg_val_named(arg_name):
            sym = call["args"].get(arg_name)
            if sym is None:
                raise ValueError(f"{call_name}: missing required arg `{arg_name}` for {target}")
            v = resolve(sym)
            if v is SENTINEL:
                raise ValueError(f"{call_name}: opaque-input symbol used as value arg `{arg_name}`")
            return v

        def operand_pair():
            """Resolve two operand arguments for a binary math call. Accepts
            any pair of names — `left`/`right`, `a`/`b`, `value`/`step`,
            `value`/`divisor`, etc. — by relying on insertion order from the
            source `arg` lines. Opaque-dependency args (e.g. an unused
            `console` passthrough) are filtered out before positional pick."""
            usable = [(k, v) for k, v in call["args"].items()
                      if v not in opaque_inputs]
            if len(usable) < 2:
                raise ValueError(
                    f"{call_name}: {target} needs 2 operand args; got {list(call['args'])}")
            a = resolve(usable[0][1])
            b = resolve(usable[1][1])
            if a is SENTINEL or b is SENTINEL:
                raise ValueError(f"{call_name}: opaque-input as operand for {target}")
            return a, b

        def operand_single():
            usable = [(k, v) for k, v in call["args"].items()
                      if v not in opaque_inputs]
            if len(usable) != 1:
                raise ValueError(
                    f"{call_name}: {target} unary domain method needs 1 operand arg; got {list(call['args'])}")
            value = resolve(usable[0][1])
            if value is SENTINEL:
                raise ValueError(f"{call_name}: opaque-input as operand for {target}")
            return value

        def coerce_i64_for_non_math_abi(v):
            if v.type == I64:
                return v
            if isinstance(v.type, ir.IntType):
                return builder.sext(v, I64) if v.type.width < 64 else builder.trunc(v, I64)
            raise ValueError(f"{call_name}: cannot coerce {v.type} to i64")

        def require_exact_type(v, expected_type, expected_name: str, context: str):
            if v.type != expected_type:
                raise ValueError(
                    f"{call_name}: {context} expects {expected_name} exactly, got {v.type}; "
                    "insert an explicit conversion operation before this math call")
            return v

        def require_i64(v, context: str):
            return require_exact_type(v, I64, "I64", context)

        def require_i32(v, context: str):
            return require_exact_type(v, I32, "CSignedInt32/I32", context)

        def require_f64(v, context: str):
            return require_exact_type(v, F64, "F64", context)

        if target.startswith(_HTML_HYDRATE_PREFIX):
            template_name = target[len(_HTML_HYDRATE_PREFIX):]
            template = self.prog.html_templates.get(template_name)
            if template is None:
                raise ValueError(
                    f"{call_name}: unknown htmlTemplate `{template_name}`")
            self._emit_html_hydrate(builder, call_name, call, template,
                                    arg_val_named)
            return

        if target == "console.writeLine":
            text = arg_val_named("text")
            self.provenance.record_external("puts", call)
            call["result"] = builder.call(self.puts, [text], name=f"{call_name}_res")
            return
        if target == "console.writeIntegerLine":
            n = coerce_i64_for_non_math_abi(arg_val_named("value"))
            fmt_ptr = self._i8p(builder, "%lld\n")
            self.provenance.record_external("printf", call)
            call["result"] = builder.call(self.printf, [fmt_ptr, n], name=f"{call_name}_res")
            return
        if target == "console.writeFloatLine":
            # Print a CFloat64 / F64 with C's `%f\n` format (six fractional
            # digits — the printf default — to match the bootstrap-emitted
            # behavior). The value arg is widened to double if the LLVM
            # type is a float; passed straight through if already a double.
            v = arg_val_named("value")
            if isinstance(v.type, ir.IntType):
                v = builder.sitofp(v, F64)
            elif isinstance(v.type, ir.FloatType):
                v = builder.fpext(v, F64)
            fmt_ptr = self._i8p(builder, "%f\n")
            self.provenance.record_external("printf", call)
            call["result"] = builder.call(
                self.printf, [fmt_ptr, v], name=f"{call_name}_res")
            return

        if target == "math.signExtendCSignedInt32ToCSignedInt64":
            usable = [(k, v) for k, v in call["args"].items()
                      if v not in opaque_inputs]
            v = resolve(usable[0][1])
            v = require_i32(v, "math.signExtendCSignedInt32ToCSignedInt64 input")
            call["result"] = builder.sext(v, I64, name=f"{call_name}_res")
            return

        if target == "math.truncateCSignedInt64ToCSignedInt32":
            usable = [(k, v) for k, v in call["args"].items()
                      if v not in opaque_inputs]
            v = resolve(usable[0][1])
            v = require_i64(v, "math.truncateCSignedInt64ToCSignedInt32 input")
            call["result"] = builder.trunc(v, I32, name=f"{call_name}_res")
            return

        if target == "math.intToFloat":
            # Convert a signed integer to double precision (sitofp).
            # Used by SemanticScript-stdlib float math to bridge integer counters
            # into float computations without linking libm.
            usable = [(k, v) for k, v in call["args"].items()
                      if v not in opaque_inputs]
            v = resolve(usable[0][1])
            v = require_i64(v, "math.intToFloat input")
            call["result"] = builder.sitofp(v, F64, name=f"{call_name}_res")
            return
        if target == "math.floatToInt":
            # Convert a double-precision value to a signed 64-bit integer
            # by rounding toward zero (fptosi). Used to implement
            # floor/ceil/trunc in pure SemanticScript.
            usable = [(k, v) for k, v in call["args"].items()
                      if v not in opaque_inputs]
            v = resolve(usable[0][1])
            v = require_f64(v, "math.floatToInt input")
            call["result"] = builder.fptosi(v, I64, name=f"{call_name}_res")
            return

        if target == "math.checkedMultiplyI64":
            # Lower to the signed-multiply-with-overflow intrinsic so that
            # callers can branchIfError on the overflow bit instead of
            # silently wrapping.
            a, b = operand_pair()
            a = require_i64(a, "math.checkedMultiplyI64 left operand")
            b = require_i64(b, "math.checkedMultiplyI64 right operand")
            agg = builder.call(self.smul_overflow_i64, [a, b],
                               name=f"{call_name}_tuple")
            product = builder.extract_value(agg, 0, name=f"{call_name}_res")
            overflow = builder.extract_value(agg, 1, name=f"{call_name}_overflow")
            call["result"] = product
            call["error_value"] = overflow
            call["error_cond"] = overflow
            return

        if target in _BINOP_TO_LLVM:
            if call.get("domain_method") == "square" and target == "math.multiplyI64":
                a = operand_single()
                b = a
            else:
                a, b = operand_pair()
            a = require_i64(a, f"{target} left operand")
            b = require_i64(b, f"{target} right operand")
            if target in ("math.divideI64", "math.moduloI64"):
                divisor_is_zero = builder.icmp_signed(
                    "==", b, ir.Constant(b.type, 0),
                    name=f"{call_name}_divisorIsZero")
                self._emit_runtime_check(
                    builder, divisor_is_zero, call,
                    f"zero divisor before {target}")
            op = _BINOP_TO_LLVM[target]
            call["result"] = getattr(builder, op)(a, b, name=f"{call_name}_res")
            return

        if target in _FBINOP_TO_LLVM:
            a, b = operand_pair()
            a = require_f64(a, f"{target} left operand")
            b = require_f64(b, f"{target} right operand")
            op = _FBINOP_TO_LLVM[target]
            call["result"] = getattr(builder, op)(a, b, name=f"{call_name}_res")
            return

        if target in _FCMP_TO_LLVM:
            a, b = operand_pair()
            a = require_f64(a, f"{target} left operand")
            b = require_f64(b, f"{target} right operand")
            call["result"] = builder.fcmp_ordered(_FCMP_TO_LLVM[target], a, b,
                                                  name=f"{call_name}_res")
            return

        if target in _CMP_TO_LLVM:
            a, b = operand_pair()
            a = require_i64(a, f"{target} left operand")
            b = require_i64(b, f"{target} right operand")
            call["result"] = builder.icmp_signed(_CMP_TO_LLVM[target], a, b, name=f"{call_name}_res")
            return

        if target in _CMP_I32_TO_LLVM:
            a, b = operand_pair()
            a = require_i32(a, f"{target} left operand")
            b = require_i32(b, f"{target} right operand")
            call["result"] = builder.icmp_signed(_CMP_I32_TO_LLVM[target], a, b, name=f"{call_name}_res")
            return

        # Pointer-arithmetic primitives. `pointer.loadByte` reads a single
        # byte at (buffer + offset). `pointer.storeByte` writes one. These
        # are the minimum primitives an SemanticScript program needs to observe buffer
        # contents without relying on a separate codecs library.
        if target == "pointer.loadByte":
            buffer_arg = arg_val_named("buffer") if "buffer" in call["args"] else None
            if buffer_arg is None:
                # Fall back to positional order: first non-opaque arg = buffer.
                usable = [(k, v) for k, v in call["args"].items()
                          if v not in opaque_inputs]
                buffer_arg = resolve(usable[0][1])
                offset_arg = resolve(usable[1][1])
            else:
                offset_arg = arg_val_named("offset")
            if buffer_arg.type != I8P:
                buffer_arg = builder.bitcast(buffer_arg, I8P)
            offset_arg = self._coerce_for_libc(builder, offset_arg, "CSize")
            self._emit_null_pointer_check(
                builder, buffer_arg, call,
                "null buffer before pointer.loadByte")
            ptr = builder.gep(buffer_arg, [offset_arg], inbounds=True,
                              name=f"{call_name}_addr")
            loaded_byte = builder.load(ptr, name=f"{call_name}_byte")
            call["result"] = builder.sext(loaded_byte, I32, name=f"{call_name}_res")
            return

        if target == "pointer.storeByte":
            usable = [(k, v) for k, v in call["args"].items()
                      if v not in opaque_inputs]
            buffer_arg = resolve(usable[0][1])
            offset_arg = resolve(usable[1][1])
            value_arg = resolve(usable[2][1])
            if buffer_arg.type != I8P:
                buffer_arg = builder.bitcast(buffer_arg, I8P)
            offset_arg = self._coerce_for_libc(builder, offset_arg, "CSize")
            value_arg = self._coerce_for_libc(builder, value_arg, "I8")
            self._emit_null_pointer_check(
                builder, buffer_arg, call,
                "null buffer before pointer.storeByte")
            ptr = builder.gep(buffer_arg, [offset_arg], inbounds=True,
                              name=f"{call_name}_addr")
            builder.store(value_arg, ptr)
            call["result"] = ir.Constant(I32, 0)
            return

        # `pointer.offset base offset` returns base + offset as a pointer
        # without dereferencing. Used to walk through a byte buffer.
        if target == "pointer.offset":
            usable = [(k, v) for k, v in call["args"].items()
                      if v not in opaque_inputs]
            base = resolve(usable[0][1])
            offset = resolve(usable[1][1])
            if base.type != I8P:
                base = builder.bitcast(base, I8P)
            offset = self._coerce_for_libc(builder, offset, "CSize")
            call["result"] = builder.gep(base, [offset], inbounds=True,
                                          name=f"{call_name}_addr")
            return

        # `pointer.difference left right` returns (left - right) as a
        # CSignedInt64. Both operands must point into the same allocation
        # for the result to be meaningful — this is a §10 contract the
        # SemanticScript-level type system does not yet enforce.
        if target == "pointer.difference":
            usable = [(k, v) for k, v in call["args"].items()
                      if v not in opaque_inputs]
            left = resolve(usable[0][1])
            right = resolve(usable[1][1])
            if left.type != I8P:
                left = builder.bitcast(left, I8P)
            if right.type != I8P:
                right = builder.bitcast(right, I8P)
            left_int = builder.ptrtoint(left, I64, name=f"{call_name}_lhs")
            right_int = builder.ptrtoint(right, I64, name=f"{call_name}_rhs")
            call["result"] = builder.sub(left_int, right_int,
                                          name=f"{call_name}_diff")
            return

        # `pointer.isNull ptr` returns 1 if ptr is NULL, 0 otherwise. The
        # default branchIfError convention `result < 0` cannot detect NULL
        # pointers returned by c.fopen / c.getenv / c.malloc — this
        # primitive gives a typed Bool that branchIf can consume.
        if target == "pointer.isNull":
            usable = [(k, v) for k, v in call["args"].items()
                      if v not in opaque_inputs]
            ptr = resolve(usable[0][1])
            if ptr.type != I8P:
                ptr = builder.bitcast(ptr, I8P)
            null_ptr = ir.Constant(I8P, None)
            call["result"] = builder.icmp_unsigned("==", ptr, null_ptr,
                                                    name=f"{call_name}_isNull")
            return

        # C macro-only math classifiers from <math.h>. These are defined as
        # macros in the C spec, not externs — calling them through a libc
        # extern would link-fail on most platforms. Lower directly to LLVM
        # FP comparisons / bit operations so the SemanticScript surface stays portable.
        if target in _MATH_CLASSIFIERS:
            usable = [(k, v) for k, v in call["args"].items()
                      if v not in opaque_inputs]
            if len(usable) != 1:
                raise ValueError(
                    f"{call_name}: {target} needs exactly one operand; got {len(usable)}")
            x = resolve(usable[0][1])
            x = self._coerce_for_libc(builder, x, "CDouble")
            classifier = target.split(".", 1)[1]
            call["result"] = self._emit_math_classifier(builder, classifier, x,
                                                        name=f"{call_name}_res")
            return

        # C standard library call. Targets of the form `c.<name>` look up the
        # signature in libc_registry, declare the LLVM extern on demand, and
        # emit a direct call. The args are matched by source-order: each
        # `arg call_name <argname> <valuename>` line contributes one
        # positional value, in declaration order, optionally followed by
        # variadic tail args for printf-style functions.
        if target.startswith("c."):
            semantic_name = target[2:]
            # Translate SemanticScript-facing camelCase to the C symbol, then look up
            # the signature under either spelling.
            c_symbol = libc_registry.resolve_c_symbol(semantic_name)
            sig = libc_registry.ALL_FUNCTIONS.get(semantic_name) \
                  or libc_registry.ALL_FUNCTIONS.get(c_symbol)
            if sig is None:
                raise ValueError(f"unsupported c.* target: {target}")
            ret_typ, param_typs, var_args = sig
            fn = self._libc_func(semantic_name)
            self.provenance.record_external(c_symbol, call)
            cname = semantic_name  # preserve downstream variable usage
            arg_values = []
            arg_items = list(call["args"].items())
            # Build the fixed prefix in source order, coercing each arg to
            # the declared LLVM type.
            for i, ptyp in enumerate(param_typs):
                if i >= len(arg_items):
                    raise ValueError(
                        f"{call_name}: c.{cname} expects {len(param_typs)} fixed args; got {len(arg_items)}")
                _aname, asym = arg_items[i]
                v = resolve(asym)
                if v is SENTINEL:
                    # opaque-dep placeholder — treat as null pointer for FILE*
                    # / void* parameter shapes.
                    if ptyp in ("CFilePtr", "CVoidPtr", "CString", "CTmPtr",
                                "CJmpBuf"):
                        v = ir.Constant(I8P, None)
                    else:
                        raise ValueError(
                            f"{call_name}: opaque-input used for non-pointer arg of c.{cname}")
                v = self._coerce_for_libc(builder, v, ptyp)
                arg_values.append(v)
            # Variadic tail: any extra args, with default coercions.
            if var_args:
                for j in range(len(param_typs), len(arg_items)):
                    _aname, asym = arg_items[j]
                    v = resolve(asym)
                    if v is SENTINEL:
                        v = ir.Constant(I8P, None)
                    # C variadic ABI: floats are promoted to double, smaller
                    # ints to int. llvmlite emits the right calling-convention
                    # code as long as we promote the SSA type explicitly.
                    v = self._promote_for_vararg(builder, v)
                    arg_values.append(v)
            res = builder.call(fn, arg_values, name=f"{call_name}_res")
            if isinstance(llvm_type_for_or_void(self.prog, ret_typ), ir.VoidType):
                # Void return — bind nothing. Set result to a constant zero so
                # any downstream `bindOk` is well-typed without surprising
                # callers (matches the puts/printf convention).
                call["result"] = ir.Constant(I32, 0)
            else:
                call["result"] = res
            return

        def gui_i32_arg(arg_name):
            value = arg_val_named(arg_name)
            if isinstance(value.type, ir.IntType):
                if value.type.width < 32:
                    return builder.sext(value, I32)
                if value.type.width > 32:
                    return builder.trunc(value, I32)
                return value
            raise ValueError(f"{call_name}: {target} arg `{arg_name}` must be an integer")

        def gui_ptr_arg(arg_name):
            value = arg_val_named(arg_name)
            if value.type == I8P:
                return value
            if isinstance(value.type, ir.PointerType):
                return builder.bitcast(value, I8P)
            if isinstance(value.type, ir.IntType):
                return builder.inttoptr(value, I8P)
            raise ValueError(f"{call_name}: {target} arg `{arg_name}` must be pointer-shaped")

        def gui_handler_arg(arg_name):
            handler_name = call["args"].get(arg_name)
            if handler_name not in self._user_ops:
                raise ValueError(
                    f"{call_name}: {target} arg `{arg_name}` must name a declared operation")
            op_info = self._user_ops[handler_name]
            handler_fnty = ir.FunctionType(I32, [I8P, I8P])
            handler_ptr_ty = handler_fnty.as_pointer()
            handler_ptr = op_info["fn"]
            if len(op_info["params"]) != 2:
                raise ValueError(
                    f"{call_name}: GUI handler `{handler_name}` must declare "
                    "input HANDLER session GuiSession and input HANDLER event GuiEvent")
            if op_info["return_type"] != I32:
                raise ValueError(
                    f"{call_name}: GUI handler `{handler_name}` must return CSignedInt32")
            if handler_ptr.type != handler_ptr_ty:
                handler_ptr = builder.bitcast(handler_ptr, handler_ptr_ty)
            return handler_ptr

        if target == "gui.applicationCreate":
            fn = self._runtime_func("ss_gui_application_create", I8P, [I8P])
            self.provenance.record_external("ss_gui_application_create", call)
            call["result"] = builder.call(
                fn, [gui_ptr_arg("title")], name=f"{call_name}_res")
            return

        if target == "gui.windowCreate":
            fn = self._runtime_func(
                "ss_gui_window_create", I8P, [I8P, I32, I32, I32, I32])
            self.provenance.record_external("ss_gui_window_create", call)
            call["result"] = builder.call(
                fn,
                [
                    gui_ptr_arg("title"),
                    gui_i32_arg("width"),
                    gui_i32_arg("height"),
                    gui_i32_arg("layout"),
                    gui_i32_arg("resizable"),
                ],
                name=f"{call_name}_res")
            return

        if target == "gui.textLabelCreate":
            fn = self._runtime_func("ss_gui_text_label_create", I8P, [I8P])
            self.provenance.record_external("ss_gui_text_label_create", call)
            call["result"] = builder.call(
                fn, [gui_ptr_arg("text")], name=f"{call_name}_res")
            return

        if target == "gui.textBoxCreate":
            fn = self._runtime_func("ss_gui_text_box_create", I8P, [I8P, I32])
            self.provenance.record_external("ss_gui_text_box_create", call)
            call["result"] = builder.call(
                fn,
                [gui_ptr_arg("placeholder"), gui_i32_arg("maxLength")],
                name=f"{call_name}_res")
            return

        if target == "gui.buttonCreate":
            fn = self._runtime_func("ss_gui_button_create", I8P, [I8P, I32])
            self.provenance.record_external("ss_gui_button_create", call)
            call["result"] = builder.call(
                fn,
                [gui_ptr_arg("text"), gui_i32_arg("isDefault")],
                name=f"{call_name}_res")
            return

        if target == "gui.listBoxCreate":
            fn = self._runtime_func("ss_gui_list_box_create", I8P, [I32])
            self.provenance.record_external("ss_gui_list_box_create", call)
            call["result"] = builder.call(
                fn, [gui_i32_arg("selectionMode")], name=f"{call_name}_res")
            return

        if target == "gui.windowAddControl":
            fn = self._runtime_func("ss_gui_window_add_control", I32, [I8P, I8P])
            self.provenance.record_external("ss_gui_window_add_control", call)
            call["result"] = builder.call(
                fn,
                [gui_ptr_arg("window"), gui_ptr_arg("control")],
                name=f"{call_name}_res")
            return

        if target == "gui.controlOnEvent":
            handler_fnty = ir.FunctionType(I32, [I8P, I8P])
            handler_ptr_ty = handler_fnty.as_pointer()
            fn = self._runtime_func(
                "ss_gui_control_on_event", I32, [I8P, I32, handler_ptr_ty])
            self.provenance.record_external("ss_gui_control_on_event", call)
            call["result"] = builder.call(
                fn,
                [
                    gui_ptr_arg("control"),
                    gui_i32_arg("eventKind"),
                    gui_handler_arg("handler"),
                ],
                name=f"{call_name}_res")
            return

        if target == "gui.applicationSetMainWindow":
            fn = self._runtime_func(
                "ss_gui_application_set_main_window", I32, [I8P, I8P])
            self.provenance.record_external("ss_gui_application_set_main_window", call)
            call["result"] = builder.call(
                fn,
                [gui_ptr_arg("application"), gui_ptr_arg("window")],
                name=f"{call_name}_res")
            return

        if target == "gui.applicationRun":
            fn = self._runtime_func("ss_gui_application_run_builder", I32, [I8P])
            self.provenance.record_external("ss_gui_application_run_builder", call)
            call["result"] = builder.call(
                fn, [gui_ptr_arg("application")], name=f"{call_name}_res")
            return

        if target == "gui.textBoxText":
            fn = self._runtime_func(
                "ss_gui_text_box_text_by_handle", I8P, [I8P, I8P])
            self.provenance.record_external("ss_gui_text_box_text_by_handle", call)
            call["result"] = builder.call(
                fn,
                [gui_ptr_arg("session"), gui_ptr_arg("textBox")],
                name=f"{call_name}_res")
            return

        if target == "gui.textBoxSetText":
            fn = self._runtime_func(
                "ss_gui_text_box_set_text_by_handle", I32, [I8P, I8P, I8P])
            self.provenance.record_external("ss_gui_text_box_set_text_by_handle", call)
            call["result"] = builder.call(
                fn,
                [
                    gui_ptr_arg("session"),
                    gui_ptr_arg("textBox"),
                    gui_ptr_arg("text"),
                ],
                name=f"{call_name}_res")
            return

        if target == "gui.listBoxSelectedIndex":
            fn = self._runtime_func(
                "ss_gui_list_box_selected_index_by_handle", I32, [I8P, I8P])
            self.provenance.record_external("ss_gui_list_box_selected_index_by_handle", call)
            call["result"] = builder.call(
                fn,
                [gui_ptr_arg("session"), gui_ptr_arg("listBox")],
                name=f"{call_name}_res")
            return

        if target == "gui.listBoxAppendItem":
            fn = self._runtime_func(
                "ss_gui_list_box_append_item_by_handle", I32, [I8P, I8P, I8P])
            self.provenance.record_external("ss_gui_list_box_append_item_by_handle", call)
            call["result"] = builder.call(
                fn,
                [
                    gui_ptr_arg("session"),
                    gui_ptr_arg("listBox"),
                    gui_ptr_arg("text"),
                ],
                name=f"{call_name}_res")
            return

        if target == "gui.listBoxClear":
            fn = self._runtime_func(
                "ss_gui_list_box_clear_by_handle", I32, [I8P, I8P])
            self.provenance.record_external("ss_gui_list_box_clear_by_handle", call)
            call["result"] = builder.call(
                fn,
                [gui_ptr_arg("session"), gui_ptr_arg("listBox")],
                name=f"{call_name}_res")
            return

        if target == "gui.textLabelSetText":
            fn = self._runtime_func(
                "ss_gui_text_label_set_text_by_handle", I32, [I8P, I8P, I8P])
            self.provenance.record_external("ss_gui_text_label_set_text_by_handle", call)
            call["result"] = builder.call(
                fn,
                [
                    gui_ptr_arg("session"),
                    gui_ptr_arg("textLabel"),
                    gui_ptr_arg("text"),
                ],
                name=f"{call_name}_res")
            return

        if target == "gui.windowClose":
            fn = self._runtime_func(
                "ss_gui_window_close_by_handle", I32, [I8P, I8P])
            self.provenance.record_external("ss_gui_window_close_by_handle", call)
            call["result"] = builder.call(
                fn,
                [gui_ptr_arg("session"), gui_ptr_arg("window")],
                name=f"{call_name}_res")
            return

        if target.startswith("gui."):
            raise ValueError(
                f"unsupported native gui call target: {target!r}; "
                "add a standard.gui function/runtime lowering before using it")

        # User-defined operation invocation. The target is the operation name.
        # Match the call's `arg` lines to the operation's declared parameter
        # list, dropping any args that pass an opaque-dep value. The function
        # returns i32 with the puts/printf convention: negative means error,
        # which the existing branchIfError default condition already handles.
        if target in self._user_ops:
            self.provenance.record_call_edge(call.get("operation", ""), target, call)
            op_info = self._user_ops[target]
            arg_values = []
            for pname, _llty, _ptype in op_info["params"]:
                sym = call["args"].get(pname)
                if sym is None:
                    # Fall back to positional matching when name-based
                    # lookup misses: refined-syntax rename work may rename
                    # an operation's `input` lines without updating every
                    # call site's `arg` label in lockstep. If the call has
                    # the same number of args as the op has params, line
                    # them up positionally so the program still links with
                    # the right values rather than silently passing zero.
                    call_arg_values = list(call["args"].values())
                    param_index = [p[0] for p in op_info["params"]].index(pname)
                    if len(call_arg_values) == len(op_info["params"]):
                        sym = call_arg_values[param_index]
                    else:
                        raise ValueError(
                            f"{call_name}: missing arg `{pname}` for operation `{target}` "
                            f"(call passed {len(call_arg_values)} args, op declares {len(op_info['params'])})")
                try:
                    v = resolve(sym)
                except ValueError:
                    raise ValueError(
                        f"{call_name}: unresolved arg value `{sym}` for "
                        f"operation `{target}` parameter `{pname}`")
                if v is SENTINEL:
                    raise ValueError(
                        f"{call_name}: opaque-input symbol used as data arg `{pname}` for `{target}`")
                # narrowing/widening to match the declared parameter type
                if isinstance(v.type, ir.IntType) and isinstance(_llty, ir.IntType):
                    if v.type.width < _llty.width:
                        v = builder.sext(v, _llty)
                    elif v.type.width > _llty.width:
                        v = builder.trunc(v, _llty)
                # Pointer/integer coercion for refined-syntax mixed-typed
                # call sites where the resolved symbol is i64/i32 but the
                # declared param is i8* (or vice versa). Use ptrtoint /
                # inttoptr / bitcast so the call type-checks.
                elif isinstance(_llty, ir.PointerType) and isinstance(v.type, ir.IntType):
                    v = builder.inttoptr(v, _llty)
                elif isinstance(_llty, ir.IntType) and isinstance(v.type, ir.PointerType):
                    v = builder.ptrtoint(v, _llty)
                elif isinstance(_llty, ir.PointerType) and isinstance(v.type, ir.PointerType) and v.type != _llty:
                    v = builder.bitcast(v, _llty)
                arg_values.append(v)
            result = builder.call(op_info["fn"], arg_values,
                                  name=f"{call_name}_res")
            call["result"] = result
            # User-defined operations may return either a libc-style
            # negative error code (when they propagate a primitive's error
            # via returnError) OR a positive makeError variant index. The
            # default branchIfError convention `result < 0` catches only the
            # first case; recording `result != 0` here catches both, which
            # is what spec §12 (failure-flow precision) requires for any
            # operation whose output contract is `Result A B`.
            #
            # The error-cond predicate depends on the return type:
            #   integer return: != 0
            #   pointer return: != null (NULL pointer is the failure marker)
            #   float return:   != 0.0 (matches the i32 convention)
            rt = result.type
            if isinstance(rt, ir.IntType):
                call["error_cond"] = builder.icmp_signed(
                    "!=", result, ir.Constant(rt, 0),
                    name=f"{call_name}_isErr")
            elif isinstance(rt, ir.PointerType):
                # NULL pointer is the failure marker: error_cond is
                # `result == null`. A user op that `returnOk handlePtr`
                # produces a non-null pointer (success); a `returnError
                # statusCode` path inttoptr's the small status into a
                # pointer that happens to be non-null, BUT user ops
                # that genuinely want the Result-error path to fire on
                # the caller side should `returnOk nullHandle` from the
                # failure branch (or set the error code via a separate
                # signal). For Result<Pointer, _> ops where any error
                # encodes as a null return, this check Just Works.
                call["error_cond"] = builder.icmp_unsigned(
                    "==", result, ir.Constant(rt, None),
                    name=f"{call_name}_isErr")
            elif isinstance(rt, (ir.FloatType, ir.DoubleType)):
                call["error_cond"] = builder.fcmp_ordered(
                    "!=", result, ir.Constant(rt, 0.0),
                    name=f"{call_name}_isErr")
            else:
                # Unknown return shape: leave error_cond unset; callers that
                # branchIfError on this will get a clear codegen error.
                pass
            return

        # ---- json.encode primitive lowerings ----
        # Integer / Bool / Float primitives have a direct JSON
        # representation (decimal digits, "true"/"false", scientific
        # notation) — implementable without a full codec runtime by
        # formatting into a per-call-site stack buffer via libc snprintf.
        # Record-typed `json.encode.TypeName` still falls through to the
        # external-module fallback because that requires walking record
        # fields and emitting a structural encoder, which is the real
        # codec runtime work tracked under SYNTAX.md's Partial row.
        if target in ("json.encode.I64", "json.encode.CSignedInt64",
                      "json.encode.CSignedInt32", "json.encode.CUnsignedInt32",
                      "json.encode.CSignedInt16", "json.encode.CUnsignedInt16",
                      "json.encode.CSignedByte", "json.encode.CUnsignedByte",
                      "json.encode.DurationMilliseconds",
                      "json.encode.MonotonicMilliseconds",
                      "json.encode.UtcMilliseconds"):
            n = coerce_i64_for_non_math_abi(arg_val_named("value"))
            buf_size = 32
            with builder.goto_entry_block():
                buf = builder.alloca(
                    ir.ArrayType(I8, buf_size),
                    name=f"{call_name}_jsonbuf")
            buf_ptr = builder.gep(
                buf, [ir.Constant(I32, 0), ir.Constant(I32, 0)], inbounds=True)
            snprintf = self._libc_func("snprintf")
            fmt = self._i8p(builder, "%lld")
            builder.call(snprintf,
                         [buf_ptr, ir.Constant(I64, buf_size), fmt, n])
            call["result"] = buf_ptr
            return
        if target == "json.encode.Bool":
            v = arg_val_named("value")
            if isinstance(v.type, ir.IntType) and v.type.width > 1:
                v = builder.icmp_signed("!=", v, ir.Constant(v.type, 0))
            true_str = self._i8p(builder, "true")
            false_str = self._i8p(builder, "false")
            call["result"] = builder.select(
                v, true_str, false_str, name=f"{call_name}_bool")
            return
        if target in ("json.encode.F64", "json.encode.CFloat64",
                      "json.encode.CFloat32"):
            v = arg_val_named("value")
            if isinstance(v.type, ir.IntType):
                v = builder.sitofp(v, F64)
            elif isinstance(v.type, ir.FloatType):
                v = builder.fpext(v, F64)
            buf_size = 32
            with builder.goto_entry_block():
                buf = builder.alloca(
                    ir.ArrayType(I8, buf_size),
                    name=f"{call_name}_jsonbuf")
            buf_ptr = builder.gep(
                buf, [ir.Constant(I32, 0), ir.Constant(I32, 0)], inbounds=True)
            snprintf = self._libc_func("snprintf")
            fmt = self._i8p(builder, "%g")
            builder.call(snprintf,
                         [buf_ptr, ir.Constant(I64, buf_size), fmt, v])
            call["result"] = buf_ptr
            return
        if target in ("json.decode.I64", "json.decode.CSignedInt64",
                      "json.decode.CSignedInt32", "json.decode.CUnsignedInt32",
                      "json.decode.CSignedInt16", "json.decode.CUnsignedInt16",
                      "json.decode.CSignedByte", "json.decode.CUnsignedByte",
                      "json.decode.DurationMilliseconds",
                      "json.decode.MonotonicMilliseconds",
                      "json.decode.UtcMilliseconds"):
            # Decode a JSON integer literal via libc atoll. The input is a
            # null-terminated byte string holding the decimal text; atoll
            # returns 0 on malformed input (matching JSON-leniency for the
            # primitive path — strict parsing belongs to the codec runtime).
            v = arg_val_named("value")
            if isinstance(v.type, ir.IntType):
                v = builder.inttoptr(v, I8P)
            atoll = self._libc_func("atoll")
            call["result"] = builder.call(
                atoll, [v], name=f"{call_name}_decoded")
            return
        if target == "json.decode.Bool":
            # Compare the input string against the literal "true" via
            # libc strcmp; result is 1 when strings are equal (i.e.
            # the JSON token was "true"), 0 otherwise.
            v = arg_val_named("value")
            if isinstance(v.type, ir.IntType):
                v = builder.inttoptr(v, I8P)
            strcmp = self._libc_func("strcmp")
            true_str = self._i8p(builder, "true")
            cmp = builder.call(strcmp, [v, true_str], name=f"{call_name}_strcmp")
            is_true = builder.icmp_signed(
                "==", cmp, ir.Constant(I32, 0), name=f"{call_name}_isTrue")
            call["result"] = builder.zext(
                is_true, I64, name=f"{call_name}_decoded")
            return
        if target in ("json.decode.F64", "json.decode.CFloat64",
                      "json.decode.CFloat32"):
            # Use libc atof to parse the JSON number; returns double 0.0
            # on malformed input.
            v = arg_val_named("value")
            if isinstance(v.type, ir.IntType):
                v = builder.inttoptr(v, I8P)
            atof = self._libc_func("atof")
            call["result"] = builder.call(
                atof, [v], name=f"{call_name}_decoded")
            return
        if target in ("json.encode.String",
                      "json.encode.CNullTerminatedByteString"):
            # JSON-encoding a string requires quoting + escape handling
            # (\\, \", \n, \r, \t, \uXXXX for control bytes). For now, we
            # produce the string surrounded by ASCII quotes — correct for
            # ASCII payloads that contain none of the special characters.
            # Full escape handling is deferred to the real codec runtime
            # tracked under SYNTAX.md's Partial row.
            v = arg_val_named("value")
            if isinstance(v.type, ir.IntType):
                v = builder.inttoptr(v, I8P)
            buf_size = 256
            with builder.goto_entry_block():
                buf = builder.alloca(
                    ir.ArrayType(I8, buf_size),
                    name=f"{call_name}_jsonbuf")
            buf_ptr = builder.gep(
                buf, [ir.Constant(I32, 0), ir.Constant(I32, 0)], inbounds=True)
            snprintf = self._libc_func("snprintf")
            fmt = self._i8p(builder, "\"%s\"")
            builder.call(snprintf,
                         [buf_ptr, ir.Constant(I64, buf_size), fmt, v])
            call["result"] = buf_ptr
            return

        # ------------------------------------------------------------
        # standard.json runtime dispatch — opaque JsonBuilder handle
        # plus the field-at-a-time encoder and the named-field finder
        # API exposed by sem_json_runtime.h. Each call lowers to a
        # direct ss_json_* invocation; the linker only pulls in
        # sem_json_runtime.c when any of these targets is actually
        # referenced (see _native_json_link_inputs).
        # ------------------------------------------------------------

        if target == "json.createBuilder":
            capacity = arg_val_named("capacity")
            if isinstance(capacity.type, ir.IntType) and capacity.type.width != 64:
                capacity = (builder.sext(capacity, I64)
                            if capacity.type.width < 64
                            else builder.trunc(capacity, I64))
            create_fn = self._runtime_func("ss_json_builder_create", I8P, [I64])
            self.provenance.record_external("ss_json_builder_create", call)
            call["result"] = builder.call(
                create_fn, [capacity], name=f"{call_name}_builder")
            return

        if target == "json.destroyBuilder":
            builder_arg = arg_val_named("builder")
            if isinstance(builder_arg.type, ir.IntType):
                builder_arg = builder.inttoptr(builder_arg, I8P)
            destroy_fn = self._runtime_func("ss_json_builder_destroy", VOID, [I8P])
            self.provenance.record_external("ss_json_builder_destroy", call)
            builder.call(destroy_fn, [builder_arg])
            # Void return — give the surrounding bind machinery a
            # deterministic zero so anything that accidentally binds
            # this call's result still has a valid SSA value.
            call["result"] = ir.Constant(I32, 0)
            return

        # Helper for any builder mutator that takes the builder handle
        # only (open/close containers).
        def _json_builder_handle_only(symbol):
            builder_arg = arg_val_named("builder")
            if isinstance(builder_arg.type, ir.IntType):
                builder_arg = builder.inttoptr(builder_arg, I8P)
            fn = self._runtime_func(symbol, I32, [I8P])
            self.provenance.record_external(symbol, call)
            call["result"] = builder.call(
                fn, [builder_arg], name=f"{call_name}_status")

        if target == "json.objectOpen":
            _json_builder_handle_only("ss_json_builder_object_open")
            return
        if target == "json.objectClose":
            _json_builder_handle_only("ss_json_builder_object_close")
            return
        if target == "json.arrayOpen":
            _json_builder_handle_only("ss_json_builder_array_open")
            return
        if target == "json.arrayClose":
            _json_builder_handle_only("ss_json_builder_array_close")
            return

        # Field writers — builder + fieldName + value of varying type.
        if target in (
            "json.fieldInt64",
            "json.fieldDouble",
            "json.fieldBool",
            "json.fieldString",
        ):
            builder_arg = arg_val_named("builder")
            field_name = arg_val_named("fieldName")
            value = arg_val_named("value")
            if isinstance(builder_arg.type, ir.IntType):
                builder_arg = builder.inttoptr(builder_arg, I8P)
            if isinstance(field_name.type, ir.IntType):
                field_name = builder.inttoptr(field_name, I8P)
            if target == "json.fieldInt64":
                if isinstance(value.type, ir.IntType) and value.type.width != 64:
                    value = (builder.sext(value, I64)
                             if value.type.width < 64
                             else builder.trunc(value, I64))
                symbol = "ss_json_builder_field_int64"
                param_tys = [I8P, I8P, I64]
            elif target == "json.fieldDouble":
                if isinstance(value.type, ir.IntType):
                    value = builder.sitofp(value, F64)
                symbol = "ss_json_builder_field_double"
                param_tys = [I8P, I8P, F64]
            elif target == "json.fieldBool":
                if isinstance(value.type, ir.IntType) and value.type.width != 32:
                    value = (builder.sext(value, I32)
                             if value.type.width < 32
                             else builder.trunc(value, I32))
                symbol = "ss_json_builder_field_bool"
                param_tys = [I8P, I8P, I32]
            else:  # json.fieldString
                if isinstance(value.type, ir.IntType):
                    value = builder.inttoptr(value, I8P)
                symbol = "ss_json_builder_field_string"
                param_tys = [I8P, I8P, I8P]
            fn = self._runtime_func(symbol, I32, param_tys)
            self.provenance.record_external(symbol, call)
            call["result"] = builder.call(
                fn, [builder_arg, field_name, value],
                name=f"{call_name}_status")
            return

        if target == "json.fieldNull":
            builder_arg = arg_val_named("builder")
            field_name = arg_val_named("fieldName")
            if isinstance(builder_arg.type, ir.IntType):
                builder_arg = builder.inttoptr(builder_arg, I8P)
            if isinstance(field_name.type, ir.IntType):
                field_name = builder.inttoptr(field_name, I8P)
            fn = self._runtime_func(
                "ss_json_builder_field_null", I32, [I8P, I8P])
            self.provenance.record_external("ss_json_builder_field_null", call)
            call["result"] = builder.call(
                fn, [builder_arg, field_name],
                name=f"{call_name}_status")
            return

        # Array-element writers — builder + value (no field name).
        if target in (
            "json.elementInt64",
            "json.elementDouble",
            "json.elementBool",
            "json.elementString",
        ):
            builder_arg = arg_val_named("builder")
            value = arg_val_named("value")
            if isinstance(builder_arg.type, ir.IntType):
                builder_arg = builder.inttoptr(builder_arg, I8P)
            if target == "json.elementInt64":
                if isinstance(value.type, ir.IntType) and value.type.width != 64:
                    value = (builder.sext(value, I64)
                             if value.type.width < 64
                             else builder.trunc(value, I64))
                symbol = "ss_json_builder_element_int64"
                param_tys = [I8P, I64]
            elif target == "json.elementDouble":
                if isinstance(value.type, ir.IntType):
                    value = builder.sitofp(value, F64)
                symbol = "ss_json_builder_element_double"
                param_tys = [I8P, F64]
            elif target == "json.elementBool":
                if isinstance(value.type, ir.IntType) and value.type.width != 32:
                    value = (builder.sext(value, I32)
                             if value.type.width < 32
                             else builder.trunc(value, I32))
                symbol = "ss_json_builder_element_bool"
                param_tys = [I8P, I32]
            else:  # json.elementString
                if isinstance(value.type, ir.IntType):
                    value = builder.inttoptr(value, I8P)
                symbol = "ss_json_builder_element_string"
                param_tys = [I8P, I8P]
            fn = self._runtime_func(symbol, I32, param_tys)
            self.provenance.record_external(symbol, call)
            call["result"] = builder.call(
                fn, [builder_arg, value], name=f"{call_name}_status")
            return

        if target == "json.elementNull":
            _json_builder_handle_only("ss_json_builder_element_null")
            return

        if target == "json.finishBuilder":
            builder_arg = arg_val_named("builder")
            if isinstance(builder_arg.type, ir.IntType):
                builder_arg = builder.inttoptr(builder_arg, I8P)
            fn = self._runtime_func("ss_json_builder_finish", I8P, [I8P])
            self.provenance.record_external("ss_json_builder_finish", call)
            call["result"] = builder.call(
                fn, [builder_arg], name=f"{call_name}_body")
            return

        if target == "json.builderLength":
            builder_arg = arg_val_named("builder")
            if isinstance(builder_arg.type, ir.IntType):
                builder_arg = builder.inttoptr(builder_arg, I8P)
            fn = self._runtime_func("ss_json_builder_length", I64, [I8P])
            self.provenance.record_external("ss_json_builder_length", call)
            call["result"] = builder.call(
                fn, [builder_arg], name=f"{call_name}_length")
            return

        # Finder side — read a single named field from a flat JSON
        # object passed as a null-terminated string. Each returns a
        # value-by-value sentinel for absent fields so a `bind` on the
        # result still has well-defined semantics; callers that need to
        # distinguish absent-vs-default should use json.hasField first.
        if target == "json.hasField":
            json_text = arg_val_named("jsonText")
            field_name = arg_val_named("fieldName")
            if isinstance(json_text.type, ir.IntType):
                json_text = builder.inttoptr(json_text, I8P)
            if isinstance(field_name.type, ir.IntType):
                field_name = builder.inttoptr(field_name, I8P)
            fn = self._runtime_func("ss_json_has_field", I32, [I8P, I8P])
            self.provenance.record_external("ss_json_has_field", call)
            call["result"] = builder.call(
                fn, [json_text, field_name], name=f"{call_name}_present")
            return

        if target == "json.findString":
            json_text = arg_val_named("jsonText")
            field_name = arg_val_named("fieldName")
            scratch = arg_val_named("scratch")
            scratch_capacity = arg_val_named("scratchCapacity")
            if isinstance(json_text.type, ir.IntType):
                json_text = builder.inttoptr(json_text, I8P)
            if isinstance(field_name.type, ir.IntType):
                field_name = builder.inttoptr(field_name, I8P)
            if isinstance(scratch.type, ir.IntType):
                scratch = builder.inttoptr(scratch, I8P)
            if (isinstance(scratch_capacity.type, ir.IntType)
                    and scratch_capacity.type.width != 64):
                scratch_capacity = (builder.sext(scratch_capacity, I64)
                                    if scratch_capacity.type.width < 64
                                    else builder.trunc(scratch_capacity, I64))
            fn = self._runtime_func(
                "ss_json_find_string", I8P, [I8P, I8P, I8P, I64])
            self.provenance.record_external("ss_json_find_string", call)
            call["result"] = builder.call(
                fn, [json_text, field_name, scratch, scratch_capacity],
                name=f"{call_name}_text")
            return

        if target == "json.findInt64":
            json_text = arg_val_named("jsonText")
            field_name = arg_val_named("fieldName")
            missing_default = arg_val_named("missingDefault")
            if isinstance(json_text.type, ir.IntType):
                json_text = builder.inttoptr(json_text, I8P)
            if isinstance(field_name.type, ir.IntType):
                field_name = builder.inttoptr(field_name, I8P)
            if (isinstance(missing_default.type, ir.IntType)
                    and missing_default.type.width != 64):
                missing_default = (builder.sext(missing_default, I64)
                                   if missing_default.type.width < 64
                                   else builder.trunc(missing_default, I64))
            fn = self._runtime_func(
                "ss_json_find_int64", I64, [I8P, I8P, I64])
            self.provenance.record_external("ss_json_find_int64", call)
            call["result"] = builder.call(
                fn, [json_text, field_name, missing_default],
                name=f"{call_name}_int")
            return

        if target == "json.findDouble":
            json_text = arg_val_named("jsonText")
            field_name = arg_val_named("fieldName")
            missing_default = arg_val_named("missingDefault")
            if isinstance(json_text.type, ir.IntType):
                json_text = builder.inttoptr(json_text, I8P)
            if isinstance(field_name.type, ir.IntType):
                field_name = builder.inttoptr(field_name, I8P)
            if isinstance(missing_default.type, ir.IntType):
                missing_default = builder.sitofp(missing_default, F64)
            fn = self._runtime_func(
                "ss_json_find_double", F64, [I8P, I8P, F64])
            self.provenance.record_external("ss_json_find_double", call)
            call["result"] = builder.call(
                fn, [json_text, field_name, missing_default],
                name=f"{call_name}_double")
            return

        if target == "json.findBool":
            json_text = arg_val_named("jsonText")
            field_name = arg_val_named("fieldName")
            missing_default = arg_val_named("missingDefault")
            if isinstance(json_text.type, ir.IntType):
                json_text = builder.inttoptr(json_text, I8P)
            if isinstance(field_name.type, ir.IntType):
                field_name = builder.inttoptr(field_name, I8P)
            if (isinstance(missing_default.type, ir.IntType)
                    and missing_default.type.width != 32):
                missing_default = (builder.sext(missing_default, I32)
                                   if missing_default.type.width < 32
                                   else builder.trunc(missing_default, I32))
            fn = self._runtime_func(
                "ss_json_find_bool", I32, [I8P, I8P, I32])
            self.provenance.record_external("ss_json_find_bool", call)
            call["result"] = builder.call(
                fn, [json_text, field_name, missing_default],
                name=f"{call_name}_bool")
            return

        # ------------------------------------------------------------
        # standard.bcrypt runtime dispatch — wraps the vendored
        # crypt_blowfish 1.3 hasher plus the platform CSPRNG and a
        # base64url encoder. All four entry points are documented in
        # SemanticScript/runtime/native_bcrypt/sem_bcrypt_runtime.h.
        # The linker only pulls in third_party/bcrypt/*.c when at
        # least one bcrypt.* call site is present in the program (see
        # _native_bcrypt_link_inputs).
        # ------------------------------------------------------------

        if target == "bcrypt.hashPassword":
            plaintext = arg_val_named("plaintext")
            cost = arg_val_named("cost")
            out_buffer = arg_val_named("outBuffer")
            out_capacity = arg_val_named("outCapacity")
            if isinstance(plaintext.type, ir.IntType):
                plaintext = builder.inttoptr(plaintext, I8P)
            if isinstance(out_buffer.type, ir.IntType):
                out_buffer = builder.inttoptr(out_buffer, I8P)
            if isinstance(cost.type, ir.IntType) and cost.type.width != 32:
                cost = (builder.trunc(cost, I32) if cost.type.width > 32
                        else builder.sext(cost, I32))
            if isinstance(out_capacity.type, ir.IntType) and out_capacity.type.width != 32:
                out_capacity = (builder.trunc(out_capacity, I32)
                                if out_capacity.type.width > 32
                                else builder.sext(out_capacity, I32))
            fn = self._runtime_func(
                "ss_bcrypt_hash", I32, [I8P, I32, I8P, I32])
            self.provenance.record_external("ss_bcrypt_hash", call)
            call["result"] = builder.call(
                fn, [plaintext, cost, out_buffer, out_capacity],
                name=f"{call_name}_status")
            return

        if target == "bcrypt.verifyPassword":
            plaintext = arg_val_named("plaintext")
            expected_hash = arg_val_named("expectedHash")
            if isinstance(plaintext.type, ir.IntType):
                plaintext = builder.inttoptr(plaintext, I8P)
            if isinstance(expected_hash.type, ir.IntType):
                expected_hash = builder.inttoptr(expected_hash, I8P)
            fn = self._runtime_func(
                "ss_bcrypt_verify", I32, [I8P, I8P])
            self.provenance.record_external("ss_bcrypt_verify", call)
            call["result"] = builder.call(
                fn, [plaintext, expected_hash],
                name=f"{call_name}_matchOrErr")
            return

        if target == "bcrypt.randomBytes":
            out_buffer = arg_val_named("outBuffer")
            byte_count = arg_val_named("byteCount")
            if isinstance(out_buffer.type, ir.IntType):
                out_buffer = builder.inttoptr(out_buffer, I8P)
            if isinstance(byte_count.type, ir.IntType) and byte_count.type.width != 32:
                byte_count = (builder.trunc(byte_count, I32)
                              if byte_count.type.width > 32
                              else builder.sext(byte_count, I32))
            fn = self._runtime_func(
                "ss_random_bytes", I32, [I8P, I32])
            self.provenance.record_external("ss_random_bytes", call)
            call["result"] = builder.call(
                fn, [out_buffer, byte_count],
                name=f"{call_name}_status")
            return

        if target == "bcrypt.base64UrlEncode":
            input_buffer = arg_val_named("inputBuffer")
            input_count = arg_val_named("inputCount")
            output_buffer = arg_val_named("outputBuffer")
            output_capacity = arg_val_named("outputCapacity")
            output_length_out = arg_val_named("outputLengthOut")
            if isinstance(input_buffer.type, ir.IntType):
                input_buffer = builder.inttoptr(input_buffer, I8P)
            if isinstance(output_buffer.type, ir.IntType):
                output_buffer = builder.inttoptr(output_buffer, I8P)
            if isinstance(output_length_out.type, ir.IntType):
                output_length_out = builder.inttoptr(
                    output_length_out, I32.as_pointer())
            if isinstance(input_count.type, ir.IntType) and input_count.type.width != 32:
                input_count = (builder.trunc(input_count, I32)
                               if input_count.type.width > 32
                               else builder.sext(input_count, I32))
            if isinstance(output_capacity.type, ir.IntType) and output_capacity.type.width != 32:
                output_capacity = (builder.trunc(output_capacity, I32)
                                   if output_capacity.type.width > 32
                                   else builder.sext(output_capacity, I32))
            fn = self._runtime_func(
                "ss_base64url_encode", I32,
                [I8P, I32, I8P, I32, I32.as_pointer()])
            self.provenance.record_external("ss_base64url_encode", call)
            call["result"] = builder.call(
                fn, [input_buffer, input_count, output_buffer,
                     output_capacity, output_length_out],
                name=f"{call_name}_status")
            return

        # ===== Native HTTP target dispatch =====
        # SOURCE-OF-TRUTH: this block is one of three places that
        # enumerate the native HTTP call targets the routed webserver
        # codegen lowers. Adding or removing a target here REQUIRES
        # updating the other two sites in lockstep:
        #
        #   1. semsc.py (here) — the lowering dispatch.
        #   2. SemanticScript/linter/semlint.py — the
        #      NULLABLE_HTTP_REQUEST_READS / HTTP_RESPONSE_BODY_WRITERS
        #      constants that drive SS3603 (unguardedHttpInput) and the
        #      `_collect_transitive_response_body_writers` walk.
        #   3. SYNTAX.md — the two `http.requestMethod, …` and
        #      `http.responseText, …` umbrella rows.
        #
        # The drift between these three sources is asserted by the
        # `TestHttpTargetSourceOfTruth` test class in
        # SemanticScript/linter/test_semlint.py — if you add a target
        # without updating all three sites, that test fails with a
        # specific drift diff. Do not "fix" the test by hiding the
        # drift; fix the drift.
        if target == "http.responseText":
            response = arg_val_named("response")
            status = arg_val_named("status")
            body = arg_val_named("body")
            content_type = ir.Constant(I8P, None)
            if "contentType" in call["args"]:
                content_type = arg_val_named("contentType")
            if isinstance(status.type, ir.IntType) and status.type.width != 32:
                status = builder.trunc(status, I32) if status.type.width > 32 else builder.sext(status, I32)
            if isinstance(response.type, ir.IntType):
                response = builder.inttoptr(response, I8P)
            if isinstance(body.type, ir.IntType):
                body = builder.inttoptr(body, I8P)
            if isinstance(content_type.type, ir.IntType):
                content_type = builder.inttoptr(content_type, I8P)
            response_text = self._runtime_func(
                "ss_http_response_text",
                I32,
                [I8P, I32, I8P, I8P]
            )
            self.provenance.record_external("ss_http_response_text", call)
            call["result"] = builder.call(
                response_text,
                [response, status, body, content_type],
                name=f"{call_name}_res"
            )
            return

        if target == "http.responseBytes":
            response = arg_val_named("response")
            status = arg_val_named("status")
            body = arg_val_named("body")
            body_length = arg_val_named("bodyLength")
            content_type = ir.Constant(I8P, None)
            if "contentType" in call["args"]:
                content_type = arg_val_named("contentType")
            if isinstance(status.type, ir.IntType) and status.type.width != 32:
                status = builder.trunc(status, I32) if status.type.width > 32 else builder.sext(status, I32)
            if isinstance(response.type, ir.IntType):
                response = builder.inttoptr(response, I8P)
            if isinstance(body.type, ir.IntType):
                body = builder.inttoptr(body, I8P)
            if isinstance(body_length.type, ir.IntType) and body_length.type.width != 64:
                body_length = builder.zext(body_length, I64) if body_length.type.width < 64 else builder.trunc(body_length, I64)
            if isinstance(content_type.type, ir.IntType):
                content_type = builder.inttoptr(content_type, I8P)
            response_bytes = self._runtime_func(
                "ss_http_response_bytes",
                I32,
                [I8P, I32, I8P, I64, I8P]
            )
            self.provenance.record_external("ss_http_response_bytes", call)
            call["result"] = builder.call(
                response_bytes,
                [response, status, body, body_length, content_type],
                name=f"{call_name}_res"
            )
            return

        if target == "http.responseSseEvent":
            response = arg_val_named("response")
            status = arg_val_named("status")
            event_name = arg_val_named("event")
            event_data = arg_val_named("data")
            if isinstance(status.type, ir.IntType) and status.type.width != 32:
                status = builder.trunc(status, I32) if status.type.width > 32 else builder.sext(status, I32)
            if isinstance(response.type, ir.IntType):
                response = builder.inttoptr(response, I8P)
            if isinstance(event_name.type, ir.IntType):
                event_name = builder.inttoptr(event_name, I8P)
            if isinstance(event_data.type, ir.IntType):
                event_data = builder.inttoptr(event_data, I8P)
            response_sse_event = self._runtime_func(
                "ss_http_response_sse_event",
                I32,
                [I8P, I32, I8P, I8P]
            )
            self.provenance.record_external("ss_http_response_sse_event", call)
            call["result"] = builder.call(
                response_sse_event,
                [response, status, event_name, event_data],
                name=f"{call_name}_res"
            )
            return

        if target == "http.responseHeader":
            response = arg_val_named("response")
            name = arg_val_named("name")
            value = arg_val_named("value")
            if isinstance(response.type, ir.IntType):
                response = builder.inttoptr(response, I8P)
            if isinstance(name.type, ir.IntType):
                name = builder.inttoptr(name, I8P)
            if isinstance(value.type, ir.IntType):
                value = builder.inttoptr(value, I8P)
            response_header = self._runtime_func(
                "ss_http_response_header",
                I32,
                [I8P, I8P, I8P]
            )
            self.provenance.record_external("ss_http_response_header", call)
            call["result"] = builder.call(
                response_header,
                [response, name, value],
                name=f"{call_name}_res"
            )
            return

        if target == "http.requestMethod":
            request = arg_val_named("request")
            if isinstance(request.type, ir.IntType):
                request = builder.inttoptr(request, I8P)
            request_method = self._runtime_func("ss_http_request_method", I8P, [I8P])
            self.provenance.record_external("ss_http_request_method", call)
            call["result"] = builder.call(request_method, [request], name=f"{call_name}_res")
            return

        if target == "http.requestPath":
            request = arg_val_named("request")
            if isinstance(request.type, ir.IntType):
                request = builder.inttoptr(request, I8P)
            request_path = self._runtime_func("ss_http_request_path", I8P, [I8P])
            self.provenance.record_external("ss_http_request_path", call)
            call["result"] = builder.call(request_path, [request], name=f"{call_name}_res")
            return

        if target == "http.requestHeader":
            request = arg_val_named("request")
            name = arg_val_named("name")
            if isinstance(request.type, ir.IntType):
                request = builder.inttoptr(request, I8P)
            if isinstance(name.type, ir.IntType):
                name = builder.inttoptr(name, I8P)
            request_header = self._runtime_func("ss_http_request_header", I8P, [I8P, I8P])
            self.provenance.record_external("ss_http_request_header", call)
            call["result"] = builder.call(request_header, [request, name], name=f"{call_name}_res")
            return

        if target == "http.requestQueryParam":
            request = arg_val_named("request")
            name = arg_val_named("name")
            if isinstance(request.type, ir.IntType):
                request = builder.inttoptr(request, I8P)
            if isinstance(name.type, ir.IntType):
                name = builder.inttoptr(name, I8P)
            request_query_param = self._runtime_func("ss_http_request_query_param", I8P, [I8P, I8P])
            self.provenance.record_external("ss_http_request_query_param", call)
            call["result"] = builder.call(request_query_param, [request, name], name=f"{call_name}_res")
            return

        if target == "http.requestPathParam":
            # Captures a `:name` segment from the route pattern at dispatch
            # time. Returns a null pointer when the named param isn't
            # declared on the matched route (or when the matched route is
            # literal-only), so callers MUST guard with pointer.isNull
            # before passing the value to a response writer — same SS3603
            # contract as the other nullable http.request* readers.
            request = arg_val_named("request")
            name = arg_val_named("name")
            if isinstance(request.type, ir.IntType):
                request = builder.inttoptr(request, I8P)
            if isinstance(name.type, ir.IntType):
                name = builder.inttoptr(name, I8P)
            request_path_param = self._runtime_func(
                "ss_http_request_path_param", I8P, [I8P, I8P])
            self.provenance.record_external("ss_http_request_path_param", call)
            call["result"] = builder.call(
                request_path_param, [request, name], name=f"{call_name}_res")
            return

        if target == "http.requestCookie":
            # Reads a single named cookie value from the request's
            # Cookie header. NULL when the header is absent OR the
            # cookie isn't present OR the value would overflow the
            # 256-byte scratch. Nullable per the SS3603 contract.
            request = arg_val_named("request")
            cookie_name = arg_val_named("cookieName")
            if isinstance(request.type, ir.IntType):
                request = builder.inttoptr(request, I8P)
            if isinstance(cookie_name.type, ir.IntType):
                cookie_name = builder.inttoptr(cookie_name, I8P)
            fn = self._runtime_func(
                "ss_http_request_cookie", I8P, [I8P, I8P])
            self.provenance.record_external("ss_http_request_cookie", call)
            call["result"] = builder.call(
                fn, [request, cookie_name], name=f"{call_name}_res")
            return

        if target == "http.responseFile":
            # Serves a file from inside `rootDirectory`. Refuses path
            # traversal and absolute paths at the runtime; the caller
            # still owns choosing a root directory that contains only
            # public assets.
            response = arg_val_named("response")
            status = arg_val_named("status")
            root_directory = arg_val_named("rootDirectory")
            requested_path = arg_val_named("requestedPath")
            if isinstance(response.type, ir.IntType):
                response = builder.inttoptr(response, I8P)
            if isinstance(status.type, ir.IntType) and status.type.width != 32:
                status = (builder.trunc(status, I32) if status.type.width > 32
                          else builder.sext(status, I32))
            if isinstance(root_directory.type, ir.IntType):
                root_directory = builder.inttoptr(root_directory, I8P)
            if isinstance(requested_path.type, ir.IntType):
                requested_path = builder.inttoptr(requested_path, I8P)
            fn = self._runtime_func(
                "ss_http_response_file", I32, [I8P, I32, I8P, I8P])
            self.provenance.record_external("ss_http_response_file", call)
            call["result"] = builder.call(
                fn, [response, status, root_directory, requested_path],
                name=f"{call_name}_status")
            return

        if target == "http.nowMillis":
            fn = self._runtime_func("ss_http_now_millis", I64, [])
            self.provenance.record_external("ss_http_now_millis", call)
            call["result"] = builder.call(fn, [], name=f"{call_name}_millis")
            return

        if target == "http.ensureDirectory":
            directory_path = arg_val_named("directoryPath")
            if isinstance(directory_path.type, ir.IntType):
                directory_path = builder.inttoptr(directory_path, I8P)
            fn = self._runtime_func(
                "ss_http_filesystem_ensure_directory", I32, [I8P])
            self.provenance.record_external(
                "ss_http_filesystem_ensure_directory", call)
            call["result"] = builder.call(
                fn, [directory_path], name=f"{call_name}_status")
            return

        if target == "http.requestBodyText":
            request = arg_val_named("request")
            if isinstance(request.type, ir.IntType):
                request = builder.inttoptr(request, I8P)
            request_body = self._runtime_func("ss_http_request_body_text", I8P, [I8P])
            self.provenance.record_external("ss_http_request_body_text", call)
            call["result"] = builder.call(request_body, [request], name=f"{call_name}_res")
            return

        if target == "http.requestBodyBytes":
            request = arg_val_named("request")
            if isinstance(request.type, ir.IntType):
                request = builder.inttoptr(request, I8P)
            request_body = self._runtime_func("ss_http_request_body_bytes", I8P, [I8P])
            self.provenance.record_external("ss_http_request_body_bytes", call)
            call["result"] = builder.call(request_body, [request], name=f"{call_name}_res")
            return

        if target == "http.requestBodyLength":
            request = arg_val_named("request")
            if isinstance(request.type, ir.IntType):
                request = builder.inttoptr(request, I8P)
            request_body_length = self._runtime_func("ss_http_request_body_length", I64, [I8P])
            self.provenance.record_external("ss_http_request_body_length", call)
            call["result"] = builder.call(request_body_length, [request], name=f"{call_name}_res")
            return

        if target in {
            "http.multipartPartText",
            "http.multipartPartBytes",
            "http.multipartPartFilename",
            "http.multipartPartContentType",
        }:
            request = arg_val_named("request")
            name = arg_val_named("name")
            runtime_name = {
                "http.multipartPartText": "ss_http_multipart_part_text",
                "http.multipartPartBytes": "ss_http_multipart_part_bytes",
                "http.multipartPartFilename": "ss_http_multipart_part_filename",
                "http.multipartPartContentType": "ss_http_multipart_part_content_type",
            }[target]
            if isinstance(request.type, ir.IntType):
                request = builder.inttoptr(request, I8P)
            if isinstance(name.type, ir.IntType):
                name = builder.inttoptr(name, I8P)
            multipart_reader = self._runtime_func(runtime_name, I8P, [I8P, I8P])
            self.provenance.record_external(runtime_name, call)
            call["result"] = builder.call(multipart_reader, [request, name], name=f"{call_name}_res")
            return

        if target == "http.multipartPartLength":
            request = arg_val_named("request")
            name = arg_val_named("name")
            if isinstance(request.type, ir.IntType):
                request = builder.inttoptr(request, I8P)
            if isinstance(name.type, ir.IntType):
                name = builder.inttoptr(name, I8P)
            multipart_length = self._runtime_func("ss_http_multipart_part_length", I64, [I8P, I8P])
            self.provenance.record_external("ss_http_multipart_part_length", call)
            call["result"] = builder.call(multipart_length, [request, name], name=f"{call_name}_res")
            return

        if target.startswith("http."):
            raise ValueError(
                f"unsupported native HTTP call target: {target!r}; "
                "add an explicit compiler lowering before using it in a webServer executable")

        # ------------------------------------------------------------
        # standard.sqlite dispatch — mirrors the http.* block above.
        # Every entry forwards to an ss_sqlite_* function defined in
        # SemanticScript/runtime/native_sqlite/sem_sqlite_runtime.h. The
        # Result-shaped calls populate call["result"], call["error_value"],
        # and call["error_cond"] so bindOk / bindError / branchIfError fall
        # through unchanged; the plain-value calls only set call["result"].
        # The integer status convention is shared with the C ABI:
        # SS_SQLITE_OK == 0, errors are 1..9, step results are 100/101.
        # See third_party/sqlite/README.md for the vendored amalgamation
        # and SemanticScript/runtime/native_sqlite/README.md for the
        # adapter that owns these symbols.
        # ------------------------------------------------------------

        def _sqlite_simple_status_error_cond(status_value):
            """Build the i1 error condition for a Result-returning sqlite.*
            call that does NOT use the SS_SQLITE_STEP_* range. Anything
            other than SS_SQLITE_OK (0) is an error."""
            return builder.icmp_signed(
                "!=", status_value, ir.Constant(I32, 0),
                name=f"{call_name}_isError")

        if target == "sqlite.openDatabase":
            path = arg_val_named("path")
            mode = arg_val_named("mode")
            if isinstance(path.type, ir.IntType):
                path = builder.inttoptr(path, I8P)
            if isinstance(mode.type, ir.IntType) and mode.type.width != 32:
                mode = (builder.trunc(mode, I32) if mode.type.width > 32
                        else builder.sext(mode, I32))
            # Entry-block alloca so a later `defer ... sqlite.closeDatabase`
            # can re-load the handle from a slot that dominates every
            # cleanup site (failure labels, returnOk fall-throughs, etc.).
            # Pre-init the slot to NULL: a defer that fires before the
            # open succeeded then sees a sentinel rather than garbage.
            with builder.goto_entry_block():
                db_slot = builder.alloca(
                    I8P, name=f"{call_name}_databaseSlot")
                builder.store(ir.Constant(I8P, None), db_slot)
            open_fn = self._runtime_func(
                "ss_sqlite_database_open", I32, [I8P, I32, I8P.as_pointer()])
            self.provenance.record_external("ss_sqlite_database_open", call)
            status = builder.call(
                open_fn, [path, mode, db_slot], name=f"{call_name}_status")
            handle = builder.load(db_slot, name=f"{call_name}_database")
            call["result"] = handle
            call["error_value"] = status
            call["error_cond"] = _sqlite_simple_status_error_cond(status)
            # Stash the slot so the bind handler can route it to
            # bind_slots, where emit_defers will find it.
            call["handle_slot"] = db_slot
            return

        if target == "sqlite.closeDatabase":
            database = arg_val_named("database")
            if isinstance(database.type, ir.IntType):
                database = builder.inttoptr(database, I8P)
            close_fn = self._runtime_func(
                "ss_sqlite_database_close", I32, [I8P])
            self.provenance.record_external("ss_sqlite_database_close", call)
            status = builder.call(
                close_fn, [database], name=f"{call_name}_status")
            call["result"] = ir.Constant(I32, 0)
            call["error_value"] = status
            call["error_cond"] = _sqlite_simple_status_error_cond(status)
            return

        if target == "sqlite.errorMessage":
            database = arg_val_named("database")
            if isinstance(database.type, ir.IntType):
                database = builder.inttoptr(database, I8P)
            errmsg_fn = self._runtime_func(
                "ss_sqlite_database_errmsg", I8P, [I8P])
            self.provenance.record_external("ss_sqlite_database_errmsg", call)
            call["result"] = builder.call(
                errmsg_fn, [database], name=f"{call_name}_message")
            return

        if target == "sqlite.lastInsertRowId":
            database = arg_val_named("database")
            if isinstance(database.type, ir.IntType):
                database = builder.inttoptr(database, I8P)
            last_rowid_fn = self._runtime_func(
                "ss_sqlite_database_last_insert_rowid", I64, [I8P])
            self.provenance.record_external(
                "ss_sqlite_database_last_insert_rowid", call)
            call["result"] = builder.call(
                last_rowid_fn, [database], name=f"{call_name}_rowid")
            return

        if target == "sqlite.changedRowCount":
            database = arg_val_named("database")
            if isinstance(database.type, ir.IntType):
                database = builder.inttoptr(database, I8P)
            changes_fn = self._runtime_func(
                "ss_sqlite_database_changes", I32, [I8P])
            self.provenance.record_external(
                "ss_sqlite_database_changes", call)
            call["result"] = builder.call(
                changes_fn, [database], name=f"{call_name}_changes")
            return

        if target == "sqlite.exec":
            database = arg_val_named("database")
            sql = arg_val_named("sql")
            if isinstance(database.type, ir.IntType):
                database = builder.inttoptr(database, I8P)
            if isinstance(sql.type, ir.IntType):
                sql = builder.inttoptr(sql, I8P)
            exec_fn = self._runtime_func(
                "ss_sqlite_exec", I32, [I8P, I8P])
            self.provenance.record_external("ss_sqlite_exec", call)
            status = builder.call(
                exec_fn, [database, sql], name=f"{call_name}_status")
            call["result"] = ir.Constant(I32, 0)
            call["error_value"] = status
            call["error_cond"] = _sqlite_simple_status_error_cond(status)
            return

        if target == "sqlite.prepareStatement":
            database = arg_val_named("database")
            sql = arg_val_named("sql")
            if isinstance(database.type, ir.IntType):
                database = builder.inttoptr(database, I8P)
            if isinstance(sql.type, ir.IntType):
                sql = builder.inttoptr(sql, I8P)
            # Entry-block alloca for the same reason openDatabase uses
            # one — a later `defer ... sqlite.finalizeStatement` must be
            # able to re-load the handle from a slot that dominates the
            # defer's basic block. Pre-init to NULL so a defer that fires
            # before prepare succeeded passes a NULL handle through to
            # the adapter (which treats NULL as a config error).
            with builder.goto_entry_block():
                stmt_slot = builder.alloca(
                    I8P, name=f"{call_name}_statementSlot")
                builder.store(ir.Constant(I8P, None), stmt_slot)
            prepare_fn = self._runtime_func(
                "ss_sqlite_statement_prepare", I32,
                [I8P, I8P, I8P.as_pointer()])
            self.provenance.record_external(
                "ss_sqlite_statement_prepare", call)
            status = builder.call(
                prepare_fn, [database, sql, stmt_slot],
                name=f"{call_name}_status")
            handle = builder.load(stmt_slot, name=f"{call_name}_statement")
            call["result"] = handle
            call["error_value"] = status
            call["error_cond"] = _sqlite_simple_status_error_cond(status)
            call["handle_slot"] = stmt_slot
            return

        if target == "sqlite.finalizeStatement":
            statement = arg_val_named("statement")
            if isinstance(statement.type, ir.IntType):
                statement = builder.inttoptr(statement, I8P)
            finalize_fn = self._runtime_func(
                "ss_sqlite_statement_finalize", I32, [I8P])
            self.provenance.record_external(
                "ss_sqlite_statement_finalize", call)
            status = builder.call(
                finalize_fn, [statement], name=f"{call_name}_status")
            call["result"] = ir.Constant(I32, 0)
            call["error_value"] = status
            call["error_cond"] = _sqlite_simple_status_error_cond(status)
            return

        if target == "sqlite.resetStatement":
            statement = arg_val_named("statement")
            if isinstance(statement.type, ir.IntType):
                statement = builder.inttoptr(statement, I8P)
            reset_fn = self._runtime_func(
                "ss_sqlite_statement_reset", I32, [I8P])
            self.provenance.record_external(
                "ss_sqlite_statement_reset", call)
            status = builder.call(
                reset_fn, [statement], name=f"{call_name}_status")
            call["result"] = ir.Constant(I32, 0)
            call["error_value"] = status
            call["error_cond"] = _sqlite_simple_status_error_cond(status)
            return

        if target == "sqlite.stepStatement":
            statement = arg_val_named("statement")
            if isinstance(statement.type, ir.IntType):
                statement = builder.inttoptr(statement, I8P)
            step_fn = self._runtime_func(
                "ss_sqlite_statement_step", I32, [I8P])
            self.provenance.record_external(
                "ss_sqlite_statement_step", call)
            status = builder.call(
                step_fn, [statement], name=f"{call_name}_status")
            # stepStatement is the only sqlite.* call whose success leg
            # carries a value the user binds: SqliteStepResult ∈
            # {SS_SQLITE_STEP_ROW=100, SS_SQLITE_STEP_DONE=101}. Anything
            # below 100 is a SS_SQLITE_ERR_* status.
            step_row_value = ir.Constant(I32, 100)
            is_error = builder.icmp_signed(
                "<", status, step_row_value, name=f"{call_name}_isError")
            call["result"] = status
            call["error_value"] = status
            call["error_cond"] = is_error
            return

        if target in (
            "sqlite.bindInt64",
            "sqlite.bindDouble",
            "sqlite.bindText",
            "sqlite.bindBlob",
            "sqlite.bindNull",
        ):
            statement = arg_val_named("statement")
            parameter_index = arg_val_named("parameterIndex")
            if isinstance(statement.type, ir.IntType):
                statement = builder.inttoptr(statement, I8P)
            if (isinstance(parameter_index.type, ir.IntType)
                    and parameter_index.type.width != 32):
                parameter_index = (
                    builder.trunc(parameter_index, I32)
                    if parameter_index.type.width > 32
                    else builder.sext(parameter_index, I32))
            if target == "sqlite.bindNull":
                bind_fn = self._runtime_func(
                    "ss_sqlite_statement_bind_null", I32, [I8P, I32])
                self.provenance.record_external(
                    "ss_sqlite_statement_bind_null", call)
                status = builder.call(
                    bind_fn, [statement, parameter_index],
                    name=f"{call_name}_status")
            elif target == "sqlite.bindInt64":
                value = arg_val_named("value")
                if isinstance(value.type, ir.IntType) and value.type.width != 64:
                    value = (
                        builder.sext(value, I64)
                        if value.type.width < 64
                        else builder.trunc(value, I64))
                bind_fn = self._runtime_func(
                    "ss_sqlite_statement_bind_int64", I32, [I8P, I32, I64])
                self.provenance.record_external(
                    "ss_sqlite_statement_bind_int64", call)
                status = builder.call(
                    bind_fn, [statement, parameter_index, value],
                    name=f"{call_name}_status")
            elif target == "sqlite.bindDouble":
                value = arg_val_named("value")
                bind_fn = self._runtime_func(
                    "ss_sqlite_statement_bind_double", I32, [I8P, I32, F64])
                self.provenance.record_external(
                    "ss_sqlite_statement_bind_double", call)
                status = builder.call(
                    bind_fn, [statement, parameter_index, value],
                    name=f"{call_name}_status")
            elif target == "sqlite.bindText":
                value = arg_val_named("value")
                if isinstance(value.type, ir.IntType):
                    value = builder.inttoptr(value, I8P)
                bind_fn = self._runtime_func(
                    "ss_sqlite_statement_bind_text", I32, [I8P, I32, I8P])
                self.provenance.record_external(
                    "ss_sqlite_statement_bind_text", call)
                status = builder.call(
                    bind_fn, [statement, parameter_index, value],
                    name=f"{call_name}_status")
            else:  # sqlite.bindBlob
                value = arg_val_named("value")
                value_length = arg_val_named("valueLength")
                if isinstance(value.type, ir.IntType):
                    value = builder.inttoptr(value, I8P)
                if (isinstance(value_length.type, ir.IntType)
                        and value_length.type.width != 64):
                    value_length = (
                        builder.sext(value_length, I64)
                        if value_length.type.width < 64
                        else builder.trunc(value_length, I64))
                bind_fn = self._runtime_func(
                    "ss_sqlite_statement_bind_blob", I32,
                    [I8P, I32, I8P, I64])
                self.provenance.record_external(
                    "ss_sqlite_statement_bind_blob", call)
                status = builder.call(
                    bind_fn,
                    [statement, parameter_index, value, value_length],
                    name=f"{call_name}_status")
            call["result"] = ir.Constant(I32, 0)
            call["error_value"] = status
            call["error_cond"] = _sqlite_simple_status_error_cond(status)
            return

        if target in (
            "sqlite.columnCount",
            "sqlite.columnType",
            "sqlite.columnName",
            "sqlite.columnInt64",
            "sqlite.columnDouble",
            "sqlite.columnText",
            "sqlite.columnBlob",
            "sqlite.columnByteCount",
        ):
            statement = arg_val_named("statement")
            if isinstance(statement.type, ir.IntType):
                statement = builder.inttoptr(statement, I8P)
            if target == "sqlite.columnCount":
                fn = self._runtime_func(
                    "ss_sqlite_statement_column_count", I32, [I8P])
                self.provenance.record_external(
                    "ss_sqlite_statement_column_count", call)
                call["result"] = builder.call(
                    fn, [statement], name=f"{call_name}_count")
                return
            column_index = arg_val_named("columnIndex")
            if (isinstance(column_index.type, ir.IntType)
                    and column_index.type.width != 32):
                column_index = (
                    builder.trunc(column_index, I32)
                    if column_index.type.width > 32
                    else builder.sext(column_index, I32))
            if target == "sqlite.columnType":
                fn = self._runtime_func(
                    "ss_sqlite_statement_column_type", I32, [I8P, I32])
                self.provenance.record_external(
                    "ss_sqlite_statement_column_type", call)
                call["result"] = builder.call(
                    fn, [statement, column_index], name=f"{call_name}_type")
            elif target == "sqlite.columnName":
                fn = self._runtime_func(
                    "ss_sqlite_statement_column_name", I8P, [I8P, I32])
                self.provenance.record_external(
                    "ss_sqlite_statement_column_name", call)
                call["result"] = builder.call(
                    fn, [statement, column_index], name=f"{call_name}_name")
            elif target == "sqlite.columnInt64":
                fn = self._runtime_func(
                    "ss_sqlite_statement_column_int64", I64, [I8P, I32])
                self.provenance.record_external(
                    "ss_sqlite_statement_column_int64", call)
                call["result"] = builder.call(
                    fn, [statement, column_index], name=f"{call_name}_int")
            elif target == "sqlite.columnDouble":
                fn = self._runtime_func(
                    "ss_sqlite_statement_column_double", F64, [I8P, I32])
                self.provenance.record_external(
                    "ss_sqlite_statement_column_double", call)
                call["result"] = builder.call(
                    fn, [statement, column_index],
                    name=f"{call_name}_double")
            elif target == "sqlite.columnText":
                fn = self._runtime_func(
                    "ss_sqlite_statement_column_text", I8P, [I8P, I32])
                self.provenance.record_external(
                    "ss_sqlite_statement_column_text", call)
                call["result"] = builder.call(
                    fn, [statement, column_index], name=f"{call_name}_text")
            elif target == "sqlite.columnBlob":
                fn = self._runtime_func(
                    "ss_sqlite_statement_column_blob", I8P, [I8P, I32])
                self.provenance.record_external(
                    "ss_sqlite_statement_column_blob", call)
                call["result"] = builder.call(
                    fn, [statement, column_index], name=f"{call_name}_blob")
            else:  # sqlite.columnByteCount
                fn = self._runtime_func(
                    "ss_sqlite_statement_column_bytes", I64, [I8P, I32])
                self.provenance.record_external(
                    "ss_sqlite_statement_column_bytes", call)
                call["result"] = builder.call(
                    fn, [statement, column_index],
                    name=f"{call_name}_byteCount")
            return

        if target == "sqlite.libraryVersion":
            version_fn = self._runtime_func(
                "ss_sqlite_library_version", I8P, [])
            self.provenance.record_external(
                "ss_sqlite_library_version", call)
            call["result"] = builder.call(
                version_fn, [], name=f"{call_name}_version")
            return

        if target.startswith("sqlite."):
            raise ValueError(
                f"unsupported native sqlite call target: {target!r}; "
                "add an explicit compiler lowering before using it")

        # External-module fallback: targets that look like a method on an
        # imported module (`http.requestCancellationToken`,
        # `database.openConnection`, `AccountBalanceResponseJsonCodec.encode`,
        # `accountIdPathValidator.validate`, etc.) have no body in this
        # translation unit. Rather than fail codegen, emit a dummy zero result
        # so the surrounding control flow + bind chain still compiles. A real
        # runtime (when wired) would supply the implementation by linking
        # against the named module's exports. This mirrors what
        # bootstrap_general.sscript does via its runUnhandled path.
        if "." in target or target in self.prog.validators or target in self.prog.policies:
            zero = ir.Constant(I64, 0)
            call["result"] = zero
            call["error_value"] = zero
            call["error_cond"] = ir.Constant(I1, 0)
            return

        raise ValueError(f"unsupported call target: {target!r}")


# ============================================================
# Driver / JIT
# ============================================================

# ============================================================
# Linter (agent-safety checks)
# ============================================================

def lint(prog: Program, strict: bool = False):
    """Walk the parsed Program and emit linter diagnostics to stderr.

    The compiler accepts non-conforming programs; the linter is the place
    where SemanticScript's agent-safety laws (spec §2 linter-class rules) are
    expressed. When `strict` is true, lint warnings escalate to fatal
    errors so CI/build pipelines can refuse to ship code that drifts from
    the constitution.

    Rules implemented:
      vagueCallName, vagueErrorName, vagueFailureName, roleSuffixMismatch,
      unbranchedFailure
      missingPurpose              -- §3 abstraction admission test
      missingEffectDeclaration    -- §2 checkability law
      branchTargetExists          -- §4 control flow must be graphable
      duplicatedDomainLiteral     -- AST.md invariant 8
      groupCommentBalance         -- §7 attention anchors
      failureLabelAggregation     -- §12 failure flow precision
    """
    diags = []

    # ---- module-level: group/endGroup balance ----
    _check_group_balance(prog.module_group_anchors, diags, scope="module")

    # ---- module-level: duplicated domain literals ----
    _check_duplicated_domain_literals(prog, diags)

    for op_name, op in prog.operations.items():
        # ---- per-operation: group/endGroup balance ----
        op_anchors = [entry for verb, entry, _ln in op.lines
                      if verb == "__groupAnchor__"]
        _check_group_balance(op_anchors, diags, scope=f"operation {op_name}")

        # Per-call bookkeeping
        calls = {}
        # Track labels: name -> first source line, and references to labels
        # so we can warn on dangling branch targets.
        labels_declared = set()
        label_references = []   # list of (label_name, lineno, kind)
        # Track branchIfError targets so we can detect aggregation
        # (multiple distinct call sites all branching into the same label,
        # which forces makeError to forget the cause).
        branchIfError_targets = {}  # label_name -> list of (call_name, lineno)
        # Track operation-level effects/headers
        purpose_present = False
        invariant_present = False
        effect_writes_console_stdout = False
        operation_uses_console_write = False
        operation_has_loop = False     # any `branch` to an earlier label = loop
        operation_has_effect = False   # any `effect` line at all

        for entry in op.lines:
            verb, args, lineno = entry[0], entry[1], entry[2]
            if verb == "purpose":
                purpose_present = True
            elif verb == "invariant":
                invariant_present = True
            elif verb == "effect" and len(args) >= 3:
                # effect OP_NAME ACTION PATH
                action = args[1]
                path = args[2]
                if action == "write" and path == "console.stdout":
                    effect_writes_console_stdout = True
                operation_has_effect = True
            elif verb == "call":
                call_name = args[0]
                target = args[1] if len(args) >= 2 else ""
                calls[call_name] = {
                    "lineno": lineno,
                    "target": target,
                    "has_bindError": False,
                    "has_branchIfError": False,
                }
                if not call_name.endswith("Call"):
                    diags.append((lineno,
                        f"vagueCallName: `{call_name}` should end with the Call role suffix"))
                if target in ("console.writeLine", "console.writeIntegerLine"):
                    operation_uses_console_write = True
            elif verb == "bindError" and len(args) >= 3:
                call_name = args[2]
                if call_name in calls:
                    calls[call_name]["has_bindError"] = True
                err_name = args[0]
                if not err_name.endswith("Error"):
                    diags.append((lineno,
                        f"vagueErrorName: `{err_name}` should end with the Error role suffix"))
            elif verb == "branchIfError" and args:
                call_name = args[0]
                if call_name in calls:
                    calls[call_name]["has_branchIfError"] = True
                if len(args) >= 2:
                    lbl = args[1]
                    label_references.append((lbl, lineno, "branchIfError"))
                    branchIfError_targets.setdefault(lbl, []).append((call_name, lineno))
                    if not (lbl.endswith("Failed") or lbl.endswith("ed")):
                        diags.append((lineno,
                            f"roleSuffixMismatch: branch label `{lbl}` should end with Failed or a past-tense -ed form"))
            elif verb == "branchIf" and len(args) >= 2:
                label_references.append((args[1], lineno, "branchIf"))
                # branchIf 3-arg legacy form: also record the false-leg label
                if len(args) >= 3:
                    label_references.append((args[2], lineno, "branchIf-false"))
            elif verb == "branch" and args:
                label_references.append((args[0], lineno, "branch"))
                # A `branch` to a label that has already been declared earlier
                # in source order represents a backward edge — i.e. a loop.
                if args[0] in labels_declared:
                    operation_has_loop = True
            elif verb == "label" and args:
                labels_declared.add(args[0])
            elif verb == "makeError" and args:
                if not args[0].endswith("Failure"):
                    diags.append((lineno,
                        f"vagueFailureName: `{args[0]}` should end with the Failure role suffix"))

        # unbranchedFailure check
        for call_name, info in calls.items():
            if info["has_bindError"] and not info["has_branchIfError"]:
                diags.append((info["lineno"],
                    f"unbranchedFailure: `{call_name}` has a bindError but no branchIfError"))

        # branchTargetExists: every branch target must be a declared label
        for lbl, lineno, kind in label_references:
            if lbl not in labels_declared:
                diags.append((lineno,
                    f"branchTargetExists: {kind} references undeclared label `{lbl}`"))

        # missingPurpose: every operation should declare a purpose
        if not purpose_present:
            decl_lineno = op.lines[0][2] if op.lines else 0
            diags.append((decl_lineno,
                f"missingPurpose: operation `{op_name}` declares no `purpose` line (§3)"))

        # missingInvariant: an operation with a loop or any declared effect
        # should carry at least one invariant. Loops need a termination
        # invariant; effectful operations need at least one safety invariant
        # over their external behavior (spec §8 hard metadata).
        if (operation_has_loop or operation_has_effect) and not invariant_present:
            decl_lineno = op.lines[0][2] if op.lines else 0
            reason = "loop" if operation_has_loop else "effect"
            diags.append((decl_lineno,
                f"missingInvariant: operation `{op_name}` has a {reason} but declares no `invariant` line (§8)"))

        # missingEffectDeclaration: if the operation calls console.writeLine
        # or console.writeIntegerLine, it must declare `effect <op> write console.stdout`
        if operation_uses_console_write and not effect_writes_console_stdout:
            decl_lineno = op.lines[0][2] if op.lines else 0
            diags.append((decl_lineno,
                f"missingEffectDeclaration: operation `{op_name}` writes to console.* but lacks `effect {op_name} write console.stdout` (§2 checkability law)"))

        # failureLabelAggregation: multiple distinct call sites branch into the
        # same label. Per §12, makeError at the shared label cannot honestly
        # name a single cause. Programs that declare `mode capturedOutputReplay`
        # at the top level are exempted: their entire algorithm is a stdout
        # transcript, the trust-boundary marker says so explicitly, and per-
        # call failure labels would multiply boilerplate without adding
        # recoverable context.
        if "capturedOutputReplay" not in prog.modes:
            for lbl, callers in branchIfError_targets.items():
                distinct = {c[0] for c in callers}
                if len(distinct) > 1:
                    if lbl in labels_declared:
                        diags.append((callers[0][1],
                            f"failureLabelAggregation: label `{lbl}` is targeted by {len(distinct)} distinct calls; "
                            f"makeError at the shared label cannot pin the cause (§12)"))

    # ---- module-level: purpose on contract-heavy abstractions ----
    _check_purpose_on_abstractions(prog, diags)

    # ---- module-level: identifier casing per spec §6 ----
    _check_identifier_casing(prog, diags)

    # ---- per-operation: output contracts must be explicit and lowerable ----
    _check_output_contracts(prog, diags)

    # ---- per-operation: declared effects need capability or authority ----
    _check_effect_authority_coverage(prog, diags)

    # ---- per-operation: declared effects must cover called c.* effects ----
    _check_libc_effect_coverage(prog, diags)

    # ---- per-operation: Result A B contract is checked at returns ----
    _check_result_contract(prog, diags)

    for diag in sorted(diags):
        sys.stderr.write(f"warning line {diag[0]}: {diag[1]}\n")
    if strict and diags:
        sys.stderr.write(f"\n{len(diags)} lint warning(s) (strict mode)\n")
        sys.exit(2)


def _check_group_balance(anchors, diags, scope: str):
    """Walk a list of (kind, name, lineno) anchors and warn on imbalance."""
    open_stack = []  # list of (name, lineno)
    for kind, name, lineno in anchors:
        if kind == "group":
            open_stack.append((name, lineno))
        elif kind == "endGroup":
            if not open_stack:
                diags.append((lineno,
                    f"groupCommentBalance: endGroup `{name}` in {scope} with no matching group"))
            else:
                opened_name, _ = open_stack.pop()
                if opened_name != name:
                    diags.append((lineno,
                        f"groupCommentBalance: endGroup `{name}` in {scope} does not match open group `{opened_name}`"))
    for name, lineno in open_stack:
        diags.append((lineno,
            f"groupCommentBalance: group `{name}` in {scope} has no matching endGroup"))


def _check_duplicated_domain_literals(prog: Program, diags):
    """Warn when two consts share the same String literal — the implicit
    rule is that a domain value lives in exactly one named const so that
    edits propagate (AST.md invariant 8). Exempt programs declared as
    `mode capturedOutputReplay`: their consts are positional transcript
    rows whose role identity is the position, not the value."""
    if "capturedOutputReplay" in prog.modes:
        return
    seen = {}   # value -> first const name that held it
    for name, (typ, value) in prog.consts.items():
        if resolve_alias(prog, typ) != "String":
            continue
        if value in seen:
            diags.append((0,
                f"duplicatedDomainLiteral: const `{name}` repeats the string already held by const `{seen[value]}`; "
                f"introduce one shared named const and reference it from both call sites"))
        else:
            seen[value] = name


def _check_purpose_on_abstractions(prog: Program, diags):
    """Every contract-heavy abstraction should declare its purpose."""
    targets = []
    for name in prog.validators:
        targets.append(("validator", name))
    for name, cdef in prog.codecs.items():
        targets.append((cdef.get("kind", "codec"), name))
    for name, pdef in prog.policies.items():
        targets.append((pdef.get("kind", "policy"), name))
    for name in prog.resources:
        targets.append(("resource", name))
    for name in prog.capabilities:
        targets.append(("capability", name))
    for name in prog.records:
        targets.append(("record", name))
    for name in prog.web_servers:
        targets.append(("webServer", name))
    for kind, name in targets:
        meta = prog.hard_metadata.get(name, {})
        if "purpose" not in meta:
            diags.append((0,
                f"missingPurpose: {kind} `{name}` declares no `purpose` line (§3 abstraction admission test)"))


def _check_identifier_casing(prog: Program, diags):
    """Spec §6: PascalCase for types/records/enums/errors/enum variants;
    camelCase for values/calls/labels/operations/vars/consts."""
    def is_pascal(name):
        return bool(name) and name[0].isupper()
    def is_camel(name):
        return bool(name) and name[0].islower()
    # PascalCase declarations
    for name in prog.type_aliases:
        if not is_pascal(name):
            diags.append((0,
                f"casingViolation: type `{name}` should start with uppercase (PascalCase) per §6"))
    for name in prog.errors:
        if not is_pascal(name):
            diags.append((0,
                f"casingViolation: error type `{name}` should start with uppercase per §6"))
    for variants in prog.errors.values():
        for vname, _cause in variants:
            if not is_pascal(vname):
                diags.append((0,
                    f"casingViolation: error variant `{vname}` should start with uppercase per §6"))
    for name in prog.records:
        if not is_pascal(name):
            diags.append((0,
                f"casingViolation: record `{name}` should start with uppercase per §6"))
    for name in prog.enums:
        if not is_pascal(name):
            diags.append((0,
                f"casingViolation: enum `{name}` should start with uppercase per §6"))
    # camelCase declarations
    for op_name in prog.operations:
        if not is_camel(op_name):
            diags.append((0,
                f"casingViolation: operation `{op_name}` should start with lowercase (camelCase) per §6"))
    for name in prog.consts:
        if not is_camel(name):
            diags.append((0,
                f"casingViolation: const `{name}` should start with lowercase per §6"))
    # Per-operation body identifiers
    CAMEL_VERBS = {"call", "var", "label", "bind", "bindOk", "bindError",
                   "ignoreOk", "ignoreValue", "makeError"}
    for op in prog.operations.values():
        for verb, args, lineno in op.lines:
            if verb in CAMEL_VERBS and args and not is_camel(args[0]):
                diags.append((lineno,
                    f"casingViolation: {verb} name `{args[0]}` should start with lowercase per §6"))


# Required effect declarations per c.* / pointer.* call target. The linter
# walks every call and verifies the operation declares the required effects;
# missing entries fire `missingEffectDeclaration` per spec §17.
_LIBC_REQUIRED_EFFECTS = {
    # stdio writes
    "printf":      [("write", "console.stdout")],
    "puts":        [("write", "console.stdout")],
    "fputs":       [("write", "console.stdout")],
    "putchar":     [("write", "console.stdout")],
    "putc":        [("write", "console.stdout")],
    "fputc":       [("write", "console.stdout")],
    "vprintf":     [("write", "console.stdout")],
    "sprintf":     [],
    "snprintf":    [],
    # stdio reads
    "scanf":       [("read", "console.stdin")],
    "getchar":     [("read", "console.stdin")],
    "consoleGetch": [("read", "console.stdin")],
    "_getch":      [("read", "console.stdin")],
    "terminalEnableRaw": [("configure", "console.terminal")],
    "ss_terminal_enable_raw": [("configure", "console.terminal")],
    "terminalDisableRaw": [("configure", "console.terminal")],
    "ss_terminal_disable_raw": [("configure", "console.terminal")],
    "terminalReadKey": [("read", "console.stdin")],
    "ss_terminal_read_key": [("read", "console.stdin")],
    "terminalGetWindowRows": [("read", "console.terminal")],
    "ss_terminal_get_window_rows": [("read", "console.terminal")],
    "terminalGetWindowCols": [("read", "console.terminal")],
    "ss_terminal_get_window_cols": [("read", "console.terminal")],
    "terminalFirstArgument": [("read", "process.arguments")],
    "ss_terminal_first_argument": [("read", "process.arguments")],
    "getsSafe":    [("read", "console.stdin")],
    "gets_s":      [("read", "console.stdin")],
    # filesystem
    "fopen":       [],
    "freopen":     [],
    "fclose":      [("close", "file")],
    "fread":       [("read", "filesystem")],
    "fwrite":      [("write", "filesystem")],
    "fgets":       [("read", "filesystem")],
    "fseek":       [("read", "filesystem")],
    "ftell":       [("read", "filesystem")],
    "remove":      [("write", "filesystem")],
    "rename":      [("write", "filesystem")],
    "tmpfile":     [("write", "filesystem")],
    # heap allocation
    "malloc":      [("allocate", "heap")],
    "calloc":      [("allocate", "heap")],
    "realloc":     [("allocate", "heap")],
    "free":        [("free", "heap")],
    "aligned_alloc": [("allocate", "heap")],
    "alignedAlloc":  [("allocate", "heap")],
    # process
    "system":      [("spawn", "process")],
    "exit":        [("terminate", "process")],
    "_Exit":       [("terminate", "process")],
    "processExitWithoutCleanup": [("terminate", "process")],
    "quick_exit":  [("terminate", "process")],
    "quickExit":   [("terminate", "process")],
    "abort":       [("terminate", "process")],
    # signals
    "raise":       [("emit", "signal")],
    "signal":      [("handle", "signal")],
    # environment
    "getenv":      [("read", "process.environment")],
    "getenv_s":    [("read", "process.environment")],
    "getenvSafe":  [("read", "process.environment")],
    # time
    "time":        [("read", "clock.utc")],
    "clock":       [("read", "clock.cpu")],
    "localtime":   [("read", "clock.utc")],
    "gmtime":      [("read", "clock.utc")],
    # raw memory writes
    "memcpy":      [("write", "memory.buffer")],
    "memmove":     [("write", "memory.buffer")],
    "memset":      [("write", "memory.buffer")],
}

_POINTER_REQUIRED_EFFECTS = {
    "pointer.storeByte": [("write", "memory.buffer")],
    "pointer.loadByte":  [("read",  "memory.buffer")],
    # pointer.offset and pointer.difference are pure arithmetic — no effect.
    "pointer.offset":     [],
    "pointer.difference": [],
    "pointer.isNull":     [],
}


def _operation_literal_values(op):
    values = {}
    for verb, args, _ in op.lines:
        if verb == "const" and len(args) >= 3:
            values[args[0]] = args[2]
        elif verb == "storage" and len(args) >= 5:
            values[args[2]] = args[4]
    return values


def _operation_call_args(op):
    call_args = {}
    for verb, args, _ in op.lines:
        if verb == "arg" and len(args) >= 3:
            call_args.setdefault(args[0], {})[args[1]] = args[2]
    return call_args


def _resolve_literal_token(token, literal_values):
    value = literal_values.get(token, token)
    if isinstance(value, tuple) and len(value) >= 2:
        value = value[1]
    return str(value).strip('"')


def _looks_like_fopen_mode(mode):
    return bool(mode) and mode[0] in {"r", "w", "a"} and all(char in {"b", "+"} for char in mode[1:])


def _fopen_required_effects(call_name, call_args, literal_values):
    mode_token = call_args.get(call_name, {}).get("mode")
    if mode_token is None:
        return [("open", "file"), ("read", "filesystem"), ("write", "filesystem")]

    mode = _resolve_literal_token(mode_token, literal_values).lower()
    if not _looks_like_fopen_mode(mode):
        return [("open", "file"), ("read", "filesystem"), ("write", "filesystem")]

    effects = [("open", "file")]
    if mode[0] == "r" or "+" in mode:
        effects.append(("read", "filesystem"))
    if mode[0] in {"w", "a"} or "+" in mode:
        effects.append(("write", "filesystem"))
    return effects


def _effect_path_covers(scope_path: str, effect_path: str) -> bool:
    return effect_path == scope_path or effect_path.startswith(scope_path + ".")


def _access_covers(grant_access: str, action: str) -> bool:
    return (
        grant_access == action
        or grant_access == "manage"
        or (grant_access == "readWrite" and action in {"read", "write"})
    )


def _check_output_contracts(prog: Program, diags):
    """Warn when an operation has no explicit lowerable output contract."""
    for op in prog.operations.values():
        contract = _operation_output_contract(prog, op)
        if contract.problem:
            diags.append((contract.line, contract.message))


def _check_effect_authority_coverage(prog: Program, diags):
    """Warn when declared effects have no matching capability or authority."""
    for op_name, op in prog.operations.items():
        declared_effects = []
        used_capabilities = []
        for verb, args, lineno in op.lines:
            if verb == "effect" and len(args) >= 3 and args[0] == op_name:
                declared_effects.append((args[1], args[2], lineno))
            elif verb == "useCapability" and len(args) >= 2:
                used_capabilities.append((args[1], lineno))

        used_capability_facts = []
        for capability_name, lineno in used_capabilities:
            capability = prog.capabilities.get(capability_name)
            if capability is None:
                diags.append((lineno,
                    f"unknownCapabilityReference: operation `{op_name}` uses "
                    f"capability `{capability_name}`, but no capability declaration defines it"))
                continue
            used_capability_facts.append(capability)

        authority_facts = []
        for authority_text in prog.hard_metadata.get(op_name, {}).get("authority", []):
            parts = authority_text.split()
            if len(parts) >= 2:
                authority_facts.append({"effect": parts[0], "access": parts[1]})

        for action, effect_path, lineno in declared_effects:
            capability_ok = any(
                _access_covers(capability.get("access", ""), action)
                and _effect_path_covers(capability.get("effect", ""), effect_path)
                for capability in used_capability_facts
            )
            authority_ok = any(
                _access_covers(authority.get("access", ""), action)
                and _effect_path_covers(authority.get("effect", ""), effect_path)
                for authority in authority_facts
            )
            if capability_ok or authority_ok:
                continue

            candidate = next(
                (
                    capability_name
                    for capability_name, capability in prog.capabilities.items()
                    if _access_covers(capability.get("access", ""), action)
                    and _effect_path_covers(capability.get("effect", ""), effect_path)
                ),
                None,
            )
            hint = (
                f"add `useCapability {op_name} {candidate}`"
                if candidate
                else f"declare a capability or authority for `{effect_path} {action}`"
            )
            diags.append((lineno,
                f"missingCapabilityUse: operation `{op_name}` declares effect "
                f"`{action} {effect_path}` without an authorizing capability or authority; {hint}"))


def _check_libc_effect_coverage(prog: Program, diags):
    """For every c.* / pointer.* call in an operation, verify that the
    operation's `effect` lines declare the required effects (spec §17
    declared-effects-must-match-called-effects)."""
    for op_name, op in prog.operations.items():
        declared = set()
        for verb, args, _ in op.lines:
            if verb == "effect" and len(args) >= 3:
                declared.add((args[1], args[2]))
        literal_values = _operation_literal_values(op)
        call_args = _operation_call_args(op)
        for verb, args, lineno in op.lines:
            if verb != "call" or len(args) < 2:
                continue
            tgt = args[1]
            required = None
            if tgt.startswith("c."):
                call_name = args[0]
                semantic_name = tgt[2:]
                if semantic_name in {"fopen", "freopen"}:
                    required = _fopen_required_effects(call_name, call_args, literal_values)
                else:
                    # Try SemanticScript-facing name first, then translate to C symbol.
                    required = _LIBC_REQUIRED_EFFECTS.get(semantic_name)
                    if required is None:
                        c_symbol = libc_registry.resolve_c_symbol(semantic_name)
                        required = _LIBC_REQUIRED_EFFECTS.get(c_symbol, [])
            elif tgt in _POINTER_REQUIRED_EFFECTS:
                required = _POINTER_REQUIRED_EFFECTS[tgt]
            if not required:
                continue
            for action, path in required:
                if (action, path) not in declared:
                    diags.append((lineno,
                        f"missingEffectDeclaration: call `{tgt}` requires "
                        f"`effect {op_name} {action} {path}` but operation "
                        f"`{op_name}` doesn't declare it (§17)"))


def _check_result_contract(prog: Program, diags):
    """Spec §11 + §17: when an operation declares `output OP Result A B`,
    every `returnOk` must produce type A and every `returnError` must
    produce type B (or chain through `makeError` of an errorCase whose
    parent error type is B)."""
    for op_name, op in prog.operations.items():
        # Locate the operation's output declaration.
        output_tokens = None
        for verb, args, _ in op.lines:
            if verb == "output" and args and args[0] == op_name:
                output_tokens = args[1:]
                break
        if not output_tokens:
            continue
        is_result = output_tokens[0] == "Result" and len(output_tokens) >= 3
        if is_result:
            ok_type = output_tokens[1]
            err_type = output_tokens[2]
        else:
            ok_type = output_tokens[0]
            err_type = None

        # Build a value→declared-type map for everything visible inside
        # this operation: consts, vars, binds (bind/bindOk/bindError),
        # and makeError outputs (whose declared type is the parent error).
        value_types = {}
        for name, (typ, _val) in op.consts.items():
            value_types[name] = typ
        for name, (typ, _val) in prog.consts.items():
            value_types.setdefault(name, typ)
        for verb, args, _ in op.lines:
            if verb == "var" and len(args) >= 2:
                value_types[args[0]] = args[1]
            elif verb in ("bind", "bindOk", "bindError") and len(args) >= 3:
                value_types[args[0]] = args[1]
            elif verb == "makeError" and len(args) >= 2 and "." in args[1]:
                value_types[args[0]] = args[1].split(".", 1)[0]

        def types_match(declared, expected):
            if declared == expected:
                return True
            # Resolve through type-alias chains on both sides.
            try:
                return resolve_alias(prog, declared) == resolve_alias(prog, expected)
            except Exception:
                return False

        for verb, args, lineno in op.lines:
            if verb == "returnOk" and args:
                vt = value_types.get(args[0])
                if vt is None:
                    continue
                if not is_result:
                    diags.append((lineno,
                        f"returnOkContract: operation `{op_name}` does not "
                        f"declare a Result output; use `returnValue` instead "
                        f"of `returnOk` (§11)"))
                elif ok_type in ("Void", "CVoid"):
                    # Void success leg: any sentinel value is accepted; the
                    # i32 ABI requires an integer to be returned even when
                    # the spec-level result has no observable value.
                    pass
                elif not types_match(vt, ok_type):
                    diags.append((lineno,
                        f"returnOkContract: returnOk value `{args[0]}` has "
                        f"declared type `{vt}` but operation `{op_name}`'s "
                        f"`Result {ok_type} {err_type}` success leg is `{ok_type}` (§11)"))
            elif verb == "returnError" and args:
                vt = value_types.get(args[0])
                if vt is None:
                    continue
                if not is_result:
                    diags.append((lineno,
                        f"returnErrorContract: operation `{op_name}` has no "
                        f"error type; `returnError` requires a Result output (§11)"))
                elif not types_match(vt, err_type):
                    diags.append((lineno,
                        f"returnErrorContract: returnError value `{args[0]}` "
                        f"has declared type `{vt}` but operation `{op_name}`'s "
                        f"`Result {ok_type} {err_type}` error leg is `{err_type}` (§11)"))


def _optimize(mod, tm, opt_level: int):
    """Run the LLVM new-pass-manager optimization pipeline."""
    pto = llvm.create_pipeline_tuning_options(speed_level=opt_level, size_level=0)
    pto.loop_vectorization = True
    pto.slp_vectorization = True
    pb = llvm.create_pass_builder(tm, pto)
    mpm = pb.getModulePassManager()
    mpm.run(mod, pb)


def _merge_build_file(prog: Program, build_path: str, explicit_std_paths=None) -> None:
    """Parse a build-time .sem / .sscript file and merge its declarations
    into the main Program. Only build-time facts (project metadata, custom
    metadata, icon registry) propagate. Conflicting redeclarations (same
    metadata key or icon group/image name already set in the main source)
    are rejected — a build file augments the main source, it does not
    silently override."""
    with open(build_path, "r", encoding="utf-8") as build_handle:
        build_source = build_handle.read()
    build_source = _resolve_imports(build_source, build_path, explicit_std_paths)
    build_prog = parse(build_source)

    for field_name, value in build_prog.project_metadata.items():
        if (field_name in prog.project_metadata
                and prog.project_metadata[field_name] != value):
            raise SyntaxError(
                f"`{field_name}` declared in both main source and build file "
                f"with different values "
                f"({prog.project_metadata[field_name]!r} vs {value!r})")
        prog.project_metadata.setdefault(field_name, value)

    for key, value in build_prog.custom_metadata.items():
        if key in prog.custom_metadata and prog.custom_metadata[key] != value:
            raise SyntaxError(
                f"metadata `{key}` declared in both main source and build "
                f"file with different values")
        prog.custom_metadata.setdefault(key, value)

    for role, description in build_prog.icon_role_definitions.items():
        prog.icon_role_definitions.setdefault(role, description)

    for group_name, group_info in build_prog.icon_groups.items():
        if group_name in prog.icon_groups:
            raise SyntaxError(
                f"icon group `{group_name}` declared in both main source "
                f"and build file")
        prog.icon_groups[group_name] = dict(group_info)

    for image_name, image_info in build_prog.icon_images.items():
        if image_name in prog.icon_images:
            raise SyntaxError(
                f"iconImage `{image_name}` declared in both main source "
                f"and build file")
        prog.icon_images[image_name] = dict(image_info)


def _pack_png_list_to_ico(images_in_size_order, ico_output_path: str) -> None:
    """Build a multi-image Windows .ico from a list of (size_pixels, png_path)
    tuples. Each entry is embedded at its declared size as PNG-encoded data
    (Vista+ supported, ubiquitous now — more compact than BMP entries and
    preserves alpha channel without conversion). The caller is responsible
    for ordering the list smallest-first."""
    import struct
    entries_bytes = b""
    data_bytes = b""
    count = len(images_in_size_order)
    # ICONDIR header (6 bytes) + count * 16-byte ICONDIRENTRY then image data.
    data_offset = 6 + count * 16
    for size, png_path in images_in_size_order:
        with open(png_path, "rb") as png_handle:
            png_bytes = png_handle.read()
        width_byte = size if size < 256 else 0   # zero means 256 in ICO spec
        height_byte = size if size < 256 else 0
        entries_bytes += struct.pack(
            "<BBBBHHII",
            width_byte, height_byte,
            0,    # color count (0 for >256 colours / PNG-encoded)
            0,    # reserved
            1,    # color planes
            32,   # bits per pixel
            len(png_bytes),
            data_offset,
        )
        data_bytes += png_bytes
        data_offset += len(png_bytes)
    header = struct.pack("<HHH", 0, 1, count)
    with open(ico_output_path, "wb") as ico_handle:
        ico_handle.write(header)
        ico_handle.write(entries_bytes)
        ico_handle.write(data_bytes)


def _select_windows_icon_payload(prog: Program):
    """Walk the program's icon registry and pick the .ico payload for the
    `applicationPrimary` group. Returns one of:

      ("prebuilt", "<path>.ico")   — a pre-built .ico from an
                                      `iconImageFormat <name> ico` row;
                                      pass to llvm-rc verbatim.
      ("packed",   [(size, png_path), ...]) — PNG inputs that need packing
                                               into a transient .ico.
      None — no Windows-eligible icon to embed.
    """
    primary_group = None
    for group_name, group_info in prog.icon_groups.items():
        if group_info.get("role") == "applicationPrimary":
            primary_group = group_name
            break
    if primary_group is None:
        return None

    source_dir = _source_dir(prog.source_path)

    def resolve_icon_asset_path(path_text: str) -> str:
        if os.path.isabs(path_text):
            return path_text
        return os.path.abspath(os.path.join(source_dir, path_text))

    prebuilt_ico_path = None
    png_inputs = []
    for image_name, image_info in prog.icon_images.items():
        if image_info.get("group") != primary_group:
            continue
        platform = image_info.get("platform", "any")
        if platform not in ("any", "windows"):
            continue
        fmt = image_info.get("format")
        path = image_info.get("path")
        if not path:
            continue
        path = resolve_icon_asset_path(path)
        if fmt == "ico" and prebuilt_ico_path is None:
            prebuilt_ico_path = path
        elif fmt == "png":
            width = image_info.get("width") or 0
            png_inputs.append((width, path, image_name))

    if prebuilt_ico_path is not None:
        return ("prebuilt", prebuilt_ico_path)
    if png_inputs:
        png_inputs.sort(key=lambda triple: triple[0])
        return ("packed", [(size, path) for size, path, _name in png_inputs])
    return None


def _normalize_version_quad(version_text: str) -> str:
    """Right-pad a SemanticScript version like `1.2.3` to the Windows
    `FIXEDFILEINFO` four-component form `1,2,3,0`. The dotted source form
    stays in the string-table entry alongside."""
    parts = version_text.split(".")
    while len(parts) < 4:
        parts.append("0")
    return ",".join(parts[:4])


def _rc_escape(value: str) -> str:
    """Escape a string for a Windows resource-compiler string literal.
    `windres` and `llvm-rc` both accept the same C-style escaping for
    backslashes and double-quotes; embedded newlines are dropped because
    string-table entries are single-line by spec."""
    cleaned = value.replace("\\", r"\\").replace("\"", r"\"")
    cleaned = cleaned.replace("\r", "").replace("\n", " ")
    return cleaned


def _render_versioninfo_rc(prog: Program, exe_path: str,
                            icon_path: str = None) -> str:
    """Build the Windows .rc source for the program's project metadata.
    Returns the .rc text. Standard StringFileInfo keys map directly from
    the project metadata; custom_metadata adds arbitrary entries below the
    fixed block so the user can attach any key/value pair."""
    version_text = prog.project_metadata.get("version", "0.0.0.0")
    version_quad = _normalize_version_quad(version_text)
    company_name = prog.project_metadata.get("publisher", "")
    file_description = prog.project_metadata.get("description",
                                                  prog.project_name or "")
    legal_copyright = prog.project_metadata.get("copyright", "")
    product_name = prog.project_metadata.get("productName",
                                              prog.project_name or "")
    internal_name = prog.project_metadata.get("internalName",
                                               prog.project_name or "")
    original_filename = prog.project_metadata.get(
        "originalFilename",
        os.path.basename(exe_path) if exe_path else "")
    trademark = prog.project_metadata.get("trademark", "")
    comments = prog.project_metadata.get("comments", "")

    # StringFileInfo block — keys in the conventional Windows order. Empty
    # values are deliberately preserved so a downstream consumer can tell
    # "field was declared empty" from "field was never declared."
    string_entries = [
        ("CompanyName",      company_name),
        ("FileDescription",  file_description),
        ("FileVersion",      version_text),
        ("InternalName",     internal_name),
        ("LegalCopyright",   legal_copyright),
        ("LegalTrademarks",  trademark),
        ("OriginalFilename", original_filename),
        ("ProductName",      product_name),
        ("ProductVersion",   version_text),
    ]
    if comments:
        string_entries.append(("Comments", comments))
    for custom_key, custom_value in prog.custom_metadata.items():
        string_entries.append((custom_key, custom_value))

    string_lines = [
        f'      VALUE "{_rc_escape(key)}", "{_rc_escape(value)}"'
        for key, value in string_entries
    ]
    string_table_body = "\n".join(string_lines)

    icon_line = ""
    if icon_path:
        # llvm-rc / rc.exe parse `1 ICON "path"` and read the .ico file
        # at resource-compile time. Forward slashes are valid in modern rc
        # paths; we also escape backslashes defensively for absolute paths.
        icon_path_rc = icon_path.replace("\\", "\\\\")
        icon_line = f"1 ICON \"{icon_path_rc}\"\n"

    return (
        "// Auto-generated by SemanticScript compiler; do not edit by hand.\n"
        "#pragma code_page(65001)\n"
        + icon_line +
        "1 VERSIONINFO\n"
        f"FILEVERSION    {version_quad}\n"
        f"PRODUCTVERSION {version_quad}\n"
        "FILEFLAGSMASK  0x3fL\n"
        "FILEFLAGS      0x0L\n"
        "FILEOS         0x40004L\n"
        "FILETYPE       0x1L\n"
        "FILESUBTYPE    0x0L\n"
        "BEGIN\n"
        "  BLOCK \"StringFileInfo\"\n"
        "  BEGIN\n"
        "    BLOCK \"040904b0\"\n"
        "    BEGIN\n"
        f"{string_table_body}\n"
        "    END\n"
        "  END\n"
        "  BLOCK \"VarFileInfo\"\n"
        "  BEGIN\n"
        "    VALUE \"Translation\", 0x0409, 0x04b0\n"
        "  END\n"
        "END\n"
    )


def _find_resource_compiler():
    """Return (name, path) for the first resource compiler we can locate, or
    None if none is available. Tries llvm-rc (ships with LLVM/clang) first,
    then windres (MinGW/binutils). PATH lookup is checked, plus the common
    Windows install location `C:\\Program Files\\LLVM\\bin\\llvm-rc.exe`
    so the resource compiler resolves the same way clang does in
    emit_executable. Honors $SEMSC_WINRC for explicit override."""
    from shutil import which
    override = os.environ.get("SEMSC_WINRC")
    if override and os.path.exists(override):
        lowered = override.lower()
        if "llvm-rc" in lowered or "rc.exe" in lowered:
            return ("llvm-rc", override)
        return ("windres", override)
    llvm_rc_candidates = [
        which("llvm-rc"),
        "C:/Program Files/LLVM/bin/llvm-rc.exe",
        "C:/Program Files (x86)/LLVM/bin/llvm-rc.exe",
    ]
    for candidate in llvm_rc_candidates:
        if candidate and os.path.exists(candidate):
            return ("llvm-rc", candidate)
    windres = which("windres")
    if windres is not None:
        return ("windres", windres)
    return None


def _compile_windows_resource(prog: Program, exe_path: str,
                              resource_dir: str = None):
    """Generate and compile a Windows VERSIONINFO resource for the program's
    metadata. Returns the path to the linkable resource object (.res or .o)
    plus any temp files to clean up, or (None, []) if metadata is empty,
    we're not building for Windows, or no resource compiler is available."""
    import subprocess

    icon_selection = _select_windows_icon_payload(prog)
    if not (prog.project_metadata or prog.custom_metadata or icon_selection):
        return None, []
    if sys.platform != "win32":
        return None, []

    compiler = _find_resource_compiler()
    if compiler is None:
        sys.stderr.write(
            "semsc: warning: project metadata / icon resources were declared "
            "but no Windows resource compiler is available (set SEMSC_WINRC "
            "or install llvm-rc / windres); linking without resources\n")
        return None, []
    compiler_kind, compiler_path = compiler

    temp_files = []
    resource_stem = os.path.splitext(os.path.basename(exe_path))[0] or "program"
    if resource_dir:
        os.makedirs(resource_dir, exist_ok=True)
    icon_path_for_rc = None
    if icon_selection is not None:
        kind, payload = icon_selection
        if kind == "prebuilt":
            # Resolve to absolute path so the rc-side reference works no
            # matter where llvm-rc is invoked from.
            icon_path_for_rc = os.path.abspath(payload)
        else:
            if resource_dir:
                ico_path = os.path.join(resource_dir, f"{resource_stem}.icon.ico")
            else:
                import tempfile
                ico_handle = tempfile.NamedTemporaryFile(
                    suffix=".ico", delete=False)
                ico_handle.close()
                ico_path = ico_handle.name
            try:
                _pack_png_list_to_ico(payload, ico_path)
            except Exception as exc:
                sys.stderr.write(
                    f"semsc: warning: failed to pack icon PNGs into a .ico "
                    f"({exc}); linking without an embedded icon\n")
                if not resource_dir:
                    try:
                        os.unlink(ico_path)
                    except OSError:
                        pass
            else:
                icon_path_for_rc = os.path.abspath(ico_path)
                if not resource_dir:
                    temp_files.append(ico_path)

    rc_text = _render_versioninfo_rc(prog, exe_path, icon_path=icon_path_for_rc)
    # Write UTF-8 with BOM. llvm-rc's preprocessor (clang-derived) reads
    # UTF-8 directly with the BOM and the `#pragma code_page(65001)`
    # already inside the .rc; rc.exe also handles UTF-8+BOM. UTF-16 LE
    # is the traditional Windows form but llvm-rc rejects it because
    # the underlying clang preprocessor only accepts UTF-8.
    if resource_dir:
        rc_path = os.path.join(resource_dir, f"{resource_stem}.versioninfo.rc")
        with open(rc_path, "wb") as rc_file:
            rc_file.write(b"\xef\xbb\xbf")
            rc_file.write(rc_text.encode("utf-8"))
    else:
        import tempfile
        rc_handle = tempfile.NamedTemporaryFile(
            suffix=".rc", delete=False, mode="wb")
        rc_handle.write(b"\xef\xbb\xbf")
        rc_handle.write(rc_text.encode("utf-8"))
        rc_handle.close()
        rc_path = rc_handle.name
        temp_files.append(rc_path)

    if compiler_kind == "llvm-rc":
        res_path = rc_path[:-3] + ".res"
        # `/C 65001` forces the input-string codepage to UTF-8 so non-ASCII
        # characters (em-dash, smart quotes, accented letters) in metadata
        # string-table entries are interpreted correctly. Without it llvm-rc
        # falls back to the system ANSI codepage and rejects high-bit bytes.
        cmd = [compiler_path, "/C", "65001", "/FO", res_path, rc_path]
    else:
        # windres compiles directly to a COFF object clang can link.
        # `--codepage=65001` is windres's equivalent of `/C 65001`.
        res_path = rc_path[:-3] + ".o"
        cmd = [compiler_path, "--codepage=65001",
               "-O", "coff", "-i", rc_path, "-o", res_path]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        sys.stderr.write(
            f"semsc: warning: resource compiler `{compiler_kind}` failed "
            f"({proc.returncode}); linking without VERSIONINFO\n"
            f"{proc.stderr}\n")
        for path in temp_files:
            try:
                os.unlink(path)
            except OSError:
                pass
        return None, []
    if not resource_dir:
        temp_files.append(res_path)
    return res_path, temp_files


def emit_executable(module_ir: str, exe_path: str, opt_level: int = 2,
                    provenance: CompilerProvenance = None,
                    diagnostics_format: str = "agent",
                    extra_sources=None,
                    extra_link_args=None,
                    link_work_dir: str = None,
                    link_ir_path: str = None,
                    cpu_config=None) -> None:
    """Ahead-of-time compile SemanticScript IR to a native executable.

    The SemanticScript runtime depends only on libc, so the same toolchain that
    builds a C program can link an SemanticScript program: write the IR to a temp `.ll`,
    invoke clang (or whatever `SEMSC_CLANG` resolves to), and let it produce
    a standalone exe. JIT overhead (MCJIT trampolines, PLT-style indirection)
    is removed entirely, which is what closes the gap with native C on tight
    inner loops."""
    import subprocess
    import tempfile

    clang = os.environ.get("SEMSC_CLANG")
    if not clang:
        # Try common Windows install locations + PATH lookup.
        for candidate in ("clang", "C:/Program Files/LLVM/bin/clang.exe"):
            if os.path.isabs(candidate):
                if os.path.exists(candidate):
                    clang = candidate
                    break
            else:
                from shutil import which
                resolved = which(candidate)
                if resolved:
                    clang = resolved
                    break
    if not clang:
        raise RuntimeError(
            "could not find a clang executable; set SEMSC_CLANG=/path/to/clang")

    remove_link_ir = link_ir_path is None
    if link_ir_path is not None:
        ll_path = link_ir_path
    else:
        if link_work_dir:
            os.makedirs(link_work_dir, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            suffix=".ll",
            prefix=".semsc-link-",
            dir=link_work_dir,
            delete=False,
            mode="w",
            encoding="utf-8",
        ) as f:
            ll_path = f.name
            f.write(module_ir)
    try:
        exe_dir = os.path.dirname(os.path.abspath(exe_path))
        if exe_dir:
            os.makedirs(exe_dir, exist_ok=True)
        cmd = [clang, f"-O{opt_level}"]
        if cpu_config is not None and cpu_config.clang_args:
            cmd.extend(cpu_config.clang_args)
        cmd.extend(["-o", exe_path, ll_path])
        if extra_sources:
            cmd.extend(extra_sources)
        if extra_link_args:
            cmd.extend(extra_link_args)
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            if provenance is not None:
                raise CompilerDiagnosticError(
                    provenance.explain_backend_error(proc.stderr, cmd=cmd))
            raise RuntimeError(
                f"clang failed to compile SemanticScript IR:\n{proc.stderr}")
    finally:
        if remove_link_ir:
            try:
                os.unlink(ll_path)
            except OSError:
                pass


def _diagnostic_from_codegen_error(prog: Program, error: Exception) -> CompilerDiagnostic:
    message = str(error)
    primary = None
    semantic_stack = []

    line_match = re.search(r"\bline\s+(\d+)\b", message)
    if line_match:
        line = int(line_match.group(1))
        primary = DiagnosticSpan(
            path=prog.source_path or "<source>",
            line=line,
            column=1,
            raw=prog.source_lines.get(line, ""),
            role="sourceError",
        )

    call_match = re.match(r"([A-Za-z_][A-Za-z0-9_]*)\s*:", message)
    call_name = call_match.group(1) if call_match else ""
    if call_name:
        for op in prog.operations.values():
            call_line = None
            call_target = ""
            for verb, args, lineno in op.lines:
                if verb == "call" and len(args) >= 2 and args[0] == call_name:
                    call_line = lineno
                    call_target = args[1]
                    break
            if call_line is not None:
                primary = DiagnosticSpan(
                    path=prog.source_path or "<source>",
                    line=call_line,
                    column=1,
                    raw=prog.source_lines.get(call_line, ""),
                    role="callSite",
                )
                semantic_stack.append(DiagnosticFrame(
                    kind="SemanticScript call",
                    operation=op.name,
                    call_name=call_name,
                    call_target=call_target,
                    span=primary,
                ))
                break

    if primary is None:
        primary = DiagnosticSpan(
            path=prog.source_path or "<source>",
            line=0,
            column=1,
            raw="",
            role="compilerError",
        )

    direction = (
        "The compiler failed while lowering SemanticScript to LLVM IR. Start "
        "from the SemanticScript stack frame, then inspect the named call, "
        "its arg rows, and the declaration of every referenced value."
    )
    if "unresolved symbol" in message:
        direction = (
            "A source value reference could not be resolved in this operation. "
            "This usually means a typo, a missing const/var/bind, or a value "
            "declared in another operation's scope."
        )
    elif "missing arg" in message or "missing required arg" in message:
        direction = (
            "The call target expects an argument that the call site did not "
            "provide. Add the missing `arg` row, or align the arg name with "
            "the target operation's `input` row."
        )
    elif "unsupported c.* target" in message:
        direction = (
            "The source uses a `c.*` target that is not registered in "
            "libc_registry.py. Add a signature/alias there or replace the "
            "call with a supported runtime primitive."
        )

    return CompilerDiagnostic(
        code="SSCG001",
        phase="codegen.lower",
        message=message,
        primary=primary,
        semantic_stack=semantic_stack,
        lowering_trace=[
            "SemanticScript source -> parsed Program",
            "Program operation body -> LLVM IRBuilder",
            "lowering stopped before native backend",
        ],
        direction=direction,
        suggested_fixes=[
            "Inspect the primary source row and the operation-local declarations.",
            "Run `semsc SOURCE --parse-only --lint` to surface structural issues before codegen.",
            "Rerun with SEMSC_TRACEBACK=1 only if this looks like a compiler bug.",
        ],
        agent_hint=(
            "Prefer source edits near the primary frame. Avoid changing LLVM "
            "output directly; it is regenerated from SemanticScript."
        ),
    )


def _resolve_runtime_checks(build_profile: str, runtime_checks: str = None) -> str:
    if runtime_checks is not None:
        return runtime_checks
    if build_profile == "prod":
        return "traps"
    return "panic"


def _render_success_message(code: str, title: str, source_path: str,
                            outputs=None, details=None, next_steps=None) -> str:
    lines = [
        f"success {code}: {title}",
        "-" * (len(f"success {code}: {title}")),
        f"source: {source_path}",
    ]
    if details:
        for label, value in details:
            if value is not None and value != "":
                lines.append(f"{label}: {value}")
    if outputs:
        lines.extend(["", "Outputs:"])
        for label, value in outputs:
            lines.append(f"  {label}: {value}")
    if next_steps:
        lines.extend(["", "Next:"])
        for step in next_steps:
            lines.append(f"  {step}")
    return "\n".join(lines)


def _source_dir(source_path: str) -> str:
    if source_path:
        return os.path.dirname(os.path.abspath(source_path)) or os.getcwd()
    return os.getcwd()


def _default_build_dir(source_path: str, build_folder_name: str = "build") -> str:
    return os.path.join(_source_dir(source_path), build_folder_name)


def _resolve_build_dir(source_path: str, build_dir: str = None,
                       build_root: str = None,
                       build_folder_name: str = None) -> str:
    folder_name = build_folder_name or "build"
    normalized_folder = folder_name.replace("\\", os.sep).replace("/", os.sep)
    if (os.path.isabs(normalized_folder)
            or os.path.dirname(normalized_folder)
            or normalized_folder in ("", ".", "..")):
        raise ValueError(
            "--build-folder-name must be a single directory name, not a path")
    if build_dir:
        if build_root or build_folder_name:
            raise ValueError(
                "--build-dir is an exact artifact directory and cannot be "
                "combined with --build-root or --build-folder-name")
        if os.path.isabs(build_dir):
            return os.path.abspath(build_dir)
        return os.path.abspath(os.path.join(_source_dir(source_path), build_dir))
    if build_root:
        if os.path.isabs(build_root):
            root = os.path.abspath(build_root)
        else:
            root = os.path.abspath(os.path.join(_source_dir(source_path), build_root))
        return os.path.join(root, normalized_folder)
    return _default_build_dir(source_path, normalized_folder)


def _path_has_directory(path_text: str) -> bool:
    normalized = path_text.replace("\\", os.sep).replace("/", os.sep)
    return bool(os.path.dirname(normalized))


def _build_metadata_bool(prog: Program, key: str):
    """Read a yes/no/true/false/on/off/1/0 flag from build-tape metadata.
    Returns None if the key isn't declared; otherwise returns the parsed
    boolean. Used by `keepResources` and similar build-tape switches."""
    raw_value = _build_metadata_value(prog, key)
    if raw_value is None:
        return None
    normalized = str(raw_value).strip().lower()
    if normalized in ("yes", "true", "on", "1"):
        return True
    if normalized in ("no", "false", "off", "0"):
        return False
    return None


def _resolve_resource_dir(prog: Program, source_path: str, build_dir: str,
                           cli_keep, cli_resource_dir):
    """Compute the directory the resource compiler writes its intermediate
    `.rc`/`.res`/`.ico` files to. Returns `None` to use a tempdir (the
    `_compile_windows_resource` machinery cleans up automatically), or a
    real path to keep the files for debugging.

    Precedence:
      1. CLI `--resource-dir PATH` — explicit path, implies keep.
      2. CLI `--keep-resources`    — boolean override; uses
                                     `<build_dir>/resources/` when on.
      3. build.sem `resourcesDir PROJECT "path"` — explicit path.
      4. build.sem `keepResources PROJECT yes`  — boolean; uses
                                                   `<build_dir>/resources/`.
      5. Default: None (tempdir + cleanup, no filesystem residue).
    """
    if cli_resource_dir is not None:
        if os.path.isabs(cli_resource_dir):
            return os.path.abspath(cli_resource_dir)
        return os.path.abspath(
            os.path.join(_source_dir(source_path), cli_resource_dir))

    if cli_keep is True:
        return os.path.join(build_dir, "resources")

    build_path = _build_metadata_value(prog, "resourcesDir")
    if build_path:
        if os.path.isabs(build_path):
            return os.path.abspath(build_path)
        return os.path.abspath(
            os.path.join(_source_dir(source_path), build_path))

    if _build_metadata_bool(prog, "keepResources") is True:
        return os.path.join(build_dir, "resources")

    return None


def _build_metadata_value(prog: Program, key: str) -> str:
    for metadata in prog.hard_metadata.values():
        rows = metadata.get(key)
        if not rows:
            continue
        first_row = rows[0]
        if first_row:
            return str(first_row[0])
    return None


def _build_metadata_rows(prog: Program, key: str):
    rows = []
    for metadata in prog.hard_metadata.values():
        rows.extend(metadata.get(key, []))
    return rows


def _resolve_choice_from_build(prog: Program, key: str, cli_value: str,
                               default_value: str, choices) -> str:
    value = cli_value
    if value is None:
        value = _build_metadata_value(prog, key)
    if value is None:
        value = default_value
    if value not in choices:
        raise ValueError(
            f"{key}: `{value}` is not valid; expected one of {sorted(choices)}")
    return value


@dataclass
class CpuBuildConfig:
    baseline: str = "generic"
    tune: str = "generic"
    feature_check: str = "auto"
    llvm_cpu: str = ""
    llvm_features: str = ""
    clang_args: list = field(default_factory=list)
    required_features: list = field(default_factory=list)
    disabled_features: list = field(default_factory=list)

    def summary(self) -> str:
        parts = [f"baseline={self.baseline}", f"tune={self.tune}"]
        if self.required_features:
            parts.append("require=" + ",".join(self.required_features))
        if self.disabled_features:
            parts.append("disable=" + ",".join(self.disabled_features))
        parts.append(f"check={self.feature_check}")
        return " ".join(parts)


def _normalize_cpu_feature(feature_name: str) -> str:
    feature_name = str(feature_name).strip().lower()
    if not _CPU_FEATURE_RE.match(feature_name):
        raise ValueError(f"cpuFeature: invalid feature name `{feature_name}`")
    return feature_name


def _parse_cpu_feature_override(raw_value: str):
    raw_value = str(raw_value).strip()
    if not raw_value:
        raise ValueError("cpuFeature: empty feature override")
    if raw_value[0] in "+-":
        return _normalize_cpu_feature(raw_value[1:]), "on" if raw_value[0] == "+" else "off"
    if "=" not in raw_value:
        raise ValueError(
            "cpuFeature: CLI overrides must look like FEATURE=on, FEATURE=off, +FEATURE, or -FEATURE")
    feature_name, feature_state = raw_value.split("=", 1)
    feature_state = feature_state.strip().lower()
    if feature_state not in _CPU_FEATURE_STATES:
        raise ValueError("cpuFeature: state must be on or off")
    return _normalize_cpu_feature(feature_name), feature_state


def _host_cpu_feature_enabled(feature_name: str) -> bool:
    try:
        host_features = llvm.get_host_cpu_features()
        return bool(host_features[feature_name])
    except Exception:
        return False


def _host_cpu_name() -> str:
    try:
        name = llvm.get_host_cpu_name()
    except Exception:
        return ""
    return str(name or "")


def _resolve_cpu_build_config(prog: Program,
                              cpu_baseline: str = None,
                              cpu_tune: str = None,
                              cpu_feature_overrides=None,
                              cpu_feature_check: str = None) -> CpuBuildConfig:
    baseline = cpu_baseline
    if baseline is None:
        baseline = _build_metadata_value(prog, "cpuBaseline")
    baseline = baseline or "generic"
    if baseline not in _BUILD_TAPE_CHOICES["cpuBaseline"]:
        raise ValueError(
            f"cpuBaseline: `{baseline}` is not valid; expected one of "
            f"{sorted(_BUILD_TAPE_CHOICES['cpuBaseline'])}")

    tune = cpu_tune
    if tune is None:
        tune = _build_metadata_value(prog, "cpuTune")
    tune = tune or "generic"
    if not _CPU_FEATURE_RE.match(str(tune)):
        raise ValueError(f"cpuTune: invalid CPU tune token `{tune}`")

    feature_check = cpu_feature_check
    if feature_check is None:
        feature_check = _build_metadata_value(prog, "cpuFeatureCheck")
    feature_check = feature_check or "auto"
    if feature_check not in _BUILD_TAPE_CHOICES["cpuFeatureCheck"]:
        raise ValueError(
            f"cpuFeatureCheck: `{feature_check}` is not valid; expected one "
            f"of {sorted(_BUILD_TAPE_CHOICES['cpuFeatureCheck'])}")

    feature_overrides = []
    for row in _build_metadata_rows(prog, "cpuFeature"):
        if len(row) < 2:
            raise ValueError("cpuFeature: build row requires FEATURE and on|off")
        feature_name = _normalize_cpu_feature(row[0])
        feature_state = str(row[1]).strip().lower()
        if feature_state not in _CPU_FEATURE_STATES:
            raise ValueError("cpuFeature: state must be on or off")
        feature_overrides.append((feature_name, feature_state))
    for override in cpu_feature_overrides or []:
        feature_overrides.append(_parse_cpu_feature_override(override))

    baseline_features = set(_CPU_BASELINE_FEATURES.get(baseline, frozenset()))
    explicit_enabled = []
    explicit_disabled = []
    for feature_name, feature_state in feature_overrides:
        if feature_state == "on":
            if feature_name not in explicit_enabled:
                explicit_enabled.append(feature_name)
            if feature_name in explicit_disabled:
                explicit_disabled.remove(feature_name)
        else:
            if feature_name in baseline_features:
                raise ValueError(
                    f"cpuFeature: `{feature_name}` cannot be disabled because "
                    f"`cpuBaseline {baseline}` requires it")
            if feature_name not in explicit_disabled:
                explicit_disabled.append(feature_name)
            if feature_name in explicit_enabled:
                explicit_enabled.remove(feature_name)

    required_features = sorted(baseline_features | set(explicit_enabled))
    missing_features = [
        feature_name for feature_name in required_features
        if not _host_cpu_feature_enabled(feature_name)
    ]
    if missing_features and feature_check in {"auto", "require"}:
        raise ValueError(
            "cpuFeatureCheck: host CPU is missing required feature(s): "
            + ", ".join(missing_features)
            + ". Lower cpuBaseline, remove cpuFeature rows, or use "
            "cpuFeatureCheck off only for a known non-host target.")
    if missing_features and feature_check == "warn":
        print(
            "semsc: warning: host CPU is missing requested feature(s): "
            + ", ".join(missing_features),
            file=sys.stderr,
        )

    llvm_cpu = ""
    if baseline == "native":
        llvm_cpu = _host_cpu_name()
    llvm_feature_parts = []
    if baseline != "native":
        llvm_feature_parts.extend("+" + feature for feature in sorted(baseline_features))
    llvm_feature_parts.extend("+" + feature for feature in explicit_enabled)
    llvm_feature_parts.extend("-" + feature for feature in explicit_disabled)

    clang_args = []
    clang_march = _CPU_BASELINE_CLANG_MARCH.get(baseline)
    if clang_march:
        clang_args.append(f"-march={clang_march}")
    if tune != "generic":
        clang_args.append(f"-mtune={tune}")
    for feature_name in explicit_enabled:
        clang_args.append(f"-m{feature_name}")
    for feature_name in explicit_disabled:
        clang_args.append(f"-mno-{feature_name}")

    return CpuBuildConfig(
        baseline=baseline,
        tune=tune,
        feature_check=feature_check,
        llvm_cpu=llvm_cpu,
        llvm_features=",".join(llvm_feature_parts),
        clang_args=clang_args,
        required_features=required_features,
        disabled_features=explicit_disabled,
    )


def _resolve_build_output_path(source_path: str, build_dir: str,
                               output_text: str) -> str:
    if os.path.isabs(output_text):
        return os.path.abspath(output_text)
    normalized = output_text.replace("\\", os.sep).replace("/", os.sep)
    if _path_has_directory(normalized):
        return os.path.abspath(os.path.join(_source_dir(source_path), normalized))
    return os.path.abspath(os.path.join(build_dir, normalized))


def _default_exe_name(prog: Program, source_path: str) -> str:
    configured_output = _build_metadata_value(prog, "nativeOutput")
    if configured_output:
        return configured_output
    original_filename = prog.project_metadata.get("originalFilename")
    if original_filename:
        return original_filename
    internal_name = prog.project_metadata.get("internalName")
    if internal_name:
        base = internal_name
    elif prog.project_name:
        base = prog.project_name
    else:
        base = os.path.splitext(os.path.basename(source_path))[0] or "program"
    if os.path.splitext(base)[1]:
        return base
    return base + (".exe" if os.name == "nt" else "")


def _resolve_emit_exe_path(source_path: str, emit_exe: str,
                           prog: Program, build_dir: str) -> str:
    if emit_exe is None:
        return None
    if emit_exe == "":
        return _resolve_build_output_path(
            source_path, build_dir, _default_exe_name(prog, source_path))
    return _resolve_build_output_path(source_path, build_dir, emit_exe)


def _default_ir_sidecar_path(source_path: str, exe_path: str = None,
                             build_dir: str = None) -> str:
    if exe_path:
        basis = exe_path
        root, _ext = os.path.splitext(basis)
        return os.path.abspath((root or basis) + ".ll")
    target_dir = build_dir or _default_build_dir(source_path)
    source_stem = os.path.splitext(os.path.basename(source_path))[0] or "program"
    return os.path.abspath(os.path.join(target_dir, source_stem + ".ll"))


def _resolve_emit_ir_path(source_path: str, emit_ir: str = None,
                          emit_exe: str = None,
                          build_dir: str = None) -> str:
    if emit_ir is None:
        return None
    if emit_ir == "":
        return _default_ir_sidecar_path(source_path, emit_exe, build_dir)
    return _resolve_build_output_path(
        source_path, build_dir or _default_build_dir(source_path), emit_ir)


def _resolve_persisted_ir_path(source_path: str, emit_exe: str = None,
                               emit_ir: str = None,
                               persist_llvm_ir: str = "auto",
                               build_dir: str = None) -> str:
    if persist_llvm_ir == "no":
        return None
    resolved_emit_ir = _resolve_emit_ir_path(
        source_path, emit_ir=emit_ir, emit_exe=emit_exe, build_dir=build_dir)
    if resolved_emit_ir:
        return resolved_emit_ir
    if persist_llvm_ir == "yes":
        return _default_ir_sidecar_path(source_path, emit_exe, build_dir)
    return None


def jit_run(module_ir: str, opt_level: int = 2,
            emit_optimized_ir_to: str = None,
            cpu_config: CpuBuildConfig = None) -> int:
    llvm.initialize_native_target()
    llvm.initialize_native_asmprinter()
    mod = llvm.parse_assembly(module_ir)
    mod.verify()
    target = llvm.Target.from_default_triple()
    tm = target.create_target_machine(
        cpu=cpu_config.llvm_cpu if cpu_config is not None else "",
        features=cpu_config.llvm_features if cpu_config is not None else "",
        opt=opt_level)
    if opt_level > 0:
        _optimize(mod, tm, opt_level)
    if emit_optimized_ir_to:
        with open(emit_optimized_ir_to, "w", encoding="utf-8") as f:
            f.write(str(mod))
    engine = llvm.create_mcjit_compiler(mod, tm)
    engine.finalize_object()
    engine.run_static_constructors()
    addr = engine.get_function_address("main")
    cmain = ctypes.CFUNCTYPE(ctypes.c_int)(addr)
    return cmain()


def _collect_module_registry(source: str, source_path: str):
    """Read build-tape module registrations from ``source``.

    ``registerModule PROJECT MODULE_PATH "PATH"`` is the canonical project
    model row. ``moduleFolder MODULE_PATH "PATH"`` remains a compatibility
    alias for older build tapes. Paths resolve relative to the source file
    that declares the registry.
    """
    source_dir = os.path.dirname(os.path.abspath(source_path))
    registry = {}
    main_files = []
    for raw in source.splitlines():
        toks = tokenize_line(raw)
        if not toks or toks[0] == "#":
            continue
        verb = toks[0]
        args = toks[1:]
        module_name = None
        folder_text = None
        if verb == "registerModule" and len(args) >= 3:
            module_name = args[1]
            folder_text = _unwrap(args[2])
        elif verb == "moduleFolder" and len(args) >= 2:
            module_name = args[0]
            folder_text = _unwrap(args[1])
        elif verb == "mainFile" and len(args) >= 2:
            main_file = _unwrap(args[1])
            if isinstance(main_file, str) and main_file:
                main_files.append(main_file)
        if module_name is None or folder_text is None:
            continue
        if not isinstance(folder_text, str):
            continue
        if os.path.isabs(folder_text):
            registered_path = folder_text
        else:
            registered_path = os.path.join(source_dir, folder_text)
        registry[module_name] = os.path.abspath(registered_path)
    return registry, main_files


def _resolve_registered_module_file(module_name: str, registered_path: str,
                                    main_files) -> str:
    if os.path.isfile(registered_path):
        return registered_path
    if not os.path.isdir(registered_path):
        return None

    leaf_name = module_name.rsplit(".", 1)[-1]
    candidate_names = []
    candidate_names.extend(main_files)
    candidate_names.extend([
        "main.sem",
        "main.sscript",
        "index.sem",
        "index.sscript",
        f"{leaf_name}.sem",
        f"{leaf_name}.sscript",
    ])
    seen_names = set()
    for candidate_name in candidate_names:
        if candidate_name in seen_names:
            continue
        seen_names.add(candidate_name)
        candidate = os.path.join(registered_path, candidate_name)
        if os.path.isfile(candidate):
            return os.path.abspath(candidate)

    module_sources = []
    for entry_name in sorted(os.listdir(registered_path)):
        lower_name = entry_name.lower()
        if lower_name == "build.sem" or lower_name == "build.sscript":
            continue
        if lower_name.endswith(".test.sem") or lower_name.endswith(".test.sscript"):
            continue
        if lower_name.endswith(".sem") or lower_name.endswith(".sscript"):
            module_sources.append(os.path.join(registered_path, entry_name))
    if len(module_sources) == 1:
        return os.path.abspath(module_sources[0])
    return None


_STDLIB_PATH_ENV_VARS = ("SEMANTICSCRIPT_STD_PATH", "SEMSC_STD_PATH")


def _dedupe_existing_std_roots(candidates):
    roots = []
    seen = set()
    for candidate in candidates:
        if not candidate:
            continue
        root = os.path.abspath(candidate)
        marker = os.path.join(root, "module.sem")
        if not os.path.isfile(marker):
            continue
        norm = os.path.normcase(root)
        if norm in seen:
            continue
        seen.add(norm)
        roots.append(root)
    return roots


def _std_root_candidates_from_path(raw_path: str):
    if not raw_path:
        return []
    expanded = os.path.abspath(os.path.expandvars(os.path.expanduser(raw_path)))
    if os.path.isfile(expanded):
        expanded = os.path.dirname(expanded)
    return [
        expanded,
        os.path.join(expanded, "std"),
        os.path.join(expanded, "SemanticScript", "std"),
    ]


def _split_std_path_list(raw_value: str):
    if not raw_value:
        return []
    return [part for part in raw_value.split(os.pathsep) if part]


def _ancestor_std_candidates(start_dir: str):
    candidates = []
    current = os.path.abspath(start_dir)
    while True:
        candidates.append(os.path.join(current, "std"))
        candidates.append(os.path.join(current, "SemanticScript", "std"))
        parent = os.path.dirname(current)
        if parent == current:
            break
        current = parent
    return candidates


def _standard_library_roots(start_dir: str, explicit_std_paths=None):
    """Return std roots in override order.

    Standard modules are libraries, not build-tape projects. A valid root is
    any directory with `module.sem` at its top level and child module folders
    such as `html/main.sem`.
    """
    candidates = []
    for raw_path in explicit_std_paths or []:
        candidates.extend(_std_root_candidates_from_path(raw_path))
    for env_name in _STDLIB_PATH_ENV_VARS:
        for raw_path in _split_std_path_list(os.environ.get(env_name, "")):
            candidates.extend(_std_root_candidates_from_path(raw_path))
    candidates.extend(_ancestor_std_candidates(start_dir))
    cwd = os.getcwd()
    candidates.append(os.path.join(cwd, "std"))
    candidates.append(os.path.join(cwd, "SemanticScript", "std"))
    candidates.append(os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "std")))
    return _dedupe_existing_std_roots(candidates)


def _resolve_imports(source: str, source_path: str, explicit_std_paths=None) -> str:
    src_dir = os.path.dirname(os.path.abspath(source_path))
    def find_project_root(start_dir: str) -> str:
        current = os.path.abspath(start_dir)
        while True:
            if (
                os.path.isdir(os.path.join(current, "compiler"))
                and os.path.isdir(os.path.join(current, "std"))
            ):
                return current
            nested_semantic_script = os.path.join(current, "SemanticScript")
            if (
                os.path.isdir(os.path.join(nested_semantic_script, "compiler"))
                and os.path.isdir(os.path.join(nested_semantic_script, "std"))
            ):
                return nested_semantic_script
            parent = os.path.dirname(current)
            if parent == current:
                return os.path.abspath(start_dir)
            current = parent

    project_root = find_project_root(src_dir)
    stdlib_dirs = _standard_library_roots(src_dir, explicit_std_paths)
    module_registry, registry_main_files = _collect_module_registry(
        source, source_path)

    def find_standard_library_module(dotted: str):
        for stdlib_dir in stdlib_dirs:
            if dotted == "standard":
                relay = os.path.join(stdlib_dir, "module.sem")
                if os.path.isfile(relay):
                    return os.path.abspath(relay)
                resolved = _resolve_registered_module_file(
                    dotted, stdlib_dir, [])
                if resolved is not None:
                    return resolved
                continue
            if not dotted.startswith("standard."):
                return None
            rel_parts = dotted.split(".")[1:]
            candidate_dir = os.path.join(stdlib_dir, *rel_parts)
            if os.path.isdir(candidate_dir):
                resolved = _resolve_registered_module_file(
                    dotted, candidate_dir, [])
                if resolved is not None:
                    return resolved
            for ext in (".sscript", ".sem"):
                candidate = os.path.join(stdlib_dir, *rel_parts[:-1],
                                         rel_parts[-1] + ext)
                if os.path.isfile(candidate):
                    return os.path.abspath(candidate)
        return None

    seen: set = set()
    out_lines: list = []
    pending: list = [(source, src_dir)]

    def find_module_file(dotted: str, from_dir: str):
        registered_path = module_registry.get(dotted)
        if registered_path is not None:
            resolved = _resolve_registered_module_file(
                dotted, registered_path, registry_main_files)
            if resolved is None:
                raise SyntaxError(
                    f"importModule: registered module `{dotted}` points at "
                    f"`{registered_path}`, but no module source file could "
                    "be selected (expected main.sem, index.sem, the leaf "
                    "module file, or exactly one non-test .sem/.sscript)")
            return resolved
        standard_path = find_standard_library_module(dotted)
        if standard_path is not None:
            return standard_path
        if dotted == "standard" or dotted.startswith("standard."):
            searched = ", ".join(stdlib_dirs) if stdlib_dirs else "(no valid std roots)"
            raise SyntaxError(
                f"importModule: standard-library module `{dotted}` could not "
                f"be resolved; searched {searched}. Set --std-path or "
                "SEMANTICSCRIPT_STD_PATH to a std root containing module.sem.")
        rel_base = dotted.replace(".", os.sep)
        for base in (from_dir, *stdlib_dirs, project_root):
            candidate_dir = os.path.join(base, rel_base)
            if os.path.isdir(candidate_dir):
                resolved = _resolve_registered_module_file(
                    dotted, candidate_dir, [])
                if resolved is not None:
                    return resolved
        for ext in (".sscript", ".sem"):
            rel = rel_base + ext
            for base in (from_dir, *stdlib_dirs, project_root):
                candidate = os.path.join(base, rel)
                if os.path.isfile(candidate):
                    return candidate
        # No leaf fallback: a missing module must stay missing, not silently
        # bind to a same-leafname file in a sibling directory (e.g. importing
        # `standard.time` should not pick up `std/time.sscript`).
        return None

    header_skip = (
        "project ", "target ", "runtime ", "entry ", "module ",
        # Module-contract docs are owned by the module itself; when an
        # import inlines into a parent program, the contract rows would
        # otherwise be attributed to whichever operation was last open
        # in the parent — codegen then errors with "unhandled verb:
        # modulePurpose". Strip at inline time so the inlined source
        # carries only operation bodies + types + capabilities.
        "modulePurpose ", "moduleOwns ", "moduleDoesNotOwn ",
        "moduleWarning ", "moduleInvariant ", "moduleSecurity ",
        "moduleObservability ", "moduleDependency ",
    )

    def process(text: str, base_dir: str, is_root: bool):
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("importModule "):
                parts = stripped.split()
                if len(parts) >= 2:
                    dotted, _alias, _syntax = _parse_import_module_args(parts[1:])
                    path = find_module_file(dotted, base_dir)
                    if path is not None and path not in seen:
                        seen.add(path)
                        try:
                            with open(path, "r", encoding="utf-8") as f:
                                imported = f.read()
                        except OSError:
                            out_lines.append(line)
                            continue
                        process(imported, os.path.dirname(path), is_root=False)
                    if path is None:
                        out_lines.append(line)
                        continue
                    out_lines.append(line)
                    continue
            if not is_root and stripped.startswith(header_skip):
                continue
            out_lines.append(line)

    seen.add(os.path.abspath(source_path))
    process(source, src_dir, is_root=True)
    return "\n".join(out_lines) + "\n"


def _load_external_literals(prog: Program, source_path: str) -> None:
    """For every `literal NAME TYPE` whose `literalSource NAME "path"`
    resolves on disk, read the file's bytes and store them as the const's
    value. Paths are tried absolute first, then relative to the source
    file's directory. Files that fail to load leave the stub in place so
    the program still compiles."""
    src_dir = os.path.dirname(os.path.abspath(source_path)) if source_path else ""
    for name, meta in list(prog.hard_metadata.items()):
        sources = meta.get("literalSource") or []
        if not sources or name not in prog.consts:
            continue
        for row in sources:
            if not row:
                continue
            raw_path = row[0]
            if not isinstance(raw_path, str):
                continue
            candidates = []
            if os.path.isabs(raw_path):
                candidates.append(raw_path)
            else:
                if src_dir:
                    candidates.append(os.path.join(src_dir, raw_path))
                candidates.append(raw_path)
            loaded = None
            for candidate in candidates:
                try:
                    with open(candidate, "r", encoding="utf-8") as f:
                        loaded = f.read()
                    break
                except (IOError, OSError, UnicodeDecodeError):
                    continue
            if loaded is not None:
                typ, _stub = prog.consts[name]
                prog.consts[name] = (typ, loaded)
                break


def _native_http_link_inputs(prog: Program):
    if "webServer" not in prog.targets:
        return [], []
    if not any(server.routes for server in prog.web_servers.values()):
        return [], []

    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    runtime_source = os.path.join(
        repo_root,
        "SemanticScript",
        "runtime",
        "native_http",
        "sem_http_runtime.c",
    )
    link_args = []
    if os.name == "nt":
        link_args.append("-lws2_32")
    return [runtime_source], link_args


def _program_uses_gui_runtime(prog: Program) -> bool:
    if "windowsGui" in prog.targets or _build_metadata_value(prog, "targetRuntime") == "windowsGui":
        return True
    for op in prog.operations.values():
        for verb, args, _lineno in op.lines:
            if verb == "call" and len(args) >= 2 and args[1].startswith("gui."):
                return True
    return False


def _native_gui_link_inputs(prog: Program):
    if not _program_uses_gui_runtime(prog):
        return [], []

    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    runtime_source = os.path.join(
        repo_root,
        "SemanticScript",
        "runtime",
        "native_win32_gui",
        "sem_win32_gui_runtime.c",
    )
    link_args = []
    if os.name == "nt":
        link_args.extend(["-luser32", "-lgdi32", "-Xlinker", "/SUBSYSTEM:WINDOWS"])
    return [runtime_source], link_args


def _program_uses_bcrypt_runtime(prog: Program) -> bool:
    for op in prog.operations.values():
        for verb, args, _lineno in op.lines:
            if verb == "call" and len(args) >= 2 and args[1].startswith("bcrypt."):
                return True
    return False


def _native_bcrypt_link_inputs(prog: Program):
    if not _program_uses_bcrypt_runtime(prog):
        return [], []

    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    runtime_dir = os.path.join(repo_root, "SemanticScript", "runtime", "native_bcrypt")
    bcrypt_dir = os.path.join(repo_root, "third_party", "bcrypt")
    extra_sources = [
        os.path.join(runtime_dir, "sem_bcrypt_runtime.c"),
        os.path.join(bcrypt_dir, "crypt_blowfish.c"),
        os.path.join(bcrypt_dir, "crypt_gensalt.c"),
    ]
    link_args = [f"-I{bcrypt_dir}"]
    if os.name == "nt":
        link_args.append("-lbcrypt")
    return extra_sources, link_args


def _program_uses_sqlite_runtime(prog: Program) -> bool:
    """True if any operation contains a `sqlite.*` call. We trigger on
    real call sites rather than the dependency declaration because a
    program can import standard.sqlite, then conditionally not call any
    sqlite.* function; we don't want to pay the ~1.5 MB amalgamation
    link cost in that case."""
    for op in prog.operations.values():
        for verb, args, _lineno in op.lines:
            if verb != "call" or len(args) < 2:
                continue
            if args[1].startswith("sqlite."):
                return True
    return False


def _native_sqlite_link_inputs(prog: Program):
    """Return the (extra_sources, extra_link_args) tuple for linking the
    native_sqlite adapter + vendored amalgamation into an --emit-exe
    build. Mirrors `_native_http_link_inputs` but triggered by any
    sqlite.* call site rather than by `target webServer`.

    The amalgamation `sqlite3.c` is compiled with the same conservative
    defines documented in
    SemanticScript/runtime/native_sqlite/CMakeLists.txt — keep the two
    lists in sync if the build profile shifts. Without those defines the
    default sqlite3 build still works, but `SQLITE_OMIT_LOAD_EXTENSION`
    in particular is a security posture we want carried over to the
    semsc-driven build too.
    """
    if not _program_uses_sqlite_runtime(prog):
        return [], []

    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    runtime_dir = os.path.join(
        repo_root, "SemanticScript", "runtime", "native_sqlite")
    amalgamation_dir = os.path.join(repo_root, "third_party", "sqlite")
    extra_sources = [
        os.path.join(runtime_dir, "sem_sqlite_runtime.c"),
        os.path.join(amalgamation_dir, "sqlite3.c"),
    ]
    # `-I` flag so the adapter source can find sqlite3.h alongside the
    # vendored amalgamation without polluting the include search path of
    # the main translation unit.
    extra_link_args = [
        f"-I{amalgamation_dir}",
        "-DSQLITE_OMIT_LOAD_EXTENSION",
        "-DSQLITE_OMIT_DEPRECATED",
        "-DSQLITE_DQS=0",
        "-DSQLITE_THREADSAFE=2",
        "-DSQLITE_DEFAULT_MEMSTATUS=0",
        "-DSQLITE_USE_URI=1",
    ]
    if os.name != "nt":
        # POSIX needs libdl + libpthread + libm for sqlite3's runtime
        # feature detection. Windows links the equivalent functionality
        # via the Win32 personality compiled into sqlite3.c.
        extra_link_args.extend(["-ldl", "-lpthread", "-lm"])
    return extra_sources, extra_link_args


# Set of json.* call targets owned by the native_json runtime adapter
# (sem_json_runtime.h). Membership-only check — used by the linker
# trigger and intentionally excludes the older primitive json.encode.X
# / json.decode.X surfaces which are inlined as libc snprintf/atoll
# stubs and need no native runtime.
_NATIVE_JSON_TARGETS = frozenset({
    "json.createBuilder", "json.destroyBuilder",
    "json.objectOpen", "json.objectClose",
    "json.arrayOpen", "json.arrayClose",
    "json.fieldInt64", "json.fieldDouble", "json.fieldBool",
    "json.fieldString", "json.fieldNull",
    "json.elementInt64", "json.elementDouble", "json.elementBool",
    "json.elementString", "json.elementNull",
    "json.finishBuilder", "json.builderLength",
    "json.hasField", "json.findString",
    "json.findInt64", "json.findDouble", "json.findBool",
})


def _program_uses_json_runtime(prog: Program) -> bool:
    """True when any operation contains a call into the native_json
    runtime (the builder + finder API). Triggers separately from the
    primitive json.encode.* / json.decode.* dispatchers, which don't
    need the runtime linked in. Defer-only references count too —
    `defer X json.destroyBuilder builderName` is enough to pull the
    runtime in."""
    for op in prog.operations.values():
        for verb, args, _lineno in op.lines:
            if verb == "call" and len(args) >= 2 and args[1] in _NATIVE_JSON_TARGETS:
                return True
            if verb in ("defer", "deferLog", "deferAwaitLog") \
                    and len(args) >= 2 and args[1] in _NATIVE_JSON_TARGETS:
                return True
            if verb == "deferWhenExitLog" and len(args) >= 3 \
                    and args[2] in _NATIVE_JSON_TARGETS:
                return True
    return False


def _native_json_link_inputs(prog: Program):
    """Return (extra_sources, extra_link_args) for linking the
    native_json adapter into an --emit-exe build. No third-party
    amalgamation here — sem_json_runtime.c is self-contained C with
    no dependencies beyond libc, so the link cost is small and the
    only argument we need is the single source path."""
    if not _program_uses_json_runtime(prog):
        return [], []
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    runtime_source = os.path.join(
        repo_root, "SemanticScript", "runtime", "native_json",
        "sem_json_runtime.c")
    return [runtime_source], []


_NATIVE_TERMINAL_TARGETS = frozenset({
    "terminalEnableRaw",
    "terminalDisableRaw",
    "terminalReadKey",
    "terminalGetWindowRows",
    "terminalGetWindowCols",
    "terminalFirstArgument",
    "ss_terminal_enable_raw",
    "ss_terminal_disable_raw",
    "ss_terminal_read_key",
    "ss_terminal_get_window_rows",
    "ss_terminal_get_window_cols",
    "ss_terminal_first_argument",
})


def _program_uses_terminal_runtime(prog: Program) -> bool:
    """True when a program calls the generic native terminal adapter.

    This is link plumbing only. Editor behavior belongs in SemanticScript
    source or in the runtime adapter implementation, not in compiler lowering.
    """
    for op in prog.operations.values():
        for verb, args, _lineno in op.lines:
            if verb != "call" or len(args) < 2:
                continue
            target = args[1]
            if not target.startswith("c."):
                continue
            semantic_name = target[2:]
            c_symbol = libc_registry.resolve_c_symbol(semantic_name)
            if semantic_name in _NATIVE_TERMINAL_TARGETS or c_symbol in _NATIVE_TERMINAL_TARGETS:
                return True
    return False


def _native_terminal_link_inputs(prog: Program):
    if not _program_uses_terminal_runtime(prog):
        return [], []
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    runtime_source = os.path.join(
        repo_root, "SemanticScript", "runtime", "native_terminal",
        "sem_terminal_runtime.c")
    return [runtime_source], []


_NATIVE_BCRYPT_TARGETS = frozenset({
    "bcrypt.hashPassword",
    "bcrypt.verifyPassword",
    "bcrypt.randomBytes",
    "bcrypt.base64UrlEncode",
})


def _program_uses_bcrypt_runtime(prog: Program) -> bool:
    """True when any operation contains a call into the native_bcrypt
    runtime. The bcrypt linker pulls in the vendored crypt_blowfish.c
    (~32 KB compiled) + crypt_gensalt.c (~4 KB compiled) plus the
    adapter, so we want to skip the cost for apps that don't hash."""
    for op in prog.operations.values():
        for verb, args, _lineno in op.lines:
            if verb == "call" and len(args) >= 2 and args[1] in _NATIVE_BCRYPT_TARGETS:
                return True
    return False


def _native_bcrypt_link_inputs(prog: Program):
    """Return (extra_sources, extra_link_args) for linking the
    native_bcrypt adapter plus the vendored crypt_blowfish 1.3 source.
    On Windows the platform CSPRNG (BCryptGenRandom) lives in bcrypt.dll
    (Windows CNG, unrelated to bcrypt the algorithm — see the prologue
    of sem_bcrypt_runtime.c) and must be linked explicitly via
    `-lbcrypt`. POSIX targets reach the CSPRNG via getrandom(2) or
    /dev/urandom and need no extra link flag."""
    if not _program_uses_bcrypt_runtime(prog):
        return [], []
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    runtime_dir = os.path.join(
        repo_root, "SemanticScript", "runtime", "native_bcrypt")
    vendor_dir = os.path.join(repo_root, "third_party", "bcrypt")
    extra_sources = [
        os.path.join(runtime_dir, "sem_bcrypt_runtime.c"),
        os.path.join(vendor_dir, "crypt_blowfish.c"),
        os.path.join(vendor_dir, "crypt_gensalt.c"),
    ]
    extra_link_args = [f"-I{vendor_dir}"]
    if os.name == "nt":
        extra_link_args.append("-lbcrypt")
    return extra_sources, extra_link_args


def main():
    ap = argparse.ArgumentParser(
        prog="semsc",
        description=f"SemanticScript compiler (LLVM backend) v{__version__}",
    )
    ap.add_argument("source", nargs="?", help="path to .sscript or .sem source file")
    ap.add_argument("--version", action="version",
                    version=f"semsc {__version__}")
    ap.add_argument("--build-dir",
                    help=("directory for compiler-managed artifacts; relative "
                          "paths resolve beside the source file. This is an "
                          "exact directory override and cannot be combined "
                          "with --build-root or --build-folder-name"))
    ap.add_argument("--build-root",
                    help=("parent directory where the compiler should create "
                          "the managed build folder. Relative paths resolve "
                          "beside the source file"))
    ap.add_argument("--build-folder-name",
                    help=("name of the managed build folder created under "
                          "the source directory or --build-root; default "
                          "`build`"))
    ap.add_argument("--emit-ir", nargs="?", const="",
                    help=("write LLVM IR. With no path, writes to the "
                          "compiler-managed build directory"))
    ap.add_argument("--persist-llvm-ir", choices=("auto", "yes", "no"),
                    default=None,
                    help=("control whether generated LLVM IR is kept on disk. "
                          "auto keeps current behavior and persists only with "
                          "--emit-ir, yes writes a .ll sidecar when needed, "
                          "no disables IR persistence"))
    ap.add_argument("--run", action="store_true", help="JIT-execute main after compile")
    ap.add_argument("--lint", action="store_true",
                    help="run agent-safety lint pass and report diagnostics")
    ap.add_argument("--strict", action="store_true",
                    help="treat lint diagnostics as fatal")
    ap.add_argument("--parse-only", action="store_true",
                    help="parse the source, run lint (if requested), and exit without codegen")
    ap.add_argument("--opt-level", type=int, default=None,
                    help=("LLVM optimization level for JIT/AOT (0..3); "
                          "default 2 or optLevel from build.sem"))
    ap.add_argument("--emit-optimized-ir",
                    help="write the post-optimization LLVM IR to this path (after --opt-level passes run)")
    ap.add_argument("--cpu-baseline",
                    choices=tuple(sorted(_BUILD_TAPE_CHOICES["cpuBaseline"])),
                    default=None,
                    help=("CPU baseline for LLVM/clang lowering. Default "
                          "generic or cpuBaseline from build.sem"))
    ap.add_argument("--cpu-tune", default=None,
                    help=("CPU scheduling tune token for clang AOT builds, "
                          "for example generic, native, or alderlake"))
    ap.add_argument("--cpu-feature", action="append", default=None,
                    help=("CPU feature override. May be repeated. Shapes: "
                          "FEATURE=on, FEATURE=off, +FEATURE, -FEATURE"))
    ap.add_argument("--cpu-feature-check",
                    choices=tuple(sorted(_BUILD_TAPE_CHOICES["cpuFeatureCheck"])),
                    default=None,
                    help=("host CPU feature check policy for build-time CPU "
                          "flags: auto, require, warn, or off"))
    ap.add_argument("--emit-exe", nargs="?", const="",
                    help="ahead-of-time compile to a native executable at this path "
                         "(uses clang on PATH or $SEMSC_CLANG to link). With no "
                         "path, writes to the compiler-managed build directory")
    ap.add_argument("--build-file", default=None,
                    help="merge build-time declarations (project metadata, icon "
                         "registry) from this .sem / .sscript file into the main "
                         "Program before codegen. Conflicting redeclarations are "
                         "rejected.")
    ap.add_argument("--std-path", action="append", default=None,
                    help=("standard-library root override. May be repeated. "
                          "Accepts a std root containing module.sem, a "
                          "SemanticScript root containing std/, or a repo root "
                          "containing SemanticScript/std. Environment fallbacks: "
                          "SEMANTICSCRIPT_STD_PATH or SEMSC_STD_PATH."))
    ap.add_argument("--keep-resources", dest="keep_resources",
                    action="store_true", default=None,
                    help="retain the intermediate Windows resource files "
                         "(.rc/.res/.ico) next to the executable for debugging. "
                         "Default behavior is to write them to a temp directory "
                         "and delete after linking — the resource bytes survive "
                         "only inside the .exe's PE resource section. Can also "
                         "be set in build.sem via `keepResources PROJECT yes`.")
    ap.add_argument("--resource-dir", dest="resource_dir", default=None,
                    help="explicit directory for intermediate resource files. "
                         "Implies --keep-resources. Path is resolved relative "
                         "to the source file's directory unless absolute. Can "
                         "also be set in build.sem via "
                         "`resourcesDir PROJECT \"path\"`.")
    ap.add_argument("--quiet", action="store_true",
                    help="suppress informational messages on success")
    ap.add_argument("--diagnostics-format", choices=("agent", "json", "raw"),
                    default="agent",
                    help="format for compiler/backend errors; default agent")
    ap.add_argument("--build-profile", choices=("dev", "prod"), default=None,
                    help=("compiled runtime profile; dev embeds SemanticScript "
                          "panic context, prod hides source context and traps; "
                          "default dev"))
    ap.add_argument("--runtime-checks", choices=("off", "traps", "panic"),
                    default=None,
                    help=("override runtime safety checks: off=no checks, "
                          "traps=llvm.trap only, panic=static SemanticScript "
                          "message then llvm.trap. Defaults to panic for "
                          "--build-profile dev and traps for --build-profile prod"))
    args = ap.parse_args()

    if not args.source:
        ap.error("the following arguments are required: source")

    try:
        with open(args.source, "r", encoding="utf-8") as f:
            source = f.read()
    except OSError as e:
        print(f"semsc: cannot read source file: {e}", file=sys.stderr)
        sys.exit(2)

    source_ext = os.path.splitext(args.source)[1].lower()
    if source_ext not in (".sscript", ".sem"):
        print("semsc: source file must use .sscript or .sem", file=sys.stderr)
        sys.exit(2)

    if _is_build_tape_path(args.source) or _looks_like_build_tape(source):
        try:
            _validate_build_tape_source(source, args.source)
        except SyntaxError as e:
            print(f"semsc: build-tape error in {args.source}: {e}", file=sys.stderr)
            sys.exit(2)

    try:
        # Resolve cross-file imports. `importModule DOTTED.PATH [as ALIAS]`
        # lines reference module files. Build tapes resolve registered
        # modules before legacy filesystem/std-lib fallback. Imported file
        # content is inlined; transitive imports are followed with cycle
        # detection.
        source = _resolve_imports(source, args.source, args.std_path)
        prog = parse(source)
        prog.source_path = args.source
    except SyntaxError as e:
        import traceback as _tb
        print(f"semsc: parse error in {args.source}: {e}", file=sys.stderr)
        if os.environ.get("SEMSC_TRACEBACK"):
            _tb.print_exc(file=sys.stderr)
        sys.exit(2)

    if args.build_file:
        try:
            _merge_build_file(prog, args.build_file, args.std_path)
        except SyntaxError as e:
            print(f"semsc: build-file error in {args.build_file}: {e}",
                  file=sys.stderr)
            sys.exit(2)

    # External literal asset loading. `literal NAME TYPE` declares the
    # binding; `literalSource NAME "path"` names the bytes' source file.
    # When both are present and the path resolves (absolute, or relative
    # to the source file's directory), inline the file content as the
    # literal's const value so name references see the actual bytes.
    _load_external_literals(prog, args.source)

    if args.lint or args.strict:
        lint(prog, strict=args.strict)

    try:
        build_dir_override = args.build_dir
        build_root_override = args.build_root
        build_folder_override = args.build_folder_name
        if build_dir_override is None:
            build_dir_override = _build_metadata_value(prog, "buildDir")
        if build_root_override is None:
            build_root_override = _build_metadata_value(prog, "buildRoot")
        if build_folder_override is None:
            build_folder_override = _build_metadata_value(prog, "buildFolderName")
        build_dir = _resolve_build_dir(
            args.source,
            build_dir=build_dir_override,
            build_root=build_root_override,
            build_folder_name=build_folder_override)
        build_profile = _resolve_choice_from_build(
            prog, "buildProfile", args.build_profile, "dev", {"dev", "prod"})
        persist_llvm_ir = _resolve_choice_from_build(
            prog, "persistLlvmIr", args.persist_llvm_ir, "auto",
            {"auto", "yes", "no"})
        opt_level_raw = args.opt_level
        if opt_level_raw is None:
            opt_level_raw = _build_metadata_value(prog, "optLevel")
        opt_level = int(opt_level_raw) if opt_level_raw is not None else 2
        if opt_level < 0 or opt_level > 3:
            raise ValueError("optLevel: value must be in range 0..3")
        cpu_config = _resolve_cpu_build_config(
            prog,
            cpu_baseline=args.cpu_baseline,
            cpu_tune=args.cpu_tune,
            cpu_feature_overrides=args.cpu_feature,
            cpu_feature_check=args.cpu_feature_check)
        runtime_checks_override = args.runtime_checks
        if runtime_checks_override is None:
            runtime_checks_override = _build_metadata_value(prog, "runtimeChecks")
            if runtime_checks_override is not None and runtime_checks_override not in {"off", "traps", "panic"}:
                raise ValueError(
                    "runtimeChecks: "
                    f"`{runtime_checks_override}` is not valid; expected one "
                    "of ['off', 'panic', 'traps']")
        runtime_checks = _resolve_runtime_checks(
            build_profile, runtime_checks_override)
        emit_exe_path = _resolve_emit_exe_path(
            args.source, args.emit_exe, prog, build_dir)
        ir_sidecar_basis_path = emit_exe_path
        if ir_sidecar_basis_path is None and (
            _build_metadata_value(prog, "nativeOutput")
            or prog.project_metadata.get("originalFilename")
        ):
            ir_sidecar_basis_path = _resolve_emit_exe_path(
                args.source, "", prog, build_dir)
        emit_ir_request = args.emit_ir
        if emit_ir_request is None:
            build_emit_ir = _build_metadata_value(prog, "emitLlvmIr")
            build_ir_output = _build_metadata_value(prog, "llvmIrOutput")
            if build_ir_output:
                emit_ir_request = build_ir_output
            elif build_emit_ir == "yes":
                emit_ir_request = ""
        if emit_ir_request is not None and persist_llvm_ir == "no":
            ap.error("--emit-ir cannot be used with --persist-llvm-ir no")
        persisted_ir_path = _resolve_persisted_ir_path(
            args.source,
            emit_exe=ir_sidecar_basis_path,
            emit_ir=emit_ir_request,
            persist_llvm_ir=persist_llvm_ir,
            build_dir=build_dir)
        emit_optimized_ir_path = args.emit_optimized_ir
        if emit_optimized_ir_path is None:
            build_optimized_ir_output = _build_metadata_value(prog, "optimizedLlvmIrOutput")
            build_emit_optimized_ir = _build_metadata_value(prog, "emitOptimizedLlvmIr")
            if build_optimized_ir_output:
                emit_optimized_ir_path = _resolve_build_output_path(
                    args.source, build_dir, build_optimized_ir_output)
            elif build_emit_optimized_ir == "yes":
                source_stem = os.path.splitext(os.path.basename(args.source))[0] or "program"
                emit_optimized_ir_path = _resolve_build_output_path(
                    args.source, build_dir, source_stem + ".opt.ll")
    except ValueError as e:
        ap.error(str(e))

    if args.parse_only:
        if not args.quiet:
            print(_render_success_message(
                "SSOK000",
                "SemanticScript parse complete",
                args.source,
                details=[
                    ("phase", "parse"),
                    ("lint", "enabled" if (args.lint or args.strict) else "not requested"),
                ],
            ))
        return

    try:
        cg = Codegen(prog, runtime_checks=runtime_checks)
        mod = cg.compile()
    except CompilerDiagnosticError as e:
        print(e.diagnostic.render(args.diagnostics_format), file=sys.stderr)
        if os.environ.get("SEMSC_TRACEBACK"):
            import traceback as _tb
            _tb.print_exc(file=sys.stderr)
        sys.exit(3)
    except NotImplementedError as e:
        print(f"semsc: {e}", file=sys.stderr)
        sys.exit(3)
    except Exception as e:
        import traceback as _tb
        diagnostic = _diagnostic_from_codegen_error(prog, e)
        print(diagnostic.render(args.diagnostics_format), file=sys.stderr)
        if os.environ.get("SEMSC_TRACEBACK"):
            _tb.print_exc(file=sys.stderr)
        sys.exit(3)
    ir_text = str(mod)

    did_output = False
    outputs = []
    if persisted_ir_path:
        persisted_ir_dir = os.path.dirname(os.path.abspath(persisted_ir_path))
        if persisted_ir_dir:
            os.makedirs(persisted_ir_dir, exist_ok=True)
        with open(persisted_ir_path, "w", encoding="utf-8") as f:
            f.write(ir_text)
        did_output = True
        outputs.append(("llvm ir", persisted_ir_path))

    if emit_exe_path:
        try:
            extra_sources, extra_link_args = _native_http_link_inputs(prog)
            sqlite_sources, sqlite_link_args = _native_sqlite_link_inputs(prog)
            if sqlite_sources:
                extra_sources = list(extra_sources or []) + sqlite_sources
                extra_link_args = list(extra_link_args or []) + sqlite_link_args
            json_sources, json_link_args = _native_json_link_inputs(prog)
            if json_sources:
                extra_sources = list(extra_sources or []) + json_sources
                extra_link_args = list(extra_link_args or []) + json_link_args
            terminal_sources, terminal_link_args = _native_terminal_link_inputs(prog)
            if terminal_sources:
                extra_sources = list(extra_sources or []) + terminal_sources
                extra_link_args = list(extra_link_args or []) + terminal_link_args
            bcrypt_sources, bcrypt_link_args = _native_bcrypt_link_inputs(prog)
            if bcrypt_sources:
                extra_sources = list(extra_sources or []) + bcrypt_sources
                extra_link_args = list(extra_link_args or []) + bcrypt_link_args
            gui_sources, gui_link_args = _native_gui_link_inputs(prog)
            if gui_sources:
                extra_sources = list(extra_sources or []) + gui_sources
                extra_link_args = list(extra_link_args or []) + gui_link_args
            resolved_resource_dir = _resolve_resource_dir(
                prog, args.source, build_dir,
                args.keep_resources, args.resource_dir)
            resource_path, resource_temp_files = _compile_windows_resource(
                prog, emit_exe_path, resource_dir=resolved_resource_dir)
            if resource_path is not None:
                extra_sources = list(extra_sources or [])
                extra_sources.append(resource_path)
                outputs.append(("resource", resource_path))
            try:
                emit_executable(ir_text, emit_exe_path, opt_level=opt_level,
                                provenance=cg.provenance,
                                diagnostics_format=args.diagnostics_format,
                                extra_sources=extra_sources,
                                extra_link_args=extra_link_args,
                                link_work_dir=build_dir,
                                link_ir_path=persisted_ir_path,
                                cpu_config=cpu_config)
            finally:
                for path in resource_temp_files:
                    try:
                        os.unlink(path)
                    except OSError:
                        pass
        except CompilerDiagnosticError as e:
            print(e.diagnostic.render(args.diagnostics_format), file=sys.stderr)
            sys.exit(4)
        except RuntimeError as e:
            print(f"semsc: {e}", file=sys.stderr)
            sys.exit(4)
        did_output = True
        outputs.append(("executable", emit_exe_path))

    if did_output and not args.quiet and not args.run:
        print(_render_success_message(
            "SSOK001",
            "SemanticScript compile complete",
            args.source,
            outputs=outputs,
            details=[
                ("profile", build_profile),
                ("runtime checks", runtime_checks),
                ("llvm ir", "persisted" if persisted_ir_path else "discarded"),
                ("build dir", build_dir if did_output else ""),
                ("opt level", opt_level),
                ("cpu", cpu_config.summary()),
            ],
        ))

    if args.run:
        rc = jit_run(ir_text, opt_level=opt_level,
                     emit_optimized_ir_to=emit_optimized_ir_path,
                     cpu_config=cpu_config)
        sys.exit(rc)

    if not did_output and not args.quiet:
        # Reaching this branch means the source compiled successfully but
        # no output flag was given. Tell the user what they could do next
        # instead of exiting silently.
        print(_render_success_message(
            "SSOK001",
            "SemanticScript compile complete",
            args.source,
            details=[
                ("profile", build_profile),
                ("runtime checks", runtime_checks),
                ("llvm ir", "persisted" if persisted_ir_path else "discarded"),
                ("opt level", opt_level),
                ("cpu", cpu_config.summary()),
            ],
            outputs=[("artifact", "none requested")],
            next_steps=[
                "Use --emit-ir PATH, --emit-exe PATH, or --run.",
            ],
        ))


if __name__ == "__main__":
    main()
