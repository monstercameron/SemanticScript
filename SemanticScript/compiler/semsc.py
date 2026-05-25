"""
semsc - the SemanticScript compiler.

Implements a faithful subset of the SemanticScript language (per
../../docs/semantic-script.md and ../../docs/ast.md). Compiles SemanticScript
semantic tape to LLVM IR via llvmlite, then either JIT-executes via MCJIT or
writes the IR to a .ll file.

Top-level verbs:
  project, target, runtime, entry, module
  type            type alias
  error           error category
  errorCase       error variant
  storage         scoped storage declaration
  operation       operation declaration

Operation header verbs include:
  input operation, output operation, effect, memory, async,
  authority, purpose operation, invariant operation, warning

Body rows include:
  Decls:     storage local/module
  Calls:     call, argument, timeout, cancelOn, run, runChecked, start, await
  Bind:      bind value, bind ok, bind error
  Ignore:    ignore value, ignore ok, ignore error, ignore void
  Errors:    makeError
  Mutation:  set memory, set storage
  Control:   label, branch if, branch error, branch else, jump
  Returns:   return value, return ok, return error, return void

bind value is for infallible values; fallible calls use explicit success/error
disposition (bind ok or ignore ok, plus bind error and branch error) or the
compact runChecked row. branch if condition X target L jumps to L on true and
falls through on false unless followed by branch else target ... .

External call targets:
  console.writeLine          -> puts(i8*)                 -> i32 (negative on failure)
  console.writeIntegerLine   -> printf("%lld\n", i64)     -> i32 (negative on failure)
  math.addInt64                -> i64 (a + b)
  math.subtractInt64           -> i64 (a - b)              (alias: math.subInt64)
  math.multiplyInt64           -> i64 (a * b)              (alias: math.mulInt64)
  math.divideInt64             -> i64 (a sdiv b)           (alias: math.divInt64)
  math.moduloInt64             -> i64 (a srem b)           (alias: math.modInt64)
  math.equalInt64              -> i1                        (alias: math.eqInt64)
  math.notEqualInt64           -> i1                        (alias: math.neInt64)
  math.lessThanInt64           -> i1                        (alias: math.ltInt64)
  math.lessThanOrEqualInt64    -> i1                        (alias: math.leInt64)
  math.greaterThanInt64        -> i1                        (alias: math.gtInt64)
  math.greaterThanOrEqualInt64 -> i1                        (alias: math.geInt64)
"""

import argparse
import ctypes
import hashlib
import json
import os
import re
import shlex
import sys
import time
from dataclasses import dataclass, field
from llvmlite import ir
import llvmlite.binding as llvm

# Make sibling/shared-module imports work when the compiler is invoked by path.
_COMPILER_DIR = os.path.dirname(os.path.abspath(__file__))
_SEMANTICSCRIPT_ROOT = os.path.dirname(_COMPILER_DIR)
for _import_path in (_COMPILER_DIR, _SEMANTICSCRIPT_ROOT):
    if _import_path not in sys.path:
        sys.path.insert(0, _import_path)
import libc_registry
import semdeps
from shared.call_contracts import (
    KNOWN_FALLIBLE_CALL_TARGETS,
    MIDDLEWARE_CONTROL_CASES,
    MIDDLEWARE_CONTROL_TYPE,
    SUPPORTED_HTTP_ROUTE_METHODS,
    fallibility_kind,
    is_supported_route_method,
)
from shared.repo_version import read_repo_version

__version__ = read_repo_version()


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
        self.field_json_names = {} # field_name -> JSON object key
        self.field_json_omit_when = {} # field_name -> empty|null|false|zero


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
        self.not_found_handler = None
        self.method_not_allowed_handler = None


class HtmlTemplate:
    def __init__(self, name, decl_line=0):
        self.name = name
        self.decl_line = decl_line
        self.args = []            # list[(arg_name, arg_type, lineno)]
        self.body_lines = []      # list[(body_text_without_base_indent, lineno)]
        self.body_line = 0


class JsonBodyLiteral:
    def __init__(self, name, storage_type, canonical_text, decl_line, body_lines):
        self.name = name
        self.storage_type = storage_type
        self.canonical_text = canonical_text
        self.decl_line = decl_line
        self.body_lines = body_lines  # list[(raw_body_text, lineno)]


class SqlBodyLiteral:
    def __init__(self, name, storage_type, sql_text, statement_kind,
                 placeholder_count, statement_count, decl_line, body_lines):
        self.name = name
        self.storage_type = storage_type
        self.sql_text = sql_text
        self.statement_kind = statement_kind
        self.placeholder_count = placeholder_count
        self.statement_count = statement_count
        self.decl_line = decl_line
        self.body_lines = body_lines  # list[(body_text_without_base_indent, lineno)]


class Program:
    def __init__(self):
        self.source_path = ""
        self.source_lines = {}        # line -> raw source text in parsed stream
        self.source_origins = {}      # line -> original source path/line before import flattening
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
        # icons. See docs/reference/syntax-inventory.md for the row schemas.
        self.icon_role_definitions = {}   # role_token -> description text
        self.icon_groups = {}             # group_name -> dict(role, purpose, line)
        self.icon_images = {}             # image_name -> dict(group, path, format, width, height, scale, depth, platform, purpose, line)
        self.consts = {}              # name -> (type, value)
        self.worker_pools = {}        # module-scope workerPool name -> line
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
        self.json_bodies = []          # list[JsonBodyLiteral]
        self.sql_bodies = []           # list[SqlBodyLiteral]
        self.record_json_constants = {} # name -> {recordType, fields}
        self.sql_constants = {}        # name -> {statementKind, placeholderCount, statementCount}
        self.storage_declarations = [] # parsed storage rows for jsonBody binding
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
        self.language_modes = []       # list[str]  -- e.g. ["strictExecutable"]
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
    "label", "set",
    "call", "argument", "timeout", "cancelOn", "run", "runChecked", "start", "await",
    "case", "done",
    "bind", "ignore",
    "makeError",
    "branch", "jump",
    "return",
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
    "operationBody", "runtimeBinding", "runtimeBindingPrecondition",
    "runtimeBindingFailure", "runtimeBindingAsyncStart",
    "runtimeBindingAsyncAwait", "intrinsicName",
    "useCapability",
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
    # canonical opt-out. See docs/reference/syntax-inventory.md#pinsNullBodyFailurePath.
    "pinsNullBodyFailurePath",
    # `responseBodyForwarder OP bodyArgName` — declares that an operation
    # forwards its `bodyArgName` input straight into an http.response*
    # writer (or another forwarder), making it part of the transitive
    # response-body-writer set. Replaces a `body` arg-name string match.
    "responseBodyForwarder",
    # `rationale CALL "text"` — operation-body counterpart to the
    # `# rationale:` typed comment; explicitly attaches a rationale to a
    # specific call site so SS3603 (and other rules) can cite it without
    # relying on comment proximity. See docs/reference/syntax-inventory.md#rationale.
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


_OLD_SYNTAX_VERBS = {
    "importModule",
    "memoryHeap",
    "arg",
    "bindOk",
    "bindError",
    "branchIf",
    "branchIfError",
    "returnValue",
    "returnOk",
    "returnError",
    "returnVoid",
    "ignoreValue",
    "ignoreOk",
    "ignoreError",
    "modulePurpose",
    "moduleInvariant",
    "htmlTemplate",
    "htmlArg",
    "htmlBody",
    "var",
    "let",
    "const",
}

_AUTHORITY_ACTIONS = {
    "read", "write", "append", "open", "close", "allocate", "free",
    "observe", "log", "execute", "connect", "send", "receive", "delete",
    "create", "update", "network", "configure",
}


def _canonicalize_syntax_row(verb, args, lineno):
    """Apply the syntax-cutover row shapes before permissive parsing.

    The compiler used to fall back to storing unknown lowercase verbs as
    metadata. For the syntax cutover, replaced rows must fail here instead of
    being hidden by that fallback. Returned rows are canonical semantic rows;
    variant-bearing rows keep their variant token in args for lowering.
    """
    if isinstance(verb, str) and (verb.startswith("@") or verb.startswith("#")):
        raise SyntaxError(
            f"line {lineno}: sigil-prefixed row verbs are not valid SemanticScript syntax")
    if isinstance(verb, str) and "." in verb:
        raise SyntaxError(
            f"line {lineno}: dotted row verb `{verb}` is not valid; keep dots in value/path tokens")
    if any(isinstance(tok, str) and "=" in tok for tok in [verb, *args]):
        raise SyntaxError(
            f"line {lineno}: equals-sign key/value rows are not valid SemanticScript syntax")
    if verb in _OLD_SYNTAX_VERBS:
        raise SyntaxError(
            f"line {lineno}: old SemanticScript syntax `{verb}` is rejected; run the syntax converter")

    if verb == "import":
        if len(args) != 2:
            raise SyntaxError(
                f"line {lineno}: import requires: import ALIAS MODULE_PATH")
        return verb, args

    if verb == "html":
        if len(args) == 2 and args[0] == "template":
            return "htmlTemplate", [args[1]]
        if len(args) == 3 and args[0] == "body" and args[1] == "template":
            return "htmlBody", [args[2]]
        raise SyntaxError(
            f"line {lineno}: html requires: html template NAME, "
            "html body template TEMPLATE")

    if verb == "type":
        if len(args) >= 2 and args[1] == "Result":
            raise SyntaxError(
                f"line {lineno}: old result type syntax is rejected; use "
                "type NAME result ok OK_TYPE error ERROR_TYPE")
        if len(args) >= 2 and args[1] == "result":
            if len(args) != 6 or args[2] != "ok" or args[4] != "error":
                raise SyntaxError(
                    f"line {lineno}: result type requires: "
                    "type NAME result ok OK_TYPE error ERROR_TYPE")
            return verb, [args[0], "Result", args[3], args[5]]
        return verb, args

    if verb == "input":
        if len(args) != 4 or args[0] != "operation":
            raise SyntaxError(
                f"line {lineno}: input requires: input operation OPERATION NAME TYPE")
        return verb, [args[1], args[2], args[3]]

    if verb == "output":
        if len(args) == 5 and args[0] == "operation" and args[2] == "Result":
            return verb, [args[1], args[2], args[3], args[4]]
        if len(args) != 3 or args[0] != "operation":
            raise SyntaxError(
                f"line {lineno}: output requires: output operation OPERATION TYPE")
        return verb, [args[1], args[2]]

    if verb in ("purpose", "invariant"):
        if len(args) < 3 or args[0] not in ("module", "operation"):
            raise SyntaxError(
                f"line {lineno}: {verb} requires: "
                f"{verb} module|operation SUBJECT \"TEXT\"")
        return verb, [args[1], *args[2:]]

    if verb == "memory":
        if len(args) < 3:
            raise SyntaxError(
                f"line {lineno}: memory requires: memory OPERATION SUBKIND ...")
        subkind = args[1]
        if subkind in ("mutable", "immutable"):
            if len(args) < 5:
                raise SyntaxError(
                    f"line {lineno}: memory {subkind} requires: "
                    f"memory OPERATION {subkind} NAME TYPE VALUE")
        elif subkind == "heap":
            if len(args) != 3:
                raise SyntaxError(
                    f"line {lineno}: memory heap requires: memory OPERATION heap MODE")
        elif subkind == "arena":
            if len(args) != 3:
                raise SyntaxError(
                    f"line {lineno}: memory arena requires: memory OPERATION arena SCOPE")
        elif subkind == "stack":
            if len(args) != 4 or args[2] != "max":
                raise SyntaxError(
                    f"line {lineno}: memory stack requires: memory OPERATION stack max SIZE")
        else:
            raise SyntaxError(
                f"line {lineno}: unknown memory subkind `{subkind}`")
        return verb, args

    if verb == "storage":
        if len(args) < 4:
            raise SyntaxError(
                f"line {lineno}: storage requires: storage SCOPE mutable|immutable NAME TYPE [VALUE]")
        if args[1] not in ("mutable", "immutable"):
            raise SyntaxError(
                f"line {lineno}: storage mutability must be mutable or immutable")
        return verb, args

    if verb == "authority":
        if len(args) != 3:
            raise SyntaxError(
                f"line {lineno}: authority requires: authority OPERATION ACTION PATH")
        if args[2] in _AUTHORITY_ACTIONS and args[1] not in _AUTHORITY_ACTIONS:
            raise SyntaxError(
                f"line {lineno}: old authority order is rejected; use authority OPERATION ACTION PATH")
        if args[1] not in _AUTHORITY_ACTIONS:
            raise SyntaxError(
                f"line {lineno}: authority action `{args[1]}` is not recognized")
        return verb, args

    if verb == "set":
        if len(args) != 3 or args[0] not in ("memory", "storage"):
            raise SyntaxError(
                f"line {lineno}: set requires: set memory|storage NAME VALUE")
        return verb, args

    if verb == "argument":
        if len(args) != 4:
            raise SyntaxError(
                f"line {lineno}: argument requires: argument CALL PARAM TYPE VALUE")
        return verb, args

    if verb == "bind":
        if len(args) != 4 or args[0] not in ("value", "ok", "error"):
            raise SyntaxError(
                f"line {lineno}: bind requires: bind value|ok|error NAME TYPE CALL")
        return verb, args

    if verb == "branch":
        if not args:
            raise SyntaxError(
                f"line {lineno}: branch requires: branch if|error|else ...")
        if args[0] == "if":
            if len(args) != 5 or args[1] != "condition" or args[3] != "target":
                raise SyntaxError(
                    f"line {lineno}: branch if requires: "
                    "branch if condition CONDITION target LABEL")
        elif args[0] == "error":
            if len(args) != 5 or args[1] != "source" or args[3] != "target":
                raise SyntaxError(
                    f"line {lineno}: branch error requires: "
                    "branch error source CALL target LABEL")
        elif args[0] == "else":
            if len(args) != 3 or args[1] != "target":
                raise SyntaxError(
                    f"line {lineno}: branch else requires: branch else target LABEL")
        else:
            raise SyntaxError(
                f"line {lineno}: bare branch is rejected; use branch if/error/else or jump target LABEL")
        return verb, args

    if verb == "jump":
        if len(args) != 2 or args[0] != "target":
            raise SyntaxError(
                f"line {lineno}: jump requires: jump target LABEL")
        return verb, args

    if verb == "return":
        if not args or args[0] not in ("value", "ok", "error", "void"):
            raise SyntaxError(
                f"line {lineno}: return requires: return value|ok|error VALUE or return void")
        if args[0] == "void":
            if len(args) != 1:
                raise SyntaxError(f"line {lineno}: return void takes no payload")
        elif len(args) != 2:
            raise SyntaxError(
                f"line {lineno}: return {args[0]} requires exactly one payload")
        return verb, args

    if verb == "ignore":
        if not args or args[0] not in ("value", "ok", "error", "void"):
            raise SyntaxError(
                f"line {lineno}: ignore requires: ignore value|ok|error|void ...")
        if args[0] in ("value", "ok"):
            if len(args) != 5 or args[1] != "source" or args[3] != "type":
                raise SyntaxError(
                    f"line {lineno}: ignore {args[0]} requires: "
                    f"ignore {args[0]} source CALL type TYPE")
            if args[4] in ("Void", "Void"):
                raise SyntaxError(
                    f"line {lineno}: ignore {args[0]} cannot discard a Void payload; use ignore void source CALL")
        elif args[0] == "error":
            if len(args) != 3 or args[1] != "source":
                raise SyntaxError(
                    f"line {lineno}: ignore error requires: ignore error source CALL")
        elif args[0] == "void":
            if len(args) != 3 or args[1] != "source":
                raise SyntaxError(
                    f"line {lineno}: ignore void requires: ignore void source CALL")
        return verb, args

    return verb, args


# Closed set of recognized `mode` declarations. See docs/ast.md §10.
_KNOWN_MODES = {
    "capturedOutputReplay",
}

_KNOWN_LANGUAGE_MODES = {
    "strictExecutable",
    "refinedSyntax",
    # `permissiveExecutable` is the explicit opt-out from the strict
    # executable wall. It exists so that research and legacy files can
    # compile without claiming strictness; strict is the default
    # for every other source.
    "permissiveExecutable",
}

_INCOMPATIBLE_LANGUAGE_MODES = {
    frozenset(("strictExecutable", "refinedSyntax")),
    frozenset(("strictExecutable", "permissiveExecutable")),
    frozenset(("refinedSyntax", "permissiveExecutable")),
}

_MODULE_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)*$")
_HTML_HOLE_REFERENCE_RE = re.compile(
    r"\{\s*([A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*)\s*\}")
_HTML_BRACE_CONTENT_RE = re.compile(r"\{([^{}\n]*)\}")
_HTML_RAW_TEXT_RE = re.compile(
    r"<(style|script)\b[^>]*>.*?</\1\s*>",
    re.IGNORECASE | re.DOTALL,
)
_HTML_ATTR_VALUE_PREFIX_RE = re.compile(
    r"([A-Za-z_:][A-Za-z0-9_:.-]*)\s*=\s*([\"'])[^\"']*$")
_HTML_ATTR_NAME_RE = re.compile(r"[A-Za-z_:][A-Za-z0-9_:.-]*")
_HTML_URL_ATTRS = {
    "action",
    "formaction",
    "href",
    "poster",
    "src",
}
_HTML_BOOLEAN_ATTRS = {
    "allowfullscreen", "async", "autofocus", "autoplay", "checked",
    "controls", "default", "defer", "disabled", "formnovalidate",
    "hidden", "inert", "ismap", "itemscope", "loop", "multiple",
    "muted", "nomodule", "novalidate", "open", "playsinline",
    "readonly", "required", "reversed", "selected",
}
_HTML_VOID_ELEMENTS = {
    "area", "base", "br", "col", "embed", "hr", "img", "input",
    "link", "meta", "param", "source", "track", "wbr",
}
_HTML_TRUST_TYPES = {
    "HtmlFragment",
    "HtmlTrustedFragment",
    "HtmlDocument",
}
_HTML_STRING_TYPES = {
    "String",
}
_HTML_FRAGMENT_TYPES = {
    "HtmlFragment",
    "HtmlTrustedFragment",
    "HtmlDocument",
}
_HTML_HYDRATE_PREFIX = "html.hydrate."
_SQL_BODY_VERBS = {"sqlBody"}
_SQL_HOLE_RE = re.compile(r"\{[^{}\n]*\}")

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
    "asyncRuntime", "guiBackend",
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
    "asyncRuntime", "guiBackend",
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
    "asyncRuntime": {"none", "libuv"},
    "guiBackend": {"win32", "winui3"},
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
_GITHUB_HOST = "github.com"
_GITHUB_OWNER_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?$")
_GITHUB_REPO_RE = re.compile(r"^[A-Za-z0-9._-]+$")


def _is_https_url(value: str) -> bool:
    return value.startswith("https://") and " " not in value and len(value) > len("https://")


def _github_owner_repo_is_valid(value: str) -> bool:
    parts = value.split("/")
    if len(parts) >= 3 and parts[0].casefold() == _GITHUB_HOST:
        parts = parts[1:]
    if len(parts) < 2:
        return False
    owner, repo = parts[:2]
    if not _GITHUB_OWNER_RE.fullmatch(owner):
        return False
    if repo in {".", ".."} or not _GITHUB_REPO_RE.fullmatch(repo):
        return False
    return all(part not in {"", ".", ".."} for part in parts[2:])


def _dependency_source_kind(args):
    if len(args) >= 4:
        return args[2], args[3:]
    if len(args) >= 3:
        source_text = str(_unwrap(args[2]))
        if source_text.startswith(("https://", "http://")):
            return "http", args[2:3]
        source_parts = source_text.split("/", 1)
        if len(source_parts) == 2 and source_parts[0].casefold() == _GITHUB_HOST:
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

# Recognised image-format tokens for iconImageFormat. Matches docs/reference/syntax-inventory.md.
_ICON_IMAGE_FORMATS = frozenset({"png", "ico"})

# Recognised colour-depth tokens for iconImageDepth. Matches docs/reference/syntax-inventory.md.
_ICON_IMAGE_DEPTHS = frozenset({"bits8", "bits24", "bits32"})

# Recognised platform tokens for iconImagePlatform. `any` means the image
# is consumed by every platform that has an emitter; the three explicit
# tokens limit the image to a single platform's lowering pass. The
# `macos` spelling matches the docs/reference/syntax-inventory.md row and the user-facing vocab.
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

    The enum is `repr Int32` because middleware operations
    return through the same i32 user-op ABI as handlers. Programs may
    redeclare `enum MiddlewareControl …` (the existing enum-registry
    code will overwrite); doing so is a footgun and tripped by
    semlint SS3611 `redeclaredBuiltinEnum` separately.

    The case names are intentionally verbose (`…MiddlewareControl`
    suffix) so they read as full role identifiers at use sites
    instead of bare `continue` / `shortCircuit` which would collide
    with future control-flow verbs.
    """
    en = Enum(MIDDLEWARE_CONTROL_TYPE)
    en.repr = "Int32"
    en.cases.extend(MIDDLEWARE_CONTROL_CASES)
    prog.enums[MIDDLEWARE_CONTROL_TYPE] = en
    # Register the two case names as integer consts so `returnValue
    # continueMiddlewareControl` (and the shortCircuit counterpart)
    # resolve through the normal const-name path used by every other
    # operation body. Type is the enum NAME (not the repr) so the
    # `_check_result_contract` linter compares apples-to-apples when a
    # middleware op declares `output OP MiddlewareControl`. Codegen
    # resolves `MiddlewareControl` → `Int32` → i32 via
    # `llvm_type_for`'s enum-repr unwrap, so the i32 user-op return
    # slot still accepts the value without a cast.
    for case_name, case_value in MIDDLEWARE_CONTROL_CASES:
        prog.consts[case_name] = (MIDDLEWARE_CONTROL_TYPE, case_value)


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


_SQLITE_INTRINSIC_EXPORT_NAMES = frozenset({
    "openDatabase",
    "closeDatabase",
    "errorMessage",
    "lastInsertRowId",
    "changedRowCount",
    "prepareStatement",
    "finalizeStatement",
    "resetStatement",
    "stepStatement",
    "bindInt64",
    "bindDouble",
    "bindText",
    "bindBlob",
    "bindNull",
    "columnCount",
    "columnType",
    "columnName",
    "columnInt64",
    "columnDouble",
    "columnText",
    "columnBlob",
    "columnByteCount",
    "libraryVersion",
    "execStatus",
})


def _finalize_import_aliases(prog: Program) -> None:
    for module_path, alias in prog.imports:
        if not alias:
            continue
        prog.import_aliases[alias] = module_path
        for operation_name in _exported_symbols_for(prog, module_path, "operation"):
            aliased_name = operation_name
            if (module_path == "standard.sqlite"
                    and operation_name in _SQLITE_INTRINSIC_EXPORT_NAMES):
                aliased_name = f"sqlite.{operation_name}"
            prog.operation_aliases[f"{alias}.{operation_name}"] = aliased_name
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


def _reject_json_constant(token: str):
    raise ValueError(f"non-standard JSON constant `{token}`")


def _is_json_text_type(prog: Program, type_name: str) -> bool:
    name = type_name
    seen = set()
    while True:
        if name == "JsonText":
            return True
        if name in seen or name not in prog.type_aliases:
            return False
        seen.add(name)
        next_target = prog.type_aliases[name]
        if isinstance(next_target, list):
            if not next_target:
                return False
            name = next_target[0]
        else:
            name = next_target


def _record_type_for_json_body(prog: Program, type_name: str) -> str | None:
    name = type_name
    seen = set()
    while True:
        if name in prog.records:
            return name
        if name in seen or name not in prog.type_aliases:
            return None
        seen.add(name)
        next_target = prog.type_aliases[name]
        if isinstance(next_target, list):
            if not next_target:
                return None
            name = next_target[0]
        else:
            name = next_target


def _is_sql_text_type(prog: Program, type_name: str) -> bool:
    name = type_name
    seen = set()
    while True:
        if name == "SqlText":
            return True
        if name in seen or name not in prog.type_aliases:
            return False
        seen.add(name)
        next_target = prog.type_aliases[name]
        if isinstance(next_target, list):
            if not next_target:
                return False
            name = next_target[0]
        else:
            name = next_target


def _sql_body_row_name(verb: str, args: list) -> str | None:
    if verb == "sqlBody":
        if len(args) == 1:
            return args[0]
        return ""
    if verb == "sql" and args[:1] == ["body"]:
        if len(args) == 2:
            return args[1]
        return ""
    return None


def _sql_first_verb(sql_text: str) -> str | None:
    index = 0
    length = len(sql_text)
    while index < length:
        ch = sql_text[index]
        if ch.isspace():
            index += 1
            continue
        if sql_text.startswith("--", index):
            newline = sql_text.find("\n", index + 2)
            if newline == -1:
                return None
            index = newline + 1
            continue
        if sql_text.startswith("/*", index):
            end = sql_text.find("*/", index + 2)
            if end == -1:
                return None
            index = end + 2
            continue
        if ch.isalpha():
            start = index
            while index < length and (sql_text[index].isalpha() or sql_text[index] == "_"):
                index += 1
            return sql_text[start:index].upper()
        return None
    return None


def _strip_sql_leading_comments(sql_text: str) -> str:
    index = 0
    length = len(sql_text)
    while index < length:
        if sql_text[index].isspace():
            index += 1
            continue
        if sql_text.startswith("--", index):
            newline = sql_text.find("\n", index + 2)
            if newline == -1:
                return ""
            index = newline + 1
            continue
        if sql_text.startswith("/*", index):
            end = sql_text.find("*/", index + 2)
            if end == -1:
                return ""
            index = end + 2
            continue
        break
    return sql_text[index:].lstrip()


def _scan_sql_text(sql_text: str):
    placeholder_count = 0
    statement_count = 0
    has_statement_content = False
    index = 0
    length = len(sql_text)

    while index < length:
        ch = sql_text[index]
        next_ch = sql_text[index + 1] if index + 1 < length else ""

        if ch.isspace():
            index += 1
            continue
        if ch == "-" and next_ch == "-":
            index += 2
            while index < length and sql_text[index] != "\n":
                index += 1
            continue
        if ch == "/" and next_ch == "*":
            end = sql_text.find("*/", index + 2)
            if end == -1:
                return placeholder_count, statement_count, "unterminated SQL block comment"
            index = end + 2
            continue
        if ch == ";":
            if has_statement_content:
                statement_count += 1
                has_statement_content = False
            index += 1
            continue
        if ch == "?":
            placeholder_count += 1
            has_statement_content = True
            index += 1
            while index < length and sql_text[index].isdigit():
                index += 1
            continue
        if ch == "'":
            has_statement_content = True
            index += 1
            while index < length:
                if sql_text[index] == "'":
                    if index + 1 < length and sql_text[index + 1] == "'":
                        index += 2
                        continue
                    index += 1
                    break
                index += 1
            else:
                return placeholder_count, statement_count, "unterminated SQL string literal"
            continue
        if ch == '"':
            has_statement_content = True
            index += 1
            while index < length:
                if sql_text[index] == '"':
                    if index + 1 < length and sql_text[index + 1] == '"':
                        index += 2
                        continue
                    index += 1
                    break
                index += 1
            else:
                return placeholder_count, statement_count, "unterminated SQL quoted identifier"
            continue
        if ch == "`":
            has_statement_content = True
            index += 1
            while index < length and sql_text[index] != "`":
                index += 1
            if index >= length:
                return placeholder_count, statement_count, "unterminated SQL quoted identifier"
            index += 1
            continue
        if ch == "[":
            has_statement_content = True
            index += 1
            while index < length and sql_text[index] != "]":
                index += 1
            if index >= length:
                return placeholder_count, statement_count, "unterminated SQL bracket identifier"
            index += 1
            continue

        has_statement_content = True
        index += 1

    if has_statement_content:
        statement_count += 1
    return placeholder_count, statement_count, None


_SQL_REDUNDANT_CASE_RE = re.compile(
    r"\bCASE\s+WHEN\s+.+?\s+THEN\s+(?P<then>.*?)\s+ELSE\s+(?P<else>.*?)\s+END\b",
    re.IGNORECASE,
)

_SQL_NARROW_EXISTENCE_RE = re.compile(
    r"(?is)^SELECT\s+(?:1\b|EXISTS\s*\()"
)

_SQL_WRITE_TABLE_RE = re.compile(
    r"(?is)^(?:INSERT\s+(?:OR\s+\w+\s+)?INTO|REPLACE\s+INTO|"
    r"UPDATE)\s+([A-Za-z_][A-Za-z0-9_]*)\b"
)

_SQL_SELECT_TABLE_RE = re.compile(
    r"(?is)^SELECT\b.+?\bFROM\s+([A-Za-z_][A-Za-z0-9_]*)\b"
)


def _normalize_sql_expression(expression: str) -> str:
    return re.sub(r"\s+", " ", expression.strip()).lower()


def _redundant_sql_cases(sql_text: str) -> list:
    redundant_cases = []
    for match in _SQL_REDUNDANT_CASE_RE.finditer(sql_text):
        then_expr = _normalize_sql_expression(match.group("then"))
        else_expr = _normalize_sql_expression(match.group("else"))
        if then_expr and then_expr == else_expr:
            redundant_cases.append(match.group(0))
    return redundant_cases


def _sql_select_is_narrow_existence_probe(sql_text: str) -> bool:
    return bool(_SQL_NARROW_EXISTENCE_RE.match(
        _strip_sql_leading_comments(sql_text)))


def _sql_write_table(sql_text: str) -> str | None:
    match = _SQL_WRITE_TABLE_RE.match(_strip_sql_leading_comments(sql_text))
    if match is None:
        return None
    return match.group(1).lower()


def _sql_select_table(sql_text: str) -> str | None:
    match = _SQL_SELECT_TABLE_RE.match(_strip_sql_leading_comments(sql_text))
    if match is None:
        return None
    return match.group(1).lower()


def _sql_has_returning(sql_text: str) -> bool:
    return bool(re.search(r"(?is)\bRETURNING\b", sql_text))


def _sql_uses_last_insert_rowid(sql_text: str) -> bool:
    return bool(re.search(r"(?is)\blast_insert_rowid\s*\(", sql_text))


def _json_record_key(record: Record, field_name: str) -> str:
    return record.field_json_names.get(field_name, field_name)


def _json_kind_name(value) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "double"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return type(value).__name__


def _json_record_default_for_policy(prog: Program, field_type: str, policy: str):
    resolved = resolve_alias(prog, field_type)
    if policy == "empty":
        if resolved in {"String", "JsonText"}:
            return ""
    if policy == "null":
        if resolved in {"String", "JsonText"}:
            return None
    if policy == "false" and resolved == "Bool":
        return False
    if policy == "zero":
        if resolved in {
            "Int64", "UInt64",
            "ByteCount", "SignedByteCount", "AddressOffset",
            "UnixSecondsSinceEpoch", "CpuClockTicks", "FileByteOffset",
            "DurationMilliseconds", "MonotonicMilliseconds",
            "UtcMilliseconds",
            "Int32", "UInt32", "ExitCode", "Char",
            "Int16", "UInt16",
            "Int8", "UInt8",
        }:
            return 0
        if resolved in {"Float16", "Float32", "Float64"}:
            return 0.0
    return None


def _validate_json_record_value(
    prog: Program,
    record_type: str,
    value,
    decl_line: int,
    path: str,
):
    if not isinstance(value, dict):
        raise SyntaxError(
            f"line {decl_line}: jsonBodyWrongType: `{path or record_type}` "
            f"expected object for record `{record_type}`, got "
            f"{_json_kind_name(value)}")
    record = prog.records[record_type]
    expected_keys = {_json_record_key(record, field_name): field_name
                     for field_name, _field_type in record.fields}
    unknown_keys = sorted(set(value.keys()) - set(expected_keys.keys()))
    if unknown_keys:
        key = unknown_keys[0]
        raise SyntaxError(
            f"line {decl_line}: jsonBodyUnknownField: `{path or record_type}` "
            f"contains unknown JSON key `{key}` for record `{record_type}`")
    fields = {}
    for field_name, field_type in record.fields:
        json_key = _json_record_key(record, field_name)
        field_path = f"{path}.{field_name}" if path else field_name
        policy = record.field_json_omit_when.get(field_name)
        if json_key not in value:
            if policy:
                fields[field_name] = _json_record_default_for_policy(
                    prog, field_type, policy)
                continue
            raise SyntaxError(
                f"line {decl_line}: jsonBodyMissingRequired: `{field_path}` "
                f"is required for record `{record_type}`")
        field_value = value[json_key]
        nested_type = _record_type_for_json_body(prog, field_type)
        if nested_type is not None:
            fields[field_name] = _validate_json_record_value(
                prog, nested_type, field_value, decl_line, field_path)
            continue
        resolved = resolve_alias(prog, field_type)
        if field_value is None and policy == "null":
            fields[field_name] = None
            continue
        if resolved in {"String", "JsonText"}:
            if not isinstance(field_value, str):
                raise SyntaxError(
                    f"line {decl_line}: jsonBodyWrongType: `{field_path}` "
                    f"expected string, got {_json_kind_name(field_value)}")
            fields[field_name] = field_value
            continue
        if resolved == "Bool":
            if not isinstance(field_value, bool):
                raise SyntaxError(
                    f"line {decl_line}: jsonBodyWrongType: `{field_path}` "
                    f"expected boolean, got {_json_kind_name(field_value)}")
            fields[field_name] = field_value
            continue
        if resolved in ("Float64", "Float64", "Float64", "Float32", "Float32",
                        "Float32"):
            if isinstance(field_value, bool) or not isinstance(field_value, (int, float)):
                raise SyntaxError(
                    f"line {decl_line}: jsonBodyWrongType: `{field_path}` "
                    f"expected number, got {_json_kind_name(field_value)}")
            fields[field_name] = field_value
            continue
        if isinstance(field_value, bool) or not isinstance(field_value, int):
            raise SyntaxError(
                f"line {decl_line}: jsonBodyWrongType: `{field_path}` "
                f"expected integer, got {_json_kind_name(field_value)}")
        fields[field_name] = field_value
    return fields


def _bind_json_body_target(prog: Program, declaration: dict,
                           canonical_text: str) -> None:
    name = declaration["name"]
    type_name = declaration["type"]
    op = declaration.get("operation")
    if declaration.get("scope") == "local" and op is not None:
        op.consts[name] = (type_name, canonical_text)
    else:
        prog.consts[name] = (type_name, canonical_text)
    declaration["has_json_body"] = True


def _parse_json_body(name: str, body_lines: list, decl_line: int):
    if not body_lines or not any(text.strip() for text, _line in body_lines):
        raise SyntaxError(
            f"line {decl_line}: emptyJsonBody: jsonBody `{name}` requires "
            "at least one indented JSON line")
    body_text = "\n".join(text for text, _line in body_lines)
    try:
        parsed = json.loads(body_text, parse_constant=_reject_json_constant)
    except json.JSONDecodeError as exc:
        source_line = decl_line
        if 1 <= exc.lineno <= len(body_lines):
            source_line = body_lines[exc.lineno - 1][1]
        raise SyntaxError(
            f"line {decl_line}: invalidJsonBody: jsonBody `{name}` contains "
            f"invalid JSON at island line {exc.lineno} column {exc.colno} "
            f"(source line {source_line}): {exc.msg}") from exc
    except ValueError as exc:
        raise SyntaxError(
            f"line {decl_line}: invalidJsonBody: jsonBody `{name}` contains "
            f"invalid JSON: {exc}") from exc
    return parsed


def _canonicalize_json_value(parsed) -> str:
    return json.dumps(parsed, ensure_ascii=False, allow_nan=False,
                      separators=(",", ":"))


def _record_storage_declaration(prog: Program, args, lineno: int):
    if len(args) < 4:
        return
    scope, mutability = args[0], args[1]
    name, type_name = args[2], args[3]
    op = prog.current_op if scope == "local" else None
    prog.storage_declarations.append({
        "name": name,
        "type": type_name,
        "scope": scope,
        "mutability": mutability,
        "line": lineno,
        "operation": op,
        "value_present": len(args) > 4,
        "has_json_body": False,
        "has_sql_body": False,
    })


def _find_json_body_target(prog: Program, name: str):
    current_op = prog.current_op
    for declaration in reversed(prog.storage_declarations):
        if declaration["name"] != name:
            continue
        if (declaration["scope"] == "local"
                and declaration.get("operation") is not current_op):
            continue
        if declaration["scope"] not in ("local", "module"):
            return declaration, "bad_scope"
        if declaration["mutability"] != "immutable":
            return declaration, "mutable"
        if declaration["value_present"]:
            return declaration, "valued"
        if declaration["has_json_body"]:
            return declaration, "duplicate"
        return declaration, None
    return None, "missing"


def _start_json_body_literal(prog: Program, name: str, lineno: int) -> dict:
    declaration, problem = _find_json_body_target(prog, name)
    if declaration is None:
        raise SyntaxError(
            f"line {lineno}: jsonBodyMissingTarget: jsonBody `{name}` "
            "requires a preceding `storage local|module immutable "
            f"{name} TYPE` row with no inline value")
    if problem == "bad_scope":
        raise SyntaxError(
            f"line {lineno}: jsonBodyMissingTarget: jsonBody `{name}` "
            "can only bind storage declared with local or module scope")
    if problem == "mutable":
        raise SyntaxError(
            f"line {lineno}: jsonBodyMissingTarget: jsonBody `{name}` "
            "can only bind immutable storage")
    if problem == "valued":
        raise SyntaxError(
            f"line {lineno}: jsonBodyTargetAlreadyValued: jsonBody `{name}` "
            f"targets storage declared on line {declaration['line']} with "
            "an inline value")
    if problem == "duplicate":
        raise SyntaxError(
            f"line {lineno}: duplicateJsonBody: storage `{name}` already "
            "has a jsonBody literal")

    type_name = declaration["type"]
    if _is_json_text_type(prog, type_name):
        return {"name": name, "line": lineno, "target": declaration,
                "body_lines": []}
    record_type = _record_type_for_json_body(prog, type_name)
    if record_type is not None:
        return {"name": name, "line": lineno, "target": declaration,
                "record_type": record_type, "body_lines": []}
    raise SyntaxError(
        f"line {lineno}: jsonBodyUnsupportedType: jsonBody `{name}` "
        f"targets `{type_name}`, expected JsonText or a declared record type")


def _finish_json_body_literal(prog: Program, active_json_body: dict) -> None:
    name = active_json_body["name"]
    declaration = active_json_body["target"]
    parsed = _parse_json_body(
        name, active_json_body["body_lines"], active_json_body["line"])
    canonical = _canonicalize_json_value(parsed)
    record_type = active_json_body.get("record_type")
    if record_type is None:
        _bind_json_body_target(prog, declaration, canonical)
    else:
        fields = _validate_json_record_value(
            prog, record_type, parsed, active_json_body["line"], "")
        prog.record_json_constants[name] = {
            "recordType": record_type,
            "fields": fields,
        }
        prog.consts[name] = (declaration["type"], name)
        declaration["has_json_body"] = True
    prog.json_bodies.append(JsonBodyLiteral(
        name,
        declaration["type"],
        canonical,
        active_json_body["line"],
        list(active_json_body["body_lines"]),
    ))


def _find_sql_body_target(prog: Program, name: str):
    for declaration in reversed(prog.storage_declarations):
        if declaration["name"] != name:
            continue
        if declaration["scope"] != "module":
            return declaration, "bad_scope"
        if declaration["mutability"] != "immutable":
            return declaration, "mutable"
        if declaration["value_present"]:
            return declaration, "valued"
        if declaration.get("has_sql_body"):
            return declaration, "duplicate"
        if declaration.get("has_json_body"):
            return declaration, "other_body"
        return declaration, None
    return None, "missing"


def _start_sql_body_literal(prog: Program, name: str, lineno: int) -> dict:
    declaration, problem = _find_sql_body_target(prog, name)
    if declaration is None:
        raise SyntaxError(
            f"line {lineno}: sqlBodyMissingTarget: sql body `{name}` "
            "requires a preceding `storage module immutable "
            f"{name} SqlText` row with no inline value")
    if problem == "bad_scope":
        raise SyntaxError(
            f"line {lineno}: sqlBodyMissingTarget: sql body `{name}` "
            "can only bind module-scope storage")
    if problem == "mutable":
        raise SyntaxError(
            f"line {lineno}: sqlBodyMissingTarget: sql body `{name}` "
            "can only bind immutable storage")
    if problem == "valued":
        raise SyntaxError(
            f"line {lineno}: sqlBodyTargetAlreadyValued: sql body `{name}` "
            f"targets storage declared on line {declaration['line']} with "
            "an inline value")
    if problem == "duplicate":
        raise SyntaxError(
            f"line {lineno}: duplicateSqlBody: storage `{name}` already "
            "has a sql body literal")
    if problem == "other_body":
        raise SyntaxError(
            f"line {lineno}: duplicateSqlBody: storage `{name}` already "
            "has another syntax-island literal")

    type_name = declaration["type"]
    if _is_sql_text_type(prog, type_name):
        return {"name": name, "line": lineno, "target": declaration,
                "body_lines": []}
    raise SyntaxError(
        f"line {lineno}: sqlBodyUnsupportedType: sql body `{name}` "
        f"targets `{type_name}`, expected SqlText")


def _parse_sql_body(name: str, body_lines: list, decl_line: int):
    raw_lines = [text for text, _line in body_lines]
    while raw_lines and not raw_lines[0].strip():
        raw_lines.pop(0)
    while raw_lines and not raw_lines[-1].strip():
        raw_lines.pop()
    if not raw_lines or not any(text.strip() for text in raw_lines):
        raise SyntaxError(
            f"line {decl_line}: emptySqlBody: sql body `{name}` requires "
            "at least one indented SQL line")
    sql_text = "\n".join(raw_lines).rstrip()
    if "\0" in sql_text:
        raise SyntaxError(
            f"line {decl_line}: invalidSqlBody: sql body `{name}` contains "
            "a NUL byte")
    dynamic_hole = _SQL_HOLE_RE.search(sql_text)
    if dynamic_hole is not None:
        raise SyntaxError(
            f"line {decl_line}: sqlBodyDynamicHole: sql body `{name}` "
            f"contains `{dynamic_hole.group(0)}`; use `?` placeholders "
            "and sqlite.bind* rows for dynamic values")
    statement_kind = _sql_first_verb(sql_text)
    if statement_kind is None:
        raise SyntaxError(
            f"line {decl_line}: invalidSqlBody: sql body `{name}` does not "
            "start with a SQL statement verb")
    placeholder_count, statement_count, scan_problem = _scan_sql_text(sql_text)
    if scan_problem is not None:
        raise SyntaxError(
            f"line {decl_line}: invalidSqlBody: sql body `{name}` contains "
            f"invalid SQL text: {scan_problem}")
    return sql_text, statement_kind, placeholder_count, statement_count


def _finish_sql_body_literal(prog: Program, active_sql_body: dict) -> None:
    name = active_sql_body["name"]
    declaration = active_sql_body["target"]
    sql_text, statement_kind, placeholder_count, statement_count = _parse_sql_body(
        name, active_sql_body["body_lines"], active_sql_body["line"])
    prog.consts[name] = (declaration["type"], sql_text)
    declaration["has_sql_body"] = True
    prog.sql_constants[name] = {
        "statementKind": statement_kind,
        "placeholderCount": placeholder_count,
        "statementCount": statement_count,
    }
    prog.sql_bodies.append(SqlBodyLiteral(
        name,
        declaration["type"],
        sql_text,
        statement_kind,
        placeholder_count,
        statement_count,
        active_sql_body["line"],
        list(active_sql_body["body_lines"]),
    ))


def parse(source: str) -> Program:
    prog = Program()
    _register_builtin_middleware_control_enum(prog)
    active_html_template = None
    active_html_base_indent = None
    active_json_body = None
    active_sql_body = None
    active_sql_base_indent = None
    lines = list(enumerate(source.splitlines(), start=1))
    index = 0

    def _finish_html_body():
        nonlocal active_html_template, active_html_base_indent
        active_html_template = None
        active_html_base_indent = None

    def _finish_json_body():
        nonlocal active_json_body
        if active_json_body is not None:
            _finish_json_body_literal(prog, active_json_body)
            active_json_body = None

    def _finish_sql_body():
        nonlocal active_sql_body, active_sql_base_indent
        if active_sql_body is not None:
            _finish_sql_body_literal(prog, active_sql_body)
            active_sql_body = None
            active_sql_base_indent = None

    while index < len(lines):
        lineno, raw = lines[index]
        index += 1
        prog.source_lines[lineno] = raw

        if active_json_body is not None:
            if raw.strip() and raw[0].isspace():
                active_json_body["body_lines"].append((raw, lineno))
                continue
            if not raw.strip():
                active_json_body["body_lines"].append(("", lineno))
                continue
            # A non-empty column-0 line ends the JSON syntax island and is
            # immediately reprocessed as normal SemanticScript.
            _finish_json_body()

        if active_sql_body is not None:
            if raw.strip() and raw[0].isspace():
                indent = len(raw) - len(raw.lstrip(" \t"))
                if active_sql_base_indent is None:
                    active_sql_base_indent = indent
                trim_count = min(active_sql_base_indent, indent)
                active_sql_body["body_lines"].append((raw[trim_count:], lineno))
                continue
            if not raw.strip():
                active_sql_body["body_lines"].append(("", lineno))
                continue
            # A non-empty column-0 line ends the SQL syntax island and is
            # immediately reprocessed as normal SemanticScript.
            _finish_sql_body()

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
        sql_body_name = _sql_body_row_name(verb, args)
        if sql_body_name is not None:
            if raw[:1].isspace():
                raise SyntaxError(
                    f"line {lineno}: sql body must start at column 0")
            if not sql_body_name:
                raise SyntaxError(
                    f"line {lineno}: sql body requires: sql body NAME")
            active_sql_body = _start_sql_body_literal(prog, sql_body_name, lineno)
            active_sql_base_indent = None
            continue
        if verb == "jsonBody":
            if raw[:1].isspace():
                raise SyntaxError(
                    f"line {lineno}: jsonBody must start at column 0")
            if len(args) != 1:
                raise SyntaxError(
                    f"line {lineno}: jsonBody requires: jsonBody NAME")
            active_json_body = _start_json_body_literal(prog, args[0], lineno)
            continue
        verb, args = _canonicalize_syntax_row(verb, args, lineno)
        try:
            handle_top(prog, verb, args, lineno)
            if verb == "storage":
                _record_storage_declaration(prog, args, lineno)
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
    _finish_json_body()
    _finish_sql_body()
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


def _looks_like_regular_build_plan(source: str) -> bool:
    """Return True for the new regular-syntax build.sem shape.

    This is intentionally a cheap lexical probe. The real validation is done
    by parsing the file as normal SemanticScript and extracting the BuildPlan
    jsonBody. The probe only decides whether build.sem should use that path
    instead of the legacy closed-row build-tape validator.
    """
    saw_build_plan_record = False
    build_plan_storage_names = set()
    json_body_names = set()
    for raw in source.splitlines():
        toks = tokenize_line(raw)
        if not toks or toks[0] == "#":
            continue
        verb, args = toks[0], toks[1:]
        if verb == "record" and args and args[0] == "BuildPlan":
            saw_build_plan_record = True
        elif (verb == "storage" and len(args) >= 4
              and args[0] == "module" and args[1] == "immutable"
              and args[3] == "BuildPlan"):
            build_plan_storage_names.add(args[2])
        elif verb == "jsonBody" and args:
            json_body_names.add(args[0])
    return (
        saw_build_plan_record
        and bool(build_plan_storage_names)
        and bool(build_plan_storage_names & json_body_names)
    )


def _declares_language_mode(source: str) -> bool:
    for raw in source.splitlines():
        toks = tokenize_line(raw)
        if toks and toks[0] == "languageMode":
            return True
    return False


def _language_mode_rows_from_source(source: str):
    rows = []
    for raw in source.splitlines():
        toks = tokenize_line(raw)
        if toks and toks[0] == "languageMode":
            rows.append(raw.strip())
    return rows


def _sem_string(value) -> str:
    return json.dumps(str(value), ensure_ascii=False)


def _sem_literal(value) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value).lower()
    return _sem_string(value)


def _build_plan_required_object(parent: dict, key: str, path: str) -> dict:
    value = parent.get(key)
    if not isinstance(value, dict):
        raise SyntaxError(f"BuildPlan `{path}.{key}` must be an object")
    return value


def _build_plan_required_text(parent: dict, key: str, path: str) -> str:
    value = parent.get(key)
    if not isinstance(value, str) or not value:
        raise SyntaxError(f"BuildPlan `{path}.{key}` must be a non-empty string")
    return value


def _build_plan_optional_text(parent: dict, key: str, default: str = None):
    value = parent.get(key, default)
    if value is None:
        return None
    if not isinstance(value, str):
        raise SyntaxError(f"BuildPlan field `{key}` must be a string")
    return value


def _build_plan_required_int(parent: dict, key: str, path: str) -> int:
    value = parent.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise SyntaxError(f"BuildPlan `{path}.{key}` must be an integer")
    return value


def _build_plan_boolish_choice(value, *, allow_auto: bool = False) -> str:
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, str):
        normalized = value.strip()
        lowered = normalized.lower()
        if allow_auto and lowered == "auto":
            return "auto"
        if lowered in {"yes", "true", "on", "1"}:
            return "yes"
        if lowered in {"no", "false", "off", "0"}:
            return "no"
    expected = "yes/no/auto" if allow_auto else "yes/no"
    raise SyntaxError(f"BuildPlan boolean build option must be {expected}")


def _build_plan_import_alias(module_name: str) -> str:
    leaf = module_name.rsplit(".", 1)[-1]
    alias = re.sub(r"[^A-Za-z0-9_]", "_", leaf)
    if not alias or not re.match(r"^[A-Za-z_]", alias):
        alias = f"module_{alias}"
    return alias


def _build_plan_module_entries(plan: dict):
    if "modules" in plan:
        modules = _build_plan_required_object(plan, "modules", "BuildPlan")
        if not modules:
            raise SyntaxError("BuildPlan `modules` must contain at least one module")
        entries = []
        for module_key, module_spec in modules.items():
            if not isinstance(module_key, str) or not module_key:
                raise SyntaxError("BuildPlan module keys must be non-empty strings")
            if not isinstance(module_spec, dict):
                raise SyntaxError(f"BuildPlan `modules.{module_key}` must be an object")
            entries.append((module_key, module_spec))
        main_key = _build_plan_required_text(plan, "mainModule", "BuildPlan")
        main_operation = _build_plan_optional_text(plan, "mainOperation")
        main_matches = [module_spec for key, module_spec in entries if key == main_key]
        if len(main_matches) != 1:
            raise SyntaxError(
                f"BuildPlan mainModule `{main_key}` must name one entry in `modules`")
        return entries, main_key, main_matches[0], main_operation

    module = _build_plan_required_object(plan, "module", "BuildPlan")
    main_operation = (
        _build_plan_optional_text(module, "mainOperation")
        or _build_plan_optional_text(plan, "mainOperation")
    )
    return [("main", module)], "main", module, main_operation


def _regular_build_plan_preserved_rows(source: str):
    preserved_verbs = {
        "iconRoleDefinition", "icon", "iconRole", "iconPurpose",
        "iconImage", "iconImageGroup", "iconImagePath", "iconImageFormat",
        "iconImageWidth", "iconImageHeight", "iconImageScale",
        "iconImageDepth", "iconImagePlatform", "iconImagePurpose",
    }
    rows = []
    for raw in source.splitlines():
        toks = tokenize_line(raw)
        if toks and toks[0] in preserved_verbs:
            rows.append(raw.rstrip())
    return rows


def _regular_build_plan_fields(source: str, source_path: str) -> dict:
    try:
        plan_prog = parse(source)
    except SyntaxError as e:
        raise SyntaxError(f"regular BuildPlan parse failed: {e}") from e

    matches = [
        (name, payload)
        for name, payload in plan_prog.record_json_constants.items()
        if payload.get("recordType") == "BuildPlan"
    ]
    if len(matches) != 1:
        raise SyntaxError(
            f"{os.path.basename(str(source_path))} requires exactly one "
            f"module immutable BuildPlan jsonBody; found {len(matches)}")
    _name, payload = matches[0]
    fields = payload.get("fields")
    if not isinstance(fields, dict):
        raise SyntaxError("BuildPlan jsonBody did not produce an object")
    return fields


def _regular_build_plan_compat_source(source: str, source_path: str) -> str:
    """Lower a regular BuildPlan file to the compiler's existing build rows.

    The generated rows are an internal compatibility source used by semsc's
    import resolver and backend. The user-authored file remains the typed
    record/jsonBody syntax.
    """
    plan = _regular_build_plan_fields(source, source_path)
    project = _build_plan_required_object(plan, "project", "BuildPlan")
    module_entries, _main_key, main_module, main_operation = (
        _build_plan_module_entries(plan))
    target = _build_plan_required_object(plan, "target", "BuildPlan")
    version_info = plan.get("versionInfo") or {}
    if not isinstance(version_info, dict):
        raise SyntaxError("BuildPlan `versionInfo` must be an object when present")

    project_id = _build_plan_required_text(project, "id", "BuildPlan.project")
    project_name = _build_plan_required_text(project, "name", "BuildPlan.project")
    source_root = (
        _build_plan_optional_text(project, "sourceRoot")
        or _build_plan_optional_text(main_module, "sourceRoot")
        or "."
    )
    main_file = _build_plan_required_text(main_module, "mainFile", "BuildPlan.modules")
    target_runtime = _build_plan_required_text(target, "runtime", "BuildPlan.target")
    native_runtime = _build_plan_optional_text(target, "nativeRuntime", "native") or "native"
    native_runtime_version = target.get("nativeRuntimeVersion", 1)
    if isinstance(native_runtime_version, bool) or not isinstance(native_runtime_version, int):
        raise SyntaxError("BuildPlan `target.nativeRuntimeVersion` must be an integer")

    rows = []
    rows.extend(_language_mode_rows_from_source(source))
    rows.extend([
        f"buildProject {project_id}",
        f"project {_sem_string(project_name)}",
        f"modulePath {project_id} {_sem_string(_build_plan_required_text(project, 'modulePath', 'BuildPlan.project'))}",
        f"languageVersion {project_id} {_sem_string(_build_plan_required_text(project, 'languageVersion', 'BuildPlan.project'))}",
        f"projectVersion {project_id} {_sem_string(_build_plan_required_text(project, 'projectVersion', 'BuildPlan.project'))}",
        f"projectLicense {project_id} {_sem_string(_build_plan_required_text(project, 'license', 'BuildPlan.project'))}",
        f"sourceRoot {project_id} {_sem_string(source_root)}",
    ])
    for module_key, module_spec in module_entries:
        module_name = _build_plan_required_text(
            module_spec, "moduleName", f"BuildPlan.modules.{module_key}")
        if not _MODULE_NAME_RE.match(module_name):
            raise SyntaxError(
                f"BuildPlan modules.{module_key}.moduleName `{module_name}` "
                "is not a valid dotted namespace")
        source_path_value = (
            _build_plan_optional_text(module_spec, "sourcePath")
            or _build_plan_optional_text(module_spec, "sourceRoot")
            or source_root
        )
        rows.append(
            f"registerModule {project_id} {module_name} "
            f"{_sem_string(source_path_value)}")
    rows.extend([
        f"mainFile {project_id} {_sem_string(main_file)}",
    ])
    if main_operation:
        rows.append(f"mainOperation {project_id} {main_operation}")
    for key, verb in (
        ("testPattern", "testPattern"),
        ("testRoot", "testRoot"),
    ):
        value = (
            _build_plan_optional_text(project, key)
            or _build_plan_optional_text(main_module, key)
        )
        if value:
            rows.append(f"{verb} {project_id} {_sem_string(value)}")

    constants = plan.get("constants")
    if constants is not None:
        if not isinstance(constants, dict):
            raise SyntaxError("BuildPlan `constants` must be an object when present")
        for const_name, const_spec in constants.items():
            if not isinstance(const_spec, dict):
                raise SyntaxError(f"BuildPlan `constants.{const_name}` must be an object")
            const_type = _build_plan_required_text(
                const_spec, "type", f"BuildPlan.constants.{const_name}")
            if "value" not in const_spec:
                raise SyntaxError(
                    f"BuildPlan `constants.{const_name}.value` is required")
            rows.append(
                f"buildConstant {project_id} {const_name} {const_type} "
                f"{_sem_literal(const_spec.get('value'))}")

    rows.extend([
        f"target {target_runtime}",
        f"targetRuntime {project_id} {target_runtime}",
        f"runtime {native_runtime} {native_runtime_version}",
        f"buildProfile {project_id} {_build_plan_required_text(target, 'profile', 'BuildPlan.target')}",
        f"runtimeChecks {project_id} {_build_plan_required_text(target, 'runtimeChecks', 'BuildPlan.target')}",
        f"persistLlvmIr {project_id} {_build_plan_boolish_choice(target.get('persistLlvmIr'), allow_auto=True)}",
        f"optLevel {project_id} {_build_plan_required_int(target, 'optLevel', 'BuildPlan.target')}",
    ])

    emit_llvm = _build_plan_optional_text(target, "emitLlvmIr")
    if emit_llvm:
        rows.append(f"emitLlvmIr {project_id} {emit_llvm}")
    if "emitOptimizedLlvmIr" in target:
        rows.append(
            f"emitOptimizedLlvmIr {project_id} "
            f"{_build_plan_boolish_choice(target.get('emitOptimizedLlvmIr'))}")
    for key, verb in (
        ("buildFolderName", "buildFolderName"),
        ("cpuBaseline", "cpuBaseline"),
        ("cpuTune", "cpuTune"),
        ("cpuFeatureCheck", "cpuFeatureCheck"),
        ("asyncRuntime", "asyncRuntime"),
        ("guiBackend", "guiBackend"),
        ("nativeHttpHost", "nativeHttpHost"),
        ("resourcesDir", "resourcesDir"),
        ("buildDir", "buildDir"),
        ("buildRoot", "buildRoot"),
        ("llvmIrOutput", "llvmIrOutput"),
        ("optimizedLlvmIrOutput", "optimizedLlvmIrOutput"),
        ("docsOutput", "docsOutput"),
        ("nativeOutput", "nativeOutput"),
        ("comptimeOperation", "comptimeOperation"),
    ):
        value = _build_plan_optional_text(target, key)
        if value:
            rows.append(f"{verb} {project_id} {_sem_string(value)}")
    if "nativeHttpPort" in target:
        rows.append(
            f"nativeHttpPort {project_id} "
            f"{_build_plan_required_int(target, 'nativeHttpPort', 'BuildPlan.target')}")
    if "keepResources" in target:
        rows.append(
            f"keepResources {project_id} "
            f"{_build_plan_boolish_choice(target.get('keepResources'))}")
    if "formatterLineWidth" in target:
        rows.append(
            f"formatterSetting {project_id} lineWidth "
            f"{_build_plan_required_int(target, 'formatterLineWidth', 'BuildPlan.target')}")
    linter_max_tier = _build_plan_optional_text(target, "linterMaxTier")
    if linter_max_tier:
        rows.append(f"linterSetting {project_id} maxTier {linter_max_tier}")

    for key in _PROJECT_METADATA_VERBS:
        value = version_info.get(key)
        if isinstance(value, str) and value:
            rows.append(f"{key} {_sem_string(value)}")
    metadata = version_info.get("metadata") or {}
    if metadata:
        if not isinstance(metadata, dict):
            raise SyntaxError("BuildPlan `versionInfo.metadata` must be an object")
        for key, value in metadata.items():
            if not isinstance(key, str) or not isinstance(value, str):
                raise SyntaxError("BuildPlan versionInfo.metadata keys and values must be strings")
            metadata_key = key[:1].upper() + key[1:]
            rows.append(f"metadata {_sem_string(metadata_key)} {_sem_string(value)}")

    if main_operation:
        rows.append(f"entry console {main_operation}")
    main_module_name = _build_plan_required_text(
        main_module, "moduleName", "BuildPlan.modules")
    rows.append(
        f"import {_build_plan_import_alias(main_module_name)} {main_module_name}")
    rows.extend(_regular_build_plan_preserved_rows(source))
    compat_source = "\n".join(rows) + "\n"
    _validate_build_tape_source(compat_source, source_path)
    return compat_source


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
    if _looks_like_regular_build_plan(source):
        # Validate the typed BuildPlan by lowering it to the current backend
        # contract and then validating that generated contract. This keeps the
        # user syntax regular while preserving the legacy build invariants.
        _regular_build_plan_compat_source(source, source_path)
        return

    build_projects = []
    rows_by_project = {}
    singleton_seen = {}
    source_roots = {}
    target_runtime_by_project = {}
    allowed_non_project_verbs = (
        {"buildProject", "project", "target", "runtime", "entry", "import",
         "moduleFolder", "languageMode"}
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


def _has_language_mode(prog: Program, mode: str) -> bool:
    return mode in prog.language_modes


def _strict_executable_is_active(prog: Program) -> bool:
    """Strict executable is opt-in for the initial rollout."""
    return _has_language_mode(prog, "strictExecutable")


def _strict_unknown_lowercase_verb_error(prog: Program, verb: str, lineno: int):
    scope = "operation-body" if prog.current_op is not None else "top-level"
    raise SyntaxError(
        f"line {lineno}: unknown lowercase {scope} verb `{verb}` is not "
        "allowed under `languageMode strictExecutable`; declare "
        "`languageMode refinedSyntax` for research files that intentionally "
        "rely on permissive metadata rows")


def _validate_run_checked_args(args, lineno: int) -> None:
    if (len(args) != 9
            or args[1] != "ok"
            or args[4] != "error"
            or args[7] != "else"):
        raise SyntaxError(
            f"line {lineno}: runChecked requires: runChecked CALL ok "
            "VALUE TYPE error ERROR TYPE else LABEL")


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
        # docs/ast.md §10:
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
    if verb == "buildProject":
        if len(args) != 1:
            raise SyntaxError(
                f"line {lineno}: buildProject requires: buildProject PROJECT")
        prog.hard_metadata.setdefault(args[0], {}).setdefault(
            "buildProject", []).append([])
        return
    if verb in _BUILD_TAPE_PROJECT_VERBS:
        minimum_arity = _BUILD_TAPE_MIN_ARITY.get(verb, 2)
        if len(args) < minimum_arity:
            raise SyntaxError(
                f"line {lineno}: {verb} requires at least "
                f"{minimum_arity} argument(s)")
        project_name = args[0]
        prog.hard_metadata.setdefault(project_name, {}).setdefault(
            verb, []).append(list(args[1:]))
        # buildConstant additionally registers the named value on
        # prog.consts so it is visible to operations the same way a
        # `storage module immutable NAME TYPE VALUE` row would be.
        # Without this, build.sem-declared constants were silently
        # discarded and any fallback `storage module immutable`
        # declaration inside main.sem won by being processed later.
        if verb == "buildConstant" and len(args) >= 4:
            const_name = args[1]
            const_type = args[2]
            raw_value = _unwrap(args[3])
            prog.consts[const_name] = (const_type, raw_value)
        return
    if verb == "languageMode":
        # Two accepted forms:
        #   languageMode MODE              (per-file declaration)
        #   languageMode PROJECT MODE      (build.sem project-wide row)
        # When the build.sem form is used the row applies to every source
        # parsed into the program; this is how a project can opt the whole
        # source tree into strict executable validation without editing each
        # .sem file.
        project_name = None
        if len(args) == 1:
            language_mode = args[0]
        elif len(args) == 2:
            project_name = args[0]
            language_mode = args[1]
        else:
            raise SyntaxError(
                f"line {lineno}: languageMode requires: languageMode MODE  or  "
                f"languageMode PROJECT MODE")
        if language_mode not in _KNOWN_LANGUAGE_MODES:
            raise SyntaxError(
                f"line {lineno}: languageMode: `{language_mode}` is not a known language "
                f"mode value; expected one of {sorted(_KNOWN_LANGUAGE_MODES)}")
        if project_name is not None:
            prog.hard_metadata.setdefault(project_name, {}).setdefault(
                "languageMode", []).append([language_mode])
        if language_mode in prog.language_modes:
            return
        for existing_mode in prog.language_modes:
            mode_pair = frozenset((existing_mode, language_mode))
            if mode_pair in _INCOMPATIBLE_LANGUAGE_MODES:
                raise SyntaxError(
                    f"line {lineno}: languageMode: `{language_mode}` cannot be combined with "
                    f"`{existing_mode}`")
        prog.language_modes.append(language_mode)
        return
    if verb == "workerPool" and prog.current_op is None:
        if not args:
            raise SyntaxError("workerPool requires: workerPool NAME")
        prog.worker_pools[args[0]] = lineno
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
    if verb == "import":
        # New syntax: import ALIAS MODULE_PATH
        module_path, alias = args[1], args[0]
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
    if verb == "recordFieldJsonName":
        if len(args) < 3:
            raise SyntaxError(
                "recordFieldJsonName requires: recordFieldJsonName RECORD FIELD JSON_KEY")
        rec = prog.records.get(args[0])
        if rec is None:
            raise SyntaxError(f"recordFieldJsonName references unknown record: {args[0]}")
        if args[1] not in {field_name for field_name, _field_type in rec.fields}:
            raise SyntaxError(
                f"recordFieldJsonName references unknown field: {args[0]}.{args[1]}")
        rec.field_json_names[args[1]] = _unwrap(args[2])
        return
    if verb == "recordFieldJsonOmitWhen":
        if len(args) < 3:
            raise SyntaxError(
                "recordFieldJsonOmitWhen requires: recordFieldJsonOmitWhen RECORD FIELD empty|null|false|zero")
        rec = prog.records.get(args[0])
        if rec is None:
            raise SyntaxError(f"recordFieldJsonOmitWhen references unknown record: {args[0]}")
        if args[1] not in {field_name for field_name, _field_type in rec.fields}:
            raise SyntaxError(
                f"recordFieldJsonOmitWhen references unknown field: {args[0]}.{args[1]}")
        policy = args[2]
        if policy not in {"empty", "null", "false", "zero"}:
            raise SyntaxError(
                "recordFieldJsonOmitWhen policy must be one of: empty, null, false, zero")
        rec.field_json_omit_when[args[1]] = policy
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
        # Reset current_op so the subsequent `purpose <serverName> "..."`
        # row (and any other webServer-scoped header verbs) doesn't get
        # mis-attributed to whatever operation an imported stdlib module
        # left dangling. Without this, importing a stdlib that ends with
        # an `operation` body (e.g. standard.log's `logError`) breaks
        # parsing of the next webServer declaration with
        # "purpose: owner X does not match current operation Y".
        prog.current_op = None
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
    if verb == "routeNotFound":
        if len(args) < 2:
            raise SyntaxError("routeNotFound requires: routeNotFound SERVER HANDLER_OPERATION")
        ws = prog.web_servers.get(args[0])
        if ws is None:
            raise SyntaxError(f"routeNotFound references unknown webServer: {args[0]}")
        ws.not_found_handler = args[1]
        return
    if verb == "routeMethodNotAllowed":
        if len(args) < 2:
            raise SyntaxError(
                "routeMethodNotAllowed requires: routeMethodNotAllowed SERVER HANDLER_OPERATION")
        ws = prog.web_servers.get(args[0])
        if ws is None:
            raise SyntaxError(f"routeMethodNotAllowed references unknown webServer: {args[0]}")
        ws.method_not_allowed_handler = args[1]
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
    if verb in ("schema", "unknownFields", "guarantee", "input", "output",
                "purpose", "invariant"):
        # These continue an abstraction declaration started earlier OR
        # (for `input`/`output`/`purpose`) belong to an operation header.
        if verb in ("purpose", "invariant", "input", "output") and prog.current_op is not None:
            # Spec §9 ownership: each header line's first arg names the
            # operation it belongs to. Reject if it doesn't match.
            if args and args[0] != prog.current_op.name:
                if args[0] not in prog.operations:
                    prog.hard_metadata.setdefault(args[0], {}).setdefault(verb, []).extend(
                        [_unwrap(t) for t in args[1:]])
                    return
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
    if verb in {"nativeRuntimeSource", "nativeRuntimeLinkArg"}:
        if len(args) < 2:
            raise SyntaxError(f"{verb} requires: {verb} MODULE VALUE")
        prog.hard_metadata.setdefault(args[0], {}).setdefault(
            verb, []).append([_unwrap(t) for t in args[1:]])
        return

    # ----- operations -----
    if verb == "operation":
        if not args:
            raise SyntaxError(f"line {lineno}: operation requires: operation NAME")
        if args[0] in prog.operations:
            previous_line = prog.operations[args[0]].decl_line
            raise SyntaxError(
                f"line {lineno}: duplicate operation `{args[0]}`; "
                f"first declared on line {previous_line}")
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
        if verb == "runChecked":
            _validate_run_checked_args(args, lineno)
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
            # `storage module immutable` defers to a value already
            # registered by an earlier `buildConstant` (or a prior
            # storage row). Without setdefault, a build-tape
            # `buildConstant project featureFlag String
            # "yes"` row would be silently clobbered by a fallback
            # `storage module immutable featureFlag
            # String "no"` in an imported module:
            # the build-tape value MUST win.
            if mutability == "mutable":
                # Mutable storage is always re-declared (rebind to
                # the latest declaration's value as the initial).
                prog.consts[name] = (typ, value)
                prog.mutable_globals[name] = (typ, value)
            else:
                prog.consts.setdefault(name, (typ, value))
        elif prog.current_op is not None:
            prog.current_op.consts[name] = (typ, value)
            prog.current_op.lines.append((verb, args, lineno))
        else:
            prog.consts.setdefault(name, (typ, value))
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
    if verb in {
        "literalSource",
        "literalBytes",
        "literalDigest",
        "literalTrust",
        "literalPreview",
    } and args:
        # Literal metadata is module-scoped even when it appears after an
        # imported operation body in a flattened build tape.
        prog.hard_metadata.setdefault(args[0], {}).setdefault(
            verb, []).append([_unwrap(t) for t in args[1:]])
        return

    # Catch-all for any other lowercase-leading verb that looks like a
    # declarative-metadata line. This is intentionally permissive so the
    # refined-syntax surface (~100 new verbs) is accepted without each
    # needing its own handler. The line is stored under hard_metadata
    # keyed by the first arg (the declared name) for tooling indexing.
    if verb and verb[0].islower():
        # The unknown-lowercase-verb gate is the *strict-vocabulary* level,
        # not the default. Most .sem files use refined-syntax metadata
        # verbs (modulePurpose, memoryHeap, moduleObservability,
        # moduleDependency, …) that are not in the hardcoded allow-list,
        # and rejecting them at parse time would be enormous churn for
        # very little safety gain. The default strict wall still enforces
        # all the SS3xxx bug-class checks via validate_strict_executable.
        # Files that opt into `languageMode strictExecutable` explicitly
        # also get the verb-vocabulary tightening on top.
        if _has_language_mode(prog, "strictExecutable"):
            _strict_unknown_lowercase_verb_error(prog, verb, lineno)
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
    "memoryAllocationSource", "operationBody", "runtimeBinding",
    "runtimeBindingPrecondition", "runtimeBindingFailure",
    "runtimeBindingAsyncStart", "runtimeBindingAsyncAwait", "intrinsicName",
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
I2 = ir.IntType(2)
I4 = ir.IntType(4)
Int8 = ir.IntType(8)
Int16 = ir.IntType(16)
Int32 = ir.IntType(32)
Int64 = ir.IntType(64)
F16 = ir.HalfType()
Float32 = ir.FloatType()
Float64 = ir.DoubleType()
Int8P = ir.IntType(8).as_pointer()
VOID = ir.VoidType()


# Implicit operation-input symbols whose value never flows into computation
# (spec §16 — the `console` dependency, the request token, the clock, etc.).
# At a user-defined operation's call site these are dropped from the LLVM
# parameter list so the call signature only carries data values.
OPAQUE_INPUTS = {
    "console", "environment", "process",
    "httpRequest", "databaseClient", "clock",
}

HTTP_METHOD_WHITELIST = SUPPORTED_HTTP_ROUTE_METHODS

NULLABLE_HTTP_REQUEST_READS = frozenset({
    "http.requestHeader",
    "http.requestQueryParam",
    "http.requestPathParam",
    "http.requestCookie",
    "http.requestBodyText",
    "http.requestBodyBytes",
    "http.multipartPartText",
    "http.multipartPartBytes",
    "http.multipartPartFilename",
    "http.multipartPartContentType",
})

HTTP_RESPONSE_BODY_WRITERS = frozenset({
    "http.responseHtml",
    "http.responseText",
    "http.responseBytes",
    "http.responseSseEvent",
})

HTTP_RESPONSE_NULLABLE_SLOTS = {
    "http.responseHtml": frozenset({"body"}),
    "http.responseText": frozenset({"body"}),
    "http.responseBytes": frozenset({"body"}),
    "http.responseSseEvent": frozenset({"event", "data"}),
}

LEGACY_HTTP_NULL_GUARD_OPT_OUT_MARKERS = (
    "null-body failure path",
    "null-body 500",
)


def resolve_alias(prog: Program, name: str) -> str:
    """Walk the type-alias chain and return the head token of the final
    type expression. For a single-token alias like `type ExitCode Int32`,
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
    For `type ExitCode Int32`, returns `["Int32"]`. For an unaliased primitive,
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


_INTEGER_LLVM_TYPES = {
    "Int2": I2,
    "UInt2": I2,
    "Int4": I4,
    "UInt4": I4,
    "Int8": Int8,
    "UInt8": Int8,
    "Int16": Int16,
    "UInt16": Int16,
    "Int32": Int32,
    "UInt32": Int32,
    "Int64": Int64,
    "UInt64": Int64,
}

_FLOAT_LLVM_TYPES = {
    "Float16": F16,
    "Float32": Float32,
    "Float64": Float64,
}

_Int64_ROLE_TYPES = {
    "ByteCount",
    "SignedByteCount",
    "AddressOffset",
    "UnixSecondsSinceEpoch",
    "CpuClockTicks",
    "FileByteOffset",
    "DurationMilliseconds",
    "MonotonicMilliseconds",
    "UtcMilliseconds",
    "SqliteRowId",
    "JsonCursor",
}

_Int32_ROLE_TYPES = {
    "ExitCode",
    "GuiPixels",
    "GuiMinimumPixels",
    "GuiTabIndex",
    "GuiKeyCode",
    "GuiSelectedIndex",
    "GuiEventDimensionPixels",
    "GuiHandlerStatus",
    "GuiRuntimeStatusCode",
}

_U32_ROLE_TYPES = {
    "GuiWindowId",
    "GuiControlId",
}

_TEXT_TYPES = {
    "String",
    "JsonText",
    "SqlText",
    "JsonPath",
    "GuiText",
    "GuiApplicationTitle",
    "GuiWindowTitle",
    "GuiControlText",
    "GuiPlaceholderText",
    "GuiAccessibleName",
    "GuiListBoxItemText",
    "GuiIconGroupName",
    "GuiKeywordToken",
    "GuiRuntimeTarget",
    "HtmlFragment",
    "HtmlTrustedFragment",
    "HtmlDocument",
    "HtmlTemplate",
}

_POINTER_TYPES = {
    "OpaquePointer",
    "FileHandle",
    "DecomposedTimePointer",
    "SetjmpRegisterBufferPointer",
    "SqliteDatabase",
    "SqliteStatement",
    "JsonBuilder",
    "JsonDocument",
    "JsonScratchBuffer",
    "GuiApplication",
    "GuiSession",
    "GuiEvent",
    "GuiWindow",
    "GuiControl",
    "GuiButton",
    "GuiTextBox",
    "GuiListBox",
    "GuiCheckBox",
    "GuiMenuItem",
    "GuiStatusBar",
    "GuiTextLabel",
    "HttpRequest",
    "HttpResponse",
    "DecomposedTimeAddress",
    "SetjmpRegisterBuffer",
    "CFile",
}


def enum_repr_type(prog: Program, name: str) -> str | None:
    enum = prog.enums.get(name)
    if enum is None:
        return None
    return enum.repr or "Int32"


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
    if typename in _INTEGER_LLVM_TYPES:
        return _INTEGER_LLVM_TYPES[typename]
    if typename in _FLOAT_LLVM_TYPES:
        return _FLOAT_LLVM_TYPES[typename]
    if typename == "Char":
        return Int32
    if typename in _Int64_ROLE_TYPES:
        return Int64
    if typename in _Int32_ROLE_TYPES or typename in _U32_ROLE_TYPES:
        return Int32
    if typename in _TEXT_TYPES or typename in _POINTER_TYPES:
        return Int8P
    if typename == "Bool":
        return I1
    if typename in ("HttpRequest", "HttpResponse", "GuiSession", "GuiEvent"):
        return Int8P
    if typename in (
        "GuiApplication", "GuiWindow", "GuiControl", "GuiButton",
        "GuiTextBox", "GuiListBox", "GuiCheckBox", "GuiMenuItem",
        "GuiStatusBar", "GuiTextLabel",
    ):
        return Int8P
    # Opaque handles for the native sqlite runtime — the C ABI in
    # `sem_sqlite_runtime.h` exposes both as `void *` typedefs and never
    # lets generated code dereference them, so lowering as `i8*` is the
    # correct shape (parallel to HttpRequest / HttpResponse above).
    if typename in ("SqliteDatabase", "SqliteStatement"):
        return Int8P
    # Opaque handle for the native JSON builder runtime
    # (sem_json_runtime.h). The AS source allocates one of these via
    # json.createBuilder, threads it through field writers, and frees
    # via `defer json.destroyBuilder`. Generated code never
    # dereferences the handle directly — same opaque-pointer contract
    # as HttpRequest / SqliteDatabase.
    if typename in ("JsonBuilder", "JsonDocument"):
        return Int8P
    return None


def llvm_type_for_or_void(prog: Program, typename: str):
    """Like llvm_type_for but also accepts 'Void' / 'Void' as the void type."""
    if typename in ("Void", "Void"):
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
        elif len(tokens) == 1:
            full = resolve_alias_full(prog, tokens[0])
            if full and full[0] == "Result":
                if len(full) < 3:
                    return OutputContract(
                        lineno, tokens, problem="malformedOutputContract",
                        message=(
                            f"malformedOutputContract: operation `{op.name}` "
                            f"declares result alias `{tokens[0]}` without both "
                            "OK and ERROR types"))
                ok_type = full[1]
            else:
                ok_type = tokens[0]
        else:
            ok_type = tokens[0]

        resolved_ok = resolve_alias(prog, ok_type)
        if resolved_ok in ("Void", "Void"):
            return OutputContract(lineno, tokens, ok_type=ok_type, llvm_type=Int32)
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
    "math.subInt64":  "math.subtractInt64",
    "math.mulInt64":  "math.multiplyInt64",
    "math.divInt64":  "math.divideInt64",
    "math.modInt64":  "math.moduloInt64",
    "math.eqInt64":   "math.equalInt64",
    "math.neInt64":   "math.notEqualInt64",
    "math.ltInt64":   "math.lessThanInt64",
    "math.leInt64":   "math.lessThanOrEqualInt64",
    "math.gtInt64":   "math.greaterThanInt64",
    "math.geInt64":   "math.greaterThanOrEqualInt64",
    "console.writeInteger": "console.writeIntegerLine",
    "math.convertInt64ToFloat64": "math.intToFloat",
    "math.convertFloat64ToInt64": "math.floatToInt",
    "math.convertSignedInt64ToFloat64": "math.intToFloat",
    "math.convertFloat64ToSignedInt64": "math.floatToInt",
    "math.convertSignedInt32ToSignedInt64": "math.signExtendInt32ToInt64",
    "math.convertSignedInt64ToSignedInt32": "math.truncateInt64ToInt32",
}

_JSON_STRINGIFY_PRIMITIVE_TARGETS = {
    "Int64": "json.encode.Int64",
    "UInt64": "json.encode.UInt64",
    "Int32": "json.encode.Int32",
    "UInt32": "json.encode.UInt32",
    "Int16": "json.encode.Int16",
    "UInt16": "json.encode.UInt16",
    "Int8": "json.encode.Int8",
    "UInt8": "json.encode.UInt8",
    "DurationMilliseconds": "json.encode.DurationMilliseconds",
    "MonotonicMilliseconds": "json.encode.MonotonicMilliseconds",
    "UtcMilliseconds": "json.encode.UtcMilliseconds",
    "Bool": "json.encode.Bool",
    "Float64": "json.encode.Float64",
    "Float32": "json.encode.Float32",
    "String": "json.encode.String",
    "JsonText": "json.encode.String",
}

_JSON_PARSE_PRIMITIVE_TARGETS = {
    "Int64": "json.decode.Int64",
    "UInt64": "json.decode.UInt64",
    "Int32": "json.decode.Int32",
    "UInt32": "json.decode.UInt32",
    "Int16": "json.decode.Int16",
    "UInt16": "json.decode.UInt16",
    "Int8": "json.decode.Int8",
    "UInt8": "json.decode.UInt8",
    "DurationMilliseconds": "json.decode.DurationMilliseconds",
    "MonotonicMilliseconds": "json.decode.MonotonicMilliseconds",
    "UtcMilliseconds": "json.decode.UtcMilliseconds",
    "Bool": "json.decode.Bool",
    "Float64": "json.decode.Float64",
    "Float32": "json.decode.Float32",
}

_STRICT_FALLIBLE_CALL_TARGETS = KNOWN_FALLIBLE_CALL_TARGETS

_STRICT_HEAP_ALLOCATION_TARGETS = frozenset({
    "c.malloc",
    "c.calloc",
    "c.realloc",
})

_STRICT_HEAP_CLEANUP_TARGETS = frozenset({
    "c.free",
})

_STRICT_SQLITE_DATABASE_OPEN_TARGETS = frozenset({
    "sqlite.openDatabase",
})

_STRICT_SQLITE_DATABASE_CLOSE_TARGETS = frozenset({
    "sqlite.closeDatabase",
})

_STRICT_SQLITE_STATEMENT_PREPARE_TARGETS = frozenset({
    "sqlite.prepareStatement",
})

_STRICT_SQLITE_STATEMENT_FINALIZE_TARGETS = frozenset({
    "sqlite.finalizeStatement",
})

_STRICT_FORBIDDEN_CALL_TARGETS_WITH_ADVICE = {
    "c.strcat": (
        "use `c.snprintf(cursor, remainingCapacity, ...)` into a tracked "
        "write offset instead; strcat has no bounded form and rescans the "
        "accumulator every call"
    ),
    "c.strcpy": (
        "use `c.snprintf(buffer, capacity, \"%s\", source)` with a bounded "
        "capacity"
    ),
    "c.strncat": (
        "use `c.snprintf(cursor, remainingCapacity, ...)`; strncat's count "
        "argument bounds the source, not the destination"
    ),
    "c.sprintf": (
        "use `c.snprintf(buffer, capacity, format, ...)`; sprintf has no "
        "destination-size argument"
    ),
    "c.gets": (
        "use `c.fgets(buffer, capacity, stream)` or `c.read(fd, buffer, "
        "capacity)` so a maximum byte count bounds the read"
    ),
}

# Non-cryptographic pseudo-random sources (CWE-338). The libc PRNG family
# (`rand`/`srand` and the POSIX `random`/`drand48` relatives) are deterministic
# generators seeded from a small space — predictable, so never appropriate for
# tokens, keys, nonces, salts, or session identifiers. The portable replacement
# already ships in the std: `bcrypt.randomBytes` (BCryptGenRandom on Windows,
# getrandom(2)/`/dev/urandom` on POSIX). Strict executable refuses these.
#
# Only `rand`/`srand` are wired in libc_registry today; the rest are listed so
# that if any is added to the registry later it is automatically covered (a
# target absent from the registry simply never reaches codegen). The advice is
# uniform: route security-sensitive randomness through `bcrypt.randomBytes`.
_INSECURE_RANDOM_ADVICE = ("use `bcrypt.randomBytes` (the platform CSPRNG that "
                           "already ships in standard.bcrypt) for any "
                           "security-sensitive value")
# Derived from the single source of truth in libc_registry so adding a PRNG
# symbol there automatically covers it here (closes the iteration-3 critique's
# brittle-allowlist note). The semlint floor mirrors this set under a parity test.
_STRICT_INSECURE_RANDOM_TARGETS = {
    "c." + symbol: _INSECURE_RANDOM_ADVICE
    for symbol in libc_registry.INSECURE_PRNG_SYMBOLS
}

_STRICT_CONSTANT_FORMAT_TARGETS = frozenset({
    "c.snprintf",
    "c.printf",
    "c.fprintf",
    "c.sprintf",
    "c.vsnprintf",
    "c.vfprintf",
    "c.vprintf",
})

_STRICT_FORMAT_ARG_SLOTS = frozenset({"format"})

_STRICT_SQL_STRING_TARGETS = frozenset({
    "sqlite.prepareStatement",
    "sqlite.exec",
    "sqlite.execStatus",
})

_STRICT_SQL_ARG_SLOTS = frozenset({"sql"})

_STRICT_SQL_PREPARE_TARGETS = frozenset({"sqlite.prepareStatement"})
_STRICT_SQL_EXEC_TARGETS = frozenset({"sqlite.exec", "sqlite.execStatus"})

_STRICT_RESPONSE_WRITER_TARGETS = frozenset({
    "http.responseHtml",
    "http.responseText",
    "http.responseBytes",
    "http.responseSseEvent",
    "http.responseFile",
})

HTTP_INTRINSIC_TARGETS = (
    NULLABLE_HTTP_REQUEST_READS
    | HTTP_RESPONSE_BODY_WRITERS
    | frozenset({
        "http.requestMethod",
        "http.requestPath",
        "http.requestBodyLength",
        "http.multipartPartLength",
        "http.responseHeader",
        "http.responseFile",
        "http.nowMillis",
        "http.ensureDirectory",
    })
)

_STRICT_OVERFLOW_SENSITIVE_TARGETS = frozenset({
    "math.addInt64",
    "math.subtractInt64",
    "math.multiplyInt64",
})

_STRICT_CHECKED_ARITHMETIC_TARGETS = frozenset({
    "math.checkedAddInt64",
    "math.checkedSubtractInt64",
    "math.checkedMultiplyInt64",
})

_STRICT_OVERFLOW_SENSITIVE_NAME_RE = re.compile(
    # Suffixes that almost always indicate overflow-risky arithmetic:
    # timestamps that add lifetimes, raw byte counts, and capacities
    # that multiply. `*Count`, `*Length`, `*Size`, `*Offset` are
    # excluded — they show up on bounded loop counters and fixed
    # array offsets so often that flagging them is more noise than
    # signal. The bytewise/timewise patterns left here are the ones
    # where real-world overflow is reachable from untrusted input.
    r"(?:Ms|AtMs|Milliseconds|Bytes|Capacity)$"
)

_STRICT_MUTEX_CAPABILITY_SUBSTRINGS = (
    "Mutex", "Lock", "mutex", "lock", "Semaphore", "semaphore",
)

_BINOP_TO_LLVM = {
    "math.addInt64":      "add",
    "math.subtractInt64": "sub",
    "math.multiplyInt64": "mul",
    "math.divideInt64":   "sdiv",
    "math.moduloInt64":   "srem",
    # Bitwise / shift primitives. Single-instruction LLVM lowerings so the
    # stdlib `bit` module no longer emits O(k) multiply/divide loops to
    # emulate shifts and masks. `left` is the value, `right` is the other
    # operand (shift count for the shift ops). Shift counts must be in
    # [0, 63]; a count >= 64 is LLVM poison (matches the bit module's
    # documented "bitIndex must be in [0, 63]" contract).
    "math.bitwiseAndInt64":        "and_",
    "math.bitwiseOrInt64":         "or_",
    "math.bitwiseXorInt64":        "xor",
    "math.shiftLeftInt64":         "shl",
    "math.shiftRightLogicalInt64": "lshr",
    "math.shiftRightArithmeticInt64": "ashr",
}

# Floating-point binary ops keep their operands at their declared width (Float64 by
# default). The dispatcher distinguishes these from the integer set so it does
# not coerce double values down to i64.
_FBINOP_TO_LLVM = {
    "math.addFloat64":      "fadd",
    "math.subtractFloat64": "fsub",
    "math.multiplyFloat64": "fmul",
    "math.divideFloat64":   "fdiv",
}

_FCMP_TO_LLVM = {
    "math.equalFloat64":              "==",
    "math.notEqualFloat64":           "!=",
    "math.lessThanFloat64":           "<",
    "math.lessThanOrEqualFloat64":    "<=",
    "math.greaterThanFloat64":        ">",
    "math.greaterThanOrEqualFloat64": ">=",
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
    "math.equalInt64":              "==",
    "math.notEqualInt64":           "!=",
    "math.lessThanInt64":           "<",
    "math.lessThanOrEqualInt64":    "<=",
    "math.greaterThanInt64":        ">",
    "math.greaterThanOrEqualInt64": ">=",
}

_CMP_Int32_TO_LLVM = {
    "math.equalInt32":              "==",
    "math.notEqualInt32":           "!=",
    "math.lessThanInt32":           "<",
    "math.lessThanOrEqualInt32":    "<=",
    "math.greaterThanInt32":        ">",
    "math.greaterThanOrEqualInt32": ">=",
}


# Domain-typed methods. A call target of the form `TypeName.methodName`
# (where TypeName is a user-declared type alias) lowers to the primitive
# below based on the alias's underlying type. This preserves domain context
# in source (`CountdownValue.subtractPositiveStep` rather than
# `math.subtractInt64`) while reusing the existing primitive dispatch.
_DOMAIN_METHOD_TO_Float64_PRIMITIVE = {
    "add":              "math.addFloat64",
    "subtract":         "math.subtractFloat64",
    "multiply":         "math.multiplyFloat64",
    "divide":           "math.divideFloat64",
    "equal":            "math.equalFloat64",
    "notEqual":         "math.notEqualFloat64",
    "lessThan":         "math.lessThanFloat64",
    "lessThanOrEqual":  "math.lessThanOrEqualFloat64",
    "greaterThan":      "math.greaterThanFloat64",
    "greaterThanOrEqual": "math.greaterThanOrEqualFloat64",
}


_DOMAIN_METHOD_TO_Int64_PRIMITIVE = {
    # infallible (use plain `bind`)
    "add":                  "math.addInt64",
    "addPositiveStep":      "math.addInt64",
    "subtract":             "math.subtractInt64",
    "subtractStep":         "math.subtractInt64",
    "subtractPositiveStep": "math.subtractInt64",
    "multiply":             "math.multiplyInt64",
    "multiplyByStep":       "math.multiplyInt64",
    "multiplyByCounter":    "math.multiplyInt64",
    "divide":               "math.divideInt64",
    "modulo":               "math.moduloInt64",
    "moduloBy":             "math.moduloInt64",
    "equal":                "math.equalInt64",
    "notEqual":             "math.notEqualInt64",
    "lessThan":             "math.lessThanInt64",
    "lessThanOrEqual":      "math.lessThanOrEqualInt64",
    "greaterThan":          "math.greaterThanInt64",
    "greaterThanOrEqual":   "math.greaterThanOrEqualInt64",
    "square":               "math.multiplyInt64",
    # fallible (use bindOk + bindError + branchIfError)
    "checkedMultiply":           "math.checkedMultiplyInt64",
    "checkedMultiplyByCounter":  "math.checkedMultiplyInt64",
    "checkedMultiplyByStep":     "math.checkedMultiplyInt64",
}


# Domain methods for Int32-repr types and enums. Mirrors the Int64
# table; used when `TypeName.methodName` resolves to a Int32-shaped
# alias or to an enum with `repr Int32`. Supports equality and
# ordered comparison on int32-shaped enum cases like SaveTodosStatus.
_DOMAIN_METHOD_TO_Int32_PRIMITIVE = {
    "equal":                "math.equalInt32",
    "notEqual":             "math.notEqualInt32",
    "lessThan":             "math.lessThanInt32",
    "lessThanOrEqual":      "math.lessThanOrEqualInt32",
    "greaterThan":          "math.greaterThanInt32",
    "greaterThanOrEqual":   "math.greaterThanOrEqualInt32",
}


# ============================================================
# Codegen
# ============================================================

class Codegen:
    def __init__(self, prog: Program, runtime_checks: str = "off",
                 trace_events: bool = False):
        self.prog = prog
        self.runtime_checks = runtime_checks
        self.trace_events = trace_events
        self.module = ir.Module(name=prog.project_name or "semanticscript_module")
        # SEMSC_TRIPLE overrides the target triple so the same tape can be
        # lowered for a non-host target (e.g. wasm32-unknown-emscripten). The
        # triple gates platform-specific codegen such as the Windows SEH crash
        # filter, so retargeting here skips host-only paths cleanly.
        self.module.triple = os.environ.get("SEMSC_TRIPLE") or llvm.get_default_triple()
        self.provenance = CompilerProvenance(prog)
        self.strings = {}
        self._next_str_id = 0
        self._next_html_buffer_id = 0
        self._next_json_buffer_id = 0
        self._web_route_handler_names = set()
        self._trace_seq_global = None
        self._trace_decimal_writer_id = 0
        self._async_user_op_wrappers = {}
        # Reactive crash reporting (SSRUN002): a single internal i8* global
        # tracking the last semantic site entered, plus the emitted fatal-signal
        # handler. Both stay None until first use; see _crash_site_global /
        # _crash_handler_fn. Site tracking is emitted only in `panic` mode;
        # the handler installs whenever runtime checks are not `off`.
        self._crash_site_global = None
        self._crash_handler = None
        self._win_seh_filter = None
        # Shadow call stack for SSRUN002: a fixed-capacity array of frame
        # descriptor pointers plus a depth counter. Pushed/popped caller-side
        # around user-op calls so it stays balanced no matter which return path
        # the callee takes. Lets the handler print the SemanticScript operation
        # chain, not just the leaf site.
        self._crash_depth_global = None
        self._crash_frames_global = None
        self._crash_reported_global = None
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
        self._win_set_unhandled_exception_filter = None
        # LLVM signed-multiply-with-overflow intrinsic. Produces a literal
        # struct { i64 product, i1 overflowOccurred }. Used to lower checked
        # multiplication call targets so callers can branchIfError on the
        # overflow bit instead of silently wrapping.
        overflow_struct_ty = ir.LiteralStructType([Int64, I1])
        smul_overflow_ty = ir.FunctionType(overflow_struct_ty, [Int64, Int64])
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
            self._puts = ir.Function(self.module, ir.FunctionType(Int32, [Int8P]),
                                     name="puts")
        return self._puts

    @property
    def printf(self):
        if self._printf is None:
            self._printf = ir.Function(self.module,
                                       ir.FunctionType(Int32, [Int8P], var_arg=True),
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
                self.module, ir.FunctionType(Int8P, [Int32]),
                name="GetStdHandle")
        return self._win_get_std_handle

    @property
    def win_write_file(self):
        if self._win_write_file is None:
            self._win_write_file = ir.Function(
                self.module,
                ir.FunctionType(Int32, [Int8P, Int8P, Int32, Int32.as_pointer(), Int8P]),
                name="WriteFile")
        return self._win_write_file

    @property
    def posix_write(self):
        if self._posix_write is None:
            self._posix_write = ir.Function(
                self.module, ir.FunctionType(Int64, [Int32, Int8P, Int64]),
                name="write")
        return self._posix_write

    @property
    def win_set_unhandled_exception_filter(self):
        if self._win_set_unhandled_exception_filter is None:
            self._win_set_unhandled_exception_filter = ir.Function(
                self.module, ir.FunctionType(Int8P, [Int8P]),
                name="SetUnhandledExceptionFilter")
        return self._win_set_unhandled_exception_filter

    def _safe_block_name(self, raw: str) -> str:
        cleaned = re.sub(r"[^A-Za-z0-9_.]+", "_", raw or "runtime_check")
        return cleaned[:80] or "runtime_check"

    def _runtime_panic_lines(self, call, reason: str):
        path = self.prog.source_path or "<source>"
        line = call.get("line", 0)
        raw = self.prog.source_lines.get(line, "").strip()
        call_bits = ""
        display_target = call.get("source_target", call.get("target"))
        if call.get("name") and display_target:
            call_bits = f"{call['name']} -> {display_target}"
        elif call.get("name") or display_target:
            call_bits = call.get("name") or display_target
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
                self.win_get_std_handle, [ir.Constant(Int32, -12)],
                name="panicStderr")
            bytes_written = builder.alloca(Int32, name="panicBytesWritten")
            builder.call(self.win_write_file, [
                handle,
                ptr,
                ir.Constant(Int32, byte_count),
                bytes_written,
                ir.Constant(Int8P, None),
            ])
            return
        builder.call(self.posix_write, [
            ir.Constant(Int32, 2),
            ptr,
            ir.Constant(Int64, byte_count),
        ])

    def _emit_runtime_buffer_write(self, builder, ptr, byte_count_i32):
        triple = (self.module.triple or "").lower()
        if "windows" in triple or "win32" in triple or "msvc" in triple:
            handle = builder.call(
                self.win_get_std_handle, [ir.Constant(Int32, -12)],
                name="traceStderr")
            bytes_written = builder.alloca(Int32, name="traceBytesWritten")
            builder.call(self.win_write_file, [
                handle,
                ptr,
                byte_count_i32,
                bytes_written,
                ir.Constant(Int8P, None),
            ])
            return
        byte_count_i64 = builder.zext(byte_count_i32, Int64, name="traceWriteLen64")
        builder.call(self.posix_write, [
            ir.Constant(Int32, 2),
            ptr,
            byte_count_i64,
        ])

    def _trace_sequence_global(self):
        if self._trace_seq_global is None:
            gv = ir.GlobalVariable(self.module, Int64, name="as.trace.seq")
            gv.linkage = "internal"
            gv.global_constant = False
            gv.initializer = ir.Constant(Int64, 0)
            self._trace_seq_global = gv
        return self._trace_seq_global

    def _emit_runtime_const_write(self, builder, text: str):
        if not text:
            return
        ptr = self._i8p(builder, text)
        byte_count = len(text.encode("utf-8"))
        self._emit_runtime_buffer_write(builder, ptr, ir.Constant(Int32, byte_count))

    def _emit_runtime_u64_decimal_write(self, builder, value):
        writer_id = self._trace_decimal_writer_id
        self._trace_decimal_writer_id += 1
        fn = builder.function
        buffer_ty = ir.ArrayType(Int8, 32)
        buffer = builder.alloca(buffer_ty, name=f"traceSeqDigits{writer_id}")
        number_slot = builder.alloca(Int64, name=f"traceSeqNumber{writer_id}")
        index_slot = builder.alloca(Int32, name=f"traceSeqIndex{writer_id}")
        builder.store(value, number_slot)
        builder.store(ir.Constant(Int32, 32), index_slot)

        loop_block = fn.append_basic_block(f"traceSeqDigitsLoop{writer_id}")
        after_block = fn.append_basic_block(f"traceSeqDigitsDone{writer_id}")
        builder.branch(loop_block)
        builder.position_at_end(loop_block)

        number = builder.load(number_slot, name=f"traceSeqNumberLoad{writer_id}")
        digit = builder.urem(number, ir.Constant(Int64, 10),
                             name=f"traceSeqDigit{writer_id}")
        quotient = builder.udiv(number, ir.Constant(Int64, 10),
                                name=f"traceSeqQuotient{writer_id}")
        index = builder.load(index_slot, name=f"traceSeqIndexLoad{writer_id}")
        next_index = builder.sub(index, ir.Constant(Int32, 1),
                                 name=f"traceSeqNextIndex{writer_id}")
        digit_i8 = builder.trunc(digit, Int8, name=f"traceSeqDigitInt8{writer_id}")
        digit_char = builder.add(digit_i8, ir.Constant(Int8, ord("0")),
                                 name=f"traceSeqDigitChar{writer_id}")
        digit_ptr = builder.gep(
            buffer, [ir.Constant(Int32, 0), next_index],
            inbounds=True, name=f"traceSeqDigitPtr{writer_id}")
        builder.store(digit_char, digit_ptr)
        builder.store(next_index, index_slot)
        builder.store(quotient, number_slot)
        has_more = builder.icmp_unsigned("!=", quotient, ir.Constant(Int64, 0),
                                         name=f"traceSeqHasMore{writer_id}")
        builder.cbranch(has_more, loop_block, after_block)

        builder.position_at_end(after_block)
        start_index = builder.load(index_slot, name=f"traceSeqStart{writer_id}")
        byte_count = builder.sub(ir.Constant(Int32, 32), start_index,
                                 name=f"traceSeqDigitCount{writer_id}")
        start_ptr = builder.gep(
            buffer, [ir.Constant(Int32, 0), start_index],
            inbounds=True, name=f"traceSeqStartPtr{writer_id}")
        self._emit_runtime_buffer_write(builder, start_ptr, byte_count)

    def _trace_json_parts(self, event: str, site_kind: str,
                          operation: str = "", name: str = "",
                          target: str = "", lineno: int = 0,
                          value_name: str = "",
                          value_status: str = "") -> tuple[str, str, str]:
        payload = {
            "schemaVersion": "sem.traceEvent.v0",
            "runId": "native",
            "seq": "__SEM_TRACE_SEQ__",
            "timestampNs": "__SEM_TRACE_TIMESTAMP__",
            "timestampSource": "sequenceCounter",
            "event": event,
            "siteId": _trace_site_id(
                self.prog, site_kind, operation, name, target, lineno),
            "siteKind": site_kind,
            "operation": operation or "",
            "name": name or "",
            "target": target or "",
            "source": _json_source_span(self.prog, lineno),
        }
        if value_name or value_status:
            payload["valueName"] = value_name or ""
            payload["valueStatus"] = value_status or ""
        text = json.dumps(payload, separators=(",", ":"))
        seq_marker = '"__SEM_TRACE_SEQ__"'
        timestamp_marker = '"__SEM_TRACE_TIMESTAMP__"'
        prefix, rest = text.split(seq_marker, 1)
        middle, suffix = rest.split(timestamp_marker, 1)
        return prefix, middle, suffix + "\n"

    def _emit_trace_event(self, builder, event: str, site_kind: str,
                          operation: str = "", name: str = "",
                          target: str = "", lineno: int = 0,
                          value_name: str = "", value_status: str = ""):
        if not self.trace_events:
            return
        seq_global = self._trace_sequence_global()
        current_seq = builder.load(seq_global, name="traceSeqCurrent")
        next_seq = builder.add(current_seq, ir.Constant(Int64, 1), name="traceSeqNext")
        builder.store(next_seq, seq_global)
        prefix, middle, suffix = self._trace_json_parts(
            event, site_kind, operation, name, target, lineno,
            value_name=value_name, value_status=value_status)
        self._emit_runtime_const_write(builder, prefix)
        self._emit_runtime_u64_decimal_write(builder, next_seq)
        self._emit_runtime_const_write(builder, middle)
        self._emit_runtime_u64_decimal_write(builder, next_seq)
        self._emit_runtime_const_write(builder, suffix)

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

    # ---------- reactive crash reporting (SSRUN002) ----------
    # The guarded checks above (_emit_runtime_check) trap *before* undefined
    # behavior at the two sites we can predict (zero divisor, null buffer).
    # Everything else — a wild pointer load, a double free, a stack overflow,
    # an explicit abort() — reaches the CPU as a fatal signal. Without a
    # handler those die with only an exit code, which gives an agent nothing
    # to fix. SSRUN002 closes that gap: a fatal-signal handler that prints the
    # last semantic site the program entered, then re-raises so the real
    # signal disposition (exit status / core dump) is preserved.

    def _fatal_signal_table(self):
        """(number, name) pairs for the signals we install a handler for.
        Numbers differ by platform: the Windows CRT renumbers SIGABRT to 22
        and has no SIGBUS, so we cannot share one table."""
        triple = (self.module.triple or "").lower()
        is_windows = ("windows" in triple or "win32" in triple
                      or "msvc" in triple)
        if is_windows:
            return [(4, "SIGILL"), (8, "SIGFPE"), (11, "SIGSEGV"),
                    (22, "SIGABRT")]
        return [(4, "SIGILL"), (6, "SIGABRT"), (7, "SIGBUS"),
                (8, "SIGFPE"), (11, "SIGSEGV")]

    def _crash_site_global_var(self):
        if self._crash_site_global is None:
            gv = ir.GlobalVariable(self.module, Int8P, name="as.crash.site")
            gv.linkage = "internal"
            gv.global_constant = False
            start = self._make_str_global(
                "<program start; no operation entered>")
            gv.initializer = start.gep(
                [ir.Constant(Int32, 0), ir.Constant(Int32, 0)])
            self._crash_site_global = gv
        return self._crash_site_global

    def _crash_reported_global_var(self):
        # Once-guard shared by the signal handler and the Windows SEH filter:
        # set on first entry so a second fatal signal (reentrancy) or a fault
        # the CRT delivers to both paths reports exactly once.
        if self._crash_reported_global is None:
            gv = ir.GlobalVariable(self.module, Int32, name="as.crash.reported")
            gv.linkage = "internal"
            gv.global_constant = False
            gv.initializer = ir.Constant(Int32, 0)
            self._crash_reported_global = gv
        return self._crash_reported_global

    def _emit_crash_site_store(self, builder, descriptor: str):
        # Site tracking only exists in panic mode; traps mode hides source
        # context (matching SSRUN001), so there is nothing to record there.
        if self.runtime_checks != "panic":
            return
        # volatile so the optimizer never elides the store as "dead": the only
        # reader is the signal handler, reached via a runtime signal() that the
        # optimizer cannot see, so a non-volatile store is legally removable.
        store = builder.store(self._i8p(builder, descriptor),
                              self._crash_site_global_var())
        store.volatile = True

    # Bounded so a runaway recursion cannot grow the frame array without limit;
    # the depth counter still climbs past it, and printing clamps to this many.
    _CRASH_FRAME_CAPACITY = 64

    def _crash_depth_global_var(self):
        if self._crash_depth_global is None:
            gv = ir.GlobalVariable(self.module, Int32, name="as.crash.depth")
            gv.linkage = "internal"
            gv.global_constant = False
            gv.initializer = ir.Constant(Int32, 0)
            self._crash_depth_global = gv
        return self._crash_depth_global

    def _crash_frames_global_var(self):
        if self._crash_frames_global is None:
            arr_ty = ir.ArrayType(Int8P, self._CRASH_FRAME_CAPACITY)
            gv = ir.GlobalVariable(self.module, arr_ty, name="as.crash.frames")
            gv.linkage = "internal"
            gv.global_constant = False
            gv.initializer = ir.Constant(arr_ty, None)
            self._crash_frames_global = gv
        return self._crash_frames_global

    def _emit_crash_frame_push(self, builder, descriptor: str):
        if self.runtime_checks != "panic":
            return
        depth_gv = self._crash_depth_global_var()
        depth = builder.load(depth_gv, name="crashPushDepth")
        # Store the descriptor only while within capacity; always advance depth
        # so the matching pop stays balanced even past the cap.
        in_range = builder.icmp_signed(
            "<", depth, ir.Constant(Int32, self._CRASH_FRAME_CAPACITY),
            name="crashPushInRange")
        fn = builder.function
        store_bb = fn.append_basic_block("crashPushStore")
        cont_bb = fn.append_basic_block("crashPushCont")
        builder.cbranch(in_range, store_bb, cont_bb)
        builder.position_at_end(store_bb)
        slot = builder.gep(
            self._crash_frames_global_var(), [ir.Constant(Int32, 0), depth],
            inbounds=True, name="crashFrameSlot")
        # volatile: the frame array is read only by the signal handler, which
        # the optimizer cannot see is reachable, so non-volatile stores are
        # legally dead-code-eliminated and the printed stack goes empty.
        frame_store = builder.store(self._i8p(builder, descriptor), slot)
        frame_store.volatile = True
        builder.branch(cont_bb)
        builder.position_at_end(cont_bb)
        depth_store = builder.store(
            builder.add(depth, ir.Constant(Int32, 1)), depth_gv)
        depth_store.volatile = True

    def _emit_crash_frame_pop(self, builder):
        if self.runtime_checks != "panic":
            return
        depth_gv = self._crash_depth_global_var()
        depth = builder.load(depth_gv, name="crashPopDepth")
        positive = builder.icmp_signed(
            ">", depth, ir.Constant(Int32, 0), name="crashPopPositive")
        decremented = builder.sub(depth, ir.Constant(Int32, 1))
        # Guard against underflow if an unwrapped path ever pops too far.
        pop_store = builder.store(
            builder.select(positive, decremented, ir.Constant(Int32, 0)),
            depth_gv)
        pop_store.volatile = True

    def _emit_crash_stack_write(self, builder):
        """Emit a runtime loop that prints the shadow call stack outermost
        first. Only meaningful in panic mode, where frames were recorded."""
        if self.runtime_checks != "panic":
            return
        self._emit_runtime_const_write(
            builder, "\nCall stack (most recent last):\n")
        fn = builder.function
        depth = builder.load(self._crash_depth_global_var(), name="crashStackDepth")
        capped = builder.icmp_signed(
            ">", depth, ir.Constant(Int32, self._CRASH_FRAME_CAPACITY),
            name="crashStackCapped")
        count = builder.select(
            capped, ir.Constant(Int32, self._CRASH_FRAME_CAPACITY), depth,
            name="crashStackCount")
        index_slot = builder.alloca(Int32, name="crashStackIndex")
        builder.store(ir.Constant(Int32, 0), index_slot)
        loop_bb = fn.append_basic_block("crashStackLoop")
        body_bb = fn.append_basic_block("crashStackBody")
        done_bb = fn.append_basic_block("crashStackDone")
        builder.branch(loop_bb)
        builder.position_at_end(loop_bb)
        index = builder.load(index_slot, name="crashStackI")
        builder.cbranch(
            builder.icmp_signed("<", index, count, name="crashStackMore"),
            body_bb, done_bb)
        builder.position_at_end(body_bb)
        self._emit_runtime_const_write(builder, "  #")
        self._emit_runtime_u64_decimal_write(builder, builder.zext(index, Int64))
        self._emit_runtime_const_write(builder, " ")
        frame_ptr = builder.load(
            builder.gep(self._crash_frames_global_var(),
                        [ir.Constant(Int32, 0), index], inbounds=True,
                        name="crashStackSlot"),
            name="crashStackFrame")
        self._emit_runtime_cstr_write(builder, frame_ptr)
        self._emit_runtime_const_write(builder, "\n")
        builder.store(builder.add(index, ir.Constant(Int32, 1)), index_slot)
        builder.branch(loop_bb)
        builder.position_at_end(done_bb)

    def _emit_runtime_cstr_write(self, builder, ptr):
        """Write a NUL-terminated runtime i8* to stderr. Used by the signal
        handler for the dynamic last-site string, so length is not known at
        compile time. The raw write syscall is async-signal-safe; strlen is not
        on the POSIX safe list, but the only pointers ever passed here are
        interned NUL-terminated constants, and the handler resets to SIG_DFL
        first so a strlen fault terminates cleanly rather than re-entering."""
        strlen = self._libc_func("strlen")
        length = builder.call(strlen, [ptr], name="crashSiteLen")
        if length.type != Int64:
            length = builder.zext(length, Int64)
        triple = (self.module.triple or "").lower()
        if "windows" in triple or "win32" in triple or "msvc" in triple:
            handle = builder.call(
                self.win_get_std_handle, [ir.Constant(Int32, -12)],
                name="crashStderr")
            bytes_written = builder.alloca(Int32, name="crashBytesWritten")
            builder.call(self.win_write_file, [
                handle, ptr, builder.trunc(length, Int32),
                bytes_written, ir.Constant(Int8P, None),
            ])
            return
        builder.call(self.posix_write, [ir.Constant(Int32, 2), ptr, length])

    def _ssrun002_header_lines(self):
        return [
            "error SSRUN002: SemanticScript native fault",
            "--------------------------------------------",
            "status: fatal signal delivered; runtime caught it before exit",
            "reason: the process received a fatal signal that no guarded "
            "check could prevent",
        ]

    def _win_exception_table(self):
        """(code, name) pairs for the Windows structured exceptions a faulting
        program is most likely to raise. Codes are NTSTATUS values; they are
        stored as Python ints and narrowed to signed i32 at constant time."""
        return [
            (0xC0000005, "ACCESS_VIOLATION"),
            (0xC00000FD, "STACK_OVERFLOW"),
            (0xC0000094, "INTEGER_DIVIDE_BY_ZERO"),
            (0xC000001D, "ILLEGAL_INSTRUCTION"),
            (0xC0000409, "FAST_FAIL"),
            (0x80000003, "BREAKPOINT"),
        ]

    def _emit_fault_name_write(self, builder, value, table, prefix):
        """Emit an if-chain that writes the symbolic name matching `value`
        (an i32) from `table`, or `unknown` if none match. `prefix` keeps the
        generated block names unique between the signal and SEH handlers."""
        fn = builder.function
        done_bb = fn.append_basic_block(f"{prefix}NameDone")
        for code, name in table:
            signed = code if code < 2 ** 31 else code - 2 ** 32
            match_bb = fn.append_basic_block(f"{prefix}_{name}")
            next_bb = fn.append_basic_block(f"{prefix}Next_{name}")
            is_match = builder.icmp_signed(
                "==", value, ir.Constant(Int32, signed),
                name=f"{prefix}Is{name}")
            builder.cbranch(is_match, match_bb, next_bb)
            builder.position_at_end(match_bb)
            self._emit_runtime_const_write(builder, name)
            builder.branch(done_bb)
            builder.position_at_end(next_bb)
        self._emit_runtime_const_write(builder, "unknown")
        builder.branch(done_bb)
        builder.position_at_end(done_bb)

    def _emit_ssrun002_intro(self, builder):
        """Write the shared header + last-site block. Both the POSIX signal
        handler and the Windows SEH filter call this; they differ only in how
        they name the fault and what they do after reporting."""
        self._emit_runtime_const_write(
            builder, "\n".join(self._ssrun002_header_lines()) + "\n")
        if self.runtime_checks == "panic":
            self._emit_crash_stack_write(builder)
            self._emit_runtime_const_write(builder, "\nLast site:\n  ")
            site = builder.load(self._crash_site_global_var(),
                                name="crashSite")
            self._emit_runtime_cstr_write(builder, site)
            self._emit_runtime_const_write(builder, "\n")

    def _emit_ssrun002_direction(self, builder):
        if self.runtime_checks == "panic":
            text = ("\nDirection:\n  Inspect the operation named in Last site; "
                    "the fault is on or just after that row.\n")
        else:
            text = ("\nDirection:\n  Rebuild with --build-profile dev (or "
                    "--runtime-checks panic) to capture the faulting operation "
                    "and source row.\n")
        self._emit_runtime_const_write(builder, text)

    def _crash_handler_fn(self):
        if self._crash_handler is not None:
            return self._crash_handler
        fn = ir.Function(self.module, ir.FunctionType(VOID, [Int32]),
                         name="as.crash.handler")
        fn.args[0].name = "signum"
        self._crash_handler = fn
        builder = ir.IRBuilder(fn.append_basic_block("entry"))
        signum = fn.args[0]
        signal_fn = self._libc_func("signal")
        raise_fn = self._libc_func("raise")
        # Restore the default disposition for this signal BEFORE doing anything
        # else. If reporting itself faults (e.g. a corrupt site pointer), the
        # recurrence now terminates cleanly instead of re-entering the handler
        # and looping. The matching raise() at the end then delivers the fatal
        # signal with its real exit status / core dump.
        builder.call(signal_fn, [signum, ir.Constant(Int8P, None)])
        # Once-guard: a second fatal signal, or a fault the CRT also routes to
        # the SEH filter, must not print a second SSRUN002 block.
        reported_gv = self._crash_reported_global_var()
        already = builder.load(reported_gv, name="crashAlreadyReported")
        handler_mark = builder.store(ir.Constant(Int32, 1), reported_gv)
        handler_mark.volatile = True
        is_first = builder.icmp_signed(
            "==", already, ir.Constant(Int32, 0), name="crashFirstReport")
        report_bb = fn.append_basic_block("crashReport")
        reraise_bb = fn.append_basic_block("crashReraise")
        builder.cbranch(is_first, report_bb, reraise_bb)
        builder.position_at_end(report_bb)
        self._emit_ssrun002_intro(builder)
        self._emit_runtime_const_write(builder, "\nSignal: ")
        self._emit_runtime_u64_decimal_write(
            builder, builder.zext(signum, Int64))
        self._emit_runtime_const_write(builder, " (")
        self._emit_fault_name_write(
            builder, signum, self._fatal_signal_table(), "crashSig")
        self._emit_runtime_const_write(builder, ")\n")
        self._emit_ssrun002_direction(builder)
        builder.branch(reraise_bb)
        builder.position_at_end(reraise_bb)
        builder.call(raise_fn, [signum])
        builder.ret_void()
        return fn

    def _win_seh_filter_fn(self):
        """Windows top-level exception filter. The CRT `signal()` handler does
        NOT see hardware faults (access violations, stack overflow) — those are
        SEH exceptions. SetUnhandledExceptionFilter is the seam that does, so
        the most common real crash on Windows still reports SSRUN002 context."""
        if self._win_seh_filter is not None:
            return self._win_seh_filter
        fn = ir.Function(self.module, ir.FunctionType(Int32, [Int8P]),
                         name="as.crash.sehFilter")
        fn.args[0].name = "excPointers"
        self._win_seh_filter = fn
        builder = ir.IRBuilder(fn.append_basic_block("entry"))
        terminate_bb = fn.append_basic_block("sehTerminate")
        # Once-guard: if the signal handler already reported (or this filter
        # ran before), terminate without a second SSRUN002 block.
        reported_gv = self._crash_reported_global_var()
        already = builder.load(reported_gv, name="sehAlreadyReported")
        seh_mark = builder.store(ir.Constant(Int32, 1), reported_gv)
        seh_mark.volatile = True
        first_bb = fn.append_basic_block("sehReport")
        builder.cbranch(
            builder.icmp_signed("==", already, ir.Constant(Int32, 0),
                                name="sehFirstReport"),
            first_bb, terminate_bb)
        builder.position_at_end(first_bb)
        # EXCEPTION_POINTERS { EXCEPTION_RECORD* ExceptionRecord; CONTEXT*; }
        # EXCEPTION_RECORD's first field is DWORD ExceptionCode, so the fault
        # code is *(*(EXCEPTION_POINTERS*)arg). Guard the deref: a malformed or
        # null pointers/record would otherwise fault inside the filter and loop.
        ptrs_ty = ir.LiteralStructType([Int8P, Int8P]).as_pointer()
        ptrs = builder.bitcast(fn.args[0], ptrs_ty, name="excPtrsTyped")
        self._emit_ssrun002_intro(builder)
        self._emit_runtime_const_write(builder, "\nException: ")
        ptrs_null = builder.icmp_unsigned(
            "==", fn.args[0], ir.Constant(Int8P, None), name="excPtrsNull")
        record = builder.load(
            builder.gep(ptrs, [ir.Constant(Int32, 0), ir.Constant(Int32, 0)],
                        inbounds=True), name="excRecord")
        record_null = builder.icmp_unsigned(
            "==", record, ir.Constant(Int8P, None), name="excRecordNull")
        missing = builder.or_(ptrs_null, record_null, name="excMissing")
        have_bb = fn.append_basic_block("sehHaveRecord")
        no_record_bb = fn.append_basic_block("sehNoRecord")
        after_bb = fn.append_basic_block("sehAfterName")
        builder.cbranch(missing, no_record_bb, have_bb)
        builder.position_at_end(have_bb)
        code = builder.load(
            builder.bitcast(record, Int32.as_pointer()), name="excCode")
        self._emit_fault_name_write(
            builder, code, self._win_exception_table(), "crashSeh")
        self._emit_runtime_const_write(builder, " (code ")
        self._emit_runtime_u64_decimal_write(builder, builder.zext(code, Int64))
        self._emit_runtime_const_write(builder, ")\n")
        builder.branch(after_bb)
        builder.position_at_end(no_record_bb)
        self._emit_runtime_const_write(builder, "unknown (no exception record)\n")
        builder.branch(after_bb)
        builder.position_at_end(after_bb)
        self._emit_ssrun002_direction(builder)
        builder.branch(terminate_bb)
        builder.position_at_end(terminate_bb)
        # EXCEPTION_EXECUTE_HANDLER (1): stop the search and let the process
        # terminate with the fault instead of returning to the faulting code.
        builder.ret(ir.Constant(Int32, 1))
        return fn

    def _install_crash_handler(self, builder):
        if self.runtime_checks == "off":
            return
        handler = self._crash_handler_fn()
        handler_ptr = builder.bitcast(handler, Int8P, name="crashHandlerPtr")
        signal_fn = self._libc_func("signal")
        for num, _name in self._fatal_signal_table():
            builder.call(signal_fn, [ir.Constant(Int32, num), handler_ptr])
        triple = (self.module.triple or "").lower()
        if "windows" in triple or "win32" in triple or "msvc" in triple:
            seh_ptr = builder.bitcast(
                self._win_seh_filter_fn(), Int8P, name="sehFilterPtr")
            builder.call(self.win_set_unhandled_exception_filter, [seh_ptr])

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

    def _async_user_op_wrapper(self, op_name: str, op_info: dict):
        cached = self._async_user_op_wrappers.get(op_name)
        if cached is not None:
            return cached

        ret_ty = op_info["return_type"]
        param_tys = [param[1] for param in op_info["params"]]
        context_ty = ir.LiteralStructType([Int8P, Int32, ret_ty] + param_tys)
        context_ptr_ty = context_ty.as_pointer()
        safe_name = re.sub(r"[^A-Za-z0-9_]", "_", op_name)
        work_fn_ty = ir.FunctionType(VOID, [Int8P])
        after_fn_ty = ir.FunctionType(VOID, [Int8P, Int32])

        work_fn = ir.Function(
            self.module,
            work_fn_ty,
            name=f"__sem_async_work_{safe_name}")
        work_builder = ir.IRBuilder(work_fn.append_basic_block("entry"))
        work_context = work_builder.bitcast(
            work_fn.args[0], context_ptr_ty, name="ctx")
        arg_values = []
        zero = ir.Constant(Int32, 0)
        for index, _param_ty in enumerate(param_tys, start=3):
            arg_ptr = work_builder.gep(
                work_context,
                [zero, ir.Constant(Int32, index)],
                inbounds=True,
                name=f"arg{index - 3}_ptr")
            arg_values.append(
                work_builder.load(arg_ptr, name=f"arg{index - 3}"))
        result = work_builder.call(
            op_info["fn"], arg_values, name=f"{safe_name}_result")
        result_ptr = work_builder.gep(
            work_context,
            [zero, ir.Constant(Int32, 2)],
            inbounds=True,
            name="result_ptr")
        work_builder.store(result, result_ptr)
        work_builder.ret_void()

        after_fn = ir.Function(
            self.module,
            after_fn_ty,
            name=f"__sem_async_after_{safe_name}")
        after_builder = ir.IRBuilder(after_fn.append_basic_block("entry"))
        after_context = after_builder.bitcast(
            after_fn.args[0], context_ptr_ty, name="ctx")
        future_ptr = after_builder.gep(
            after_context,
            [zero, zero],
            inbounds=True,
            name="future_ptr")
        future = after_builder.load(future_ptr, name="future")
        complete_fn = self._runtime_func(
            "ss_async_future_complete", Int32, [Int8P, Int32, Int8P])
        after_builder.call(
            complete_fn,
            [future, after_fn.args[1], after_fn.args[0]])
        after_builder.ret_void()

        # Over-allocate by slot count instead of reverse-engineering every
        # target ABI's struct layout. The context only stores scalar/pointer
        # values that this compiler already knows how to pass at the ABI
        # boundary, and every supported target currently has <= 8-byte scalar
        # alignment.
        context_size = 64 + (len(context_ty.elements) * 8)
        cached = {
            "context_ty": context_ty,
            "context_ptr_ty": context_ptr_ty,
            "context_size": context_size,
            "work_fn": work_fn,
            "after_fn": after_fn,
            "work_fn_ptr_ty": work_fn_ty.as_pointer(),
            "after_fn_ptr_ty": after_fn_ty.as_pointer(),
        }
        self._async_user_op_wrappers[op_name] = cached
        return cached

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
            return builder.zext(result_bool, Int32)
        if classifier == "isinf":
            # |x| == inf
            inf = ir.Constant(Float64, float("inf"))
            abs_x = builder.call(self._llvm_fabs_f64(), [x], name=name + "_abs")
            eq = builder.fcmp_ordered("==", abs_x, inf, name=name + "_eq")
            return builder.zext(eq, Int32)
        if classifier == "isfinite":
            # |x| < inf  (also rules out NaN because NaN < anything is false)
            inf = ir.Constant(Float64, float("inf"))
            abs_x = builder.call(self._llvm_fabs_f64(), [x], name=name + "_abs")
            lt = builder.fcmp_ordered("<", abs_x, inf, name=name + "_lt")
            return builder.zext(lt, Int32)
        if classifier == "isnormal":
            # |x| is finite AND |x| >= DBL_MIN (normal positive). This is the
            # spec definition: normal floats are non-zero, finite, and not
            # subnormal. DBL_MIN = 2^-1022.
            dbl_min = ir.Constant(Float64, 2.2250738585072014e-308)
            inf = ir.Constant(Float64, float("inf"))
            abs_x = builder.call(self._llvm_fabs_f64(), [x], name=name + "_abs")
            lt_inf = builder.fcmp_ordered("<", abs_x, inf, name=name + "_lt_inf")
            ge_min = builder.fcmp_ordered(">=", abs_x, dbl_min, name=name + "_ge_min")
            both = builder.and_(lt_inf, ge_min, name=name + "_both")
            return builder.zext(both, Int32)
        if classifier == "signbit":
            # Read the sign bit by reinterpreting the double as i64.
            i64_bits = builder.bitcast(x, Int64, name=name + "_bits")
            shifted = builder.lshr(i64_bits, ir.Constant(Int64, 63),
                                    name=name + "_shift")
            return builder.trunc(shifted, Int32)
        if classifier == "fpclassify":
            # Returns FP_INFINITE, FP_NAN, FP_NORMAL, FP_SUBNORMAL, FP_ZERO.
            # Implementation-defined integer values; we use the MSVC values
            # (1, 2, -1, -2, 0). The result is computed by chained selects.
            FP_NAN, FP_INFINITE, FP_ZERO, FP_SUBNORMAL, FP_NORMAL = 2, 1, 0, -2, -1
            inf = ir.Constant(Float64, float("inf"))
            zero = ir.Constant(Float64, 0.0)
            dbl_min = ir.Constant(Float64, 2.2250738585072014e-308)
            abs_x = builder.call(self._llvm_fabs_f64(), [x], name=name + "_abs")
            is_nan = builder.fcmp_unordered("uno", x, x, name=name + "_uno")
            is_inf = builder.fcmp_ordered("==", abs_x, inf, name=name + "_inf")
            is_zero = builder.fcmp_ordered("==", x, zero, name=name + "_zero")
            is_subnormal = builder.fcmp_ordered("<", abs_x, dbl_min,
                                                 name=name + "_sub")
            result_normal = ir.Constant(Int32, FP_NORMAL)
            result_subnorm = builder.select(is_subnormal,
                ir.Constant(Int32, FP_SUBNORMAL), result_normal,
                name=name + "_sel_sub")
            result_zero = builder.select(is_zero, ir.Constant(Int32, FP_ZERO),
                result_subnorm, name=name + "_sel_zero")
            result_inf = builder.select(is_inf, ir.Constant(Int32, FP_INFINITE),
                result_zero, name=name + "_sel_inf")
            return builder.select(is_nan, ir.Constant(Int32, FP_NAN),
                result_inf, name=name + "_sel_nan")
        raise ValueError(f"unknown math classifier: {classifier}")

    def _llvm_fabs_f64(self):
        """Get-or-declare the LLVM `llvm.fabs.f64` intrinsic."""
        for fn in self.module.functions:
            if fn.name == "llvm.fabs.f64":
                return fn
        fnty = ir.FunctionType(Float64, [Float64])
        return ir.Function(self.module, fnty, name="llvm.fabs.f64")

    def _promote_for_vararg(self, builder, value):
        """C variadic ABI: integer args < int are promoted to int; float is
        promoted to double. Apply the same promotion here so call-site types
        match what printf/scanf expect."""
        if isinstance(value.type, ir.IntType) and value.type.width < 32:
            return builder.sext(value, Int32)
        if isinstance(value.type, ir.FloatType):
            return builder.fpext(value, Float64)
        return value

    def _libc_stream(self, name: str):
        """Return the i8* SSA value of a libc stdio stream global."""
        if name in self._libc_streams:
            return self._libc_streams[name]
        # On MSVC the streams are accessed via __acrt_iob_func(stream_id);
        # the simplest portable mapping is to declare the symbol as a
        # `FILE*` global and let the linker resolve it. llvmlite emits
        # external globals when no initializer is set.
        gv = ir.GlobalVariable(self.module, Int8P, name=f"as_{name}")
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
        zero = ir.Constant(Int32, 0)
        return builder.gep(gv, [zero, zero], inbounds=True)

    def _html_mask_raw_text_elements(self, body: str) -> str:
        chars = list(body)
        for match in _HTML_RAW_TEXT_RE.finditer(body):
            for index in range(match.start(), match.end()):
                chars[index] = " "
        return "".join(chars)

    def _html_find_tag_end(self, body: str, tag_start: int) -> int:
        quote = None
        index = tag_start + 1
        while index < len(body):
            char = body[index]
            if quote is not None:
                if char == quote:
                    quote = None
            elif char in ("\"", "'"):
                quote = char
            elif char == ">":
                return index
            index += 1
        return -1

    def _validate_html_template_structure(self, template: HtmlTemplate,
                                          body: str) -> None:
        index = 0
        while index < len(body):
            tag_start = body.find("<", index)
            if tag_start == -1:
                return
            if body.startswith("<!--", tag_start):
                comment_end = body.find("-->", tag_start + 4)
                if comment_end == -1:
                    raise ValueError(
                        f"htmlBody {template.name}: unterminated HTML comment")
                index = comment_end + 3
                continue
            tag_end = self._html_find_tag_end(body, tag_start)
            if tag_end == -1:
                raise ValueError(
                    f"htmlBody {template.name}: unterminated HTML tag")
            tag_text = body[tag_start + 1:tag_end].strip()
            if tag_text in {"", "/"}:
                index = tag_end + 1
                continue
            if tag_text.startswith("{") or tag_text.startswith("/{"):
                index = tag_end + 1
                continue
            if tag_text.startswith("!") or tag_text.startswith("?"):
                index = tag_end + 1
                continue
            name_offset = 1 if tag_text.startswith("/") else 0
            while name_offset < len(tag_text) and tag_text[name_offset].isspace():
                name_offset += 1
            tag_name_match = _HTML_ATTR_NAME_RE.match(tag_text, name_offset)
            if tag_name_match is None:
                raise ValueError(
                    f"htmlBody {template.name}: malformed HTML tag `{tag_text}`")
            tag_name = tag_name_match.group(0).lower()
            if (not tag_text.startswith("/")
                    and tag_name in {"script", "style"}):
                close_match = re.search(
                    rf"</\s*{re.escape(tag_name)}\s*>",
                    body[tag_end + 1:],
                    re.IGNORECASE,
                )
                if close_match is None:
                    raise ValueError(
                        f"htmlBody {template.name}: raw `{tag_name}` element "
                        "is missing a closing tag")
                index = tag_end + 1 + close_match.end()
                continue
            index = tag_end + 1

    def _validate_html_dynamic_holes(self, template: HtmlTemplate, body: str):
        self._validate_html_template_structure(template, body)
        masked = self._html_mask_raw_text_elements(body)
        html_hole_spans = {
            (match.start(), match.end())
            for match in _HTML_HOLE_REFERENCE_RE.finditer(masked)
        }
        for match in _HTML_BRACE_CONTENT_RE.finditer(masked):
            if (match.start(), match.end()) in html_hole_spans:
                continue
            content = match.group(1).strip()
            if not content:
                continue
            raise ValueError(
                f"htmlBody {template.name}: dynamic hole `{{{content}}}` "
                "must be a bare name or dotted field path")

    def _html_hole_context_from_tag(self, body: str, tag_start: int,
                                    hole_start: int):
        index = tag_start + 1
        if body.startswith("!--", index):
            return "comment", None
        if index < hole_start and body[index] in ("!", "?"):
            return "doctype", None
        if index < hole_start and body[index] == "/":
            index += 1
        while index < hole_start and body[index].isspace():
            index += 1
        tag_name = _HTML_ATTR_NAME_RE.match(body, index)
        if tag_name is None:
            return "tag", None
        if hole_start <= tag_name.end():
            return "tag", None
        index = tag_name.end()

        while index <= hole_start:
            while index < hole_start and body[index].isspace():
                index += 1
            if index == hole_start and hole_start < len(body) and body[hole_start] == "{":
                return "booleanAttribute", None
            if index >= hole_start:
                return "tag", None
            if body[index] in "/>":
                return "tag", None
            attr_match = _HTML_ATTR_NAME_RE.match(body, index)
            if attr_match is None:
                return "tag", None
            attr_name = attr_match.group(0).lower()
            if hole_start <= attr_match.end():
                return "tag", attr_name
            index = attr_match.end()
            while index < hole_start and body[index].isspace():
                index += 1
            if index == hole_start and hole_start < len(body) and body[hole_start] == "{":
                if attr_name in _HTML_BOOLEAN_ATTRS:
                    return "booleanAttribute", attr_name
                return "tag", attr_name
            if index >= hole_start:
                return "tag", attr_name
            if body[index] != "=":
                continue
            index += 1
            while index < hole_start and body[index].isspace():
                index += 1
            if index >= hole_start:
                return "unquotedAttribute", attr_name
            if body[index] in ("\"", "'"):
                quote = body[index]
                value_start = index + 1
                quote_end = body.find(quote, value_start)
                if quote_end == -1 or hole_start <= quote_end:
                    return "attribute", attr_name
                index = quote_end + 1
                continue
            value_start = index
            while (index < hole_start and not body[index].isspace()
                   and body[index] not in "/>"):
                index += 1
            if value_start <= hole_start <= index:
                return "unquotedAttribute", attr_name
        return "tag", None

    def _html_hole_context(self, body: str, hole_start: int):
        for raw_match in _HTML_RAW_TEXT_RE.finditer(body):
            if raw_match.start() < hole_start < raw_match.end():
                return "rawText", raw_match.group(1).lower()
        comment_start = body.rfind("<!--", 0, hole_start)
        comment_end = body.rfind("-->", 0, hole_start)
        if comment_start > comment_end:
            return "comment", None
        last_lt = body.rfind("<", 0, hole_start)
        last_gt = body.rfind(">", 0, hole_start)
        if last_lt <= last_gt:
            return "text", None
        return self._html_hole_context_from_tag(body, last_lt, hole_start)

    def _validate_html_arg_context(self, template: HtmlTemplate, arg_name: str,
                                   type_name: str, context_kind: str,
                                   attr_name):
        resolved = (
            type_name if type_name in _HTML_TRUST_TYPES
            else resolve_alias(self.prog, type_name)
        )
        if context_kind == "tag":
            raise ValueError(
                f"htmlBody {template.name}: hole `{arg_name}` cannot "
                "hydrate HTML tag syntax; dynamic holes must be text content "
                "or quoted attribute values")
        if context_kind == "comment":
            raise ValueError(
                f"htmlBody {template.name}: hole `{arg_name}` cannot "
                "hydrate HTML comments")
        if context_kind == "doctype":
            raise ValueError(
                f"htmlBody {template.name}: hole `{arg_name}` cannot "
                "hydrate HTML doctypes or declarations")
        if context_kind == "rawText":
            raise ValueError(
                f"htmlBody {template.name}: hole `{arg_name}` cannot "
                f"hydrate raw `{attr_name}` text")
        if context_kind == "unquotedAttribute":
            raise ValueError(
                f"htmlBody {template.name}: attribute hole `{arg_name}` "
                f"for `{attr_name}` must be inside a quoted attribute value")
        if context_kind == "booleanAttribute":
            if attr_name:
                target = f"boolean attribute `{attr_name}`"
            else:
                target = "boolean or dynamic attribute syntax"
            raise ValueError(
                f"htmlBody {template.name}: hole `{arg_name}` cannot hydrate "
                f"{target}; boolean attribute presence must be static")
        if resolved in _HTML_STRING_TYPES:
            is_string_like = True
        else:
            is_string_like = resolve_alias(self.prog, resolved) in _HTML_STRING_TYPES
        if context_kind == "text":
            if not is_string_like and resolved not in _HTML_FRAGMENT_TYPES:
                raise ValueError(
                    f"htmlBody {template.name}: hole `{arg_name}` has "
                    f"type `{type_name}`; text holes require String or "
                    "an explicit HTML fragment/document type")
            return
        if context_kind != "attribute":
            return
        if resolved in _HTML_FRAGMENT_TYPES:
            raise ValueError(
                f"htmlBody {template.name}: hole `{arg_name}` has "
                f"type `{type_name}` and cannot hydrate attribute `{attr_name}`")
        if attr_name in _HTML_BOOLEAN_ATTRS:
            raise ValueError(
                f"htmlBody {template.name}: dynamic boolean attribute "
                f"`{attr_name}` hole `{arg_name}` is rejected; boolean "
                "attribute presence must be static")
        if attr_name in _HTML_URL_ATTRS:
            raise ValueError(
                f"htmlBody {template.name}: dynamic `{attr_name}` attribute "
                f"hole `{arg_name}` is rejected; URL-bearing attributes must "
                "be static until a dedicated safe-url contract exists")
        if not is_string_like:
            raise ValueError(
                f"htmlBody {template.name}: attribute hole "
                f"`{arg_name}` requires a string-like type, got `{type_name}`")

    def _html_arg_escape_mode(self, type_name: str, context_kind: str):
        resolved = (
            type_name if type_name in _HTML_TRUST_TYPES
            else resolve_alias(self.prog, type_name)
        )
        if context_kind == "text" and resolved in _HTML_FRAGMENT_TYPES:
            return "raw"
        if context_kind == "attribute":
            return "attribute"
        if resolved in _HTML_STRING_TYPES:
            return "text"
        return "raw"

    def _html_template_parts_and_args(self, template: HtmlTemplate):
        if not template.body_lines:
            raise ValueError(
                f"htmlBody {template.name}: template has no body lines")
        declared_arg_types = {name: typ for name, typ, _line in template.args}
        required_roots = {}
        parts = []
        body = "\n".join(line for line, _lineno in template.body_lines)
        if template.body_lines:
            body += "\n"
        self._validate_html_dynamic_holes(template, body)
        cursor = 0
        for match in _HTML_HOLE_REFERENCE_RE.finditer(body):
            static_text = body[cursor:match.start()]
            if static_text:
                parts.append(("static", static_text, None, None))
            hole_path = match.group(1)
            arg_name = hole_path.split(".", 1)[0]
            if declared_arg_types and arg_name not in declared_arg_types:
                raise ValueError(
                    f"htmlBody {template.name}: unknown html hole `{arg_name}`")
            required_roots.setdefault(arg_name, declared_arg_types.get(arg_name))
            context_kind, attr_name = self._html_hole_context(body, match.start())
            parts.append(("arg", hole_path, context_kind, attr_name))
            cursor = match.end()
        tail_text = body[cursor:]
        if tail_text:
            parts.append(("static", tail_text, None, None))
        return parts, required_roots

    def _html_arg_as_cstring(self, builder, value, arg_name: str, type_name: str):
        resolved = (
            type_name if type_name in _HTML_TRUST_TYPES
            else resolve_alias(self.prog, type_name)
        )
        if resolved not in (_HTML_STRING_TYPES | _HTML_FRAGMENT_TYPES):
            raise ValueError(
                f"html hole `{arg_name}` has type `{type_name}`; "
                "html.hydrate requires String or an explicit HTML fragment/document type")
        if isinstance(value.type, ir.IntType):
            return builder.inttoptr(value, Int8P)
        if isinstance(value.type, ir.PointerType) and value.type != Int8P:
            return builder.bitcast(value, Int8P)
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
        one = ir.Constant(Int64, 1)
        zero_byte = ir.Constant(Int8, 0)

        builder.branch(loop_block)
        builder.position_at_end(loop_block)
        src_phi = builder.phi(Int8P, name=f"{name_hint}_src")
        dst_phi = builder.phi(Int8P, name=f"{name_hint}_dst")
        src_phi.add_incoming(source_ptr, entry_block)
        dst_phi.add_incoming(write_ptr, entry_block)
        ch = builder.load(src_phi, name=f"{name_hint}_ch")
        done = builder.icmp_unsigned("==", ch, zero_byte, name=f"{name_hint}_is_end")
        dst_offset = builder.ptrtoint(dst_phi, Int64, name=f"{name_hint}_dst_addr")
        limit_offset = builder.ptrtoint(limit_ptr, Int64, name=f"{name_hint}_limit_addr")
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
        one = ir.Constant(Int64, 1)
        zero_byte = ir.Constant(Int8, 0)

        builder.branch(loop_block)
        builder.position_at_end(loop_block)
        src_phi = builder.phi(Int8P, name=f"{name_hint}_escape_src")
        dst_phi = builder.phi(Int8P, name=f"{name_hint}_escape_dst")
        src_phi.add_incoming(source_ptr, entry_block)
        dst_phi.add_incoming(write_ptr, entry_block)
        ch = builder.load(src_phi, name=f"{name_hint}_escape_ch")
        done = builder.icmp_unsigned("==", ch, zero_byte,
                                     name=f"{name_hint}_escape_is_end")
        dst_offset = builder.ptrtoint(dst_phi, Int64,
                                      name=f"{name_hint}_escape_dst_addr")
        limit_offset = builder.ptrtoint(limit_ptr, Int64,
                                        name=f"{name_hint}_escape_limit_addr")
        at_limit = builder.icmp_unsigned(
            ">=", dst_offset, limit_offset, name=f"{name_hint}_escape_at_limit")
        should_stop = builder.or_(done, at_limit, name=f"{name_hint}_escape_stop")
        builder.cbranch(should_stop, done_block, check_blocks[0])

        for index, (byte_value, suffix, entity_text) in enumerate(checks):
            builder.position_at_end(check_blocks[index])
            is_match = builder.icmp_unsigned(
                "==", ch, ir.Constant(Int8, byte_value),
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
                           arg_val_named, arg_path_named=None):
        parts, required_roots = self._html_template_parts_and_args(template)
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
        arg_types = dict(call.get("arg_types", {}))
        for required_arg, declared_type in required_roots.items():
            if required_arg not in call["args"]:
                raise ValueError(
                    f"{call_name}: missing required arg `{required_arg}` "
                    f"for htmlTemplate `{template.name}`")
            if declared_type and required_arg in arg_types:
                resolved_declared = resolve_alias(self.prog, declared_type)
                resolved_provided = resolve_alias(self.prog, arg_types[required_arg])
                if resolved_declared != resolved_provided:
                    raise ValueError(
                        f"{call_name}: arg `{required_arg}` has type "
                        f"`{arg_types[required_arg]}` but htmlTemplate "
                        f"`{template.name}` declared `{declared_type}`")
        for provided_arg in call["args"]:
            if provided_arg not in required_roots:
                raise ValueError(
                    f"{call_name}: arg `{provided_arg}` is not declared by "
                    f"htmlTemplate `{template.name}`")
        array_ty = ir.ArrayType(Int8, buffer_size)
        buffer_name = f"as.htmlbuf.{self._next_html_buffer_id}.{call_name}"
        self._next_html_buffer_id += 1
        html_buffer = ir.GlobalVariable(self.module, array_ty, name=buffer_name)
        html_buffer.linkage = "internal"
        html_buffer.global_constant = False
        html_buffer.initializer = ir.Constant(array_ty, bytearray(buffer_size))
        zero = ir.Constant(Int32, 0)
        buffer_ptr = builder.gep(html_buffer, [zero, zero], inbounds=True)
        limit_ptr = builder.gep(
            buffer_ptr, [ir.Constant(Int64, buffer_size - 1)],
            name=f"{call_name}_html_limit")
        write_ptr = buffer_ptr
        arg_index = 0
        for part_index, (kind, value_text, context_kind, attr_name) in enumerate(parts):
            if kind == "static":
                write_ptr = self._emit_html_append_static(
                    builder, write_ptr, limit_ptr, value_text,
                    f"{call_name}_{part_index}_static")
                continue
            hole_path = value_text
            arg_name = hole_path.split(".", 1)[0]
            if "." in hole_path:
                if arg_path_named is None:
                    raise ValueError(
                        f"htmlBody {template.name}: record-field hole "
                        f"`{hole_path}` is not available in this context")
                value, type_name = arg_path_named(hole_path)
            else:
                type_name = arg_types.get(arg_name) or required_roots.get(arg_name) or "String"
                value = arg_val_named(arg_name)
            self._validate_html_arg_context(
                template, hole_path, type_name, context_kind, attr_name)
            value = self._html_arg_as_cstring(
                builder, value, hole_path, type_name)
            escape_mode = self._html_arg_escape_mode(
                type_name, context_kind)
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
        builder.store(ir.Constant(Int8, 0), write_ptr)
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
            # deep so `storage module mutable A Int64 zeroCount` works when
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
        validate_security_floor(self.prog)
        validate_strict_executable(self.prog)
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
        if mode == "windowsGui":
            raise NotImplementedError(
                "entry windowsGui is outside the committed executable surface. "
                "Use `target windowsGui`, declare `entry console main`, build "
                "the application with `gui.*` calls from standard.gui, and run "
                "it with `gui.applicationRun`.")
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
            raise ValueError(
                f"entry references unknown operation: {opname}. "
                f"Entry resolution only sees operations declared in the entry "
                f"compilation unit, not ones pulled in by `import`. If "
                f"`{opname}` lives in an imported module, move the entry "
                f"operation into this file. For standard-library smoke tests "
                f"this usually means the `main` was left in the imported "
                f"`module standard.*` file instead of the colocated "
                f"main.test.sem (see semlint SS2515)."
            )
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
        async_native_start = None
        async_native_await = None
        for verb, args, _ln in op.lines:
            if verb == "runtimeBindingAsyncStart" and len(args) >= 2:
                async_native_start = args[1]
            elif verb == "runtimeBindingAsyncAwait" and len(args) >= 2:
                async_native_await = args[1]
        self._user_ops[op.name] = {
            "fn": fn,
            "params": params,
            "return_type": return_type,
            "return_type_name": return_type_name,
            "async_native_start": async_native_start,
            "async_native_await": async_native_await,
        }

    # Refined-syntax operations marked `operationBody NAME runtimeBinding`
    # delegate to a pure ABI shim named on the `runtimeBinding` line.
    # Mapping the spec-shaped binding name to the actual libc symbol gives
    # those operations real ABI semantics instead of returning zero.
    _RUNTIME_BINDING_MAP = {
        "runtime.cstring.compare":         ("strcmp",  "i32_from_two_i8p"),
        "runtime.cstring.byteLength":      ("strlen",  "i64_from_i8p"),
        "runtime.cstring.validateNullTerminated":
                                            ("strlen",  "i64_from_i8p"),
        "runtime.memory.copyBytes":        ("memcpy",  "i8p_from_dst_src_n"),
    }
    _UNSUPPORTED_DOMAIN_RUNTIME_BINDINGS = {
        "metrics.computeIncrementInt64",
        "metricsLock.acquire",
        "metricsLock.release",
        "retryPolicy.delayForAttempt",
        "runtime.calendar.isLeapYearAsInt32",
        "runtime.calendar.isLeapYearBool",
        "runtime.text.validateUtf8",
        "scheduler.sleep",
    }

    # Refined-syntax operations marked `operationBody NAME intrinsic` lower
    # to real arithmetic IR. The `intrinsicName NAME arithmetic.X` line
    # picks which IR pattern to emit.
    _INTRINSIC_MAP = {
        "arithmetic.addInt64":           ("add",  "i64"),
        "arithmetic.subtractInt64":      ("sub",  "i64"),
        "arithmetic.multiplyInt64":      ("mul",  "i64"),
        "arithmetic.divideInt64":        ("sdiv", "i64"),
        "arithmetic.moduloInt64":        ("srem", "i64"),
        "arithmetic.equalInt64":         ("==",   "i1"),
        "arithmetic.notEqualInt64":      ("!=",   "i1"),
        "arithmetic.lessThanInt64":      ("<",    "i1"),
        "arithmetic.lessThanOrEqualInt64": ("<=", "i1"),
        "arithmetic.greaterThanInt64":   (">",    "i1"),
        "arithmetic.greaterThanOrEqualInt64": (">=", "i1"),
        "arithmetic.greaterThanOrEqualByteCount": (">=", "i1"),
        "arithmetic.equalInt32": ("==",  "i1"),
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
        target_line = op.decl_line
        for verb, args, ln in op.lines:
            if verb == "runtimeBinding" and len(args) >= 2:
                target = args[1]
                target_line = ln
                break
        mapping = self._RUNTIME_BINDING_MAP.get(target)
        if mapping is None:
            if target and target.startswith("native."):
                symbol = target[len("native."):]
                if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", symbol):
                    raise ValueError(
                        f"line {target_line}: invalid native runtime symbol "
                        f"`{symbol}` for operation `{op.name}`")
                rty = fn.function_type.return_type
                params = list(fn.args)
                param_tys = [param.type for param in params]
                extern = self._runtime_func(symbol, rty, param_tys)
                self.provenance.record_external(symbol, {
                    "operation": op.name,
                    "name": op.name,
                    "target": target,
                    "line": target_line,
                })
                result = builder.call(extern, params)
                if rty == VOID:
                    builder.ret_void()
                else:
                    builder.ret(result)
                return True
            if target in self._UNSUPPORTED_DOMAIN_RUNTIME_BINDINGS:
                raise ValueError(
                    f"line {target_line}: unsupported non-ABI runtimeBinding "
                    f"`{target}` for operation `{op.name}`; implement this "
                    "behavior as a SemanticScript operation body or bind an "
                    "explicit native runtime instead")
            return False
        libc_name, shape = mapping
        rty = fn.function_type.return_type
        params = list(fn.args)
        if shape == "i32_from_two_i8p" and len(params) >= 2:
            fty = ir.FunctionType(Int32, [Int8P, Int8P])
            extern = self.module.globals.get(libc_name) or ir.Function(
                self.module, fty, name=libc_name)
            res = builder.call(extern, [params[0], params[1]])
            if rty == Int32:
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
            fty = ir.FunctionType(Int64, [Int8P])
            extern = self.module.globals.get(libc_name) or ir.Function(
                self.module, fty, name=libc_name)
            res = builder.call(extern, [params[0]])
            if rty == Int64:
                builder.ret(res)
            elif isinstance(rty, ir.IntType):
                if rty.width < 64:
                    builder.ret(builder.trunc(res, rty))
                else:
                    builder.ret(builder.sext(res, rty))
            else:
                builder.ret(ir.Constant(rty, 0))
            return True
        if shape == "i8p_from_dst_src_n" and len(params) >= 3:
            fty = ir.FunctionType(Int8P, [Int8P, Int8P, Int64])
            extern = self.module.globals.get(libc_name) or ir.Function(
                self.module, fty, name=libc_name)
            # Coerce the third arg (byteCount) to i64 if needed.
            count = params[2]
            if isinstance(count.type, ir.IntType) and count.type.width != 64:
                count = builder.sext(count, Int64) if count.type.width < 64 else builder.trunc(count, Int64)
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
        fnty = ir.FunctionType(Int32, [])
        fn = ir.Function(self.module, fnty, name="main")
        entry_bb = fn.append_basic_block("entry")
        builder = ir.IRBuilder(entry_bb)
        self._install_crash_handler(builder)
        self._emit_crash_frame_push(builder, f"operation {op.name} (entry)")
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

        fnty = ir.FunctionType(Int32, [])
        fn = ir.Function(self.module, fnty, name="main")
        entry_bb = fn.append_basic_block("entry")
        builder = ir.IRBuilder(entry_bb)
        builder.ret(ir.Constant(Int32, 0))

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
        if op_info["return_type"] != Int32:
            raise ValueError(
                f"route {server_name} {method} {path}: handler `{handler_name}` must return Int32")

    def _emit_webserver_main(self, server: WebServer):
        if server.host is None:
            raise ValueError(f"webServer `{server.name}` is missing serverHost")
        if server.port is None:
            raise ValueError(f"webServer `{server.name}` is missing serverPort")
        for method, path, handler_name in server.routes:
            self._validate_web_route_handler(server.name, method, path, handler_name)
        if server.not_found_handler is not None:
            self._validate_web_route_handler(
                server.name, "NOT_FOUND", "*", server.not_found_handler)
        if server.method_not_allowed_handler is not None:
            self._validate_web_route_handler(
                server.name, "METHOD_NOT_ALLOWED", "*", server.method_not_allowed_handler)
        middleware_by_path = {}
        for path, middleware_name in server.middleware:
            route_path = _unwrap(path)
            self._validate_web_route_handler(server.name, "MIDDLEWARE", route_path, middleware_name)
            middleware_by_path[route_path] = middleware_name

        handler_fnty = ir.FunctionType(Int32, [Int8P, Int8P])
        handler_ptr_ty = handler_fnty.as_pointer()
        route_ty = ir.LiteralStructType([Int8P, Int8P, handler_ptr_ty, handler_ptr_ty])
        # Trailing fields are optional fallback function pointers.
        config_ty = ir.LiteralStructType(
            [Int8P, Int16, route_ty.as_pointer(), Int64, handler_ptr_ty, handler_ptr_ty])
        server_run = self._runtime_func("ss_http_server_run", Int32, [config_ty.as_pointer()])

        fnty = ir.FunctionType(Int32, [])
        fn = ir.Function(self.module, fnty, name="main")
        entry_bb = fn.append_basic_block("entry")
        builder = ir.IRBuilder(entry_bb)
        self._install_crash_handler(builder)
        self._emit_crash_frame_push(builder, "operation main (entry)")

        route_count = len(server.routes)
        routes_ty = ir.ArrayType(route_ty, route_count)
        routes_slot = builder.alloca(routes_ty, name="ss_routes")
        zero_i32 = ir.Constant(Int32, 0)

        for index, (method, path, handler_name) in enumerate(server.routes):
            route_ptr = builder.gep(
                routes_slot,
                [zero_i32, ir.Constant(Int32, index)],
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
                route_ptr, [zero_i32, ir.Constant(Int32, 1)], inbounds=True))
            builder.store(handler_ptr, builder.gep(
                route_ptr, [zero_i32, ir.Constant(Int32, 2)], inbounds=True))
            builder.store(middleware_ptr, builder.gep(
                route_ptr, [zero_i32, ir.Constant(Int32, 3)], inbounds=True))

        config_slot = builder.alloca(config_ty, name="ss_server_config")
        first_route_ptr = builder.gep(routes_slot, [zero_i32, zero_i32], inbounds=True)
        builder.store(self._i8p(builder, server.host), builder.gep(
            config_slot, [zero_i32, zero_i32], inbounds=True))
        builder.store(ir.Constant(Int16, int(server.port)), builder.gep(
            config_slot, [zero_i32, ir.Constant(Int32, 1)], inbounds=True))
        builder.store(first_route_ptr, builder.gep(
            config_slot, [zero_i32, ir.Constant(Int32, 2)], inbounds=True))
        builder.store(ir.Constant(Int64, route_count), builder.gep(
            config_slot, [zero_i32, ir.Constant(Int32, 3)], inbounds=True))

        # not_found_handler slot. Prefer explicit routeNotFound, but keep
        # the wildcard route convention for compatibility.
        nf_ptr = ir.Constant(handler_ptr_ty, None)
        if server.not_found_handler is not None:
            nf_fn = self._user_ops[server.not_found_handler]["fn"]
            nf_ptr = nf_fn
            if nf_ptr.type != handler_ptr_ty:
                nf_ptr = builder.bitcast(nf_ptr, handler_ptr_ty)
        else:
            for _method, _path, handler_name in server.routes:
                if _path == "*":
                    nf_fn = self._user_ops[handler_name]["fn"]
                    nf_ptr = nf_fn
                    if nf_ptr.type != handler_ptr_ty:
                        nf_ptr = builder.bitcast(nf_ptr, handler_ptr_ty)
                    break
        builder.store(nf_ptr, builder.gep(
            config_slot, [zero_i32, ir.Constant(Int32, 4)], inbounds=True))

        mna_ptr = ir.Constant(handler_ptr_ty, None)
        if server.method_not_allowed_handler is not None:
            mna_fn = self._user_ops[server.method_not_allowed_handler]["fn"]
            mna_ptr = mna_fn
            if mna_ptr.type != handler_ptr_ty:
                mna_ptr = builder.bitcast(mna_ptr, handler_ptr_ty)
        builder.store(mna_ptr, builder.gep(
            config_slot, [zero_i32, ir.Constant(Int32, 5)], inbounds=True))

        rc = builder.call(server_run, [config_slot], name="ss_http_server_status")
        builder.ret(rc)

    # ---------- shared body compilation ----------
    def _compile_body(self, op: Operation, fn, builder, initial_binds: dict):
        prog = self.prog

        labels = {}        # name -> BasicBlock
        calls = {}         # callName -> {target, args, result, error_value, error_cond}
        binds = dict(initial_binds)  # bind-name -> SSA value (or alloca pointer for vars)
        record_values = {} # record value name -> {type, slots, field_types}
        self._current_record_values = record_values
        # bind-name -> entry-block alloca slot for handles that need to be
        # re-loaded at later use sites (defer cleanup). See bindOk handling
        # below and the sqlite.openDatabase / sqlite.prepareStatement
        # dispatchers in _emit_run for the producer side.
        bind_slots = {}
        var_types = {}     # var-name -> LLVM type
        is_var = set()     # set of mutable var names

        # Pre-create blocks for every label in source order
        declared_label_lines = {}
        for verb, args, _ln in op.lines:
            if verb == "label":
                labels[args[0]] = fn.append_basic_block(args[0])
                declared_label_lines[args[0]] = _ln
        declared_label_names = set(labels.keys())
        declared_call_names = {
            args[0]
            for verb, args, _ln in op.lines
            if verb == "call" and args
        }

        SENTINEL = object()
        opaque_inputs = OPAQUE_INPUTS

        def make_call(call_name, target, lineno):
            return {
                "name": call_name,
                "operation": op.name,
                "line": lineno,
                "target": target,
                "source_target": target,
                "args": {},
                "arg_types": {},
                "arg_lines": {},
                "result": None,
                "error_value": None,
                "error_cond": None,
            }

        def get_block(name):
            if name not in labels:
                labels[name] = fn.append_basic_block(name)
            return labels[name]

        def error_condition_for_call(call_name):
            call = calls[call_name]
            err_cond = call["error_cond"]
            if err_cond is not None:
                return err_cond
            result = call["result"]
            if result is None:
                raise ValueError(
                    f"branchIfError/runChecked: call `{call_name}` has no "
                    "result or explicit error condition")
            if isinstance(result.type, ir.PointerType):
                nullptr = ir.Constant(result.type, None)
                return builder.icmp_unsigned(
                    "==", result, nullptr, name=f"{call_name}_isErr")
            zero = ir.Constant(result.type, 0)
            return builder.icmp_signed(
                "<", result, zero, name=f"{call_name}_isErr")

        def emit_const_value(typ, raw):
            llty = llvm_type_for(prog, typ)
            resolved = resolve_alias(prog, typ)
            enum_cases = enum_case_values(prog)
            if enum_repr_type(prog, resolved) is not None and isinstance(raw, str):
                enum_case = enum_cases.get(raw)
                if enum_case is not None and enum_case[0] == resolved:
                    raw = enum_case[1]
            # Refined-syntax `storage module immutable A Int64 B` lets `B` be
            # the name of another const rather than a literal. Recursively
            # resolve up to a small depth to avoid pathological cycles.
            if isinstance(raw, str) and raw in prog.consts:
                inner_typ, inner_val = prog.consts[raw]
                if isinstance(inner_val, str) and inner_val in prog.consts:
                    raw = prog.consts[inner_val][1]
                else:
                    raw = inner_val
            # Any type that lowers to the i8* pointer shape (the canonical
            # `String` surface, or any user alias that resolves to one of
            # these) and whose const value is a literal string gets the
            # interned-i8-array treatment. The check is on the LLVM type so
            # future pointer-shaped aliases don't need a special case.
            if llty == Int8P and isinstance(raw, str):
                return self._i8p(builder, raw)
            if llty == Int8P and raw is None:
                return ir.Constant(Int8P, None)
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
                    return ir.Constant(Int64, int(tok))
                # Float literal: contains a '.' and the rest is digits/sign/e.
                if "." in tok or "e" in tok or "E" in tok:
                    try:
                        return ir.Constant(Float64, float(tok))
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

        def coerce_to_type(value, target_type):
            if value.type == target_type:
                return value
            if isinstance(value.type, ir.IntType) and isinstance(target_type, ir.IntType):
                if value.type.width < target_type.width:
                    return (builder.zext if value.type.width == 1 else builder.sext)(
                        value, target_type)
                if value.type.width > target_type.width:
                    return builder.trunc(value, target_type)
            if isinstance(value.type, ir.IntType) and isinstance(target_type, ir.PointerType):
                return builder.inttoptr(value, target_type)
            if isinstance(value.type, ir.PointerType) and isinstance(target_type, ir.IntType):
                return builder.ptrtoint(value, target_type)
            if isinstance(value.type, ir.PointerType) and isinstance(target_type, ir.PointerType):
                return builder.bitcast(value, target_type)
            if isinstance(value.type, ir.IntType) and isinstance(target_type, (ir.FloatType, ir.DoubleType)):
                return builder.sitofp(value, target_type)
            if isinstance(value.type, (ir.FloatType, ir.DoubleType)) and isinstance(target_type, ir.IntType):
                return builder.fptosi(value, target_type)
            if isinstance(value.type, ir.FloatType) and isinstance(target_type, ir.DoubleType):
                return builder.fpext(value, target_type)
            if isinstance(value.type, ir.DoubleType) and isinstance(target_type, ir.FloatType):
                return builder.fptrunc(value, target_type)
            return value

        def record_leaf_type(record_type, field_path):
            current_type = record_type
            parts = field_path.split(".")
            for index, part in enumerate(parts):
                record = prog.records.get(current_type)
                if record is None:
                    return None
                match = None
                for field_name, field_type in record.fields:
                    if field_name == part:
                        match = field_type
                        break
                if match is None:
                    return None
                if index == len(parts) - 1:
                    return match
                nested = _record_type_for_json_body(prog, match)
                if nested is None:
                    return None
                current_type = nested
            return None

        def iter_record_leaf_fields(record_type, prefix=""):
            record = prog.records.get(record_type)
            if record is None:
                return
            for field_name, field_type in record.fields:
                path = f"{prefix}.{field_name}" if prefix else field_name
                nested = _record_type_for_json_body(prog, field_type)
                if nested is not None:
                    yield from iter_record_leaf_fields(nested, path)
                else:
                    yield path, field_type

        def nested_json_field(record_fields, field_path):
            current = record_fields
            for part in field_path.split("."):
                if not isinstance(current, dict) or part not in current:
                    return None
                current = current[part]
            return current

        def allocate_record_slots(value_name, record_type, initial_fields=None):
            slots = {}
            field_types = {}
            for field_path, field_type in iter_record_leaf_fields(record_type):
                llty = llvm_type_for(prog, field_type)
                if llty is None:
                    continue
                with builder.goto_entry_block():
                    slot = builder.alloca(
                        llty,
                        name=f"{value_name}_{field_path.replace('.', '_')}")
                raw_initial = None
                if initial_fields is not None:
                    raw_initial = nested_json_field(initial_fields, field_path)
                init = emit_const_value(field_type, raw_initial)
                init = coerce_to_type(init, llty)
                builder.store(init, slot)
                slots[field_path] = slot
                field_types[field_path] = field_type
            record_values[value_name] = {
                "type": record_type,
                "slots": slots,
                "field_types": field_types,
            }
            return record_values[value_name]

        async_loop_slot = None

        def ensure_async_loop():
            nonlocal async_loop_slot
            if async_loop_slot is None:
                with builder.goto_entry_block():
                    async_loop_slot = builder.alloca(
                        Int8P, name="ss_async_loop_slot")
                builder.store(ir.Constant(Int8P, None), async_loop_slot)
                init_fn = self._runtime_func(
                    "ss_async_loop_init", Int32, [Int8P.as_pointer()])
                loop_status = builder.call(
                    init_fn, [async_loop_slot], name="ss_async_loop_init_status")
                # The first async start will fail with runtime-unavailable or
                # config if the loop did not initialize. Keep the explicit
                # status value alive for trace/provenance without adding a
                # second control-flow branch here.
                _ = loop_status
            return builder.load(async_loop_slot, name="ss_async_loop")

        def record_field_value(record_symbol, field_path, target_type=None):
            source = record_values.get(record_symbol)
            if source is None:
                raise ValueError(f"record `{record_symbol}` has no allocated fields")
            slot = source["slots"].get(field_path)
            if slot is None:
                raise ValueError(
                    f"record `{record_symbol}` has no field `{field_path}`")
            value = builder.load(
                slot,
                name=f"{record_symbol}_{field_path.replace('.', '_')}_async")
            if target_type is not None:
                value = coerce_to_type(value, target_type)
            return value

        def canonical_call_target(call_obj):
            raw_target = call_obj.get("target", "")
            target = _TARGET_ALIASES.get(raw_target, raw_target)
            return self.prog.operation_aliases.get(target, target)

        def is_async_fetch_target(call_obj):
            return canonical_call_target(call_obj) in {
                "net.fetchText",
                "fetchText",
                "standard.net.fetchText",
            }

        operation_async_enabled = any(
            row_verb == "async"
            and len(row_args) >= 2
            and row_args[0] == op.name
            and str(row_args[1]).lower() in {"yes", "true", "1", "on"}
            for row_verb, row_args, _row_ln in op.lines
        )

        def user_op_call_target(call_obj):
            return canonical_call_target(call_obj)

        def is_async_user_op_target(call_obj):
            return user_op_call_target(call_obj) in self._user_ops

        def default_value_for_type(target_type):
            if isinstance(target_type, ir.PointerType):
                return ir.Constant(target_type, None)
            if isinstance(target_type, (ir.FloatType, ir.DoubleType)):
                return ir.Constant(target_type, 0.0)
            return ir.Constant(target_type, 0)

        def error_cond_for_result(result, name):
            if isinstance(result.type, ir.IntType):
                return builder.icmp_signed(
                    "!=", result, ir.Constant(result.type, 0),
                    name=f"{name}_isErr")
            if isinstance(result.type, ir.PointerType):
                return builder.icmp_unsigned(
                    "==", result, ir.Constant(result.type, None),
                    name=f"{name}_isErr")
            if isinstance(result.type, (ir.FloatType, ir.DoubleType)):
                return builder.fcmp_ordered(
                    "!=", result, ir.Constant(result.type, 0.0),
                    name=f"{name}_isErr")
            return ir.Constant(I1, 0)

        def user_op_argument_values(call_name, call_obj, op_info):
            values = []
            call_arg_values = list(call_obj["args"].values())
            param_names = [param[0] for param in op_info["params"]]
            for param_index, (pname, llty, _ptype) in enumerate(op_info["params"]):
                sym = call_obj["args"].get(pname)
                if sym is None:
                    if len(call_arg_values) == len(op_info["params"]):
                        sym = call_arg_values[param_index]
                    else:
                        raise ValueError(
                            f"{call_name}: missing arg `{pname}` for operation "
                            f"`{user_op_call_target(call_obj)}` "
                            f"(call passed {len(call_arg_values)} args, op declares "
                            f"{len(param_names)})")
                try:
                    value = resolve(sym)
                except ValueError:
                    raise ValueError(
                        f"{call_name}: unresolved arg value `{sym}` for "
                        f"operation `{user_op_call_target(call_obj)}` "
                        f"parameter `{pname}`")
                if value is SENTINEL:
                    raise ValueError(
                        f"{call_name}: opaque-input symbol used as data arg "
                        f"`{pname}` for `{user_op_call_target(call_obj)}`")
                values.append(coerce_to_type(value, llty))
            return values

        def parse_timeout_ms_literal(raw_value):
            text = str(raw_value)
            match = re.match(r"^([0-9]+)(ms|s|m)?$", text)
            if match is None:
                return None
            amount = int(match.group(1))
            unit = match.group(2) or "ms"
            if unit == "ms":
                return amount
            if unit == "s":
                return amount * 1000
            if unit == "m":
                return amount * 60000
            return None

        def timeout_ms_value_for_call(call_name, call_obj):
            raw_timeout = call_obj.get("timeout")
            if raw_timeout is None:
                return ir.Constant(Int64, 0)
            parsed_timeout = parse_timeout_ms_literal(raw_timeout)
            if parsed_timeout is not None:
                return ir.Constant(Int64, parsed_timeout)
            try:
                timeout_value = resolve(raw_timeout)
            except ValueError:
                raise ValueError(
                    f"timeout: `{call_name}` uses unsupported timeout value "
                    f"`{raw_timeout}`; use a literal like `1000ms` or an integer symbol")
            if timeout_value is SENTINEL:
                raise ValueError(
                    f"timeout: `{call_name}` uses opaque timeout symbol `{raw_timeout}`")
            return coerce_to_type(timeout_value, Int64)

        def cancel_token_value_for_call(call_name, call_obj):
            raw_cancel = call_obj.get("cancel_on")
            if raw_cancel is None:
                return ir.Constant(Int8P, None)
            try:
                cancel_value = resolve(raw_cancel)
            except ValueError:
                raise ValueError(
                    f"cancelOn: `{call_name}` uses unresolved cancellation token "
                    f"`{raw_cancel}`")
            if cancel_value is SENTINEL:
                return ir.Constant(Int8P, None)
            return coerce_to_type(cancel_value, Int8P)

        def native_symbol_from_async_metadata(raw_symbol, row_name, target):
            if not raw_symbol:
                return None
            if not str(raw_symbol).startswith("native."):
                raise ValueError(
                    f"{row_name}: `{target}` uses unsupported async runtime "
                    f"binding `{raw_symbol}`; expected native.SYMBOL")
            symbol = str(raw_symbol)[len("native."):]
            if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", symbol):
                raise ValueError(
                    f"{row_name}: `{target}` uses invalid native async symbol "
                    f"`{symbol}`")
            return symbol

        def async_native_binding_info(call_obj):
            target = user_op_call_target(call_obj)
            op_info = self._user_ops.get(target)
            if op_info is None or not operation_async_enabled:
                return None
            start_symbol = native_symbol_from_async_metadata(
                op_info.get("async_native_start"),
                "runtimeBindingAsyncStart",
                target)
            await_symbol = native_symbol_from_async_metadata(
                op_info.get("async_native_await"),
                "runtimeBindingAsyncAwait",
                target)
            if start_symbol is None and await_symbol is None:
                return None
            if start_symbol is None or await_symbol is None:
                raise ValueError(
                    f"async runtimeBinding `{target}` must declare both "
                    "runtimeBindingAsyncStart and runtimeBindingAsyncAwait")
            return target, op_info, start_symbol, await_symbol

        def async_native_binding_metadata_target(call_obj):
            if call_obj is None:
                return None
            target = user_op_call_target(call_obj)
            op_info = self._user_ops.get(target)
            if op_info is None:
                return None
            if op_info.get("async_native_start") or op_info.get("async_native_await"):
                return target
            return None

        def result_error_condition(result, call_name):
            if isinstance(result.type, ir.PointerType):
                return builder.icmp_unsigned(
                    "==", result, ir.Constant(result.type, None),
                    name=f"{call_name}_async_result_is_null")
            if isinstance(result.type, ir.IntType):
                return builder.icmp_signed(
                    "<", result, ir.Constant(result.type, 0),
                    name=f"{call_name}_async_result_is_negative")
            return ir.Constant(I1, 0)

        def emit_async_native_binding_start(call_name):
            call_obj = calls[call_name]
            binding = async_native_binding_info(call_obj)
            if binding is None:
                return False
            target, op_info, start_symbol, _await_symbol = binding
            if call_obj.get("async_awaited"):
                raise ValueError(
                    f"start: `{call_name}` was already awaited or consumed "
                    "by an await wait-set case")

            arg_values = user_op_argument_values(call_name, call_obj, op_info)
            loop = ensure_async_loop()
            timeout_value = timeout_ms_value_for_call(call_name, call_obj)
            cancel_value = cancel_token_value_for_call(call_name, call_obj)
            param_tys = [Int8P] + [param[1] for param in op_info["params"]] + [
                Int64,
                Int8P,
                Int8P.as_pointer(),
            ]
            start_fn = self._runtime_func(start_symbol, Int32, param_tys)
            self.provenance.record_external(start_symbol, call_obj)

            with builder.goto_entry_block():
                future_slot = builder.alloca(Int8P, name=f"{call_name}_native_future_out")
                status_slot = builder.alloca(Int32, name=f"{call_name}_native_start_status_out")
            builder.store(ir.Constant(Int8P, None), future_slot)
            start_status = builder.call(
                start_fn,
                [loop] + arg_values + [timeout_value, cancel_value, future_slot],
                name=f"{call_name}_native_start_status")
            builder.store(start_status, status_slot)
            call_obj["future_slot"] = future_slot
            call_obj["start_status_slot"] = status_slot
            call_obj["start_status"] = start_status
            call_obj["result"] = builder.load(
                future_slot, name=f"{call_name}_native_future")
            call_obj["error_value"] = start_status
            call_obj["error_cond"] = builder.icmp_unsigned(
                "!=", start_status, ir.Constant(Int32, 0),
                name=f"{call_name}_native_start_is_error")
            return True

        def emit_async_native_binding_await(call_name):
            call_obj = calls[call_name]
            binding = async_native_binding_info(call_obj)
            if binding is None:
                return False
            _target, op_info, _start_symbol, await_symbol = binding
            if call_obj.get("async_awaited"):
                raise ValueError(
                    f"await: `{call_name}` was already awaited or consumed "
                    "by an await wait-set case")
            future_slot = call_obj.get("future_slot")
            if future_slot is None:
                raise ValueError(
                    f"await: `{call_name}` targets async runtimeBinding "
                    f"`{user_op_call_target(call_obj)}` but was not started")

            loop = ensure_async_loop()
            future = builder.load(future_slot, name=f"{call_name}_native_await_future")
            await_fn = self._runtime_func(
                await_symbol,
                op_info["return_type"],
                [Int8P, Int8P])
            self.provenance.record_external(await_symbol, call_obj)
            result = builder.call(
                await_fn, [loop, future], name=f"{call_name}_native_async_result")
            builder.store(ir.Constant(Int8P, None), future_slot)

            start_status = call_obj.get("start_status")
            if start_status is None and call_obj.get("start_status_slot") is not None:
                start_status = builder.load(
                    call_obj["start_status_slot"],
                    name=f"{call_name}_native_start_status_reload")
            if start_status is None:
                start_status = ir.Constant(Int32, 0)
            start_failed = builder.icmp_unsigned(
                "!=", start_status, ir.Constant(Int32, 0),
                name=f"{call_name}_native_start_failed_at_await")
            result_failed = result_error_condition(result, call_name)
            call_obj["result"] = result
            if isinstance(result.type, ir.IntType):
                call_obj["error_value"] = builder.select(
                    start_failed,
                    coerce_to_type(start_status, result.type),
                    result,
                    name=f"{call_name}_native_async_error_value")
            else:
                call_obj["error_value"] = start_status
            call_obj["error_cond"] = builder.or_(
                start_failed,
                result_failed,
                name=f"{call_name}_native_async_is_error")
            call_obj["async_awaited"] = True
            return True

        def emit_async_fetch_start(call_name):
            call_obj = calls[call_name]
            if not is_async_fetch_target(call_obj):
                return False
            if call_obj.get("async_awaited"):
                raise ValueError(
                    f"start: `{call_name}` was already awaited or consumed "
                    "by an await wait-set case")
            request_symbol = call_obj["args"].get("request")
            if request_symbol is None:
                raise ValueError(f"start: `{call_name}` missing request argument")
            loop = ensure_async_loop()
            url = record_field_value(request_symbol, "url", Int8P)
            timeout_ms = record_field_value(
                request_symbol, "policy.timeoutMillis", Int64)
            max_body_bytes = record_field_value(
                request_symbol, "policy.maxBodyBytes", Int64)
            redirect_limit = record_field_value(
                request_symbol, "policy.redirectLimit", Int32)
            with builder.goto_entry_block():
                future_out = builder.alloca(
                    Int8P, name=f"{call_name}_future_out")
            builder.store(ir.Constant(Int8P, None), future_out)
            start_fn = self._runtime_func(
                "ss_http_client_fetch_text_request_start",
                Int32,
                [Int8P, Int8P, Int64, Int64, Int32, Int8P.as_pointer()])
            self.provenance.record_external(
                "ss_http_client_fetch_text_request_start", call_obj)
            start_status = builder.call(
                start_fn,
                [loop, url, timeout_ms, max_body_bytes, redirect_limit, future_out],
                name=f"{call_name}_start_status")
            call_obj["future_slot"] = future_out
            call_obj["start_status"] = start_status
            call_obj["result"] = builder.load(
                future_out, name=f"{call_name}_future")
            call_obj["error_value"] = start_status
            call_obj["error_cond"] = builder.icmp_unsigned(
                "!=", start_status, ir.Constant(Int32, 0),
                name=f"{call_name}_start_is_error")
            return True

        def emit_async_fetch_await(call_name):
            call_obj = calls[call_name]
            if not is_async_fetch_target(call_obj):
                return False
            if call_obj.get("async_awaited"):
                raise ValueError(
                    f"await: `{call_name}` was already awaited or consumed "
                    "by an await wait-set case")
            future_slot = call_obj.get("future_slot")
            if future_slot is None:
                raise ValueError(
                    f"await: `{call_name}` targets {canonical_call_target(call_obj)} "
                    "but was not started with async lowering")
            loop = ensure_async_loop()
            future = builder.load(future_slot, name=f"{call_name}_await_future")
            await_fn = self._runtime_func(
                "ss_http_client_fetch_text_await", Int32, [Int8P, Int8P])
            self.provenance.record_external(
                "ss_http_client_fetch_text_await", call_obj)
            await_status = builder.call(
                await_fn, [loop, future], name=f"{call_name}_await_status")

            status_fn = self._runtime_func(
                "ss_http_client_fetch_status", Int64, [Int8P])
            body_copy_fn = self._runtime_func(
                "ss_http_client_fetch_body_text_copy",
                Int32,
                [Int8P, Int8P.as_pointer()])
            free_future_fn = self._runtime_func(
                "ss_http_client_fetch_free", VOID, [Int8P])
            self.provenance.record_external(
                "ss_http_client_fetch_status", call_obj)
            self.provenance.record_external(
                "ss_http_client_fetch_body_text_copy", call_obj)
            self.provenance.record_external(
                "ss_http_client_fetch_free", call_obj)
            with builder.goto_entry_block():
                body_out = builder.alloca(Int8P, name=f"{call_name}_async_body_out")
                response_status = builder.alloca(
                    Int32, name=f"{call_name}_async_response_status")
                response_body = builder.alloca(
                    Int8P, name=f"{call_name}_async_response_body")
            builder.store(ir.Constant(Int8P, None), body_out)
            http_status = builder.call(
                status_fn, [future], name=f"{call_name}_async_http_status")
            body_copy_status = builder.call(
                body_copy_fn, [future, body_out],
                name=f"{call_name}_body_copy_status")
            body = builder.load(body_out, name=f"{call_name}_async_body")
            builder.call(free_future_fn, [future])
            builder.store(ir.Constant(Int8P, None), future_slot)
            builder.store(coerce_to_type(http_status, Int32), response_status)
            builder.store(body, response_body)
            start_status = call_obj.get("start_status", ir.Constant(Int32, 0))
            start_error = builder.icmp_unsigned(
                "!=", start_status, ir.Constant(Int32, 0),
                name=f"{call_name}_start_error_at_await")
            await_or_copy_status = builder.select(
                builder.icmp_unsigned(
                    "!=", await_status, ir.Constant(Int32, 0),
                    name=f"{call_name}_await_is_error"),
                await_status,
                body_copy_status,
                name=f"{call_name}_await_or_copy_status")
            final_status = builder.select(
                start_error,
                start_status,
                await_or_copy_status,
                name=f"{call_name}_async_status")
            call_obj["record_result"] = {
                "type": "HttpTextResponse",
                "slots": {
                    "status": response_status,
                    "body": response_body,
                },
                "field_types": {
                    "status": "HttpClientStatusCode",
                    "body": "HttpClientBodyText",
                },
            }
            call_obj["result"] = body
            call_obj["error_value"] = final_status
            call_obj["error_cond"] = builder.icmp_unsigned(
                "!=", final_status, ir.Constant(Int32, 0),
                name=f"{call_name}_async_is_error")
            call_obj["async_awaited"] = True
            return True

        def emit_async_user_op_start(call_name):
            call_obj = calls[call_name]
            target = user_op_call_target(call_obj)
            op_info = self._user_ops.get(target)
            if op_info is None or not operation_async_enabled:
                return False
            if call_obj.get("async_awaited"):
                raise ValueError(
                    f"start: `{call_name}` was already awaited or consumed "
                    "by an await wait-set case")

            arg_values = user_op_argument_values(call_name, call_obj, op_info)
            wrapper = self._async_user_op_wrapper(target, op_info)
            loop = ensure_async_loop()
            malloc_fn = self._libc_func("malloc")
            free_fn = self._libc_func("free")
            future_create_fn = self._runtime_func(
                "ss_async_future_create", Int8P, [Int8P])
            future_destroy_fn = self._runtime_func(
                "ss_async_future_destroy", VOID, [Int8P])
            queue_work_fn = self._runtime_func(
                "ss_async_queue_work",
                Int32,
                [
                    Int8P,
                    wrapper["work_fn_ptr_ty"],
                    wrapper["after_fn_ptr_ty"],
                    Int8P,
                ])
            self.provenance.record_external("ss_async_future_create", call_obj)
            self.provenance.record_external("ss_async_queue_work", call_obj)

            with builder.goto_entry_block():
                future_slot = builder.alloca(Int8P, name=f"{call_name}_future_out")
                context_slot = builder.alloca(Int8P, name=f"{call_name}_context_out")
                status_slot = builder.alloca(Int32, name=f"{call_name}_start_status_out")
            builder.store(ir.Constant(Int8P, None), future_slot)
            builder.store(ir.Constant(Int8P, None), context_slot)
            builder.store(ir.Constant(Int32, -1), status_slot)

            ctx_i8p = builder.call(
                malloc_fn,
                [ir.Constant(Int64, wrapper["context_size"])],
                name=f"{call_name}_context")
            builder.store(ctx_i8p, context_slot)

            fn = builder.function
            create_future_block = fn.append_basic_block(f"{call_name}_create_future")
            allocation_failed_block = fn.append_basic_block(f"{call_name}_alloc_failed")
            queue_block = fn.append_basic_block(f"{call_name}_queue")
            future_failed_block = fn.append_basic_block(f"{call_name}_future_failed")
            queue_failed_block = fn.append_basic_block(f"{call_name}_queue_failed")
            start_done_block = fn.append_basic_block(f"{call_name}_start_done")

            builder.cbranch(
                builder.icmp_unsigned(
                    "==", ctx_i8p, ir.Constant(Int8P, None),
                    name=f"{call_name}_context_is_null"),
                allocation_failed_block,
                create_future_block)

            builder.position_at_end(allocation_failed_block)
            builder.store(ir.Constant(Int32, 3), status_slot)
            builder.branch(start_done_block)

            builder.position_at_end(create_future_block)
            future = builder.call(
                future_create_fn, [loop], name=f"{call_name}_future")
            builder.store(future, future_slot)
            builder.cbranch(
                builder.icmp_unsigned(
                    "==", future, ir.Constant(Int8P, None),
                    name=f"{call_name}_future_is_null"),
                future_failed_block,
                queue_block)

            builder.position_at_end(future_failed_block)
            builder.call(free_fn, [ctx_i8p])
            builder.store(ir.Constant(Int8P, None), context_slot)
            builder.store(ir.Constant(Int32, 3), status_slot)
            builder.branch(start_done_block)

            builder.position_at_end(queue_block)
            context = builder.bitcast(
                ctx_i8p, wrapper["context_ptr_ty"], name=f"{call_name}_ctx")
            zero = ir.Constant(Int32, 0)
            future_ptr = builder.gep(
                context, [zero, zero], inbounds=True,
                name=f"{call_name}_ctx_future_ptr")
            builder.store(future, future_ptr)
            for index, value in enumerate(arg_values, start=3):
                arg_ptr = builder.gep(
                    context,
                    [zero, ir.Constant(Int32, index)],
                    inbounds=True,
                    name=f"{call_name}_ctx_arg{index - 3}_ptr")
                builder.store(value, arg_ptr)
            queue_status = builder.call(
                queue_work_fn,
                [loop, wrapper["work_fn"], wrapper["after_fn"], ctx_i8p],
                name=f"{call_name}_queue_status")
            builder.cbranch(
                builder.icmp_unsigned(
                    "!=", queue_status, ir.Constant(Int32, 0),
                    name=f"{call_name}_queue_failed_cond"),
                queue_failed_block,
                start_done_block)

            builder.position_at_end(queue_failed_block)
            builder.call(future_destroy_fn, [future])
            builder.call(free_fn, [ctx_i8p])
            builder.store(ir.Constant(Int8P, None), future_slot)
            builder.store(ir.Constant(Int8P, None), context_slot)
            builder.store(queue_status, status_slot)
            builder.branch(start_done_block)

            builder.position_at_end(start_done_block)
            if not builder.block.is_terminated:
                current_status = builder.load(
                    status_slot, name=f"{call_name}_queued_status_current")
                is_unset = builder.icmp_signed(
                    "==", current_status, ir.Constant(Int32, -1),
                    name=f"{call_name}_status_unset")
                final_start_status = builder.select(
                    is_unset,
                    ir.Constant(Int32, 0),
                    current_status,
                    name=f"{call_name}_start_status")
                builder.store(final_start_status, status_slot)
            else:
                final_start_status = ir.Constant(Int32, 3)

            call_obj["future_slot"] = future_slot
            call_obj["context_slot"] = context_slot
            call_obj["start_status_slot"] = status_slot
            call_obj["start_status"] = builder.load(
                status_slot, name=f"{call_name}_start_status_value")
            call_obj["result"] = builder.load(
                future_slot, name=f"{call_name}_future_value")
            call_obj["error_value"] = call_obj["start_status"]
            call_obj["error_cond"] = builder.icmp_unsigned(
                "!=", call_obj["start_status"], ir.Constant(Int32, 0),
                name=f"{call_name}_start_is_error")
            return True

        def emit_async_user_op_await(call_name):
            call_obj = calls[call_name]
            target = user_op_call_target(call_obj)
            op_info = self._user_ops.get(target)
            if op_info is None or not operation_async_enabled:
                return False
            if call_obj.get("async_awaited"):
                raise ValueError(
                    f"await: `{call_name}` was already awaited or consumed "
                    "by an await wait-set case")
            future_slot = call_obj.get("future_slot")
            if future_slot is None:
                raise ValueError(
                    f"await: `{call_name}` targets user operation `{target}` "
                    "but was not started with async lowering")

            wrapper = self._async_user_op_wrapper(target, op_info)
            loop = ensure_async_loop()
            await_fn = self._runtime_func(
                "ss_async_future_await", Int32, [Int8P, Int8P])
            result_fn = self._runtime_func(
                "ss_async_future_result", Int8P, [Int8P])
            future_destroy_fn = self._runtime_func(
                "ss_async_future_destroy", VOID, [Int8P])
            free_fn = self._libc_func("free")
            self.provenance.record_external("ss_async_future_await", call_obj)
            self.provenance.record_external("ss_async_future_result", call_obj)
            self.provenance.record_external("ss_async_future_destroy", call_obj)

            ret_ty = op_info["return_type"]
            with builder.goto_entry_block():
                result_slot = builder.alloca(
                    ret_ty, name=f"{call_name}_async_result_out")
                status_slot = builder.alloca(
                    Int32, name=f"{call_name}_await_status_out")
            builder.store(default_value_for_type(ret_ty), result_slot)
            builder.store(ir.Constant(Int32, 3), status_slot)

            future = builder.load(future_slot, name=f"{call_name}_await_future")
            await_status = builder.call(
                await_fn, [loop, future], name=f"{call_name}_await_status")
            start_status_value = call_obj.get("start_status")
            if start_status_value is None and call_obj.get("start_status_slot") is not None:
                start_status_value = builder.load(
                    call_obj["start_status_slot"],
                    name=f"{call_name}_start_status_reload")
            if start_status_value is None:
                start_status_value = ir.Constant(Int32, 0)
            start_failed = builder.icmp_unsigned(
                "!=", start_status_value, ir.Constant(Int32, 0),
                name=f"{call_name}_start_failed_at_await")
            final_status = builder.select(
                start_failed,
                start_status_value,
                await_status,
                name=f"{call_name}_async_runtime_status")
            builder.store(final_status, status_slot)

            fn = builder.function
            load_result_block = fn.append_basic_block(f"{call_name}_load_async_result")
            cleanup_error_block = fn.append_basic_block(f"{call_name}_async_error_cleanup")
            after_await_block = fn.append_basic_block(f"{call_name}_after_async_await")
            builder.cbranch(
                builder.icmp_unsigned(
                    "!=", final_status, ir.Constant(Int32, 0),
                    name=f"{call_name}_runtime_failed"),
                cleanup_error_block,
                load_result_block)

            builder.position_at_end(load_result_block)
            ctx_i8p = builder.call(
                result_fn, [future], name=f"{call_name}_result_context")
            context = builder.bitcast(
                ctx_i8p, wrapper["context_ptr_ty"], name=f"{call_name}_result_ctx")
            result_ptr = builder.gep(
                context,
                [ir.Constant(Int32, 0), ir.Constant(Int32, 2)],
                inbounds=True,
                name=f"{call_name}_result_ptr")
            result = builder.load(result_ptr, name=f"{call_name}_async_result")
            builder.store(result, result_slot)
            builder.call(free_fn, [ctx_i8p])
            if call_obj.get("context_slot") is not None:
                builder.store(ir.Constant(Int8P, None), call_obj["context_slot"])
            builder.call(future_destroy_fn, [future])
            builder.store(ir.Constant(Int8P, None), future_slot)
            builder.branch(after_await_block)

            builder.position_at_end(cleanup_error_block)
            ctx_from_slot = (
                builder.load(call_obj["context_slot"], name=f"{call_name}_error_ctx")
                if call_obj.get("context_slot") is not None
                else ir.Constant(Int8P, None)
            )
            builder.call(free_fn, [ctx_from_slot])
            if call_obj.get("context_slot") is not None:
                builder.store(ir.Constant(Int8P, None), call_obj["context_slot"])
            builder.call(future_destroy_fn, [future])
            builder.store(ir.Constant(Int8P, None), future_slot)
            builder.branch(after_await_block)

            builder.position_at_end(after_await_block)
            final_result = builder.load(
                result_slot, name=f"{call_name}_async_final_result")
            runtime_status = builder.load(
                status_slot, name=f"{call_name}_async_final_status")
            runtime_error = builder.icmp_unsigned(
                "!=", runtime_status, ir.Constant(Int32, 0),
                name=f"{call_name}_async_runtime_is_error")
            result_error = error_cond_for_result(final_result, call_name)
            call_obj["result"] = final_result
            if isinstance(final_result.type, ir.IntType):
                coerced_runtime_status = coerce_to_type(
                    runtime_status, final_result.type)
                call_obj["error_value"] = builder.select(
                    runtime_error,
                    coerced_runtime_status,
                    final_result,
                    name=f"{call_name}_async_error_value")
            else:
                call_obj["error_value"] = runtime_status
            call_obj["error_cond"] = builder.or_(
                runtime_error,
                result_error,
                name=f"{call_name}_async_is_error")
            call_obj["async_awaited"] = True
            return True

        def const_record_field(record_name, field_path):
            record_const = prog.record_json_constants.get(record_name)
            if record_const is None:
                return None
            field_type = record_leaf_type(record_const["recordType"], field_path)
            if field_type is None:
                return None
            raw_value = nested_json_field(record_const["fields"], field_path)
            return emit_const_value(field_type, raw_value)

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
        current_block_reachable = True
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
        worker_pools = set(self.prog.worker_pools)
        for verb, args, _ln in op.lines:
            if verb == "workerPool" and args:
                worker_pools.add(args[0])
        work_items = {}

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
                slot = builder.alloca(Int64, name=f"channel_{channel_name}")
            builder.store(ir.Constant(Int64, 0), slot)
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
                "ss_sqlite_database_close", Int32, [Int8P]),
            "sqlite.finalizeStatement": (
                "ss_sqlite_statement_finalize", Int32, [Int8P]),
            "sqlite.resetStatement": (
                "ss_sqlite_statement_reset", Int32, [Int8P]),
            # json.destroyBuilder returns void in the C ABI but our
            # defer machinery wants a uniform i32 status shape; map
            # the return type as VOID and the defer-site call will
            # ignore the result regardless. The free() inside the
            # native impl runs unconditionally on a non-NULL handle.
            "json.destroyBuilder": (
                "ss_json_builder_destroy", VOID, [Int8P]),
            "json.destroyDocument": (
                "ss_json_document_destroy", VOID, [Int8P]),
            "net.freeTextBody": (
                "ss_http_client_free_string", VOID, [Int8P]),
            "freeTextBody": (
                "ss_http_client_free_string", VOID, [Int8P]),
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

        def trace_call_event(event, call_name):
            call = calls.get(call_name)
            if call is None:
                return
            target_text = call.get("source_target", call.get("target", ""))
            if event == "call.start":
                self._emit_crash_site_store(
                    builder,
                    f"operation {op.name} call {call_name} -> {target_text} "
                    f"line {call.get('line', 0)}")
            self._emit_trace_event(
                builder, event, "call", op.name, call_name,
                target_text, call.get("line", 0))

        self._emit_trace_event(
            builder, "op.enter", "operation", op.name, op.name,
            "", op.decl_line)
        self._emit_crash_site_store(
            builder, f"operation {op.name} line {op.decl_line}")

        branch_else_by_line = {}
        attached_branch_else_lines = set()
        for idx, (row_verb, row_args, row_ln) in enumerate(op.lines[:-1]):
            if row_verb != "branch" or not row_args or row_args[0] not in ("if", "error"):
                continue
            next_verb, next_args, next_ln = op.lines[idx + 1]
            if next_verb == "branch" and next_args[:2] == ["else", "target"]:
                branch_else_by_line[row_ln] = next_args[2]
                attached_branch_else_lines.add(next_ln)
        source_reachable_line_numbers_cache = None

        def collect_await_cases(start_index):
            cases = []
            done_label = None
            done_lineno = None
            index = start_index
            while index < len(op.lines):
                row_verb, row_args, row_ln = op.lines[index]
                if row_verb in {"__typedComment__", "__groupAnchor__"}:
                    index += 1
                    continue
                if row_verb == "case":
                    if len(row_args) != 2:
                        raise ValueError(
                            f"line {row_ln}: case requires: case CALL LABEL")
                    cases.append((row_args[0], row_args[1], row_ln))
                    index += 1
                    continue
                if row_verb == "done":
                    if len(row_args) != 1:
                        raise ValueError(
                            f"line {row_ln}: done requires: done LABEL")
                    done_label = row_args[0]
                    done_lineno = row_ln
                    index += 1
                break
            return cases, done_label, done_lineno, index

        def source_branch_targets(row_verb, row_args):
            if row_verb == "jump" and len(row_args) >= 2 and row_args[0] == "target":
                return [row_args[1]]
            if row_verb == "branch":
                if len(row_args) >= 5 and row_args[0] in {"if", "error"} and row_args[3] == "target":
                    return [row_args[4]]
                if len(row_args) >= 3 and row_args[0] == "else" and row_args[1] == "target":
                    return [row_args[2]]
                if row_args:
                    return [row_args[0]]
            if row_verb == "branchIf" and len(row_args) >= 2:
                targets = [row_args[1]]
                if len(row_args) >= 3:
                    targets.append(row_args[2])
                return targets
            if row_verb in {"branchIfError", "branchIfGroupError", "branchIfChannelClosed"} and len(row_args) >= 2:
                return [row_args[1]]
            if row_verb == "branchSelected" and len(row_args) >= 3:
                return [row_args[2]]
            if row_verb == "runChecked" and len(row_args) >= 9:
                return [row_args[8]]
            if row_verb == "case" and len(row_args) >= 2:
                return [row_args[1]]
            if row_verb == "done" and row_args:
                return [row_args[0]]
            return []

        def source_branch_targets_with_attached_else(row_verb, row_args, row_ln):
            targets = list(source_branch_targets(row_verb, row_args))
            else_label = branch_else_by_line.get(row_ln)
            if else_label is not None and else_label not in targets:
                targets.append(else_label)
            return targets

        def source_line_reachable_numbers():
            nonlocal source_reachable_line_numbers_cache
            if source_reachable_line_numbers_cache is not None:
                return source_reachable_line_numbers_cache
            if not op.lines:
                source_reachable_line_numbers_cache = set()
                return source_reachable_line_numbers_cache

            label_indices = {
                row_args[0]: index
                for index, (row_verb, row_args, _row_ln) in enumerate(op.lines)
                if row_verb == "label" and row_args
            }

            def add_label_successor(successors, label_name):
                target_index = label_indices.get(label_name)
                if target_index is not None:
                    successors.append(target_index)

            def add_fallthrough_successor(successors, index):
                next_index = index + 1
                if next_index < len(op.lines):
                    successors.append(next_index)

            def successor_indices(index):
                row_verb, row_args, row_ln = op.lines[index]
                successors = []
                if row_verb == "await":
                    await_cases, done_label, _done_lineno, _next_index = collect_await_cases(index + 1)
                    if await_cases or done_label is not None:
                        for _call_name, target_label, _case_lineno in await_cases:
                            add_label_successor(successors, target_label)
                        if done_label is not None:
                            add_label_successor(successors, done_label)
                        return successors
                if row_verb in {"return", "returnOk", "returnError", "returnVoid"}:
                    return successors
                if row_verb == "jump" and len(row_args) >= 2 and row_args[0] == "target":
                    add_label_successor(successors, row_args[1])
                    return successors
                if row_verb == "branch":
                    if len(row_args) >= 5 and row_args[0] in {"if", "error"} and row_args[3] == "target":
                        add_label_successor(successors, row_args[4])
                        else_label = branch_else_by_line.get(row_ln)
                        if else_label is None:
                            add_fallthrough_successor(successors, index)
                        else:
                            add_label_successor(successors, else_label)
                        return successors
                    if len(row_args) >= 3 and row_args[0] == "else" and row_args[1] == "target":
                        add_label_successor(successors, row_args[2])
                        return successors
                    if row_args:
                        add_label_successor(successors, row_args[0])
                        add_fallthrough_successor(successors, index)
                        return successors
                if row_verb == "branchIf" and len(row_args) >= 2:
                    add_label_successor(successors, row_args[1])
                    if len(row_args) >= 3:
                        add_label_successor(successors, row_args[2])
                    else:
                        add_fallthrough_successor(successors, index)
                    return successors
                if row_verb in {"branchIfError", "branchIfGroupError", "branchIfChannelClosed"} and len(row_args) >= 2:
                    add_label_successor(successors, row_args[1])
                    add_fallthrough_successor(successors, index)
                    return successors
                if row_verb == "runChecked" and len(row_args) >= 9:
                    add_label_successor(successors, row_args[8])
                    add_fallthrough_successor(successors, index)
                    return successors
                if row_verb == "branchSelected" and len(row_args) >= 3:
                    add_label_successor(successors, row_args[2])
                    add_fallthrough_successor(successors, index)
                    return successors
                add_fallthrough_successor(successors, index)
                return successors

            reachable_indices = set()
            stack = [0]
            while stack:
                current_index = stack.pop()
                if current_index in reachable_indices:
                    continue
                reachable_indices.add(current_index)
                stack.extend(successor_indices(current_index))
            source_reachable_line_numbers_cache = {
                op.lines[index][2] for index in reachable_indices
            }
            return source_reachable_line_numbers_cache

        def source_row_terminates_before_next_label(row_verb, row_args):
            if row_verb in {"jump", "return", "returnOk", "returnError", "returnVoid"}:
                return True
            if row_verb == "branch" and len(row_args) >= 3 and row_args[0] == "else":
                return True
            return False

        def source_call_result_reference(row_verb, row_args):
            if row_verb == "bind" and len(row_args) >= 4 and row_args[0] in {"value", "ok", "error"}:
                return row_args[3]
            if row_verb == "ignore":
                if len(row_args) >= 5 and row_args[0] in {"value", "ok"} and row_args[1] == "source":
                    return row_args[2]
                if len(row_args) >= 3 and row_args[0] in {"error", "void"} and row_args[1] == "source":
                    return row_args[2]
            if row_verb == "await" and len(row_args) == 1:
                return row_args[0]
            if row_verb == "branch" and len(row_args) >= 5 and row_args[:2] == ["error", "source"]:
                return row_args[2]
            if row_verb == "branchIfError" and row_args:
                return row_args[0]
            return None

        def source_symbol_definition(row_verb, row_args):
            if row_verb == "bind" and len(row_args) >= 4 and row_args[0] in {"value", "ok", "error"}:
                return row_args[1]
            if row_verb == "fieldGet" and row_args:
                return row_args[0]
            if row_verb in {"new", "call", "recordBuild", "receive"} and row_args:
                return row_args[0]
            if (row_verb == "read" and len(row_args) >= 4
                    and row_args[0] in {"sharedState", "local", "module"}):
                return row_args[1]
            if row_verb in {"memory", "storage"} and len(row_args) >= 4:
                return row_args[2]
            return None

        def source_call_result_definition(row_verb, row_args):
            if row_verb in {"run", "await", "submitWork", "awaitWork"} and row_args:
                return row_args[0]
            return None

        def source_symbol_references(row_verb, row_args):
            refs = set()
            call_ref = source_call_result_reference(row_verb, row_args)
            if call_ref is not None:
                refs.add(call_ref)
            if row_verb == "argument" and len(row_args) >= 4:
                refs.add(row_args[3])
            elif row_verb == "arg" and len(row_args) >= 3:
                refs.add(row_args[2])
            elif row_verb == "cancelOn" and len(row_args) >= 2:
                refs.add(row_args[1])
            elif row_verb in {"run", "runChecked"} and row_args:
                refs.add(row_args[0])
            elif row_verb == "fieldSet" and len(row_args) >= 3:
                refs.add(row_args[0])
                refs.add(row_args[2])
            elif row_verb == "fieldGet" and len(row_args) >= 3:
                refs.add(row_args[2])
            elif row_verb in {"memory", "storage"} and len(row_args) >= 5:
                refs.add(row_args[4])
            elif (row_verb == "read" and len(row_args) >= 4
                    and row_args[0] in {"sharedState", "local", "module"}):
                refs.add(row_args[3])
            elif row_verb == "receive" and len(row_args) >= 3:
                refs.add(row_args[2])
            elif row_verb == "send" and len(row_args) >= 2:
                refs.add(row_args[1])
            elif row_verb == "workArg" and len(row_args) >= 3:
                refs.add(row_args[2])
            elif row_verb in {"defer", "deferLog", "deferAwaitLog"} and len(row_args) >= 3:
                refs.update(row_args[2:])
            elif row_verb == "deferWhenExitLog" and len(row_args) >= 4:
                refs.update(row_args[3:])
            elif row_verb == "set" and len(row_args) >= 3:
                refs.add(row_args[1])
                refs.add(row_args[2])
            elif row_verb == "return" and len(row_args) >= 2 and row_args[0] in {"value", "ok", "error"}:
                refs.add(row_args[1])
            elif row_verb in {"returnValue", "returnOk", "returnError"} and row_args:
                refs.add(row_args[0])
            elif row_verb == "branch" and len(row_args) >= 5 and row_args[0] == "if":
                refs.add(row_args[2])
            elif row_verb == "branchIf" and row_args:
                refs.add(row_args[0])
            elif row_verb == "makeError" and len(row_args) >= 3:
                refs.add(row_args[2])
            return refs

        def source_label_before_line(lineno):
            current_label = None
            for row_verb, row_args, row_ln in op.lines:
                if row_ln >= lineno:
                    break
                if row_verb == "label" and row_args:
                    current_label = row_args[0]
            return current_label

        def source_label_reaches_line(label_name, target_lineno):
            label_indices = {
                row_args[0]: index
                for index, (row_verb, row_args, _row_ln) in enumerate(op.lines)
                if row_verb == "label" and row_args
            }
            line_indices = {
                row_ln: index
                for index, (_row_verb, _row_args, row_ln) in enumerate(op.lines)
            }
            start_index = label_indices.get(label_name)
            target_index = line_indices.get(target_lineno)
            if start_index is None or target_index is None:
                return False

            def add_label_successor(successors, target_label):
                next_index = label_indices.get(target_label)
                if next_index is not None:
                    successors.append(next_index)

            def add_fallthrough_successor(successors, index):
                next_index = index + 1
                if next_index < len(op.lines):
                    successors.append(next_index)

            def successor_indices(index):
                row_verb, row_args, row_ln = op.lines[index]
                successors = []
                if row_verb == "await":
                    await_cases, done_label, _done_lineno, _next_index = collect_await_cases(index + 1)
                    if await_cases or done_label is not None:
                        for _call_name, target_label, _case_lineno in await_cases:
                            add_label_successor(successors, target_label)
                        if done_label is not None:
                            add_label_successor(successors, done_label)
                        return successors
                if row_verb in {"return", "returnOk", "returnError", "returnVoid"}:
                    return successors
                if row_verb == "jump" and len(row_args) >= 2 and row_args[0] == "target":
                    add_label_successor(successors, row_args[1])
                    return successors
                if row_verb == "branch":
                    if len(row_args) >= 5 and row_args[0] in {"if", "error"} and row_args[3] == "target":
                        add_label_successor(successors, row_args[4])
                        else_label = branch_else_by_line.get(row_ln)
                        if else_label is None:
                            add_fallthrough_successor(successors, index)
                        else:
                            add_label_successor(successors, else_label)
                        return successors
                    if len(row_args) >= 3 and row_args[0] == "else" and row_args[1] == "target":
                        add_label_successor(successors, row_args[2])
                        return successors
                    if row_args:
                        add_label_successor(successors, row_args[0])
                        add_fallthrough_successor(successors, index)
                        return successors
                if row_verb == "branchIf" and len(row_args) >= 2:
                    add_label_successor(successors, row_args[1])
                    if len(row_args) >= 3:
                        add_label_successor(successors, row_args[2])
                    else:
                        add_fallthrough_successor(successors, index)
                    return successors
                if row_verb in {"branchIfError", "branchIfGroupError", "branchIfChannelClosed"} and len(row_args) >= 2:
                    add_label_successor(successors, row_args[1])
                    add_fallthrough_successor(successors, index)
                    return successors
                if row_verb == "runChecked" and len(row_args) >= 9:
                    add_label_successor(successors, row_args[8])
                    add_fallthrough_successor(successors, index)
                    return successors
                if row_verb == "branchSelected" and len(row_args) >= 3:
                    add_label_successor(successors, row_args[2])
                    add_fallthrough_successor(successors, index)
                    return successors
                add_fallthrough_successor(successors, index)
                return successors

            seen = set()
            stack = [start_index]
            while stack:
                current_index = stack.pop()
                if current_index in seen:
                    continue
                if current_index == target_index:
                    return True
                seen.add(current_index)
                stack.extend(successor_indices(current_index))
            return False

        def start_reentry_edge(start_lineno):
            labels_before_start = {
                label_name
                for label_name, label_lineno in declared_label_lines.items()
                if label_lineno <= start_lineno
            }
            for row_verb, row_args, row_ln in op.lines:
                if row_ln <= start_lineno:
                    continue
                if row_ln not in source_line_reachable_numbers():
                    continue
                for target_label in source_branch_targets_with_attached_else(
                        row_verb, row_args, row_ln):
                    if (target_label in labels_before_start
                            and source_label_reaches_line(
                                target_label, start_lineno)):
                        return row_verb, row_ln, target_label
            return None

        def start_reaches_wait_set_entry(call_name, await_lineno):
            start_lines = [
                row_ln
                for row_verb, row_args, row_ln in op.lines
                if row_verb == "start"
                and row_args
                and row_args[0] == call_name
                and row_ln < await_lineno
            ]
            if len(start_lines) > 1:
                return False, start_lines[-1], "multiple"
            reachable_line_numbers = source_line_reachable_numbers()
            for start_lineno in reversed(start_lines):
                if start_lineno not in reachable_line_numbers:
                    continue
                blocked_by_terminator = False
                for row_verb, row_args, row_ln in op.lines:
                    if row_ln not in reachable_line_numbers:
                        continue
                    if row_ln >= start_lineno:
                        break
                    if row_verb == "label":
                        blocked_by_terminator = False
                        continue
                    if source_row_terminates_before_next_label(row_verb, row_args):
                        blocked_by_terminator = True
                if blocked_by_terminator:
                    continue
                intervening_labels = {
                    row_args[0]: row_ln
                    for row_verb, row_args, row_ln in op.lines
                    if row_verb == "label"
                    and row_args
                    and start_lineno < row_ln < await_lineno
                }
                bypasses_start = False
                for row_verb, row_args, row_ln in op.lines:
                    if row_ln not in reachable_line_numbers:
                        continue
                    if row_ln >= start_lineno:
                        continue
                    for target_label in source_branch_targets_with_attached_else(
                            row_verb, row_args, row_ln):
                        if target_label in intervening_labels:
                            bypasses_start = True
                            break
                    if bypasses_start:
                        break
                if not bypasses_start:
                    return True, start_lineno, "ok"
            return False, (start_lines[-1] if start_lines else None), "missing"

        def source_row_ignored_in_wait_set_gap(row_verb):
            return row_verb in {
                "__typedComment__", "__groupAnchor__",
                "input", "output", "effect", "async",
                "purpose", "invariant", "warning",
            }

        def next_effective_source_row_after(lineno):
            for row_verb, row_args, row_ln in op.lines:
                if row_ln <= lineno:
                    continue
                if source_row_ignored_in_wait_set_gap(row_verb):
                    continue
                return row_verb, row_args, row_ln
            return None

        await_select_name_counts = {}

        def async_start_failed_cond(call_name, call_obj):
            start_status = None
            if call_obj.get("start_status_slot") is not None:
                start_status = builder.load(
                    call_obj["start_status_slot"],
                    name=f"{call_name}_select_start_status")
            elif call_obj.get("start_status") is not None:
                start_status = call_obj["start_status"]
            if start_status is None:
                start_status = ir.Constant(Int32, 0)
            if start_status.type != Int32:
                start_status = coerce_to_type(start_status, Int32)
            return builder.icmp_unsigned(
                "!=", start_status, ir.Constant(Int32, 0),
                name=f"{call_name}_select_start_failed")

        def async_case_ready_cond(
            wait_name, block_prefix, call_name, case_index, wait_error_slot):
            call_obj = calls.get(call_name)
            if call_obj is None:
                raise ValueError(
                    f"await {wait_name}: case references unknown call `{call_name}`")
            if call_obj.get("async_awaited"):
                raise ValueError(
                    f"await {wait_name}: case `{call_name}` was already "
                    "awaited or consumed by an earlier wait-set case")
            future_slot = call_obj.get("future_slot")
            if future_slot is None:
                raise ValueError(
                    f"await {wait_name}: case `{call_name}` was not started "
                    "with async lowering")
            future = builder.load(
                future_slot,
                name=f"{block_prefix}_{call_name}_case_future")
            if is_async_fetch_target(call_obj):
                ready_fn = self._runtime_func(
                    "ss_http_client_fetch_is_ready", Int32, [Int8P])
                self.provenance.record_external(
                    "ss_http_client_fetch_is_ready", call_obj)
            elif is_async_user_op_target(call_obj) and operation_async_enabled:
                ready_fn = self._runtime_func(
                    "ss_async_future_is_ready", Int32, [Int8P])
                self.provenance.record_external(
                    "ss_async_future_is_ready", call_obj)
            else:
                raise ValueError(
                    f"await {wait_name}: case `{call_name}` does not target "
                    "a supported async future")
            ready_value = builder.call(
                ready_fn,
                [future],
                name=f"{block_prefix}_{case_index}_{call_name}_ready")
            ready_cond = builder.icmp_unsigned(
                "!=", ready_value, ir.Constant(Int32, 0),
                name=f"{block_prefix}_{case_index}_{call_name}_is_ready")
            start_failed = async_start_failed_cond(call_name, call_obj)
            ready_or_start_failed = builder.or_(
                ready_cond,
                start_failed,
                name=f"{block_prefix}_{case_index}_{call_name}_ready_or_start_failed")
            wait_error_status = builder.load(
                wait_error_slot,
                name=f"{block_prefix}_{case_index}_{call_name}_poll_status")
            wait_error = builder.icmp_unsigned(
                "!=",
                wait_error_status,
                ir.Constant(Int32, 0),
                name=f"{block_prefix}_{case_index}_{call_name}_poll_failed")
            return builder.or_(
                ready_or_start_failed,
                wait_error,
                name=f"{block_prefix}_{case_index}_{call_name}_selectable")

        def validate_await_select_source(
            wait_name, cases, done_label, done_lineno, lineno,
            seen_wait_set_case_calls=None,
        ):
            if not cases:
                raise ValueError(
                    f"line {lineno}: await {wait_name} requires at least one "
                    "following case row")
            if done_label is None:
                raise ValueError(
                    f"line {lineno}: await {wait_name} requires a following "
                    "done LABEL row")
            if wait_name in declared_call_names:
                raise ValueError(
                    f"line {lineno}: await wait-set name `{wait_name}` "
                    "collides with a declared call name")
            if done_label not in declared_label_names:
                raise ValueError(
                    f"line {lineno}: await {wait_name} done label "
                    f"`{done_label}` is not declared")
            done_label_line = declared_label_lines.get(done_label)
            if done_label_line is not None and done_label_line <= done_lineno:
                raise ValueError(
                    f"line {lineno}: await {wait_name} done label "
                    f"`{done_label}` must be declared after its done row")
            next_after_done = next_effective_source_row_after(done_lineno)
            if next_after_done is not None:
                next_verb, _next_args, next_lineno = next_after_done
                if next_verb != "label":
                    raise ValueError(
                        f"line {next_lineno}: await {wait_name} done row "
                        "must be followed by a label before executable row "
                        f"`{next_verb}`")
            seen_case_calls = set()
            seen_case_target_labels = {}
            for call_name, target_label, case_lineno in cases:
                if call_name in seen_case_calls:
                    raise ValueError(
                        f"line {case_lineno}: duplicate await case `{call_name}` "
                        f"for wait set `{wait_name}`")
                if seen_wait_set_case_calls is not None:
                    previous_case = seen_wait_set_case_calls.get(call_name)
                    if previous_case is not None:
                        previous_wait_name = previous_case[0]
                        previous_case_lineno = previous_case[2]
                        raise ValueError(
                            f"line {case_lineno}: await {wait_name} case "
                            f"`{call_name}` was already awaited or consumed "
                            "by an earlier wait-set case "
                            f"`await {previous_wait_name}` on line "
                            f"{previous_case_lineno}")
                if call_name not in declared_call_names:
                    raise ValueError(
                        f"await {wait_name}: case references unknown call "
                        f"`{call_name}`")
                start_reaches_entry, start_lineno, start_reason = start_reaches_wait_set_entry(
                    call_name, lineno)
                if not start_reaches_entry:
                    if start_reason == "multiple":
                        raise ValueError(
                            f"line {case_lineno}: await {wait_name} case "
                            f"`{call_name}` has multiple prior start rows; "
                            "use a fresh call name for each future")
                    if start_lineno is None:
                        raise ValueError(
                            f"await {wait_name}: case `{call_name}` was not "
                            "started with async lowering")
                    raise ValueError(
                        f"line {case_lineno}: await {wait_name} case "
                        f"`{call_name}` start on line {start_lineno} does "
                        "not dominate the wait-set entry")
                reentry_edge = start_reentry_edge(start_lineno)
                if reentry_edge is not None:
                    edge_verb, edge_lineno, edge_label = reentry_edge
                    raise ValueError(
                        f"line {edge_lineno}: await {wait_name} case "
                        f"`{call_name}` start on line {start_lineno} can be "
                        f"re-entered by `{edge_verb}` targeting "
                        f"`{edge_label}`; use a fresh call name for each "
                        "future")
                if target_label not in declared_label_names:
                    raise ValueError(
                        f"line {case_lineno}: await {wait_name} case "
                        f"`{call_name}` target label `{target_label}` "
                        "is not declared")
                target_label_line = declared_label_lines.get(target_label)
                if target_label_line is not None and target_label_line <= case_lineno:
                    raise ValueError(
                        f"line {case_lineno}: await {wait_name} case "
                        f"target label `{target_label}` must be declared "
                        "after its case row")
                previous_effective_row = None
                for row_verb, row_args, row_ln in op.lines:
                    if row_ln >= target_label_line:
                        break
                    if row_verb in {
                        "__typedComment__", "__groupAnchor__",
                        "input", "output", "effect", "async",
                        "purpose", "invariant", "warning",
                    }:
                        continue
                    previous_effective_row = (row_verb, row_args, row_ln)
                if previous_effective_row is not None:
                    prev_verb, prev_args, prev_ln = previous_effective_row
                    if prev_verb != "done" and not source_row_terminates_before_next_label(
                            prev_verb, prev_args):
                        raise ValueError(
                            f"line {case_lineno}: await {wait_name} case "
                            f"target label `{target_label}` must not be "
                            f"reachable by fallthrough from `{prev_verb}` "
                            f"on line {prev_ln}")
                if target_label == done_label:
                    raise ValueError(
                        f"line {case_lineno}: await {wait_name} case "
                        f"target label `{target_label}` must differ from "
                        "the done label")
                previous_target_lineno = seen_case_target_labels.get(target_label)
                if previous_target_lineno is not None:
                    raise ValueError(
                        f"line {case_lineno}: await {wait_name} case "
                        f"target label `{target_label}` is used by "
                        f"multiple cases; first used on line "
                        f"{previous_target_lineno}")
                seen_case_calls.add(call_name)
                if seen_wait_set_case_calls is not None:
                    seen_wait_set_case_calls[call_name] = (
                        wait_name, target_label, case_lineno)
                seen_case_target_labels[target_label] = case_lineno
            for target_label, case_lineno in seen_case_target_labels.items():
                for row_verb, row_args, row_ln in op.lines:
                    if row_verb == "case" and row_ln == case_lineno:
                        continue
                    if target_label not in source_branch_targets_with_attached_else(
                            row_verb, row_args, row_ln):
                        continue
                    raise ValueError(
                        f"line {case_lineno}: await {wait_name} case "
                        f"target label `{target_label}` may only be reached "
                        f"from that case; also referenced by `{row_verb}` "
                        f"on line {row_ln}")
            previous_effective_row = None
            for row_verb, row_args, row_ln in op.lines:
                if row_ln >= done_label_line:
                    break
                if row_verb in {
                    "__typedComment__", "__groupAnchor__",
                    "input", "output", "effect", "async",
                    "purpose", "invariant", "warning",
                }:
                    continue
                previous_effective_row = (row_verb, row_args, row_ln)
            if previous_effective_row is not None:
                prev_verb, prev_args, prev_ln = previous_effective_row
                previous_is_owning_done_row = (
                    prev_verb == "done"
                    and prev_args
                    and prev_args[0] == done_label
                    and prev_ln == done_lineno
                )
                if (prev_verb != "case"
                        and not previous_is_owning_done_row
                        and not source_row_terminates_before_next_label(
                            prev_verb, prev_args)):
                    raise ValueError(
                        f"line {lineno}: await {wait_name} done label "
                        f"`{done_label}` must not be reachable by "
                        f"fallthrough from `{prev_verb}` on line {prev_ln}")
            for row_verb, row_args, row_ln in op.lines:
                if row_verb == "done" and row_ln == done_lineno:
                    continue
                if done_label not in source_branch_targets_with_attached_else(
                        row_verb, row_args, row_ln):
                    continue
                raise ValueError(
                    f"line {lineno}: await {wait_name} done label "
                        f"`{done_label}` may only be reached from that done row; "
                    f"also referenced by `{row_verb}` on line {row_ln}")

        def validate_wait_set_case_result_ownership(case_owners):
            private_symbols = {}
            for wait_name, target_label, case_lineno in case_owners.values():
                target_label_line = declared_label_lines.get(target_label)
                if target_label_line is None:
                    continue
                for row_verb, row_args, row_ln in op.lines:
                    if row_ln <= target_label_line:
                        continue
                    if row_verb == "label":
                        break
                    symbol_name = source_symbol_definition(row_verb, row_args)
                    if symbol_name is not None:
                        private_symbols[symbol_name] = (
                            wait_name, target_label, case_lineno, row_ln)
                    call_result_name = source_call_result_definition(
                        row_verb, row_args)
                    if call_result_name is not None:
                        private_symbols[call_result_name] = (
                            wait_name, target_label, case_lineno, row_ln)
                    if row_verb == "runChecked" and len(row_args) >= 6:
                        private_symbols[row_args[2]] = (
                            wait_name, target_label, case_lineno, row_ln)
                        private_symbols[row_args[5]] = (
                            wait_name, target_label, case_lineno, row_ln)
            call_private_dependencies = {}

            def private_owner_for_symbol(symbol_name):
                owner = private_symbols.get(symbol_name)
                if owner is not None:
                    return owner
                if symbol_name in case_owners:
                    wait_name, target_label, case_lineno = case_owners[symbol_name]
                    return wait_name, target_label, case_lineno, case_lineno
                return None

            for row_verb, row_args, _row_ln in op.lines:
                call_name = None
                value_name = None
                if row_verb == "argument" and len(row_args) >= 4:
                    call_name = row_args[0]
                    value_name = row_args[3]
                elif row_verb == "arg" and len(row_args) >= 3:
                    call_name = row_args[0]
                    value_name = row_args[2]
                elif row_verb == "workArg" and len(row_args) >= 3:
                    call_name = row_args[0]
                    value_name = row_args[2]
                if call_name is None or value_name is None:
                    continue
                owner = private_owner_for_symbol(value_name)
                if owner is None:
                    continue
                call_private_dependencies.setdefault(call_name, []).append(
                    (value_name, *owner))
            for row_verb, row_args, row_ln in op.lines:
                if row_verb == "case":
                    continue
                current_label = source_label_before_line(row_ln)
                referenced_private_symbols = []
                if row_verb in {
                    "run", "runChecked", "start", "startInGroup", "submitWork"
                } and row_args:
                    for dependency in call_private_dependencies.get(row_args[0], []):
                        symbol_name, wait_name, target_label, case_lineno, definition_lineno = dependency
                        referenced_private_symbols.append((
                            symbol_name, wait_name, target_label,
                            case_lineno, definition_lineno, "value"))
                mutation_escape = None
                if (row_verb == "set" and len(row_args) >= 3
                        and row_args[0] in {"memory", "storage"}):
                    mutation_escape = (row_args[2], row_args[1])
                elif row_verb == "fieldSet" and len(row_args) >= 3:
                    mutation_escape = (row_args[2], row_args[0])
                elif row_verb == "send" and len(row_args) >= 2:
                    mutation_escape = (row_args[1], row_args[0])
                if mutation_escape is not None:
                    value_name, target_name = mutation_escape
                    owner = private_owner_for_symbol(value_name)
                    if owner is not None:
                        wait_name, target_label, case_lineno, definition_lineno = owner
                        target_owner = private_owner_for_symbol(target_name)
                        target_is_private_to_same_handler = (
                            target_owner is not None
                            and target_owner[1] == target_label
                        )
                        if (row_ln > definition_lineno
                                and current_label == target_label
                                and not target_is_private_to_same_handler):
                            raise ValueError(
                                f"line {row_ln}: await {wait_name} case "
                                f"`{value_name}` value may not be written "
                                "into non-private state "
                                f"`{target_name}` from handler label "
                                f"`{target_label}`; consume it before "
                                "re-entering the wait set or keep it in "
                            "handler-local state")
                referenced_call = source_call_result_reference(row_verb, row_args)
                if referenced_call is not None and referenced_call in case_owners:
                    wait_name, target_label, case_lineno = case_owners[referenced_call]
                    referenced_private_symbols.append((
                        referenced_call, wait_name, target_label,
                        case_lineno, case_lineno, "result"))
                for symbol_name in source_symbol_references(row_verb, row_args):
                    owner = private_owner_for_symbol(symbol_name)
                    if owner is None:
                        continue
                    wait_name, target_label, case_lineno, definition_lineno = owner
                    referenced_private_symbols.append((
                        symbol_name, wait_name, target_label,
                        case_lineno, definition_lineno, "value"))
                for symbol_name, wait_name, target_label, case_lineno, definition_lineno, value_kind in referenced_private_symbols:
                    if current_label == target_label:
                        continue
                    raise ValueError(
                        f"line {row_ln}: await {wait_name} case "
                        f"`{symbol_name}` {value_kind} may only be read inside "
                        f"handler label `{target_label}` from case line "
                        f"{case_lineno}; `{row_verb}` is under label "
                        f"`{current_label or '<entry>'}`")

        def validate_wait_set_case_handler_reentry(
            wait_name, cases, lineno, wait_entry_label):
            if wait_entry_label is None:
                raise ValueError(
                    f"line {lineno}: await {wait_name} wait-set must be "
                    "preceded by a label so case handlers can re-enter it")
            for call_name, target_label, case_lineno in cases:
                target_label_line = declared_label_lines.get(target_label)
                if target_label_line is None:
                    continue
                saw_reentry = False
                for row_verb, row_args, row_ln in op.lines:
                    if row_ln <= target_label_line:
                        continue
                    if row_verb == "label":
                        break
                    if source_row_ignored_in_wait_set_gap(row_verb):
                        continue
                    if row_verb in {
                        "defer", "deferLog", "deferAwaitLog",
                        "deferWhenExitLog", "deferRunOn",
                    }:
                        raise ValueError(
                            f"line {row_ln}: await {wait_name} case "
                            f"`{call_name}` handler `{target_label}` must "
                            "not register defer cleanup before jumping back "
                            f"to `{wait_entry_label}`")
                    targets = source_branch_targets_with_attached_else(
                        row_verb, row_args, row_ln)
                    if row_verb == "jump" and targets == [wait_entry_label]:
                        saw_reentry = True
                        break
                    if row_verb in {"return", "returnOk", "returnError", "returnVoid"}:
                        raise ValueError(
                            f"line {row_ln}: await {wait_name} case "
                            f"`{call_name}` handler `{target_label}` must "
                            f"jump back to `{wait_entry_label}` before "
                            "returning")
                    disallowed_targets = [
                        target for target in targets
                        if target != wait_entry_label
                    ]
                    if disallowed_targets:
                        raise ValueError(
                            f"line {row_ln}: await {wait_name} case "
                            f"`{call_name}` handler `{target_label}` must "
                            f"not branch to `{disallowed_targets[0]}` before "
                            f"all cases are consumed; jump back to "
                            f"`{wait_entry_label}`")
                if not saw_reentry:
                    raise ValueError(
                        f"line {case_lineno}: await {wait_name} case "
                        f"`{call_name}` handler `{target_label}` must "
                        f"jump back to `{wait_entry_label}` after handling "
                        "the selected result")

        def validate_await_wait_sets_before_lowering():
            seen_wait_set_case_calls = {}
            index = 0
            while index < len(op.lines):
                row_verb, row_args, row_ln = op.lines[index]
                index += 1
                if row_verb == "await":
                    await_cases, done_label, done_lineno, next_index = collect_await_cases(index)
                    if await_cases or done_label is not None:
                        if len(row_args) != 1:
                            raise ValueError(
                                f"line {row_ln}: await wait set requires: await NAME")
                        validate_await_select_source(
                            row_args[0],
                            await_cases,
                            done_label,
                            done_lineno,
                            row_ln,
                            seen_wait_set_case_calls,
                        )
                        validate_wait_set_case_handler_reentry(
                            row_args[0],
                            await_cases,
                            row_ln,
                            source_label_before_line(row_ln),
                        )
                        index = next_index
                    continue
                if row_verb in {"case", "done"}:
                    raise ValueError(
                        f"line {row_ln}: `{row_verb}` must immediately follow "
                        "an `await NAME` wait-set row")
            validate_wait_set_case_result_ownership(seen_wait_set_case_calls)

        def emit_await_select(wait_name, cases, done_label, done_lineno, lineno):
            validate_await_select_source(
                wait_name, cases, done_label, done_lineno, lineno)
            wait_name_use_count = await_select_name_counts.get(wait_name, 0)
            await_select_name_counts[wait_name] = wait_name_use_count + 1
            block_prefix = (
                wait_name
                if wait_name_use_count == 0
                else f"{wait_name}_{wait_name_use_count}")
            consumed_slots = {}
            with builder.goto_entry_block():
                wait_error_slot = builder.alloca(
                    Int32, name=f"{block_prefix}_await_poll_error_status")
                builder.store(ir.Constant(Int32, 0), wait_error_slot)
            for call_name, _target_label, _case_lineno in cases:
                with builder.goto_entry_block():
                    consumed_slot = builder.alloca(
                        I1, name=f"{block_prefix}_{call_name}_consumed")
                    builder.store(ir.Constant(I1, 0), consumed_slot)
                consumed_slots[call_name] = consumed_slot

            fn = builder.function
            check_block = fn.append_basic_block(f"{block_prefix}_await_check")
            case_blocks = [
                fn.append_basic_block(f"{block_prefix}_{index}_{call_name}_case_check")
                for index, (call_name, _target_label, _case_lineno)
                in enumerate(cases)
            ]
            poll_block = fn.append_basic_block(f"{block_prefix}_await_poll")

            if not builder.block.is_terminated:
                builder.branch(check_block)

            builder.position_at_end(check_block)
            all_consumed = ir.Constant(I1, 1)
            for call_name, _target_label, _case_lineno in cases:
                consumed = builder.load(
                    consumed_slots[call_name],
                    name=f"{block_prefix}_{call_name}_consumed_value")
                all_consumed = builder.and_(
                    all_consumed,
                    consumed,
                    name=f"{block_prefix}_{call_name}_all_consumed")
            record_label_defers(done_label, active_defers)
            builder.cbranch(all_consumed, get_block(done_label), case_blocks[0])

            for index, (call_name, target_label, _case_lineno) in enumerate(cases):
                builder.position_at_end(case_blocks[index])
                consumed = builder.load(
                    consumed_slots[call_name],
                    name=f"{block_prefix}_{index}_{call_name}_consumed")
                not_consumed = builder.icmp_unsigned(
                    "==",
                    consumed,
                    ir.Constant(I1, 0),
                    name=f"{block_prefix}_{index}_{call_name}_not_consumed")
                selectable = async_case_ready_cond(
                    wait_name, block_prefix, call_name, index, wait_error_slot)
                eligible = builder.and_(
                    not_consumed,
                    selectable,
                    name=f"{block_prefix}_{index}_{call_name}_eligible")
                selected_block = fn.append_basic_block(
                    f"{block_prefix}_{index}_{call_name}_selected")
                next_block = (
                    case_blocks[index + 1]
                    if index + 1 < len(case_blocks)
                    else poll_block
                )
                builder.cbranch(eligible, selected_block, next_block)

                builder.position_at_end(selected_block)
                builder.store(ir.Constant(I1, 1), consumed_slots[call_name])
                if not emit_async_fetch_await(call_name):
                    if not emit_async_user_op_await(call_name):
                        raise ValueError(
                            f"await {wait_name}: case `{call_name}` does not "
                            "target a supported async future")
                record_label_defers(target_label, active_defers)
                self._emit_trace_event(
                    builder, "branch.decision", "branch", op.name,
                    wait_name, target_label, lineno)
                builder.branch(get_block(target_label))

            builder.position_at_end(poll_block)
            loop = ensure_async_loop()
            run_once_fn = self._runtime_func(
                "ss_async_loop_run_once", Int32, [Int8P])
            self.provenance.record_external("ss_async_loop_run_once", None)
            poll_status = builder.call(
                run_once_fn,
                [loop],
                name=f"{block_prefix}_await_poll_status")
            poll_failed = builder.icmp_unsigned(
                "!=",
                poll_status,
                ir.Constant(Int32, 0),
                name=f"{block_prefix}_await_poll_failed")
            poll_error_block = fn.append_basic_block(
                f"{block_prefix}_await_poll_error")
            poll_continue_block = fn.append_basic_block(
                f"{block_prefix}_await_poll_continue")
            builder.cbranch(poll_failed, poll_error_block, poll_continue_block)

            builder.position_at_end(poll_error_block)
            builder.store(poll_status, wait_error_slot)
            builder.branch(check_block)

            builder.position_at_end(poll_continue_block)
            builder.branch(check_block)

            dead_block = fn.append_basic_block(f"after_{block_prefix}_await_select")
            builder.position_at_end(dead_block)
            builder.unreachable()

        validate_await_wait_sets_before_lowering()

        line_index = 0
        while line_index < len(op.lines):
            verb, args, _ln = op.lines[line_index]
            line_index += 1
            # ----- metadata: ignored at codegen -----
            if verb in ("input", "output", "effect", "async",
                        "purpose", "invariant", "warning"):
                continue
            if verb == "memory" and len(args) >= 2 and args[1] in ("heap", "arena", "stack"):
                continue

            if verb == "label":
                label_name = args[0]
                target_bb = labels[label_name]
                if not builder.block.is_terminated:
                    if current_block_reachable:
                        record_label_defers(label_name, active_defers)
                    builder.branch(target_bb)
                builder.position_at_end(target_bb)
                if label_name in label_defer_snapshots:
                    active_defers = list(label_defer_snapshots[label_name])
                elif not current_block_reachable:
                    active_defers = []
                current_block_reachable = True
                continue

            if verb == "const":
                continue

            if verb == "memory" and len(args) >= 5 and args[1] in ("mutable", "immutable"):
                # memory OPERATION mutable|immutable NAME TYPE INITIAL_VALUE
                _owner, mutability = args[0], args[1]
                name, typ_name = args[2], args[3]
                raw = _unwrap(args[4])
                if mutability == "immutable":
                    op.consts[name] = (typ_name, raw)
                    continue
                llty = llvm_type_for(prog, typ_name)
                if llty is None:
                    raise ValueError(f"memory: unsupported type {typ_name}")
                with builder.goto_entry_block():
                    slot = builder.alloca(llty, name=name)
                if isinstance(raw, str):
                    try:
                        init = resolve(raw)
                    except ValueError:
                        init = emit_const_value(typ_name, raw)
                else:
                    init = emit_const_value(typ_name, raw)
                if init is SENTINEL:
                    raise ValueError("memory: cannot initialize from opaque input")
                if init.type != llty:
                    if isinstance(init.type, ir.IntType) and isinstance(llty, ir.IntType):
                        if init.type.width < llty.width:
                            init = (builder.zext if init.type.width == 1 else builder.sext)(
                                init, llty)
                        else:
                            init = builder.trunc(init, llty)
                    elif isinstance(init.type, ir.IntType) and isinstance(llty, ir.PointerType):
                        init = builder.inttoptr(init, llty)
                    elif isinstance(init.type, ir.PointerType) and isinstance(llty, ir.IntType):
                        init = builder.ptrtoint(init, llty)
                    elif isinstance(init.type, ir.PointerType) and isinstance(llty, ir.PointerType):
                        init = builder.bitcast(init, llty)
                builder.store(init, slot)
                binds[name] = slot
                var_types[name] = llty
                is_var.add(name)
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
                    if const_ll == Int8P and isinstance(const_val, str):
                        init = self._i8p(builder, const_val)
                    elif resolve_alias(prog, const_typ) == "Bool":
                        # Use the var's declared LLVM width — when the var
                        # is Int64 / Bool / etc., we want the init to match
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
                elif llty == Int8P and isinstance(raw, str):
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
                # Syntax-cutover form: set memory|storage NAME VALUE.
                scope_prefixed = bool(args and args[0] in
                                       ("memory", "storage", "sharedState"))
                if scope_prefixed:
                    name, value_name = args[1], args[2]
                else:
                    name, value_name = args[0], args[1]
                # Module-scope mutable globals: route the store through the
                # LLVM global. Owner / guard authority is accepted as metadata
                # but not enforced — surfacing it requires real ownership
                # tracking, which the spec leaves as future work.
                if (scope_prefixed and args[0] in ("storage", "sharedState")
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
                    # Some refined metadata surfaces non-lowered storage;
                    # keep storage writes to those declarations as no-ops,
                    # but require new `set memory` rows to hit real memory.
                    if scope_prefixed and args[0] != "memory":
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
                call_name, source_target = args[0], args[1]
                target = _TARGET_ALIASES.get(source_target, source_target)
                # `result`      : value bound by bindOk / bind
                # `error_value` : value bound by bindError (defaults to result)
                # `error_cond`  : i1 used by branchIfError (default: result < 0)
                calls[call_name] = make_call(call_name, target, _ln)
                calls[call_name]["source_target"] = source_target
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

            if verb == "argument":
                call_name, arg_name, _type_name, value_name = args[0], args[1], args[2], args[3]
                calls[call_name]["args"][arg_name] = value_name
                calls[call_name]["arg_types"][arg_name] = _type_name
                calls[call_name]["arg_lines"][arg_name] = _ln
                continue

            if verb == "timeout" and len(args) >= 2:
                calls[args[0]]["timeout"] = args[1]
                continue

            if verb == "cancelOn" and len(args) >= 2:
                calls[args[0]]["cancel_on"] = args[1]
                continue

            if verb == "run":
                call_name = args[0]
                async_only_target = async_native_binding_metadata_target(calls.get(call_name))
                if async_only_target is not None:
                    raise ValueError(
                        f"run: `{call_name}` targets async-only runtimeBinding "
                        f"operation `{async_only_target}`; use start/await")
                policy_name = retry_attachments.get(call_name)
                if policy_name is None:
                    trace_call_event("call.start", call_name)
                    self._emit_run(builder, call_name, calls,
                                   resolve, opaque_inputs, SENTINEL)
                    trace_call_event("call.end", call_name)
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
                        Int64, name=f"{call_name}_attempt")
                builder.store(ir.Constant(Int64, 0), attempt_slot)
                builder.branch(retry_top)
                builder.position_at_end(retry_top)
                cur_attempt = builder.load(attempt_slot)
                cond = builder.icmp_signed(
                    "<", cur_attempt, ir.Constant(Int64, max_attempts))
                builder.cbranch(cond, retry_body, retry_exit)
                builder.position_at_end(retry_body)
                trace_call_event("call.start", call_name)
                self._emit_run(builder, call_name, calls,
                               resolve, opaque_inputs, SENTINEL)
                trace_call_event("call.end", call_name)
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
                    builder.load(attempt_slot), ir.Constant(Int64, 1))
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

            if verb == "runChecked":
                (call_name, _ok_keyword, ok_name, _ok_type,
                 _error_keyword, error_name, _error_type,
                 _else_keyword, fail_label) = args
                if call_name not in calls:
                    raise ValueError(
                        f"line {_ln}: runChecked references unknown call "
                        f"`{call_name}`")
                async_only_target = async_native_binding_metadata_target(calls.get(call_name))
                if async_only_target is not None:
                    raise ValueError(
                        f"runChecked: `{call_name}` targets async-only "
                        f"runtimeBinding operation `{async_only_target}`; use start/await")
                if call_name in retry_attachments:
                    raise ValueError(
                        f"runChecked: call `{call_name}` has useRetry policy "
                        "metadata, but runChecked retry lowering is not "
                        "implemented yet; use explicit `run` plus checked "
                        "bindings for retry-managed calls")
                trace_call_event("call.start", call_name)
                self._emit_run(builder, call_name, calls,
                               resolve, opaque_inputs, SENTINEL)
                trace_call_event("call.end", call_name)
                call = calls[call_name]
                binds[ok_name] = call["result"]
                slot = call.get("handle_slot")
                if slot is not None:
                    bind_slots[ok_name] = slot
                binds[error_name] = (
                    call["error_value"]
                    if call["error_value"] is not None
                    else call["result"]
                )
                err_cond = error_condition_for_call(call_name)
                cont = builder.function.append_basic_block(
                    f"after_{call_name}_checked")
                record_label_defers(fail_label, active_defers)
                builder.cbranch(err_cond, get_block(fail_label), cont)
                builder.position_at_end(cont)
                continue

            if verb in ("start", "await"):
                if not args:
                    raise ValueError(f"line {_ln}: {verb} requires a call or wait-set name")
                if verb == "await":
                    await_cases, done_label, done_lineno, next_index = collect_await_cases(line_index)
                    if await_cases or done_label is not None:
                        if len(args) != 1:
                            raise ValueError(
                                f"line {_ln}: await wait set requires: await NAME")
                        emit_await_select(args[0], await_cases, done_label, done_lineno, _ln)
                        line_index = next_index
                        continue
                call_name = args[0]
                if verb == "start":
                    trace_call_event("call.start", call_name)
                    lowered_async = emit_async_native_binding_start(call_name)
                    if not lowered_async:
                        lowered_async = emit_async_fetch_start(call_name)
                    if not lowered_async:
                        lowered_async = emit_async_user_op_start(call_name)
                    trace_call_event("call.end", call_name)
                    if lowered_async:
                        continue
                    if is_async_fetch_target(calls[call_name]):
                        raise ValueError(
                            f"start: `{call_name}` targets "
                            f"{canonical_call_target(calls[call_name])} "
                            "but was not lowered to an async future")
                if verb == "await":
                    trace_call_event("call.await", call_name)
                    lowered_async = emit_async_native_binding_await(call_name)
                    if not lowered_async:
                        lowered_async = emit_async_fetch_await(call_name)
                    if not lowered_async:
                        lowered_async = emit_async_user_op_await(call_name)
                    trace_call_event("call.await.end", call_name)
                    if lowered_async:
                        continue
                # synchronous fallback for non-net targets at this
                # implementation level
                if verb == "await":
                    trace_call_event("call.start", call_name)
                    self._emit_run(builder, call_name, calls, resolve, opaque_inputs, SENTINEL)
                    trace_call_event("call.end", call_name)
                continue

            if verb in ("case", "done"):
                raise ValueError(
                    f"line {_ln}: `{verb}` must immediately follow an "
                    "`await NAME` wait-set row")

            if verb == "bind" and args[0] in ("value", "ok"):
                _variant, value_name, _type_name, call_name = args[0], args[1], args[2], args[3]
                if _type_name in prog.records and "record_result" in calls[call_name]:
                    record_values[value_name] = calls[call_name]["record_result"]
                    binds[value_name] = ir.Constant(Int64, 0)
                    continue
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

            if verb == "bind" and args[0] == "error":
                _variant, value_name, _type_name, call_name = args[0], args[1], args[2], args[3]
                call = calls[call_name]
                # Prefer the explicit error value if the call recorded one
                # (e.g. checked arithmetic exposes an overflow flag); otherwise
                # fall back to the call's primary result.
                binds[value_name] = call["error_value"] if call["error_value"] is not None else call["result"]
                continue

            if verb == "ignore":
                # ignore value|ok source CALL type TYPE
                # ignore error|void source CALL
                # The parser has already validated the role words. At lowering
                # time the row is an explicit disposition marker only.
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
            if verb == "work" and len(args) >= 3 and args[1] == "target":
                work_name, target_op = args[0], args[2]
                work_item = work_items.setdefault(work_name, {
                    "target": None,
                    "args": {},
                    "declared": False,
                })
                work_item["target"] = target_op
                work_item["declared"] = True
                continue
            if verb == "workArg" and len(args) >= 3:
                work_name, arg_name, value_name = args[0], args[1], args[2]
                work_items.setdefault(work_name, {
                    "target": None,
                    "args": {},
                    "declared": False,
                })
                work_items[work_name]["args"][arg_name] = value_name
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
                if work_def is None or not work_def.get("declared"):
                    raise ValueError(
                        f"line {_ln}: submitWork: work `{work_name}` is "
                        "not declared")
                pool_name = args[1] if len(args) >= 2 else ""
                if pool_name not in worker_pools:
                    raise ValueError(
                        f"line {_ln}: submitWork: worker pool `{pool_name}` "
                        "is not declared")
                target_op = work_def.get("target")
                if target_op not in self._user_ops:
                    raise ValueError(
                        f"line {_ln}: submitWork: work `{work_name}` target "
                        f"`{target_op}` is not a user operation")
                synth_call_name = f"_workSubmit__{work_name}"
                calls[synth_call_name] = make_call(
                    synth_call_name, target_op, _ln)
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
                binds[work_name] = ir.Constant(Int64, 0)
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
                        v = ir.Constant(Int64, 0)
                    if v is SENTINEL:
                        v = ir.Constant(Int64, 0)
                    if v.type != Int64:
                        if isinstance(v.type, ir.IntType):
                            if v.type.width < 64:
                                v = (builder.zext if v.type.width == 1
                                     else builder.sext)(v, Int64)
                            else:
                                v = builder.trunc(v, Int64)
                        elif isinstance(v.type, ir.PointerType):
                            v = builder.ptrtoint(v, Int64)
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
                    binds[out_name] = ir.Constant(Int64, 0)
                continue
            if verb == "receive" and len(args) >= 2:
                # Short-form `receive OUT CHANNEL` (rare): register OUT as
                # a zero bind so later references resolve.
                binds[args[0]] = ir.Constant(Int64, 0)
                continue
            if verb == "awaitWork" and len(args) >= 1:
                # `awaitWork WORK` — register WORK as zero bind.
                binds[args[0]] = ir.Constant(Int64, 0)
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
                binds[args[0]] = ir.Constant(Int64, 0)
                continue
            if verb == "new" and len(args) >= 1:
                value_name = args[0]
                record_type = args[1] if len(args) >= 2 else ""
                if record_type in prog.records:
                    allocate_record_slots(value_name, record_type)
                    binds[value_name] = ir.Constant(Int64, 0)
                else:
                    binds[value_name] = ir.Constant(Int64, 0)
                continue
            if verb == "fieldGet" and len(args) >= 1:
                out_name = args[0]
                out_type = args[1] if len(args) >= 2 else "Int64"
                record_name = args[2] if len(args) >= 3 else ""
                field_path = args[3] if len(args) >= 4 else ""
                record_value = record_values.get(record_name)
                if record_value is not None:
                    slot = record_value["slots"].get(field_path)
                    if slot is None:
                        raise ValueError(
                            f"fieldGet: `{record_name}` has no field `{field_path}`")
                    loaded = builder.load(slot, name=f"{out_name}_field")
                    target_llty = llvm_type_for(prog, out_type)
                    if target_llty is not None:
                        loaded = coerce_to_type(loaded, target_llty)
                    binds[out_name] = loaded
                    continue
                const_value = const_record_field(record_name, field_path)
                if const_value is not None:
                    target_llty = llvm_type_for(prog, out_type)
                    if target_llty is not None:
                        const_value = coerce_to_type(const_value, target_llty)
                    binds[out_name] = const_value
                    continue
                binds[out_name] = ir.Constant(Int64, 0)
                continue
            if verb == "fieldSet":
                if len(args) >= 3:
                    record_name, field_path, value_name = args[0], args[1], args[2]
                    record_value = record_values.get(record_name)
                    if record_value is not None:
                        slot = record_value["slots"].get(field_path)
                        if slot is None:
                            raise ValueError(
                                f"fieldSet: `{record_name}` has no field `{field_path}`")
                        value = resolve(value_name)
                        if value is SENTINEL:
                            raise ValueError("fieldSet: cannot store opaque input")
                        value = coerce_to_type(value, slot.type.pointee)
                        builder.store(value, slot)
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
                binds[name] = ir.Constant(Int32, idx)
                continue

            if verb == "branch" and args[0] == "error":
                _variant, _source_kw, call_name, _target_kw, fail_label = args
                err_cond = error_condition_for_call(call_name)
                else_label = branch_else_by_line.get(_ln)
                record_label_defers(fail_label, active_defers)
                self._emit_trace_event(
                    builder, "branch.decision", "branch", op.name,
                    call_name, fail_label if else_label is None else f"{fail_label}|{else_label}", _ln)
                if else_label is None:
                    cont = builder.function.append_basic_block(f"after_{call_name}")
                    builder.cbranch(err_cond, get_block(fail_label), cont)
                    builder.position_at_end(cont)
                else:
                    record_label_defers(else_label, active_defers)
                    builder.cbranch(err_cond, get_block(fail_label), get_block(else_label))
                    dead = builder.function.append_basic_block(f"after_branch_error_{call_name}")
                    builder.position_at_end(dead)
                    active_defers = []
                    current_block_reachable = False
                continue

            if verb == "branch" and args[0] == "if":
                _variant, _condition_kw, cond_name, _target_kw, t_label = args
                cond_val = resolve(cond_name)
                if cond_val.type != I1:
                    cond_val = builder.icmp_signed("!=", cond_val, ir.Constant(cond_val.type, 0))
                else_label = branch_else_by_line.get(_ln)
                record_label_defers(t_label, active_defers)
                self._emit_trace_event(
                    builder, "branch.decision", "branch", op.name,
                    cond_name, t_label if else_label is None else f"{t_label}|{else_label}", _ln)
                if else_label is None:
                    cont = builder.function.append_basic_block(f"after_branch_if_{cond_name}")
                    builder.cbranch(cond_val, get_block(t_label), cont)
                    builder.position_at_end(cont)
                else:
                    record_label_defers(else_label, active_defers)
                    builder.cbranch(cond_val, get_block(t_label), get_block(else_label))
                    dead = builder.function.append_basic_block(f"after_branch_if_{cond_name}")
                    builder.position_at_end(dead)
                    active_defers = []
                    current_block_reachable = False
                continue

            if verb == "branch" and args[0] == "else":
                # Attached else rows are consumed by the preceding branch. If
                # lowering reaches one directly, the source violated adjacency.
                if _ln in attached_branch_else_lines:
                    continue
                raise ValueError(
                    f"branch else: line {_ln}: must immediately follow branch if/error")

            if verb == "jump":
                _target_kw, target_label = args[0], args[1]
                record_label_defers(target_label, active_defers)
                self._emit_trace_event(
                    builder, "branch.decision", "branch", op.name,
                    "jump", target_label, _ln)
                builder.branch(get_block(target_label))
                dead = builder.function.append_basic_block(f"after_jump_{target_label}")
                builder.position_at_end(dead)
                active_defers = []
                current_block_reachable = False
                continue

            if verb == "return" and args[0] == "void":
                # `returnVoid` is the explicit "no caller-actionable value"
                # return form for operations declared `output OP Void` /
                # `output OP Void`. The user-op ABI still uses an i32 return
                # slot (see `_operation_output_contract` for the Void → Int32
                # mapping), so codegen emits a zero sentinel — but the source
                # says exactly what it means, instead of forcing a fake
                # `returnValue zeroSentinel` line that asks readers to
                # understand the ABI quirk on their own. Rejected on
                # non-Void outputs so the verb cannot become a backdoor
                # around the result-contract checker.
                output_contract = _operation_output_contract(self.prog, op)
                resolved_ok = resolve_alias(self.prog, output_contract.ok_type) \
                    if output_contract.ok_type else ""
                if resolved_ok not in ("Void", "Void"):
                    declared = output_contract.ok_type or "<missing output>"
                    raise ValueError(
                        f"return void: line {_ln}: operation `{op.name}` "
                        f"declares `output {op.name} {declared}` — use "
                        f"`return value NAME` for non-Void outputs. "
                        f"`return void` is only legal when output is `Void`."
                    )
                emit_defers("return void")
                self._emit_trace_event(
                    builder, "return.value", "return", op.name,
                    "return void", "", _ln,
                    value_name="", value_status="void")
                self._emit_trace_event(
                    builder, "op.exit", "operation", op.name, op.name,
                    "", op.decl_line)
                target_type = fn.function_type.return_type
                if isinstance(target_type, ir.IntType):
                    builder.ret(ir.Constant(target_type, 0))
                else:
                    # Defensive: the Void → i32 mapping is the documented
                    # lowering; if a future ABI change made Void return a
                    # different shape, this branch keeps codegen honest by
                    # zero-initialising whatever the new shape is.
                    builder.ret(ir.Constant(target_type, None))
                dead = builder.function.append_basic_block("after_return_void")
                builder.position_at_end(dead)
                continue

            if verb == "return" and args[0] in ("value", "ok", "error"):
                return_variant = args[0]
                emit_defers(f"return {return_variant}")
                value_name = args[1] if len(args) > 1 else ""
                self._emit_trace_event(
                    builder, "return.value", "return", op.name,
                    f"return {return_variant}", value_name, _ln,
                    value_name=value_name, value_status="redacted")
                self._emit_trace_event(
                    builder, "op.exit", "operation", op.name, op.name,
                    "", op.decl_line)
                val = resolve(value_name)
                if val is SENTINEL:
                    raise ValueError(f"return {return_variant}: cannot return opaque input")
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
                    # Float64 return slot, or vice versa).
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
                binds[args[0]] = ir.Constant(Int64, 0)
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
                if len(args) > 4 or args[2] not in op.consts:
                    op.consts[args[2]] = (
                        args[3], _unwrap(args[4]) if len(args) > 4 else 0)
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
                        binds[args[1]] = ir.Constant(Int64, 0)
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
            self._emit_trace_event(
                builder, "op.exit", "operation", op.name, op.name,
                "", op.decl_line)
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
                and source_target not in self.prog.operation_aliases
                and target not in HTTP_INTRINSIC_TARGETS
                and not source_target.startswith("sqlite.")):
            raise ValueError(
                f"{call_name}: qualified import target `{source_target}` is "
                "not an exported operation")

        # Lower domain-typed methods (`TypeName.methodName`) to the underlying
        # primitive based on the type alias's resolution chain. This keeps the
        # source-level call advertising domain context while reusing the
        # primitive dispatch below. Enum names also dispatch through here:
        # `SaveTodosStatus.equal` resolves the enum's repr type and picks the
        # matching width's primitive (Int32 → math.equalInt32,
        # Int64 → math.equalInt64), so callers compare enum values
        # without leaking the underlying integer width into source.
        if (target not in _BINOP_TO_LLVM and target not in _CMP_TO_LLVM
                and target not in _CMP_Int32_TO_LLVM
                and target not in _FBINOP_TO_LLVM and target not in _FCMP_TO_LLVM
                and target not in ("console.writeLine", "console.writeIntegerLine",
                                   "console.writeFloatLine")
                and not target.startswith("c.")
                and "." in target):
            type_part, method_part = target.split(".", 1)
            enum_repr = enum_repr_type(self.prog, type_part)
            if enum_repr is not None:
                # Enum dispatch — pick the primitive for the declared repr.
                if enum_repr == "Int64":
                    primitive = _DOMAIN_METHOD_TO_Int64_PRIMITIVE.get(method_part)
                else:
                    primitive = _DOMAIN_METHOD_TO_Int32_PRIMITIVE.get(method_part)
                if primitive is not None:
                    target = primitive
                    call["target"] = primitive
                    call["domain_method"] = method_part
            else:
                underlying = resolve_alias(self.prog, type_part)
                primitive = _DOMAIN_METHOD_TO_Int64_PRIMITIVE.get(method_part)
                if primitive is not None and underlying == "Int64":
                    target = primitive
                    call["target"] = primitive
                    call["domain_method"] = method_part
                elif method_part in _DOMAIN_METHOD_TO_Int32_PRIMITIVE and underlying == "Int32":
                    target = _DOMAIN_METHOD_TO_Int32_PRIMITIVE[method_part]
                    call["target"] = target
                    call["domain_method"] = method_part
                elif method_part in _DOMAIN_METHOD_TO_Float64_PRIMITIVE and underlying == "Float64":
                    target = _DOMAIN_METHOD_TO_Float64_PRIMITIVE[method_part]
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

        def coerce_declared_argument(arg_name, value):
            """Apply the explicit revised-syntax argument type when present."""
            declared = call.get("arg_types", {}).get(arg_name)
            if not declared:
                return value
            expected = llvm_type_for(self.prog, declared)
            if expected is None or value.type == expected:
                return value
            if isinstance(value.type, ir.IntType) and isinstance(expected, ir.IntType):
                if value.type.width < expected.width:
                    extend = builder.zext if value.type.width == 1 else builder.sext
                    return extend(value, expected, name=f"{call_name}_{arg_name}_as_{declared}")
                return builder.trunc(value, expected, name=f"{call_name}_{arg_name}_as_{declared}")
            if isinstance(value.type, ir.FloatType) and isinstance(expected, ir.DoubleType):
                return builder.fpext(value, expected, name=f"{call_name}_{arg_name}_as_{declared}")
            if isinstance(value.type, ir.DoubleType) and isinstance(expected, ir.FloatType):
                return builder.fptrunc(value, expected, name=f"{call_name}_{arg_name}_as_{declared}")
            return value

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
            return (
                coerce_declared_argument(usable[0][0], a),
                coerce_declared_argument(usable[1][0], b),
            )

        def operand_single():
            usable = [(k, v) for k, v in call["args"].items()
                      if v not in opaque_inputs]
            if len(usable) != 1:
                raise ValueError(
                    f"{call_name}: {target} unary domain method needs 1 operand arg; got {list(call['args'])}")
            value = resolve(usable[0][1])
            if value is SENTINEL:
                raise ValueError(f"{call_name}: opaque-input as operand for {target}")
            return coerce_declared_argument(usable[0][0], value)

        def coerce_i64_for_non_math_abi(v):
            if v.type == Int64:
                return v
            if isinstance(v.type, ir.IntType):
                return builder.sext(v, Int64) if v.type.width < 64 else builder.trunc(v, Int64)
            raise ValueError(f"{call_name}: cannot coerce {v.type} to i64")

        def require_exact_type(v, expected_type, expected_name: str, context: str):
            if v.type != expected_type:
                raise ValueError(
                    f"{call_name}: {context} expects {expected_name} exactly, got {v.type}; "
                    "insert an explicit conversion operation before this math call")
            return v

        def require_i64(v, context: str):
            return require_exact_type(v, Int64, "Int64", context)

        def require_i32(v, context: str):
            return require_exact_type(v, Int32, "Int32", context)

        def require_f64(v, context: str):
            return require_exact_type(v, Float64, "Float64", context)

        high_level_json_alias = False

        def mark_high_level_json_success():
            call["error_value"] = ir.Constant(Int32, 0)
            call["error_cond"] = ir.Constant(I1, 0)

        def mark_high_level_json_status(status, error_code=1):
            call["error_value"] = ir.Constant(Int32, error_code)
            call["error_cond"] = builder.icmp_signed(
                "!=", status, ir.Constant(Int32, 0),
                name=f"{call_name}_isJsonError")

        def target_type_is_json_text(name: str) -> bool:
            seen = set()
            current = name
            while True:
                if current == "JsonText":
                    return True
                if current in seen or current not in self.prog.type_aliases:
                    return False
                seen.add(current)
                alias_target = self.prog.type_aliases[current]
                current = alias_target[0] if isinstance(alias_target, list) else alias_target

        record_values = getattr(self, "_current_record_values", {})

        def high_json_as_i8p(value):
            if value.type == Int8P:
                return value
            if isinstance(value.type, ir.PointerType):
                return builder.bitcast(value, Int8P)
            if isinstance(value.type, ir.IntType):
                return builder.inttoptr(value, Int8P)
            raise ValueError(f"{call_name}: {target} expected pointer-shaped JSON text")

        def high_json_i64(value):
            if isinstance(value.type, ir.IntType):
                if value.type.width < 64:
                    return builder.sext(value, Int64)
                if value.type.width > 64:
                    return builder.trunc(value, Int64)
                return value
            if isinstance(value.type, ir.PointerType):
                return builder.ptrtoint(value, Int64)
            raise ValueError(f"{call_name}: {target} expected integer-shaped value")

        def high_json_i32(value):
            if isinstance(value.type, ir.IntType):
                if value.type.width < 32:
                    return (builder.zext if value.type.width == 1 else builder.sext)(value, Int32)
                if value.type.width > 32:
                    return builder.trunc(value, Int32)
                return value
            raise ValueError(f"{call_name}: {target} expected i32-shaped value")

        def high_json_f64(value):
            if value.type == Float64:
                return value
            if isinstance(value.type, ir.FloatType):
                return builder.fpext(value, Float64)
            if isinstance(value.type, ir.IntType):
                return builder.sitofp(value, Float64)
            raise ValueError(f"{call_name}: {target} expected numeric value")

        def high_json_coerce_to(value, target_type):
            if value.type == target_type:
                return value
            if isinstance(value.type, ir.IntType) and isinstance(target_type, ir.IntType):
                if value.type.width < target_type.width:
                    return (builder.zext if value.type.width == 1 else builder.sext)(
                        value, target_type)
                if value.type.width > target_type.width:
                    return builder.trunc(value, target_type)
            if isinstance(value.type, ir.IntType) and isinstance(target_type, ir.PointerType):
                return builder.inttoptr(value, target_type)
            if isinstance(value.type, ir.PointerType) and isinstance(target_type, ir.IntType):
                return builder.ptrtoint(value, target_type)
            if isinstance(value.type, ir.PointerType) and isinstance(target_type, ir.PointerType):
                return builder.bitcast(value, target_type)
            if isinstance(value.type, ir.IntType) and isinstance(target_type, (ir.FloatType, ir.DoubleType)):
                return builder.sitofp(value, target_type)
            if isinstance(value.type, ir.FloatType) and isinstance(target_type, ir.DoubleType):
                return builder.fpext(value, target_type)
            if isinstance(value.type, ir.DoubleType) and isinstance(target_type, ir.FloatType):
                return builder.fptrunc(value, target_type)
            if isinstance(value.type, (ir.FloatType, ir.DoubleType)) and isinstance(target_type, ir.IntType):
                return builder.fptosi(value, target_type)
            return value

        def high_json_const_value(field_type, raw):
            llty = llvm_type_for(self.prog, field_type)
            resolved = resolve_alias(self.prog, field_type)
            if llty == Int8P:
                if raw is None:
                    return ir.Constant(Int8P, None)
                return self._i8p(builder, "" if raw is None else str(raw))
            if llty == I1:
                return ir.Constant(I1, 1 if raw is True or raw == 1 else 0)
            if isinstance(llty, ir.IntType):
                try:
                    return ir.Constant(llty, int(raw or 0))
                except (TypeError, ValueError):
                    return ir.Constant(llty, 0)
            if isinstance(llty, (ir.FloatType, ir.DoubleType)):
                try:
                    return ir.Constant(llty, float(raw or 0.0))
                except (TypeError, ValueError):
                    return ir.Constant(llty, 0.0)
            if resolved in self.prog.records:
                return ir.Constant(Int64, 0)
            raise ValueError(f"{call_name}: unsupported record field type `{field_type}`")

        def high_json_nested_field(fields, field_path):
            current = fields
            for part in field_path.split("."):
                if not isinstance(current, dict) or part not in current:
                    return None
                current = current[part]
            return current

        def high_json_record_source(record_symbol, record_type):
            source = record_values.get(record_symbol)
            if source is not None:
                return source
            record_const = self.prog.record_json_constants.get(record_symbol)
            if record_const is not None:
                return {
                    "type": record_const["recordType"],
                    "const_fields": record_const["fields"],
                }
            return None

        def high_json_record_field_value(source, field_path, field_type):
            slots = source.get("slots")
            if slots is not None and field_path in slots:
                return builder.load(
                    slots[field_path],
                    name=f"{call_name}_{field_path.replace('.', '_')}")
            return high_json_const_value(
                field_type,
                high_json_nested_field(source.get("const_fields", {}), field_path))

        def high_json_record_leaf_fields(record_type, prefix=""):
            record = self.prog.records.get(record_type)
            if record is None:
                return
            for field_name, field_type in record.fields:
                path = f"{prefix}.{field_name}" if prefix else field_name
                nested = _record_type_for_json_body(self.prog, field_type)
                if nested is not None:
                    yield from high_json_record_leaf_fields(nested, path)
                else:
                    yield path, field_type

        def high_json_record_leaf_policy(record_type, field_path):
            current_type = record_type
            parts = field_path.split(".")
            for index, part in enumerate(parts):
                record = self.prog.records.get(current_type)
                if record is None:
                    return None
                match = None
                for field_name, field_type in record.fields:
                    if field_name == part:
                        match = (field_name, field_type)
                        break
                if match is None:
                    return None
                field_name, field_type = match
                if index == len(parts) - 1:
                    return record.field_json_omit_when.get(field_name)
                nested = _record_type_for_json_body(self.prog, field_type)
                if nested is None:
                    return None
                current_type = nested

        def high_json_global_buffer(byte_count, stem):
            array_ty = ir.ArrayType(Int8, byte_count)
            safe_stem = re.sub(r"[^A-Za-z0-9_]", "_", stem)
            name = f"as.json.{self._next_json_buffer_id}.{safe_stem}"
            self._next_json_buffer_id += 1
            gv = ir.GlobalVariable(self.module, array_ty, name=name)
            gv.linkage = "internal"
            gv.global_constant = False
            gv.initializer = ir.Constant(array_ty, bytearray(byte_count))
            return builder.gep(
                gv, [ir.Constant(Int32, 0), ir.Constant(Int32, 0)],
                inbounds=True)

        def high_json_record_slots(record_type, value_name):
            slots = {}
            field_types = {}
            for field_path, field_type in high_json_record_leaf_fields(record_type):
                llty = llvm_type_for(self.prog, field_type)
                if llty is None:
                    continue
                with builder.goto_entry_block():
                    slot = builder.alloca(
                        llty,
                        name=f"{call_name}_{value_name}_{field_path.replace('.', '_')}")
                policy = high_json_record_leaf_policy(record_type, field_path)
                raw_default = _json_record_default_for_policy(
                    self.prog, field_type, policy) if policy else None
                builder.store(high_json_const_value(field_type, raw_default), slot)
                slots[field_path] = slot
                field_types[field_path] = field_type
            return {"type": record_type, "slots": slots, "field_types": field_types}

        def high_json_status_slot(name_suffix="status"):
            with builder.goto_entry_block():
                slot = builder.alloca(Int32, name=f"{call_name}_{name_suffix}")
                builder.store(ir.Constant(Int32, 0), slot)
            return slot

        def high_json_out_slot(slot_type, name_suffix):
            with builder.goto_entry_block():
                slot = builder.alloca(slot_type, name=f"{call_name}_{name_suffix}")
                if isinstance(slot_type, ir.PointerType):
                    builder.store(ir.Constant(slot_type, None), slot)
                elif isinstance(slot_type, (ir.FloatType, ir.DoubleType)):
                    builder.store(ir.Constant(slot_type, 0.0), slot)
                else:
                    builder.store(ir.Constant(slot_type, 0), slot)
            return slot

        def high_json_merge_status(status_slot, new_status):
            if new_status.type != Int32:
                new_status = high_json_i32(new_status)
            current = builder.load(status_slot, name=f"{call_name}_statusCurrent")
            current_is_error = builder.icmp_signed(
                "!=", current, ir.Constant(Int32, 0),
                name=f"{call_name}_statusAlreadyError")
            merged = builder.select(current_is_error, current, new_status,
                                    name=f"{call_name}_statusMerged")
            builder.store(merged, status_slot)

        def high_json_encode_error_status(native_status):
            status = high_json_i32(native_status)
            is_ok = builder.icmp_signed(
                "==", status, ir.Constant(Int32, 0),
                name=f"{call_name}_encodeStatusOk")
            is_wrong_type = builder.icmp_signed(
                "==", status, ir.Constant(Int32, 2),
                name=f"{call_name}_encodeStatusWrongType")
            is_output_too_small = builder.icmp_signed(
                "==", status, ir.Constant(Int32, 8),
                name=f"{call_name}_encodeStatusOutputSmall")
            mapped_nonzero = builder.select(
                is_wrong_type, ir.Constant(Int32, 2), ir.Constant(Int32, 1),
                name=f"{call_name}_encodeStatusWrongMapped")
            mapped_nonzero = builder.select(
                is_output_too_small, ir.Constant(Int32, 3), mapped_nonzero,
                name=f"{call_name}_encodeStatusSmallMapped")
            return builder.select(
                is_ok, ir.Constant(Int32, 0), mapped_nonzero,
                name=f"{call_name}_encodeStatusMapped")

        def high_json_decode_error_status(native_status):
            status = high_json_i32(native_status)
            is_ok = builder.icmp_signed(
                "==", status, ir.Constant(Int32, 0),
                name=f"{call_name}_decodeStatusOk")
            is_missing = builder.icmp_signed(
                "==", status, ir.Constant(Int32, 1),
                name=f"{call_name}_decodeStatusMissing")
            is_wrong_type = builder.icmp_signed(
                "==", status, ir.Constant(Int32, 2),
                name=f"{call_name}_decodeStatusWrongType")
            is_oversize = builder.icmp_signed(
                "==", status, ir.Constant(Int32, 6),
                name=f"{call_name}_decodeStatusOversize")
            is_truncated = builder.icmp_signed(
                "==", status, ir.Constant(Int32, 8),
                name=f"{call_name}_decodeStatusTruncated")
            mapped_nonzero = builder.select(
                is_missing, ir.Constant(Int32, 2), ir.Constant(Int32, 1),
                name=f"{call_name}_decodeStatusMissingMapped")
            mapped_nonzero = builder.select(
                is_wrong_type, ir.Constant(Int32, 3), mapped_nonzero,
                name=f"{call_name}_decodeStatusWrongMapped")
            mapped_nonzero = builder.select(
                is_oversize, ir.Constant(Int32, 4), mapped_nonzero,
                name=f"{call_name}_decodeStatusOversizeMapped")
            mapped_nonzero = builder.select(
                is_truncated, ir.Constant(Int32, 5), mapped_nonzero,
                name=f"{call_name}_decodeStatusTruncatedMapped")
            return builder.select(
                is_ok, ir.Constant(Int32, 0), mapped_nonzero,
                name=f"{call_name}_decodeStatusMapped")

        def high_json_emit_json_text_passthrough(is_stringify):
            source_arg = "value" if is_stringify else "jsonText"
            if source_arg not in call["args"]:
                for fallback_arg in ("jsonText", "text", "value"):
                    if fallback_arg in call["args"]:
                        source_arg = fallback_arg
                        break
            json_text = high_json_as_i8p(arg_val_named(source_arg))
            if is_stringify:
                status_slot = high_json_status_slot()
                out_slot = high_json_out_slot(Int8P, "jsonTextSlot")
                scratch_capacity = 65536
                scratch = high_json_global_buffer(
                    scratch_capacity, f"{call_name}_jsonText")
                strlen_fn = self._libc_func("strlen")
                memcpy_fn = self._libc_func("memcpy")
                text_len = builder.call(
                    strlen_fn, [json_text], name=f"{call_name}_jsonTextLength")
                too_large = builder.icmp_unsigned(
                    ">=", text_len, ir.Constant(Int64, scratch_capacity),
                    name=f"{call_name}_jsonTextTooLarge")
                status = builder.select(
                    too_large, ir.Constant(Int32, 3), ir.Constant(Int32, 0),
                    name=f"{call_name}_jsonTextStatus")
                builder.store(status, status_slot)
                copy_block = builder.function.append_basic_block(
                    f"{call_name}_jsonText_copy")
                after_block = builder.function.append_basic_block(
                    f"{call_name}_jsonText_after")
                builder.cbranch(too_large, after_block, copy_block)
                builder.position_at_end(copy_block)
                byte_count = builder.add(
                    text_len, ir.Constant(Int64, 1),
                    name=f"{call_name}_jsonTextBytesWithNul")
                builder.call(memcpy_fn, [scratch, json_text, byte_count])
                builder.store(scratch, out_slot)
                builder.branch(after_block)
                builder.position_at_end(after_block)
                call["result"] = builder.load(
                    out_slot, name=f"{call_name}_jsonText")
                call["error_value"] = builder.load(
                    status_slot, name=f"{call_name}_finalStatus")
                call["error_cond"] = builder.icmp_signed(
                    "!=", call["error_value"], ir.Constant(Int32, 0),
                    name=f"{call_name}_isError")
                return

            doc_slot = high_json_out_slot(Int8P, "documentSlot")
            create_fn = self._runtime_func(
                "ss_json_document_create_from_text",
                Int32, [Int8P, Int64, Int8P.as_pointer()])
            self.provenance.record_external(
                "ss_json_document_create_from_text", call)
            create_status = builder.call(
                create_fn,
                [json_text, ir.Constant(Int64, 65536), doc_slot],
                name=f"{call_name}_createStatus")
            document = builder.load(doc_slot, name=f"{call_name}_document")
            destroy_fn = self._runtime_func("ss_json_document_destroy", VOID, [Int8P])
            self.provenance.record_external("ss_json_document_destroy", call)
            builder.call(destroy_fn, [document])
            failed = builder.icmp_signed(
                "!=", create_status, ir.Constant(Int32, 0),
                name=f"{call_name}_parseFailed")
            call["result"] = json_text
            call["error_value"] = builder.select(
                failed, ir.Constant(Int32, 1), ir.Constant(Int32, 0),
                name=f"{call_name}_decodeStatus")
            call["error_cond"] = failed

        def high_json_emit_record_stringify(record_type):
            record_symbol = call["args"].get("value") or call["args"].get("record")
            if record_symbol is None:
                raise ValueError(f"{call_name}: {target} requires arg `value`")
            source = high_json_record_source(record_symbol, record_type)
            if source is None:
                raise ValueError(
                    f"{call_name}: `{record_symbol}` is not a materialized "
                    f"record value of type `{record_type}`")
            status_slot = high_json_status_slot()
            doc_slot = high_json_out_slot(Int8P, "documentSlot")
            with builder.goto_entry_block():
                out_slot = builder.alloca(Int8P, name=f"{call_name}_jsonTextSlot")
                builder.store(ir.Constant(Int8P, None), out_slot)
            create_fn = self._runtime_func(
                "ss_json_document_create_empty",
                Int32, [Int64, Int32, Int8P.as_pointer()])
            self.provenance.record_external("ss_json_document_create_empty", call)
            create_status = builder.call(
                create_fn,
                [ir.Constant(Int64, 65536), ir.Constant(Int32, 0), doc_slot],
                name=f"{call_name}_createStatus")
            high_json_merge_status(
                status_slot, high_json_encode_error_status(create_status))
            document = builder.load(doc_slot, name=f"{call_name}_document")
            root_fn = self._runtime_func("ss_json_document_root", Int64, [Int8P])
            self.provenance.record_external("ss_json_document_root", call)
            root_cursor = builder.call(root_fn, [document], name=f"{call_name}_root")

            def emit_set_scalar(cursor_value, json_key, field_type, value):
                resolved = resolve_alias(self.prog, field_type)
                if resolved == "String":
                    symbol = "ss_json_set_object_field_string"
                    fn = self._runtime_func(symbol, Int32, [Int8P, Int64, Int8P, Int8P])
                    args_for_call = [document, cursor_value, self._i8p(builder, json_key),
                                     high_json_as_i8p(value)]
                elif resolved == "JsonText":
                    symbol = "ss_json_set_object_field_json_text"
                    cursor_slot = high_json_out_slot(Int64, "jsonTextCursor")
                    fn = self._runtime_func(symbol, Int32, [Int8P, Int64, Int8P, Int8P, Int64.as_pointer()])
                    args_for_call = [document, cursor_value, self._i8p(builder, json_key),
                                     high_json_as_i8p(value), cursor_slot]
                elif resolved == "Bool":
                    symbol = "ss_json_set_object_field_bool"
                    fn = self._runtime_func(symbol, Int32, [Int8P, Int64, Int8P, Int32])
                    args_for_call = [document, cursor_value, self._i8p(builder, json_key),
                                     high_json_i32(value)]
                elif resolved in (
                    "Float16", "Float32", "Float64",
                    "Float64", "Float64", "Float64",
                    "Float32", "Float32", "Float32",
                ):
                    symbol = "ss_json_set_object_field_double"
                    fn = self._runtime_func(symbol, Int32, [Int8P, Int64, Int8P, Float64])
                    args_for_call = [document, cursor_value, self._i8p(builder, json_key),
                                     high_json_f64(value)]
                else:
                    symbol = "ss_json_set_object_field_int64"
                    fn = self._runtime_func(symbol, Int32, [Int8P, Int64, Int8P, Int64])
                    args_for_call = [document, cursor_value, self._i8p(builder, json_key),
                                     high_json_i64(value)]
                self.provenance.record_external(symbol, call)
                status = builder.call(fn, args_for_call, name=f"{call_name}_{json_key}_status")
                high_json_merge_status(
                    status_slot, high_json_encode_error_status(status))

            def emit_record_fields(record_type_name, source_value, cursor_value, prefix=""):
                record = self.prog.records[record_type_name]
                for field_name, field_type in record.fields:
                    json_key = _json_record_key(record, field_name)
                    path = f"{prefix}.{field_name}" if prefix else field_name
                    nested_type = _record_type_for_json_body(self.prog, field_type)
                    if nested_type is not None:
                        cursor_slot = high_json_out_slot(Int64, f"{field_name}Cursor")
                        symbol = "ss_json_set_object_field_object"
                        fn = self._runtime_func(
                            symbol, Int32, [Int8P, Int64, Int8P, Int64.as_pointer()])
                        self.provenance.record_external(symbol, call)
                        status = builder.call(
                            fn,
                            [document, cursor_value, self._i8p(builder, json_key), cursor_slot],
                            name=f"{call_name}_{json_key}_objectStatus")
                        high_json_merge_status(
                            status_slot, high_json_encode_error_status(status))
                        child_cursor = builder.load(
                            cursor_slot, name=f"{call_name}_{json_key}_cursor")
                        emit_record_fields(nested_type, source_value, child_cursor, path)
                        continue
                    value = high_json_record_field_value(source_value, path, field_type)
                    policy = record.field_json_omit_when.get(field_name)
                    omit_cond = None
                    resolved = resolve_alias(self.prog, field_type)
                    if policy == "empty" and isinstance(value.type, ir.PointerType):
                        first = builder.load(value, name=f"{call_name}_{json_key}_first")
                        omit_cond = builder.icmp_signed(
                            "==", first, ir.Constant(Int8, 0),
                            name=f"{call_name}_{json_key}_empty")
                    elif policy == "null" and isinstance(value.type, ir.PointerType):
                        omit_cond = builder.icmp_unsigned(
                            "==", value, ir.Constant(value.type, None),
                            name=f"{call_name}_{json_key}_null")
                    elif policy == "false":
                        bool_value = high_json_i32(value)
                        omit_cond = builder.icmp_signed(
                            "==", bool_value, ir.Constant(Int32, 0),
                            name=f"{call_name}_{json_key}_false")
                    elif policy == "zero":
                        if isinstance(value.type, (ir.FloatType, ir.DoubleType)):
                            omit_cond = builder.fcmp_ordered(
                                "==", high_json_f64(value), ir.Constant(Float64, 0.0),
                                name=f"{call_name}_{json_key}_zero")
                        else:
                            int_value = high_json_i64(value)
                            omit_cond = builder.icmp_signed(
                                "==", int_value, ir.Constant(Int64, 0),
                                name=f"{call_name}_{json_key}_zero")
                    if omit_cond is None:
                        emit_set_scalar(cursor_value, json_key, field_type, value)
                    else:
                        set_block = builder.function.append_basic_block(
                            f"{call_name}_{json_key}_set")
                        after_block = builder.function.append_basic_block(
                            f"{call_name}_{json_key}_after")
                        builder.cbranch(omit_cond, after_block, set_block)
                        builder.position_at_end(set_block)
                        emit_set_scalar(cursor_value, json_key, field_type, value)
                        builder.branch(after_block)
                        builder.position_at_end(after_block)

            emit_record_fields(record_type, source, root_cursor)
            scratch = high_json_global_buffer(65536, f"{call_name}_stringify")
            serialize_fn = self._runtime_func(
                "ss_json_document_serialize",
                Int32, [Int8P, Int8P, Int64, Int8P.as_pointer()])
            self.provenance.record_external("ss_json_document_serialize", call)
            serialize_status = builder.call(
                serialize_fn,
                [document, scratch, ir.Constant(Int64, 65536), out_slot],
                name=f"{call_name}_serializeStatus")
            high_json_merge_status(
                status_slot, high_json_encode_error_status(serialize_status))
            destroy_fn = self._runtime_func("ss_json_document_destroy", VOID, [Int8P])
            self.provenance.record_external("ss_json_document_destroy", call)
            builder.call(destroy_fn, [document])
            call["result"] = builder.load(out_slot, name=f"{call_name}_jsonText")
            call["error_value"] = builder.load(status_slot, name=f"{call_name}_finalStatus")
            call["error_cond"] = builder.icmp_signed(
                "!=", call["error_value"], ir.Constant(Int32, 0),
                name=f"{call_name}_isError")

        def high_json_emit_record_parse(record_type):
            source_arg = "jsonText"
            if source_arg not in call["args"]:
                for fallback_arg in ("text", "value"):
                    if fallback_arg in call["args"]:
                        source_arg = fallback_arg
                        break
            json_text = high_json_as_i8p(arg_val_named(source_arg))
            status_slot = high_json_status_slot()
            doc_slot = high_json_out_slot(Int8P, "documentSlot")
            create_fn = self._runtime_func(
                "ss_json_document_create_from_text",
                Int32, [Int8P, Int64, Int8P.as_pointer()])
            self.provenance.record_external("ss_json_document_create_from_text", call)
            create_status = builder.call(
                create_fn,
                [json_text, ir.Constant(Int64, 65536), doc_slot],
                name=f"{call_name}_createStatus")
            high_json_merge_status(
                status_slot, high_json_decode_error_status(create_status))
            document = builder.load(doc_slot, name=f"{call_name}_document")
            root_fn = self._runtime_func("ss_json_document_root", Int64, [Int8P])
            self.provenance.record_external("ss_json_document_root", call)
            root_cursor = builder.call(root_fn, [document], name=f"{call_name}_root")
            record_result = high_json_record_slots(record_type, "parsed")
            wrong_type_status = ir.Constant(Int32, 3)

            def store_if_status_ok(status, slot, value, block_suffix):
                ok = builder.icmp_signed(
                    "==", status, ir.Constant(Int32, 0),
                    name=f"{call_name}_{block_suffix}_statusOk")
                store_block = builder.function.append_basic_block(
                    f"{call_name}_{block_suffix}_store")
                after_block = builder.function.append_basic_block(
                    f"{call_name}_{block_suffix}_afterStore")
                builder.cbranch(ok, store_block, after_block)
                builder.position_at_end(store_block)
                builder.store(value, slot)
                builder.branch(after_block)
                builder.position_at_end(after_block)

            def expected_kind_cond(kind, field_type, nested_type):
                if nested_type is not None:
                    return builder.icmp_signed(
                        "==", kind, ir.Constant(Int32, 0),
                        name=f"{call_name}_kindIsObject")
                resolved = resolve_alias(self.prog, field_type)
                if resolved in {"String", "JsonText"}:
                    return builder.icmp_signed(
                        "==", kind, ir.Constant(Int32, 2),
                        name=f"{call_name}_kindIsString")
                if resolved == "Bool":
                    return builder.icmp_signed(
                        "==", kind, ir.Constant(Int32, 5),
                        name=f"{call_name}_kindIsBool")
                if resolved in (
                    "Float16", "Float32", "Float64",
                    "Float64", "Float64", "Float64",
                    "Float32", "Float32", "Float32",
                ):
                    is_double = builder.icmp_signed(
                        "==", kind, ir.Constant(Int32, 4),
                        name=f"{call_name}_kindIsDouble")
                    is_integer = builder.icmp_signed(
                        "==", kind, ir.Constant(Int32, 3),
                        name=f"{call_name}_kindIsNumericInteger")
                    return builder.or_(is_double, is_integer, name=f"{call_name}_kindIsNumber")
                return builder.icmp_signed(
                    "==", kind, ir.Constant(Int32, 3),
                    name=f"{call_name}_kindIsInteger")

            def emit_present_field_read(nav_status, policy, field_type, nested_type,
                                        read_body, block_suffix):
                present = builder.icmp_signed(
                    "==", nav_status, ir.Constant(Int32, 0),
                    name=f"{call_name}_{block_suffix}_present")
                present_block = builder.function.append_basic_block(
                    f"{call_name}_{block_suffix}_present")
                after_block = builder.function.append_basic_block(
                    f"{call_name}_{block_suffix}_after")
                builder.cbranch(present, present_block, after_block)
                builder.position_at_end(present_block)
                kind_fn = self._runtime_func(
                    "ss_json_cursor_kind", Int32, [Int8P, Int64])
                self.provenance.record_external("ss_json_cursor_kind", call)
                kind = builder.call(
                    kind_fn, [document, builder.load(current_field_cursor_slot[0])],
                    name=f"{call_name}_{block_suffix}_kind")
                if policy == "null":
                    is_null = builder.icmp_signed(
                        "==", kind, ir.Constant(Int32, 6),
                        name=f"{call_name}_{block_suffix}_isNull")
                    non_null_block = builder.function.append_basic_block(
                        f"{call_name}_{block_suffix}_nonnull")
                    builder.cbranch(is_null, after_block, non_null_block)
                    builder.position_at_end(non_null_block)
                kind_ok = expected_kind_cond(kind, field_type, nested_type)
                read_block = builder.function.append_basic_block(
                    f"{call_name}_{block_suffix}_read")
                wrong_block = builder.function.append_basic_block(
                    f"{call_name}_{block_suffix}_wrongType")
                builder.cbranch(kind_ok, read_block, wrong_block)
                builder.position_at_end(wrong_block)
                high_json_merge_status(status_slot, wrong_type_status)
                builder.branch(after_block)
                builder.position_at_end(read_block)
                read_body()
                builder.branch(after_block)
                builder.position_at_end(after_block)

            def emit_read_field(cursor_value, record_type_name, prefix=""):
                record = self.prog.records[record_type_name]
                for field_name, field_type in record.fields:
                    json_key = _json_record_key(record, field_name)
                    path = f"{prefix}.{field_name}" if prefix else field_name
                    field_cursor_slot = high_json_out_slot(Int64, f"{json_key}Cursor")
                    nav_fn = self._runtime_func(
                        "ss_json_navigate_object_field",
                        Int32, [Int8P, Int64, Int8P, Int64.as_pointer()])
                    self.provenance.record_external("ss_json_navigate_object_field", call)
                    nav_status = builder.call(
                        nav_fn,
                        [document, cursor_value, self._i8p(builder, json_key),
                         field_cursor_slot],
                        name=f"{call_name}_{json_key}_navStatus")
                    policy = record.field_json_omit_when.get(field_name)
                    if policy:
                        is_missing = builder.icmp_signed(
                            "==", nav_status, ir.Constant(Int32, 1),
                            name=f"{call_name}_{json_key}_missing")
                        effective_status = builder.select(
                            is_missing, ir.Constant(Int32, 0),
                            high_json_decode_error_status(nav_status),
                            name=f"{call_name}_{json_key}_effectiveStatus")
                    else:
                        effective_status = high_json_decode_error_status(nav_status)
                    high_json_merge_status(status_slot, effective_status)
                    field_cursor = builder.load(
                        field_cursor_slot, name=f"{call_name}_{json_key}_cursor")
                    nested_type = _record_type_for_json_body(self.prog, field_type)
                    if nested_type is not None:
                        current_field_cursor_slot[0] = field_cursor_slot
                        emit_present_field_read(
                            nav_status, policy, field_type, nested_type,
                            lambda nested_type=nested_type, field_cursor=field_cursor,
                                   path=path: emit_read_field(field_cursor, nested_type, path),
                            re.sub(r"[^A-Za-z0-9_]", "_", path))
                        continue
                    slot = record_result["slots"].get(path)
                    if slot is None:
                        continue
                    resolved = resolve_alias(self.prog, field_type)
                    if resolved in {"String", "JsonText"}:
                        def read_string(slot=slot, field_cursor=field_cursor,
                                        json_key=json_key, path=path):
                            scratch = high_json_global_buffer(
                                4096, f"{call_name}_{json_key}_scratch")
                            out_slot = high_json_out_slot(Int8P, f"{json_key}String")
                            read_fn = self._runtime_func(
                                "ss_json_cursor_string",
                                Int32, [Int8P, Int64, Int8P, Int64, Int8P.as_pointer()])
                            self.provenance.record_external("ss_json_cursor_string", call)
                            read_status = builder.call(
                                read_fn,
                                [document, field_cursor, scratch, ir.Constant(Int64, 4096),
                                 out_slot],
                                name=f"{call_name}_{json_key}_readStatus")
                            mapped_read_status = high_json_decode_error_status(read_status)
                            high_json_merge_status(status_slot, mapped_read_status)
                            store_if_status_ok(
                                read_status, slot, builder.load(out_slot),
                                re.sub(r"[^A-Za-z0-9_]", "_", path))
                        current_field_cursor_slot[0] = field_cursor_slot
                        emit_present_field_read(
                            nav_status, policy, field_type, nested_type,
                            read_string, re.sub(r"[^A-Za-z0-9_]", "_", path))
                    elif resolved == "Bool":
                        def read_bool(slot=slot, field_cursor=field_cursor,
                                      json_key=json_key):
                            read_fn = self._runtime_func(
                                "ss_json_cursor_bool", Int32, [Int8P, Int64, Int32])
                            self.provenance.record_external("ss_json_cursor_bool", call)
                            value = builder.call(
                                read_fn, [document, field_cursor, ir.Constant(Int32, 0)],
                                name=f"{call_name}_{json_key}_bool")
                            builder.store(high_json_coerce_to(value, slot.type.pointee), slot)
                        current_field_cursor_slot[0] = field_cursor_slot
                        emit_present_field_read(
                            nav_status, policy, field_type, nested_type,
                            read_bool, re.sub(r"[^A-Za-z0-9_]", "_", path))
                    elif resolved in (
                        "Float16", "Float32", "Float64",
                        "Float64", "Float64", "Float64",
                        "Float32", "Float32", "Float32",
                    ):
                        def read_double(slot=slot, field_cursor=field_cursor,
                                        json_key=json_key):
                            read_fn = self._runtime_func(
                                "ss_json_cursor_double", Float64, [Int8P, Int64, Float64])
                            self.provenance.record_external("ss_json_cursor_double", call)
                            value = builder.call(
                                read_fn, [document, field_cursor, ir.Constant(Float64, 0.0)],
                                name=f"{call_name}_{json_key}_double")
                            builder.store(
                                high_json_coerce_to(high_json_f64(value), slot.type.pointee),
                                slot)
                        current_field_cursor_slot[0] = field_cursor_slot
                        emit_present_field_read(
                            nav_status, policy, field_type, nested_type,
                            read_double, re.sub(r"[^A-Za-z0-9_]", "_", path))
                    else:
                        def read_int(slot=slot, field_cursor=field_cursor,
                                     json_key=json_key):
                            read_fn = self._runtime_func(
                                "ss_json_cursor_int64", Int64, [Int8P, Int64, Int64])
                            self.provenance.record_external("ss_json_cursor_int64", call)
                            value = builder.call(
                                read_fn, [document, field_cursor, ir.Constant(Int64, 0)],
                                name=f"{call_name}_{json_key}_int64")
                            builder.store(
                                high_json_coerce_to(high_json_i64(value), slot.type.pointee),
                                slot)
                        current_field_cursor_slot[0] = field_cursor_slot
                        emit_present_field_read(
                            nav_status, policy, field_type, nested_type,
                            read_int, re.sub(r"[^A-Za-z0-9_]", "_", path))

            current_field_cursor_slot = [None]
            emit_read_field(root_cursor, record_type)
            destroy_fn = self._runtime_func("ss_json_document_destroy", VOID, [Int8P])
            self.provenance.record_external("ss_json_document_destroy", call)
            builder.call(destroy_fn, [document])
            call["record_result"] = record_result
            call["result"] = ir.Constant(Int64, 0)
            call["error_value"] = builder.load(status_slot, name=f"{call_name}_finalStatus")
            call["error_cond"] = builder.icmp_signed(
                "!=", call["error_value"], ir.Constant(Int32, 0),
                name=f"{call_name}_isError")

        if target.startswith("json.stringify.") or target.startswith("json.parse."):
            is_stringify = target.startswith("json.stringify.")
            prefix = "json.stringify." if is_stringify else "json.parse."
            type_name = target[len(prefix):]
            primitive_targets = (
                _JSON_STRINGIFY_PRIMITIVE_TARGETS
                if is_stringify
                else _JSON_PARSE_PRIMITIVE_TARGETS
            )
            resolved_type = resolve_alias(self.prog, type_name)
            primitive_target = (
                primitive_targets.get(type_name)
                or primitive_targets.get(resolved_type)
            )
            if target_type_is_json_text(type_name):
                high_json_emit_json_text_passthrough(is_stringify)
                return
            if primitive_target is None:
                record_type = type_name if type_name in self.prog.records else resolved_type
                if record_type in self.prog.records:
                    if is_stringify:
                        high_json_emit_record_stringify(record_type)
                    else:
                        high_json_emit_record_parse(record_type)
                    return
                raise ValueError(
                    f"{call_name}: unsupported high-level JSON target "
                    f"`{target}`; primitive aliases currently cover "
                    f"{sorted(primitive_targets)}")
            if not is_stringify and "value" not in call["args"]:
                for json_text_arg in ("jsonText", "text"):
                    if json_text_arg in call["args"]:
                        call["args"]["value"] = call["args"][json_text_arg]
                        break
            high_level_json_alias = True
            target = primitive_target

        if target.startswith(_HTML_HYDRATE_PREFIX):
            template_name = target[len(_HTML_HYDRATE_PREFIX):]
            template = self.prog.html_templates.get(template_name)
            if template is None:
                raise ValueError(
                    f"{call_name}: unknown htmlTemplate `{template_name}`")

            def html_record_leaf_type(record_type, field_path):
                current_type = record_type
                for index, part in enumerate(field_path.split(".")):
                    record = self.prog.records.get(current_type)
                    if record is None:
                        return None
                    field_type = None
                    for candidate_name, candidate_type in record.fields:
                        if candidate_name == part:
                            field_type = candidate_type
                            break
                    if field_type is None:
                        return None
                    if index == len(field_path.split(".")) - 1:
                        return field_type
                    nested = _record_type_for_json_body(self.prog, field_type)
                    if nested is None:
                        return None
                    current_type = nested
                return None

            def html_arg_path_named(hole_path):
                root_name, field_path = hole_path.split(".", 1)
                if root_name not in call["args"]:
                    raise ValueError(
                        f"{call_name}: missing required arg `{root_name}` "
                        f"for htmlTemplate `{template.name}`")
                root_type = call.get("arg_types", {}).get(root_name)
                if not root_type:
                    raise ValueError(
                        f"htmlBody {template.name}: record-field hole "
                        f"`{hole_path}` requires argument `{root_name}` to "
                        "declare a record type")
                record_type = (
                    root_type if root_type in self.prog.records
                    else _record_type_for_json_body(self.prog, root_type)
                )
                if record_type is None:
                    raise ValueError(
                        f"htmlBody {template.name}: record-field hole "
                        f"`{hole_path}` requires record argument `{root_name}`, "
                        f"got `{root_type}`")
                field_type = html_record_leaf_type(record_type, field_path)
                if field_type is None:
                    raise ValueError(
                        f"htmlBody {template.name}: record `{record_type}` "
                        f"has no string field path `{field_path}`")
                source_name = call["args"][root_name]
                source = record_values.get(source_name)
                if source is not None and field_path in source.get("slots", {}):
                    return (
                        builder.load(
                            source["slots"][field_path],
                            name=f"{call_name}_{hole_path.replace('.', '_')}_field"),
                        field_type,
                    )
                record_const = self.prog.record_json_constants.get(source_name)
                if record_const is not None:
                    raw_value = high_json_nested_field(
                        record_const.get("fields", {}), field_path)
                    return high_json_const_value(field_type, raw_value), field_type
                raise ValueError(
                    f"htmlBody {template.name}: record-field hole "
                    f"`{hole_path}` cannot resolve record value `{source_name}`")

            self._emit_html_hydrate(builder, call_name, call, template,
                                    arg_val_named, html_arg_path_named)
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
            # Print a Float64 / Float64 with C's `%f\n` format (six fractional
            # digits — the printf default — to match native-output behavior).
            # The value arg is widened to double if the LLVM
            # type is a float; passed straight through if already a double.
            v = arg_val_named("value")
            if isinstance(v.type, ir.IntType):
                v = builder.sitofp(v, Float64)
            elif isinstance(v.type, ir.FloatType):
                v = builder.fpext(v, Float64)
            fmt_ptr = self._i8p(builder, "%f\n")
            self.provenance.record_external("printf", call)
            call["result"] = builder.call(
                self.printf, [fmt_ptr, v], name=f"{call_name}_res")
            return

        if target == "math.signExtendInt32ToInt64":
            usable = [(k, v) for k, v in call["args"].items()
                      if v not in opaque_inputs]
            v = resolve(usable[0][1])
            v = require_i32(v, "math.signExtendInt32ToInt64 input")
            call["result"] = builder.sext(v, Int64, name=f"{call_name}_res")
            return

        if target == "math.truncateInt64ToInt32":
            usable = [(k, v) for k, v in call["args"].items()
                      if v not in opaque_inputs]
            v = resolve(usable[0][1])
            v = require_i64(v, "math.truncateInt64ToInt32 input")
            call["result"] = builder.trunc(v, Int32, name=f"{call_name}_res")
            return

        if target == "math.bitwiseNotInt64":
            # One's-complement of an i64: every bit flipped. Lowered as
            # `xor value, -1` (all-ones), a single LLVM instruction.
            usable = [(k, v) for k, v in call["args"].items()
                      if v not in opaque_inputs]
            v = resolve(usable[0][1])
            v = require_i64(v, "math.bitwiseNotInt64 input")
            call["result"] = builder.xor(
                v, ir.Constant(Int64, -1), name=f"{call_name}_res")
            return

        if target == "math.intToFloat":
            # Convert a signed integer to double precision (sitofp).
            # Used by SemanticScript-stdlib float math to bridge integer counters
            # into float computations without linking libm.
            usable = [(k, v) for k, v in call["args"].items()
                      if v not in opaque_inputs]
            v = resolve(usable[0][1])
            v = require_i64(v, "math.intToFloat input")
            call["result"] = builder.sitofp(v, Float64, name=f"{call_name}_res")
            return
        if target == "math.floatToInt":
            # Convert a double-precision value to a signed 64-bit integer
            # by rounding toward zero (fptosi). Used to implement
            # floor/ceil/trunc in pure SemanticScript.
            usable = [(k, v) for k, v in call["args"].items()
                      if v not in opaque_inputs]
            v = resolve(usable[0][1])
            v = require_f64(v, "math.floatToInt input")
            call["result"] = builder.fptosi(v, Int64, name=f"{call_name}_res")
            return

        if target == "math.checkedMultiplyInt64":
            # Lower to the signed-multiply-with-overflow intrinsic so that
            # callers can branchIfError on the overflow bit instead of
            # silently wrapping.
            a, b = operand_pair()
            a = require_i64(a, "math.checkedMultiplyInt64 left operand")
            b = require_i64(b, "math.checkedMultiplyInt64 right operand")
            agg = builder.call(self.smul_overflow_i64, [a, b],
                               name=f"{call_name}_tuple")
            product = builder.extract_value(agg, 0, name=f"{call_name}_res")
            overflow = builder.extract_value(agg, 1, name=f"{call_name}_overflow")
            call["result"] = product
            call["error_value"] = overflow
            call["error_cond"] = overflow
            return

        if target in _BINOP_TO_LLVM:
            if call.get("domain_method") == "square" and target == "math.multiplyInt64":
                a = operand_single()
                b = a
            else:
                a, b = operand_pair()
            a = require_i64(a, f"{target} left operand")
            b = require_i64(b, f"{target} right operand")
            if target in ("math.divideInt64", "math.moduloInt64"):
                divisor_is_zero = builder.icmp_signed(
                    "==", b, ir.Constant(b.type, 0),
                    name=f"{call_name}_divisorIsZero")
                source_target = call.get("source_target") or target
                self._emit_runtime_check(
                    builder, divisor_is_zero, call,
                    f"zero divisor before {source_target}")
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

        if target in _CMP_Int32_TO_LLVM:
            a, b = operand_pair()
            a = require_i32(a, f"{target} left operand")
            b = require_i32(b, f"{target} right operand")
            call["result"] = builder.icmp_signed(_CMP_Int32_TO_LLVM[target], a, b, name=f"{call_name}_res")
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
            if buffer_arg.type != Int8P:
                buffer_arg = builder.bitcast(buffer_arg, Int8P)
            offset_arg = self._coerce_for_libc(builder, offset_arg, "ByteCount")
            self._emit_null_pointer_check(
                builder, buffer_arg, call,
                "null buffer before pointer.loadByte")
            ptr = builder.gep(buffer_arg, [offset_arg], inbounds=True,
                              name=f"{call_name}_addr")
            loaded_byte = builder.load(ptr, name=f"{call_name}_byte")
            call["result"] = builder.sext(loaded_byte, Int32, name=f"{call_name}_res")
            return

        if target == "pointer.storeByte":
            usable = [(k, v) for k, v in call["args"].items()
                      if v not in opaque_inputs]
            buffer_arg = resolve(usable[0][1])
            offset_arg = resolve(usable[1][1])
            value_arg = resolve(usable[2][1])
            if buffer_arg.type != Int8P:
                buffer_arg = builder.bitcast(buffer_arg, Int8P)
            offset_arg = self._coerce_for_libc(builder, offset_arg, "ByteCount")
            value_arg = self._coerce_for_libc(builder, value_arg, "Int8")
            self._emit_null_pointer_check(
                builder, buffer_arg, call,
                "null buffer before pointer.storeByte")
            ptr = builder.gep(buffer_arg, [offset_arg], inbounds=True,
                              name=f"{call_name}_addr")
            builder.store(value_arg, ptr)
            call["result"] = ir.Constant(Int32, 0)
            return

        # `pointer.offset base offset` returns base + offset as a pointer
        # without dereferencing. Used to walk through a byte buffer.
        if target == "pointer.offset":
            usable = [(k, v) for k, v in call["args"].items()
                      if v not in opaque_inputs]
            base = resolve(usable[0][1])
            offset = resolve(usable[1][1])
            if base.type != Int8P:
                base = builder.bitcast(base, Int8P)
            offset = self._coerce_for_libc(builder, offset, "ByteCount")
            call["result"] = builder.gep(base, [offset], inbounds=True,
                                          name=f"{call_name}_addr")
            return

        # `pointer.difference left right` returns (left - right) as a
        # Int64. Both operands must point into the same allocation
        # for the result to be meaningful — this is a §10 contract the
        # SemanticScript-level type system does not yet enforce.
        if target == "pointer.difference":
            usable = [(k, v) for k, v in call["args"].items()
                      if v not in opaque_inputs]
            left = resolve(usable[0][1])
            right = resolve(usable[1][1])
            if left.type != Int8P:
                left = builder.bitcast(left, Int8P)
            if right.type != Int8P:
                right = builder.bitcast(right, Int8P)
            left_int = builder.ptrtoint(left, Int64, name=f"{call_name}_lhs")
            right_int = builder.ptrtoint(right, Int64, name=f"{call_name}_rhs")
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
            if ptr.type != Int8P:
                ptr = builder.bitcast(ptr, Int8P)
            null_ptr = ir.Constant(Int8P, None)
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
            x = self._coerce_for_libc(builder, x, "Float64")
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
                    if ptyp in ("FileHandle", "OpaquePointer", "DecomposedTimeAddress",
                                "SetjmpRegisterBuffer"):
                        v = ir.Constant(Int8P, None)
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
                        v = ir.Constant(Int8P, None)
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
                call["result"] = ir.Constant(Int32, 0)
            else:
                call["result"] = res
            return

        def gui_i32_arg(arg_name):
            value = arg_val_named(arg_name)
            if isinstance(value.type, ir.IntType):
                if value.type.width < 32:
                    return builder.sext(value, Int32)
                if value.type.width > 32:
                    return builder.trunc(value, Int32)
                return value
            raise ValueError(f"{call_name}: {target} arg `{arg_name}` must be an integer")

        def gui_ptr_arg(arg_name):
            value = arg_val_named(arg_name)
            if value.type == Int8P:
                return value
            if isinstance(value.type, ir.PointerType):
                return builder.bitcast(value, Int8P)
            if isinstance(value.type, ir.IntType):
                return builder.inttoptr(value, Int8P)
            raise ValueError(f"{call_name}: {target} arg `{arg_name}` must be pointer-shaped")

        def gui_handler_arg(arg_name):
            handler_name = call["args"].get(arg_name)
            if handler_name not in self._user_ops:
                raise ValueError(
                    f"{call_name}: {target} arg `{arg_name}` must name a declared operation")
            op_info = self._user_ops[handler_name]
            handler_fnty = ir.FunctionType(Int32, [Int8P, Int8P])
            handler_ptr_ty = handler_fnty.as_pointer()
            handler_ptr = op_info["fn"]
            if len(op_info["params"]) != 2:
                raise ValueError(
                    f"{call_name}: GUI handler `{handler_name}` must declare "
                    "input HANDLER session GuiSession and input HANDLER event GuiEvent")
            if op_info["return_type"] != Int32:
                raise ValueError(
                    f"{call_name}: GUI handler `{handler_name}` must return Int32")
            if handler_ptr.type != handler_ptr_ty:
                handler_ptr = builder.bitcast(handler_ptr, handler_ptr_ty)
            return handler_ptr

        if target == "gui.applicationCreate":
            fn = self._runtime_func("ss_gui_application_create", Int8P, [Int8P])
            self.provenance.record_external("ss_gui_application_create", call)
            call["result"] = builder.call(
                fn, [gui_ptr_arg("title")], name=f"{call_name}_res")
            return

        if target == "gui.windowCreate":
            fn = self._runtime_func(
                "ss_gui_window_create", Int8P, [Int8P, Int32, Int32, Int32, Int32])
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
            fn = self._runtime_func("ss_gui_text_label_create", Int8P, [Int8P])
            self.provenance.record_external("ss_gui_text_label_create", call)
            call["result"] = builder.call(
                fn, [gui_ptr_arg("text")], name=f"{call_name}_res")
            return

        if target == "gui.textBoxCreate":
            fn = self._runtime_func("ss_gui_text_box_create", Int8P, [Int8P, Int32])
            self.provenance.record_external("ss_gui_text_box_create", call)
            call["result"] = builder.call(
                fn,
                [gui_ptr_arg("placeholder"), gui_i32_arg("maxLength")],
                name=f"{call_name}_res")
            return

        if target == "gui.buttonCreate":
            fn = self._runtime_func("ss_gui_button_create", Int8P, [Int8P, Int32])
            self.provenance.record_external("ss_gui_button_create", call)
            call["result"] = builder.call(
                fn,
                [gui_ptr_arg("text"), gui_i32_arg("isDefault")],
                name=f"{call_name}_res")
            return

        if target == "gui.listBoxCreate":
            fn = self._runtime_func("ss_gui_list_box_create", Int8P, [Int32])
            self.provenance.record_external("ss_gui_list_box_create", call)
            call["result"] = builder.call(
                fn, [gui_i32_arg("selectionMode")], name=f"{call_name}_res")
            return

        if target == "gui.windowAddControl":
            fn = self._runtime_func("ss_gui_window_add_control", Int32, [Int8P, Int8P])
            self.provenance.record_external("ss_gui_window_add_control", call)
            call["result"] = builder.call(
                fn,
                [gui_ptr_arg("window"), gui_ptr_arg("control")],
                name=f"{call_name}_res")
            return

        if target == "gui.controlOnEvent":
            handler_fnty = ir.FunctionType(Int32, [Int8P, Int8P])
            handler_ptr_ty = handler_fnty.as_pointer()
            fn = self._runtime_func(
                "ss_gui_control_on_event", Int32, [Int8P, Int32, handler_ptr_ty])
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
                "ss_gui_application_set_main_window", Int32, [Int8P, Int8P])
            self.provenance.record_external("ss_gui_application_set_main_window", call)
            call["result"] = builder.call(
                fn,
                [gui_ptr_arg("application"), gui_ptr_arg("window")],
                name=f"{call_name}_res")
            return

        if target == "gui.applicationRun":
            fn = self._runtime_func("ss_gui_application_run_builder", Int32, [Int8P])
            self.provenance.record_external("ss_gui_application_run_builder", call)
            call["result"] = builder.call(
                fn, [gui_ptr_arg("application")], name=f"{call_name}_res")
            return

        if target == "gui.textBoxText":
            fn = self._runtime_func(
                "ss_gui_text_box_text_by_handle", Int8P, [Int8P, Int8P])
            self.provenance.record_external("ss_gui_text_box_text_by_handle", call)
            call["result"] = builder.call(
                fn,
                [gui_ptr_arg("session"), gui_ptr_arg("textBox")],
                name=f"{call_name}_res")
            return

        if target == "gui.textBoxSetText":
            fn = self._runtime_func(
                "ss_gui_text_box_set_text_by_handle", Int32, [Int8P, Int8P, Int8P])
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
                "ss_gui_list_box_selected_index_by_handle", Int32, [Int8P, Int8P])
            self.provenance.record_external("ss_gui_list_box_selected_index_by_handle", call)
            call["result"] = builder.call(
                fn,
                [gui_ptr_arg("session"), gui_ptr_arg("listBox")],
                name=f"{call_name}_res")
            return

        if target == "gui.listBoxAppendItem":
            fn = self._runtime_func(
                "ss_gui_list_box_append_item_by_handle", Int32, [Int8P, Int8P, Int8P])
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
                "ss_gui_list_box_clear_by_handle", Int32, [Int8P, Int8P])
            self.provenance.record_external("ss_gui_list_box_clear_by_handle", call)
            call["result"] = builder.call(
                fn,
                [gui_ptr_arg("session"), gui_ptr_arg("listBox")],
                name=f"{call_name}_res")
            return

        if target == "gui.textLabelSetText":
            fn = self._runtime_func(
                "ss_gui_text_label_set_text_by_handle", Int32, [Int8P, Int8P, Int8P])
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
                "ss_gui_window_close_by_handle", Int32, [Int8P, Int8P])
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
            self._emit_crash_frame_push(
                builder,
                f"operation {target} (call {call_name} line {call.get('line', 0)})")
            result = builder.call(op_info["fn"], arg_values,
                                  name=f"{call_name}_res")
            self._emit_crash_frame_pop(builder)
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
        # codec runtime work tracked under docs/reference/syntax-inventory.md's Partial row.
        if target in (
            "json.encode.Int64", "json.encode.UInt64",
            "json.encode.Int32", "json.encode.UInt32",
            "json.encode.Int16", "json.encode.UInt16",
            "json.encode.Int8", "json.encode.UInt8",
            "json.encode.DurationMilliseconds",
            "json.encode.MonotonicMilliseconds",
            "json.encode.UtcMilliseconds",
        ):
            n = coerce_i64_for_non_math_abi(arg_val_named("value"))
            if high_level_json_alias:
                buf_size = 64
                with builder.goto_entry_block():
                    buf = builder.alloca(
                        ir.ArrayType(Int8, buf_size),
                        name=f"{call_name}_jsonbuf")
                    out_slot = builder.alloca(Int8P, name=f"{call_name}_jsonOut")
                buf_ptr = builder.gep(
                    buf, [ir.Constant(Int32, 0), ir.Constant(Int32, 0)], inbounds=True)
                stringify_fn = self._runtime_func(
                    "ss_json_stringify_int64", Int32,
                    [Int64, Int8P, Int64, Int8P.as_pointer()])
                self.provenance.record_external("ss_json_stringify_int64", call)
                status = builder.call(
                    stringify_fn,
                    [n, buf_ptr, ir.Constant(Int64, buf_size), out_slot],
                    name=f"{call_name}_jsonStatus")
                call["result"] = builder.load(out_slot, name=f"{call_name}_encoded")
                mark_high_level_json_status(status, 3)
                return
            buf_size = 32
            with builder.goto_entry_block():
                buf = builder.alloca(
                    ir.ArrayType(Int8, buf_size),
                    name=f"{call_name}_jsonbuf")
            buf_ptr = builder.gep(
                buf, [ir.Constant(Int32, 0), ir.Constant(Int32, 0)], inbounds=True)
            snprintf = self._libc_func("snprintf")
            fmt = self._i8p(builder, "%lld")
            builder.call(snprintf,
                         [buf_ptr, ir.Constant(Int64, buf_size), fmt, n])
            call["result"] = buf_ptr
            if high_level_json_alias:
                mark_high_level_json_success()
            return
        if target == "json.encode.Bool":
            v = arg_val_named("value")
            if isinstance(v.type, ir.IntType) and v.type.width > 1:
                v = builder.icmp_signed("!=", v, ir.Constant(v.type, 0))
            if high_level_json_alias:
                bool_i32 = builder.zext(v, Int32, name=f"{call_name}_boolInt32")
                buf_size = 8
                with builder.goto_entry_block():
                    buf = builder.alloca(
                        ir.ArrayType(Int8, buf_size),
                        name=f"{call_name}_jsonbuf")
                    out_slot = builder.alloca(Int8P, name=f"{call_name}_jsonOut")
                buf_ptr = builder.gep(
                    buf, [ir.Constant(Int32, 0), ir.Constant(Int32, 0)], inbounds=True)
                stringify_fn = self._runtime_func(
                    "ss_json_stringify_bool", Int32,
                    [Int32, Int8P, Int64, Int8P.as_pointer()])
                self.provenance.record_external("ss_json_stringify_bool", call)
                status = builder.call(
                    stringify_fn,
                    [bool_i32, buf_ptr, ir.Constant(Int64, buf_size), out_slot],
                    name=f"{call_name}_jsonStatus")
                call["result"] = builder.load(out_slot, name=f"{call_name}_encoded")
                mark_high_level_json_status(status, 3)
                return
            true_str = self._i8p(builder, "true")
            false_str = self._i8p(builder, "false")
            call["result"] = builder.select(
                v, true_str, false_str, name=f"{call_name}_bool")
            if high_level_json_alias:
                mark_high_level_json_success()
            return
        if target in (
            "json.encode.Float64", "json.encode.Float32", "json.encode.Float16",
        ):
            v = arg_val_named("value")
            if isinstance(v.type, ir.IntType):
                v = builder.sitofp(v, Float64)
            elif isinstance(v.type, ir.FloatType):
                v = builder.fpext(v, Float64)
            if high_level_json_alias:
                buf_size = 64
                with builder.goto_entry_block():
                    buf = builder.alloca(
                        ir.ArrayType(Int8, buf_size),
                        name=f"{call_name}_jsonbuf")
                    out_slot = builder.alloca(Int8P, name=f"{call_name}_jsonOut")
                buf_ptr = builder.gep(
                    buf, [ir.Constant(Int32, 0), ir.Constant(Int32, 0)], inbounds=True)
                stringify_fn = self._runtime_func(
                    "ss_json_stringify_double", Int32,
                    [Float64, Int8P, Int64, Int8P.as_pointer()])
                self.provenance.record_external("ss_json_stringify_double", call)
                status = builder.call(
                    stringify_fn,
                    [v, buf_ptr, ir.Constant(Int64, buf_size), out_slot],
                    name=f"{call_name}_jsonStatus")
                call["result"] = builder.load(out_slot, name=f"{call_name}_encoded")
                mark_high_level_json_status(status, 3)
                return
            buf_size = 32
            with builder.goto_entry_block():
                buf = builder.alloca(
                    ir.ArrayType(Int8, buf_size),
                    name=f"{call_name}_jsonbuf")
            buf_ptr = builder.gep(
                buf, [ir.Constant(Int32, 0), ir.Constant(Int32, 0)], inbounds=True)
            snprintf = self._libc_func("snprintf")
            fmt = self._i8p(builder, "%g")
            builder.call(snprintf,
                         [buf_ptr, ir.Constant(Int64, buf_size), fmt, v])
            call["result"] = buf_ptr
            if high_level_json_alias:
                mark_high_level_json_success()
            return
        if target in (
            "json.decode.Int64", "json.decode.UInt64",
            "json.decode.Int32", "json.decode.UInt32",
            "json.decode.Int16", "json.decode.UInt16",
            "json.decode.Int8", "json.decode.UInt8",
            "json.decode.DurationMilliseconds",
            "json.decode.MonotonicMilliseconds",
            "json.decode.UtcMilliseconds",
        ):
            if high_level_json_alias:
                v = arg_val_named("value")
                if isinstance(v.type, ir.IntType):
                    v = builder.inttoptr(v, Int8P)
                with builder.goto_entry_block():
                    out_slot = builder.alloca(Int64, name=f"{call_name}_decodedSlot")
                parse_fn = self._runtime_func(
                    "ss_json_parse_int64", Int32, [Int8P, Int64.as_pointer()])
                self.provenance.record_external("ss_json_parse_int64", call)
                status = builder.call(
                    parse_fn, [v, out_slot], name=f"{call_name}_jsonStatus")
                decoded = builder.load(out_slot, name=f"{call_name}_decoded")
                call["result"] = decoded
                mark_high_level_json_status(status, 1)
                return
            # Decode a JSON integer literal via libc atoll. The input is a
            # null-terminated byte string holding the decimal text; atoll
            # returns 0 on malformed input (matching JSON-leniency for the
            # primitive path — strict parsing belongs to the codec runtime).
            v = arg_val_named("value")
            if isinstance(v.type, ir.IntType):
                v = builder.inttoptr(v, Int8P)
            atoll = self._libc_func("atoll")
            call["result"] = builder.call(
                atoll, [v], name=f"{call_name}_decoded")
            if high_level_json_alias:
                mark_high_level_json_success()
            return
        if target == "json.decode.Bool":
            if high_level_json_alias:
                v = arg_val_named("value")
                if isinstance(v.type, ir.IntType):
                    v = builder.inttoptr(v, Int8P)
                with builder.goto_entry_block():
                    out_slot = builder.alloca(Int32, name=f"{call_name}_decodedSlot")
                parse_fn = self._runtime_func(
                    "ss_json_parse_bool", Int32, [Int8P, Int32.as_pointer()])
                self.provenance.record_external("ss_json_parse_bool", call)
                status = builder.call(
                    parse_fn, [v, out_slot], name=f"{call_name}_jsonStatus")
                decoded_i32 = builder.load(out_slot, name=f"{call_name}_decodedInt32")
                call["result"] = builder.sext(
                    decoded_i32, Int64, name=f"{call_name}_decoded")
                mark_high_level_json_status(status, 1)
                return
            # Compare the input string against the literal "true" via
            # libc strcmp; result is 1 when strings are equal (i.e.
            # the JSON token was "true"), 0 otherwise.
            v = arg_val_named("value")
            if isinstance(v.type, ir.IntType):
                v = builder.inttoptr(v, Int8P)
            strcmp = self._libc_func("strcmp")
            true_str = self._i8p(builder, "true")
            cmp = builder.call(strcmp, [v, true_str], name=f"{call_name}_strcmp")
            is_true = builder.icmp_signed(
                "==", cmp, ir.Constant(Int32, 0), name=f"{call_name}_isTrue")
            call["result"] = builder.zext(
                is_true, Int64, name=f"{call_name}_decoded")
            if high_level_json_alias:
                mark_high_level_json_success()
            return
        if target in (
            "json.decode.Float64", "json.decode.Float32", "json.decode.Float16",
        ):
            if high_level_json_alias:
                v = arg_val_named("value")
                if isinstance(v.type, ir.IntType):
                    v = builder.inttoptr(v, Int8P)
                with builder.goto_entry_block():
                    out_slot = builder.alloca(Float64, name=f"{call_name}_decodedSlot")
                parse_fn = self._runtime_func(
                    "ss_json_parse_double", Int32, [Int8P, Float64.as_pointer()])
                self.provenance.record_external("ss_json_parse_double", call)
                status = builder.call(
                    parse_fn, [v, out_slot], name=f"{call_name}_jsonStatus")
                call["result"] = builder.load(out_slot, name=f"{call_name}_decoded")
                mark_high_level_json_status(status, 1)
                return
            # Use libc atof to parse the JSON number; returns double 0.0
            # on malformed input.
            v = arg_val_named("value")
            if isinstance(v.type, ir.IntType):
                v = builder.inttoptr(v, Int8P)
            atof = self._libc_func("atof")
            call["result"] = builder.call(
                atof, [v], name=f"{call_name}_decoded")
            if high_level_json_alias:
                mark_high_level_json_success()
            return
        if target == "json.encode.String":
            if high_level_json_alias:
                v = arg_val_named("value")
                if isinstance(v.type, ir.IntType):
                    v = builder.inttoptr(v, Int8P)
                buf_size = 4096
                with builder.goto_entry_block():
                    buf = builder.alloca(
                        ir.ArrayType(Int8, buf_size),
                        name=f"{call_name}_jsonbuf")
                    out_slot = builder.alloca(Int8P, name=f"{call_name}_jsonOut")
                buf_ptr = builder.gep(
                    buf, [ir.Constant(Int32, 0), ir.Constant(Int32, 0)], inbounds=True)
                stringify_fn = self._runtime_func(
                    "ss_json_stringify_string", Int32,
                    [Int8P, Int8P, Int64, Int8P.as_pointer()])
                self.provenance.record_external("ss_json_stringify_string", call)
                status = builder.call(
                    stringify_fn,
                    [v, buf_ptr, ir.Constant(Int64, buf_size), out_slot],
                    name=f"{call_name}_jsonStatus")
                call["result"] = builder.load(out_slot, name=f"{call_name}_encoded")
                mark_high_level_json_status(status, 3)
                return
            # JSON-encoding a string requires quoting + escape handling
            # (\\, \", \n, \r, \t, \uXXXX for control bytes). For now, we
            # produce the string surrounded by ASCII quotes — correct for
            # ASCII payloads that contain none of the special characters.
            # Full escape handling is deferred to the real codec runtime
            # tracked under docs/reference/syntax-inventory.md's Partial row.
            v = arg_val_named("value")
            if isinstance(v.type, ir.IntType):
                v = builder.inttoptr(v, Int8P)
            buf_size = 256
            with builder.goto_entry_block():
                buf = builder.alloca(
                    ir.ArrayType(Int8, buf_size),
                    name=f"{call_name}_jsonbuf")
            buf_ptr = builder.gep(
                buf, [ir.Constant(Int32, 0), ir.Constant(Int32, 0)], inbounds=True)
            snprintf = self._libc_func("snprintf")
            fmt = self._i8p(builder, "\"%s\"")
            builder.call(snprintf,
                         [buf_ptr, ir.Constant(Int64, buf_size), fmt, v])
            call["result"] = buf_ptr
            if high_level_json_alias:
                mark_high_level_json_success()
            return

        # ------------------------------------------------------------
        # standard.json runtime dispatch — opaque JsonBuilder handle
        # plus the field-at-a-time encoder and the named-field finder
        # API exposed by sem_json_runtime.h. Each call lowers to a
        # direct ss_json_* invocation; the linker only pulls in
        # sem_json_runtime.c when any of these targets is actually
        # referenced (see _native_json_link_inputs).
        # ------------------------------------------------------------

        def json_arg_any(*arg_names):
            for arg_name in arg_names:
                if arg_name in call["args"]:
                    return arg_val_named(arg_name)
            expected = " / ".join(arg_names)
            raise ValueError(
                f"{call_name}: missing required arg `{expected}` for {target}")

        def json_as_i8p(value, arg_name: str):
            if value.type == Int8P:
                return value
            if isinstance(value.type, ir.PointerType):
                return builder.bitcast(value, Int8P)
            if isinstance(value.type, ir.IntType):
                return builder.inttoptr(value, Int8P)
            raise ValueError(
                f"{call_name}: {target} arg `{arg_name}` must be pointer-shaped")

        def json_i8p_arg(*arg_names):
            return json_as_i8p(json_arg_any(*arg_names), arg_names[0])

        def json_i64_value(value, arg_name: str):
            if isinstance(value.type, ir.IntType):
                if value.type.width < 64:
                    return builder.sext(value, Int64)
                if value.type.width > 64:
                    return builder.trunc(value, Int64)
                return value
            if isinstance(value.type, ir.PointerType):
                return builder.ptrtoint(value, Int64)
            raise ValueError(
                f"{call_name}: {target} arg `{arg_name}` must be integer-shaped")

        def json_i64_arg(*arg_names):
            return json_i64_value(json_arg_any(*arg_names), arg_names[0])

        def json_i32_value(value, arg_name: str):
            if isinstance(value.type, ir.IntType):
                if value.type.width < 32:
                    extend = builder.zext if value.type.width == 1 else builder.sext
                    return extend(value, Int32)
                if value.type.width > 32:
                    return builder.trunc(value, Int32)
                return value
            raise ValueError(
                f"{call_name}: {target} arg `{arg_name}` must be a 32-bit integer")

        def json_i32_arg(*arg_names):
            return json_i32_value(json_arg_any(*arg_names), arg_names[0])

        def json_f64_value(value, arg_name: str):
            if value.type == Float64:
                return value
            if isinstance(value.type, ir.FloatType):
                return builder.fpext(value, Float64)
            if isinstance(value.type, ir.IntType):
                return builder.sitofp(value, Float64)
            raise ValueError(
                f"{call_name}: {target} arg `{arg_name}` must be numeric")

        def json_out_slot(slot_type, suffix: str):
            with builder.goto_entry_block():
                slot = builder.alloca(slot_type, name=f"{call_name}_{suffix}")
                if isinstance(slot_type, ir.PointerType):
                    builder.store(ir.Constant(slot_type, None), slot)
                elif isinstance(slot_type, (ir.FloatType, ir.DoubleType)):
                    builder.store(ir.Constant(slot_type, 0.0), slot)
                else:
                    builder.store(ir.Constant(slot_type, 0), slot)
            return slot

        def json_status_is_error(status):
            return builder.icmp_signed(
                "!=", status, ir.Constant(Int32, 0),
                name=f"{call_name}_isError")

        def json_result(success_value, status):
            call["result"] = success_value
            call["error_value"] = status
            call["error_cond"] = json_status_is_error(status)

        def json_status_result(status):
            json_result(ir.Constant(Int32, 0), status)

        if target == "json.createDocument":
            json_text = json_i8p_arg("jsonText", "text", "value")
            capacity = json_i64_arg("capacityBytes", "capacity")
            doc_slot = json_out_slot(Int8P, "documentSlot")
            create_fn = self._runtime_func(
                "ss_json_document_create_from_text",
                Int32, [Int8P, Int64, Int8P.as_pointer()])
            self.provenance.record_external(
                "ss_json_document_create_from_text", call)
            status = builder.call(
                create_fn, [json_text, capacity, doc_slot],
                name=f"{call_name}_status")
            document = builder.load(doc_slot, name=f"{call_name}_document")
            json_result(document, status)
            call["handle_slot"] = doc_slot
            return

        if target == "json.createEmptyDocument":
            capacity = json_i64_arg("capacityBytes", "capacity")
            root_kind = json_i32_arg("rootKind", "kind")
            doc_slot = json_out_slot(Int8P, "documentSlot")
            create_fn = self._runtime_func(
                "ss_json_document_create_empty",
                Int32, [Int64, Int32, Int8P.as_pointer()])
            self.provenance.record_external(
                "ss_json_document_create_empty", call)
            status = builder.call(
                create_fn, [capacity, root_kind, doc_slot],
                name=f"{call_name}_status")
            document = builder.load(doc_slot, name=f"{call_name}_document")
            json_result(document, status)
            call["handle_slot"] = doc_slot
            return

        if target == "json.destroyDocument":
            document = json_i8p_arg("document")
            destroy_fn = self._runtime_func(
                "ss_json_document_destroy", VOID, [Int8P])
            self.provenance.record_external("ss_json_document_destroy", call)
            builder.call(destroy_fn, [document])
            call["result"] = ir.Constant(Int32, 0)
            return

        if target == "json.serializeDocument":
            document = json_i8p_arg("document")
            scratch = json_i8p_arg("scratch", "scratchBuffer")
            scratch_capacity = json_i64_arg("scratchCapacity", "capacityBytes")
            out_slot = json_out_slot(Int8P, "jsonTextSlot")
            serialize_fn = self._runtime_func(
                "ss_json_document_serialize",
                Int32, [Int8P, Int8P, Int64, Int8P.as_pointer()])
            self.provenance.record_external(
                "ss_json_document_serialize", call)
            status = builder.call(
                serialize_fn, [document, scratch, scratch_capacity, out_slot],
                name=f"{call_name}_status")
            json_text = builder.load(out_slot, name=f"{call_name}_jsonText")
            json_result(json_text, status)
            return

        if target == "json.documentLength":
            document = json_i8p_arg("document")
            fn = self._runtime_func(
                "ss_json_document_length", Int64, [Int8P])
            self.provenance.record_external("ss_json_document_length", call)
            call["result"] = builder.call(
                fn, [document], name=f"{call_name}_length")
            return

        if target == "json.documentRoot":
            document = json_i8p_arg("document")
            fn = self._runtime_func(
                "ss_json_document_root", Int64, [Int8P])
            self.provenance.record_external("ss_json_document_root", call)
            call["result"] = builder.call(
                fn, [document], name=f"{call_name}_root")
            return

        if target in (
            "json.objectFieldAt",
            "json.arrayElementAt",
            "json.cursorParent",
            "json.cursorAtPath",
        ):
            document = json_i8p_arg("document")
            out_slot = json_out_slot(Int64, "cursorSlot")
            if target == "json.objectFieldAt":
                cursor = json_i64_arg("cursor")
                field_name = json_i8p_arg("fieldName", "name")
                symbol = "ss_json_navigate_object_field"
                param_tys = [Int8P, Int64, Int8P, Int64.as_pointer()]
                args_for_call = [document, cursor, field_name, out_slot]
            elif target == "json.arrayElementAt":
                cursor = json_i64_arg("cursor")
                index = json_i64_arg("index")
                symbol = "ss_json_navigate_array_element"
                param_tys = [Int8P, Int64, Int64, Int64.as_pointer()]
                args_for_call = [document, cursor, index, out_slot]
            elif target == "json.cursorParent":
                cursor = json_i64_arg("cursor")
                symbol = "ss_json_cursor_parent"
                param_tys = [Int8P, Int64, Int64.as_pointer()]
                args_for_call = [document, cursor, out_slot]
            else:
                path = json_i8p_arg("path", "jsonPath")
                symbol = "ss_json_cursor_at_path"
                param_tys = [Int8P, Int8P, Int64.as_pointer()]
                args_for_call = [document, path, out_slot]
            fn = self._runtime_func(symbol, Int32, param_tys)
            self.provenance.record_external(symbol, call)
            status = builder.call(fn, args_for_call, name=f"{call_name}_status")
            cursor_value = builder.load(out_slot, name=f"{call_name}_cursor")
            json_result(cursor_value, status)
            return

        if target == "json.cursorKind":
            document = json_i8p_arg("document")
            cursor = json_i64_arg("cursor")
            fn = self._runtime_func(
                "ss_json_cursor_kind", Int32, [Int8P, Int64])
            self.provenance.record_external("ss_json_cursor_kind", call)
            call["result"] = builder.call(
                fn, [document, cursor], name=f"{call_name}_kind")
            return

        if target == "json.cursorIsNull":
            document = json_i8p_arg("document")
            cursor = json_i64_arg("cursor")
            fn = self._runtime_func(
                "ss_json_cursor_is_null", Int32, [Int8P, Int64])
            self.provenance.record_external("ss_json_cursor_is_null", call)
            raw = builder.call(fn, [document, cursor], name=f"{call_name}_raw")
            call["result"] = builder.icmp_signed(
                "!=", raw, ir.Constant(Int32, 0), name=f"{call_name}_isNull")
            return

        if target in ("json.cursorInt64", "json.cursorDouble", "json.cursorBool"):
            document = json_i8p_arg("document")
            cursor = json_i64_arg("cursor")
            if target == "json.cursorInt64":
                missing_default = json_i64_arg("missingDefault", "default")
                symbol = "ss_json_cursor_int64"
                return_ty = Int64
                param_tys = [Int8P, Int64, Int64]
                args_for_call = [document, cursor, missing_default]
                result_name = "int64"
            elif target == "json.cursorDouble":
                missing_default = json_f64_value(
                    json_arg_any("missingDefault", "default"),
                    "missingDefault")
                symbol = "ss_json_cursor_double"
                return_ty = Float64
                param_tys = [Int8P, Int64, Float64]
                args_for_call = [document, cursor, missing_default]
                result_name = "double"
            else:
                missing_default = json_i32_value(
                    json_arg_any("missingDefault", "default"),
                    "missingDefault")
                symbol = "ss_json_cursor_bool"
                return_ty = Int32
                param_tys = [Int8P, Int64, Int32]
                args_for_call = [document, cursor, missing_default]
                result_name = "boolRaw"
            fn = self._runtime_func(symbol, return_ty, param_tys)
            self.provenance.record_external(symbol, call)
            loaded = builder.call(fn, args_for_call, name=f"{call_name}_{result_name}")
            if target == "json.cursorBool":
                loaded = builder.icmp_signed(
                    "!=", loaded, ir.Constant(Int32, 0),
                    name=f"{call_name}_bool")
            call["result"] = loaded
            return

        if target in (
            "json.cursorString",
            "json.cursorArrayLength",
            "json.cursorObjectFieldCount",
            "json.cursorObjectFieldNameAt",
            "json.cursorObjectFieldValueAt",
        ):
            document = json_i8p_arg("document")
            cursor = json_i64_arg("cursor")
            if target == "json.cursorString":
                scratch = json_i8p_arg("scratch", "scratchBuffer")
                scratch_capacity = json_i64_arg("scratchCapacity", "capacityBytes")
                out_slot = json_out_slot(Int8P, "stringSlot")
                symbol = "ss_json_cursor_string"
                param_tys = [Int8P, Int64, Int8P, Int64, Int8P.as_pointer()]
                args_for_call = [document, cursor, scratch, scratch_capacity, out_slot]
                result_name = "string"
            elif target == "json.cursorArrayLength":
                out_slot = json_out_slot(Int64, "arrayLengthSlot")
                symbol = "ss_json_cursor_array_length"
                param_tys = [Int8P, Int64, Int64.as_pointer()]
                args_for_call = [document, cursor, out_slot]
                result_name = "arrayLength"
            elif target == "json.cursorObjectFieldCount":
                out_slot = json_out_slot(Int64, "fieldCountSlot")
                symbol = "ss_json_cursor_object_field_count"
                param_tys = [Int8P, Int64, Int64.as_pointer()]
                args_for_call = [document, cursor, out_slot]
                result_name = "fieldCount"
            elif target == "json.cursorObjectFieldNameAt":
                index = json_i64_arg("index")
                scratch = json_i8p_arg("scratch", "scratchBuffer")
                scratch_capacity = json_i64_arg("scratchCapacity", "capacityBytes")
                out_slot = json_out_slot(Int8P, "fieldNameSlot")
                symbol = "ss_json_cursor_object_field_name_at"
                param_tys = [Int8P, Int64, Int64, Int8P, Int64, Int8P.as_pointer()]
                args_for_call = [
                    document, cursor, index, scratch, scratch_capacity, out_slot]
                result_name = "fieldName"
            else:
                index = json_i64_arg("index")
                out_slot = json_out_slot(Int64, "fieldValueSlot")
                symbol = "ss_json_cursor_object_field_value_at"
                param_tys = [Int8P, Int64, Int64, Int64.as_pointer()]
                args_for_call = [document, cursor, index, out_slot]
                result_name = "fieldValue"
            fn = self._runtime_func(symbol, Int32, param_tys)
            self.provenance.record_external(symbol, call)
            status = builder.call(fn, args_for_call, name=f"{call_name}_status")
            value = builder.load(out_slot, name=f"{call_name}_{result_name}")
            json_result(value, status)
            return

        object_field_mutators = {
            "json.setObjectFieldString": ("ss_json_set_object_field_string", "string"),
            "json.setObjectFieldInt64": ("ss_json_set_object_field_int64", "int64"),
            "json.setObjectFieldDouble": ("ss_json_set_object_field_double", "double"),
            "json.setObjectFieldBool": ("ss_json_set_object_field_bool", "bool"),
            "json.setObjectFieldNull": ("ss_json_set_object_field_null", "null"),
            "json.setObjectFieldObject": ("ss_json_set_object_field_object", "container"),
            "json.setObjectFieldArray": ("ss_json_set_object_field_array", "container"),
            "json.setObjectFieldJsonText": ("ss_json_set_object_field_json_text", "jsonText"),
        }
        if target in object_field_mutators:
            symbol, value_kind = object_field_mutators[target]
            document = json_i8p_arg("document")
            cursor = json_i64_arg("cursor")
            field_name = json_i8p_arg("fieldName", "name")
            param_tys = [Int8P, Int64, Int8P]
            args_for_call = [document, cursor, field_name]
            cursor_out_slot = None
            if value_kind == "string":
                param_tys.append(Int8P)
                args_for_call.append(json_i8p_arg("value", "stringValue"))
            elif value_kind == "int64":
                param_tys.append(Int64)
                args_for_call.append(json_i64_arg("value"))
            elif value_kind == "double":
                param_tys.append(Float64)
                args_for_call.append(json_f64_value(json_arg_any("value"), "value"))
            elif value_kind == "bool":
                param_tys.append(Int32)
                args_for_call.append(json_i32_value(json_arg_any("value"), "value"))
            elif value_kind == "container":
                cursor_out_slot = json_out_slot(Int64, "cursorSlot")
                param_tys.append(Int64.as_pointer())
                args_for_call.append(cursor_out_slot)
            elif value_kind == "jsonText":
                param_tys.append(Int8P)
                args_for_call.append(json_i8p_arg("jsonText", "value"))
                cursor_out_slot = json_out_slot(Int64, "cursorSlot")
                param_tys.append(Int64.as_pointer())
                args_for_call.append(cursor_out_slot)
            fn = self._runtime_func(symbol, Int32, param_tys)
            self.provenance.record_external(symbol, call)
            status = builder.call(fn, args_for_call, name=f"{call_name}_status")
            if cursor_out_slot is not None:
                child_cursor = builder.load(cursor_out_slot, name=f"{call_name}_cursor")
                json_result(child_cursor, status)
            else:
                json_status_result(status)
            return

        array_mutators = {
            "json.appendArrayElementString": ("ss_json_append_array_element_string", "append", "string"),
            "json.appendArrayElementInt64": ("ss_json_append_array_element_int64", "append", "int64"),
            "json.appendArrayElementDouble": ("ss_json_append_array_element_double", "append", "double"),
            "json.appendArrayElementBool": ("ss_json_append_array_element_bool", "append", "bool"),
            "json.appendArrayElementNull": ("ss_json_append_array_element_null", "append", "null"),
            "json.appendArrayElementObject": ("ss_json_append_array_element_object", "append", "container"),
            "json.appendArrayElementArray": ("ss_json_append_array_element_array", "append", "container"),
            "json.appendArrayElementJsonText": ("ss_json_append_array_element_json_text", "append", "jsonText"),
            "json.insertArrayElementString": ("ss_json_insert_array_element_string", "indexed", "string"),
            "json.insertArrayElementInt64": ("ss_json_insert_array_element_int64", "indexed", "int64"),
            "json.insertArrayElementDouble": ("ss_json_insert_array_element_double", "indexed", "double"),
            "json.insertArrayElementBool": ("ss_json_insert_array_element_bool", "indexed", "bool"),
            "json.insertArrayElementNull": ("ss_json_insert_array_element_null", "indexed", "null"),
            "json.insertArrayElementObject": ("ss_json_insert_array_element_object", "indexed", "container"),
            "json.insertArrayElementArray": ("ss_json_insert_array_element_array", "indexed", "container"),
            "json.insertArrayElementJsonText": ("ss_json_insert_array_element_json_text", "indexed", "jsonText"),
            "json.replaceArrayElementString": ("ss_json_replace_array_element_string", "indexed", "string"),
            "json.replaceArrayElementInt64": ("ss_json_replace_array_element_int64", "indexed", "int64"),
            "json.replaceArrayElementDouble": ("ss_json_replace_array_element_double", "indexed", "double"),
            "json.replaceArrayElementBool": ("ss_json_replace_array_element_bool", "indexed", "bool"),
            "json.replaceArrayElementNull": ("ss_json_replace_array_element_null", "indexed", "null"),
            "json.replaceArrayElementObject": ("ss_json_replace_array_element_object", "indexed", "container"),
            "json.replaceArrayElementArray": ("ss_json_replace_array_element_array", "indexed", "container"),
            "json.replaceArrayElementJsonText": ("ss_json_replace_array_element_json_text", "indexed", "jsonText"),
        }
        if target in array_mutators:
            symbol, index_kind, value_kind = array_mutators[target]
            document = json_i8p_arg("document")
            cursor = json_i64_arg("cursor")
            param_tys = [Int8P, Int64]
            args_for_call = [document, cursor]
            cursor_out_slot = None
            if index_kind == "indexed":
                param_tys.append(Int64)
                args_for_call.append(json_i64_arg("index"))
            if value_kind == "string":
                param_tys.append(Int8P)
                args_for_call.append(json_i8p_arg("value", "stringValue"))
            elif value_kind == "int64":
                param_tys.append(Int64)
                args_for_call.append(json_i64_arg("value"))
            elif value_kind == "double":
                param_tys.append(Float64)
                args_for_call.append(json_f64_value(json_arg_any("value"), "value"))
            elif value_kind == "bool":
                param_tys.append(Int32)
                args_for_call.append(json_i32_value(json_arg_any("value"), "value"))
            elif value_kind == "container":
                cursor_out_slot = json_out_slot(Int64, "cursorSlot")
                param_tys.append(Int64.as_pointer())
                args_for_call.append(cursor_out_slot)
            elif value_kind == "jsonText":
                param_tys.append(Int8P)
                args_for_call.append(json_i8p_arg("jsonText", "value"))
                cursor_out_slot = json_out_slot(Int64, "cursorSlot")
                param_tys.append(Int64.as_pointer())
                args_for_call.append(cursor_out_slot)
            fn = self._runtime_func(symbol, Int32, param_tys)
            self.provenance.record_external(symbol, call)
            status = builder.call(fn, args_for_call, name=f"{call_name}_status")
            if cursor_out_slot is not None:
                child_cursor = builder.load(cursor_out_slot, name=f"{call_name}_cursor")
                json_result(child_cursor, status)
            else:
                json_status_result(status)
            return

        if target == "json.removeObjectField":
            document = json_i8p_arg("document")
            cursor = json_i64_arg("cursor")
            field_name = json_i8p_arg("fieldName", "name")
            fn = self._runtime_func(
                "ss_json_remove_object_field", Int32, [Int8P, Int64, Int8P])
            self.provenance.record_external("ss_json_remove_object_field", call)
            status = builder.call(
                fn, [document, cursor, field_name], name=f"{call_name}_status")
            json_status_result(status)
            return

        if target == "json.removeArrayElementAt":
            document = json_i8p_arg("document")
            cursor = json_i64_arg("cursor")
            index = json_i64_arg("index")
            fn = self._runtime_func(
                "ss_json_remove_array_element_at", Int32, [Int8P, Int64, Int64])
            self.provenance.record_external(
                "ss_json_remove_array_element_at", call)
            status = builder.call(
                fn, [document, cursor, index], name=f"{call_name}_status")
            json_status_result(status)
            return

        if target in ("json.clearObject", "json.clearArray"):
            document = json_i8p_arg("document")
            cursor = json_i64_arg("cursor")
            symbol = (
                "ss_json_clear_object"
                if target == "json.clearObject"
                else "ss_json_clear_array"
            )
            fn = self._runtime_func(symbol, Int32, [Int8P, Int64])
            self.provenance.record_external(symbol, call)
            status = builder.call(
                fn, [document, cursor], name=f"{call_name}_status")
            json_status_result(status)
            return

        if target == "json.createBuilder":
            capacity = arg_val_named("capacity")
            if isinstance(capacity.type, ir.IntType) and capacity.type.width != 64:
                capacity = (builder.sext(capacity, Int64)
                            if capacity.type.width < 64
                            else builder.trunc(capacity, Int64))
            create_fn = self._runtime_func("ss_json_builder_create", Int8P, [Int64])
            self.provenance.record_external("ss_json_builder_create", call)
            call["result"] = builder.call(
                create_fn, [capacity], name=f"{call_name}_builder")
            return

        if target == "json.destroyBuilder":
            builder_arg = arg_val_named("builder")
            if isinstance(builder_arg.type, ir.IntType):
                builder_arg = builder.inttoptr(builder_arg, Int8P)
            destroy_fn = self._runtime_func("ss_json_builder_destroy", VOID, [Int8P])
            self.provenance.record_external("ss_json_builder_destroy", call)
            builder.call(destroy_fn, [builder_arg])
            # Void return — give the surrounding bind machinery a
            # deterministic zero so anything that accidentally binds
            # this call's result still has a valid SSA value.
            call["result"] = ir.Constant(Int32, 0)
            return

        # Helper for any builder mutator that takes the builder handle
        # only (open/close containers).
        def _json_builder_handle_only(symbol):
            builder_arg = arg_val_named("builder")
            if isinstance(builder_arg.type, ir.IntType):
                builder_arg = builder.inttoptr(builder_arg, Int8P)
            fn = self._runtime_func(symbol, Int32, [Int8P])
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
                builder_arg = builder.inttoptr(builder_arg, Int8P)
            if isinstance(field_name.type, ir.IntType):
                field_name = builder.inttoptr(field_name, Int8P)
            if target == "json.fieldInt64":
                if isinstance(value.type, ir.IntType) and value.type.width != 64:
                    value = (builder.sext(value, Int64)
                             if value.type.width < 64
                             else builder.trunc(value, Int64))
                symbol = "ss_json_builder_field_int64"
                param_tys = [Int8P, Int8P, Int64]
            elif target == "json.fieldDouble":
                if isinstance(value.type, ir.IntType):
                    value = builder.sitofp(value, Float64)
                symbol = "ss_json_builder_field_double"
                param_tys = [Int8P, Int8P, Float64]
            elif target == "json.fieldBool":
                if isinstance(value.type, ir.IntType) and value.type.width != 32:
                    value = (builder.sext(value, Int32)
                             if value.type.width < 32
                             else builder.trunc(value, Int32))
                symbol = "ss_json_builder_field_bool"
                param_tys = [Int8P, Int8P, Int32]
            else:  # json.fieldString
                if isinstance(value.type, ir.IntType):
                    value = builder.inttoptr(value, Int8P)
                symbol = "ss_json_builder_field_string"
                param_tys = [Int8P, Int8P, Int8P]
            fn = self._runtime_func(symbol, Int32, param_tys)
            self.provenance.record_external(symbol, call)
            call["result"] = builder.call(
                fn, [builder_arg, field_name, value],
                name=f"{call_name}_status")
            return

        if target == "json.fieldNull":
            builder_arg = arg_val_named("builder")
            field_name = arg_val_named("fieldName")
            if isinstance(builder_arg.type, ir.IntType):
                builder_arg = builder.inttoptr(builder_arg, Int8P)
            if isinstance(field_name.type, ir.IntType):
                field_name = builder.inttoptr(field_name, Int8P)
            fn = self._runtime_func(
                "ss_json_builder_field_null", Int32, [Int8P, Int8P])
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
                builder_arg = builder.inttoptr(builder_arg, Int8P)
            if target == "json.elementInt64":
                if isinstance(value.type, ir.IntType) and value.type.width != 64:
                    value = (builder.sext(value, Int64)
                             if value.type.width < 64
                             else builder.trunc(value, Int64))
                symbol = "ss_json_builder_element_int64"
                param_tys = [Int8P, Int64]
            elif target == "json.elementDouble":
                if isinstance(value.type, ir.IntType):
                    value = builder.sitofp(value, Float64)
                symbol = "ss_json_builder_element_double"
                param_tys = [Int8P, Float64]
            elif target == "json.elementBool":
                if isinstance(value.type, ir.IntType) and value.type.width != 32:
                    value = (builder.sext(value, Int32)
                             if value.type.width < 32
                             else builder.trunc(value, Int32))
                symbol = "ss_json_builder_element_bool"
                param_tys = [Int8P, Int32]
            else:  # json.elementString
                if isinstance(value.type, ir.IntType):
                    value = builder.inttoptr(value, Int8P)
                symbol = "ss_json_builder_element_string"
                param_tys = [Int8P, Int8P]
            fn = self._runtime_func(symbol, Int32, param_tys)
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
                builder_arg = builder.inttoptr(builder_arg, Int8P)
            fn = self._runtime_func("ss_json_builder_finish", Int8P, [Int8P])
            self.provenance.record_external("ss_json_builder_finish", call)
            call["result"] = builder.call(
                fn, [builder_arg], name=f"{call_name}_body")
            return

        if target == "json.builderLength":
            builder_arg = arg_val_named("builder")
            if isinstance(builder_arg.type, ir.IntType):
                builder_arg = builder.inttoptr(builder_arg, Int8P)
            fn = self._runtime_func("ss_json_builder_length", Int64, [Int8P])
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
                json_text = builder.inttoptr(json_text, Int8P)
            if isinstance(field_name.type, ir.IntType):
                field_name = builder.inttoptr(field_name, Int8P)
            fn = self._runtime_func("ss_json_has_field", Int32, [Int8P, Int8P])
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
                json_text = builder.inttoptr(json_text, Int8P)
            if isinstance(field_name.type, ir.IntType):
                field_name = builder.inttoptr(field_name, Int8P)
            if isinstance(scratch.type, ir.IntType):
                scratch = builder.inttoptr(scratch, Int8P)
            if (isinstance(scratch_capacity.type, ir.IntType)
                    and scratch_capacity.type.width != 64):
                scratch_capacity = (builder.sext(scratch_capacity, Int64)
                                    if scratch_capacity.type.width < 64
                                    else builder.trunc(scratch_capacity, Int64))
            fn = self._runtime_func(
                "ss_json_find_string", Int8P, [Int8P, Int8P, Int8P, Int64])
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
                json_text = builder.inttoptr(json_text, Int8P)
            if isinstance(field_name.type, ir.IntType):
                field_name = builder.inttoptr(field_name, Int8P)
            if (isinstance(missing_default.type, ir.IntType)
                    and missing_default.type.width != 64):
                missing_default = (builder.sext(missing_default, Int64)
                                   if missing_default.type.width < 64
                                   else builder.trunc(missing_default, Int64))
            fn = self._runtime_func(
                "ss_json_find_int64", Int64, [Int8P, Int8P, Int64])
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
                json_text = builder.inttoptr(json_text, Int8P)
            if isinstance(field_name.type, ir.IntType):
                field_name = builder.inttoptr(field_name, Int8P)
            if isinstance(missing_default.type, ir.IntType):
                missing_default = builder.sitofp(missing_default, Float64)
            fn = self._runtime_func(
                "ss_json_find_double", Float64, [Int8P, Int8P, Float64])
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
                json_text = builder.inttoptr(json_text, Int8P)
            if isinstance(field_name.type, ir.IntType):
                field_name = builder.inttoptr(field_name, Int8P)
            if (isinstance(missing_default.type, ir.IntType)
                    and missing_default.type.width != 32):
                missing_default = (builder.sext(missing_default, Int32)
                                   if missing_default.type.width < 32
                                   else builder.trunc(missing_default, Int32))
            fn = self._runtime_func(
                "ss_json_find_bool", Int32, [Int8P, Int8P, Int32])
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

        if target in ("bcrypt.hashPassword", "hashPassword"):
            plaintext = arg_val_named("plaintext")
            cost = arg_val_named("cost")
            out_buffer = arg_val_named("outBuffer")
            out_capacity = arg_val_named("outCapacity")
            if isinstance(plaintext.type, ir.IntType):
                plaintext = builder.inttoptr(plaintext, Int8P)
            if isinstance(out_buffer.type, ir.IntType):
                out_buffer = builder.inttoptr(out_buffer, Int8P)
            if isinstance(cost.type, ir.IntType) and cost.type.width != 32:
                cost = (builder.trunc(cost, Int32) if cost.type.width > 32
                        else builder.sext(cost, Int32))
            if isinstance(out_capacity.type, ir.IntType) and out_capacity.type.width != 32:
                out_capacity = (builder.trunc(out_capacity, Int32)
                                if out_capacity.type.width > 32
                                else builder.sext(out_capacity, Int32))
            fn = self._runtime_func(
                "ss_bcrypt_hash", Int32, [Int8P, Int32, Int8P, Int32])
            self.provenance.record_external("ss_bcrypt_hash", call)
            call["result"] = builder.call(
                fn, [plaintext, cost, out_buffer, out_capacity],
                name=f"{call_name}_status")
            return

        if target in ("bcrypt.verifyPassword", "verifyPassword"):
            plaintext = arg_val_named("plaintext")
            expected_hash = arg_val_named("expectedHash")
            if isinstance(plaintext.type, ir.IntType):
                plaintext = builder.inttoptr(plaintext, Int8P)
            if isinstance(expected_hash.type, ir.IntType):
                expected_hash = builder.inttoptr(expected_hash, Int8P)
            fn = self._runtime_func(
                "ss_bcrypt_verify", Int32, [Int8P, Int8P])
            self.provenance.record_external("ss_bcrypt_verify", call)
            call["result"] = builder.call(
                fn, [plaintext, expected_hash],
                name=f"{call_name}_matchOrErr")
            return

        if target in ("bcrypt.randomBytes", "randomBytes"):
            out_buffer = arg_val_named("outBuffer")
            byte_count = arg_val_named("byteCount")
            if isinstance(out_buffer.type, ir.IntType):
                out_buffer = builder.inttoptr(out_buffer, Int8P)
            if isinstance(byte_count.type, ir.IntType) and byte_count.type.width != 32:
                byte_count = (builder.trunc(byte_count, Int32)
                              if byte_count.type.width > 32
                              else builder.sext(byte_count, Int32))
            fn = self._runtime_func(
                "ss_random_bytes", Int32, [Int8P, Int32])
            self.provenance.record_external("ss_random_bytes", call)
            call["result"] = builder.call(
                fn, [out_buffer, byte_count],
                name=f"{call_name}_status")
            return

        if target in ("bcrypt.base64UrlEncode", "base64UrlEncode"):
            input_buffer = arg_val_named("inputBuffer")
            input_count = arg_val_named("inputCount")
            output_buffer = arg_val_named("outputBuffer")
            output_capacity = arg_val_named("outputCapacity")
            output_length_out = arg_val_named("outputLengthOut")
            if isinstance(input_buffer.type, ir.IntType):
                input_buffer = builder.inttoptr(input_buffer, Int8P)
            if isinstance(output_buffer.type, ir.IntType):
                output_buffer = builder.inttoptr(output_buffer, Int8P)
            if isinstance(output_length_out.type, ir.IntType):
                output_length_out = builder.inttoptr(
                    output_length_out, Int32.as_pointer())
            if isinstance(input_count.type, ir.IntType) and input_count.type.width != 32:
                input_count = (builder.trunc(input_count, Int32)
                               if input_count.type.width > 32
                               else builder.sext(input_count, Int32))
            if isinstance(output_capacity.type, ir.IntType) and output_capacity.type.width != 32:
                output_capacity = (builder.trunc(output_capacity, Int32)
                                   if output_capacity.type.width > 32
                                   else builder.sext(output_capacity, Int32))
            fn = self._runtime_func(
                "ss_base64url_encode", Int32,
                [Int8P, Int32, Int8P, Int32, Int32.as_pointer()])
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
        #   3. docs/reference/syntax-inventory.md — the two `http.requestMethod, …` and
        #      `http.responseText, …` umbrella rows.
        #
        # The drift between these three sources is asserted by the
        # `TestHttpTargetSourceOfTruth` test class in
        # SemanticScript/linter/test_semlint.py — if you add a target
        # without updating all three sites, that test fails with a
        # specific drift diff. Do not "fix" the test by hiding the
        # drift; fix the drift.
        if target == "http.responseHtml":
            response = arg_val_named("response")
            status = arg_val_named("status")
            body = arg_val_named("body")
            content_type = self._i8p(builder, "text/html; charset=utf-8")
            if isinstance(status.type, ir.IntType) and status.type.width != 32:
                status = builder.trunc(status, Int32) if status.type.width > 32 else builder.sext(status, Int32)
            if isinstance(response.type, ir.IntType):
                response = builder.inttoptr(response, Int8P)
            if isinstance(body.type, ir.IntType):
                body = builder.inttoptr(body, Int8P)
            response_text = self._runtime_func(
                "ss_http_response_text",
                Int32,
                [Int8P, Int32, Int8P, Int8P]
            )
            self.provenance.record_external("ss_http_response_text", call)
            call["result"] = builder.call(
                response_text,
                [response, status, body, content_type],
                name=f"{call_name}_res"
            )
            return

        if target == "http.responseText":
            response = arg_val_named("response")
            status = arg_val_named("status")
            body = arg_val_named("body")
            content_type = ir.Constant(Int8P, None)
            if "contentType" in call["args"]:
                content_type = arg_val_named("contentType")
            if isinstance(status.type, ir.IntType) and status.type.width != 32:
                status = builder.trunc(status, Int32) if status.type.width > 32 else builder.sext(status, Int32)
            if isinstance(response.type, ir.IntType):
                response = builder.inttoptr(response, Int8P)
            if isinstance(body.type, ir.IntType):
                body = builder.inttoptr(body, Int8P)
            if isinstance(content_type.type, ir.IntType):
                content_type = builder.inttoptr(content_type, Int8P)
            response_text = self._runtime_func(
                "ss_http_response_text",
                Int32,
                [Int8P, Int32, Int8P, Int8P]
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
            content_type = ir.Constant(Int8P, None)
            if "contentType" in call["args"]:
                content_type = arg_val_named("contentType")
            if isinstance(status.type, ir.IntType) and status.type.width != 32:
                status = builder.trunc(status, Int32) if status.type.width > 32 else builder.sext(status, Int32)
            if isinstance(response.type, ir.IntType):
                response = builder.inttoptr(response, Int8P)
            if isinstance(body.type, ir.IntType):
                body = builder.inttoptr(body, Int8P)
            if isinstance(body_length.type, ir.IntType) and body_length.type.width != 64:
                body_length = builder.zext(body_length, Int64) if body_length.type.width < 64 else builder.trunc(body_length, Int64)
            if isinstance(content_type.type, ir.IntType):
                content_type = builder.inttoptr(content_type, Int8P)
            response_bytes = self._runtime_func(
                "ss_http_response_bytes",
                Int32,
                [Int8P, Int32, Int8P, Int64, Int8P]
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
                status = builder.trunc(status, Int32) if status.type.width > 32 else builder.sext(status, Int32)
            if isinstance(response.type, ir.IntType):
                response = builder.inttoptr(response, Int8P)
            if isinstance(event_name.type, ir.IntType):
                event_name = builder.inttoptr(event_name, Int8P)
            if isinstance(event_data.type, ir.IntType):
                event_data = builder.inttoptr(event_data, Int8P)
            response_sse_event = self._runtime_func(
                "ss_http_response_sse_event",
                Int32,
                [Int8P, Int32, Int8P, Int8P]
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
                response = builder.inttoptr(response, Int8P)
            if isinstance(name.type, ir.IntType):
                name = builder.inttoptr(name, Int8P)
            if isinstance(value.type, ir.IntType):
                value = builder.inttoptr(value, Int8P)
            response_header = self._runtime_func(
                "ss_http_response_header",
                Int32,
                [Int8P, Int8P, Int8P]
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
                request = builder.inttoptr(request, Int8P)
            request_method = self._runtime_func("ss_http_request_method", Int8P, [Int8P])
            self.provenance.record_external("ss_http_request_method", call)
            call["result"] = builder.call(request_method, [request], name=f"{call_name}_res")
            return

        if target == "http.requestPath":
            request = arg_val_named("request")
            if isinstance(request.type, ir.IntType):
                request = builder.inttoptr(request, Int8P)
            request_path = self._runtime_func("ss_http_request_path", Int8P, [Int8P])
            self.provenance.record_external("ss_http_request_path", call)
            call["result"] = builder.call(request_path, [request], name=f"{call_name}_res")
            return

        if target == "http.requestHeader":
            request = arg_val_named("request")
            name = arg_val_named("name")
            if isinstance(request.type, ir.IntType):
                request = builder.inttoptr(request, Int8P)
            if isinstance(name.type, ir.IntType):
                name = builder.inttoptr(name, Int8P)
            request_header = self._runtime_func("ss_http_request_header", Int8P, [Int8P, Int8P])
            self.provenance.record_external("ss_http_request_header", call)
            call["result"] = builder.call(request_header, [request, name], name=f"{call_name}_res")
            return

        if target == "http.requestQueryParam":
            request = arg_val_named("request")
            name = arg_val_named("name")
            if isinstance(request.type, ir.IntType):
                request = builder.inttoptr(request, Int8P)
            if isinstance(name.type, ir.IntType):
                name = builder.inttoptr(name, Int8P)
            request_query_param = self._runtime_func("ss_http_request_query_param", Int8P, [Int8P, Int8P])
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
                request = builder.inttoptr(request, Int8P)
            if isinstance(name.type, ir.IntType):
                name = builder.inttoptr(name, Int8P)
            request_path_param = self._runtime_func(
                "ss_http_request_path_param", Int8P, [Int8P, Int8P])
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
                request = builder.inttoptr(request, Int8P)
            if isinstance(cookie_name.type, ir.IntType):
                cookie_name = builder.inttoptr(cookie_name, Int8P)
            fn = self._runtime_func(
                "ss_http_request_cookie", Int8P, [Int8P, Int8P])
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
                response = builder.inttoptr(response, Int8P)
            if isinstance(status.type, ir.IntType) and status.type.width != 32:
                status = (builder.trunc(status, Int32) if status.type.width > 32
                          else builder.sext(status, Int32))
            if isinstance(root_directory.type, ir.IntType):
                root_directory = builder.inttoptr(root_directory, Int8P)
            if isinstance(requested_path.type, ir.IntType):
                requested_path = builder.inttoptr(requested_path, Int8P)
            fn = self._runtime_func(
                "ss_http_response_file", Int32, [Int8P, Int32, Int8P, Int8P])
            self.provenance.record_external("ss_http_response_file", call)
            call["result"] = builder.call(
                fn, [response, status, root_directory, requested_path],
                name=f"{call_name}_status")
            return

        if target == "http.nowMillis":
            fn = self._runtime_func("ss_http_now_millis", Int64, [])
            self.provenance.record_external("ss_http_now_millis", call)
            call["result"] = builder.call(fn, [], name=f"{call_name}_millis")
            return

        if target == "http.ensureDirectory":
            directory_path = arg_val_named("directoryPath")
            if isinstance(directory_path.type, ir.IntType):
                directory_path = builder.inttoptr(directory_path, Int8P)
            fn = self._runtime_func(
                "ss_http_filesystem_ensure_directory", Int32, [Int8P])
            self.provenance.record_external(
                "ss_http_filesystem_ensure_directory", call)
            call["result"] = builder.call(
                fn, [directory_path], name=f"{call_name}_status")
            return

        if target == "http.requestBodyText":
            request = arg_val_named("request")
            if isinstance(request.type, ir.IntType):
                request = builder.inttoptr(request, Int8P)
            request_body = self._runtime_func("ss_http_request_body_text", Int8P, [Int8P])
            self.provenance.record_external("ss_http_request_body_text", call)
            call["result"] = builder.call(request_body, [request], name=f"{call_name}_res")
            return

        if target == "http.requestBodyBytes":
            request = arg_val_named("request")
            if isinstance(request.type, ir.IntType):
                request = builder.inttoptr(request, Int8P)
            request_body = self._runtime_func("ss_http_request_body_bytes", Int8P, [Int8P])
            self.provenance.record_external("ss_http_request_body_bytes", call)
            call["result"] = builder.call(request_body, [request], name=f"{call_name}_res")
            return

        if target == "http.requestBodyLength":
            request = arg_val_named("request")
            if isinstance(request.type, ir.IntType):
                request = builder.inttoptr(request, Int8P)
            request_body_length = self._runtime_func("ss_http_request_body_length", Int64, [Int8P])
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
                request = builder.inttoptr(request, Int8P)
            if isinstance(name.type, ir.IntType):
                name = builder.inttoptr(name, Int8P)
            multipart_reader = self._runtime_func(runtime_name, Int8P, [Int8P, Int8P])
            self.provenance.record_external(runtime_name, call)
            call["result"] = builder.call(multipart_reader, [request, name], name=f"{call_name}_res")
            return

        if target == "http.multipartPartLength":
            request = arg_val_named("request")
            name = arg_val_named("name")
            if isinstance(request.type, ir.IntType):
                request = builder.inttoptr(request, Int8P)
            if isinstance(name.type, ir.IntType):
                name = builder.inttoptr(name, Int8P)
            multipart_length = self._runtime_func("ss_http_multipart_part_length", Int64, [Int8P, Int8P])
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
                "!=", status_value, ir.Constant(Int32, 0),
                name=f"{call_name}_isError")

        if target in ("sqlite.openDatabase", "openDatabase"):
            path = arg_val_named("path")
            mode = arg_val_named("mode")
            if isinstance(path.type, ir.IntType):
                path = builder.inttoptr(path, Int8P)
            if isinstance(mode.type, ir.IntType) and mode.type.width != 32:
                mode = (builder.trunc(mode, Int32) if mode.type.width > 32
                        else builder.sext(mode, Int32))
            # Entry-block alloca so a later `defer ... sqlite.closeDatabase`
            # can re-load the handle from a slot that dominates every
            # cleanup site (failure labels, returnOk fall-throughs, etc.).
            # Pre-init the slot to NULL: a defer that fires before the
            # open succeeded then sees a sentinel rather than garbage.
            with builder.goto_entry_block():
                db_slot = builder.alloca(
                    Int8P, name=f"{call_name}_databaseSlot")
                builder.store(ir.Constant(Int8P, None), db_slot)
            open_fn = self._runtime_func(
                "ss_sqlite_database_open", Int32, [Int8P, Int32, Int8P.as_pointer()])
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

        if target in ("sqlite.closeDatabase", "closeDatabase"):
            database = arg_val_named("database")
            if isinstance(database.type, ir.IntType):
                database = builder.inttoptr(database, Int8P)
            close_fn = self._runtime_func(
                "ss_sqlite_database_close", Int32, [Int8P])
            self.provenance.record_external("ss_sqlite_database_close", call)
            status = builder.call(
                close_fn, [database], name=f"{call_name}_status")
            call["result"] = ir.Constant(Int32, 0)
            call["error_value"] = status
            call["error_cond"] = _sqlite_simple_status_error_cond(status)
            return

        if target in ("sqlite.errorMessage", "errorMessage"):
            database = arg_val_named("database")
            if isinstance(database.type, ir.IntType):
                database = builder.inttoptr(database, Int8P)
            errmsg_fn = self._runtime_func(
                "ss_sqlite_database_errmsg", Int8P, [Int8P])
            self.provenance.record_external("ss_sqlite_database_errmsg", call)
            call["result"] = builder.call(
                errmsg_fn, [database], name=f"{call_name}_message")
            return

        if target in ("sqlite.lastInsertRowId", "lastInsertRowId"):
            database = arg_val_named("database")
            if isinstance(database.type, ir.IntType):
                database = builder.inttoptr(database, Int8P)
            last_rowid_fn = self._runtime_func(
                "ss_sqlite_database_last_insert_rowid", Int64, [Int8P])
            self.provenance.record_external(
                "ss_sqlite_database_last_insert_rowid", call)
            call["result"] = builder.call(
                last_rowid_fn, [database], name=f"{call_name}_rowid")
            return

        if target in ("sqlite.changedRowCount", "changedRowCount"):
            database = arg_val_named("database")
            if isinstance(database.type, ir.IntType):
                database = builder.inttoptr(database, Int8P)
            changes_fn = self._runtime_func(
                "ss_sqlite_database_changes", Int32, [Int8P])
            self.provenance.record_external(
                "ss_sqlite_database_changes", call)
            call["result"] = builder.call(
                changes_fn, [database], name=f"{call_name}_changes")
            return

        if target in ("sqlite.execStatus", "execStatus"):
            database = arg_val_named("database")
            sql = arg_val_named("sql")
            if isinstance(database.type, ir.IntType):
                database = builder.inttoptr(database, Int8P)
            if isinstance(sql.type, ir.IntType):
                sql = builder.inttoptr(sql, Int8P)
            exec_fn = self._runtime_func(
                "ss_sqlite_exec", Int32, [Int8P, Int8P])
            self.provenance.record_external("ss_sqlite_exec", call)
            call["result"] = builder.call(
                exec_fn, [database, sql], name=f"{call_name}_status")
            return

        if target in ("sqlite.exec", "exec"):
            database = arg_val_named("database")
            sql = arg_val_named("sql")
            if isinstance(database.type, ir.IntType):
                database = builder.inttoptr(database, Int8P)
            if isinstance(sql.type, ir.IntType):
                sql = builder.inttoptr(sql, Int8P)
            exec_fn = self._runtime_func(
                "ss_sqlite_exec", Int32, [Int8P, Int8P])
            self.provenance.record_external("ss_sqlite_exec", call)
            status = builder.call(
                exec_fn, [database, sql], name=f"{call_name}_status")
            call["result"] = ir.Constant(Int32, 0)
            call["error_value"] = status
            call["error_cond"] = _sqlite_simple_status_error_cond(status)
            return

        if target in ("sqlite.prepareStatement", "prepareStatement"):
            database = arg_val_named("database")
            sql = arg_val_named("sql")
            if isinstance(database.type, ir.IntType):
                database = builder.inttoptr(database, Int8P)
            if isinstance(sql.type, ir.IntType):
                sql = builder.inttoptr(sql, Int8P)
            # Entry-block alloca for the same reason openDatabase uses
            # one — a later `defer ... sqlite.finalizeStatement` must be
            # able to re-load the handle from a slot that dominates the
            # defer's basic block. Pre-init to NULL so a defer that fires
            # before prepare succeeded passes a NULL handle through to
            # the adapter (which treats NULL as a config error).
            with builder.goto_entry_block():
                stmt_slot = builder.alloca(
                    Int8P, name=f"{call_name}_statementSlot")
                builder.store(ir.Constant(Int8P, None), stmt_slot)
            prepare_fn = self._runtime_func(
                "ss_sqlite_statement_prepare", Int32,
                [Int8P, Int8P, Int8P.as_pointer()])
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

        if target in ("sqlite.finalizeStatement", "finalizeStatement"):
            statement = arg_val_named("statement")
            if isinstance(statement.type, ir.IntType):
                statement = builder.inttoptr(statement, Int8P)
            finalize_fn = self._runtime_func(
                "ss_sqlite_statement_finalize", Int32, [Int8P])
            self.provenance.record_external(
                "ss_sqlite_statement_finalize", call)
            status = builder.call(
                finalize_fn, [statement], name=f"{call_name}_status")
            call["result"] = ir.Constant(Int32, 0)
            call["error_value"] = status
            call["error_cond"] = _sqlite_simple_status_error_cond(status)
            return

        if target in ("sqlite.resetStatement", "resetStatement"):
            statement = arg_val_named("statement")
            if isinstance(statement.type, ir.IntType):
                statement = builder.inttoptr(statement, Int8P)
            reset_fn = self._runtime_func(
                "ss_sqlite_statement_reset", Int32, [Int8P])
            self.provenance.record_external(
                "ss_sqlite_statement_reset", call)
            status = builder.call(
                reset_fn, [statement], name=f"{call_name}_status")
            call["result"] = ir.Constant(Int32, 0)
            call["error_value"] = status
            call["error_cond"] = _sqlite_simple_status_error_cond(status)
            return

        if target in ("sqlite.stepStatement", "stepStatement"):
            statement = arg_val_named("statement")
            if isinstance(statement.type, ir.IntType):
                statement = builder.inttoptr(statement, Int8P)
            step_fn = self._runtime_func(
                "ss_sqlite_statement_step", Int32, [Int8P])
            self.provenance.record_external(
                "ss_sqlite_statement_step", call)
            status = builder.call(
                step_fn, [statement], name=f"{call_name}_status")
            # stepStatement is the only sqlite.* call whose success leg
            # carries a value the user binds: SqliteStepResult ∈
            # {SS_SQLITE_STEP_ROW=100, SS_SQLITE_STEP_DONE=101}. Anything
            # below 100 is a SS_SQLITE_ERR_* status.
            step_row_value = ir.Constant(Int32, 100)
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
            "bindInt64",
            "bindDouble",
            "bindText",
            "bindBlob",
            "bindNull",
        ):
            statement = arg_val_named("statement")
            parameter_index = arg_val_named("parameterIndex")
            if isinstance(statement.type, ir.IntType):
                statement = builder.inttoptr(statement, Int8P)
            if (isinstance(parameter_index.type, ir.IntType)
                    and parameter_index.type.width != 32):
                parameter_index = (
                    builder.trunc(parameter_index, Int32)
                    if parameter_index.type.width > 32
                    else builder.sext(parameter_index, Int32))
            if target in ("sqlite.bindNull", "bindNull"):
                bind_fn = self._runtime_func(
                    "ss_sqlite_statement_bind_null", Int32, [Int8P, Int32])
                self.provenance.record_external(
                    "ss_sqlite_statement_bind_null", call)
                status = builder.call(
                    bind_fn, [statement, parameter_index],
                    name=f"{call_name}_status")
            elif target in ("sqlite.bindInt64", "bindInt64"):
                value = arg_val_named("value")
                if isinstance(value.type, ir.IntType) and value.type.width != 64:
                    value = (
                        builder.sext(value, Int64)
                        if value.type.width < 64
                        else builder.trunc(value, Int64))
                bind_fn = self._runtime_func(
                    "ss_sqlite_statement_bind_int64", Int32, [Int8P, Int32, Int64])
                self.provenance.record_external(
                    "ss_sqlite_statement_bind_int64", call)
                status = builder.call(
                    bind_fn, [statement, parameter_index, value],
                    name=f"{call_name}_status")
            elif target in ("sqlite.bindDouble", "bindDouble"):
                value = arg_val_named("value")
                bind_fn = self._runtime_func(
                    "ss_sqlite_statement_bind_double", Int32, [Int8P, Int32, Float64])
                self.provenance.record_external(
                    "ss_sqlite_statement_bind_double", call)
                status = builder.call(
                    bind_fn, [statement, parameter_index, value],
                    name=f"{call_name}_status")
            elif target in ("sqlite.bindText", "bindText"):
                value = arg_val_named("value")
                if isinstance(value.type, ir.IntType):
                    value = builder.inttoptr(value, Int8P)
                bind_fn = self._runtime_func(
                    "ss_sqlite_statement_bind_text", Int32, [Int8P, Int32, Int8P])
                self.provenance.record_external(
                    "ss_sqlite_statement_bind_text", call)
                status = builder.call(
                    bind_fn, [statement, parameter_index, value],
                    name=f"{call_name}_status")
            else:  # sqlite.bindBlob
                value = arg_val_named("value")
                value_length = arg_val_named("valueLength")
                if isinstance(value.type, ir.IntType):
                    value = builder.inttoptr(value, Int8P)
                if (isinstance(value_length.type, ir.IntType)
                        and value_length.type.width != 64):
                    value_length = (
                        builder.sext(value_length, Int64)
                        if value_length.type.width < 64
                        else builder.trunc(value_length, Int64))
                bind_fn = self._runtime_func(
                    "ss_sqlite_statement_bind_blob", Int32,
                    [Int8P, Int32, Int8P, Int64])
                self.provenance.record_external(
                    "ss_sqlite_statement_bind_blob", call)
                status = builder.call(
                    bind_fn,
                    [statement, parameter_index, value, value_length],
                    name=f"{call_name}_status")
            call["result"] = ir.Constant(Int32, 0)
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
            "columnCount",
            "columnType",
            "columnName",
            "columnInt64",
            "columnDouble",
            "columnText",
            "columnBlob",
            "columnByteCount",
        ):
            statement = arg_val_named("statement")
            if isinstance(statement.type, ir.IntType):
                statement = builder.inttoptr(statement, Int8P)
            if target in ("sqlite.columnCount", "columnCount"):
                fn = self._runtime_func(
                    "ss_sqlite_statement_column_count", Int32, [Int8P])
                self.provenance.record_external(
                    "ss_sqlite_statement_column_count", call)
                call["result"] = builder.call(
                    fn, [statement], name=f"{call_name}_count")
                return
            column_index = arg_val_named("columnIndex")
            if (isinstance(column_index.type, ir.IntType)
                    and column_index.type.width != 32):
                column_index = (
                    builder.trunc(column_index, Int32)
                    if column_index.type.width > 32
                    else builder.sext(column_index, Int32))
            if target in ("sqlite.columnType", "columnType"):
                fn = self._runtime_func(
                    "ss_sqlite_statement_column_type", Int32, [Int8P, Int32])
                self.provenance.record_external(
                    "ss_sqlite_statement_column_type", call)
                call["result"] = builder.call(
                    fn, [statement, column_index], name=f"{call_name}_type")
            elif target in ("sqlite.columnName", "columnName"):
                fn = self._runtime_func(
                    "ss_sqlite_statement_column_name", Int8P, [Int8P, Int32])
                self.provenance.record_external(
                    "ss_sqlite_statement_column_name", call)
                call["result"] = builder.call(
                    fn, [statement, column_index], name=f"{call_name}_name")
            elif target in ("sqlite.columnInt64", "columnInt64"):
                fn = self._runtime_func(
                    "ss_sqlite_statement_column_int64", Int64, [Int8P, Int32])
                self.provenance.record_external(
                    "ss_sqlite_statement_column_int64", call)
                call["result"] = builder.call(
                    fn, [statement, column_index], name=f"{call_name}_int")
            elif target in ("sqlite.columnDouble", "columnDouble"):
                fn = self._runtime_func(
                    "ss_sqlite_statement_column_double", Float64, [Int8P, Int32])
                self.provenance.record_external(
                    "ss_sqlite_statement_column_double", call)
                call["result"] = builder.call(
                    fn, [statement, column_index],
                    name=f"{call_name}_double")
            elif target in ("sqlite.columnText", "columnText"):
                fn = self._runtime_func(
                    "ss_sqlite_statement_column_text", Int8P, [Int8P, Int32])
                self.provenance.record_external(
                    "ss_sqlite_statement_column_text", call)
                call["result"] = builder.call(
                    fn, [statement, column_index], name=f"{call_name}_text")
            elif target in ("sqlite.columnBlob", "columnBlob"):
                fn = self._runtime_func(
                    "ss_sqlite_statement_column_blob", Int8P, [Int8P, Int32])
                self.provenance.record_external(
                    "ss_sqlite_statement_column_blob", call)
                call["result"] = builder.call(
                    fn, [statement, column_index], name=f"{call_name}_blob")
            else:  # sqlite.columnByteCount
                fn = self._runtime_func(
                    "ss_sqlite_statement_column_bytes", Int64, [Int8P, Int32])
                self.provenance.record_external(
                    "ss_sqlite_statement_column_bytes", call)
                call["result"] = builder.call(
                    fn, [statement, column_index],
                    name=f"{call_name}_byteCount")
            return

        if target in ("sqlite.libraryVersion", "libraryVersion"):
            version_fn = self._runtime_func(
                "ss_sqlite_library_version", Int8P, [])
            self.provenance.record_external(
                "ss_sqlite_library_version", call)
            call["result"] = builder.call(
                version_fn, [], name=f"{call_name}_version")
            return

        if target.startswith("sqlite."):
            raise ValueError(
                f"unsupported native sqlite call target: {target!r}; "
                "add an explicit compiler lowering before using it")

        def net_i8p(value):
            if isinstance(value.type, ir.IntType):
                return builder.inttoptr(value, Int8P)
            if isinstance(value.type, ir.PointerType) and value.type != Int8P:
                return builder.bitcast(value, Int8P)
            return value

        def net_i64(value):
            if isinstance(value.type, ir.IntType) and value.type.width != 64:
                return (builder.zext(value, Int64)
                        if value.type.width < 64
                        else builder.trunc(value, Int64))
            return value

        def net_i32(value):
            if isinstance(value.type, ir.IntType) and value.type.width != 32:
                return (builder.zext(value, Int32)
                        if value.type.width < 32
                        else builder.trunc(value, Int32))
            return value

        def net_record_field(record_symbol, field_path):
            source = record_values.get(record_symbol)
            if source is None:
                raise ValueError(
                    f"{call_name}: `{record_symbol}` is not a materialized record")
            slot = source["slots"].get(field_path)
            if slot is None:
                raise ValueError(
                    f"{call_name}: `{record_symbol}` has no field `{field_path}`")
            return builder.load(
                slot,
                name=f"{call_name}_{field_path.replace('.', '_')}")

        def net_emit_text_copy(url, timeout_ms, max_body_bytes, redirect_limit=None):
            url = net_i8p(url)
            timeout_ms = net_i64(timeout_ms)
            max_body_bytes = net_i64(max_body_bytes)
            with builder.goto_entry_block():
                body_out = builder.alloca(Int8P, name=f"{call_name}_body_out")
                status_out = builder.alloca(Int64, name=f"{call_name}_status_out")
            builder.store(ir.Constant(Int8P, None), body_out)
            builder.store(ir.Constant(Int64, 0), status_out)
            if redirect_limit is None:
                symbol = "ss_http_client_fetch_text_copy"
                fn = self._runtime_func(
                    symbol,
                    Int32,
                    [Int8P, Int64, Int64, Int8P.as_pointer(), Int64.as_pointer()])
                args = [url, timeout_ms, max_body_bytes, body_out, status_out]
            else:
                redirect_limit = net_i32(redirect_limit)
                symbol = "ss_http_client_fetch_text_request_copy"
                fn = self._runtime_func(
                    symbol,
                    Int32,
                    [Int8P, Int64, Int64, Int32, Int8P.as_pointer(), Int64.as_pointer()])
                args = [
                    url,
                    timeout_ms,
                    max_body_bytes,
                    redirect_limit,
                    body_out,
                    status_out,
                ]
            self.provenance.record_external(symbol, call)
            status = builder.call(fn, args, name=f"{call_name}_status")
            body = builder.load(body_out, name=f"{call_name}_body")
            return status, body, status_out

        if target in {"net.fetchText", "fetchText"}:
            if "request" in call["args"]:
                request_symbol = call["args"]["request"]
                url = net_record_field(request_symbol, "url")
                timeout_ms = net_record_field(request_symbol, "policy.timeoutMillis")
                max_body_bytes = net_record_field(request_symbol, "policy.maxBodyBytes")
                redirect_limit = net_record_field(request_symbol, "policy.redirectLimit")
                status, body, status_out = net_emit_text_copy(
                    url, timeout_ms, max_body_bytes, redirect_limit)
                with builder.goto_entry_block():
                    response_status = builder.alloca(
                        Int32, name=f"{call_name}_response_status")
                    response_body = builder.alloca(
                        Int8P, name=f"{call_name}_response_body")
                builder.store(
                    net_i32(builder.load(status_out, name=f"{call_name}_http_status")),
                    response_status)
                builder.store(body, response_body)
                call["record_result"] = {
                    "type": "HttpTextResponse",
                    "slots": {
                        "status": response_status,
                        "body": response_body,
                    },
                    "field_types": {
                        "status": "HttpClientStatusCode",
                        "body": "HttpClientBodyText",
                    },
                }
                call["result"] = body
                call["error_value"] = status
                call["error_cond"] = builder.icmp_unsigned(
                    "!=", status, ir.Constant(Int32, 0),
                    name=f"{call_name}_is_error")
                return

            url = arg_val_named("url")
            timeout_ms = arg_val_named("timeoutMillis")
            max_body_bytes = arg_val_named("maxBodyBytes")
            status, body, _status_out = net_emit_text_copy(
                url, timeout_ms, max_body_bytes)
            call["result"] = body
            call["error_value"] = status
            call["error_cond"] = builder.icmp_unsigned(
                "!=", status, ir.Constant(Int32, 0),
                name=f"{call_name}_is_error")
            return

        if target in {"net.freeTextBody", "freeTextBody"}:
            body = net_i8p(arg_val_named("body"))
            fn = self._runtime_func("ss_http_client_free_string", VOID, [Int8P])
            self.provenance.record_external("ss_http_client_free_string", call)
            builder.call(fn, [body])
            call["result"] = ir.Constant(Int32, 0)
            return

        if target == "net.fetchBytes":
            # MVP bytes lowering shares the text fetch buffer. The native ABI
            # returns a byte pointer plus a null terminator; callers that need
            # exact binary length should use the lower-level response API once
            # it is surfaced in source.
            url = arg_val_named("url")
            timeout_ms = arg_val_named("timeoutMillis")
            max_body_bytes = arg_val_named("maxBodyBytes")
            if isinstance(url.type, ir.IntType):
                url = builder.inttoptr(url, Int8P)
            if isinstance(timeout_ms.type, ir.IntType) and timeout_ms.type.width != 64:
                timeout_ms = (builder.zext(timeout_ms, Int64)
                              if timeout_ms.type.width < 64
                              else builder.trunc(timeout_ms, Int64))
            if isinstance(max_body_bytes.type, ir.IntType) and max_body_bytes.type.width != 64:
                max_body_bytes = (builder.zext(max_body_bytes, Int64)
                                  if max_body_bytes.type.width < 64
                                  else builder.trunc(max_body_bytes, Int64))
            with builder.goto_entry_block():
                body_out = builder.alloca(Int8P, name=f"{call_name}_body_out")
                status_out = builder.alloca(Int64, name=f"{call_name}_status_out")
            builder.store(ir.Constant(Int8P, None), body_out)
            builder.store(ir.Constant(Int64, 0), status_out)
            fn = self._runtime_func(
                "ss_http_client_fetch_text_copy",
                Int32,
                [Int8P, Int64, Int64, Int8P.as_pointer(), Int64.as_pointer()])
            self.provenance.record_external(
                "ss_http_client_fetch_text_copy", call)
            status = builder.call(
                fn,
                [url, timeout_ms, max_body_bytes, body_out, status_out],
                name=f"{call_name}_status")
            body = builder.load(body_out, name=f"{call_name}_body")
            call["result"] = body
            call["error_value"] = status
            call["error_cond"] = builder.icmp_unsigned(
                "!=", status, ir.Constant(Int32, 0),
                name=f"{call_name}_is_error")
            return

        # External-module fallback: targets that look like a method on an
        # imported module (`http.requestCancellationToken`,
        # `database.openConnection`, `AccountBalanceResponseJsonCodec.encode`,
        # `accountIdPathValidator.validate`, etc.) have no body in this
        # translation unit. Rather than fail codegen, emit a dummy zero result
        # so the surrounding control flow + bind chain still compiles. A real
        # runtime (when wired) would supply the implementation by linking
        # against the named module's exports.
        if "." in target or target in self.prog.validators or target in self.prog.policies:
            zero = ir.Constant(Int64, 0)
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

def _source_rows(prog: Program, verb_name: str):
    for lineno in sorted(prog.source_lines):
        raw = prog.source_lines[lineno]
        toks = tokenize_line(raw)
        if not toks or toks[0] == "#":
            continue
        if toks[0] == verb_name:
            yield lineno, toks[1:]


def _operation_inputs(op: Operation) -> dict:
    inputs = {}
    for verb, args, lineno in op.lines:
        if verb == "input" and len(args) >= 3 and args[0] == op.name:
            inputs[args[1]] = {"type": args[2], "line": lineno}
    return inputs


def _operation_input_sequence(op: Operation) -> list:
    sequence = []
    for verb, args, lineno in op.lines:
        if verb == "input" and len(args) >= 3 and args[0] == op.name:
            sequence.append((args[1], args[2], lineno))
    return sequence


def _operation_call_targets(op: Operation) -> dict:
    targets = {}
    for verb, args, _lineno in op.lines:
        if verb == "call" and len(args) >= 2:
            targets[args[0]] = args[1]
    return targets


def _declared_response_body_forwarders(prog: Program) -> dict:
    forwarders = {}
    for op in prog.operations.values():
        for verb, args, lineno in op.lines:
            if (verb == "responseBodyForwarder" and len(args) >= 2
                    and args[0] == op.name):
                forwarders[op.name] = {"arg": args[1], "line": lineno}
    return forwarders


def _operation_is_response_runtime_binding(op: Operation) -> bool:
    has_runtime_binding_body = False
    has_response_write_effect = False
    for verb, args, _lineno in op.lines:
        if verb == "operationBody" and len(args) >= 2:
            if args[0] == op.name and args[1] == "runtimeBinding":
                has_runtime_binding_body = True
        elif verb == "effect" and len(args) >= 3:
            if (args[0] == op.name
                    and args[1] == "write"
                    and str(args[2]).startswith("http." + "response")):
                has_response_write_effect = True
    return has_runtime_binding_body and has_response_write_effect


def _response_body_writer_slots(prog: Program) -> dict:
    """Return writer target -> response-body argument names.

    Runtime writers expose fixed body slots. User wrappers only become
    response-body writers when they explicitly declare
    `responseBodyForwarder OP ARG` and their body actually forwards ARG to
    an already-known writer. This mirrors semlint's SS3603/SS3615 walk so
    strict compiler mode does not infer hidden wrapper contracts from names.
    """
    slots_by_target = dict(HTTP_RESPONSE_NULLABLE_SLOTS)
    declared = _declared_response_body_forwarders(prog)
    for op_name, claim in declared.items():
        op = prog.operations.get(op_name)
        if op is not None and _operation_is_response_runtime_binding(op):
            slots_by_target[op_name] = frozenset({claim["arg"]})
    changed = True
    while changed:
        changed = False
        for op_name, claim in declared.items():
            if op_name in slots_by_target:
                continue
            op = prog.operations.get(op_name)
            if op is None:
                continue
            call_targets = _operation_call_targets(op)
            claimed_arg = claim["arg"]
            forwards_claim = False
            for verb, args, _lineno in op.lines:
                if verb != "argument" or len(args) < 4:
                    continue
                call_name, arg_name, value_name = args[0], args[1], args[3]
                target = call_targets.get(call_name)
                accepted_slots = slots_by_target.get(target)
                if (accepted_slots is not None
                        and arg_name in accepted_slots
                        and value_name == claimed_arg):
                    forwards_claim = True
                    break
            if forwards_claim:
                slots_by_target[op_name] = frozenset({claimed_arg})
                changed = True
    return slots_by_target


def _operation_has_null_body_opt_out(op: Operation) -> bool:
    for verb, args, _lineno in op.lines:
        if verb == "pinsNullBodyFailurePath" and args and args[0] == op.name:
            return True
        if verb == "warning" and len(args) >= 2 and args[0] == op.name:
            warning_text = " ".join(str(_unwrap(arg)) for arg in args[1:])
            if any(marker in warning_text
                   for marker in LEGACY_HTTP_NULL_GUARD_OPT_OUT_MARKERS):
                return True
    return False


def _check_http_route_methods(prog: Program, diags):
    allowed = ", ".join(sorted(HTTP_METHOD_WHITELIST))
    for lineno, args in _source_rows(prog, "route"):
        if len(args) < 4:
            continue
        method = args[1]
        if is_supported_route_method(method):
            continue
        diags.append((lineno,
            f"SS3601 invalidRouteMethod: route method `{method}` is not "
            f"supported by the native HTTP dispatcher; expected one of {allowed}"))


def _check_http_route_handler_input_shape(prog: Program, diags):
    binding_sites = {}
    for lineno, args in _source_rows(prog, "route"):
        if len(args) >= 4:
            binding_sites.setdefault(args[3], []).append(lineno)
    for lineno, args in _source_rows(prog, "routeNotFound"):
        if len(args) >= 2:
            binding_sites.setdefault(args[1], []).append(lineno)
    for lineno, args in _source_rows(prog, "routeMethodNotAllowed"):
        if len(args) >= 2:
            binding_sites.setdefault(args[1], []).append(lineno)
    for lineno, args in _source_rows(prog, "routeMiddleware"):
        if len(args) >= 3:
            binding_sites.setdefault(args[2], []).append(lineno)

    expected = [("request", "HttpRequest"), ("response", "HttpResponse")]
    for op_name, lines in sorted(binding_sites.items()):
        op = prog.operations.get(op_name)
        if op is None:
            continue
        carried_inputs = [
            (name, typ, lineno)
            for name, typ, lineno in _operation_input_sequence(op)
            if name not in OPAQUE_INPUTS
        ]
        actual_shape = [(name, typ) for name, typ, _line in carried_inputs]
        if actual_shape == expected:
            continue
        primary_line = carried_inputs[0][2] if carried_inputs else lines[0]
        rendered = ", ".join(
            f"{name}:{typ}" for name, typ, _line in carried_inputs
        ) or "<none>"
        diags.append((primary_line,
            f"SS3609 routeHandlerInputNameMismatch: route-bound operation "
            f"`{op_name}` must declare exactly `input {op_name} request "
            f"HttpRequest` then `input {op_name} response HttpResponse` "
            f"for the native HTTP ABI; found {rendered}"))


def _check_http_middleware_output_contract(prog: Program, diags):
    middleware_ops = set()
    for _lineno, args in _source_rows(prog, "routeMiddleware"):
        if len(args) >= 3:
            middleware_ops.add(args[2])
    for op_name in sorted(middleware_ops):
        op = prog.operations.get(op_name)
        if op is None:
            continue
        contract = _operation_output_contract(prog, op)
        if contract.problem:
            continue
        if contract.ok_type == "MiddlewareControl":
            continue
        diags.append((contract.line,
            f"SS3610 middlewareReturnNotMiddlewareControl: middleware "
            f"`{op_name}` returns `{contract.ok_type}`, but every operation "
            f"bound via `routeMiddleware` must declare `output {op_name} "
            f"MiddlewareControl` so continue/short-circuit semantics are "
            f"type checked"))


def _check_http_nullable_response_inputs(prog: Program, diags):
    slots_by_writer = _response_body_writer_slots(prog)
    for op in prog.operations.values():
        call_targets = _operation_call_targets(op)
        nullable_binds = {}
        for verb, args, lineno in op.lines:
            if verb != "bind" or len(args) < 4 or args[0] not in ("value", "ok"):
                continue
            call_name = args[3]
            if call_targets.get(call_name) in NULLABLE_HTTP_REQUEST_READS:
                nullable_binds[args[1]] = lineno
        if not nullable_binds or _operation_has_null_body_opt_out(op):
            continue

        guarded = set()
        pointer_is_null_calls = set()
        for verb, args, lineno in op.lines:
            if verb == "call" and len(args) >= 2 and args[1] == "pointer.isNull":
                pointer_is_null_calls.add(args[0])
                continue
            if (verb == "argument" and len(args) >= 4
                    and args[0] in pointer_is_null_calls
                    and args[1] == "pointer"
                    and args[3] in nullable_binds):
                guarded.add(args[3])
                continue
            if verb != "argument" or len(args) < 4:
                continue
            call_name, arg_name, value_name = args[0], args[1], args[3]
            target = call_targets.get(call_name)
            accepted_slots = slots_by_writer.get(target)
            if (accepted_slots is not None
                    and arg_name in accepted_slots
                    and value_name in nullable_binds
                    and value_name not in guarded):
                diags.append((lineno,
                    f"SS3603 unguardedHttpInput: nullable HTTP request value "
                    f"`{value_name}` reaches `{target}` argument `{arg_name}` "
                    f"without a preceding `pointer.isNull` guard"))


def _check_http_response_body_forwarders(prog: Program, diags):
    slots_by_writer = _response_body_writer_slots(prog)
    declared = _declared_response_body_forwarders(prog)
    for op_name, claim in sorted(declared.items()):
        if op_name in slots_by_writer:
            continue
        diags.append((claim["line"],
            f"SS3607 forwarderDeclarationNotHonored: "
            f"`responseBodyForwarder {op_name} {claim['arg']}` is not backed "
            f"by an `argument <writerCall> <body-slot> <type> {claim['arg']}` flow into "
            f"a known response body writer or declared forwarder"))

    declared_ops = set(declared)
    for op in prog.operations.values():
        inputs = _operation_inputs(op)
        if not inputs:
            continue
        call_targets = _operation_call_targets(op)
        for verb, args, lineno in op.lines:
            if verb != "argument" or len(args) < 4:
                continue
            call_name, arg_name, value_name = args[0], args[1], args[3]
            target = call_targets.get(call_name)
            accepted_slots = slots_by_writer.get(target)
            if accepted_slots is None or arg_name not in accepted_slots:
                continue
            if value_name not in inputs:
                continue
            if (op.name in declared
                    and declared[op.name]["arg"] == value_name):
                continue
            if op.name in declared_ops:
                continue
            diags.append((lineno,
                f"SS3615 responseBodyForwarderMissing: operation `{op.name}` "
                f"forwards input `{value_name}` to response body writer "
                f"`{target}`; declare `responseBodyForwarder {op.name} "
                f"{value_name}` so nullable request values are checked "
                f"through the wrapper"))


def _check_http_contracts(prog: Program, diags):
    _check_http_route_methods(prog, diags)
    _check_http_route_handler_input_shape(prog, diags)
    _check_http_middleware_output_contract(prog, diags)
    _check_http_response_body_forwarders(prog, diags)
    _check_http_nullable_response_inputs(prog, diags)


def _strict_raise_first_http_contract(prog: Program, diags):
    if not diags:
        return
    lineno, message = sorted(diags)[0]
    code_match = re.match(r"(SS\d+)", message)
    code = code_match.group(1) if code_match else "SS3600"
    span = _strict_span(prog, lineno)
    raise CompilerDiagnosticError(CompilerDiagnostic(
        code=code,
        phase="semantic.strictExecutable",
        message=message,
        primary=span,
        semantic_stack=[
            DiagnosticFrame(
                kind="strictExecutable HTTP contract validation",
                span=span,
                note=(
                    "native HTTP route, middleware, nullable, and response "
                    "forwarding contracts are compile-blocking in "
                    "strictExecutable mode"
                ),
            ),
        ],
        direction=(
            "`languageMode strictExecutable` requires native HTTP metadata "
            "to match the executable dispatcher ABI. Fix the route/middleware "
            "shape or add the explicit response forwarding/nullability "
            "contract named by the diagnostic."
        ),
    ))


def _strict_raise_first_fallible_contract(prog: Program, diags):
    if not diags:
        return
    lineno, message = sorted(diags)[0]
    span = _strict_span(prog, lineno)
    raise CompilerDiagnosticError(CompilerDiagnostic(
        code="SS3201",
        phase="semantic.strictExecutable",
        message=message,
        primary=span,
        semantic_stack=[
            DiagnosticFrame(
                kind="strictExecutable fallible-call validation",
                span=span,
                note=(
                    "known fallible calls require executable success and "
                    "failure disposition in strictExecutable mode"
                ),
            ),
        ],
        direction=(
            "`languageMode strictExecutable` rejects plain `run` for known "
            "fallible targets. Use `runChecked`, or the explicit "
            "`run` + `bind ok`/`ignore ok`/`ignore void` + `bind error` "
            "+ `branch error` "
            "shape."
        ),
    ))


def _strict_span(prog: Program, lineno: int, role: str = "primary") -> DiagnosticSpan:
    return DiagnosticSpan(
        path=prog.source_path or "<source>",
        line=lineno or 0,
        column=1,
        raw=prog.source_lines.get(lineno, ""),
        role=role,
    )


def _strict_target(prog: Program, target: str) -> str:
    canonical = _TARGET_ALIASES.get(target, target)
    return prog.operation_aliases.get(canonical, canonical)


def _strict_raise(
    prog: Program,
    code: str,
    message: str,
    op: Operation,
    lineno: int,
    *,
    call_name: str = "",
    call_target: str = "",
    note: str = "",
    suggested_fixes: list | None = None,
) -> None:
    span = _strict_span(prog, lineno)
    raise CompilerDiagnosticError(CompilerDiagnostic(
        code=code,
        phase="semantic.strictExecutable",
        message=message,
        primary=span,
        semantic_stack=[
            DiagnosticFrame(
                kind="strictExecutable owned-resource validation",
                operation=op.name,
                call_name=call_name,
                call_target=call_target,
                span=span,
                note=note,
            ),
        ],
        direction=(
            "`languageMode strictExecutable` makes ownership and failure "
            "cleanup compile-blocking. The compiler only accepts resource "
            "lifetimes it can see in executable control flow."
        ),
        suggested_fixes=suggested_fixes or [],
    ))


def _strict_collect_calls(prog: Program, op: Operation) -> dict:
    calls = {}
    for verb, args, lineno in op.lines:
        if verb == "call" and len(args) >= 2:
            calls[args[0]] = {
                "name": args[0],
                "target": _strict_target(prog, args[1]),
                "line": lineno,
                "args": [],
                "binds": [],
                "bind_oks": [],
                "bind_errors": [],
                "branch_errors": [],
            }
            continue
        if not args:
            continue
        if verb == "argument" and len(args) >= 4 and args[0] in calls:
            calls[args[0]]["args"].append((args[1], args[3], lineno))
        elif verb == "bind" and len(args) >= 4 and args[3] in calls:
            if args[0] == "value":
                calls[args[3]]["binds"].append((args[1], args[2], lineno))
            elif args[0] == "ok":
                calls[args[3]]["bind_oks"].append((args[1], args[2], lineno))
            elif args[0] == "error":
                calls[args[3]]["bind_errors"].append((args[1], args[2], lineno))
        elif (verb == "branch" and len(args) >= 5 and args[0] == "error"
              and args[2] in calls):
            label = args[4]
            calls[args[2]]["branch_errors"].append((label, lineno))
        elif verb == "runChecked" and len(args) == 9 and args[0] in calls:
            call_info = calls[args[0]]
            call_info["bind_oks"].append((args[2], args[3], lineno))
            call_info["bind_errors"].append((args[5], args[6], lineno))
            call_info["branch_errors"].append((args[8], lineno))
    return calls


def _strict_success_names(call_info: dict) -> set:
    return {
        name
        for name, _typ, _line in (
            list(call_info.get("binds", []))
            + list(call_info.get("bind_oks", []))
        )
    }


def _strict_call_arg_value(call_info: dict, arg_name: str) -> str | None:
    value = None
    for candidate_name, candidate_value, _line in call_info.get("args", []):
        if candidate_name == arg_name:
            value = candidate_value
    return value


def _strict_call_consumes_any(call_info: dict, names: set) -> bool:
    return any(value_name in names
               for _arg_name, value_name, _line in call_info.get("args", []))


def _strict_cleanup_calls(calls: dict, cleanup_targets: set, names: set,
                          after_line: int = 0) -> list:
    matches = []
    for cleanup_call in calls.values():
        if cleanup_call["target"] not in cleanup_targets:
            continue
        if cleanup_call["line"] <= after_line:
            continue
        if _strict_call_consumes_any(cleanup_call, names):
            matches.append(cleanup_call)
    return matches


def _strict_collect_defers(op: Operation) -> list:
    defers = []
    by_name = {}
    for verb, args, lineno in op.lines:
        if verb in ("defer", "deferLog", "deferAwaitLog") and len(args) >= 2:
            entry = {
                "name": args[0],
                "target": args[1],
                "args": list(args[2:]),
                "line": lineno,
                "run_on": set(),
            }
            defers.append(entry)
            by_name[args[0]] = entry
        elif verb == "deferWhenExitLog" and len(args) >= 3:
            entry = {
                "name": args[0],
                "target": args[2],
                "args": list(args[3:]),
                "line": lineno,
                "run_on": set(),
            }
            defers.append(entry)
            by_name[args[0]] = entry
        elif verb == "deferRunOn" and len(args) >= 2:
            entry = by_name.get(args[0])
            if entry is not None:
                entry["run_on"].add(args[1])
    for entry in defers:
        if not entry["run_on"]:
            entry["run_on"] = {"all"}
    return defers


def _strict_defer_is_all_paths(defer_info: dict) -> bool:
    return bool(defer_info.get("run_on", set()) & {"all", "always"})


def _strict_first_cleanup_line(calls: dict, defers: list, cleanup_targets: set,
                               names: set, after_line: int = 0,
                               *, accept_defers: bool) -> int | None:
    lines = [
        call_info["line"]
        for call_info in _strict_cleanup_calls(
            calls, cleanup_targets, names, after_line)
    ]
    if accept_defers:
        for defer_info in defers:
            if defer_info["target"] not in cleanup_targets:
                continue
            if defer_info["line"] <= after_line:
                continue
            if not _strict_defer_is_all_paths(defer_info):
                continue
            if any(arg in names for arg in defer_info["args"]):
                lines.append(defer_info["line"])
    return min(lines) if lines else None


def _strict_label_body_lines(op: Operation, label_name: str) -> list:
    label_index = None
    for index, (verb, args, _lineno) in enumerate(op.lines):
        if verb == "label" and args and args[0] == label_name:
            label_index = index
            break
    if label_index is None:
        return []
    body = []
    for entry in op.lines[label_index + 1:]:
        verb, _args, _lineno = entry
        if verb == "label":
            break
        body.append(entry)
    return body


def _strict_label_has_cleanup(prog: Program, op: Operation, label_name: str,
                              cleanup_targets: set, names: set) -> bool:
    label_op = Operation(op.name, op.decl_line)
    label_op.lines = _strict_label_body_lines(op, label_name)
    if not label_op.lines:
        return False
    label_calls = _strict_collect_calls(prog, label_op)
    return bool(_strict_cleanup_calls(label_calls, cleanup_targets, names))


def _strict_transfer_line(op: Operation, names: set, after_line: int = 0) -> int | None:
    for verb, args, lineno in op.lines:
        if lineno <= after_line:
            continue
        if verb == "return" and len(args) >= 2 and args[0] in ("ok", "value") and args[1] in names:
            return lineno
        if verb == "set" and args and args[-1] in names:
            return lineno
    return None


def _strict_output_success_type(op: Operation) -> str | None:
    for verb, args, _lineno in op.lines:
        if verb != "output" or len(args) < 2 or args[0] != op.name:
            continue
        if args[1] == "Result" and len(args) >= 3:
            return args[2]
        return args[1]
    return None


def _strict_validate_heap_resources(prog: Program, op: Operation,
                                    calls: dict, defers: list) -> None:
    del defers  # c.free defers are metadata today; strict mode requires calls.
    owned_by_name = {}
    for call_info in calls.values():
        if call_info["target"] not in _STRICT_HEAP_ALLOCATION_TARGETS:
            continue
        names = _strict_success_names(call_info)
        if not call_info["bind_errors"] or not call_info["branch_errors"]:
            _strict_raise(
                prog,
                "SS3305",
                f"SS3305 uncheckedHeapAllocation: `{call_info['name']}` "
                f"targets `{call_info['target']}` without an executable OOM "
                "branch",
                op,
                call_info["line"],
                call_name=call_info["name"],
                call_target=call_info["target"],
                note="heap allocations must bind and branch on allocation failure",
                suggested_fixes=[
                    f"Add `bindError <errorName> <ErrorType> {call_info['name']}`.",
                    f"Add `branchIfError {call_info['name']} <allocationFailedLabel>`.",
                ],
            )
        if not names:
            _strict_raise(
                prog,
                "SS3305",
                f"SS3305 uncheckedHeapAllocation: `{call_info['name']}` "
                "does not bind its successful heap pointer",
                op,
                call_info["line"],
                call_name=call_info["name"],
                call_target=call_info["target"],
                note="strict resource tracking needs a named owned pointer",
            )
        for name in names:
            owned_by_name[name] = call_info
        cleanup_line = _strict_first_cleanup_line(
            calls, [], _STRICT_HEAP_CLEANUP_TARGETS, names,
            call_info["line"], accept_defers=False)
        transfer_line = _strict_transfer_line(
            op, names, call_info["line"])
        if cleanup_line is None and transfer_line is None:
            _strict_raise(
                prog,
                "SS3303",
                f"SS3303 resourceLifecycle.allocateFreeUnpaired: "
                f"`{call_info['name']}` allocates heap memory without an "
                "executable `c.free` cleanup call",
                op,
                call_info["line"],
                call_name=call_info["name"],
                call_target=call_info["target"],
                note="`defer ... c.free` is metadata-only in this backend",
                suggested_fixes=[
                    "Add an explicit `call <freeCall> c.free` path before every return.",
                    "Add explicit `c.free` cleanup in later failure labels before returning.",
                ],
            )
        # When ownership transfers to the caller (returnOk / returnValue
        # of the owned pointer), failure paths reachable before that
        # transfer still need explicit cleanup. The original heap check
        # used `cleanup_line` exclusively; we now bound the failure-
        # branch scan with whichever appears first.
        boundary_lines = [
            line for line in (cleanup_line, transfer_line)
            if line is not None
        ]
        boundary_line = min(boundary_lines) if boundary_lines else 0
        for verb, args, lineno in op.lines:
            if lineno <= call_info["line"]:
                continue
            if boundary_line and lineno >= boundary_line:
                continue
            if verb != "branch" or len(args) < 5 or args[0] != "error":
                continue
            if args[2] == call_info["name"]:
                continue
            failure_label = args[4]
            if _strict_label_has_cleanup(
                    prog, op, failure_label,
                    _STRICT_HEAP_CLEANUP_TARGETS, names):
                continue
            _strict_raise(
                prog,
                "SS3303",
                f"SS3303 resourceLifecycle.allocateFreeUnpaired: "
                f"`{call_info['name']}` heap pointer can reach failure label "
                f"`{failure_label}` before `c.free`",
                op,
                lineno,
                call_name=call_info["name"],
                call_target=call_info["target"],
                note="failure labels after heap acquisition must release the owned pointer",
            )

    released_in_segment = set()
    for verb, args, _lineno in op.lines:
        if verb == "label":
            released_in_segment = set()
            continue
        if verb == "call" and args:
            call_info = calls.get(args[0])
            if (call_info is not None
                    and call_info["target"] in _STRICT_HEAP_CLEANUP_TARGETS):
                consumed = {
                    value_name
                    for _arg_name, value_name, _line in call_info.get("args", [])
                    if value_name in owned_by_name
                }
                for value_name in consumed:
                    if value_name in released_in_segment:
                        producer = owned_by_name[value_name]
                        _strict_raise(
                            prog,
                            "SS3307",
                            f"SS3307 resourceLifecycle.heapDoubleFree: "
                            f"`{value_name}` is released more than once on "
                            "the same strictExecutable path",
                            op,
                            call_info["line"],
                            call_name=call_info["name"],
                            call_target=call_info["target"],
                            note=f"first owner was produced by `{producer['name']}`",
                        )
                    released_in_segment.add(value_name)
        if verb in ("returnOk", "returnError", "returnValue", "returnVoid", "branch"):
            released_in_segment = set()


def _strict_validate_sqlite_database_cleanup(prog: Program, op: Operation,
                                             calls: dict, defers: list) -> None:
    for open_call in calls.values():
        if open_call["target"] not in _STRICT_SQLITE_DATABASE_OPEN_TARGETS:
            continue
        database_names = _strict_success_names(open_call)
        if not database_names:
            continue
        transfer_line = _strict_transfer_line(
            op, database_names, open_call["line"])
        cleanup_line = _strict_first_cleanup_line(
            calls, defers, _STRICT_SQLITE_DATABASE_CLOSE_TARGETS,
            database_names, open_call["line"], accept_defers=True)
        if transfer_line is None and cleanup_line is None:
            _strict_raise(
                prog,
                "SS3905",
                f"SS3905 resourceLifecycle.sqliteDatabaseFailureCleanupMissing: "
                f"`{open_call['name']}` opens a SQLite database without "
                "close or ownership transfer",
                op,
                open_call["line"],
                call_name=open_call["name"],
                call_target=open_call["target"],
                note="strict mode requires a close call, lowered close defer, set, or return transfer",
            )
        stop_line = min(
            line for line in (transfer_line, cleanup_line)
            if line is not None
        ) if (transfer_line is not None or cleanup_line is not None) else None
        for verb, args, lineno in op.lines:
            if lineno <= open_call["line"]:
                continue
            if stop_line is not None and lineno >= stop_line:
                continue
            if verb != "branch" or len(args) < 5 or args[0] != "error":
                continue
            if args[2] == open_call["name"]:
                continue
            failure_label = args[4]
            if _strict_label_has_cleanup(
                    prog, op, failure_label,
                    _STRICT_SQLITE_DATABASE_CLOSE_TARGETS, database_names):
                continue
            _strict_raise(
                prog,
                "SS3905",
                f"SS3905 resourceLifecycle.sqliteDatabaseFailureCleanupMissing: "
                f"`{open_call['name']}` database handle can reach failure "
                f"label `{failure_label}` without `sqlite.closeDatabase`",
                op,
                lineno,
                call_name=open_call["name"],
                call_target=open_call["target"],
                note="SQLite setup failures after open must close the fresh handle",
            )


def _strict_validate_sqlite_statement_cleanup(prog: Program, op: Operation,
                                             calls: dict, defers: list) -> None:
    output_success_type = _strict_output_success_type(op)
    for prepare_call in calls.values():
        if prepare_call["target"] not in _STRICT_SQLITE_STATEMENT_PREPARE_TARGETS:
            continue
        statement_names = _strict_success_names(prepare_call)
        if not statement_names:
            continue
        cleanup_line = _strict_first_cleanup_line(
            calls, defers, _STRICT_SQLITE_STATEMENT_FINALIZE_TARGETS,
            statement_names, prepare_call["line"], accept_defers=True)
        output_transfers_statement = output_success_type == "SqliteStatement"
        if cleanup_line is None and not output_transfers_statement:
            _strict_raise(
                prog,
                "SS3906",
                f"SS3906 resourceLifecycle.sqliteStatementFinalizeMissing: "
                f"`{prepare_call['name']}` prepares a SQLite statement "
                "without `sqlite.finalizeStatement`",
                op,
                prepare_call["line"],
                call_name=prepare_call["name"],
                call_target=prepare_call["target"],
                note="prepared statements must be finalized by call or lowered SQLite defer",
                suggested_fixes=[
                    "Add `defer <name> sqlite.finalizeStatement <statement>` after the successful prepare.",
                    "Or add an explicit `sqlite.finalizeStatement` call on every exit path.",
                ],
            )
        if cleanup_line is None:
            continue
        for verb, args, lineno in op.lines:
            if lineno <= prepare_call["line"] or lineno >= cleanup_line:
                continue
            if verb != "branch" or len(args) < 5 or args[0] != "error":
                continue
            if args[2] == prepare_call["name"]:
                continue
            failure_label = args[4]
            if _strict_label_has_cleanup(
                    prog, op, failure_label,
                    _STRICT_SQLITE_STATEMENT_FINALIZE_TARGETS, statement_names):
                continue
            _strict_raise(
                prog,
                "SS3906",
                f"SS3906 resourceLifecycle.sqliteStatementFinalizeMissing: "
                f"`{prepare_call['name']}` statement can reach failure label "
                f"`{failure_label}` before finalize",
                op,
                lineno,
                call_name=prepare_call["name"],
                call_target=prepare_call["target"],
                note="failure labels after prepare must finalize the owned statement",
            )


def _strict_collect_constant_string_names(prog: Program,
                                          op: Operation = None) -> set:
    names = set()
    for name, (typ, _value) in prog.consts.items():
        if resolve_alias(prog, typ) != "String":
            continue
        if name in prog.mutable_globals:
            continue
        names.add(name)
    if op is not None:
        for name, (typ, _value) in op.consts.items():
            if resolve_alias(prog, typ) == "String":
                names.add(name)
        for verb, args, _lineno in op.lines:
            if verb != "storage" or len(args) < 4:
                continue
            if args[0] != "local" or args[1] != "immutable":
                continue
            if resolve_alias(prog, args[3]) != "String":
                continue
            names.add(args[2])
    return names


def _strict_call_target_map(op: Operation) -> dict:
    targets = {}
    for verb, args, lineno in op.lines:
        if verb == "call" and len(args) >= 2:
            targets[args[0]] = (args[1], lineno)
    return targets


def _strict_argument_parts(verb: str, args: list):
    if verb == "argument" and len(args) >= 4:
        return args[0], args[1], args[3]
    if verb == "arg" and len(args) >= 3:
        return args[0], args[1], args[2]
    return None


def _strict_raise_first_simple(prog: Program, diags, default_code: str,
                               phase_note: str, direction: str) -> None:
    if not diags:
        return
    lineno, message = sorted(diags)[0]
    code_match = re.match(r"(SS\d+)", message)
    diag_code = code_match.group(1) if code_match else default_code
    span = _strict_span(prog, lineno)
    raise CompilerDiagnosticError(CompilerDiagnostic(
        code=diag_code,
        phase="semantic.strictExecutable",
        message=message,
        primary=span,
        semantic_stack=[
            DiagnosticFrame(
                kind=phase_note,
                span=span,
                note=(
                    "`languageMode strictExecutable` holds this source to "
                    "the executable contract wall"
                ),
            ),
        ],
        direction=direction,
    ))


def _strict_branch_else_targets_by_line(op: Operation) -> dict:
    branch_else_by_line = {}
    for index, (verb, args, lineno) in enumerate(op.lines[:-1]):
        if verb != "branch" or not args or args[0] not in ("if", "error"):
            continue
        next_verb, next_args, _next_lineno = op.lines[index + 1]
        if (next_verb == "branch" and len(next_args) >= 3
                and next_args[:2] == ["else", "target"]):
            branch_else_by_line[lineno] = next_args[2]
    return branch_else_by_line


def _strict_reachable_line_numbers(op: Operation) -> set:
    if not op.lines:
        return set()
    branch_else_by_line = _strict_branch_else_targets_by_line(op)
    label_indices = {
        args[0]: index
        for index, (verb, args, _lineno) in enumerate(op.lines)
        if verb == "label" and args
    }

    def add_label_successor(successors, label_name):
        target_index = label_indices.get(label_name)
        if target_index is not None:
            successors.append(target_index)

    def add_fallthrough_successor(successors, index):
        next_index = index + 1
        if next_index < len(op.lines):
            successors.append(next_index)

    def successor_indices(index):
        verb, args, lineno = op.lines[index]
        successors = []
        if verb == "await":
            cursor = index + 1
            found_wait_set = False
            while cursor < len(op.lines):
                candidate_verb, candidate_args, _candidate_lineno = op.lines[cursor]
                if candidate_verb in {"__typedComment__", "__groupAnchor__"}:
                    cursor += 1
                    continue
                if candidate_verb == "case":
                    found_wait_set = True
                    successors.append(cursor)
                    cursor += 1
                    continue
                if candidate_verb == "done":
                    found_wait_set = True
                    successors.append(cursor)
                    break
                break
            if found_wait_set:
                return successors
        if verb == "case" and len(args) >= 2:
            add_label_successor(successors, args[1])
            return successors
        if verb == "done" and args:
            add_label_successor(successors, args[0])
            return successors
        if verb in {"return", "returnOk", "returnError", "returnVoid"}:
            return successors
        if verb == "jump" and len(args) >= 2 and args[0] == "target":
            add_label_successor(successors, args[1])
            return successors
        if verb == "branch":
            if len(args) >= 5 and args[0] in {"if", "error"} and args[3] == "target":
                add_label_successor(successors, args[4])
                else_label = branch_else_by_line.get(lineno)
                if else_label is None:
                    add_fallthrough_successor(successors, index)
                else:
                    add_label_successor(successors, else_label)
                return successors
            if len(args) >= 3 and args[0] == "else" and args[1] == "target":
                add_label_successor(successors, args[2])
                return successors
            if args:
                add_label_successor(successors, args[0])
                add_fallthrough_successor(successors, index)
                return successors
        if verb == "branchIf" and len(args) >= 2:
            add_label_successor(successors, args[1])
            if len(args) >= 3:
                add_label_successor(successors, args[2])
            else:
                add_fallthrough_successor(successors, index)
            return successors
        if (verb in {"branchIfError", "branchIfGroupError", "branchIfChannelClosed"}
                and len(args) >= 2):
            add_label_successor(successors, args[1])
            add_fallthrough_successor(successors, index)
            return successors
        if verb == "runChecked" and len(args) >= 9:
            add_label_successor(successors, args[8])
            add_fallthrough_successor(successors, index)
            return successors
        if verb == "branchSelected" and len(args) >= 3:
            add_label_successor(successors, args[2])
            add_fallthrough_successor(successors, index)
            return successors
        add_fallthrough_successor(successors, index)
        return successors

    reachable_indices = set()
    stack = [0]
    while stack:
        current_index = stack.pop()
        if current_index in reachable_indices:
            continue
        reachable_indices.add(current_index)
        stack.extend(successor_indices(current_index))
    return {op.lines[index][2] for index in reachable_indices}


def _check_strict_unreachable_operation_rows(prog: Program, diags) -> None:
    """SS3410 - strict executable code rejects dead operation rows because
    they inflate generated IR and hide stale resource/SQL paths from agents.
    """
    for op_name, op in prog.operations.items():
        reachable = _strict_reachable_line_numbers(op)
        for verb, args, lineno in op.lines:
            if lineno in reachable:
                continue
            if verb in {"__typedComment__", "__groupAnchor__"}:
                continue
            subject = args[0] if args else verb
            diags.append((lineno,
                f"SS3410 unreachableOperationRow: operation `{op_name}` "
                f"contains unreachable `{verb}` row `{subject}`; remove "
                "the stale block or route control flow to it with an "
                "explicit branch/jump"))
            break


def _strict_raise_first_reachability(prog: Program, diags) -> None:
    _strict_raise_first_simple(
        prog, diags, "SS3410",
        "strictExecutable control-flow reachability validation",
        "Strict executable requires operation rows to be reachable from "
        "the operation entry. Dead blocks waste generated code and often "
        "hide obsolete resource, SQL, or response paths.",
    )


def _check_strict_forbidden_call_targets(prog: Program, diags) -> None:
    """SS3313 — reject stdlib targets that have no bounded form (strcat,
    strcpy, sprintf, gets, strncat)."""
    for op_name, op in prog.operations.items():
        for verb, args, lineno in op.lines:
            if verb != "call" or len(args) < 2:
                continue
            call_name, target = args[0], args[1]
            canonical = _strict_target(prog, target)
            advice = (
                _STRICT_FORBIDDEN_CALL_TARGETS_WITH_ADVICE.get(canonical)
                or _STRICT_FORBIDDEN_CALL_TARGETS_WITH_ADVICE.get(target)
            )
            if advice is None:
                continue
            diags.append((lineno,
                f"SS3313 forbiddenUnsafeCallTarget: operation `{op_name}` "
                f"declares `call {call_name} {target}`, which has no "
                f"bounded form; {advice}"))


def _strict_raise_first_forbidden_target(prog: Program, diags) -> None:
    _strict_raise_first_simple(
        prog, diags, "SS3313",
        "strictExecutable forbidden call-target validation",
        "Strict executable (the default) rejects unsafe stdlib targets "
        "that have no bounded form. Migrate to the bounded variant the "
        "diagnostic names.",
    )


def _check_strict_insecure_random(prog: Program, diags) -> None:
    """SS4601 — reject non-cryptographic PRNG targets (c.rand/c.srand/c.random,
    CWE-338). Predictable randomness must never back security-sensitive values."""
    for op_name, op in prog.operations.items():
        for verb, args, lineno in op.lines:
            if verb != "call" or len(args) < 2:
                continue
            call_name, target = args[0], args[1]
            canonical = _strict_target(prog, target)
            advice = (_STRICT_INSECURE_RANDOM_TARGETS.get(canonical)
                      or _STRICT_INSECURE_RANDOM_TARGETS.get(target))
            if advice is None:
                continue
            diags.append((lineno,
                f"SS4601 insecurePseudoRandom: operation `{op_name}` declares "
                f"`call {call_name} {target}`, a non-cryptographic PRNG "
                f"(CWE-338); {advice}"))


def _strict_raise_first_insecure_random(prog: Program, diags) -> None:
    if not diags:
        return
    lineno, message = sorted(diags)[0]
    span = _strict_span(prog, lineno)
    raise CompilerDiagnosticError(CompilerDiagnostic(
        code="SS4601",
        phase="semantic.strictExecutable",
        message=message,
        primary=span,
        semantic_stack=[
            DiagnosticFrame(
                kind="strictExecutable insecure-random validation",
                span=span,
                note=("`languageMode strictExecutable` forbids predictable "
                      "pseudo-random sources for any value"),
            ),
        ],
        direction=("Strict executable rejects the non-cryptographic libc PRNG "
                   "family (rand/srand/random/drand48/...); predictable "
                   "randomness is a CWE-338 vulnerability when it backs tokens, "
                   "keys, nonces, or salts."),
        suggested_fixes=["fill a buffer with `bcrypt.randomBytes` (platform "
                         "CSPRNG) and derive the value from those bytes"],
        agent_hint=("libc rand/srand/random are deterministic generators; use "
                    "`bcrypt.randomBytes` for anything security-sensitive"),
    ))


# bcrypt password-hash work-factor floor (CWE-916). `bcrypt.hashPassword` is by
# definition password hashing; a cost below this floor is brute-forceable. The
# module's `bcryptRecommendedCost` is 12; the OWASP-ASVS floor is 10.
#
_STRICT_PASSWORD_HASH_TARGET = "bcrypt.hashPassword"
_STRICT_SECURE_BCRYPT_COST_FLOOR = 10


def _is_bcrypt_hash_target(prog: Program, raw_target: str) -> bool:
    """True iff a call target is the bcrypt.hashPassword intrinsic, in either its
    qualified (`bcrypt.hashPassword`) or singular-import-flattened (bare
    `hashPassword`) spelling — but NOT a user operation literally named
    `hashPassword` (which lives in `prog.operations`). Matching only the
    qualified form (the iteration-4 false-positive fix) silently missed the bare
    form that import flattening produces, leaving SS4602 inert on the normal
    imported-bcrypt path; this restores it without re-introducing the FP."""
    for candidate in (raw_target, _strict_target(prog, raw_target)):
        if candidate == "bcrypt.hashPassword":
            return True
        if candidate == "hashPassword" and "hashPassword" not in prog.operations:
            return True
    return False


def _check_strict_weak_password_hash_cost(prog: Program, diags) -> None:
    """SS4602 — `bcrypt.hashPassword` must declare an explicit, adequate work
    factor (CWE-916). Flags both a missing `cost` argument (which otherwise
    slips past validation and only fails later as an opaque codegen error) and a
    provable constant cost below the security floor."""
    for op_name, op in prog.operations.items():
        constants = _strict_operation_int_constants(prog, op)
        call_targets = _strict_call_target_map(op)
        cost_value_by_call = {}
        cost_line_by_call = {}
        for verb, args, lineno in op.lines:
            arg_parts = _strict_argument_parts(verb, args)
            if arg_parts is not None and arg_parts[1] == "cost":
                cost_value_by_call[arg_parts[0]] = arg_parts[2]
                cost_line_by_call[arg_parts[0]] = lineno
        for call_name, (raw_target, call_line) in call_targets.items():
            if not _is_bcrypt_hash_target(prog, raw_target):
                continue
            cost_value = cost_value_by_call.get(call_name)
            if cost_value is None:
                # Missing `cost` — closes the evasion where omitting the arg
                # skipped this check entirely. (Codegen would still reject the
                # malformed call with a coded SSCG002, but only after passing
                # validation; this is the earlier, CWE-tagged security signal,
                # and via the security floor it blocks the default build too.)
                diags.append((call_line,
                    f"SS4602 weakPasswordHashCost: in operation `{op_name}`, call "
                    f"`{call_name}` (bcrypt.hashPassword) is missing the required "
                    f"`cost` argument; bcrypt needs an explicit work factor "
                    f"(use `bcryptRecommendedCost` = 12, CWE-916)."))
                continue
            resolved = _strict_resolve_int(cost_value, constants)
            if resolved is None or resolved >= _STRICT_SECURE_BCRYPT_COST_FLOOR:
                continue
            diags.append((cost_line_by_call[call_name],
                f"SS4602 weakPasswordHashCost: in operation `{op_name}`, call "
                f"`{call_name}` (bcrypt.hashPassword) uses cost {resolved}, below "
                f"the security floor of {_STRICT_SECURE_BCRYPT_COST_FLOOR} "
                f"(CWE-916); use `bcryptRecommendedCost` (12)."))


def _strict_raise_first_weak_password_hash_cost(prog: Program, diags) -> None:
    if not diags:
        return
    lineno, message = sorted(diags)[0]
    span = _strict_span(prog, lineno)
    raise CompilerDiagnosticError(CompilerDiagnostic(
        code="SS4602",
        phase="semantic.strictExecutable",
        message=message,
        primary=span,
        semantic_stack=[
            DiagnosticFrame(
                kind="strictExecutable password-hash work-factor validation",
                span=span,
                note=("`languageMode strictExecutable` requires a production "
                      "bcrypt work factor"),
            ),
        ],
        direction=("Strict executable rejects a bcrypt cost below the security "
                   "floor; a low work factor is a CWE-916 brute-force exposure."),
        suggested_fixes=["set the cost to `bcryptRecommendedCost` (12), or a "
                         "higher application-policy constant"],
        agent_hint=("bcrypt cost is a work factor; production code must use "
                    "bcryptRecommendedCost (12), not a low constant"),
    ))


# OS command-execution targets (CWE-78). `c.system` hands its argument to a
# shell; if any part is runtime/untrusted data it is command injection. There is
# no safe shell-parameterization in this toolchain, so the command must be a
# compile-time-constant string (a module/op-local immutable) — never built from
# input, a mutable slot, or a bind result. Mirrors the SQL-must-be-constant rule.
_STRICT_COMMAND_EXEC_TARGETS = frozenset({"c.system"})


def _check_strict_command_string_is_constant(prog: Program, diags) -> None:
    """SS4603 — `c.system` (and any shell-exec target) must take a compile-time
    constant command string; a runtime/untrusted command is OS command injection
    (CWE-78)."""
    for op_name, op in prog.operations.items():
        constants = _strict_operation_int_constants(prog, op)  # immutable names in scope
        call_targets = _strict_call_target_map(op)
        arg_values: dict = {}
        for verb, args, lineno in op.lines:
            arg_parts = _strict_argument_parts(verb, args)
            if arg_parts is not None:
                arg_values.setdefault(arg_parts[0], []).append(
                    (arg_parts[1], arg_parts[2], lineno))
        for call_name, (raw_target, _line) in call_targets.items():
            if _strict_target(prog, raw_target) not in _STRICT_COMMAND_EXEC_TARGETS:
                continue
            for arg_name, value, lineno in arg_values.get(call_name, []):
                # An inline string/typed literal is represented as a tuple
                # (e.g. ('str','ls -la')) — that IS a compile-time constant, so
                # `c.system("ls -la")` is allowed. Only a bare name that is not a
                # resolvable immutable constant (a runtime binding / input /
                # written-mutable) is the injection risk.
                if isinstance(value, tuple):
                    continue
                if value in constants:
                    continue
                diags.append((lineno,
                    f"SS4603 shellCommandNotConstant: in operation `{op_name}`, "
                    f"call `{call_name}` passes `{value}` to `c.system`; the "
                    f"command must be a compile-time-constant string (a literal "
                    f"or module/op-local immutable), never runtime/untrusted data "
                    f"(OS command injection, CWE-78)."))
                break


def _strict_raise_first_command_injection(prog: Program, diags) -> None:
    if not diags:
        return
    lineno, message = sorted(diags)[0]
    span = _strict_span(prog, lineno)
    raise CompilerDiagnosticError(CompilerDiagnostic(
        code="SS4603",
        phase="semantic.strictExecutable",
        message=message,
        primary=span,
        semantic_stack=[
            DiagnosticFrame(
                kind="strictExecutable command-injection validation",
                span=span,
                note=("`languageMode strictExecutable` forbids passing runtime "
                      "data to a shell"),
            ),
        ],
        direction=("Strict executable rejects a non-constant `c.system` command; "
                   "untrusted data in a shell command is CWE-78. There is no safe "
                   "shell-parameterization — keep the command a static constant."),
        suggested_fixes=["declare the command as a `storage module immutable "
                         "<name> String \"...\"` and pass that, or avoid c.system"],
        agent_hint=("never build a shell command from input/runtime values; pass "
                    "a compile-time-constant string to c.system, or do not shell out"),
    ))


def _strict_secret_trust_types(prog: Program) -> set:
    """Types declared `typeTrust <T> secret` — values of these must never be
    embedded as a source literal (CWE-798). Empty-string sentinels filled at
    runtime (e.g. `storage module mutable cachedJwtSigningSecret JwtSecret ""`)
    are the legitimate pattern and are allowed."""
    return {
        type_name
        for type_name, meta in prog.type_metadata.items()
        if "secret" in meta.get("trust", [])
    }


def _strict_type_chain_is_secret(prog: Program, type_name: str, base_secret: set) -> bool:
    """True if `type_name`, or any type it aliases through, has typeTrust secret.
    Walks `prog.type_aliases` step by step (NOT `resolve_alias`, which overshoots
    to the primitive head and would miss an intermediate secret type). Closes the
    `type AppSecret JwtSecret` alias evasion."""
    seen: set = set()
    current = type_name
    while current is not None and current not in seen:
        if current in base_secret:
            return True
        seen.add(current)
        alias = prog.type_aliases.get(current)
        current = alias[0] if alias else None
    return False


def _strict_resolve_const_chain(prog: Program, value):
    """Follow a const-name chain to its ultimate compile-time value. A secret slot
    bound to another constant (`secretB <- secretA <- "lit"`) is still hard-coded;
    a slot bound to an empty sentinel resolves to "" and is correctly allowed."""
    seen: set = set()
    current = value
    for _ in range(8):
        if not isinstance(current, str) or current in seen:
            return current
        entry = prog.consts.get(current)
        if entry is None:
            return current
        seen.add(current)
        current = entry[1]
    return current


def _check_strict_hardcoded_secret(prog: Program, diags) -> None:
    """SS4604 — a non-empty compile-time value bound to a secret-trust-typed
    storage/sharedState/memory slot is a hard-coded credential (CWE-798). The
    secret must come from the environment / secure config (`c.getenv` /
    `process.environment`), not source. Iterating `prog.consts` covers all
    declaration kinds (storage/sharedState/memory/domainLiteral) — not just the
    `storage` verb."""
    base_secret = _strict_secret_trust_types(prog)
    if not base_secret:
        return
    line_by_name = {d["name"]: d["line"] for d in prog.storage_declarations}
    for name, entry in prog.consts.items():
        # Import flattening puts BOTH the qualified (`mod.secret`) and unqualified
        # (`secret`) name into prog.consts; report only the unqualified twin so a
        # single secret yields a single advisory (no double-fire).
        if "." in name and name.rsplit(".", 1)[-1] in prog.consts:
            continue
        declared_type, value = entry[0], entry[1]
        if not _strict_type_chain_is_secret(prog, declared_type, base_secret):
            continue
        resolved = _strict_resolve_const_chain(prog, value)
        if not isinstance(resolved, str) or resolved == "":
            continue  # empty sentinel filled at runtime — the good pattern
        diags.append((line_by_name.get(name, 0),
            f"SS4604 hardCodedSecret: `{name}` ({declared_type}, typeTrust "
            f"secret) is bound to a non-empty compile-time value; a hard-coded "
            f"credential is CWE-798. Load it from the environment (`c.getenv`) "
            f"or secure config at runtime, never from source."))


def _strict_raise_first_hardcoded_secret(prog: Program, diags) -> None:
    if not diags:
        return
    lineno, message = sorted(diags)[0]
    span = _strict_span(prog, lineno)
    raise CompilerDiagnosticError(CompilerDiagnostic(
        code="SS4604",
        phase="semantic.strictExecutable",
        message=message,
        primary=span,
        semantic_stack=[
            DiagnosticFrame(
                kind="strictExecutable hard-coded-secret validation",
                span=span,
                note=("`languageMode strictExecutable` forbids embedding a "
                      "secret-trust-typed value as a source literal"),
            ),
        ],
        direction=("Strict executable rejects a hard-coded credential (CWE-798); "
                   "a secret-trust-typed value must be loaded at runtime from the "
                   "environment or secure config, never written in source."),
        suggested_fixes=["declare an empty sentinel (`... <SecretType> \"\"`) and "
                         "fill it at runtime from `c.getenv` / process.environment"],
        agent_hint=("never put a real secret in source; read it from the "
                    "environment into a secret-typed slot at runtime"),
    ))


def _check_strict_format_string_is_constant(prog: Program, diags) -> None:
    """SS3310 — c.snprintf / c.printf / c.fprintf / c.sprintf-family
    `format` arg must reference a `storage * immutable
    String` row so `%n` / `%s` conversions cannot be
    injected from runtime data."""
    for op_name, op in prog.operations.items():
        constant_names = _strict_collect_constant_string_names(prog, op)
        call_targets = _strict_call_target_map(op)
        for verb, args, lineno in op.lines:
            arg_parts = _strict_argument_parts(verb, args)
            if arg_parts is None:
                continue
            call_name, arg_name, value_name = arg_parts
            target_info = call_targets.get(call_name)
            if target_info is None:
                continue
            target = _strict_target(prog, target_info[0])
            if target not in _STRICT_CONSTANT_FORMAT_TARGETS:
                continue
            if arg_name not in _STRICT_FORMAT_ARG_SLOTS:
                continue
            if value_name in constant_names:
                continue
            diags.append((lineno,
                f"SS3310 formatStringMustBeConstant: in operation "
                f"`{op_name}`, call `{call_name}` (target `{target}`) "
                f"uses `{value_name}` as `format`; the format-string "
                f"argument must reference a `storage * immutable "
                f"String` row so `%n` / `%s` "
                f"conversions cannot be injected"))


def _check_strict_sql_string_is_constant(prog: Program, diags) -> None:
    """SS3911 — sqlite.prepareStatement / sqlite.exec `sql` arg must be
    a module-scope immutable SqlText value backed by a sql body island or
    a trusted external literalSource asset. Forces parameterised statements:
    dynamic values go through sqlite.bind*, not into the SQL text itself."""
    for op_name, op in prog.operations.items():
        call_targets = _strict_call_target_map(op)
        for verb, args, lineno in op.lines:
            arg_parts = _strict_argument_parts(verb, args)
            if arg_parts is None:
                continue
            call_name, arg_name, value_name = arg_parts
            target_info = call_targets.get(call_name)
            if target_info is None:
                continue
            target = _strict_target(prog, target_info[0])
            if target not in _STRICT_SQL_STRING_TARGETS:
                continue
            if arg_name not in _STRICT_SQL_ARG_SLOTS:
                continue
            const = _strict_sql_const(prog, value_name)
            if const is None:
                diags.append((lineno,
                    f"SS3911 sqlMustBeStaticSqlText: in operation `{op_name}`, "
                    f"call `{call_name}` (target `{target}`) uses "
                    f"`{value_name}` as `sql`, but that name is not a "
                    "module-scope SQL constant"))
                continue
            typ, _value = const
            if not _strict_is_sql_text_type(prog, typ):
                diags.append((lineno,
                    f"SS3911 sqlMustBeSqlText: in operation `{op_name}`, "
                    f"call `{call_name}` (target `{target}`) uses "
                    f"`{value_name}` as `sql`; SQL text must be typed "
                    "`SqlText`, not `String`"))
                continue
            if any(name in prog.mutable_globals for name in _strict_sql_names_for(value_name)):
                diags.append((lineno,
                    f"SS3911 sqlMustBeImmutable: in operation `{op_name}`, "
                    f"call `{call_name}` (target `{target}`) uses mutable "
                    f"`{value_name}` as `sql`; SQL text must be immutable"))
                continue
            if _strict_sql_source_is_body_or_external_literal(prog, value_name):
                continue
            diags.append((lineno,
                f"SS3916 sqlMustUseBodyOrLiteralSource: in operation `{op_name}`, "
                f"call `{call_name}` (target `{target}`) uses "
                f"`{value_name}` as `sql`; inline SQL strings are rejected "
                "in strictExecutable mode. Use `storage module immutable "
                "NAME SqlText` plus `sql body NAME`, or a `literal NAME "
                "SqlText` with `literalSource` for external .sql assets"))


def _strict_sql_names_for(value_name: str) -> list:
    names = [value_name]
    if "." in value_name:
        names.append(value_name.rsplit(".", 1)[1])
    return names


def _strict_sql_const(prog: Program, value_name: str):
    for name in _strict_sql_names_for(value_name):
        const = prog.consts.get(name)
        if const is not None:
            return const
    return None


def _strict_is_sql_text_type(prog: Program, typ: str) -> bool:
    resolved = resolve_alias(prog, typ)
    return typ == "SqlText" or resolved == "SqlText"


def _strict_sql_source_is_body_or_external_literal(
    prog: Program,
    value_name: str,
) -> bool:
    names = set(_strict_sql_names_for(value_name))
    for declaration in prog.storage_declarations:
        if declaration.get("name") not in names:
            continue
        if not _strict_is_sql_text_type(prog, declaration.get("type", "")):
            continue
        if declaration.get("scope") != "module":
            continue
        if declaration.get("mutability") != "immutable":
            continue
        if declaration.get("has_sql_body"):
            return True
    for name in names:
        const = prog.consts.get(name)
        if const is None:
            continue
        typ, _value = const
        if not _strict_is_sql_text_type(prog, typ):
            continue
        literal_source = prog.hard_metadata.get(name, {}).get("literalSource")
        if literal_source:
            return True
    return False


def _is_sql_constant_type(prog: Program, typ: str) -> bool:
    resolved = resolve_alias(prog, typ)
    return typ == "SqlText" or resolved in ("SqlText", "String")


def _sql_constant_usage(prog: Program):
    for op_name, op in prog.operations.items():
        call_targets = _strict_call_target_map(op)
        for verb, args, lineno in op.lines:
            arg_parts = _strict_argument_parts(verb, args)
            if arg_parts is None:
                continue
            call_name, arg_name, value_name = arg_parts
            target_info = call_targets.get(call_name)
            if target_info is None:
                continue
            target = _strict_target(prog, target_info[0])
            if target not in _STRICT_SQL_STRING_TARGETS or arg_name not in _STRICT_SQL_ARG_SLOTS:
                continue
            yield op_name, op, call_name, target, value_name, lineno


def _strict_sqlite_statement_has_column_reads(
    calls: dict,
    statement_names: set,
) -> bool:
    if not statement_names:
        return False
    for call_info in calls.values():
        if not call_info["target"].startswith("sqlite.column"):
            continue
        if _strict_call_arg_value(call_info, "statement") in statement_names:
            return True
    return False


def _strict_sqlite_statement_passed_to_helper(
    calls: dict,
    statement_names: set,
) -> bool:
    if not statement_names:
        return False
    ignored_targets = {
        "sqlite.bindBlob",
        "sqlite.bindDouble",
        "sqlite.bindInt",
        "sqlite.bindInt64",
        "sqlite.bindNull",
        "sqlite.bindText",
        "sqlite.finalizeStatement",
        "sqlite.resetStatement",
        "sqlite.stepStatement",
    }
    for call_info in calls.values():
        if (call_info["target"].startswith("sqlite.column")
                or call_info["target"] in ignored_targets):
            continue
        if _strict_call_consumes_any(call_info, statement_names):
            return True
    return False


def _strict_sql_usage_is_wide_existence_probe(
    prog: Program,
    op: Operation,
    call_name: str,
    sql_text: str,
) -> bool:
    if _sql_first_verb(sql_text) != "SELECT":
        return False
    if _sql_select_is_narrow_existence_probe(sql_text):
        return False
    calls = _strict_collect_calls(prog, op)
    call_info = calls.get(call_name)
    if call_info is None:
        return False
    statement_names = _strict_success_names(call_info)
    if _strict_sqlite_statement_has_column_reads(calls, statement_names):
        return False
    if _strict_sqlite_statement_passed_to_helper(calls, statement_names):
        return False
    return bool(statement_names)


def _check_sqlite_write_then_read_usage(prog: Program, diags) -> None:
    for op_name, op in prog.operations.items():
        calls = _strict_collect_calls(prog, op)
        prior_writes = {}
        for call_info in sorted(
            calls.values(),
            key=lambda candidate: candidate["line"],
        ):
            if call_info["target"] != "sqlite.prepareStatement":
                continue
            sql_name = _strict_call_arg_value(call_info, "sql")
            if sql_name is None:
                continue
            const = _strict_sql_const(prog, sql_name)
            if const is None:
                continue
            _typ, sql_text = const
            if not isinstance(sql_text, str):
                continue
            write_table = _sql_write_table(sql_text)
            if write_table is not None:
                if not _sql_has_returning(sql_text):
                    prior_writes.setdefault(write_table, (call_info, sql_name))
                continue
            select_table = _sql_select_table(sql_text)
            if select_table is None or select_table not in prior_writes:
                continue
            write_call, write_sql_name = prior_writes[select_table]
            diags.append((call_info["line"],
                f"SS3918 sqliteWriteThenReadShouldUseReturning: operation "
                f"`{op_name}` prepares write SQL `{write_sql_name}` with "
                f"call `{write_call['name']}` and then prepares SELECT SQL "
                f"`{sql_name}` against the same table `{select_table}`; "
                "fold the read into the write with `RETURNING` to avoid an "
                "extra prepare/bind/step/finalize round trip"))


_STRICT_SQL_WRITE_STATEMENT_VERBS = frozenset({
    "DELETE",
    "INSERT",
    "REPLACE",
    "UPDATE",
})


def _strict_sql_text_for_name(prog: Program, sql_name: str) -> str | None:
    const = _strict_sql_const(prog, sql_name)
    if const is None:
        return None
    _typ, sql_text = const
    if not isinstance(sql_text, str):
        return None
    return sql_text


def _strict_sql_is_write_statement(sql_text: str) -> bool:
    return _sql_first_verb(sql_text) in _STRICT_SQL_WRITE_STATEMENT_VERBS


def _check_sqlite_multiple_writes_have_transaction(prog: Program, diags) -> None:
    for op_name, op in prog.operations.items():
        calls = _strict_collect_calls(prog, op)
        write_steps = []
        for prepare_call in calls.values():
            if prepare_call["target"] != "sqlite.prepareStatement":
                continue
            sql_name = _strict_call_arg_value(prepare_call, "sql")
            if sql_name is None:
                continue
            sql_text = _strict_sql_text_for_name(prog, sql_name)
            if sql_text is None or not _strict_sql_is_write_statement(sql_text):
                continue
            statement_names = _strict_success_names(prepare_call)
            if not statement_names:
                continue
            for step_call in calls.values():
                if step_call["target"] != "sqlite.stepStatement":
                    continue
                if _strict_call_arg_value(step_call, "statement") not in statement_names:
                    continue
                write_steps.append((prepare_call, step_call, sql_name))

        if len(write_steps) < 2:
            continue

        has_begin = False
        has_commit = False
        for call_info in calls.values():
            if call_info["target"] not in _STRICT_SQL_EXEC_TARGETS:
                continue
            sql_name = _strict_call_arg_value(call_info, "sql")
            if sql_name is None:
                continue
            sql_text = _strict_sql_text_for_name(prog, sql_name)
            if sql_text is None:
                continue
            verb = _sql_first_verb(sql_text)
            if verb in {"BEGIN", "SAVEPOINT"}:
                has_begin = True
            elif verb in {"COMMIT", "RELEASE"}:
                has_commit = True

        if has_begin and has_commit:
            continue

        first_prepare, _first_step, first_sql_name = write_steps[0]
        _second_prepare, second_step, second_sql_name = write_steps[1]
        diags.append((second_step["line"],
            f"SS3922 sqliteMultipleWritesRequireTransaction: operation "
            f"`{op_name}` steps write SQL `{first_sql_name}` via "
            f"`{first_prepare['name']}` and write SQL `{second_sql_name}` "
            f"without a visible SQLite BEGIN/COMMIT pair; strictExecutable "
            "multi-write operations must use an explicit transaction so "
            "SQLite avoids per-statement implicit transactions and failures "
            "cannot commit partial state"))


_STRICT_SQLITE_RETURNING_DRAIN_TARGETS = frozenset({
    "sqlite.finalizeStatement",
    "sqlite.resetStatement",
    "sqlite.stepStatement",
})


def _check_sqlite_returning_statement_drained_before_commit(
    prog: Program,
    diags,
) -> None:
    for op_name, op in prog.operations.items():
        calls = _strict_collect_calls(prog, op)
        returning_statements = {}
        for prepare_call in calls.values():
            if prepare_call["target"] != "sqlite.prepareStatement":
                continue
            sql_name = _strict_call_arg_value(prepare_call, "sql")
            if sql_name is None:
                continue
            sql_text = _strict_sql_text_for_name(prog, sql_name)
            if sql_text is None or not _sql_has_returning(sql_text):
                continue
            for statement_name in _strict_success_names(prepare_call):
                returning_statements[statement_name] = (prepare_call, sql_name)
        if not returning_statements:
            continue

        commit_calls = []
        for call_info in calls.values():
            if call_info["target"] not in _STRICT_SQL_EXEC_TARGETS:
                continue
            sql_name = _strict_call_arg_value(call_info, "sql")
            if sql_name is None:
                continue
            sql_text = _strict_sql_text_for_name(prog, sql_name)
            if sql_text is None:
                continue
            if _sql_first_verb(sql_text) in {"COMMIT", "RELEASE"}:
                commit_calls.append(call_info)
        if not commit_calls:
            continue

        for statement_name, (prepare_call, sql_name) in returning_statements.items():
            column_reads = sorted(
                (
                    call_info for call_info in calls.values()
                    if call_info["target"].startswith("sqlite.column")
                    and _strict_call_arg_value(call_info, "statement") == statement_name
                ),
                key=lambda call_info: call_info["line"],
            )
            if not column_reads:
                continue
            last_read = column_reads[-1]
            for commit_call in sorted(
                commit_calls,
                key=lambda call_info: call_info["line"],
            ):
                if commit_call["line"] <= last_read["line"]:
                    continue
                drained = any(
                    drain_call["target"] in _STRICT_SQLITE_RETURNING_DRAIN_TARGETS
                    and _strict_call_arg_value(drain_call, "statement") == statement_name
                    and last_read["line"] < drain_call["line"] < commit_call["line"]
                    for drain_call in calls.values()
                )
                if drained:
                    continue
                diags.append((commit_call["line"],
                    f"SS3923 sqliteReturningStatementMustBeDrained: "
                    f"operation `{op_name}` reads columns from RETURNING SQL "
                    f"`{sql_name}` prepared by `{prepare_call['name']}` and "
                    f"then commits via `{commit_call['name']}` without a "
                    "visible second step/reset/finalize on the statement; "
                    "strictExecutable requires RETURNING statements to be "
                    "drained before COMMIT so SQLite cannot reject the "
                    "transaction because a row is still active"))
                break


def _check_strict_sqlite_last_insert_rowid_calls(prog: Program, diags) -> None:
    for op_name, op in prog.operations.items():
        calls = _strict_collect_calls(prog, op)
        for call_info in calls.values():
            if call_info["target"] != "sqlite.lastInsertRowId":
                continue
            diags.append((call_info["line"],
                f"SS3926 sqliteLastInsertRowidShouldUseReturning: operation "
                f"`{op_name}` calls `sqlite.lastInsertRowId` via "
                f"`{call_info['name']}`; strict executable SQL must return "
                "generated ids from the INSERT with `RETURNING` and pass "
                "them to later statements as explicit binds instead of "
                "reading connection-global mutable state"))


_STRICT_PROCESS_ENVIRONMENT_READ_TARGETS = frozenset({
    "c.getenv",
    "c.getenv_s",
    "c.getenvSafe",
})

_STRICT_REQUEST_TIME_READ_TARGETS = frozenset({
    "http.nowMillis",
})

_STRICT_LARGE_LOCAL_STATIC_LITERAL_MIN_BYTES = 512
_STRICT_LARGE_LOCAL_STATIC_LITERAL_TYPES = frozenset({
    "String",
    "String",
    "JsonText",
    "SqlText",
})


def _strict_storage_name_looks_like_cache(name: str) -> bool:
    lowered = name.lower()
    return "cache" in lowered or "cached" in lowered


def _strict_operation_has_environment_cache_guard(
    op: Operation,
    first_getenv_line: int,
) -> bool:
    has_cache_write = any(
        verb == "set"
        and len(args) >= 3
        and args[0] == "storage"
        and _strict_storage_name_looks_like_cache(args[1])
        for verb, args, _lineno in op.lines
    )
    has_pre_getenv_guard = any(
        lineno < first_getenv_line
        and verb == "branch"
        and len(args) >= 5
        and args[0] == "if"
        for verb, args, lineno in op.lines
    )
    return has_cache_write and has_pre_getenv_guard


def _check_strict_process_environment_reads_cached(prog: Program, diags) -> None:
    for op_name, op in prog.operations.items():
        if op_name == "main":
            continue
        calls = _strict_collect_calls(prog, op)
        getenv_calls = [
            call_info for call_info in calls.values()
            if call_info["target"] in _STRICT_PROCESS_ENVIRONMENT_READ_TARGETS
        ]
        if not getenv_calls:
            continue
        first_getenv = min(
            getenv_calls,
            key=lambda call_info: call_info["line"],
        )
        if _strict_operation_has_environment_cache_guard(
                op, first_getenv["line"]):
            continue
        diags.append((first_getenv["line"],
            f"SS3920 getenvShouldBeCached: operation `{op_name}` calls "
            f"`{first_getenv['target']}` via `{first_getenv['name']}` "
            "without a visible module-storage cache guard; non-entry "
            "strict executable operations must resolve process environment "
            "configuration once and reuse cached storage on hot paths"))


def _strict_operation_has_http_boundary(op: Operation) -> bool:
    return any(
        input_info.get("type") in {"HttpRequest", "HttpResponse"}
        for input_info in _operation_inputs(op).values()
    )


def _check_strict_repeated_request_time_reads(prog: Program, diags) -> None:
    for op_name, op in prog.operations.items():
        if not _strict_operation_has_http_boundary(op):
            continue
        calls = _strict_collect_calls(prog, op)
        time_calls = sorted(
            (
                call_info for call_info in calls.values()
                if call_info["target"] in _STRICT_REQUEST_TIME_READ_TARGETS
            ),
            key=lambda call_info: call_info["line"],
        )
        if len(time_calls) < 2:
            continue
        first_time_call = time_calls[0]
        second_time_call = time_calls[1]
        diags.append((second_time_call["line"],
            f"SS3924 repeatedRequestTimeRead: operation `{op_name}` calls "
            f"`{first_time_call['target']}` via `{first_time_call['name']}` "
            f"and again via `{second_time_call['name']}`; "
            "strict executable request paths must read wall-clock time once "
            "and reuse the bound timestamp so hot handlers avoid repeated "
            "native calls and persist consistent row times"))


_STRICT_IDEMPOTENCY_SELECT_NAMES = frozenset({
    "sqlSelectIdempotency",
})

_STRICT_IDEMPOTENCY_RESPONSE_JSON_COLUMN_INDEXES = frozenset({
    "1",
    "columnIndex1",
    "runtime.columnIndex1",
})


def _strict_sql_name_or_text_is_idempotency_select(
    prog: Program,
    sql_name: str,
) -> bool:
    unqualified_name = sql_name.rsplit(".", 1)[-1]
    if unqualified_name in _STRICT_IDEMPOTENCY_SELECT_NAMES:
        return True
    sql_text = _strict_sql_text_for_name(prog, sql_name)
    if sql_text is None:
        return False
    folded = re.sub(r"\s+", " ", sql_text).lower()
    return (
        _sql_first_verb(sql_text) == "SELECT"
        and " from idempotency_keys" in folded
        and "response_json" in folded
        and "response_status" in folded
    )


def _strict_call_uses_response_json_column(call_info: dict) -> bool:
    column_index = _strict_call_arg_value(call_info, "columnIndex")
    return column_index in _STRICT_IDEMPOTENCY_RESPONSE_JSON_COLUMN_INDEXES


def _check_strict_idempotency_replay_uses_response_status(
    prog: Program,
    diags,
) -> None:
    for op_name, op in prog.operations.items():
        calls = _strict_collect_calls(prog, op)
        idempotency_statements = {}
        for prepare_call in calls.values():
            if prepare_call["target"] != "sqlite.prepareStatement":
                continue
            sql_name = _strict_call_arg_value(prepare_call, "sql")
            if sql_name is None:
                continue
            if not _strict_sql_name_or_text_is_idempotency_select(
                prog, sql_name
            ):
                continue
            for statement_name in _strict_success_names(prepare_call):
                idempotency_statements[statement_name] = prepare_call
        if not idempotency_statements:
            continue

        replay_body_reads = {}
        for read_call in calls.values():
            if read_call["target"] != "sqlite.columnText":
                continue
            statement_name = _strict_call_arg_value(read_call, "statement")
            if statement_name not in idempotency_statements:
                continue
            if not _strict_call_uses_response_json_column(read_call):
                continue
            prepare_call = idempotency_statements[statement_name]
            for body_name in _strict_success_names(read_call):
                replay_body_reads[body_name] = (read_call, prepare_call)
        if not replay_body_reads:
            continue

        for compare_call in sorted(
            calls.values(),
            key=lambda call_info: call_info["line"],
        ):
            if compare_call["target"] != "c.strcmp":
                continue
            compared_names = {
                name for name in (
                    _strict_call_arg_value(compare_call, "left"),
                    _strict_call_arg_value(compare_call, "right"),
                )
                if name is not None
            }
            replay_body_name = next(
                (
                    name for name in compared_names
                    if name in replay_body_reads
                ),
                None,
            )
            if replay_body_name is None:
                continue
            read_call, prepare_call = replay_body_reads[replay_body_name]
            diags.append((compare_call["line"],
                f"SS3925 idempotencyReplayShouldUseResponseStatus: "
                f"operation `{op_name}` reads idempotency response_json "
                f"as `{replay_body_name}` via `{read_call['name']}` and "
                f"classifies it with `{compare_call['name']}`; "
                f"`{prepare_call['name']}` also selects response_status, "
                "so strict executable replay paths must branch on that "
                "scalar instead of comparing full JSON response bodies"))


def _strict_inline_string_literal(value) -> str | None:
    if isinstance(value, tuple) and value and value[0] == "str":
        return value[1]
    return None


def _strict_is_large_local_static_literal_type(
    prog: Program,
    type_name: str,
) -> bool:
    return resolve_alias(prog, type_name) in _STRICT_LARGE_LOCAL_STATIC_LITERAL_TYPES


def _check_strict_large_local_static_literals(prog: Program, diags) -> None:
    for op_name, op in prog.operations.items():
        for verb, args, lineno in op.lines:
            if (verb != "storage" or len(args) < 5
                    or args[0] != "local" or args[1] != "immutable"):
                continue
            name = args[2]
            type_name = args[3]
            literal_value = _strict_inline_string_literal(args[4])
            if literal_value is None:
                continue
            if not _strict_is_large_local_static_literal_type(prog, type_name):
                continue
            literal_bytes = len(literal_value.encode("utf-8"))
            if literal_bytes < _STRICT_LARGE_LOCAL_STATIC_LITERAL_MIN_BYTES:
                continue
            diags.append((lineno,
                f"SS3921 localStaticLiteralShouldBeModuleImmutable: "
                f"operation `{op_name}` declares `{name}` as a "
                f"{literal_bytes}-byte inline local immutable `{type_name}`; "
                "large static literals are process constants and must be "
                "hoisted to `storage module immutable` so hot handlers do "
                "not carry large per-call context"))


def _check_sqlite_sql_body_usage(prog: Program, diags) -> None:
    for op_name, op, call_name, target, value_name, lineno in _sql_constant_usage(prog):
        const = _strict_sql_const(prog, value_name)
        if const is None:
            continue
        _typ, value = const
        if not isinstance(value, str):
            continue
        placeholder_count, statement_count, scan_problem = _scan_sql_text(value)
        if scan_problem is not None:
            diags.append((lineno,
                f"SS3913 invalidSqlText: in operation `{op_name}`, call "
                f"`{call_name}` (target `{target}`) uses SQL constant "
                f"`{value_name}` with invalid SQL text: {scan_problem}"))
            continue
        redundant_cases = _redundant_sql_cases(value)
        if redundant_cases:
            diags.append((lineno,
                f"SS3915 redundantSqlCase: in operation `{op_name}`, call "
                f"`{call_name}` (target `{target}`) uses SQL constant "
                f"`{value_name}` with a CASE expression whose THEN and ELSE "
                "branches are identical; simplify the SQL and remove any "
                "bind parameters used only by the redundant condition"))
            continue
        if _sql_uses_last_insert_rowid(value):
            diags.append((lineno,
                f"SS3926 sqliteLastInsertRowidShouldUseReturning: in "
                f"operation `{op_name}`, call `{call_name}` (target "
                f"`{target}`) uses SQL constant `{value_name}` with "
                "`last_insert_rowid()`; strict executable SQL must return "
                "generated ids from the INSERT with `RETURNING` and pass "
                "them to later statements as explicit binds"))
            continue
        if target in _STRICT_SQL_PREPARE_TARGETS and statement_count != 1:
            diags.append((lineno,
                f"SS3913 prepareSqlMustBeSingleStatement: in operation "
                f"`{op_name}`, call `{call_name}` uses SQL constant "
                f"`{value_name}` containing {statement_count} statements; "
                "sqlite.prepareStatement accepts exactly one statement"))
            continue
        if (target in _STRICT_SQL_PREPARE_TARGETS
                and _strict_sql_usage_is_wide_existence_probe(
                    prog, op, call_name, value)):
            diags.append((lineno,
                f"SS3917 wideSqlExistenceProbe: in operation `{op_name}`, "
                f"call `{call_name}` (target `{target}`) uses SQL constant "
                f"`{value_name}` as a row-exists probe but the SELECT "
                "projects columns that are never read; use `SELECT 1` or "
                "`SELECT EXISTS(...)` for boolean existence checks"))
        if target in _STRICT_SQL_EXEC_TARGETS and placeholder_count:
            diags.append((lineno,
                f"SS3914 execSqlCannotUsePlaceholders: in operation "
                f"`{op_name}`, call `{call_name}` uses SQL constant "
                f"`{value_name}` containing {placeholder_count} bind "
                "placeholder(s), but sqlite.exec / sqlite.execStatus have no "
                "sqlite.bind* path; use sqlite.prepareStatement for "
                "parameterized SQL"))


def _strict_raise_first_sql_usage_violation(prog: Program, diags) -> None:
    _strict_raise_first_simple(
        prog, diags, "SS3913",
        "strictExecutable sqlite SQL body validation",
        "Strict executable requires prepared SQL to contain exactly one "
        "statement, sqlite.exec SQL to contain no bind placeholders, and "
        "SQL bodies to avoid dead constructs such as CASE expressions with "
        "identical THEN/ELSE branches or full-row projections used only as "
        "existence probes. Write/read round trips on the same table should "
        "use SQLite RETURNING when the value is produced by the write, and "
        "SQL should not depend on connection-global last_insert_rowid(). "
        "Multi-write operations should make transaction boundaries visible. "
        "RETURNING statements must be drained before transaction commit.",
    )


def _strict_raise_first_process_environment_violation(prog: Program, diags) -> None:
    _strict_raise_first_simple(
        prog, diags, "SS3920",
        "strictExecutable process environment cache validation",
        "Strict executable requires non-entry operations to cache process "
        "environment configuration behind module storage. Request-path code "
        "should not repeatedly call getenv for stable deployment settings.",
    )


def _strict_raise_first_request_time_violation(prog: Program, diags) -> None:
    _strict_raise_first_simple(
        prog, diags, "SS3924",
        "strictExecutable request timestamp validation",
        "Strict executable requires each operation to read request wall-clock "
        "time once and reuse the bound timestamp for rows, events, logs, and "
        "idempotency expiry calculations created by the same logical request.",
    )


def _strict_raise_first_idempotency_replay_violation(
    prog: Program,
    diags,
) -> None:
    _strict_raise_first_simple(
        prog, diags, "SS3925",
        "strictExecutable idempotency replay validation",
        "Strict executable requires idempotency replay paths to branch on "
        "stored response_status rather than compare stored response_json "
        "bodies. The status column is fixed-width, faster, and decoupled "
        "from envelope text formatting.",
    )


def _strict_raise_first_large_static_literal_violation(prog: Program, diags) -> None:
    _strict_raise_first_simple(
        prog, diags, "SS3921",
        "strictExecutable static literal placement validation",
        "Strict executable requires large static string/blob literals to live "
        "at module scope. Operation bodies should carry request flow, not "
        "large immutable data blocks.",
    )


def _strict_raise_first_constant_string_violation(prog: Program, diags) -> None:
    _strict_raise_first_simple(
        prog, diags, "SS3310",
        "strictExecutable constant-string validation",
        "Strict executable requires every format string to come from a "
        "static immutable string row, and every SQLite statement to come "
        "from `SqlText` backed by a `sql body` island or trusted "
        "`literalSource` asset.",
    )


def _check_strict_step_result_disposition(prog: Program, diags) -> None:
    """SS3912 — sqlite.stepStatement result must be bound, EXCEPT when
    the call already has an executable error disposition (`bind error` +
    `branch error`) that exits the segment. That pattern is the
    legitimate DELETE/UPDATE shape: the user only cares whether the
    step errored, not whether it returned `row` vs `done`. SELECT
    iteration still needs an actual `bind ok` so the loop knows when
    to terminate.
    """
    for op_name, op in prog.operations.items():
        step_calls = {}
        for verb, args, lineno in op.lines:
            if (verb == "call" and len(args) >= 2
                    and _strict_target(prog, args[1]) == "sqlite.stepStatement"):
                step_calls[args[0]] = lineno
        if not step_calls:
            continue
        dispositions = {}
        has_bind_error = set()
        has_branch_if_error = set()
        for verb, args, _lineno in op.lines:
            if not args:
                continue
            if verb == "bind" and len(args) >= 4:
                if args[0] in ("value", "ok") and args[3] in step_calls:
                    dispositions[args[3]] = "bind"
            elif (verb == "runChecked" and len(args) >= 9
                    and args[0] in step_calls):
                dispositions[args[0]] = "runChecked"
            elif verb == "ignore" and len(args) >= 3 and args[2] in step_calls:
                if args[0] in ("ok", "value", "void"):
                    dispositions.setdefault(args[2], "ignore")
            elif verb == "bind" and len(args) >= 4 and args[0] == "error":
                if args[3] in step_calls:
                    has_bind_error.add(args[3])
            elif (verb == "branch" and len(args) >= 5 and args[0] == "error"
                  and args[2] in step_calls):
                has_branch_if_error.add(args[2])
        for call_name, lineno in step_calls.items():
            disposition = dispositions.get(call_name)
            if disposition in ("bind", "runChecked"):
                continue
            if (disposition == "ignore"
                    and call_name in has_bind_error
                    and call_name in has_branch_if_error):
                # DELETE/UPDATE shape: row/done collapses to "done"
                # whenever errors are routed elsewhere. The user has
                # explicitly opted in to dropping the success value.
                continue
            diags.append((lineno,
                f"SS3912 sqliteStepResultIgnored: in operation `{op_name}`, "
                f"call `{call_name}` (target `sqlite.stepStatement`) does "
                f"not bind its SqliteStepResult; bind it with `bind ok` or "
                f"`runChecked` (SELECT iteration) or add `bind error` + "
                f"`branch error` alongside `ignore ok` or `ignore void` "
                f"(DELETE/UPDATE)"))


def _strict_raise_first_step_disposition(prog: Program, diags) -> None:
    _strict_raise_first_simple(
        prog, diags, "SS3912",
        "strictExecutable sqlite-step disposition validation",
        "Strict executable requires every `sqlite.stepStatement` result "
        "to be bound so the row/done/error outcome is inspected.",
    )


def _check_strict_handler_writes_response(prog: Program, diags) -> None:
    """SS3614 — every route/middleware handler must call at least one
    response-body writer somewhere in its body, with one exception for
    middleware that only ever returns `continueMiddlewareControl`.

    This is a weaker contract than per-return-path inspection, but
    accurate per-path tracking requires dataflow reconstruction across
    labels and branches. Catching the "handler forgot to write a body
    entirely" shape with a simple any-writer-in-body check covers the
    actually-common bug at zero false-positive rate; per-path holes are
    deferred to the existing SS3607/SS3615 forwarder contract walks.
    """
    handler_ops = set()
    for _lineno, args in _source_rows(prog, "route"):
        if len(args) >= 4:
            handler_ops.add(args[3])
    for _lineno, args in _source_rows(prog, "routeNotFound"):
        if len(args) >= 2:
            handler_ops.add(args[1])
    for _lineno, args in _source_rows(prog, "routeMethodNotAllowed"):
        if len(args) >= 2:
            handler_ops.add(args[1])
    middleware_ops = set()
    for _lineno, args in _source_rows(prog, "routeMiddleware"):
        if len(args) >= 3:
            middleware_ops.add(args[2])
            handler_ops.add(args[2])
    writer_targets = set(_STRICT_RESPONSE_WRITER_TARGETS)
    writer_targets.update(_response_body_writer_slots(prog).keys())
    for op_name in handler_ops:
        op = prog.operations.get(op_name)
        if op is None:
            continue
        has_writer = False
        only_continue_returns = True
        return_lines = []
        for verb, args, lineno in op.lines:
            if verb == "call" and len(args) >= 2:
                if _strict_target(prog, args[1]) in writer_targets:
                    has_writer = True
            elif verb == "return" and len(args) >= 2 and args[0] in ("ok", "value"):
                return_lines.append(lineno)
                if args[1] != "continueMiddlewareControl":
                    only_continue_returns = False
        if has_writer:
            continue
        # Middleware whose every return is `continueMiddlewareControl`
        # legitimately never writes a body — the downstream handler will.
        if op_name in middleware_ops and only_continue_returns and return_lines:
            continue
        primary_line = return_lines[0] if return_lines else op.decl_line
        diags.append((primary_line,
            f"SS3614 handlerReturnsWithoutResponse: handler "
            f"`{op_name}` never calls a response body writer "
            f"(http.responseText|Bytes|SseEvent|File or a declared "
            f"responseBodyForwarder); every route handler must produce "
            f"an HTTP response. Middleware that delegates must return "
            f"`continueMiddlewareControl`"))


def _strict_raise_first_handler_response(prog: Program, diags) -> None:
    _strict_raise_first_simple(
        prog, diags, "SS3614",
        "strictExecutable handler response-writer validation",
        "Strict executable requires every reachable return from a route "
        "handler to follow a response body writer on the same "
        "control-flow segment.",
    )


def _check_strict_shared_state_lock(prog: Program, diags) -> None:
    """SS3408 — when multiple operations write to the same module-mutable
    storage, every writer must declare a mutex/lock capability via
    `useCapability OP <Mutex|Lock|Semaphore>`. Single-writer storages are
    not flagged (no race surface)."""
    writers_by_target = {}
    capabilities_by_op = {}
    effect_line_by_op_target = {}
    for op_name, op in prog.operations.items():
        for verb, args, lineno in op.lines:
            if (verb == "useCapability" and len(args) >= 2
                    and args[0] == op_name):
                capabilities_by_op.setdefault(op_name, set()).add(args[1])
            if (verb == "effect" and len(args) >= 3
                    and args[0] == op_name):
                effect_kind = args[1]
                effect_target = args[2]
                if effect_kind in ("readWrite", "writeOnly", "write"):
                    if effect_target in prog.mutable_globals:
                        writers_by_target.setdefault(
                            effect_target, []).append(op_name)
                        effect_line_by_op_target[
                            (op_name, effect_target)] = lineno
    for target, writers in writers_by_target.items():
        unique_writers = set(writers)
        if len(unique_writers) < 2:
            continue
        for op_name in unique_writers:
            caps = capabilities_by_op.get(op_name, set())
            if any(any(token in cap for token in
                       _STRICT_MUTEX_CAPABILITY_SUBSTRINGS)
                   for cap in caps):
                continue
            lineno = effect_line_by_op_target.get((op_name, target), 0)
            diags.append((lineno,
                f"SS3408 sharedStateLockRequired: operation `{op_name}` "
                f"writes to `storage module mutable {target}` which has "
                f"{len(unique_writers)} concurrent writers; declare a "
                f"mutex capability with `useCapability {op_name} "
                f"<MutexOrLock>`"))


def _strict_raise_first_shared_state(prog: Program, diags) -> None:
    _strict_raise_first_simple(
        prog, diags, "SS3408",
        "strictExecutable shared-state mutex validation",
        "Strict executable requires operations that write shared "
        "`storage module mutable` state with multiple writers to declare "
        "a mutex capability.",
    )


# Integer divide/modulo (sdiv/srem) and shift targets, plus short aliases.
# These mirror the semlint SS4308/SS4309 floor; here they are *compile-blocking*
# under `languageMode strictExecutable`.
_STRICT_DIVISION_INT64_TARGETS = frozenset({
    "math.divideInt64", "math.moduloInt64",
    "math.divInt64", "math.modInt64",
})
_STRICT_SHIFT_INT64_TARGETS = frozenset({
    "math.shiftLeftInt64",
    "math.shiftRightLogicalInt64",
    "math.shiftRightArithmeticInt64",
})


def _strict_is_int_literal(token: str) -> bool:
    if not isinstance(token, str):
        return False
    stripped = token.lstrip("-")
    return bool(stripped) and stripped.isdigit()


def _strict_resolve_arith_target(prog: Program, raw_target: str) -> str:
    """Resolve a call target to its underlying integer math primitive, including
    domain-typed methods (`QuotaCount.divide` -> `math.divideInt64`) and enum
    methods. Mirrors the codegen resolution in `_compile_body` so the strict
    arithmetic-UB wall sees through the idiomatic domain-typed surface — without
    this, `Type.divide` by a constant zero lowers to sdiv but evades SS4308."""
    target = _strict_target(prog, raw_target)
    if target in _BINOP_TO_LLVM or "." not in target or target.startswith("c."):
        return target
    type_part, method_part = target.split(".", 1)
    enum_repr = enum_repr_type(prog, type_part)
    if enum_repr is not None:
        table = (_DOMAIN_METHOD_TO_Int64_PRIMITIVE if enum_repr == "Int64"
                 else _DOMAIN_METHOD_TO_Int32_PRIMITIVE)
        return table.get(method_part, target)
    underlying = resolve_alias(prog, type_part)
    if underlying == "Int64" and method_part in _DOMAIN_METHOD_TO_Int64_PRIMITIVE:
        return _DOMAIN_METHOD_TO_Int64_PRIMITIVE[method_part]
    if underlying == "Int32" and method_part in _DOMAIN_METHOD_TO_Int32_PRIMITIVE:
        return _DOMAIN_METHOD_TO_Int32_PRIMITIVE[method_part]
    # Float64 divide-by-zero is defined (inf/nan), not UB, so it is intentionally
    # not mapped into the integer division target set here.
    return target


def _strict_arith_rebound_name(verb: str, args: list):
    """The local name introduced/reassigned by this row (so a same-named module
    constant must not be trusted inside the operation). Mirrors the semlint
    resolver: `input` / `bind` / `set memory|storage` / mutable slot."""
    if verb == "input":
        if len(args) >= 4 and args[0] == "operation":
            return args[2]
        if len(args) >= 3:
            return args[1]
        return None
    if verb == "bind":
        if len(args) >= 4 and args[0] in ("value", "ok", "error"):
            return args[1]
        if len(args) >= 3:
            return args[0]
        return None
    if verb in ("bindOk", "bindError") and len(args) >= 3:
        return args[0]
    if verb == "set" and len(args) >= 2 and args[0] in ("memory", "storage"):
        return args[1]
    if verb in ("storage", "memory") and len(args) >= 4 and args[1] == "mutable":
        return args[2]
    return None


def _strict_program_written_names(prog: Program) -> set:
    """Every name that is the target of a `set memory|storage|sharedState` row
    anywhere in the program. A mutable global that is NEVER written is
    effectively constant at its initializer — so it must be resolved like a
    constant (closing the `storage module mutable X 0` never-written divide-by-
    zero evasion). A mutable global that IS written is genuinely runtime.

    Memoized per-Program: the security checks call this once per operation per
    rule, but the answer is a whole-program property, so we compute the
    O(lines) scan once per build instead of O(ops x rules) times.

    INVARIANT (load-bearing for cache correctness): operation `.lines` are frozen
    once parsing completes. The cache is populated at first validation (after
    parse + import inlining) and reused through codegen, which only READS lines.
    If a future lowering pass ever rewrites `operation.lines` in place, it MUST
    invalidate `prog._written_names_cache` (or this returns a stale set and a
    newly-written mutable divisor/cost could be misjudged as constant)."""
    cached = getattr(prog, "_written_names_cache", None)
    if cached is not None:
        return cached
    written: set = set()
    for operation in prog.operations.values():
        for verb, args, _lineno in operation.lines:
            if verb == "set" and len(args) >= 2 and args[0] in (
                    "memory", "storage", "sharedState"):
                written.add(args[1])
    try:
        prog._written_names_cache = written
    except Exception:
        pass  # if Program forbids attrs, correctness is unaffected — just slower
    return written


def _strict_operation_int_constants(prog: Program, op: Operation) -> dict:
    """name -> integer value for every *immutable* constant resolvable inside
    this operation: module-scope `prog.consts` (minus mutable globals that are
    actually written) plus the op's own immutable `storage`/`memory`/
    `domainLiteral`/`const` rows, minus any name the op rebinds.

    A mutable global that is never the target of a `set` is treated as the
    constant it effectively is (so `storage module mutable X Int64 0` used as a
    divisor is still caught). Mostly mirrors the semlint resolver, with one known
    divergence: `prog.consts` already has *imported* `exportConstant`s inlined,
    so the wall resolves e.g. an imported `bcryptMinimumCost`; the linter floor
    scans only the file's own lines and conservatively misses imported constants
    (an advisory under-report, never a false block). The wall is binding."""
    written = _strict_program_written_names(prog)
    constants: dict = {}
    for name, (typ, value) in prog.consts.items():
        if name in prog.mutable_globals and name in written:
            continue  # genuinely runtime-mutated — not a constant
        constants[name] = value
    rebound = set()
    for verb, args, _lineno in op.lines:
        if verb in ("domainLiteral", "const", "literal") and len(args) >= 3:
            constants[args[0]] = args[2]
            continue
        if verb == "storage" and len(args) >= 5 and args[1] == "immutable":
            constants[args[2]] = args[4]
            continue
        if verb == "memory" and len(args) >= 5 and args[1] == "immutable":
            constants[args[2]] = args[4]
            continue
        reboundName = _strict_arith_rebound_name(verb, args)
        if reboundName is not None:
            rebound.add(reboundName)
    for name in rebound:
        constants.pop(name, None)
    return constants


def _strict_resolve_int(value_name: str, constants: dict):
    """Resolve an operand to a concrete int via a bounded constant alias chain,
    or None when it is not a provable constant (runtime binding, opaque)."""
    seen = set()
    current = value_name
    for _ in range(8):
        if _strict_is_int_literal(current):
            return int(current)
        if current in seen or current not in constants:
            return None
        seen.add(current)
        current = constants[current]
    return None


def _check_strict_constant_division_or_shift(prog: Program, diags) -> None:
    """SS4308 / SS4309 — compile-blocking arithmetic UB:

      * SS4308 divisionByConstantZero — `math.divideInt64`/`moduloInt64` whose
        `right` divisor resolves to a provable constant 0 (sdiv/srem by 0 is UB).
      * SS4309 shiftCountOutOfRange — a shift whose `right` count resolves to a
        provable constant outside [0, 63] (LLVM poison).

    Provable-constant only, so runtime/guarded operands are never flagged here.
    """
    for op_name, op in prog.operations.items():
        constants = _strict_operation_int_constants(prog, op)
        call_targets = _strict_call_target_map(op)
        right_value_by_call = {}
        right_line_by_call = {}
        for verb, args, lineno in op.lines:
            arg_parts = _strict_argument_parts(verb, args)
            if arg_parts is not None and arg_parts[1] == "right":
                right_value_by_call[arg_parts[0]] = arg_parts[2]
                right_line_by_call[arg_parts[0]] = lineno
        for call_name, (raw_target, _call_line) in call_targets.items():
            divisor = right_value_by_call.get(call_name)
            if divisor is None:
                continue
            target = _strict_resolve_arith_target(prog, raw_target)
            resolved = _strict_resolve_int(divisor, constants)
            lineno = right_line_by_call[call_name]
            if target in _STRICT_DIVISION_INT64_TARGETS and resolved == 0:
                diags.append((lineno,
                    f"SS4308 divisionByConstantZero: in operation `{op_name}`, "
                    f"call `{call_name}` (target `{target}`) divides by "
                    f"`{divisor}` which is the constant 0; LLVM sdiv/srem by 0 "
                    f"is undefined behavior. Guard the divisor or change it."))
            elif (target in _STRICT_SHIFT_INT64_TARGETS and resolved is not None
                  and not (0 <= resolved <= 63)):
                diags.append((lineno,
                    f"SS4309 shiftCountOutOfRange: in operation `{op_name}`, "
                    f"call `{call_name}` (target `{target}`) shifts by "
                    f"`{divisor}` = {resolved}; shift counts must be in [0, 63] "
                    f"(a count outside that range is LLVM poison). Mask with & 63."))


def _strict_raise_first_constant_arith_ub(prog: Program, diags) -> None:
    if not diags:
        return
    lineno, message = sorted(diags)[0]
    code_match = re.match(r"(SS\d+)", message)
    code = code_match.group(1) if code_match else "SS4308"
    span = _strict_span(prog, lineno)
    if code == "SS4309":
        fixes = ["mask the shift count into [0, 63] with "
                 "`math.bitwiseAndInt64` against 63 before the shift"]
        hint = ("an out-of-range constant shift count is undefined at the LLVM "
                "level; keep the count in [0, 63]")
    else:
        fixes = ["guard the divide so it is unreachable when the divisor is 0, "
                 "or change the divisor to a non-zero value"]
        hint = ("a constant-zero divisor is always undefined behavior; it is "
                "never an intended program")
    raise CompilerDiagnosticError(CompilerDiagnostic(
        code=code,
        phase="semantic.strictExecutable",
        message=message,
        primary=span,
        semantic_stack=[
            DiagnosticFrame(
                kind="strictExecutable arithmetic-UB validation",
                span=span,
                note=("`languageMode strictExecutable` refuses arithmetic whose "
                      "operand is a compile-time-provable undefined value"),
            ),
        ],
        direction=("Strict executable rejects integer divide/modulo by a "
                   "constant zero and shifts by a constant outside [0, 63]; "
                   "these are LLVM UB/poison, not wraps."),
        suggested_fixes=fixes,
        agent_hint=hint,
    ))


def _check_strict_checked_arithmetic(prog: Program, diags) -> None:
    """SS3402 — math.addInt64 / subtractInt64 / multiplyInt64 results that
    look like sizes, byte counts, offsets, or timestamps must use the
    checked variant (`math.checkedAddInt64` + bindError + branchIfError).
    Heuristic on bound-name suffix; false negatives possible if the
    binding name is opaque."""
    for op_name, op in prog.operations.items():
        call_targets = _strict_call_target_map(op)
        for verb, args, _lineno in op.lines:
            if verb not in ("bind", "bindOk") or len(args) < 3:
                continue
            bound_name, _bound_type, source_call = args[0], args[1], args[2]
            target_info = call_targets.get(source_call)
            if target_info is None:
                continue
            target = _strict_target(prog, target_info[0])
            if target in _STRICT_CHECKED_ARITHMETIC_TARGETS:
                continue
            if target not in _STRICT_OVERFLOW_SENSITIVE_TARGETS:
                continue
            if not _STRICT_OVERFLOW_SENSITIVE_NAME_RE.search(bound_name):
                continue
            call_line = target_info[1]
            diags.append((call_line,
                f"SS3402 uncheckedSizeOrTimeArithmetic: in operation "
                f"`{op_name}`, call `{source_call}` (target `{target}`) "
                f"produces `{bound_name}` whose name suggests a "
                f"size/timestamp/byte-count; use the checked variant "
                f"(e.g. `math.checkedAddInt64` with `bindError` + "
                f"`branchIfError`)"))


def _strict_raise_first_overflow(prog: Program, diags) -> None:
    _strict_raise_first_simple(
        prog, diags, "SS3402",
        "strictExecutable checked-arithmetic validation",
        "Strict executable requires size/timestamp/byte-count arithmetic "
        "to use checked math primitives so overflow is observable.",
    )


def _strict_validate_use_after_free(prog: Program, op: Operation,
                                    calls: dict) -> None:
    """SS3309 — every read of a heap-owned pointer must precede its free.

    Walks the operation linearly per segment. A `run` of a c.free target
    marks the freed pointer as released; subsequent `arg` reads of that
    pointer on the same segment are flagged. Mutating control-flow verbs
    (label, returnOk/Error/Value/Void, branch) clear the freed set so a
    pointer freed on one path is not considered freed on a sibling path.
    Double-free is intentionally not reported here — SS3307 already
    covers that.
    """
    heap_owners = {}
    for call_info in calls.values():
        if call_info["target"] not in _STRICT_HEAP_ALLOCATION_TARGETS:
            continue
        for name in _strict_success_names(call_info):
            heap_owners[name] = call_info["name"]
    if not heap_owners:
        return
    cleanup_pointer_by_call = {}
    for call_info in calls.values():
        if call_info["target"] not in _STRICT_HEAP_CLEANUP_TARGETS:
            continue
        for arg_name, value_name, _line in call_info["args"]:
            if arg_name in ("pointer", "address", "ptr"):
                cleanup_pointer_by_call[call_info["name"]] = value_name
                break
    freed = set()
    for verb, args, lineno in op.lines:
        if verb == "label":
            freed = set()
            continue
        if verb in ("returnOk", "returnError", "returnValue",
                    "returnVoid", "branch"):
            freed = set()
            continue
        if verb == "arg" and len(args) >= 3:
            call_name, _arg_name, value_name = args[0], args[1], args[2]
            if value_name in heap_owners and value_name in freed:
                call_info = calls.get(call_name)
                target = call_info["target"] if call_info else ""
                if target not in _STRICT_HEAP_CLEANUP_TARGETS:
                    _strict_raise(
                        prog,
                        "SS3309",
                        f"SS3309 resourceLifecycle.useAfterFree: "
                        f"`{value_name}` is read by `{call_name}` after "
                        f"being released earlier on this control-flow "
                        f"segment",
                        op,
                        lineno,
                        call_name=call_name,
                        call_target=target,
                        note=(
                            f"`{value_name}` is owned by "
                            f"`{heap_owners[value_name]}`; releasing it "
                            "before the last read is undefined behavior"
                        ),
                    )
            continue
        if verb == "run" and args:
            value_name = cleanup_pointer_by_call.get(args[0])
            if value_name in heap_owners:
                freed.add(value_name)


_STRICT_SECRET_NAME_RE = re.compile(
    # Heap-owned bindings that appear to hold sensitive material. Anything
    # matching this pattern must be wiped via `c.memset` before the matching
    # `c.free` so a freed-but-not-yet-reused page does not carry the bytes into
    # the next allocation that reuses it.
    r"(?i)(password|secret|plaintext|privatekey|passphrase|credential)"
)

_STRICT_MEMSET_TARGETS = frozenset({"c.memset"})


def _strict_validate_secret_zeroing(prog: Program, op: Operation,
                                    calls: dict) -> None:
    """SS3320 — heap buffers whose binding names indicate sensitive
    material must be wiped with
    `c.memset(buffer, 0, capacity)` before the matching `c.free` (or
    `defer c.free`) fires. Without the wipe, `c.free` leaves the
    plaintext on a freed-but-not-yet-reused heap page where a separate
    memory-disclosure bug can read it.

    The check is per-operation rather than per-segment: it accepts any
    `c.memset` call on the secret pointer anywhere in the op body as
    evidence the wipe pattern is in place. Per-path precision is
    deferred; this catches the "no wipe at all" shape today.
    """
    secret_owners = set()
    for call_info in calls.values():
        if call_info["target"] not in _STRICT_HEAP_ALLOCATION_TARGETS:
            continue
        for name in _strict_success_names(call_info):
            if _STRICT_SECRET_NAME_RE.search(name):
                secret_owners.add(name)
    if not secret_owners:
        return

    freed_secrets = set()
    for call_info in calls.values():
        if call_info["target"] not in _STRICT_HEAP_CLEANUP_TARGETS:
            continue
        for arg_name, value_name, _line in call_info.get("args", []):
            if value_name in secret_owners:
                freed_secrets.add(value_name)
    for verb, args, _lineno in op.lines:
        if verb == "defer" and len(args) >= 3:
            if _strict_target(prog, args[1]) in _STRICT_HEAP_CLEANUP_TARGETS:
                for tail in args[2:]:
                    if tail in secret_owners:
                        freed_secrets.add(tail)

    if not freed_secrets:
        return

    zeroed = set()
    for call_info in calls.values():
        if call_info["target"] not in _STRICT_MEMSET_TARGETS:
            continue
        for arg_name, value_name, _line in call_info.get("args", []):
            if arg_name in ("ptr", "pointer", "buffer", "destination",
                            "address"):
                if value_name in freed_secrets:
                    zeroed.add(value_name)

    for name in sorted(freed_secrets - zeroed):
        producer = next(
            (call_info for call_info in calls.values()
             if name in _strict_success_names(call_info)),
            None,
        )
        producer_line = producer["line"] if producer else op.decl_line
        _strict_raise(
            prog,
            "SS3320",
            f"SS3320 secretBufferNotZeroedBeforeFree: heap buffer "
            f"`{name}` looks like it holds a secret (password / "
            f"plaintext / credential / etc.) and reaches `c.free` "
            f"without a preceding `c.memset({name}, 0, capacity)` "
            f"call. Freed-but-not-reused pages let the plaintext leak "
            f"into the next allocation that reuses the slot",
            op,
            producer_line,
            call_name=producer["name"] if producer else "",
            call_target=producer["target"] if producer else "",
            note=(
                "Either add `c.memset(" + name + ", 0, <capacity>)` "
                "before the matching `c.free` / defer, or rename the "
                "binding if it does NOT actually carry a secret"
            ),
        )


def validate_security_floor(prog: Program) -> None:
    """The always-on security floor: a small set of checks that block *every*
    build regardless of `languageMode`, because the patterns they catch are
    undefined behavior with NO legitimate use in any context (not even tests).

    This is deliberately narrow. Only pure, context-free UB lives here:
      * SS4308 — integer divide/modulo by a provable constant 0 (sdiv/srem UB).
      * SS4309 — shift by a provable constant outside [0, 63] (LLVM poison).

    Dual-use security rules (SS4601 insecure PRNG, SS4602 weak bcrypt cost) are
    deliberately NOT here — they have legitimate non-security / test uses, so
    they stay gated to `languageMode strictExecutable` plus an advisory lint
    floor. The floor is the fence that makes the UB rules bind default builds;
    without it those checks only fire under opt-in strict mode."""
    arith_ub_diags = []
    _check_strict_constant_division_or_shift(prog, arith_ub_diags)
    _strict_raise_first_constant_arith_ub(prog, arith_ub_diags)
    # Weak or missing bcrypt cost (CWE-916) has NO legitimate *production* use —
    # a sub-floor or unspecified work factor is only ever defensible at test
    # speed. So it blocks EVERY build, with one narrow exemption: `*.test.sem`
    # sources (which legitimately hash at low cost for fast tests) get only the
    # advisory. This is unlike the dual-use rules (insecure PRNG) that stay
    # advisory-on-default — a weak password hash is never intended in production.
    source_path = (getattr(prog, "source_path", "") or "")
    if not source_path.endswith((".test.sem", ".test.sscript")):
        weak_cost_diags = []
        _check_strict_weak_password_hash_cost(prog, weak_cost_diags)
        _strict_raise_first_weak_password_hash_cost(prog, weak_cost_diags)


def collect_security_advisories(prog: Program) -> list:
    """Run the SS46xx-family security checks (insecure PRNG, weak bcrypt cost,
    command injection, hard-coded secret) as a NON-blocking advisory pass for
    builds that have not opted into `languageMode strictExecutable`.

    Under strict these are fatal (via validate_strict_executable); on a default
    build the same findings are surfaced as warnings so an agent who never opts
    into strict still sees CWE-338/916/78/798 issues. Returns sorted
    (lineno, message) tuples; the caller prints them without exiting."""
    diags: list = []
    _check_strict_insecure_random(prog, diags)
    _check_strict_command_string_is_constant(prog, diags)
    _check_strict_weak_password_hash_cost(prog, diags)
    _check_strict_hardcoded_secret(prog, diags)
    # Injection floor consistency: SQL (D1) and format-string (J1) injection are
    # equally severe to command injection (D3). These run here post-import-
    # resolution (the program is fully built by main()), so the SqlText/format
    # constant determination is accurate — unlike a single-file lint scan.
    _check_strict_sql_string_is_constant(prog, diags)
    _check_strict_format_string_is_constant(prog, diags)
    return sorted(diags)


# Per-code agent guidance for the default-build advisory printer, so a non-strict
# warning is as actionable as the strict error (the strict raisers carry these;
# the advisory collectors return only (lineno, message), so the printer looks the
# guidance up here). Keyed by SS code -> (agent_hint, suggested_fix).
_SECURITY_ADVISORY_GUIDANCE = {
    "SS4601": ("libc rand/srand/random are deterministic generators",
               "use `bcrypt.randomBytes` (platform CSPRNG) for any "
               "security-sensitive value"),
    "SS4602": ("bcrypt cost is a work factor; a missing/low cost is "
               "brute-forceable",
               "set `cost Int32 bcryptRecommendedCost` (12)"),
    "SS4603": ("never build a shell command from input/runtime values",
               "pass a compile-time-constant String to c.system, or avoid "
               "shelling out"),
    "SS4604": ("a typeTrust-secret value must never be a source literal",
               "declare an empty `\"\"` sentinel and fill it at runtime from "
               "`c.getenv` / secure config"),
    "SS3911": ("untrusted data must not be concatenated into SQL",
               "use a module-scope immutable `SqlText` constant + sqlite.bind* "
               "for values"),
    "SS3310": ("a runtime format string allows %n/%s injection",
               "use a `storage * immutable String` format and pass values as "
               "arguments"),
}


def validate_strict_executable(prog: Program) -> None:
    if not _strict_executable_is_active(prog):
        return
    fallible_call_diags = []
    _check_strict_checked_fallible_calls(prog, fallible_call_diags)
    _strict_raise_first_fallible_contract(prog, fallible_call_diags)
    http_contract_diags = []
    _check_http_contracts(prog, http_contract_diags)
    _strict_raise_first_http_contract(prog, http_contract_diags)
    reachability_diags = []
    _check_strict_unreachable_operation_rows(prog, reachability_diags)
    _strict_raise_first_reachability(prog, reachability_diags)
    forbidden_call_diags = []
    _check_strict_forbidden_call_targets(prog, forbidden_call_diags)
    _strict_raise_first_forbidden_target(prog, forbidden_call_diags)
    insecure_random_diags = []
    _check_strict_insecure_random(prog, insecure_random_diags)
    _strict_raise_first_insecure_random(prog, insecure_random_diags)
    weak_hash_cost_diags = []
    _check_strict_weak_password_hash_cost(prog, weak_hash_cost_diags)
    _strict_raise_first_weak_password_hash_cost(prog, weak_hash_cost_diags)
    constant_string_diags = []
    _check_strict_format_string_is_constant(prog, constant_string_diags)
    _check_strict_sql_string_is_constant(prog, constant_string_diags)
    _strict_raise_first_constant_string_violation(prog, constant_string_diags)
    command_injection_diags = []
    _check_strict_command_string_is_constant(prog, command_injection_diags)
    _strict_raise_first_command_injection(prog, command_injection_diags)
    hardcoded_secret_diags = []
    _check_strict_hardcoded_secret(prog, hardcoded_secret_diags)
    _strict_raise_first_hardcoded_secret(prog, hardcoded_secret_diags)
    sql_usage_diags = []
    _check_sqlite_sql_body_usage(prog, sql_usage_diags)
    _check_sqlite_write_then_read_usage(prog, sql_usage_diags)
    _check_sqlite_multiple_writes_have_transaction(prog, sql_usage_diags)
    _check_sqlite_returning_statement_drained_before_commit(
        prog, sql_usage_diags)
    _check_strict_sqlite_last_insert_rowid_calls(prog, sql_usage_diags)
    _strict_raise_first_sql_usage_violation(prog, sql_usage_diags)
    process_environment_diags = []
    _check_strict_process_environment_reads_cached(
        prog, process_environment_diags)
    _strict_raise_first_process_environment_violation(
        prog, process_environment_diags)
    request_time_diags = []
    _check_strict_repeated_request_time_reads(prog, request_time_diags)
    _strict_raise_first_request_time_violation(prog, request_time_diags)
    idempotency_replay_diags = []
    _check_strict_idempotency_replay_uses_response_status(
        prog, idempotency_replay_diags)
    _strict_raise_first_idempotency_replay_violation(
        prog, idempotency_replay_diags)
    large_static_literal_diags = []
    _check_strict_large_local_static_literals(prog, large_static_literal_diags)
    _strict_raise_first_large_static_literal_violation(
        prog, large_static_literal_diags)
    step_disposition_diags = []
    _check_strict_step_result_disposition(prog, step_disposition_diags)
    _strict_raise_first_step_disposition(prog, step_disposition_diags)
    handler_response_diags = []
    _check_strict_handler_writes_response(prog, handler_response_diags)
    _strict_raise_first_handler_response(prog, handler_response_diags)
    shared_state_diags = []
    _check_strict_shared_state_lock(prog, shared_state_diags)
    _strict_raise_first_shared_state(prog, shared_state_diags)
    overflow_diags = []
    _check_strict_checked_arithmetic(prog, overflow_diags)
    _strict_raise_first_overflow(prog, overflow_diags)
    # SS4308/SS4309 (constant divide-by-zero / out-of-range shift) are enforced
    # unconditionally by validate_security_floor(), so they are not repeated
    # here — they block every build, not just strict ones.
    for op in prog.operations.values():
        calls = _strict_collect_calls(prog, op)
        defers = _strict_collect_defers(op)
        _strict_validate_heap_resources(prog, op, calls, defers)
        _strict_validate_sqlite_database_cleanup(prog, op, calls, defers)
        _strict_validate_sqlite_statement_cleanup(prog, op, calls, defers)
        _strict_validate_use_after_free(prog, op, calls)
        _strict_validate_secret_zeroing(prog, op, calls)


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
      duplicatedDomainLiteral     -- docs/ast.md invariant 8
      groupCommentBalance         -- §7 attention anchors
      failureLabelAggregation     -- §12 failure flow precision
    """
    diags = []

    # ---- module-level: group/endGroup balance ----
    _check_group_balance(prog.module_group_anchors, diags, scope="module")

    # ---- module-level: duplicated domain literals ----
    _check_duplicated_domain_literals(prog, diags)

    for op_name, op in prog.operations.items():
        wait_set_case_calls = set()
        wait_set_handler_labels = set()
        label_before_line = {}
        current_label = None
        for verb, args, lineno in op.lines:
            label_before_line[lineno] = current_label
            if verb == "label" and args:
                current_label = args[0]
            elif verb == "case" and len(args) >= 2:
                wait_set_case_calls.add(args[0])
                wait_set_handler_labels.add(args[1])

        def call_in_wait_set_completion_context(call_name, info):
            if call_name in wait_set_case_calls:
                return True
            return any(
                label_before_line.get(line) in wait_set_handler_labels
                for line in info.get("run_lines", [])
            )

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
                    "target": prog.operation_aliases.get(
                        _TARGET_ALIASES.get(target, target),
                        _TARGET_ALIASES.get(target, target)),
                    "has_bindError": False,
                    "has_branchIfError": False,
                    "run_lines": [],
                    "related_lines": [],
                }
                if not call_name.endswith("Call"):
                    diags.append((lineno,
                        f"vagueCallName: `{call_name}` should end with the Call role suffix"))
                if target in ("console.writeLine", "console.writeIntegerLine"):
                    operation_uses_console_write = True
            elif verb == "run" and args:
                call_name = args[0]
                if call_name in calls:
                    calls[call_name]["run_lines"].append(lineno)
            elif verb == "bindError" and len(args) >= 3:
                call_name = args[2]
                if call_name in calls:
                    calls[call_name]["has_bindError"] = True
                    calls[call_name]["related_lines"].append(lineno)
                err_name = args[0]
                if not err_name.endswith("Error"):
                    diags.append((lineno,
                        f"vagueErrorName: `{err_name}` should end with the Error role suffix"))
            elif verb == "bind" and len(args) >= 4 and args[0] == "error":
                call_name = args[3]
                if call_name in calls:
                    calls[call_name]["has_bindError"] = True
                    calls[call_name]["related_lines"].append(lineno)
                err_name = args[1]
                if not err_name.endswith("Error"):
                    diags.append((lineno,
                        f"vagueErrorName: `{err_name}` should end with the Error role suffix"))
            elif verb == "branchIfError" and args:
                call_name = args[0]
                if call_name in calls:
                    calls[call_name]["has_branchIfError"] = True
                    calls[call_name]["related_lines"].append(lineno)
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
            elif verb == "branch" and len(args) >= 5 and args[0] == "if" and args[1] == "condition" and args[3] == "target":
                label_references.append((args[4], lineno, "branch if"))
                if args[4] in labels_declared:
                    operation_has_loop = True
            elif verb == "branch" and len(args) >= 5 and args[0] == "error" and args[1] == "source" and args[3] == "target":
                call_name = args[2]
                if call_name in calls:
                    calls[call_name]["has_branchIfError"] = True
                    calls[call_name]["related_lines"].append(lineno)
                label_references.append((args[4], lineno, "branch error"))
                branchIfError_targets.setdefault(args[4], []).append((call_name, lineno))
                if not (args[4].endswith("Failed") or args[4].endswith("ed")):
                    diags.append((lineno,
                        f"roleSuffixMismatch: branch label `{args[4]}` should end with Failed or a past-tense -ed form"))
                if args[4] in labels_declared:
                    operation_has_loop = True
            elif verb == "branch" and len(args) >= 3 and args[0] == "else" and args[1] == "target":
                label_references.append((args[2], lineno, "branch else"))
                if args[2] in labels_declared:
                    operation_has_loop = True
            elif verb == "jump" and len(args) >= 2 and args[0] == "target":
                label_references.append((args[1], lineno, "jump"))
                if args[1] in labels_declared:
                    operation_has_loop = True
            elif verb == "branch" and args:
                label_references.append((args[0], lineno, "branch"))
                # A `branch` to a label that has already been declared earlier
                # in source order represents a backward edge — i.e. a loop.
                if args[0] in labels_declared:
                    operation_has_loop = True
            elif verb == "case" and len(args) >= 2:
                label_references.append((args[1], lineno, "case"))
                if args[1] in labels_declared:
                    operation_has_loop = True
            elif verb == "done" and args:
                label_references.append((args[0], lineno, "done"))
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
            if (info["has_bindError"] and not info["has_branchIfError"]
                    and not call_in_wait_set_completion_context(call_name, info)):
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
                if len(distinct) <= 1:
                    continue
                if lbl not in labels_declared:
                    continue
                # §12 wants the cause pinned. When every distinct caller
                # has its own `bindError` row, the cause IS pinned per
                # call (each call's error value lives in its own named
                # binding) even if all callers converge on one response
                # label — that convergence is the idiomatic "one body
                # per failure category" shape the apps use. Fire only
                # when at least one caller branched WITHOUT capturing
                # its error, i.e. the cause is genuinely lost.
                if all(calls.get(call_name, {}).get("has_bindError")
                       for call_name in distinct):
                    continue
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

    # ---- strict-only: fallible calls must use checked error flow ----
    if strict:
        _check_strict_checked_fallible_calls(prog, diags)

    # ---- per-operation: Result A B contract is checked at returns ----
    _check_result_contract(prog, diags)

    # ---- native HTTP strict-executable contracts mirrored from SS36xx ----
    _check_http_contracts(prog, diags)

    # ---- performance advisories: arena + prepared-statement cache hints ----
    # These don't catch correctness bugs; they catch patterns where the
    # request hot path is doing avoidable work. Each is opt-out by removing
    # the matching pattern (or coalescing into the suggested primitive).
    _check_many_small_mallocs_in_op(prog, diags)
    _check_repeated_prepare_statement_same_sql(prog, diags)
    _check_sqlite_sql_body_usage(prog, diags)

    # ---- security advisories: secret-buffer wipe ----
    # These ARE correctness bugs (security ones); they advise here so
    # `sem check` surfaces them, and `validate_strict_executable` upgrades
    # them to compile errors when the file declares
    # `languageMode strictExecutable`.
    _check_lint_secret_buffer_not_zeroed(prog, diags)
    _check_multiple_writes_without_transaction(prog, diags)
    _check_dead_sql_constant(prog, diags)

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
    edits propagate (docs/ast.md invariant 8). Exempt programs declared as
    `mode capturedOutputReplay`: their consts are positional transcript
    rows whose role identity is the position, not the value."""
    if "capturedOutputReplay" in prog.modes:
        return
    seen = {}   # value -> first const name that held it
    for name, (typ, value) in prog.consts.items():
        if "." in name:
            continue
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
        if "." in name:
            continue
        targets.append(("capability", name))
    for name in prog.records:
        if "." in name:
            continue
        targets.append(("record", name))
    for name in prog.web_servers:
        if "." in name:
            continue
        targets.append(("webServer", name))
    for kind, name in targets:
        meta = prog.hard_metadata.get(name, {})
        if "purpose" not in meta:
            diags.append((0,
                f"missingPurpose: {kind} `{name}` declares no `purpose` line (§3 abstraction admission test)"))


def _check_identifier_casing(prog: Program, diags):
    """Spec §6: PascalCase for types/records/enums/errors/enum variants;
    camelCase for values/calls/labels/operations/vars/consts."""
    def local_name(name):
        return name.rsplit(".", 1)[-1]
    def is_pascal(name):
        return bool(name) and name[0].isupper()
    def is_camel(name):
        return bool(name) and name[0].islower()
    # PascalCase declarations
    for name in prog.type_aliases:
        if "." in name:
            continue
        if not is_pascal(local_name(name)):
            diags.append((0,
                f"casingViolation: type `{name}` should start with uppercase (PascalCase) per §6"))
    for name in prog.errors:
        if "." in name:
            continue
        if not is_pascal(local_name(name)):
            diags.append((0,
                f"casingViolation: error type `{name}` should start with uppercase per §6"))
    for variants in prog.errors.values():
        for vname, _cause in variants:
            if not is_pascal(vname):
                diags.append((0,
                    f"casingViolation: error variant `{vname}` should start with uppercase per §6"))
    for name in prog.records:
        if "." in name:
            continue
        if not is_pascal(local_name(name)):
            diags.append((0,
                f"casingViolation: record `{name}` should start with uppercase per §6"))
    for name in prog.enums:
        if "." in name:
            continue
        if not is_pascal(local_name(name)):
            diags.append((0,
                f"casingViolation: enum `{name}` should start with uppercase per §6"))
    # camelCase declarations
    for op_name in prog.operations:
        if not is_camel(op_name):
            diags.append((0,
                f"casingViolation: operation `{op_name}` should start with lowercase (camelCase) per §6"))
    for name in prog.consts:
        if "." in name:
            continue
        if not is_camel(local_name(name)):
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
        elif verb == "memory" and len(args) >= 5 and args[1] in ("mutable", "immutable"):
            values[args[2]] = args[4]
    return values


def _operation_call_args(op):
    call_args = {}
    for verb, args, _ in op.lines:
        if verb == "argument" and len(args) >= 4:
            call_args.setdefault(args[0], {})[args[1]] = args[3]
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
                authority_facts.append({"access": parts[0], "effect": parts[1]})

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


_MANY_MALLOCS_THRESHOLD_COUNT = 4
_MANY_MALLOCS_THRESHOLD_BYTES = 8192
_MALLOC_FAMILY_TARGETS = frozenset({"c.malloc", "c.calloc", "c.realloc"})


def _check_many_small_mallocs_in_op(prog: Program, diags):
    """SS3318 — advisory: if an operation issues ≥4 c.malloc-family calls
    whose declared sizes sum to ≤ 8 KiB and none of the returned pointers
    escape via returnOk/returnValue, recommend an arena (one upfront
    malloc + pointer.offset advances). The per-malloc allocator round-trip
    is the bottleneck for small short-lived buffers; coalescing into one
    allocation also colocates the scratch surface so the CPU prefetcher
    sees contiguous accesses instead of randomly-placed pages.
    """
    for op_name, op in prog.operations.items():
        malloc_calls = []
        call_targets = _strict_call_target_map(op)
        for call_name, (target, lineno) in call_targets.items():
            if _strict_target(prog, target) in _MALLOC_FAMILY_TARGETS:
                malloc_calls.append((call_name, lineno))
        if len(malloc_calls) < _MANY_MALLOCS_THRESHOLD_COUNT:
            continue
        size_arg_by_call = {}
        for verb, args, _lineno in op.lines:
            if verb != "arg" or len(args) < 3:
                continue
            if args[0] in dict(malloc_calls) and args[1] == "size":
                size_arg_by_call[args[0]] = args[2]
        total_bytes = 0
        unresolved = False
        for call_name, _line in malloc_calls:
            size_name = size_arg_by_call.get(call_name)
            if size_name is None:
                unresolved = True
                break
            const = prog.consts.get(size_name)
            if const is None:
                unresolved = True
                break
            try:
                total_bytes += int(const[1])
            except (TypeError, ValueError):
                unresolved = True
                break
        if unresolved or total_bytes > _MANY_MALLOCS_THRESHOLD_BYTES:
            continue
        # Skip when any malloc's bound name appears in a returnOk/returnValue.
        # That marks the allocation as escaping ownership to the caller, so
        # an arena coalesce would break the caller's lifetime contract.
        owned_names = set()
        for verb, args, _lineno in op.lines:
            if verb in ("bind", "bindOk") and len(args) >= 3:
                if args[2] in dict(malloc_calls):
                    owned_names.add(args[0])
        escapes = False
        for verb, args, _lineno in op.lines:
            if verb in ("returnOk", "returnValue") and args:
                if args[0] in owned_names:
                    escapes = True
                    break
        if escapes:
            continue
        primary_line = malloc_calls[0][1]
        diags.append((primary_line,
            f"SS3318 manySmallMallocsSuggestArena: operation `{op_name}` "
            f"issues {len(malloc_calls)} c.malloc-family calls totalling "
            f"{total_bytes} bytes within the request lifetime; consider one "
            f"upfront `c.malloc handlerArena <total>` + `pointer.offset` "
            f"advances. Each per-buffer malloc costs an allocator round-trip "
            f"(~100ns) and scatters the scratch surface across heap pages, "
            f"defeating the prefetcher"))


def _check_repeated_prepare_statement_same_sql(prog: Program, diags):
    """SS3319 — advisory: if a module immutable SQL byte-string
    SQL constant is passed as the `sql` arg to `sqlite.prepareStatement`
    in more than one operation (or more than once in any single
    operation), recommend a prepared-statement cache. Every prepare/
    finalize pair re-runs the SQLite parser + planner; for hot lookups
    that run on every request or event, this can dominate latency.
    """
    sql_usage = {}  # sql_const_name -> list[(op_name, call_name, lineno)]
    for op_name, op in prog.operations.items():
        call_targets = _strict_call_target_map(op)
        for verb, args, lineno in op.lines:
            arg_parts = _strict_argument_parts(verb, args)
            if arg_parts is None:
                continue
            call_name, arg_name, value_name = arg_parts
            target_info = call_targets.get(call_name)
            if target_info is None:
                continue
            if _strict_target(prog, target_info[0]) != "sqlite.prepareStatement":
                continue
            if arg_name != "sql":
                continue
            sql_usage.setdefault(value_name, []).append(
                (op_name, call_name, lineno))
    for sql_name, sites in sql_usage.items():
        if len(sites) < 2:
            continue
        op_set = {op for op, _call, _line in sites}
        primary_line = sites[0][2]
        if len(op_set) > 1:
            diags.append((primary_line,
                f"SS3319 repeatedPrepareSuggestStatementCache: SQL constant "
                f"`{sql_name}` is prepared by {len(op_set)} different "
                f"operations ({sorted(op_set)}); each call re-runs the "
                f"SQLite parser + planner. Consider a prepared-statement "
                f"cache keyed by the SQL constant so the first request "
                f"plans and subsequent requests reuse via "
                f"`sqlite3_reset`"))
        else:
            diags.append((primary_line,
                f"SS3319 repeatedPrepareSuggestStatementCache: operation "
                f"`{sites[0][0]}` prepares SQL constant `{sql_name}` "
                f"{len(sites)} times; hoist the prepare out of the loop "
                f"or cache the statement"))


_LINT_SQL_VERB_RE = re.compile(
    r"(?is)^\s*(?:--[^\n]*\n\s*)*"
    r"(SELECT|INSERT|UPDATE|DELETE|CREATE|DROP|ALTER|REPLACE|PRAGMA|"
    r"BEGIN|COMMIT|ROLLBACK|SAVEPOINT|RELEASE|WITH)\b"
)

_LINT_WRITE_VERB_RE = re.compile(
    r"(?is)^\s*(?:--[^\n]*\n\s*)*"
    r"(INSERT|UPDATE|DELETE|REPLACE)\b"
)

_LINT_TRANSACTION_VERB_RE = re.compile(
    r"(?is)^\s*(?:--[^\n]*\n\s*)*"
    r"(BEGIN|COMMIT|ROLLBACK|SAVEPOINT|RELEASE)\b"
)


def _check_lint_secret_buffer_not_zeroed(prog: Program, diags):
    """SS3320 advisory — heap buffers whose binding names match the
    secret pattern (`password`/`secret`/`plaintext`/etc.) should be
    `c.memset` wiped before the matching `c.free` / defer fires.
    Mirrors the strict-mode `_strict_validate_secret_zeroing`; the
    lint advisory fires unconditionally so apps without
    `languageMode strictExecutable` still see the warning."""
    for op_name, op in prog.operations.items():
        calls = _strict_collect_calls(prog, op)
        secret_owners = set()
        producers = {}
        for call_info in calls.values():
            if call_info["target"] not in _STRICT_HEAP_ALLOCATION_TARGETS:
                continue
            for name in _strict_success_names(call_info):
                if _STRICT_SECRET_NAME_RE.search(name):
                    secret_owners.add(name)
                    producers[name] = call_info
        if not secret_owners:
            continue
        freed_secrets = set()
        for call_info in calls.values():
            if call_info["target"] not in _STRICT_HEAP_CLEANUP_TARGETS:
                continue
            for _arg, value_name, _line in call_info.get("args", []):
                if value_name in secret_owners:
                    freed_secrets.add(value_name)
        for verb, args, _lineno in op.lines:
            if verb == "defer" and len(args) >= 3:
                if _strict_target(prog, args[1]) in _STRICT_HEAP_CLEANUP_TARGETS:
                    for tail in args[2:]:
                        if tail in secret_owners:
                            freed_secrets.add(tail)
        if not freed_secrets:
            continue
        zeroed = set()
        for call_info in calls.values():
            if call_info["target"] not in _STRICT_MEMSET_TARGETS:
                continue
            for arg_name, value_name, _line in call_info.get("args", []):
                if arg_name in ("ptr", "pointer", "buffer", "destination",
                                "address"):
                    if value_name in freed_secrets:
                        zeroed.add(value_name)
        for name in sorted(freed_secrets - zeroed):
            producer = producers.get(name)
            primary_line = producer["line"] if producer else op.decl_line
            diags.append((primary_line,
                f"SS3320 secretBufferNotZeroedBeforeFree: in operation "
                f"`{op_name}`, heap buffer `{name}` looks like it holds "
                f"a secret (password / plaintext / credential / etc.) "
                f"and reaches `c.free` without a preceding "
                f"`c.memset({name}, 0, capacity)`. The freed page can "
                f"leak the plaintext into a later allocation that "
                f"reuses the slot. Either wipe via c.memset before "
                f"the free, or rename the binding if it does not hold "
                f"a secret"))


def _check_multiple_writes_without_transaction(prog: Program, diags):
    """SS3411 advisory — if an op executes 2+ INSERT/UPDATE/DELETE
    statements (each via prepareStatement + step), AND the op does
    not exec a BEGIN/COMMIT pair, warn about the atomicity gap.
    Without the transaction, a step failure on the second write leaves the
    first write committed, producing partial state."""
    for op_name, op in prog.operations.items():
        write_step_count = 0
        opened_transaction = False
        call_targets = _strict_call_target_map(op)
        for call_name, (target, _line) in call_targets.items():
            canonical = _strict_target(prog, target)
            if canonical == "sqlite.stepStatement":
                # Find the matching prepareStatement's sql arg
                prep_sql = _operation_step_call_to_sql(prog, op, call_name)
                if prep_sql is None:
                    continue
                const = prog.consts.get(prep_sql)
                if const is None:
                    continue
                if not _is_sql_constant_type(prog, const[0]):
                    continue
                value = const[1]
                if not isinstance(value, str):
                    continue
                if _LINT_WRITE_VERB_RE.match(value):
                    write_step_count += 1
            elif canonical in _STRICT_SQL_EXEC_TARGETS:
                # If any sqlite.exec arg's sql is a BEGIN/COMMIT/etc.
                pass
        for verb, args, _lineno in op.lines:
            arg_parts = _strict_argument_parts(verb, args)
            if arg_parts is None:
                continue
            call_name, arg_name, value_name = arg_parts
            target_info = call_targets.get(call_name)
            if target_info is None:
                continue
            if _strict_target(prog, target_info[0]) not in _STRICT_SQL_EXEC_TARGETS:
                continue
            if arg_name != "sql":
                continue
            const = prog.consts.get(value_name)
            if const is None:
                continue
            if not _is_sql_constant_type(prog, const[0]):
                continue
            value = const[1]
            if isinstance(value, str) and _LINT_TRANSACTION_VERB_RE.match(value):
                opened_transaction = True
        if write_step_count >= 2 and not opened_transaction:
            diags.append((op.decl_line,
                f"SS3411 multipleWritesWithoutTransaction: operation "
                f"`{op_name}` executes {write_step_count} write "
                f"statements (INSERT/UPDATE/DELETE) without an "
                f"enclosing `sqlite.exec BEGIN` / `sqlite.exec COMMIT` "
                f"pair. A failure between the writes leaves earlier "
                f"writes committed and later ones rolled back — "
                f"consistency hazard. Wrap the writes in a SQLite "
                f"transaction"))


def _operation_step_call_to_sql(prog: Program, op: Operation,
                                step_call_name: str) -> str:
    """Best-effort lookup: given a `sqlite.stepStatement` call name, find
    the SQL constant that was passed to the matching prepareStatement.
    The matching prepare is identified by following the SqliteStatement
    binding the step's `statement` arg references back to the
    prepareStatement that produced it."""
    statement_arg = None
    for verb, args, _lineno in op.lines:
        arg_parts = _strict_argument_parts(verb, args)
        if arg_parts is None:
            continue
        call_name, arg_name, value_name = arg_parts
        if call_name == step_call_name and arg_name == "statement":
            statement_arg = value_name
            break
    if statement_arg is None:
        return None
    prepare_call_name = None
    for verb, args, _lineno in op.lines:
        if verb == "bind" and len(args) >= 4:
            if args[0] in ("ok", "value") and args[1] == statement_arg:
                prepare_call_name = args[3]
                break
        if verb == "bindOk" and len(args) >= 3:
            if args[0] == statement_arg:
                prepare_call_name = args[2]
                break
    if prepare_call_name is None:
        return None
    for verb, args, _lineno in op.lines:
        arg_parts = _strict_argument_parts(verb, args)
        if arg_parts is None:
            continue
        call_name, arg_name, value_name = arg_parts
        if call_name == prepare_call_name and arg_name == "sql":
            return value_name
    return None


def _check_dead_sql_constant(prog: Program, diags):
    """SS3415 advisory — a module immutable SQL byte-string
    row whose value begins with a SQL verb (SELECT/INSERT/UPDATE/DELETE/
    CREATE/PRAGMA/etc.) but which is never passed as the `sql` arg of
    `sqlite.prepareStatement` or `sqlite.exec` is dead weight. Flag it
    so the user can either delete the constant or wire it into the
    code path the SQL was meant for."""
    sql_constants = {}
    for name, (typ, value) in prog.consts.items():
        if not _is_sql_constant_type(prog, typ):
            continue
        if name in prog.mutable_globals:
            continue
        if not isinstance(value, str):
            continue
        if not _LINT_SQL_VERB_RE.match(value):
            continue
        sql_constants[name] = value
    if not sql_constants:
        return
    referenced = set()
    for op in prog.operations.values():
        call_targets = _strict_call_target_map(op)
        for verb, args, _lineno in op.lines:
            arg_parts = _strict_argument_parts(verb, args)
            if arg_parts is not None:
                call_name, arg_name, value_name = arg_parts
                if arg_name == "sql":
                    target_info = call_targets.get(call_name)
                    if target_info is not None:
                        target = _strict_target(prog, target_info[0])
                        if target == "sqlite.prepareStatement" or target in _STRICT_SQL_EXEC_TARGETS:
                            referenced.add(value_name)
                continue
            # defer rows that wrap sqlite.exec pass positional args: the
            # second positional (defer NAME sqlite.exec DATABASE SQL) is
            # the SQL constant. Without this branch, deferred rollback
            # statements would look "dead" because the named-arg walk
            # above never sees them.
            if verb == "defer" and len(args) >= 4:
                if _strict_target(prog, args[1]) in _STRICT_SQL_EXEC_TARGETS:
                    # args = [NAME, sqlite.exec, DATABASE, SQL, ...]
                    referenced.add(args[3])
    for name in sorted(set(sql_constants) - referenced):
        diags.append((0,
            f"SS3415 deadSqlConstant: SQL constant `{name}` is declared "
            f"but never referenced by `sqlite.prepareStatement`, "
            f"`sqlite.exec`, or `sqlite.execStatus`. Either delete the "
            f"declaration or wire it "
            f"into the handler it was meant for"))


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


def _strict_normalized_call_target(prog: Program, target: str) -> str:
    target = _TARGET_ALIASES.get(target, target)
    target = prog.operation_aliases.get(target, target)
    if target.startswith("c."):
        semantic_name = target[2:]
        c_symbol = libc_registry.resolve_c_symbol(semantic_name)
        if c_symbol:
            normalized = f"c.{c_symbol}"
            if normalized in _STRICT_FALLIBLE_CALL_TARGETS:
                return normalized
    return target


def _check_strict_checked_fallible_calls(prog: Program, diags):
    """Strict executable mode rejects unchecked fallible call sites.

    A result-shaped fallible call is checked when it uses `runChecked`, or
    when it uses the explicit shape: `run`, a success disposition
    (`bind ok`, `ignore ok`, or `ignore void`), `bind error`, and
    `branch error`.
    """
    for op_name, op in prog.operations.items():
        wait_set_case_calls = set()
        wait_set_handler_labels = set()
        label_before_line = {}
        current_label = None
        for verb, args, lineno in op.lines:
            label_before_line[lineno] = current_label
            if verb == "label" and args:
                current_label = args[0]
            elif verb == "case" and len(args) >= 2:
                wait_set_case_calls.add(args[0])
                wait_set_handler_labels.add(args[1])

        def in_wait_set_completion_context(info):
            if info["name"] in wait_set_case_calls:
                return True
            return any(
                label_before_line.get(line) in wait_set_handler_labels
                for line in info["execution_lines"]
            )

        def is_wait_set_handler_line(line):
            return label_before_line.get(line) in wait_set_handler_labels

        def after_last_execution(line, info):
            if not info["execution_lines"]:
                return True
            return line > max(info["execution_lines"])

        def ordered_success_disposition_lines(info, wait_set_completion_context):
            return [
                line
                for line in info["success_disposition_lines"]
                if after_last_execution(line, info)
                and (
                    not wait_set_completion_context
                    or is_wait_set_handler_line(line)
                )
            ]

        def ordered_bind_error_lines(info, wait_set_completion_context):
            return [
                line
                for line in info["bind_error_lines"]
                if after_last_execution(line, info)
                and (
                    not wait_set_completion_context
                    or is_wait_set_handler_line(line)
                )
            ]

        def ordered_handler_ignore_error_lines(info):
            return [
                line
                for line in info["ignore_error_lines"]
                if after_last_execution(line, info)
                and is_wait_set_handler_line(line)
            ]

        def ordered_branch_error_lines(info):
            return [
                line
                for line in info["branch_error_lines"]
                if after_last_execution(line, info)
            ]

        def has_ordered_value_disposition(info):
            return any(
                after_last_execution(line, info)
                for line in info["value_disposition_lines"]
            )

        calls = {}
        for verb, args, lineno in op.lines:
            if verb == "call" and len(args) >= 2:
                target = _strict_normalized_call_target(prog, args[1])
                calls[args[0]] = {
                    "name": args[0],
                    "target": target,
                    "source_target": args[1],
                    "call_lineno": lineno,
                    "execution_lineno": None,
                    "execution_lines": [],
                    "success_disposition_lines": [],
                    "value_disposition_lines": [],
                    "bind_error_lines": [],
                    "ignore_error_lines": [],
                    "branch_error_lines": [],
                    "has_run_checked": False,
                    "has_success_disposition": False,
                    "has_value_disposition": False,
                    "has_bind_error": False,
                    "has_ignore_error": False,
                    "has_branch_if_error": False,
                }
                continue
            if not args:
                continue
            if verb == "run":
                info = calls.get(args[0])
                if info is not None:
                    if info["execution_lineno"] is None:
                        info["execution_lineno"] = lineno
                    info["execution_lines"].append(lineno)
                continue
            if verb in ("start", "startInGroup", "await"):
                info = calls.get(args[0])
                if info is not None:
                    if info["execution_lineno"] is None:
                        info["execution_lineno"] = lineno
                    info["execution_lines"].append(lineno)
                continue
            if verb == "runChecked":
                info = calls.get(args[0])
                if info is not None:
                    info["has_run_checked"] = True
                continue
            if verb == "bind" and len(args) >= 4 and args[0] in ("value", "ok"):
                call_name = args[3]
                info = calls.get(call_name)
                if info is not None:
                    info["has_value_disposition"] = True
                    info["value_disposition_lines"].append(lineno)
                    if args[0] == "ok":
                        info["has_success_disposition"] = True
                        info["success_disposition_lines"].append(lineno)
                continue
            if verb == "ignore" and len(args) >= 3:
                call_name = args[2]
                info = calls.get(call_name)
                if info is not None:
                    if args[0] in ("value", "ok", "void"):
                        info["has_value_disposition"] = True
                        info["value_disposition_lines"].append(lineno)
                    if args[0] in ("ok", "void"):
                        info["has_success_disposition"] = True
                        info["success_disposition_lines"].append(lineno)
                    if args[0] == "error":
                        info["has_ignore_error"] = True
                        info["ignore_error_lines"].append(lineno)
                continue
            if verb == "bind" and len(args) >= 4 and args[0] == "error":
                info = calls.get(args[3])
                if info is not None:
                    info["has_bind_error"] = True
                    info["bind_error_lines"].append(lineno)
                continue
            if verb == "branch" and len(args) >= 5 and args[0] == "error":
                info = calls.get(args[2])
                if info is not None:
                    info["has_branch_if_error"] = True
                    info["branch_error_lines"].append(lineno)

        for call_name, info in calls.items():
            kind = fallibility_kind(info["target"])
            if kind is None:
                continue
            if info["has_run_checked"] and info["execution_lines"]:
                diags.append((info["execution_lines"][0],
                    f"uncheckedFallibleCall: strict mode rejects mixing "
                    f"unchecked execution with `runChecked` for known fallible target "
                    f"`{info['source_target']}` in operation `{op_name}`; "
                    f"call `{call_name}` was declared on line "
                    f"{info['call_lineno']}. Use `runChecked` for every "
                    "execution or remove it and use the explicit checked "
                    "`run`/`start` + disposition shape."))
                continue
            if info["has_run_checked"]:
                continue
            if info["execution_lineno"] is None:
                continue
            missing = []
            if kind == "result":
                wait_set_completion_context = in_wait_set_completion_context(info)
                handler_ignore_error = ordered_handler_ignore_error_lines(info)
                if not ordered_success_disposition_lines(
                        info,
                        wait_set_completion_context):
                    missing.append("bind ok|ignore ok|ignore void")
                if (not ordered_bind_error_lines(
                            info,
                            wait_set_completion_context)
                        and not (wait_set_completion_context
                                 and handler_ignore_error)):
                    missing.append(
                        "bind error|ignore error"
                        if wait_set_completion_context else "bind error")
                if (not wait_set_completion_context
                        and not ordered_branch_error_lines(info)):
                    missing.append("branch error")
            else:
                if not has_ordered_value_disposition(info):
                    missing.append("bind value|ignore value")
            if not missing:
                continue
            if kind == "result":
                advice = (
                    "Use `runChecked`, or the checked pattern: `run`, "
                    "`bind ok`/`ignore ok`/`ignore void`, `bind error`, "
                    "and `branch error`."
                )
            else:
                advice = (
                    "Bind the returned status/pointer or explicitly discard it "
                    "with `ignore value` after documenting why the failure is "
                    "non-actionable."
                )
            diags.append((info["execution_lineno"],
                f"uncheckedFallibleCall: strict mode rejects unchecked "
                f"execution "
                f"for known fallible target `{info['source_target']}` in "
                f"operation `{op_name}`; call `{call_name}` was declared on "
                f"line {info['call_lineno']} and is missing "
                f"{', '.join(missing)}. {advice}"))


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
                elif ok_type in ("Void", "Void"):
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


def _render_windows_gui_manifest() -> str:
    """Return the manifest used by `windowsGui` executables.

    The Common Controls v6 dependency is what switches classic Win32 control
    classes from the old flat look to themed controls when the host OS supports
    them. DPI awareness keeps the runtime's DPI-scaled layout metrics aligned
    with Windows' per-monitor scaling behavior.
    """
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        '<assembly xmlns="urn:schemas-microsoft-com:asm.v1" manifestVersion="1.0">\n'
        '  <assemblyIdentity version="1.0.0.0" processorArchitecture="*" '
        'name="SemanticScript.WindowsGui" type="win32"/>\n'
        '  <dependency>\n'
        '    <dependentAssembly>\n'
        '      <assemblyIdentity type="win32" '
        'name="Microsoft.Windows.Common-Controls" version="6.0.0.0" '
        'processorArchitecture="*" publicKeyToken="6595b64144ccf1df" '
        'language="*"/>\n'
        '    </dependentAssembly>\n'
        '  </dependency>\n'
        '  <application xmlns="urn:schemas-microsoft-com:asm.v3">\n'
        '    <windowsSettings>\n'
        '      <dpiAware xmlns="http://schemas.microsoft.com/SMI/2005/WindowsSettings">'
        'true/PM</dpiAware>\n'
        '      <dpiAwareness xmlns="http://schemas.microsoft.com/SMI/2016/WindowsSettings">'
        'PerMonitorV2, PerMonitor</dpiAwareness>\n'
        '    </windowsSettings>\n'
        '  </application>\n'
        '</assembly>\n'
    )


def _render_versioninfo_rc(prog: Program, exe_path: str,
                            icon_path: str = None,
                            manifest_path: str = None) -> str:
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

    manifest_line = ""
    if manifest_path:
        manifest_path_rc = manifest_path.replace("\\", "\\\\")
        manifest_line = f"1 24 \"{manifest_path_rc}\"\n"

    return (
        "// Auto-generated by SemanticScript compiler; do not edit by hand.\n"
        "#pragma code_page(65001)\n"
        + icon_line +
        manifest_line +
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
    """Generate and compile Windows resources for the program.

    Returns the path to the linkable resource object (.res or .o) plus any
    temp files to clean up, or (None, []) if no resources are needed, we're
    not building for Windows, or no resource compiler is available.
    """
    import subprocess

    icon_selection = _select_windows_icon_payload(prog)
    needs_windows_gui_manifest = _program_uses_gui_runtime(prog)
    if not (prog.project_metadata or prog.custom_metadata or icon_selection or
            needs_windows_gui_manifest):
        return None, []
    if sys.platform != "win32":
        return None, []

    compiler = _find_resource_compiler()
    if compiler is None:
        sys.stderr.write(
            "semsc: warning: Windows resources were declared "
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

    manifest_path_for_rc = None
    if needs_windows_gui_manifest:
        manifest_text = _render_windows_gui_manifest()
        if resource_dir:
            manifest_path = os.path.join(resource_dir, f"{resource_stem}.manifest")
            with open(manifest_path, "w", encoding="utf-8", newline="\n") as manifest_file:
                manifest_file.write(manifest_text)
        else:
            import tempfile
            manifest_handle = tempfile.NamedTemporaryFile(
                suffix=".manifest", delete=False, mode="w", encoding="utf-8", newline="\n")
            manifest_handle.write(manifest_text)
            manifest_handle.close()
            manifest_path = manifest_handle.name
            temp_files.append(manifest_path)
        manifest_path_for_rc = os.path.abspath(manifest_path)

    rc_text = _render_versioninfo_rc(
        prog,
        exe_path,
        icon_path=icon_path_for_rc,
        manifest_path=manifest_path_for_rc,
    )
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
            f"({proc.returncode}); linking without Windows resources\n"
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

    clang_env = os.environ.get("SEMSC_CLANG")
    clang_cmd = []
    if clang_env:
        clang_cmd = [clang_env] if os.path.exists(clang_env) else shlex.split(
            clang_env, posix=os.name != "nt")
    if not clang_cmd:
        # Try common Windows install locations + PATH lookup.
        for candidate in ("clang", "C:/Program Files/LLVM/bin/clang.exe"):
            if os.path.isabs(candidate):
                if os.path.exists(candidate):
                    clang_cmd = [candidate]
                    break
            else:
                from shutil import which
                resolved = which(candidate)
                if resolved:
                    clang_cmd = [resolved]
                    break
        if not clang_cmd:
            from shutil import which
            zig = which("zig")
            if zig:
                clang_cmd = [zig, "cc"]
    if not clang_cmd:
        raise RuntimeError(
            "could not find clang or zig cc; set SEMSC_CLANG=/path/to/clang")

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
        cmd = list(clang_cmd) + [f"-O{opt_level}"]
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
    elif "unsupported non-ABI runtimeBinding" in message:
        direction = (
            "This runtimeBinding target used to hide domain behavior in the "
            "compiler. Move the behavior into a normal SemanticScript "
            "operation body, or bind an explicit native runtime that owns the "
            "policy."
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
            return str(_unwrap(first_row[0]))
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


def _peak_working_set_bytes():
    """Return ``(peak_bytes, source)`` for the current process.

    Windows reads ``PeakWorkingSetSize`` via ``GetProcessMemoryInfo``; POSIX uses
    ``getrusage(RUSAGE_SELF).ru_maxrss`` (KiB on Linux, bytes on macOS/BSD). This
    is the whole-process peak (compiler + JIT + program), a proxy for program
    memory rather than a program-only heap measurement. Returns
    ``(None, "unavailable")`` when the platform query fails.
    """
    if sys.platform == "win32":
        try:
            import ctypes.wintypes as wintypes

            class PROCESS_MEMORY_COUNTERS(ctypes.Structure):
                _fields_ = [
                    ("cb", wintypes.DWORD),
                    ("PageFaultCount", wintypes.DWORD),
                    ("PeakWorkingSetSize", ctypes.c_size_t),
                    ("WorkingSetSize", ctypes.c_size_t),
                    ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                    ("PagefileUsage", ctypes.c_size_t),
                    ("PeakPagefileUsage", ctypes.c_size_t),
                ]

            kernel32 = ctypes.WinDLL("kernel32")
            psapi = ctypes.WinDLL("psapi")
            kernel32.GetCurrentProcess.restype = wintypes.HANDLE
            psapi.GetProcessMemoryInfo.argtypes = [
                wintypes.HANDLE,
                ctypes.POINTER(PROCESS_MEMORY_COUNTERS),
                wintypes.DWORD,
            ]
            psapi.GetProcessMemoryInfo.restype = wintypes.BOOL
            counters = PROCESS_MEMORY_COUNTERS()
            counters.cb = ctypes.sizeof(PROCESS_MEMORY_COUNTERS)
            handle = kernel32.GetCurrentProcess()
            ok = psapi.GetProcessMemoryInfo(
                handle, ctypes.byref(counters), counters.cb)
            if ok:
                return int(counters.PeakWorkingSetSize), "GetProcessMemoryInfo"
        except Exception:
            return None, "unavailable"
        return None, "unavailable"
    try:
        import resource
        max_rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        # Linux reports KiB; macOS/BSD report bytes.
        if sys.platform == "darwin":
            return int(max_rss), "getrusage"
        return int(max_rss) * 1024, "getrusage"
    except Exception:
        return None, "unavailable"


def jit_run(module_ir: str, opt_level: int = 2,
            emit_optimized_ir_to: str = None,
            cpu_config: CpuBuildConfig = None,
            collect_execution_metrics: bool = False):
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
    if collect_execution_metrics:
        execute_start_ns = time.perf_counter_ns()
        rc = cmain()
        execute_ns = time.perf_counter_ns() - execute_start_ns
        return rc, execute_ns
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


def _resolve_imports(source: str, source_path: str, explicit_std_paths=None,
                     return_origins: bool = False):
    if _is_build_tape_path(source_path) and _looks_like_regular_build_plan(source):
        source = _regular_build_plan_compat_source(source, source_path)

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

    # External-dependency import bridge. When the unit being resolved is a
    # build tape carrying `dependency*` rows, merge the offline, materialized
    # dependency cache into the registry so `import ALIAS MODULE_PATH` resolves
    # against fetched packages. Import resolution stays offline: a declared but
    # unsynced dependency is recorded as pending and only errors if the program
    # actually imports it, with an actionable `sem deps sync` message.
    dep_pending: dict = {}
    if _is_build_tape_path(source_path):
        try:
            dep_config = semdeps.parse_build_sem(source, source_path)
            if dep_config.specs:
                dep_registry, dep_pending = semdeps.resolve_import_registry(dep_config)
                for dep_module_path, dep_source_file in dep_registry.items():
                    module_registry.setdefault(dep_module_path, dep_source_file)
        except semdeps.DependencyError as dep_error:
            raise SyntaxError(f"build.sem dependency error: {dep_error}")

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
    out_origins: list = []
    pending: list = [(source, src_dir)]

    def find_module_file(dotted: str, from_dir: str):
        registered_path = module_registry.get(dotted)
        if registered_path is not None:
            resolved = _resolve_registered_module_file(
                dotted, registered_path, registry_main_files)
            if resolved is None:
                raise SyntaxError(
                    f"import: registered module `{dotted}` points at "
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
                f"import: standard-library module `{dotted}` could not "
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
        if dotted in dep_pending:
            raise SyntaxError(dep_pending[dotted])
        # No leaf fallback: a missing module must stay missing, not silently
        # bind to a same-leafname file in a sibling directory (e.g. importing
        # `standard.time` should not pick up `std/time.sscript`).
        return None

    header_skip = (
        "project ", "target ", "runtime ", "entry ", "module ",
        "purpose module ", "invariant module ",
        # Module-contract docs are owned by the module itself; when an
        # import inlines into a parent program, the contract rows would
        # otherwise be attributed to whichever operation was last open
        # in the parent — codegen then errors with "unhandled verb:
        # modulePurpose". Strip at inline time so the inlined source
        # carries only operation bodies + types + capabilities.
        "moduleOwns ", "moduleDoesNotOwn ",
        "moduleWarning ", "moduleSecurity ",
        "moduleObservability ", "moduleDependency ",
    )

    def is_stdlib_origin(path: str) -> bool:
        if not path:
            return False
        origin_abs = os.path.abspath(path)
        for stdlib_dir in stdlib_dirs:
            stdlib_abs = os.path.abspath(stdlib_dir)
            try:
                if os.path.commonpath([origin_abs, stdlib_abs]) == stdlib_abs:
                    return True
            except ValueError:
                continue
        return False

    def append_line(line: str, origin_path: str, origin_line: int,
                    imported: bool) -> None:
        out_lines.append(line)
        out_origins.append({
            "path": os.path.abspath(origin_path) if origin_path else "",
            "line": origin_line,
            "column": 1,
            "raw": line,
            "imported": imported,
        })

    def process(text: str, base_dir: str, is_root: bool, origin_path: str):
        skipping_imported_main = False
        skip_imported_main = (not is_root) and is_stdlib_origin(origin_path)
        for origin_line, line in enumerate(text.splitlines(), start=1):
            stripped = line.strip()
            parts = stripped.split()
            is_operation_row = len(parts) >= 2 and parts[0] == "operation"
            if skipping_imported_main:
                if is_operation_row and parts[1] != "main":
                    skipping_imported_main = False
                else:
                    continue
            if skip_imported_main and is_operation_row and parts[1] == "main":
                # Imported stdlib modules may carry standalone smoke-test
                # `operation main` bodies. They are not part of the imported
                # API and collide with other imported smoke tests, so drop the
                # whole imported main body while preserving exported helpers.
                skipping_imported_main = True
                continue
            if stripped.startswith("import "):
                if len(parts) >= 3:
                    dotted = parts[2]
                    path = find_module_file(dotted, base_dir)
                    if path is not None and path not in seen:
                        seen.add(path)
                        try:
                            with open(path, "r", encoding="utf-8") as f:
                                imported = f.read()
                        except OSError:
                            append_line(line, origin_path, origin_line,
                                        imported=not is_root)
                            continue
                        process(imported, os.path.dirname(path), is_root=False,
                                origin_path=path)
                    if path is None:
                        append_line(line, origin_path, origin_line,
                                    imported=not is_root)
                        continue
                    append_line(line, origin_path, origin_line,
                                imported=not is_root)
                    continue
            if not is_root and stripped.startswith(header_skip):
                continue
            append_line(line, origin_path, origin_line, imported=not is_root)

    seen.add(os.path.abspath(source_path))
    process(source, src_dir, is_root=True, origin_path=source_path)
    resolved = "\n".join(out_lines) + "\n"
    if not return_origins:
        return resolved
    origins_by_line = {
        line_number: origin
        for line_number, origin in enumerate(out_origins, start=1)
    }
    return resolved, origins_by_line


def _load_external_literals(prog: Program, source_path: str) -> None:
    """For every `literal NAME TYPE` whose `literalSource NAME "path"`
    resolves on disk, read the file's bytes and store them as the const's
    value. Paths are tried absolute first, then relative to the row's original
    source file directory, then relative to the root source file directory.
    Files that fail to load leave the stub in place so the program still
    compiles."""
    src_dir = os.path.dirname(os.path.abspath(source_path)) if source_path else ""
    source_dirs_by_literal = {}
    for line_number, raw_line in prog.source_lines.items():
        tokens = tokenize_line(raw_line)
        if len(tokens) < 3 or tokens[0] != "literalSource":
            continue
        literal_name = tokens[1]
        origin = prog.source_origins.get(line_number, {})
        origin_path = origin.get("path") if isinstance(origin, dict) else None
        if not origin_path:
            continue
        origin_dir = os.path.dirname(os.path.abspath(origin_path))
        if origin_dir:
            source_dirs_by_literal.setdefault(literal_name, [])
            if origin_dir not in source_dirs_by_literal[literal_name]:
                source_dirs_by_literal[literal_name].append(origin_dir)
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
                for row_dir in source_dirs_by_literal.get(name, []):
                    candidates.append(os.path.join(row_dir, raw_path))
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


def _build_metadata_span(prog: Program, key: str, value: str = None) -> DiagnosticSpan:
    for lineno in sorted(prog.source_lines):
        raw = prog.source_lines.get(lineno, "")
        tokens = tokenize_line(raw)
        if not tokens or tokens[0] != key:
            continue
        args = tokens[1:]
        if value is not None:
            if len(args) < 2 or str(_unwrap(args[1])) != value:
                continue
        return DiagnosticSpan(
            path=prog.source_path or "<source>",
            line=lineno or 0,
            column=1,
            raw=raw,
            role="buildMetadata",
        )
    return DiagnosticSpan(
        path=prog.source_path or "<source>",
        line=0,
        column=1,
        raw="",
        role="buildMetadata",
    )


def _gui_backend_for_program(prog: Program) -> str:
    backend = _build_metadata_value(prog, "guiBackend") or "win32"
    if backend not in _BUILD_TAPE_CHOICES["guiBackend"]:
        raise CompilerDiagnosticError(CompilerDiagnostic(
            code="SSCG003",
            phase="native-runtime-selection",
            message=(
                f"guiBackend value `{backend}` is invalid; expected one of "
                f"{sorted(_BUILD_TAPE_CHOICES['guiBackend'])}"),
            primary=_build_metadata_span(prog, "guiBackend", backend),
            direction=(
                "Use `guiBackend PROJECT win32` or omit the row. `winui3` is "
                "reserved for the Windows App SDK backend scaffold."),
            suggested_fixes=[
                "Replace the guiBackend value with `win32`.",
                "Remove the guiBackend row to use the compatibility default `win32`.",
            ],
            agent_hint="Do not invent another GUI source API; backend selection is a build setting.",
        ))
    return backend


def _native_gui_link_inputs(prog: Program):
    if not _program_uses_gui_runtime(prog):
        return [], []

    backend = _gui_backend_for_program(prog)
    if backend == "winui3":
        raise CompilerDiagnosticError(CompilerDiagnostic(
            code="SSCG003",
            phase="native-runtime-selection",
            message=(
                "guiBackend winui3 is recognized but not buildable yet; "
                "Windows App SDK / C++/WinRT package integration has not landed"),
            primary=_build_metadata_span(prog, "guiBackend", "winui3"),
            direction=(
                "The current executable GUI backend is `win32`. The WinUI 3 "
                "directory is only a scaffold until the compiler has a Windows "
                "App SDK build path and deployment model."),
            suggested_fixes=[
                "Use `guiBackend PROJECT win32` for now, or omit the row.",
                "See SemanticScript/runtime/native_winui3_gui/README.md for the missing Windows App SDK integration work.",
            ],
            agent_hint=(
                "Keep the public source API as standard.gui gui.* calls. Add the "
                "WinUI 3 adapter behind the existing ss_gui_* C ABI before "
                "allowing this backend."),
        ))

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
        link_args.extend([
            "-luser32",
            "-lgdi32",
            "-lcomctl32",
            "-Xlinker",
            "/SUBSYSTEM:WINDOWS",
        ])
    return [runtime_source], link_args


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
# trigger and intentionally excludes legacy primitive json.encode.X /
# json.decode.X stubs. High-level json.stringify/parse primitive aliases
# link native_json for runtime-owned formatting, escaping, and strict parse
# status. The document CRUD names are listed even while the C adapter
# implementation is landing so any executable use links the native_json
# translation unit rather than silently compiling a dangling extern.
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
    "json.createDocument", "json.createEmptyDocument",
    "json.destroyDocument", "json.serializeDocument",
    "json.documentLength", "json.documentRoot",
    "json.objectFieldAt", "json.arrayElementAt",
    "json.cursorParent", "json.cursorAtPath",
    "json.cursorKind", "json.cursorIsNull",
    "json.cursorInt64", "json.cursorDouble", "json.cursorBool",
    "json.cursorString", "json.cursorArrayLength",
    "json.cursorObjectFieldCount", "json.cursorObjectFieldNameAt",
    "json.cursorObjectFieldValueAt",
    "json.setObjectFieldString", "json.setObjectFieldInt64",
    "json.setObjectFieldDouble", "json.setObjectFieldBool",
    "json.setObjectFieldNull", "json.setObjectFieldObject",
    "json.setObjectFieldArray", "json.setObjectFieldJsonText",
    "json.appendArrayElementString", "json.appendArrayElementInt64",
    "json.appendArrayElementDouble", "json.appendArrayElementBool",
    "json.appendArrayElementNull", "json.appendArrayElementObject",
    "json.appendArrayElementArray", "json.appendArrayElementJsonText",
    "json.insertArrayElementString", "json.insertArrayElementInt64",
    "json.insertArrayElementDouble", "json.insertArrayElementBool",
    "json.insertArrayElementNull", "json.insertArrayElementObject",
    "json.insertArrayElementArray", "json.insertArrayElementJsonText",
    "json.replaceArrayElementString", "json.replaceArrayElementInt64",
    "json.replaceArrayElementDouble", "json.replaceArrayElementBool",
    "json.replaceArrayElementNull", "json.replaceArrayElementObject",
    "json.replaceArrayElementArray", "json.replaceArrayElementJsonText",
    "json.removeObjectField", "json.removeArrayElementAt",
    "json.clearObject", "json.clearArray",
})


def _program_uses_json_runtime(prog: Program) -> bool:
    """True when any operation contains a call into the native_json
    runtime (the builder, finder, and document CRUD API). Triggers
    separately from primitive json.encode.* / json.decode.* dispatchers
    and json.stringify/parse primitive aliases, which don't need the
    runtime linked in. Defer-only references count too — `defer X
    json.destroyDocument documentName` is enough to pull the runtime in."""
    def target_is_json_text(type_name: str) -> bool:
        current = type_name
        seen = set()
        while True:
            if current == "JsonText":
                return True
            if current in seen or current not in prog.type_aliases:
                return False
            seen.add(current)
            alias_target = prog.type_aliases[current]
            current = alias_target[0] if isinstance(alias_target, list) else alias_target

    for op in prog.operations.values():
        for verb, args, _lineno in op.lines:
            if verb == "call" and len(args) >= 2 and args[1] in _NATIVE_JSON_TARGETS:
                return True
            if verb == "call" and len(args) >= 2:
                target = args[1]
                if target.startswith("json.stringify.") or target.startswith("json.parse."):
                    type_name = target.split(".", 2)[2]
                    resolved_type = resolve_alias(prog, type_name)
                    if target.startswith("json.parse.") and (
                        type_name in _JSON_PARSE_PRIMITIVE_TARGETS
                        or resolved_type in _JSON_PARSE_PRIMITIVE_TARGETS
                    ):
                        return True
                    if target.startswith("json.stringify.") and (
                        type_name in _JSON_STRINGIFY_PRIMITIVE_TARGETS
                        or resolved_type in _JSON_STRINGIFY_PRIMITIVE_TARGETS
                    ):
                        return True
                    if target.startswith("json.parse.") and target_is_json_text(type_name):
                        return True
                    if type_name in prog.records or resolved_type in prog.records:
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
    "hashPassword",
    "verifyPassword",
    "randomBytes",
    "base64UrlEncode",
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


def _native_declared_link_inputs(prog: Program):
    """Return native sources/link args declared by imported std modules.

    Standard-library modules own concrete native adapter placement via
    top-level metadata rows:

      nativeRuntimeSource MODULE "relative/or/absolute/path.c"
      nativeRuntimeLinkArg MODULE any "-lm"
      nativeRuntimeLinkArg MODULE windows "-lbcrypt"

    The compiler only resolves those declarations; it does not know the
    component-specific call names.
    """
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    current_platform = "windows" if os.name == "nt" else "posix"
    extra_sources = []
    extra_link_args = []
    for metadata in prog.hard_metadata.values():
        for row in metadata.get("nativeRuntimeSource", []):
            if not row:
                continue
            source_path = row[0]
            if not os.path.isabs(source_path):
                source_path = os.path.join(repo_root, source_path)
            extra_sources.append(os.path.normpath(source_path))
        for row in metadata.get("nativeRuntimeLinkArg", []):
            if not row:
                continue
            if len(row) == 1:
                extra_link_args.append(row[0])
                continue
            platform, link_arg = row[0], row[1]
            if platform in ("any", current_platform):
                extra_link_args.append(link_arg)
    return extra_sources, extra_link_args


def _program_uses_async_runtime(prog: Program) -> bool:
    """True when source-level start/await targets a user operation.

    HTTP fetch intrinsics also use native_async, but they link it through the
    native_http_client collector. This trigger exists for programmable async
    user operations that do not otherwise touch standard.net.
    """
    for op in prog.operations.values():
        call_targets = {}
        op_async_enabled = False
        for verb, args, _lineno in op.lines:
            if (verb == "async" and len(args) >= 2 and args[0] == op.name
                    and str(args[1]).lower() in {"yes", "true", "1", "on"}):
                op_async_enabled = True
            elif verb == "call" and len(args) >= 2:
                target = _TARGET_ALIASES.get(args[1], args[1])
                target = prog.operation_aliases.get(target, target)
                call_targets[args[0]] = target
        if not op_async_enabled:
            continue
        for verb, args, _lineno in op.lines:
            if verb not in ("start", "await", "case") or not args:
                continue
            target = call_targets.get(args[0])
            if target in prog.operations:
                return True
    return False


def _native_async_link_inputs(prog: Program):
    if not _program_uses_async_runtime(prog):
        return [], []
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    async_dir = os.path.join(repo_root, "SemanticScript", "runtime", "native_async")
    extra_link_args = []
    if os.name != "nt":
        extra_link_args.append("-pthread")
    return [os.path.join(async_dir, "sem_async_runtime.c")], extra_link_args


_NATIVE_HTTP_CLIENT_TARGETS = frozenset({
    "net.fetchText",
    "net.fetchBytes",
    "net.freeTextBody",
    "fetchText",
    "fetchBytes",
    "freeTextBody",
})


def _program_uses_http_client_runtime(prog: Program) -> bool:
    for op in prog.operations.values():
        for verb, args, _lineno in op.lines:
            if verb == "call" and len(args) >= 2 and args[1] in _NATIVE_HTTP_CLIENT_TARGETS:
                return True
    return False


def _native_http_client_link_inputs(prog: Program):
    if not _program_uses_http_client_runtime(prog):
        return [], []
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    async_dir = os.path.join(repo_root, "SemanticScript", "runtime", "native_async")
    client_dir = os.path.join(repo_root, "SemanticScript", "runtime", "native_http_client")
    extra_link_args = []
    if os.name != "nt":
        extra_link_args.append("-pthread")
    return [
        os.path.join(async_dir, "sem_async_runtime.c"),
        os.path.join(client_dir, "sem_http_client_runtime.c"),
    ], extra_link_args


_NATIVE_RUNTIME_LINK_REGISTRY = (
    {
        "component": "native_http",
        "owner": "compiler/runtime",
        "collector": _native_http_link_inputs,
    },
    {
        "component": "native_sqlite",
        "owner": "standard.sqlite/runtime",
        "collector": _native_sqlite_link_inputs,
    },
    {
        "component": "native_json",
        "owner": "standard.json/runtime",
        "collector": _native_json_link_inputs,
    },
    {
        "component": "native_terminal",
        "owner": "compiler/runtime",
        "collector": _native_terminal_link_inputs,
    },
    {
        "component": "native_bcrypt",
        "owner": "standard.bcrypt/runtime",
        "collector": _native_bcrypt_link_inputs,
    },
    {
        "component": "declared_native",
        "owner": "standard-library/runtimeBinding",
        "collector": _native_declared_link_inputs,
    },
    {
        "component": "native_gui",
        "owner": "standard.gui/runtime",
        "collector": _native_gui_link_inputs,
    },
    {
        "component": "native_async",
        "owner": "compiler/runtime",
        "collector": _native_async_link_inputs,
    },
    {
        "component": "native_http_client",
        "owner": "standard.net/runtime",
        "collector": _native_http_client_link_inputs,
    },
)


def _native_runtime_link_inputs(prog: Program):
    """Return aggregate native runtime link inputs plus per-runtime details.

    Keeping this as one collector matters for agent tooling: `sem inspect-ir`
    and `--emit-exe` must describe and use the same native runtime surface.
    Add new stdlib/runtime owned adapters to `_NATIVE_RUNTIME_LINK_REGISTRY`
    rather than branching here.
    """
    components = []
    aggregate_sources = []
    aggregate_args = []
    for entry in _NATIVE_RUNTIME_LINK_REGISTRY:
        collector = entry.get("collector")
        if collector is None:
            continue
        sources, link_args = collector(prog)
        sources = list(sources or [])
        link_args = list(link_args or [])
        if not sources and not link_args:
            continue
        for source_path in sources:
            if source_path not in aggregate_sources:
                aggregate_sources.append(source_path)
        for link_arg in link_args:
            if link_arg not in aggregate_args:
                aggregate_args.append(link_arg)
        components.append({
            "component": entry["component"],
            "owner": entry.get("owner", ""),
            "sources": sources,
            "linkArgs": link_args,
        })
    return aggregate_sources, aggregate_args, components


def _sha256_text(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def _program_source_fingerprint(prog: Program) -> str:
    parts = []
    for lineno in sorted(prog.source_lines):
        parts.append(f"{lineno}\0{prog.source_lines[lineno]}")
    return _sha256_text("\n".join(parts))


def _source_origin_summary(prog: Program) -> list:
    origins = {}
    root_path = os.path.abspath(prog.source_path) if prog.source_path else ""
    for origin in prog.source_origins.values():
        path = os.path.abspath(origin.get("path", "")) if origin.get("path") else ""
        if not path or path == root_path:
            continue
        item = origins.setdefault(path, {
            "path": path,
            "imported": bool(origin.get("imported", False)),
            "lineCount": 0,
            "firstLine": int(origin.get("line") or 0),
            "lastLine": int(origin.get("line") or 0),
        })
        line = int(origin.get("line") or 0)
        item["lineCount"] += 1
        if line:
            item["firstLine"] = min(item["firstLine"] or line, line)
            item["lastLine"] = max(item["lastLine"] or line, line)
    return [origins[path] for path in sorted(origins)]


def _json_source_span(prog: Program, lineno: int, role: str = "source") -> dict:
    span = {
        "path": os.path.abspath(prog.source_path) if prog.source_path else "",
        "line": int(lineno or 0),
        "column": 1,
        "raw": prog.source_lines.get(lineno, ""),
        "role": role,
    }
    origin = prog.source_origins.get(lineno)
    if origin:
        span["origin"] = {
            "path": os.path.abspath(origin.get("path", "")) if origin.get("path") else "",
            "line": int(origin.get("line") or 0),
            "column": int(origin.get("column") or 1),
            "imported": bool(origin.get("imported", False)),
            "raw": origin.get("raw", ""),
        }
    return span


def _trace_site_id(prog: Program, kind: str, operation: str = "",
                   name: str = "", target: str = "", lineno: int = 0) -> str:
    raw = prog.source_lines.get(lineno, "")
    origin = prog.source_origins.get(lineno, {})
    basis = "\0".join([
        os.path.abspath(prog.source_path) if prog.source_path else "",
        str(lineno or 0),
        os.path.abspath(origin.get("path", "")) if origin.get("path") else "",
        str(origin.get("line", "") or ""),
        kind or "",
        operation or "",
        name or "",
        target or "",
        raw or "",
    ])
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()[:16]


def _trace_site(prog: Program, kind: str, operation: str = "",
                name: str = "", target: str = "", lineno: int = 0,
                extra: dict = None) -> dict:
    site = {
        "siteId": _trace_site_id(prog, kind, operation, name, target, lineno),
        "kind": kind,
        "operation": operation or "",
        "name": name or "",
        "target": target or "",
        "sourceSpan": _json_source_span(prog, lineno),
    }
    if extra:
        site.update(extra)
    return site


def _operation_llvm_function_name(prog: Program, op_name: str) -> str:
    if prog.entry and len(prog.entry) >= 2 and prog.entry[1] == op_name:
        return "main"
    return op_name


def _operation_summary_for_agents(prog: Program, op: Operation) -> dict:
    inputs = []
    labels = []
    calls = []
    branches = []
    returns = []
    effects = []
    call_args = {}
    for verb, args, lineno in op.lines:
        if verb == "input" and len(args) >= 3 and args[0] == op.name:
            inputs.append({
                "name": args[1],
                "type": args[2],
                "sourceSpan": _json_source_span(prog, lineno),
            })
        elif verb == "effect" and len(args) >= 3 and args[0] == op.name:
            effects.append({
                "action": args[1],
                "path": args[2],
                "sourceSpan": _json_source_span(prog, lineno),
            })
        elif verb == "label" and args:
            labels.append({
                "name": args[0],
                "siteId": _trace_site_id(prog, "label", op.name, args[0], "", lineno),
                "sourceSpan": _json_source_span(prog, lineno),
            })
        elif verb == "argument" and len(args) >= 4:
            call_args.setdefault(args[0], []).append({
                "name": args[1],
                "type": args[2],
                "value": args[3],
                "sourceSpan": _json_source_span(prog, lineno),
            })
        elif verb == "call" and len(args) >= 2:
            calls.append({
                "name": args[0],
                "target": args[1],
                "siteId": _trace_site_id(prog, "call", op.name, args[0], args[1], lineno),
                "args": [],
                "sourceSpan": _json_source_span(prog, lineno),
            })
        elif verb == "branch":
            name = args[2] if len(args) >= 3 and args[0] in ("if", "error") else args[0]
            target = args[-1] if args else ""
            branches.append({
                "verb": f"branch {args[0]}" if args else verb,
                "name": name,
                "target": target,
                "siteId": _trace_site_id(prog, "branch", op.name, name, target, lineno),
                "sourceSpan": _json_source_span(prog, lineno),
            })
        elif verb == "jump":
            target = args[1] if len(args) >= 2 else ""
            branches.append({
                "verb": "jump",
                "name": "jump",
                "target": target,
                "siteId": _trace_site_id(prog, "branch", op.name, "jump", target, lineno),
                "sourceSpan": _json_source_span(prog, lineno),
            })
        elif verb == "return":
            value = args[1] if len(args) > 1 else ""
            returns.append({
                "verb": f"return {args[0]}" if args else verb,
                "value": value,
                "siteId": _trace_site_id(prog, "return", op.name, f"return {args[0]}" if args else verb, value, lineno),
                "sourceSpan": _json_source_span(prog, lineno),
            })
    for call in calls:
        call["args"] = call_args.get(call["name"], [])

    output = {}
    contract = _operation_output_contract(prog, op)
    output["tokens"] = list(contract.tokens)
    output["okType"] = contract.ok_type
    output["llvmType"] = str(contract.llvm_type) if contract.llvm_type is not None else ""
    output["sourceSpan"] = _json_source_span(prog, contract.line)
    if contract.problem:
        output["problem"] = contract.problem
        output["message"] = contract.message

    return {
        "name": op.name,
        "siteId": _trace_site_id(prog, "operation", op.name, op.name, "", op.decl_line),
        "llvmFunction": _operation_llvm_function_name(prog, op.name),
        "sourceSpan": _json_source_span(prog, op.decl_line, role="operation"),
        "output": output,
        "inputs": inputs,
        "effects": effects,
        "labels": labels,
        "calls": calls,
        "branches": branches,
        "returns": returns,
    }


def _route_summaries_for_agents(prog: Program) -> list:
    routes = []
    for lineno, args in _source_rows(prog, "route"):
        if len(args) < 4:
            continue
        server_name = args[0]
        method = args[1]
        path = _unwrap(args[2])
        handler = args[3]
        routes.append({
            "server": server_name,
            "method": method,
            "path": path,
            "handler": handler,
            "siteId": _trace_site_id(
                prog, "route", handler, f"{method} {path}", server_name, lineno),
            "sourceSpan": _json_source_span(prog, lineno, role="route"),
            "nativeAbi": {
                "kind": "httpHandler",
                "semanticSignature": "Int32(HttpRequest, HttpResponse)",
                "llvmSignature": "i32 (i8*, i8*)",
            },
        })
    return routes


def _function_summaries_for_agents(prog: Program, mod, routes: list) -> list:
    function_to_operation = {}
    for op_name in prog.operations:
        function_to_operation[_operation_llvm_function_name(prog, op_name)] = op_name
    routes_by_handler = {}
    for route in routes:
        routes_by_handler.setdefault(route["handler"], []).append({
            "server": route["server"],
            "method": route["method"],
            "path": route["path"],
            "siteId": route["siteId"],
        })

    functions = []
    for fn in mod.functions:
        blocks = []
        try:
            blocks = [{"name": block.name} for block in fn.blocks]
        except Exception:
            blocks = []
        op_name = function_to_operation.get(fn.name, "")
        abi = None
        if op_name in routes_by_handler:
            abi = {
                "kind": "httpHandler",
                "semanticSignature": "Int32(HttpRequest, HttpResponse)",
                "llvmSignature": "i32 (i8*, i8*)",
                "routes": routes_by_handler[op_name],
            }
        functions.append({
            "name": fn.name,
            "signature": str(fn.function_type),
            "isDeclaration": len(blocks) == 0,
            "operation": op_name,
            "sourceSpan": _json_source_span(
                prog,
                prog.operations[op_name].decl_line if op_name in prog.operations else 0,
                role="operation" if op_name else "llvm"),
            "blocks": blocks,
            "nativeAbi": abi,
        })
    return functions


def _runtime_symbol_summaries_for_agents(prog: Program,
                                         provenance: CompilerProvenance) -> list:
    symbols = []
    for symbol in sorted(provenance.externals):
        frames = []
        for frame in provenance.externals[symbol]:
            span = frame.span
            frames.append({
                "operation": frame.operation,
                "callName": frame.call_name,
                "callTarget": frame.call_target,
                "siteId": _trace_site_id(
                    prog, "runtime.external", frame.operation,
                    frame.call_name, symbol, span.line),
                "sourceSpan": _json_source_span(prog, span.line, role=span.role),
            })
        symbols.append({
            "symbol": symbol,
            "frames": frames,
        })
    return symbols


def _trace_map_for_agents(prog: Program, cg: Codegen, mod,
                          runtime_link_components: list) -> dict:
    routes = _route_summaries_for_agents(prog)
    sites = []
    for op in sorted(prog.operations.values(), key=lambda item: (item.decl_line, item.name)):
        sites.append(_trace_site(
            prog, "operation", op.name, op.name, "", op.decl_line))
        for verb, args, lineno in op.lines:
            if verb == "label" and args:
                sites.append(_trace_site(prog, "label", op.name, args[0], "", lineno))
            elif verb == "call" and len(args) >= 2:
                sites.append(_trace_site(prog, "call", op.name, args[0], args[1], lineno))
            elif verb == "branch":
                name = args[2] if len(args) >= 3 and args[0] in ("if", "error") else args[0]
                target = args[-1] if args else ""
                sites.append(_trace_site(prog, "branch", op.name, name, target, lineno,
                                         {"verb": f"branch {args[0]}" if args else verb}))
            elif verb == "jump":
                target = args[1] if len(args) >= 2 else ""
                sites.append(_trace_site(prog, "branch", op.name, "jump", target, lineno,
                                         {"verb": "jump"}))
            elif verb == "return":
                value = args[1] if len(args) > 1 else ""
                return_verb = f"return {args[0]}" if args else verb
                sites.append(_trace_site(prog, "return", op.name, return_verb, value, lineno,
                                         {"verb": return_verb}))
    for route in routes:
        sites.append({
            "siteId": route["siteId"],
            "kind": "route",
            "operation": route["handler"],
            "name": f"{route['method']} {route['path']}",
            "target": route["server"],
            "sourceSpan": route["sourceSpan"],
            "nativeAbi": route["nativeAbi"],
        })
    for symbol in _runtime_symbol_summaries_for_agents(prog, cg.provenance):
        for frame in symbol["frames"]:
            sites.append({
                "siteId": frame["siteId"],
                "kind": "runtime.external",
                "operation": frame["operation"],
                "name": frame["callName"],
                "target": symbol["symbol"],
                "sourceSpan": frame["sourceSpan"],
            })
    for component in runtime_link_components:
        for source in component["sources"]:
            sites.append({
                "siteId": _trace_site_id(
                    prog, "runtime.linkInput", "", component["component"], source, 0),
                "kind": "runtime.linkInput",
                "operation": "",
                "name": component["component"],
                "target": source,
                "sourceSpan": _json_source_span(prog, 0, role="runtimeLink"),
            })

    return {
        "schemaVersion": "sem.traceMap.v0",
        "source": {
            "path": os.path.abspath(prog.source_path) if prog.source_path else "",
            "fingerprint": _program_source_fingerprint(prog),
            "sourceModel": "flattenedResolvedStreamWithOrigins",
            "lineCount": len(prog.source_lines),
            "importedSources": _source_origin_summary(prog),
        },
        "redaction": {
            "sourceRows": "included",
            "runtimeValues": "redactedByDefault",
            "sensitiveMetadata": "notYetModeled",
        },
        "llvm": {
            "triple": str(getattr(mod, "triple", "") or ""),
        },
        "sites": sites,
    }


def _build_fingerprint_for_agents(prog: Program, ir_text: str,
                                  build_profile: str, runtime_checks: str,
                                  opt_level: int, cpu_config: CpuBuildConfig,
                                  runtime_link_components: list) -> str:
    payload = {
        "sourceFingerprint": _program_source_fingerprint(prog),
        "irSha256": _sha256_text(ir_text),
        "buildProfile": build_profile,
        "runtimeChecks": runtime_checks,
        "optLevel": opt_level,
        "cpu": cpu_config.summary() if cpu_config is not None else "",
        "runtimeLink": runtime_link_components,
    }
    return _sha256_text(json.dumps(payload, sort_keys=True))


def _inspect_ir_payload_for_agents(prog: Program, cg: Codegen, mod, ir_text: str,
                                   build_profile: str, runtime_checks: str,
                                   opt_level: int, cpu_config: CpuBuildConfig,
                                   persisted_ir_path: str,
                                   emit_optimized_ir_path: str,
                                   runtime_link_components: list) -> dict:
    routes = _route_summaries_for_agents(prog)
    trace_map = _trace_map_for_agents(prog, cg, mod, runtime_link_components)
    llvm_version = getattr(llvm, "llvm_version_info", ())
    return {
        "schemaVersion": "sem.inspectIr.v0",
        "tool": {
            "name": "semsc",
            "version": __version__,
            "llvmVersion": list(llvm_version) if llvm_version else [],
        },
        "source": {
            "path": os.path.abspath(prog.source_path) if prog.source_path else "",
            "fingerprint": _program_source_fingerprint(prog),
            "sourceModel": "flattenedResolvedStreamWithOrigins",
            "lineCount": len(prog.source_lines),
            "importedSources": _source_origin_summary(prog),
        },
        "redaction": {
            "sourceRows": "included",
            "runtimeValues": "redactedByDefault",
            "sensitiveMetadata": "notYetModeled",
        },
        "build": {
            "fingerprint": _build_fingerprint_for_agents(
                prog, ir_text, build_profile, runtime_checks,
                opt_level, cpu_config, runtime_link_components),
            "profile": build_profile,
            "runtimeChecks": runtime_checks,
            "optLevel": opt_level,
            "cpu": {
                "summary": cpu_config.summary() if cpu_config is not None else "",
                "baseline": cpu_config.baseline if cpu_config is not None else "",
                "tune": cpu_config.tune if cpu_config is not None else "",
                "featureCheck": cpu_config.feature_check if cpu_config is not None else "",
                "llvmCpu": cpu_config.llvm_cpu if cpu_config is not None else "",
                "llvmFeatures": cpu_config.llvm_features if cpu_config is not None else "",
                "clangArgs": list(cpu_config.clang_args) if cpu_config is not None else [],
            },
        },
        "artifacts": {
            "llvmIrPath": persisted_ir_path or "",
            "optimizedLlvmIrPath": emit_optimized_ir_path or "",
        },
        "entry": {
            "mode": prog.entry[0] if prog.entry else "",
            "operation": prog.entry[1] if prog.entry and len(prog.entry) >= 2 else "",
        },
        "operations": [
            _operation_summary_for_agents(prog, op)
            for op in sorted(prog.operations.values(), key=lambda item: (item.decl_line, item.name))
        ],
        "routes": routes,
        "llvm": {
            "triple": str(getattr(mod, "triple", "") or ""),
            "irSha256": _sha256_text(ir_text),
            "irLineCount": len(ir_text.splitlines()),
            "functions": _function_summaries_for_agents(prog, mod, routes),
            "runtimeSymbols": _runtime_symbol_summaries_for_agents(prog, cg.provenance),
        },
        "runtimeLink": {
            "components": runtime_link_components,
            "sources": [
                source
                for component in runtime_link_components
                for source in component["sources"]
            ],
            "linkArgs": [
                arg
                for component in runtime_link_components
                for arg in component["linkArgs"]
            ],
        },
        "traceMap": trace_map,
    }


def _resolve_agent_json_output_path(source_path: str, build_dir: str,
                                    request: str, suffix: str) -> str:
    if request is None or request == "-":
        return None
    if request == "":
        stem = os.path.splitext(os.path.basename(source_path))[0] or "program"
        return os.path.abspath(os.path.join(build_dir, stem + suffix))
    return _resolve_build_output_path(source_path, build_dir, request)


def _write_agent_json_payload(payload: dict, output_path: str) -> None:
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    if output_path is None:
        sys.stdout.write(text)
        return
    output_dir = os.path.dirname(os.path.abspath(output_path))
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as output_file:
        output_file.write(text)


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
    ap.add_argument("--run-metrics", action="store_true",
                    help=("with --run, time only program execution and capture "
                          "peak working set, emitting a single "
                          "`__SEM_RUN_METRICS__ {json}` line to stderr before "
                          "exit. Program stdout is left untouched"))
    ap.add_argument("--trace", action="store_true",
                    help=("instrument generated LLVM IR to emit agent JSONL "
                          "trace events to stderr at runtime"))
    ap.add_argument("--lint", action="store_true",
                    help="run agent-safety lint pass and report diagnostics")
    ap.add_argument("--strict", action="store_true",
                    help=("enable strictExecutable semantic validation and "
                          "treat lint diagnostics as fatal"))
    ap.add_argument("--language-mode", action="append", default=[],
                    metavar="MODE",
                    help=("inject a `languageMode MODE` row before semantic "
                          "validation. Used by the `sem` driver to forward "
                          "build.sem language-mode rows. May be passed "
                          "multiple times."))
    ap.add_argument("--parse-only", action="store_true",
                    help="parse the source, run lint (if requested), and exit without codegen")
    ap.add_argument("--opt-level", type=int, default=None,
                    help=("LLVM optimization level for JIT/AOT (0..3); "
                          "default 2 or optLevel from build.sem"))
    ap.add_argument("--emit-optimized-ir",
                    help="write the post-optimization LLVM IR to this path (after --opt-level passes run)")
    ap.add_argument("--inspect-ir", nargs="?", const="-",
                    help=("emit machine-readable JSON describing generated LLVM "
                          "IR, source provenance, trace-map ids, native ABI "
                          "signatures, and linked runtime inputs. With no "
                          "path, writes JSON to stdout; use '-' explicitly "
                          "for stdout."))
    ap.add_argument("--emit-trace-map", nargs="?", const="",
                    help=("write the agent trace-map sidecar JSON. With no "
                          "path, writes SOURCE.trace-map.json in the "
                          "compiler-managed build directory."))
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
    except UnicodeDecodeError as e:
        # Source files must be UTF-8. A non-UTF-8 file is operator error, not a
        # compiler bug: report it cleanly instead of letting the decode raise an
        # unhandled traceback out of main().
        print(f"semsc: source file is not valid UTF-8: {e}", file=sys.stderr)
        sys.exit(2)

    source_ext = os.path.splitext(args.source)[1].lower()
    if source_ext not in (".sscript", ".sem"):
        print("semsc: source file must use .sscript or .sem", file=sys.stderr)
        sys.exit(2)

    try:
        is_build_tape_source = _is_build_tape_path(args.source) or _looks_like_build_tape(source)
    except SyntaxError:
        # Build-tape sniffing tokenizes the source; if it doesn't even lex
        # (e.g. an unterminated string), it isn't a build tape. Defer to the
        # guarded parse() path below, which reports the lex error cleanly
        # instead of letting it escape main() as a traceback.
        is_build_tape_source = False
    if is_build_tape_source:
        try:
            _validate_build_tape_source(source, args.source)
        except SyntaxError as e:
            print(f"semsc: build-tape error in {args.source}: {e}", file=sys.stderr)
            sys.exit(2)

    prelude_language_modes = []
    if is_build_tape_source and not _declares_language_mode(source):
        prelude_language_modes.append("permissiveExecutable")
    for forwarded_mode in args.language_mode or []:
        if forwarded_mode not in _KNOWN_LANGUAGE_MODES:
            print(f"semsc: --language-mode `{forwarded_mode}` is not a "
                  f"known language mode (expected one of "
                  f"{sorted(_KNOWN_LANGUAGE_MODES)})", file=sys.stderr)
            sys.exit(2)
        if forwarded_mode not in prelude_language_modes:
            prelude_language_modes.append(forwarded_mode)
    if prelude_language_modes:
        source = "".join(
            f"languageMode {mode}\n" for mode in prelude_language_modes
        ) + source

    try:
        # Resolve cross-file imports. `importModule DOTTED.PATH [as ALIAS]`
        # lines reference module files. Build tapes resolve registered
        # modules before legacy filesystem/std-lib fallback. Imported file
        # content is inlined; transitive imports are followed with cycle
        # detection.
        source, source_origins = _resolve_imports(
            source, args.source, args.std_path, return_origins=True)
        prog = parse(source)
        prog.source_path = args.source
        prog.source_origins = source_origins
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

    # `--language-mode` carries project-level language modes from build.sem
    # into the per-file semantic validator. The `sem` driver is responsible
    # for reading `languageMode PROJECT MODE` rows out of build.sem and
    # passing one --language-mode per row here; direct semsc invocations opt
    # into the strict executable wall with either an in-source languageMode row
    # or `--strict`.
    forwarded_modes = list(args.language_mode or [])
    if args.strict:
        forwarded_modes.append("strictExecutable")
    for forwarded_mode in forwarded_modes:
        if forwarded_mode not in _KNOWN_LANGUAGE_MODES:
            print(f"semsc: --language-mode `{forwarded_mode}` is not a "
                  f"known language mode (expected one of "
                  f"{sorted(_KNOWN_LANGUAGE_MODES)})", file=sys.stderr)
            sys.exit(2)
        if forwarded_mode in prog.language_modes:
            continue
        conflict = next(
            (existing for existing in prog.language_modes
             if frozenset((existing, forwarded_mode))
             in _INCOMPATIBLE_LANGUAGE_MODES),
            None,
        )
        if conflict is not None:
            print(f"semsc: --language-mode `{forwarded_mode}` conflicts with "
                  f"in-source `languageMode {conflict}`", file=sys.stderr)
            sys.exit(2)
        prog.language_modes.append(forwarded_mode)

    try:
        # The always-on security floor runs first and binds EVERY build,
        # regardless of language mode; strict adds the broader executable wall.
        validate_security_floor(prog)
        validate_strict_executable(prog)
    except CompilerDiagnosticError as e:
        print(e.diagnostic.render(args.diagnostics_format), file=sys.stderr)
        if os.environ.get("SEMSC_TRACEBACK"):
            import traceback as _tb
            _tb.print_exc(file=sys.stderr)
        sys.exit(3)

    # Surface the SS46xx security rules on the DEFAULT (non-strict) build path so
    # they reach agents who never opt into `--strict`. Non-blocking warnings;
    # under strict these are already fatal above.
    #
    # Gated on `not --quiet` by design: the PRIMARY agent path — an interactive
    # `sem build` / `sem run`, which do NOT pass --quiet — surfaces them, meeting
    # the goal. `--quiet` builds (the std `*.test.sem` lane and CI smoke tests
    # that legitimately hard-code TEST secrets / use throwaway values) stay quiet
    # to avoid test-fixture noise; production CI that wants fatal enforcement
    # should use `--strict`. (Critique GAP-3 weighed against the test-fixture
    # noise of always-printing; the interactive default path is what matters.)
    if not _strict_executable_is_active(prog) and not args.quiet:
        for advisory_lineno, advisory_message in collect_security_advisories(prog):
            code_match = re.match(r"(SS\d+)", advisory_message)
            advisory_code = code_match.group(1) if code_match else "SS4600"
            advisory_span = _strict_span(prog, advisory_lineno)
            location = (f"{advisory_span.path}:{advisory_span.line}"
                        if advisory_span else "<unknown>")
            hint, fix = _SECURITY_ADVISORY_GUIDANCE.get(advisory_code, ("", ""))
            lines = [f"warning {advisory_code}: {advisory_message}",
                     f"  at {location}"]
            if hint:
                lines.append(f"  hint: {hint}")
            if fix:
                lines.append(f"  fix: {fix}")
            lines.append("  non-blocking; `languageMode strictExecutable` / "
                         "`--strict` makes security rules fatal")
            print("\n".join(lines), file=sys.stderr)

    if args.lint or args.strict:
        lint(prog, strict=args.strict)

    try:
        build_dir_override = args.build_dir
        build_root_override = args.build_root
        build_folder_override = args.build_folder_name
        if build_dir_override is None:
            build_dir_override = _build_metadata_value(prog, "buildDir")
        if build_dir_override is None:
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
        if args.parse_only and (
                args.inspect_ir is not None or args.emit_trace_map is not None):
            ap.error("--inspect-ir and --emit-trace-map require codegen; "
                     "remove --parse-only")
        if args.run and args.inspect_ir == "-":
            ap.error("--run cannot be combined with --inspect-ir stdout output; "
                     "write --inspect-ir to a path")
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
        cg = Codegen(prog, runtime_checks=runtime_checks,
                     trace_events=args.trace)
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

    try:
        runtime_sources, runtime_link_args, runtime_link_components = (
            _native_runtime_link_inputs(prog))
    except CompilerDiagnosticError as e:
        print(e.diagnostic.render(args.diagnostics_format), file=sys.stderr)
        if os.environ.get("SEMSC_TRACEBACK"):
            import traceback as _tb
            _tb.print_exc(file=sys.stderr)
        sys.exit(3)
    inspect_ir_path = _resolve_agent_json_output_path(
        args.source, build_dir, args.inspect_ir, ".inspect-ir.json")
    trace_map_path = _resolve_agent_json_output_path(
        args.source, build_dir, args.emit_trace_map, ".trace-map.json")
    inspect_payload = None
    wrote_stdout_json = False
    did_output = False
    outputs = []
    if args.inspect_ir is not None or args.emit_trace_map is not None:
        inspect_payload = _inspect_ir_payload_for_agents(
            prog, cg, mod, ir_text, build_profile, runtime_checks,
            opt_level, cpu_config, persisted_ir_path, emit_optimized_ir_path,
            runtime_link_components)
    if args.inspect_ir is not None:
        _write_agent_json_payload(inspect_payload, inspect_ir_path)
        if inspect_ir_path is None:
            wrote_stdout_json = True
        else:
            did_output = True
            outputs.append(("inspect ir json", inspect_ir_path))
    if args.emit_trace_map is not None:
        _write_agent_json_payload(inspect_payload["traceMap"], trace_map_path)
        if trace_map_path is None:
            wrote_stdout_json = True
        else:
            did_output = True
            outputs.append(("trace map json", trace_map_path))

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
            extra_sources = list(runtime_sources)
            extra_link_args = list(runtime_link_args)
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

    if did_output and not args.quiet and not args.run and not wrote_stdout_json:
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
        if getattr(args, "run_metrics", False):
            rc, execute_ns = jit_run(
                ir_text, opt_level=opt_level,
                emit_optimized_ir_to=emit_optimized_ir_path,
                cpu_config=cpu_config,
                collect_execution_metrics=True)
            peak_bytes, memory_source = _peak_working_set_bytes()
            metrics = {
                "executeNs": execute_ns,
                "exitCode": rc,
                "peakWorkingSetBytes": peak_bytes,
                "memorySource": memory_source,
                # A caller-supplied nonce lets the consumer distinguish this
                # genuine end-of-run sentinel from any look-alike line the
                # running program may have written to stderr.
                "nonce": os.environ.get("SEM_RUN_METRICS_NONCE", ""),
            }
            sys.stdout.flush()
            print("__SEM_RUN_METRICS__ " + json.dumps(metrics, sort_keys=True),
                  file=sys.stderr, flush=True)
            sys.exit(rc)
        rc = jit_run(ir_text, opt_level=opt_level,
                     emit_optimized_ir_to=emit_optimized_ir_path,
                     cpu_config=cpu_config)
        sys.exit(rc)

    if not did_output and not wrote_stdout_json and not args.quiet:
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
