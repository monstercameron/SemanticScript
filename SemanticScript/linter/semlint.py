#!/usr/bin/env python3
"""Refined SemanticScript linter — design playground.

Parallel implementation of the linter that demonstrates the structured-
diagnostic architecture:

  * Tiered codes (T0 parse, T1 spec, T2 lowering, T3 refinement, T4 style)
  * Structured subject/gap fields (no prose-disguised-as-data)
  * Citations from narrative attachments (purpose/invariant/warning/
    security/timing/observability/# rationale:) — diagnostics CITE the
    author's stated intent rather than restating gaps in English
  * Fix candidates with evidence pointers and auto-applicable flags
  * Four output formats: human (block render), json (full), agent
    (priority queue), sem-record (proposed SemanticScript-form, see header note)

The existing semlint.py stays as the stable surface. This file is the
playground for evolving the diagnostic schema before migration.
"""

from __future__ import annotations

import argparse
import io
import json
import os
import sys

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        sys.stderr.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except (AttributeError, io.UnsupportedOperation):
        pass

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Set, Tuple

__version__ = "0.3.0"


# ==========================================================================
# Shared parser surface
# ==========================================================================
# Tokenizer, line shape, and program-facts dataclasses. This block was the
# legacy `semlint.py` schema, kept here so the canonical `semlint` linter
# has one self-contained file. The previous parallel implementation has
# been fully merged into this module.

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
    tokens: List["Token"]

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
class BaseCapabilityFact:
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
class ImportModuleFact:
    module_name: str
    alias: Optional[str]
    line: SourceLine
    syntax: str


@dataclass
class SingularImportFact:
    kind: str
    local_name: str
    module_alias: str
    exported_name: str
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
    capabilities: Dict[str, BaseCapabilityFact] = field(default_factory=dict)
    routes: List[RouteFact] = field(default_factory=list)
    imports: Set[str] = field(default_factory=set)
    module_imports: List[ImportModuleFact] = field(default_factory=list)
    singular_imports: List[SingularImportFact] = field(default_factory=list)


BUILTIN_VALUE_TYPES: Dict[str, str] = {
    "continueMiddlewareControl": "MiddlewareControl",
    "shortCircuitMiddlewareControl": "MiddlewareControl",
    "readOnlySqliteOpenMode": "SqliteOpenMode",
    "readWriteSqliteOpenMode": "SqliteOpenMode",
    "readWriteCreateSqliteOpenMode": "SqliteOpenMode",
    "inMemorySqliteOpenMode": "SqliteOpenMode",
    "rowSqliteStepResult": "SqliteStepResult",
    "doneSqliteStepResult": "SqliteStepResult",
    "integerSqliteColumnType": "SqliteColumnType",
    "floatSqliteColumnType": "SqliteColumnType",
    "textSqliteColumnType": "SqliteColumnType",
    "blobSqliteColumnType": "SqliteColumnType",
    "nullSqliteColumnType": "SqliteColumnType",
    "windowGuiTargetKind": "GuiTargetKind",
    "controlGuiTargetKind": "GuiTargetKind",
    "defaultGuiWindowLayout": "GuiWindowLayout",
    "verticalStackGuiWindowLayout": "GuiWindowLayout",
    "horizontalStackGuiWindowLayout": "GuiWindowLayout",
    "gridGuiWindowLayout": "GuiWindowLayout",
    "absoluteGuiWindowLayout": "GuiWindowLayout",
    "buttonGuiControlKind": "GuiControlKind",
    "textBoxGuiControlKind": "GuiControlKind",
    "listBoxGuiControlKind": "GuiControlKind",
    "checkBoxGuiControlKind": "GuiControlKind",
    "menuItemGuiControlKind": "GuiControlKind",
    "statusBarGuiControlKind": "GuiControlKind",
    "textLabelGuiControlKind": "GuiControlKind",
    "defaultGuiListBoxSelectionMode": "GuiListBoxSelectionMode",
    "singleGuiListBoxSelectionMode": "GuiListBoxSelectionMode",
    "multipleGuiListBoxSelectionMode": "GuiListBoxSelectionMode",
    "clickGuiEventKind": "GuiEventKind",
    "valueChangedGuiEventKind": "GuiEventKind",
    "selectionChangedGuiEventKind": "GuiEventKind",
    "enterPressedGuiEventKind": "GuiEventKind",
    "keyPressedGuiEventKind": "GuiEventKind",
    "focusGainedGuiEventKind": "GuiEventKind",
    "focusLostGuiEventKind": "GuiEventKind",
    "closeRequestedGuiEventKind": "GuiEventKind",
    "resizedGuiEventKind": "GuiEventKind",
    "shownGuiEventKind": "GuiEventKind",
    "hiddenGuiEventKind": "GuiEventKind",
    "okGuiRuntimeStatus": "GuiRuntimeStatus",
    "configGuiRuntimeStatus": "GuiRuntimeStatus",
    "runtimeUnavailableGuiRuntimeStatus": "GuiRuntimeStatus",
    "allocationGuiRuntimeStatus": "GuiRuntimeStatus",
    "platformGuiRuntimeStatus": "GuiRuntimeStatus",
    "notFoundGuiRuntimeStatus": "GuiRuntimeStatus",
    "wrongKindGuiRuntimeStatus": "GuiRuntimeStatus",
    "handlerGuiRuntimeStatus": "GuiRuntimeStatus",
    "unsupportedGuiRuntimeStatus": "GuiRuntimeStatus",
    "threadGuiRuntimeStatus": "GuiRuntimeStatus",
}

BUILTIN_VALUE_LITERALS: Dict[str, str] = {
    "continueMiddlewareControl": "0",
    "shortCircuitMiddlewareControl": "1",
    "readOnlySqliteOpenMode": "1",
    "readWriteSqliteOpenMode": "2",
    "readWriteCreateSqliteOpenMode": "6",
    "inMemorySqliteOpenMode": "14",
    "rowSqliteStepResult": "100",
    "doneSqliteStepResult": "101",
    "integerSqliteColumnType": "1",
    "floatSqliteColumnType": "2",
    "textSqliteColumnType": "3",
    "blobSqliteColumnType": "4",
    "nullSqliteColumnType": "5",
    "windowGuiTargetKind": "1",
    "controlGuiTargetKind": "2",
    "defaultGuiWindowLayout": "0",
    "verticalStackGuiWindowLayout": "1",
    "horizontalStackGuiWindowLayout": "2",
    "gridGuiWindowLayout": "3",
    "absoluteGuiWindowLayout": "4",
    "buttonGuiControlKind": "1",
    "textBoxGuiControlKind": "2",
    "listBoxGuiControlKind": "3",
    "checkBoxGuiControlKind": "4",
    "menuItemGuiControlKind": "5",
    "statusBarGuiControlKind": "6",
    "textLabelGuiControlKind": "7",
    "defaultGuiListBoxSelectionMode": "0",
    "singleGuiListBoxSelectionMode": "1",
    "multipleGuiListBoxSelectionMode": "2",
    "clickGuiEventKind": "1",
    "valueChangedGuiEventKind": "2",
    "selectionChangedGuiEventKind": "3",
    "enterPressedGuiEventKind": "4",
    "keyPressedGuiEventKind": "5",
    "focusGainedGuiEventKind": "6",
    "focusLostGuiEventKind": "7",
    "closeRequestedGuiEventKind": "8",
    "resizedGuiEventKind": "9",
    "shownGuiEventKind": "10",
    "hiddenGuiEventKind": "11",
    "okGuiRuntimeStatus": "0",
    "configGuiRuntimeStatus": "1",
    "runtimeUnavailableGuiRuntimeStatus": "2",
    "allocationGuiRuntimeStatus": "3",
    "platformGuiRuntimeStatus": "4",
    "notFoundGuiRuntimeStatus": "5",
    "wrongKindGuiRuntimeStatus": "6",
    "handlerGuiRuntimeStatus": "7",
    "unsupportedGuiRuntimeStatus": "8",
    "threadGuiRuntimeStatus": "9",
}

BUILTIN_TYPE_ALIASES: Dict[str, str] = {
    "SqliteDatabase": "COpaqueMemoryAddress",
    "SqliteStatement": "COpaqueMemoryAddress",
    "SqliteRowId": "CSignedInt64",
    "GuiApplication": "COpaqueMemoryAddress",
    "GuiSession": "COpaqueMemoryAddress",
    "GuiEvent": "COpaqueMemoryAddress",
    "GuiWindow": "COpaqueMemoryAddress",
    "GuiControl": "COpaqueMemoryAddress",
    "GuiWindowId": "CUnsignedInt32",
    "GuiControlId": "CUnsignedInt32",
    "GuiText": "CNullTerminatedByteString",
    "GuiApplicationTitle": "GuiText",
    "GuiWindowTitle": "GuiText",
    "GuiControlText": "GuiText",
    "GuiPlaceholderText": "GuiText",
    "GuiAccessibleName": "GuiText",
    "GuiListBoxItemText": "GuiText",
    "GuiIconGroupName": "CNullTerminatedByteString",
    "GuiPixels": "CSignedInt32",
    "GuiMinimumPixels": "GuiPixels",
    "GuiTabIndex": "CSignedInt32",
    "GuiKeyCode": "CSignedInt32",
    "GuiSelectedIndex": "CSignedInt32",
    "GuiEventDimensionPixels": "GuiPixels",
    "GuiHandlerStatus": "CSignedInt32",
    "GuiRuntimeStatusCode": "CSignedInt32",
    "GuiKeywordToken": "CNullTerminatedByteString",
    "GuiRuntimeTarget": "CNullTerminatedByteString",
}

BUILTIN_ABSTRACTIONS: Dict[str, str] = {
    "MiddlewareControl": "enum",
    "SqliteOpenMode": "enum",
    "SqliteStepResult": "enum",
    "SqliteColumnType": "enum",
    "GuiTargetKind": "enum",
    "GuiWindowLayout": "enum",
    "GuiControlKind": "enum",
    "GuiListBoxSelectionMode": "enum",
    "GuiEventKind": "enum",
    "GuiRuntimeStatus": "enum",
}

GUI_CONTROL_HANDLE_TYPES: frozenset = frozenset({
    "GuiControl",
    "GuiButton",
    "GuiTextBox",
    "GuiListBox",
    "GuiCheckBox",
    "GuiMenuItem",
    "GuiStatusBar",
    "GuiTextLabel",
})

_STDLIB_PATH_ENV_VARS = ("SEMANTICSCRIPT_STD_PATH", "SEMSC_STD_PATH")
_CLI_STDLIB_PATHS: List[str] = []


def _std_root_candidates_from_path(rawPath: str) -> List[Path]:
    if not rawPath:
        return []
    expanded = Path(os.path.expandvars(os.path.expanduser(rawPath))).resolve()
    if expanded.is_file():
        expanded = expanded.parent
    return [
        expanded,
        expanded / "std",
        expanded / "SemanticScript" / "std",
    ]


def _split_std_path_list(rawValue: str) -> List[str]:
    if not rawValue:
        return []
    return [part for part in rawValue.split(os.pathsep) if part]


def _ancestor_std_candidates(startPath: Optional[Path]) -> List[Path]:
    if startPath is None:
        return []
    current = startPath.resolve()
    if current.is_file():
        current = current.parent
    candidates: List[Path] = []
    for ancestor in [current, *current.parents]:
        candidates.append(ancestor / "std")
        candidates.append(ancestor / "SemanticScript" / "std")
    return candidates


def _standard_library_roots(startPath: Optional[Path] = None) -> List[Path]:
    candidates: List[Path] = []
    for rawPath in _CLI_STDLIB_PATHS:
        candidates.extend(_std_root_candidates_from_path(rawPath))
    for envName in _STDLIB_PATH_ENV_VARS:
        for rawPath in _split_std_path_list(os.environ.get(envName, "")):
            candidates.extend(_std_root_candidates_from_path(rawPath))
    candidates.extend(_ancestor_std_candidates(startPath))
    cwd = Path.cwd()
    candidates.append(cwd / "std")
    candidates.append(cwd / "SemanticScript" / "std")
    candidates.append(Path(__file__).resolve().parents[1] / "std")

    roots: List[Path] = []
    seen: Set[Path] = set()
    for candidate in candidates:
        root = candidate.resolve()
        if not (root / "module.sem").is_file():
            continue
        if root in seen:
            continue
        seen.add(root)
        roots.append(root)
    return roots


def _standard_module_source(
    moduleName: str,
    startPath: Optional[Path] = None,
) -> Optional[Path]:
    if moduleName != "standard" and not moduleName.startswith("standard."):
        return None
    for stdlibRoot in _standard_library_roots(startPath):
        if moduleName == "standard":
            relayPath = stdlibRoot / "module.sem"
            if relayPath.is_file():
                return relayPath.resolve()
            continue
        relativeModule = Path(*moduleName.split(".")[1:])
        candidateDir = stdlibRoot / relativeModule
        if candidateDir.is_dir():
            for candidateName in ("main.sem", "main.sscript", "index.sem", "index.sscript"):
                candidate = candidateDir / candidateName
                if candidate.is_file():
                    return candidate.resolve()
        for suffix in (".sscript", ".sem"):
            candidate = stdlibRoot / relativeModule.with_suffix(suffix)
            if candidate.is_file():
                return candidate.resolve()
    return None


def _is_known_standard_module(
    moduleName: str,
    startPath: Optional[Path] = None,
) -> bool:
    return _standard_module_source(moduleName, startPath) is not None


def _builtin_line(path: Path, raw: str) -> SourceLine:
    return SourceLine(path=path, number=0, raw=raw, tokens=tokenize_line(raw))


def _register_builtin_surface(program: ProgramFacts) -> None:
    for name, typeName in BUILTIN_TYPE_ALIASES.items():
        program.type_aliases.setdefault(name, typeName)

    for name, kind in BUILTIN_ABSTRACTIONS.items():
        program.abstractions.setdefault(
            name,
            AbstractionFact(kind, name, _builtin_line(program.path, f"{kind} {name}")),
        )

    for name, typeName in BUILTIN_VALUE_TYPES.items():
        literalValue = BUILTIN_VALUE_LITERALS.get(name, "")
        program.consts.setdefault(
            name,
            ConstFact(
                name=name,
                type_name=typeName,
                value=literalValue,
                line=_builtin_line(program.path, f"const {name} {typeName} {literalValue}"),
            ),
        )


# Verb classification — used by the parser to decide which lines attach to
# the currently-open operation. The closed sets here are intentionally
# narrow; this module's checker passes interpret unknown verbs as SS0001.
_PARSER_CONTEXT_VERBS: Set[str] = {
    "input", "output", "effect", "memory", "async", "purpose", "invariant",
    "warning", "precondition",
    "guarantee", "failure", "security", "timing", "observability",
    "memoryHeap", "memoryArena", "memoryStackLimit",
    "memoryAllocationSource",
    "pinsNullBodyFailurePath", "responseBodyForwarder", "rationale",
}
_PARSER_ACTION_VERBS: Set[str] = {
    "set", "call", "arg", "timeout", "cancelOn", "run", "start", "await",
    "bind", "bindOk", "bindError", "ignoreOk", "ignoreValue", "makeError",
    "taskGroup", "startInGroup", "awaitGroup", "bindGroupError", "defer",
    "deferLog", "deferAwaitLog", "deferWhenExitLog", "new", "fieldGet",
    "fieldSet", "send", "receive", "lock", "unlock", "select", "selectCase",
    "runSelect", "useRetry", "useCapability",
    "deferRunOn", "startInterval", "awaitIntervalTick",
    "submitWork", "awaitWork",
}
_PARSER_CONTROL_VERBS: Set[str] = {
    "label", "branch", "branchIf", "branchIfError", "branchIfGroupError",
    "branchIfChannelClosed", "branchSelected", "returnOk", "returnError",
    "returnValue", "returnVoid",
}
_PARSER_BODY_VERBS: Set[str] = (
    _PARSER_CONTEXT_VERBS
    | _PARSER_ACTION_VERBS
    | _PARSER_CONTROL_VERBS
    | {"const", "var", "storage", "importModule"}
)
_PARSER_CONTRACT_HEAVY_KINDS: Set[str] = {
    "record", "codec", "jsonCodec", "validator", "mapper", "adapter",
    "boundary", "policy", "errorPolicy", "retryPolicy", "timeoutBudget",
    "resource", "webServer",
}


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


def parse_group_comment(line: SourceLine) -> Optional[Tuple[str, str, SourceLine]]:
    text = comment_text(line)
    if text.startswith("group "):
        return ("group", text.split(None, 1)[1].strip(), line)
    if text.startswith("endGroup "):
        return ("endGroup", text.split(None, 1)[1].strip(), line)
    return None


def parse_import_module_args(args: Sequence[str]) -> Tuple[str, Optional[str], str]:
    """Return (module_path, alias, syntax_shape) for supported import forms.

    Compatibility form:
      importModule MODULE_PATH [as ALIAS]

    Preferred project form:
      importModule ALIAS MODULE_PATH
    """
    if not args:
        return "", None, "malformed"
    if len(args) >= 3 and args[1] == "as":
        return args[0], args[2], "module-as-alias"
    if len(args) == 2 and args[1] != "as":
        return args[1], args[0], "alias-module"
    return args[0], None, "module-only"


SINGULAR_IMPORT_VERB_KINDS: Dict[str, str] = {
    "importOperation": "operation",
    "importType": "type",
    "importError": "error",
    "importCapability": "capability",
    "importConstant": "constant",
}


def parse_file(path: Path) -> ProgramFacts:
    program = ProgramFacts(path=path)
    _register_builtin_surface(program)
    current_op: Optional[OperationFact] = None
    active_html_body = False

    with path.open("r", encoding="utf-8") as source_file:
        for line_number, raw_line in enumerate(source_file, start=1):
            raw = raw_line.rstrip("\n")
            if active_html_body:
                if raw.strip() and raw[0].isspace():
                    continue
                if not raw.strip():
                    continue
                active_html_body = False
            line = SourceLine(path=path, number=line_number, raw=raw,
                              tokens=tokenize_line(raw))
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
                program.abstractions.setdefault(
                    args[0], AbstractionFact("operation", args[0], line))
                continue

            if current_op and verb in _PARSER_BODY_VERBS:
                current_op.lines.append(line)

            if verb == "mode" and args:
                program.modes.add(args[0])
            elif verb == "importModule" and args:
                moduleName, alias, syntax = parse_import_module_args(args)
                if moduleName:
                    program.imports.add(moduleName)
                    program.module_imports.append(
                        ImportModuleFact(moduleName, alias, line, syntax))
            elif verb in SINGULAR_IMPORT_VERB_KINDS and len(args) >= 3:
                program.singular_imports.append(SingularImportFact(
                    kind=SINGULAR_IMPORT_VERB_KINDS[verb],
                    local_name=args[0],
                    module_alias=args[1],
                    exported_name=args[2],
                    line=line,
                ))
            elif verb == "const" and len(args) >= 3:
                program.consts[args[0]] = ConstFact(
                    args[0], args[1], args[2], line)
            elif verb == "type" and len(args) >= 2:
                program.type_aliases[args[0]] = args[1]
            elif verb.startswith("type") and len(args) >= 1 and verb != "type":
                program.type_metadata.setdefault(args[0], set()).add(verb)
            elif verb == "capability" and len(args) >= 3:
                program.capabilities[args[0]] = BaseCapabilityFact(
                    args[0], args[1], args[2], line)
            elif verb == "route" and len(args) >= 4:
                program.routes.append(
                    RouteFact(args[0], args[1], args[2], args[3], line))
            elif verb == "htmlTemplate" and args:
                program.abstractions.setdefault(
                    args[0], AbstractionFact(verb, args[0], line))
            elif verb == "htmlBody" and args:
                active_html_body = True
            elif verb in _PARSER_CONTRACT_HEAVY_KINDS and args:
                program.abstractions.setdefault(
                    args[0], AbstractionFact(verb, args[0], line))
            elif (verb in {"purpose", "invariant", "warning", "guarantee",
                           "failure", "security", "timing", "observability"}
                  and args):
                program.hard_metadata.setdefault(args[0], set()).add(verb)

    return program


# Alias retained because checkers downstream call `parse_file_base` —
# the previous shape was an `import as` from semlint; same function now.
parse_file_base = parse_file


# ==========================================================================
# Tier model
# ==========================================================================

class Tier(str, Enum):
    T0_PARSE = "T0"          # grammar — non-overridable error
    T1_SPEC = "T1"           # spec violation — non-overridable error
    T2_LOWERING = "T2"       # lowering invariant — non-overridable error
    T3_REFINEMENT = "T3"     # refinement gap — warning by default, configurable
    T4_STYLE = "T4"          # style/convention — info by default, configurable


class Severity(str, Enum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class Confidence(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class Effort(str, Enum):
    TRIVIAL = "trivial"
    LOCAL = "local"
    CROSS_FILE = "crossFile"


# Narrative attachments the linter recognises on operations. These are the
# edges every diagnostic should CITE when bound to an operation, not just
# point at — they hold the author's stated intent and are the basis for
# refinement decisions.
NARRATIVE_EDGES: Tuple[str, ...] = (
    "purpose",
    "invariant",
    "warning",
    "guarantee",
    "security",
    "timing",
    "observability",
    "failure",
)


# Names that are too vague for SemanticScript's descriptive-identifier rule.
# Curated from common-abuse list; covers the canonical "generic placeholder
# leaked into source" patterns. Single letters and 2-3-char counters are
# rejected as a class — they read as scratch from another language.
VAGUE_NAME_BLACKLIST: frozenset = frozenset({
    "err", "tmp", "res", "data", "handler", "thing", "stuff", "value",
    "item", "obj", "util", "helper", "processData", "doThing",
    "buf", "ptr", "ret", "val", "var", "arr", "list", "map", "set",
    "n", "i", "j", "k", "m", "x", "y", "z", "a", "b", "c", "d", "e",
    "f", "g", "h", "p", "q", "r", "s", "t", "u", "v", "w",
})

OPAQUE_DEPENDENCY_INPUT_NAMES: frozenset = frozenset({
    "console", "environment", "process",
    "httpRequest", "databaseClient", "clock",
    "session", "event",
})


# Call targets that return Result-shaped or can fail at the runtime level.
# Calls to these MUST have both `bindError` and `branchIfError` (or be
# explicitly discarded with documented rationale). This is the
# hiddenFailure detection surface.
KNOWN_FALLIBLE_CALL_TARGETS: frozenset = frozenset({
    "console.writeLine",
    "console.writeIntegerLine",
    "console.writeInteger",
    "console.writeFloatLine",
    "math.checkedMultiplyI64",
    # libc with errno-or-EOF semantics
    "c.fopen", "c.fread", "c.fwrite", "c.fclose",
    "c.malloc", "c.calloc", "c.realloc",
    "c.fputs", "c.fputc", "c.putchar",
    "c.fgets", "c.fseek", "c.ftell",
    "c.open", "c.read", "c.write", "c.close",
})

C_SENTINEL_FALLIBLE_CALL_TARGETS: frozenset = frozenset({
    "c.fopen", "c.fread", "c.fwrite", "c.fclose",
    "c.fputs", "c.fputc", "c.putchar",
    "c.fgets", "c.fseek", "c.ftell",
    "c.open", "c.read", "c.write", "c.close",
})


# Metadata edges that should be consistent across sibling operations in
# the same file. If 60%+ of operations declare an edge and any sibling
# doesn't, that's drift worth flagging.
SIBLING_METADATA_EDGES: Tuple[str, ...] = (
    "memoryHeap",
    "memoryStackLimit",
    "memoryArena",
    "async",
)


# Heap-allocating call targets. Distinct from KNOWN_FALLIBLE_CALL_TARGETS
# because some (c.free) don't allocate but still relate to memory discipline.
HEAP_ALLOCATION_CALL_TARGETS: frozenset = frozenset({
    "c.malloc", "c.calloc", "c.realloc",
})

HEAP_DEALLOCATION_CALL_TARGETS: frozenset = frozenset({
    "c.free",
})


# Stack-byte estimates for primitive SemanticScript types. Used by SS3304 stack-limit
# overrun heuristic. Values are conservative C ABI widths; types not in this
# table contribute 8 bytes (pointer-sized) — slightly pessimistic but never
# under-counts.
PRIMITIVE_TYPE_STACK_BYTES: Dict[str, int] = {
    "Bool": 1,
    "CSignedByte": 1, "CUnsignedByte": 1, "I8": 1,
    "CSignedInt16": 2, "CUnsignedInt16": 2, "I16": 2,
    "I32": 4, "CSignedInt32": 4, "CUnsignedInt32": 4, "ExitCode": 4,
    "CFloat32": 4,
    "I64": 8, "CSignedInt64": 8, "CUnsignedInt64": 8,
    "F64": 8, "CFloat64": 8,
    "DurationMilliseconds": 8, "MonotonicMilliseconds": 8, "UtcMilliseconds": 8,
    "CByteCount": 8, "CSignedByteCount": 8, "CAddressOffset": 8,
    "CUnixSecondsSinceEpoch": 8, "CCpuClockTicks": 8, "CFileByteOffset": 8,
    "CNullTerminatedByteString": 8, "COpaqueMemoryAddress": 8, "CFileHandle": 8,
    "Void": 0,
}


# Map of dotted-target call → (action, effectPath) so we can detect when a
# body call implies an effect the operation didn't declare via `effect OP
# ACTION PATH`. Only built-in / runtime-bound targets are listed; user-op
# calls are skipped (their effects must be analysed transitively, which
# we defer to a future iteration).
CALL_TARGET_IMPLIED_EFFECTS: Dict[str, Tuple[str, str]] = {
    # Console writes
    "console.writeLine":         ("write", "console.stdout"),
    "console.writeIntegerLine":  ("write", "console.stdout"),
    "console.writeInteger":      ("write", "console.stdout"),
    "console.writeFloatLine":    ("write", "console.stdout"),
    "c.putchar":                 ("write", "console.stdout"),
    "c.fputs":                   ("write", "console.stdout"),
    "c.fputc":                   ("write", "console.stdout"),
    # File data I/O. `file` is reserved for handle lifecycle; filesystem
    # covers bytes read/written through an opened handle.
    "c.fgets":                   ("read",  "filesystem"),
    # Heap allocation
    "c.malloc":                  ("allocate", "heap"),
    "c.calloc":                  ("allocate", "heap"),
    "c.realloc":                 ("allocate", "heap"),
    "c.free":                    ("free",     "heap"),
    # Process lifecycle
    "c.exit":                    ("write", "process.lifecycle"),
    "c.abort":                   ("write", "process.lifecycle"),
    # File I/O
    "c.fopen":                   ("open",  "file"),
    "c.fclose":                  ("close", "file"),
    "c.fread":                   ("read",  "filesystem"),
    "c.fwrite":                  ("write", "filesystem"),
    "c.fseek":                   ("seek",  "file"),
    "c.ftell":                   ("read",  "file"),
    "c.open":                    ("open",  "file"),
    "c.close":                   ("close", "file"),
    "c.read":                    ("read",  "file"),
    "c.write":                   ("write", "file"),
    # GUI runtime calls. Richer control/event validation belongs in
    # standard.gui; these entries only feed the generic effect coverage pass.
    "gui.applicationCreate":     ("allocate", "gui.application"),
    "gui.windowCreate":          ("allocate", "gui.window"),
    "gui.textLabelCreate":       ("allocate", "gui.control"),
    "gui.textBoxCreate":         ("allocate", "gui.control"),
    "gui.buttonCreate":          ("allocate", "gui.control"),
    "gui.listBoxCreate":         ("allocate", "gui.control"),
    "gui.windowAddControl":      ("write", "gui.window"),
    "gui.controlOnEvent":        ("write", "gui.control.event"),
    "gui.applicationSetMainWindow": ("write", "gui.window"),
    "gui.applicationRun":        ("write", "gui.window"),
    "gui.textBoxText":           ("read",  "gui.control.textBox.text"),
    "gui.textBoxSetText":        ("write", "gui.control.textBox.text"),
    "gui.listBoxSelectedIndex":  ("read",  "gui.control.listBox.selection"),
    "gui.listBoxAppendItem":     ("write", "gui.control.listBox.items"),
    "gui.listBoxClear":          ("write", "gui.control.listBox.items"),
    "gui.textLabelSetText":      ("write", "gui.control.textLabel.text"),
    "gui.windowClose":           ("write", "gui.window"),
    "gui.eventKeyCode":          ("read",  "gui.event"),
    "gui.eventSelectedIndex":    ("read",  "gui.event"),
    "gui.eventWindowWidth":      ("read",  "gui.event"),
    "gui.eventWindowHeight":     ("read",  "gui.event"),
}


# Primitive types that are interchangeable at the SemanticScript surface — `I64` and
# `CSignedInt64` are the same shape, `String` and `CNullTerminatedByteString`
# are the same wire form, etc. Used by broad arg-type-mismatch checks to avoid
# false-positive complaints about role-equivalent aliases. Math calls get a
# stricter width pass below because their lowering is intentionally exact.
_PRIMITIVE_TYPE_EQUIVALENCE_GROUPS: Tuple[frozenset, ...] = (
    # All signed integer widths AND Bool are treated as interchangeable for
    # legacy/user-op compatibility; strict math width diagnostics are handled
    # separately by SS4303.
    frozenset({"I64", "CSignedInt64",
               "I32", "CSignedInt32", "ExitCode",
               "I16", "CSignedInt16",
               "I8", "CSignedByte",
               # 8-byte signed role types — interchangeable with I64 in
               # math.*I64, pointer.* (for byte counts/offsets), and time
               # APIs throughout the stdlib.
               "CByteCount", "CSignedByteCount", "CAddressOffset",
               "CUnixSecondsSinceEpoch", "CCpuClockTicks", "CFileByteOffset",
               "DurationMilliseconds", "MonotonicMilliseconds", "UtcMilliseconds",
               "Bool"}),
    frozenset({"CUnsignedByte", "CUnsignedInt16",
               "CUnsignedInt32", "CUnsignedInt64"}),
    frozenset({"F64", "CFloat64", "F32", "CFloat32"}),
    # All pointer-shaped types are interchangeable — pointer.* primitives
    # accept any of them and the compiler emits the necessary bitcasts.
    # String / CNullTerminatedByteString are pointer-shaped byte sequences
    # so they live in the pointer family for SemanticScript arg-type purposes.
    frozenset({"String", "CNullTerminatedByteString",
               "COpaqueMemoryAddress", "CFileHandle",
               "CDecomposedTimeAddress", "CSetjmpRegisterBuffer"}),
    frozenset({"Void"}),
)


def _build_primitive_canonical_map() -> Dict[str, str]:
    canonicalByName: Dict[str, str] = {}
    for equivalenceGroup in _PRIMITIVE_TYPE_EQUIVALENCE_GROUPS:
        groupCanonical = sorted(equivalenceGroup)[0]
        for member in equivalenceGroup:
            canonicalByName[member] = groupCanonical
    return canonicalByName


PRIMITIVE_CANONICAL_BY_TYPE: Dict[str, str] = _build_primitive_canonical_map()


# Hardcoded signatures for built-in call targets. Each entry maps the
# dotted target → ordered list of (argName, declaredType). Targets not in
# this map fall through to user-op signature lookup; targets in neither
# table are SKIPPED to avoid false positives on unknowns.
BUILTIN_TARGET_SIGNATURES: Dict[str, List[Tuple[str, str]]] = {
    # Console writes
    "console.writeLine":          [("console", "Console"), ("text", "CNullTerminatedByteString")],
    "console.writeIntegerLine":   [("console", "Console"), ("value", "I64")],
    "console.writeInteger":       [("console", "Console"), ("value", "I64")],
    "console.writeFloatLine":     [("console", "Console"), ("value", "F64")],
    # Integer arithmetic
    "math.addI64":                [("left", "I64"), ("right", "I64")],
    "math.subtractI64":           [("left", "I64"), ("right", "I64")],
    "math.multiplyI64":           [("left", "I64"), ("right", "I64")],
    "math.divideI64":             [("left", "I64"), ("right", "I64")],
    "math.moduloI64":             [("left", "I64"), ("right", "I64")],
    "math.equalI64":              [("left", "I64"), ("right", "I64")],
    "math.notEqualI64":           [("left", "I64"), ("right", "I64")],
    "math.lessThanI64":           [("left", "I64"), ("right", "I64")],
    "math.lessThanOrEqualI64":    [("left", "I64"), ("right", "I64")],
    "math.greaterThanI64":        [("left", "I64"), ("right", "I64")],
    "math.greaterThanOrEqualI64": [("left", "I64"), ("right", "I64")],
    "math.equalCSignedInt32":              [("left", "CSignedInt32"), ("right", "CSignedInt32")],
    "math.notEqualCSignedInt32":           [("left", "CSignedInt32"), ("right", "CSignedInt32")],
    "math.lessThanCSignedInt32":           [("left", "CSignedInt32"), ("right", "CSignedInt32")],
    "math.lessThanOrEqualCSignedInt32":    [("left", "CSignedInt32"), ("right", "CSignedInt32")],
    "math.greaterThanCSignedInt32":        [("left", "CSignedInt32"), ("right", "CSignedInt32")],
    "math.greaterThanOrEqualCSignedInt32": [("left", "CSignedInt32"), ("right", "CSignedInt32")],
    "math.checkedMultiplyI64":    [("left", "I64"), ("right", "I64")],
    "math.signExtendCSignedInt32ToCSignedInt64": [("inputValue", "CSignedInt32")],
    "math.truncateCSignedInt64ToCSignedInt32":   [("inputValue", "I64")],
    # Float arithmetic
    "math.addF64":                [("left", "F64"), ("right", "F64")],
    "math.subtractF64":           [("left", "F64"), ("right", "F64")],
    "math.multiplyF64":           [("left", "F64"), ("right", "F64")],
    "math.divideF64":             [("left", "F64"), ("right", "F64")],
    "math.equalF64":              [("left", "F64"), ("right", "F64")],
    "math.lessThanF64":           [("left", "F64"), ("right", "F64")],
    # Numeric conversion
    "math.intToFloat":            [("inputValue", "I64")],
    "math.floatToInt":            [("inputValue", "F64")],
    # Pointer primitives
    "pointer.loadByte":           [("buffer", "COpaqueMemoryAddress"), ("offset", "CByteCount")],
    "pointer.storeByte":          [("buffer", "COpaqueMemoryAddress"), ("offset", "CByteCount"), ("value", "CSignedInt64")],
    "pointer.offset":             [("buffer", "COpaqueMemoryAddress"), ("offset", "CByteCount")],
    "pointer.difference":         [("left", "COpaqueMemoryAddress"), ("right", "COpaqueMemoryAddress")],
    "pointer.isNull":             [("pointer", "COpaqueMemoryAddress")],
    # C lib
    "c.malloc":                   [("size", "CByteCount")],
    "c.calloc":                   [("count", "CByteCount"), ("size", "CByteCount")],
    "c.realloc":                  [("ptr", "COpaqueMemoryAddress"), ("size", "CByteCount")],
    "c.free":                     [("ptr", "COpaqueMemoryAddress")],
    "c.exit":                     [("code", "CSignedInt32")],
    "c.abort":                    [],
    "c.putchar":                  [("c", "CSignedInt32")],
}

GUI_RUNTIME_TARGET_SIGNATURES: Dict[str, List[Tuple[str, str]]] = {
    "gui.applicationCreate": [
        ("title", "GuiText"),
    ],
    "gui.windowCreate": [
        ("title", "GuiText"),
        ("width", "GuiPixels"),
        ("height", "GuiPixels"),
        ("layout", "GuiWindowLayout"),
        ("resizable", "CSignedInt32"),
    ],
    "gui.textLabelCreate": [
        ("text", "GuiText"),
    ],
    "gui.textBoxCreate": [
        ("placeholder", "GuiText"),
        ("maxLength", "CSignedInt32"),
    ],
    "gui.buttonCreate": [
        ("text", "GuiText"),
        ("isDefault", "CSignedInt32"),
    ],
    "gui.listBoxCreate": [
        ("selectionMode", "GuiListBoxSelectionMode"),
    ],
    "gui.windowAddControl": [
        ("window", "GuiWindow"),
        ("control", "GuiControl"),
    ],
    "gui.controlOnEvent": [
        ("control", "GuiControl"),
        ("eventKind", "GuiEventKind"),
    ],
    "gui.applicationSetMainWindow": [
        ("application", "GuiApplication"),
        ("window", "GuiWindow"),
    ],
    "gui.applicationRun": [
        ("application", "GuiApplication"),
    ],
    "gui.textBoxText": [
        ("session", "GuiSession"),
        ("textBox", "GuiTextBox"),
    ],
    "gui.textBoxSetText": [
        ("session", "GuiSession"),
        ("textBox", "GuiTextBox"),
        ("text", "CNullTerminatedByteString"),
    ],
    "gui.listBoxSelectedIndex": [
        ("session", "GuiSession"),
        ("listBox", "GuiListBox"),
    ],
    "gui.listBoxAppendItem": [
        ("session", "GuiSession"),
        ("listBox", "GuiListBox"),
        ("text", "CNullTerminatedByteString"),
    ],
    "gui.listBoxClear": [
        ("session", "GuiSession"),
        ("listBox", "GuiListBox"),
    ],
    "gui.textLabelSetText": [
        ("session", "GuiSession"),
        ("textLabel", "GuiTextLabel"),
        ("text", "GuiText"),
    ],
    "gui.windowClose": [
        ("session", "GuiSession"),
        ("window", "GuiWindow"),
    ],
    "gui.eventKeyCode": [
        ("event", "GuiEvent"),
    ],
    "gui.eventSelectedIndex": [
        ("event", "GuiEvent"),
    ],
    "gui.eventWindowWidth": [
        ("event", "GuiEvent"),
    ],
    "gui.eventWindowHeight": [
        ("event", "GuiEvent"),
    ],
}

BUILTIN_TARGET_SIGNATURES.update(GUI_RUNTIME_TARGET_SIGNATURES)


# Minimum argument count per verb. SemanticScript lines are `verb arg1 arg2 …`; verbs
# with too few args can't be interpreted by any downstream pass. Ported
# from semlint.py and extended for refined-syntax surfaces.
SUPPORTED_JSON_PRIMITIVE_TARGETS: frozenset = frozenset({
    "json.encode.I64", "json.encode.CSignedInt64",
    "json.encode.CSignedInt32", "json.encode.CUnsignedInt32",
    "json.encode.CSignedInt16", "json.encode.CUnsignedInt16",
    "json.encode.CSignedByte", "json.encode.CUnsignedByte",
    "json.encode.DurationMilliseconds",
    "json.encode.MonotonicMilliseconds",
    "json.encode.UtcMilliseconds",
    "json.encode.Bool",
    "json.encode.F64", "json.encode.CFloat64", "json.encode.CFloat32",
    "json.encode.String", "json.encode.CNullTerminatedByteString",
    "json.decode.I64", "json.decode.CSignedInt64",
    "json.decode.CSignedInt32", "json.decode.CUnsignedInt32",
    "json.decode.CSignedInt16", "json.decode.CUnsignedInt16",
    "json.decode.CSignedByte", "json.decode.CUnsignedByte",
    "json.decode.DurationMilliseconds",
    "json.decode.MonotonicMilliseconds",
    "json.decode.UtcMilliseconds",
    "json.decode.Bool",
    "json.decode.F64", "json.decode.CFloat64", "json.decode.CFloat32",
})

SUPPORTED_JSON_RUNTIME_TARGETS: frozenset = frozenset({
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

SUPPORTED_GUI_RUNTIME_TARGETS: frozenset = frozenset({
    "gui.applicationCreate", "gui.windowCreate",
    "gui.textLabelCreate", "gui.textBoxCreate",
    "gui.buttonCreate", "gui.listBoxCreate",
    "gui.windowAddControl", "gui.controlOnEvent",
    "gui.applicationSetMainWindow",
    "gui.applicationRun",
    "gui.textBoxText", "gui.textBoxSetText",
    "gui.listBoxSelectedIndex", "gui.listBoxAppendItem", "gui.listBoxClear",
    "gui.textLabelSetText", "gui.windowClose",
    "gui.eventKeyCode", "gui.eventSelectedIndex",
    "gui.eventWindowWidth", "gui.eventWindowHeight",
})

COLLECTION_RUNTIME_METHODS: frozenset = frozenset({
    "append", "get", "set", "insert", "remove", "length", "clear",
    "contains", "slice", "borrow", "capacity", "reserve",
})

COLLECTION_TYPE_SUFFIXES: Tuple[str, ...] = (
    "List", "Map", "Array", "Slice",
)


VERB_MINIMUM_ARITY: Dict[str, int] = {
    # Project structure
    "project": 1, "target": 1, "runtime": 2, "entry": 2, "mode": 1,
    "module": 1, "section": 1, "importModule": 1,
    "importOperation": 3, "importType": 3, "importError": 3,
    "importCapability": 3, "importConstant": 3,
    "buildProject": 1, "modulePath": 2, "languageVersion": 2,
    "sourceRoot": 2, "mainFile": 2, "mainOperation": 2,
    "testPattern": 2, "dependencySource": 3, "dependencyFetch": 4,
    "dependencyCache": 2, "dependencyLock": 2, "dependencyIntegrity": 3,
    "buildProfile": 2, "runtimeChecks": 2, "persistLlvmIr": 2,
    "nativeOutput": 2, "targetRuntime": 2, "comptimeOperation": 2,
    "projectVersion": 2, "projectLicense": 2, "testRoot": 2,
    "nativeHttpHost": 2, "nativeHttpPort": 2,
    "formatterSetting": 3, "linterSetting": 3, "docsOutput": 2,
    "optLevel": 2, "emitLlvmIr": 2, "llvmIrOutput": 2,
    "emitOptimizedLlvmIr": 2, "optimizedLlvmIrOutput": 2,
    "buildDir": 2, "buildRoot": 2, "buildFolderName": 2,
    "cpuBaseline": 2, "cpuTune": 2, "cpuFeature": 3,
    "cpuFeatureCheck": 2,
    "keepResources": 2, "resourcesDir": 2,
    "registerModule": 3,
    "moduleFolder": 2, "modulePurpose": 2, "moduleOwns": 2,
    "moduleDoesNotOwn": 2, "moduleDependency": 2, "moduleWarning": 2,
    "moduleInvariant": 2, "moduleSecurity": 2, "moduleObservability": 2,
    "exportType": 2, "exportError": 2, "exportOperation": 2,
    "exportCapability": 2, "exportConstant": 2,
    "iconRoleDefinition": 2, "icon": 1, "iconRole": 2, "iconPurpose": 2,
    "iconImage": 1, "iconImageGroup": 2, "iconImagePath": 2,
    "iconImageFormat": 2, "iconImageWidth": 2, "iconImageHeight": 2,
    "iconImageScale": 2, "iconImageDepth": 2, "iconImagePlatform": 2,
    "iconImagePurpose": 2,
    # Types / records / errors
    "type": 2, "typeInvariant": 2, "typeRepresentation": 2, "typeTrust": 2,
    "typeMemory": 2, "typeLayout": 2, "typeLiteralEncoding": 2,
    "typeLiteralTerminator": 2,
    "record": 1, "field": 3, "recordLayout": 2, "recordAlign": 2,
    "new": 2, "fieldSet": 3, "fieldGet": 4,
    "error": 1, "errorCase": 2, "enum": 1, "enumCase": 2,
    # HTML / SSX
    "htmlTemplate": 1, "htmlArg": 3, "htmlBody": 1,
    # Operations + narrative
    "operation": 1, "operationBody": 2,
    "input": 2, "output": 2, "effect": 3,
    "memory": 2, "memoryHeap": 2, "memoryArena": 2, "memoryStackLimit": 2,
    "memoryAllocationSource": 2,
    "async": 2,
    "purpose": 2, "invariant": 2, "warning": 2, "guarantee": 2, "failure": 2,
    "security": 2, "timing": 2, "observability": 2,
    # Storage / shared state
    "storage": 4, "sharedState": 4,
    "set": 2, "read": 4,
    # Domain literals / literals
    "domainLiteral": 3, "domainLiteralSource": 2,
    "domainLiteralTrust": 2, "domainLiteralValidation": 2,
    "literal": 2, "literalBytes": 2, "literalDigest": 3,
    "literalPreview": 2, "literalSource": 2, "literalTrust": 2,
    # Calls
    "call": 2, "arg": 3, "timeout": 2, "cancelOn": 2,
    "run": 1, "start": 1, "await": 1,
    "bind": 3, "bindOk": 3, "bindError": 3,
    "ignoreOk": 2, "ignoreValue": 2,
    "makeError": 2, "declareFailure": 2,
    # Control flow
    "label": 1, "branch": 1, "branchIf": 2, "branchIfError": 2,
    "branchIfGroupError": 2, "branchIfChannelClosed": 2, "branchSelected": 3,
    "returnOk": 1, "returnError": 1, "returnValue": 1,
    # Capabilities + dependencies
    "capability": 3, "useCapability": 2, "authority": 3,
    "dependency": 1, "dependencyFunction": 1,
    # Policies + retry
    "retryPolicy": 1, "retryMaxAttempts": 2, "retryInitialDelay": 2,
    "retryMaximumDelay": 2, "retryJitter": 2, "useRetry": 2,
    "errorPolicy": 1, "timeoutBudget": 2,
    # Trust boundaries
    "trustBoundary": 1, "trustBoundaryKind": 2, "trustBoundaryInput": 2,
    "trustBoundaryOutput": 2, "trustBoundaryValidator": 2,
    # Codecs
    "codec": 1, "jsonCodec": 1, "schema": 2,
    "jsonCodecInput": 2, "jsonCodecOutput": 2,
    "jsonCodecDecodeTarget": 2, "jsonCodecEncodeTarget": 2,
    # Defer / cleanup
    "defer": 2, "deferLog": 2, "deferAwaitLog": 2, "deferWhenExitLog": 3,
    "deferRunOn": 2, "deferOrder": 2, "deferFailurePolicy": 2,
    # Concurrency
    "taskGroup": 1, "startInGroup": 2, "awaitGroup": 1,
    "bindGroupError": 3, "send": 2, "receive": 3,
    "lock": 1, "unlock": 1,
    "select": 1, "selectCase": 3, "runSelect": 1,
    "interval": 1, "startInterval": 1, "awaitIntervalTick": 1,
    "workerPool": 1, "work": 1, "workArg": 3, "submitWork": 2, "awaitWork": 1,
    # Guard tokens
    "guardTokenSource": 2, "guardTokenOwner": 2,
    "guardTokenProtects": 2, "guardTokenRelease": 2,
    # Collections
    "listType": 2, "arrayType": 2, "arrayLength": 2, "sliceType": 2,
    "smallListType": 2, "smallListInlineCapacity": 2, "smallListSpillAllocator": 2,
    "mapType": 1, "mapKey": 2, "mapValue": 2,
    # Runtime bindings
    "runtimeBinding": 2, "intrinsicName": 2,
    # Constants
    "const": 3, "var": 3,
}


# Verbs that reference a `call NAME TARGET` declaration at args[0]. Used by
# SS4101 reference-integrity checks.
CALL_REFERENCE_VERBS_AT_ARG_ZERO: frozenset = frozenset({
    "arg", "run", "start", "await",
    "ignoreOk", "ignoreValue", "branchIfError",
    "timeout", "cancelOn", "useRetry",
    "startInGroup",
})

# Verbs that reference a call at args[2] (bind/bindOk/bindError).
CALL_REFERENCE_VERBS_AT_ARG_TWO: frozenset = frozenset({
    "bind", "bindOk", "bindError",
})

# Verbs that reference a label at args[0].
LABEL_REFERENCE_VERBS_AT_ARG_ZERO: frozenset = frozenset({"branch"})

# Verbs that reference a label at args[1].
LABEL_REFERENCE_VERBS_AT_ARG_ONE: frozenset = frozenset({
    "branchIf", "branchIfError", "branchIfGroupError", "branchIfChannelClosed",
})

# Verbs whose first argument names an OPERATION (narrative attachments,
# memory edges, etc.). Used by SS4104 unresolved-attachment-target check.
OPERATION_ATTACHMENT_VERBS: frozenset = frozenset({
    "input", "output", "effect", "async",
    "purpose", "invariant", "warning", "precondition",
    "guarantee", "failure",
    "security", "timing", "observability",
    "memory", "memoryHeap", "memoryArena",
    "memoryAllocationSource", "memoryStackLimit",
    "operationBody", "useCapability", "authority",
    # SS36xx explicit contract verbs — args[0] is the owning operation.
    "pinsNullBodyFailurePath",
    "responseBodyForwarder",
})


# Comprehensive vocabulary built from SYNTAX.md. Verbs missing from this
# set are reported as SS0001 unknownVerb at T0 (parse / grammar). Additive
# refinements to SemanticScript land in SYNTAX.md first, then in this set — keeping
# both in lockstep is the linter's job over time.
KNOWN_AGENT_SCRIPT_VERBS: frozenset = frozenset({
    # Project structure
    "project", "target", "runtime", "entry", "module", "mode",
    "buildProject", "modulePath", "languageVersion", "sourceRoot",
    "mainFile", "mainOperation", "testPattern", "dependency", "dependencySource",
    "dependencyFetch", "dependencyCache", "dependencyLock", "dependencyIntegrity",
    "buildProfile", "runtimeChecks", "persistLlvmIr",
    "nativeOutput", "targetRuntime", "comptimeOperation", "registerModule",
    "projectVersion", "projectLicense", "testRoot", "nativeHttpHost",
    "nativeHttpPort", "formatterSetting", "linterSetting", "docsOutput",
    "optLevel", "emitLlvmIr", "llvmIrOutput", "emitOptimizedLlvmIr",
    "optimizedLlvmIrOutput", "buildDir", "buildRoot", "buildFolderName",
    "cpuBaseline", "cpuTune", "cpuFeature", "cpuFeatureCheck",
    "keepResources", "resourcesDir",
    "moduleFolder", "modulePurpose", "moduleOwns", "moduleDoesNotOwn",
    "moduleDependency", "moduleWarning", "moduleInvariant", "moduleSecurity",
    "moduleObservability",
    "exportType", "exportError", "exportOperation", "exportCapability",
    "exportConstant",
    "iconRoleDefinition", "icon", "iconRole", "iconPurpose",
    "iconImage", "iconImageGroup", "iconImagePath", "iconImageFormat",
    "iconImageWidth", "iconImageHeight", "iconImageScale", "iconImageDepth",
    "iconImagePlatform", "iconImagePurpose",
    # Project metadata (lowered to OS-native formats — Windows VERSIONINFO —
    # at --emit-exe; values are still parsed and indexed on other platforms
    # so future tooling and IDE tooltips can read them).
    "version", "publisher", "description", "copyright", "productName",
    "internalName", "originalFilename", "trademark", "comments", "metadata",
    # Imports & sections
    "importModule", "importOperation", "importType", "importError",
    "importCapability", "importConstant", "section",
    # Groups
    "group", "groupPurpose", "groupInput", "groupOutput", "groupError",
    "groupFailure", "groupTiming",
    # Types
    "type", "typeInvariant", "typeRepresentation", "typeTrust", "typeMemory",
    "typeLayout", "typeParameter", "typeLiteralEncoding", "typeLiteralTerminator",
    # Records
    "record", "field", "recordLayout", "recordAlign", "recordConstructor",
    "recordConstructorFailure", "recordBuilder", "recordSet", "recordBuild",
    "recordBuildFailure", "new", "fieldSet", "fieldGet",
    # Errors / enums
    "error", "errorCase", "enum", "enumCase",
    # Operations + narrative
    "operation", "operationBody", "input", "output", "effect",
    "memory", "memoryHeap", "memoryArena", "memoryAllocationSource", "memoryStackLimit",
    "async", "purpose", "invariant", "warning", "precondition",
    "guarantee", "failure",
    "security", "timing", "observability",
    # Storage / shared state
    "storage", "sharedState", "set", "read",
    "sharedStateOwner", "sharedStateGuard",
    # Domain literals
    "domainLiteral", "domainLiteralSource", "domainLiteralTrust", "domainLiteralValidation",
    # Literals
    "literal", "literalBytes", "literalDigest", "literalPreview",
    "literalSource", "literalTrust",
    # Calls
    "call", "arg", "timeout", "cancelOn", "run", "start", "await",
    "bind", "bindOk", "bindError", "ignoreOk", "ignoreValue",
    "makeError", "declareFailure",
    # Control flow
    "label", "branch", "branchIf", "branchIfError",
    "returnOk", "returnError", "returnValue", "returnVoid",
    # Dependencies
    "dependency", "dependencyEffect", "dependencyExports",
    "dependencyFunction", "dependencyFunctionInput", "dependencyFunctionOutput",
    "dependencyFunctionEffect", "dependencyFunctionAsync",
    "dependencyPath", "dependencyFailure",
    # Capabilities
    "capability", "useCapability", "authority",
    # Resources
    "resource", "resourceKey", "resourceValue", "resourceKind",
    # Codecs
    "codec", "schema", "unknownFields",
    "jsonCodec", "jsonCodecStrict", "jsonCodecUnknownFields",
    "jsonCodecInput", "jsonCodecOutput",
    "jsonCodecDecodeTarget", "jsonCodecEncodeTarget",
    "jsonCodecRequiredField", "jsonCodecDecodeFailure", "jsonCodecEncodeFailure",
    "jsonCodecLimit",
    # Validation
    "validator", "mapper", "adapter", "boundary",
    # Policies
    "policy", "retryPolicy", "retryMaxAttempts", "retryInitialDelay",
    "retryMaximumDelay", "retryJitter", "useRetry",
    "errorPolicy", "timeoutBudget",
    # Trust boundaries
    "trustBoundary", "trustBoundaryKind", "trustBoundaryInput",
    "trustBoundaryOutput", "trustBoundaryValidator", "trustBoundarySource",
    # Web
    "webServer", "serverHost", "serverPort", "route",
    "routeTimeout", "routeMiddleware",
    "htmlTemplate", "htmlArg", "htmlBody",
    # SS3604 coverage opt-outs — declare a route's intentional omission
    # of the cross-cutting timeout / middleware contract.
    "routeTimeoutOptOut", "routeMiddlewareOptOut",
    # SS36xx explicit contract verbs (per-operation declarations that the
    # webserver-discipline checkers cite instead of inferring from
    # arg-name shapes or warning-text marker phrases)
    "pinsNullBodyFailurePath",
    "responseBodyForwarder",
    # `rationale CALL "text"` — call-site rationale; sister to the
    # `# rationale:` typed comment, but explicit enough that diagnostics
    # can cite it by call-name reference.
    "rationale",
    # Defer / cleanup
    "defer", "deferLog", "deferLogSink", "deferRunOn", "deferOrder",
    "deferFailurePolicy", "deferConsumes",
    "deferAwaitLog", "deferAwaitLogSink", "deferAwaitTimeout",
    "deferWhenExitLog", "deferWhenExitLogSink",
    # Guard tokens
    "guardTokenSource", "guardTokenOwner", "guardTokenProtects", "guardTokenRelease",
    # Concurrency
    "taskGroup", "startInGroup", "awaitGroup", "bindGroupError",
    "branchIfGroupError", "send", "receive", "branchIfChannelClosed",
    "lock", "unlock", "select", "selectCase", "runSelect", "branchSelected",
    "interval", "startInterval", "awaitIntervalTick",
    "workerPool", "work", "workArg", "submitWork", "awaitWork",
    # Collections
    "listType", "listAllocator",
    "arrayType", "arrayLength",
    "sliceType",
    "smallListType", "smallListInlineCapacity", "smallListSpillAllocator",
    "mapType", "mapKey", "mapValue", "mapAllocator",
    "collectionOperation", "collectionOperationArg", "collectionOperationOutput",
    "collectionOperationFailure", "collectionOperationEffect",
    "collectionOperationAllocation", "collectionOperationMutation",
    "collectionOperationIndexPolicy", "collectionOperationLengthSource",
    "collectionOperationCapacitySource", "collectionOperationBorrowSource",
    "collectionOperationSpillAllocator", "collectionOperationSpillFailure",
    "listLiteral", "listLiteralLength", "listLiteralIndexBase",
    "listLiteralIndexPolicy", "listLiteralItem",
    # Runtime bindings
    "runtimeBinding", "runtimeBindingPrecondition", "runtimeBindingFailure",
    "intrinsicName",
    # Token literals that may appear standalone
    "const", "var", "testCovers",
})


# ==========================================================================
# Diagnostic record
# ==========================================================================

@dataclass
class Span:
    path: Path
    line: int
    column: int = 1
    role: str = ""

    def to_json(self) -> Dict[str, object]:
        return {
            "path": str(self.path),
            "line": self.line,
            "column": self.column,
            "role": self.role,
        }


@dataclass
class Citation:
    span: Span
    edgeKind: str        # the narrative edge being cited: purpose|rationale|invariant|…
    text: str            # the quoted text from the source

    def to_json(self) -> Dict[str, object]:
        return {
            "span": self.span.to_json(),
            "edgeKind": self.edgeKind,
            "text": self.text,
        }


@dataclass
class FixCandidate:
    name: str
    shape: str
    autoApplicable: bool = False
    evidence: List[Span] = field(default_factory=list)

    def to_json(self) -> Dict[str, object]:
        return {
            "name": self.name,
            "shape": self.shape,
            "autoApplicable": self.autoApplicable,
            "evidence": [evidenceSpan.to_json() for evidenceSpan in self.evidence],
        }


@dataclass
class Diagnostic:
    # Identification
    tier: Tier
    code: str                          # e.g. "SS0101"
    kind: str                          # e.g. "unusedDeclaration.call"
    severity: Severity

    # Primary span is required — every diagnostic must point at one place.
    primary: Span

    # Structured subject (pattern-matchable; agents read these, not English)
    subjectName: str = ""              # the SemanticScript identifier the diagnostic is about
    subjectKind: str = ""              # operation | call | label | capability | …
    gapEdge: str = ""                  # SemanticScript edge that's missing (useCapability, retryMaxAttempts, …)

    # Short slogan, ≤6 tokens, no full sentences
    intentSlogan: str = ""

    # Additional spans (cause site, effect source, missing-catch site, …)
    related: List[Span] = field(default_factory=list)

    # Rule + spec anchor
    invariantRule: str = ""
    specAnchor: str = ""

    # Citations: the author's existing narrative attachments and rationale comments
    citations: List[Citation] = field(default_factory=list)

    # Fixes
    fixCandidates: List[FixCandidate] = field(default_factory=list)

    # Workflow metadata
    confidence: Confidence = Confidence.HIGH
    blocksCompile: bool = False
    prerequisite: List[str] = field(default_factory=list)
    effort: Effort = Effort.LOCAL
    passProvenance: str = ""
    agentHint: str = ""

    def to_json(self) -> Dict[str, object]:
        return {
            "tier": self.tier.value,
            "code": self.code,
            "kind": self.kind,
            "severity": self.severity.value,
            "subjectName": self.subjectName,
            "subjectKind": self.subjectKind,
            "gapEdge": self.gapEdge,
            "intentSlogan": self.intentSlogan,
            "primary": self.primary.to_json(),
            "related": [span.to_json() for span in self.related],
            "invariantRule": self.invariantRule,
            "specAnchor": self.specAnchor,
            "citations": [citation.to_json() for citation in self.citations],
            "fixCandidates": [fix.to_json() for fix in self.fixCandidates],
            "confidence": self.confidence.value,
            "blocksCompile": self.blocksCompile,
            "prerequisite": list(self.prerequisite),
            "effort": self.effort.value,
            "passProvenance": self.passProvenance,
            "agentHint": self.agentHint,
        }


def span_of_line(sourceLine: SourceLine, role: str = "") -> Span:
    return Span(
        path=sourceLine.path,
        line=sourceLine.number,
        column=sourceLine.column,
        role=role,
    )


# ==========================================================================
# Extended facts — augments base ProgramFacts with everything checkers need
# ==========================================================================

@dataclass
class CapabilityFact:
    name: str
    line: SourceLine
    # Effect-path + access action this capability authorises. Populated from
    # `capability NAME EFFECT_PATH ACCESS` rows. Used by SS3104 to reuse an
    # existing capability when its path matches a missing-proof effect.
    effectPath: str = ""
    accessAction: str = ""


@dataclass
class LabelFact:
    name: str
    line: SourceLine
    operationName: str


@dataclass
class ErrorCaseFact:
    errorName: str
    variant: str
    line: SourceLine


@dataclass
class RetryPolicyFact:
    name: str
    line: SourceLine
    hasMaxAttempts: bool = False
    hasInitialDelay: bool = False
    hasMaximumDelay: bool = False
    hasJitter: bool = False


@dataclass
class TrustBoundaryFact:
    typeName: str
    line: SourceLine
    hasInput: bool = False
    hasOutput: bool = False
    hasValidator: bool = False


@dataclass
class StorageFact:
    name: str
    line: SourceLine
    scope: str                         # local | module | sharedState
    mutability: str                    # mutable | immutable


@dataclass
class LiteralFact:
    name: str
    line: SourceLine
    typeName: str
    hasExternalSource: bool = False
    hasDigest: bool = False
    hasTrust: bool = False
    hasBytes: bool = False


@dataclass
class SharedStateAccessFact:
    line: SourceLine
    accessKind: str                    # "set" | "read"
    slotName: str
    hasProtection: bool                # whether `protectedBy <token>` clause present
    protectedByToken: Optional[str] = None


@dataclass
class ExportContractEdge:
    moduleName: str
    exportVerb: str
    symbolName: str
    edgeKind: str
    values: Tuple[str, ...]
    line: SourceLine


@dataclass
class ConstantDeclarationFact:
    name: str
    line: SourceLine
    typeName: str
    value: str
    scope: str = "module"
    mutability: str = "immutable"
    declarationVerb: str = "const"


@dataclass
class ImportedModuleContract:
    moduleName: str
    alias: str
    sourcePath: Path
    importLine: SourceLine
    exportsByKind: Dict[str, Set[str]]
    contractTape: List[ExportContractEdge]


@dataclass
class ImportedSymbolContract:
    kind: str
    localName: str
    qualifiedName: str
    moduleAlias: str
    moduleName: str
    exportedName: str
    edges: List[ExportContractEdge]
    importLine: SourceLine


@dataclass
class ImportContractIndex:
    modulesByAlias: Dict[str, ImportedModuleContract] = field(default_factory=dict)
    qualifiedSymbols: Dict[str, ImportedSymbolContract] = field(default_factory=dict)
    singularSymbols: Dict[str, ImportedSymbolContract] = field(default_factory=dict)


@dataclass
class ExtendedFacts:
    base: ProgramFacts
    # Declarations indexed by name (or composite key) for unused-detection
    capabilities: Dict[str, CapabilityFact] = field(default_factory=dict)
    capabilityUses: Set[str] = field(default_factory=set)
    labels: Dict[str, LabelFact] = field(default_factory=dict)
    labelReferences: Set[str] = field(default_factory=set)
    errorCases: Dict[Tuple[str, str], ErrorCaseFact] = field(default_factory=dict)
    errorCaseUses: Set[Tuple[str, str]] = field(default_factory=set)
    retryPolicies: Dict[str, RetryPolicyFact] = field(default_factory=dict)
    trustBoundaries: Dict[str, TrustBoundaryFact] = field(default_factory=dict)
    storageSlots: Dict[str, StorageFact] = field(default_factory=dict)
    storageWrites: Set[str] = field(default_factory=set)
    storageReads: Set[str] = field(default_factory=set)
    literals: Dict[str, LiteralFact] = field(default_factory=dict)
    sharedStateAccesses: List[SharedStateAccessFact] = field(default_factory=list)
    # Per-operation indices
    operationEffects: Dict[str, List[SourceLine]] = field(default_factory=dict)
    operationUseCapability: Dict[str, List[SourceLine]] = field(default_factory=dict)
    operationAuthority: Dict[str, List[SourceLine]] = field(default_factory=dict)
    # Narrative attachments per operation; lines preserved so checkers can cite
    operationNarrative: Dict[str, Dict[str, SourceLine]] = field(default_factory=dict)
    operationRationale: Dict[str, List[Citation]] = field(default_factory=dict)
    # Memory discipline: `memoryHeap OP yes|no` and `memoryAllocationSource OP CALL`
    operationMemoryHeapAllowed: Dict[str, Tuple[SourceLine, bool]] = field(default_factory=dict)
    operationMemoryAllocationSource: Dict[str, List[SourceLine]] = field(default_factory=dict)
    operationMemoryStackLimitBytes: Dict[str, Tuple[SourceLine, int]] = field(default_factory=dict)
    # Per-op defers — list of (declaring line, target verb-or-op name)
    operationDefers: Dict[str, List[Tuple[SourceLine, str]]] = field(default_factory=dict)
    # Layout discipline tracking
    recordAlignDeclarations: Dict[str, Tuple[SourceLine, int]] = field(default_factory=dict)
    smallListInlineCapacities: Dict[str, Tuple[SourceLine, int]] = field(default_factory=dict)
    smallListSpillAllocators: Dict[str, SourceLine] = field(default_factory=dict)
    arrayLengthDeclarations: Dict[str, Tuple[SourceLine, int]] = field(default_factory=dict)
    typesWithLiteralEncoding: Set[str] = field(default_factory=set)
    # Concurrency primitives — per-operation paired-handle tracking
    operationStartInGroup: Dict[str, List[Tuple[SourceLine, str]]] = field(default_factory=dict)
    operationAwaitedGroups: Dict[str, Set[str]] = field(default_factory=dict)
    operationLockSites: Dict[str, List[Tuple[SourceLine, str]]] = field(default_factory=dict)
    operationUnlockedMutexes: Dict[str, Set[str]] = field(default_factory=dict)
    operationDeferUnlockedMutexes: Dict[str, Set[str]] = field(default_factory=dict)
    operationSubmittedWork: Dict[str, List[Tuple[SourceLine, str]]] = field(default_factory=dict)
    operationAwaitedWork: Dict[str, Set[str]] = field(default_factory=dict)
    # Module-scope select / case tracking
    selectDeclarations: Dict[str, SourceLine] = field(default_factory=dict)
    selectCasesBySelectName: Dict[str, List[SourceLine]] = field(default_factory=dict)
    # Guard token paired tracking
    guardTokenSourceDeclarations: Dict[str, SourceLine] = field(default_factory=dict)
    guardTokenProtectsDeclarations: Dict[str, Set[str]] = field(default_factory=dict)
    guardTokenReleaseDeclarations: Set[str] = field(default_factory=set)
    # JSON codec tracking
    jsonCodecDeclarations: Dict[str, SourceLine] = field(default_factory=dict)
    jsonCodecHasInput: Set[str] = field(default_factory=set)
    jsonCodecHasOutput: Set[str] = field(default_factory=set)
    jsonCodecHasDecodeTarget: Set[str] = field(default_factory=set)
    jsonCodecHasEncodeTarget: Set[str] = field(default_factory=set)
    jsonCodecGeneratedTargets: Dict[str, SourceLine] = field(default_factory=dict)
    codecDeclarations: Dict[str, SourceLine] = field(default_factory=dict)
    collectionTypeDeclarations: Dict[str, SourceLine] = field(default_factory=dict)
    collectionOperationDeclarations: Dict[str, SourceLine] = field(default_factory=dict)
    # P10 — `rationale CALL "text"` verb attaches a rationale to a
    # specific call name within an operation. Sister to the `# rationale:`
    # typed comment (which attaches to the operation), but explicit
    # enough that diagnostics can cite it by call-name lookup rather
    # than by comment proximity. Keyed by (operationName, callName).
    callRationales: Dict[Tuple[str, str], Citation] = field(default_factory=dict)


def gather_extended(baseFacts: ProgramFacts) -> ExtendedFacts:
    facts = ExtendedFacts(base=baseFacts)
    currentOperation: Optional[str] = None

    for sourceLine in baseFacts.lines:
        if not sourceLine.tokens:
            continue

        if is_comment(sourceLine):
            commentBody = comment_text(sourceLine)
            if commentBody.startswith("rationale:") and currentOperation:
                facts.operationRationale.setdefault(currentOperation, []).append(
                    Citation(
                        span=span_of_line(sourceLine, "rationaleComment"),
                        edgeKind="rationale",
                        text=commentBody[len("rationale:"):].strip(),
                    )
                )
            continue

        verb = sourceLine.verb
        args = sourceLine.args

        if verb == "rationale" and currentOperation and len(args) >= 2:
            # `rationale CALL "text"` — args[0] is the call name; the
            # rest is rationale text (the parser keeps quoted text as
            # one token, but allow whitespace-joined fallback for tools
            # that emit unquoted multi-token bodies).
            callName = args[0]
            rationaleText = " ".join(args[1:]).strip()
            facts.callRationales[(currentOperation, callName)] = Citation(
                span=span_of_line(sourceLine, "callRationale"),
                edgeKind="rationale",
                text=rationaleText,
            )
            # Also surface in the per-op rationale list so the existing
            # narrative_citations_for_operation walk picks it up.
            facts.operationRationale.setdefault(currentOperation, []).append(
                facts.callRationales[(currentOperation, callName)]
            )
            continue

        if verb == "operation" and args:
            currentOperation = args[0]
            facts.operationNarrative.setdefault(currentOperation, {})
            continue

        if verb in NARRATIVE_EDGES and args:
            owner = args[0]
            facts.operationNarrative.setdefault(owner, {})[verb] = sourceLine

        if verb == "capability" and args:
            # `capability NAME EFFECT_PATH ACCESS`
            facts.capabilities[args[0]] = CapabilityFact(
                name=args[0],
                line=sourceLine,
                effectPath=args[1] if len(args) >= 2 else "",
                accessAction=args[2] if len(args) >= 3 else "",
            )
        elif verb == "useCapability" and len(args) >= 2:
            facts.capabilityUses.add(args[1])
            facts.operationUseCapability.setdefault(args[0], []).append(sourceLine)
        elif verb == "authority" and args:
            facts.operationAuthority.setdefault(args[0], []).append(sourceLine)
        elif verb == "label" and args and currentOperation:
            facts.labels[args[0]] = LabelFact(args[0], sourceLine, currentOperation)
        elif verb == "branch" and args:
            facts.labelReferences.add(args[0])
        elif verb == "branchIf" and len(args) >= 2:
            facts.labelReferences.add(args[1])
            if len(args) >= 3:
                facts.labelReferences.add(args[2])
        elif verb in {"branchIfError", "branchIfGroupError", "branchIfChannelClosed"} and len(args) >= 2:
            facts.labelReferences.add(args[1])
        elif verb == "branchSelected" and len(args) >= 3:
            facts.labelReferences.add(args[2])
        elif verb == "errorCase" and len(args) >= 2:
            facts.errorCases[(args[0], args[1])] = ErrorCaseFact(args[0], args[1], sourceLine)
        elif verb in {"makeError", "declareFailure"} and len(args) >= 2:
            dotted = args[1]
            if "." in dotted:
                errorName, variant = dotted.split(".", 1)
                facts.errorCaseUses.add((errorName, variant))
        elif verb == "retryPolicy" and args:
            facts.retryPolicies[args[0]] = RetryPolicyFact(args[0], sourceLine)
        elif verb == "retryMaxAttempts" and args:
            retryPolicyFact = facts.retryPolicies.get(args[0])
            if retryPolicyFact:
                retryPolicyFact.hasMaxAttempts = True
        elif verb == "retryInitialDelay" and args:
            retryPolicyFact = facts.retryPolicies.get(args[0])
            if retryPolicyFact:
                retryPolicyFact.hasInitialDelay = True
        elif verb == "retryMaximumDelay" and args:
            retryPolicyFact = facts.retryPolicies.get(args[0])
            if retryPolicyFact:
                retryPolicyFact.hasMaximumDelay = True
        elif verb == "retryJitter" and args:
            retryPolicyFact = facts.retryPolicies.get(args[0])
            if retryPolicyFact:
                retryPolicyFact.hasJitter = True
        elif verb == "trustBoundary" and args:
            facts.trustBoundaries[args[0]] = TrustBoundaryFact(args[0], sourceLine)
        elif verb == "trustBoundaryInput" and args:
            trustBoundaryFact = facts.trustBoundaries.get(args[0])
            if trustBoundaryFact:
                trustBoundaryFact.hasInput = True
        elif verb == "trustBoundaryOutput" and args:
            trustBoundaryFact = facts.trustBoundaries.get(args[0])
            if trustBoundaryFact:
                trustBoundaryFact.hasOutput = True
        elif verb == "trustBoundaryValidator" and args:
            trustBoundaryFact = facts.trustBoundaries.get(args[0])
            if trustBoundaryFact:
                trustBoundaryFact.hasValidator = True
        elif verb == "storage" and len(args) >= 4:
            # storage SCOPE MUTABILITY NAME TYPE INIT
            scope, mutability, name = args[0], args[1], args[2]
            facts.storageSlots[name] = StorageFact(name, sourceLine, scope, mutability)
        elif verb == "sharedState" and len(args) >= 4:
            scope, mutability, name = args[0], args[1], args[2]
            facts.storageSlots[name] = StorageFact(name, sourceLine, f"sharedState.{scope}", mutability)
        elif verb == "set" and len(args) >= 2:
            # set SCOPE NAME VALUE [ownedBy|protectedBy …]
            facts.storageWrites.add(args[1])
            if args[0] == "sharedState":
                protectedByToken = _metadata_value(args, "protectedBy")
                facts.sharedStateAccesses.append(SharedStateAccessFact(
                    line=sourceLine,
                    accessKind="set",
                    slotName=args[1],
                    hasProtection=protectedByToken is not None,
                    protectedByToken=protectedByToken,
                ))
        elif verb == "read" and len(args) >= 4:
            # read sharedState BINDING TYPE BACKING [protectedBy GUARD]
            facts.storageReads.add(args[3])
            if args[0] == "sharedState":
                protectedByToken = _metadata_value(args, "protectedBy")
                facts.sharedStateAccesses.append(SharedStateAccessFact(
                    line=sourceLine,
                    accessKind="read",
                    slotName=args[3],
                    hasProtection=protectedByToken is not None,
                    protectedByToken=protectedByToken,
                ))
        elif verb == "literal" and len(args) >= 2:
            facts.literals[args[0]] = LiteralFact(args[0], sourceLine, args[1])
        elif verb == "literalSource" and args:
            literalFact = facts.literals.get(args[0])
            if literalFact:
                literalFact.hasExternalSource = True
        elif verb == "literalDigest" and args:
            literalFact = facts.literals.get(args[0])
            if literalFact:
                literalFact.hasDigest = True
        elif verb == "literalTrust" and args:
            literalFact = facts.literals.get(args[0])
            if literalFact:
                literalFact.hasTrust = True
        elif verb == "literalBytes" and args:
            literalFact = facts.literals.get(args[0])
            if literalFact:
                literalFact.hasBytes = True
        elif verb == "effect" and len(args) >= 3:
            facts.operationEffects.setdefault(args[0], []).append(sourceLine)
        elif verb == "memoryHeap" and len(args) >= 2:
            heapAllowed = args[1].lower() in {"yes", "true"}
            facts.operationMemoryHeapAllowed[args[0]] = (sourceLine, heapAllowed)
        elif verb == "memoryAllocationSource" and len(args) >= 2:
            facts.operationMemoryAllocationSource.setdefault(args[0], []).append(sourceLine)
        elif verb == "memoryStackLimit" and len(args) >= 2:
            try:
                stackLimitBytes = int(args[1])
                facts.operationMemoryStackLimitBytes[args[0]] = (sourceLine, stackLimitBytes)
            except ValueError:
                # Domain literal reference — skip until we resolve const facts
                pass
        elif verb in {"defer", "deferLog", "deferAwaitLog", "deferWhenExitLog"} and len(args) >= 2 and currentOperation:
            # `defer NAME TARGET ARGS...` — args[1] is the cleanup target
            facts.operationDefers.setdefault(currentOperation, []).append(
                (sourceLine, args[1])
            )
            # If the deferred target is `unlock` and an explicit mutex name
            # follows in ARGS, record it for SS3503 cleanup pairing.
            if args[1] == "unlock" and len(args) >= 3:
                facts.operationDeferUnlockedMutexes.setdefault(
                    currentOperation, set()
                ).add(args[2])
        elif verb == "recordAlign" and len(args) >= 2:
            try:
                facts.recordAlignDeclarations[args[0]] = (sourceLine, int(args[1]))
            except ValueError:
                pass
        elif verb == "smallListInlineCapacity" and len(args) >= 2:
            try:
                facts.smallListInlineCapacities[args[0]] = (sourceLine, int(args[1]))
            except ValueError:
                pass
        elif verb == "smallListSpillAllocator" and len(args) >= 2:
            facts.smallListSpillAllocators[args[0]] = sourceLine
        elif verb == "arrayLength" and len(args) >= 2:
            try:
                facts.arrayLengthDeclarations[args[0]] = (sourceLine, int(args[1]))
            except ValueError:
                pass
        elif verb == "typeLiteralEncoding" and len(args) >= 1:
            facts.typesWithLiteralEncoding.add(args[0])
        # Concurrency primitive tracking
        elif verb == "startInGroup" and len(args) >= 2 and currentOperation:
            # `startInGroup CALL GROUP_NAME` — track per-op (line, group_name)
            facts.operationStartInGroup.setdefault(currentOperation, []).append(
                (sourceLine, args[1])
            )
        elif verb == "awaitGroup" and args and currentOperation:
            facts.operationAwaitedGroups.setdefault(currentOperation, set()).add(args[0])
        elif verb == "lock" and args and currentOperation:
            facts.operationLockSites.setdefault(currentOperation, []).append(
                (sourceLine, args[0])
            )
        elif verb == "unlock" and args and currentOperation:
            facts.operationUnlockedMutexes.setdefault(currentOperation, set()).add(args[0])
        elif verb == "submitWork" and len(args) >= 2 and currentOperation:
            # `submitWork WORK POOL` — first arg is the work item name
            facts.operationSubmittedWork.setdefault(currentOperation, []).append(
                (sourceLine, args[0])
            )
        elif verb == "awaitWork" and args and currentOperation:
            facts.operationAwaitedWork.setdefault(currentOperation, set()).add(args[0])
        # Module-scope select / selectCase tracking
        elif verb == "select" and args:
            facts.selectDeclarations[args[0]] = sourceLine
        elif verb == "selectCase" and args:
            facts.selectCasesBySelectName.setdefault(args[0], []).append(sourceLine)
        # Guard token source/release pairing
        elif verb == "guardTokenSource" and args:
            facts.guardTokenSourceDeclarations[args[0]] = sourceLine
        elif verb == "guardTokenProtects" and len(args) >= 2:
            facts.guardTokenProtectsDeclarations.setdefault(args[0], set()).add(args[1])
        elif verb == "guardTokenRelease" and args:
            facts.guardTokenReleaseDeclarations.add(args[0])
        # JSON codec completeness tracking
        elif verb == "jsonCodec" and args:
            facts.jsonCodecDeclarations[args[0]] = sourceLine
        elif verb == "codec" and args:
            facts.codecDeclarations[args[0]] = sourceLine
        elif verb == "jsonCodecInput" and args:
            facts.jsonCodecHasInput.add(args[0])
        elif verb == "jsonCodecOutput" and args:
            facts.jsonCodecHasOutput.add(args[0])
        elif verb == "jsonCodecDecodeTarget" and args:
            facts.jsonCodecHasDecodeTarget.add(args[0])
            if len(args) >= 2:
                facts.jsonCodecGeneratedTargets[args[1]] = sourceLine
        elif verb == "jsonCodecEncodeTarget" and args:
            facts.jsonCodecHasEncodeTarget.add(args[0])
            if len(args) >= 2:
                facts.jsonCodecGeneratedTargets[args[1]] = sourceLine
        elif verb in {"listType", "arrayType", "sliceType", "smallListType", "mapType"} and args:
            facts.collectionTypeDeclarations[args[0]] = sourceLine
        elif verb == "collectionOperation" and args:
            facts.collectionOperationDeclarations[args[0]] = sourceLine

    return facts


def _metadata_value(args: Sequence[str], key: str) -> Optional[str]:
    try:
        keyIndex = args.index(key)
    except ValueError:
        return None
    valueIndex = keyIndex + 1
    if valueIndex >= len(args):
        return None
    return args[valueIndex]


def narrative_citations_for_operation(facts: ExtendedFacts, operationName: str) -> List[Citation]:
    """Return Citation list for every narrative edge AND rationale comment
    attached to the given operation. Diagnostics on an operation should
    attach these so the agent sees the author's stated intent in context."""
    citations: List[Citation] = []
    edges = facts.operationNarrative.get(operationName, {})
    for edgeKind in NARRATIVE_EDGES:
        narrativeLine = edges.get(edgeKind)
        if not narrativeLine:
            continue
        # `purpose foo "the text"` → args = ["foo", "the text"]
        text = narrativeLine.args[1] if len(narrativeLine.args) >= 2 else ""
        citations.append(Citation(
            span=span_of_line(narrativeLine, f"narrative.{edgeKind}"),
            edgeKind=edgeKind,
            text=text,
        ))
    citations.extend(facts.operationRationale.get(operationName, []))
    return citations


# ==========================================================================
# Per-op call collection (mirrors semlint.py's logic, kept local for clarity)
# ==========================================================================

def collect_operation_calls(operation: OperationFact) -> Dict[str, CallFact]:
    operationCalls: Dict[str, CallFact] = {}
    for sourceLine in operation.lines:
        if is_comment(sourceLine) or not sourceLine.tokens:
            continue
        verb = sourceLine.verb
        args = sourceLine.args
        if verb == "call" and len(args) >= 2:
            operationCalls[args[0]] = CallFact(args[0], args[1], sourceLine)
            continue
        if not args:
            continue
        target = None
        # Most call-attachment verbs use args[0] as the call name
        if verb in {"arg", "run", "start", "await", "ignoreOk", "ignoreValue",
                    "branchIfError", "startInGroup", "timeout", "cancelOn"}:
            target = operationCalls.get(args[0])
        # bind/bindOk/bindError name the call at args[2]
        elif verb in {"bind", "bindOk", "bindError"} and len(args) >= 3:
            target = operationCalls.get(args[2])
        if target is None:
            continue
        if verb == "arg":
            target.arg_lines.append(sourceLine)
        elif verb == "run":
            target.run_lines.append(sourceLine)
        elif verb == "start":
            target.start_lines.append(sourceLine)
        elif verb == "await":
            target.await_lines.append(sourceLine)
        elif verb == "bind":
            target.bind_lines.append(sourceLine)
        elif verb == "bindOk":
            target.bind_ok_lines.append(sourceLine)
        elif verb == "bindError":
            target.bind_error_lines.append(sourceLine)
        elif verb == "ignoreOk":
            target.ignore_ok_lines.append(sourceLine)
        elif verb == "ignoreValue":
            target.ignore_value_lines.append(sourceLine)
        elif verb == "branchIfError":
            target.branch_error_lines.append(sourceLine)
        elif verb == "startInGroup":
            target.group_start_lines.append(sourceLine)
        elif verb == "timeout":
            target.timeout_lines.append(sourceLine)
        elif verb == "cancelOn":
            target.cancel_lines.append(sourceLine)
    return operationCalls


def call_success_value_names(callFact: CallFact) -> Set[str]:
    """Names that carry a call's successful return value in this operation."""
    names: Set[str] = set()
    for bindLine in callFact.bind_lines + callFact.bind_ok_lines:
        if bindLine.args:
            names.add(bindLine.args[0])
    return names


def call_has_value_disposition(callFact: CallFact) -> bool:
    """Whether a non-Result C-style call return is bound or explicitly ignored."""
    return bool(
        callFact.bind_lines
        or callFact.bind_ok_lines
        or callFact.ignore_value_lines
        or callFact.ignore_ok_lines
    )


def call_consumes_any_value(callFact: CallFact, valueNames: Set[str]) -> bool:
    if not valueNames:
        return False
    for argLine in callFact.arg_lines:
        if len(argLine.args) >= 3 and argLine.args[2] in valueNames:
            return True
    return False


def call_has_later_cleanup_call(
    resourceCall: CallFact,
    operationCalls: Dict[str, CallFact],
    cleanupTargets: Set[str],
) -> bool:
    """Return true when a later cleanup call consumes this call's bound value."""
    resourceValueNames = call_success_value_names(resourceCall)
    if not resourceValueNames:
        return False
    for cleanupCall in operationCalls.values():
        if cleanupCall.target not in cleanupTargets:
            continue
        if cleanupCall.line.number <= resourceCall.line.number:
            continue
        if call_consumes_any_value(cleanupCall, resourceValueNames):
            return True
    return False


# ==========================================================================
# Checkers
#
# Code ranges:
#   AS00xx — grammar / parse                  (T0 — non-overridable error)
#            SS0001 unknownVerb, SS0002 argumentArityTooFew
#   AS01xx — unused declarations              (T3 refinement)
#            SS0101 call, SS0102 label, SS0103 capability, SS0104 errorCase,
#            SS0105 mutableStorage, SS0106 bindSlot,
#            SS0107 const, SS0108 input
#   AS12xx — partial declarations             (T3 refinement)
#            SS1201 retryPolicy, SS1202 trustBoundary, SS1203 externalLiteral
#   AS31xx — operation / coverage gaps        (T3 refinement)
#            SS3101 missing purpose, SS3102 missing invariant,
#            SS3104 capabilityCoverage, SS3105 unprotectedSharedState,
#            SS3106 hiddenFailure, SS3107 siblingMetadataDrift,
#            SS3108 unsupportedSharedStateScope,
#            SS3111 undeclaredBodyEffect, SS3112 unknownErrorVariant
#   AS32xx — performance discipline           (T3 refinement)
#            SS3201 deadStore, SS3202 allocationInLoop,
#            SS3204 bindThenIgnore
#   AS33xx — memory / resource discipline     (T3 refinement)
#            SS3301 heapContradiction, SS3302 allocationSourceMissing,
#            SS3303 allocateFreeUnpaired, SS3304 stackLimitOverrun
#   AS34xx — layout / representation          (T3 refinement)
#            SS3401 recordAlignNotPowerOfTwo, SS3404 arrayLengthZero,
#            SS3405 inlineCapacityWithoutSpillAllocator,
#            SS3406 literalEncodingMissing
#   SS35xx — concurrency discipline           (T3 refinement)
#            SS3501 unawaitedTaskGroup, SS3503 lockWithoutCleanup,
#            SS3506 unawaitedSubmitWork, SS3507 selectWithoutCases,
#            SS3508 selectCaseReferencesUnknownSelect,
#            SS3510 asyncCallMissingBoundary
#   SS36xx — webserver discipline             (T3 refinement / T1 spec)
#            SS3601 invalidRouteMethod (whitelist: GET/HEAD/POST/PUT/PATCH/
#                   DELETE/OPTIONS; the native dispatcher silently never
#                   matches anything outside this set),
#            SS3602 middlewareMissingResponseEffect (ops bound via
#                   routeMiddleware must declare write http.response*),
#            SS3603 unguardedHttpInput (values bound from nullable
#                   http.request* reads passed to body of http.response*
#                   without a pointer.isNull guard; opt out per-op with
#                   `pinsNullBodyFailurePath OP "rationale"`),
#            SS3604 routeCoverageDrift (every route should have matching
#                   routeTimeout + routeMiddleware OR an explicit
#                   routeTimeoutOptOut / routeMiddlewareOptOut),
#            SS3605 legacyNullBodyMarker (deprecation pointer: the
#                   stringly-typed `null-body failure path` marker inside
#                   a `warning` line is the legacy form of the SS3603
#                   opt-out and should migrate to the verb; fires only
#                   when the marker is load-bearing, i.e. removing it
#                   would trip SS3603),
#            SS3606 pinsNullBodyFailurePathMissingRationale (the verb
#                   requires a non-empty rationale string),
#            SS3607 forwarderDeclarationNotHonored (responseBodyForwarder
#                   declarations must actually wire `arg <call> body
#                   <declaredArgName>` against a known writer),
#            SS3608 rationaleReferencesUnknownCall / rationaleMissingText
#                   (the `rationale CALL "text"` verb must name a real
#                   call AND carry non-empty text; orphan rationale is
#                   the strongest dangling-context signal),
#            SS3609 routeHandlerInputNameMismatch (route/middleware ops
#                   MUST declare HttpRequest input as `request` and
#                   HttpResponse input as `response` — graded ERROR +
#                   blocksCompile because the names are part of the
#                   native HTTP ABI's name-based-lookup contract),
#            SS3610 middlewareReturnNotMiddlewareControl (every
#                   `routeMiddleware`-bound op MUST declare `output OP
#                   MiddlewareControl` not bare CSignedInt32; ERROR +
#                   blocksCompile because the dispatcher's short-circuit
#                   semantics depend on the typed enum),
#            SS3612 voidReturnValueShouldBeReturnVoid (an op declared
#                   `output OP Void` should end with `returnVoid`, not
#                   `returnValue NAME` — the legacy form leaks the
#                   user-op ABI's i32 sentinel into the source),
#            SS3613 narrativeReferencesLineNumber (narrative attachments
#                   should cite STABLE identifiers — function names,
#                   rule IDs, grep-anchors — never `<file>:<line>` or
#                   `line <N>` patterns that drift on the next edit)
#   SS37xx — type system discipline           (T3 refinement)
#            SS3701 circularAlias
#   SS38xx — codec discipline                 (T3 refinement)
#            SS3801 jsonCodecIncomplete,
#            SS3802 generatedJsonRuntimeMissing,
#            SS3803 genericCodecRuntimeMissing,
#            SS3804 collectionRuntimeMissing
#   SS39xx — resource lifecycle               (T3 refinement)
#            SS3901 fileHandleNotClosed,
#            SS3903 guardTokenSourceWithoutRelease,
#            SS3904 guardTokenDoesNotProtectSharedState
#   AS40xx — style discipline                 (T4 style)
#            SS4001 callObjectSuffix, SS4002 bindErrorSuffix,
#            SS4003 makeErrorSuffix, SS4004 vagueName,
#            SS4005 semOneZeroLegacyForm, SS4006 declarationOnlySample
#   AS41xx — reference integrity              (T1 spec — blocks compile)
#            SS4101 unresolvedCall, SS4102 unresolvedLabel,
#            SS4103 unresolvedCapability,
#            SS4104 unresolvedOperationAttachment
#   AS42xx — duplicate declarations           (T1 spec — blocks compile)
#            SS4201 duplicateDeclaration (operation/label/call/type/record/
#                   error/capability/enum/retryPolicy/trustBoundary/jsonCodec)
#   AS43xx — type integrity                   (T1 spec — blocks compile)
#            SS4301 argumentTypeMismatch (resolves type aliases + primitive
#                   equivalences; skips unknowns to avoid false positives)
#   SS25xx â€” project module / export contracts
#            SS2501 missing registered module source, SS2502 export row in
#                   build tape, SS2503 unregistered module declaration,
#                   SS2504 unregistered import, SS2505 export target mismatch,
#                   SS2506 unknown export, SS2507 duplicate export,
#                   SS2508 mutable storage export, SS2509 non-module state
#                   export, SS2510 private import access, SS2511 exported
#                   op missing purpose, SS2512 generic exported name,
#                   SS2513 exported op undeclared effect, SS2514 exported
#                   dependency wrapper missing module ownership context
#            SS2530-SS2542 import alias, qualified-reference, singular-import,
#                   shadowing, implicit-import, import-cycle, and imported
#                   effect propagation contracts
#            SS2550-SS2555 dependency fetch/cache/lock/source/integrity
#                   build-tape contracts
# ==========================================================================

def check_unused_calls(facts: ExtendedFacts) -> List[Diagnostic]:
    diagnostics: List[Diagnostic] = []
    for operation in facts.base.operations.values():
        operationCalls = collect_operation_calls(operation)
        for callFact in operationCalls.values():
            executedSomewhere = bool(
                callFact.run_lines or callFact.start_lines or callFact.group_start_lines
            )
            referencedSomewhere = bool(
                callFact.bind_lines or callFact.bind_ok_lines or callFact.bind_error_lines
                or callFact.ignore_ok_lines or callFact.ignore_value_lines
                or callFact.branch_error_lines or callFact.await_lines
            )
            if executedSomewhere or referencedSomewhere:
                continue
            diagnostics.append(Diagnostic(
                tier=Tier.T3_REFINEMENT,
                code="SS0101",
                kind="unusedDeclaration.call",
                severity=Severity.WARNING,
                subjectName=callFact.name,
                subjectKind="call",
                gapEdge="executionSite",
                intentSlogan="call declared but never executed",
                primary=span_of_line(callFact.line, "callDeclaration"),
                related=[span_of_line(operation.line, "enclosingOperation")],
                invariantRule="every declared call must be either executed or referenced",
                specAnchor="SYNTAX.md#call",
                citations=narrative_citations_for_operation(facts, operation.name),
                fixCandidates=[
                    FixCandidate(
                        name="removeUnusedCall",
                        shape=f"# remove `call {callFact.name} {callFact.target}` and any `arg {callFact.name} …` lines",
                        autoApplicable=True,
                        evidence=[span_of_line(callFact.line)],
                    ),
                    FixCandidate(
                        name="addRunSite",
                        shape=f"run {callFact.name}",
                        evidence=[span_of_line(callFact.line)],
                    ),
                ],
                confidence=Confidence.HIGH,
                effort=Effort.TRIVIAL,
                passProvenance="check_unused_calls",
                agentHint="usually a refactor leftover; check enclosing operation's purpose citation before deletion",
            ))
    return diagnostics


def _is_entry_anchor_label(labelName: str, operationName: str) -> bool:
    """Stdlib convention: `label start<OperationNamePascalCase>` placed at the
    top of an operation body as a section anchor for readability — never
    branched to. 213 such labels across std. Treating these as unused
    drowns the queue, so we suppress that one shape and keep everything else."""
    expectedAnchor = "start" + operationName[:1].upper() + operationName[1:]
    return labelName == expectedAnchor


def check_unused_labels(facts: ExtendedFacts) -> List[Diagnostic]:
    diagnostics: List[Diagnostic] = []
    for labelName, labelFact in facts.labels.items():
        if labelName in facts.labelReferences:
            continue
        if _is_entry_anchor_label(labelName, labelFact.operationName):
            continue
        diagnostics.append(Diagnostic(
            tier=Tier.T3_REFINEMENT,
            code="SS0102",
            kind="unusedDeclaration.label",
            severity=Severity.WARNING,
            subjectName=labelName,
            subjectKind="label",
            gapEdge="branchReference",
            intentSlogan="label declared but unreachable",
            primary=span_of_line(labelFact.line, "labelDeclaration"),
            related=[span_of_line(facts.base.operations[labelFact.operationName].line, "enclosingOperation")]
                if labelFact.operationName in facts.base.operations else [],
            invariantRule="every declared label must be reachable via branch / branchIf*",
            specAnchor="SYNTAX.md#label",
            citations=narrative_citations_for_operation(facts, labelFact.operationName),
            fixCandidates=[
                FixCandidate(
                    name="removeUnusedLabel",
                    shape=f"# remove `label {labelName}`",
                    autoApplicable=True,
                    evidence=[span_of_line(labelFact.line)],
                ),
            ],
            confidence=Confidence.HIGH,
            effort=Effort.TRIVIAL,
            passProvenance="check_unused_labels",
            agentHint="if used as a readability anchor, convert to a `# group …` comment instead",
        ))
    return diagnostics


def check_unused_capabilities(facts: ExtendedFacts) -> List[Diagnostic]:
    diagnostics: List[Diagnostic] = []
    exportedCapabilities = {
        sourceLine.args[1]
        for sourceLine in facts.base.lines
        if sourceLine.tokens and not is_comment(sourceLine)
        and sourceLine.verb == "exportCapability"
        and len(sourceLine.args) >= 2
    }
    for capabilityName, capabilityFact in facts.capabilities.items():
        if capabilityName in facts.capabilityUses:
            continue
        if capabilityName in exportedCapabilities:
            continue
        diagnostics.append(Diagnostic(
            tier=Tier.T3_REFINEMENT,
            code="SS0103",
            kind="unusedDeclaration.capability",
            severity=Severity.WARNING,
            subjectName=capabilityName,
            subjectKind="capability",
            gapEdge="useCapability",
            intentSlogan="capability declared but unused",
            primary=span_of_line(capabilityFact.line, "capabilityDeclaration"),
            invariantRule="every declared capability must authorize at least one site",
            specAnchor="SYNTAX.md#capability",
            fixCandidates=[
                FixCandidate(
                    name="addUseCapabilityAtEffectSite",
                    shape=f"useCapability <op> {capabilityName}",
                ),
                FixCandidate(
                    name="removeUnusedCapability",
                    shape=f"# remove `capability {capabilityName} …` (only if confirmed dead)",
                ),
            ],
            confidence=Confidence.MEDIUM,
            effort=Effort.LOCAL,
            passProvenance="check_unused_capabilities",
            agentHint="capabilities are usually load-bearing — prefer wiring them to an effect site",
        ))
    return diagnostics


def check_unused_error_cases(facts: ExtendedFacts) -> List[Diagnostic]:
    diagnostics: List[Diagnostic] = []
    for (errorName, variant), errorCaseFact in facts.errorCases.items():
        if (errorName, variant) in facts.errorCaseUses:
            continue
        diagnostics.append(Diagnostic(
            tier=Tier.T3_REFINEMENT,
            code="SS0104",
            kind="unusedDeclaration.errorCase",
            severity=Severity.WARNING,
            subjectName=f"{errorName}.{variant}",
            subjectKind="errorCase",
            gapEdge="constructionSite",
            intentSlogan="errorCase declared but never raised",
            primary=span_of_line(errorCaseFact.line, "errorCaseDeclaration"),
            invariantRule="every errorCase variant should have at least one construction site",
            specAnchor="SYNTAX.md#errorCase",
            fixCandidates=[
                FixCandidate(
                    # Suffix the suggested name with `Failure` so applying
                    # this fix doesn't subsequently trip SS4003 (makeError
                    # naming discipline).
                    name="raiseAtFailurePath",
                    shape=f"makeError {variant[:1].lower()}{variant[1:]}Failure {errorName}.{variant}",
                ),
                FixCandidate(
                    name="removeUnusedErrorCase",
                    shape=f"# remove `errorCase {errorName} {variant}`",
                ),
            ],
            confidence=Confidence.MEDIUM,
            effort=Effort.LOCAL,
            passProvenance="check_unused_error_cases",
            agentHint="dead variants often signal incomplete error-path coverage, not a removable declaration",
        ))
    return diagnostics


def check_unused_mutable_storage(facts: ExtendedFacts) -> List[Diagnostic]:
    """Mutable storage / sharedState that's declared but never `set` is a
    strong signal of incomplete refactor or dead state. Immutable slots are
    skipped (declared-and-read is the whole point)."""
    diagnostics: List[Diagnostic] = []
    for storageName, storageFact in facts.storageSlots.items():
        if storageFact.mutability != "mutable":
            continue
        if storageName in facts.storageWrites:
            continue
        diagnostics.append(Diagnostic(
            tier=Tier.T3_REFINEMENT,
            code="SS0105",
            kind="unusedDeclaration.mutableStorage",
            severity=Severity.WARNING,
            subjectName=storageName,
            subjectKind=storageFact.scope,            # "local" | "module" | "sharedState.*"
            gapEdge="set",
            intentSlogan="mutable storage never mutated",
            primary=span_of_line(storageFact.line, "storageDeclaration"),
            invariantRule="mutable storage slots should be written via `set` at least once",
            specAnchor="SYNTAX.md#storage",
            fixCandidates=[
                FixCandidate(
                    name="demoteToImmutable",
                    shape=f"storage {storageFact.scope.replace('sharedState.', 'sharedState ')} immutable {storageName} <type> <init>",
                ),
                FixCandidate(
                    # For sharedState slots, include the `protectedBy` clause
                    # so applying this fix doesn't subsequently trip SS3105
                    # (unprotected sharedState access).
                    name="addSetSite",
                    shape=(
                        f"set {storageFact.scope.replace('sharedState.', 'sharedState ')} "
                        f"{storageName} <value>"
                        + (" protectedBy <guardTokenName>"
                           if storageFact.scope.startswith("sharedState") else "")
                    ),
                ),
                FixCandidate(
                    name="removeStorageSlot",
                    shape=f"# remove `storage {storageFact.scope} mutable {storageName} …`",
                ),
            ],
            confidence=Confidence.HIGH,
            effort=Effort.LOCAL,
            passProvenance="check_unused_mutable_storage",
            agentHint="immutable demotion preserves the value while removing mutation surface",
        ))
    return diagnostics


def check_partial_retry_policies(facts: ExtendedFacts) -> List[Diagnostic]:
    """Emit one diagnostic per policy listing every missing edge.
    Matches the shape of check_partial_trust_boundaries."""
    diagnostics: List[Diagnostic] = []
    for retryPolicyFact in facts.retryPolicies.values():
        missing: List[str] = []
        if not retryPolicyFact.hasMaxAttempts:
            missing.append("retryMaxAttempts")
        if not retryPolicyFact.hasInitialDelay:
            missing.append("retryInitialDelay")
        if not retryPolicyFact.hasMaximumDelay:
            missing.append("retryMaximumDelay")
        if not retryPolicyFact.hasJitter:
            missing.append("retryJitter")
        if not missing:
            continue
        # retryMaxAttempts is load-bearing: the lowering needs a bound. Other
        # edges (delay/jitter) tune behavior. Emit ONE diagnostic listing every
        # missing edge; if delay/jitter are missing and maxAttempts is also
        # missing, mark maxAttempts as the prerequisite so an agent walking the
        # queue fixes the load-bearing edge first.
        loadBearing = "retryMaxAttempts" in missing
        prerequisiteCodes: List[str] = []
        if loadBearing and len(missing) > 1:
            # Future iteration: emit a separate SS1201a diagnostic just for the
            # maxAttempts gap and reference it here. For v0.3 we surface the
            # ordering hint through the agentHint + intentSlogan.
            pass
        diagnostics.append(Diagnostic(
            tier=Tier.T3_REFINEMENT,
            code="SS1201",
            kind="partiallyDeclared.retryPolicy",
            severity=Severity.WARNING,
            subjectName=retryPolicyFact.name,
            subjectKind="retryPolicy",
            gapEdge=",".join(missing),
            intentSlogan="retryPolicy missing edges",
            primary=span_of_line(retryPolicyFact.line, "policyDeclaration"),
            invariantRule="retryPolicy should declare maxAttempts plus delay/jitter for predictable behavior",
            specAnchor="SYNTAX.md#retryPolicy",
            fixCandidates=[
                FixCandidate(
                    name=f"add{edgeName[0].upper()}{edgeName[1:]}",
                    shape=f"{edgeName} {retryPolicyFact.name} <value>",
                    autoApplicable=False,
                )
                for edgeName in missing
            ],
            confidence=Confidence.HIGH if loadBearing else Confidence.MEDIUM,
            effort=Effort.LOCAL,
            prerequisite=prerequisiteCodes,
            passProvenance="check_partial_retry_policies",
            agentHint=(
                "fix retryMaxAttempts first — the lowering needs a bound; "
                "delay/jitter knobs only tune an already-bounded policy"
            ) if loadBearing else "delay/jitter tune the existing bound",
        ))
    return diagnostics


def check_partial_trust_boundaries(facts: ExtendedFacts) -> List[Diagnostic]:
    diagnostics: List[Diagnostic] = []
    for trustBoundaryFact in facts.trustBoundaries.values():
        missing: List[str] = []
        if not trustBoundaryFact.hasInput:
            missing.append("trustBoundaryInput")
        if not trustBoundaryFact.hasOutput:
            missing.append("trustBoundaryOutput")
        if not trustBoundaryFact.hasValidator:
            missing.append("trustBoundaryValidator")
        if not missing:
            continue
        diagnostics.append(Diagnostic(
            tier=Tier.T3_REFINEMENT,
            code="SS1202",
            kind="partiallyDeclared.trustBoundary",
            severity=Severity.WARNING,
            subjectName=trustBoundaryFact.typeName,
            subjectKind="trustBoundary",
            gapEdge=",".join(missing),
            intentSlogan="trustBoundary triad incomplete",
            primary=span_of_line(trustBoundaryFact.line, "trustBoundaryDeclaration"),
            invariantRule="trustBoundary must declare input, output, and validator to prove the transition",
            specAnchor="SYNTAX.md#trustBoundary",
            fixCandidates=[
                FixCandidate(
                    name=f"add{edgeName[0].upper()}{edgeName[1:]}",
                    shape=f"{edgeName} {trustBoundaryFact.typeName} <value>",
                )
                for edgeName in missing
            ],
            confidence=Confidence.HIGH,
            effort=Effort.LOCAL,
            passProvenance="check_partial_trust_boundaries",
            agentHint="trust boundaries are security-critical — complete them, do not remove",
        ))
    return diagnostics


def check_literal_without_digest(facts: ExtendedFacts) -> List[Diagnostic]:
    """External-sourced literals without a literalDigest are a supply-chain
    gap: nothing pins the bytes that get inlined at compile time."""
    diagnostics: List[Diagnostic] = []
    for literalName, literalFact in facts.literals.items():
        if not literalFact.hasExternalSource:
            continue
        if literalFact.hasDigest:
            continue
        diagnostics.append(Diagnostic(
            tier=Tier.T3_REFINEMENT,
            code="SS1203",
            kind="partiallyDeclared.externalLiteral",
            severity=Severity.WARNING,
            subjectName=literalName,
            subjectKind="literal",
            gapEdge="literalDigest",
            intentSlogan="external literal lacks integrity pin",
            primary=span_of_line(literalFact.line, "literalDeclaration"),
            invariantRule="literals with `literalSource` should pin bytes via `literalDigest`",
            specAnchor="SYNTAX.md#literalDigest",
            fixCandidates=[
                FixCandidate(
                    name="addLiteralDigest",
                    shape=f"literalDigest {literalName} sha256 <hex>",
                ),
            ],
            confidence=Confidence.HIGH,
            effort=Effort.LOCAL,
            passProvenance="check_literal_without_digest",
            agentHint="run the digest at the same time you commit the source file so they stay in lockstep",
        ))
    return diagnostics


def check_operation_metadata_gaps(facts: ExtendedFacts) -> List[Diagnostic]:
    diagnostics: List[Diagnostic] = []
    for operationName, operation in facts.base.operations.items():
        bodyLines = [
            sourceLine for sourceLine in operation.lines[1:]
            if not is_comment(sourceLine) and sourceLine.tokens
        ]
        if not bodyLines:
            continue

        firstBodyLine = bodyLines[0]
        firstBodySpan = span_of_line(firstBodyLine, "firstBodyOp")
        existingNarrative = facts.operationNarrative.get(operationName, {})

        # Load-bearing gaps: purpose is the op's reason for existing
        gapPlan: List[Tuple[str, str, str]] = []   # (edge, code, agentHint)
        if "purpose" not in existingNarrative:
            gapPlan.append((
                "purpose", "SS3101",
                "draft from the body's calls, effects, and storage edges",
            ))

        touchesState = any(
            sourceLine.verb in {"set", "read"} for sourceLine in bodyLines
        )
        if touchesState and "invariant" not in existingNarrative:
            gapPlan.append((
                "invariant", "SS3102",
                "describe the relation between storage reads/writes the op preserves",
            ))

        operationCitations = narrative_citations_for_operation(facts, operationName)

        for edgeName, diagnosticCode, hintText in gapPlan:
            diagnostics.append(Diagnostic(
                tier=Tier.T3_REFINEMENT,
                code=diagnosticCode,
                kind=f"operationMetadataGap.{edgeName}",
                severity=Severity.WARNING,
                subjectName=operationName,
                subjectKind="operation",
                gapEdge=edgeName,
                intentSlogan=f"operation missing {edgeName}",
                primary=span_of_line(operation.line, "operationDeclaration"),
                related=[firstBodySpan],
                invariantRule=f"every operation should declare `{edgeName}`",
                specAnchor=f"SYNTAX.md#{edgeName}",
                citations=operationCitations,
                fixCandidates=[
                    FixCandidate(
                        name=f"add{edgeName.capitalize()}",
                        shape=f'{edgeName} {operationName} "<one-sentence …>"',
                        evidence=[firstBodySpan],
                    ),
                ],
                confidence=Confidence.HIGH,
                effort=Effort.TRIVIAL,
                passProvenance="check_operation_metadata_gaps",
                agentHint=hintText,
            ))
    return diagnostics


def check_shared_state_protection(facts: ExtendedFacts) -> List[Diagnostic]:
    """`sharedState` set/read without a `protectedBy <guardToken>` clause is
    a guard-token gap. In single-thread lowering it's benign, but the
    multi-thread lowering inherits the contract — declaring the guard now
    locks in the invariant before scheduler runtime arrives."""
    diagnostics: List[Diagnostic] = []
    for accessFact in facts.sharedStateAccesses:
        if accessFact.hasProtection:
            continue
        diagnostics.append(Diagnostic(
            tier=Tier.T3_REFINEMENT,
            code="SS3105",
            kind="capabilityCoverage.unprotectedSharedState",
            severity=Severity.WARNING,
            subjectName=accessFact.slotName,
            subjectKind=f"sharedState{accessFact.accessKind.capitalize()}",
            gapEdge="protectedBy",
            intentSlogan="sharedState access lacks guard token",
            primary=span_of_line(accessFact.line, f"sharedState{accessFact.accessKind.capitalize()}"),
            invariantRule="every sharedState set/read should declare protectedBy <guardToken>",
            specAnchor="SYNTAX.md#sharedState",
            fixCandidates=[
                FixCandidate(
                    name="addProtectedByClause",
                    shape=f"{accessFact.line.raw.strip()} protectedBy <guardToken>",
                    evidence=[span_of_line(accessFact.line)],
                ),
                FixCandidate(
                    # SYNTAX.md has no bare `guardToken NAME` declaration verb;
                    # guard tokens are declared via their acquisition call
                    # plus protects/owner/release edges. Shape uses only
                    # registered verbs so the fix doesn't trip SS0001.
                    name="declareGuardTokenViaAcquisitionEdges",
                    shape=(
                        f"guardTokenSource <guardTokenName> <acquisitionCall>\n"
                        f"guardTokenProtects <guardTokenName> {accessFact.slotName}\n"
                        f"guardTokenRelease <guardTokenName> <releaseOperation>"
                    ),
                ),
            ],
            confidence=Confidence.HIGH,
            effort=Effort.LOCAL,
            passProvenance="check_shared_state_protection",
            agentHint=(
                "single-thread lowering ignores the guard, but declaring it now "
                "locks in the contract before the multi-thread scheduler lands"
            ),
        ))
    return diagnostics


def check_supported_shared_state_scope(facts: ExtendedFacts) -> List[Diagnostic]:
    """Current codegen only implements process-scoped shared state. Other
    scopes would overstate the runtime boundary because they still lower to
    an in-process LLVM global."""
    diagnostics: List[Diagnostic] = []
    for storageName, storageFact in facts.storageSlots.items():
        if not storageFact.scope.startswith("sharedState."):
            continue
        sharedStateScope = storageFact.scope.split(".", 1)[1]
        if sharedStateScope == "process":
            continue
        replacementShape = (
            "sharedState process " + " ".join(storageFact.line.args[1:])
            if len(storageFact.line.args) >= 4
            else "sharedState process <mutability> <name> <type> [initial]"
        )
        diagnostics.append(Diagnostic(
            tier=Tier.T3_REFINEMENT,
            code="SS3108",
            kind="stateSemantics.unsupportedSharedStateScope",
            severity=Severity.WARNING,
            subjectName=storageName,
            subjectKind="sharedState",
            gapEdge="processScopeOnly",
            intentSlogan="sharedState scope exceeds current runtime",
            primary=span_of_line(storageFact.line, "sharedStateDeclaration"),
            invariantRule=(
                "SemanticScript 1.0 codegen implements sharedState as an LLVM "
                "module global visible within one process; cross-process or "
                "cluster state requires an external runtime not wired today"
            ),
            specAnchor="SYNTAX.md#sharedState",
            fixCandidates=[
                FixCandidate(
                    name="useProcessScope",
                    shape=replacementShape,
                    evidence=[span_of_line(storageFact.line)],
                ),
                FixCandidate(
                    name="documentExternalStateRuntime",
                    shape='warning <operationName> "sharedState uses an external cross-process runtime"',
                    autoApplicable=False,
                ),
            ],
            confidence=Confidence.HIGH,
            effort=Effort.LOCAL,
            passProvenance="check_supported_shared_state_scope",
            agentHint=(
                "do not rely on the compiler for cross-process sharing; only "
                "`sharedState process` has a concrete 1.0 lowering"
            ),
        ))
    return diagnostics


def _build_capability_coverage_fix_candidates(
    operationName: str,
    effectAction: str,
    effectPath: str,
    effectLine: SourceLine,
    reusableCapabilityName: Optional[str],
    reusableCapabilityIsAlreadyUsed: bool,
) -> List[FixCandidate]:
    """Build SS3104 fix candidates, preferring reuse of an existing
    capability when one matches the effect path/action.

    Reconciliation with SS0103 (unused capability):
      - Unused matching capability → top fix is `useCapability` referencing
        it; clears SS3104 here AND SS0103 there in one stroke.
      - Already-used matching capability → top fix is `useCapability`
        referencing it; clears SS3104 here, SS0103 stays clear.
      - No matching capability → top fix is `declareAndUseCapability` with
        a placeholder name.
    """
    fixCandidates: List[FixCandidate] = []
    if reusableCapabilityName:
        reuseLabel = "reuseExistingCapability"
        if not reusableCapabilityIsAlreadyUsed:
            reuseLabel = "reuseExistingDanglingCapability"
        fixCandidates.append(FixCandidate(
            name=reuseLabel,
            shape=f"useCapability {operationName} {reusableCapabilityName}",
            evidence=[span_of_line(effectLine)],
        ))
    fixCandidates.append(FixCandidate(
        name="declareAndUseCapability",
        shape=(
            f"capability <capabilityName> {effectPath} {effectAction}\n"
            f"useCapability {operationName} <capabilityName>"
        ),
        evidence=[span_of_line(effectLine)],
    ))
    fixCandidates.append(FixCandidate(
        name="inlineAuthority",
        shape=f"authority {operationName} {effectPath} {effectAction}",
        evidence=[span_of_line(effectLine)],
    ))
    return fixCandidates


def check_effect_without_capability(facts: ExtendedFacts) -> List[Diagnostic]:
    diagnostics: List[Diagnostic] = []
    for operationName, effectLines in facts.operationEffects.items():
        if operationName in facts.operationUseCapability:
            continue
        if operationName in facts.operationAuthority:
            continue
        operationCitations = narrative_citations_for_operation(facts, operationName)
        for effectLine in effectLines:
            args = effectLine.args
            if len(args) < 3:
                continue
            action, effectPath = args[1], args[2]
            # Reconcile with SS0103: if a declared capability covers this
            # (path, action), prefer reusing it over declaring a new one.
            # Unused matching capabilities are preferred — wiring it here
            # also clears SS0103 for that capability in one stroke.
            reusableCapabilityName: Optional[str] = None
            reusableCapabilityIsAlreadyUsed = False
            for candidateCapability in facts.capabilities.values():
                if candidateCapability.effectPath != effectPath:
                    continue
                if candidateCapability.accessAction != action:
                    continue
                if candidateCapability.name not in facts.capabilityUses:
                    reusableCapabilityName = candidateCapability.name
                    reusableCapabilityIsAlreadyUsed = False
                    break
                if reusableCapabilityName is None:
                    reusableCapabilityName = candidateCapability.name
                    reusableCapabilityIsAlreadyUsed = True
            diagnostics.append(Diagnostic(
                # SYNTAX.md frames capability coverage as a LINTER rule, not a
                # compiler-blocking spec violation: "the linter checks that
                # every effect site has an authorizing capability… enforcement
                # at the runtime authority layer is a future runtime concern."
                # So T3 refinement gap, not T1 spec error.
                tier=Tier.T3_REFINEMENT,
                code="SS3104",
                kind="capabilityCoverage.missing",
                severity=Severity.WARNING,
                subjectName=operationName,
                subjectKind="operation",
                gapEdge="useCapability",
                intentSlogan="effect lacks capability proof",
                primary=span_of_line(effectLine, "effectDeclaration"),
                invariantRule="every declared effect should have an authorizing capability proof",
                specAnchor="SYNTAX.md#useCapability",
                citations=operationCitations,
                fixCandidates=_build_capability_coverage_fix_candidates(
                    operationName=operationName,
                    effectAction=action,
                    effectPath=effectPath,
                    effectLine=effectLine,
                    reusableCapabilityName=reusableCapabilityName,
                    reusableCapabilityIsAlreadyUsed=reusableCapabilityIsAlreadyUsed,
                ),
                confidence=Confidence.HIGH,
                blocksCompile=False,
                effort=Effort.LOCAL,
                passProvenance="check_effect_without_capability",
                agentHint=(
                    f"if `{effectPath}` recurs across files, declare a shared `capability` "
                    f"at module scope and reuse it"
                ),
            ))
    return diagnostics


def check_unknown_verbs(facts: ExtendedFacts) -> List[Diagnostic]:
    """Verbs not in `KNOWN_AGENT_SCRIPT_VERBS` are grammar gaps — either a
    typo, or a SYNTAX.md row landed without updating this set. Reported as
    T0 because nothing else downstream can interpret an unrecognised verb."""
    diagnostics: List[Diagnostic] = []
    seenUnknownAtLine: Set[Tuple[Path, int]] = set()
    for sourceLine in facts.base.lines:
        if not sourceLine.tokens or is_comment(sourceLine):
            continue
        verb = sourceLine.verb
        if verb in KNOWN_AGENT_SCRIPT_VERBS:
            continue
        key = (sourceLine.path, sourceLine.number)
        if key in seenUnknownAtLine:
            continue
        seenUnknownAtLine.add(key)
        diagnostics.append(Diagnostic(
            tier=Tier.T0_PARSE,
            code="SS0001",
            kind="grammar.unknownVerb",
            severity=Severity.ERROR,
            subjectName=verb,
            subjectKind="verb",
            gapEdge="grammarRegistration",
            intentSlogan="verb not in language vocabulary",
            primary=span_of_line(sourceLine, "unknownVerbSite"),
            invariantRule="every verb must be a row in SYNTAX.md and registered in KNOWN_AGENT_SCRIPT_VERBS",
            specAnchor="SYNTAX.md",
            fixCandidates=[
                FixCandidate(
                    name="correctTypo",
                    shape=f"# verify spelling of `{verb}` against SYNTAX.md",
                ),
                FixCandidate(
                    name="addToVocabulary",
                    shape=f"# add `{verb}` to KNOWN_AGENT_SCRIPT_VERBS if the spec row exists",
                ),
            ],
            confidence=Confidence.HIGH,
            blocksCompile=True,
            effort=Effort.TRIVIAL,
            passProvenance="check_unknown_verbs",
            agentHint=(
                "if a new SYNTAX.md row was added recently, this vocab is "
                "out of date — sync the set"
            ),
        ))
    return diagnostics


def check_vague_names(facts: ExtendedFacts) -> List[Diagnostic]:
    """Enforce the descriptive-identifier rule:
      * call names must end in `Call`
      * bindError values must end in `Error`
      * makeError / declareFailure values must end in `Failure`
      * names from VAGUE_NAME_BLACKLIST are rejected outright
    Each violation is one diagnostic so the agent can fix in place."""
    diagnostics: List[Diagnostic] = []
    for operation in facts.base.operations.values():
        operationCitations = narrative_citations_for_operation(facts, operation.name)
        for sourceLine in operation.lines:
            if not sourceLine.tokens or is_comment(sourceLine):
                continue
            verb = sourceLine.verb
            args = sourceLine.args
            if verb == "call" and len(args) >= 2:
                callName = args[0]
                if not callName.endswith("Call"):
                    diagnostics.append(_make_vague_name_diagnostic(
                        sourceLine=sourceLine,
                        operation=operation,
                        operationCitations=operationCitations,
                        code="SS4001",
                        kind="namingDiscipline.callObjectSuffix",
                        subjectName=callName,
                        subjectKind="call",
                        intentSlogan="call name lacks `Call` suffix",
                        invariantRule="call object names must end with `Call` to read distinctly from regular bindings",
                        fixShape=f"call {callName}Call <target>",
                        agentHint=(
                            f"rename `{callName}` → `{callName}Call` and "
                            f"update every `arg/run/start/bind*` reference"
                        ),
                    ))
                if callName in VAGUE_NAME_BLACKLIST:
                    diagnostics.append(_make_vague_name_diagnostic(
                        sourceLine=sourceLine,
                        operation=operation,
                        operationCitations=operationCitations,
                        code="SS4004",
                        kind="namingDiscipline.vagueName",
                        subjectName=callName,
                        subjectKind="call",
                        intentSlogan="call name is in vague-name blacklist",
                        invariantRule="names from the vague-name blacklist obscure intent and must be replaced with descriptive identifiers",
                        fixShape=f"call <descriptiveNameCall> <target>",
                        agentHint="draft the new name from the call's target verb and the data it operates on",
                    ))
            elif verb == "bindError" and len(args) >= 3:
                errorBindingName = args[0]
                if not errorBindingName.endswith("Error"):
                    diagnostics.append(_make_vague_name_diagnostic(
                        sourceLine=sourceLine,
                        operation=operation,
                        operationCitations=operationCitations,
                        code="SS4002",
                        kind="namingDiscipline.bindErrorSuffix",
                        subjectName=errorBindingName,
                        subjectKind="bindError",
                        intentSlogan="error binding lacks `Error` suffix",
                        invariantRule="bindError values must end with `Error` so they read distinctly from success bindings",
                        fixShape=f"bindError {errorBindingName}Error <type> <call>",
                        agentHint="rename to `<context>Error` (e.g. `accountLookupError`)",
                    ))
            elif verb in {"makeError", "declareFailure"} and args:
                failureValueName = args[0]
                if not failureValueName.endswith("Failure"):
                    diagnostics.append(_make_vague_name_diagnostic(
                        sourceLine=sourceLine,
                        operation=operation,
                        operationCitations=operationCitations,
                        code="SS4003",
                        kind="namingDiscipline.makeErrorSuffix",
                        subjectName=failureValueName,
                        subjectKind=verb,
                        intentSlogan=f"{verb} value lacks `Failure` suffix",
                        invariantRule=f"{verb} values must end with `Failure` so error construction sites are visually distinct",
                        fixShape=f"{verb} {failureValueName}Failure <Error>.<Variant>",
                        agentHint="rename to `<context>Failure` (e.g. `accountLookupFailure`)",
                    ))
            elif verb in {"bind", "bindOk"} and len(args) >= 3:
                bindName = args[0]
                if bindName in VAGUE_NAME_BLACKLIST:
                    diagnostics.append(_make_vague_name_diagnostic(
                        sourceLine=sourceLine,
                        operation=operation,
                        operationCitations=operationCitations,
                        code="SS4004",
                        kind="namingDiscipline.vagueName",
                        subjectName=bindName,
                        subjectKind=verb,
                        intentSlogan=f"{verb} name is in vague-name blacklist",
                        invariantRule="bound values should describe what they hold, not their position in the algorithm",
                        fixShape=f"{verb} <descriptiveName> <type> <call>",
                        agentHint="name after the meaning of the bound value, not its role as an intermediate",
                    ))
            elif verb == "const" and len(args) >= 1:
                constName = args[0]
                if constName in VAGUE_NAME_BLACKLIST:
                    diagnostics.append(_make_vague_name_diagnostic(
                        sourceLine=sourceLine,
                        operation=operation,
                        operationCitations=operationCitations,
                        code="SS4004",
                        kind="namingDiscipline.vagueName",
                        subjectName=constName,
                        subjectKind="const",
                        intentSlogan="const name is in vague-name blacklist",
                        invariantRule="const names must describe the literal's semantic meaning, not its position",
                        fixShape=f"const <descriptiveName> <type> <value>",
                        agentHint="name after what the literal MEANS in this context",
                    ))
    return diagnostics


def _make_vague_name_diagnostic(
    sourceLine: SourceLine,
    operation: OperationFact,
    operationCitations: List[Citation],
    code: str,
    kind: str,
    subjectName: str,
    subjectKind: str,
    intentSlogan: str,
    invariantRule: str,
    fixShape: str,
    agentHint: str,
) -> Diagnostic:
    return Diagnostic(
        tier=Tier.T4_STYLE,
        code=code,
        kind=kind,
        severity=Severity.WARNING,
        subjectName=subjectName,
        subjectKind=subjectKind,
        gapEdge="descriptiveName",
        intentSlogan=intentSlogan,
        primary=span_of_line(sourceLine, "vagueNameSite"),
        related=[span_of_line(operation.line, "enclosingOperation")],
        invariantRule=invariantRule,
        specAnchor="memory#feedback_descriptive_as_identifiers",
        citations=operationCitations,
        fixCandidates=[
            FixCandidate(
                name="renameToDescriptive",
                shape=fixShape,
            ),
        ],
        confidence=Confidence.HIGH,
        effort=Effort.LOCAL,
        passProvenance="check_vague_names",
        agentHint=agentHint,
    )


def check_unused_bind_slots(facts: ExtendedFacts) -> List[Diagnostic]:
    """`bind` / `bindOk` / `bindError` declarations whose name is never
    referenced on any subsequent line of the same operation. Common pattern
    when a programmer binds out of habit but the value isn't consumed."""
    diagnostics: List[Diagnostic] = []
    for operation in facts.base.operations.values():
        bindDeclarations: List[Tuple[str, str, SourceLine, int]] = []
        for lineIndex, sourceLine in enumerate(operation.lines):
            if is_comment(sourceLine) or not sourceLine.tokens:
                continue
            if sourceLine.verb in {"bind", "bindOk", "bindError"} and len(sourceLine.args) >= 3:
                bindDeclarations.append((
                    sourceLine.args[0], sourceLine.verb, sourceLine, lineIndex,
                ))

        for bindName, bindVerb, declarationLine, declarationIndex in bindDeclarations:
            isReferenced = False
            for laterLine in operation.lines[declarationIndex + 1:]:
                if is_comment(laterLine) or not laterLine.tokens:
                    continue
                # Skip the bind declarations themselves to avoid self-match
                if laterLine.verb in {"bind", "bindOk", "bindError"} and len(laterLine.args) >= 1:
                    if laterLine.args[0] == bindName:
                        continue
                for token in laterLine.tokens:
                    if token.text == bindName:
                        isReferenced = True
                        break
                if isReferenced:
                    break
            if isReferenced:
                continue
            diagnostics.append(Diagnostic(
                tier=Tier.T3_REFINEMENT,
                code="SS0106",
                kind=f"unusedDeclaration.{bindVerb}Slot",
                severity=Severity.WARNING,
                subjectName=bindName,
                subjectKind=bindVerb,
                gapEdge="reference",
                intentSlogan=f"{bindVerb} value bound but never read",
                primary=span_of_line(declarationLine, "bindDeclaration"),
                related=[span_of_line(operation.line, "enclosingOperation")],
                invariantRule=f"every `{bindVerb}` value should be referenced on a subsequent line",
                specAnchor=f"SYNTAX.md#{bindVerb}",
                citations=narrative_citations_for_operation(facts, operation.name),
                fixCandidates=[
                    FixCandidate(
                        name="removeBindDeclaration",
                        shape=f"# remove `{bindVerb} {bindName} …`",
                        autoApplicable=True,
                        evidence=[span_of_line(declarationLine)],
                    ),
                    FixCandidate(
                        name="readBindValue",
                        shape=f"# use `{bindName}` in a return / arg / branchIf on a subsequent line",
                    ),
                ],
                confidence=Confidence.HIGH,
                effort=Effort.TRIVIAL,
                passProvenance="check_unused_bind_slots",
                agentHint=(
                    "if the bind exists only to document the call's result, "
                    "delete it — the call already runs"
                ),
            ))
    return diagnostics


def check_hidden_failure(facts: ExtendedFacts) -> List[Diagnostic]:
    """Calls to known-fallible targets without both `bindError` AND
    `branchIfError` (or an explicit ignoreOk + bindError pair) silently
    drop failures. Matches semlint.py's hiddenFailure rule but on the new
    structured schema."""
    diagnostics: List[Diagnostic] = []
    for operation in facts.base.operations.values():
        operationCitations = narrative_citations_for_operation(facts, operation.name)
        operationCalls = collect_operation_calls(operation)
        for callFact in operationCalls.values():
            if callFact.target not in KNOWN_FALLIBLE_CALL_TARGETS:
                continue
            if callFact.target in C_SENTINEL_FALLIBLE_CALL_TARGETS:
                if call_has_value_disposition(callFact):
                    continue
                diagnostics.append(Diagnostic(
                    tier=Tier.T3_REFINEMENT,
                    code="SS3106",
                    kind="errorPathCoverage.hiddenFailure",
                    severity=Severity.WARNING,
                    subjectName=callFact.name,
                    subjectKind="call",
                    gapEdge="bindOrIgnoreValue",
                    intentSlogan="C-style fallible call without value disposition",
                    primary=span_of_line(callFact.line, "callDeclaration"),
                    related=[span_of_line(operation.line, "enclosingOperation")],
                    invariantRule=(
                        f"C-style fallible target `{callFact.target}` returns a "
                        "sentinel/status value; bind it for checking or explicitly "
                        "discard it with `ignoreValue`"
                    ),
                    specAnchor="SYNTAX.md#ignoreValue",
                    citations=operationCitations,
                    fixCandidates=[
                        FixCandidate(
                            name="bindOrIgnoreStatus",
                            shape=(
                                f"bind {callFact.name}Status <ReturnType> {callFact.name}\n"
                                f"# ...check status...\n"
                                f"# or: ignoreValue {callFact.name} <ReturnType>"
                            ),
                            evidence=[span_of_line(callFact.line)],
                        ),
                    ],
                    confidence=Confidence.HIGH,
                    effort=Effort.LOCAL,
                    passProvenance="check_hidden_failure",
                    agentHint=(
                        f"`{callFact.target}` is not Result-shaped; use a bound "
                        "sentinel/status check or an explicit ignoreValue"
                    ),
                ))
                continue
            missingDisposition: List[str] = []
            if not callFact.bind_error_lines:
                missingDisposition.append("bindError")
            if not callFact.branch_error_lines:
                missingDisposition.append("branchIfError")
            if not missingDisposition:
                continue
            diagnostics.append(Diagnostic(
                tier=Tier.T3_REFINEMENT,
                code="SS3106",
                kind="errorPathCoverage.hiddenFailure",
                severity=Severity.WARNING,
                subjectName=callFact.name,
                subjectKind="call",
                gapEdge=",".join(missingDisposition),
                intentSlogan="fallible call without error disposition",
                primary=span_of_line(callFact.line, "callDeclaration"),
                related=[span_of_line(operation.line, "enclosingOperation")],
                invariantRule=(
                    f"calls to known-fallible target `{callFact.target}` must "
                    f"have both `bindError` and `branchIfError`"
                ),
                specAnchor="SYNTAX.md#bindError",
                citations=operationCitations,
                fixCandidates=[
                    FixCandidate(
                        # Full pattern: bind + branch + handler that ACTUALLY
                        # consumes the bound error via returnError. Without
                        # the handler's returnError, SS0106 would fire on the
                        # newly-introduced bindError slot — a true cycle.
                        # `bindError` values end in `Error` per SS4002.
                        name="addBindErrorAndBranchAndConsume",
                        shape=(
                            f"bindError {callFact.name}Error <ErrorType> {callFact.name}\n"
                            f"branchIfError {callFact.name} <handlerLabel>\n"
                            f"# ...success continuation...\n"
                            f"label <handlerLabel>\n"
                            f"returnError {callFact.name}Error"
                        ),
                        evidence=[span_of_line(callFact.line)],
                    ),
                ],
                confidence=Confidence.HIGH,
                effort=Effort.LOCAL,
                passProvenance="check_hidden_failure",
                agentHint=(
                    f"`{callFact.target}` can fail at runtime; explicit error "
                    f"disposition makes the failure path part of the operation's "
                    f"contract"
                ),
            ))
    return diagnostics


def check_sibling_metadata_drift(facts: ExtendedFacts) -> List[Diagnostic]:
    """Inconsistent metadata across siblings in the same file. If ≥60% of
    operations declare an edge and ≥1 sibling doesn't, that sibling is
    drifting from the file-local convention."""
    diagnostics: List[Diagnostic] = []
    edgeByOperation: Dict[str, Set[str]] = {
        operationName: set() for operationName in facts.base.operations
    }
    edgeLineByOperation: Dict[str, Dict[str, SourceLine]] = {
        operationName: {} for operationName in facts.base.operations
    }

    for sourceLine in facts.base.lines:
        if not sourceLine.tokens or is_comment(sourceLine):
            continue
        verb = sourceLine.verb
        args = sourceLine.args
        if verb in SIBLING_METADATA_EDGES and args:
            operationName = args[0]
            if operationName in edgeByOperation:
                edgeByOperation[operationName].add(verb)
                edgeLineByOperation[operationName][verb] = sourceLine

    operationNamesWithAnyMetadata = [
        operationName for operationName, edges in edgeByOperation.items()
        if edges
    ]
    if len(operationNamesWithAnyMetadata) < 3:
        return diagnostics

    for edgeName in SIBLING_METADATA_EDGES:
        operationsWithEdge = [
            operationName for operationName in operationNamesWithAnyMetadata
            if edgeName in edgeByOperation[operationName]
        ]
        operationsWithoutEdge = [
            operationName for operationName in operationNamesWithAnyMetadata
            if edgeName not in edgeByOperation[operationName]
        ]
        if not operationsWithoutEdge or not operationsWithEdge:
            continue
        adoptionRatio = len(operationsWithEdge) / len(operationNamesWithAnyMetadata)
        if adoptionRatio < 0.6:
            continue

        examplePresentOperation = operationsWithEdge[0]
        examplePresentLine = edgeLineByOperation[examplePresentOperation][edgeName]

        for operationName in operationsWithoutEdge:
            operation = facts.base.operations[operationName]
            adoptionPercent = int(adoptionRatio * 100)
            diagnostics.append(Diagnostic(
                tier=Tier.T3_REFINEMENT,
                code="SS3107",
                kind="metadataConsistency.siblingDrift",
                severity=Severity.WARNING,
                subjectName=operationName,
                subjectKind="operation",
                gapEdge=edgeName,
                intentSlogan=f"operation diverges from sibling {edgeName} convention",
                primary=span_of_line(operation.line, "driftingOperation"),
                related=[span_of_line(examplePresentLine, "siblingConventionExample")],
                invariantRule=(
                    f"operations in the same file should consistently declare or "
                    f"omit `{edgeName}`; mixed declarations create ambiguity"
                ),
                specAnchor=f"SYNTAX.md#{edgeName}",
                citations=narrative_citations_for_operation(facts, operationName),
                fixCandidates=[
                    FixCandidate(
                        name=f"add{edgeName[0].upper()}{edgeName[1:]}ToMatch",
                        shape=f"{edgeName} {operationName} <valueMatchingSiblings>",
                        evidence=[span_of_line(examplePresentLine)],
                    ),
                ],
                confidence=Confidence.MEDIUM,
                effort=Effort.TRIVIAL,
                passProvenance="check_sibling_metadata_drift",
                agentHint=(
                    f"{adoptionPercent}% of siblings declare `{edgeName}` — "
                    f"either add it here with a value drawn from the related "
                    f"span, or strip it from the siblings"
                ),
            ))
    return diagnostics


def check_undeclared_body_effect(facts: ExtendedFacts) -> List[Diagnostic]:
    """Body call to a target with a known effect, but the enclosing op
    doesn't declare that effect via `effect OP ACTION PATH`. Catches the
    'I added a console.writeLine and forgot the effect line' class."""
    diagnostics: List[Diagnostic] = []
    for operation in facts.base.operations.values():
        declaredEffectPairs: Set[Tuple[str, str]] = set()
        for effectLine in facts.operationEffects.get(operation.name, []):
            if len(effectLine.args) >= 3:
                declaredEffectPairs.add((effectLine.args[1], effectLine.args[2]))

        operationCalls = collect_operation_calls(operation)
        operationCitations = narrative_citations_for_operation(facts, operation.name)
        seenPairsForOperation: Set[Tuple[str, str]] = set()
        for callFact in operationCalls.values():
            impliedEffect = CALL_TARGET_IMPLIED_EFFECTS.get(callFact.target)
            if not impliedEffect:
                continue
            if impliedEffect in declaredEffectPairs:
                continue
            # Dedupe: emit one diagnostic per (op, effectPair) — multiple body
            # calls implying the same effect collapse into one finding.
            if impliedEffect in seenPairsForOperation:
                continue
            seenPairsForOperation.add(impliedEffect)
            impliedAction, impliedPath = impliedEffect
            diagnostics.append(Diagnostic(
                tier=Tier.T3_REFINEMENT,
                code="SS3111",
                kind="effectCoverage.undeclaredBodyEffect",
                severity=Severity.WARNING,
                subjectName=operation.name,
                subjectKind="operation",
                gapEdge="effect",
                intentSlogan="body produces undeclared effect",
                primary=span_of_line(callFact.line, "effectCausingCall"),
                related=[span_of_line(operation.line, "enclosingOperation")],
                invariantRule=(
                    f"calling `{callFact.target}` produces effect "
                    f"`{impliedAction} {impliedPath}`; the operation must "
                    f"declare it via `effect OP ACTION PATH`"
                ),
                specAnchor="SYNTAX.md#effect",
                citations=operationCitations,
                fixCandidates=[
                    FixCandidate(
                        # The combined fix avoids the SS3111 → SS3104 cascade:
                        # adding `effect` alone would make SS3104 fire on the
                        # same op once it has an undeclared-authority effect.
                        # Bundle the capability declaration so the agent
                        # resolves both gaps in one edit.
                        name="addEffectDeclarationWithCapabilityProof",
                        shape=(
                            f"effect {operation.name} {impliedAction} {impliedPath}\n"
                            f"authority {operation.name} {impliedPath} {impliedAction}"
                        ),
                        evidence=[span_of_line(callFact.line)],
                    ),
                    FixCandidate(
                        name="addEffectDeclarationOnly",
                        shape=f"effect {operation.name} {impliedAction} {impliedPath}",
                        evidence=[span_of_line(callFact.line)],
                    ),
                ],
                confidence=Confidence.HIGH,
                effort=Effort.TRIVIAL,
                # Prerequisite chain: SS3111 fix (effect only) → SS3104 fires.
                # Declared here so agent walks fixes in order.
                prerequisite=[],
                passProvenance="check_undeclared_body_effect",
                agentHint=(
                    "declaring the effect ALONE will trigger SS3104 next; "
                    "prefer the bundled fix that includes `authority` so both "
                    "gaps resolve in one edit"
                ),
            ))
    return diagnostics


def check_make_error_unknown_variant(facts: ExtendedFacts) -> List[Diagnostic]:
    """`makeError NAME Foo.NotAVariant` where `errorCase Foo NotAVariant`
    isn't declared — typo catch. Connects facts already gathered."""
    diagnostics: List[Diagnostic] = []
    declaredVariants: Set[Tuple[str, str]] = set(facts.errorCases.keys())
    for sourceLine in facts.base.lines:
        if not sourceLine.tokens or is_comment(sourceLine):
            continue
        if sourceLine.verb not in {"makeError", "declareFailure"}:
            continue
        if len(sourceLine.args) < 2:
            continue
        dotted = sourceLine.args[1]
        if "." not in dotted:
            continue
        errorName, variantName = dotted.split(".", 1)
        if (errorName, variantName) in declaredVariants:
            continue
        # Suggest the closest declared variant of the same error domain
        sameDomainVariants = sorted(
            variant for (declaredError, variant) in declaredVariants
            if declaredError == errorName
        )
        diagnostics.append(Diagnostic(
            tier=Tier.T3_REFINEMENT,
            code="SS3112",
            kind="errorPathCoverage.unknownVariant",
            severity=Severity.WARNING,
            subjectName=f"{errorName}.{variantName}",
            subjectKind="errorReference",
            gapEdge="errorCaseDeclaration",
            intentSlogan=f"{sourceLine.verb} references unknown variant",
            primary=span_of_line(sourceLine, f"{sourceLine.verb}Site"),
            invariantRule=(
                f"`{sourceLine.verb}` must reference a declared "
                f"`errorCase {errorName} <variant>` row"
            ),
            specAnchor="SYNTAX.md#errorCase",
            fixCandidates=[
                FixCandidate(
                    name="declareMissingErrorCase",
                    shape=f"errorCase {errorName} {variantName}",
                ),
                FixCandidate(
                    name="correctVariantSpelling",
                    shape=(
                        f"# {sourceLine.verb} ... {errorName}.<oneOf: "
                        f"{', '.join(sameDomainVariants) if sameDomainVariants else '(no variants declared)'}>"
                    ),
                ),
            ],
            confidence=Confidence.HIGH,
            effort=Effort.TRIVIAL,
            passProvenance="check_make_error_unknown_variant",
            agentHint=(
                "if the spelling is correct, the errorCase row is missing — "
                "add it under the matching `error` domain"
            ),
        ))
    return diagnostics


def check_unused_const(facts: ExtendedFacts) -> List[Diagnostic]:
    """`const NAME TYPE VALUE` declared in an op but never referenced on a
    subsequent line of the same op. Mirrors SS0106 unusedDeclaration.bindSlot.
    Module-level consts (outside any op) are tracked under base ProgramFacts
    and skipped here — separate checker for that scope is future work."""
    diagnostics: List[Diagnostic] = []
    for operation in facts.base.operations.values():
        operationCitations = narrative_citations_for_operation(facts, operation.name)
        constDeclarations: List[Tuple[str, SourceLine, int]] = []
        for lineIndex, sourceLine in enumerate(operation.lines):
            if is_comment(sourceLine) or not sourceLine.tokens:
                continue
            if sourceLine.verb == "const" and len(sourceLine.args) >= 1:
                constDeclarations.append((sourceLine.args[0], sourceLine, lineIndex))

        for constName, declarationLine, declarationIndex in constDeclarations:
            isReferenced = False
            for laterLine in operation.lines[declarationIndex + 1:]:
                if is_comment(laterLine) or not laterLine.tokens:
                    continue
                if laterLine.verb == "const" and laterLine.args and laterLine.args[0] == constName:
                    # Skip another const declaration of the same name (shadows)
                    continue
                for token in laterLine.tokens:
                    if token.text == constName:
                        isReferenced = True
                        break
                if isReferenced:
                    break
            if isReferenced:
                continue
            diagnostics.append(Diagnostic(
                tier=Tier.T3_REFINEMENT,
                code="SS0107",
                kind="unusedDeclaration.const",
                severity=Severity.WARNING,
                subjectName=constName,
                subjectKind="const",
                gapEdge="reference",
                intentSlogan="const declared but never referenced",
                primary=span_of_line(declarationLine, "constDeclaration"),
                related=[span_of_line(operation.line, "enclosingOperation")],
                invariantRule="every `const` declaration in an operation must be referenced on a later line",
                specAnchor="SYNTAX.md#domainLiteral",
                citations=operationCitations,
                fixCandidates=[
                    FixCandidate(
                        name="removeUnusedConst",
                        shape=f"# remove `const {constName} …`",
                        autoApplicable=True,
                        evidence=[span_of_line(declarationLine)],
                    ),
                ],
                confidence=Confidence.HIGH,
                effort=Effort.TRIVIAL,
                passProvenance="check_unused_const",
                agentHint=(
                    "consts in operations are scratchpad; if it's not consumed "
                    "by a later arg / return / branchIf, it's dead"
                ),
            ))
    return diagnostics


def check_unused_input(facts: ExtendedFacts) -> List[Diagnostic]:
    """`input OP argName TYPE` declares a parameter but the body never
    references `argName`. Mirror of unused-bind-slot for parameters."""
    diagnostics: List[Diagnostic] = []
    for operation in facts.base.operations.values():
        operationCitations = narrative_citations_for_operation(facts, operation.name)
        inputDeclarations: List[Tuple[str, SourceLine, int]] = []
        for lineIndex, sourceLine in enumerate(operation.lines):
            if is_comment(sourceLine) or not sourceLine.tokens:
                continue
            if sourceLine.verb == "input" and len(sourceLine.args) >= 2:
                inputDeclarations.append((sourceLine.args[1], sourceLine, lineIndex))

        for inputArgName, declarationLine, declarationIndex in inputDeclarations:
            if inputArgName in OPAQUE_DEPENDENCY_INPUT_NAMES:
                continue
            isReferenced = False
            for laterLine in operation.lines[declarationIndex + 1:]:
                if is_comment(laterLine) or not laterLine.tokens:
                    continue
                # Don't count the operation's own subsequent `input` lines
                if laterLine.verb == "input":
                    continue
                for token in laterLine.tokens:
                    if token.text == inputArgName:
                        isReferenced = True
                        break
                if isReferenced:
                    break
            if isReferenced:
                continue
            diagnostics.append(Diagnostic(
                tier=Tier.T3_REFINEMENT,
                code="SS0108",
                kind="unusedDeclaration.input",
                severity=Severity.WARNING,
                subjectName=inputArgName,
                subjectKind="input",
                gapEdge="reference",
                intentSlogan="input parameter never referenced in body",
                primary=span_of_line(declarationLine, "inputDeclaration"),
                related=[span_of_line(operation.line, "enclosingOperation")],
                invariantRule="every declared input parameter must be referenced in the operation body",
                specAnchor="SYNTAX.md#input",
                citations=operationCitations,
                fixCandidates=[
                    FixCandidate(
                        name="removeUnusedInput",
                        shape=f"# remove `input {operation.name} {inputArgName} …` and update callers",
                        evidence=[span_of_line(declarationLine)],
                    ),
                    FixCandidate(
                        name="useInputInBody",
                        shape=f"# reference `{inputArgName}` in arg / branchIf / returnOk on a later line",
                    ),
                ],
                confidence=Confidence.HIGH,
                effort=Effort.LOCAL,
                passProvenance="check_unused_input",
                agentHint=(
                    "unused parameters are usually leftover from a refactor; "
                    "removing changes the calling convention so check callers"
                ),
            ))
    return diagnostics


# ==========================================================================
# C-style discipline checkers — performance / memory / layout
# These map C-tooling concerns onto SemanticScript's declared-intent vocabulary
# (memoryHeap, memoryStackLimit, memoryArena, memoryAllocationSource,
# recordAlign, arrayLength, smallListInlineCapacity, typeLiteralEncoding).
# Code ranges: AS32xx performance, AS33xx memory, AS34xx layout.
# ==========================================================================

def _normalize_set_target_name(setLine: SourceLine) -> Optional[str]:
    """Return the storage slot name a `set` line targets, normalising
    scoped (`set local NAME …`) and legacy scopeless (`set NAME …`) forms."""
    args = setLine.args
    if not args:
        return None
    if args[0] in {"local", "module", "sharedState"}:
        return args[1] if len(args) >= 2 else None
    return args[0]


def _branch_target_names(sourceLine: SourceLine) -> List[str]:
    verb = sourceLine.verb
    args = sourceLine.args
    if verb == "branch" and args:
        return [args[0]]
    if verb == "branchIf" and len(args) >= 2:
        targets = [args[1]]
        if len(args) >= 3:
            targets.append(args[2])
        return targets
    if verb in {"branchIfError", "branchIfGroupError", "branchIfChannelClosed"} and len(args) >= 2:
        return [args[1]]
    if verb == "branchSelected" and len(args) >= 3:
        return [args[2]]
    return []


def _label_block_reads_name(
    operation: OperationFact,
    labelIndexByName: Dict[str, int],
    labelName: str,
    targetName: str,
) -> bool:
    labelIndex = labelIndexByName.get(labelName)
    if labelIndex is None:
        return False
    for laterLine in operation.lines[labelIndex + 1:]:
        if is_comment(laterLine) or not laterLine.tokens:
            continue
        if laterLine.verb == "label":
            return False
        if any(token.text == targetName for token in laterLine.tokens):
            return True
    return False


def check_dead_store(facts: ExtendedFacts) -> List[Diagnostic]:
    """`set X val1` followed by `set X val2` with no read of X between is a
    dead store — the first write is overwritten before observation."""
    diagnostics: List[Diagnostic] = []
    for operation in facts.base.operations.values():
        operationCitations = narrative_citations_for_operation(facts, operation.name)
        labelIndexByName: Dict[str, int] = {}
        for lineIndex, sourceLine in enumerate(operation.lines):
            if (not is_comment(sourceLine) and sourceLine.tokens
                    and sourceLine.verb == "label" and sourceLine.args):
                labelIndexByName[sourceLine.args[0]] = lineIndex

        # Walk lines in order, track per-name (lastSetIndex, lastSetLine)
        lastSetSeen: Dict[str, Tuple[int, SourceLine]] = {}
        for lineIndex, sourceLine in enumerate(operation.lines):
            if is_comment(sourceLine) or not sourceLine.tokens:
                continue
            verb = sourceLine.verb
            if verb == "set":
                targetName = _normalize_set_target_name(sourceLine)
                if not targetName:
                    continue
                priorSet = lastSetSeen.get(targetName)
                if priorSet is not None:
                    priorIndex, priorLine = priorSet
                    # Check intervening lines for any read of targetName
                    intervening = operation.lines[priorIndex + 1:lineIndex]
                    isReadBetween = any(
                        (
                            (
                                laterLine.verb != "set"
                                and any(token.text == targetName for token in laterLine.tokens)
                            )
                            or any(
                                _label_block_reads_name(
                                    operation,
                                    labelIndexByName,
                                    labelName,
                                    targetName,
                                )
                                for labelName in _branch_target_names(laterLine)
                            )
                        )
                        for laterLine in intervening
                        if not is_comment(laterLine) and laterLine.tokens
                    )
                    if not isReadBetween:
                        diagnostics.append(Diagnostic(
                            tier=Tier.T3_REFINEMENT,
                            code="SS3201",
                            kind="performanceDiscipline.deadStore",
                            severity=Severity.WARNING,
                            subjectName=targetName,
                            subjectKind="storageSlot",
                            gapEdge="interveningRead",
                            intentSlogan="set overwritten before any read",
                            primary=span_of_line(priorLine, "firstSet"),
                            related=[
                                span_of_line(sourceLine, "shadowingSet"),
                                span_of_line(operation.line, "enclosingOperation"),
                            ],
                            invariantRule="every `set` write should be observed before being overwritten",
                            specAnchor="SYNTAX.md#set",
                            citations=operationCitations,
                            fixCandidates=[
                                FixCandidate(
                                    name="removeDeadStore",
                                    shape=f"# remove the first `set` for `{targetName}` — it's never read",
                                    autoApplicable=True,
                                    evidence=[span_of_line(priorLine)],
                                ),
                                FixCandidate(
                                    name="readBeforeOverwriting",
                                    shape=f"# add a use of `{targetName}` between the two sets if the first value matters",
                                ),
                            ],
                            confidence=Confidence.MEDIUM,
                            effort=Effort.TRIVIAL,
                            passProvenance="check_dead_store",
                            agentHint="if the first set documents the initial state, prefer `storage local mutable` with that initial value",
                        ))
                lastSetSeen[targetName] = (lineIndex, sourceLine)
            else:
                # If we see a read of any tracked name, clear its lastSet
                # (we no longer have a dead-store candidate from earlier).
                for token in sourceLine.tokens:
                    if token.text in lastSetSeen:
                        del lastSetSeen[token.text]
    return diagnostics


_DUPLICATE_LOCAL_IMMUTABLE_THRESHOLD = 3


def _scan_op_local_immutables(
    operation: OperationFact,
) -> List[Tuple[str, str, str, SourceLine]]:
    """Return every `storage local immutable NAME TYPE INIT` declaration in an
    operation as ``(name, typeName, initValue, sourceLine)``. Storage rows that
    don't carry an init token (rare; legal only for some types) record an empty
    init string so the duplicate-detection key collapses by shape alone."""
    declarations: List[Tuple[str, str, str, SourceLine]] = []
    for sourceLine in operation.lines:
        if is_comment(sourceLine) or not sourceLine.tokens:
            continue
        if sourceLine.verb != "storage" or len(sourceLine.args) < 4:
            continue
        scope, mutability = sourceLine.args[0], sourceLine.args[1]
        if scope != "local" or mutability != "immutable":
            continue
        name = sourceLine.args[2]
        typeName = sourceLine.args[3]
        initValue = sourceLine.args[4] if len(sourceLine.args) >= 5 else ""
        declarations.append((name, typeName, initValue, sourceLine))
    return declarations


def _preceding_comment_block_text(
    facts: ExtendedFacts,
    sourceLine: SourceLine,
) -> str:
    """Return concatenated text of the nearest `# …` comment block above
    ``sourceLine``, walking past contiguous sibling ``storage`` rows so a
    rationale block placed above a block of related declarations counts for
    every row in that block. Lower-cased and joined by whitespace. Blank
    lines terminate the search. Returns "" if no comment block is reachable."""
    if sourceLine.number < 2:
        return ""
    lines = facts.base.lines
    cursor = sourceLine.number - 2
    fragments: List[str] = []
    sawComment = False
    while cursor >= 0:
        candidate = lines[cursor]
        if not candidate.tokens:
            break
        if is_comment(candidate):
            fragments.append(comment_text(candidate))
            sawComment = True
            cursor -= 1
            continue
        if not sawComment and candidate.verb == "storage":
            # Walk past a contiguous block of sibling storage rows; the
            # rationale block that introduces them applies to the whole group.
            cursor -= 1
            continue
        break
    return " ".join(reversed(fragments)).lower()


def _rationale_names_ascii_char(commentText: str, codepoint: int) -> bool:
    """The rationale comment is acceptable evidence for an ASCII byte literal
    if it (a) mentions ascii/codepoint/character/byte/char vocabulary, or
    (b) contains the glyph itself (e.g. the `"` character for codepoint 34)."""
    if not commentText:
        return False
    if any(kw in commentText for kw in ("ascii", "codepoint", "character", "byte ", "char")):
        return True
    glyph = chr(codepoint)
    if glyph in commentText:
        return True
    return False


def check_duplicate_local_immutable_across_ops(facts: ExtendedFacts) -> List[Diagnostic]:
    """``storage local immutable NAME TYPE VALUE`` declared identically in three
    or more operations is a hoist signal. The same value across the file is no
    longer per-operation context — it is a shared protocol or convention and
    belongs in ``storage module immutable`` so the project has one source of
    truth. Reported as T4_STYLE info, not warning, because the right balance
    between local convenience and module hoist is a judgement call."""
    diagnostics: List[Diagnostic] = []
    occurrences: Dict[Tuple[str, str, str], List[Tuple[str, SourceLine]]] = {}
    for operationName, operation in facts.base.operations.items():
        for name, typeName, initValue, sourceLine in _scan_op_local_immutables(operation):
            key = (name, typeName, initValue)
            occurrences.setdefault(key, []).append((operationName, sourceLine))

    for (name, typeName, initValue), declarations in occurrences.items():
        uniqueOperations = sorted({opName for opName, _ in declarations})
        if len(uniqueOperations) < _DUPLICATE_LOCAL_IMMUTABLE_THRESHOLD:
            continue
        sampleOpsText = ", ".join(uniqueOperations[:5])
        if len(uniqueOperations) > 5:
            sampleOpsText = f"{sampleOpsText}, +{len(uniqueOperations) - 5} more"
        moduleScopeShape = f"storage module immutable {name} {typeName} {initValue}".rstrip()
        for _opName, sourceLine in declarations:
            diagnostics.append(Diagnostic(
                tier=Tier.T4_STYLE,
                code="SS4401",
                kind="styleDiscipline.duplicateLocalImmutableAcrossOps",
                severity=Severity.INFO,
                subjectName=name,
                subjectKind="storageSlot",
                gapEdge="storage module immutable",
                intentSlogan="shared scalar repeated across operations",
                primary=span_of_line(sourceLine, "storageDeclaration"),
                invariantRule=(
                    f"`storage local immutable {name} {typeName} {initValue}` is "
                    f"declared in {len(uniqueOperations)} operations "
                    f"({sampleOpsText}); a value repeated across operations is a "
                    "shared protocol and belongs at module scope."
                ),
                specAnchor="docs/optimization-guide.md#hoist-shared-immutables-to-module-scope",
                fixCandidates=[
                    FixCandidate(
                        name="hoistToModuleImmutable",
                        shape=moduleScopeShape,
                    ),
                    FixCandidate(
                        name="renameAndKeepLocal",
                        shape=(
                            f"# keep `{name}` local only if it carries operation-specific "
                            "meaning; rename to something operation-scoped"
                        ),
                    ),
                ],
                confidence=Confidence.HIGH,
                effort=Effort.LOCAL,
                passProvenance="check_duplicate_local_immutable_across_ops",
                agentHint=(
                    "delete the per-operation declarations and add one module-scope "
                    "row; references resolve to the module value without rename"
                ),
            ))
    return diagnostics


def check_magic_ascii_byte_literal(facts: ExtendedFacts) -> List[Diagnostic]:
    """``storage local immutable NAME CSignedInt32 V`` where ``V`` is a
    printable-ASCII codepoint (32..126) but the preceding line is not a
    ``# rationale:`` comment naming the character. Either hoist to
    ``storage module immutable`` with a rationale, or add a rationale comment
    so the codepoint-to-character mapping is visible at the declaration site.
    Hoist candidates already flagged by SS4401 are skipped to avoid stacking
    diagnostics on the same line."""
    diagnostics: List[Diagnostic] = []
    duplicateNames: Set[str] = set()
    occurrenceCounts: Dict[Tuple[str, str, str], int] = {}
    for operation in facts.base.operations.values():
        seenInThisOperation: Set[Tuple[str, str, str]] = set()
        for name, typeName, initValue, _line in _scan_op_local_immutables(operation):
            key = (name, typeName, initValue)
            if key in seenInThisOperation:
                continue
            seenInThisOperation.add(key)
            occurrenceCounts[key] = occurrenceCounts.get(key, 0) + 1
    for (name, _typeName, _initValue), count in occurrenceCounts.items():
        if count >= _DUPLICATE_LOCAL_IMMUTABLE_THRESHOLD:
            duplicateNames.add(name)

    for operation in facts.base.operations.values():
        for name, typeName, initValue, sourceLine in _scan_op_local_immutables(operation):
            if typeName != "CSignedInt32":
                continue
            try:
                codepoint = int(initValue)
            except ValueError:
                continue
            if not (32 <= codepoint <= 126):
                continue
            if name in duplicateNames:
                continue
            rationaleText = _preceding_comment_block_text(facts, sourceLine)
            if _rationale_names_ascii_char(rationaleText, codepoint):
                continue
            glyph = chr(codepoint)
            glyphDisplay = "space" if codepoint == 32 else repr(glyph)
            diagnostics.append(Diagnostic(
                tier=Tier.T4_STYLE,
                code="SS4402",
                kind="styleDiscipline.magicAsciiByteLiteral",
                severity=Severity.INFO,
                subjectName=name,
                subjectKind="storageSlot",
                gapEdge="# rationale: comment",
                intentSlogan="printable-ASCII byte without rationale",
                primary=span_of_line(sourceLine, "storageDeclaration"),
                invariantRule=(
                    f"`{name}` holds printable-ASCII codepoint {codepoint} "
                    f"({glyphDisplay}); the preceding line is not a "
                    "`# rationale:` comment naming the character."
                ),
                specAnchor="docs/optimization-guide.md#ascii-byte-literals",
                fixCandidates=[
                    FixCandidate(
                        name="addRationaleComment",
                        shape=f"# rationale: {codepoint} = ASCII {glyphDisplay}.",
                    ),
                    FixCandidate(
                        name="hoistToModuleImmutable",
                        shape=f"storage module immutable ascii<Role> CSignedInt32 {codepoint}",
                    ),
                ],
                confidence=Confidence.MEDIUM,
                effort=Effort.TRIVIAL,
                passProvenance="check_magic_ascii_byte_literal",
                agentHint=(
                    "ASCII byte literals are protocol values, not arithmetic "
                    "constants; name the character role at the declaration site"
                ),
            ))
    return diagnostics


def check_dead_storage_initializer(facts: ExtendedFacts) -> List[Diagnostic]:
    """``storage local mutable NAME TYPE INIT`` immediately followed (skipping
    comments and adjacent storage rows) by ``set local NAME NEW`` with no
    intervening read of NAME is a dead initializer — the declared starting
    value is overwritten before any operation reads it. Replace the
    initializer with the real first value."""
    diagnostics: List[Diagnostic] = []
    for operation in facts.base.operations.values():
        bodyLines = [
            sourceLine for sourceLine in operation.lines
            if sourceLine.tokens and not is_comment(sourceLine)
        ]
        for lineIndex, sourceLine in enumerate(bodyLines):
            if sourceLine.verb != "storage" or len(sourceLine.args) < 4:
                continue
            scope, mutability = sourceLine.args[0], sourceLine.args[1]
            if scope != "local" or mutability != "mutable":
                continue
            name = sourceLine.args[2]
            initToken = sourceLine.args[4] if len(sourceLine.args) >= 5 else ""
            # Skip ahead through any contiguous storage rows (a block of
            # `storage local immutable …` declarations doesn't count as a read).
            cursor = lineIndex + 1
            while cursor < len(bodyLines):
                candidate = bodyLines[cursor]
                if candidate.verb == "storage":
                    cursor += 1
                    continue
                break
            if cursor >= len(bodyLines):
                continue
            nextLine = bodyLines[cursor]
            if nextLine.verb != "set" or len(nextLine.args) < 3:
                continue
            if nextLine.args[0] != "local" or nextLine.args[1] != name:
                continue
            # The set-after-init pattern is real — but only flag if no
            # intervening body line touched the name. Storage rows skipped
            # above never read the name (they introduce fresh slots).
            diagnostics.append(Diagnostic(
                tier=Tier.T4_STYLE,
                code="SS4403",
                kind="styleDiscipline.deadStorageInitializer",
                severity=Severity.INFO,
                subjectName=name,
                subjectKind="storageSlot",
                gapEdge="meaningful initializer",
                intentSlogan="initializer overwritten before any read",
                primary=span_of_line(sourceLine, "storageDeclaration"),
                related=[span_of_line(nextLine, "shadowingSet")],
                invariantRule=(
                    f"`storage local mutable {name}` initializer `{initToken}` is "
                    f"overwritten by `set local {name}` on line {nextLine.number} "
                    "with no read in between"
                ),
                specAnchor="docs/optimization-guide.md#dead-initializers",
                fixCandidates=[
                    FixCandidate(
                        name="seedWithRealFirstValue",
                        shape=(
                            f"storage local mutable {name} <type> {nextLine.args[2]}"
                        ),
                        autoApplicable=False,
                        evidence=[span_of_line(nextLine)],
                    ),
                    FixCandidate(
                        name="moveInitializationDown",
                        shape=(
                            f"# move `storage local mutable {name} <type> <init>` to where "
                            "the first meaningful value is computed"
                        ),
                    ),
                ],
                confidence=Confidence.MEDIUM,
                effort=Effort.TRIVIAL,
                passProvenance="check_dead_storage_initializer",
                agentHint=(
                    "the declared initial value lies about where the loop or block "
                    "actually starts; seed with the real first value or move the "
                    "declaration closer to the use"
                ),
            ))
    return diagnostics


_FIXED_OFFSET_NAME_SUFFIXES: Tuple[str, ...] = ("Offset", "OFFSET")
_FIXED_OFFSET_BLOCK_THRESHOLD = 2
_EMITTER_REFERENCE_TOKENS: Tuple[str, ...] = (
    "format", "emit", "writes", "serializ", "encoder", "produces",
    "lockstep", "coupled", "saveTodos", "produced by", "emitted by",
)


def check_fixed_offset_parser_needs_rationale(facts: ExtendedFacts) -> List[Diagnostic]:
    """An operation that declares two or more ``storage local immutable
    NAME TYPE V`` rows whose names end in ``Offset`` is using the fixed-offset
    parser pattern — a known fragile coupling to whichever emitter produces the
    bytes being indexed. The block must be introduced by a ``# rationale:``
    comment that either names the emitter operation or describes the format
    fragment whose bytes are being counted, so future edits to the emitter
    can update the offsets in lockstep. Without that rationale a downstream
    agent could change either side and silently misparse."""
    diagnostics: List[Diagnostic] = []
    for operation in facts.base.operations.values():
        bodyLines = [
            sourceLine for sourceLine in operation.lines
            if sourceLine.tokens and not is_comment(sourceLine)
        ]
        if not bodyLines:
            continue
        # Walk the body looking for contiguous blocks of offset storage rows.
        index = 0
        while index < len(bodyLines):
            current = bodyLines[index]
            if not _is_offset_storage_row(current):
                index += 1
                continue
            blockStart = index
            while index < len(bodyLines) and _is_offset_storage_row(bodyLines[index]):
                index += 1
            blockSize = index - blockStart
            if blockSize < _FIXED_OFFSET_BLOCK_THRESHOLD:
                continue
            firstRow = bodyLines[blockStart]
            rationaleText = _preceding_comment_block_text(facts, firstRow)
            if any(token.lower() in rationaleText for token in _EMITTER_REFERENCE_TOKENS):
                continue
            offsetNames = sorted({
                bodyLines[i].args[2] for i in range(blockStart, blockStart + blockSize)
                if len(bodyLines[i].args) >= 3
            })
            sampleNames = ", ".join(offsetNames[:4])
            if len(offsetNames) > 4:
                sampleNames = f"{sampleNames}, +{len(offsetNames) - 4} more"
            diagnostics.append(Diagnostic(
                tier=Tier.T4_STYLE,
                code="SS4404",
                kind="styleDiscipline.fixedOffsetParserNeedsRationale",
                severity=Severity.INFO,
                subjectName=operation.name,
                subjectKind="operation",
                gapEdge="# rationale: comment naming emitter",
                intentSlogan="fixed-offset block missing emitter rationale",
                primary=span_of_line(firstRow, "firstOffsetDeclaration"),
                related=[span_of_line(operation.line, "enclosingOperation")],
                invariantRule=(
                    f"operation `{operation.name}` declares {blockSize} `*Offset` "
                    f"storage rows ({sampleNames}) without a preceding `# rationale:` "
                    "comment naming the emitter operation or the format-string "
                    "derivation; fixed-offset parsing silently drifts when the "
                    "emitter's format changes."
                ),
                specAnchor="docs/optimization-guide.md#implicit-format-coupling",
                fixCandidates=[
                    FixCandidate(
                        name="addEmitterRationale",
                        shape=(
                            "# rationale: Offsets count bytes into the line written "
                            "by <emitterOperation>'s <formatConstant>; any edit to "
                            "<formatConstant> must update these offsets in lockstep."
                        ),
                    ),
                    FixCandidate(
                        name="addInvariantNamingCoupling",
                        shape=(
                            f"invariant {operation.name} \"Offset constants are coupled "
                            "to <emitterOperation>'s format string.\""
                        ),
                    ),
                ],
                confidence=Confidence.MEDIUM,
                effort=Effort.TRIVIAL,
                passProvenance="check_fixed_offset_parser_needs_rationale",
                agentHint=(
                    "the offset block is the parser side of a producer/consumer "
                    "pair; name the producer at the declaration site so a future "
                    "edit to the format string is reviewable"
                ),
            ))
    return diagnostics


def _is_offset_storage_row(sourceLine: SourceLine) -> bool:
    if sourceLine.verb != "storage" or len(sourceLine.args) < 4:
        return False
    if sourceLine.args[0] != "local" or sourceLine.args[1] != "immutable":
        return False
    name = sourceLine.args[2]
    return any(name.endswith(suffix) for suffix in _FIXED_OFFSET_NAME_SUFFIXES)


_INT_COMPARISON_TARGET_TO_ENUM_METHOD: Dict[str, str] = {
    "math.equalI64":                       "equal",
    "math.notEqualI64":                    "notEqual",
    "math.lessThanI64":                    "lessThan",
    "math.lessThanOrEqualI64":             "lessThanOrEqual",
    "math.greaterThanI64":                 "greaterThan",
    "math.greaterThanOrEqualI64":          "greaterThanOrEqual",
    "math.equalCSignedInt32":              "equal",
    "math.notEqualCSignedInt32":           "notEqual",
    "math.lessThanCSignedInt32":           "lessThan",
    "math.lessThanOrEqualCSignedInt32":    "lessThanOrEqual",
    "math.greaterThanCSignedInt32":        "greaterThan",
    "math.greaterThanOrEqualCSignedInt32": "greaterThanOrEqual",
}


def check_enum_repr_comparison(facts: ExtendedFacts) -> List[Diagnostic]:
    """A `math.equal*` / `math.notEqual*` / `math.lessThan*` /
    `math.greaterThan*` call whose operand binds, inputs, storage values,
    enum cases, or module-scope values resolve to an enum type is leaking
    the enum's repr into the call site. Use the typed `EnumName.equal`
    domain-method form instead so the source-level call expresses the
    enum identity, not the underlying integer width."""
    diagnostics: List[Diagnostic] = []
    enumReprs, _enumCasesByType, _enumCaseValuesByType, enumTypeByCase = _enum_context(facts)
    enumNames: Set[str] = set(enumReprs.keys())
    if not enumNames:
        return diagnostics

    moduleScopeValueTypes: Dict[str, str] = {
        name: constFact.type_name
        for name, constFact in facts.base.consts.items()
    }
    insideOperation = False
    for sourceLine in facts.base.lines:
        if not sourceLine.tokens or is_comment(sourceLine):
            continue
        verb = sourceLine.verb
        args = sourceLine.args
        if verb == "operation" and args:
            insideOperation = True
            continue
        if insideOperation:
            continue
        if verb == "storage" and len(args) >= 5:
            moduleScopeValueTypes[args[2]] = args[3]
        elif verb == "sharedState" and len(args) >= 5:
            moduleScopeValueTypes[args[2]] = args[3]
        elif verb == "enumCase" and len(args) >= 2:
            moduleScopeValueTypes[args[1]] = args[0]

    for operation in facts.base.operations.values():
        operationCitations = narrative_citations_for_operation(facts, operation.name)
        valueTypesInScope: Dict[str, str] = dict(moduleScopeValueTypes)
        callTargetByCallName: Dict[str, Tuple[SourceLine, str]] = {}
        argLinesByCallName: Dict[str, List[SourceLine]] = {}

        for sourceLine in operation.lines:
            if not sourceLine.tokens or is_comment(sourceLine):
                continue
            verb = sourceLine.verb
            args = sourceLine.args
            if verb == "input" and len(args) >= 3 and args[0] == operation.name:
                valueTypesInScope[args[1]] = args[2]
            elif verb == "storage" and len(args) >= 5:
                valueTypesInScope[args[2]] = args[3]
            elif verb in {"bind", "bindOk", "bindError"} and len(args) >= 3:
                valueTypesInScope[args[0]] = args[1]
            elif verb == "call" and len(args) >= 2:
                callTargetByCallName[args[0]] = (sourceLine, args[1])
            elif verb == "arg" and len(args) >= 3:
                argLinesByCallName.setdefault(args[0], []).append(sourceLine)

        for callName, (callLine, targetName) in callTargetByCallName.items():
            enumMethod = _INT_COMPARISON_TARGET_TO_ENUM_METHOD.get(targetName)
            if enumMethod is None:
                continue
            enumOperandTypes: Set[str] = set()
            for argLine in argLinesByCallName.get(callName, []):
                operandName = argLine.args[2]
                operandType = valueTypesInScope.get(operandName)
                if operandType is None and operandName in enumTypeByCase:
                    operandType = enumTypeByCase[operandName]
                if operandType in enumNames:
                    enumOperandTypes.add(operandType)
            if not enumOperandTypes:
                continue
            enumName = sorted(enumOperandTypes)[0]
            suggestedTarget = f"{enumName}.{enumMethod}"
            diagnostics.append(Diagnostic(
                tier=Tier.T4_STYLE,
                code="SS4405",
                kind="styleDiscipline.enumReprComparison",
                severity=Severity.INFO,
                subjectName=callName,
                subjectKind="call",
                gapEdge="EnumName.<method> domain target",
                intentSlogan="enum compared via raw-width math target",
                primary=span_of_line(callLine, "rawWidthCompareCall"),
                related=[span_of_line(operation.line, "enclosingOperation")],
                invariantRule=(
                    f"`{targetName}` is comparing values of enum type "
                    f"`{enumName}` directly. The enum's repr is leaking into "
                    f"the call site; use `{suggestedTarget}` instead so the "
                    f"source compare expresses the enum, not the integer width."
                ),
                specAnchor="SYNTAX.md#enum-domain-methods",
                citations=operationCitations,
                fixCandidates=[
                    FixCandidate(
                        name="useEnumDomainMethod",
                        shape=f"call {callName} {suggestedTarget}",
                        autoApplicable=True,
                        evidence=[span_of_line(callLine)],
                    ),
                ],
                confidence=Confidence.HIGH,
                effort=Effort.TRIVIAL,
                passProvenance="check_enum_repr_comparison",
                agentHint=(
                    "rename the call target only; argument lines stay the "
                    "same — the compiler resolves the enum's repr"
                ),
            ))
    return diagnostics


def check_enum_result_discarded(facts: ExtendedFacts) -> List[Diagnostic]:
    """`ignoreValue CALL TYPE` where TYPE is the name of a declared enum is
    silently dropping a value that carries semantic alternatives. Enum
    returns are not raw scalars: each case is a distinct outcome the
    caller chose not to act on. Bind the result and either branch on the
    cases or add a `# rationale:` line explaining why every case is
    acceptable."""
    diagnostics: List[Diagnostic] = []
    enumReprs, _enumCasesByType, _enumCaseValuesByType, _enumTypeByCase = _enum_context(facts)
    enumNames: Set[str] = set(enumReprs.keys())
    if not enumNames:
        return diagnostics

    for operation in facts.base.operations.values():
        operationCitations = narrative_citations_for_operation(facts, operation.name)
        for sourceLine in operation.lines:
            if not sourceLine.tokens or is_comment(sourceLine):
                continue
            if sourceLine.verb != "ignoreValue" or len(sourceLine.args) < 2:
                continue
            callName = sourceLine.args[0]
            discardedType = sourceLine.args[1]
            if discardedType not in enumNames:
                continue
            diagnostics.append(Diagnostic(
                tier=Tier.T4_STYLE,
                code="SS4406",
                kind="styleDiscipline.enumResultDiscarded",
                severity=Severity.INFO,
                subjectName=callName,
                subjectKind="call",
                gapEdge="bind + branch (or # rationale:)",
                intentSlogan="enum result silently discarded",
                primary=span_of_line(sourceLine, "ignoreValueRow"),
                related=[span_of_line(operation.line, "enclosingOperation")],
                invariantRule=(
                    f"`ignoreValue {callName} {discardedType}` discards an "
                    f"enum-typed return. Each enum case is a distinct outcome; "
                    "the discard claims every case is equally acceptable. "
                    "Bind the result and branch on the cases, or add a "
                    "preceding `# rationale:` comment justifying the discard."
                ),
                specAnchor="docs/optimization-guide.md#enum-result-discipline",
                citations=operationCitations,
                fixCandidates=[
                    FixCandidate(
                        name="bindAndBranchOnEnum",
                        shape=f"bind {callName}Result {discardedType} {callName}",
                    ),
                    FixCandidate(
                        name="documentDiscardRationale",
                        shape=(
                            f"# rationale: every {discardedType} case is acceptable "
                            "here because <state why>."
                        ),
                    ),
                ],
                confidence=Confidence.MEDIUM,
                effort=Effort.TRIVIAL,
                passProvenance="check_enum_result_discarded",
                agentHint=(
                    "an enum return is the call's contract — discarding it "
                    "with no rationale claims all cases are interchangeable"
                ),
            ))
    return diagnostics


import re as _ss4407_re

_PAIRED_EQUALITY_ANCHOR_RE = _ss4407_re.compile(
    r"\bmust\s+stay\s+equal\b|\bmust\s+be\s+equal\b",
    _ss4407_re.IGNORECASE,
)
_PAIRED_NAMES_RE = _ss4407_re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*)\b")


def check_paired_scalar_must_stay_equal(facts: ExtendedFacts) -> List[Diagnostic]:
    """An `invariant OP "..."` text that says two storage scalars `MUST stay
    equal` is a hand-rolled equality contract the compiler cannot enforce.
    Locate every identifier in the invariant text that resolves to a
    declared storage scalar (module or operation-local), and flag if two
    named scalars carry different literal init values. Catches drift like:

        invariant main "lineBufferBytes and lineBufferCapacity MUST stay equal"
        storage local immutable lineBufferBytes CByteCount 384
        storage local immutable lineBufferCapacity CSignedInt32 256   # drift

    Suppression: rephrase the invariant so it no longer contains the
    `must stay equal` anchor, or resync the divergent init values."""
    diagnostics: List[Diagnostic] = []

    moduleScopeValues: Dict[str, Tuple[str, SourceLine]] = {}
    operationScopeValues: Dict[str, Dict[str, Tuple[str, SourceLine]]] = {}
    insideOperation: Optional[str] = None
    for sourceLine in facts.base.lines:
        if not sourceLine.tokens or is_comment(sourceLine):
            continue
        if sourceLine.verb == "operation" and sourceLine.args:
            insideOperation = sourceLine.args[0]
            operationScopeValues.setdefault(insideOperation, {})
            continue
        if sourceLine.verb == "storage" and len(sourceLine.args) >= 5:
            scope = sourceLine.args[0]
            name = sourceLine.args[2]
            init = sourceLine.args[4]
            if scope == "module":
                moduleScopeValues[name] = (init, sourceLine)
            elif scope == "local" and insideOperation is not None:
                operationScopeValues.setdefault(insideOperation, {})[name] = (init, sourceLine)

    for operation in facts.base.operations.values():
        operationCitations = narrative_citations_for_operation(facts, operation.name)
        for sourceLine in operation.lines:
            if (is_comment(sourceLine) or not sourceLine.tokens
                    or sourceLine.verb != "invariant"
                    or len(sourceLine.args) < 2):
                continue
            invariantText = sourceLine.args[1]
            if not isinstance(invariantText, str):
                continue
            if not _PAIRED_EQUALITY_ANCHOR_RE.search(invariantText):
                continue
            scopeIndex = dict(moduleScopeValues)
            scopeIndex.update(operationScopeValues.get(operation.name, {}))
            mentionedScalars: List[Tuple[str, str, SourceLine]] = []
            seenNames: Set[str] = set()
            for nameMatch in _PAIRED_NAMES_RE.findall(invariantText):
                if nameMatch in seenNames:
                    continue
                if nameMatch in scopeIndex:
                    initValue, declLine = scopeIndex[nameMatch]
                    mentionedScalars.append((nameMatch, initValue, declLine))
                    seenNames.add(nameMatch)
            if len(mentionedScalars) < 2:
                continue
            valuesSeen = {init for _name, init, _ln in mentionedScalars}
            if len(valuesSeen) == 1:
                continue
            valuesByName = ", ".join(
                f"{name}={init}" for name, init, _ln in mentionedScalars
            )
            diagnostics.append(Diagnostic(
                tier=Tier.T4_STYLE,
                code="SS4407",
                kind="styleDiscipline.pairedScalarMustStayEqual",
                severity=Severity.WARNING,
                subjectName=operation.name,
                subjectKind="operation",
                gapEdge="equal init values",
                intentSlogan="paired-scalar invariant violated",
                primary=span_of_line(sourceLine, "pairedInvariant"),
                related=[span_of_line(declLine, "storageDeclaration")
                         for _name, _init, declLine in mentionedScalars],
                invariantRule=(
                    f"`{operation.name}` declares an invariant that names "
                    f"these storage scalars as paired (`MUST stay equal`), "
                    f"but their init values diverge: {valuesByName}. Either "
                    f"resync the declared values or rephrase the invariant "
                    f"to remove the `must stay equal` claim."
                ),
                specAnchor="docs/optimization-guide.md#hoist-shared-immutables-to-module-scope",
                citations=operationCitations,
                fixCandidates=[
                    FixCandidate(
                        name="resyncInitValues",
                        shape=(
                            "# update the divergent storage init values to "
                            "match each other"
                        ),
                    ),
                    FixCandidate(
                        name="dropPairedEqualityClaim",
                        shape=(
                            "# rephrase the invariant so it no longer asserts "
                            "the two scalars must stay equal"
                        ),
                    ),
                ],
                confidence=Confidence.MEDIUM,
                effort=Effort.TRIVIAL,
                passProvenance="check_paired_scalar_must_stay_equal",
                agentHint=(
                    "the invariant is the source of truth for the pairing "
                    "claim; bring the storage init values into agreement"
                ),
            ))
    return diagnostics


def _is_top_level_sem_sample(path: Path) -> bool:
    return path.suffix == ".sem" and path.parent.name == "sem"


def _declares_agent_runtime_one_zero(facts: ExtendedFacts) -> bool:
    return any(
        sourceLine.verb == "runtime"
        and len(sourceLine.args) >= 2
        and sourceLine.args[0] == "AgentRuntime"
        and sourceLine.args[1] == "1.0"
        for sourceLine in facts.base.lines
        if sourceLine.tokens and not is_comment(sourceLine)
    )


def check_sem_one_zero_legacy_forms(facts: ExtendedFacts) -> List[Diagnostic]:
    """Top-level `.sem` samples that declare AgentRuntime 1.0 should use the
    current storage/memory forms, not legacy const/var/memory or scopeless set.
    Feature tests and old `.sscript` sources are intentionally outside this
    rule's scope."""
    diagnostics: List[Diagnostic] = []
    if not _is_top_level_sem_sample(facts.base.path):
        return diagnostics
    if not _declares_agent_runtime_one_zero(facts):
        return diagnostics

    for sourceLine in facts.base.lines:
        if not sourceLine.tokens or is_comment(sourceLine):
            continue
        verb = sourceLine.verb
        isLegacySet = (
            verb == "set"
            and sourceLine.args
            and sourceLine.args[0] not in {"local", "module", "sharedState"}
        )
        if verb not in {"const", "var", "memory"} and not isLegacySet:
            continue
        diagnostics.append(Diagnostic(
            tier=Tier.T4_STYLE,
            code="SS4005",
            kind="style.semOneZeroLegacyForm",
            severity=Severity.INFO,
            subjectName=verb,
            subjectKind="verb",
            gapEdge="oneZeroForm",
            intentSlogan="AgentRuntime 1.0 .sem sample uses a legacy local form",
            primary=span_of_line(sourceLine, "legacyForm"),
            invariantRule=(
                "top-level `.sem` samples declaring AgentRuntime 1.0 should use "
                "`storage local immutable`, `storage local mutable`, `set local`, "
                "`memoryHeap`, and `memoryStackLimit`"
            ),
            specAnchor="SYNTAX.md#storage",
            fixCandidates=[
                FixCandidate(
                    name="convertToOneZeroForm",
                    shape="# convert legacy declaration to the 1.0 storage/memory form",
                    evidence=[span_of_line(sourceLine)],
                ),
            ],
            confidence=Confidence.HIGH,
            effort=Effort.TRIVIAL,
            passProvenance="check_sem_one_zero_legacy_forms",
            agentHint="do not update benchmark sources just to satisfy this sample-style rule",
        ))
    return diagnostics


def check_declaration_only_sample(facts: ExtendedFacts) -> List[Diagnostic]:
    """Top-level `.sem` samples should contain an executable source tape.
    This prevents parity samples from becoming constants-only fixtures that
    accidentally match output while exercising no calls or control flow."""
    diagnostics: List[Diagnostic] = []
    if not _is_top_level_sem_sample(facts.base.path):
        return diagnostics

    executableVerbs = {
        "call", "arg", "run", "start", "await",
        "bind", "bindOk", "bindError", "ignoreOk", "ignoreValue",
        "makeError", "declareFailure",
        "branch", "branchIf", "branchIfError",
        "returnOk", "returnError", "returnValue",
        "set", "new", "fieldSet", "fieldGet", "recordBuild",
    }
    activeVerbs = [
        sourceLine.verb
        for sourceLine in facts.base.lines
        if sourceLine.tokens and not is_comment(sourceLine)
    ]
    executableCount = sum(1 for verb in activeVerbs if verb in executableVerbs)
    hasCall = "call" in activeVerbs
    hasRun = "run" in activeVerbs
    if hasCall and hasRun and executableCount >= 4:
        return diagnostics

    primaryLine = next(
        (
            sourceLine
            for sourceLine in facts.base.lines
            if sourceLine.tokens and not is_comment(sourceLine)
        ),
        None,
    )
    if primaryLine is None:
        return diagnostics

    diagnostics.append(Diagnostic(
        tier=Tier.T4_STYLE,
        code="SS4006",
        kind="style.declarationOnlySample",
        severity=Severity.INFO,
        subjectName=facts.base.path.name,
        subjectKind="sampleProgram",
        gapEdge="executableSourceTape",
        intentSlogan="top-level .sem sample has too little executable code",
        primary=span_of_line(primaryLine, "sampleStart"),
        invariantRule=(
            "top-level `.sem` samples should include call/run/control-flow rows "
            "so they exercise the compiler rather than only storing constants"
        ),
        specAnchor="SYNTAX.md#call",
        fixCandidates=[
            FixCandidate(
                name="addExecutableSourceTape",
                shape="# add call/run/bind/branch rows that compute or emit the sample behavior",
            ),
        ],
        confidence=Confidence.HIGH,
        effort=Effort.LOCAL,
        passProvenance="check_declaration_only_sample",
        agentHint=(
            "capturedOutputReplay samples are allowed, but they still need an "
            "honest executable write/error path"
        ),
    ))
    return diagnostics


def check_allocation_in_loop(facts: ExtendedFacts) -> List[Diagnostic]:
    """Heap-allocating call inside a label that's branched back to (loop
    body). Each iteration allocates afresh — usually unintended."""
    diagnostics: List[Diagnostic] = []
    for operation in facts.base.operations.values():
        operationCitations = narrative_citations_for_operation(facts, operation.name)
        labelIndexByName: Dict[str, int] = {}
        for lineIndex, sourceLine in enumerate(operation.lines):
            if is_comment(sourceLine) or not sourceLine.tokens:
                continue
            if sourceLine.verb == "label" and sourceLine.args:
                labelIndexByName[sourceLine.args[0]] = lineIndex

        # For each back-branch, the loop body is [labelIndex, branchIndex]
        loopBodyRanges: List[Tuple[int, int, str]] = []  # (start, end, labelName)
        for lineIndex, sourceLine in enumerate(operation.lines):
            if is_comment(sourceLine) or not sourceLine.tokens:
                continue
            verb = sourceLine.verb
            args = sourceLine.args
            branchTarget: Optional[str] = None
            if verb == "branch" and args:
                branchTarget = args[0]
            elif verb == "branchIf" and len(args) >= 2:
                branchTarget = args[1]
            elif verb in {"branchIfError", "branchIfGroupError", "branchIfChannelClosed"} and len(args) >= 2:
                branchTarget = args[1]
            elif verb == "branchSelected" and len(args) >= 3:
                branchTarget = args[2]
            if not branchTarget:
                continue
            labelIndex = labelIndexByName.get(branchTarget)
            if labelIndex is None or labelIndex >= lineIndex:
                # Forward branch, not a back-edge — skip
                continue
            loopBodyRanges.append((labelIndex, lineIndex, branchTarget))

        # Find heap-allocating calls in each loop body
        operationCallsByName = collect_operation_calls(operation)
        for loopStart, loopEnd, loopLabel in loopBodyRanges:
            for bodyLine in operation.lines[loopStart:loopEnd]:
                if is_comment(bodyLine) or not bodyLine.tokens:
                    continue
                if bodyLine.verb != "call" or len(bodyLine.args) < 2:
                    continue
                if bodyLine.args[1] not in HEAP_ALLOCATION_CALL_TARGETS:
                    continue
                diagnostics.append(Diagnostic(
                    tier=Tier.T3_REFINEMENT,
                    code="SS3202",
                    kind="performanceDiscipline.allocationInLoop",
                    severity=Severity.WARNING,
                    subjectName=bodyLine.args[0],
                    subjectKind="call",
                    gapEdge="loopHoist",
                    intentSlogan="heap allocation in loop body",
                    primary=span_of_line(bodyLine, "allocatingCallInLoop"),
                    related=[
                        span_of_line(operation.lines[loopStart], "loopHeaderLabel"),
                        span_of_line(operation.line, "enclosingOperation"),
                    ],
                    invariantRule=(
                        f"`{bodyLine.args[1]}` allocates fresh memory each "
                        f"iteration; hoist the allocation above the `label "
                        f"{loopLabel}` loop header"
                    ),
                    specAnchor="SYNTAX.md#label",
                    citations=operationCitations,
                    fixCandidates=[
                        FixCandidate(
                            name="hoistAllocationAboveLoop",
                            shape=(
                                f"# move `call {bodyLine.args[0]} {bodyLine.args[1]}` "
                                f"and its arg lines BEFORE `label {loopLabel}`"
                            ),
                            evidence=[span_of_line(bodyLine)],
                        ),
                    ],
                    confidence=Confidence.HIGH,
                    effort=Effort.LOCAL,
                    passProvenance="check_allocation_in_loop",
                    agentHint="allocating once and reusing avoids both allocator pressure and leak risk per-iteration",
                ))
    return diagnostics


def check_bind_then_ignore(facts: ExtendedFacts) -> List[Diagnostic]:
    """`bind X T call` immediately followed by `ignoreValue X T` declares a
    binding only to discard it. Use `ignoreValue call T` directly instead."""
    diagnostics: List[Diagnostic] = []
    for operation in facts.base.operations.values():
        operationCitations = narrative_citations_for_operation(facts, operation.name)
        operationBodyLines = [
            sourceLine for sourceLine in operation.lines
            if not is_comment(sourceLine) and sourceLine.tokens
        ]
        for index in range(len(operationBodyLines) - 1):
            currentLine = operationBodyLines[index]
            nextLine = operationBodyLines[index + 1]
            if currentLine.verb != "bind" or len(currentLine.args) < 3:
                continue
            if nextLine.verb != "ignoreValue" or not nextLine.args:
                continue
            boundName = currentLine.args[0]
            if nextLine.args[0] != boundName:
                continue
            diagnostics.append(Diagnostic(
                tier=Tier.T3_REFINEMENT,
                code="SS3204",
                kind="performanceDiscipline.bindThenIgnore",
                severity=Severity.WARNING,
                subjectName=boundName,
                subjectKind="bind",
                gapEdge="redundantBinding",
                intentSlogan="bind only to ignore — collapse to direct ignoreValue",
                primary=span_of_line(currentLine, "bindDeclaration"),
                related=[span_of_line(nextLine, "ignoreValueSite")],
                invariantRule="binding a value just to discard it is redundant; ignoreValue the call directly",
                specAnchor="SYNTAX.md#ignoreValue",
                citations=operationCitations,
                fixCandidates=[
                    FixCandidate(
                        name="collapseToDirectIgnoreValue",
                        shape=f"# remove `bind {boundName} …`; keep only `ignoreValue {currentLine.args[2]} {currentLine.args[1]}`",
                        autoApplicable=True,
                        evidence=[span_of_line(currentLine)],
                    ),
                ],
                confidence=Confidence.HIGH,
                effort=Effort.TRIVIAL,
                passProvenance="check_bind_then_ignore",
                agentHint="ignoreValue can name the call directly; the intermediate bind serves no purpose",
            ))
    return diagnostics


def check_memory_heap_contradiction(facts: ExtendedFacts) -> List[Diagnostic]:
    """`memoryHeap OP no` but op body contains a heap-allocating call.
    Body contradicts declared intent."""
    diagnostics: List[Diagnostic] = []
    for operation in facts.base.operations.values():
        heapDeclaration = facts.operationMemoryHeapAllowed.get(operation.name)
        if heapDeclaration is None:
            continue
        heapDeclarationLine, heapAllowed = heapDeclaration
        if heapAllowed:
            continue
        operationCitations = narrative_citations_for_operation(facts, operation.name)
        for sourceLine in operation.lines:
            if is_comment(sourceLine) or not sourceLine.tokens:
                continue
            if sourceLine.verb != "call" or len(sourceLine.args) < 2:
                continue
            if sourceLine.args[1] not in HEAP_ALLOCATION_CALL_TARGETS:
                continue
            diagnostics.append(Diagnostic(
                tier=Tier.T3_REFINEMENT,
                code="SS3301",
                kind="memoryDiscipline.heapContradiction",
                severity=Severity.WARNING,
                subjectName=operation.name,
                subjectKind="operation",
                gapEdge="memoryHeap",
                intentSlogan="memoryHeap=no contradicted by allocating body call",
                primary=span_of_line(sourceLine, "allocatingCall"),
                related=[
                    span_of_line(heapDeclarationLine, "memoryHeapDeclaration"),
                    span_of_line(operation.line, "enclosingOperation"),
                ],
                invariantRule=(
                    f"`memoryHeap {operation.name} no` forbids heap allocation but "
                    f"body calls `{sourceLine.args[1]}`"
                ),
                specAnchor="SYNTAX.md#memoryHeap",
                citations=operationCitations,
                fixCandidates=[
                    FixCandidate(
                        # Bundle BOTH the heap=yes flip AND the allocation source
                        # declaration to pre-empt SS3302 cascading next.
                        name="permitHeapAndDeclareAllocationSource",
                        shape=(
                            f"memoryHeap {operation.name} yes\n"
                            f"memoryAllocationSource {operation.name} {sourceLine.args[0]}"
                        ),
                        evidence=[span_of_line(heapDeclarationLine), span_of_line(sourceLine)],
                    ),
                    FixCandidate(
                        name="removeOrReplaceAllocation",
                        shape=f"# replace `{sourceLine.args[1]}` with a stack-only equivalent or remove",
                    ),
                ],
                confidence=Confidence.HIGH,
                effort=Effort.LOCAL,
                passProvenance="check_memory_heap_contradiction",
                agentHint=(
                    "flipping memoryHeap to yes without an allocationSource trips "
                    "SS3302 next; the bundled fix avoids the cascade"
                ),
            ))
    return diagnostics


def check_allocation_source_missing(facts: ExtendedFacts) -> List[Diagnostic]:
    """`memoryHeap OP yes` but no `memoryAllocationSource OP <call>` row.
    Caller cannot audit which call holds the allocation contract."""
    diagnostics: List[Diagnostic] = []
    for operationName, (heapLine, heapAllowed) in facts.operationMemoryHeapAllowed.items():
        if not heapAllowed:
            continue
        if facts.operationMemoryAllocationSource.get(operationName):
            continue
        operation = facts.base.operations.get(operationName)
        if operation is None:
            continue
        # Find a body call that could be the source, to suggest a fix
        allocatingCallName: Optional[str] = None
        for sourceLine in operation.lines:
            if (not is_comment(sourceLine) and sourceLine.tokens
                    and sourceLine.verb == "call" and len(sourceLine.args) >= 2
                    and sourceLine.args[1] in HEAP_ALLOCATION_CALL_TARGETS):
                allocatingCallName = sourceLine.args[0]
                break
        diagnostics.append(Diagnostic(
            tier=Tier.T3_REFINEMENT,
            code="SS3302",
            kind="memoryDiscipline.allocationSourceMissing",
            severity=Severity.WARNING,
            subjectName=operationName,
            subjectKind="operation",
            gapEdge="memoryAllocationSource",
            intentSlogan="memoryHeap=yes but no allocation source declared",
            primary=span_of_line(heapLine, "memoryHeapDeclaration"),
            related=[span_of_line(operation.line, "enclosingOperation")],
            invariantRule=(
                f"`memoryHeap {operationName} yes` requires "
                f"`memoryAllocationSource {operationName} <callName>` so the "
                f"allocator contract is auditable"
            ),
            specAnchor="SYNTAX.md#memoryAllocationSource",
            citations=narrative_citations_for_operation(facts, operationName),
            fixCandidates=[
                FixCandidate(
                    name="declareAllocationSource",
                    shape=f"memoryAllocationSource {operationName} {allocatingCallName or '<allocatingCallName>'}",
                ),
            ],
            confidence=Confidence.HIGH,
            effort=Effort.TRIVIAL,
            passProvenance="check_allocation_source_missing",
            agentHint="the allocation source points callers at the specific call that may fail with out-of-memory",
        ))
    return diagnostics


def check_allocate_free_unpaired(facts: ExtendedFacts) -> List[Diagnostic]:
    """Op body allocates heap memory but has no paired cleanup in the same op."""
    diagnostics: List[Diagnostic] = []
    for operation in facts.base.operations.values():
        operationCitations = narrative_citations_for_operation(facts, operation.name)
        operationCalls = collect_operation_calls(operation)
        operationDefers = facts.operationDefers.get(operation.name, [])
        hasFreeDefer = any(
            target in HEAP_DEALLOCATION_CALL_TARGETS
            for _line, target in operationDefers
        )
        if hasFreeDefer:
            continue
        for callFact in operationCalls.values():
            if callFact.target not in HEAP_ALLOCATION_CALL_TARGETS:
                continue
            if call_has_later_cleanup_call(
                callFact,
                operationCalls,
                set(HEAP_DEALLOCATION_CALL_TARGETS),
            ):
                continue
            # Skip ops whose declared purpose IS to allocate-and-return (the
            # alloc moves ownership to the caller). Heuristic: op output type
            # is a pointer (COpaqueMemoryAddress, CNullTerminatedByteString, …).
            outputLine = None
            for line in operation.lines:
                if line.verb == "output" and line.args and line.args[0] == operation.name:
                    outputLine = line
                    break
            if outputLine and len(outputLine.args) >= 2:
                outputTypeName = outputLine.args[1]
                if outputTypeName in {"COpaqueMemoryAddress", "CNullTerminatedByteString", "CFileHandle"}:
                    # Likely an allocator wrapper — caller owns the lifetime.
                    continue
                if outputTypeName == "Result" and len(outputLine.args) >= 3:
                    if outputLine.args[2] in {"COpaqueMemoryAddress", "CNullTerminatedByteString", "CFileHandle"}:
                        continue
            diagnostics.append(Diagnostic(
                tier=Tier.T3_REFINEMENT,
                code="SS3303",
                kind="resourceLifecycle.allocateFreeUnpaired",
                severity=Severity.WARNING,
                subjectName=callFact.name,
                subjectKind="call",
                gapEdge="defer",
                intentSlogan="heap allocation without paired free defer",
                primary=span_of_line(callFact.line, "allocatingCall"),
                related=[span_of_line(operation.line, "enclosingOperation")],
                invariantRule=(
                    f"every `{callFact.target}` should be paired with a "
                    f"`defer NAME c.free <pointerArg>` or explicit `c.free` "
                    "cleanup in the same operation"
                ),
                specAnchor="SYNTAX.md#defer",
                citations=operationCitations,
                fixCandidates=[
                    FixCandidate(
                        name="addFreeDefer",
                        shape=f"defer release{callFact.name[:1].upper()}{callFact.name[1:]} c.free <allocatedPointer>",
                        evidence=[span_of_line(callFact.line)],
                    ),
                ],
                confidence=Confidence.HIGH,
                effort=Effort.LOCAL,
                passProvenance="check_allocate_free_unpaired",
                agentHint="if the op returns the pointer to the caller, mark the output type as a pointer alias and this check is suppressed",
            ))
    return diagnostics


def _estimate_operation_alloca_bytes(operation: OperationFact) -> int:
    """Conservative stack-byte estimate. Counts `const`, `bind*`, `var`,
    `new`, `recordSet` declarations; unknown types contribute 8 (pointer-
    sized pessimism). Always under-counts on unions and records-with-
    embedded-arrays — those need full type resolution."""
    estimatedBytes = 0
    for sourceLine in operation.lines:
        if is_comment(sourceLine) or not sourceLine.tokens:
            continue
        verb = sourceLine.verb
        args = sourceLine.args
        if verb in {"const", "var"} and len(args) >= 2:
            estimatedBytes += PRIMITIVE_TYPE_STACK_BYTES.get(args[1], 8)
        elif verb in {"bind", "bindOk", "bindError"} and len(args) >= 2:
            estimatedBytes += PRIMITIVE_TYPE_STACK_BYTES.get(args[1], 8)
        elif verb == "new" and args:
            estimatedBytes += 32  # record-sized pessimism
    return estimatedBytes


def check_stack_limit_overrun(facts: ExtendedFacts) -> List[Diagnostic]:
    """Sum of estimated alloca bytes exceeds declared `memoryStackLimit`.
    Heuristic — under-counts records, but never silently OVER-counts."""
    diagnostics: List[Diagnostic] = []
    for operationName, (stackLine, declaredLimitBytes) in facts.operationMemoryStackLimitBytes.items():
        operation = facts.base.operations.get(operationName)
        if operation is None:
            continue
        estimatedBytes = _estimate_operation_alloca_bytes(operation)
        if estimatedBytes <= declaredLimitBytes:
            continue
        diagnostics.append(Diagnostic(
            tier=Tier.T3_REFINEMENT,
            code="SS3304",
            kind="memoryDiscipline.stackLimitOverrun",
            severity=Severity.WARNING,
            subjectName=operationName,
            subjectKind="operation",
            gapEdge="memoryStackLimit",
            intentSlogan="estimated allocas exceed declared stack limit",
            primary=span_of_line(stackLine, "memoryStackLimitDeclaration"),
            related=[span_of_line(operation.line, "enclosingOperation")],
            invariantRule=(
                f"declared `memoryStackLimit {operationName} {declaredLimitBytes}` is "
                f"smaller than the estimated alloca footprint ({estimatedBytes} bytes)"
            ),
            specAnchor="SYNTAX.md#memoryStackLimit",
            citations=narrative_citations_for_operation(facts, operationName),
            fixCandidates=[
                FixCandidate(
                    name="raiseStackLimit",
                    shape=f"memoryStackLimit {operationName} {max(declaredLimitBytes, estimatedBytes * 2)}",
                ),
                FixCandidate(
                    name="reduceAllocations",
                    shape="# move large records / lists to heap via memoryHeap yes + memoryAllocationSource",
                ),
            ],
            confidence=Confidence.MEDIUM,
            effort=Effort.LOCAL,
            passProvenance="check_stack_limit_overrun",
            agentHint=(
                "estimate is conservative (8 bytes per unknown-type bind); "
                "if records are involved, the true footprint may be higher"
            ),
        ))
    return diagnostics


def check_record_align_power_of_two(facts: ExtendedFacts) -> List[Diagnostic]:
    """`recordAlign NAME N` requires N ∈ {1,2,4,8,16,32,64}. Non-pow-2
    alignment is unsupported on every mainstream ABI."""
    diagnostics: List[Diagnostic] = []
    validAlignments = {1, 2, 4, 8, 16, 32, 64}
    for recordName, (alignLine, alignValue) in facts.recordAlignDeclarations.items():
        if alignValue in validAlignments:
            continue
        nearestPowerOfTwo = 1 << max(0, (alignValue - 1).bit_length())
        diagnostics.append(Diagnostic(
            tier=Tier.T3_REFINEMENT,
            code="SS3401",
            kind="layoutDiscipline.recordAlignNotPowerOfTwo",
            severity=Severity.WARNING,
            subjectName=recordName,
            subjectKind="record",
            gapEdge="recordAlign",
            intentSlogan="record alignment must be power of two",
            primary=span_of_line(alignLine, "recordAlignDeclaration"),
            invariantRule="recordAlign values must be in {1, 2, 4, 8, 16, 32, 64}",
            specAnchor="SYNTAX.md#recordAlign",
            fixCandidates=[
                FixCandidate(
                    name="alignToNearestPowerOfTwo",
                    shape=f"recordAlign {recordName} {nearestPowerOfTwo}",
                ),
            ],
            confidence=Confidence.HIGH,
            effort=Effort.TRIVIAL,
            passProvenance="check_record_align_power_of_two",
            agentHint="every mainstream ABI requires power-of-two record alignment",
        ))
    return diagnostics


def check_array_length_zero(facts: ExtendedFacts) -> List[Diagnostic]:
    """`arrayLength NAME 0` is almost always a bug — fixed-length arrays
    should hold at least one element."""
    diagnostics: List[Diagnostic] = []
    for typeName, (lengthLine, lengthValue) in facts.arrayLengthDeclarations.items():
        if lengthValue != 0:
            continue
        diagnostics.append(Diagnostic(
            tier=Tier.T3_REFINEMENT,
            code="SS3404",
            kind="layoutDiscipline.arrayLengthZero",
            severity=Severity.WARNING,
            subjectName=typeName,
            subjectKind="arrayType",
            gapEdge="nonZeroLength",
            intentSlogan="fixed array declared with length zero",
            primary=span_of_line(lengthLine, "arrayLengthDeclaration"),
            invariantRule="arrayLength should be > 0 (use sliceType / listType for variable-length sequences)",
            specAnchor="SYNTAX.md#arrayLength",
            fixCandidates=[
                FixCandidate(
                    name="setNonZeroLength",
                    shape=f"arrayLength {typeName} <positiveCount>",
                ),
                FixCandidate(
                    name="useSliceTypeInstead",
                    shape=f"# replace `arrayType {typeName} ...` with `sliceType {typeName} <elementType>`",
                ),
            ],
            confidence=Confidence.HIGH,
            effort=Effort.TRIVIAL,
            passProvenance="check_array_length_zero",
            agentHint="zero-length arrays are a C-ism that SemanticScript's sliceType handles cleanly",
        ))
    return diagnostics


def check_inline_capacity_without_spill_allocator(facts: ExtendedFacts) -> List[Diagnostic]:
    """`smallListInlineCapacity NAME N` without a matching
    `smallListSpillAllocator NAME ALLOC` means appending past N has no
    declared fallback path."""
    diagnostics: List[Diagnostic] = []
    for typeName, (capacityLine, _capacityValue) in facts.smallListInlineCapacities.items():
        if typeName in facts.smallListSpillAllocators:
            continue
        diagnostics.append(Diagnostic(
            tier=Tier.T3_REFINEMENT,
            code="SS3405",
            kind="layoutDiscipline.inlineCapacityWithoutSpillAllocator",
            severity=Severity.WARNING,
            subjectName=typeName,
            subjectKind="smallListType",
            gapEdge="smallListSpillAllocator",
            intentSlogan="inline capacity declared without spill path",
            primary=span_of_line(capacityLine, "smallListInlineCapacityDeclaration"),
            invariantRule=(
                f"`smallListInlineCapacity {typeName} N` requires "
                f"`smallListSpillAllocator {typeName} <allocator>` for the "
                f"overflow path"
            ),
            specAnchor="SYNTAX.md#smallListSpillAllocator",
            fixCandidates=[
                FixCandidate(
                    name="addSpillAllocator",
                    shape=f"smallListSpillAllocator {typeName} <allocatorName>",
                ),
            ],
            confidence=Confidence.HIGH,
            effort=Effort.TRIVIAL,
            passProvenance="check_inline_capacity_without_spill_allocator",
            agentHint="even a no-op `failOnSpillAllocator` makes the overflow policy explicit",
        ))
    return diagnostics


def check_literal_encoding_missing(facts: ExtendedFacts) -> List[Diagnostic]:
    """`literal NAME TYPE` with `literalSource NAME PATH` should have its
    TYPE declared via `typeLiteralEncoding TYPE ENCODING` so the byte
    interpretation is explicit."""
    diagnostics: List[Diagnostic] = []
    for literalName, literalFact in facts.literals.items():
        if not literalFact.hasExternalSource:
            continue
        if literalFact.typeName in facts.typesWithLiteralEncoding:
            continue
        # Primitive SemanticScript types don't need typeLiteralEncoding rows — they're
        # already encoded by their representation.
        if literalFact.typeName in PRIMITIVE_TYPE_STACK_BYTES:
            continue
        diagnostics.append(Diagnostic(
            tier=Tier.T3_REFINEMENT,
            code="SS3406",
            kind="layoutDiscipline.literalEncodingMissing",
            severity=Severity.WARNING,
            subjectName=literalName,
            subjectKind="literal",
            gapEdge="typeLiteralEncoding",
            intentSlogan="external literal type lacks encoding declaration",
            primary=span_of_line(literalFact.line, "literalDeclaration"),
            invariantRule=(
                f"literal `{literalName}` loads bytes from disk but its type "
                f"`{literalFact.typeName}` has no `typeLiteralEncoding` row"
            ),
            specAnchor="SYNTAX.md#typeLiteralEncoding",
            fixCandidates=[
                FixCandidate(
                    name="declareTypeLiteralEncoding",
                    shape=f"typeLiteralEncoding {literalFact.typeName} <encodingName>",
                ),
            ],
            confidence=Confidence.MEDIUM,
            effort=Effort.TRIVIAL,
            passProvenance="check_literal_encoding_missing",
            agentHint="common encodings: utf8, ascii, rawBytes, base64",
        ))
    return diagnostics


# ==========================================================================
# Concurrency / resource / type-system / codec discipline (SS35xx async,
# SS37xx type system, SS38xx codec, SS39xx resource handles)
# ==========================================================================

def check_unawaited_task_group(facts: ExtendedFacts) -> List[Diagnostic]:
    """`startInGroup CALL GROUP` without a matching `awaitGroup GROUP` in
    the same op leaves async work unjoined. Even under the synchronous-
    lowering fallback the contract is wrong on a future multi-thread
    scheduler — flag now so the call site is rewriteable."""
    diagnostics: List[Diagnostic] = []
    for operation in facts.base.operations.values():
        operationCitations = narrative_citations_for_operation(facts, operation.name)
        startInGroupSites = facts.operationStartInGroup.get(operation.name, [])
        awaitedGroupNames = facts.operationAwaitedGroups.get(operation.name, set())
        flaggedGroupNames: Set[str] = set()
        for startLine, groupName in startInGroupSites:
            if groupName in awaitedGroupNames:
                continue
            if groupName in flaggedGroupNames:
                continue
            flaggedGroupNames.add(groupName)
            diagnostics.append(Diagnostic(
                tier=Tier.T3_REFINEMENT,
                code="SS3501",
                kind="concurrencyDiscipline.unawaitedTaskGroup",
                severity=Severity.WARNING,
                subjectName=groupName,
                subjectKind="taskGroup",
                gapEdge="awaitGroup",
                intentSlogan="startInGroup without matching awaitGroup",
                primary=span_of_line(startLine, "startInGroupSite"),
                related=[span_of_line(operation.line, "enclosingOperation")],
                invariantRule=(
                    f"every `startInGroup` must be paired with an `awaitGroup "
                    f"{groupName}` in the same operation"
                ),
                specAnchor="SYNTAX.md#awaitGroup",
                citations=operationCitations,
                fixCandidates=[
                    FixCandidate(
                        name="addAwaitGroup",
                        shape=f"awaitGroup {groupName}",
                        evidence=[span_of_line(startLine)],
                    ),
                ],
                confidence=Confidence.HIGH,
                effort=Effort.TRIVIAL,
                passProvenance="check_unawaited_task_group",
                agentHint=(
                    "single-thread lowering treats awaitGroup as a no-op today; "
                    "declaring it now bakes the contract in before the scheduler lands"
                ),
            ))
    return diagnostics


def check_lock_without_cleanup(facts: ExtendedFacts) -> List[Diagnostic]:
    """`lock MUTEX` without either a matching `unlock MUTEX` OR a
    `defer NAME unlock MUTEX` in the same op risks holding the lock
    across exit paths."""
    diagnostics: List[Diagnostic] = []
    for operation in facts.base.operations.values():
        operationCitations = narrative_citations_for_operation(facts, operation.name)
        lockSites = facts.operationLockSites.get(operation.name, [])
        unlockedMutexes = facts.operationUnlockedMutexes.get(operation.name, set())
        deferUnlockedMutexes = facts.operationDeferUnlockedMutexes.get(operation.name, set())
        flaggedMutexes: Set[str] = set()
        for lockLine, mutexName in lockSites:
            if mutexName in unlockedMutexes or mutexName in deferUnlockedMutexes:
                continue
            if mutexName in flaggedMutexes:
                continue
            flaggedMutexes.add(mutexName)
            diagnostics.append(Diagnostic(
                tier=Tier.T3_REFINEMENT,
                code="SS3503",
                kind="concurrencyDiscipline.lockWithoutCleanup",
                severity=Severity.WARNING,
                subjectName=mutexName,
                subjectKind="mutex",
                gapEdge="unlockOrDeferUnlock",
                intentSlogan="lock without paired unlock or defer-unlock",
                primary=span_of_line(lockLine, "lockSite"),
                related=[span_of_line(operation.line, "enclosingOperation")],
                invariantRule=(
                    f"every `lock {mutexName}` must be paired with `unlock "
                    f"{mutexName}` or `defer NAME unlock {mutexName}` "
                    f"for exit-path safety"
                ),
                specAnchor="SYNTAX.md#unlock",
                citations=operationCitations,
                fixCandidates=[
                    FixCandidate(
                        # Prefer defer-unlock — covers every exit path including
                        # error returns. Same pattern as SS3303 allocate/free.
                        name="addDeferUnlock",
                        shape=f"defer release{mutexName[:1].upper()}{mutexName[1:]} unlock {mutexName}",
                        evidence=[span_of_line(lockLine)],
                    ),
                    FixCandidate(
                        name="addExplicitUnlock",
                        shape=f"unlock {mutexName}",
                    ),
                ],
                confidence=Confidence.HIGH,
                effort=Effort.LOCAL,
                passProvenance="check_lock_without_cleanup",
                agentHint=(
                    "defer-unlock guarantees release on every exit path; "
                    "explicit unlock only covers the fall-through"
                ),
            ))
    return diagnostics


def check_unawaited_submit_work(facts: ExtendedFacts) -> List[Diagnostic]:
    """`submitWork WORK POOL` without a matching `awaitWork WORK` in the
    same op leaves the result unjoined."""
    diagnostics: List[Diagnostic] = []
    for operation in facts.base.operations.values():
        operationCitations = narrative_citations_for_operation(facts, operation.name)
        submittedWork = facts.operationSubmittedWork.get(operation.name, [])
        awaitedWork = facts.operationAwaitedWork.get(operation.name, set())
        flaggedWork: Set[str] = set()
        for submitLine, workName in submittedWork:
            if workName in awaitedWork:
                continue
            if workName in flaggedWork:
                continue
            flaggedWork.add(workName)
            diagnostics.append(Diagnostic(
                tier=Tier.T3_REFINEMENT,
                code="SS3506",
                kind="concurrencyDiscipline.unawaitedSubmitWork",
                severity=Severity.WARNING,
                subjectName=workName,
                subjectKind="work",
                gapEdge="awaitWork",
                intentSlogan="submitWork without matching awaitWork",
                primary=span_of_line(submitLine, "submitWorkSite"),
                related=[span_of_line(operation.line, "enclosingOperation")],
                invariantRule=(
                    f"every `submitWork {workName}` must be paired with "
                    f"`awaitWork {workName}` in the same operation"
                ),
                specAnchor="SYNTAX.md#awaitWork",
                citations=operationCitations,
                fixCandidates=[
                    FixCandidate(
                        name="addAwaitWork",
                        shape=f"awaitWork {workName}",
                        evidence=[span_of_line(submitLine)],
                    ),
                ],
                confidence=Confidence.HIGH,
                effort=Effort.TRIVIAL,
                passProvenance="check_unawaited_submit_work",
                agentHint=(
                    "without awaitWork the result is never collected; "
                    "single-thread lowering loses it silently"
                ),
            ))
    return diagnostics


def check_select_without_cases(facts: ExtendedFacts) -> List[Diagnostic]:
    """`select NAME` declared but no `selectCase NAME …` rows attached.
    A zero-case select is a deadlock guarantee."""
    diagnostics: List[Diagnostic] = []
    for selectName, selectLine in facts.selectDeclarations.items():
        if facts.selectCasesBySelectName.get(selectName):
            continue
        diagnostics.append(Diagnostic(
            tier=Tier.T3_REFINEMENT,
            code="SS3507",
            kind="concurrencyDiscipline.selectWithoutCases",
            severity=Severity.WARNING,
            subjectName=selectName,
            subjectKind="select",
            gapEdge="selectCase",
            intentSlogan="select declared with zero cases",
            primary=span_of_line(selectLine, "selectDeclaration"),
            invariantRule=(
                f"`select {selectName}` requires at least one `selectCase "
                f"{selectName} <token> <branch>` row; zero-case select "
                f"deadlocks at runtime"
            ),
            specAnchor="SYNTAX.md#selectCase",
            fixCandidates=[
                FixCandidate(
                    name="addAtLeastOneSelectCase",
                    shape=f"selectCase {selectName} <readyToken> <branchLabel>",
                ),
                FixCandidate(
                    name="removeUnusedSelect",
                    shape=f"# remove `select {selectName}` if no race is needed",
                ),
            ],
            confidence=Confidence.HIGH,
            effort=Effort.LOCAL,
            passProvenance="check_select_without_cases",
            agentHint="under multi-thread lowering a zero-case select blocks forever",
        ))
    return diagnostics


def check_select_case_references_unknown_select(facts: ExtendedFacts) -> List[Diagnostic]:
    """`selectCase NAME …` referencing a NAME that has no `select NAME`
    declaration. Typo catch."""
    diagnostics: List[Diagnostic] = []
    for selectName, caseLines in facts.selectCasesBySelectName.items():
        if selectName in facts.selectDeclarations:
            continue
        # Suggest the closest declared select name if any exist
        declaredSelectNames = sorted(facts.selectDeclarations.keys())
        for caseLine in caseLines:
            diagnostics.append(Diagnostic(
                tier=Tier.T3_REFINEMENT,
                code="SS3508",
                kind="concurrencyDiscipline.selectCaseReferencesUnknownSelect",
                severity=Severity.WARNING,
                subjectName=selectName,
                subjectKind="selectReference",
                gapEdge="selectDeclaration",
                intentSlogan="selectCase references undeclared select",
                primary=span_of_line(caseLine, "selectCaseSite"),
                invariantRule=(
                    f"`selectCase {selectName} …` must reference a declared "
                    f"`select {selectName}` row"
                ),
                specAnchor="SYNTAX.md#select",
                fixCandidates=[
                    FixCandidate(
                        # Bundle the select + at least one case so applying
                        # this fix doesn't subsequently trip SS3507.
                        name="declareSelectWithCase",
                        shape=(
                            f"select {selectName}\n"
                            f"# (existing) selectCase {selectName} …"
                        ),
                    ),
                    FixCandidate(
                        name="correctSelectNameSpelling",
                        shape=(
                            f"# selectCase ... <oneOf: "
                            f"{', '.join(declaredSelectNames) if declaredSelectNames else '(no selects declared)'}>"
                        ),
                    ),
                ],
                confidence=Confidence.HIGH,
                effort=Effort.TRIVIAL,
                passProvenance="check_select_case_references_unknown_select",
                agentHint=(
                    "declaring the select alone trips SS3507 next; the bundled "
                    "fix preserves at least one case"
                ),
            ))
    return diagnostics


def check_async_call_missing_boundary(facts: ExtendedFacts) -> List[Diagnostic]:
    """An awaited call should declare BOTH a `timeout CALL DURATION` and
    a `cancelOn CALL TOKEN` — without them the await is unbounded and
    uncancellable. Consolidates semlint.py's unboundedAsyncCall +
    uncancellableAsyncCall into one diagnostic listing all missing edges."""
    diagnostics: List[Diagnostic] = []
    for operation in facts.base.operations.values():
        operationCitations = narrative_citations_for_operation(facts, operation.name)
        operationCalls = collect_operation_calls(operation)
        for callFact in operationCalls.values():
            if not callFact.await_lines:
                continue
            missingBoundaryEdges: List[str] = []
            if not callFact.timeout_lines:
                missingBoundaryEdges.append("timeout")
            if not callFact.cancel_lines:
                missingBoundaryEdges.append("cancelOn")
            if not missingBoundaryEdges:
                continue
            diagnostics.append(Diagnostic(
                tier=Tier.T3_REFINEMENT,
                code="SS3510",
                kind="concurrencyDiscipline.asyncCallMissingBoundary",
                severity=Severity.WARNING,
                subjectName=callFact.name,
                subjectKind="call",
                gapEdge=",".join(missingBoundaryEdges),
                intentSlogan="awaited call lacks timeout/cancelOn boundary",
                primary=span_of_line(callFact.await_lines[0], "awaitSite"),
                related=[
                    span_of_line(callFact.line, "callDeclaration"),
                    span_of_line(operation.line, "enclosingOperation"),
                ],
                invariantRule=(
                    f"every awaited call must declare both `timeout` and "
                    f"`cancelOn` to bound the wait and allow cancellation"
                ),
                specAnchor="SYNTAX.md#timeout",
                citations=operationCitations,
                fixCandidates=[
                    FixCandidate(
                        name=f"add{edgeName[0].upper()}{edgeName[1:]}",
                        shape=(
                            f"timeout {callFact.name} <durationConst>"
                            if edgeName == "timeout"
                            else f"cancelOn {callFact.name} <cancellationToken>"
                        ),
                        evidence=[span_of_line(callFact.line)],
                    )
                    for edgeName in missingBoundaryEdges
                ],
                confidence=Confidence.HIGH,
                effort=Effort.LOCAL,
                passProvenance="check_async_call_missing_boundary",
                agentHint=(
                    "single-thread lowering completes synchronously so the "
                    "boundary is trivially satisfied today, but declaring it "
                    "now is the contract for the future scheduler"
                ),
            ))
    return diagnostics


def check_file_handle_not_closed(facts: ExtendedFacts) -> List[Diagnostic]:
    """`c.fopen` / `c.open` body call without a matching `c.fclose` /
    `c.close` defer in the same op. Same shape as SS3303 but for file
    handles."""
    diagnostics: List[Diagnostic] = []
    fileOpenTargets: Set[str] = {"c.fopen", "c.open"}
    fileCloseTargets: Set[str] = {"c.fclose", "c.close"}
    for operation in facts.base.operations.values():
        operationCitations = narrative_citations_for_operation(facts, operation.name)
        operationCalls = collect_operation_calls(operation)
        operationDefers = facts.operationDefers.get(operation.name, [])
        hasCloseDefer = any(
            deferTarget in fileCloseTargets
            for _deferLine, deferTarget in operationDefers
        )
        if hasCloseDefer:
            continue
        for callFact in operationCalls.values():
            callTarget = callFact.target
            if callTarget not in fileOpenTargets:
                continue
            if call_has_later_cleanup_call(callFact, operationCalls, fileCloseTargets):
                continue
            # Suppress when the op's output type IS CFileHandle — caller owns lifetime
            outputLine = None
            for opLine in operation.lines:
                if opLine.verb == "output" and opLine.args and opLine.args[0] == operation.name:
                    outputLine = opLine
                    break
            if outputLine and len(outputLine.args) >= 2:
                if outputLine.args[1] == "CFileHandle":
                    continue
                if outputLine.args[1] == "Result" and len(outputLine.args) >= 3 and outputLine.args[2] == "CFileHandle":
                    continue
            closeTargetSuggestion = "c.fclose" if callTarget == "c.fopen" else "c.close"
            diagnostics.append(Diagnostic(
                tier=Tier.T3_REFINEMENT,
                code="SS3901",
                kind="resourceLifecycle.fileHandleNotClosed",
                severity=Severity.WARNING,
                subjectName=callFact.name,
                subjectKind="call",
                gapEdge="defer",
                intentSlogan="file handle opened without paired close defer",
                primary=span_of_line(callFact.line, "openCall"),
                related=[span_of_line(operation.line, "enclosingOperation")],
                invariantRule=(
                    f"every `{callTarget}` should be paired with a "
                    f"`defer NAME {closeTargetSuggestion} <handle>` or explicit "
                    f"`{closeTargetSuggestion}` cleanup in the same operation"
                ),
                specAnchor="SYNTAX.md#defer",
                citations=operationCitations,
                fixCandidates=[
                    FixCandidate(
                        name="addCloseDefer",
                        shape=(
                            f"defer release{callFact.name[:1].upper()}{callFact.name[1:]} "
                            f"{closeTargetSuggestion} <openedHandle>"
                        ),
                        evidence=[span_of_line(callFact.line)],
                    ),
                ],
                confidence=Confidence.HIGH,
                effort=Effort.LOCAL,
                passProvenance="check_file_handle_not_closed",
                agentHint=(
                    "if the op returns the handle to the caller, declare output "
                    "type `CFileHandle` to suppress this check"
                ),
            ))
    return diagnostics


def check_guard_token_source_without_release(facts: ExtendedFacts) -> List[Diagnostic]:
    """`guardTokenSource TOKEN CALL` declares an acquisition site; every
    such token must also have a matching `guardTokenRelease TOKEN OP` row."""
    diagnostics: List[Diagnostic] = []
    for tokenName, sourceLine in facts.guardTokenSourceDeclarations.items():
        if tokenName in facts.guardTokenReleaseDeclarations:
            continue
        diagnostics.append(Diagnostic(
            tier=Tier.T3_REFINEMENT,
            code="SS3903",
            kind="resourceLifecycle.guardTokenSourceWithoutRelease",
            severity=Severity.WARNING,
            subjectName=tokenName,
            subjectKind="guardToken",
            gapEdge="guardTokenRelease",
            intentSlogan="guardTokenSource without paired release",
            primary=span_of_line(sourceLine, "guardTokenSourceSite"),
            invariantRule=(
                f"every `guardTokenSource {tokenName} …` requires a matching "
                f"`guardTokenRelease {tokenName} <releaseOp>` so callers know "
                f"the release path"
            ),
            specAnchor="SYNTAX.md#guardTokenRelease",
            fixCandidates=[
                FixCandidate(
                    name="declareGuardTokenRelease",
                    shape=f"guardTokenRelease {tokenName} <releaseOperation>",
                ),
            ],
            confidence=Confidence.HIGH,
            effort=Effort.TRIVIAL,
            passProvenance="check_guard_token_source_without_release",
            agentHint="release op should match the lifetime of the protected resource",
        ))
    return diagnostics


def check_guard_token_protects_shared_state_access(facts: ExtendedFacts) -> List[Diagnostic]:
    """A `protectedBy TOKEN` access should have a matching
    `guardTokenProtects TOKEN RESOURCE` edge. The current compiler does not
    enforce tokens at runtime, so the metadata graph must be explicit."""
    diagnostics: List[Diagnostic] = []
    for accessFact in facts.sharedStateAccesses:
        tokenName = accessFact.protectedByToken
        if not tokenName:
            continue
        protectedResources = facts.guardTokenProtectsDeclarations.get(tokenName, set())
        if accessFact.slotName in protectedResources:
            continue
        diagnostics.append(Diagnostic(
            tier=Tier.T3_REFINEMENT,
            code="SS3904",
            kind="resourceLifecycle.guardTokenDoesNotProtectSharedState",
            severity=Severity.WARNING,
            subjectName=tokenName,
            subjectKind="guardToken",
            gapEdge="guardTokenProtects",
            intentSlogan="protectedBy token lacks matching guardTokenProtects edge",
            primary=span_of_line(accessFact.line, "sharedStateAccess"),
            invariantRule=(
                f"`protectedBy {tokenName}` on sharedState `{accessFact.slotName}` "
                f"requires `guardTokenProtects {tokenName} {accessFact.slotName}`"
            ),
            specAnchor="SYNTAX.md#guardTokenProtects",
            fixCandidates=[
                FixCandidate(
                    name="declareGuardTokenProtectsResource",
                    shape=f"guardTokenProtects {tokenName} {accessFact.slotName}",
                    evidence=[span_of_line(accessFact.line)],
                ),
            ],
            confidence=Confidence.HIGH,
            effort=Effort.TRIVIAL,
            passProvenance="check_guard_token_protects_shared_state_access",
            agentHint=(
                "guard tokens are metadata in the 1.0 runtime; the linter can "
                "only verify the declared protection graph"
            ),
        ))
    return diagnostics


def check_circular_type_alias(facts: ExtendedFacts) -> List[Diagnostic]:
    """`type A B; type B A` (directly or transitively) is a cycle that
    can't be resolved at compile time."""
    diagnostics: List[Diagnostic] = []
    typeAliases = facts.base.type_aliases
    flaggedCycleAnchors: Set[str] = set()
    for startTypeName in typeAliases:
        if startTypeName in flaggedCycleAnchors:
            continue
        # Walk the alias chain detecting revisit
        visitedNames: List[str] = [startTypeName]
        currentName = typeAliases[startTypeName]
        while currentName in typeAliases:
            if currentName in visitedNames:
                cycleStartIndex = visitedNames.index(currentName)
                cycleChain = visitedNames[cycleStartIndex:] + [currentName]
                # Find the SourceLine for the start of the cycle
                # (the linter's base only retains the alias dict, no per-line
                # for `type` rows — we report it on the program lines that
                # declared the cycle starter for now).
                cycleStarterName = cycleChain[0]
                cycleStarterLine: Optional[SourceLine] = None
                for sourceLine in facts.base.lines:
                    if (sourceLine.tokens and not is_comment(sourceLine)
                            and sourceLine.verb == "type"
                            and sourceLine.args
                            and sourceLine.args[0] == cycleStarterName):
                        cycleStarterLine = sourceLine
                        break
                if cycleStarterLine is None:
                    break
                flaggedCycleAnchors.update(cycleChain)
                diagnostics.append(Diagnostic(
                    tier=Tier.T3_REFINEMENT,
                    code="SS3701",
                    kind="typeSystem.circularAlias",
                    severity=Severity.WARNING,
                    subjectName=" → ".join(cycleChain),
                    subjectKind="typeAlias",
                    gapEdge="terminatingType",
                    intentSlogan="type alias chain contains a cycle",
                    primary=span_of_line(cycleStarterLine, "cycleStarter"),
                    invariantRule="type alias chains must terminate in a base type, not loop",
                    specAnchor="SYNTAX.md#type",
                    fixCandidates=[
                        FixCandidate(
                            name="breakCycleAtConcreteBase",
                            shape=f"# rewrite one of {{{', '.join(cycleChain)}}} to terminate at a concrete base type",
                        ),
                    ],
                    confidence=Confidence.HIGH,
                    effort=Effort.LOCAL,
                    passProvenance="check_circular_type_alias",
                    agentHint="the cycle root is usually a recent rename — check git log on the type rows",
                ))
                break
            visitedNames.append(currentName)
            currentName = typeAliases[currentName]
    return diagnostics


def check_json_codec_incomplete(facts: ExtendedFacts) -> List[Diagnostic]:
    """`jsonCodec NAME` requires `jsonCodecInput`, `jsonCodecOutput`,
    `jsonCodecDecodeTarget`, and `jsonCodecEncodeTarget` for the codec
    to be wireable end-to-end. Emit one diagnostic per codec listing
    every missing edge."""
    diagnostics: List[Diagnostic] = []
    for codecName, codecLine in facts.jsonCodecDeclarations.items():
        missingEdges: List[str] = []
        if codecName not in facts.jsonCodecHasInput:
            missingEdges.append("jsonCodecInput")
        if codecName not in facts.jsonCodecHasOutput:
            missingEdges.append("jsonCodecOutput")
        if codecName not in facts.jsonCodecHasDecodeTarget:
            missingEdges.append("jsonCodecDecodeTarget")
        if codecName not in facts.jsonCodecHasEncodeTarget:
            missingEdges.append("jsonCodecEncodeTarget")
        if not missingEdges:
            continue
        diagnostics.append(Diagnostic(
            tier=Tier.T3_REFINEMENT,
            code="SS3801",
            kind="codec.jsonCodecIncomplete",
            severity=Severity.WARNING,
            subjectName=codecName,
            subjectKind="jsonCodec",
            gapEdge=",".join(missingEdges),
            intentSlogan="jsonCodec missing required edges",
            primary=span_of_line(codecLine, "jsonCodecDeclaration"),
            invariantRule=(
                "every jsonCodec must declare input, output, decodeTarget, "
                "and encodeTarget for the codec to be wireable"
            ),
            specAnchor="SYNTAX.md#jsonCodec",
            fixCandidates=[
                FixCandidate(
                    name=f"add{edgeName[0].upper()}{edgeName[1:]}",
                    shape=f"{edgeName} {codecName} <value>",
                )
                for edgeName in missingEdges
            ],
            confidence=Confidence.HIGH,
            effort=Effort.LOCAL,
            passProvenance="check_json_codec_incomplete",
            agentHint=(
                "an incomplete codec compiles to a zero-stub at codegen — "
                "callers will see runtime zeros where decoded values should be"
            ),
        ))
    return diagnostics


# ==========================================================================
# Foundational basics — argument arity, unresolved references, duplicates
# These all produce T0/T1 errors that should block compilation; they sit
# upstream of every refinement-level check.
# ==========================================================================

def _is_generated_json_codec_target(targetName: str) -> bool:
    return targetName.startswith("json.encode.") or targetName.startswith("json.decode.")


def _collection_type_name_from_target(targetName: str) -> Optional[str]:
    if "." not in targetName:
        return None
    typeName, methodName = targetName.split(".", 1)
    if methodName not in COLLECTION_RUNTIME_METHODS:
        return None
    if typeName.endswith(COLLECTION_TYPE_SUFFIXES):
        return typeName
    return None


def check_runtime_backing_missing(facts: ExtendedFacts) -> List[Diagnostic]:
    """Flag calls whose current compiler path is the zero-value external
    fallback, not a real codec or collection runtime."""
    diagnostics: List[Diagnostic] = []
    for operation in facts.base.operations.values():
        operationCitations = narrative_citations_for_operation(facts, operation.name)
        for callFact in collect_operation_calls(operation).values():
            targetName = callFact.target
            if targetName in SUPPORTED_JSON_PRIMITIVE_TARGETS:
                continue

            if _is_generated_json_codec_target(targetName):
                related: List[Span] = [span_of_line(operation.line, "enclosingOperation")]
                codecTargetLine = facts.jsonCodecGeneratedTargets.get(targetName)
                if codecTargetLine:
                    related.append(span_of_line(codecTargetLine, "jsonCodecTargetDeclaration"))
                diagnostics.append(Diagnostic(
                    tier=Tier.T3_REFINEMENT,
                    code="SS3802",
                    kind="codec.generatedJsonRuntimeMissing",
                    severity=Severity.WARNING,
                    subjectName=targetName,
                    subjectKind="callTarget",
                    gapEdge="runtimeBinding",
                    intentSlogan="generated JSON runtime missing",
                    primary=span_of_line(callFact.line, "callTarget"),
                    related=related,
                    invariantRule=(
                        f"`{targetName}` is not one of the primitive JSON targets "
                        "with direct compiler lowering; current codegen returns a "
                        "zero stub unless a real runtime binding or user operation exists"
                    ),
                    specAnchor="docs/language/records-codecs-boundaries.md#json-codecs",
                    citations=operationCitations,
                    fixCandidates=[
                        FixCandidate(
                            name="provideRuntimeBinding",
                            shape=f"runtimeBinding {targetName} <nativeOrSemanticScriptImplementation>",
                        ),
                        FixCandidate(
                            name="replaceWithPrimitiveCodec",
                            shape="# use json.encode.I64/json.decode.I64/json.encode.Bool/etc. when the value is scalar",
                        ),
                    ],
                    confidence=Confidence.HIGH,
                    effort=Effort.CROSS_FILE,
                    passProvenance="check_runtime_backing_missing",
                    agentHint="do not treat record-level generated JSON codecs as executable until a backing runtime is wired",
                ))
                continue

            if "." in targetName:
                targetPrefix = targetName.split(".", 1)[0]
                codecLine = facts.codecDeclarations.get(targetPrefix)
                if codecLine:
                    diagnostics.append(Diagnostic(
                        tier=Tier.T3_REFINEMENT,
                        code="SS3803",
                        kind="codec.genericRuntimeMissing",
                        severity=Severity.WARNING,
                        subjectName=targetName,
                        subjectKind="callTarget",
                        gapEdge="runtimeBinding",
                        intentSlogan="generic codec runtime missing",
                        primary=span_of_line(callFact.line, "callTarget"),
                        related=[
                            span_of_line(operation.line, "enclosingOperation"),
                            span_of_line(codecLine, "codecDeclaration"),
                        ],
                        invariantRule=(
                            f"`{targetName}` references generic codec `{targetPrefix}`, "
                            "but generic codecs are contract metadata until a backend "
                            "operation or runtime binding is provided"
                        ),
                        specAnchor="docs/language/records-codecs-boundaries.md#generic-codecs",
                        citations=operationCitations,
                        fixCandidates=[
                            FixCandidate(
                                name="provideCodecRuntimeBinding",
                                shape=f"runtimeBinding {targetName} <codecBackendImplementation>",
                            ),
                            FixCandidate(
                                name="replaceWithUserOperation",
                                shape=f"operation <descriptive{targetPrefix[0].upper()}{targetPrefix[1:]}Operation>",
                            ),
                        ],
                        confidence=Confidence.HIGH,
                        effort=Effort.CROSS_FILE,
                        passProvenance="check_runtime_backing_missing",
                        agentHint="generic codec declarations do not create encode/decode functions by themselves",
                    ))
                    continue

            collectionTypeName = _collection_type_name_from_target(targetName)
            collectionLine = (
                facts.collectionOperationDeclarations.get(targetName)
                or (
                    facts.collectionTypeDeclarations.get(collectionTypeName)
                    if collectionTypeName else None
                )
            )
            if collectionTypeName:
                related = [span_of_line(operation.line, "enclosingOperation")]
                if collectionLine:
                    related.append(span_of_line(collectionLine, "collectionDeclaration"))
                diagnostics.append(Diagnostic(
                    tier=Tier.T3_REFINEMENT,
                    code="SS3804",
                    kind="collection.runtimeMissing",
                    severity=Severity.WARNING,
                    subjectName=targetName,
                    subjectKind="callTarget",
                    gapEdge="runtimeBinding",
                    intentSlogan="collection runtime missing",
                    primary=span_of_line(callFact.line, "callTarget"),
                    related=related,
                    invariantRule=(
                        f"`{targetName}` is a typed collection operation, but "
                        "collectionOperation/listType/mapType metadata does not "
                        "create executable storage behavior yet"
                    ),
                    specAnchor="docs/reference/verb-index.md#collections",
                    citations=operationCitations,
                    fixCandidates=[
                        FixCandidate(
                            name="provideCollectionRuntimeBinding",
                            shape=f"runtimeBinding {targetName} <collectionBackendImplementation>",
                        ),
                        FixCandidate(
                            name="replaceWithExplicitOperation",
                            shape="# implement the append/get behavior as a named operation and call it directly",
                        ),
                    ],
                    confidence=Confidence.HIGH,
                    effort=Effort.CROSS_FILE,
                    passProvenance="check_runtime_backing_missing",
                    agentHint="TaskList.append and TaskMap.get currently compile through the zero-stub fallback",
                ))
    return diagnostics


def check_argument_arity(facts: ExtendedFacts) -> List[Diagnostic]:
    """Verb appears with fewer arguments than its declared minimum arity.
    Lines below the threshold can't be interpreted by any downstream pass
    — T0 grammar error, blocks compile."""
    diagnostics: List[Diagnostic] = []
    for sourceLine in facts.base.lines:
        if not sourceLine.tokens or is_comment(sourceLine):
            continue
        verb = sourceLine.verb
        requiredArity = VERB_MINIMUM_ARITY.get(verb)
        if requiredArity is None:
            continue
        actualArity = len(sourceLine.args)
        if actualArity >= requiredArity:
            continue
        diagnostics.append(Diagnostic(
            tier=Tier.T0_PARSE,
            code="SS0002",
            kind="grammar.argumentArityTooFew",
            severity=Severity.ERROR,
            subjectName=verb,
            subjectKind="verb",
            gapEdge="argumentCount",
            intentSlogan=f"`{verb}` needs {requiredArity}+ args, got {actualArity}",
            primary=span_of_line(sourceLine, "arityViolationSite"),
            invariantRule=(
                f"verb `{verb}` requires at least {requiredArity} argument(s); "
                f"row supplied {actualArity}"
            ),
            specAnchor=f"SYNTAX.md#{verb}",
            fixCandidates=[
                FixCandidate(
                    name="supplyMissingArguments",
                    shape=f"{verb} <arg1> <arg2> … (need {requiredArity - actualArity} more)",
                ),
            ],
            confidence=Confidence.HIGH,
            blocksCompile=True,
            effort=Effort.TRIVIAL,
            passProvenance="check_argument_arity",
            agentHint=(
                f"check SYNTAX.md row for `{verb}` to see the exact argument shape"
            ),
        ))
    return diagnostics


def check_unresolved_references(facts: ExtendedFacts) -> List[Diagnostic]:
    """Reference verbs (`arg`, `branch`, `useCapability`, etc.) that point
    at names that were never declared. Surfaces typos and copy-paste
    leftovers. T1 spec — should block compile (downstream lowering can't
    resolve the reference)."""
    diagnostics: List[Diagnostic] = []
    importIndex = build_import_contract_index(facts)
    importedCapabilityNames = {
        name for name, symbol in importIndex.qualifiedSymbols.items()
        if symbol.kind == "capability"
    } | {
        name for name, symbol in importIndex.singularSymbols.items()
        if symbol.kind == "capability"
    }
    importedConstantNames = {
        name for name, symbol in importIndex.qualifiedSymbols.items()
        if symbol.kind == "constant"
    } | {
        name for name, symbol in importIndex.singularSymbols.items()
        if symbol.kind == "constant"
    }

    # Build per-op sets of declared call objects + labels.
    operationCallsByOperationName: Dict[str, Set[str]] = {}
    operationCallTargetsByOperationName: Dict[str, Dict[str, str]] = {}
    operationLabelsByOperationName: Dict[str, Set[str]] = {}
    moduleScopeValueNames: Set[str] = (
        set(OPAQUE_DEPENDENCY_INPUT_NAMES) | set(BUILTIN_VALUE_TYPES)
    )
    moduleScopeValueNames.update(facts.base.consts.keys())
    moduleScopeValueNames.update(importedConstantNames)
    currentOperationDuringValueScan: Optional[str] = None
    for sourceLine in facts.base.lines:
        if not sourceLine.tokens or is_comment(sourceLine):
            continue
        verb = sourceLine.verb
        args = sourceLine.args
        if verb == "operation" and args:
            currentOperationDuringValueScan = args[0]
            continue
        if currentOperationDuringValueScan is not None:
            continue
        if verb in {"domainLiteral", "literal", "const"} and args:
            moduleScopeValueNames.add(args[0])
        elif verb == "enumCase" and len(args) >= 2:
            moduleScopeValueNames.add(args[1])
        elif verb in {"storage", "sharedState"} and len(args) >= 5:
            moduleScopeValueNames.add(args[2])

    for operation in facts.base.operations.values():
        operationCalls = collect_operation_calls(operation)
        operationCallsByOperationName[operation.name] = set(
            operationCalls.keys()
        )
        operationCallTargetsByOperationName[operation.name] = {
            callName: callFact.target
            for callName, callFact in operationCalls.items()
        }
        operationLabelsByOperationName[operation.name] = {
            sourceLine.args[0]
            for sourceLine in operation.lines
            if (not is_comment(sourceLine) and sourceLine.tokens
                and sourceLine.verb == "label" and sourceLine.args)
        }

    # Per-op reference checks
    for operation in facts.base.operations.values():
        operationCitations = narrative_citations_for_operation(facts, operation.name)
        declaredCallNames = operationCallsByOperationName.get(operation.name, set())
        callTargetByCallName = operationCallTargetsByOperationName.get(operation.name, {})
        declaredLabelNames = operationLabelsByOperationName.get(operation.name, set())
        declaredValueNames: Set[str] = set(moduleScopeValueNames)
        for declarationLine in operation.lines:
            if not declarationLine.tokens or is_comment(declarationLine):
                continue
            declarationVerb = declarationLine.verb
            declarationArgs = declarationLine.args
            if (declarationVerb == "input" and len(declarationArgs) >= 3
                    and declarationArgs[0] == operation.name):
                declaredValueNames.add(declarationArgs[1])
            elif declarationVerb in {"const", "var", "literal"} and declarationArgs:
                declaredValueNames.add(declarationArgs[0])
            elif declarationVerb == "storage" and len(declarationArgs) >= 5:
                declaredValueNames.add(declarationArgs[2])
            elif declarationVerb in {"bind", "bindOk", "bindError"} and declarationArgs:
                declaredValueNames.add(declarationArgs[0])
            elif declarationVerb == "read" and len(declarationArgs) >= 2:
                declaredValueNames.add(declarationArgs[1])
            elif declarationVerb == "receive" and declarationArgs:
                declaredValueNames.add(declarationArgs[0])
            elif declarationVerb == "makeError" and declarationArgs:
                declaredValueNames.add(declarationArgs[0])

        for sourceLine in operation.lines:
            if not sourceLine.tokens or is_comment(sourceLine) or not sourceLine.args:
                continue
            verb = sourceLine.verb

            # Call references
            referencedCallName: Optional[str] = None
            if verb in CALL_REFERENCE_VERBS_AT_ARG_ZERO and sourceLine.args:
                referencedCallName = sourceLine.args[0]
            elif verb in CALL_REFERENCE_VERBS_AT_ARG_TWO and len(sourceLine.args) >= 3:
                referencedCallName = sourceLine.args[2]
            if referencedCallName and referencedCallName not in declaredCallNames:
                diagnostics.append(_unresolved_reference_diagnostic(
                    sourceLine=sourceLine,
                    operation=operation,
                    operationCitations=operationCitations,
                    referencedName=referencedCallName,
                    referencedKind="call",
                    verbThatReferenced=verb,
                    code="SS4101",
                    declarationShape=f"call {referencedCallName} <target>",
                ))

            if verb == "arg" and len(sourceLine.args) >= 3:
                referencedValueName = sourceLine.args[2]
                callReferenceName = sourceLine.args[0]
                argumentName = sourceLine.args[1]
                referencedOperationAsArgument = (
                    callTargetByCallName.get(callReferenceName) == "gui.controlOnEvent"
                    and argumentName == "handler"
                    and referencedValueName in facts.base.operations
                )
                if (referencedValueName not in declaredValueNames
                        and not _is_integer_literal(referencedValueName)
                        and referencedValueName not in {"true", "false"}
                        and not referencedOperationAsArgument):
                    diagnostics.append(_unresolved_reference_diagnostic(
                        sourceLine=sourceLine,
                        operation=operation,
                        operationCitations=operationCitations,
                        referencedName=referencedValueName,
                        referencedKind="value",
                        verbThatReferenced=verb,
                        code="SS4105",
                        declarationShape=f"const {referencedValueName} <type> <value>",
                    ))

            # Label references
            referencedLabelName: Optional[str] = None
            if verb in LABEL_REFERENCE_VERBS_AT_ARG_ZERO and sourceLine.args:
                referencedLabelName = sourceLine.args[0]
            elif verb in LABEL_REFERENCE_VERBS_AT_ARG_ONE and len(sourceLine.args) >= 2:
                referencedLabelName = sourceLine.args[1]
            elif verb == "branchSelected" and len(sourceLine.args) >= 3:
                referencedLabelName = sourceLine.args[2]
            elif verb == "branchIf" and len(sourceLine.args) >= 3:
                # legacy branchIf X trueLabel falseLabel
                if sourceLine.args[2] not in declaredLabelNames:
                    diagnostics.append(_unresolved_reference_diagnostic(
                        sourceLine=sourceLine,
                        operation=operation,
                        operationCitations=operationCitations,
                        referencedName=sourceLine.args[2],
                        referencedKind="label",
                        verbThatReferenced=verb,
                        code="SS4102",
                        declarationShape=f"label {sourceLine.args[2]}",
                    ))
            if referencedLabelName and referencedLabelName not in declaredLabelNames:
                diagnostics.append(_unresolved_reference_diagnostic(
                    sourceLine=sourceLine,
                    operation=operation,
                    operationCitations=operationCitations,
                    referencedName=referencedLabelName,
                    referencedKind="label",
                    verbThatReferenced=verb,
                    code="SS4102",
                    declarationShape=f"label {referencedLabelName}",
                ))

            # useCapability references — args[1] is the capability name
            if verb == "useCapability" and len(sourceLine.args) >= 2:
                referencedCapabilityName = sourceLine.args[1]
                if (referencedCapabilityName not in facts.capabilities
                        and referencedCapabilityName not in importedCapabilityNames):
                    diagnostics.append(_unresolved_reference_diagnostic(
                        sourceLine=sourceLine,
                        operation=operation,
                        operationCitations=operationCitations,
                        referencedName=referencedCapabilityName,
                        referencedKind="capability",
                        verbThatReferenced=verb,
                        code="SS4103",
                        declarationShape=f"capability {referencedCapabilityName} <effectPath> <action>",
                    ))

    # Module-scope: narrative-attachment verbs reference a declared subject
    # at args[0]. The subject may be an operation OR any other declarable
    # top-level kind (webServer, capability, timeoutBudget, type alias,
    # storage slot, enum, error domain, literal, domainLiteral,
    # trustBoundary, retryPolicy, jsonCodec, etc.) — `purpose`,
    # `invariant`, `warning`, and friends are not operation-only verbs.
    #
    # SS4104 fires only when the subject is undeclared anywhere; SS4104b
    # (a new structural counterpart) fires when an operation-only verb
    # (`input`, `output`, `effect`, `memory*`, `async`, `useCapability`,
    # `authority`, `operationBody`) attaches to a subject that exists but
    # isn't an operation.
    validAttachmentSubjects: Set[str] = set()
    validAttachmentSubjects.update(facts.base.operations.keys())
    validAttachmentSubjects.update(facts.base.abstractions.keys())
    validAttachmentSubjects.update(facts.base.capabilities.keys())
    validAttachmentSubjects.update(facts.base.type_aliases.keys())
    validAttachmentSubjects.update(facts.storageSlots.keys())
    validAttachmentSubjects.update(facts.literals.keys())
    validAttachmentSubjects.update(facts.retryPolicies.keys())
    validAttachmentSubjects.update(facts.trustBoundaries.keys())
    validAttachmentSubjects.update(facts.codecDeclarations.keys())
    validAttachmentSubjects.update(facts.jsonCodecDeclarations.keys())
    validAttachmentSubjects.update(facts.collectionTypeDeclarations.keys())
    validAttachmentSubjects.update(facts.collectionOperationDeclarations.keys())
    # Module-scope verbs not already tracked by ExtendedFacts but legal
    # narrative-attachment subjects per SYNTAX.md.
    for sourceLine in facts.base.lines:
        if not sourceLine.tokens or is_comment(sourceLine) or not sourceLine.args:
            continue
        if sourceLine.verb in {
            "enum", "error", "domainLiteral", "policy", "errorPolicy",
            "resource", "validator", "mapper", "adapter", "boundary",
        }:
            validAttachmentSubjects.add(sourceLine.args[0])

    # Operation-only attachment verbs — these MUST resolve to an operation
    # (a webServer or capability cannot legitimately carry `input` or
    # `effect`, even though it can carry `purpose`).
    OPERATION_BODY_ONLY_VERBS = frozenset({
        "input", "output", "effect", "async", "operationBody",
        "memory", "memoryHeap", "memoryArena",
        "memoryAllocationSource", "memoryStackLimit",
        "useCapability", "authority",
    })

    for sourceLine in facts.base.lines:
        if not sourceLine.tokens or is_comment(sourceLine) or not sourceLine.args:
            continue
        if sourceLine.verb not in OPERATION_ATTACHMENT_VERBS:
            continue
        referencedSubjectName = sourceLine.args[0]
        # Subject doesn't exist anywhere — true unresolved-attachment.
        if referencedSubjectName not in validAttachmentSubjects:
            diagnostics.append(Diagnostic(
                tier=Tier.T1_SPEC,
                code="SS4104",
                kind="referenceIntegrity.unresolvedAttachmentSubject",
                severity=Severity.ERROR,
                subjectName=referencedSubjectName,
                subjectKind="declaration",
                gapEdge="subjectDeclaration",
                intentSlogan=f"`{sourceLine.verb}` attaches to undeclared subject",
                primary=span_of_line(sourceLine, "attachmentSite"),
                invariantRule=(
                    f"`{sourceLine.verb} {referencedSubjectName} …` requires a prior "
                    f"declaration of `{referencedSubjectName}` (operation, webServer, "
                    f"capability, type, enum, error, storage, literal, retryPolicy, "
                    f"trustBoundary, jsonCodec, codec, validator, mapper, adapter, "
                    f"boundary, policy, errorPolicy, resource, timeoutBudget, or "
                    f"collection declaration)"
                ),
                specAnchor="SYNTAX.md#operation",
                fixCandidates=[
                    FixCandidate(
                        name="declareSubject",
                        shape=f"# add a declaration line for `{referencedSubjectName}` (operation/webServer/capability/…)",
                    ),
                    FixCandidate(
                        name="correctSubjectName",
                        shape=f"# verify `{referencedSubjectName}` spelling against your declarations",
                    ),
                ],
                confidence=Confidence.HIGH,
                blocksCompile=True,
                effort=Effort.LOCAL,
                passProvenance="check_unresolved_references",
                agentHint="attachment-verb typos are the #1 source of silent narrative drift",
            ))
            continue
        # Subject exists but isn't an operation — only operation-body verbs
        # care about that distinction. `purpose` / `invariant` / `warning`
        # legitimately attach to any subject kind.
        if (sourceLine.verb in OPERATION_BODY_ONLY_VERBS
                and referencedSubjectName not in facts.base.operations):
            diagnostics.append(Diagnostic(
                tier=Tier.T1_SPEC,
                code="SS4105",
                kind="referenceIntegrity.attachmentSubjectKindMismatch",
                severity=Severity.ERROR,
                subjectName=referencedSubjectName,
                subjectKind="operation",
                gapEdge="operationDeclaration",
                intentSlogan=f"`{sourceLine.verb}` requires an operation subject",
                primary=span_of_line(sourceLine, "attachmentSite"),
                invariantRule=(
                    f"`{sourceLine.verb} {referencedSubjectName} …` attaches "
                    f"operation-body metadata (input/output/effect/memory/async/"
                    f"useCapability/authority/operationBody) — those verbs are "
                    f"meaningful only for `operation` subjects, not for the kind "
                    f"of `{referencedSubjectName}` that is actually declared"
                ),
                specAnchor="SYNTAX.md#operation",
                fixCandidates=[
                    FixCandidate(
                        name="renameSubjectToActualOperation",
                        shape=f"# replace `{referencedSubjectName}` with the operation name that owns this {sourceLine.verb} edge",
                    ),
                    FixCandidate(
                        name="removeOperationBodyAttachment",
                        shape=f"# remove `{sourceLine.verb} {referencedSubjectName} …` — this verb is operation-only",
                    ),
                ],
                confidence=Confidence.HIGH,
                blocksCompile=True,
                effort=Effort.TRIVIAL,
                passProvenance="check_unresolved_references",
                agentHint="operation-body verbs like `input`/`effect` are not valid on webServer/capability/storage subjects",
            ))

    return diagnostics


def _unresolved_reference_diagnostic(
    sourceLine: SourceLine,
    operation: OperationFact,
    operationCitations: List[Citation],
    referencedName: str,
    referencedKind: str,
    verbThatReferenced: str,
    code: str,
    declarationShape: str,
) -> Diagnostic:
    return Diagnostic(
        tier=Tier.T1_SPEC,
        code=code,
        kind=f"referenceIntegrity.unresolved{referencedKind.capitalize()}",
        severity=Severity.ERROR,
        subjectName=referencedName,
        subjectKind=referencedKind,
        gapEdge=f"{referencedKind}Declaration",
        intentSlogan=f"`{verbThatReferenced}` references undeclared {referencedKind}",
        primary=span_of_line(sourceLine, "referenceSite"),
        related=[span_of_line(operation.line, "enclosingOperation")],
        invariantRule=(
            f"every `{verbThatReferenced}` reference must resolve to a declared "
            f"{referencedKind} in scope"
        ),
        specAnchor=f"SYNTAX.md#{referencedKind}",
        citations=operationCitations,
        fixCandidates=[
            FixCandidate(
                name=f"declareMissing{referencedKind.capitalize()}",
                shape=declarationShape,
            ),
            FixCandidate(
                name="correctIdentifierSpelling",
                shape=f"# verify `{referencedName}` matches a declared {referencedKind}",
            ),
        ],
        confidence=Confidence.HIGH,
        blocksCompile=True,
        effort=Effort.TRIVIAL,
        passProvenance="check_unresolved_references",
        agentHint=(
            f"if `{referencedName}` is a typo, fix the reference; if the "
            f"{referencedKind} was deleted in a refactor, restore it or "
            f"remove all references"
        ),
    )


def _resolve_type_to_canonical(
    typeName: Optional[str],
    typeAliases: Dict[str, str],
    enumReprs: Optional[Dict[str, str]] = None,
) -> Optional[str]:
    """Chase a name through `type X Y` aliases, then collapse to a canonical
    primitive when the alias terminus is one of the equivalence groups."""
    if typeName is None:
        return None
    enumReprs = enumReprs or {}
    visited: Set[str] = set()
    currentName = typeName
    while currentName in typeAliases and currentName not in visited:
        visited.add(currentName)
        currentName = typeAliases[currentName]
    if currentName in enumReprs and currentName not in visited:
        visited.add(currentName)
        currentName = enumReprs[currentName]
        while currentName in typeAliases and currentName not in visited:
            visited.add(currentName)
            currentName = typeAliases[currentName]
    return PRIMITIVE_CANONICAL_BY_TYPE.get(currentName, currentName)


def _resolve_type_head(
    typeName: Optional[str],
    typeAliases: Dict[str, str],
    enumReprs: Optional[Dict[str, str]] = None,
) -> Optional[str]:
    if typeName is None:
        return None
    enumReprs = enumReprs or {}
    visited: Set[str] = set()
    currentName = typeName
    while currentName in typeAliases and currentName not in visited:
        visited.add(currentName)
        currentName = typeAliases[currentName]
    if currentName in enumReprs and currentName not in visited:
        visited.add(currentName)
        currentName = enumReprs[currentName]
        while currentName in typeAliases and currentName not in visited:
            visited.add(currentName)
            currentName = typeAliases[currentName]
    return currentName


def _strict_numeric_shape(typeName: Optional[str]) -> Optional[str]:
    if typeName is None:
        return None
    signed8 = {"I8", "CSignedByte", "CChar", "CSchar", "CByte"}
    signed16 = {"I16", "CSignedInt16", "CShort"}
    signed32 = {"I32", "CSignedInt32", "ExitCode"}
    signed64 = {
        "I64", "CSignedInt64", "CByteCount", "CSignedByteCount",
        "CAddressOffset", "CUnixSecondsSinceEpoch", "CCpuClockTicks",
        "CFileByteOffset", "DurationMilliseconds", "MonotonicMilliseconds",
        "UtcMilliseconds",
    }
    unsigned8 = {"CUnsignedByte", "CUchar"}
    unsigned16 = {"CUnsignedInt16", "CUshort"}
    unsigned32 = {"CUnsignedInt32", "CUint"}
    unsigned64 = {"CUnsignedInt64", "CMaxUnsignedInt", "CUintmax"}
    float32 = {"F32", "CFloat32", "CFloat"}
    float64 = {"F64", "CFloat64", "CDouble"}
    if typeName == "Bool":
        return "bool"
    if typeName in signed8:
        return "signed8"
    if typeName in signed16:
        return "signed16"
    if typeName in signed32:
        return "signed32"
    if typeName in signed64:
        return "signed64"
    if typeName in unsigned8:
        return "unsigned8"
    if typeName in unsigned16:
        return "unsigned16"
    if typeName in unsigned32:
        return "unsigned32"
    if typeName in unsigned64:
        return "unsigned64"
    if typeName in float32:
        return "float32"
    if typeName in float64:
        return "float64"
    return typeName


def _enum_arg_shape_mismatch(
    expectedType: str,
    actualType: str,
    typeAliases: Dict[str, str],
    enumReprs: Dict[str, str],
) -> bool:
    if actualType not in enumReprs and expectedType not in enumReprs:
        return False
    if expectedType in enumReprs and actualType in enumReprs:
        return expectedType != actualType
    expectedHead = _resolve_type_head(expectedType, typeAliases, enumReprs)
    actualHead = _resolve_type_head(actualType, typeAliases, enumReprs)
    return _strict_numeric_shape(expectedHead) != _strict_numeric_shape(actualHead)


I64_COMPARISON_TARGETS: Dict[str, str] = {
    "math.equalI64": "math.equalCSignedInt32",
    "math.notEqualI64": "math.notEqualCSignedInt32",
    "math.lessThanI64": "math.lessThanCSignedInt32",
    "math.lessThanOrEqualI64": "math.lessThanOrEqualCSignedInt32",
    "math.greaterThanI64": "math.greaterThanCSignedInt32",
    "math.greaterThanOrEqualI64": "math.greaterThanOrEqualCSignedInt32",
}

I32_COMPARISON_TARGETS: Dict[str, str] = {
    value: key for key, value in I64_COMPARISON_TARGETS.items()
}

MATH_EXACT_TARGET_SIGNATURES: Dict[str, List[Tuple[str, str]]] = {
    targetName: signature
    for targetName, signature in BUILTIN_TARGET_SIGNATURES.items()
    if targetName.startswith("math.")
}


def _enum_context(
    facts: ExtendedFacts,
) -> Tuple[Dict[str, str], Dict[str, List[str]], Dict[str, Dict[str, str]], Dict[str, str]]:
    enumReprs: Dict[str, str] = {}
    enumCasesByType: Dict[str, List[str]] = {}
    enumCaseValuesByType: Dict[str, Dict[str, str]] = {}
    enumTypeByCase: Dict[str, str] = {}

    nextValueByEnum: Dict[str, int] = {}
    for sourceLine in facts.base.lines:
        if not sourceLine.tokens or is_comment(sourceLine):
            continue
        if sourceLine.verb == "enum" and sourceLine.args:
            enumName = sourceLine.args[0]
            reprName = "CSignedInt32"
            if len(sourceLine.args) >= 3 and sourceLine.args[1] == "repr":
                reprName = sourceLine.args[2]
            enumReprs[enumName] = reprName
            enumCasesByType.setdefault(enumName, [])
            enumCaseValuesByType.setdefault(enumName, {})
            nextValueByEnum.setdefault(enumName, 0)
        elif sourceLine.verb == "enumCase" and len(sourceLine.args) >= 2:
            enumName = sourceLine.args[0]
            caseName = sourceLine.args[1]
            enumCasesByType.setdefault(enumName, []).append(caseName)
            enumTypeByCase[caseName] = enumName
            nextValue = nextValueByEnum.get(enumName, 0)
            if len(sourceLine.args) >= 3:
                try:
                    caseValue = int(sourceLine.args[2])
                except ValueError:
                    caseValue = nextValue
            else:
                caseValue = nextValue
            enumCaseValuesByType.setdefault(enumName, {}).setdefault(str(caseValue), caseName)
            nextValueByEnum[enumName] = caseValue + 1

    return enumReprs, enumCasesByType, enumCaseValuesByType, enumTypeByCase


def check_argument_type_mismatch(facts: ExtendedFacts) -> List[Diagnostic]:
    """`arg CALL ARGNAME VALUE` where VALUE's declared type doesn't match
    the call target's expected type for ARGNAME. Looks up target signature
    from BUILTIN_TARGET_SIGNATURES (for built-ins) or from `input OP NAME
    TYPE` rows (for user ops). Skipped when either type is unknown — we
    err on the side of false negatives rather than false positives."""
    diagnostics: List[Diagnostic] = []
    importIndex = build_import_contract_index(facts)
    typeAliases = dict(facts.base.type_aliases)
    for importedSymbol in (
        list(importIndex.qualifiedSymbols.values())
        + list(importIndex.singularSymbols.values())
    ):
        if importedSymbol.kind not in {"type", "error"}:
            continue
        aliasTarget: Optional[str] = None
        for edge in importedSymbol.edges:
            if edge.edgeKind == "type.alias" and len(edge.values) >= 2:
                aliasTarget = edge.values[1]
                break
        typeAliases.setdefault(
            importedSymbol.localName,
            aliasTarget or importedSymbol.exportedName,
        )

    # Build per-user-op signature: argName → declared type
    enumReprs, _enumCasesByType, _enumCaseValuesByType, _enumTypeByCase = _enum_context(facts)

    userOperationSignatures: Dict[str, Dict[str, str]] = {}
    for operation in facts.base.operations.values():
        signature: Dict[str, str] = {}
        for sourceLine in operation.lines:
            if (sourceLine.tokens and not is_comment(sourceLine)
                    and sourceLine.verb == "input" and len(sourceLine.args) >= 3
                    and sourceLine.args[0] == operation.name):
                signature[sourceLine.args[1]] = sourceLine.args[2]
        userOperationSignatures[operation.name] = signature
    for importedSymbol in (
        list(importIndex.qualifiedSymbols.values())
        + list(importIndex.singularSymbols.values())
    ):
        if importedSymbol.kind != "operation":
            continue
        signature: Dict[str, str] = {}
        for edge in importedSymbol.edges:
            if edge.edgeKind == "operation.input" and len(edge.values) >= 3:
                signature[edge.values[1]] = edge.values[2]
        userOperationSignatures[importedSymbol.localName] = signature

    # Build module-scope value-name → type map from forms that survive
    # outside any operation body (domain literals, module storage, etc.).
    moduleScopeValueTypes: Dict[str, str] = {
        name: constFact.type_name
        for name, constFact in facts.base.consts.items()
    }
    for importedSymbol in (
        list(importIndex.qualifiedSymbols.values())
        + list(importIndex.singularSymbols.values())
    ):
        if importedSymbol.kind != "constant":
            continue
        for edge in importedSymbol.edges:
            if edge.edgeKind == "constant.value" and edge.values:
                moduleScopeValueTypes[importedSymbol.localName] = edge.values[0]
                break
    currentOperationDuringScan: Optional[str] = None
    for sourceLine in facts.base.lines:
        if not sourceLine.tokens or is_comment(sourceLine):
            continue
        verb = sourceLine.verb
        args = sourceLine.args
        if verb == "operation" and args:
            currentOperationDuringScan = args[0]
            continue
        if currentOperationDuringScan is not None:
            # Inside an operation body — defer to per-op walk below.
            continue
        if verb == "domainLiteral" and len(args) >= 2:
            moduleScopeValueTypes[args[0]] = args[1]
        elif verb == "literal" and len(args) >= 2:
            moduleScopeValueTypes[args[0]] = args[1]
        elif verb in {"const"} and len(args) >= 2:
            moduleScopeValueTypes[args[0]] = args[1]
        elif verb == "enumCase" and len(args) >= 2:
            moduleScopeValueTypes[args[1]] = args[0]
        elif verb == "storage" and len(args) >= 5:
            # `storage SCOPE MUTABILITY NAME TYPE INIT`
            moduleScopeValueTypes[args[2]] = args[3]
        elif verb == "sharedState" and len(args) >= 5:
            moduleScopeValueTypes[args[2]] = args[3]

    # Per-op: build local value-type map + call target map, then check args
    for operation in facts.base.operations.values():
        operationCitations = narrative_citations_for_operation(facts, operation.name)
        # Start with module-scope visibility, layer operation-local on top
        valueTypesInScope: Dict[str, str] = dict(moduleScopeValueTypes)
        callTargetByCallName: Dict[str, str] = {}
        for sourceLine in operation.lines:
            if not sourceLine.tokens or is_comment(sourceLine):
                continue
            verb = sourceLine.verb
            args = sourceLine.args
            if verb == "input" and len(args) >= 3 and args[0] == operation.name:
                valueTypesInScope[args[1]] = args[2]
            elif verb in {"const", "var"} and len(args) >= 2:
                valueTypesInScope[args[0]] = args[1]
            elif verb in {"bind", "bindOk", "bindError"} and len(args) >= 3:
                valueTypesInScope[args[0]] = args[1]
            elif verb == "call" and len(args) >= 2:
                callTargetByCallName[args[0]] = args[1]

        # Second pass: every `arg CALL ARGNAME VALUE` against the target signature
        for sourceLine in operation.lines:
            if (not sourceLine.tokens or is_comment(sourceLine)
                    or sourceLine.verb != "arg" or len(sourceLine.args) < 3):
                continue
            callReferenceName, argumentName, suppliedValueName = (
                sourceLine.args[0], sourceLine.args[1], sourceLine.args[2]
            )
            targetName = callTargetByCallName.get(callReferenceName)
            if not targetName:
                # Unresolved call — SS4101 already handles that.
                continue

            expectedType: Optional[str] = None
            if targetName in BUILTIN_TARGET_SIGNATURES:
                for signatureArgName, signatureArgType in BUILTIN_TARGET_SIGNATURES[targetName]:
                    if signatureArgName == argumentName:
                        expectedType = signatureArgType
                        break
            elif targetName in userOperationSignatures:
                expectedType = userOperationSignatures[targetName].get(argumentName)

            if expectedType is None:
                # Unknown signature → skip rather than guess.
                continue

            actualType = valueTypesInScope.get(suppliedValueName)
            if actualType is None:
                # Unknown value type → skip; might be a magic placeholder
                # or a name the linter hasn't yet learned.
                continue

            if expectedType == "GuiControl" and actualType in GUI_CONTROL_HANDLE_TYPES:
                continue

            resolvedExpected = _resolve_type_to_canonical(expectedType, typeAliases, enumReprs)
            resolvedActual = _resolve_type_to_canonical(actualType, typeAliases, enumReprs)
            if resolvedExpected == resolvedActual:
                if not _enum_arg_shape_mismatch(expectedType, actualType, typeAliases, enumReprs):
                    continue

            diagnostics.append(Diagnostic(
                tier=Tier.T1_SPEC,
                code="SS4301",
                kind="typeIntegrity.argumentTypeMismatch",
                severity=Severity.ERROR,
                subjectName=suppliedValueName,
                subjectKind="argValue",
                gapEdge="matchingType",
                intentSlogan="arg value type does not match target signature",
                primary=span_of_line(sourceLine, "argTypeMismatchSite"),
                related=[span_of_line(operation.line, "enclosingOperation")],
                invariantRule=(
                    f"`arg {callReferenceName} {argumentName} {suppliedValueName}` "
                    f"expects type `{expectedType}` (canonical `{resolvedExpected}`); "
                    f"`{suppliedValueName}` is declared `{actualType}` "
                    f"(canonical `{resolvedActual}`)"
                ),
                specAnchor="SYNTAX.md#arg",
                citations=operationCitations,
                fixCandidates=[
                    FixCandidate(
                        name="supplyValueOfExpectedType",
                        shape=f"arg {callReferenceName} {argumentName} <valueOfType:{expectedType}>",
                    ),
                    FixCandidate(
                        name="declareAdapterCall",
                        shape=(
                            f"# bind an intermediate value via a conversion call "
                            f"producing `{expectedType}` from `{actualType}`, "
                            f"then arg that intermediate here"
                        ),
                    ),
                ],
                confidence=Confidence.HIGH,
                blocksCompile=True,
                effort=Effort.LOCAL,
                passProvenance="check_argument_type_mismatch",
                agentHint=(
                    f"type mismatches at call boundaries are the #1 cause of "
                    f"downstream lowering failures; resolve at the source"
                ),
            ))
    return diagnostics


def check_math_operand_width_drift(facts: ExtendedFacts) -> List[Diagnostic]:
    diagnostics: List[Diagnostic] = []
    typeAliases = facts.base.type_aliases
    enumReprs, _enumCasesByType, _enumCaseValuesByType, enumTypeByCase = _enum_context(facts)

    moduleScopeValueTypes: Dict[str, str] = {
        name: constFact.type_name
        for name, constFact in facts.base.consts.items()
    }
    currentOperationDuringScan: Optional[str] = None
    for sourceLine in facts.base.lines:
        if not sourceLine.tokens or is_comment(sourceLine):
            continue
        verb = sourceLine.verb
        args = sourceLine.args
        if verb == "operation" and args:
            currentOperationDuringScan = args[0]
            continue
        if currentOperationDuringScan is not None:
            continue
        if verb == "domainLiteral" and len(args) >= 2:
            moduleScopeValueTypes[args[0]] = args[1]
        elif verb == "literal" and len(args) >= 2:
            moduleScopeValueTypes[args[0]] = args[1]
        elif verb in {"const"} and len(args) >= 2:
            moduleScopeValueTypes[args[0]] = args[1]
        elif verb == "enumCase" and len(args) >= 2:
            moduleScopeValueTypes[args[1]] = args[0]
        elif verb == "storage" and len(args) >= 5:
            moduleScopeValueTypes[args[2]] = args[3]
        elif verb == "sharedState" and len(args) >= 5:
            moduleScopeValueTypes[args[2]] = args[3]

    for operation in facts.base.operations.values():
        operationCitations = narrative_citations_for_operation(facts, operation.name)
        valueTypesInScope: Dict[str, str] = dict(moduleScopeValueTypes)
        callTargetByCallName: Dict[str, str] = {}
        argLinesByCallName: Dict[str, List[SourceLine]] = {}

        for sourceLine in operation.lines:
            if not sourceLine.tokens or is_comment(sourceLine):
                continue
            verb = sourceLine.verb
            args = sourceLine.args
            if verb == "input" and len(args) >= 3 and args[0] == operation.name:
                valueTypesInScope[args[1]] = args[2]
            elif verb in {"const", "var"} and len(args) >= 2:
                valueTypesInScope[args[0]] = args[1]
            elif verb == "storage" and len(args) >= 5:
                valueTypesInScope[args[2]] = args[3]
            elif verb in {"bind", "bindOk", "bindError"} and len(args) >= 3:
                valueTypesInScope[args[0]] = args[1]
            elif verb == "call" and len(args) >= 2:
                callTargetByCallName[args[0]] = args[1]
            elif verb == "arg" and len(args) >= 3:
                argLinesByCallName.setdefault(args[0], []).append(sourceLine)

        for callName, targetName in callTargetByCallName.items():
            targetSignature = MATH_EXACT_TARGET_SIGNATURES.get(targetName)
            if targetSignature is None:
                continue
            expectedTypesByArgName = {
                argName: expectedType for argName, expectedType in targetSignature
            }
            mismatchedArgs: List[Tuple[SourceLine, str, str, str, str, str, str]] = []
            for argLine in argLinesByCallName.get(callName, []):
                argumentName = argLine.args[1]
                suppliedValue = argLine.args[2]
                expectedType = expectedTypesByArgName.get(argumentName)
                if expectedType is None:
                    continue
                actualType = valueTypesInScope.get(suppliedValue)
                if actualType is None:
                    continue
                expectedHead = _resolve_type_head(expectedType, typeAliases, enumReprs)
                actualHead = _resolve_type_head(actualType, typeAliases, enumReprs)
                expectedShape = _strict_numeric_shape(expectedHead)
                actualShape = _strict_numeric_shape(actualHead)
                if expectedShape != actualShape:
                    mismatchedArgs.append((
                        argLine,
                        suppliedValue,
                        actualType,
                        expectedType,
                        expectedShape or expectedHead or expectedType,
                        actualShape or actualHead or actualType,
                        argumentName,
                    ))

            if not mismatchedArgs:
                continue

            (
                firstArgLine,
                firstValue,
                firstType,
                expectedType,
                expectedShape,
                actualShape,
                argumentName,
            ) = mismatchedArgs[0]
            suggestedTarget: Optional[str] = None
            if targetName in I64_COMPARISON_TARGETS and actualShape == "signed32":
                suggestedTarget = I64_COMPARISON_TARGETS[targetName]
            elif targetName in I32_COMPARISON_TARGETS and actualShape == "signed64":
                suggestedTarget = I32_COMPARISON_TARGETS[targetName]
            fixCandidates = [
                FixCandidate(
                    name="makeConversionExplicit",
                    shape=(
                        f"# convert `{firstValue}` to `{expectedType}` with an explicit "
                        f"conversion before `arg {callName} {argumentName} ...`"
                    ),
                ),
            ]
            if suggestedTarget is not None:
                fixCandidates.insert(0, FixCandidate(
                    name="useWidthSpecificMathTarget",
                    shape=f"call {callName} {suggestedTarget}",
                ))
            diagnostics.append(Diagnostic(
                tier=Tier.T1_SPEC,
                code="SS4303",
                kind="typeIntegrity.mathOperandWidthDrift",
                severity=Severity.ERROR,
                subjectName=callName,
                subjectKind="call",
                gapEdge="exactMathOperandWidth",
                intentSlogan="math operand width must be explicit",
                primary=span_of_line(firstArgLine, "widthDriftArg"),
                related=[span_of_line(operation.line, "enclosingOperation")],
                invariantRule=(
                    f"`{targetName}` argument `{argumentName}` expects "
                    f"`{expectedType}`-shaped math input (`{expectedShape}`); "
                    f"`{firstValue}` is `{firstType}` (`{actualShape}`). "
                    "Math lowering does not widen or narrow implicitly; use a "
                    "width-specific math target or an explicit conversion."
                ),
                specAnchor="docs/toolchain/linter.md#width-checks",
                citations=operationCitations,
                fixCandidates=fixCandidates,
                confidence=Confidence.HIGH,
                blocksCompile=True,
                effort=Effort.LOCAL,
                passProvenance="check_math_operand_width_drift",
                agentHint=(
                    "math lowering requires exact operand widths; insert an "
                    "explicit conversion operation instead of relying on codegen"
                ),
            ))

    return diagnostics


def _is_integer_literal(token: str) -> bool:
    stripped = token.lstrip("-")
    return bool(stripped) and stripped.isdigit()


def _operation_success_output_type(
    operation: OperationFact,
) -> Tuple[Optional[str], Optional[str], Optional[SourceLine]]:
    for sourceLine in operation.lines:
        if (sourceLine.tokens and not is_comment(sourceLine)
                and sourceLine.verb == "output" and len(sourceLine.args) >= 2
                and sourceLine.args[0] == operation.name):
            if sourceLine.args[1] == "Result":
                if len(sourceLine.args) >= 3:
                    return sourceLine.args[2], "returnOk", sourceLine
                return None, None, sourceLine
            return sourceLine.args[1], "returnValue", sourceLine
    return None, None, None


def check_enum_return_uses_case(facts: ExtendedFacts) -> List[Diagnostic]:
    diagnostics: List[Diagnostic] = []
    typeAliases = facts.base.type_aliases
    _enumReprs, enumCasesByType, enumCaseValuesByType, enumTypeByCase = _enum_context(facts)

    for operation in facts.base.operations.values():
        outputType, expectedReturnVerb, outputLine = _operation_success_output_type(operation)
        if outputType is None or expectedReturnVerb is None:
            continue
        enumType = _resolve_type_head(outputType, typeAliases, {})
        if enumType not in enumCasesByType:
            continue

        validCases = set(enumCasesByType.get(enumType, []))
        operationCitations = narrative_citations_for_operation(facts, operation.name)
        for sourceLine in operation.lines:
            if (not sourceLine.tokens or is_comment(sourceLine)
                    or sourceLine.verb != expectedReturnVerb or not sourceLine.args):
                continue
            returnedValue = sourceLine.args[0]
            if returnedValue in validCases:
                continue

            returnedEnumType = enumTypeByCase.get(returnedValue)
            isWrongEnumCase = returnedEnumType is not None and returnedEnumType != enumType
            if not _is_integer_literal(returnedValue) and not isWrongEnumCase:
                continue

            suggestedCase = enumCaseValuesByType.get(enumType, {}).get(returnedValue)
            if suggestedCase is None:
                suggestedCase = enumCasesByType.get(enumType, [f"<{enumType}Case>"])[0]
                autoApplicable = False
            else:
                autoApplicable = True

            diagnostics.append(Diagnostic(
                tier=Tier.T1_SPEC,
                code="SS4302",
                kind="typeIntegrity.enumReturnUsesRawValue",
                severity=Severity.ERROR,
                subjectName=returnedValue,
                subjectKind="returnValue",
                gapEdge="enumCase",
                intentSlogan="enum return uses raw value",
                primary=span_of_line(sourceLine, "enumReturnSite"),
                related=[span_of_line(outputLine, "enumOutputContract")] if outputLine else [],
                invariantRule=(
                    f"operation `{operation.name}` returns enum `{enumType}`; "
                    f"`{expectedReturnVerb}` must use one of its enum cases"
                ),
                specAnchor="SYNTAX.md#enumCase",
                citations=operationCitations,
                fixCandidates=[
                    FixCandidate(
                        name="returnEnumCase",
                        shape=f"{expectedReturnVerb} {suggestedCase}",
                        autoApplicable=autoApplicable,
                    ),
                ],
                confidence=Confidence.HIGH,
                blocksCompile=True,
                effort=Effort.TRIVIAL,
                passProvenance="check_enum_return_uses_case",
                agentHint=(
                    "closed enum outputs should preserve their semantic case "
                    "names at operation boundaries; raw repr values erase the "
                    "status domain the enum was created to expose"
                ),
            ))

    return diagnostics


def check_duplicate_declarations(facts: ExtendedFacts) -> List[Diagnostic]:
    """Same name declared twice in the same scope. Operation-scoped kinds
    (label, call) collide only within the same op; module-scoped kinds
    (operation, type, record, error, capability) collide globally."""
    diagnostics: List[Diagnostic] = []
    seenDeclarations: Dict[Tuple[str, ...], SourceLine] = {}
    currentOperationName: Optional[str] = None

    for sourceLine in facts.base.lines:
        if not sourceLine.tokens or is_comment(sourceLine) or not sourceLine.args:
            continue
        verb = sourceLine.verb

        declarationKey: Optional[Tuple[str, ...]] = None
        declarationKind = ""

        if verb == "operation":
            declarationKey = ("operation", sourceLine.args[0])
            declarationKind = "operation"
            currentOperationName = sourceLine.args[0]
        elif verb == "label" and currentOperationName:
            declarationKey = ("label", currentOperationName, sourceLine.args[0])
            declarationKind = "label"
        elif verb == "call" and currentOperationName and len(sourceLine.args) >= 2:
            declarationKey = ("call", currentOperationName, sourceLine.args[0])
            declarationKind = "call"
        elif verb == "type":
            declarationKey = ("type", sourceLine.args[0])
            declarationKind = "typeAlias"
        elif verb == "record":
            declarationKey = ("record", sourceLine.args[0])
            declarationKind = "record"
        elif verb == "error":
            declarationKey = ("error", sourceLine.args[0])
            declarationKind = "errorDomain"
        elif verb == "capability":
            declarationKey = ("capability", sourceLine.args[0])
            declarationKind = "capability"
        elif verb == "enum":
            declarationKey = ("enum", sourceLine.args[0])
            declarationKind = "enum"
        elif verb == "retryPolicy":
            declarationKey = ("retryPolicy", sourceLine.args[0])
            declarationKind = "retryPolicy"
        elif verb == "trustBoundary":
            declarationKey = ("trustBoundary", sourceLine.args[0])
            declarationKind = "trustBoundary"
        elif verb == "jsonCodec":
            declarationKey = ("jsonCodec", sourceLine.args[0])
            declarationKind = "jsonCodec"

        if declarationKey is None:
            continue
        priorLine = seenDeclarations.get(declarationKey)
        if priorLine is None:
            seenDeclarations[declarationKey] = sourceLine
            continue

        scopeHint = f" (in operation `{currentOperationName}`)" if len(declarationKey) > 2 else ""
        diagnostics.append(Diagnostic(
            tier=Tier.T1_SPEC,
            code="SS4201",
            kind=f"duplicateDeclaration.{declarationKind}",
            severity=Severity.ERROR,
            subjectName=declarationKey[-1],
            subjectKind=declarationKind,
            gapEdge="uniqueIdentifier",
            intentSlogan=f"{declarationKind} `{declarationKey[-1]}` declared twice",
            primary=span_of_line(sourceLine, "duplicateDeclaration"),
            related=[span_of_line(priorLine, "originalDeclaration")],
            invariantRule=(
                f"each `{verb}` declaration name must be unique within its scope"
                + scopeHint
            ),
            specAnchor=f"SYNTAX.md#{verb}",
            fixCandidates=[
                FixCandidate(
                    name="renameDuplicate",
                    shape=f"{verb} <distinctName> …",
                ),
                FixCandidate(
                    name="removeDuplicateDeclaration",
                    shape=f"# remove the duplicate `{verb} {declarationKey[-1]} …` row",
                    autoApplicable=False,  # could be either of two; agent must pick
                ),
            ],
            confidence=Confidence.HIGH,
            blocksCompile=True,
            effort=Effort.TRIVIAL,
            passProvenance="check_duplicate_declarations",
            agentHint=(
                "duplicates almost always come from copy-paste; check that the "
                "two rows aren't meant to be different declarations with a "
                "renamed identifier"
            ),
        ))

    return diagnostics


# ==========================================================================
# SS36xx — webserver discipline
# ==========================================================================

# --------------------------------------------------------------------------
# SOURCE-OF-TRUTH note for native HTTP target sets
# --------------------------------------------------------------------------
# The constants below enumerate the native HTTP surface. They are one of
# three sites that must stay in lockstep:
#
#   1. semsc.py — the dispatch block (`if target == "http.responseText":`
#      and friends). That block carries the same SOURCE-OF-TRUTH banner.
#   2. semlint.py (here) — the constants below + ALL_NATIVE_HTTP_TARGETS.
#   3. SYNTAX.md — the two `http.requestMethod, …` and
#      `http.responseText, …` umbrella rows under the call-targets section.
#
# Adding or removing a target requires updating all three sites. The
# `TestHttpTargetSourceOfTruth` class in test_semlint.py parses semsc.py's
# dispatch block and asserts the parsed set equals ALL_NATIVE_HTTP_TARGETS.
# If that test fails the drift is real — fix the underlying mismatch
# rather than the test.
# --------------------------------------------------------------------------

# RFC 7231 / 5789 verbs the native webserver dispatcher pattern-matches on.
# CONNECT and TRACE are excluded on purpose: the blocking adapter has no
# tunneling semantics, and TRACE would echo opaque request bytes back to
# the client which is a known information-disclosure footgun. A handler
# bound to a route whose METHOD is outside this set is dead code — the
# dispatcher silently never matches it.
HTTP_METHOD_WHITELIST: frozenset = frozenset({
    "GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS",
})

# http.* request readers that return a non-null pointer for any
# dispatched request. Handlers that bind from these do NOT need a
# pointer.isNull guard before forwarding to a response body writer.
NON_NULLABLE_HTTP_REQUEST_READS: frozenset = frozenset({
    "http.requestMethod",
    "http.requestPath",
    "http.requestBodyLength",
    "http.multipartPartLength",
})

# http.* call targets that return a pointer which may legitimately be null
# when the named header / query / multipart part is absent. Values bound
# from these calls are a footgun when handed straight back into a response
# body writer without a null guard, because the response writer rejects a
# null pointer with the adapter's `handler failed` 500 path.
NULLABLE_HTTP_REQUEST_READS: frozenset = frozenset({
    "http.requestHeader",
    "http.requestQueryParam",
    # ss_http_request_path_param returns NULL when the named param isn't
    # part of the matched route's pattern (or when the matched route is
    # literal-only). Treated the same as the other absent-input readers
    # so SS3603 forces a pointer.isNull guard before the value flows
    # into a response body writer.
    "http.requestPathParam",
    # ss_http_request_cookie returns NULL when the Cookie header is
    # absent, the named cookie isn't present, or the value overflows
    # the per-request scratch. Apps reading the session-cookie value
    # MUST pointer.isNull guard before treating the result as a real
    # token, or SS3603 fires.
    "http.requestCookie",
    "http.requestBodyText",
    "http.requestBodyBytes",
    "http.multipartPartText",
    "http.multipartPartBytes",
    "http.multipartPartFilename",
    "http.multipartPartContentType",
})

# Response writers that reject a null `body` argument at runtime. Passing
# a nullable bind to any of these surfaces the adapter's null-body 500
# unless the handler has guarded the pointer first OR explicitly opted
# into the failure-path contract via a warning text marker.
HTTP_RESPONSE_BODY_WRITERS: frozenset = frozenset({
    "http.responseText",
    "http.responseBytes",
    "http.responseSseEvent",
})

# Non-body response writers (headers etc.). Together with the body
# writers, these form the full response-side surface.
HTTP_RESPONSE_OTHER_WRITERS: frozenset = frozenset({
    "http.responseHeader",
    # File responses write a body, but the linter's nullable-body
    # propagation tracks `body`/`data` arguments specifically. The file
    # writer has root/path arguments and is classified here so target
    # coverage stays explicit without turning it into a body-forwarder.
    "http.responseFile",
})

# HTTP utility calls that are compiler-dispatched but are neither
# request readers nor response writers.
HTTP_UTILITY_TARGETS: frozenset = frozenset({
    "http.nowMillis",
    "http.ensureDirectory",
})

# The union the drift test compares against semsc.py's dispatch block.
# Any http.* target reachable in the lowering must appear in exactly one
# of the four classifier sets above so we can answer "is this target
# nullable" / "is this target a body writer" by membership alone.
ALL_NATIVE_HTTP_TARGETS: frozenset = (
    NON_NULLABLE_HTTP_REQUEST_READS
    | NULLABLE_HTTP_REQUEST_READS
    | HTTP_RESPONSE_BODY_WRITERS
    | HTTP_RESPONSE_OTHER_WRITERS
    | HTTP_UTILITY_TARGETS
)

# Legacy substring markers that, when present in an operation's `warning`
# text, used to opt the operation out of the unguardedHttpInput lint. The
# canonical opt-out is now the `pinsNullBodyFailurePath OP "rationale"`
# verb (see SYNTAX.md); these substrings are still honored for one
# deprecation cycle, but their use trips SS3605 `legacyNullBodyMarker`
# pointing the agent at the verb-based replacement.
LEGACY_HTTP_NULL_GUARD_OPT_OUT_MARKERS: Tuple[str, ...] = (
    "null-body failure path",
    "null-body 500",
)


def _collect_transitive_response_body_writers(facts: ExtendedFacts) -> Set[str]:
    """Return HTTP_RESPONSE_BODY_WRITERS expanded with every user op that
    declares `responseBodyForwarder OP bodyArgName` and actually forwards
    that input to one of the writers (or to another forwarder).

    The verb is the contract: an op that wraps a response writer MUST
    declare it explicitly so the lint can cite the declaration rather
    than infer the wrapper role from a magic `body` arg-name match. The
    walk still iterates to a fixed point so a wrapper-of-a-wrapper is
    recognized — but only when each layer carries the verb.

    A `responseBodyForwarder` declaration that does NOT actually forward
    the named input to a writer trips SS3607 (forwarderDeclarationNotHonored,
    checked separately) — that keeps the verb from being a no-op claim.
    """
    writers: Set[str] = set(HTTP_RESPONSE_BODY_WRITERS)
    # Build the declared (op_name -> body_arg_name) map once. Ops without
    # the verb are never added to `writers` regardless of their shape.
    declaredForwarderArgNameByOp: Dict[str, str] = {}
    for sourceLine in facts.base.lines:
        if (is_comment(sourceLine) or not sourceLine.tokens
                or sourceLine.verb != "responseBodyForwarder"
                or len(sourceLine.args) < 2):
            continue
        declaredForwarderArgNameByOp[sourceLine.args[0]] = sourceLine.args[1]
    if not declaredForwarderArgNameByOp:
        return writers
    changed = True
    while changed:
        changed = False
        for operationName, declaredBodyArgName in declaredForwarderArgNameByOp.items():
            if operationName in writers:
                continue
            operationFact = facts.base.operations.get(operationName)
            if operationFact is None:
                continue
            # Build the op's call-target map fresh each pass so newly-
            # promoted wrappers feed the next iteration.
            callTargetsByCallName: Dict[str, str] = {
                sl.args[0]: sl.args[1]
                for sl in operationFact.lines
                if (not is_comment(sl) and sl.tokens
                    and sl.verb == "call" and len(sl.args) >= 2)
            }
            forwardsDeclaredArg = False
            for sourceLine in operationFact.lines:
                if (is_comment(sourceLine) or not sourceLine.tokens
                        or sourceLine.verb != "arg"
                        or len(sourceLine.args) < 3):
                    continue
                if (sourceLine.args[1] == "body"
                        and sourceLine.args[2] == declaredBodyArgName
                        and callTargetsByCallName.get(sourceLine.args[0]) in writers):
                    forwardsDeclaredArg = True
                    break
            if forwardsDeclaredArg:
                writers.add(operationName)
                changed = True
    return writers


def check_response_body_forwarder_declaration_honored(facts: ExtendedFacts) -> List[Diagnostic]:
    """SS3607 — `responseBodyForwarder OP bodyArgName` claims the op
    forwards `bodyArgName` to an http.response* writer (or another
    forwarder). If the op never actually wires `arg <writerCall> body
    bodyArgName` against a known writer, the declaration is a false
    claim — the lint would treat callers as forwarders without basis."""
    diagnostics: List[Diagnostic] = []
    # Compute writers WITHOUT trusting unverified forwarder declarations:
    # start from the runtime writers and only count ops as forwarders
    # after this check has accepted them. So for THIS check we just need
    # to verify the forwarding shape against the runtime writers + any
    # other op whose declaration ALSO honors its claim (fixed point).
    runtimeWriters: Set[str] = set(HTTP_RESPONSE_BODY_WRITERS)
    declaredForwarderRows: List[Tuple[SourceLine, str, str]] = []  # (line, op, argName)
    for sourceLine in facts.base.lines:
        if (is_comment(sourceLine) or not sourceLine.tokens
                or sourceLine.verb != "responseBodyForwarder"
                or len(sourceLine.args) < 2):
            continue
        declaredForwarderRows.append(
            (sourceLine, sourceLine.args[0], sourceLine.args[1])
        )
    honoredForwarders: Set[str] = set()
    changed = True
    while changed:
        changed = False
        for sourceLine, operationName, declaredBodyArgName in declaredForwarderRows:
            if operationName in honoredForwarders:
                continue
            operationFact = facts.base.operations.get(operationName)
            if operationFact is None:
                continue
            callTargetsByCallName: Dict[str, str] = {
                sl.args[0]: sl.args[1]
                for sl in operationFact.lines
                if (not is_comment(sl) and sl.tokens
                    and sl.verb == "call" and len(sl.args) >= 2)
            }
            acceptedWriters = runtimeWriters | honoredForwarders
            for innerLine in operationFact.lines:
                if (is_comment(innerLine) or not innerLine.tokens
                        or innerLine.verb != "arg"
                        or len(innerLine.args) < 3):
                    continue
                if (innerLine.args[1] == "body"
                        and innerLine.args[2] == declaredBodyArgName
                        and callTargetsByCallName.get(innerLine.args[0]) in acceptedWriters):
                    honoredForwarders.add(operationName)
                    changed = True
                    break
    for sourceLine, operationName, declaredBodyArgName in declaredForwarderRows:
        if operationName in honoredForwarders:
            continue
        diagnostics.append(Diagnostic(
            tier=Tier.T3_REFINEMENT,
            code="SS3607",
            kind="webserver.forwarderDeclarationNotHonored",
            severity=Severity.WARNING,
            subjectName=operationName,
            subjectKind="operation",
            gapEdge="forwarderImplementation",
            intentSlogan=f"`{declaredBodyArgName}` is not actually forwarded to a response writer",
            primary=span_of_line(sourceLine, "responseBodyForwarderDeclaration"),
            invariantRule=(
                f"`responseBodyForwarder {operationName} {declaredBodyArgName}` "
                f"claims this op forwards its `{declaredBodyArgName}` input to "
                f"an http.response* writer (or another declared forwarder); the "
                f"op body must contain `arg <writerCall> body {declaredBodyArgName}` "
                f"against a known writer for the claim to hold"
            ),
            specAnchor="SYNTAX.md#responseBodyForwarder",
            citations=narrative_citations_for_operation(facts, operationName),
            fixCandidates=[
                FixCandidate(
                    name="wireForwardingCall",
                    shape=(
                        f"# inside `operation {operationName}`:\n"
                        f"# arg <writerCallName> body {declaredBodyArgName}"
                    ),
                ),
                FixCandidate(
                    name="removeFalseForwarderClaim",
                    shape=f"# remove `responseBodyForwarder {operationName} {declaredBodyArgName}`",
                ),
            ],
            confidence=Confidence.HIGH,
            effort=Effort.LOCAL,
            passProvenance="check_response_body_forwarder_declaration_honored",
            agentHint="the forwarder verb is the explicit alternative to the magic `body` arg-name match; an unhonored declaration is worse than no declaration",
        ))
    return diagnostics


def check_invalid_route_method(facts: ExtendedFacts) -> List[Diagnostic]:
    """SS3601 — `route SERVER METHOD PATH HANDLER` METHOD must be in the
    native dispatcher's whitelist. Unrecognized verbs never match at
    runtime and the handler binding becomes dead code."""
    diagnostics: List[Diagnostic] = []
    allowedList = ", ".join(sorted(HTTP_METHOD_WHITELIST))
    for routeFact in facts.base.routes:
        if routeFact.method in HTTP_METHOD_WHITELIST:
            continue
        diagnostics.append(Diagnostic(
            tier=Tier.T3_REFINEMENT,
            code="SS3601",
            kind="webserver.invalidRouteMethod",
            severity=Severity.WARNING,
            subjectName=routeFact.path,
            subjectKind="route",
            gapEdge="route.method",
            intentSlogan=f"method `{routeFact.method}` not in dispatcher whitelist",
            primary=span_of_line(routeFact.line, "routeDeclaration"),
            invariantRule=(
                "route SERVER METHOD PATH HANDLER — METHOD must be one of "
                "GET/HEAD/POST/PUT/PATCH/DELETE/OPTIONS; the native dispatcher "
                "silently never matches anything else, leaving the handler dead"
            ),
            specAnchor="SYNTAX.md#route",
            fixCandidates=[
                FixCandidate(
                    name="useWhitelistedMethod",
                    shape=f"route <server> <METHOD-from: {allowedList}> {routeFact.path} {routeFact.handler}",
                ),
                FixCandidate(
                    name="removeRouteEntry",
                    shape=f"# remove `route <server> {routeFact.method} {routeFact.path} {routeFact.handler}` (dead binding)",
                ),
            ],
            confidence=Confidence.HIGH,
            effort=Effort.TRIVIAL,
            passProvenance="check_invalid_route_method",
            agentHint=(
                "CONNECT and TRACE are intentionally excluded from the "
                "whitelist; if the route is meant to be a custom verb, that "
                "is not currently supported by the native dispatcher"
            ),
        ))
    return diagnostics


def check_middleware_missing_response_effect(facts: ExtendedFacts) -> List[Diagnostic]:
    """SS3602 — an operation bound via `routeMiddleware` must declare
    `effect OP write http.response*`. The native dispatcher invokes
    middleware before the route handler specifically so it can stamp
    response headers / write response state; without a declared write
    effect the linter cannot prove the middleware honored its capability
    contract (§2 checkability law) and a future agent edit could quietly
    delete the writes."""
    diagnostics: List[Diagnostic] = []
    for sourceLine in facts.base.lines:
        if (is_comment(sourceLine) or not sourceLine.tokens
                or sourceLine.verb != "routeMiddleware"
                or len(sourceLine.args) < 3):
            continue
        routePath = sourceLine.args[1]
        middlewareName = sourceLine.args[2]
        middlewareOp = facts.base.operations.get(middlewareName)
        if middlewareOp is None:
            # Unresolved op reference is caught by SS4104; nothing to add here.
            continue
        declaresResponseWrite = False
        responseEffectLine: Optional[SourceLine] = None
        for opLine in middlewareOp.lines:
            if is_comment(opLine) or opLine.verb != "effect" or len(opLine.args) < 3:
                continue
            if (opLine.args[0] == middlewareName
                    and opLine.args[1] == "write"
                    and opLine.args[2].startswith("http.response")):
                declaresResponseWrite = True
                responseEffectLine = opLine
                break
        if declaresResponseWrite:
            continue
        diagnostics.append(Diagnostic(
            tier=Tier.T3_REFINEMENT,
            code="SS3602",
            kind="webserver.middlewareMissingResponseEffect",
            severity=Severity.WARNING,
            subjectName=middlewareName,
            subjectKind="operation.middleware",
            gapEdge="effect.write.http.response",
            intentSlogan="middleware op lacks `write http.response*` effect",
            primary=span_of_line(sourceLine, "routeMiddlewareBinding"),
            related=[span_of_line(middlewareOp.line, "middlewareOperationHeader")],
            invariantRule=(
                "every op bound via `routeMiddleware` must declare "
                "`effect <op> write http.response*` because the dispatcher "
                "invokes middleware specifically so it can write response "
                "state before the handler runs"
            ),
            specAnchor="SYNTAX.md#routeMiddleware",
            citations=narrative_citations_for_operation(facts, middlewareName),
            fixCandidates=[
                FixCandidate(
                    name="addResponseWriteEffect",
                    shape=f"effect {middlewareName} write http.response",
                ),
                FixCandidate(
                    name="removeMiddlewareBinding",
                    shape=f"# remove `routeMiddleware <server> {routePath} {middlewareName}` if this op is not actually a middleware",
                ),
            ],
            confidence=Confidence.HIGH,
            effort=Effort.TRIVIAL,
            passProvenance="check_middleware_missing_response_effect",
            agentHint=(
                "middleware that only reads request state without writing "
                "anything is usually a logging/metrics op that belongs in a "
                "different hook; if this one truly is write-free, the "
                "routeMiddleware binding is the wrong shape"
            ),
        ))
    return diagnostics


def check_unguarded_http_input(facts: ExtendedFacts) -> List[Diagnostic]:
    """SS3603 — a value bound from a nullable http.request* read must not
    flow into the `body` argument of an http.response* writer (or a
    transitive wrapper) without an intervening `pointer.isNull` guard.

    Opt-out (per-operation): include the phrase `null-body failure path`
    or `null-body 500` in a `warning OP "..."` line. This matches the
    AgentScript convention of pinning intentional negative-test surfaces
    in the source rather than the linter config — a future refactor that
    silently adds a guard would erase the pinned coverage, and the marker
    text is the contract that prevents that.
    """
    diagnostics: List[Diagnostic] = []
    responseBodyWriters = _collect_transitive_response_body_writers(facts)
    for operationName, operationFact in facts.base.operations.items():
        callTargetsByCallName: Dict[str, str] = {}
        bindLineByCallName: Dict[str, SourceLine] = {}
        for sourceLine in operationFact.lines:
            if is_comment(sourceLine) or not sourceLine.tokens:
                continue
            if sourceLine.verb == "call" and len(sourceLine.args) >= 2:
                callTargetsByCallName[sourceLine.args[0]] = sourceLine.args[1]

        # Index nullable binds: name -> declaring SourceLine
        nullableBoundValueLines: Dict[str, SourceLine] = {}
        for sourceLine in operationFact.lines:
            if (is_comment(sourceLine) or sourceLine.verb != "bind"
                    or len(sourceLine.args) < 3):
                continue
            callName = sourceLine.args[2]
            if callTargetsByCallName.get(callName) in NULLABLE_HTTP_REQUEST_READS:
                nullableBoundValueLines[sourceLine.args[0]] = sourceLine
        if not nullableBoundValueLines:
            continue

        # Canonical opt-out: `pinsNullBodyFailurePath OP "rationale"`.
        # Walk the op's lines for the verb; any presence (regardless of
        # rationale text) satisfies the opt-in. The rationale is required
        # by SS3606 `pinsNullBodyFailurePathMissingRationale` separately
        # so the explicit-context bar isn't lowered.
        optOut = False
        for sourceLine in operationFact.lines:
            if (is_comment(sourceLine) or not sourceLine.tokens
                    or sourceLine.verb != "pinsNullBodyFailurePath"
                    or not sourceLine.args
                    or sourceLine.args[0] != operationName):
                continue
            optOut = True
            break
        if optOut:
            continue
        # Legacy: fall back to the deprecated warning-text marker so the
        # one-cycle deprecation window doesn't break existing programs.
        # If the legacy form matches, the per-op SS3605 emitted by
        # `check_legacy_null_body_marker` will steer the agent to migrate.
        for sourceLine in operationFact.lines:
            if (is_comment(sourceLine) or sourceLine.verb != "warning"
                    or len(sourceLine.args) < 2):
                continue
            if sourceLine.args[0] != operationName:
                continue
            warningText = " ".join(sourceLine.args[1:])
            if any(marker in warningText for marker in LEGACY_HTTP_NULL_GUARD_OPT_OUT_MARKERS):
                optOut = True
                break
        if optOut:
            continue

        # Walk in source order so a pointer.isNull guard that runs BEFORE
        # the body usage marks the bound value as inspected. We collect
        # `arg <pointerIsNullCall> pointer <boundValue>` pairs and treat
        # everything passed through such a check as guarded thereafter.
        guardedBoundValues: Set[str] = set()
        pointerIsNullCallNames: Set[str] = set()
        for sourceLine in operationFact.lines:
            if is_comment(sourceLine) or not sourceLine.tokens:
                continue
            verb = sourceLine.verb
            args = sourceLine.args
            if verb == "call" and len(args) >= 2 and args[1] == "pointer.isNull":
                pointerIsNullCallNames.add(args[0])
            elif (verb == "arg" and len(args) >= 3
                    and args[0] in pointerIsNullCallNames
                    and args[1] == "pointer"
                    and args[2] in nullableBoundValueLines):
                guardedBoundValues.add(args[2])
            elif verb == "arg" and len(args) >= 3:
                callName = args[0]
                argName = args[1]
                valueName = args[2]
                if (argName == "body"
                        and callTargetsByCallName.get(callName) in responseBodyWriters
                        and valueName in nullableBoundValueLines
                        and valueName not in guardedBoundValues):
                    bindSourceLine = nullableBoundValueLines[valueName]
                    targetCallTarget = callTargetsByCallName[callName]
                    diagnostics.append(Diagnostic(
                        tier=Tier.T3_REFINEMENT,
                        code="SS3603",
                        kind="webserver.unguardedHttpInput",
                        severity=Severity.WARNING,
                        subjectName=valueName,
                        subjectKind="bind",
                        gapEdge="pointer.isNull",
                        intentSlogan=f"nullable bind `{valueName}` reaches response body unguarded",
                        primary=span_of_line(sourceLine, "responseBodyArg"),
                        related=[
                            span_of_line(bindSourceLine, "nullableBindSite"),
                        ],
                        invariantRule=(
                            "values bound from nullable http.request* reads "
                            "must pass a `pointer.isNull` guard before "
                            "reaching the `body` argument of http.response* "
                            "(or a wrapper that forwards body to one); the "
                            "adapter rejects a null body pointer with a 500"
                        ),
                        specAnchor="SYNTAX.md#pointer.isNull",
                        citations=narrative_citations_for_operation(facts, operationName),
                        fixCandidates=[
                            FixCandidate(
                                name="addPointerIsNullGuardThenBranch",
                                shape=(
                                    f"call {valueName}MissingCheckCall pointer.isNull\n"
                                    f"arg {valueName}MissingCheckCall pointer {valueName}\n"
                                    f"run {valueName}MissingCheckCall\n"
                                    f"bind {valueName}Missing Bool {valueName}MissingCheckCall\n"
                                    f"branchIf {valueName}Missing <missingPathLabel>"
                                ),
                            ),
                            FixCandidate(
                                name="optInToNullBodyFailurePath",
                                shape=(
                                    f"warning {operationName} \"... null-body "
                                    f"failure path ... (intentional)\""
                                ),
                            ),
                        ],
                        confidence=Confidence.HIGH,
                        effort=Effort.LOCAL,
                        passProvenance="check_unguarded_http_input",
                        agentHint=(
                            "either guard with pointer.isNull and branch to a "
                            "400 reply, or accept the null-body 500 contract "
                            "and document it with the opt-out marker phrase; "
                            "silently routing nullable reads to response body "
                            "exposes adapter internals to clients"
                        ),
                    ))
    return diagnostics


def check_middleware_return_type_is_middleware_control(facts: ExtendedFacts) -> List[Diagnostic]:
    """SS3610 — every operation bound via `routeMiddleware` MUST declare
    `output OP MiddlewareControl` (NOT bare `CSignedInt32`).

    The native HTTP dispatcher at sem_http_runtime.c interprets the
    middleware return value as a `MiddlewareControl` enum:

      - `continueMiddlewareControl`     (0) → call the route handler
      - `shortCircuitMiddlewareControl` (1) → skip the handler; send
        the response middleware already wrote
      - Anything else                       → send `500 middleware failed`

    A middleware op that declares bare `CSignedInt32` output silently
    erases that contract: a future agent could return `1` thinking it
    means "failure" (the same value means "short-circuit" under the
    real contract), and the dispatcher would happily skip the handler
    and ship whatever was in `response.body` (or an empty body, or
    uninitialized state). The MiddlewareControl type IS the contract;
    the enum's named cases make the intent visible at every
    `returnValue` site, and `_check_result_contract` then enforces
    that the only legal returns are the named cases.

    Graded ERROR + blocksCompile because the dispatcher's
    short-circuit semantics depend on the type being right. Strict
    mode treats this as a hard fail.
    """
    diagnostics: List[Diagnostic] = []
    # Build (middleware_op_name -> first binding-site SourceLine). One
    # binding per op is sufficient for the diagnostic's related-span
    # citation — if a middleware is bound to many routes, picking any
    # one of them is enough for the agent to trace back why the op is
    # held to the MiddlewareControl contract.
    middlewareOpToBindingLine: Dict[str, SourceLine] = {}
    for sourceLine in facts.base.lines:
        if (is_comment(sourceLine) or not sourceLine.tokens
                or sourceLine.verb != "routeMiddleware"
                or len(sourceLine.args) < 3):
            continue
        opName = sourceLine.args[2]
        if opName not in middlewareOpToBindingLine:
            middlewareOpToBindingLine[opName] = sourceLine

    for operationName, bindingLine in middlewareOpToBindingLine.items():
        operationFact = facts.base.operations.get(operationName)
        if operationFact is None:
            # SS4104 covers the missing-op case.
            continue
        outputLine: Optional[SourceLine] = None
        declaredOutputType = ""
        for sourceLine in operationFact.lines:
            if (is_comment(sourceLine) or not sourceLine.tokens
                    or sourceLine.verb != "output"
                    or len(sourceLine.args) < 2
                    or sourceLine.args[0] != operationName):
                continue
            outputLine = sourceLine
            # `output OP TYPE` or `output OP Result OK ERROR` — read
            # the OK type as the comparand. Middleware ops shouldn't
            # declare Result outputs (the dispatcher reads a raw i32),
            # but the rule still gets the right type either way.
            if sourceLine.args[1] == "Result" and len(sourceLine.args) >= 3:
                declaredOutputType = sourceLine.args[2]
            else:
                declaredOutputType = sourceLine.args[1]
            break
        if outputLine is None:
            # An op without an `output` line trips a different rule
            # (missing output contract); SS3610 only speaks to the
            # type-of-output question.
            continue
        if declaredOutputType == "MiddlewareControl":
            continue
        diagnostics.append(Diagnostic(
            tier=Tier.T1_SPEC,
            code="SS3610",
            kind="webserver.middlewareReturnNotMiddlewareControl",
            severity=Severity.ERROR,
            subjectName=operationName,
            subjectKind="operation",
            gapEdge="output.MiddlewareControl",
            intentSlogan=(
                f"middleware `{operationName}` returns `{declaredOutputType}`, "
                f"must return `MiddlewareControl`"
            ),
            primary=span_of_line(outputLine, "middlewareOutputDeclaration"),
            related=[span_of_line(bindingLine, "routeMiddlewareBinding")],
            invariantRule=(
                f"every operation bound via `routeMiddleware` must declare "
                f"`output {operationName} MiddlewareControl` so the "
                f"dispatcher's short-circuit semantics (0 → continue, "
                f"1 → skip handler; see sem_http_runtime.c's "
                f"SS_HTTP_MIDDLEWARE_* enum) are type-checked at the "
                f"return-value site. A bare `CSignedInt32` output erases "
                f"the named-case contract: a returnValue of `1` would "
                f"silently short-circuit the route handler even when the "
                f"author intended it as a failure sentinel."
            ),
            specAnchor="SYNTAX.md#MiddlewareControl",
            citations=narrative_citations_for_operation(facts, operationName),
            fixCandidates=[
                FixCandidate(
                    name="changeOutputTypeToMiddlewareControl",
                    shape=f"output {operationName} MiddlewareControl",
                    autoApplicable=True,
                    evidence=[span_of_line(outputLine, "currentOutputDeclaration")],
                ),
                FixCandidate(
                    name="returnContinueCaseAtAllReturnValueSites",
                    shape=(
                        f"# in `operation {operationName}` body:\n"
                        f"returnValue continueMiddlewareControl"
                    ),
                ),
                FixCandidate(
                    name="returnShortCircuitToSkipHandler",
                    shape=(
                        f"# in `operation {operationName}` body, when the\n"
                        f"# middleware decided to send the response itself:\n"
                        f"returnValue shortCircuitMiddlewareControl"
                    ),
                ),
            ],
            confidence=Confidence.HIGH,
            blocksCompile=True,
            effort=Effort.TRIVIAL,
            passProvenance="check_middleware_return_type_is_middleware_control",
            agentHint=(
                "the MiddlewareControl enum is auto-registered by semsc "
                "(no `enum MiddlewareControl` declaration needed in the "
                "source); just change the output type and use the named "
                "cases `continueMiddlewareControl` and "
                "`shortCircuitMiddlewareControl` at every returnValue"
            ),
        ))
    return diagnostics


def check_route_handler_input_names(facts: ExtendedFacts) -> List[Diagnostic]:
    """SS3609 — every operation reachable from a `route` or
    `routeMiddleware` binding MUST declare its `HttpRequest` input under
    the canonical name `request` and its `HttpResponse` input under the
    canonical name `response`. This is a HARD ABI rule, not a style
    convention — multiple SS36xx checks resolve the request/response
    slots by name in `arg <call> request <slot>` / `arg <call> response
    <slot>` lookups, and the dispatcher at semsc.py:2290 requires the
    handler signature to be exactly `[HttpRequest, HttpResponse,
    CSignedInt32]` positionally. A handler with `req`/`resp`/`r`/`rsp`
    compiles (the dispatcher binds by position) but every downstream
    name-based lookup breaks silently — SS3603's transitive-body walk,
    `narrative_citations_for_operation`, and any future agent reading
    the source all assume the canonical names.

    Severity is ERROR with `blocksCompile=True` because the
    consequences of a mismatch are silent: nothing else in the
    toolchain enforces the contract, and a successful compile + lint
    pass would be the only signal you get. The fix is a 1-token rename.

    The check pairs each `input HANDLER NAME HttpRequest` / `... HttpResponse`
    with its canonical name. Mismatches are flagged with:
    - the offending `input` line as primary span
    - the binding site (`route` row or `routeMiddleware` row) as a
      related span, so the agent sees which route makes this op a
      handler / middleware in the first place
    - the operation's narrative citations attached, so the rationale
      for the op's existence is in scope when reading the diagnostic
    - a `renameInputToCanonical` fix candidate with the exact
      replacement line
    """
    diagnostics: List[Diagnostic] = []
    canonicalNameByType: Dict[str, str] = {
        "HttpRequest": "request",
        "HttpResponse": "response",
    }
    # Build (op -> list of binding-site source lines) so the diagnostic
    # can cite WHERE the op got pulled into the route ABI. A reader of
    # the SS3609 diagnostic should see the route line that demands the
    # canonical names alongside the input line that violates them.
    bindingSitesByOp: Dict[str, List[SourceLine]] = {}
    for routeFact in facts.base.routes:
        bindingSitesByOp.setdefault(routeFact.handler, []).append(routeFact.line)
    for sourceLine in facts.base.lines:
        if (is_comment(sourceLine) or not sourceLine.tokens
                or sourceLine.verb != "routeMiddleware"
                or len(sourceLine.args) < 3):
            continue
        bindingSitesByOp.setdefault(sourceLine.args[2], []).append(sourceLine)

    for operationName in sorted(bindingSitesByOp.keys()):
        operationFact = facts.base.operations.get(operationName)
        if operationFact is None:
            # SS4104 catches the unresolved-handler case; nothing
            # actionable for SS3609 if the op doesn't exist at all.
            continue
        bindingSiteLines = bindingSitesByOp[operationName]
        for sourceLine in operationFact.lines:
            if (is_comment(sourceLine) or not sourceLine.tokens
                    or sourceLine.verb != "input"
                    or len(sourceLine.args) < 3):
                continue
            if sourceLine.args[0] != operationName:
                continue
            inputName = sourceLine.args[1]
            inputType = sourceLine.args[2]
            canonicalName = canonicalNameByType.get(inputType)
            if canonicalName is None or inputName == canonicalName:
                continue
            # Cite up to the first 3 binding sites so the diagnostic
            # stays bounded even on heavily-shared middleware. The
            # canonical-name violation is the same regardless of which
            # binding site you read; one is enough for an agent to
            # trace back, three is a hint that the op is widely reused.
            relatedSpans: List[Span] = [
                span_of_line(bindingLine, "routeBindingSite")
                for bindingLine in bindingSiteLines[:3]
            ]
            inputRoleHint = (
                "request slot" if inputType == "HttpRequest"
                else "response slot"
            )
            diagnostics.append(Diagnostic(
                tier=Tier.T1_SPEC,
                code="SS3609",
                kind="webserver.routeHandlerInputNameMismatch",
                severity=Severity.ERROR,
                subjectName=operationName,
                subjectKind="operation",
                gapEdge="input.canonicalName",
                intentSlogan=(
                    f"{inputRoleHint} named `{inputName}`, must be `{canonicalName}`"
                ),
                primary=span_of_line(sourceLine, "handlerInputDeclaration"),
                related=relatedSpans,
                invariantRule=(
                    f"the native HTTP ABI defined at SYNTAX.md#route requires "
                    f"every route-bound or middleware-bound operation to "
                    f"declare its `{inputType}` input under the exact name "
                    f"`{canonicalName}`. The dispatcher at semsc.py:2290 "
                    f"matches handlers positionally (`[HttpRequest, "
                    f"HttpResponse, CSignedInt32]`), but the linter and "
                    f"every other agent reading the source uses the "
                    f"canonical input names to resolve which slot is the "
                    f"request vs the response. A mismatch compiles and "
                    f"runs but silently breaks SS36xx's name-based lookups, "
                    f"so the rule is graded ERROR and blocks compile under "
                    f"--strict so the contract cannot drift unnoticed."
                ),
                specAnchor="SYNTAX.md#route",
                citations=narrative_citations_for_operation(facts, operationName),
                fixCandidates=[
                    FixCandidate(
                        name="renameInputToCanonical",
                        shape=f"input {operationName} {canonicalName} {inputType}",
                        autoApplicable=True,
                        evidence=[span_of_line(sourceLine, "currentDeclaration")],
                    ),
                ],
                confidence=Confidence.HIGH,
                blocksCompile=True,
                effort=Effort.TRIVIAL,
                passProvenance="check_route_handler_input_names",
                agentHint=(
                    f"`{inputName}` likely came from a different language's "
                    f"convention (Go `r`/`w`, Rust `req`/`res`, JS "
                    f"`req`/`resp`). The canonical AgentScript names are "
                    f"`request` and `response` — match them and every "
                    f"downstream `arg <call> {canonicalName} {canonicalName}` "
                    f"resolves cleanly without positional inference."
                ),
            ))
    return diagnostics


def check_main_file_must_exist(facts: ExtendedFacts) -> List[Diagnostic]:
    """SS3614 — every `mainFile PROJECT "PATH"` row in a build tape MUST
    reference a file that exists on disk (resolved relative to
    `sourceRoot PROJECT "ROOT_PATH"`, or to the build tape's own
    directory when sourceRoot is absent).

    This catches the rename-rot scenario: when the module file gets
    renamed (e.g. `http_api_gauntlet.sscript` → `main.sem`) and the
    `mainFile` row in `build.sem` isn't updated, semsc would silently
    fail later in the build OR — worse — `importModule` would resolve
    via the module registry and the `mainFile` row would become a
    decorative lie. The lint surfaces the mismatch BEFORE compile.

    Resolution rules (matching semsc.py's build-tape resolver):
      1. `mainFile httpApiGauntlet "main.sem"` is resolved relative to
         the directory of the build tape file.
      2. If `sourceRoot httpApiGauntlet "."` is declared, the file is
         resolved relative to (build-tape-dir / sourceRoot-path).
      3. The path is required to exist; the file's content is NOT
         parsed (that's a separate concern handled by the importModule
         lowering).

    Graded ERROR + blocksCompile=True because a missing main file is
    a hard build failure waiting to happen, and the diagnostic site is
    the canonical place to surface it (semsc's error would arrive
    later with a less actionable trace).
    """
    diagnostics: List[Diagnostic] = []
    sourceRootByProject: Dict[str, Tuple[str, SourceLine]] = {}
    mainFileRows: List[Tuple[str, str, SourceLine]] = []  # (project, path, line)
    for sourceLine in facts.base.lines:
        if (is_comment(sourceLine) or not sourceLine.tokens
                or len(sourceLine.args) < 2):
            continue
        if sourceLine.verb == "sourceRoot" and len(sourceLine.args) >= 2:
            sourceRootByProject[sourceLine.args[0]] = (sourceLine.args[1], sourceLine)
        elif sourceLine.verb == "mainFile" and len(sourceLine.args) >= 2:
            mainFileRows.append((sourceLine.args[0], sourceLine.args[1], sourceLine))

    if not mainFileRows:
        # Not a build tape (or one that simply omits mainFile — semsc
        # may still accept this for non-routed module-only files).
        return diagnostics

    buildTapeDir = Path(str(facts.base.path)).resolve().parent
    for projectName, declaredPath, sourceLine in mainFileRows:
        sourceRootEntry = sourceRootByProject.get(projectName)
        if sourceRootEntry is not None:
            sourceRootPath, _sourceRootLine = sourceRootEntry
            resolvedDir = (buildTapeDir / sourceRootPath).resolve()
        else:
            resolvedDir = buildTapeDir
        resolvedFile = (resolvedDir / declaredPath).resolve()
        if resolvedFile.exists() and resolvedFile.is_file():
            continue
        # Build the diagnostic. Show the declared path AND the resolved
        # absolute path so the agent doesn't have to redo the resolution
        # logic in its head.
        diagnostics.append(Diagnostic(
            tier=Tier.T1_SPEC,
            code="SS3614",
            kind="buildTape.mainFileMustExist",
            severity=Severity.ERROR,
            subjectName=declaredPath,
            subjectKind="mainFile",
            gapEdge="filesystem.exists",
            intentSlogan=(
                f"mainFile `{declaredPath}` does not exist on disk"
            ),
            primary=span_of_line(sourceLine, "mainFileDeclaration"),
            invariantRule=(
                f"`mainFile {projectName} \"{declaredPath}\"` requires the "
                f"referenced file to exist relative to "
                f"`sourceRoot {projectName} \"...\"` (or the build tape's "
                f"directory when no sourceRoot is declared). The resolver "
                f"looked at `{resolvedFile}` and found nothing. This is the "
                f"rename-rot failure mode: the module file was probably "
                f"renamed and the build tape's mainFile row wasn't updated "
                f"in lockstep."
            ),
            specAnchor="SYNTAX.md#mainFile",
            fixCandidates=[
                FixCandidate(
                    name="updateMainFileToActualName",
                    shape=(
                        f"# inspect `{resolvedDir}` for the real module "
                        f"filename and update the mainFile row:\n"
                        f"mainFile {projectName} \"<actual-filename>\""
                    ),
                ),
                FixCandidate(
                    name="restoreOrRenameModuleFile",
                    shape=(
                        f"# create or rename the module source so it "
                        f"matches the declared path:\n"
                        f"# mv <current-name> {resolvedFile.name}"
                    ),
                ),
                FixCandidate(
                    name="fixSourceRootIfWrongDirectory",
                    shape=(
                        f"# if the module is in a different folder, point "
                        f"sourceRoot at it:\n"
                        f"sourceRoot {projectName} \"<correct-source-dir>\""
                    ),
                ),
            ],
            confidence=Confidence.HIGH,
            blocksCompile=True,
            effort=Effort.TRIVIAL,
            passProvenance="check_main_file_must_exist",
            agentHint=(
                "build-tape paths are filesystem-relative; renaming a module "
                "source without updating the build tape's mainFile row is "
                "the canonical drift this rule catches. The diagnostic's "
                "`resolvedFile` shows exactly where the resolver looked."
            ),
        ))
    return diagnostics


def check_route_coverage_drift(facts: ExtendedFacts) -> List[Diagnostic]:
    """SS3604 — every declared route SHOULD have a matching
    `routeTimeout SERVER PATH BUDGET` and `routeMiddleware SERVER PATH MW`,
    OR an explicit per-path opt-out:
    `routeTimeoutOptOut SERVER PATH "rationale"` /
    `routeMiddlewareOptOut SERVER PATH "rationale"`.

    The native dispatcher accepts routes without timeouts or middleware
    bindings, but coverage drift is exactly the kind of silent gap the
    spec calls out: missing routeTimeout means the future preemptive
    runtime will dispatch the route without a budget; missing
    routeMiddleware means a route slipped past whatever cross-cutting
    contract (tracing, auth header stamp) the other routes share. Make
    the omission a declared choice instead of a quiet gap.
    """
    diagnostics: List[Diagnostic] = []
    routesPerServer: Dict[str, Dict[str, SourceLine]] = {}
    for routeFact in facts.base.routes:
        routesPerServer.setdefault(routeFact.server, {})[routeFact.path] = routeFact.line
    timeoutCoverage: Dict[Tuple[str, str], SourceLine] = {}
    middlewareCoverage: Dict[Tuple[str, str], SourceLine] = {}
    timeoutOptOuts: Dict[Tuple[str, str], SourceLine] = {}
    middlewareOptOuts: Dict[Tuple[str, str], SourceLine] = {}
    for sourceLine in facts.base.lines:
        if (is_comment(sourceLine) or not sourceLine.tokens
                or len(sourceLine.args) < 2):
            continue
        verb = sourceLine.verb
        if verb == "routeTimeout" and len(sourceLine.args) >= 3:
            timeoutCoverage[(sourceLine.args[0], sourceLine.args[1])] = sourceLine
        elif verb == "routeMiddleware" and len(sourceLine.args) >= 3:
            middlewareCoverage[(sourceLine.args[0], sourceLine.args[1])] = sourceLine
        elif verb == "routeTimeoutOptOut" and len(sourceLine.args) >= 2:
            timeoutOptOuts[(sourceLine.args[0], sourceLine.args[1])] = sourceLine
        elif verb == "routeMiddlewareOptOut" and len(sourceLine.args) >= 2:
            middlewareOptOuts[(sourceLine.args[0], sourceLine.args[1])] = sourceLine

    for serverName, pathsByName in routesPerServer.items():
        for routePath, routeLine in pathsByName.items():
            key = (serverName, routePath)
            if key not in timeoutCoverage and key not in timeoutOptOuts:
                diagnostics.append(Diagnostic(
                    tier=Tier.T3_REFINEMENT,
                    code="SS3604",
                    kind="webserver.routeTimeoutCoverageDrift",
                    severity=Severity.WARNING,
                    subjectName=routePath,
                    subjectKind="route",
                    gapEdge="routeTimeout",
                    intentSlogan=f"route `{routePath}` has no timeout coverage",
                    primary=span_of_line(routeLine, "routeDeclaration"),
                    invariantRule=(
                        "every declared `route SERVER METHOD PATH HANDLER` should "
                        "either have a matching `routeTimeout SERVER PATH BUDGET` "
                        "row OR an explicit `routeTimeoutOptOut SERVER PATH "
                        "\"rationale\"` so future preemptive-runtime coverage is "
                        "not a silent gap"
                    ),
                    specAnchor="SYNTAX.md#routeTimeout",
                    fixCandidates=[
                        FixCandidate(
                            name="addRouteTimeout",
                            shape=f"routeTimeout {serverName} \"{routePath}\" <yourTimeoutBudgetName>",
                        ),
                        FixCandidate(
                            name="declareRouteTimeoutOptOut",
                            shape=(
                                f"routeTimeoutOptOut {serverName} \"{routePath}\" "
                                f"\"<why this route has no timeout>\""
                            ),
                        ),
                    ],
                    confidence=Confidence.HIGH,
                    effort=Effort.TRIVIAL,
                    passProvenance="check_route_coverage_drift",
                    agentHint="the native runtime does not enforce route timeouts yet, but declaring them now lets a preemptive runtime inherit complete coverage without a sweep",
                ))
            if key not in middlewareCoverage and key not in middlewareOptOuts:
                diagnostics.append(Diagnostic(
                    tier=Tier.T3_REFINEMENT,
                    code="SS3604",
                    kind="webserver.routeMiddlewareCoverageDrift",
                    severity=Severity.WARNING,
                    subjectName=routePath,
                    subjectKind="route",
                    gapEdge="routeMiddleware",
                    intentSlogan=f"route `{routePath}` has no middleware coverage",
                    primary=span_of_line(routeLine, "routeDeclaration"),
                    invariantRule=(
                        "every declared `route SERVER METHOD PATH HANDLER` should "
                        "either have a matching `routeMiddleware SERVER PATH MW` "
                        "row OR an explicit `routeMiddlewareOptOut SERVER PATH "
                        "\"rationale\"` so cross-cutting middleware contracts "
                        "(tracing headers, auth checks, etc.) are not silently "
                        "skipped on the missed route"
                    ),
                    specAnchor="SYNTAX.md#routeMiddleware",
                    fixCandidates=[
                        FixCandidate(
                            name="addRouteMiddleware",
                            shape=f"routeMiddleware {serverName} \"{routePath}\" <yourMiddlewareOpName>",
                        ),
                        FixCandidate(
                            name="declareRouteMiddlewareOptOut",
                            shape=(
                                f"routeMiddlewareOptOut {serverName} \"{routePath}\" "
                                f"\"<why this route skips middleware (e.g., bare healthcheck)>\""
                            ),
                        ),
                    ],
                    confidence=Confidence.HIGH,
                    effort=Effort.TRIVIAL,
                    passProvenance="check_route_coverage_drift",
                    agentHint="dropping a route from the middleware list silently bypasses any cross-cutting contract the other routes share; opt out explicitly if that's the intent",
                ))
    return diagnostics


def check_legacy_null_body_marker(facts: ExtendedFacts) -> List[Diagnostic]:
    """SS3605 — a `warning OP "... null-body failure path ..."` line opts an
    operation out of SS3603 via a stringly-typed marker. This is the
    deprecated form; the canonical opt-out is
    `pinsNullBodyFailurePath OP "rationale"`.

    To avoid false-positives on warnings that *discuss* the contract
    (e.g., "do not switch this back to the null-body failure path"), the
    rule only fires when the marker is LOAD-BEARING — i.e., the operation
    has at least one nullable http.request* bind flowing into an
    http.response* body that would trip SS3603 if the marker were
    removed. A warning text that only references the contract for
    documentation purposes (because the op is actually guarded with
    pointer.isNull) is not flagged.
    """
    diagnostics: List[Diagnostic] = []
    # Reuse SS3603's machinery to know which ops are actually relying on
    # the marker. Build the set of ops that have unguarded nullable binds
    # passed to response body — those are the only ops where SS3605
    # would matter.
    responseBodyWriters = _collect_transitive_response_body_writers(facts)
    opsWithUnguardedNullableBind: Set[str] = set()
    for operationName, operationFact in facts.base.operations.items():
        callTargetsByCallName: Dict[str, str] = {
            sourceLine.args[0]: sourceLine.args[1]
            for sourceLine in operationFact.lines
            if (not is_comment(sourceLine) and sourceLine.tokens
                and sourceLine.verb == "call" and len(sourceLine.args) >= 2)
        }
        nullableBoundValueNames: Set[str] = set()
        for sourceLine in operationFact.lines:
            if (is_comment(sourceLine) or sourceLine.verb != "bind"
                    or len(sourceLine.args) < 3):
                continue
            if callTargetsByCallName.get(sourceLine.args[2]) in NULLABLE_HTTP_REQUEST_READS:
                nullableBoundValueNames.add(sourceLine.args[0])
        if not nullableBoundValueNames:
            continue
        guardedBoundValueNames: Set[str] = set()
        pointerIsNullCallNames: Set[str] = set()
        for sourceLine in operationFact.lines:
            if is_comment(sourceLine) or not sourceLine.tokens:
                continue
            verb = sourceLine.verb
            args = sourceLine.args
            if verb == "call" and len(args) >= 2 and args[1] == "pointer.isNull":
                pointerIsNullCallNames.add(args[0])
            elif (verb == "arg" and len(args) >= 3
                    and args[0] in pointerIsNullCallNames
                    and args[1] == "pointer"
                    and args[2] in nullableBoundValueNames):
                guardedBoundValueNames.add(args[2])
            elif (verb == "arg" and len(args) >= 3
                    and args[1] == "body"
                    and callTargetsByCallName.get(args[0]) in responseBodyWriters
                    and args[2] in nullableBoundValueNames
                    and args[2] not in guardedBoundValueNames):
                opsWithUnguardedNullableBind.add(operationName)
                break

    for operationName, operationFact in facts.base.operations.items():
        # The marker only matters if the op would have tripped SS3603 without it.
        if operationName not in opsWithUnguardedNullableBind:
            continue
        hasNewVerb = False
        legacyWarningLine: Optional[SourceLine] = None
        for sourceLine in operationFact.lines:
            if is_comment(sourceLine) or not sourceLine.tokens:
                continue
            if (sourceLine.verb == "pinsNullBodyFailurePath"
                    and sourceLine.args
                    and sourceLine.args[0] == operationName):
                hasNewVerb = True
            elif (sourceLine.verb == "warning"
                    and len(sourceLine.args) >= 2
                    and sourceLine.args[0] == operationName):
                warningText = " ".join(sourceLine.args[1:])
                if any(marker in warningText
                       for marker in LEGACY_HTTP_NULL_GUARD_OPT_OUT_MARKERS):
                    legacyWarningLine = sourceLine
        if legacyWarningLine is None or hasNewVerb:
            continue
        diagnostics.append(Diagnostic(
            tier=Tier.T4_STYLE,
            code="SS3605",
            kind="webserver.legacyNullBodyMarker",
            severity=Severity.WARNING,
            subjectName=operationName,
            subjectKind="operation",
            gapEdge="pinsNullBodyFailurePath",
            intentSlogan="legacy null-body opt-out via warning text",
            primary=span_of_line(legacyWarningLine, "legacyMarkerWarning"),
            invariantRule=(
                "the canonical SS3603 opt-out is "
                "`pinsNullBodyFailurePath OP \"rationale\"`; the stringly-"
                "typed `null-body failure path` marker inside `warning` text "
                "is still honored for one deprecation cycle but should be "
                "replaced with the explicit verb"
            ),
            specAnchor="SYNTAX.md#pinsNullBodyFailurePath",
            citations=narrative_citations_for_operation(facts, operationName),
            fixCandidates=[
                FixCandidate(
                    name="addPinsNullBodyFailurePathVerb",
                    shape=(
                        f"pinsNullBodyFailurePath {operationName} "
                        f"\"why this route deliberately exercises the adapter's "
                        f"null-body 500 path\""
                    ),
                ),
            ],
            confidence=Confidence.HIGH,
            effort=Effort.TRIVIAL,
            passProvenance="check_legacy_null_body_marker",
            agentHint=(
                "after adding the new verb, the warning line can keep its "
                "human-readable text but should drop the literal phrase "
                "`null-body failure path` to make the contract single-sourced"
            ),
        ))
    return diagnostics


def check_pins_null_body_failure_path_missing_rationale(facts: ExtendedFacts) -> List[Diagnostic]:
    """SS3606 — `pinsNullBodyFailurePath OP` without a rationale string is
    the form that's just as opaque as a bare ignore. Require a non-empty
    quoted rationale so the contract is human-readable AND machine-
    detectable, not just one or the other."""
    diagnostics: List[Diagnostic] = []
    for sourceLine in facts.base.lines:
        if (is_comment(sourceLine) or not sourceLine.tokens
                or sourceLine.verb != "pinsNullBodyFailurePath"
                or not sourceLine.args):
            continue
        operationName = sourceLine.args[0]
        rationaleText = " ".join(sourceLine.args[1:]).strip()
        if rationaleText:
            continue
        diagnostics.append(Diagnostic(
            tier=Tier.T3_REFINEMENT,
            code="SS3606",
            kind="webserver.pinsNullBodyFailurePathMissingRationale",
            severity=Severity.WARNING,
            subjectName=operationName,
            subjectKind="operation",
            gapEdge="rationaleText",
            intentSlogan="pinsNullBodyFailurePath needs a rationale",
            primary=span_of_line(sourceLine, "pinsVerbWithoutRationale"),
            invariantRule=(
                "`pinsNullBodyFailurePath OP \"rationale\"` requires a non-"
                "empty rationale string explaining WHY this route is "
                "intentionally exercising the adapter's null-body 500 path"
            ),
            specAnchor="SYNTAX.md#pinsNullBodyFailurePath",
            fixCandidates=[
                FixCandidate(
                    name="addRationaleString",
                    shape=(
                        f"pinsNullBodyFailurePath {operationName} "
                        f"\"<why this route deliberately pins the adapter's null-body 500 contract>\""
                    ),
                ),
            ],
            confidence=Confidence.HIGH,
            effort=Effort.TRIVIAL,
            passProvenance="check_pins_null_body_failure_path_missing_rationale",
            agentHint="the rationale is the operation's contract; a bare verb without it is no better than the legacy marker",
        ))
    return diagnostics


def check_rationale_call_references_known_call(facts: ExtendedFacts) -> List[Diagnostic]:
    """SS3608 — `rationale CALL "text"` must reference a call name that
    was declared earlier in the same operation. A rationale attached to
    a typoed or removed call name is dangling context — the lint surfaces
    it instead of letting it rot. Empty rationale text also trips: a
    bare `rationale callName` is the same magic as a `#` proximity
    comment with none of the explicit-binding benefit."""
    diagnostics: List[Diagnostic] = []
    for (operationName, callName), citation in facts.callRationales.items():
        operationFact = facts.base.operations.get(operationName)
        if operationFact is None:
            # SS4104 already covers the missing-op case.
            continue
        declaredCallNames: Set[str] = set()
        for sourceLine in operationFact.lines:
            if (is_comment(sourceLine) or not sourceLine.tokens
                    or sourceLine.verb != "call" or len(sourceLine.args) < 2):
                continue
            declaredCallNames.add(sourceLine.args[0])
        rationaleSpan = citation.span
        if callName not in declaredCallNames:
            diagnostics.append(Diagnostic(
                tier=Tier.T1_SPEC,
                code="SS3608",
                kind="webserver.rationaleReferencesUnknownCall",
                severity=Severity.ERROR,
                subjectName=callName,
                subjectKind="call",
                gapEdge="callDeclaration",
                intentSlogan=f"`rationale {callName}` references undeclared call",
                primary=Span(
                    path=rationaleSpan.path,
                    line=rationaleSpan.line,
                    column=rationaleSpan.column,
                    role="rationaleCallReference",
                ),
                invariantRule=(
                    f"`rationale {callName} \"…\"` must name a call declared "
                    f"earlier in operation `{operationName}`; dangling "
                    f"rationale rots when the call is renamed or removed"
                ),
                specAnchor="SYNTAX.md#rationale",
                fixCandidates=[
                    FixCandidate(
                        name="correctCallName",
                        shape=f"# verify `{callName}` against the call names in operation `{operationName}`",
                    ),
                    FixCandidate(
                        name="removeOrphanRationale",
                        shape=f"# remove `rationale {callName} \"…\"` if the call no longer exists",
                    ),
                ],
                confidence=Confidence.HIGH,
                blocksCompile=True,
                effort=Effort.TRIVIAL,
                passProvenance="check_rationale_call_references_known_call",
                agentHint="orphan rationale is one of the strongest signals that a refactor moved code but left context behind",
            ))
            continue
        if not citation.text:
            diagnostics.append(Diagnostic(
                tier=Tier.T3_REFINEMENT,
                code="SS3608",
                kind="webserver.rationaleMissingText",
                severity=Severity.WARNING,
                subjectName=callName,
                subjectKind="call",
                gapEdge="rationaleText",
                intentSlogan=f"`rationale {callName}` has no rationale text",
                primary=Span(
                    path=rationaleSpan.path,
                    line=rationaleSpan.line,
                    column=rationaleSpan.column,
                    role="rationaleVerbWithoutText",
                ),
                invariantRule=(
                    "`rationale CALL \"text\"` requires a non-empty rationale "
                    "string; a bare `rationale callName` is no better than the "
                    "proximity-based `# rationale:` comment it was meant to "
                    "replace"
                ),
                specAnchor="SYNTAX.md#rationale",
                fixCandidates=[
                    FixCandidate(
                        name="addRationaleText",
                        shape=f"rationale {callName} \"<why this call is shaped this way>\"",
                    ),
                ],
                confidence=Confidence.HIGH,
                effort=Effort.TRIVIAL,
                passProvenance="check_rationale_call_references_known_call",
                agentHint="the rationale text IS the value-add; without it, prefer the `# rationale:` comment form",
            ))
    return diagnostics


def check_void_output_should_use_return_void(facts: ExtendedFacts) -> List[Diagnostic]:
    """SS3612 — an operation declared `output OP Void` (or `output OP
    CVoid`) should terminate with `returnVoid`, not `returnValue NAME`.

    The user-op ABI returns i32 even for Void outputs (see
    `_operation_output_contract` and the `Void → I32` mapping), so a
    `returnValue someI32Sentinel` form compiles — but the source is then
    lying about its semantic contract: it says "no caller-actionable
    value" at the output line and "here's an integer sentinel" at the
    return site. A future agent reading either half in isolation has
    to know about the ABI quirk to reconcile them.

    `returnVoid` (added in this iteration of the spec) is the explicit
    form: the source matches the semantic contract; codegen still emits
    the i32-zero sentinel under the hood, but the reader doesn't need
    to know that.

    Fires WARNING (not ERROR) because the legacy form compiles and
    produces correct runtime behavior — the issue is source-level
    honesty, not a contract violation. Strict mode promotes it to
    fatal so a CI pipeline can refuse to ship Void-output ops that
    return integer sentinels.
    """
    diagnostics: List[Diagnostic] = []
    for operationName, operationFact in facts.base.operations.items():
        outputLine: Optional[SourceLine] = None
        outputType = ""
        for sourceLine in operationFact.lines:
            if (is_comment(sourceLine) or not sourceLine.tokens
                    or sourceLine.verb != "output"
                    or len(sourceLine.args) < 2
                    or sourceLine.args[0] != operationName):
                continue
            outputLine = sourceLine
            outputType = sourceLine.args[1]
            break
        if outputType not in ("Void", "CVoid"):
            continue
        returnValueLine: Optional[SourceLine] = None
        returnValueName = ""
        for sourceLine in operationFact.lines:
            if (is_comment(sourceLine) or not sourceLine.tokens
                    or sourceLine.verb != "returnValue"
                    or not sourceLine.args):
                continue
            returnValueLine = sourceLine
            returnValueName = sourceLine.args[0]
            break
        if returnValueLine is None:
            continue
        diagnostics.append(Diagnostic(
            tier=Tier.T3_REFINEMENT,
            code="SS3612",
            kind="returnContract.voidReturnValueShouldBeReturnVoid",
            severity=Severity.WARNING,
            subjectName=operationName,
            subjectKind="operation",
            gapEdge="returnVoid",
            intentSlogan=(
                f"`output {operationName} {outputType}` should pair with "
                f"`returnVoid`, not `returnValue {returnValueName}`"
            ),
            primary=span_of_line(returnValueLine, "returnValueAtVoidOutput"),
            related=[span_of_line(outputLine, "voidOutputDeclaration")] if outputLine else [],
            invariantRule=(
                f"operations declared `output OP {outputType}` must end with "
                f"`returnVoid` so the source matches the semantic contract. "
                f"`returnValue NAME` is the form for typed outputs; using it "
                f"on a Void-output op leaks the user-op ABI's i32 zero "
                f"sentinel into the source, which a future agent then has "
                f"to recognise as a Void-ABI quirk instead of as a real "
                f"value being returned."
            ),
            specAnchor="SYNTAX.md#returnVoid",
            citations=narrative_citations_for_operation(facts, operationName),
            fixCandidates=[
                FixCandidate(
                    name="replaceReturnValueWithReturnVoid",
                    shape="returnVoid",
                    autoApplicable=True,
                    evidence=[span_of_line(returnValueLine, "currentReturnValue")],
                ),
                FixCandidate(
                    name="changeOutputToTypedValue",
                    shape=(
                        f"# if `{operationName}` actually produces a "
                        f"caller-actionable value, change the output declaration:\n"
                        f"output {operationName} <ConcreteType>"
                    ),
                ),
            ],
            confidence=Confidence.HIGH,
            effort=Effort.TRIVIAL,
            passProvenance="check_void_output_should_use_return_void",
            agentHint=(
                "if `returnValue <name>` is referencing a `0` const, the "
                "const itself is also dead code after this fix — delete "
                "the storage line at the same time so the source stays clean"
            ),
        ))
    return diagnostics


# Regex matching `<filename>.<py|c|h>:<line-number>` and `line <number>` and
# `:<number>-<number>` patterns. These are the brittle line-references the
# external review flagged: rule IDs (SS3603) are stable, line numbers are
# not. The regex deliberately excludes URL fragment anchors (#L123 in a
# code-host link) since those are versioned and stable; it targets the
# bare path:line shape that drifts on every edit.
import re as _re_for_narrative
_NARRATIVE_LINE_NUMBER_PATTERN = _re_for_narrative.compile(
    r"\b[A-Za-z_][A-Za-z0-9_]*\.(?:py|c|h|cpp|rs|go|js|ts|sscript|sem)"
    r":\d+(?:[-–]\d+)?\b"
    r"|\bline\s+\d+\b"
)


def check_narrative_references_line_number(facts: ExtendedFacts) -> List[Diagnostic]:
    """SS3613 — `purpose` / `invariant` / `warning` / `rationale` text
    that contains `<filename>:<line>` or `line <N>` patterns will rot
    the next time the referenced file is edited. Rule IDs (SS3603),
    function names (`_check_route_methods`), and grep-anchors are
    stable; line numbers are not.

    This is the prevention rule for the external-review finding:
    several narrative lines in the gauntlet sscript referenced
    `semsc.py:3674` and `test_http_api_gauntlet.py:273-279`, and both
    references would silently drift the moment those files got an
    insertion. Replacing the references with function names + rule
    IDs makes the citation stable.

    Fires WARNING — the narrative still parses, the code still
    compiles, the only loss is durability. Strict mode promotes to
    fatal for projects that want narrative durability enforced.
    """
    diagnostics: List[Diagnostic] = []
    # Track every narrative-bearing line. Per SYNTAX.md, the narrative
    # verbs are purpose / invariant / warning / guarantee / failure /
    # security / timing / observability + the `rationale CALL` verb +
    # `# rationale:` comments. The check looks at args[1:] joined
    # because the parser stores quoted text as one token per arg.
    for sourceLine in facts.base.lines:
        if (is_comment(sourceLine) or not sourceLine.tokens
                or len(sourceLine.args) < 2):
            continue
        verb = sourceLine.verb
        if verb not in NARRATIVE_EDGES and verb != "rationale":
            continue
        # First arg is the owning subject (op / call name); the rest is
        # the narrative text. Join with space because semlint.py's
        # tokenizer keeps each whitespace-separated token (and quoted
        # strings as single tokens).
        narrativeText = " ".join(sourceLine.args[1:])
        match = _NARRATIVE_LINE_NUMBER_PATTERN.search(narrativeText)
        if match is None:
            continue
        offendingReference = match.group(0)
        subjectName = sourceLine.args[0]
        diagnostics.append(Diagnostic(
            tier=Tier.T4_STYLE,
            code="SS3613",
            kind="narrative.referencesLineNumber",
            severity=Severity.WARNING,
            subjectName=subjectName,
            subjectKind=verb,
            gapEdge="stableIdentifier",
            intentSlogan=f"`{verb}` text cites `{offendingReference}` (will drift)",
            primary=span_of_line(sourceLine, f"{verb}TextWithLineNumber"),
            invariantRule=(
                f"narrative attachments (`purpose` / `invariant` / `warning` / "
                f"`guarantee` / `failure` / `security` / `timing` / "
                f"`observability` / `rationale`) should cite STABLE "
                f"identifiers: function names, rule IDs (SS3603), spec "
                f"anchors (SYNTAX.md#routeMiddleware), or grep-strings. "
                f"Line numbers drift the moment the referenced file gets "
                f"an insertion — your narrative says `{offendingReference}` "
                f"and a future agent will trust it to find the wrong line."
            ),
            specAnchor="docs/optimization-guide.md#cross-document-references",
            fixCandidates=[
                FixCandidate(
                    name="replaceLineNumberWithFunctionName",
                    shape=(
                        f"# replace `{offendingReference}` in this narrative "
                        f"line with a function name or rule ID — e.g. "
                        f"`semsc.py:_check_route_methods` or `SS3601`"
                    ),
                ),
                FixCandidate(
                    name="replaceWithGrepAnchor",
                    shape=(
                        f"# replace `{offendingReference}` with a quoted "
                        f"string that uniquely greps to the cited code"
                    ),
                ),
            ],
            confidence=Confidence.HIGH,
            effort=Effort.TRIVIAL,
            passProvenance="check_narrative_references_line_number",
            agentHint=(
                "rule IDs (SS36xx) are pinned in this module's CHECKERS list "
                "and never renumber once shipped; function names rename "
                "rarely and break loudly when they do — both are better "
                "anchors than `:NNN` line numbers"
            ),
        ))
    return diagnostics


MODULE_EXPORT_VERBS: frozenset = frozenset({
    "exportType",
    "exportError",
    "exportOperation",
    "exportCapability",
    "exportConstant",
})


EXPORT_VERB_DECLARATION_KIND: Dict[str, str] = {
    "exportType": "type",
    "exportError": "error",
    "exportOperation": "operation",
    "exportCapability": "capability",
    "exportConstant": "constant",
}


BUILD_TAPE_PROJECT_VERBS: Set[str] = {
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
}

BUILD_TAPE_SINGLETON_VERBS: Set[str] = {
    "modulePath", "languageVersion", "projectVersion", "projectLicense",
    "sourceRoot", "mainFile", "mainOperation", "targetRuntime",
    "buildProfile", "runtimeChecks", "persistLlvmIr", "nativeOutput",
    "keepResources", "resourcesDir", "nativeHttpHost", "nativeHttpPort",
    "docsOutput", "optLevel", "emitLlvmIr", "llvmIrOutput",
    "emitOptimizedLlvmIr", "optimizedLlvmIrOutput",
    "buildDir", "buildRoot", "buildFolderName", "comptimeOperation",
    "cpuBaseline", "cpuTune", "cpuFeatureCheck",
    "dependencyCache", "dependencyLock",
}

BUILD_TAPE_REQUIRED_VERBS: Set[str] = {
    "modulePath", "languageVersion", "projectVersion", "projectLicense",
    "sourceRoot", "targetRuntime", "buildProfile", "runtimeChecks",
    "persistLlvmIr", "optLevel",
}

BUILD_TAPE_CHOICES: Dict[str, Set[str]] = {
    "targetRuntime": {"nativeExe", "webServer", "library", "windowsGui"},
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

CPU_FEATURE_STATES: Set[str] = {"on", "off"}

BUILD_TAPE_PATH_VERBS: Set[str] = {
    "sourceRoot", "mainFile", "testPattern", "testRoot", "nativeOutput",
    "resourcesDir", "docsOutput", "llvmIrOutput",
    "optimizedLlvmIrOutput", "buildDir", "buildRoot",
    "dependencyCache", "dependencyLock",
}

BUILD_TAPE_MIN_ARITY: Dict[str, int] = {
    "dependency": 4,
    "dependencySource": 3,
    "dependencyFetch": 4,
    "dependencyIntegrity": 3,
    "dependencyCache": 2,
    "dependencyLock": 2,
    "cpuFeature": 3,
    "formatterSetting": 3,
    "linterSetting": 3,
    "registerModule": 3,
}

BUILD_TAPE_ALLOWED_NON_PROJECT_VERBS: Set[str] = {
    "buildProject", "project", "target", "runtime", "entry", "importModule",
    "moduleFolder",
    "version", "publisher", "description", "copyright", "productName",
    "internalName", "originalFilename", "trademark", "comments", "metadata",
    "iconRoleDefinition", "icon", "iconRole", "iconPurpose",
    "iconImage", "iconImageGroup", "iconImagePath", "iconImageFormat",
    "iconImageWidth", "iconImageHeight", "iconImageScale",
    "iconImageDepth", "iconImagePlatform", "iconImagePurpose",
}


REMOTE_DEPENDENCY_KINDS: Set[str] = {"github", "http"}
DEPENDENCY_SOURCE_KINDS: Set[str] = {"local", "path", "github", "http"}
DEPENDENCY_FETCH_KINDS: Set[str] = {"github", "http"}


def _is_https_url(value: str) -> bool:
    return value.startswith("https://") and " " not in value and len(value) > len("https://")


def _github_owner_repo_is_valid(value: str) -> bool:
    if value.startswith("github.com/"):
        value = value[len("github.com/"):]
    parts = value.split("/")
    return len(parts) >= 2 and all(parts[:2]) and not any(part in {".", ".."} for part in parts[:2])


def _dependency_source_kind(args: Sequence[str]) -> Tuple[str, Sequence[str]]:
    if len(args) >= 4:
        return args[2], args[3:]
    if len(args) >= 3:
        sourceText = args[2]
        if sourceText.startswith(("https://", "http://")):
            return "http", args[2:3]
        if sourceText.startswith("github.com/"):
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


def _collect_declared_export_symbols(facts: ExtendedFacts) -> Dict[str, Set[str]]:
    declared: Dict[str, Set[str]] = {
        "type": set(),
        "error": set(),
        "operation": set(facts.base.operations.keys()),
        "capability": set(facts.base.capabilities.keys()),
        "constant": set(facts.base.consts.keys()),
    }
    for sourceLine in facts.base.lines:
        if not sourceLine.tokens or is_comment(sourceLine):
            continue
        verb = sourceLine.verb
        args = sourceLine.args
        if not args:
            continue
        if verb in {
            "type",
            "enum",
            "record",
            "listType",
            "arrayType",
            "sliceType",
            "smallListType",
            "mapType",
        }:
            declared["type"].add(args[0])
        elif verb == "error":
            declared["error"].add(args[0])
        elif verb == "capability":
            declared["capability"].add(args[0])
        elif verb in {"const", "domainLiteral", "literal"}:
            declared["constant"].add(args[0])
        elif verb in {"storage", "sharedState"} and len(args) >= 3:
            declared["constant"].add(args[2])
    return declared


def _collect_constant_declarations(
    facts: ExtendedFacts,
) -> Dict[str, ConstantDeclarationFact]:
    declarations: Dict[str, ConstantDeclarationFact] = {}
    for name, constFact in facts.base.consts.items():
        declarations[name] = ConstantDeclarationFact(
            name=name,
            line=constFact.line,
            typeName=constFact.type_name,
            value=constFact.value,
            declarationVerb="const",
        )
    for sourceLine in facts.base.lines:
        if not sourceLine.tokens or is_comment(sourceLine):
            continue
        verb = sourceLine.verb
        args = sourceLine.args
        if verb == "domainLiteral" and len(args) >= 3:
            declarations[args[0]] = ConstantDeclarationFact(
                name=args[0],
                line=sourceLine,
                typeName=args[1],
                value=args[2],
                declarationVerb=verb,
            )
        elif verb == "literal" and len(args) >= 3:
            declarations[args[0]] = ConstantDeclarationFact(
                name=args[0],
                line=sourceLine,
                typeName=args[1],
                value=args[2],
                declarationVerb=verb,
            )
        elif verb == "storage" and len(args) >= 4:
            declarations[args[2]] = ConstantDeclarationFact(
                name=args[2],
                line=sourceLine,
                typeName=args[3],
                value=args[4] if len(args) >= 5 else "",
                scope=args[0],
                mutability=args[1],
                declarationVerb=verb,
            )
        elif verb == "sharedState" and len(args) >= 4:
            declarations[args[2]] = ConstantDeclarationFact(
                name=args[2],
                line=sourceLine,
                typeName=args[3],
                value=args[4] if len(args) >= 5 else "",
                scope=f"sharedState.{args[0]}",
                mutability=args[1],
                declarationVerb=verb,
            )
    return declarations


def _export_rows(
    facts: ExtendedFacts,
) -> List[Tuple[str, str, str, SourceLine]]:
    rows: List[Tuple[str, str, str, SourceLine]] = []
    for sourceLine in facts.base.lines:
        if (not sourceLine.tokens or is_comment(sourceLine)
                or sourceLine.verb not in MODULE_EXPORT_VERBS
                or len(sourceLine.args) < 2):
            continue
        rows.append((
            sourceLine.verb,
            sourceLine.args[0],
            sourceLine.args[1],
            sourceLine,
        ))
    return rows


def build_export_contract_tape(
    facts: ExtendedFacts,
) -> List[ExportContractEdge]:
    """Extract the public module contract carried by explicit export rows.

    This is intentionally a tape, not a nested object graph: consumers can
    stream it, diff it, and preserve every source row that contributed to the
    public API. Symbols without an export row are absent by design.
    """
    edges: List[ExportContractEdge] = []
    constantDeclarations = _collect_constant_declarations(facts)

    def add_edge(
        moduleName: str,
        exportVerb: str,
        symbolName: str,
        edgeKind: str,
        values: Sequence[str],
        line: SourceLine,
    ) -> None:
        edges.append(ExportContractEdge(
            moduleName=moduleName,
            exportVerb=exportVerb,
            symbolName=symbolName,
            edgeKind=edgeKind,
            values=tuple(values),
            line=line,
        ))

    for exportVerb, moduleName, symbolName, exportLine in _export_rows(facts):
        add_edge(moduleName, exportVerb, symbolName, "export.row",
                 [exportVerb, moduleName, symbolName], exportLine)

        if exportVerb == "exportOperation":
            operation = facts.base.operations.get(symbolName)
            if operation is None:
                continue
            for opLine in operation.lines:
                if not opLine.tokens or is_comment(opLine):
                    continue
                verb = opLine.verb
                args = opLine.args
                if verb in {
                    "input", "output", "effect", "useCapability", "authority",
                    "failure", "async", "timing", "memory", "memoryHeap",
                    "memoryStackLimit", "timeout", "cancelOn", "purpose",
                    "invariant", "warning", "guarantee", "security",
                    "observability",
                }:
                    add_edge(moduleName, exportVerb, symbolName,
                             f"operation.{verb}", args, opLine)
                    if (verb == "output" and len(args) >= 4
                            and args[1] == "Result"):
                        failureType = args[3]
                        add_edge(moduleName, exportVerb, symbolName,
                                 "operation.failureType", [failureType], opLine)
                        for (errorName, caseName), caseFact in facts.errorCases.items():
                            if errorName == failureType:
                                add_edge(moduleName, exportVerb, symbolName,
                                         "operation.failureCase",
                                         [errorName, caseName], caseFact.line)
            continue

        if exportVerb == "exportType":
            for sourceLine in facts.base.lines:
                if not sourceLine.tokens or is_comment(sourceLine):
                    continue
                verb = sourceLine.verb
                args = sourceLine.args
                if not args:
                    continue
                if verb == "type" and args[0] == symbolName:
                    add_edge(moduleName, exportVerb, symbolName,
                             "type.alias", args, sourceLine)
                elif verb == "record" and args[0] == symbolName:
                    add_edge(moduleName, exportVerb, symbolName,
                             "type.record", args, sourceLine)
                elif (verb in {"field", "recordLayout", "recordAlign"}
                      and args[0] == symbolName):
                    add_edge(moduleName, exportVerb, symbolName,
                             f"type.{verb}", args, sourceLine)
                elif verb == "enum" and args[0] == symbolName:
                    add_edge(moduleName, exportVerb, symbolName,
                             "type.enum", args, sourceLine)
                elif verb == "enumCase" and args[0] == symbolName:
                    add_edge(moduleName, exportVerb, symbolName,
                             "type.enumCase", args, sourceLine)
                elif (verb in {"invariant", "warning", "purpose"}
                      and args[0] == symbolName):
                    add_edge(moduleName, exportVerb, symbolName,
                             f"type.{verb}", args, sourceLine)
            continue

        if exportVerb == "exportError":
            for (errorName, caseName), caseFact in facts.errorCases.items():
                if errorName == symbolName:
                    add_edge(moduleName, exportVerb, symbolName,
                             "error.case", [errorName, caseName], caseFact.line)
            for sourceLine in facts.base.lines:
                if (sourceLine.verb == "error" and sourceLine.args
                        and sourceLine.args[0] == symbolName):
                    add_edge(moduleName, exportVerb, symbolName,
                             "error.declaration", sourceLine.args, sourceLine)
            continue

        if exportVerb == "exportCapability":
            capability = facts.base.capabilities.get(symbolName)
            if capability is not None:
                add_edge(moduleName, exportVerb, symbolName,
                         "capability.authority",
                         [capability.effect_path, capability.access],
                         capability.line)
            continue

        if exportVerb == "exportConstant":
            declaration = constantDeclarations.get(symbolName)
            if declaration is not None:
                add_edge(moduleName, exportVerb, symbolName,
                         "constant.value",
                         [
                             declaration.typeName,
                             declaration.value,
                             declaration.scope,
                             declaration.mutability,
                             declaration.declarationVerb,
                         ],
                         declaration.line)
                for sourceLine in facts.base.lines:
                    if (sourceLine.args and sourceLine.args[0] == symbolName
                            and sourceLine.verb in {
                                "literalEncoding", "literalSource",
                                "literalDigest", "literalTrust",
                            }):
                        add_edge(moduleName, exportVerb, symbolName,
                                 f"constant.{sourceLine.verb}",
                                 sourceLine.args, sourceLine)

    return edges


def _exported_symbols_by_kind(
    facts: ExtendedFacts,
) -> Dict[str, Set[str]]:
    exported: Dict[str, Set[str]] = {
        "type": set(),
        "error": set(),
        "operation": set(),
        "capability": set(),
        "constant": set(),
    }
    for exportVerb, _moduleName, symbolName, _line in _export_rows(facts):
        exportKind = EXPORT_VERB_DECLARATION_KIND.get(exportVerb)
        if exportKind is not None:
            exported.setdefault(exportKind, set()).add(symbolName)
    return exported


def _is_build_tape(facts: ExtendedFacts) -> bool:
    return any(
        line.verb in {"buildProject", "registerModule"}
        for line in facts.base.lines
        if line.tokens and not is_comment(line)
    )


def _build_tape_diagnostic(
    sourceLine: SourceLine,
    code: str,
    kind: str,
    subjectName: str,
    subjectKind: str,
    gapEdge: str,
    intentSlogan: str,
    invariantRule: str,
    fixShape: str,
) -> Diagnostic:
    return Diagnostic(
        tier=Tier.T1_SPEC,
        code=code,
        kind=kind,
        severity=Severity.ERROR,
        subjectName=subjectName,
        subjectKind=subjectKind,
        gapEdge=gapEdge,
        intentSlogan=intentSlogan,
        primary=span_of_line(sourceLine, "buildTapeSchema"),
        invariantRule=invariantRule,
        specAnchor="docs/language/project-layout-build-sem.md#buildsem-schema-reference",
        fixCandidates=[
            FixCandidate(name="repairBuildTapeRow", shape=fixShape),
        ],
        confidence=Confidence.HIGH,
        blocksCompile=True,
        effort=Effort.TRIVIAL,
        passProvenance="check_project_build_tape_schema",
        agentHint=(
            "build.sem is the single project contract; repair the row "
            "instead of compensating in module source files"
        ),
    )


def _check_dependency_build_rows(
    facts: ExtendedFacts,
    projectName: str,
) -> List[Diagnostic]:
    diagnostics: List[Diagnostic] = []
    declaredDependencies: Dict[str, SourceLine] = {}
    sourceRows: Dict[str, List[Tuple[SourceLine, str]]] = {}
    fetchRows: Dict[str, List[Tuple[SourceLine, str]]] = {}
    integrityRows: Dict[str, SourceLine] = {}
    cacheRows: List[SourceLine] = []
    lockRows: List[SourceLine] = []

    def add_dependency_diag(
        sourceLine: SourceLine,
        code: str,
        kind: str,
        subjectName: str,
        subjectKind: str,
        gapEdge: str,
        intentSlogan: str,
        invariantRule: str,
        fixShape: str,
        severity: Severity = Severity.WARNING,
        blocksCompile: bool = False,
    ) -> None:
        diagnostics.append(Diagnostic(
            tier=Tier.T1_SPEC if severity == Severity.ERROR else Tier.T3_REFINEMENT,
            code=code,
            kind=kind,
            severity=severity,
            subjectName=subjectName,
            subjectKind=subjectKind,
            gapEdge=gapEdge,
            intentSlogan=intentSlogan,
            primary=span_of_line(sourceLine, "dependencyBuildRow"),
            invariantRule=invariantRule,
            specAnchor="docs/language/project-layout-build-sem.md#dependency-fetch-cache-and-lock-rows",
            fixCandidates=[FixCandidate(name="repairDependencyRow", shape=fixShape)],
            confidence=Confidence.HIGH,
            blocksCompile=blocksCompile,
            effort=Effort.LOCAL,
            passProvenance="check_project_build_tape_schema",
            agentHint=(
                "dependency fetch rows are build-time authority edges; keep "
                "the alias, source kind, cache, lock, and integrity rows "
                "source-located in build.sem"
            ),
        ))

    for sourceLine in facts.base.lines:
        if not sourceLine.tokens or is_comment(sourceLine):
            continue
        verb = sourceLine.verb
        args = sourceLine.args
        if verb not in {
            "dependency", "dependencySource", "dependencyFetch",
            "dependencyCache", "dependencyLock", "dependencyIntegrity",
        }:
            continue
        if not args or args[0] != projectName:
            continue
        if verb == "dependency" and len(args) >= 4:
            alias = args[1]
            previous = declaredDependencies.get(alias)
            if previous is not None:
                add_dependency_diag(
                    sourceLine,
                    "SS2550",
                    "buildTape.dependencyAliasCollision",
                    alias,
                    "dependencyAlias",
                    "uniqueDependencyAlias",
                    "dependency alias is declared more than once",
                    "Dependency aliases key cache folders, lock rows, imports, and diagnostics. Reusing one alias creates an ambiguous module authority edge.",
                    f"dependency {projectName} {alias}Renamed <modulePath> <version-or-ref>",
                    severity=Severity.ERROR,
                    blocksCompile=True,
                )
            else:
                declaredDependencies[alias] = sourceLine
        elif verb == "dependencySource" and len(args) >= 3:
            alias = args[1]
            kind, payload = _dependency_source_kind(args)
            sourceRows.setdefault(alias, []).append((sourceLine, kind))
            if kind not in DEPENDENCY_SOURCE_KINDS:
                add_dependency_diag(
                    sourceLine,
                    "SS2552",
                    "buildTape.dependencySourceKind",
                    kind,
                    "dependencySource",
                    "closedDependencySourceKind",
                    "dependency source kind is not supported",
                    "`dependencySource PROJECT ALIAS KIND ...` accepts local, path, github, or http. Legacy rows infer kind from SOURCE_TEXT.",
                    f"dependencySource {projectName} {alias} github owner/repo",
                    severity=Severity.ERROR,
                    blocksCompile=True,
                )
            elif kind == "http":
                url = payload[0] if payload else ""
                if not _is_https_url(url):
                    add_dependency_diag(
                        sourceLine,
                        "SS2552",
                        "buildTape.dependencyInsecureHttpSource",
                        alias,
                        "dependencySource",
                        "httpsDependencySource",
                        "HTTP dependency sources must use https",
                        "Remote dependency source rows are executable supply-chain inputs. Plain http is rejected so fetched source cannot be silently rewritten in transit.",
                        f"dependencySource {projectName} {alias} http \"https://example.com/archive.tar.gz\"",
                        severity=Severity.ERROR,
                        blocksCompile=True,
                    )
            elif kind == "github":
                repo = payload[0] if payload else ""
                if not _github_owner_repo_is_valid(repo):
                    add_dependency_diag(
                        sourceLine,
                        "SS2552",
                        "buildTape.dependencyGithubSourceShape",
                        alias,
                        "dependencySource",
                        "githubOwnerRepo",
                        "GitHub dependency source must name owner/repo",
                        "`dependencySource PROJECT ALIAS github OWNER/REPO [REF]` keeps the provider identity parseable for cache and lock tooling.",
                        f"dependencySource {projectName} {alias} github monstercameron/SemanticScript main",
                        severity=Severity.ERROR,
                        blocksCompile=True,
                    )
        elif verb == "dependencyFetch" and len(args) >= 4:
            alias = args[1]
            kind = args[2]
            fetchRows.setdefault(alias, []).append((sourceLine, kind))
            if kind not in DEPENDENCY_FETCH_KINDS:
                add_dependency_diag(
                    sourceLine,
                    "SS2552",
                    "buildTape.dependencyFetchKind",
                    kind,
                    "dependencyFetch",
                    "closedDependencyFetchKind",
                    "dependency fetch kind is not supported",
                    "`dependencyFetch` is currently intentionally narrow: github or http. Add new fetch kinds only with cache and lock semantics.",
                    f"dependencyFetch {projectName} {alias} github owner/repo v1.0.0",
                    severity=Severity.ERROR,
                    blocksCompile=True,
                )
            elif kind == "http":
                url = args[3] if len(args) >= 4 else ""
                if not _is_https_url(url):
                    add_dependency_diag(
                        sourceLine,
                        "SS2552",
                        "buildTape.dependencyInsecureHttpFetch",
                        alias,
                        "dependencyFetch",
                        "httpsDependencyFetch",
                        "HTTP dependency fetches must use https",
                        "Remote dependency fetches are supply-chain inputs. Plain http is rejected before any future fetcher performs network IO.",
                        f"dependencyFetch {projectName} {alias} http \"https://example.com/archive.tar.gz\"",
                        severity=Severity.ERROR,
                        blocksCompile=True,
                    )
            elif kind == "github":
                repo = args[3] if len(args) >= 4 else ""
                ref = args[4] if len(args) >= 5 else ""
                if not _github_owner_repo_is_valid(repo) or not ref:
                    add_dependency_diag(
                        sourceLine,
                        "SS2552",
                        "buildTape.dependencyGithubFetchShape",
                        alias,
                        "dependencyFetch",
                        "githubOwnerRepoRef",
                        "GitHub dependency fetches must name owner/repo and ref",
                        "`dependencyFetch PROJECT ALIAS github OWNER/REPO REF` gives the future fetcher a stable cache key and gives the lock tape a concrete requested ref.",
                        f"dependencyFetch {projectName} {alias} github monstercameron/SemanticScript main",
                        severity=Severity.ERROR,
                        blocksCompile=True,
                    )
        elif verb == "dependencyIntegrity" and len(args) >= 3:
            alias = args[1]
            integrityRows[alias] = sourceLine
            if not _dependency_integrity_is_strong(args[2]):
                add_dependency_diag(
                    sourceLine,
                    "SS2553",
                    "buildTape.dependencyWeakIntegrity",
                    alias,
                    "dependencyIntegrity",
                    "pinnedDependencyIntegrity",
                    "dependency integrity should be a strong pin",
                    "`dependencyIntegrity` should use `sha256:<64 hex>` for archives or `commit:<7-40 hex>` for GitHub commits. Freeform text is not a reproducible lock input.",
                    f"dependencyIntegrity {projectName} {alias} sha256:<64-hex-digest>",
                )
        elif verb == "dependencyCache":
            cacheRows.append(sourceLine)
        elif verb == "dependencyLock":
            lockRows.append(sourceLine)

    remoteAliases: Set[str] = set()
    for alias, rows in sourceRows.items():
        if any(kind in REMOTE_DEPENDENCY_KINDS for _line, kind in rows):
            remoteAliases.add(alias)
    for alias, rows in fetchRows.items():
        if any(kind in REMOTE_DEPENDENCY_KINDS for _line, kind in rows):
            remoteAliases.add(alias)

    for alias, line in list(sourceRows.items()) + list(fetchRows.items()):
        if alias in declaredDependencies:
            continue
        firstLine = line[0][0]
        add_dependency_diag(
            firstLine,
            "SS2551",
            "buildTape.dependencySourceUnknownAlias",
            alias,
            "dependencyAlias",
            "declaredDependencyAlias",
            "dependency source/fetch targets an undeclared alias",
            "`dependencySource`, `dependencyFetch`, and `dependencyIntegrity` attach to a `dependency PROJECT ALIAS MODULE_PATH VERSION_OR_REF` row.",
            f"dependency {projectName} {alias} <modulePath> <version-or-ref>",
            severity=Severity.ERROR,
            blocksCompile=True,
        )

    for alias, sourceLine in integrityRows.items():
        if alias in declaredDependencies:
            continue
        add_dependency_diag(
            sourceLine,
            "SS2551",
            "buildTape.dependencyIntegrityUnknownAlias",
            alias,
            "dependencyAlias",
            "declaredDependencyAlias",
            "dependency integrity targets an undeclared alias",
            "`dependencyIntegrity` must attach to a declared dependency alias so the lock tape can bind the pin to one module path.",
            f"dependency {projectName} {alias} <modulePath> <version-or-ref>",
            severity=Severity.ERROR,
            blocksCompile=True,
        )

    for alias, declarationLine in declaredDependencies.items():
        if alias not in sourceRows and alias not in fetchRows:
            add_dependency_diag(
                declarationLine,
                "SS2550",
                "buildTape.dependencyMissingFetchSource",
                alias,
                "dependencyAlias",
                "dependencyFetchSource",
                "dependency declaration lacks a source or fetch row",
                "A dependency row names the requested module contract. A source or fetch row names how the dependency will be found for cache, lock, and future network-safe builds.",
                f"dependencyFetch {projectName} {alias} github owner/repo <ref>",
            )

    for alias in sorted(remoteAliases):
        sourceLine = declaredDependencies.get(alias)
        if sourceLine is None:
            continue
        if alias not in integrityRows:
            add_dependency_diag(
                sourceLine,
                "SS2553",
                "buildTape.remoteDependencyMissingIntegrity",
                alias,
                "dependencyAlias",
                "remoteDependencyIntegrity",
                "remote dependency lacks an integrity pin",
                "GitHub and HTTP dependencies should be pinned by `dependencyIntegrity` so locked builds can avoid trusting mutable network responses.",
                f"dependencyIntegrity {projectName} {alias} commit:<resolved-commit-or-sha256-digest>",
            )

    if remoteAliases and not cacheRows:
        firstRemoteLine = declaredDependencies.get(sorted(remoteAliases)[0])
        if firstRemoteLine is not None:
            add_dependency_diag(
                firstRemoteLine,
                "SS2554",
                "buildTape.remoteDependencyMissingCache",
                projectName,
                "buildProject",
                "dependencyCache",
                "remote dependencies need an explicit cache directory",
                "`dependencyCache PROJECT \"PATH\"` declares where fetched dependency source lives. The default should be `.semcache`, but spelling it in build.sem makes the authority edge visible.",
                f"dependencyCache {projectName} \".semcache\"",
            )
    if remoteAliases and not lockRows:
        firstRemoteLine = declaredDependencies.get(sorted(remoteAliases)[0])
        if firstRemoteLine is not None:
            add_dependency_diag(
                firstRemoteLine,
                "SS2555",
                "buildTape.remoteDependencyMissingLock",
                projectName,
                "buildProject",
                "dependencyLock",
                "remote dependencies need an explicit lock tape",
                "`dependencyLock PROJECT \"PATH\"` declares the reproducible lock tape for resolved commit, archive checksum, and transitive dependency rows.",
                f"dependencyLock {projectName} \"sem.lock\"",
            )

    return diagnostics


def check_project_build_tape_schema(facts: ExtendedFacts) -> List[Diagnostic]:
    """SS252x - build.sem project rows must form a strict build contract."""
    diagnostics: List[Diagnostic] = []
    if not _is_build_tape(facts):
        return diagnostics

    buildProjects: List[Tuple[str, SourceLine]] = []
    rowsByProject: Dict[str, Set[str]] = {}
    singletonSeen: Dict[Tuple[str, str], SourceLine] = {}
    sourceRoots: Dict[str, str] = {}
    targetRuntimes: Dict[str, str] = {}

    for sourceLine in facts.base.lines:
        if not sourceLine.tokens or is_comment(sourceLine):
            continue
        verb = sourceLine.verb
        args = sourceLine.args

        if verb == "buildProject":
            if args:
                buildProjects.append((args[0], sourceLine))
            continue

        if verb not in BUILD_TAPE_PROJECT_VERBS:
            if verb not in BUILD_TAPE_ALLOWED_NON_PROJECT_VERBS:
                diagnostics.append(_build_tape_diagnostic(
                    sourceLine,
                    "SS2520",
                    "buildTape.unknownTopLevelRow",
                    verb,
                    "verb",
                    "buildTapeVocabulary",
                    f"`{verb}` is not valid in build.sem",
                    (
                        "A build tape is a closed project contract. Top-level "
                        "rows must be project metadata, module registration, "
                        "build settings, resource metadata, or the current "
                        "compiler bridge rows."
                    ),
                    "# move this row into module source or add a documented build.sem verb",
                ))
            continue

        minimumArity = BUILD_TAPE_MIN_ARITY.get(verb, 2)
        if len(args) < minimumArity:
            diagnostics.append(_build_tape_diagnostic(
                sourceLine,
                "SS2523",
                "buildTape.malformedProjectRow",
                verb,
                "verb",
                "projectScopedBuildRow",
                f"`{verb}` is missing required arguments",
                (
                    f"`{verb}` rows in build.sem require at least "
                    f"{minimumArity} argument(s), starting with PROJECT."
                ),
                f"{verb} <project> <value>",
            ))
            continue

        projectName = args[0]
        rowsByProject.setdefault(projectName, set()).add(verb)

        if verb in BUILD_TAPE_SINGLETON_VERBS:
            key = (projectName, verb)
            previousLine = singletonSeen.get(key)
            if previousLine is not None:
                diagnostics.append(_build_tape_diagnostic(
                    sourceLine,
                    "SS2524",
                    "buildTape.duplicateSingletonRow",
                    verb,
                    "verb",
                    "singleSourceOfTruth",
                    f"`{verb}` is declared more than once",
                    (
                        f"`{verb}` is a singleton build setting for "
                        f"`{projectName}`. Keep one row so tooling does not "
                        "need precedence rules."
                    ),
                    f"# remove one `{verb} {projectName} ...` row",
                ))
            else:
                singletonSeen[key] = sourceLine

        if verb in BUILD_TAPE_CHOICES:
            value = args[1]
            if value not in BUILD_TAPE_CHOICES[verb]:
                diagnostics.append(_build_tape_diagnostic(
                    sourceLine,
                    "SS2525",
                    "buildTape.invalidChoiceValue",
                    value,
                    verb,
                    "closedEnumValue",
                    f"`{value}` is not valid for `{verb}`",
                    (
                        f"`{verb}` accepts only "
                        f"{', '.join(sorted(BUILD_TAPE_CHOICES[verb]))}."
                    ),
                    f"{verb} {projectName} <valid-value>",
                ))

        if verb == "cpuFeature":
            featureState = args[2] if len(args) >= 3 else ""
            if featureState not in CPU_FEATURE_STATES:
                diagnostics.append(_build_tape_diagnostic(
                    sourceLine,
                    "SS2525",
                    "buildTape.invalidChoiceValue",
                    featureState,
                    "cpuFeature",
                    "cpuFeatureState",
                    "`cpuFeature` state must be on or off",
                    "`cpuFeature PROJECT FEATURE STATE` accepts only `on` or `off`.",
                    f"cpuFeature {projectName} avx2 on",
                ))

        if verb == "optLevel":
            try:
                optLevel = int(args[1])
            except ValueError:
                optLevel = -1
            if optLevel < 0 or optLevel > 3:
                diagnostics.append(_build_tape_diagnostic(
                    sourceLine,
                    "SS2525",
                    "buildTape.invalidChoiceValue",
                    args[1],
                    "optLevel",
                    "llvmOptLevel",
                    "`optLevel` must be 0..3",
                    "LLVM optimization levels exposed by build.sem are integers 0, 1, 2, or 3.",
                    f"optLevel {projectName} 2",
                ))

        if verb == "nativeHttpPort":
            try:
                port = int(args[1])
            except ValueError:
                port = -1
            if port <= 0 or port > 65535:
                diagnostics.append(_build_tape_diagnostic(
                    sourceLine,
                    "SS2525",
                    "buildTape.invalidChoiceValue",
                    args[1],
                    "nativeHttpPort",
                    "tcpPort",
                    "`nativeHttpPort` must be 1..65535",
                    "Native HTTP build metadata must name a valid TCP port.",
                    f"nativeHttpPort {projectName} 18080",
                ))

        if verb == "buildFolderName":
            folderName = args[1]
            normalized = folderName.replace("\\", os.sep).replace("/", os.sep)
            if (os.path.isabs(normalized)
                    or os.path.dirname(normalized)
                    or normalized in {"", ".", ".."}):
                diagnostics.append(_build_tape_diagnostic(
                    sourceLine,
                    "SS2526",
                    "buildTape.invalidPathValue",
                    folderName,
                    "buildFolderName",
                    "managedBuildFolderName",
                    "`buildFolderName` must be one folder name",
                    (
                        "`buildFolderName PROJECT NAME` renames the managed "
                        "folder only. Use `buildDir` for an exact path or "
                        "`buildRoot` for a parent directory."
                    ),
                    f"buildFolderName {projectName} build",
                ))

        if verb == "sourceRoot":
            sourceRoots[projectName] = args[1]
        elif verb == "targetRuntime":
            targetRuntimes[projectName] = args[1]

        if verb in BUILD_TAPE_PATH_VERBS:
            baseDir = Path(facts.base.path).resolve().parent
            sourceRoot = sourceRoots.get(projectName)
            if sourceRoot:
                sourceRootPath = Path(sourceRoot)
                if not sourceRootPath.is_absolute():
                    baseDir = (baseDir / sourceRootPath).resolve()
                else:
                    baseDir = sourceRootPath.resolve()
            rawPath = Path(args[1])
            _ = rawPath if rawPath.is_absolute() else (baseDir / rawPath).resolve()

    if len(buildProjects) != 1:
        primaryLine = buildProjects[0][1] if buildProjects else facts.base.lines[0]
        diagnostics.append(_build_tape_diagnostic(
            primaryLine,
            "SS2521",
            "buildTape.projectCount",
            str(len(buildProjects)),
            "buildProject",
            "singleBuildProject",
            "build.sem must declare exactly one buildProject",
            "A build tape describes one project. Multi-project orchestration belongs in a higher-level workspace tool later.",
            "buildProject <project>",
        ))
        return diagnostics

    projectName, projectLine = buildProjects[0]
    projectRows = rowsByProject.get(projectName, set())
    missingRows = sorted(BUILD_TAPE_REQUIRED_VERBS - projectRows)
    if missingRows:
        diagnostics.append(_build_tape_diagnostic(
            projectLine,
            "SS2522",
            "buildTape.missingRequiredRow",
            projectName,
            "buildProject",
            "requiredBuildRows",
            "buildProject is missing required rows",
            (
                f"`buildProject {projectName}` must include: "
                f"{', '.join(sorted(BUILD_TAPE_REQUIRED_VERBS))}. "
                f"Missing now: {', '.join(missingRows)}."
            ),
            f"# add rows for: {', '.join(missingRows)}",
        ))

    for otherProject, rows in sorted(rowsByProject.items()):
        if otherProject == projectName:
            continue
        firstOffendingLine = next(
            line for line in facts.base.lines
            if line.tokens
            and not is_comment(line)
            and line.verb in rows
            and line.args
            and line.args[0] == otherProject
        )
        diagnostics.append(_build_tape_diagnostic(
            firstOffendingLine,
            "SS2527",
            "buildTape.rowTargetsUnknownProject",
            otherProject,
            "project",
            "projectNameConsistency",
            f"row targets `{otherProject}`, not `{projectName}`",
            "Every project-scoped build row must use the single active buildProject name.",
            f"{firstOffendingLine.verb} {projectName} ...",
        ))

    targetRuntime = targetRuntimes.get(projectName)
    if targetRuntime in {"nativeExe", "webServer", "windowsGui"} and "mainFile" not in projectRows:
        diagnostics.append(_build_tape_diagnostic(
            projectLine,
            "SS2522",
            "buildTape.missingRequiredRow",
            projectName,
            "buildProject",
            "mainFile",
            "`mainFile` is required for executable targets",
            "`targetRuntime nativeExe`, `targetRuntime webServer`, and `targetRuntime windowsGui` need an explicit default source file.",
            f"mainFile {projectName} \"main.sem\"",
        ))
    if targetRuntime == "nativeExe" and "mainOperation" not in projectRows:
        diagnostics.append(_build_tape_diagnostic(
            projectLine,
            "SS2522",
            "buildTape.missingRequiredRow",
            projectName,
            "buildProject",
            "mainOperation",
            "`mainOperation` is required for nativeExe",
            "`targetRuntime nativeExe` needs an explicit entry operation inside mainFile.",
            f"mainOperation {projectName} main",
        ))
    diagnostics.extend(_check_dependency_build_rows(facts, projectName))

    return diagnostics


def _nearest_build_facts(modulePath: Path) -> Optional[ProgramFacts]:
    current = modulePath.parent.resolve()
    for parent in (current, *current.parents):
        for buildName in ("build.sem", "build.sscript"):
            candidate = parent / buildName
            if candidate.exists() and candidate.resolve() != modulePath.resolve():
                try:
                    return parse_file(candidate)
                except OSError:
                    continue
    return None


def _collect_registered_modules(
    buildFacts: ProgramFacts,
) -> Tuple[Dict[str, Tuple[SourceLine, str]], List[str]]:
    registered: Dict[str, Tuple[SourceLine, str]] = {}
    mainFiles: List[str] = []
    for sourceLine in buildFacts.lines:
        if not sourceLine.tokens or is_comment(sourceLine):
            continue
        verb = sourceLine.verb
        args = sourceLine.args
        if verb == "registerModule" and len(args) >= 3:
            registered[args[1]] = (sourceLine, args[2])
        elif verb == "moduleFolder" and len(args) >= 2:
            registered[args[0]] = (sourceLine, args[1])
        elif verb == "mainFile" and len(args) >= 2:
            mainFiles.append(args[1])
    return registered, mainFiles


def _resolve_registered_module_source(
    moduleName: str,
    rawPath: str,
    buildPath: Path,
    mainFiles: Sequence[str],
) -> Optional[Path]:
    registeredPath = Path(rawPath)
    if not registeredPath.is_absolute():
        registeredPath = buildPath.parent / registeredPath
    if registeredPath.is_file():
        return registeredPath.resolve()
    if not registeredPath.is_dir():
        return None

    leafName = moduleName.rsplit(".", 1)[-1]
    candidateNames: List[str] = []
    candidateNames.extend(mainFiles)
    candidateNames.extend([
        "main.sem",
        "main.sscript",
        "index.sem",
        "index.sscript",
        f"{leafName}.sem",
        f"{leafName}.sscript",
    ])
    for candidateName in dict.fromkeys(candidateNames):
        candidatePath = registeredPath / candidateName
        if candidatePath.is_file():
            return candidatePath.resolve()

    moduleSources = [
        path for path in registeredPath.iterdir()
        if path.is_file()
        and path.name.lower() not in {"build.sem", "build.sscript"}
        and not path.name.lower().endswith((".test.sem", ".test.sscript"))
        and path.suffix.lower() in {".sem", ".sscript"}
    ]
    if len(moduleSources) == 1:
        return moduleSources[0].resolve()
    return None


def _registered_module_source_exists(
    moduleName: str,
    rawPath: str,
    buildPath: Path,
    mainFiles: Sequence[str],
) -> bool:
    return _resolve_registered_module_source(
        moduleName, rawPath, buildPath, mainFiles) is not None


def _contract_edges_for_symbol(
    contractTape: Sequence[ExportContractEdge],
    symbolName: str,
) -> List[ExportContractEdge]:
    return [edge for edge in contractTape if edge.symbolName == symbolName]


def _import_alias_for_module(importFact: ImportModuleFact) -> Optional[str]:
    return importFact.alias


def build_import_contract_index(facts: ExtendedFacts) -> ImportContractIndex:
    """Resolve imported public contracts visible from one module source.

    The returned index is intentionally source-facing: keys preserve the
    qualified name or local singular import name used by the importing file,
    while values retain provider module/export tape provenance.
    """
    index = ImportContractIndex()
    buildFacts = _nearest_build_facts(facts.base.path)
    if buildFacts is None:
        return index
    registeredModules, mainFiles = _collect_registered_modules(buildFacts)

    for importFact in facts.base.module_imports:
        alias = _import_alias_for_module(importFact)
        if not alias:
            continue
        registration = registeredModules.get(importFact.module_name)
        if registration is None:
            providerPath = _standard_module_source(
                importFact.module_name, facts.base.path)
            if providerPath is None:
                continue
        else:
            _registrationLine, rawPath = registration
            providerPath = _resolve_registered_module_source(
                importFact.module_name, rawPath, buildFacts.path, mainFiles)
        if providerPath is None or providerPath == facts.base.path.resolve():
            continue
        try:
            providerFacts = gather_extended(parse_file(providerPath))
        except OSError:
            continue
        contractTape = build_export_contract_tape(providerFacts)
        exportsByKind = _exported_symbols_by_kind(providerFacts)
        moduleContract = ImportedModuleContract(
            moduleName=importFact.module_name,
            alias=alias,
            sourcePath=providerPath,
            importLine=importFact.line,
            exportsByKind=exportsByKind,
            contractTape=contractTape,
        )
        index.modulesByAlias[alias] = moduleContract
        for kind, names in exportsByKind.items():
            for exportedName in names:
                qualifiedName = f"{alias}.{exportedName}"
                index.qualifiedSymbols[qualifiedName] = ImportedSymbolContract(
                    kind=kind,
                    localName=qualifiedName,
                    qualifiedName=qualifiedName,
                    moduleAlias=alias,
                    moduleName=importFact.module_name,
                    exportedName=exportedName,
                    edges=_contract_edges_for_symbol(contractTape, exportedName),
                    importLine=importFact.line,
                )

    for singularImport in facts.base.singular_imports:
        moduleContract = index.modulesByAlias.get(singularImport.module_alias)
        if moduleContract is None:
            continue
        exportedSymbols = moduleContract.exportsByKind.get(singularImport.kind, set())
        if singularImport.exported_name not in exportedSymbols:
            continue
        qualifiedName = f"{singularImport.module_alias}.{singularImport.exported_name}"
        index.singularSymbols[singularImport.local_name] = ImportedSymbolContract(
            kind=singularImport.kind,
            localName=singularImport.local_name,
            qualifiedName=qualifiedName,
            moduleAlias=singularImport.module_alias,
            moduleName=moduleContract.moduleName,
            exportedName=singularImport.exported_name,
            edges=_contract_edges_for_symbol(
                moduleContract.contractTape, singularImport.exported_name),
            importLine=singularImport.line,
        )

    return index


def check_registered_module_contract(facts: ExtendedFacts) -> List[Diagnostic]:
    """SS250x - build.sem registers modules; modules own imports/exports."""
    diagnostics: List[Diagnostic] = []
    buildFacts = facts.base if _is_build_tape(facts) else _nearest_build_facts(facts.base.path)
    if buildFacts is None:
        return diagnostics

    registeredModules, mainFiles = _collect_registered_modules(buildFacts)
    registeredNames = set(registeredModules)
    declaredExportSymbols = _collect_declared_export_symbols(facts)
    constantDeclarations = _collect_constant_declarations(facts)
    exportRows = _export_rows(facts)
    exportedSymbolsByKind = _exported_symbols_by_kind(facts)
    currentModuleNames = {
        sourceLine.args[0]
        for sourceLine in facts.base.lines
        if sourceLine.tokens
        and not is_comment(sourceLine)
        and sourceLine.verb == "module"
        and sourceLine.args
    }
    currentIsBuildTape = buildFacts.path.resolve() == facts.base.path.resolve()

    if currentIsBuildTape:
        for moduleName, (registrationLine, rawPath) in registeredModules.items():
            if _registered_module_source_exists(moduleName, rawPath, buildFacts.path, mainFiles):
                continue
            diagnostics.append(Diagnostic(
                tier=Tier.T1_SPEC,
                code="SS2501",
                kind="module.registrationMissingSource",
                severity=Severity.ERROR,
                subjectName=moduleName,
                subjectKind="module",
                gapEdge="registerModule.source",
                intentSlogan=f"`{moduleName}` is registered but no module source file is selectable",
                primary=span_of_line(registrationLine, "moduleRegistration"),
                invariantRule=(
                    "`registerModule PROJECT MODULE_PATH \"PATH\"` must point "
                    "at a file or a folder with a deterministic module source "
                    "(main.sem, index.sem, the leaf module file, or exactly "
                    "one non-test .sem/.sscript)."
                ),
                specAnchor="SYNTAX.md#registerModule",
                fixCandidates=[
                    FixCandidate(
                        name="pointRegistrationAtSource",
                        shape=f"registerModule <project> {moduleName} \"path/to/main.sem\"",
                    ),
                    FixCandidate(name="addModuleMain", shape="main.sem"),
                ],
                confidence=Confidence.HIGH,
                blocksCompile=True,
                effort=Effort.TRIVIAL,
                passProvenance="check_registered_module_contract",
                agentHint=(
                    "build.sem is the module registry; make the registry "
                    "resolve deterministically before changing import/export rows"
                ),
            ))

    if not currentIsBuildTape:
        seenExportByModuleAndName: Dict[Tuple[str, str], SourceLine] = {}
        seenExactExport: Dict[Tuple[str, str, str], SourceLine] = {}
        for exportVerb, moduleName, exportedSymbol, sourceLine in exportRows:
            exactKey = (moduleName, exportVerb, exportedSymbol)
            previousExact = seenExactExport.get(exactKey)
            previousByName = seenExportByModuleAndName.get((moduleName, exportedSymbol))
            if previousExact is not None or previousByName is not None:
                previousLine = previousExact or previousByName
                diagnostics.append(Diagnostic(
                    tier=Tier.T1_SPEC,
                    code="SS2507",
                    kind="module.duplicateExport",
                    severity=Severity.ERROR,
                    subjectName=exportedSymbol,
                    subjectKind=exportVerb,
                    gapEdge="uniquePublicSymbol",
                    intentSlogan=f"`{exportedSymbol}` is exported more than once",
                    primary=span_of_line(sourceLine, "duplicateExport"),
                    related=[span_of_line(previousLine, "firstExport")],
                    invariantRule=(
                        "A module contract tape is keyed by public symbol "
                        "name. Exporting the same name twice, even under "
                        "different export verbs, creates an ambiguous public "
                        "API edge for importers and documentation tools."
                    ),
                    specAnchor="SYNTAX.md#exportOperation",
                    fixCandidates=[
                        FixCandidate(
                            name="removeDuplicateExport",
                            shape=f"# remove duplicate `{exportVerb} {moduleName} {exportedSymbol}`",
                        ),
                    ],
                    confidence=Confidence.HIGH,
                    blocksCompile=True,
                    effort=Effort.TRIVIAL,
                    passProvenance="check_registered_module_contract",
                    agentHint=(
                        "keep one export row per public symbol; if two "
                        "declarations need to be visible, rename one so the "
                        "contract tape stays unambiguous"
                    ),
                ))
            seenExactExport.setdefault(exactKey, sourceLine)
            seenExportByModuleAndName.setdefault((moduleName, exportedSymbol), sourceLine)

            if exportVerb == "exportConstant":
                declaration = constantDeclarations.get(exportedSymbol)
                if declaration is None:
                    continue
                if (declaration.declarationVerb == "storage"
                        and declaration.scope == "module"
                        and declaration.mutability == "mutable"):
                    diagnostics.append(Diagnostic(
                        tier=Tier.T1_SPEC,
                        code="SS2508",
                        kind="module.mutableStorageExport",
                        severity=Severity.ERROR,
                        subjectName=exportedSymbol,
                        subjectKind="exportConstant",
                        gapEdge="immutablePublicConstant",
                        intentSlogan="mutable module storage cannot be exported as a constant",
                        primary=span_of_line(sourceLine, "moduleExport"),
                        related=[span_of_line(declaration.line, "storageDeclaration")],
                        invariantRule=(
                            "`exportConstant` is a value contract. Mutable "
                            "module storage can change behind an importer's "
                            "back, so cross-module mutation must go through "
                            "an exported operation with explicit effects."
                        ),
                        specAnchor="SYNTAX.md#exportConstant",
                        fixCandidates=[
                            FixCandidate(
                                name="exportMutationOperation",
                                shape=f"exportOperation {moduleName} <operationThatReadsOrWrites{exportedSymbol}>",
                            ),
                            FixCandidate(
                                name="makeStorageImmutable",
                                shape=f"storage module immutable {exportedSymbol} {declaration.typeName} {declaration.value}".rstrip(),
                            ),
                        ],
                        confidence=Confidence.HIGH,
                        blocksCompile=True,
                        effort=Effort.LOCAL,
                        passProvenance="check_registered_module_contract",
                        agentHint=(
                            "public constants must be stable values; expose "
                            "mutable state through an operation contract so "
                            "effects and capabilities stay visible"
                        ),
                    ))
                elif declaration.scope != "module":
                    diagnostics.append(Diagnostic(
                        tier=Tier.T1_SPEC,
                        code="SS2509",
                        kind="module.nonModuleStateExport",
                        severity=Severity.ERROR,
                        subjectName=exportedSymbol,
                        subjectKind="exportConstant",
                        gapEdge="moduleScopePublicConstant",
                        intentSlogan="exported constants must be module-scope values",
                        primary=span_of_line(sourceLine, "moduleExport"),
                        related=[span_of_line(declaration.line, "stateDeclaration")],
                        invariantRule=(
                            "Local storage and sharedState slots are runtime "
                            "state, not public value contracts. Export a "
                            "module immutable constant or an operation that "
                            "accesses the state with declared effects."
                        ),
                        specAnchor="SYNTAX.md#exportConstant",
                        fixCandidates=[
                            FixCandidate(
                                name="moveToImmutableModuleStorage",
                                shape=f"storage module immutable {exportedSymbol} {declaration.typeName} {declaration.value}".rstrip(),
                            ),
                            FixCandidate(
                                name="removeStateExport",
                                shape=f"# remove `exportConstant {moduleName} {exportedSymbol}`",
                            ),
                        ],
                        confidence=Confidence.HIGH,
                        blocksCompile=True,
                        effort=Effort.LOCAL,
                        passProvenance="check_registered_module_contract",
                        agentHint=(
                            "do not make sharedState or local slots part of "
                            "the public API; importers need an operation "
                            "contract, not a direct state edge"
                        ),
                    ))

        moduleOwnsByName = {
            sourceLine.args[0]
            for sourceLine in facts.base.lines
            if sourceLine.tokens
            and not is_comment(sourceLine)
            and sourceLine.verb == "moduleOwns"
            and sourceLine.args
        }
        for exportedOperation in sorted(exportedSymbolsByKind.get("operation", set())):
            operation = facts.base.operations.get(exportedOperation)
            if operation is None:
                continue
            narrative = facts.operationNarrative.get(exportedOperation, {})
            if "purpose" not in narrative:
                diagnostics.append(Diagnostic(
                    tier=Tier.T3_REFINEMENT,
                    code="SS2511",
                    kind="module.exportedOperationMissingPurpose",
                    severity=Severity.WARNING,
                    subjectName=exportedOperation,
                    subjectKind="operation",
                    gapEdge="publicPurpose",
                    intentSlogan="exported operation lacks purpose",
                    primary=span_of_line(operation.line, "operationDeclaration"),
                    invariantRule=(
                        "An exported operation is public API. It needs a "
                        "`purpose OP \"...\"` row so importers and agents can "
                        "understand why the contract exists without reading "
                        "the body first."
                    ),
                    specAnchor="SYNTAX.md#purpose",
                    fixCandidates=[
                        FixCandidate(
                            name="addPurpose",
                            shape=f"purpose {exportedOperation} \"Describe the public contract.\"",
                        ),
                    ],
                    confidence=Confidence.HIGH,
                    effort=Effort.TRIVIAL,
                    passProvenance="check_registered_module_contract",
                    agentHint="public operations should carry their own rationale at the declaration site",
                ))

            publicName = exportedOperation
            if publicName != "main" and publicName in VAGUE_NAME_BLACKLIST:
                diagnostics.append(Diagnostic(
                    tier=Tier.T4_STYLE,
                    code="SS2512",
                    kind="module.exportedNameTooGeneric",
                    severity=Severity.INFO,
                    subjectName=publicName,
                    subjectKind="operation",
                    gapEdge="descriptivePublicName",
                    intentSlogan="exported operation name is overly generic",
                    primary=span_of_line(operation.line, "operationDeclaration"),
                    invariantRule=(
                        "Exported names are the module's public vocabulary. "
                        "A generic name forces importers to recover intent "
                        "from context that is not present at the call site."
                    ),
                    specAnchor="SYNTAX.md#naming",
                    fixCandidates=[
                        FixCandidate(
                            name="renamePublicOperation",
                            shape=f"operation <domainSpecific{publicName[0].upper()}{publicName[1:]}>",
                        ),
                    ],
                    confidence=Confidence.MEDIUM,
                    effort=Effort.LOCAL,
                    passProvenance="check_registered_module_contract",
                    agentHint="rename the operation and its export row together",
                ))

            declaredEffectPairs = {
                (effectLine.args[1], effectLine.args[2])
                for effectLine in facts.operationEffects.get(exportedOperation, [])
                if len(effectLine.args) >= 3
            }
            emittedEffectPairs: Set[Tuple[str, str]] = set()
            wrapsDependency = False
            for callFact in collect_operation_calls(operation).values():
                if "." in callFact.target:
                    wrapsDependency = True
                impliedEffect = CALL_TARGET_IMPLIED_EFFECTS.get(callFact.target)
                if not impliedEffect or impliedEffect in declaredEffectPairs:
                    continue
                if impliedEffect in emittedEffectPairs:
                    continue
                emittedEffectPairs.add(impliedEffect)
                impliedAction, impliedPath = impliedEffect
                diagnostics.append(Diagnostic(
                    tier=Tier.T3_REFINEMENT,
                    code="SS2513",
                    kind="module.exportedOperationUndeclaredEffect",
                    severity=Severity.WARNING,
                    subjectName=exportedOperation,
                    subjectKind="operation",
                    gapEdge="publicEffectContract",
                    intentSlogan="exported operation hides an undeclared body effect",
                    primary=span_of_line(callFact.line, "effectCausingCall"),
                    related=[span_of_line(operation.line, "operationDeclaration")],
                    invariantRule=(
                        f"Public operation `{exportedOperation}` calls "
                        f"`{callFact.target}`, which implies "
                        f"`effect {exportedOperation} {impliedAction} "
                        f"{impliedPath}`. Importers cannot reason about the "
                        "effect unless it is part of the exported contract."
                    ),
                    specAnchor="SYNTAX.md#effect",
                    fixCandidates=[
                        FixCandidate(
                            name="addPublicEffect",
                            shape=f"effect {exportedOperation} {impliedAction} {impliedPath}",
                        ),
                    ],
                    confidence=Confidence.HIGH,
                    effort=Effort.TRIVIAL,
                    passProvenance="check_registered_module_contract",
                    agentHint=(
                        "this mirrors SS3111 but is scoped to exported API; "
                        "public effect gaps affect every importer"
                    ),
                ))

            if wrapsDependency and currentModuleNames and not (
                currentModuleNames & moduleOwnsByName
            ):
                diagnostics.append(Diagnostic(
                    tier=Tier.T3_REFINEMENT,
                    code="SS2514",
                    kind="module.exportedWrapperMissingOwnershipContext",
                    severity=Severity.WARNING,
                    subjectName=exportedOperation,
                    subjectKind="operation",
                    gapEdge="moduleOwnershipContext",
                    intentSlogan="exported dependency wrapper lacks module ownership context",
                    primary=span_of_line(operation.line, "operationDeclaration"),
                    invariantRule=(
                        "When a public operation wraps dotted dependency "
                        "behavior, the module should state what it owns via "
                        "`moduleOwns MODULE \"...\"`. Without that context, "
                        "agents cannot tell whether the wrapper is a facade, "
                        "adapter, or accidental pass-through."
                    ),
                    specAnchor="docs/language/project-layout-build-sem.md#module-source-contracts",
                    fixCandidates=[
                        FixCandidate(
                            name="addModuleOwnership",
                            shape="moduleOwns <module.path> \"Describe the public dependency boundary this module owns.\"",
                        ),
                    ],
                    confidence=Confidence.MEDIUM,
                    effort=Effort.TRIVIAL,
                    passProvenance="check_registered_module_contract",
                    agentHint="add moduleOwns near modulePurpose/moduleInvariant at the top of the module file",
                ))

        for importedModuleName in sorted(facts.base.imports):
            if importedModuleName not in registeredModules:
                continue
            if importedModuleName in currentModuleNames:
                continue
            registrationLine, rawPath = registeredModules[importedModuleName]
            providerPath = _resolve_registered_module_source(
                importedModuleName, rawPath, buildFacts.path, mainFiles)
            if providerPath is None or providerPath == facts.base.path.resolve():
                continue
            try:
                providerFacts = gather_extended(parse_file(providerPath))
            except OSError:
                continue
            providerOperations = set(providerFacts.base.operations)
            providerExports = _exported_symbols_by_kind(providerFacts)
            providerExportedOperations = providerExports.get("operation", set())
            for operation in facts.base.operations.values():
                for callFact in collect_operation_calls(operation).values():
                    if callFact.target in facts.base.operations:
                        continue
                    if callFact.target not in providerOperations:
                        continue
                    if callFact.target in providerExportedOperations:
                        continue
                    diagnostics.append(Diagnostic(
                        tier=Tier.T1_SPEC,
                        code="SS2510",
                        kind="module.privateImportAccess",
                        severity=Severity.ERROR,
                        subjectName=callFact.target,
                        subjectKind="callTarget",
                        gapEdge="exportedOperationOnly",
                        intentSlogan=(
                            f"`{callFact.target}` is private to `{importedModuleName}`"
                        ),
                        primary=span_of_line(callFact.line, "privateCall"),
                        related=[
                            span_of_line(registrationLine, "registeredModule"),
                            span_of_line(providerFacts.base.operations[callFact.target].line,
                                         "providerOperation"),
                        ],
                        invariantRule=(
                            "Imported module symbols are private unless the "
                            "provider module declares a matching export row. "
                            "The current import bridge inlines files, but the "
                            "semantic contract is already export-only."
                        ),
                        specAnchor="SYNTAX.md#exportOperation",
                        fixCandidates=[
                            FixCandidate(
                                name="exportProviderOperation",
                                shape=f"exportOperation {importedModuleName} {callFact.target}",
                            ),
                            FixCandidate(
                                name="callPublicFacade",
                                shape=f"call {callFact.name} <exportedOperationFrom{importedModuleName.rsplit('.', 1)[-1].title()}>",
                            ),
                        ],
                        confidence=Confidence.HIGH,
                        blocksCompile=True,
                        effort=Effort.CROSS_FILE,
                        passProvenance="check_registered_module_contract",
                        agentHint=(
                            "do not rely on import inlining to reach private "
                            "provider operations; add an export row or call a "
                            "public facade operation"
                        ),
                    ))

    for sourceLine in facts.base.lines:
        if not sourceLine.tokens or is_comment(sourceLine):
            continue
        verb = sourceLine.verb
        args = sourceLine.args

        if currentIsBuildTape and verb in MODULE_EXPORT_VERBS:
            moduleName = args[0] if args else ""
            diagnostics.append(Diagnostic(
                tier=Tier.T1_SPEC,
                code="SS2502",
                kind="module.exportDeclaredInBuildTape",
                severity=Severity.ERROR,
                subjectName=moduleName or verb,
                subjectKind=verb,
                gapEdge="moduleLocalExportContract",
                intentSlogan=f"`{verb}` belongs in the module source, not build.sem",
                primary=span_of_line(sourceLine, "buildTapeExport"),
                invariantRule=(
                    "build.sem registers modules and selects build outputs; "
                    "the module source owns its import/export contract so "
                    "agents can reason about a folder without editing the "
                    "build entry point."
                ),
                specAnchor="SYNTAX.md#exportOperation",
                fixCandidates=[
                    FixCandidate(
                        name="moveExportToModuleSource",
                        shape=f"# move this `{verb}` row into the registered module file",
                    ),
                ],
                confidence=Confidence.HIGH,
                blocksCompile=True,
                effort=Effort.TRIVIAL,
                passProvenance="check_registered_module_contract",
                agentHint=(
                    "copy the export row into the file that declares the "
                    "same `module MODULE_PATH`; delete it from build.sem"
                ),
            ))
            continue

        if verb == "module" and args and registeredNames and args[0] not in registeredNames:
            diagnostics.append(Diagnostic(
                tier=Tier.T1_SPEC,
                code="SS2503",
                kind="module.declarationNotRegistered",
                severity=Severity.ERROR,
                subjectName=args[0],
                subjectKind="module",
                gapEdge="registeredModule",
                intentSlogan=f"`module {args[0]}` is not registered by build.sem",
                primary=span_of_line(sourceLine, "moduleDeclaration"),
                invariantRule=(
                    "Every project module folder must be registered from "
                    "build.sem before module source can import from it or "
                    "export a public contract."
                ),
                specAnchor="SYNTAX.md#registerModule",
                related=[
                    span_of_line(line, "registeredModule")
                    for _module, (line, _path) in registeredModules.items()
                ],
                fixCandidates=[
                    FixCandidate(
                        name="registerModule",
                        shape=f"registerModule <project> {args[0]} \"relative/folder\"",
                    ),
                ],
                confidence=Confidence.HIGH,
                blocksCompile=True,
                effort=Effort.TRIVIAL,
                passProvenance="check_registered_module_contract",
                agentHint="add a registerModule row to build.sem or correct the module path spelling",
            ))

        if verb == "importModule" and args and registeredNames:
            importedModuleName, _alias, _syntax = parse_import_module_args(args)
            if (importedModuleName not in registeredNames
                    and not _is_known_standard_module(
                        importedModuleName, facts.base.path)):
                diagnostics.append(Diagnostic(
                    tier=Tier.T1_SPEC,
                    code="SS2504",
                    kind="module.importNotRegistered",
                    severity=Severity.ERROR,
                    subjectName=importedModuleName,
                    subjectKind="importModule",
                    gapEdge="registeredDependency",
                    intentSlogan=f"`importModule {importedModuleName}` does not target a registered module",
                    primary=span_of_line(sourceLine, "moduleImport"),
                    invariantRule=(
                        "Project module imports must target modules registered "
                        "by build.sem; dependency modules should also be given a "
                        "build-time registration before module source imports them."
                    ),
                    specAnchor="SYNTAX.md#importModule",
                    fixCandidates=[
                        FixCandidate(
                            name="registerImportedModule",
                            shape=f"registerModule <project> {importedModuleName} \"relative/folder\"",
                        ),
                        FixCandidate(
                            name="fixImportPath",
                            shape="importModule <alias> <registered.module.path>",
                        ),
                    ],
                    confidence=Confidence.HIGH,
                    blocksCompile=True,
                    effort=Effort.TRIVIAL,
                    passProvenance="check_registered_module_contract",
                    agentHint=(
                        "the compiler resolves registered modules before filesystem "
                        "fallbacks; use the same dotted path in build.sem and importModule"
                    ),
                ))
            continue

        if verb in MODULE_EXPORT_VERBS and args and registeredNames:
            moduleName = args[0]
            if moduleName not in registeredNames or (
                currentModuleNames and moduleName not in currentModuleNames
            ):
                diagnostics.append(Diagnostic(
                    tier=Tier.T1_SPEC,
                    code="SS2505",
                    kind="module.exportTargetMismatch",
                    severity=Severity.ERROR,
                    subjectName=moduleName,
                    subjectKind=verb,
                    gapEdge="localRegisteredModule",
                    intentSlogan=f"`{verb}` targets `{moduleName}`, which is not this registered module",
                    primary=span_of_line(sourceLine, "moduleExport"),
                    invariantRule=(
                        "Module exports are local: the first argument must "
                        "name the module declared by this source file, and "
                        "that module must be registered by build.sem."
                    ),
                    specAnchor="SYNTAX.md#exportOperation",
                    fixCandidates=[
                        FixCandidate(
                            name="retargetExport",
                            shape=f"{verb} <this.module.path> <symbol>",
                        ),
                    ],
                    confidence=Confidence.HIGH,
                    blocksCompile=True,
                    effort=Effort.TRIVIAL,
                    passProvenance="check_registered_module_contract",
                    agentHint=(
                        "do not export another module's symbols from this file; "
                        "move the row to that module or fix the module path"
                    ),
                ))
                continue

            if len(args) >= 2:
                exportKind = EXPORT_VERB_DECLARATION_KIND[verb]
                exportedSymbol = args[1]
                if exportedSymbol not in declaredExportSymbols.get(exportKind, set()):
                    diagnostics.append(Diagnostic(
                        tier=Tier.T1_SPEC,
                        code="SS2506",
                        kind="module.exportedSymbolNotDeclared",
                        severity=Severity.ERROR,
                        subjectName=exportedSymbol,
                        subjectKind=verb,
                        gapEdge="declaredBeforePublicContract",
                        intentSlogan=(
                            f"`{verb}` exports `{exportedSymbol}`, but this "
                            f"module does not declare that {exportKind}"
                        ),
                        primary=span_of_line(sourceLine, "moduleExport"),
                        invariantRule=(
                            "Exports are never inferred. An `export*` row is "
                            "allowed only when the same module source declares "
                            "the exported type, error, operation, capability, "
                            "or constant."
                        ),
                        specAnchor="SYNTAX.md#exportOperation",
                        fixCandidates=[
                            FixCandidate(
                                name="declareExportedSymbol",
                                shape=f"# add a {exportKind} declaration for `{exportedSymbol}`",
                            ),
                            FixCandidate(
                                name="removeExport",
                                shape=f"# remove `{verb} {moduleName} {exportedSymbol}`",
                            ),
                        ],
                        confidence=Confidence.HIGH,
                        blocksCompile=True,
                        effort=Effort.TRIVIAL,
                        passProvenance="check_registered_module_contract",
                        agentHint=(
                            "do not invent a public API from call sites or "
                            "narrative; keep exports as explicit, backed "
                            "module-contract rows only"
                        ),
                    ))

    return diagnostics


def _module_import_diagnostic(
    sourceLine: SourceLine,
    code: str,
    kind: str,
    severity: Severity,
    subjectName: str,
    subjectKind: str,
    gapEdge: str,
    intentSlogan: str,
    invariantRule: str,
    fixShape: str,
    related: Optional[List[Span]] = None,
    blocksCompile: bool = True,
    effort: Effort = Effort.LOCAL,
) -> Diagnostic:
    return Diagnostic(
        tier=Tier.T1_SPEC if severity == Severity.ERROR else Tier.T3_REFINEMENT,
        code=code,
        kind=kind,
        severity=severity,
        subjectName=subjectName,
        subjectKind=subjectKind,
        gapEdge=gapEdge,
        intentSlogan=intentSlogan,
        primary=span_of_line(sourceLine, "moduleImport"),
        related=related or [],
        invariantRule=invariantRule,
        specAnchor="docs/language/project-layout-build-sem.md#import-contracts",
        fixCandidates=[FixCandidate(name="repairImportContract", shape=fixShape)],
        confidence=Confidence.HIGH,
        blocksCompile=blocksCompile,
        effort=effort,
        passProvenance="check_module_import_contracts",
        agentHint=(
            "imports are resolved from explicit provider export tape; keep "
            "qualified names or singular imports source-located and unambiguous"
        ),
    )


def _local_declaration_names(facts: ExtendedFacts) -> Set[str]:
    declared = _collect_declared_export_symbols(facts)
    names: Set[str] = set()
    for symbols in declared.values():
        names.update(symbols)
    names.update(facts.base.operations)
    return names


def _qualified_name_parts(name: str) -> Optional[Tuple[str, str]]:
    if "." not in name:
        return None
    alias, rest = name.split(".", 1)
    if not alias or not rest:
        return None
    return alias, rest


def _line_qualified_references(sourceLine: SourceLine) -> List[Tuple[str, str]]:
    if not sourceLine.tokens or is_comment(sourceLine):
        return []
    verb = sourceLine.verb
    args = sourceLine.args
    references: List[Tuple[str, str]] = []
    if verb == "call" and len(args) >= 2:
        references.append(("operation", args[1]))
    elif verb == "input" and len(args) >= 3:
        references.append(("type", args[2]))
    elif verb == "output" and len(args) >= 2:
        if args[1] == "Result":
            if len(args) >= 3:
                references.append(("type", args[2]))
            if len(args) >= 4:
                references.append(("error", args[3]))
        else:
            references.append(("type", args[1]))
    elif verb in {"bind", "bindOk", "bindError"} and len(args) >= 2:
        references.append(("type", args[1]))
    elif verb in {"ignoreOk", "ignoreValue"} and len(args) >= 2:
        references.append(("type", args[1]))
    elif verb == "useCapability" and len(args) >= 2:
        references.append(("capability", args[1]))
    elif verb == "makeError" and len(args) >= 2:
        qualified = args[1]
        parts = qualified.split(".")
        if len(parts) >= 3:
            references.append(("error", ".".join(parts[:2])))
    elif verb == "arg" and len(args) >= 3:
        references.append(("constant", args[2]))
    return references


def _mutable_public_constant_edges(
    importedSymbol: ImportedSymbolContract,
) -> List[ExportContractEdge]:
    if importedSymbol.kind != "constant":
        return []
    mutableEdges: List[ExportContractEdge] = []
    for edge in importedSymbol.edges:
        if edge.edgeKind != "constant.value" or len(edge.values) < 5:
            continue
        _typeName, _value, scope, mutability, declarationVerb = edge.values[:5]
        if declarationVerb == "storage" and scope == "module" and mutability == "mutable":
            mutableEdges.append(edge)
    return mutableEdges


def _effect_path_covers(declaredPath: str, requiredPath: str) -> bool:
    return declaredPath == requiredPath or requiredPath.startswith(declaredPath + ".")


def _operation_declares_imported_effect(
    facts: ExtendedFacts,
    operationName: str,
    action: str,
    path: str,
) -> bool:
    for effectLine in facts.operationEffects.get(operationName, []):
        if len(effectLine.args) < 3:
            continue
        declaredAction = effectLine.args[1]
        declaredPath = effectLine.args[2]
        if declaredAction == action and _effect_path_covers(declaredPath, path):
            return True
    return False


def _imported_operation_effect_edges(
    importedSymbol: ImportedSymbolContract,
) -> List[ExportContractEdge]:
    if importedSymbol.kind != "operation":
        return []
    return [
        edge for edge in importedSymbol.edges
        if edge.edgeKind == "operation.effect" and len(edge.values) >= 3
    ]


def _diagnose_imported_operation_effects(
    diagnostics: List[Diagnostic],
    facts: ExtendedFacts,
    operation: OperationFact,
    callFact: CallFact,
    importedSymbol: ImportedSymbolContract,
) -> None:
    seenRequiredEffects: Set[Tuple[str, str]] = set()
    for effectEdge in _imported_operation_effect_edges(importedSymbol):
        action = effectEdge.values[1]
        path = effectEdge.values[2]
        key = (action, path)
        if key in seenRequiredEffects:
            continue
        seenRequiredEffects.add(key)
        if _operation_declares_imported_effect(facts, operation.name, action, path):
            continue
        diagnostics.append(_module_import_diagnostic(
            callFact.line,
            "SS2542",
            "moduleImport.importedEffectNotDeclared",
            Severity.WARNING,
            callFact.target,
            "callTarget",
            "callerEffectContract",
            "imported operation effect is not declared by caller",
            (
                f"`{operation.name}` calls imported operation "
                f"`{callFact.target}`, whose public contract includes "
                f"`effect {importedSymbol.exportedName} {action} {path}`. "
                "The caller must restate the effect so file/network/database/"
                "observability authority does not disappear through a module "
                "boundary."
            ),
            f"effect {operation.name} {action} {path}",
            related=[span_of_line(effectEdge.line, "providerEffect")],
            blocksCompile=False,
            effort=Effort.CROSS_FILE,
        ))


def _find_import_cycle(
    startModule: str,
    registeredModules: Dict[str, Tuple[SourceLine, str]],
    buildPath: Path,
    mainFiles: Sequence[str],
) -> Optional[List[str]]:
    visiting: Set[str] = set()
    visited: Set[str] = set()

    def imports_for(moduleName: str) -> Set[str]:
        registration = registeredModules.get(moduleName)
        if registration is None:
            return set()
        _line, rawPath = registration
        sourcePath = _resolve_registered_module_source(
            moduleName, rawPath, buildPath, mainFiles)
        if sourcePath is None:
            return set()
        try:
            return set(parse_file(sourcePath).imports)
        except OSError:
            return set()

    def dfs(moduleName: str, stack: List[str]) -> Optional[List[str]]:
        if moduleName in visiting:
            cycleStart = stack.index(moduleName) if moduleName in stack else 0
            return stack[cycleStart:] + [moduleName]
        if moduleName in visited:
            return None
        visiting.add(moduleName)
        stack.append(moduleName)
        for importedName in sorted(imports_for(moduleName)):
            if importedName not in registeredModules:
                continue
            cycle = dfs(importedName, stack)
            if cycle is not None:
                return cycle
        stack.pop()
        visiting.remove(moduleName)
        visited.add(moduleName)
        return None

    return dfs(startModule, [])


def check_module_import_contracts(facts: ExtendedFacts) -> List[Diagnostic]:
    diagnostics: List[Diagnostic] = []
    if _is_build_tape(facts):
        return diagnostics

    buildFacts = _nearest_build_facts(facts.base.path)
    if buildFacts is None:
        return diagnostics
    registeredModules, mainFiles = _collect_registered_modules(buildFacts)
    importIndex = build_import_contract_index(facts)
    currentModuleNames = {
        sourceLine.args[0]
        for sourceLine in facts.base.lines
        if sourceLine.tokens and not is_comment(sourceLine)
        and sourceLine.verb == "module" and sourceLine.args
    }

    seenAliases: Dict[str, ImportModuleFact] = {}
    localNames = _local_declaration_names(facts)
    for importFact in facts.base.module_imports:
        if importFact.syntax == "malformed":
            diagnostics.append(_module_import_diagnostic(
                importFact.line, "SS2530", "moduleImport.malformed",
                Severity.ERROR, "importModule", "importModule",
                "moduleAlias", "malformed importModule row",
                "`importModule` must use either `importModule MODULE`, "
                "`importModule MODULE as ALIAS`, or `importModule ALIAS MODULE`.",
                "importModule alias provider.module.path",
            ))
            continue
        alias = importFact.alias
        if not alias:
            continue
        previous = seenAliases.get(alias)
        if previous is not None:
            diagnostics.append(_module_import_diagnostic(
                importFact.line, "SS2531", "moduleImport.aliasCollision",
                Severity.ERROR, alias, "moduleAlias", "uniqueModuleAlias",
                "module alias collision",
                "A module alias creates a qualified namespace. Reusing it "
                "would make `alias.Symbol` resolve to more than one provider.",
                f"importModule {alias} <different.module.path>",
                related=[span_of_line(previous.line, "previousAlias")],
            ))
        else:
            seenAliases[alias] = importFact
        if alias in localNames:
            diagnostics.append(_module_import_diagnostic(
                importFact.line, "SS2531", "moduleImport.aliasCollision",
                Severity.ERROR, alias, "moduleAlias", "namespaceShadow",
                "module alias shadows local declaration",
                "A module alias must not reuse an operation, type, error, "
                "capability, or constant name declared in the same source.",
                f"importModule {alias}Renamed {importFact.module_name}",
            ))

    singularByLocal: Dict[str, SingularImportFact] = {}
    singularCountByAlias: Dict[str, int] = {}
    for singularImport in facts.base.singular_imports:
        singularCountByAlias[singularImport.module_alias] = (
            singularCountByAlias.get(singularImport.module_alias, 0) + 1)
        if "*" in {
            singularImport.local_name,
            singularImport.module_alias,
            singularImport.exported_name,
        }:
            diagnostics.append(_module_import_diagnostic(
                singularImport.line, "SS2532", "moduleImport.wildcardImport",
                Severity.ERROR, singularImport.local_name, "singularImport",
                "explicitPublicSymbol", "wildcard imports are rejected",
                "SemanticScript import rows must name one exported symbol. "
                "Wildcard imports erase the public contract edge agents need "
                "for call, type, effect, and capability reasoning.",
                "importOperation localName moduleAlias exportedOperation",
            ))
            continue

        moduleContract = importIndex.modulesByAlias.get(singularImport.module_alias)
        if moduleContract is None:
            diagnostics.append(_module_import_diagnostic(
                singularImport.line, "SS2533", "moduleImport.unknownAlias",
                Severity.ERROR, singularImport.module_alias, "moduleAlias",
                "registeredImportAlias", "singular import uses unknown alias",
                "A singular import selects from a module alias declared by "
                "`importModule ALIAS MODULE_PATH` or `importModule MODULE_PATH as ALIAS`.",
                f"importModule {singularImport.module_alias} <registered.module.path>",
            ))
            continue

        exportedSymbols = moduleContract.exportsByKind.get(singularImport.kind, set())
        if singularImport.exported_name not in exportedSymbols:
            diagnostics.append(_module_import_diagnostic(
                singularImport.line, "SS2534", "moduleImport.privateSymbol",
                Severity.ERROR, singularImport.exported_name, singularImport.kind,
                "providerExportTape", "singular import targets private symbol",
                "Singular imports can only bind symbols present in the "
                "provider module's explicit export rows.",
                f"export{singularImport.kind.title()} {moduleContract.moduleName} {singularImport.exported_name}",
                related=[span_of_line(moduleContract.importLine, "moduleImport")],
                effort=Effort.CROSS_FILE,
            ))
            continue

        importedSingularSymbol = ImportedSymbolContract(
            kind=singularImport.kind,
            localName=singularImport.local_name,
            qualifiedName=f"{singularImport.module_alias}.{singularImport.exported_name}",
            moduleAlias=singularImport.module_alias,
            moduleName=moduleContract.moduleName,
            exportedName=singularImport.exported_name,
            edges=_contract_edges_for_symbol(
                moduleContract.contractTape, singularImport.exported_name),
            importLine=singularImport.line,
        )
        mutableConstantEdges = _mutable_public_constant_edges(importedSingularSymbol)
        if mutableConstantEdges:
            diagnostics.append(_module_import_diagnostic(
                singularImport.line, "SS2541", "moduleImport.mutableConstantImport",
                Severity.ERROR, singularImport.exported_name, "constant",
                "immutablePublicConstant", "mutable storage import rejected",
                "A singular constant import must bind a stable value edge. "
                "Mutable module storage can change behind an importer's back; "
                "cross-module state access must go through an exported operation.",
                f"exportOperation {moduleContract.moduleName} <operationThatReadsOrWrites{singularImport.exported_name}>",
                related=[span_of_line(mutableConstantEdges[0].line, "mutableStorage")],
                effort=Effort.CROSS_FILE,
            ))
            continue

        previous = singularByLocal.get(singularImport.local_name)
        if previous is not None:
            diagnostics.append(_module_import_diagnostic(
                singularImport.line, "SS2535", "moduleImport.singularShadow",
                Severity.ERROR, singularImport.local_name, "singularImport",
                "uniqueLocalImportName", "singular import shadows another import",
                "A local singular import name must identify exactly one "
                "provider symbol in this source file.",
                f"import{singularImport.kind.title()} {singularImport.local_name}2 {singularImport.module_alias} {singularImport.exported_name}",
                related=[span_of_line(previous.line, "previousImport")],
            ))
        else:
            singularByLocal[singularImport.local_name] = singularImport

        if singularImport.local_name in localNames:
            diagnostics.append(_module_import_diagnostic(
                singularImport.line, "SS2535", "moduleImport.singularShadow",
                Severity.ERROR, singularImport.local_name, "singularImport",
                "localDeclarationShadow", "singular import shadows local declaration",
                "A singular import must not hide a locally declared operation, "
                "type, error, capability, or constant. Local declarations win "
                "at codegen, which would make the import contract misleading.",
                f"import{singularImport.kind.title()} {singularImport.local_name}From{singularImport.module_alias.title()} {singularImport.module_alias} {singularImport.exported_name}",
            ))

        genericAliases = {
            "get", "set", "read", "write", "load", "save", "open", "close",
            "run", "main", "helper", "util", "handler",
        }
        if singularImport.local_name in genericAliases:
            diagnostics.append(_module_import_diagnostic(
                singularImport.line, "SS2539", "moduleImport.localAliasTooGeneric",
                Severity.INFO, singularImport.local_name, "singularImport",
                "providerDomainContext", "local import alias is too generic",
                "A singular import may rename a provider symbol, but the "
                "local name should preserve enough provider/domain context "
                "that a call site is still readable without opening imports.",
                f"import{singularImport.kind.title()} {singularImport.module_alias}{singularImport.exported_name[0].upper()}{singularImport.exported_name[1:]} {singularImport.module_alias} {singularImport.exported_name}",
                blocksCompile=False,
                effort=Effort.TRIVIAL,
            ))

    for moduleAlias, count in singularCountByAlias.items():
        if count >= 4:
            importLine = next(
                (row.line for row in facts.base.singular_imports
                 if row.module_alias == moduleAlias),
                None,
            )
            if importLine is not None:
                diagnostics.append(_module_import_diagnostic(
                    importLine, "SS2538", "moduleImport.tooManySingularImports",
                    Severity.WARNING, moduleAlias, "moduleAlias",
                    "qualifiedReadability", "many singular imports reduce clarity",
                    "When a source pulls many names from one provider, "
                    "qualified calls usually preserve more context for agents "
                    "and humans than a long local alias block.",
                    f"# prefer `{moduleAlias}.symbolName` for routine use",
                    blocksCompile=False,
                    effort=Effort.TRIVIAL,
                ))

    for operation in facts.base.operations.values():
        for callFact in collect_operation_calls(operation).values():
            targetParts = _qualified_name_parts(callFact.target)
            if targetParts is not None and targetParts[0] in importIndex.modulesByAlias:
                moduleContract = importIndex.modulesByAlias[targetParts[0]]
                if (moduleContract.moduleName == "standard.html"
                        and targetParts[1].startswith("hydrate.")):
                    continue
                intrinsicTarget = f"{targetParts[0]}.{targetParts[1]}"
                if (moduleContract.moduleName == "standard.http"
                        and intrinsicTarget in ALL_NATIVE_HTTP_TARGETS):
                    continue
                if (moduleContract.moduleName == "standard.json"
                        and (intrinsicTarget in SUPPORTED_JSON_PRIMITIVE_TARGETS
                             or intrinsicTarget in SUPPORTED_JSON_RUNTIME_TARGETS
                             or targetParts[1].startswith("encode.")
                             or targetParts[1].startswith("decode."))):
                    continue
                if (moduleContract.moduleName == "standard.gui"
                        and intrinsicTarget in SUPPORTED_GUI_RUNTIME_TARGETS):
                    continue
                importedSymbol = importIndex.qualifiedSymbols.get(callFact.target)
                if importedSymbol is None or importedSymbol.kind != "operation":
                    diagnostics.append(_module_import_diagnostic(
                        callFact.line, "SS2534", "moduleImport.privateSymbol",
                        Severity.ERROR, callFact.target, "callTarget",
                        "providerExportTape", "qualified call targets private symbol",
                        "Qualified calls may only target operations present "
                        "in the provider module's export tape. The original "
                        "qualified source name is preserved in this diagnostic.",
                        f"exportOperation {moduleContract.moduleName} {targetParts[1]}",
                        related=[span_of_line(moduleContract.importLine, "moduleImport")],
                        effort=Effort.CROSS_FILE,
                    ))
                else:
                    _diagnose_imported_operation_effects(
                        diagnostics, facts, operation, callFact, importedSymbol)
                continue

            if callFact.target in facts.base.operations:
                continue
            singular = importIndex.singularSymbols.get(callFact.target)
            if singular is not None and singular.kind == "operation":
                _diagnose_imported_operation_effects(
                    diagnostics, facts, operation, callFact, singular)
                continue
            providerAliases = [
                alias for alias, moduleContract in importIndex.modulesByAlias.items()
                if callFact.target in moduleContract.exportsByKind.get("operation", set())
            ]
            if len(providerAliases) > 1:
                diagnostics.append(_module_import_diagnostic(
                    callFact.line, "SS2536", "moduleImport.ambiguousUnqualifiedReference",
                    Severity.ERROR, callFact.target, "callTarget",
                    "qualifiedImportReference", "unqualified import is ambiguous",
                    "More than one imported module exports this operation "
                    "name. Use a qualified call or a singular import alias.",
                    f"call {callFact.name} {providerAliases[0]}.{callFact.target}",
                ))
            elif len(providerAliases) == 1:
                diagnostics.append(_module_import_diagnostic(
                    callFact.line, "SS2537", "moduleImport.implicitSingularImport",
                    Severity.ERROR, callFact.target, "callTarget",
                    "explicitImportEdge", "implicit singular import rejected",
                    "An aliased module import creates a namespace. Calling "
                    "an exported provider operation by bare name skips the "
                    "source-located import edge and should be written as a "
                    "qualified call or explicit singular import.",
                    f"call {callFact.name} {providerAliases[0]}.{callFact.target}",
                ))

    for sourceLine in facts.base.lines:
        for expectedKind, qualifiedName in _line_qualified_references(sourceLine):
            if expectedKind == "operation":
                continue
            parts = _qualified_name_parts(qualifiedName)
            if parts is None:
                continue
            alias, _symbol = parts
            if alias not in importIndex.modulesByAlias:
                continue
            importedSymbol = importIndex.qualifiedSymbols.get(qualifiedName)
            if importedSymbol is None or importedSymbol.kind != expectedKind:
                moduleContract = importIndex.modulesByAlias[alias]
                diagnostics.append(_module_import_diagnostic(
                    sourceLine, "SS2534", "moduleImport.privateSymbol",
                    Severity.ERROR, qualifiedName, expectedKind,
                    "providerExportTape", "qualified reference is not public",
                    f"`{qualifiedName}` is used as a {expectedKind}, but that "
                    "symbol is not exported with the matching kind by the "
                    "provider module.",
                    f"export{expectedKind.title()} {moduleContract.moduleName} {qualifiedName.split('.', 1)[1]}",
                    related=[span_of_line(moduleContract.importLine, "moduleImport")],
                    effort=Effort.CROSS_FILE,
                ))
                continue
            mutableConstantEdges = _mutable_public_constant_edges(importedSymbol)
            if mutableConstantEdges:
                moduleContract = importIndex.modulesByAlias[alias]
                diagnostics.append(_module_import_diagnostic(
                    sourceLine, "SS2541", "moduleImport.mutableConstantImport",
                    Severity.ERROR, qualifiedName, "constant",
                    "immutablePublicConstant", "mutable storage import rejected",
                    "Qualified constant access must resolve to a stable value "
                    "edge. Mutable module storage can change behind an "
                    "importer's back; cross-module state access must go "
                    "through an exported operation.",
                    f"exportOperation {moduleContract.moduleName} <operationThatReadsOrWrites{importedSymbol.exportedName}>",
                    related=[span_of_line(mutableConstantEdges[0].line, "mutableStorage")],
                    effort=Effort.CROSS_FILE,
                ))

    for moduleName in sorted(currentModuleNames):
        cycle = _find_import_cycle(
            moduleName, registeredModules, buildFacts.path, mainFiles)
        if cycle is not None and len(cycle) > 1:
            sourceLine = next(
                (line for line in facts.base.lines
                 if line.tokens and not is_comment(line)
                 and line.verb == "module" and line.args
                 and line.args[0] == moduleName),
                facts.base.lines[0],
            )
            diagnostics.append(_module_import_diagnostic(
                sourceLine, "SS2540", "moduleImport.cycle",
                Severity.ERROR, moduleName, "module",
                "acyclicImportGraph", "module import cycle rejected",
                "Registered module imports must form an acyclic graph so "
                "contract loading, effect propagation, and dependency cache "
                "work can terminate deterministically.",
                "# break the cycle with a smaller shared module or public facade",
                blocksCompile=True,
                effort=Effort.CROSS_FILE,
            ))
            break

    return diagnostics


CHECKERS = [
    # Foundational basics — run first so reference / arity / duplicate
    # errors surface before any refinement-level diagnostic.
    check_argument_arity,
    check_unresolved_references,
    check_argument_type_mismatch,
    check_enum_return_uses_case,
    check_math_operand_width_drift,
    check_duplicate_declarations,
    check_unknown_verbs,
    check_project_build_tape_schema,
    check_registered_module_contract,
    check_module_import_contracts,
    check_unused_calls,
    check_unused_labels,
    check_unused_capabilities,
    check_unused_error_cases,
    check_unused_mutable_storage,
    check_unused_bind_slots,
    check_partial_retry_policies,
    check_partial_trust_boundaries,
    check_literal_without_digest,
    check_operation_metadata_gaps,
    check_shared_state_protection,
    check_supported_shared_state_scope,
    check_effect_without_capability,
    check_hidden_failure,
    check_sibling_metadata_drift,
    check_undeclared_body_effect,
    check_make_error_unknown_variant,
    check_unused_const,
    check_unused_input,
    check_vague_names,
    check_sem_one_zero_legacy_forms,
    check_declaration_only_sample,
    # C-style discipline (AS32xx perf, AS33xx memory, AS34xx layout)
    check_dead_store,
    check_allocation_in_loop,
    check_bind_then_ignore,
    check_memory_heap_contradiction,
    check_allocation_source_missing,
    check_allocate_free_unpaired,
    check_stack_limit_overrun,
    check_record_align_power_of_two,
    check_array_length_zero,
    check_inline_capacity_without_spill_allocator,
    check_literal_encoding_missing,
    # Style discipline (SS44xx) — info-severity hoist/rationale/dead-init signals
    check_duplicate_local_immutable_across_ops,
    check_magic_ascii_byte_literal,
    check_dead_storage_initializer,
    check_fixed_offset_parser_needs_rationale,
    check_enum_repr_comparison,
    check_enum_result_discarded,
    check_paired_scalar_must_stay_equal,
    # Concurrency / type system / codec / resource (SS35xx, SS37xx, SS38xx, SS39xx)
    check_unawaited_task_group,
    check_lock_without_cleanup,
    check_unawaited_submit_work,
    check_select_without_cases,
    check_select_case_references_unknown_select,
    check_async_call_missing_boundary,
    check_file_handle_not_closed,
    check_guard_token_source_without_release,
    check_guard_token_protects_shared_state_access,
    check_circular_type_alias,
    check_json_codec_incomplete,
    check_runtime_backing_missing,
    # Webserver discipline (SS36xx) — route methods, middleware contracts,
    # nullable-input footgun detection, coverage drift, and
    # explicit-verb migrations
    check_invalid_route_method,
    check_middleware_missing_response_effect,
    check_unguarded_http_input,
    check_route_coverage_drift,
    check_legacy_null_body_marker,
    check_pins_null_body_failure_path_missing_rationale,
    check_response_body_forwarder_declaration_honored,
    check_rationale_call_references_known_call,
    check_route_handler_input_names,
    check_middleware_return_type_is_middleware_control,
    check_void_output_should_use_return_void,
    check_narrative_references_line_number,
    # Build-tape integrity (SS3614) — mainFile must reference a real file
    check_main_file_must_exist,
]


def lint_path(filePath: Path) -> List[Diagnostic]:
    baseFacts = parse_file_base(filePath)
    facts = gather_extended(baseFacts)
    diagnostics: List[Diagnostic] = []
    for checker in CHECKERS:
        diagnostics.extend(checker(facts))
    return sorted(diagnostics, key=_diagnostic_sort_key)


def _diagnostic_sort_key(diagnostic: Diagnostic) -> Tuple:
    return (
        not diagnostic.blocksCompile,
        diagnostic.tier.value,
        str(diagnostic.primary.path),
        diagnostic.primary.line,
        diagnostic.primary.column,
        diagnostic.code,
    )


# ==========================================================================
# Renderers
# ==========================================================================

def render_human(diagnostics: Sequence[Diagnostic]) -> str:
    if not diagnostics:
        return "(no diagnostics)"
    blocks: List[str] = []
    for diagnostic in diagnostics:
        lines: List[str] = []
        lines.append(
            f"┌─ [{diagnostic.tier.value}] {diagnostic.code}  "
            f"{diagnostic.severity.value.upper():<7} {diagnostic.kind}"
        )
        lines.append(
            f"│  {diagnostic.primary.path}:{diagnostic.primary.line}:{diagnostic.primary.column}"
        )
        # Structured subject — the agent-readable identity
        subjectLine = (
            f"│  subject    : {diagnostic.subjectKind} `{diagnostic.subjectName}`"
            if diagnostic.subjectName else ""
        )
        if subjectLine:
            lines.append(subjectLine)
        if diagnostic.gapEdge:
            lines.append(f"│  gap        : {diagnostic.gapEdge}")
        if diagnostic.intentSlogan:
            lines.append(f"│  intent     : {diagnostic.intentSlogan}")
        if diagnostic.invariantRule:
            lines.append(f"│  invariant  : {diagnostic.invariantRule}")
        if diagnostic.related:
            lines.append("│  related    :")
            for span in diagnostic.related:
                role = span.role or "related"
                lines.append(f"│    • {role:<24} {span.path}:{span.line}:{span.column}")
        if diagnostic.citations:
            lines.append("│  citations  :")
            for citation in diagnostic.citations:
                truncated = citation.text if len(citation.text) <= 72 else citation.text[:69] + "…"
                lines.append(
                    f"│    [{citation.edgeKind:<13} @{citation.span.line}] \"{truncated}\""
                )
        if diagnostic.fixCandidates:
            lines.append("│  fixes      :")
            for fixIndex, fix in enumerate(diagnostic.fixCandidates, start=1):
                marker = "[auto] " if fix.autoApplicable else "       "
                lines.append(f"│    {fixIndex}. {marker}{fix.name}")
                for shapeLine in fix.shape.splitlines():
                    lines.append(f"│         │ {shapeLine}")
        if diagnostic.specAnchor:
            lines.append(f"│  spec       : {diagnostic.specAnchor}")
        if diagnostic.agentHint:
            lines.append(f"│  agent hint : {diagnostic.agentHint}")
        metadataBits: List[str] = []
        if diagnostic.blocksCompile:
            metadataBits.append("blocks-compile")
        metadataBits.append(f"confidence={diagnostic.confidence.value}")
        metadataBits.append(f"effort={diagnostic.effort.value}")
        if diagnostic.passProvenance:
            metadataBits.append(f"pass={diagnostic.passProvenance}")
        lines.append("│  · " + " · ".join(metadataBits))
        lines.append("└─")
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


def render_json(diagnostics: Sequence[Diagnostic]) -> str:
    return json.dumps([diagnostic.to_json() for diagnostic in diagnostics], indent=2)


def render_agent(diagnostics: Sequence[Diagnostic]) -> str:
    confidenceRank = {"high": 0, "medium": 1, "low": 2}
    effortRank = {"trivial": 0, "local": 1, "crossFile": 2}
    orderedDiagnostics = sorted(
        diagnostics,
        key=lambda diagnostic: (
            not diagnostic.blocksCompile,
            confidenceRank[diagnostic.confidence.value],
            effortRank[diagnostic.effort.value],
            diagnostic.tier.value,
            diagnostic.code,
        ),
    )
    queue: List[Dict[str, object]] = []
    for diagnostic in orderedDiagnostics:
        queue.append({
            "code": diagnostic.code,
            "kind": diagnostic.kind,
            "subjectName": diagnostic.subjectName,
            "subjectKind": diagnostic.subjectKind,
            "gapEdge": diagnostic.gapEdge,
            "intentSlogan": diagnostic.intentSlogan,
            "blocksCompile": diagnostic.blocksCompile,
            "confidence": diagnostic.confidence.value,
            "effort": diagnostic.effort.value,
            "autoApplicable": any(
                fix.autoApplicable for fix in diagnostic.fixCandidates
            ),
            "primary": diagnostic.primary.to_json(),
            "fixCandidates": [fix.to_json() for fix in diagnostic.fixCandidates],
            "citations": [citation.to_json() for citation in diagnostic.citations],
            "agentHint": diagnostic.agentHint,
            "prerequisite": list(diagnostic.prerequisite),
            "specAnchor": diagnostic.specAnchor,
        })
    return json.dumps({"refinementQueue": queue}, indent=2)


# Note for the sem-record format: the `diagnostic*` verbs emitted below are
# DRAFT PROPOSALS for the diagnostic syntax surface — they are not yet rows
# in SYNTAX.md, so the output will NOT pass `semsc --lint --parse-only`. We
# emit the format here as a design demonstration; a real spec landing must
# precede production use. See refined-diagnostic design notes for the proposed grammar.
SEM_RECORD_HEADER = (
    "# DRAFT: diagnostic* verbs below are PROPOSED, not yet in SYNTAX.md.\n"
    "# Output will not pass `semsc --lint --parse-only` until the diagnostic\n"
    "# syntax surface is landed. See refined-diagnostic design notes.\n"
)


def render_sem_record(diagnostics: Sequence[Diagnostic]) -> str:
    """Proposed SemanticScript-form rendering: diagnostics as parseable declaration blocks.
    Header explicitly marks the verbs as draft."""
    chunks: List[str] = [SEM_RECORD_HEADER]
    for diagnostic in diagnostics:
        diagnosticSlug = _diagnostic_slug(diagnostic)
        recordLines: List[str] = [f"diagnostic {diagnosticSlug}"]
        recordLines.append(f"diagnosticTier {diagnosticSlug} {diagnostic.tier.value}")
        recordLines.append(f"diagnosticCode {diagnosticSlug} {diagnostic.code}")
        recordLines.append(f"diagnosticKind {diagnosticSlug} {diagnostic.kind}")
        recordLines.append(f"diagnosticSeverity {diagnosticSlug} {diagnostic.severity.value}")
        if diagnostic.subjectName:
            recordLines.append(
                f"diagnosticSubject {diagnosticSlug} "
                f"{diagnostic.subjectKind} {diagnostic.subjectName}"
            )
        if diagnostic.gapEdge:
            recordLines.append(f"diagnosticGapEdge {diagnosticSlug} {diagnostic.gapEdge}")
        if diagnostic.intentSlogan:
            recordLines.append(
                f'diagnosticIntent {diagnosticSlug} "{_escape(diagnostic.intentSlogan)}"'
            )
        recordLines.append(
            f"diagnosticSpan {diagnosticSlug} primary "
            f"{diagnostic.primary.path} line {diagnostic.primary.line} "
            f"column {diagnostic.primary.column} role {diagnostic.primary.role or 'primary'}"
        )
        for span in diagnostic.related:
            recordLines.append(
                f"diagnosticSpan {diagnosticSlug} related "
                f"{span.path} line {span.line} column {span.column} "
                f"role {span.role or 'related'}"
            )
        if diagnostic.invariantRule:
            recordLines.append(
                f'diagnosticInvariant {diagnosticSlug} "{_escape(diagnostic.invariantRule)}"'
            )
        if diagnostic.specAnchor:
            recordLines.append(f"diagnosticSpecAnchor {diagnosticSlug} {diagnostic.specAnchor}")
        for citation in diagnostic.citations:
            recordLines.append(
                f"diagnosticCitation {diagnosticSlug} {citation.edgeKind} "
                f"{citation.span.path} line {citation.span.line} "
                f'"{_escape(citation.text)}"'
            )
        for fix in diagnostic.fixCandidates:
            recordLines.append(f"diagnosticFixCandidate {diagnosticSlug} {fix.name}")
            recordLines.append(
                f'diagnosticFixShape {diagnosticSlug} {fix.name} "{_escape(fix.shape)}"'
            )
            recordLines.append(
                f"diagnosticFixAutoApplicable {diagnosticSlug} {fix.name} "
                f"{'yes' if fix.autoApplicable else 'no'}"
            )
        recordLines.append(f"diagnosticConfidence {diagnosticSlug} {diagnostic.confidence.value}")
        recordLines.append(
            f"diagnosticBlocksCompile {diagnosticSlug} "
            f"{'yes' if diagnostic.blocksCompile else 'no'}"
        )
        recordLines.append(f"diagnosticEffort {diagnosticSlug} {diagnostic.effort.value}")
        for prerequisiteCode in diagnostic.prerequisite:
            recordLines.append(f"diagnosticPrerequisite {diagnosticSlug} {prerequisiteCode}")
        if diagnostic.passProvenance:
            recordLines.append(f"diagnosticPassProvenance {diagnosticSlug} {diagnostic.passProvenance}")
        if diagnostic.agentHint:
            recordLines.append(
                f'diagnosticAgentHint {diagnosticSlug} "{_escape(diagnostic.agentHint)}"'
            )
        chunks.append("\n".join(recordLines))
    return "\n\n".join(chunks)


def _diagnostic_slug(diagnostic: Diagnostic) -> str:
    """Descriptive slug — every component spelled out, no abbreviations.
    Pattern: <code-lower>In<FileStem>AsAtLine<n>"""
    fileStem = Path(diagnostic.primary.path).stem
    fileStemPascal = fileStem[:1].upper() + fileStem[1:] if fileStem else "Unnamed"
    return f"{diagnostic.code.lower()}In{fileStemPascal}AsAtLine{diagnostic.primary.line}"


def _escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


# ==========================================================================
# CLI
# ==========================================================================

def collect_paths(rawPaths: Sequence[str]) -> List[Path]:
    collected: List[Path] = []
    for rawPath in rawPaths:
        candidatePath = Path(rawPath)
        if candidatePath.is_dir():
            collected.extend(sorted(candidatePath.rglob("*.sscript")))
            collected.extend(sorted(candidatePath.rglob("*.sem")))
        elif candidatePath.is_file():
            if candidatePath.suffix in {".sscript", ".sem"}:
                collected.append(candidatePath)
        else:
            collected.extend(
                path for path in sorted(Path().glob(rawPath))
                if path.suffix in {".sscript", ".sem"}
            )
    return collected


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="semlint",
        description=f"Refined SemanticScript linter — design playground. v{__version__}",
    )
    parser.add_argument("paths", nargs="+")
    parser.add_argument(
        "--format",
        choices=["human", "json", "agent", "sem-record"],
        default="human",
        help="Output format. sem-record emits proposed SemanticScript-form (see header).",
    )
    parser.add_argument(
        "--tier", action="append",
        help="Filter to tiers (T0..T4). May be repeated.",
    )
    parser.add_argument(
        "--code", action="append",
        help="Filter to codes (e.g. SS0101). May be repeated.",
    )
    parser.add_argument(
        "--strict", action="store_true",
        help="Exit non-zero on any diagnostic.",
    )
    parser.add_argument(
        "--summary", action="store_true",
        help="Print a tier/severity summary after diagnostics (human format only).",
    )
    parser.add_argument(
        "--std-path", action="append", default=None,
        help=(
            "standard-library root override. May be repeated. Accepts a std "
            "root containing module.sem, a SemanticScript root containing std/, "
            "or a repo root containing SemanticScript/std. Environment "
            "fallbacks: SEMANTICSCRIPT_STD_PATH or SEMSC_STD_PATH."
        ),
    )
    args = parser.parse_args(argv)

    global _CLI_STDLIB_PATHS
    _CLI_STDLIB_PATHS = list(args.std_path or [])

    resolvedPaths = collect_paths(args.paths)
    if not resolvedPaths:
        print("semlint: no .sscript or .sem files matched", file=sys.stderr)
        return 2

    allDiagnostics: List[Diagnostic] = []
    for resolvedPath in resolvedPaths:
        try:
            allDiagnostics.extend(lint_path(resolvedPath))
        except OSError as readError:
            print(f"semlint: failed to read {resolvedPath}: {readError}", file=sys.stderr)
            return 2

    if args.tier:
        wantedTiers = set(args.tier)
        allDiagnostics = [d for d in allDiagnostics if d.tier.value in wantedTiers]
    if args.code:
        wantedCodes = set(args.code)
        allDiagnostics = [d for d in allDiagnostics if d.code in wantedCodes]

    renderer = {
        "human": render_human,
        "json": render_json,
        "agent": render_agent,
        "sem-record": render_sem_record,
    }[args.format]

    renderedOutput = renderer(allDiagnostics)
    if renderedOutput:
        print(renderedOutput)

    if args.format == "human" and args.summary:
        print()
        tierCounts: Dict[str, int] = {}
        for diagnostic in allDiagnostics:
            tierCounts[diagnostic.tier.value] = tierCounts.get(diagnostic.tier.value, 0) + 1
        blockerCount = sum(1 for d in allDiagnostics if d.blocksCompile)
        autoApplicableCount = sum(
            1 for d in allDiagnostics
            if any(fix.autoApplicable for fix in d.fixCandidates)
        )
        summaryLine = " · ".join(
            f"{tierName}={count}" for tierName, count in sorted(tierCounts.items())
        )
        print(
            f"summary: {len(allDiagnostics)} diagnostic(s) · {summaryLine} · "
            f"{blockerCount} blocker(s) · {autoApplicableCount} auto-applicable"
        )

    blockerCount = sum(1 for d in allDiagnostics if d.blocksCompile)
    if blockerCount:
        return 1
    if args.strict and allDiagnostics:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
