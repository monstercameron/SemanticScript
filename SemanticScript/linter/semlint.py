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
    "mutex", "shared", "channel", "const", "var", "testCovers",
}

CONTEXT_VERBS = {
    "input", "output", "effect", "memory", "async", "purpose", "invariant",
    "warning", "guarantee", "failure", "security", "timing", "observability",
}

ACTION_VERBS = {
    "set", "call", "arg", "timeout", "cancelOn", "run", "start", "await",
    "bind", "bindOk", "bindError", "ignoreOk", "ignoreValue", "makeError",
    "taskGroup", "startInGroup", "awaitGroup", "bindGroupError", "defer",
    "deferLog", "deferAwaitLog", "deferWhenExitLog", "new", "fieldGet",
    "fieldSet", "send", "receive", "lock", "unlock", "select", "selectCase",
    "runSelect", "useRetry", "useCapability",
}

CONTROL_VERBS = {
    "label", "branch", "branchIf", "branchIfError", "branchIfGroupError",
    "branchIfChannelClosed", "branchSelected", "returnOk", "returnError",
    "returnValue",
}

KNOWN_VERBS = DECLARATION_VERBS | CONTEXT_VERBS | ACTION_VERBS | CONTROL_VERBS

BODY_VERBS = CONTEXT_VERBS | ACTION_VERBS | CONTROL_VERBS | {"const", "var", "importModule"}

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

CONTRACT_HEAVY_KINDS = {
    "record", "codec", "jsonCodec", "validator", "mapper", "adapter",
    "boundary", "policy", "errorPolicy", "retryPolicy", "timeoutBudget",
    "resource", "capability", "webServer",
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
    "async": 2,
    "purpose": 2,
    "invariant": 2,
    "warning": 2,
    "const": 3,
    "var": 3,
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
            elif verb == "const" and len(args) >= 3:
                program.consts[args[0]] = ConstFact(args[0], args[1], args[2], line)
            elif verb == "type" and len(args) >= 2:
                program.type_aliases[args[0]] = args[1]
            elif verb.startswith("type") and len(args) >= 1 and verb != "type":
                program.type_metadata.setdefault(args[0], set()).add(verb)
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

    lint_line_shape(program, diags)
    lint_group_balance(program.module_group_anchors, diags, "module")
    lint_duplicate_literals(program, diags)
    lint_abstractions(program, diags)

    for operation in program.operations.values():
        lint_group_balance(operation.group_anchors, diags, f"operation {operation.name}")
        lint_operation(program, operation, diags)

    return sorted(diags, key=lambda item: (str(item.path), item.line, item.column, item.rule))


def lint_line_shape(program: ProgramFacts, diags: List[Diagnostic]) -> None:
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

    has_purpose = False
    has_output = False
    has_memory = False
    has_async = False
    has_return = False
    effect_tuples: Set[Tuple[str, str]] = set()
    uses_console_write = False

    for line in operation.lines:
        if is_comment(line) or not line.tokens:
            continue

        verb = line.verb
        args = line.args

        if verb == "purpose" and args and args[0] == operation.name:
            has_purpose = True
        elif verb == "output" and args and args[0] == operation.name:
            has_output = True
        elif verb == "memory" and args and args[0] == operation.name:
            has_memory = True
        elif verb == "async" and args and args[0] == operation.name:
            has_async = True
        elif verb == "effect" and len(args) >= 3 and args[0] == operation.name:
            effect_tuples.add((args[1], args[2]))

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
            if not (label.endswith("Failed") or label.endswith("ed")):
                add_diag(diags, "warning", "roleSuffixMismatch", line, f"failure label `{label}` should end with Failed or a past-tense -ed suffix", line.arg_column(1))
        elif verb in {"returnOk", "returnError", "returnValue"}:
            has_return = True

        if verb == "call" and len(args) >= 2:
            call_name, target = args[0], args[1]
            calls[call_name] = CallFact(call_name, target, line)
            if not call_name.endswith("Call"):
                add_diag(diags, "warning", "vagueCallName", line, f"call object `{call_name}` should end with Call", line.arg_column(0))
            if target in CONSOLE_WRITE_TARGETS:
                uses_console_write = True
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
            attach_call_line(calls, args[2], line, "bind", diags)
        elif verb == "bindOk" and len(args) >= 3:
            attach_call_line(calls, args[2], line, "bindOk", diags)
        elif verb == "bindError" and len(args) >= 3:
            if not args[0].endswith("Error"):
                add_diag(diags, "warning", "vagueErrorName", line, f"error binding `{args[0]}` should end with Error", line.arg_column(0))
            attach_call_line(calls, args[2], line, "bindError", diags)
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
    if not has_return:
        add_diag(diags, "warning", "missingReturn", operation.line, f"operation `{operation.name}` has no explicit return line")
    if uses_console_write and ("write", "console.stdout") not in effect_tuples:
        add_diag(diags, "warning", "missingEffectDeclaration", operation.line, f"operation `{operation.name}` writes console output but lacks `effect {operation.name} write console.stdout`")

    for label, ref_line, kind in label_refs:
        if label not in labels:
            add_diag(diags, "error", "branchTargetExists", ref_line, f"{kind} references undeclared label `{label}`")

    if "capturedOutputReplay" not in program.modes:
        for label, callers in branch_error_targets.items():
            distinct_calls = {call_name for call_name, _line in callers}
            if len(distinct_calls) > 1:
                first_line = callers[0][1]
                add_diag(diags, "warning", "failureLabelAggregation", first_line, f"label `{label}` receives {len(distinct_calls)} distinct branchIfError sources; split labels to preserve failure cause")

    for call in calls.values():
        lint_call(call, diags)

    for group_name in sorted(start_groups - awaited_groups):
        line = next((call_line for call in calls.values() for call_line in call.group_start_lines if len(call_line.args) >= 2 and call_line.args[1] == group_name), operation.line)
        add_diag(diags, "warning", "unawaitedTaskGroup", line, f"task group `{group_name}` is started but not awaited")

    lint_resource_cleanup(calls, deferred_lines, diags)


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

    if call.bind_error_lines and not (call.bind_ok_lines or call.ignore_ok_lines):
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
        add_diag(diags, "info", "cleanupNotProven", call.line, f"resource-like call `{call.name}` may need a defer/deferAwaitLog cleanup next to acquisition")


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
