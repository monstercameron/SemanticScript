#!/usr/bin/env python3
"""Standalone SemanticScript linter.

The compiler has a small lint pass, but the language needs a linter that can
run independently in CI, editors, and agent workflows. This tool parses the
SemanticScript semantic tape directly and checks source-level laws that do not require
LLVM code generation.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

__version__ = "1.0.0"
SUPPORTED_SOURCE_SUFFIXES = {".sscript", ".sem"}


DECLARATION_VERBS = {
    "project", "target", "runtime", "entry", "module", "mode",
    "dependency", "dependencyEffect", "dependencyExports",
    "dependencyFunction", "dependencyFunctionInput", "dependencyFunctionOutput",
    "dependencyFunctionEffect", "dependencyFunctionAsync", "importModule",
    "type", "typeInvariant", "typeRepresentation", "typeTrust", "typeMemory",
    "typeLayout", "record", "field", "enum", "enumCase", "error",
    "errorCase", "operation", "webServer", "serverHost", "serverPort",
    "route", "routeTimeout", "routeMiddleware", "jsonCodec", "codec",
    "schema", "unknownFields", "validator", "mapper", "adapter", "boundary",
    "policy", "errorPolicy", "retryPolicy", "timeoutBudget", "resource",
    "resourceKey", "resourceValue", "resourceKind", "capability", "authority",
    "mutex", "shared", "channel", "const", "var", "storage", "testCovers",
    "section",
    "operationBody", "runtimeBinding", "intrinsicName",
    "domainLiteral", "domainLiteralSource", "domainLiteralTrust",
    "domainLiteralValidation",
    "literal", "literalSource", "literalTrust", "literalBytes",
    "literalPreview", "literalDigest",
    "typeParameter", "typeLiteralEncoding", "typeLiteralTerminator",
    "recordLayout", "recordAlign",
    "arrayType", "arrayLength", "sliceType", "listType", "listAllocator",
    "listLiteral", "listLiteralLength", "listLiteralIndexBase",
    "listLiteralIndexPolicy",
    "smallListType", "smallListInlineCapacity", "smallListSpillAllocator",
    "mapType", "mapKey", "mapValue", "mapAllocator",
    "collectionOperation", "collectionOperationArg",
    "collectionOperationOutput", "collectionOperationEffect",
    "collectionOperationFailure", "collectionOperationMutation",
    "collectionOperationAllocation", "collectionOperationCapacitySource",
    "collectionOperationLengthSource", "collectionOperationBorrowSource",
    "collectionOperationSpillAllocator", "collectionOperationSpillFailure",
    "collectionOperationIndexPolicy",
    "jsonCodecStrict", "jsonCodecUnknownFields", "jsonCodecInput",
    "jsonCodecOutput", "jsonCodecDecodeTarget", "jsonCodecEncodeTarget",
    "jsonCodecRequiredField", "jsonCodecLimit", "jsonCodecDecodeFailure",
    "jsonCodecEncodeFailure",
    "trustBoundary", "trustBoundaryKind", "trustBoundaryInput",
    "trustBoundaryOutput", "trustBoundarySource", "trustBoundaryValidator",
    "retryMaxAttempts", "retryInitialDelay", "retryMaximumDelay",
    "retryJitter",
    "workerPool", "work", "workArg",
    "group", "groupInput", "groupOutput", "groupPurpose", "groupTiming",
    "sharedState", "sharedStateOwner", "sharedStateGuard",
    "interval",
}

CONTEXT_VERBS = {
    "input", "output", "effect", "memory", "async", "purpose", "invariant",
    "warning", "guarantee", "failure", "security", "timing", "observability",
    "memoryHeap", "memoryArena", "memoryStackLimit",
    "memoryAllocationSource",
    # SS36xx explicit contract verbs (op-attached metadata; semlint2's
    # SS3603/SS3604/SS3606 cite them by walking op.lines)
    "pinsNullBodyFailurePath",
    "responseBodyForwarder",
    # `rationale CALL "text"` — call-site rationale; operation body verb
    # (sister to the `# rationale:` typed comment, more explicit).
    "rationale",
}

ACTION_VERBS = {
    "set", "call", "arg", "timeout", "cancelOn", "run", "start", "await",
    "bind", "bindOk", "bindError", "ignoreOk", "ignoreValue", "makeError",
    "taskGroup", "startInGroup", "awaitGroup", "bindGroupError", "defer",
    "deferLog", "deferAwaitLog", "deferWhenExitLog", "new", "fieldGet",
    "fieldSet", "send", "receive", "lock", "unlock", "select", "selectCase",
    "runSelect", "useRetry", "useCapability",
    "deferRunOn", "startInterval", "awaitIntervalTick",
    "submitWork", "awaitWork",
}

CONTROL_VERBS = {
    "label", "branch", "branchIf", "branchIfError", "branchIfGroupError",
    "branchIfChannelClosed", "branchSelected", "returnOk", "returnError",
    "returnValue",
}

KNOWN_VERBS = DECLARATION_VERBS | CONTEXT_VERBS | ACTION_VERBS | CONTROL_VERBS

BODY_VERBS = CONTEXT_VERBS | ACTION_VERBS | CONTROL_VERBS | {"const", "var", "storage", "importModule"}

PRIMITIVE_TARGETS = {
    "console.writeLine",
    "console.writeIntegerLine",
    "console.writeInteger",
    "math.addI64",
    "math.subtractI64",
    "math.multiplyI64",
    "math.divideI64",
    "math.moduloI64",
    "math.equalI64",
    "math.notEqualI64",
    "math.lessThanI64",
    "math.lessThanOrEqualI64",
    "math.greaterThanI64",
    "math.greaterThanOrEqualI64",
    "math.equalCSignedInt32",
    "math.notEqualCSignedInt32",
    "math.lessThanCSignedInt32",
    "math.lessThanOrEqualCSignedInt32",
    "math.greaterThanCSignedInt32",
    "math.greaterThanOrEqualCSignedInt32",
    "math.checkedMultiplyI64",
    "math.subI64",
    "math.mulI64",
    "math.divI64",
    "math.modI64",
    "math.eqI64",
    "math.neI64",
    "math.ltI64",
    "math.leI64",
    "math.gtI64",
    "math.geI64",
}

INFALLIBLE_DOMAIN_METHODS = {
    "add", "addPositiveStep", "subtract", "subtractStep",
    "subtractPositiveStep", "multiply", "multiplyByStep",
    "multiplyByCounter", "divide", "modulo", "moduloBy", "equal",
    "notEqual", "lessThan", "lessThanOrEqual", "greaterThan",
    "greaterThanOrEqual", "square",
}

FALLIBLE_DOMAIN_METHODS = {
    "checkedMultiply", "checkedMultiplyByCounter", "checkedMultiplyByStep",
}

CONSOLE_WRITE_TARGETS = {
    "console.writeLine", "console.writeIntegerLine", "console.writeInteger",
}

LIBC_POSITIVE_SUCCESS_TARGETS = {
    "printf", "fprintf", "sprintf", "snprintf",
    "vprintf", "vfprintf", "vsprintf", "vsnprintf",
    "puts", "fputs", "putchar", "fputc", "putc",
    "scanf", "fscanf", "sscanf", "vscanf", "vfscanf", "vsscanf",
    "fread", "fwrite",
}

HTTP_CALL_TARGET_EFFECTS = {
    "http.requestCancellationToken": ("read", "http.request.cancellationToken"),
    "http.requestMethod": ("read", "http.request.method"),
    "http.requestPath": ("read", "http.request.path"),
    "http.requestHeader": ("read", "http.request.header"),
    "http.requestQueryParam": ("read", "http.request.query"),
    "http.requestBodyText": ("read", "http.request.body"),
    "http.requestBodyBytes": ("read", "http.request.body"),
    "http.requestBodyLength": ("read", "http.request.body"),
    "http.multipartPartText": ("read", "http.request.multipart"),
    "http.multipartPartBytes": ("read", "http.request.multipart"),
    "http.multipartPartLength": ("read", "http.request.multipart"),
    "http.multipartPartFilename": ("read", "http.request.multipart"),
    "http.multipartPartContentType": ("read", "http.request.multipart"),
    "http.responseJson": ("write", "http.response"),
    "http.responseText": ("write", "http.response"),
    "http.responseBytes": ("write", "http.response"),
    "http.responseSseEvent": ("write", "http.response"),
    "http.responseHeader": ("write", "http.response.header"),
}

NULLABLE_HTTP_READER_TARGETS = {
    "http.requestHeader",
    "http.requestQueryParam",
    "http.multipartPartText",
    "http.multipartPartBytes",
    "http.multipartPartFilename",
    "http.multipartPartContentType",
}

NON_NULL_HTTP_SINK_ARG_NAMES = {
    "body",
    "value",
    "contentType",
    "event",
    "data",
}

CONTRACT_HEAVY_KINDS = {
    "record", "codec", "jsonCodec", "validator", "mapper", "adapter",
    "boundary", "policy", "errorPolicy", "retryPolicy", "timeoutBudget",
    "resource", "webServer",
}

BAD_NAMES = {
    "err", "tmp", "res", "data", "handler", "thing", "stuff", "value",
    "item", "obj", "util", "helper", "processData", "doThing",
}

SEMANTIC_COMMENT_PREFIXES = (
    "rationale:", "invariant:", "warning:", "failure:", "agent:", "purpose:",
    "group ", "endGroup ", "-----", "=====", "syntax_sample", "",
)

MIN_ARITY = {
    "project": 1,
    "target": 1,
    "runtime": 2,
    "entry": 2,
    "mode": 1,
    "type": 2,
    "error": 1,
    "errorCase": 2,
    "operation": 1,
    "input": 2,
    "output": 2,
    "effect": 3,
    "memory": 3,
    "memoryHeap": 2,
    "memoryArena": 3,
    "memoryStackLimit": 2,
    "async": 2,
    "purpose": 2,
    "invariant": 2,
    "warning": 2,
    "const": 3,
    "var": 3,
    "storage": 4,
    "label": 1,
    "call": 2,
    "arg": 3,
    "timeout": 2,
    "cancelOn": 2,
    "run": 1,
    "start": 1,
    "await": 1,
    "bind": 3,
    "bindOk": 3,
    "bindError": 3,
    "ignoreOk": 2,
    "ignoreValue": 2,
    "makeError": 2,
    "branch": 1,
    "branchIf": 2,
    "branchIfError": 2,
    "returnOk": 1,
    "returnError": 1,
    "returnValue": 1,
}

SEVERITY_ORDER = {"info": 0, "warning": 1, "error": 2}

INTEGER_WIDTH_TYPES = {
    "CSignedInt32": 32,
    "I32": 32,
    "CSignedInt64": 64,
    "I64": 64,
}


@dataclass
class Token:
    text: str
    start: int
    quoted: bool = False


@dataclass
class SourceLine:
    path: Path
    number: int
    raw: str
    tokens: List[Token]

    @property
    def verb(self) -> str:
        return self.tokens[0].text if self.tokens else ""

    @property
    def args(self) -> List[str]:
        return [token.text for token in self.tokens[1:]]

    @property
    def column(self) -> int:
        return self.tokens[0].start + 1 if self.tokens else 1

    def arg_column(self, index: int) -> int:
        token_index = index + 1
        if token_index < len(self.tokens):
            return self.tokens[token_index].start + 1
        return self.column


@dataclass
class Diagnostic:
    severity: str
    rule: str
    path: Path
    line: int
    column: int
    message: str

    def to_json(self) -> Dict[str, object]:
        return {
            "severity": self.severity,
            "rule": self.rule,
            "path": str(self.path),
            "line": self.line,
            "column": self.column,
            "message": self.message,
        }


@dataclass
class ConstFact:
    name: str
    type_name: str
    value: str
    line: SourceLine


@dataclass
class CallFact:
    name: str
    target: str
    line: SourceLine
    arg_lines: List[SourceLine] = field(default_factory=list)
    run_lines: List[SourceLine] = field(default_factory=list)
    start_lines: List[SourceLine] = field(default_factory=list)
    await_lines: List[SourceLine] = field(default_factory=list)
    bind_lines: List[SourceLine] = field(default_factory=list)
    bind_ok_lines: List[SourceLine] = field(default_factory=list)
    bind_error_lines: List[SourceLine] = field(default_factory=list)
    ignore_ok_lines: List[SourceLine] = field(default_factory=list)
    ignore_value_lines: List[SourceLine] = field(default_factory=list)
    branch_error_lines: List[SourceLine] = field(default_factory=list)
    timeout_lines: List[SourceLine] = field(default_factory=list)
    cancel_lines: List[SourceLine] = field(default_factory=list)
    group_start_lines: List[SourceLine] = field(default_factory=list)


@dataclass
class OperationFact:
    name: str
    line: SourceLine
    lines: List[SourceLine] = field(default_factory=list)
    group_anchors: List[Tuple[str, str, SourceLine]] = field(default_factory=list)


@dataclass
class AbstractionFact:
    kind: str
    name: str
    line: SourceLine


@dataclass
class CapabilityFact:
    name: str
    effect_path: str
    access: str
    line: SourceLine


@dataclass
class RouteFact:
    server: str
    method: str
    path: str
    handler: str
    line: SourceLine


@dataclass
class ProgramFacts:
    path: Path
    lines: List[SourceLine] = field(default_factory=list)
    modes: Set[str] = field(default_factory=set)
    consts: Dict[str, ConstFact] = field(default_factory=dict)
    operations: Dict[str, OperationFact] = field(default_factory=dict)
    abstractions: Dict[str, AbstractionFact] = field(default_factory=dict)
    hard_metadata: Dict[str, Set[str]] = field(default_factory=dict)
    type_metadata: Dict[str, Set[str]] = field(default_factory=dict)
    type_aliases: Dict[str, str] = field(default_factory=dict)
    module_group_anchors: List[Tuple[str, str, SourceLine]] = field(default_factory=list)
    capabilities: Dict[str, CapabilityFact] = field(default_factory=dict)
    routes: List[RouteFact] = field(default_factory=list)
    imports: Set[str] = field(default_factory=set)


def tokenize_line(raw: str) -> List[Token]:
    stripped = raw.strip()
    if not stripped:
        return []
    if stripped.startswith("#"):
        comment_start = raw.index("#")
        return [Token("#", comment_start), Token(stripped[1:].strip(), comment_start + 1)]

    tokens: List[Token] = []
    index = 0
    length = len(raw)
    while index < length:
        char = raw[index]
        if char.isspace():
            index += 1
            continue
        if char == "#":
            break
        if char == '"':
            start = index
            index += 1
            value_chars: List[str] = []
            while index < length:
                current = raw[index]
                if current == "\\" and index + 1 < length:
                    escaped = raw[index + 1]
                    value_chars.append({
                        "n": "\n",
                        "t": "\t",
                        "r": "\r",
                        "\\": "\\",
                        '"': '"',
                        "0": "\0",
                    }.get(escaped, escaped))
                    index += 2
                    continue
                if current == '"':
                    index += 1
                    break
                value_chars.append(current)
                index += 1
            tokens.append(Token("".join(value_chars), start, quoted=True))
            continue

        start = index
        while index < length and not raw[index].isspace():
            if raw[index] == "#":
                break
            index += 1
        tokens.append(Token(raw[start:index], start))
    return tokens


def is_comment(line: SourceLine) -> bool:
    return bool(line.tokens) and line.tokens[0].text == "#"


def comment_text(line: SourceLine) -> str:
    if is_comment(line) and len(line.tokens) >= 2:
        return line.tokens[1].text
    return ""


def parse_file(path: Path) -> ProgramFacts:
    program = ProgramFacts(path=path)
    current_op: Optional[OperationFact] = None

    with path.open("r", encoding="utf-8") as source_file:
        for line_number, raw_line in enumerate(source_file, start=1):
            raw = raw_line.rstrip("\n")
            line = SourceLine(path=path, number=line_number, raw=raw, tokens=tokenize_line(raw))
            program.lines.append(line)
            if not line.tokens:
                continue

            if is_comment(line):
                anchor = parse_group_comment(line)
                if anchor:
                    if current_op:
                        current_op.group_anchors.append(anchor)
                    else:
                        program.module_group_anchors.append(anchor)
                continue

            verb = line.verb
            args = line.args

            if verb == "operation" and args:
                current_op = OperationFact(name=args[0], line=line)
                current_op.lines.append(line)
                program.operations[args[0]] = current_op
                program.abstractions.setdefault(args[0], AbstractionFact("operation", args[0], line))
                continue

            if current_op and (verb in BODY_VERBS or verb in CONTEXT_VERBS):
                current_op.lines.append(line)

            if verb == "mode" and args:
                program.modes.add(args[0])
            elif verb == "importModule" and args:
                program.imports.add(args[0])
            elif verb == "const" and len(args) >= 3:
                program.consts[args[0]] = ConstFact(args[0], args[1], args[2], line)
            elif verb == "type" and len(args) >= 2:
                program.type_aliases[args[0]] = args[1]
            elif verb.startswith("type") and len(args) >= 1 and verb != "type":
                program.type_metadata.setdefault(args[0], set()).add(verb)
            elif verb == "capability" and len(args) >= 3:
                program.capabilities[args[0]] = CapabilityFact(args[0], args[1], args[2], line)
            elif verb == "route" and len(args) >= 4:
                program.routes.append(RouteFact(args[0], args[1], args[2], args[3], line))
            elif verb in CONTRACT_HEAVY_KINDS and args:
                program.abstractions.setdefault(args[0], AbstractionFact(verb, args[0], line))
            elif verb in {"purpose", "invariant", "warning", "guarantee", "failure", "security", "timing", "observability"} and args:
                program.hard_metadata.setdefault(args[0], set()).add(verb)

    return program


def parse_group_comment(line: SourceLine) -> Optional[Tuple[str, str, SourceLine]]:
    text = comment_text(line)
    if text.startswith("group "):
        return ("group", text.split(None, 1)[1].strip(), line)
    if text.startswith("endGroup "):
        return ("endGroup", text.split(None, 1)[1].strip(), line)
    return None


def resolve_type(program: ProgramFacts, type_name: str) -> str:
    seen = set()
    while type_name in program.type_aliases and type_name not in seen:
        seen.add(type_name)
        type_name = program.type_aliases[type_name]
    return type_name


def add_diag(diags: List[Diagnostic], severity: str, rule: str, line: SourceLine, message: str, column: Optional[int] = None) -> None:
    diags.append(Diagnostic(
        severity=severity,
        rule=rule,
        path=line.path,
        line=line.number,
        column=column if column is not None else line.column,
        message=message,
    ))


def lint_program(program: ProgramFacts) -> List[Diagnostic]:
    diags: List[Diagnostic] = []
    relaxed_operation_profile = uses_relaxed_operation_lint_profile(program.path)

    lint_line_shape(program, diags)
    lint_group_balance(program.module_group_anchors, diags, "module")
    lint_duplicate_literals(program, diags)
    lint_route_metadata(program, diags)
    lint_webserver_native_abi(program, diags)
    if relaxed_operation_profile:
        return sorted(diags, key=lambda item: (str(item.path), item.line, item.column, item.rule))

    lint_abstractions(program, diags)

    for operation in program.operations.values():
        lint_group_balance(operation.group_anchors, diags, f"operation {operation.name}")
        lint_operation(program, operation, diags)

    return sorted(diags, key=lambda item: (str(item.path), item.line, item.column, item.rule))


def uses_relaxed_operation_lint_profile(path: Path) -> bool:
    normalized_parts = [part.lower() for part in path.parts]
    if "semanticscript" not in normalized_parts:
        return False
    return "sem" in normalized_parts or "bootstrap" in normalized_parts


def effect_path_covers(scope_path: str, effect_path: str) -> bool:
    return effect_path == scope_path or effect_path.startswith(scope_path + ".")


def capability_authorizes(capability: CapabilityFact, action: str, effect_path: str) -> bool:
    return access_action_covers(capability.access, action) and effect_path_covers(capability.effect_path, effect_path)


def declared_effect_covers_actual(declared_effects: Set[Tuple[str, str]], action: str, effect_path: str) -> bool:
    return any(
        declared_action == action and effect_path_covers(declared_path, effect_path)
        for declared_action, declared_path in declared_effects
    )


def actual_effect_satisfies_declared(actual_effects: Dict[Tuple[str, str], List[SourceLine]], action: str, effect_path: str) -> bool:
    return any(
        actual_action == action and effect_path_covers(effect_path, actual_path)
        for actual_action, actual_path in actual_effects
    )


def lint_route_metadata(program: ProgramFacts, diags: List[Diagnostic]) -> None:
    route_paths_by_server: Dict[str, Set[str]] = {}
    for route in program.routes:
        route_paths_by_server.setdefault(route.server, set()).add(route.path)

    for line in program.lines:
        if line.verb not in {"routeTimeout", "routeMiddleware"} or len(line.args) < 2:
            continue

        server, selector = line.args[0], line.args[1]
        known_paths = route_paths_by_server.get(server, set())
        if selector in known_paths:
            continue

        selector_hint = "path selector" if selector.startswith("/") else "non-path selector"
        add_diag(
            diags,
            "warning",
            "danglingRouteMetadata",
            line,
            (
                f"`{line.verb}` references {selector_hint} `{selector}` on server `{server}`, "
                "but no declared route path matches it. Current route syntax exposes paths; "
                "use an existing path such as `/` or add named-route syntax before using route IDs."
            ),
            line.arg_column(1),
        )


def lint_webserver_native_abi(program: ProgramFacts, diags: List[Diagnostic]) -> None:
    for operation in program.operations.values():
        for line in operation.lines:
            if line.verb == "call" and len(line.args) >= 2 and line.args[1] in {
                "http.responseText",
                "http.responseBytes",
                "http.responseSseEvent",
                "http.responseJson",
                "http.responseHeader",
            }:
                lint_http_response_call_args(operation, line, operation.lines, diags)
            if line.verb == "call" and len(line.args) >= 2 and line.args[1] in {
                "http.requestMethod",
                "http.requestPath",
                "http.requestHeader",
                "http.requestQueryParam",
                "http.requestBodyText",
                "http.requestBodyBytes",
                "http.requestBodyLength",
                "http.multipartPartText",
                "http.multipartPartBytes",
                "http.multipartPartLength",
                "http.multipartPartFilename",
                "http.multipartPartContentType",
            }:
                lint_http_request_call_args(operation, line, operation.lines, diags)

    if not program.routes:
        return

    for route in program.routes:
        operation = program.operations.get(route.handler)
        if operation is None:
            add_diag(
                diags,
                "error",
                "webRouteHandlerMissing",
                route.line,
                f"route `{route.method} {route.path}` references missing handler `{route.handler}`",
                route.line.arg_column(3),
            )
            continue

        input_types: List[str] = []
        output_types: List[str] = []
        for line in operation.lines:
            if line.verb == "input" and len(line.args) >= 3 and line.args[0] == operation.name:
                input_types.append(line.args[2])
            elif line.verb == "output" and len(line.args) >= 2 and line.args[0] == operation.name:
                output_types = line.args[1:]

        if input_types != ["HttpRequest", "HttpResponse"]:
            add_diag(
                diags,
                "error",
                "webRouteHandlerAbi",
                operation.line,
                (
                    f"routed handler `{operation.name}` must declare exactly "
                    "`input <handler> request HttpRequest` and "
                    "`input <handler> response HttpResponse` for the native HTTP ABI"
                ),
                operation.line.arg_column(0),
            )
        if output_types != ["CSignedInt32"]:
            add_diag(
                diags,
                "error",
                "webRouteHandlerAbi",
                operation.line,
                f"routed handler `{operation.name}` must declare `output {operation.name} CSignedInt32`",
                operation.line.arg_column(0),
            )


def lint_http_response_call_args(
    operation: OperationFact,
    call_line: SourceLine,
    operation_lines: List[SourceLine],
    diags: List[Diagnostic],
) -> None:
    call_name = call_line.args[0]
    arg_names = {
        line.args[1]
        for line in operation_lines
        if line.verb == "arg" and len(line.args) >= 3 and line.args[0] == call_name
    }
    required_args = {
        "http.responseText": ("response", "status", "body"),
        "http.responseBytes": ("response", "status", "body", "bodyLength"),
        "http.responseSseEvent": ("response", "status", "event", "data"),
        "http.responseJson": ("response", "status", "body"),
        "http.responseHeader": ("response", "name", "value"),
    }.get(call_line.args[1], ())
    missing = [arg for arg in required_args if arg not in arg_names]
    if not missing:
        return
    add_diag(
        diags,
        "error",
        "httpResponseCallAbi",
        call_line,
        (
            f"call `{call_name}` targets `{call_line.args[1]}` but is missing "
            f"required arg(s): {', '.join(missing)}"
        ),
        call_line.arg_column(0),
    )


def lint_http_request_call_args(
    operation: OperationFact,
    call_line: SourceLine,
    operation_lines: List[SourceLine],
    diags: List[Diagnostic],
) -> None:
    call_name = call_line.args[0]
    arg_names = {
        line.args[1]
        for line in operation_lines
        if line.verb == "arg" and len(line.args) >= 3 and line.args[0] == call_name
    }
    required_args = {
        "http.requestMethod": ("request",),
        "http.requestPath": ("request",),
        "http.requestHeader": ("request", "name"),
        "http.requestQueryParam": ("request", "name"),
        "http.requestBodyText": ("request",),
        "http.requestBodyBytes": ("request",),
        "http.requestBodyLength": ("request",),
        "http.multipartPartText": ("request", "name"),
        "http.multipartPartBytes": ("request", "name"),
        "http.multipartPartLength": ("request", "name"),
        "http.multipartPartFilename": ("request", "name"),
        "http.multipartPartContentType": ("request", "name"),
    }.get(call_line.args[1], ())
    missing = [arg for arg in required_args if arg not in arg_names]
    if not missing:
        return
    add_diag(
        diags,
        "error",
        "httpRequestCallAbi",
        call_line,
        (
            f"call `{call_name}` targets `{call_line.args[1]}` but is missing "
            f"required arg(s): {', '.join(missing)}"
        ),
        call_line.arg_column(0),
    )


def lint_nullable_http_value_flow(
    operation: OperationFact,
    calls: Dict[str, CallFact],
    bind_sources: Dict[str, str],
    operation_contract_text: str,
    diags: List[Diagnostic],
) -> None:
    nullable_values = {
        symbol
        for symbol, call_name in bind_sources.items()
        if call_name in calls and calls[call_name].target in NULLABLE_HTTP_READER_TARGETS
    }
    if not nullable_values:
        return

    contract_documents_null_flow = any(
        marker in operation_contract_text
        for marker in ("null", "missing", "absent", "negative", "guard")
    )
    if contract_documents_null_flow:
        return

    guarded_nullable_values: Set[str] = set()
    for call in calls.values():
        if call.target != "pointer.isNull":
            continue
        guarded_values_for_call = {
            arg_line.args[2]
            for arg_line in call.arg_lines
            if len(arg_line.args) >= 3 and arg_line.args[2] in nullable_values
        }
        if not guarded_values_for_call:
            continue
        guard_result_symbols = {
            symbol
            for symbol, call_name in bind_sources.items()
            if call_name == call.name
        }
        if not guard_result_symbols:
            continue
        guard_is_branched = any(
            line.verb == "branchIf" and line.args and line.args[0] in guard_result_symbols
            for line in operation.lines
        )
        if guard_is_branched:
            guarded_nullable_values.update(guarded_values_for_call)

    for call in calls.values():
        for arg_line in call.arg_lines:
            if len(arg_line.args) < 3:
                continue
            arg_name = arg_line.args[1]
            arg_value = arg_line.args[2]
            if (
                arg_value not in nullable_values
                or arg_value in guarded_nullable_values
                or arg_name not in NON_NULL_HTTP_SINK_ARG_NAMES
            ):
                continue
            add_diag(
                diags,
                "warning",
                "nullableHttpValueFlow",
                arg_line,
                (
                    f"nullable HTTP reader result `{arg_value}` flows into "
                    f"`{call.name}` arg `{arg_name}` without a documented null guard; "
                    "use `pointer.isNull` or add an explicit warning/invariant for "
                    "the intentional negative behavior"
                ),
                arg_line.arg_column(2),
            )


def lint_line_shape(program: ProgramFacts, diags: List[Diagnostic]) -> None:
    relaxed_operation_profile = uses_relaxed_operation_lint_profile(program.path)
    for line in program.lines:
        if not line.tokens:
            continue
        if is_comment(line):
            lint_comment(line, diags)
            continue

        verb = line.verb
        if verb not in KNOWN_VERBS:
            add_diag(diags, "error", "unknownVerb", line, f"unknown SemanticScript verb `{verb}`")
            continue

        min_arity = MIN_ARITY.get(verb)
        if min_arity is not None and len(line.args) < min_arity:
            add_diag(diags, "error", "missingArgument", line, f"`{verb}` expects at least {min_arity} argument(s)")

        if any(";" in token.text for token in line.tokens if not token.quoted):
            add_diag(diags, "warning", "multipleSemanticActions", line, "semicolon suggests multiple semantic actions on one line")

        if any(("{" in token.text or "}" in token.text) for token in line.tokens if not token.quoted):
            add_diag(diags, "warning", "nestedSyntax", line, "brace syntax conflicts with SemanticScript's semantic tape model")

        for token in line.tokens:
            if token.quoted and looks_like_raw_json_string_interpolation(token.text):
                add_diag(
                    diags,
                    "warning",
                    "rawJsonStringInterpolation",
                    line,
                    "JSON-like string literal interpolates `%s` inside quotes; use a JSON encoder, escaping writer, or input validator",
                    token.start + 1,
                )

        if not relaxed_operation_profile:
            vague_positions = vague_name_positions(line)
            for arg_index in vague_positions:
                arg = line.args[arg_index]
                if arg in BAD_NAMES:
                    add_diag(
                        diags,
                        "warning",
                        "vagueName",
                        line,
                        f"`{arg}` is too vague for SemanticScript semantic context",
                        line.arg_column(arg_index),
                    )

            if verb == "type" and line.args and not is_pascal_case(line.args[0]):
                add_diag(diags, "warning", "typeNameCase", line, f"type alias `{line.args[0]}` should be PascalCase", line.arg_column(0))

            if verb == "operation" and line.args and not is_camel_case(line.args[0]):
                add_diag(diags, "warning", "operationNameCase", line, f"operation `{line.args[0]}` should be camelCase", line.arg_column(0))


def lint_comment(line: SourceLine, diags: List[Diagnostic]) -> None:
    text = comment_text(line)
    if not text:
        return
    if any(text.startswith(prefix) for prefix in SEMANTIC_COMMENT_PREFIXES):
        return
    add_diag(
        diags,
        "info",
        "nonSemanticComment",
        line,
        "comment does not use a semantic prefix such as rationale:, invariant:, warning:, failure:, agent:, group, or endGroup",
    )


def looks_like_raw_json_string_interpolation(value: str) -> bool:
    if "%s" not in value:
        return False
    compact = re.sub(r"\s+", "", value)
    if "{" not in compact and "[" not in compact:
        return False
    return bool(re.search(r'"\w+"\s*:\s*"%s"', compact) or re.search(r'"\%s"\s*[,}\]]', compact))


def vague_name_positions(line: SourceLine) -> List[int]:
    if not line.args:
        return []
    if line.verb in {
        "operation", "const", "var", "label", "call", "makeError", "type",
        "record", "enum", "error", "codec", "jsonCodec", "validator",
        "mapper", "adapter", "boundary", "policy", "errorPolicy",
        "retryPolicy", "timeoutBudget", "resource", "capability", "mutex",
        "shared", "channel", "webServer",
    }:
        return [0]
    if line.verb in {"bind", "bindOk", "bindError"}:
        return [0]
    return []


def lint_group_balance(anchors: List[Tuple[str, str, SourceLine]], diags: List[Diagnostic], scope: str) -> None:
    stack: List[Tuple[str, SourceLine]] = []
    for kind, name, line in anchors:
        if kind == "group":
            stack.append((name, line))
            continue
        if not stack:
            add_diag(diags, "warning", "groupCommentBalance", line, f"endGroup `{name}` in {scope} has no matching group")
            continue
        open_name, _open_line = stack.pop()
        if open_name != name:
            add_diag(diags, "warning", "groupCommentBalance", line, f"endGroup `{name}` in {scope} does not match group `{open_name}`")
    for name, line in stack:
        add_diag(diags, "warning", "groupCommentBalance", line, f"group `{name}` in {scope} has no matching endGroup")


def lint_duplicate_literals(program: ProgramFacts, diags: List[Diagnostic]) -> None:
    if "capturedOutputReplay" in program.modes:
        return

    string_values: Dict[str, ConstFact] = {}
    for const in program.consts.values():
        if resolve_type(program, const.type_name) != "String":
            continue
        existing = string_values.get(const.value)
        if existing:
            add_diag(
                diags,
                "warning",
                "duplicatedDomainLiteral",
                const.line,
                f"const `{const.name}` repeats the string literal already held by `{existing.name}`",
                const.line.arg_column(0),
            )
        else:
            string_values[const.value] = const


def lint_abstractions(program: ProgramFacts, diags: List[Diagnostic]) -> None:
    for abstraction in program.abstractions.values():
        if abstraction.kind == "operation":
            continue
        if abstraction.kind not in CONTRACT_HEAVY_KINDS:
            continue
        if "purpose" not in program.hard_metadata.get(abstraction.name, set()):
            add_diag(
                diags,
                "warning",
                "missingPurpose",
                abstraction.line,
                f"{abstraction.kind} `{abstraction.name}` needs a purpose line to justify the abstraction",
                abstraction.line.arg_column(0),
            )


def lint_operation(program: ProgramFacts, operation: OperationFact, diags: List[Diagnostic]) -> None:
    calls: Dict[str, CallFact] = {}
    labels: Dict[str, SourceLine] = {}
    label_refs: List[Tuple[str, SourceLine, str]] = []
    branch_error_targets: Dict[str, List[Tuple[str, SourceLine]]] = {}
    start_groups: Set[str] = set()
    awaited_groups: Set[str] = set()
    deferred_lines: List[SourceLine] = []
    bind_sources: Dict[str, str] = {}
    returned_values: List[Tuple[str, SourceLine]] = []

    has_purpose = False
    has_output = False
    has_memory = False
    has_async = False
    has_return = False
    has_return_error = False
    output_tokens: List[str] = []
    effect_tuples: Set[Tuple[str, str]] = set()
    effect_lines: Dict[Tuple[str, str], SourceLine] = {}
    actual_effects: Dict[Tuple[str, str], List[SourceLine]] = {}
    used_capabilities: Set[str] = set()
    use_capability_lines: Dict[str, SourceLine] = {}
    symbol_types: Dict[str, str] = {}
    literal_values: Dict[str, str] = {}
    invariant_texts: List[str] = []
    operation_contract_texts: List[str] = []
    fixed_offset_lines: List[SourceLine] = []
    scalar_assignment_checks: List[Tuple[str, str, SourceLine]] = []
    uses_console_write = False

    for line in operation.lines:
        if is_comment(line) or not line.tokens:
            continue

        verb = line.verb
        args = line.args

        if verb == "input" and len(args) >= 3 and args[0] == operation.name:
            symbol_types[args[1]] = args[2]
        elif verb == "const" and len(args) >= 2:
            symbol_types[args[0]] = args[1]
            if len(args) >= 3:
                literal_values[args[0]] = args[2]
        elif verb == "storage" and len(args) >= 4:
            symbol_types[args[2]] = args[3]
            if len(args) >= 5:
                literal_values[args[2]] = args[4]
            if (
                len(args) >= 5
                and (args[2].endswith("ValueOffset") or args[2].endswith("FieldOffset"))
                and re.fullmatch(r"-?\d+", args[4])
            ):
                fixed_offset_lines.append(line)

        if verb == "purpose" and args and args[0] == operation.name:
            has_purpose = True
            if len(args) >= 2:
                operation_contract_texts.append(args[1])
        elif verb == "invariant" and args and args[0] == operation.name:
            if len(args) >= 2:
                invariant_texts.append(args[1])
                operation_contract_texts.append(args[1])
        elif verb in {"guarantee", "warning", "failure", "security", "timing", "observability"} and args and args[0] == operation.name:
            if len(args) >= 2:
                operation_contract_texts.append(args[1])
        elif verb == "output" and args and args[0] == operation.name:
            has_output = True
            output_tokens = args[1:]
        elif verb == "memory" and args and args[0] == operation.name:
            has_memory = True
        elif verb in {"memoryHeap", "memoryArena", "memoryStackLimit"} and args and args[0] == operation.name:
            has_memory = True
        elif verb == "async" and args and args[0] == operation.name:
            has_async = True
        elif verb == "effect" and len(args) >= 3 and args[0] == operation.name:
            effect_tuple = (args[1], args[2])
            effect_tuples.add(effect_tuple)
            effect_lines.setdefault(effect_tuple, line)
        elif verb == "useCapability" and len(args) >= 2 and args[0] == operation.name:
            used_capabilities.add(args[1])
            use_capability_lines[args[1]] = line

        if verb == "label" and args:
            label = args[0]
            if label in labels:
                add_diag(diags, "error", "duplicateLabel", line, f"label `{label}` is already declared", line.arg_column(0))
            labels[label] = line
        elif verb == "branch" and args:
            label_refs.append((args[0], line, "branch"))
        elif verb == "branchIf" and len(args) >= 2:
            label_refs.append((args[1], line, "branchIf"))
            if len(args) >= 3:
                label_refs.append((args[2], line, "branchIf false leg"))
                add_diag(diags, "info", "legacyBranchIf", line, "prefer single-target branchIf plus a following branch")
        elif verb == "branchIfError" and len(args) >= 2:
            call_name = args[0]
            label = args[1]
            label_refs.append((label, line, "branchIfError"))
            branch_error_targets.setdefault(label, []).append((call_name, line))
            if not failure_label_name_is_clear(label):
                add_diag(diags, "warning", "roleSuffixMismatch", line, f"failure label `{label}` should end with Failed or a past-tense -ed suffix", line.arg_column(1))
        elif verb in {"returnOk", "returnError", "returnValue"}:
            has_return = True
            if verb == "returnError":
                has_return_error = True
            if verb == "returnValue" and args:
                returned_values.append((args[0], line))

        if verb == "call" and len(args) >= 2:
            call_name, target = args[0], args[1]
            calls[call_name] = CallFact(call_name, target, line)
            if not call_name.endswith("Call"):
                add_diag(diags, "warning", "vagueCallName", line, f"call object `{call_name}` should end with Call", line.arg_column(0))
            if target in CONSOLE_WRITE_TARGETS:
                uses_console_write = True
            implied_effect = HTTP_CALL_TARGET_EFFECTS.get(target)
            if implied_effect:
                actual_effects.setdefault(implied_effect, []).append(line)
        elif verb == "arg" and len(args) >= 1:
            call = calls.get(args[0])
            if call:
                call.arg_lines.append(line)
            else:
                add_diag(diags, "error", "unknownCallReference", line, f"arg references unknown call `{args[0]}`", line.arg_column(0))
        elif verb == "run" and args:
            call = calls.get(args[0])
            if call:
                call.run_lines.append(line)
            else:
                add_diag(diags, "error", "unknownCallReference", line, f"run references unknown call `{args[0]}`", line.arg_column(0))
        elif verb == "start" and args:
            call = calls.get(args[0])
            if call:
                call.start_lines.append(line)
            else:
                add_diag(diags, "error", "unknownCallReference", line, f"start references unknown call `{args[0]}`", line.arg_column(0))
        elif verb == "await" and args:
            call = calls.get(args[0])
            if call:
                call.await_lines.append(line)
            else:
                add_diag(diags, "error", "unknownCallReference", line, f"await references unknown call `{args[0]}`", line.arg_column(0))
        elif verb == "bind" and len(args) >= 3:
            symbol_types[args[0]] = args[1]
            bind_sources[args[0]] = args[2]
            attach_call_line(calls, args[2], line, "bind", diags)
        elif verb == "bindOk" and len(args) >= 3:
            symbol_types[args[0]] = args[1]
            bind_sources[args[0]] = args[2]
            attach_call_line(calls, args[2], line, "bindOk", diags)
        elif verb == "bindError" and len(args) >= 3:
            symbol_types[args[0]] = args[1]
            if not args[0].endswith("Error"):
                add_diag(diags, "warning", "vagueErrorName", line, f"error binding `{args[0]}` should end with Error", line.arg_column(0))
            attach_call_line(calls, args[2], line, "bindError", diags)
        elif verb == "set" and len(args) >= 2:
            if args[0] == "local" and len(args) >= 3:
                scalar_assignment_checks.append((args[1], args[2], line))
            else:
                scalar_assignment_checks.append((args[0], args[1], line))
        elif verb == "ignoreOk" and args:
            attach_call_line(calls, args[0], line, "ignoreOk", diags)
        elif verb == "ignoreValue" and args:
            attach_call_line(calls, args[0], line, "ignoreValue", diags)
        elif verb == "branchIfError" and args:
            attach_call_line(calls, args[0], line, "branchIfError", diags)
        elif verb == "timeout" and args:
            call = calls.get(args[0])
            if call:
                call.timeout_lines.append(line)
            if len(args) >= 2 and re.fullmatch(r"-?\d+", args[1]):
                add_diag(diags, "warning", "rawTimeLiteral", line, "timeout uses a raw integer; declare a DurationMilliseconds const instead", line.arg_column(1))
        elif verb == "cancelOn" and args:
            call = calls.get(args[0])
            if call:
                call.cancel_lines.append(line)
        elif verb == "makeError" and args:
            if not args[0].endswith("Failure"):
                add_diag(diags, "warning", "vagueFailureName", line, f"failure value `{args[0]}` should end with Failure", line.arg_column(0))
        elif verb == "startInGroup" and len(args) >= 2:
            call = calls.get(args[0])
            if call:
                call.group_start_lines.append(line)
            start_groups.add(args[1])
        elif verb == "awaitGroup" and args:
            awaited_groups.add(args[0])
        elif verb in {"defer", "deferLog", "deferAwaitLog", "deferWhenExitLog"}:
            deferred_lines.append(line)

    if not has_purpose:
        add_diag(diags, "warning", "missingPurpose", operation.line, f"operation `{operation.name}` needs a purpose line", operation.line.arg_column(0))
    if not has_output:
        add_diag(diags, "warning", "missingOutput", operation.line, f"operation `{operation.name}` should declare output")
    if not has_memory:
        add_diag(diags, "warning", "missingMemory", operation.line, f"operation `{operation.name}` should declare memory behavior")
    if not has_async:
        add_diag(diags, "warning", "missingAsync", operation.line, f"operation `{operation.name}` should declare async yes|no")
    operation_contract_text = " ".join(operation_contract_texts).lower()
    operation_is_nonreturning = "does not return" in operation_contract_text or "terminates the process" in operation_contract_text
    if not has_return and not operation_is_nonreturning:
        add_diag(diags, "warning", "missingReturn", operation.line, f"operation `{operation.name}` has no explicit return line")
    if len(output_tokens) >= 3 and output_tokens[0] == "Result" and output_tokens[2] == "Void" and not has_return_error:
        add_diag(
            diags,
            "warning",
            "resultVoidErrorWithoutFailurePath",
            operation.line,
            (
                f"operation `{operation.name}` declares `Result {output_tokens[1]} Void` but has no "
                "returnError path; use a plain output type for infallible helpers"
            ),
            operation.line.arg_column(0),
        )
    if uses_console_write and ("write", "console.stdout") not in effect_tuples:
        add_diag(diags, "warning", "missingEffectDeclaration", operation.line, f"operation `{operation.name}` writes console output but lacks `effect {operation.name} write console.stdout`")

    lint_nullable_http_value_flow(operation, calls, bind_sources, operation_contract_text, diags)
    lint_effect_capability_coverage(program, operation, effect_tuples, effect_lines, used_capabilities, use_capability_lines, diags)
    lint_http_effect_precision(operation, effect_tuples, effect_lines, actual_effects, diags)
    lint_filesystem_effect_precision(program, operation, effect_tuples, effect_lines, calls, literal_values, diags)
    lint_printf_format_widths(calls, symbol_types, literal_values, diags)
    lint_fixed_offset_contract(operation, fixed_offset_lines, invariant_texts, diags)
    lint_scalar_width_drift(symbol_types, scalar_assignment_checks, diags)

    for label, ref_line, kind in label_refs:
        if label not in labels:
            add_diag(diags, "error", "branchTargetExists", ref_line, f"{kind} references undeclared label `{label}`")

    if "capturedOutputReplay" not in program.modes:
        for label, callers in branch_error_targets.items():
            distinct_calls = {call_name for call_name, _line in callers}
            if len(distinct_calls) > 1:
                if failure_label_name_is_clear(label):
                    continue
                first_line = callers[0][1]
                add_diag(diags, "warning", "failureLabelAggregation", first_line, f"label `{label}` receives {len(distinct_calls)} distinct branchIfError sources; split labels to preserve failure cause")

    for call in calls.values():
        lint_call(call, diags)

    lint_raw_libc_return_escape(operation, calls, bind_sources, returned_values, operation_contract_texts, diags)

    for group_name in sorted(start_groups - awaited_groups):
        line = next((call_line for call in calls.values() for call_line in call.group_start_lines if len(call_line.args) >= 2 and call_line.args[1] == group_name), operation.line)
        add_diag(diags, "warning", "unawaitedTaskGroup", line, f"task group `{group_name}` is started but not awaited")

    lint_resource_cleanup(calls, deferred_lines, diags)
    lint_terminal_state_cleanup(operation, calls, deferred_lines, diags)


def access_action_covers(capability_access: str, effect_action: str) -> bool:
    if capability_access == effect_action:
        return True
    return capability_access == "readWrite" and effect_action in {"read", "write"}


def lint_effect_capability_coverage(
    program: ProgramFacts,
    operation: OperationFact,
    effect_tuples: Set[Tuple[str, str]],
    effect_lines: Dict[Tuple[str, str], SourceLine],
    used_capabilities: Set[str],
    use_capability_lines: Dict[str, SourceLine],
    diags: List[Diagnostic],
) -> None:
    available_capabilities = dict(program.capabilities)
    available_capabilities.update(load_imported_capabilities(program))

    if not available_capabilities and not used_capabilities:
        return

    used_capability_facts = [
        available_capabilities[capability_name]
        for capability_name in used_capabilities
        if capability_name in available_capabilities
    ]

    for capability_name in sorted(used_capabilities - set(available_capabilities)):
        line = use_capability_lines.get(capability_name, operation.line)
        add_diag(
            diags,
            "warning",
            "unknownCapabilityReference",
            line,
            (
                f"operation `{operation.name}` uses capability `{capability_name}`, "
                "but no local or resolved imported capability declaration defines it"
            ),
            line.arg_column(1),
        )

    for action, effect_path in sorted(effect_tuples):
        if any(capability_authorizes(capability, action, effect_path) for capability in used_capability_facts):
            continue

        candidate = next(
            (
                capability.name
                for capability in available_capabilities.values()
                if access_action_covers(capability.access, action) and effect_path_covers(capability.effect_path, effect_path)
            ),
            None,
        )
        fix_hint = (
            f"add `useCapability {operation.name} {candidate}`"
            if candidate
            else f"declare a capability for `{effect_path} {action}` and use it in `{operation.name}`"
        )
        effect_line = effect_lines.get((action, effect_path), operation.line)
        add_diag(
            diags,
            "warning",
            "missingCapabilityUse",
            effect_line,
            (
                f"operation `{operation.name}` declares effect `{action} {effect_path}` "
                f"without an authorizing used capability; {fix_hint}"
            ),
            effect_line.arg_column(1),
        )


def load_imported_capabilities(program: ProgramFacts) -> Dict[str, CapabilityFact]:
    imported: Dict[str, CapabilityFact] = {}
    if not program.imports:
        return imported

    visited: Set[Path] = set()
    for module_name in sorted(program.imports):
        module_path = resolve_import_module_path(program.path, module_name)
        if module_path is None:
            continue
        collect_capabilities_from_file(module_path, imported, visited)
    return imported


def resolve_import_module_path(source_path: Path, dotted: str) -> Optional[Path]:
    rel_base = Path(*dotted.split("."))
    candidate_roots: List[Path] = [source_path.parent]

    for parent in [source_path.parent, *source_path.parents]:
        if (parent / "stdlib_sem").is_dir():
            candidate_roots.extend([parent / "stdlib_sem", parent])
            break

    semantic_root = Path(__file__).resolve().parents[1]
    candidate_roots.extend([semantic_root / "stdlib_sem", semantic_root])

    seen_roots: Set[Path] = set()
    for root in candidate_roots:
        resolved_root = root.resolve()
        if resolved_root in seen_roots:
            continue
        seen_roots.add(resolved_root)
        for suffix in SUPPORTED_SOURCE_SUFFIXES:
            candidate = resolved_root / rel_base.with_suffix(suffix)
            if candidate.is_file():
                return candidate
    return None


def collect_capabilities_from_file(path: Path, imported: Dict[str, CapabilityFact], visited: Set[Path]) -> None:
    resolved_path = path.resolve()
    if resolved_path in visited:
        return
    visited.add(resolved_path)

    try:
        raw_lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return

    for line_number, raw in enumerate(raw_lines, start=1):
        line = SourceLine(path=path, number=line_number, raw=raw, tokens=tokenize_line(raw))
        if not line.tokens or is_comment(line):
            continue
        if line.verb == "capability" and len(line.args) >= 3:
            imported[line.args[0]] = CapabilityFact(line.args[0], line.args[1], line.args[2], line)
        elif line.verb == "importModule" and line.args:
            nested_path = resolve_import_module_path(path, line.args[0])
            if nested_path is not None:
                collect_capabilities_from_file(nested_path, imported, visited)


def lint_http_effect_precision(
    operation: OperationFact,
    effect_tuples: Set[Tuple[str, str]],
    effect_lines: Dict[Tuple[str, str], SourceLine],
    actual_effects: Dict[Tuple[str, str], List[SourceLine]],
    diags: List[Diagnostic],
) -> None:
    for (action, effect_path), lines in sorted(actual_effects.items()):
        if declared_effect_covers_actual(effect_tuples, action, effect_path):
            continue
        add_diag(
            diags,
            "warning",
            "missingEffectDeclaration",
            lines[0],
            (
                f"operation `{operation.name}` calls a native HTTP target that performs "
                f"`{action} {effect_path}` but does not declare a matching effect"
            ),
            lines[0].arg_column(1),
        )

    for action, effect_path in sorted(effect_tuples):
        if action != "read" or not (effect_path == "http.request" or effect_path.startswith("http.request.")):
            continue
        if actual_effect_satisfies_declared(actual_effects, action, effect_path):
            continue
        effect_line = effect_lines.get((action, effect_path), operation.line)
        add_diag(
            diags,
            "warning",
            "overdeclaredEffect",
            effect_line,
            (
                f"operation `{operation.name}` declares `{action} {effect_path}` but its body "
                "does not call a matching HTTP request reader such as `http.requestMethod` or `http.requestPath`"
            ),
            effect_line.arg_column(1),
        )


def operation_declared_effects(operation: OperationFact) -> Set[Tuple[str, str]]:
    effects: Set[Tuple[str, str]] = set()
    for line in operation.lines:
        if line.verb == "effect" and len(line.args) >= 3 and line.args[0] == operation.name:
            effects.add((line.args[1], line.args[2]))
    return effects


def resolve_literal_value(token: str, literal_values: Dict[str, str]) -> str:
    return literal_values.get(token, token).strip('"')


def looks_like_fopen_mode(mode: str) -> bool:
    return bool(mode) and mode[0] in {"r", "w", "a"} and all(char in {"b", "+"} for char in mode[1:])


def call_arg_value(call: CallFact, arg_name: str) -> Optional[str]:
    for arg_line in call.arg_lines:
        if len(arg_line.args) >= 3 and arg_line.args[1] == arg_name:
            return arg_line.args[2]
    return None


def fopen_mode_effects(call: CallFact, literal_values: Dict[str, str]) -> List[Tuple[str, str]]:
    mode_token = call_arg_value(call, "mode")
    if mode_token is None:
        return [("open", "file"), ("read", "filesystem"), ("write", "filesystem")]

    mode = resolve_literal_value(mode_token, literal_values).lower()
    if not looks_like_fopen_mode(mode):
        return [("open", "file"), ("read", "filesystem"), ("write", "filesystem")]

    effects: List[Tuple[str, str]] = [("open", "file")]
    if mode[0] == "r" or "+" in mode:
        effects.append(("read", "filesystem"))
    if mode[0] in {"w", "a"} or "+" in mode:
        effects.append(("write", "filesystem"))
    return effects


def filesystem_actual_effects(
    program: ProgramFacts,
    calls: Dict[str, CallFact],
    literal_values: Dict[str, str],
) -> Dict[Tuple[str, str], List[SourceLine]]:
    actual_effects: Dict[Tuple[str, str], List[SourceLine]] = {}
    read_targets = {"c.fread", "c.fgets"}
    write_targets = {"c.fwrite", "c.fprintf", "c.fputs", "c.fputc", "c.putc"}

    for call in calls.values():
        if call.target in program.operations:
            for action, effect_path in operation_declared_effects(program.operations[call.target]):
                if (
                    (effect_path == "filesystem" and action in {"read", "write"})
                    or (effect_path == "file" and action in {"open", "close"})
                ):
                    actual_effects.setdefault((action, effect_path), []).append(call.line)
            continue

        if call.target in {"c.fopen", "c.freopen"}:
            for effect in fopen_mode_effects(call, literal_values):
                actual_effects.setdefault(effect, []).append(call.line)
            continue

        if call.target in read_targets:
            actual_effects.setdefault(("read", "filesystem"), []).append(call.line)
        elif call.target in write_targets:
            actual_effects.setdefault(("write", "filesystem"), []).append(call.line)
        elif call.target == "c.fclose":
            actual_effects.setdefault(("close", "file"), []).append(call.line)

    return actual_effects


def lint_filesystem_effect_precision(
    program: ProgramFacts,
    operation: OperationFact,
    effect_tuples: Set[Tuple[str, str]],
    effect_lines: Dict[Tuple[str, str], SourceLine],
    calls: Dict[str, CallFact],
    literal_values: Dict[str, str],
    diags: List[Diagnostic],
) -> None:
    actual_effects = filesystem_actual_effects(program, calls, literal_values)
    for (action, effect_path), lines in sorted(actual_effects.items()):
        if not (
            (effect_path == "filesystem" and action in {"read", "write"})
            or (effect_path == "file" and action in {"open", "close"})
        ):
            continue
        if declared_effect_covers_actual(effect_tuples, action, effect_path):
            continue
        add_diag(
            diags,
            "warning",
            "missingEffectDeclaration",
            lines[0],
            (
                f"operation `{operation.name}` performs `{action} {effect_path}` "
                "but does not declare a matching effect"
            ),
            lines[0].arg_column(1),
        )

    for action, effect_path in sorted(effect_tuples):
        if not (
            (effect_path == "filesystem" and action in {"read", "write"})
            or (effect_path == "file" and action in {"open", "close"})
        ):
            continue
        if actual_effect_satisfies_declared(actual_effects, action, effect_path):
            continue
        effect_line = effect_lines.get((action, effect_path), operation.line)
        add_diag(
            diags,
            "warning",
            "overAuthorizedEffect",
            effect_line,
            (
                f"operation `{operation.name}` declares `{action} {effect_path}` but its body "
                "does not justify that access through a matching file mode, file I/O call, or local operation call"
            ),
            effect_line.arg_column(1),
        )


def lint_fixed_offset_contract(
    operation: OperationFact,
    fixed_offset_lines: List[SourceLine],
    invariant_texts: List[str],
    diags: List[Diagnostic],
) -> None:
    if not fixed_offset_lines:
        return
    contract_text = " ".join(invariant_texts).lower()
    names_exact_format = (
        "exact" in contract_text
        and any(marker in contract_text for marker in ("format", "emitted", "producer", "schema", "object key order"))
    )
    names_fixed_offsets = "fixed" in contract_text and "offset" in contract_text
    if names_exact_format or names_fixed_offsets:
        return

    first_offset_line = fixed_offset_lines[0]
    add_diag(
        diags,
        "warning",
        "fixedOffsetParserContract",
        first_offset_line,
        (
            f"operation `{operation.name}` declares numeric `*Offset` constants but no invariant names "
            "the exact fixed format or producer shape it accepts"
        ),
        first_offset_line.arg_column(2),
    )


def lint_printf_format_widths(
    calls: Dict[str, CallFact],
    symbol_types: Dict[str, str],
    literal_values: Dict[str, str],
    diags: List[Diagnostic],
) -> None:
    printf_targets = {"c.printf", "c.fprintf", "c.sprintf", "c.snprintf"}
    narrow_integer_types = {"CSignedInt32", "CUnsignedInt32", "I32", "U32"}
    for call in calls.values():
        if call.target not in printf_targets:
            continue
        format_token = call_arg_value(call, "format")
        if not format_token:
            continue
        format_text = resolve_literal_value(format_token, literal_values)
        if "%lld" not in format_text and "%lli" not in format_text:
            continue
        for arg_line in call.arg_lines:
            if len(arg_line.args) < 3 or arg_line.args[1] in {"stream", "format", "buffer", "size"}:
                continue
            value_name = arg_line.args[2]
            value_type = symbol_types.get(value_name)
            if value_type not in narrow_integer_types:
                continue
            add_diag(
                diags,
                "warning",
                "printfFormatWidthMismatch",
                arg_line,
                (
                    f"`{call.target}` format uses a 64-bit integer conversion but argument "
                    f"`{value_name}` is `{value_type}`; widen explicitly or use a matching format"
                ),
                arg_line.arg_column(1),
            )


def lint_scalar_width_drift(
    symbol_types: Dict[str, str],
    scalar_assignment_checks: List[Tuple[str, str, SourceLine]],
    diags: List[Diagnostic],
) -> None:
    for target_name, source_name, line in scalar_assignment_checks:
        target_type = symbol_types.get(target_name)
        source_type = symbol_types.get(source_name)
        if not target_type or not source_type:
            continue
        target_width = INTEGER_WIDTH_TYPES.get(target_type)
        source_width = INTEGER_WIDTH_TYPES.get(source_type)
        if target_width is None or source_width is None or target_width == source_width:
            continue
        add_diag(
            diags,
            "warning",
            "implicitScalarWidthDrift",
            line,
            (
                f"`set` assigns `{source_name}` ({source_type}) to `{target_name}` ({target_type}); "
                "use matching scalar widths or an explicit widening/narrowing operation"
            ),
            line.arg_column(1 if line.args and line.args[0] == "local" else 0),
        )


def canonical_target_name(target: str) -> str:
    if target.startswith("c."):
        return target[2:]
    return target


def lint_raw_libc_return_escape(
    operation: OperationFact,
    calls: Dict[str, CallFact],
    bind_sources: Dict[str, str],
    returned_values: List[Tuple[str, SourceLine]],
    operation_contract_texts: List[str],
    diags: List[Diagnostic],
) -> None:
    contract_text = " ".join(operation_contract_texts).lower()
    raw_return_is_contractual = "libc" in contract_text and "return" in contract_text
    for returned_value, return_line in returned_values:
        call_name = bind_sources.get(returned_value)
        if call_name is None and returned_value in calls:
            call_name = returned_value
        if call_name is None:
            continue
        call = calls.get(call_name)
        if call is None:
            continue
        target_name = canonical_target_name(call.target)
        if target_name not in LIBC_POSITIVE_SUCCESS_TARGETS:
            continue
        if raw_return_is_contractual:
            continue
        add_diag(
            diags,
            "warning",
            "rawLibcReturnEscapesOperation",
            return_line,
            (
                f"operation `{operation.name}` returns `{returned_value}` from "
                f"`{call.target}`; this libc target returns a byte/count/raw status, "
                "not a canonical operation success value. Map success to an explicit "
                "zero/status value or use `Result` with typed failure."
            ),
            return_line.arg_column(0),
        )


def failure_label_name_is_clear(label: str) -> bool:
    if label.endswith("Failed") or label.endswith("ed"):
        return True
    return any(marker in label for marker in ("Failed", "Failure", "Error"))


def attach_call_line(calls: Dict[str, CallFact], call_name: str, line: SourceLine, kind: str, diags: List[Diagnostic]) -> None:
    call = calls.get(call_name)
    if not call:
        add_diag(diags, "error", "unknownCallReference", line, f"{kind} references unknown call `{call_name}`", line.arg_column(2 if kind in {"bind", "bindOk", "bindError"} else 0))
        return
    if kind == "bind":
        call.bind_lines.append(line)
    elif kind == "bindOk":
        call.bind_ok_lines.append(line)
    elif kind == "bindError":
        call.bind_error_lines.append(line)
    elif kind == "ignoreOk":
        call.ignore_ok_lines.append(line)
    elif kind == "ignoreValue":
        call.ignore_value_lines.append(line)
    elif kind == "branchIfError":
        call.branch_error_lines.append(line)


def lint_call(call: CallFact, diags: List[Diagnostic]) -> None:
    target_kind = classify_target(call.target)

    if not (call.run_lines or call.start_lines or call.group_start_lines):
        add_diag(diags, "warning", "callNotExecuted", call.line, f"call `{call.name}` is declared but never run, started, or started in a group")

    if len(call.run_lines) > 1:
        add_diag(diags, "warning", "callRunMultipleTimes", call.run_lines[1], f"call `{call.name}` is run more than once")

    if call.bind_error_lines and not call.branch_error_lines:
        add_diag(diags, "warning", "unbranchedFailure", call.line, f"call `{call.name}` binds an error but has no branchIfError")

    if call.bind_error_lines and not (call.bind_ok_lines or call.ignore_ok_lines or call.bind_lines):
        add_diag(diags, "warning", "missingSuccessDisposition", call.line, f"fallible call `{call.name}` binds an error but does not bindOk or ignoreOk the success value")

    if target_kind == "consoleWrite":
        if not call.ignore_ok_lines:
            add_diag(diags, "warning", "missingSuccessDisposition", call.line, f"console write call `{call.name}` should explicitly ignoreOk its Void success")
        if not call.bind_error_lines:
            add_diag(diags, "warning", "hiddenFailure", call.line, f"console write call `{call.name}` should bindError")
        if not call.branch_error_lines:
            add_diag(diags, "warning", "hiddenFailure", call.line, f"console write call `{call.name}` should branchIfError")

    if target_kind == "infallibleMath":
        if call.bind_ok_lines or call.bind_error_lines or call.ignore_ok_lines:
            add_diag(diags, "warning", "infallibleCallUsesFallibleFlow", call.line, f"infallible math/domain call `{call.name}` should use bind or ignoreValue, not bindOk/bindError/ignoreOk")

    if target_kind == "fallibleMath":
        if not call.bind_ok_lines:
            add_diag(diags, "warning", "missingSuccessDisposition", call.line, f"fallible checked math call `{call.name}` should bindOk")
        if not call.bind_error_lines:
            add_diag(diags, "warning", "hiddenFailure", call.line, f"fallible checked math call `{call.name}` should bindError")
        if not call.branch_error_lines:
            add_diag(diags, "warning", "hiddenFailure", call.line, f"fallible checked math call `{call.name}` should branchIfError")

    if call.start_lines and not (call.await_lines or call.group_start_lines):
        add_diag(diags, "warning", "unawaitedAsyncCall", call.start_lines[0], f"started call `{call.name}` is not awaited or attached to a task group")

    if call.await_lines and not call.timeout_lines:
        add_diag(diags, "warning", "unboundedAsyncCall", call.await_lines[0], f"awaited call `{call.name}` has no timeout line")

    if call.await_lines and not call.cancel_lines:
        add_diag(diags, "warning", "uncancellableAsyncCall", call.await_lines[0], f"awaited call `{call.name}` has no cancelOn line")


def lint_resource_cleanup(calls: Dict[str, CallFact], deferred_lines: List[SourceLine], diags: List[Diagnostic]) -> None:
    defer_text = "\n".join(line.raw for line in deferred_lines)
    for call in calls.values():
        target_lower = call.target.lower()
        if not any(marker in target_lower for marker in ("open", "connect", "acquire")):
            continue
        if any(marker in target_lower for marker in ("response", "encode")):
            continue
        if call.name in defer_text or ("close" in defer_text.lower() and deferred_lines):
            continue
        if resource_call_has_explicit_close(call, calls):
            continue
        add_diag(diags, "info", "cleanupNotProven", call.line, f"resource-like call `{call.name}` may need a defer/deferAwaitLog cleanup next to acquisition")


def lint_terminal_state_cleanup(operation: OperationFact, calls: Dict[str, CallFact], deferred_lines: List[SourceLine], diags: List[Diagnostic]) -> None:
    hide_calls = [call for call in calls.values() if call.target in {"hideCursor", "terminal.hideCursor"}]
    if not hide_calls:
        return
    has_show_call = any(call.target in {"showCursor", "terminal.showCursor"} for call in calls.values())
    has_show_defer = any(
        len(line.args) >= 2 and line.args[1] in {"showCursor", "terminal.showCursor"}
        for line in deferred_lines
    )
    if has_show_call or has_show_defer:
        return
    first_hide_call = hide_calls[0]
    add_diag(
        diags,
        "warning",
        "terminalStateCleanup.missing",
        first_hide_call.line,
        (
            f"operation `{operation.name}` calls `{first_hide_call.target}` without a matching "
            "`showCursor`/`terminal.showCursor` cleanup call"
        ),
        first_hide_call.line.arg_column(1),
    )


def resource_call_has_explicit_close(resource_call: CallFact, calls: Dict[str, CallFact]) -> bool:
    handle_names = {
        bind_line.args[0]
        for bind_line in [*resource_call.bind_lines, *resource_call.bind_ok_lines]
        if bind_line.args
    }
    if not handle_names:
        return False

    for close_call in calls.values():
        if "close" not in close_call.target.lower():
            continue
        if not close_call.run_lines:
            continue
        for arg_line in close_call.arg_lines:
            if len(arg_line.args) >= 3 and arg_line.args[2] in handle_names:
                return True
    return False


def classify_target(target: str) -> str:
    canonical = {
        "console.writeInteger": "console.writeIntegerLine",
        "math.subI64": "math.subtractI64",
        "math.mulI64": "math.multiplyI64",
        "math.divI64": "math.divideI64",
        "math.modI64": "math.moduloI64",
        "math.eqI64": "math.equalI64",
        "math.neI64": "math.notEqualI64",
        "math.ltI64": "math.lessThanI64",
        "math.leI64": "math.lessThanOrEqualI64",
        "math.gtI64": "math.greaterThanI64",
        "math.geI64": "math.greaterThanOrEqualI64",
    }.get(target, target)

    if canonical in CONSOLE_WRITE_TARGETS:
        return "consoleWrite"
    if canonical == "math.checkedMultiplyI64":
        return "fallibleMath"
    if canonical.startswith("math."):
        return "infallibleMath"
    domain_method = domain_method_name(canonical)
    if domain_method in FALLIBLE_DOMAIN_METHODS:
        return "fallibleMath"
    if domain_method in INFALLIBLE_DOMAIN_METHODS:
        return "infallibleMath"
    return "external"


def domain_method_name(target: str) -> Optional[str]:
    if "." not in target:
        return None
    left, right = target.split(".", 1)
    if left and left[0].isupper():
        return right
    return None


def is_pascal_case(text: str) -> bool:
    return bool(re.fullmatch(r"[A-Z][A-Za-z0-9]*", text))


def is_camel_case(text: str) -> bool:
    return bool(re.fullmatch(r"[a-z][A-Za-z0-9]*", text))


def collect_paths(paths: Sequence[str]) -> List[Path]:
    collected: List[Path] = []
    for raw_path in paths:
        path = Path(raw_path)
        if path.is_dir():
            for suffix in sorted(SUPPORTED_SOURCE_SUFFIXES):
                collected.extend(sorted(path.rglob(f"*{suffix}")))
        elif path.is_file():
            if path.suffix in SUPPORTED_SOURCE_SUFFIXES:
                collected.append(path)
        else:
            matches = sorted(Path().glob(raw_path))
            collected.extend(match for match in matches if match.is_file() and match.suffix in SUPPORTED_SOURCE_SUFFIXES)
    return collected


def format_text(diags: Sequence[Diagnostic], root: Path) -> str:
    lines = []
    for diag in diags:
        try:
            display_path = diag.path.resolve().relative_to(root.resolve())
        except ValueError:
            display_path = diag.path
        lines.append(
            f"{display_path}:{diag.line}:{diag.column}: {diag.severity} {diag.rule}: {diag.message}"
        )
    return "\n".join(lines)


def should_fail(diags: Sequence[Diagnostic], fail_on: str) -> bool:
    if fail_on == "none":
        return False
    threshold = SEVERITY_ORDER[fail_on]
    return any(SEVERITY_ORDER[diag.severity] >= threshold for diag in diags)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="semlint",
        description=f"Lint SemanticScript .sscript and .sem files. v{__version__}",
    )
    parser.add_argument("--version", action="version",
                        version=f"semlint {__version__}")
    parser.add_argument("paths", nargs="+", help="SemanticScript files, directories, or glob patterns.")
    parser.add_argument("--format", choices=("text", "json"), default="text", help="Diagnostic output format.")
    parser.add_argument("--fail-on", choices=("error", "warning", "info", "none"), default="error", help="Minimum severity that returns a non-zero exit code.")
    parser.add_argument("--strict", action="store_true", help="Alias for --fail-on warning.")
    parser.add_argument("--summary", action="store_true", help="Print a severity count summary after text diagnostics.")
    args = parser.parse_args(argv)

    fail_on = "warning" if args.strict else args.fail_on
    paths = collect_paths(args.paths)
    if not paths:
        print("semlint: no .sscript or .sem files matched", file=sys.stderr)
        return 2

    all_diags: List[Diagnostic] = []
    for path in paths:
        try:
            all_diags.extend(lint_program(parse_file(path)))
        except OSError as exc:
            all_diags.append(Diagnostic("error", "fileReadFailed", path, 0, 0, str(exc)))

    if args.format == "json":
        print(json.dumps([diag.to_json() for diag in all_diags], indent=2))
    else:
        text = format_text(all_diags, Path.cwd())
        if text:
            print(text)
        if args.summary:
            counts = {"error": 0, "warning": 0, "info": 0}
            for diag in all_diags:
                counts[diag.severity] += 1
            print(f"\nsummary: {counts['error']} error(s), {counts['warning']} warning(s), {counts['info']} info diagnostic(s)")

    return 1 if should_fail(all_diags, fail_on) else 0


if __name__ == "__main__":
    raise SystemExit(main())
