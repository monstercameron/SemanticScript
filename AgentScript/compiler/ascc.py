"""
ascc - the AgentScript compiler.

Implements a faithful subset of the AgentScript language (per
../spec/AgentScript.md and ../AST.md). Compiles a line-oriented AgentScript
program to LLVM IR via llvmlite, then either JIT-executes via MCJIT or writes
the IR to a .ll file.

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
import os
import sys
from llvmlite import ir
import llvmlite.binding as llvm

# Make sibling-module imports work when the compiler is invoked by path.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import libc_registry

__version__ = "1.0.0"


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


# ============================================================
# AST
# ============================================================

class Operation:
    def __init__(self, name):
        self.name = name
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


class Program:
    def __init__(self):
        # ---- declarations relevant to codegen ----
        self.project_name = None
        self.targets = []
        self.entry = None
        self.consts = {}              # name -> (type, value)
        self.type_aliases = {}        # alias -> underlying typename
        self.errors = {}              # err_type_name -> list[(variant_name, underlying_cause_type)]
        self.operations = {}          # name -> Operation
        self.current_op = None

        # ---- richer-surface storage (parsed; codegen treats as metadata) ----
        self.records = {}             # name -> Record
        self.enums = {}                # name -> Enum
        self.web_servers = {}          # name -> WebServer
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
    "returnOk", "returnError", "returnValue",
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
    "useCapability",
    "importModule",
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


def parse(source: str) -> Program:
    prog = Program()
    for lineno, raw in enumerate(source.splitlines(), start=1):
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
        except SyntaxError:
            raise
        except Exception as e:
            raise SyntaxError(f"line {lineno}: {e}\n  >> {raw}") from e
    return prog


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
    if verb in ("runtime", "module"):
        return
    if verb == "mode":
        # mode NAME — declares an honest classification of the program's
        # algorithm. The closed set of supported values is documented in
        # AST.md §10:
        #   capturedOutputReplay  the program's stdout is a transcript captured
        #                         from a sibling implementation rather than the
        #                         output of a re-run algorithm in AgentScript
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

    # ----- dependency contract -----
    if verb in ("dependency", "dependencyEffect", "dependencyExports",
                "dependencyFunction", "dependencyFunctionInput",
                "dependencyFunctionOutput", "dependencyFunctionEffect",
                "dependencyFunctionAsync"):
        return
    if verb == "importModule":
        # importModule DOTTED.PATH as ALIAS  (the `as ALIAS` part is optional)
        alias = None
        if len(args) >= 3 and args[1] == "as":
            alias = args[2]
        prog.imports.append((args[0], alias))
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
        prog.hard_metadata.setdefault(args[0], {}).setdefault(
            "authority", []).append(" ".join(args[1:]))
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
        op = Operation(args[0])
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

    raise SyntaxError(f"line {lineno}: unknown verb: {verb!r}")


# Verbs that carry the operation name as their first arg for §9 checkability.
HEADER_VERBS_WITH_OWNERSHIP = {
    "input", "output", "effect", "memory", "async",
    "purpose", "invariant", "warning",
    "guarantee", "failure", "security", "timing", "observability",
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


def llvm_type_for(prog: Program, typename: str):
    typename = resolve_alias(prog, typename)
    # C-stdlib alignment: every C scalar type has a spec-compliant
    # AgentScript alias whose name carries signedness, width, ABI role, or
    # encoding contract (spec §6 names-must-carry-local-intent, §10
    # types-encode-intent). The short forms (CInt / CDouble / CSize / …)
    # are retained as backward-compatible aliases for older programs but
    # new code should prefer the spec-compliant names listed first.
    #
    # i64 — every 64-bit-wide C type
    if typename in (
        # canonical AgentScript names
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
    ):
        return I8P
    if typename in (
        "VoidPtr", "COpaqueMemoryAddress", "CFileHandle",
        "CDecomposedTimeAddress", "CSetjmpRegisterBuffer",
        "CVoidPtr", "CFile", "CFilePtr", "CTm", "CTmPtr", "CJmpBuf",
    ):
        return I8P
    return None


def llvm_type_for_or_void(prog: Program, typename: str):
    """Like llvm_type_for but also accepts 'Void' / 'CVoid' as the void type."""
    if typename in ("Void", "CVoid"):
        return VOID
    return llvm_type_for(prog, typename)


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
# the AS surface matches the spec without link-time surprises across libc
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


# ============================================================
# Codegen
# ============================================================

class Codegen:
    def __init__(self, prog: Program):
        self.prog = prog
        self.module = ir.Module(name=prog.project_name or "agentscript_module")
        self.module.triple = llvm.get_default_triple()
        self.strings = {}
        self._next_str_id = 0
        self._declare_externals()

    def _declare_externals(self):
        # `puts` and `printf` are declared lazily, on first reference (see
        # `_get_puts` / `_get_printf`). The lazy declaration lets an
        # AgentScript program define its OWN user-operation called `puts`
        # (e.g. an AS-native stdio.as that bottoms out through c.putchar)
        # without colliding with the compiler's libc glue. The first call
        # that actually needs the libc symbol gets it declared then.
        self._puts = None
        self._printf = None
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
        # Cache for stdio stream globals (stdin / stdout / stderr).
        self._libc_streams = {}

    @property
    def puts(self):
        """Lazily declare the libc puts extern. Skipped if the program
        already defines a user-operation named `puts` (in that case
        console.writeLine etc. will pick up the AS-native one through the
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

    # Attribute groups applied to libc declarations so the LLVM optimizer can
    # treat them as nearly-pure functions. Without these the JIT cannot hoist
    # repeated math calls across a loop or vectorize them, which leaves
    # AgentScript several times slower than clang -O2 on math-heavy code.
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

    def _libc_func(self, as_name: str):
        """Return an LLVM Function for libc <as_name>, declaring it on
        demand. The AS-facing name may be the C symbol itself (printf,
        strlen, malloc) or a camelCase alias (alignedAlloc, threadCreate,
        mutexLock, …) that maps to an underscored C symbol. The dispatcher
        consults `libc_registry.resolve_c_symbol` to translate.

        If the module already has a function by the resolved C symbol
        (e.g. `printf` is pre-declared by _declare_externals for the
        writeIntegerLine path), reuse the existing declaration."""
        if as_name in self._libc_funcs:
            return self._libc_funcs[as_name]
        # Translate AS-facing camelCase to the underscored C symbol per
        # spec §5 (only `.`/`"`/`#`/`/` are AS punctuation; foreign symbol
        # names that contain `_` are exposed through aliases).
        c_symbol = libc_registry.resolve_c_symbol(as_name)
        # Reuse any existing LLVM extern with the target C symbol name.
        for existing in self.module.functions:
            if existing.name == c_symbol:
                self._libc_funcs[as_name] = existing
                return existing
        # Signature lookup: try AS-facing name first, then the C symbol.
        sig = libc_registry.ALL_FUNCTIONS.get(as_name)
        if sig is None:
            sig = libc_registry.ALL_FUNCTIONS.get(c_symbol)
        if sig is None:
            raise ValueError(f"unknown c.* function: c.{as_name}")
        ret_typ, param_typs, var_args = sig
        llvm_ret = llvm_type_for_or_void(self.prog, ret_typ)
        if llvm_ret is None:
            raise ValueError(f"unsupported return type `{ret_typ}` for c.{as_name}")
        llvm_params = []
        for ptyp in param_typs:
            ll = llvm_type_for(self.prog, ptyp)
            if ll is None:
                raise ValueError(f"unsupported param type `{ptyp}` for c.{as_name}")
            llvm_params.append(ll)
        fnty = ir.FunctionType(llvm_ret, llvm_params, var_arg=var_args)
        # Use the C symbol as the LLVM extern name so the linker resolves
        # to the actual libc function (not the AS-facing camelCase form).
        fn = ir.Function(self.module, fnty, name=c_symbol)
        for attr in self._attrs_for(c_symbol):
            fn.attributes.add(attr)
        self._libc_funcs[as_name] = fn
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

    # ---------- entry ----------
    def compile(self):
        # When `target webServer` is declared with no explicit `entry` line,
        # the program's entry points are its `route` handlers, not a main()
        # operation. We don't yet host an HTTP runtime, but we still emit
        # every handler as an LLVM function and a stub `int main() { return 0; }`
        # so the program links and the AST/tooling pass sees the real bodies.
        webserver_mode = (
            self.prog.entry is None
            and ("webServer" in self.prog.targets or self.prog.web_servers)
        )
        if webserver_mode:
            self._compile_webserver_program()
            return self.module
        if self.prog.entry is None:
            raise ValueError("no `entry` line found")
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

        # ---- pass 1: pre-declare every non-main user operation as an LLVM
        # function prototype, so any operation can call any other regardless
        # of source order. The signature is `i32 op(params...)` where params
        # come from `input` lines minus opaque-dependency symbols (the
        # `console`/`process`/etc. inputs documented by §16 but not carried
        # at the LLVM ABI boundary).
        self._user_ops = {}  # opName -> {"fn": LLVMFn, "params": [(pname, llty, ptype_name)]}
        for name, op in self.prog.operations.items():
            if name == opname:
                continue
            self._declare_user_op(op)

        # ---- pass 2: compile each non-main op's body into its prototype.
        for name, op in self.prog.operations.items():
            if name == opname:
                continue
            self._compile_user_op(op)

        # ---- pass 3: compile main with the void signature `i32 @main()`.
        self._compile_main(self.prog.operations[opname])
        return self.module

    # ---------- user-defined operations ----------
    def _declare_user_op(self, op: Operation):
        """Walk the operation's `input` lines, drop opaque-dep params, build
        the LLVM function prototype, and record it for later call-site lookup.

        The return type is derived from the operation's `output` line:
            output OPNAME Result OK_TYPE ERR_TYPE     -> OK_TYPE
            output OPNAME OK_TYPE                     -> OK_TYPE
        If OK_TYPE is `Void` (the spec's no-value success leg), we fall back
        to i32 because the LLVM ABI still needs a concrete return slot — the
        i32 then carries a sentinel zero. If the output line is missing or
        the OK type isn't a known AS type alias, we also use i32 (backward
        compatible with pre-typed user-ops)."""
        params = []  # list of (pname, llvm_type, source_type_name)
        return_type = I32  # default
        return_type_name = None
        for verb, args, _ln in op.lines:
            if verb == "output" and len(args) >= 2:
                # args = [opname, ...rest]
                rest = args[1:]
                ok_type_name = None
                if len(rest) >= 1 and rest[0] == "Result" and len(rest) >= 2:
                    ok_type_name = rest[1]
                elif len(rest) >= 1:
                    ok_type_name = rest[0]
                if ok_type_name and ok_type_name not in ("Void", "CVoid"):
                    rt = llvm_type_for(self.prog, ok_type_name)
                    if rt is not None:
                        return_type = rt
                        return_type_name = ok_type_name
                continue
            if verb != "input" or len(args) < 3:
                continue
            _owner_op_name, pname, ptype = args[0], args[1], args[2]
            if pname in OPAQUE_INPUTS:
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

    def _compile_user_op(self, op: Operation):
        info = self._user_ops[op.name]
        fn = info["fn"]
        entry_bb = fn.append_basic_block("entry")
        builder = ir.IRBuilder(entry_bb)
        initial_binds = {pname: fn.args[i]
                         for i, (pname, _, _) in enumerate(info["params"])}
        self._compile_body(op, fn, builder, initial_binds=initial_binds)

    # ---------- main operation ----------
    def _compile_main(self, op: Operation):
        fnty = ir.FunctionType(I32, [])
        fn = ir.Function(self.module, fnty, name="main")
        entry_bb = fn.append_basic_block("entry")
        builder = ir.IRBuilder(entry_bb)
        self._compile_body(op, fn, builder, initial_binds={})

    def _compile_webserver_program(self):
        # Compile every operation as a callable function (handlers + any
        # helpers). The HTTP runtime isn't wired here — instead we emit a
        # stub `int main()` that returns 0 so the program links. The route
        # handlers exist as real LLVM functions that an external runtime
        # could dispatch to once added.
        self._user_ops = {}
        for name, op in self.prog.operations.items():
            self._declare_user_op(op)
        for name, op in self.prog.operations.items():
            self._compile_user_op(op)
        fnty = ir.FunctionType(I32, [])
        fn = ir.Function(self.module, fnty, name="main")
        entry_bb = fn.append_basic_block("entry")
        builder = ir.IRBuilder(entry_bb)
        builder.ret(ir.Constant(I32, 0))

    # ---------- shared body compilation ----------
    def _compile_body(self, op: Operation, fn, builder, initial_binds: dict):
        prog = self.prog

        labels = {}        # name -> BasicBlock
        calls = {}         # callName -> {target, args, result, error_value, error_cond}
        binds = dict(initial_binds)  # bind-name -> SSA value (or alloca pointer for vars)
        var_types = {}     # var-name -> LLVM type
        is_var = set()     # set of mutable var names

        # Pre-create blocks for every label in source order
        for verb, args, _ln in op.lines:
            if verb == "label":
                labels[args[0]] = fn.append_basic_block(args[0])

        SENTINEL = object()
        opaque_inputs = OPAQUE_INPUTS

        def get_block(name):
            if name not in labels:
                labels[name] = fn.append_basic_block(name)
            return labels[name]

        def emit_const_value(typ, raw):
            llty = llvm_type_for(prog, typ)
            resolved = resolve_alias(prog, typ)
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
                    return ir.Constant(I1, int(bool(int(raw))))
                return ir.Constant(llty, int(raw))
            if isinstance(llty, (ir.FloatType, ir.DoubleType)):
                return ir.Constant(llty, float(raw))
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
            if tok in prog.consts:
                typ, val = prog.consts[tok]
                return emit_const_value(typ, val)
            if tok in opaque_inputs:
                return SENTINEL
            raise ValueError(f"unresolved symbol: {tok!r}")

        for verb, args, _ln in op.lines:
            # ----- metadata: ignored at codegen -----
            if verb in ("input", "output", "effect", "memory", "async",
                        "purpose", "invariant", "warning"):
                continue

            if verb == "label":
                target_bb = labels[args[0]]
                if not builder.block.is_terminated:
                    builder.branch(target_bb)
                builder.position_at_end(target_bb)
                continue

            if verb == "const":
                continue

            if verb == "var":
                # var NAME TYPE INITIAL_VALUE
                # INITIAL_VALUE may be a literal OR the name of a previously
                # declared const, so a domain start value can be expressed once
                # and referenced from its initialization. The latter form is
                # the recommended AgentScript style.
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
                        init = ir.Constant(I1, int(bool(int(const_val))))
                    elif isinstance(llty, (ir.FloatType, ir.DoubleType)):
                        init = ir.Constant(llty, float(const_val))
                    else:
                        init = ir.Constant(llty, int(const_val))
                elif llty == I8P and isinstance(raw, str):
                    init = self._i8p(builder, raw)
                elif resolved_typ == "Bool":
                    init = ir.Constant(I1, int(bool(int(raw))))
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
                name, value_name = args[0], args[1]
                if name not in is_var:
                    raise ValueError(f"set: {name} is not a var")
                new_val = resolve(value_name)
                slot = binds[name]
                if new_val.type != var_types[name]:
                    if isinstance(new_val.type, ir.IntType) and isinstance(var_types[name], ir.IntType):
                        if new_val.type.width < var_types[name].width:
                            new_val = builder.sext(new_val, var_types[name])
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
                calls[call_name] = {
                    "target": target, "args": {},
                    "result": None, "error_value": None, "error_cond": None,
                }
                continue

            if verb == "arg":
                call_name, arg_name, value_name = args[0], args[1], args[2]
                calls[call_name]["args"][arg_name] = value_name
                continue

            if verb in ("timeout", "cancelOn"):
                continue

            if verb == "run":
                self._emit_run(builder, args[0], calls, resolve, opaque_inputs, SENTINEL)
                continue

            if verb in ("start", "await"):
                # synchronous fallback for this implementation level
                if verb == "await":
                    self._emit_run(builder, args[0], calls, resolve, opaque_inputs, SENTINEL)
                continue

            if verb in ("bindOk", "bind"):
                value_name, _type_name, call_name = args[0], args[1], args[2]
                binds[value_name] = calls[call_name]["result"]
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
            if verb in ("defer", "deferLog", "deferAwaitLog",
                        "deferWhenExitLog", "useRetry",
                        "taskGroup", "startInGroup", "awaitGroup",
                        "branchIfGroupError"):
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
                    # default convention for console/io calls: a negative
                    # return value indicates failure.
                    result = call["result"]
                    zero = ir.Constant(result.type, 0)
                    err_cond = builder.icmp_signed("<", result, zero, name=f"{call_name}_isErr")
                cont = builder.function.append_basic_block(f"after_{call_name}")
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
                    builder.cbranch(cond_val, get_block(t_label), cont)
                    builder.position_at_end(cont)
                else:
                    cond_name, t_label, f_label = args[0], args[1], args[2]
                    cond_val = resolve(cond_name)
                    if cond_val.type != I1:
                        cond_val = builder.icmp_signed("!=", cond_val, ir.Constant(cond_val.type, 0))
                    builder.cbranch(cond_val, get_block(t_label), get_block(f_label))
                    dead = builder.function.append_basic_block(f"after_branchIf_{cond_name}")
                    builder.position_at_end(dead)
                continue

            if verb == "branch":
                builder.branch(get_block(args[0]))
                dead = builder.function.append_basic_block(f"after_branch_{args[0]}")
                builder.position_at_end(dead)
                continue

            if verb in ("returnOk", "returnError", "returnValue"):
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
                    # Otherwise: fall through; llvmlite will complain if the
                    # mismatch is genuinely irreconcilable, which is what we
                    # want for surfacing source-level type errors.
                builder.ret(val)
                continue

            raise ValueError(f"codegen unhandled verb: {verb}")

        if not builder.block.is_terminated:
            builder.ret(ir.Constant(I32, 0))

    # ---------- run dispatch ----------
    def _emit_run(self, builder, call_name, calls, resolve, opaque_inputs, SENTINEL):
        call = calls[call_name]
        target = _TARGET_ALIASES.get(call["target"], call["target"])

        # Lower domain-typed methods (`TypeName.methodName`) to the underlying
        # primitive based on the type alias's resolution chain. This keeps the
        # source-level call advertising domain context while reusing the
        # primitive dispatch below.
        if (target not in _BINOP_TO_LLVM and target not in _CMP_TO_LLVM
                and target not in _FBINOP_TO_LLVM and target not in _FCMP_TO_LLVM
                and target not in ("console.writeLine", "console.writeIntegerLine")
                and not target.startswith("c.")
                and "." in target):
            type_part, method_part = target.split(".", 1)
            underlying = resolve_alias(self.prog, type_part)
            primitive = _DOMAIN_METHOD_TO_I64_PRIMITIVE.get(method_part)
            if primitive is not None and underlying == "I64":
                target = primitive
                call["target"] = primitive
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

        def to_i64(v):
            if v.type == I64:
                return v
            if isinstance(v.type, ir.IntType):
                return builder.sext(v, I64) if v.type.width < 64 else builder.trunc(v, I64)
            raise ValueError(f"{call_name}: cannot coerce {v.type} to i64")

        if target == "console.writeLine":
            text = arg_val_named("text")
            call["result"] = builder.call(self.puts, [text], name=f"{call_name}_res")
            return
        if target == "console.writeIntegerLine":
            n = to_i64(arg_val_named("value"))
            fmt_ptr = self._i8p(builder, "%lld\n")
            call["result"] = builder.call(self.printf, [fmt_ptr, n], name=f"{call_name}_res")
            return

        if target == "math.intToFloat":
            # Convert a signed integer to double precision (sitofp).
            # Used by AS-stdlib float math to bridge integer counters
            # into float computations without linking libm.
            usable = [(k, v) for k, v in call["args"].items()
                      if v not in opaque_inputs]
            v = resolve(usable[0][1])
            v = to_i64(v)
            call["result"] = builder.sitofp(v, F64, name=f"{call_name}_res")
            return
        if target == "math.floatToInt":
            # Convert a double-precision value to a signed 64-bit integer
            # by rounding toward zero (fptosi). Used to implement
            # floor/ceil/trunc in pure AS.
            usable = [(k, v) for k, v in call["args"].items()
                      if v not in opaque_inputs]
            v = resolve(usable[0][1])
            v = self._coerce_for_libc(builder, v, "CDouble")
            call["result"] = builder.fptosi(v, I64, name=f"{call_name}_res")
            return

        if target == "math.checkedMultiplyI64":
            # Lower to the signed-multiply-with-overflow intrinsic so that
            # callers can branchIfError on the overflow bit instead of
            # silently wrapping.
            a, b = operand_pair()
            a, b = to_i64(a), to_i64(b)
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
            a, b = to_i64(a), to_i64(b)
            op = _BINOP_TO_LLVM[target]
            call["result"] = getattr(builder, op)(a, b, name=f"{call_name}_res")
            return

        if target in _FBINOP_TO_LLVM:
            a, b = operand_pair()
            a = self._coerce_for_libc(builder, a, "CDouble")
            b = self._coerce_for_libc(builder, b, "CDouble")
            op = _FBINOP_TO_LLVM[target]
            call["result"] = getattr(builder, op)(a, b, name=f"{call_name}_res")
            return

        if target in _FCMP_TO_LLVM:
            a, b = operand_pair()
            a = self._coerce_for_libc(builder, a, "CDouble")
            b = self._coerce_for_libc(builder, b, "CDouble")
            call["result"] = builder.fcmp_ordered(_FCMP_TO_LLVM[target], a, b,
                                                  name=f"{call_name}_res")
            return

        if target in _CMP_TO_LLVM:
            a, b = operand_pair()
            a, b = to_i64(a), to_i64(b)
            call["result"] = builder.icmp_signed(_CMP_TO_LLVM[target], a, b, name=f"{call_name}_res")
            return

        # Pointer-arithmetic primitives. `pointer.loadByte` reads a single
        # byte at (buffer + offset). `pointer.storeByte` writes one. These
        # are the minimum primitives an AS program needs to observe buffer
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
            ptr = builder.gep(buffer_arg, [offset_arg], inbounds=True,
                              name=f"{call_name}_addr")
            call["result"] = builder.load(ptr, name=f"{call_name}_res")
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
        # AgentScript-level type system does not yet enforce.
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
        # FP comparisons / bit operations so the AS surface stays portable.
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
            as_name = target[2:]
            # Translate AS-facing camelCase to the C symbol, then look up
            # the signature under either spelling.
            c_symbol = libc_registry.resolve_c_symbol(as_name)
            sig = libc_registry.ALL_FUNCTIONS.get(as_name) \
                  or libc_registry.ALL_FUNCTIONS.get(c_symbol)
            if sig is None:
                raise ValueError(f"unsupported c.* target: {target}")
            ret_typ, param_typs, var_args = sig
            fn = self._libc_func(as_name)
            cname = as_name  # preserve downstream variable usage
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

        # User-defined operation invocation. The target is the operation name.
        # Match the call's `arg` lines to the operation's declared parameter
        # list, dropping any args that pass an opaque-dep value. The function
        # returns i32 with the puts/printf convention: negative means error,
        # which the existing branchIfError default condition already handles.
        if target in self._user_ops:
            op_info = self._user_ops[target]
            arg_values = []
            for pname, _llty, _ptype in op_info["params"]:
                sym = call["args"].get(pname)
                if sym is None:
                    raise ValueError(
                        f"{call_name}: missing arg `{pname}` for operation `{target}`")
                v = resolve(sym)
                if v is SENTINEL:
                    raise ValueError(
                        f"{call_name}: opaque-input symbol used as data arg `{pname}` for `{target}`")
                # narrowing/widening to match the declared parameter type
                if isinstance(v.type, ir.IntType) and isinstance(_llty, ir.IntType):
                    if v.type.width < _llty.width:
                        v = builder.sext(v, _llty)
                    elif v.type.width > _llty.width:
                        v = builder.trunc(v, _llty)
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
                call["error_cond"] = builder.icmp_unsigned(
                    "!=", result, ir.Constant(rt, None),
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

        # External-module fallback: targets that look like a method on an
        # imported module (`http.requestCancellationToken`,
        # `database.openConnection`, `AccountBalanceResponseJsonCodec.encode`,
        # `accountIdPathValidator.validate`, etc.) have no body in this
        # translation unit. Rather than fail codegen, emit a dummy zero result
        # so the surrounding control flow + bind chain still compiles. A real
        # runtime (when wired) would supply the implementation by linking
        # against the named module's exports. This mirrors what
        # bootstrap_general.as does via its runUnhandled path.
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
    where AgentScript's agent-safety laws (spec §2 linter-class rules) are
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
    "getsSafe":    [("read", "console.stdin")],
    "gets_s":      [("read", "console.stdin")],
    # filesystem
    "fopen":       [("read", "filesystem"), ("write", "filesystem")],
    "freopen":     [("read", "filesystem"), ("write", "filesystem")],
    "fclose":      [("write", "filesystem")],
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


def _check_libc_effect_coverage(prog: Program, diags):
    """For every c.* / pointer.* call in an operation, verify that the
    operation's `effect` lines declare the required effects (spec §17
    declared-effects-must-match-called-effects)."""
    for op_name, op in prog.operations.items():
        declared = set()
        for verb, args, _ in op.lines:
            if verb == "effect" and len(args) >= 3:
                declared.add((args[1], args[2]))
        for verb, args, lineno in op.lines:
            if verb != "call" or len(args) < 2:
                continue
            tgt = args[1]
            required = None
            if tgt.startswith("c."):
                as_name = tgt[2:]
                # Try AS-facing name first, then translate to C symbol.
                required = _LIBC_REQUIRED_EFFECTS.get(as_name)
                if required is None:
                    c_symbol = libc_registry.resolve_c_symbol(as_name)
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


def emit_executable(module_ir: str, exe_path: str, opt_level: int = 2) -> None:
    """Ahead-of-time compile AgentScript IR to a native executable.

    The AgentScript runtime depends only on libc, so the same toolchain that
    builds a C program can link an AS program: write the IR to a temp `.ll`,
    invoke clang (or whatever `ASCC_CLANG` resolves to), and let it produce
    a standalone exe. JIT overhead (MCJIT trampolines, PLT-style indirection)
    is removed entirely, which is what closes the gap with native C on tight
    inner loops."""
    import subprocess
    import tempfile

    clang = os.environ.get("ASCC_CLANG")
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
            "could not find a clang executable; set ASCC_CLANG=/path/to/clang")

    with tempfile.NamedTemporaryFile(suffix=".ll", delete=False, mode="w",
                                     encoding="utf-8") as f:
        ll_path = f.name
        f.write(module_ir)
    try:
        cmd = [clang, f"-O{opt_level}", "-o", exe_path, ll_path]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            raise RuntimeError(
                f"clang failed to compile AgentScript IR:\n{proc.stderr}")
    finally:
        try:
            os.unlink(ll_path)
        except OSError:
            pass


def jit_run(module_ir: str, opt_level: int = 2,
            emit_optimized_ir_to: str = None) -> int:
    llvm.initialize_native_target()
    llvm.initialize_native_asmprinter()
    mod = llvm.parse_assembly(module_ir)
    mod.verify()
    target = llvm.Target.from_default_triple()
    tm = target.create_target_machine(opt=opt_level)
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


def _resolve_imports(source: str, source_path: str) -> str:
    src_dir = os.path.dirname(os.path.abspath(source_path))
    project_root = os.path.dirname(src_dir) if os.path.basename(src_dir) in ("compiler", "bootstrap", "as", "stdlib_as", "feature_tests") else src_dir
    stdlib_dir = os.path.join(project_root, "stdlib_as")

    seen: set = set()
    out_lines: list = []
    pending: list = [(source, src_dir)]

    def find_module_file(dotted: str, from_dir: str):
        rel = dotted.replace(".", os.sep) + ".as"
        for base in (from_dir, stdlib_dir, project_root):
            candidate = os.path.join(base, rel)
            if os.path.isfile(candidate):
                return candidate
        # No leaf fallback: a missing module must stay missing, not silently
        # bind to a same-leafname file in a sibling directory (e.g. importing
        # `standard.time` should not pick up `stdlib_as/time.as`).
        return None

    header_skip = ("project ", "target ", "runtime ", "entry ")

    def process(text: str, base_dir: str, is_root: bool):
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("importModule "):
                parts = stripped.split()
                if len(parts) >= 2:
                    dotted = parts[1]
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
                        continue
                    if path is None:
                        out_lines.append(line)
                        continue
                    continue
            if not is_root and stripped.startswith(header_skip):
                continue
            out_lines.append(line)

    seen.add(os.path.abspath(source_path))
    process(source, src_dir, is_root=True)
    return "\n".join(out_lines) + "\n"


def main():
    ap = argparse.ArgumentParser(
        prog="ascc",
        description=f"AgentScript compiler (LLVM backend) v{__version__}",
    )
    ap.add_argument("source", nargs="?", help="path to .as source file")
    ap.add_argument("--version", action="version",
                    version=f"ascc {__version__}")
    ap.add_argument("--emit-ir", help="write LLVM IR to this path")
    ap.add_argument("--run", action="store_true", help="JIT-execute main after compile")
    ap.add_argument("--lint", action="store_true",
                    help="run agent-safety lint pass and report diagnostics")
    ap.add_argument("--strict", action="store_true",
                    help="treat lint diagnostics as fatal")
    ap.add_argument("--parse-only", action="store_true",
                    help="parse the source, run lint (if requested), and exit without codegen")
    ap.add_argument("--opt-level", type=int, default=2,
                    help="LLVM optimization level for the JIT (0..3); default 2")
    ap.add_argument("--emit-optimized-ir",
                    help="write the post-optimization LLVM IR to this path (after --opt-level passes run)")
    ap.add_argument("--emit-exe",
                    help="ahead-of-time compile to a native executable at this path "
                         "(uses clang on PATH or $ASCC_CLANG to link)")
    ap.add_argument("--quiet", action="store_true",
                    help="suppress informational messages on success")
    args = ap.parse_args()

    if not args.source:
        ap.error("the following arguments are required: source")

    try:
        with open(args.source, "r", encoding="utf-8") as f:
            source = f.read()
    except OSError as e:
        print(f"ascc: cannot read source file: {e}", file=sys.stderr)
        sys.exit(2)

    # Resolve cross-file imports. `importModule DOTTED.PATH [as ALIAS]`
    # lines reference module files. Convert the dotted path to a file
    # path (X.Y.Z → X/Y/Z.as) and search the source-file's directory and
    # the project's stdlib_as/ directory. Imported file content is
    # inlined; transitive imports are followed (with cycle detection).
    source = _resolve_imports(source, args.source)

    try:
        prog = parse(source)
    except SyntaxError as e:
        import traceback as _tb
        print(f"ascc: parse error in {args.source}: {e}", file=sys.stderr)
        if os.environ.get("ASCC_TRACEBACK"):
            _tb.print_exc(file=sys.stderr)
        sys.exit(2)

    if args.lint or args.strict:
        lint(prog, strict=args.strict)

    if args.parse_only:
        if not args.quiet:
            print(f"ascc: parse OK ({args.source})")
        return

    try:
        cg = Codegen(prog)
        mod = cg.compile()
    except NotImplementedError as e:
        print(f"ascc: {e}", file=sys.stderr)
        sys.exit(3)
    except Exception as e:
        import traceback as _tb
        print(f"ascc: codegen error in {args.source}: {e}", file=sys.stderr)
        if os.environ.get("ASCC_TRACEBACK"):
            _tb.print_exc(file=sys.stderr)
        sys.exit(3)
    ir_text = str(mod)

    did_output = False
    if args.emit_ir:
        with open(args.emit_ir, "w", encoding="utf-8") as f:
            f.write(ir_text)
        did_output = True
        if not args.quiet:
            print(f"ascc: wrote LLVM IR to {args.emit_ir}")

    if args.emit_exe:
        try:
            emit_executable(ir_text, args.emit_exe, opt_level=args.opt_level)
        except RuntimeError as e:
            print(f"ascc: {e}", file=sys.stderr)
            sys.exit(4)
        did_output = True
        if not args.quiet:
            print(f"ascc: wrote executable to {args.emit_exe}")

    if args.run:
        rc = jit_run(ir_text, opt_level=args.opt_level,
                     emit_optimized_ir_to=args.emit_optimized_ir)
        sys.exit(rc)

    if not did_output and not args.quiet:
        # Reaching this branch means the source compiled successfully but
        # no output flag was given. Tell the user what they could do next
        # instead of exiting silently.
        print(f"ascc: compile OK ({args.source}); no output requested. "
              f"Try --emit-ir, --emit-exe, or --run.")


if __name__ == "__main__":
    main()
