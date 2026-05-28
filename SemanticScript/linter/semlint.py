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
import re
import struct
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

_SEMANTICSCRIPT_ROOT = Path(__file__).resolve().parents[1]
if str(_SEMANTICSCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(_SEMANTICSCRIPT_ROOT))
from shared.call_contracts import (
    EXPLICIT_DISPOSITION_FALLIBLE_CALL_TARGETS as SHARED_EXPLICIT_DISPOSITION_FALLIBLE_CALL_TARGETS,
    KNOWN_FALLIBLE_CALL_TARGETS as SHARED_KNOWN_FALLIBLE_CALL_TARGETS,
    MIDDLEWARE_CONTROL_CASES as SHARED_MIDDLEWARE_CONTROL_CASES,
    MIDDLEWARE_CONTROL_TYPE as SHARED_MIDDLEWARE_CONTROL_TYPE,
    RESULT_FALLIBLE_CALL_TARGETS as SHARED_RESULT_FALLIBLE_CALL_TARGETS,
    SUPPORTED_HTTP_ROUTE_METHODS as SHARED_SUPPORTED_HTTP_ROUTE_METHODS,
    is_supported_route_method,
)
from shared.repo_version import read_repo_version
from shared.console_encoding import force_utf8_streams as _force_utf8_streams

__version__ = read_repo_version()


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
    run_checked_lines: List[SourceLine] = field(default_factory=list)
    start_lines: List[SourceLine] = field(default_factory=list)
    await_lines: List[SourceLine] = field(default_factory=list)
    bind_lines: List[SourceLine] = field(default_factory=list)
    bind_ok_lines: List[SourceLine] = field(default_factory=list)
    bind_error_lines: List[SourceLine] = field(default_factory=list)
    ignore_ok_lines: List[SourceLine] = field(default_factory=list)
    ignore_value_lines: List[SourceLine] = field(default_factory=list)
    ignore_error_lines: List[SourceLine] = field(default_factory=list)
    ignore_void_lines: List[SourceLine] = field(default_factory=list)
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
class ResultTypeFact:
    name: str
    ok_type: str
    error_type: str
    line: SourceLine


@dataclass
class SingularImportFact:
    kind: str
    local_name: str
    module_alias: str
    exported_name: str
    line: SourceLine


@dataclass
class JsonBodyFact:
    name: str
    line: SourceLine
    body_lines: List[Tuple[str, int]] = field(default_factory=list)


@dataclass
class SqlBodyFact:
    name: str
    line: SourceLine
    body_lines: List[Tuple[str, int]] = field(default_factory=list)


@dataclass
class HtmlTemplateFact:
    name: str
    line: SourceLine
    body_line: Optional[SourceLine] = None
    body_lines: List[Tuple[str, int]] = field(default_factory=list)


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
    result_types: Dict[str, ResultTypeFact] = field(default_factory=dict)
    singular_imports: List[SingularImportFact] = field(default_factory=list)
    json_bodies: List[JsonBodyFact] = field(default_factory=list)
    sql_bodies: List[SqlBodyFact] = field(default_factory=list)
    html_templates: Dict[str, HtmlTemplateFact] = field(default_factory=dict)
    records: Dict[str, List[Tuple[str, str]]] = field(default_factory=dict)
    record_json_names: Dict[Tuple[str, str], str] = field(default_factory=dict)
    record_json_omit_when: Dict[Tuple[str, str], str] = field(default_factory=dict)


BUILTIN_VALUE_TYPES: Dict[str, str] = {
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

for _middleware_case_name, _middleware_case_value in SHARED_MIDDLEWARE_CONTROL_CASES:
    BUILTIN_VALUE_TYPES[_middleware_case_name] = SHARED_MIDDLEWARE_CONTROL_TYPE
    BUILTIN_VALUE_LITERALS[_middleware_case_name] = str(_middleware_case_value)

BUILTIN_TYPE_ALIASES: Dict[str, str] = {
    "SqliteDatabase": "OpaquePointer",
    "SqliteStatement": "OpaquePointer",
    "SqliteRowId": "Int64",
    "GuiApplication": "OpaquePointer",
    "GuiSession": "OpaquePointer",
    "GuiEvent": "OpaquePointer",
    "GuiWindow": "OpaquePointer",
    "GuiControl": "OpaquePointer",
    "GuiWindowId": "UInt32",
    "GuiControlId": "UInt32",
    "GuiText": "String",
    "GuiApplicationTitle": "GuiText",
    "GuiWindowTitle": "GuiText",
    "GuiControlText": "GuiText",
    "GuiPlaceholderText": "GuiText",
    "GuiAccessibleName": "GuiText",
    "GuiListBoxItemText": "GuiText",
    "GuiIconGroupName": "String",
    "GuiPixels": "Int32",
    "GuiMinimumPixels": "GuiPixels",
    "GuiTabIndex": "Int32",
    "GuiKeyCode": "Int32",
    "GuiSelectedIndex": "Int32",
    "GuiEventDimensionPixels": "GuiPixels",
    "GuiHandlerStatus": "Int32",
    "GuiRuntimeStatusCode": "Int32",
    "GuiKeywordToken": "String",
    "GuiRuntimeTarget": "String",
    "JsonText": "String",
    "SqlText": "String",
    "JsonBuilder": "OpaquePointer",
    "JsonDocument": "OpaquePointer",
    "JsonCursor": "Int64",
    "JsonPath": "String",
    "JsonScratchBuffer": "OpaquePointer",
    "JsonCapacityBytes": "ByteCount",
}

REMOVED_PRIMITIVE_SPELLINGS: Dict[str, str] = {}

REMOVED_CALL_TARGET_SPELLINGS: Dict[str, str] = {}

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
    "input", "output", "effect", "memory", "async", "operationBody", "purpose", "invariant",
    "warning", "precondition",
    "guarantee", "failure", "security", "timing", "observability",
    "memoryHeap", "memoryArena", "memoryStackLimit",
    "memoryAllocationSource",
    "pinsNullBodyFailurePath", "responseBodyForwarder", "rationale",
}
_PARSER_ACTION_VERBS: Set[str] = {
    "set", "call", "arg", "argument", "timeout", "cancelOn", "run", "runChecked", "start", "await",
    "case", "done",
    "bind", "bindOk", "bindError", "ignore", "ignoreOk", "ignoreValue", "ignoreError", "makeError",
    "taskGroup", "startInGroup", "awaitGroup", "bindGroupError", "defer",
    "deferLog", "deferAwaitLog", "deferWhenExitLog", "new", "fieldGet",
    "fieldSet", "send", "receive", "lock", "unlock", "select", "selectCase",
    "runSelect", "useRetry", "useCapability",
    "deferRunOn", "startInterval", "awaitIntervalTick",
    "read", "workerPool", "work", "workArg", "submitWork", "awaitWork",
}
_PARSER_CONTROL_VERBS: Set[str] = {
    "label", "branch", "branchIf", "branchIfError", "branchIfGroupError",
    "branchIfChannelClosed", "branchSelected", "returnOk", "returnError",
    "returnValue", "returnVoid", "return", "jump",
}
_PARSER_BODY_VERBS: Set[str] = (
    _PARSER_CONTEXT_VERBS
    | _PARSER_ACTION_VERBS
    | _PARSER_CONTROL_VERBS
    | {"const", "var", "let", "storage", "importModule", "import"}
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


def parse_import_args(args: Sequence[str]) -> Tuple[str, Optional[str], str]:
    """Return (module_path, alias, syntax_shape) for `import ALIAS MODULE`."""
    if len(args) != 2:
        return "", None, "malformed"
    return args[1], args[0], "alias-module"


SINGULAR_IMPORT_VERB_KINDS: Dict[str, str] = {
    "importOperation": "operation",
    "importType": "type",
    "importError": "error",
    "importCapability": "capability",
    "importConstant": "constant",
}


def input_parts(sourceLine: SourceLine) -> Optional[Tuple[str, str, str]]:
    """Return (operation, input_name, type) for old or new input rows."""
    if sourceLine.verb != "input":
        return None
    args = sourceLine.args
    if len(args) >= 4 and args[0] == "operation":
        return args[1], args[2], args[3]
    if len(args) >= 3:
        return args[0], args[1], args[2]
    return None


def output_parts(sourceLine: SourceLine) -> Optional[Tuple[str, str]]:
    """Return (operation, output_type) for old or new output rows."""
    if sourceLine.verb != "output":
        return None
    args = sourceLine.args
    if len(args) >= 3 and args[0] == "operation":
        return args[1], args[2]
    if len(args) >= 2:
        return args[0], args[1]
    return None


def bind_parts(sourceLine: SourceLine) -> Optional[Tuple[str, str, str, str]]:
    """Return (variant, name, type, call) for bind rows."""
    args = sourceLine.args
    if sourceLine.verb == "bind":
        if len(args) >= 4 and args[0] in {"value", "ok", "error"}:
            return args[0], args[1], args[2], args[3]
        if len(args) >= 3:
            return "value", args[0], args[1], args[2]
    if sourceLine.verb == "bindOk" and len(args) >= 3:
        return "ok", args[0], args[1], args[2]
    if sourceLine.verb == "bindError" and len(args) >= 3:
        return "error", args[0], args[1], args[2]
    return None


def argument_parts(sourceLine: SourceLine) -> Optional[Tuple[str, str, Optional[str], str]]:
    """Return (call, parameter, declared_type, value) for argument rows."""
    args = sourceLine.args
    if sourceLine.verb == "argument" and len(args) >= 4:
        return args[0], args[1], args[2], args[3]
    if sourceLine.verb == "arg" and len(args) >= 3:
        return args[0], args[1], None, args[2]
    return None


def ignore_parts(sourceLine: SourceLine) -> Optional[Tuple[str, str, Optional[str]]]:
    """Return (variant, call, type) for ignore rows."""
    args = sourceLine.args
    if sourceLine.verb == "ignore":
        if len(args) >= 5 and args[0] in {"value", "ok"} and args[1] == "source" and args[3] == "type":
            return args[0], args[2], args[4]
        if len(args) >= 3 and args[0] in {"error", "void"} and args[1] == "source":
            return args[0], args[2], None
    if sourceLine.verb == "ignoreValue" and len(args) >= 2:
        variant = "void" if args[1] == "Void" else "value"
        return variant, args[0], args[1]
    if sourceLine.verb == "ignoreOk" and len(args) >= 2:
        return "ok", args[0], args[1]
    if sourceLine.verb == "ignoreError" and args:
        return "error", args[0], None
    return None


def branch_target_names_from_row(sourceLine: SourceLine) -> List[str]:
    args = sourceLine.args
    if sourceLine.verb == "jump" and len(args) >= 2 and args[0] == "target":
        return [args[1]]
    if sourceLine.verb == "branch":
        if len(args) >= 5 and args[0] in {"if", "error"} and args[3] == "target":
            return [args[4]]
        if len(args) >= 3 and args[0] == "else" and args[1] == "target":
            return [args[2]]
        if args:
            targets = [args[0]]
            if len(args) >= 3 and sourceLine.verb == "branchIf":
                targets.append(args[2])
            return targets
    if sourceLine.verb == "branchIf" and len(args) >= 2:
        targets = [args[1]]
        if len(args) >= 3:
            targets.append(args[2])
        return targets
    if sourceLine.verb in {"branchIfError", "branchIfGroupError", "branchIfChannelClosed"} and len(args) >= 2:
        return [args[1]]
    if sourceLine.verb == "branchSelected" and len(args) >= 3:
        return [args[2]]
    if sourceLine.verb == "runChecked" and len(args) >= 9:
        return [args[8]]
    if sourceLine.verb == "case" and len(args) >= 2:
        return [args[1]]
    if sourceLine.verb == "done" and args:
        return [args[0]]
    return []


def branch_else_targets_by_line(lines: Sequence[SourceLine]) -> Dict[int, str]:
    branchElseByLine: Dict[int, str] = {}
    for index, sourceLine in enumerate(lines[:-1]):
        if (sourceLine.verb == "branch" and sourceLine.args
                and sourceLine.args[0] in {"if", "error"}):
            nextLine = lines[index + 1]
            if nextLine.verb == "branch" and nextLine.args[:2] == ["else", "target"]:
                branchElseByLine[sourceLine.number] = nextLine.args[2]
    return branchElseByLine


def branch_target_names_with_attached_else(
    sourceLine: SourceLine,
    branchElseByLine: Dict[int, str],
) -> List[str]:
    targets = list(branch_target_names_from_row(sourceLine))
    elseLabel = branchElseByLine.get(sourceLine.number)
    if elseLabel is not None and elseLabel not in targets:
        targets.append(elseLabel)
    return targets


def branch_error_source(sourceLine: SourceLine) -> Optional[str]:
    args = sourceLine.args
    if sourceLine.verb == "branch" and len(args) >= 5 and args[:2] == ["error", "source"] and args[3] == "target":
        return args[2]
    if sourceLine.verb == "branchIfError" and len(args) >= 2:
        return args[0]
    return None


def return_parts(sourceLine: SourceLine) -> Optional[Tuple[str, Optional[str]]]:
    args = sourceLine.args
    if sourceLine.verb == "return":
        if args and args[0] == "void":
            return "void", None
        if len(args) >= 2 and args[0] in {"value", "ok", "error"}:
            return args[0], args[1]
    legacy = {
        "returnValue": "value",
        "returnOk": "ok",
        "returnError": "error",
        "returnVoid": "void",
    }.get(sourceLine.verb)
    if legacy:
        return legacy, args[0] if args else None
    return None


def memory_parts(sourceLine: SourceLine) -> Optional[Tuple[str, str, Sequence[str]]]:
    args = sourceLine.args
    if sourceLine.verb == "memory" and len(args) >= 2:
        return args[0], args[1], args[2:]
    if sourceLine.verb == "memoryHeap" and len(args) >= 2:
        return args[0], "heap", args[1:]
    if sourceLine.verb == "memoryArena" and len(args) >= 2:
        return args[0], "arena", args[1:]
    if sourceLine.verb == "memoryStackLimit" and len(args) >= 2:
        return args[0], "stack", ("max", args[1])
    return None


def parse_file(path: Path) -> ProgramFacts:
    program = ProgramFacts(path=path)
    _register_builtin_surface(program)
    current_op: Optional[OperationFact] = None
    active_html_body: Optional[HtmlTemplateFact] = None
    active_json_body: Optional[JsonBodyFact] = None
    active_sql_body: Optional[SqlBodyFact] = None

    with path.open("r", encoding="utf-8") as source_file:
        for line_number, raw_line in enumerate(source_file, start=1):
            raw = raw_line.rstrip("\n")
            if active_json_body is not None:
                if raw.strip() and raw[0].isspace():
                    active_json_body.body_lines.append((raw, line_number))
                    continue
                if not raw.strip():
                    active_json_body.body_lines.append(("", line_number))
                    continue
                active_json_body = None
            if active_sql_body is not None:
                if raw.strip() and raw[0].isspace():
                    active_sql_body.body_lines.append((raw, line_number))
                    continue
                if not raw.strip():
                    active_sql_body.body_lines.append(("", line_number))
                    continue
                active_sql_body = None
            if active_html_body is not None:
                if raw.strip() and raw[0].isspace():
                    active_html_body.body_lines.append((raw, line_number))
                    continue
                if not raw.strip():
                    active_html_body.body_lines.append(("", line_number))
                    continue
                active_html_body = None
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

            if verb == "module" and args:
                current_op = None
                program.abstractions.setdefault(
                    args[0], AbstractionFact("module", args[0], line))
                continue

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
            elif verb == "import" and args:
                moduleName, alias, syntax = parse_import_args(args)
                if moduleName:
                    program.imports.add(moduleName)
                    program.module_imports.append(
                        ImportModuleFact(moduleName, alias, line, syntax))
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
            elif (verb == "type" and len(args) >= 6
                  and args[1] == "result" and args[2] == "ok"
                  and args[4] == "error"):
                program.result_types[args[0]] = ResultTypeFact(
                    args[0], args[3], args[5], line)
                program.type_aliases[args[0]] = args[1]
            elif verb == "type" and len(args) >= 2:
                program.type_aliases[args[0]] = args[1]
            elif verb == "record" and args:
                program.records.setdefault(args[0], [])
                program.abstractions.setdefault(
                    args[0], AbstractionFact(verb, args[0], line))
            elif verb == "field" and len(args) >= 3:
                program.records.setdefault(args[0], []).append((args[1], args[2]))
            elif verb == "recordFieldJsonName" and len(args) >= 3:
                program.record_json_names[(args[0], args[1])] = args[2]
            elif verb == "recordFieldJsonOmitWhen" and len(args) >= 3:
                program.record_json_omit_when[(args[0], args[1])] = args[2]
            elif verb.startswith("type") and len(args) >= 1 and verb != "type":
                program.type_metadata.setdefault(args[0], set()).add(verb)
            elif verb == "capability" and len(args) >= 3:
                program.capabilities[args[0]] = BaseCapabilityFact(
                    args[0], args[1], args[2], line)
            elif verb == "route" and len(args) >= 4:
                program.routes.append(
                    RouteFact(args[0], args[1], args[2], args[3], line))
            elif verb == "html" and len(args) >= 2 and args[0] == "template":
                program.html_templates.setdefault(
                    args[1], HtmlTemplateFact(args[1], line))
                program.abstractions.setdefault(
                    args[1], AbstractionFact("htmlTemplate", args[1], line))
            elif verb == "htmlTemplate" and args:
                program.html_templates.setdefault(
                    args[0], HtmlTemplateFact(args[0], line))
                program.abstractions.setdefault(
                    args[0], AbstractionFact(verb, args[0], line))
            elif (verb == "html" and len(args) >= 3
                  and args[0] == "body" and args[1] == "template"):
                template = program.html_templates.setdefault(
                    args[2], HtmlTemplateFact(args[2], line))
                template.body_line = line
                active_html_body = template
            elif verb == "htmlBody" and args:
                template = program.html_templates.setdefault(
                    args[0], HtmlTemplateFact(args[0], line))
                template.body_line = line
                active_html_body = template
            elif verb == "jsonBody":
                json_body = JsonBodyFact(args[0] if args else "", line)
                program.json_bodies.append(json_body)
                active_json_body = json_body
            elif verb == "sqlBody" or (verb == "sql" and args[:1] == ["body"]):
                name = args[0] if verb == "sqlBody" and args else ""
                if verb == "sql" and len(args) >= 2:
                    name = args[1]
                sql_body = SqlBodyFact(name, line)
                program.sql_bodies.append(sql_body)
                active_sql_body = sql_body
            elif verb in _PARSER_CONTRACT_HEAVY_KINDS and args:
                program.abstractions.setdefault(
                    args[0], AbstractionFact(verb, args[0], line))
            elif (verb in {"purpose", "invariant", "warning", "guarantee",
                           "failure", "security", "timing", "observability"}
                  and args):
                owner = args[1] if len(args) >= 3 and ((verb == "purpose" and args[0] in PURPOSE_SUBJECT_KINDS) or (verb == "invariant" and args[0] in {"module", "operation"})) else args[0]
                program.hard_metadata.setdefault(owner, set()).add(verb)

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


# Subject kinds a `purpose` row may name. Mirrors `_PURPOSE_SUBJECT_KINDS` in
# the compiler: operations and modules plus the contract-heavy abstractions the
# `missingPurpose` advisory asks for. When `args[0]` is one of these, the owner
# name is `args[1]`; otherwise the row is the legacy unqualified form.
PURPOSE_SUBJECT_KINDS: frozenset = frozenset({
    "module", "operation",
    "capability", "webServer", "record",
    "resource", "validator", "codec", "policy",
})

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
# Result-shaped calls need explicit success/error disposition; C-style
# status/pointer fallibles need an explicit value disposition. This is the
# hiddenFailure detection surface.
KNOWN_FALLIBLE_CALL_TARGETS: frozenset = SHARED_KNOWN_FALLIBLE_CALL_TARGETS
RESULT_FALLIBLE_CALL_TARGETS: frozenset = SHARED_RESULT_FALLIBLE_CALL_TARGETS
C_SENTINEL_FALLIBLE_CALL_TARGETS: frozenset = SHARED_EXPLICIT_DISPOSITION_FALLIBLE_CALL_TARGETS


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
    "c.malloc", "c.calloc", "c.realloc", "c.alignedAlloc", "c.aligned_alloc",
})

HEAP_DEALLOCATION_CALL_TARGETS: frozenset = frozenset({
    "c.free",
})

C_STRING_ACCUMULATOR_CALL_TARGETS: frozenset = frozenset({
    "c.strcat", "c.strncat", "c.strcatSafe", "c.strncatSafe",
})

SQLITE_DATABASE_OPEN_TARGETS: frozenset = frozenset({
    "sqlite.openDatabase",
})

SQLITE_DATABASE_CLOSE_TARGETS: frozenset = frozenset({
    "sqlite.closeDatabase",
})

SQLITE_STATEMENT_PREPARE_TARGETS: frozenset = frozenset({
    "sqlite.prepareStatement",
})

SQLITE_STATEMENT_FINALIZE_TARGETS: frozenset = frozenset({
    "sqlite.finalizeStatement",
})

FIXED_ROW_COUNT_MUTATION_TARGETS: frozenset = frozenset({
    "insertEmptyRowAt",
    "splitRowAt",
})


# Stack-byte estimates for primitive SemanticScript types. Used by SS3304 stack-limit
# overrun heuristic. Values are conservative C ABI widths; types not in this
# table contribute 8 bytes (pointer-sized) — slightly pessimistic but never
# under-counts.
PRIMITIVE_TYPE_STACK_BYTES: Dict[str, int] = {
    "Bool": 1,
    "Int2": 1, "UInt2": 1,
    "Int4": 1, "UInt4": 1,
    "Int8": 1, "UInt8": 1,
    "Int16": 2, "UInt16": 2,
    "Int32": 4, "UInt32": 4, "ExitCode": 4, "Char": 4,
    "Float16": 2, "Float32": 4, "Float64": 8,
    "Int64": 8, "UInt64": 8,
    "ByteCount": 8, "SignedByteCount": 8, "AddressOffset": 8,
    "UnixSecondsSinceEpoch": 8, "CpuClockTicks": 8, "FileByteOffset": 8,
    "String": 8, "OpaquePointer": 8, "FileHandle": 8,
    "DurationMilliseconds": 8, "MonotonicMilliseconds": 8, "UtcMilliseconds": 8,
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
    "c.alignedAlloc":            ("allocate", "heap"),
    "c.aligned_alloc":           ("allocate", "heap"),
    "c.free":                    ("free",     "heap"),
    # Process lifecycle
    "c.exit":                    ("write", "process.lifecycle"),
    "c.abort":                   ("write", "process.lifecycle"),
    # Outbound network client
    "net.fetchText":             ("write", "network.http.client"),
    "net.fetchBytes":            ("write", "network.http.client"),
    "net.freeTextBody":          ("free", "heap"),
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


# Primitive types that are interchangeable at the SemanticScript surface. Used
# by broad arg-type-mismatch checks to avoid
# false-positive complaints about role-equivalent aliases. Math calls get a
# stricter width pass below because their lowering is intentionally exact.
_PRIMITIVE_TYPE_EQUIVALENCE_GROUPS: Tuple[frozenset, ...] = (
    # All signed integer widths AND Bool are treated as interchangeable for
    # user-op compatibility; strict math width diagnostics are handled
    # separately by SS4303.
    frozenset({"Int64", "Int32", "ExitCode", "Char",
               "Int16", "Int8",
               "ByteCount", "SignedByteCount", "AddressOffset",
               "UnixSecondsSinceEpoch", "CpuClockTicks", "FileByteOffset",
               "DurationMilliseconds", "MonotonicMilliseconds", "UtcMilliseconds",
               "Bool"}),
    frozenset({"UInt2", "UInt4", "UInt8", "UInt16", "UInt32", "UInt64"}),
    frozenset({"Float16", "Float32", "Float64"}),
    # All pointer-shaped types are interchangeable — pointer.* primitives
    # accept any of them and the compiler emits the necessary bitcasts.
    # String and related text aliases are pointer-shaped byte sequences
    # so they live in the pointer family for SemanticScript arg-type purposes.
    frozenset({"String", "JsonText", "SqlText", "GuiText", "JsonPath",
               "OpaquePointer", "FileHandle",
               "DecomposedTimeAddress", "SetjmpRegisterBuffer"}),
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
# Width-preserving C-ABI spelling aliases: the LLVM-style name and the
# C-ABI name for the same machine type. Used to compare an `argument` row's
# declared type against a builtin signature without false-flagging `Float64`
# vs `Float64` (same double) or `Int64` vs `Int64` (same 64-bit int). Width
# is preserved on purpose — `Int32` is NOT folded into `Int64`.
_C_ABI_WIDTH_ALIAS: Dict[str, str] = {
    "Float64": "Float64",
    "Float32": "Float32",
    "Int64": "Int64",
    "UInt64": "UInt64",
    "Int32": "Int32",
    "UInt32": "UInt32",
    "Int16": "Int16",
    "UInt16": "UInt16",
    "Int8": "Int8",
    "UInt8": "UInt8",
    "ByteCount": "ByteCount",
    "SignedByteCount": "SignedByteCount",
    "AddressOffset": "AddressOffset",
    "OpaquePointer": "OpaquePointer",
    "FileHandle": "FileHandle",
    "String": "String",
}


# Opaque domain-handle types: these lower to a raw pointer (i8*) but are NOT
# interchangeable with String or with each other. Binding a String/scalar value
# as one of these (or vice versa) is a provable type lie that the ABI hides —
# the exact shape that turned `string.concat` (returns String) bound as
# HtmlFragment into a runtime SIGSEGV when hydrated. See check_bind_return_type_domain.
_OPAQUE_DOMAIN_HANDLE_TYPES: frozenset = frozenset({
    "HtmlFragment", "HtmlTrustedFragment", "HtmlDocument",
    "JsonDocument", "JsonBuilder",
})

# Conservative return-type registry for the builtins where the bind-return
# domain check is meaningful. Only targets whose return type is unambiguous are
# listed; anything absent is skipped (false-negative over false-positive).
BUILTIN_TARGET_RETURN_TYPES: Dict[str, str] = {
    # Native HTTP response writers return an Int32 status, NOT a body handle.
    "http.responseHtml":      "Int32",
    "http.responseText":      "Int32",
    "http.responseBytes":     "Int32",
    "http.responseSseEvent":  "Int32",
    "http.responseHeader":    "Int32",
    "http.responseFile":      "Int32",
    # Request readers return text.
    "http.requestMethod":     "String",
    "http.requestPath":       "String",
    # Integer arithmetic returns its width; comparisons return Bool. Binding any
    # of these as an opaque HTML/JSON handle is a domain lie (caught by SS4302).
    "math.addInt64":          "Int64",
    "math.subtractInt64":     "Int64",
    "math.multiplyInt64":     "Int64",
    "math.divideInt64":       "Int64",
    "math.moduloInt64":       "Int64",
    "math.minInt64":          "Int64",
    "math.maxInt64":          "Int64",
    "math.clampInt64":        "Int64",
    "math.bitwiseAndInt64":   "Int64",
    "math.bitwiseOrInt64":    "Int64",
    "math.bitwiseXorInt64":   "Int64",
    "math.shiftLeftInt64":    "Int64",
    "math.shiftRightLogicalInt64":    "Int64",
    "math.shiftRightArithmeticInt64": "Int64",
    "math.equalInt64":            "Bool",
    "math.notEqualInt64":         "Bool",
    "math.lessThanInt64":         "Bool",
    "math.lessThanOrEqualInt64":  "Bool",
    "math.greaterThanInt64":      "Bool",
    "math.greaterThanOrEqualInt64": "Bool",
    "math.equalInt32":            "Bool",
    "math.lessThanInt32":         "Bool",
    "math.greaterThanInt32":      "Bool",
    "math.addFloat64":        "Float64",
    "math.subtractFloat64":   "Float64",
    "math.multiplyFloat64":   "Float64",
    "math.divideFloat64":     "Float64",
}


BUILTIN_TARGET_SIGNATURES: Dict[str, List[Tuple[str, str]]] = {
    # Console writes
    "console.writeLine":          [("console", "Console"), ("text", "String")],
    "console.writeIntegerLine":   [("console", "Console"), ("value", "Int64")],
    "console.writeInteger":       [("console", "Console"), ("value", "Int64")],
    "console.writeFloatLine":     [("console", "Console"), ("value", "Float64")],
    # Integer arithmetic
    "math.addInt64":                [("left", "Int64"), ("right", "Int64")],
    "math.subtractInt64":           [("left", "Int64"), ("right", "Int64")],
    "math.multiplyInt64":           [("left", "Int64"), ("right", "Int64")],
    "math.divideInt64":             [("left", "Int64"), ("right", "Int64")],
    "math.moduloInt64":             [("left", "Int64"), ("right", "Int64")],
    "math.minInt64":                [("left", "Int64"), ("right", "Int64")],
    "math.maxInt64":                [("left", "Int64"), ("right", "Int64")],
    "math.clampInt64":              [("value", "Int64"), ("low", "Int64"), ("high", "Int64")],
    "math.equalInt64":              [("left", "Int64"), ("right", "Int64")],
    "math.notEqualInt64":           [("left", "Int64"), ("right", "Int64")],
    "math.lessThanInt64":           [("left", "Int64"), ("right", "Int64")],
    "math.lessThanOrEqualInt64":    [("left", "Int64"), ("right", "Int64")],
    "math.greaterThanInt64":        [("left", "Int64"), ("right", "Int64")],
    "math.greaterThanOrEqualInt64": [("left", "Int64"), ("right", "Int64")],
    "math.equalInt32":              [("left", "Int32"), ("right", "Int32")],
    "math.notEqualInt32":           [("left", "Int32"), ("right", "Int32")],
    "math.lessThanInt32":           [("left", "Int32"), ("right", "Int32")],
    "math.lessThanOrEqualInt32":    [("left", "Int32"), ("right", "Int32")],
    "math.greaterThanInt32":        [("left", "Int32"), ("right", "Int32")],
    "math.greaterThanOrEqualInt32": [("left", "Int32"), ("right", "Int32")],
    "math.checkedMultiplyInt64":    [("left", "Int64"), ("right", "Int64")],
    # Bitwise / shift primitives (single-instruction LLVM lowerings).
    "math.bitwiseAndInt64":         [("left", "Int64"), ("right", "Int64")],
    "math.bitwiseOrInt64":          [("left", "Int64"), ("right", "Int64")],
    "math.bitwiseXorInt64":         [("left", "Int64"), ("right", "Int64")],
    "math.shiftLeftInt64":          [("left", "Int64"), ("right", "Int64")],
    "math.shiftRightLogicalInt64":  [("left", "Int64"), ("right", "Int64")],
    "math.shiftRightArithmeticInt64": [("left", "Int64"), ("right", "Int64")],
    "math.bitwiseNotInt64":         [("value", "Int64")],
    "math.signExtendInt32ToInt64": [("inputValue", "Int32")],
    "math.truncateInt64ToInt32":   [("inputValue", "Int64")],
    # Float arithmetic
    "math.addFloat64":                [("left", "Float64"), ("right", "Float64")],
    "math.subtractFloat64":           [("left", "Float64"), ("right", "Float64")],
    "math.multiplyFloat64":           [("left", "Float64"), ("right", "Float64")],
    "math.divideFloat64":             [("left", "Float64"), ("right", "Float64")],
    "math.equalFloat64":              [("left", "Float64"), ("right", "Float64")],
    "math.notEqualFloat64":           [("left", "Float64"), ("right", "Float64")],
    "math.lessThanFloat64":           [("left", "Float64"), ("right", "Float64")],
    "math.lessThanOrEqualFloat64":    [("left", "Float64"), ("right", "Float64")],
    "math.greaterThanFloat64":        [("left", "Float64"), ("right", "Float64")],
    "math.greaterThanOrEqualFloat64": [("left", "Float64"), ("right", "Float64")],
    # Numeric conversion
    "math.intToFloat":            [("inputValue", "Int64")],
    "math.floatToInt":            [("inputValue", "Float64")],
    "math.convertInt64ToFloat64": [("inputValue", "Int64")],
    "math.convertFloat64ToInt64": [("inputValue", "Float64")],
    # Pointer primitives
    "pointer.loadByte":           [("buffer", "OpaquePointer"), ("offset", "ByteCount")],
    "pointer.storeByte":          [("buffer", "OpaquePointer"), ("offset", "ByteCount"), ("value", "Int64")],
    "pointer.offset":             [("buffer", "OpaquePointer"), ("offset", "ByteCount")],
    "pointer.difference":         [("left", "OpaquePointer"), ("right", "OpaquePointer")],
    "pointer.isNull":             [("pointer", "OpaquePointer")],
    # Outbound network
    "net.fetchText":              [("request", "HttpGetRequest")],
    "net.fetchBytes":             [("url", "Url"), ("timeoutMillis", "NetworkTimeoutMilliseconds"), ("maxBodyBytes", "ResponseBodyLimitBytes")],
    "net.freeTextBody":           [("body", "HttpClientBodyText")],
    # C lib
    "c.malloc":                   [("size", "ByteCount")],
    "c.calloc":                   [("count", "ByteCount"), ("size", "ByteCount")],
    "c.realloc":                  [("ptr", "OpaquePointer"), ("size", "ByteCount")],
    "c.alignedAlloc":             [("alignment", "ByteCount"), ("size", "ByteCount")],
    "c.aligned_alloc":            [("alignment", "ByteCount"), ("size", "ByteCount")],
    "c.free":                     [("ptr", "OpaquePointer")],
    "c.exit":                     [("code", "Int32")],
    "c.abort":                    [],
    "c.putchar":                  [("c", "Int32")],
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
        ("resizable", "Int32"),
    ],
    "gui.textLabelCreate": [
        ("text", "GuiText"),
    ],
    "gui.textBoxCreate": [
        ("placeholder", "GuiText"),
        ("maxLength", "Int32"),
    ],
    "gui.buttonCreate": [
        ("text", "GuiText"),
        ("isDefault", "Int32"),
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
        ("handler", "GuiEventHandler"),
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
        ("text", "String"),
    ],
    "gui.listBoxSelectedIndex": [
        ("session", "GuiSession"),
        ("listBox", "GuiListBox"),
    ],
    "gui.listBoxAppendItem": [
        ("session", "GuiSession"),
        ("listBox", "GuiListBox"),
        ("text", "String"),
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
    "json.encode.Int64", "json.encode.UInt64",
    "json.encode.Int32", "json.encode.UInt32",
    "json.encode.Int16", "json.encode.UInt16",
    "json.encode.Int8", "json.encode.UInt8",
    "json.encode.DurationMilliseconds",
    "json.encode.MonotonicMilliseconds",
    "json.encode.UtcMilliseconds",
    "json.encode.Bool",
    "json.encode.Float64", "json.encode.Float32",
    "json.encode.String",
    "json.decode.Int64", "json.decode.UInt64",
    "json.decode.Int32", "json.decode.UInt32",
    "json.decode.Int16", "json.decode.UInt16",
    "json.decode.Int8", "json.decode.UInt8",
    "json.decode.DurationMilliseconds",
    "json.decode.MonotonicMilliseconds",
    "json.decode.UtcMilliseconds",
    "json.decode.Bool",
    "json.decode.Float64", "json.decode.Float32",
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
    "json.createDocument", "json.createEmptyDocument", "json.destroyDocument",
    "json.serializeDocument", "json.documentLength", "json.documentRoot",
    "json.objectFieldAt", "json.arrayElementAt", "json.cursorParent",
    "json.cursorAtPath", "json.cursorKind", "json.cursorIsNull",
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

JSON_FALLIBLE_CURSOR_NAVIGATOR_TARGETS: frozenset = frozenset({
    "json.objectFieldAt",
    "json.arrayElementAt",
    "json.cursorParent",
    "json.cursorAtPath",
    "json.cursorObjectFieldValueAt",
})

JSON_STRUCTURAL_CURSOR_MUTATOR_TARGETS: frozenset = frozenset({
    "json.removeObjectField",
    "json.removeArrayElementAt",
    "json.clearObject",
    "json.clearArray",
    "json.setObjectFieldObject",
    "json.setObjectFieldArray",
    "json.insertArrayElementString",
    "json.insertArrayElementInt64",
    "json.insertArrayElementDouble",
    "json.insertArrayElementBool",
    "json.insertArrayElementNull",
    "json.insertArrayElementObject",
    "json.insertArrayElementArray",
    "json.insertArrayElementJsonText",
    "json.replaceArrayElementObject",
    "json.replaceArrayElementArray",
    "json.replaceArrayElementJsonText",
})

DEPRECATED_JSON_BUILDER_TARGETS: frozenset = frozenset({
    "json.createBuilder", "json.destroyBuilder",
    "json.finishBuilder", "json.builderLength",
    "json.objectOpen", "json.objectClose",
    "json.arrayOpen", "json.arrayClose",
    "json.fieldInt64", "json.fieldDouble", "json.fieldBool",
    "json.fieldString", "json.fieldNull",
    "json.elementInt64", "json.elementDouble", "json.elementBool",
    "json.elementString", "json.elementNull",
})

DEPRECATED_JSON_FINDER_TARGETS: frozenset = frozenset({
    "json.findString", "json.findInt64", "json.findDouble",
    "json.findBool", "json.hasField",
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
    "module": 1, "section": 1, "import": 2, "importModule": 1,
    "importOperation": 3, "importType": 3, "importError": 3,
    "importCapability": 3, "importConstant": 3,
    "buildProject": 1, "modulePath": 2, "languageVersion": 2,
    "sourceRoot": 2, "mainFile": 2, "mainOperation": 2,
    "testPattern": 2, "dependencySource": 3, "dependencyFetch": 4,
    "dependencyCache": 2, "dependencyLock": 2, "dependencyIntegrity": 3,
    "buildProfile": 2, "runtimeChecks": 2, "asyncRuntime": 2, "guiBackend": 2, "persistLlvmIr": 2,
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
    "buildConstant": 4,
    "moduleFolder": 2, "modulePurpose": 2, "moduleOwns": 2,
    "moduleDoesNotOwn": 2, "moduleDependency": 2, "moduleWarning": 2,
    "moduleInvariant": 2, "moduleSecurity": 2, "moduleObservability": 2,
    "nativeRuntimeSource": 2, "nativeRuntimeLinkArg": 2,
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
    "recordFieldJsonName": 3, "recordFieldJsonOmitWhen": 3,
    "new": 2, "fieldSet": 3, "fieldGet": 4,
    "error": 1, "errorCase": 2, "enum": 1, "enumCase": 2,
    # HTML / SSX / JSON islands
    "html": 2, "htmlTemplate": 1, "htmlArg": 3, "htmlBody": 1,
    "jsonBody": 1, "sql": 2, "sqlBody": 1,
    # Operations + narrative
    "operation": 1, "operationBody": 2,
    "input": 4, "output": 3, "effect": 3,
    "memory": 3, "memoryHeap": 2, "memoryArena": 2, "memoryStackLimit": 2,
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
    "call": 2, "argument": 4, "arg": 3, "timeout": 2, "cancelOn": 2,
    "run": 1, "runChecked": 9, "start": 1, "await": 1,
    "bind": 4, "bindOk": 3, "bindError": 3,
    "ignore": 3, "ignoreOk": 2, "ignoreValue": 2, "ignoreError": 1,
    "makeError": 2, "declareFailure": 2,
    # Control flow
    "label": 1, "branch": 3, "jump": 2, "branchIf": 2, "branchIfError": 2,
    "branchIfGroupError": 2, "branchIfChannelClosed": 2, "branchSelected": 3,
    "return": 1, "returnOk": 1, "returnError": 1, "returnValue": 1,
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
    "case": 2, "done": 1,
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
    "runtimeBinding": 2, "runtimeBindingAsyncStart": 2,
    "runtimeBindingAsyncAwait": 2, "intrinsicName": 2,
    # Constants
    "const": 3, "var": 3, "let": 3,
}


# Verbs that reference a `call NAME TARGET` declaration at args[0]. Used by
# SS4101 reference-integrity checks.
CALL_REFERENCE_VERBS_AT_ARG_ZERO: frozenset = frozenset({
    "arg", "argument", "run", "runChecked", "start", "await",
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
    "operationBody", "runtimeBindingAsyncStart", "runtimeBindingAsyncAwait",
    "useCapability", "authority",
    # SS36xx explicit contract verbs — args[0] is the owning operation.
    "pinsNullBodyFailurePath",
    "responseBodyForwarder",
})


# Comprehensive vocabulary built from docs/reference/syntax-inventory.md. Verbs missing from this
# set are reported as SS0001 unknownVerb at T0 (parse / grammar). Additive
# refinements to SemanticScript land in docs/reference/syntax-inventory.md first, then in this set — keeping
# both in lockstep is the linter's job over time.
KNOWN_AGENT_SCRIPT_VERBS: frozenset = frozenset({
    # Project structure
    "project", "target", "runtime", "entry", "module", "mode", "languageMode",
    "buildProject", "modulePath", "languageVersion", "sourceRoot",
    "mainFile", "mainOperation", "testPattern", "dependency", "dependencySource",
    "dependencyFetch", "dependencyCache", "dependencyLock", "dependencyIntegrity",
    "buildProfile", "runtimeChecks", "asyncRuntime", "guiBackend", "persistLlvmIr",
    "nativeOutput", "targetRuntime", "comptimeOperation", "registerModule",
    "buildConstant",
    "projectVersion", "projectLicense", "testRoot", "nativeHttpHost",
    "nativeHttpPort", "formatterSetting", "linterSetting", "docsOutput",
    "optLevel", "emitLlvmIr", "llvmIrOutput", "emitOptimizedLlvmIr",
    "optimizedLlvmIrOutput", "buildDir", "buildRoot", "buildFolderName",
    "cpuBaseline", "cpuTune", "cpuFeature", "cpuFeatureCheck",
    "keepResources", "resourcesDir",
    "moduleFolder", "modulePurpose", "moduleOwns", "moduleDoesNotOwn",
    "moduleDependency", "moduleWarning", "moduleInvariant", "moduleSecurity",
    "moduleObservability",
    "nativeRuntimeSource", "nativeRuntimeLinkArg",
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
    "import", "importModule", "importOperation", "importType", "importError",
    "importCapability", "importConstant", "section",
    # Groups
    "group", "groupPurpose", "groupInput", "groupOutput", "groupError",
    "groupFailure", "groupTiming",
    # Types
    "type", "typeInvariant", "typeRepresentation", "typeTrust", "typeMemory",
    "typeLayout", "typeParameter", "typeLiteralEncoding", "typeLiteralTerminator",
    # Records
    "record", "field", "recordLayout", "recordAlign",
    "recordFieldJsonName", "recordFieldJsonOmitWhen", "recordConstructor",
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
    "call", "argument", "arg", "timeout", "cancelOn", "run", "runChecked",
    "start", "await",
    "case", "done",
    "bind", "bindOk", "bindError", "ignore", "ignoreOk", "ignoreValue", "ignoreError",
    "makeError", "declareFailure",
    # Control flow
    "label", "branch", "jump", "branchIf", "branchIfError",
    "return", "returnOk", "returnError", "returnValue", "returnVoid",
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
    "routeNotFound", "routeMethodNotAllowed",
    "webServerStartup", "webServerShutdown",
    "routeTimeout", "routeMiddleware",
    "html", "htmlTemplate", "htmlArg", "htmlBody", "jsonBody", "sql", "sqlBody",
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
    "runtimeBindingAsyncStart", "runtimeBindingAsyncAwait", "intrinsicName",
    # Token literals that may appear standalone
    "const", "var", "let", "testCovers",
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
    moduleWorkerPools: Dict[str, SourceLine] = field(default_factory=dict)
    operationWorkerPools: Dict[str, Dict[str, SourceLine]] = field(default_factory=dict)
    operationWorkTargets: Dict[str, Dict[str, List[Tuple[SourceLine, Optional[str]]]]] = field(default_factory=dict)
    operationWorkArgs: Dict[str, Dict[str, Dict[str, List[SourceLine]]]] = field(default_factory=dict)
    operationSubmittedWork: Dict[str, List[Tuple[SourceLine, str, str]]] = field(default_factory=dict)
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
            owner = args[1] if verb in {"purpose", "invariant"} and len(args) >= 3 and args[0] in {"module", "operation"} else args[0]
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
        elif verb in {
            "branch", "jump", "branchIf", "branchIfError",
            "branchIfGroupError", "branchIfChannelClosed",
            "branchSelected", "runChecked", "case", "done",
        }:
            facts.labelReferences.update(branch_target_names_from_row(sourceLine))
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
        elif verb == "memory":
            memory = memory_parts(sourceLine)
            if memory is not None and memory[1] in {"mutable", "immutable"} and len(memory[2]) >= 2:
                operationName, mutability, rest = memory
                facts.storageSlots[rest[0]] = StorageFact(
                    rest[0], sourceLine, f"memory.{operationName}", mutability)
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
        elif verb in {"memory", "memoryHeap", "memoryArena", "memoryStackLimit"}:
            memory = memory_parts(sourceLine)
            if memory is None:
                continue
            operationName, subkind, rest = memory
            if subkind == "heap" and rest:
                heapAllowed = rest[0].lower() in {"yes", "true"}
                facts.operationMemoryHeapAllowed[operationName] = (sourceLine, heapAllowed)
            elif subkind == "stack" and len(rest) >= 2 and rest[0] == "max":
                try:
                    stackLimitBytes = int(rest[1])
                    facts.operationMemoryStackLimitBytes[operationName] = (sourceLine, stackLimitBytes)
                except ValueError:
                    pass
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
        elif verb == "workerPool" and args:
            if currentOperation:
                facts.operationWorkerPools.setdefault(currentOperation, {})[args[0]] = sourceLine
            else:
                facts.moduleWorkerPools[args[0]] = sourceLine
        elif verb == "work" and args and currentOperation:
            targetOperation = args[2] if len(args) >= 3 and args[1] == "target" else None
            facts.operationWorkTargets.setdefault(currentOperation, {}).setdefault(
                args[0],
                [],
            ).append((
                sourceLine,
                targetOperation,
            ))
        elif verb == "workArg" and len(args) >= 3 and currentOperation:
            facts.operationWorkArgs.setdefault(currentOperation, {}).setdefault(
                args[0],
                {},
            ).setdefault(args[1], []).append(sourceLine)
        elif verb == "submitWork" and len(args) >= 2 and currentOperation:
            # `submitWork WORK POOL` — first arg is the work item name
            facts.operationSubmittedWork.setdefault(currentOperation, []).append(
                (sourceLine, args[0], args[1])
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
        if len(narrativeLine.args) >= 3 and ((edgeKind == "purpose" and narrativeLine.args[0] in PURPOSE_SUBJECT_KINDS) or (edgeKind == "invariant" and narrativeLine.args[0] in {"module", "operation"})):
            text = narrativeLine.args[2]
        else:
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
        bind = bind_parts(sourceLine)
        argument = argument_parts(sourceLine)
        ignore = ignore_parts(sourceLine)
        branchErrorSource = branch_error_source(sourceLine)
        # Most call-attachment verbs use args[0] as the call name
        if argument is not None:
            target = operationCalls.get(argument[0])
        elif ignore is not None:
            target = operationCalls.get(ignore[1])
        elif branchErrorSource is not None:
            target = operationCalls.get(branchErrorSource)
        elif verb == "case" and len(args) >= 2:
            target = operationCalls.get(args[0])
        elif verb in {
            "run", "runChecked", "start", "await", "startInGroup",
            "timeout", "cancelOn",
        }:
            target = operationCalls.get(args[0])
        elif bind is not None:
            target = operationCalls.get(bind[3])
        if target is None:
            continue
        if argument is not None:
            target.arg_lines.append(sourceLine)
        elif verb == "run":
            target.run_lines.append(sourceLine)
        elif verb == "runChecked":
            target.run_checked_lines.append(sourceLine)
        elif verb == "start":
            target.start_lines.append(sourceLine)
        elif verb == "await":
            target.await_lines.append(sourceLine)
        elif verb == "case":
            target.await_lines.append(sourceLine)
        elif bind is not None and bind[0] == "value":
            target.bind_lines.append(sourceLine)
        elif bind is not None and bind[0] == "ok":
            target.bind_ok_lines.append(sourceLine)
        elif bind is not None and bind[0] == "error":
            target.bind_error_lines.append(sourceLine)
        elif ignore is not None and ignore[0] == "ok":
            target.ignore_ok_lines.append(sourceLine)
        elif ignore is not None and ignore[0] == "value":
            target.ignore_value_lines.append(sourceLine)
        elif ignore is not None and ignore[0] == "error":
            target.ignore_error_lines.append(sourceLine)
        elif ignore is not None and ignore[0] == "void":
            target.ignore_void_lines.append(sourceLine)
        elif branchErrorSource is not None:
            target.branch_error_lines.append(sourceLine)
        elif verb == "startInGroup":
            target.group_start_lines.append(sourceLine)
        elif verb == "timeout":
            target.timeout_lines.append(sourceLine)
        elif verb == "cancelOn":
            target.cancel_lines.append(sourceLine)
    return operationCalls


def wait_set_await_line_numbers(operation: OperationFact) -> Set[int]:
    """Return `await NAME` rows that introduce an await/case/done wait set.

    In that shape NAME is a local wait-set label for diagnostics/tracing, not a
    declared `call NAME TARGET`, so call-reference checks must not resolve it.
    """
    wait_set_lines: Set[int] = set()
    lines = operation.lines
    for index, sourceLine in enumerate(lines):
        if (is_comment(sourceLine) or not sourceLine.tokens
                or sourceLine.verb != "await" or not sourceLine.args):
            continue
        next_index = index + 1
        while next_index < len(lines):
            next_line = lines[next_index]
            if is_comment(next_line) or not next_line.tokens:
                next_index += 1
                continue
            if next_line.verb in {"case", "done"}:
                wait_set_lines.add(sourceLine.number)
            break
    return wait_set_lines


def operation_async_enabled(operation: OperationFact) -> bool:
    for sourceLine in operation.lines:
        if (sourceLine.verb == "async" and len(sourceLine.args) >= 2
                and sourceLine.args[0] == operation.name
                and sourceLine.args[1].lower() in {"yes", "true", "1", "on"}):
            return True
    return False


def call_can_start_async_future(
    facts: ExtendedFacts,
    operation: OperationFact,
    callFact: CallFact,
) -> bool:
    target = callFact.target
    if target in {"net.fetchText", "fetchText", "standard.net.fetchText"}:
        return True
    if not operation_async_enabled(operation):
        return False
    if target in facts.base.operations:
        return True
    return False


def source_row_terminates_before_next_label(sourceLine: SourceLine) -> bool:
    if sourceLine.verb in {"jump", "return", "returnOk", "returnError", "returnVoid"}:
        return True
    if sourceLine.verb == "branch" and len(sourceLine.args) >= 3 and sourceLine.args[0] == "else":
        return True
    return False


def source_line_reachable_numbers(operation: OperationFact) -> Set[int]:
    lines = operation.lines
    if not lines:
        return set()
    branchElseByLine = branch_else_targets_by_line(lines)
    labelIndices = {
        sourceLine.args[0]: index
        for index, sourceLine in enumerate(lines)
        if sourceLine.verb == "label" and sourceLine.args
    }

    def add_label_successor(successors: List[int], labelName: str) -> None:
        targetIndex = labelIndices.get(labelName)
        if targetIndex is not None:
            successors.append(targetIndex)

    def add_fallthrough_successor(successors: List[int], index: int) -> None:
        nextIndex = index + 1
        if nextIndex < len(lines):
            successors.append(nextIndex)

    def successor_indices(index: int) -> List[int]:
        sourceLine = lines[index]
        args = sourceLine.args
        successors: List[int] = []
        if sourceLine.verb == "await":
            cursor = index + 1
            foundWaitSetRows = False
            while cursor < len(lines):
                candidate = lines[cursor]
                if is_comment(candidate) or not candidate.tokens:
                    cursor += 1
                    continue
                if candidate.verb == "case":
                    foundWaitSetRows = True
                    if len(candidate.args) >= 2:
                        add_label_successor(successors, candidate.args[1])
                    cursor += 1
                    continue
                if candidate.verb == "done":
                    foundWaitSetRows = True
                    if candidate.args:
                        add_label_successor(successors, candidate.args[0])
                    break
                break
            if foundWaitSetRows:
                return successors
        if sourceLine.verb in {"return", "returnOk", "returnError", "returnVoid"}:
            return successors
        if sourceLine.verb == "jump" and len(args) >= 2 and args[0] == "target":
            add_label_successor(successors, args[1])
            return successors
        if sourceLine.verb == "branch":
            if len(args) >= 5 and args[0] in {"if", "error"} and args[3] == "target":
                add_label_successor(successors, args[4])
                elseLabel = branchElseByLine.get(sourceLine.number)
                if elseLabel is None:
                    add_fallthrough_successor(successors, index)
                else:
                    add_label_successor(successors, elseLabel)
                return successors
            if len(args) >= 3 and args[0] == "else" and args[1] == "target":
                add_label_successor(successors, args[2])
                return successors
            if args:
                add_label_successor(successors, args[0])
                add_fallthrough_successor(successors, index)
                return successors
        if sourceLine.verb == "branchIf" and len(args) >= 2:
            add_label_successor(successors, args[1])
            if len(args) >= 3:
                add_label_successor(successors, args[2])
            else:
                add_fallthrough_successor(successors, index)
            return successors
        if sourceLine.verb in {"branchIfError", "branchIfGroupError", "branchIfChannelClosed"} and len(args) >= 2:
            add_label_successor(successors, args[1])
            add_fallthrough_successor(successors, index)
            return successors
        if sourceLine.verb == "runChecked" and len(args) >= 9:
            add_label_successor(successors, args[8])
            add_fallthrough_successor(successors, index)
            return successors
        if sourceLine.verb == "branchSelected" and len(args) >= 3:
            add_label_successor(successors, args[2])
            add_fallthrough_successor(successors, index)
            return successors
        add_fallthrough_successor(successors, index)
        return successors

    reachableIndices: Set[int] = set()
    stack = [0]
    while stack:
        currentIndex = stack.pop()
        if currentIndex in reachableIndices:
            continue
        reachableIndices.add(currentIndex)
        stack.extend(successor_indices(currentIndex))
    return {lines[index].number for index in reachableIndices}


def start_reaches_wait_set_entry(
    operation: OperationFact,
    callFact: CallFact,
    awaitLine: SourceLine,
) -> bool:
    priorStartLines = [
        startLine
        for startLine in callFact.start_lines
        if startLine.number < awaitLine.number
    ]
    branchElseByLine = branch_else_targets_by_line(operation.lines)
    reachableLineNumbers = source_line_reachable_numbers(operation)
    for startLine in reversed(priorStartLines):
        if startLine.number not in reachableLineNumbers:
            continue
        blockedByTerminator = False
        for sourceLine in operation.lines:
            if sourceLine.number not in reachableLineNumbers:
                continue
            if sourceLine.number >= startLine.number:
                break
            if sourceLine.verb == "label":
                blockedByTerminator = False
                continue
            if source_row_terminates_before_next_label(sourceLine):
                blockedByTerminator = True
        if blockedByTerminator:
            continue
        interveningLabelNames = {
            sourceLine.args[0]
            for sourceLine in operation.lines
            if (sourceLine.verb == "label" and sourceLine.args
                and startLine.number < sourceLine.number < awaitLine.number)
        }
        bypassesStart = False
        for sourceLine in operation.lines:
            if sourceLine.number not in reachableLineNumbers:
                continue
            if sourceLine.number >= startLine.number:
                continue
            if interveningLabelNames & set(branch_target_names_with_attached_else(
                    sourceLine, branchElseByLine)):
                bypassesStart = True
                break
        if not bypassesStart:
            return True
    return False


def operation_input_types(operation: OperationFact) -> Dict[str, str]:
    inputs: Dict[str, str] = {}
    for sourceLine in operation.lines:
        if is_comment(sourceLine) or not sourceLine.tokens:
            continue
        parsed = input_parts(sourceLine)
        if parsed is not None and parsed[0] == operation.name:
            inputs[parsed[1]] = parsed[2]
    return inputs


def operation_declares_result_output(operation: OperationFact, program: ProgramFacts) -> bool:
    for sourceLine in operation.lines:
        if is_comment(sourceLine) or not sourceLine.tokens:
            continue
        parsed = output_parts(sourceLine)
        if parsed is None or parsed[0] != operation.name:
            continue
        if parsed[1] == "Result":
            return True
        alias_target = program.type_aliases.get(parsed[1])
        if alias_target == "result":
            return True
    return False


def result_returning_operation_names(program: ProgramFacts) -> Set[str]:
    return {
        operation.name
        for operation in program.operations.values()
        if operation_declares_result_output(operation, program)
    }


def call_arg_values(callFact: CallFact) -> Dict[str, List[str]]:
    values: Dict[str, List[str]] = {}
    for argLine in callFact.arg_lines:
        parsed = argument_parts(argLine)
        if parsed is not None:
            _callName, argumentName, _declaredType, suppliedValue = parsed
            values.setdefault(argumentName, []).append(suppliedValue)
    return values


def call_arg_value(callFact: CallFact, argumentName: str) -> Optional[str]:
    values = call_arg_values(callFact).get(argumentName)
    if not values:
        return None
    return values[-1]


def call_success_value_names(callFact: CallFact) -> Set[str]:
    """Names that carry a call's successful return value in this operation."""
    names: Set[str] = set()
    for bindLine in callFact.bind_lines + callFact.bind_ok_lines:
        parsed = bind_parts(bindLine)
        if parsed is not None:
            names.add(parsed[1])
    return names


def call_success_value_lines(callFact: CallFact) -> List[Tuple[str, SourceLine]]:
    values: List[Tuple[str, SourceLine]] = []
    for bindLine in callFact.bind_lines + callFact.bind_ok_lines:
        parsed = bind_parts(bindLine)
        if parsed is not None:
            values.append((parsed[1], bindLine))
    return values


def call_has_value_disposition(callFact: CallFact) -> bool:
    """Whether a non-Result C-style call return is bound or explicitly ignored."""
    return bool(
        callFact.bind_lines
        or callFact.bind_ok_lines
        or callFact.run_checked_lines
        or callFact.ignore_value_lines
        or callFact.ignore_ok_lines
        or callFact.ignore_void_lines
    )


def call_result_success_disposition_lines(callFact: CallFact) -> List[SourceLine]:
    """Rows that explicitly dispose the success side of a Result-shaped call."""
    return callFact.bind_ok_lines + callFact.ignore_ok_lines + callFact.ignore_void_lines


def call_consumes_any_value(callFact: CallFact, valueNames: Set[str]) -> bool:
    if not valueNames:
        return False
    for argLine in callFact.arg_lines:
        parsed = argument_parts(argLine)
        if parsed is not None and parsed[3] in valueNames:
            return True
    return False


def defer_consumes_any_value(
    deferLines: List[Tuple[SourceLine, str]],
    cleanupTargets: Set[str],
    valueNames: Set[str],
    afterLine: Optional[int] = None,
) -> bool:
    if not valueNames:
        return False
    for deferLine, deferTarget in deferLines:
        if deferTarget not in cleanupTargets:
            continue
        if afterLine is not None and deferLine.number <= afterLine:
            continue
        if any(arg in valueNames for arg in deferLine.args[2:]):
            return True
    return False


def operation_label_body_lines(operation: OperationFact, labelName: str) -> List[SourceLine]:
    labelIndex: Optional[int] = None
    for index, sourceLine in enumerate(operation.lines):
        if (not is_comment(sourceLine) and sourceLine.tokens
                and sourceLine.verb == "label" and sourceLine.args
                and sourceLine.args[0] == labelName):
            labelIndex = index
            break
    if labelIndex is None:
        return []
    bodyLines: List[SourceLine] = []
    for sourceLine in operation.lines[labelIndex + 1:]:
        if (not is_comment(sourceLine) and sourceLine.tokens
                and sourceLine.verb == "label"):
            break
        bodyLines.append(sourceLine)
    return bodyLines


def label_body_calls_cleanup_for_value(
    operation: OperationFact,
    labelName: str,
    cleanupTargets: Set[str],
    valueNames: Set[str],
) -> bool:
    if not valueNames:
        return False
    labelLines = operation_label_body_lines(operation, labelName)
    if not labelLines:
        return False
    labelOperation = OperationFact(operation.name, operation.line, labelLines)
    labelCalls = collect_operation_calls(labelOperation)
    for cleanupCall in labelCalls.values():
        if cleanupCall.target not in cleanupTargets:
            continue
        if call_consumes_any_value(cleanupCall, valueNames):
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


def _line_declares_value(sourceLine: SourceLine, valueName: str) -> bool:
    if is_comment(sourceLine) or not sourceLine.tokens or not sourceLine.args:
        return False
    verb = sourceLine.verb
    args = sourceLine.args
    bind = bind_parts(sourceLine)
    if bind is not None:
        return bind[1] == valueName
    if verb in {"const", "var", "let", "literal",
                "domainLiteral", "makeError", "declareFailure", "receive"}:
        return args[0] == valueName
    if verb == "storage" and len(args) >= 3:
        return args[2] == valueName
    memory = memory_parts(sourceLine)
    if memory is not None and memory[1] in {"mutable", "immutable"} and len(memory[2]) >= 2:
        return memory[2][0] == valueName
    if verb == "sharedState" and len(args) >= 3:
        return args[2] == valueName
    parsedInput = input_parts(sourceLine)
    if parsedInput is not None:
        return parsedInput[1] == valueName
    if verb == "read" and len(args) >= 2:
        return args[1] == valueName
    return False


def _line_uses_value(sourceLine: SourceLine, valueName: str) -> bool:
    if is_comment(sourceLine) or not sourceLine.tokens:
        return False
    if _line_declares_value(sourceLine, valueName):
        return False
    return any(token.text == valueName for token in sourceLine.tokens)


def _first_value_use_after_line(
    operation: OperationFact,
    valueName: str,
    afterLineNumber: int,
) -> Optional[SourceLine]:
    for sourceLine in operation.lines:
        if sourceLine.number <= afterLineNumber:
            continue
        if _line_uses_value(sourceLine, valueName):
            return sourceLine
    return None


def _literal_assignment(sourceLine: SourceLine) -> Optional[Tuple[str, str, str]]:
    if is_comment(sourceLine) or not sourceLine.tokens:
        return None
    args = sourceLine.args
    if sourceLine.verb in {"const", "literal"} and len(args) >= 3:
        return args[0], args[1], args[2]
    if sourceLine.verb == "storage" and len(args) >= 5:
        return args[2], args[3], args[4]
    memory = memory_parts(sourceLine)
    if memory is not None and memory[1] in {"mutable", "immutable"} and len(memory[2]) >= 3:
        return memory[2][0], memory[2][1], memory[2][2]
    return None


def _module_literal_assignments(facts: ExtendedFacts) -> Dict[str, Tuple[str, str, SourceLine]]:
    operationLineKeys = {
        (sourceLine.path, sourceLine.number)
        for operation in facts.base.operations.values()
        for sourceLine in operation.lines
    }
    literals: Dict[str, Tuple[str, str, SourceLine]] = {}
    for sourceLine in facts.base.lines:
        if (sourceLine.path, sourceLine.number) in operationLineKeys:
            continue
        assignment = _literal_assignment(sourceLine)
        if assignment is None:
            continue
        name, typeName, value = assignment
        literals[name] = (typeName, value, sourceLine)
    return literals


def _operation_literal_assignments(
    facts: ExtendedFacts,
    operation: OperationFact,
) -> Dict[str, Tuple[str, str, SourceLine]]:
    literals = dict(_module_literal_assignments(facts))
    for sourceLine in operation.lines:
        assignment = _literal_assignment(sourceLine)
        if assignment is None:
            continue
        name, typeName, value = assignment
        literals[name] = (typeName, value, sourceLine)
    return literals


def _json_path_malformed_reason(pathText: str) -> Optional[str]:
    if pathText == "":
        return None

    index = 0
    while index < len(pathText):
        current = pathText[index]
        if current == ".":
            index += 1
            if index >= len(pathText) or pathText[index] in {".", "["}:
                return "emptyObjectFieldSegment"
            while index < len(pathText) and pathText[index] not in {".", "["}:
                if pathText[index] == "]":
                    return "malformedObjectFieldSegment"
                if pathText[index] == "\\":
                    if index + 1 < len(pathText) and pathText[index + 1] == ".":
                        index += 2
                        continue
                    return "malformedObjectFieldEscape"
                index += 1
            continue
        if current == "[":
            closeIndex = pathText.find("]", index + 1)
            if closeIndex == -1:
                return "unmatchedArrayIndexBracket"
            indexText = pathText[index + 1:closeIndex]
            if not indexText or not indexText.isdigit():
                return "nonNumericArrayIndex"
            index = closeIndex + 1
            continue
        return "pathStepMustStartWithDotOrBracket"
    return None


def _format_contains_json_string_percent_s(formatText: str) -> bool:
    if "%s" not in formatText:
        return False
    if not any(marker in formatText for marker in ("{", ":", ",")):
        return False

    searchIndex = 0
    while True:
        percentIndex = formatText.find("%s", searchIndex)
        if percentIndex == -1:
            return False
        if percentIndex > 0 and formatText[percentIndex - 1] == "%":
            searchIndex = percentIndex + 2
            continue
        priorQuote = formatText.rfind('"', 0, percentIndex)
        nextQuote = formatText.find('"', percentIndex + 2)
        if priorQuote != -1 and nextQuote != -1:
            return True
        searchIndex = percentIndex + 2


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
#            SS3109 authorityEffectMismatch,
#            SS3110 columnUseAfterFree,
#            SS3111 undeclaredBodyEffect, SS3112 unknownErrorVariant
#   AS32xx — performance discipline           (T3 refinement)
#            SS3201 deadStore, SS3202 allocationInLoop,
#            SS3203 stringAccumulatorAppendInLoop,
#            SS3204 bindThenIgnore,
#            SS3205 snprintfInt32OffsetWithoutWidening,
#            SS3206 selectedListAppendInHandler,
#            SS3207 rowCountMutationUnchecked,
#            SS3208 loopInvariantPureCall
#   AS33xx — memory / resource discipline     (T3 refinement)
#            SS3301 heapContradiction, SS3302 allocationSourceMissing,
#            SS3303 allocateFreeUnpaired, SS3304 stackLimitOverrun,
#            SS3305 uncheckedHeapAllocation
#   AS34xx — layout / representation          (T3 refinement)
#            SS3401 recordAlignNotPowerOfTwo, SS3404 arrayLengthZero,
#            SS3405 inlineCapacityWithoutSpillAllocator,
#            SS3406 literalEncodingMissing
#   SS35xx — concurrency discipline           (T3 refinement)
#            SS3501 unawaitedTaskGroup, SS3503 lockWithoutCleanup,
#            SS3506 unawaitedSubmitWork, SS3507 selectWithoutCases,
#            SS3508 selectCaseReferencesUnknownSelect,
#            SS3510 asyncCallMissingBoundary
#   SS36xx — JSON / webserver discipline      (T3 refinement / T1 spec)
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
#                   MiddlewareControl` not bare Int32; ERROR +
#                   blocksCompile because the dispatcher's short-circuit
#                   semantics depend on the typed enum),
#            SS3612 voidReturnValueShouldBeReturnVoid (an op declared
#                   `output OP Void` should end with `returnVoid`, not
#                   `returnValue NAME` — the legacy form leaks the
#                   user-op ABI's i32 sentinel into the source),
#            SS3613 narrativeReferencesLineNumber (narrative attachments
#                   should cite STABLE identifiers — function names,
#                   rule IDs, grep-anchors — never `<file>:<line>` or
#                   `line <N>` patterns that drift on the next edit),
#            SS3615 responseBodyForwarderMissing (user-op wrappers around
#                   http.responseText/Bytes/SSE must declare the forwarded
#                   body input so SS3603 remains transitive),
#            SS3617 lifecycleHookContract (webServerStartup /
#                   webServerShutdown handlers must exist, take no inputs,
#                   and return Int32),
#            SS3620 unguardedJsonAccess, SS3621 staleJsonCursor,
#            SS3622 malformedJsonPath, SS3623 unescapedJsonStringInterpolation,
#            SS3624 deprecatedJsonBuilderCall,
#            SS3625 deprecatedJsonFinderCall
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
#            SS3904 guardTokenDoesNotProtectSharedState,
#            SS3905 sqliteDatabaseFailureCleanupMissing,
#            SS3906 sqliteStatementFinalizeMissing
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
                callFact.run_lines or callFact.run_checked_lines
                or callFact.start_lines or callFact.group_start_lines
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
                specAnchor="docs/reference/syntax-inventory.md#call",
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
            specAnchor="docs/reference/syntax-inventory.md#label",
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


def _is_unreachable_operation_row_candidate(sourceLine: SourceLine) -> bool:
    if is_comment(sourceLine) or not sourceLine.tokens:
        return False
    if sourceLine.verb in {"__typedComment__", "__groupAnchor__"}:
        return False
    return True


def check_unreachable_operation_rows(facts: ExtendedFacts) -> List[Diagnostic]:
    """SS3630 - rows after terminal control-flow that are not reachable by
    branch/jump edges are stale executable context. This catches old blocks
    left behind after response fast paths or SQL flow rewrites.
    """
    diagnostics: List[Diagnostic] = []
    for operation in facts.base.operations.values():
        reachableLineNumbers = source_line_reachable_numbers(operation)
        # `branch else target L` rows attached to a preceding `branch if/error`
        # are consumed by the CFG model as that branch's else-edge (see
        # source_line_reachable_numbers / branch_else_targets_by_line), so the
        # else ROW itself never lands in reachableLineNumbers even though it is a
        # live control-flow edge. Exempt those rows; they are the idiomatic
        # two-line conditional, not stale unreachable code.
        attachedElseLineNumbers: Set[int] = set()
        lines = operation.lines
        for index in range(len(lines) - 1):
            current = lines[index]
            if current.verb == "branch" and current.args and current.args[0] in {"if", "error"}:
                nextLine = lines[index + 1]
                if nextLine.verb == "branch" and nextLine.args[:2] == ["else", "target"]:
                    attachedElseLineNumbers.add(nextLine.number)
        for sourceLine in operation.lines:
            if sourceLine.number in reachableLineNumbers:
                continue
            if sourceLine.number in attachedElseLineNumbers:
                continue
            if not _is_unreachable_operation_row_candidate(sourceLine):
                continue
            diagnostics.append(Diagnostic(
                tier=Tier.T3_REFINEMENT,
                code="SS3630",
                kind="controlFlow.unreachableRow",
                severity=Severity.WARNING,
                subjectName=(sourceLine.args[0] if sourceLine.args else sourceLine.verb),
                subjectKind=sourceLine.verb,
                gapEdge="controlReachability",
                intentSlogan="unreachable operation row",
                primary=span_of_line(sourceLine, "unreachableRow"),
                related=[span_of_line(operation.line, "enclosingOperation")],
                invariantRule=(
                    "every executable operation row must be reachable from the "
                    "operation entry through fallthrough, branch, jump, await, "
                    "or runChecked edges"
                ),
                specAnchor="docs/reference/syntax-inventory.md#control-flow",
                fixCandidates=[
                    FixCandidate(
                        name="removeUnreachableBlock",
                        shape="# remove the stale rows, or add an explicit branch/jump if this block is intended",
                        evidence=[span_of_line(sourceLine)],
                    ),
                ],
                confidence=Confidence.HIGH,
                blocksCompile=False,
                effort=Effort.LOCAL,
                passProvenance="check_unreachable_operation_rows",
                agentHint=(
                    "dead operation rows still consume compiler context and "
                    "can hide obsolete resource or SQL paths"
                ),
            ))
            break
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
            specAnchor="docs/reference/syntax-inventory.md#capability",
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
            specAnchor="docs/reference/syntax-inventory.md#errorCase",
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
            specAnchor="docs/reference/syntax-inventory.md#storage",
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
            specAnchor="docs/reference/syntax-inventory.md#retryPolicy",
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
            specAnchor="docs/reference/syntax-inventory.md#trustBoundary",
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
            specAnchor="docs/reference/syntax-inventory.md#literalDigest",
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
                specAnchor=f"docs/reference/syntax-inventory.md#{edgeName}",
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
            specAnchor="docs/reference/syntax-inventory.md#sharedState",
            fixCandidates=[
                FixCandidate(
                    name="addProtectedByClause",
                    shape=f"{accessFact.line.raw.strip()} protectedBy <guardToken>",
                    evidence=[span_of_line(accessFact.line)],
                ),
                FixCandidate(
                    # docs/reference/syntax-inventory.md has no bare `guardToken NAME` declaration verb;
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
            specAnchor="docs/reference/syntax-inventory.md#sharedState",
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
        # `authority` is access-first (`authority OP ACCESS PATH`), mirroring the
        # `effect OP ACCESS PATH` row it backs — unlike `capability`, which is
        # path-first. Emitting it path-first produced a grant that matched no
        # effect and tripped SS3109.
        name="inlineAuthority",
        shape=f"authority {operationName} {effectAction} {effectPath}",
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
                # docs/reference/syntax-inventory.md frames capability coverage as a LINTER rule, not a
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
                specAnchor="docs/reference/syntax-inventory.md#useCapability",
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


def _authority_path_related_to_effect(grantPath: str, effectPath: str) -> bool:
    """True when an authority grant path and an effect path are on the same
    hierarchical branch — equal, or one a dotted-segment prefix of the other.
    A grant at `http.request` covers `http.request.method`; a narrower grant is
    still treated as related (not flagged) to keep this advisory low-noise. Only
    a genuinely unrelated path (or a mismatched access verb, checked separately)
    is reported. Segment-aware so `database.account` does not match
    `database.accountHistory`."""
    if grantPath == effectPath:
        return True
    return effectPath.startswith(grantPath + ".") or grantPath.startswith(effectPath + ".")


def check_authority_effect_mismatch(facts: ExtendedFacts) -> List[Diagnostic]:
    """An inline `authority OP PATH ACCESS` grant should back a declared effect
    on that operation. SS3104 treats the mere PRESENCE of an authority row as
    coverage, so a grant whose access verb or path matches no declared effect (a
    typo such as `read` for a `write` effect, or a stale path) silently passes as
    'covered' while authorizing nothing — and the effect it was meant to back is
    really unprotected. Flag the dead grant so the gap is visible."""
    diagnostics: List[Diagnostic] = []
    for operationName, authorityLines in facts.operationAuthority.items():
        effectLines = facts.operationEffects.get(operationName, [])
        effects = [(line.args[1], line.args[2]) for line in effectLines if len(line.args) >= 3]
        if not effects:
            # No declared effects to reconcile against — a different gap, not this one.
            continue
        for authorityLine in authorityLines:
            authorityArgs = authorityLine.args
            if len(authorityArgs) < 3:
                continue
            # Canonical grammar is `authority OP ACCESS PATH`, parallel to
            # `effect OP ACCESS PATH` (access first, then the dotted path).
            grantAccess, grantPath = authorityArgs[1], authorityArgs[2]
            covers = any(
                grantAccess == effectAction and _authority_path_related_to_effect(grantPath, effectPath)
                for (effectAction, effectPath) in effects
            )
            if covers:
                continue
            fixCandidates = [
                FixCandidate(
                    name="alignAuthorityToEffect",
                    shape=f"authority {operationName} {effectAction} {effectPath}",
                )
                for (effectAction, effectPath) in effects[:3]
            ]
            diagnostics.append(Diagnostic(
                tier=Tier.T3_REFINEMENT,
                code="SS3109",
                kind="capabilityCoverage.authorityEffectMismatch",
                severity=Severity.WARNING,
                subjectName=operationName,
                subjectKind="operation",
                gapEdge="authority",
                intentSlogan="authority grant matches no declared effect",
                primary=span_of_line(authorityLine, "authorityDeclaration"),
                invariantRule="every inline authority grant must back a declared effect by access and path",
                specAnchor="docs/language/errors-effects-capabilities.md#capabilities-and-authority",
                citations=narrative_citations_for_operation(facts, operationName),
                fixCandidates=fixCandidates,
                confidence=Confidence.MEDIUM,
                blocksCompile=False,
                effort=Effort.LOCAL,
                passProvenance="check_authority_effect_mismatch",
                agentHint=(
                    f"`authority {operationName} {grantAccess} {grantPath}` authorizes nothing on "
                    f"{operationName}; align its access verb and path to a declared "
                    f"`effect {operationName} <action> <path>` row (order is access-first: "
                    f"`authority OP ACCESS PATH`)"
                ),
            ))
    return diagnostics


_OWNED_COLUMN_SOURCES = frozenset({
    "sqlite.columnText", "sqlite.columnBlob", "sqlite.columnName",
})
_STATEMENT_RELEASE_TARGETS = frozenset({"sqlite.finalizeStatement"})
_DATABASE_RELEASE_TARGETS = frozenset({"sqlite.closeDatabase"})


def _sqlite_statement_argument(call_fact) -> Optional[str]:
    """The value bound to a call's `SqliteStatement`-typed argument, if any."""
    for arg_line in call_fact.arg_lines:
        parts = argument_parts(arg_line)
        if parts and parts[2] == "SqliteStatement":
            return parts[3]
    return None


def check_column_memory_use_after_free(facts: ExtendedFacts) -> List[Diagnostic]:
    """SS3110 — a value read from `sqlite.columnText`/`columnBlob`/`columnName`
    points into the prepared statement's own memory. Using it after that
    statement is finalized or the database is closed is a use-after-free: it
    builds and checks cleanly, then SIGSEGVs at runtime when the response writer
    dereferences freed memory (the devlog's hardest bug — invisible to check AND
    build). Flag a column value consumed as a call argument that linearly
    follows an EXPLICIT `run` of `finalizeStatement` (same statement) or
    `closeDatabase`, within the same straight-line block. `defer`-based release
    runs at scope exit (after the use) and is correctly NOT flagged — which is
    exactly the idiomatic fix."""
    diagnostics: List[Diagnostic] = []
    for operation in facts.base.operations.values():
        calls = collect_operation_calls(operation)

        # column value -> (owning statement value, bind line number)
        column_values: Dict[str, Tuple[Optional[str], int]] = {}
        for call_fact in calls.values():
            if call_fact.target not in _OWNED_COLUMN_SOURCES:
                continue
            statement = _sqlite_statement_argument(call_fact)
            for bind_line in call_fact.bind_lines:
                bind = bind_parts(bind_line)
                if bind and bind[0] == "value":
                    column_values[bind[1]] = (statement, bind_line.number)
        if not column_values:
            continue

        # release points: (statement value or None == closes everything, run line)
        releases: List[Tuple[Optional[str], int]] = []
        for call_fact in calls.values():
            if call_fact.target in _STATEMENT_RELEASE_TARGETS:
                statement = _sqlite_statement_argument(call_fact)
                releases.extend((statement, run_line.number) for run_line in call_fact.run_lines)
            elif call_fact.target in _DATABASE_RELEASE_TARGETS:
                releases.extend((None, run_line.number) for run_line in call_fact.run_lines)
        if not releases:
            continue

        label_lines = sorted(
            line.number for line in operation.lines
            if line.tokens and not is_comment(line) and line.verb == "label"
        )

        for use_line in operation.lines:
            if is_comment(use_line) or not use_line.tokens:
                continue
            parts = argument_parts(use_line)
            if parts is None or parts[3] not in column_values:
                continue
            used_value = parts[3]
            owning_statement, bind_line_number = column_values[used_value]
            for release_statement, release_line in releases:
                if not (bind_line_number < release_line < use_line.number):
                    continue
                # finalize of a DIFFERENT statement does not free this value;
                # closeDatabase (release_statement is None) frees everything.
                if (release_statement is not None and owning_statement is not None
                        and release_statement != owning_statement):
                    continue
                # A label between the release and the use means they may be on
                # different control-flow paths — stay conservative (no FP).
                if any(release_line < ln < use_line.number for ln in label_lines):
                    continue
                release_kind = "the database is closed" if release_statement is None else \
                    f"statement `{owning_statement or release_statement}` is finalized"
                diagnostics.append(Diagnostic(
                    tier=Tier.T3_REFINEMENT,
                    code="SS3110",
                    kind="resourceLifetime.columnUseAfterFree",
                    severity=Severity.WARNING,
                    subjectName=used_value,
                    subjectKind="value",
                    gapEdge="defer",
                    intentSlogan="column memory used after finalize/close",
                    primary=span_of_line(use_line, "columnValueUse"),
                    invariantRule="a sqlite.column* value must be consumed before its statement is finalized or its database closed",
                    specAnchor="docs/reference/syntax-inventory.md#defer",
                    citations=narrative_citations_for_operation(facts, operation.name),
                    fixCandidates=[
                        FixCandidate(
                            name="releaseWithDefer",
                            shape=f"defer <name> sqlite.finalizeStatement {owning_statement or '<statement>'}",
                        ),
                        FixCandidate(
                            name="writeResponseBeforeRelease",
                            shape="# move the response/use rows above the finalize/close rows",
                        ),
                    ],
                    confidence=Confidence.MEDIUM,
                    blocksCompile=False,
                    effort=Effort.LOCAL,
                    passProvenance="check_column_memory_use_after_free",
                    agentHint=(
                        f"`{used_value}` points into statement memory freed at line {release_line} "
                        f"({release_kind}); consume it before that row, or release with `defer` "
                        f"so cleanup runs at scope exit"
                    ),
                ))
                break  # one diagnostic per use site
    return diagnostics


# A live `columnText`/`columnBlob`/`columnName` pointer is invalidated by the
# NEXT pointer-returning column read, or by step/reset, on the SAME statement —
# even before the statement is finalized (which is SS3110's separate case). The
# SQLite contract: the pointer is valid only until the next such call.
_COLUMN_TEXT_INVALIDATORS = frozenset({
    "sqlite.columnText", "sqlite.columnBlob", "sqlite.columnName",
    "sqlite.stepStatement", "sqlite.resetStatement",
})


def check_column_text_overwritten_before_use(facts: ExtendedFacts) -> List[Diagnostic]:
    """SS3113 — a `sqlite.columnText`/`columnBlob`/`columnName` value points into
    a per-statement buffer that the NEXT pointer-returning column read (or a
    step/reset) on the same statement overwrites. Reading a second text column,
    then using the first, yields CORRUPT OUTPUT — not an error — at runtime
    (the devlog's documented footgun). The idiomatic fix is to consume/copy each
    column value (e.g. hydrate it into a template) before reading the next one.
    Flag a column value used as a call argument that linearly follows an
    invalidating call on the same statement, within one straight-line block."""
    diagnostics: List[Diagnostic] = []
    for operation in facts.base.operations.values():
        calls = collect_operation_calls(operation)

        # transient column value -> (owning statement value, bind line number)
        column_values: Dict[str, Tuple[Optional[str], int]] = {}
        for call_fact in calls.values():
            if call_fact.target not in _OWNED_COLUMN_SOURCES:
                continue
            statement = _sqlite_statement_argument(call_fact)
            for bind_line in call_fact.bind_lines:
                bind = bind_parts(bind_line)
                if bind and bind[0] == "value":
                    column_values[bind[1]] = (statement, bind_line.number)
        if not column_values:
            continue

        # invalidation points: (statement value, run line) for every column
        # read / step / reset on a statement.
        invalidations: List[Tuple[Optional[str], int]] = []
        for call_fact in calls.values():
            if call_fact.target not in _COLUMN_TEXT_INVALIDATORS:
                continue
            statement = _sqlite_statement_argument(call_fact)
            invalidations.extend(
                (statement, run_line.number) for run_line in call_fact.run_lines)
        if not invalidations:
            continue

        label_lines = sorted(
            line.number for line in operation.lines
            if line.tokens and not is_comment(line) and line.verb == "label"
        )

        for use_line in operation.lines:
            if is_comment(use_line) or not use_line.tokens:
                continue
            parts = argument_parts(use_line)
            if parts is None or parts[3] not in column_values:
                continue
            used_value = parts[3]
            owning_statement, bind_line_number = column_values[used_value]
            for invalidation_statement, invalidation_line in invalidations:
                # The value's own producing read sits at its bind line; only a
                # LATER call on the SAME statement overwrites the buffer.
                if not (bind_line_number < invalidation_line < use_line.number):
                    continue
                if (invalidation_statement is not None and owning_statement is not None
                        and invalidation_statement != owning_statement):
                    continue
                # A label between the invalidation and the use means they may be
                # on different control-flow paths — stay conservative (no FP).
                if any(invalidation_line < ln < use_line.number for ln in label_lines):
                    continue
                diagnostics.append(Diagnostic(
                    tier=Tier.T3_REFINEMENT,
                    code="SS3113",
                    kind="resourceLifetime.columnTextOverwrittenBeforeUse",
                    severity=Severity.WARNING,
                    subjectName=used_value,
                    subjectKind="value",
                    gapEdge="columnConsumeOrder",
                    intentSlogan="column value used after a later same-statement read overwrote it",
                    primary=span_of_line(use_line, "columnValueUse"),
                    related=[span_of_line(operation.line, "enclosingOperation")],
                    invariantRule="a sqlite.columnText/columnBlob/columnName pointer is valid only until the next column read or step/reset on the same statement; consume or copy it first",
                    specAnchor="docs/reference/syntax-inventory.md#sqlite",
                    citations=narrative_citations_for_operation(facts, operation.name),
                    fixCandidates=[
                        FixCandidate(
                            name="consumeBeforeNextRead",
                            shape="# copy/hydrate this column value before the next sqlite.column* read on the same statement",
                        ),
                    ],
                    confidence=Confidence.MEDIUM,
                    blocksCompile=False,
                    effort=Effort.LOCAL,
                    passProvenance="check_column_text_overwritten_before_use",
                    agentHint=(
                        f"`{used_value}` points into statement `{owning_statement or '<statement>'}`'s "
                        f"buffer, which was overwritten at line {invalidation_line} by a later column "
                        f"read/step; consume or copy `{used_value}` before that row"
                    ),
                ))
                break  # one diagnostic per use site
    return diagnostics


def check_unknown_verbs(facts: ExtendedFacts) -> List[Diagnostic]:
    """Verbs not in `KNOWN_AGENT_SCRIPT_VERBS` are grammar gaps — either a
    typo, or a docs/reference/syntax-inventory.md row landed without updating this set. Reported as
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
            invariantRule="every verb must be a row in docs/reference/syntax-inventory.md and registered in KNOWN_AGENT_SCRIPT_VERBS",
            specAnchor="docs/reference/syntax-inventory.md",
            fixCandidates=[
                FixCandidate(
                    name="correctTypo",
                    shape=f"# verify spelling of `{verb}` against docs/reference/syntax-inventory.md",
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
                "if a new docs/reference/syntax-inventory.md row was added recently, this vocab is "
                "out of date — sync the set"
            ),
        ))
    return diagnostics


_CUTOVER_ACTIONS: Set[str] = {
    "read", "write", "append", "allocate", "free", "open", "close",
    "execute", "delete", "create", "update", "network", "observe",
    "log", "connect", "send", "receive", "configure",
}

_REPLACED_VERB_FIXES: Dict[str, str] = {
    "importModule": "import <alias> <module.path>",
    "arg": "argument <call> <parameter> <type> <value>",
    "bindOk": "bind ok <name> <type> <call>",
    "bindError": "bind error <name> <type> <call>",
    "branchIf": "branch if condition <condition> target <label>",
    "branchIfError": "branch error source <call> target <label>",
    "returnValue": "return value <value>",
    "returnOk": "return ok <value>",
    "returnError": "return error <value>",
    "returnVoid": "return void",
    "ignoreValue": "ignore value source <call> type <type>",
    "ignoreOk": "ignore ok source <call> type <type>",
    "ignoreError": "ignore error source <call>",
    "memoryHeap": "memory <operation> heap yes|no|auto",
    "memoryArena": "memory <operation> arena <scope>",
    "memoryStackLimit": "memory <operation> stack max <size>",
    "const": "storage module immutable <name> <type> <value>",
    "let": "memory <operation> mutable <name> <type> <value>",
    "var": "memory <operation> mutable <name> <type> <value>",
    "modulePurpose": "purpose module <module> \"...\"",
    "moduleInvariant": "invariant module <module> \"...\"",
    "htmlTemplate": "html template <name>",
    "htmlArg": "# remove; html hydrate parameters are inferred from body holes",
    "htmlBody": "html body template <template>",
}


def _syntax_cutover_diagnostic(
    sourceLine: SourceLine,
    subjectName: str,
    intent: str,
    rule: str,
    shape: str,
) -> Diagnostic:
    return Diagnostic(
        tier=Tier.T0_PARSE,
        code="SS0003",
        kind="grammar.syntaxCutover",
        severity=Severity.ERROR,
        subjectName=subjectName,
        subjectKind="row",
        gapEdge="newSyntax",
        intentSlogan=intent,
        primary=span_of_line(sourceLine, "syntaxCutoverSite"),
        invariantRule=rule,
        specAnchor="docs/reference/syntax-inventory.md#syntax-cutover",
        fixCandidates=[
            FixCandidate(
                name="runMigrateSyntax",
                shape="sem migrate-syntax --write <file>",
            ),
            FixCandidate(
                name="rewriteToNewSyntax",
                shape=shape,
            ),
        ],
        confidence=Confidence.HIGH,
        blocksCompile=True,
        effort=Effort.TRIVIAL,
        passProvenance="check_syntax_cutover_rows",
        agentHint="run `sem migrate-syntax --diff <file>` to preview the upgrade then `--write` to apply it; this rewrites every cutover row mechanically. Or rewrite this row to the shape shown. The linter no longer treats old syntax as source.",
    )


def check_syntax_cutover_rows(facts: ExtendedFacts) -> List[Diagnostic]:
    diagnostics: List[Diagnostic] = []
    for sourceLine in facts.base.lines:
        if sourceLine.number == 0 or not sourceLine.tokens:
            continue

        stripped = sourceLine.raw.strip()
        if stripped.startswith("#label"):
            diagnostics.append(_syntax_cutover_diagnostic(
                sourceLine, "#label", "sigil-prefixed labels are rejected",
                "labels must use `label NAME`, not `#label NAME`",
                "label <name>",
            ))
            continue
        if is_comment(sourceLine):
            continue

        verb = sourceLine.verb
        args = sourceLine.args
        if verb.startswith("@") or verb.startswith("#"):
            diagnostics.append(_syntax_cutover_diagnostic(
                sourceLine, verb, "sigil-prefixed row verb is rejected",
                "row verbs must be plain words; labels use `label NAME`",
                "label <name>" if "label" in verb else "# remove the sigil prefix",
            ))
            continue
        if "." in verb:
            diagnostics.append(_syntax_cutover_diagnostic(
                sourceLine, verb, "dotted fact-row verb is rejected",
                "dotted path/value tokens are allowed, but row verbs cannot contain dots",
                "# rewrite as a supported space-separated row",
            ))
            continue
        if any("=" in token.text for token in sourceLine.tokens if not token.quoted):
            diagnostics.append(_syntax_cutover_diagnostic(
                sourceLine, verb, "equals-sign key/value rows are rejected",
                "SemanticScript rows remain space-separated positional rows with role words",
                "# rewrite without key=value fields",
            ))
            continue
        if verb in _REPLACED_VERB_FIXES:
            diagnostics.append(_syntax_cutover_diagnostic(
                sourceLine, verb, f"`{verb}` was replaced by the syntax cutover",
                f"`{verb}` is converter input only, not valid SemanticScript source",
                _REPLACED_VERB_FIXES[verb],
            ))
            continue

        if verb == "type" and len(args) >= 2 and args[1] == "Result":
            diagnostics.append(_syntax_cutover_diagnostic(
                sourceLine, "type Result", "old result type row is rejected",
                "`type NAME Result OK ERROR` must become `type NAME result ok OK error ERROR`",
                "type <name> result ok <okType> error <errorType>",
            ))
        elif verb == "input" and not (len(args) >= 4 and args[0] == "operation"):
            diagnostics.append(_syntax_cutover_diagnostic(
                sourceLine, "input", "input rows must be subject-qualified",
                "`input OP NAME TYPE` was replaced by `input operation OP NAME TYPE`",
                "input operation <operation> <name> <type>",
            ))
        elif verb == "output" and not (len(args) >= 3 and args[0] == "operation"):
            diagnostics.append(_syntax_cutover_diagnostic(
                sourceLine, "output", "output rows must be subject-qualified",
                "`output OP TYPE` was replaced by `output operation OP TYPE`",
                "output operation <operation> <type>",
            ))
        elif verb == "purpose" and not (len(args) >= 3 and args[0] in PURPOSE_SUBJECT_KINDS):
            diagnostics.append(_syntax_cutover_diagnostic(
                sourceLine, "purpose", "purpose rows must name the subject kind",
                "`purpose SUBJECT TEXT` was replaced by `purpose <kind> SUBJECT TEXT` "
                "(kind is one of: " + ", ".join(sorted(PURPOSE_SUBJECT_KINDS)) + ")",
                "purpose operation <operation> \"...\"",
            ))
        elif verb == "invariant" and not (len(args) >= 3 and args[0] in {"module", "operation"}):
            diagnostics.append(_syntax_cutover_diagnostic(
                sourceLine, "invariant", "invariant rows must name the subject kind",
                "`invariant SUBJECT TEXT` was replaced by `invariant operation SUBJECT TEXT` or `invariant module SUBJECT TEXT`",
                "invariant operation <operation> \"...\"",
            ))
        elif verb == "import" and len(args) != 2:
            diagnostics.append(_syntax_cutover_diagnostic(
                sourceLine, "import", "import rows require alias and module path",
                "`import` must be `import ALIAS MODULE_PATH`",
                "import <alias> <module.path>",
            ))
        elif verb == "bind" and not (len(args) >= 4 and args[0] in {"value", "ok", "error"}):
            diagnostics.append(_syntax_cutover_diagnostic(
                sourceLine, "bind", "bind rows require a variant word",
                "`bind NAME TYPE CALL` was replaced by `bind value NAME TYPE CALL`",
                "bind value <name> <type> <call>",
            ))
        elif verb == "branch":
            validBranch = (
                len(args) == 5 and args[0] == "if" and args[1] == "condition" and args[3] == "target"
            ) or (
                len(args) == 5 and args[0] == "error" and args[1] == "source" and args[3] == "target"
            ) or (
                len(args) == 3 and args[0] == "else" and args[1] == "target"
            )
            if not validBranch:
                diagnostics.append(_syntax_cutover_diagnostic(
                    sourceLine, "branch", "branch rows require if/error/else role-word shape",
                    "bare `branch TARGET` was replaced by `jump target TARGET`; conditional branches use role words",
                    "branch if condition <condition> target <label>",
                ))
        elif verb == "jump" and not (len(args) == 2 and args[0] == "target"):
            diagnostics.append(_syntax_cutover_diagnostic(
                sourceLine, "jump", "jump rows require `target` role word",
                "`jump LABEL` is invalid; use `jump target LABEL`",
                "jump target <label>",
            ))
        elif verb == "return":
            validReturn = (
                len(args) == 1 and args[0] == "void"
            ) or (
                len(args) == 2 and args[0] in {"value", "ok", "error"}
            )
            if not validReturn:
                diagnostics.append(_syntax_cutover_diagnostic(
                    sourceLine, "return", "return rows require value/ok/error/void variant",
                    "`return` must be `return value|ok|error VALUE` or `return void`",
                    "return value <value>",
                ))
        elif verb == "ignore":
            validIgnore = (
                len(args) == 5 and args[0] in {"value", "ok"} and args[1] == "source" and args[3] == "type"
            ) or (
                len(args) == 3 and args[0] in {"error", "void"} and args[1] == "source"
            )
            if not validIgnore:
                diagnostics.append(_syntax_cutover_diagnostic(
                    sourceLine, "ignore", "ignore rows require variant and role words",
                    "`ignore` must use `source` and, for value/ok, `type` role words",
                    "ignore value source <call> type <type>",
                ))
        elif verb == "argument" and len(args) != 4:
            diagnostics.append(_syntax_cutover_diagnostic(
                sourceLine, "argument", "argument rows require call, parameter, type, and value",
                "`argument` must be `argument CALL PARAM TYPE VALUE`",
                "argument <call> <parameter> <type> <value>",
            ))
        elif verb == "html":
            validHtml = (
                len(args) == 2 and args[0] == "template"
            ) or (
                len(args) == 3 and args[0] == "body" and args[1] == "template"
            )
            if not validHtml:
                diagnostics.append(_syntax_cutover_diagnostic(
                    sourceLine, "html", "html rows require root-specific role words",
                    "`html` rows must be `html template` or `html body template`; holes infer hydrate arguments",
                    "html body template <template>",
                ))
        elif verb == "memory":
            validMemory = False
            if len(args) >= 3 and args[1] in {"mutable", "immutable"}:
                validMemory = len(args) >= 5
            elif len(args) >= 3 and args[1] == "heap":
                validMemory = len(args) == 3 and args[2] in {"yes", "no", "true", "false", "auto"}
            elif len(args) >= 3 and args[1] == "arena":
                validMemory = len(args) == 3
            elif len(args) >= 4 and args[1] == "stack":
                validMemory = args[2] == "max"
            if not validMemory:
                diagnostics.append(_syntax_cutover_diagnostic(
                    sourceLine, "memory", "memory rows require a known subkind",
                    "`memory` subkind must be heap, arena, stack, mutable, or immutable",
                    "memory <operation> heap yes|no|auto",
                ))
        elif verb == "set" and args and args[0] in {"local", "module"}:
            diagnostics.append(_syntax_cutover_diagnostic(
                sourceLine, "set", "`set local/module` was replaced",
                "set targets must use declaration families: `memory` or `storage`",
                "set memory <name> <value>",
            ))
        elif verb == "authority" and len(args) >= 3 and args[1] not in _CUTOVER_ACTIONS and args[2] in _CUTOVER_ACTIONS:
            diagnostics.append(_syntax_cutover_diagnostic(
                sourceLine, "authority", "authority action/path ordering is reversed",
                "`authority OP PATH ACTION` was replaced by `authority OP ACTION PATH`",
                f"authority {args[0]} {args[2]} {args[1]}",
            ))

    return diagnostics


_HTML_HOLE_REFERENCE_RE = re.compile(
    r"\{\s*([A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*)\s*\}")
_HTML_BRACE_CONTENT_RE = re.compile(r"\{([^{}\n]*)\}")
_HTML_RAW_TEXT_RE = re.compile(
    r"<(style|script)\b[^>]*>.*?</\1\s*>",
    re.IGNORECASE | re.DOTALL,
)
_HTML_RAW_HYDRATION_TYPES: frozenset = frozenset({
    "HtmlFragment",
    "HtmlTrustedFragment",
    "HtmlDocument",
})


def _html_line_for(template: HtmlTemplateFact, line_number: int, raw: str) -> SourceLine:
    return SourceLine(
        path=template.line.path,
        number=line_number,
        raw=raw,
        tokens=tokenize_line(raw),
    )


def _html_hole_diagnostic(
    sourceLine: SourceLine,
    *,
    subjectName: str,
    intent: str,
    rule: str,
    shape: str,
) -> Diagnostic:
    return Diagnostic(
        tier=Tier.T2_LOWERING,
        code="SS3520",
        kind="html.implicitHoleContract",
        severity=Severity.ERROR,
        subjectName=subjectName,
        subjectKind="htmlTemplate",
        gapEdge="htmlHole",
        intentSlogan=intent,
        primary=span_of_line(sourceLine, "htmlHoleSite"),
        invariantRule=rule,
        specAnchor="docs/reference/syntax-inventory.md#html",
        fixCandidates=[FixCandidate(name="rewriteHtmlHole", shape=shape)],
        confidence=Confidence.HIGH,
        blocksCompile=True,
        effort=Effort.LOCAL,
        passProvenance="check_html_implicit_holes",
        agentHint="template holes are bare names or dotted record fields; hydrate calls must pass exactly those root names",
    )


def _html_body_text(template: HtmlTemplateFact) -> str:
    if not template.body_lines:
        return ""
    return "\n".join(raw[1:] if raw[:1].isspace() else raw
                     for raw, _line in template.body_lines) + "\n"


def _html_hole_roots(template: HtmlTemplateFact) -> Tuple[Set[str], List[Diagnostic]]:
    diagnostics: List[Diagnostic] = []
    body = _html_body_text(template)
    roots: Set[str] = set()
    raw_spans = [(match.start(), match.end(), match.group(1).lower())
                 for match in _HTML_RAW_TEXT_RE.finditer(body)]
    for match in _HTML_HOLE_REFERENCE_RE.finditer(body):
        raw_context = next(
            (name for start, end, name in raw_spans
             if start < match.start() < end),
            None,
        )
        if raw_context is not None:
            sourceLine = template.body_line or template.line
            diagnostics.append(_html_hole_diagnostic(
                sourceLine,
                subjectName=template.name,
                intent="raw text hole rejected",
                rule=f"`{raw_context}` raw text cannot contain dynamic HTML holes",
                shape=f"# move {{{match.group(1)}}} outside <{raw_context}>",
            ))
            continue
        roots.add(match.group(1).split(".", 1)[0])

    masked = list(body)
    for start, end, _name in raw_spans:
        for index in range(start, end):
            masked[index] = " "
    masked_body = "".join(masked)
    hole_spans = {(match.start(), match.end())
                  for match in _HTML_HOLE_REFERENCE_RE.finditer(masked_body)}
    for match in _HTML_BRACE_CONTENT_RE.finditer(masked_body):
        if (match.start(), match.end()) in hole_spans:
            continue
        content = match.group(1).strip()
        if not content:
            continue
        sourceLine = template.body_line or template.line
        diagnostics.append(_html_hole_diagnostic(
            sourceLine,
            subjectName=template.name,
            intent="complex hole rejected",
            rule="HTML dynamic holes must be a bare name or dotted record-field path",
            shape="{name} or {record.field}",
        ))
    return roots, diagnostics


def check_html_implicit_holes(facts: ExtendedFacts) -> List[Diagnostic]:
    diagnostics: List[Diagnostic] = []
    template_roots: Dict[str, Set[str]] = {}
    for template in facts.base.html_templates.values():
        roots, bodyDiagnostics = _html_hole_roots(template)
        template_roots[template.name] = roots
        diagnostics.extend(bodyDiagnostics)

    for operation in facts.base.operations.values():
        for callFact in collect_operation_calls(operation).values():
            prefix = "html.hydrate."
            if not callFact.target.startswith(prefix):
                continue
            templateName = callFact.target[len(prefix):]
            if templateName not in template_roots:
                continue
            required = template_roots[templateName]
            provided = {
                parsed[1]
                for parsed in (argument_parts(line) for line in callFact.arg_lines)
                if parsed is not None
            }
            for missing in sorted(required - provided):
                diagnostics.append(_html_hole_diagnostic(
                    callFact.line,
                    subjectName=templateName,
                    intent="hydrate arg missing",
                    rule=f"`html.hydrate.{templateName}` must pass hole root `{missing}`",
                    shape=f"argument {callFact.name} {missing} String <value>",
                ))
            for extra in sorted(provided - required):
                diagnostics.append(_html_hole_diagnostic(
                    callFact.line,
                    subjectName=templateName,
                    intent="hydrate arg extra",
                    rule=f"`html.hydrate.{templateName}` has no hole root `{extra}`",
                    shape=f"# remove argument {callFact.name} {extra} ...",
                ))
    return diagnostics


def check_unused_html_template(facts: ExtendedFacts) -> List[Diagnostic]:
    """SS0109 — an `html template NAME` that is never rendered by any
    `html.hydrate.NAME` call is dead (mirrors the unused-call/label checks).
    A declared-but-unhydrated template is usually a leftover or a typo'd hydrate
    target; either way it ships markup that never reaches a response."""
    diagnostics: List[Diagnostic] = []
    if not facts.base.html_templates:
        return diagnostics
    hydrated: Set[str] = set()
    prefix = "html.hydrate."
    for operation in facts.base.operations.values():
        for sourceLine in operation.lines:
            if (sourceLine.tokens and not is_comment(sourceLine)
                    and sourceLine.verb == "call" and len(sourceLine.args) >= 2
                    and sourceLine.args[1].startswith(prefix)):
                hydrated.add(sourceLine.args[1][len(prefix):])
    for template in facts.base.html_templates.values():
        if template.name in hydrated:
            continue
        diagnostics.append(Diagnostic(
            tier=Tier.T3_REFINEMENT,
            code="SS0109",
            kind="unusedDeclaration.htmlTemplate",
            severity=Severity.WARNING,
            subjectName=template.name,
            subjectKind="htmlTemplate",
            gapEdge="hydrationSite",
            intentSlogan="html template never hydrated",
            primary=span_of_line(template.line, "htmlTemplateDeclaration"),
            invariantRule=(
                f"`html template {template.name}` is declared but no "
                f"`html.hydrate.{template.name}` call renders it; the template "
                f"markup is dead."
            ),
            specAnchor="docs/reference/syntax-inventory.md#html",
            fixCandidates=[
                FixCandidate(
                    name="hydrateTemplate",
                    shape=f"call <name>Call html.hydrate.{template.name}",
                ),
                FixCandidate(
                    name="removeTemplate",
                    shape=f"# remove the unused `html template {template.name}` and its body",
                ),
            ],
            confidence=Confidence.HIGH,
            blocksCompile=False,
            effort=Effort.LOCAL,
            passProvenance="check_unused_html_template",
            agentHint="hydrate the template where the page is rendered, or delete it if it is a leftover",
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
            bind = bind_parts(sourceLine)
            if bind is not None and bind[0] == "error":
                errorBindingName = bind[1]
                if not errorBindingName.endswith("Error"):
                    diagnostics.append(_make_vague_name_diagnostic(
                        sourceLine=sourceLine,
                        operation=operation,
                        operationCitations=operationCitations,
                        code="SS4002",
                        kind="namingDiscipline.bindErrorSuffix",
                        subjectName=errorBindingName,
                        subjectKind="bind error",
                        intentSlogan="error binding lacks `Error` suffix",
                        invariantRule="`bind error` values must end with `Error` so they read distinctly from success bindings",
                        fixShape=f"bind error {errorBindingName}Error <type> <call>",
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
            elif bind is not None and bind[0] in {"value", "ok"}:
                bindName = bind[1]
                if bindName in VAGUE_NAME_BLACKLIST:
                    diagnostics.append(_make_vague_name_diagnostic(
                        sourceLine=sourceLine,
                        operation=operation,
                        operationCitations=operationCitations,
                        code="SS4004",
                        kind="namingDiscipline.vagueName",
                        subjectName=bindName,
                        subjectKind=f"bind {bind[0]}",
                        intentSlogan=f"bind {bind[0]} name is in vague-name blacklist",
                        invariantRule="bound values should describe what they hold, not their position in the algorithm",
                        fixShape=f"bind {bind[0]} <descriptiveName> <type> <call>",
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
        # Calls whose error condition is discharged by a `branch error source
        # <call>` / `branchIfError <call>` row. For such a call, its
        # `bind error <slot> <call>` slot is the structurally-required vehicle
        # SS3106 demands — the branch consumes the error via the CALL name, so
        # the typed SLOT name is legitimately never read. Exempt those slots
        # from the unused-bind check rather than flagging the canonical
        # error-handling idiom (which would contradict SS3106).
        branchErrorDischargedCalls: Set[str] = set()
        for sourceLine in operation.lines:
            if is_comment(sourceLine) or not sourceLine.tokens:
                continue
            dischargedCall = branch_error_source(sourceLine)
            if dischargedCall is not None:
                branchErrorDischargedCalls.add(dischargedCall)

        bindDeclarations: List[Tuple[str, str, SourceLine, int, str, str]] = []
        for lineIndex, sourceLine in enumerate(operation.lines):
            if is_comment(sourceLine) or not sourceLine.tokens:
                continue
            bind = bind_parts(sourceLine)
            if bind is not None:
                bindDeclarations.append((
                    bind[1], f"bind {bind[0]}", sourceLine, lineIndex,
                    bind[0], bind[3],
                ))

        for (bindName, bindVerb, declarationLine, declarationIndex,
                bindVariant, boundFromCall) in bindDeclarations:
            # Error slot discharged by `branch error`/`branchIfError` on its
            # call is part of the required idiom, not dead.
            if bindVariant == "error" and boundFromCall in branchErrorDischargedCalls:
                continue
            isReferenced = False
            for laterLine in operation.lines[declarationIndex + 1:]:
                if is_comment(laterLine) or not laterLine.tokens:
                    continue
                # Skip the bind declarations themselves to avoid self-match
                laterBind = bind_parts(laterLine)
                if laterBind is not None:
                    if laterBind[1] == bindName:
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
                specAnchor=f"docs/reference/syntax-inventory.md#{bindVerb}",
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


# A `sqlite.bind*` row binds one parameter of a prepared statement; a bind
# failure (SQLITE_RANGE/SQLITE_MISUSE/OOM) is realized and surfaced by the
# subsequent step/exec on the same statement. When that statement lifecycle is
# already error-handled in the operation, demanding a separate `bind error` +
# `branch error` on every parameter bind is ~hundreds of low-value rows that
# also spawn unused-bind (SS0106) churn. We therefore suppress SS3106 on
# `sqlite.bind*` rows inside an operation whose prepare/step/exec is
# error-handled. This is a deliberate, scoped softening (the bind's own status
# is not independently checked) chosen over forcing per-bind error branches.
_SQLITE_BIND_CALL_TARGETS: FrozenSet[str] = frozenset({
    "sqlite.bindInt", "sqlite.bindInt64", "sqlite.bindDouble",
    "sqlite.bindText", "sqlite.bindBlob", "sqlite.bindNull",
})
_SQLITE_STATEMENT_LIFECYCLE_TARGETS: FrozenSet[str] = frozenset({
    "sqlite.prepareStatement", "sqlite.stepStatement",
    "sqlite.exec", "sqlite.execStatus",
})


def check_hidden_failure(facts: ExtendedFacts) -> List[Diagnostic]:
    """Known-fallible calls must expose their failure/status disposition.

    Exception: `sqlite.bind*` rows are not required to carry their own error
    disposition when the enclosing operation already error-handles a sqlite
    statement-lifecycle call (prepare/step/exec) — the bind's effect is
    validated downstream by that step. See `_SQLITE_BIND_CALL_TARGETS`."""
    diagnostics: List[Diagnostic] = []
    resultReturningUserOps = result_returning_operation_names(facts.base)
    for operation in facts.base.operations.values():
        operationCitations = narrative_citations_for_operation(facts, operation.name)
        operationCalls = collect_operation_calls(operation)
        # Does this operation error-handle a sqlite statement lifecycle? A
        # lifecycle call counts as handled when it branches on error or uses
        # runChecked.
        operationHasHandledSqliteLifecycle = any(
            lifecycleCall.target in _SQLITE_STATEMENT_LIFECYCLE_TARGETS
            and (lifecycleCall.branch_error_lines or lifecycleCall.run_checked_lines)
            for lifecycleCall in operationCalls.values()
        )
        lines = [
            sourceLine
            for sourceLine in operation.lines
            if sourceLine.tokens and not is_comment(sourceLine)
        ]
        waitSetCaseCalls: Set[str] = set()
        waitSetHandlerLabels: Set[str] = set()
        labelBeforeLine: Dict[int, Optional[str]] = {}
        currentLabel: Optional[str] = None
        for sourceLine in lines:
            labelBeforeLine[sourceLine.number] = currentLabel
            if sourceLine.verb == "label" and sourceLine.args:
                currentLabel = sourceLine.args[0]
            if sourceLine.verb == "case" and len(sourceLine.args) >= 2:
                waitSetCaseCalls.add(sourceLine.args[0])
                waitSetHandlerLabels.add(sourceLine.args[1])

        def in_wait_set_completion_context(callFact: CallFact) -> bool:
            if callFact.name in waitSetCaseCalls:
                return True
            executionLines = (
                callFact.run_lines
                + callFact.run_checked_lines
                + callFact.start_lines
                + callFact.group_start_lines
                + callFact.await_lines
            )
            return any(
                labelBeforeLine.get(line.number) in waitSetHandlerLabels
                for line in executionLines
            )

        def is_wait_set_handler_line(line: SourceLine) -> bool:
            return labelBeforeLine.get(line.number) in waitSetHandlerLabels

        def unchecked_execution_lines(callFact: CallFact) -> List[SourceLine]:
            return (
                callFact.run_lines
                + callFact.start_lines
                + callFact.group_start_lines
                + callFact.await_lines
            )

        def after_last_execution(line: SourceLine, executionLines: List[SourceLine]) -> bool:
            if not executionLines:
                return True
            return line.number > max(executionLine.number for executionLine in executionLines)

        def has_ordered_result_success(
            callFact: CallFact,
            executionLines: List[SourceLine],
            waitSetCompletionContext: bool,
        ) -> bool:
            return any(
                after_last_execution(line, executionLines)
                and (
                    not waitSetCompletionContext
                    or is_wait_set_handler_line(line)
                )
                for line in call_result_success_disposition_lines(callFact)
            )

        def has_ordered_bind_error(
            callFact: CallFact,
            executionLines: List[SourceLine],
            waitSetCompletionContext: bool,
        ) -> bool:
            return any(
                after_last_execution(line, executionLines)
                and (
                    not waitSetCompletionContext
                    or is_wait_set_handler_line(line)
                )
                for line in callFact.bind_error_lines
            )

        def has_ordered_branch_error(
            callFact: CallFact,
            executionLines: List[SourceLine],
        ) -> bool:
            return any(
                after_last_execution(line, executionLines)
                for line in callFact.branch_error_lines
            )

        def has_ordered_value_disposition(
            callFact: CallFact,
            executionLines: List[SourceLine],
        ) -> bool:
            return any(
                after_last_execution(line, executionLines)
                for line in (
                    callFact.bind_lines
                    + callFact.bind_ok_lines
                    + callFact.ignore_value_lines
                    + callFact.ignore_ok_lines
                    + callFact.ignore_void_lines
                )
            )

        for callFact in operationCalls.values():
            if (callFact.target not in KNOWN_FALLIBLE_CALL_TARGETS
                    and callFact.target not in resultReturningUserOps):
                continue
            # Scoped exception: a parameter bind inside an error-handled sqlite
            # transaction does not need its own error disposition (the step/exec
            # surfaces the failure). See _SQLITE_BIND_CALL_TARGETS rationale.
            if (callFact.target in _SQLITE_BIND_CALL_TARGETS
                    and operationHasHandledSqliteLifecycle):
                continue
            uncheckedExecutionLines = unchecked_execution_lines(callFact)
            if callFact.run_checked_lines and uncheckedExecutionLines:
                diagnostics.append(Diagnostic(
                    tier=Tier.T3_REFINEMENT,
                    code="SS3106",
                    kind="errorPathCoverage.hiddenFailure",
                    severity=Severity.WARNING,
                    subjectName=callFact.name,
                    subjectKind="call",
                    gapEdge="runOrRunChecked",
                    intentSlogan="fallible call mixes checked and unchecked execution",
                    primary=span_of_line(uncheckedExecutionLines[0], "uncheckedExecutionSite"),
                    related=[
                        span_of_line(callFact.line, "callDeclaration"),
                        *[
                            span_of_line(runCheckedLine, "checkedRunSite")
                            for runCheckedLine in callFact.run_checked_lines
                        ],
                    ],
                    invariantRule=(
                        f"known-fallible target `{callFact.target}` must use either "
                        "`runChecked` for every execution or the explicit unchecked "
                        "execution + success/error/branch disposition shape; do not "
                        "mix both on the same call name"
                    ),
                    specAnchor="docs/reference/syntax-inventory.md#runchecked",
                    citations=operationCitations,
                    fixCandidates=[
                        FixCandidate(
                            name="useOneExecutionShape",
                            shape=(
                                f"runChecked {callFact.name} ok <okName> <OkType> "
                                "error <errorName> <ErrorType> else <failureLabel>\n"
                                "# or remove runChecked and add bind/ignore + branch "
                                "disposition for the unchecked execution"
                            ),
                            evidence=[span_of_line(uncheckedExecutionLines[0])],
                        ),
                    ],
                    confidence=Confidence.HIGH,
                    effort=Effort.LOCAL,
                    passProvenance="check_hidden_failure",
                    agentHint=(
                        "`runChecked` only checks its own execution row; a sibling "
                        "`run`/`start`/`await` path would still execute unchecked"
                    ),
                ))
                continue
            if callFact.run_checked_lines:
                continue
            if callFact.target in C_SENTINEL_FALLIBLE_CALL_TARGETS:
                if has_ordered_value_disposition(callFact, uncheckedExecutionLines):
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
                        "discard it with `ignore value`"
                    ),
                    specAnchor="docs/reference/syntax-inventory.md#ignore",
                    citations=operationCitations,
                    fixCandidates=[
                        FixCandidate(
                            name="bindOrIgnoreStatus",
                            shape=(
                                f"bind value {callFact.name}Status <ReturnType> {callFact.name}\n"
                                f"# ...check status...\n"
                                f"# or: ignore value source {callFact.name} type <ReturnType>"
                            ),
                            evidence=[span_of_line(callFact.line)],
                        ),
                    ],
                    confidence=Confidence.HIGH,
                    effort=Effort.LOCAL,
                    passProvenance="check_hidden_failure",
                    agentHint=(
                        f"`{callFact.target}` is not Result-shaped; use a bound "
                        "sentinel/status check or an explicit ignore value"
                    ),
                ))
                continue
            waitSetCompletionContext = in_wait_set_completion_context(callFact)
            relevantIgnoreError = any(
                after_last_execution(line, uncheckedExecutionLines)
                and is_wait_set_handler_line(line)
                for line in callFact.ignore_error_lines
            ) if waitSetCompletionContext else False
            hasBindError = has_ordered_bind_error(
                callFact,
                uncheckedExecutionLines,
                waitSetCompletionContext,
            )
            missingDisposition: List[str] = []
            if not has_ordered_result_success(
                callFact,
                uncheckedExecutionLines,
                waitSetCompletionContext,
            ):
                missingDisposition.append("bind/ignore ok")
            if not hasBindError and not relevantIgnoreError:
                missingDisposition.append("bind error")
            if (
                not waitSetCompletionContext
                and not has_ordered_branch_error(callFact, uncheckedExecutionLines)
            ):
                missingDisposition.append("branch error")
            if not missingDisposition:
                continue
            if waitSetCompletionContext:
                invariantRule = (
                    f"calls to known-fallible target `{callFact.target}` inside "
                    "an await wait-set completion path must bind or explicitly "
                    "ignore both the success and error sides; branching from a "
                    "case handler can abandon sibling futures"
                )
                fixShape = (
                    f"ignore ok source {callFact.name} type <OkType>\n"
                    f"bind error {callFact.name}Error <ErrorType> {callFact.name}\n"
                    f"# or: ignore error source {callFact.name}"
                )
                agentHint = (
                    "wait-set case handlers must re-enter the wait set; stash "
                    "the error for an after-done decision or explicitly ignore it"
                )
            else:
                invariantRule = (
                    f"calls to known-fallible target `{callFact.target}` must "
                    f"have both `bind error` and `branch error`"
                )
                fixShape = (
                    f"bind error {callFact.name}Error <ErrorType> {callFact.name}\n"
                    f"branch error source {callFact.name} target <handlerLabel>\n"
                    f"# ...success continuation...\n"
                    f"label <handlerLabel>\n"
                    f"return error {callFact.name}Error"
                )
                agentHint = (
                    f"`{callFact.target}` can fail at runtime; explicit error "
                    f"disposition makes the failure path part of the operation's "
                    f"contract"
                )
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
                invariantRule=invariantRule,
                specAnchor="docs/reference/syntax-inventory.md#bind",
                citations=operationCitations,
                fixCandidates=[
                    FixCandidate(
                        # Full pattern: bind + branch + handler that ACTUALLY
                        # consumes the bound error via returnError. Without
                        # the handler's returnError, SS0106 would fire on the
                        # newly-introduced bindError slot — a true cycle.
                        # `bindError` values end in `Error` per SS4002.
                        name="addBindErrorAndBranchAndConsume",
                        shape=fixShape,
                        evidence=[span_of_line(callFact.line)],
                    ),
                ],
                confidence=Confidence.HIGH,
                effort=Effort.LOCAL,
                passProvenance="check_hidden_failure",
                agentHint=agentHint,
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
                specAnchor=f"docs/reference/syntax-inventory.md#{edgeName}",
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
                specAnchor="docs/reference/syntax-inventory.md#effect",
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
                            # access-first, mirroring the effect row (see SS3104)
                            f"authority {operation.name} {impliedAction} {impliedPath}"
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
            specAnchor="docs/reference/syntax-inventory.md#errorCase",
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
                specAnchor="docs/reference/syntax-inventory.md#domainLiteral",
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
                specAnchor="docs/reference/syntax-inventory.md#input",
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
    if args[0] in {"local", "module", "memory", "storage", "sharedState"}:
        return args[1] if len(args) >= 2 else None
    return args[0]


# Verbs that end a straight-line basic block: control can transfer away (so a
# prior `set`'s value may escape to a read on the taken path) or join from
# elsewhere (a label reachable by branch). Across any of these, a later `set`
# to the same slot is not a sound textual shadow of an earlier one.
_DEAD_STORE_BLOCK_BOUNDARY_VERBS: FrozenSet[str] = frozenset({
    "label",
    "jump",
    "return", "returnValue", "returnOk", "returnError", "returnVoid",
    "branch", "branchIf", "branchIfError", "branchIfGroupError",
    "branchIfChannelClosed", "branchSelected",
    "await", "runChecked", "case", "done",
})


def check_dead_store(facts: ExtendedFacts) -> List[Diagnostic]:
    """`set X val1` followed by `set X val2` with no read of X between is a
    dead store — the first write is overwritten before observation.

    Only flagged within a single straight-line basic block: the tracker is
    cleared at every control-flow boundary (see
    `_DEAD_STORE_BLOCK_BOUNDARY_VERBS`) so two `set`s separated by a
    `jump`/`branch`/`label` — which may lie on disjoint paths — are not
    mistaken for a shadow."""
    diagnostics: List[Diagnostic] = []
    for operation in facts.base.operations.values():
        operationCitations = narrative_citations_for_operation(facts, operation.name)

        # Walk lines in order, track per-name (lastSetIndex, lastSetLine).
        # Dead-store shadowing (`set X a` … `set X b` with no read of X between)
        # is only sound WITHIN a straight-line basic block: across a control-flow
        # boundary the two writes may sit on disjoint paths (an intervening
        # `jump`/`branch` carries the first value to a read elsewhere, or the
        # second `set` is in a branch the first never reaches). Clearing the
        # tracker at every boundary keeps the analysis basic-block-local and
        # avoids cross-branch false positives.
        lastSetSeen: Dict[str, Tuple[int, SourceLine]] = {}
        for lineIndex, sourceLine in enumerate(operation.lines):
            if is_comment(sourceLine) or not sourceLine.tokens:
                continue
            verb = sourceLine.verb
            if verb in _DEAD_STORE_BLOCK_BOUNDARY_VERBS:
                lastSetSeen.clear()
                continue
            if verb == "set":
                targetName = _normalize_set_target_name(sourceLine)
                if not targetName:
                    continue
                priorSet = lastSetSeen.get(targetName)
                if priorSet is not None:
                    priorIndex, priorLine = priorSet
                    # Check intervening lines for any read of targetName
                    intervening = operation.lines[priorIndex + 1:lineIndex]
                    # Both sets are in the same straight-line block (the tracker
                    # is cleared at every control-flow boundary), so a read is
                    # simply any non-`set` row that mentions the slot name.
                    isReadBetween = any(
                        laterLine.verb != "set"
                        and any(token.text == targetName for token in laterLine.tokens)
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
                            specAnchor="docs/reference/syntax-inventory.md#set",
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
_LARGE_LOCAL_STATIC_LITERAL_MIN_BYTES = 512
_LARGE_LOCAL_STATIC_LITERAL_TYPES = frozenset({
    "String",
    "String",
    "JsonText",
    "SqlText",
})


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


def _is_large_local_static_literal_type(
    facts: ExtendedFacts,
    typeName: str,
) -> bool:
    resolvedType = _resolve_type_alias_head(typeName, facts.base.type_aliases)
    return resolvedType in _LARGE_LOCAL_STATIC_LITERAL_TYPES


def check_large_local_static_literal(facts: ExtendedFacts) -> List[Diagnostic]:
    """SS3634 - large inline local string/blob literals in operations should be
    hoisted to module storage. They are static data, not per-call context, and
    they bloat hot handlers plus agent working context when left inline.
    """
    diagnostics: List[Diagnostic] = []
    for operationName, operation in facts.base.operations.items():
        for sourceLine in operation.lines:
            if (is_comment(sourceLine) or not sourceLine.tokens
                    or sourceLine.verb != "storage"
                    or len(sourceLine.args) < 5):
                continue
            scope, mutability = sourceLine.args[0], sourceLine.args[1]
            if scope != "local" or mutability != "immutable":
                continue
            name = sourceLine.args[2]
            typeName = sourceLine.args[3]
            valueTokenIndex = 5
            if valueTokenIndex >= len(sourceLine.tokens):
                continue
            valueToken = sourceLine.tokens[valueTokenIndex]
            if not valueToken.quoted:
                continue
            if not _is_large_local_static_literal_type(facts, typeName):
                continue
            literalBytes = len(valueToken.text.encode("utf-8"))
            if literalBytes < _LARGE_LOCAL_STATIC_LITERAL_MIN_BYTES:
                continue
            diagnostics.append(Diagnostic(
                tier=Tier.T3_REFINEMENT,
                code="SS3634",
                kind="performance.largeLocalStaticLiteral",
                severity=Severity.WARNING,
                subjectName=name,
                subjectKind="storageSlot",
                gapEdge="storage module immutable",
                intentSlogan="large static literal declared in operation body",
                primary=span_of_line(sourceLine, "storageDeclaration"),
                related=[span_of_line(operation.line, "enclosingOperation")],
                invariantRule=(
                    f"`{operationName}` declares `{name}` as a {literalBytes}-byte "
                    "inline local immutable literal; static literals at or above "
                    f"{_LARGE_LOCAL_STATIC_LITERAL_MIN_BYTES} bytes belong at "
                    "module scope so handlers do not carry large per-call context."
                ),
                specAnchor="docs/optimization-guide.md#hoist-shared-immutables-to-module-scope",
                fixCandidates=[
                    FixCandidate(
                        name="hoistToModuleImmutable",
                        shape=(
                            f"storage module immutable {name} {typeName} "
                            '"<same literal>"'
                        ),
                        evidence=[span_of_line(sourceLine)],
                    ),
                ],
                confidence=Confidence.HIGH,
                blocksCompile=False,
                effort=Effort.LOCAL,
                passProvenance="check_large_local_static_literal",
                agentHint=(
                    "move the storage row above operations at module scope and "
                    "keep operation references pointed at the same name"
                ),
            ))
    return diagnostics


def check_magic_ascii_byte_literal(facts: ExtendedFacts) -> List[Diagnostic]:
    """``storage local immutable NAME Int32 V`` where ``V`` is a
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
            if typeName not in {"Int32", "Int32"}:
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
                        shape=f"storage module immutable ascii<Role> Int32 {codepoint}",
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
    "math.equalInt64":                       "equal",
    "math.notEqualInt64":                    "notEqual",
    "math.lessThanInt64":                    "lessThan",
    "math.lessThanOrEqualInt64":             "lessThanOrEqual",
    "math.greaterThanInt64":                 "greaterThan",
    "math.greaterThanOrEqualInt64":          "greaterThanOrEqual",
    "math.equalInt32":              "equal",
    "math.notEqualInt32":           "notEqual",
    "math.lessThanInt32":           "lessThan",
    "math.lessThanOrEqualInt32":    "lessThanOrEqual",
    "math.greaterThanInt32":        "greaterThan",
    "math.greaterThanOrEqualInt32": "greaterThanOrEqual",
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
        if verb == "storage" and len(args) >= 4:
            moduleScopeValueTypes[args[2]] = args[3]
        elif verb == "sharedState" and len(args) >= 4:
            moduleScopeValueTypes[args[2]] = args[3]
        elif verb == "enumCase" and len(args) >= 2:
            moduleScopeValueTypes[args[1]] = args[0]
        else:
            parsedMemory = memory_parts(sourceLine)
            if parsedMemory is not None and parsedMemory[1] in {"mutable", "immutable"} and len(parsedMemory[2]) >= 3:
                moduleScopeValueTypes[parsedMemory[2][0]] = parsedMemory[2][1]

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
            elif verb == "storage" and len(args) >= 4:
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
                specAnchor="docs/reference/syntax-inventory.md#enum-domain-methods",
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
        storage local immutable lineBufferBytes ByteCount 384
        storage local immutable lineBufferCapacity Int32 256   # drift

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
            specAnchor="docs/reference/syntax-inventory.md#storage",
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
        specAnchor="docs/reference/syntax-inventory.md#call",
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
                    specAnchor="docs/reference/syntax-inventory.md#label",
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


# Deterministic, side-effect-free arithmetic / comparison builtins. A call to
# one of these is a pure function of its arguments, so when every argument is
# loop-invariant the result is identical on every iteration and the call can be
# hoisted above the loop header. The set is intentionally conservative — only
# pure compute targets, never anything that reads or writes memory / effects —
# so the SS3208 diagnostic stays high-precision (no false positives on calls
# whose value legitimately changes per iteration).
PURE_HOISTABLE_CALL_TARGETS: FrozenSet[str] = frozenset({
    "math.addInt64", "math.subtractInt64", "math.multiplyInt64",
    "math.divideInt64", "math.moduloInt64",
    "math.equalInt64", "math.notEqualInt64",
    "math.lessThanInt64", "math.lessThanOrEqualInt64",
    "math.greaterThanInt64", "math.greaterThanOrEqualInt64",
    "math.bitwiseAndInt64", "math.bitwiseOrInt64", "math.bitwiseXorInt64",
    "math.bitwiseNotInt64",
    "math.shiftLeftInt64", "math.shiftRightLogicalInt64",
    "math.shiftRightArithmeticInt64",
    "math.addInt32", "math.subtractInt32", "math.multiplyInt32",
    "math.divideInt32", "math.moduloInt32",
    "math.equalInt32", "math.notEqualInt32",
    "math.lessThanInt32", "math.greaterThanInt32",
    "math.addFloat64", "math.subtractFloat64", "math.multiplyFloat64",
    "math.divideFloat64",
    "math.equalFloat64", "math.notEqualFloat64",
    "math.lessThanFloat64", "math.lessThanOrEqualFloat64",
    "math.greaterThanFloat64", "math.greaterThanOrEqualFloat64",
})


def check_loop_invariant_pure_call(facts: ExtendedFacts) -> List[Diagnostic]:
    """SS3208 - a pure arithmetic/comparison call inside a loop body whose every
    argument is loop-invariant computes the same value on every iteration and
    can be hoisted above the loop header.

    Conservative for precision: only fires when the target is a deterministic
    side-effect-free builtin (PURE_HOISTABLE_CALL_TARGETS) and no argument is
    rebound or `set memory`-mutated inside the loop body. The loop body is the
    [labelIndex, backEdgeIndex] span of any back-edge — including unconditional
    `jump target <earlierLabel>`, which the idiomatic loop tail uses."""
    diagnostics: List[Diagnostic] = []
    for operation in facts.base.operations.values():
        operationCitations = narrative_citations_for_operation(facts, operation.name)
        labelIndexByName: Dict[str, int] = {}
        for lineIndex, sourceLine in enumerate(operation.lines):
            if is_comment(sourceLine) or not sourceLine.tokens:
                continue
            if sourceLine.verb == "label" and sourceLine.args:
                labelIndexByName[sourceLine.args[0]] = lineIndex

        loopBodyRanges: List[Tuple[int, int, str]] = []
        for lineIndex, sourceLine in enumerate(operation.lines):
            if is_comment(sourceLine) or not sourceLine.tokens:
                continue
            # Use the shared branch-target helper so every control-flow form is
            # covered identically to the rest of the linter — crucially the
            # canonical `branch if condition C target L` (target is args[4]),
            # `branch else target L`, branchIf*, branchSelected, runChecked, and
            # unconditional `jump target L`. A target whose label precedes this
            # row is a back-edge, so [labelIndex, lineIndex] is a loop body.
            for branchTarget in branch_target_names_from_row(sourceLine):
                labelIndex = labelIndexByName.get(branchTarget)
                if labelIndex is None or labelIndex >= lineIndex:
                    # Forward branch/jump (or unknown label), not a back-edge.
                    continue
                loopBodyRanges.append((labelIndex, lineIndex, branchTarget))

        # Dedup across overlapping / nested back-edge ranges so one `call` row
        # is reported at most once.
        flaggedCallLines: Set[int] = set()
        for loopStart, loopEnd, loopLabel in loopBodyRanges:
            bodyLines = operation.lines[loopStart:loopEnd]
            # Names that change across iterations: anything (re)defined or
            # mutated inside the loop body via any of the three write
            # mechanisms — `bind`, `set <scope>`, or a `storage`/`sharedState`
            # re-declaration that captures a mutated value.
            loopVariantNames: Set[str] = set()
            for bodyLine in bodyLines:
                if is_comment(bodyLine) or not bodyLine.tokens:
                    continue
                bind = bind_parts(bodyLine)
                if bind is not None:
                    loopVariantNames.add(bind[1])
                # `set <scope> <name> <value>` mutates <name>; scope may be
                # memory / local / shared / module, so key on the slot name
                # (args[1]) regardless of scope to avoid false positives.
                if bodyLine.verb == "set" and len(bodyLine.args) >= 2:
                    loopVariantNames.add(bodyLine.args[1])
                # `storage <scope> <mutability> <name> <type> <init>` declared
                # inside the loop redefines <name> (args[2]) each iteration; if
                # its initializer reads a mutated value it is NOT invariant.
                if bodyLine.verb == "storage" and len(bodyLine.args) >= 3:
                    loopVariantNames.add(bodyLine.args[2])
                # `sharedState <name> …` re-declaration similarly redefines it.
                if bodyLine.verb == "sharedState" and len(bodyLine.args) >= 2:
                    loopVariantNames.add(bodyLine.args[1])

            # Argument value operands grouped by the call they belong to.
            argOperandsByCall: Dict[str, List[str]] = {}
            for bodyLine in bodyLines:
                parts = argument_parts(bodyLine)
                if parts is None:
                    continue
                callName, _param, _type, value = parts
                argOperandsByCall.setdefault(callName, []).append(value)

            for bodyLine in bodyLines:
                if is_comment(bodyLine) or not bodyLine.tokens:
                    continue
                if bodyLine.verb != "call" or len(bodyLine.args) < 2:
                    continue
                callName = bodyLine.args[0]
                target = bodyLine.args[1]
                if target not in PURE_HOISTABLE_CALL_TARGETS:
                    continue
                operands = argOperandsByCall.get(callName, [])
                if not operands:
                    continue
                # Hoistable only if EVERY operand is loop-invariant.
                if any(value in loopVariantNames for value in operands):
                    continue
                if bodyLine.number in flaggedCallLines:
                    continue
                flaggedCallLines.add(bodyLine.number)
                diagnostics.append(Diagnostic(
                    tier=Tier.T3_REFINEMENT,
                    code="SS3208",
                    kind="performanceDiscipline.loopInvariantPureCall",
                    severity=Severity.WARNING,
                    subjectName=callName,
                    subjectKind="call",
                    gapEdge="loopHoist",
                    intentSlogan="loop-invariant pure call recomputed every iteration",
                    primary=span_of_line(bodyLine, "invariantPureCallInLoop"),
                    related=[
                        span_of_line(operation.lines[loopStart], "loopHeaderLabel"),
                        span_of_line(operation.line, "enclosingOperation"),
                    ],
                    invariantRule=(
                        f"`{target}` is side-effect-free and every argument of "
                        f"`{callName}` is loop-invariant, so it yields the same "
                        f"value each iteration; hoisting it above `label "
                        f"{loopLabel}` makes the once-per-loop computation "
                        f"explicit in the tape"
                    ),
                    specAnchor="docs/reference/syntax-inventory.md#call",
                    citations=operationCitations,
                    fixCandidates=[
                        FixCandidate(
                            name="hoistPureCallAboveLoop",
                            shape=(
                                f"# move `call {callName} {target}` and its arg "
                                f"lines BEFORE `label {loopLabel}`"
                            ),
                            evidence=[span_of_line(bodyLine)],
                        ),
                    ],
                    confidence=Confidence.HIGH,
                    effort=Effort.LOCAL,
                    passProvenance="check_loop_invariant_pure_call",
                    agentHint="a source-clarity refinement: makes the once-per-loop computation explicit in the dataflow tape rather than leaving it to optimizer LICM; the native -O2 backend already hoists pure loop-invariant arithmetic, so expect little or no runtime change",
                ))
    return diagnostics


def check_string_accumulator_append_in_loop(facts: ExtendedFacts) -> List[Diagnostic]:
    """Repeated strcat-style appends in loops rescan the accumulator."""
    diagnostics: List[Diagnostic] = []
    for operation in facts.base.operations.values():
        operationCitations = narrative_citations_for_operation(facts, operation.name)
        labelIndexByName: Dict[str, int] = {}
        for lineIndex, sourceLine in enumerate(operation.lines):
            if is_comment(sourceLine) or not sourceLine.tokens:
                continue
            if sourceLine.verb == "label" and sourceLine.args:
                labelIndexByName[sourceLine.args[0]] = lineIndex

        loopBodyRanges: List[Tuple[int, int, str]] = []
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
                continue
            loopBodyRanges.append((labelIndex, lineIndex, branchTarget))

        for loopStart, loopEnd, loopLabel in loopBodyRanges:
            for bodyLine in operation.lines[loopStart:loopEnd]:
                if is_comment(bodyLine) or not bodyLine.tokens:
                    continue
                if bodyLine.verb != "call" or len(bodyLine.args) < 2:
                    continue
                if bodyLine.args[1] not in C_STRING_ACCUMULATOR_CALL_TARGETS:
                    continue
                diagnostics.append(Diagnostic(
                    tier=Tier.T3_REFINEMENT,
                    code="SS3203",
                    kind="performanceDiscipline.stringAccumulatorAppendInLoop",
                    severity=Severity.WARNING,
                    subjectName=bodyLine.args[0],
                    subjectKind="call",
                    gapEdge="cursorBuilder",
                    intentSlogan="strcat-style accumulator append in loop",
                    primary=span_of_line(bodyLine, "stringAppendInLoop"),
                    related=[
                        span_of_line(operation.lines[loopStart], "loopHeaderLabel"),
                        span_of_line(operation.line, "enclosingOperation"),
                    ],
                    invariantRule=(
                        f"`{bodyLine.args[1]}` rescans the destination on every "
                        f"iteration of `label {loopLabel}`; track a write offset "
                        "and copy or format at that cursor instead"
                    ),
                    specAnchor="docs/optimization-guide.md#bounded-string-accumulators",
                    citations=operationCitations,
                    fixCandidates=[
                        FixCandidate(
                            name="useCursorBasedBuilder",
                            shape=(
                                f"# track writeOffset outside `label {loopLabel}`\n"
                                "# write at pointer.offset(destination, writeOffset)\n"
                                "# increment writeOffset by the bytes written"
                            ),
                            evidence=[span_of_line(bodyLine)],
                        ),
                    ],
                    confidence=Confidence.HIGH,
                    effort=Effort.LOCAL,
                    passProvenance="check_string_accumulator_append_in_loop",
                    agentHint=(
                        "strcat and strncat are bounded by NUL-terminated scans; "
                        "hot loops should append with an explicit cursor"
                    ),
                ))
    return diagnostics


def check_snprintf_i32_offset_without_widening(facts: ExtendedFacts) -> List[Diagnostic]:
    """A c.snprintf byte count is Int32; cursor offsets are Int64."""
    diagnostics: List[Diagnostic] = []
    for operation in facts.base.operations.values():
        operationCalls = collect_operation_calls(operation)
        snprintfResultNames: Dict[str, SourceLine] = {}
        for callFact in operationCalls.values():
            if callFact.target != "c.snprintf":
                continue
            for resultName, bindLine in call_success_value_lines(callFact):
                snprintfResultNames[resultName] = bindLine
        if not snprintfResultNames:
            continue
        operationCitations = narrative_citations_for_operation(facts, operation.name)
        for callFact in operationCalls.values():
            if callFact.target not in {"math.addInt64", "math.addInt64"}:
                continue
            for argLine in callFact.arg_lines:
                if len(argLine.args) < 3:
                    continue
                argValue = argLine.args[2]
                if argValue not in snprintfResultNames:
                    continue
                diagnostics.append(Diagnostic(
                    tier=Tier.T3_REFINEMENT,
                    code="SS3205",
                    kind="performanceDiscipline.snprintfInt32OffsetWithoutWidening",
                    severity=Severity.WARNING,
                    subjectName=callFact.name,
                    subjectKind="call",
                    gapEdge="signExtendInt32ToInt64",
                    intentSlogan="snprintf count added to i64 cursor",
                    primary=span_of_line(argLine, "i64AddArgument"),
                    related=[
                        span_of_line(snprintfResultNames[argValue], "snprintfResultBind"),
                        span_of_line(operation.line, "enclosingOperation"),
                    ],
                    invariantRule=(
                        "`c.snprintf` returns an Int32 byte count; "
                        "cursor math using an Int64 add target must first widen it "
                        "with math.signExtendInt32ToInt64"
                    ),
                    specAnchor="docs/optimization-guide.md#bounded-string-accumulators",
                    citations=operationCitations,
                    fixCandidates=[
                        FixCandidate(
                            name="widenSnprintfResultBeforeCursorMath",
                            shape=(
                                f"call widen{argValue}Call math.signExtendInt32ToInt64\n"
                                f"arg widen{argValue}Call inputValue {argValue}\n"
                                f"run widen{argValue}Call\n"
                                f"bind {argValue}Int64 Int64 widen{argValue}Call\n"
                                f"# use `{argValue}Int64` in `{callFact.name}`"
                            ),
                            evidence=[span_of_line(argLine)],
                        ),
                    ],
                    confidence=Confidence.HIGH,
                    effort=Effort.LOCAL,
                    passProvenance="check_snprintf_i32_offset_without_widening",
                    agentHint=(
                        "cursor builders should keep offsets in one width; "
                        "explicit widening prevents silent no-op or width-drift lowering"
                    ),
                ))
    return diagnostics


def check_gui_selection_handler_appends_list_item(facts: ExtendedFacts) -> List[Diagnostic]:
    """Reading list selection and appending an item in the same GUI handler
    is usually an accidental growth path, not a completion/update."""
    diagnostics: List[Diagnostic] = []
    for operation in facts.base.operations.values():
        operationCalls = collect_operation_calls(operation)
        selectionReads = [
            callFact for callFact in operationCalls.values()
            if callFact.target == "gui.listBoxSelectedIndex"
        ]
        if not selectionReads:
            continue
        appendCalls = [
            callFact for callFact in operationCalls.values()
            if callFact.target == "gui.listBoxAppendItem"
        ]
        if not appendCalls:
            continue
        operationCitations = narrative_citations_for_operation(facts, operation.name)
        for appendCall in appendCalls:
            diagnostics.append(Diagnostic(
                tier=Tier.T3_REFINEMENT,
                code="SS3206",
                kind="performanceDiscipline.selectedListAppendInHandler",
                severity=Severity.WARNING,
                subjectName=operation.name,
                subjectKind="operation",
                gapEdge="selectionMutationBoundary",
                intentSlogan="selection handler appends list item",
                primary=span_of_line(appendCall.line, "listAppendCall"),
                related=[
                    span_of_line(selectionReads[0].line, "selectionReadCall"),
                    span_of_line(operation.line, "enclosingOperation"),
                ],
                invariantRule=(
                    "an operation that reads gui.listBoxSelectedIndex should "
                    "not also append to the same list; complete/update handlers "
                    "must mutate status or selected-row state without growing the collection"
                ),
                specAnchor="docs/optimization-guide.md#gui-event-mutation-boundaries",
                citations=operationCitations,
                fixCandidates=[
                    FixCandidate(
                        name="separateAddAndSelectionHandlers",
                        shape=(
                            "# keep gui.listBoxAppendItem in the add/create handler\n"
                            "# keep selection handlers to selected-index reads and status/row updates"
                        ),
                        evidence=[span_of_line(appendCall.line)],
                    ),
                ],
                confidence=Confidence.MEDIUM,
                effort=Effort.LOCAL,
                passProvenance="check_gui_selection_handler_appends_list_item",
                agentHint=(
                    "this catches the completed-task button pattern that grows "
                    "a list every click instead of updating the selected item"
                ),
            ))
    return diagnostics


def _row_count_mutation_target_needs_guard(callFact: CallFact) -> bool:
    if callFact.target in FIXED_ROW_COUNT_MUTATION_TARGETS:
        return True
    target = callFact.target.lower()
    if not (target.startswith("insert") or target.startswith("split")):
        return False
    return (
        "row" in target
        and call_arg_value(callFact, "activeRowCount") is not None
        and call_arg_value(callFact, "maxRows") is not None
    )


def check_row_count_mutation_unchecked(facts: ExtendedFacts) -> List[Diagnostic]:
    """Fixed-capacity row mutators return the old row count when full; callers
    must branch before moving cursors or marking dirty state."""
    diagnostics: List[Diagnostic] = []
    for operation in facts.base.operations.values():
        operationCalls = collect_operation_calls(operation)
        operationCitations = narrative_citations_for_operation(facts, operation.name)
        for callFact in operationCalls.values():
            if not _row_count_mutation_target_needs_guard(callFact):
                continue
            activeCountName = call_arg_value(callFact, "activeRowCount")
            if activeCountName is None:
                continue
            resultNames = call_success_value_names(callFact)
            if not resultNames:
                continue
            comparisonBoolNames: Set[str] = set()
            comparisonLines: List[SourceLine] = []
            for compareCall in operationCalls.values():
                if compareCall.line.number <= callFact.line.number:
                    continue
                if compareCall.target != "math.equalInt64":
                    continue
                leftValue = call_arg_value(compareCall, "left")
                rightValue = call_arg_value(compareCall, "right")
                if not (
                    (leftValue in resultNames and rightValue == activeCountName)
                    or (rightValue in resultNames and leftValue == activeCountName)
                ):
                    continue
                comparisonBoolNames.update(call_success_value_names(compareCall))
                comparisonLines.append(compareCall.line)
            hasBranch = False
            if comparisonBoolNames:
                for sourceLine in operation.lines:
                    if (not is_comment(sourceLine) and sourceLine.tokens
                            and sourceLine.verb == "branchIf"
                            and len(sourceLine.args) >= 2
                            and sourceLine.args[0] in comparisonBoolNames):
                        hasBranch = True
                        break
            if hasBranch:
                continue
            related = [span_of_line(operation.line, "enclosingOperation")]
            related.extend(span_of_line(line, "rowCountComparison") for line in comparisonLines[:1])
            diagnostics.append(Diagnostic(
                tier=Tier.T3_REFINEMENT,
                code="SS3207",
                kind="performanceDiscipline.rowCountMutationUnchecked",
                severity=Severity.WARNING,
                subjectName=callFact.name,
                subjectKind="call",
                gapEdge="capacityFailureBranch",
                intentSlogan="row-count mutation lacks full-buffer branch",
                primary=span_of_line(callFact.line, "rowCountMutationCall"),
                related=related,
                invariantRule=(
                    f"`{callFact.target}` returns the unchanged activeRowCount "
                    "when the fixed row buffer is full; callers must compare "
                    "the returned row count to the prior count and branch before "
                    "moving cursors, setting dirty state, or writing into the row"
                ),
                specAnchor="docs/optimization-guide.md#fixed-capacity-row-mutations",
                citations=operationCitations,
                fixCandidates=[
                    FixCandidate(
                        name="branchOnUnchangedRowCount",
                        shape=(
                            f"call {callFact.name}FailedCheckCall math.equalInt64\n"
                            f"arg {callFact.name}FailedCheckCall left <rowsAfterMutation>\n"
                            f"arg {callFact.name}FailedCheckCall right {activeCountName}\n"
                            f"run {callFact.name}FailedCheckCall\n"
                            f"bind {callFact.name}Failed Bool {callFact.name}FailedCheckCall\n"
                            f"branchIf {callFact.name}Failed <noMutationLabel>"
                        ),
                        evidence=[span_of_line(callFact.line)],
                    ),
                ],
                confidence=Confidence.HIGH,
                effort=Effort.LOCAL,
                passProvenance="check_row_count_mutation_unchecked",
                agentHint=(
                    "fixed-capacity editors must treat unchanged row count as "
                    "a refused insert/split before deriving cursor positions from it"
                ),
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
                specAnchor="docs/reference/syntax-inventory.md#ignoreValue",
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
                specAnchor="docs/reference/syntax-inventory.md#memoryHeap",
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
            specAnchor="docs/reference/syntax-inventory.md#memoryAllocationSource",
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


def check_unchecked_heap_allocation(facts: ExtendedFacts) -> List[Diagnostic]:
    """Heap allocation calls must explicitly handle allocation failure."""
    diagnostics: List[Diagnostic] = []
    for operation in facts.base.operations.values():
        operationCitations = narrative_citations_for_operation(facts, operation.name)
        operationCalls = collect_operation_calls(operation)
        for callFact in operationCalls.values():
            if callFact.target not in HEAP_ALLOCATION_CALL_TARGETS:
                continue
            if callFact.run_checked_lines:
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
                code="SS3305",
                kind="memoryDiscipline.uncheckedHeapAllocation",
                severity=Severity.WARNING,
                subjectName=callFact.name,
                subjectKind="call",
                gapEdge=",".join(missingDisposition),
                intentSlogan="heap allocation without failure path",
                primary=span_of_line(callFact.line, "allocationCall"),
                related=[span_of_line(operation.line, "enclosingOperation")],
                invariantRule=(
                    f"`{callFact.target}` can fail under memory pressure; "
                    "allocation calls must have both `bindError` and "
                    "`branchIfError`"
                ),
                specAnchor="docs/reference/syntax-inventory.md#bindError",
                citations=operationCitations,
                fixCandidates=[
                    FixCandidate(
                        name="addAllocationFailurePath",
                        shape=(
                            f"bindError {callFact.name}Error <ErrorType> {callFact.name}\n"
                            f"branchIfError {callFact.name} <allocationFailedLabel>\n"
                            f"# ...success continuation...\n"
                            f"label <allocationFailedLabel>\n"
                            f"returnError {callFact.name}Error"
                        ),
                        evidence=[span_of_line(callFact.line)],
                    ),
                ],
                confidence=Confidence.HIGH,
                effort=Effort.LOCAL,
                passProvenance="check_unchecked_heap_allocation",
                agentHint=(
                    "allocator failure must be represented in the operation's "
                    "control flow before the returned pointer is used"
                ),
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
            # is a pointer/handle surface that transfers ownership.
            outputLine = None
            for line in operation.lines:
                if line.verb != "output" or not line.args:
                    continue
                if line.args[0] == operation.name:
                    outputLine = line
                    break
                if len(line.args) >= 2 and line.args[0] == "operation" and line.args[1] == operation.name:
                    outputLine = line
                    break
            if outputLine:
                outputArgs = outputLine.args[2:] if outputLine.args[0] == "operation" else outputLine.args[1:]
                outputTypeName = outputArgs[0] if outputArgs else ""
                if outputTypeName in {"OpaquePointer", "String", "FileHandle"}:
                    # Likely an allocator wrapper — caller owns the lifetime.
                    continue
                if outputTypeName == "Result" and len(outputArgs) >= 2:
                    if outputArgs[1] in {"OpaquePointer", "String", "FileHandle"}:
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
                specAnchor="docs/reference/syntax-inventory.md#defer",
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
            specAnchor="docs/reference/syntax-inventory.md#memoryStackLimit",
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
            specAnchor="docs/reference/syntax-inventory.md#recordAlign",
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
            specAnchor="docs/reference/syntax-inventory.md#arrayLength",
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
            specAnchor="docs/reference/syntax-inventory.md#smallListSpillAllocator",
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
            specAnchor="docs/reference/syntax-inventory.md#typeLiteralEncoding",
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
                specAnchor="docs/reference/syntax-inventory.md#awaitGroup",
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
                specAnchor="docs/reference/syntax-inventory.md#unlock",
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
        for submitLine, workName, _poolName in submittedWork:
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
                specAnchor="docs/reference/syntax-inventory.md#awaitWork",
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


def check_invalid_submit_work(facts: ExtendedFacts) -> List[Diagnostic]:
    """`submitWork WORK POOL` must name a declared user-operation work item."""
    diagnostics: List[Diagnostic] = []
    userOperationNames = set(facts.base.operations.keys())
    for operation in facts.base.operations.values():
        operationCitations = narrative_citations_for_operation(facts, operation.name)
        submittedWork = facts.operationSubmittedWork.get(operation.name, [])
        workTargets = facts.operationWorkTargets.get(operation.name, {})
        workArgs = facts.operationWorkArgs.get(operation.name, {})
        workerPools = set(facts.moduleWorkerPools)
        workerPools.update(facts.operationWorkerPools.get(operation.name, {}))
        flaggedWork: Set[Tuple[str, str]] = set()

        def add_invalid_submit_work_diagnostic(
            submitLine: SourceLine,
            workName: str,
            gapEdge: str,
            invariantRule: str,
            workLine: Optional[SourceLine] = None,
        ) -> None:
            key = (workName, gapEdge)
            if key in flaggedWork:
                return
            flaggedWork.add(key)
            related = [span_of_line(operation.line, "enclosingOperation")]
            if workLine is not None:
                related.append(span_of_line(workLine, "workDeclaration"))
            diagnostics.append(Diagnostic(
                tier=Tier.T1_SPEC,
                code="SS3514",
                kind="concurrencyDiscipline.invalidSubmitWork",
                severity=Severity.ERROR,
                subjectName=workName,
                subjectKind="work",
                gapEdge=gapEdge,
                intentSlogan="submitWork references invalid work item",
                primary=span_of_line(submitLine, "submitWorkSite"),
                related=related,
                invariantRule=invariantRule,
                specAnchor="docs/reference/syntax-inventory.md#submitWork",
                citations=operationCitations,
                fixCandidates=[
                    FixCandidate(
                        name="declareWorkTarget",
                        shape=(
                            f"work {workName} target <userOperation>\n"
                            f"submitWork {workName} <workerPool>"
                        ),
                        evidence=[span_of_line(submitLine)],
                    ),
                ],
                confidence=Confidence.HIGH,
                blocksCompile=True,
                effort=Effort.LOCAL,
                passProvenance="check_invalid_submit_work",
                agentHint=(
                    "worker-pool lowering dispatches through a user operation; "
                    "unknown work would otherwise await a zero-value stub"
                ),
            ))

        for submitLine, workName, poolName in submittedWork:
            if poolName not in workerPools:
                add_invalid_submit_work_diagnostic(
                    submitLine,
                    workName,
                    "workerPool",
                    (
                        f"`submitWork {workName} {poolName}` requires a "
                        f"declared `workerPool {poolName}` row"
                    ),
                )
            workInfos = workTargets.get(workName, [])
            if not workInfos:
                add_invalid_submit_work_diagnostic(
                    submitLine,
                    workName,
                    "workDeclaration",
                    (
                        f"`submitWork {workName}` requires a preceding "
                        f"`work {workName} target <userOperation>` row in "
                        f"operation `{operation.name}`"
                    ),
                )
                continue
            priorWorkInfos = [
                workInfo
                for workInfo in workInfos
                if workInfo[0].number < submitLine.number
            ]
            if not priorWorkInfos:
                add_invalid_submit_work_diagnostic(
                    submitLine,
                    workName,
                    "workDeclaration",
                    (
                        f"`submitWork {workName}` requires `work {workName} "
                        "target <userOperation>` to appear before the "
                        "submit row"
                    ),
                    workInfos[0][0],
                )
                continue
            priorTargetWorkInfos = [
                workInfo
                for workInfo in priorWorkInfos
                if workInfo[1]
            ]
            if not priorTargetWorkInfos:
                workLine, _targetOperation = max(
                    priorWorkInfos,
                    key=lambda workInfo: workInfo[0].number,
                )
                add_invalid_submit_work_diagnostic(
                    submitLine,
                    workName,
                    "workTarget",
                    (
                        f"`work {workName}` must name a target user operation "
                        "before it can be submitted"
                    ),
                    workLine,
                )
                continue
            workLine, targetOperation = max(
                priorTargetWorkInfos,
                key=lambda workInfo: workInfo[0].number,
            )
            if not targetOperation:
                add_invalid_submit_work_diagnostic(
                    submitLine,
                    workName,
                    "workTarget",
                    (
                        f"`work {workName}` must name a target user operation "
                        "before it can be submitted"
                    ),
                    workLine,
                )
                continue
            if targetOperation not in userOperationNames:
                add_invalid_submit_work_diagnostic(
                    submitLine,
                    workName,
                    "workTarget",
                    (
                        f"`work {workName} target {targetOperation}` must "
                        "target a declared user operation"
                    ),
                    workLine,
                )
                continue
            requiredInputs = {
                parsedInput[1]
                for inputLine in facts.base.operations[targetOperation].lines
                for parsedInput in [input_parts(inputLine)]
                if parsedInput is not None and parsedInput[0] == targetOperation
            }
            providedArgs = {
                argName
                for argName, argLines in workArgs.get(workName, {}).items()
                if any(argLine.number < submitLine.number for argLine in argLines)
            }
            missingInputs = sorted(requiredInputs - providedArgs)
            for missingInput in missingInputs:
                add_invalid_submit_work_diagnostic(
                    submitLine,
                    workName,
                    "workArg",
                    (
                        f"`work {workName} target {targetOperation}` is "
                        f"submitted without required `workArg {workName} "
                        f"{missingInput} <value>`"
                    ),
                    workLine,
                )
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
            specAnchor="docs/reference/syntax-inventory.md#selectCase",
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
                specAnchor="docs/reference/syntax-inventory.md#select",
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


def check_await_wait_set_shape(facts: ExtendedFacts) -> List[Diagnostic]:
    """Validate the compact `await WAIT_SET` / `case` / `done` block shape.

    The wait-set name is not a call reference; the cases are the call
    references. This checker catches malformed blocks before the compiler has
    to fail deeper in lowering.
    """
    diagnostics: List[Diagnostic] = []
    for operation in facts.base.operations.values():
        operationCitations = narrative_citations_for_operation(facts, operation.name)
        operationCalls = collect_operation_calls(operation)
        lines = [
            sourceLine
            for sourceLine in operation.lines
            if sourceLine.tokens and not is_comment(sourceLine)
        ]
        labelLineByName = {
            sourceLine.args[0]: sourceLine
            for sourceLine in lines
            if sourceLine.verb == "label" and sourceLine.args
        }
        branchElseByLine = branch_else_targets_by_line(lines)

        def branch_targets_for_wait_set(sourceLine: SourceLine) -> List[str]:
            return branch_target_names_with_attached_else(
                sourceLine, branchElseByLine)

        def is_wait_set_gap_ignored(sourceLine: SourceLine) -> bool:
            return sourceLine.verb in {
                "input", "output", "effect", "async",
                "purpose", "invariant", "warning",
            }

        def next_effective_line_after(lineNumber: int) -> Optional[SourceLine]:
            for candidate in lines:
                if candidate.number <= lineNumber:
                    continue
                if is_wait_set_gap_ignored(candidate):
                    continue
                return candidate
            return None

        def label_before_line(lineNumber: int) -> Optional[str]:
            currentLabel: Optional[str] = None
            for candidate in lines:
                if candidate.number >= lineNumber:
                    break
                if candidate.verb == "label" and candidate.args:
                    currentLabel = candidate.args[0]
            return currentLabel

        def call_result_reference(sourceLine: SourceLine) -> Optional[str]:
            parsedBind = bind_parts(sourceLine)
            if parsedBind is not None:
                return parsedBind[3]
            parsedIgnore = ignore_parts(sourceLine)
            if parsedIgnore is not None:
                return parsedIgnore[1]
            parsedBranchErrorSource = branch_error_source(sourceLine)
            if parsedBranchErrorSource is not None:
                return parsedBranchErrorSource
            if sourceLine.verb == "await" and len(sourceLine.args) == 1:
                return sourceLine.args[0]
            return None

        def symbol_definition(sourceLine: SourceLine) -> Optional[str]:
            parsedBind = bind_parts(sourceLine)
            if parsedBind is not None:
                return parsedBind[1]
            if sourceLine.verb == "fieldGet" and sourceLine.args:
                return sourceLine.args[0]
            if sourceLine.verb in {"new", "call", "recordBuild", "receive"} and sourceLine.args:
                return sourceLine.args[0]
            if (sourceLine.verb == "read" and len(sourceLine.args) >= 4
                    and sourceLine.args[0] in {"sharedState", "local", "module"}):
                return sourceLine.args[1]
            if sourceLine.verb in {"memory", "storage"} and len(sourceLine.args) >= 4:
                return sourceLine.args[2]
            return None

        def call_result_definition(sourceLine: SourceLine) -> Optional[str]:
            if sourceLine.verb in {"run", "await", "submitWork", "awaitWork"} and sourceLine.args:
                return sourceLine.args[0]
            return None

        def symbol_references(sourceLine: SourceLine) -> Set[str]:
            refs: Set[str] = set()
            resultReference = call_result_reference(sourceLine)
            if resultReference is not None:
                refs.add(resultReference)
            parsedArgument = argument_parts(sourceLine)
            if parsedArgument is not None:
                refs.add(parsedArgument[3])
            elif sourceLine.verb == "cancelOn" and len(sourceLine.args) >= 2:
                refs.add(sourceLine.args[1])
            elif sourceLine.verb in {"run", "runChecked"} and sourceLine.args:
                refs.add(sourceLine.args[0])
            elif sourceLine.verb == "fieldSet" and len(sourceLine.args) >= 3:
                refs.add(sourceLine.args[0])
                refs.add(sourceLine.args[2])
            elif sourceLine.verb == "fieldGet" and len(sourceLine.args) >= 3:
                refs.add(sourceLine.args[2])
            elif sourceLine.verb in {"memory", "storage"} and len(sourceLine.args) >= 5:
                refs.add(sourceLine.args[4])
            elif (sourceLine.verb == "read" and len(sourceLine.args) >= 4
                    and sourceLine.args[0] in {"sharedState", "local", "module"}):
                refs.add(sourceLine.args[3])
            elif sourceLine.verb == "receive" and len(sourceLine.args) >= 3:
                refs.add(sourceLine.args[2])
            elif sourceLine.verb == "send" and len(sourceLine.args) >= 2:
                refs.add(sourceLine.args[1])
            elif sourceLine.verb == "workArg" and len(sourceLine.args) >= 3:
                refs.add(sourceLine.args[2])
            elif sourceLine.verb in {"defer", "deferLog", "deferAwaitLog"} and len(sourceLine.args) >= 3:
                refs.update(sourceLine.args[2:])
            elif sourceLine.verb == "deferWhenExitLog" and len(sourceLine.args) >= 4:
                refs.update(sourceLine.args[3:])
            elif sourceLine.verb == "set" and len(sourceLine.args) >= 3:
                refs.add(sourceLine.args[1])
                refs.add(sourceLine.args[2])
            else:
                parsedReturn = return_parts(sourceLine)
                if parsedReturn is not None and parsedReturn[1] is not None:
                    refs.add(parsedReturn[1])
                elif (sourceLine.verb == "branch" and len(sourceLine.args) >= 5
                        and sourceLine.args[0] == "if"):
                    refs.add(sourceLine.args[2])
                elif sourceLine.verb == "branchIf" and sourceLine.args:
                    refs.add(sourceLine.args[0])
                elif sourceLine.verb == "makeError" and len(sourceLine.args) >= 3:
                    refs.add(sourceLine.args[2])
            return refs

        def label_reaches_line(labelName: str, targetLine: SourceLine) -> bool:
            labelIndices = {
                candidate.args[0]: index
                for index, candidate in enumerate(lines)
                if candidate.verb == "label" and candidate.args
            }
            lineIndices = {
                candidate.number: index
                for index, candidate in enumerate(lines)
            }
            branchElseByLine: Dict[int, str] = {}
            for index, candidate in enumerate(lines[:-1]):
                if (candidate.verb == "branch" and candidate.args
                        and candidate.args[0] in {"if", "error"}):
                    nextLine = lines[index + 1]
                    if nextLine.verb == "branch" and nextLine.args[:2] == ["else", "target"]:
                        branchElseByLine[candidate.number] = nextLine.args[2]

            def add_label_successor(successors: List[int], targetLabel: str) -> None:
                targetIndex = labelIndices.get(targetLabel)
                if targetIndex is not None:
                    successors.append(targetIndex)

            def add_fallthrough_successor(successors: List[int], index: int) -> None:
                nextIndex = index + 1
                if nextIndex < len(lines):
                    successors.append(nextIndex)

            def successor_indices(index: int) -> List[int]:
                sourceLine = lines[index]
                args = sourceLine.args
                successors: List[int] = []
                if sourceLine.verb == "await":
                    cursor = index + 1
                    foundWaitSetRows = False
                    while cursor < len(lines):
                        candidate = lines[cursor]
                        if candidate.verb == "case":
                            foundWaitSetRows = True
                            if len(candidate.args) >= 2:
                                add_label_successor(successors, candidate.args[1])
                            cursor += 1
                            continue
                        if candidate.verb == "done":
                            foundWaitSetRows = True
                            if candidate.args:
                                add_label_successor(successors, candidate.args[0])
                            break
                        break
                    if foundWaitSetRows:
                        return successors
                if sourceLine.verb in {"return", "returnOk", "returnError", "returnVoid"}:
                    return successors
                if sourceLine.verb == "jump" and len(args) >= 2 and args[0] == "target":
                    add_label_successor(successors, args[1])
                    return successors
                if sourceLine.verb == "branch":
                    if len(args) >= 5 and args[0] in {"if", "error"} and args[3] == "target":
                        add_label_successor(successors, args[4])
                        elseLabel = branchElseByLine.get(sourceLine.number)
                        if elseLabel is None:
                            add_fallthrough_successor(successors, index)
                        else:
                            add_label_successor(successors, elseLabel)
                        return successors
                    if len(args) >= 3 and args[0] == "else" and args[1] == "target":
                        add_label_successor(successors, args[2])
                        return successors
                    if args:
                        add_label_successor(successors, args[0])
                        add_fallthrough_successor(successors, index)
                        return successors
                if sourceLine.verb == "branchIf" and len(args) >= 2:
                    add_label_successor(successors, args[1])
                    if len(args) >= 3:
                        add_label_successor(successors, args[2])
                    else:
                        add_fallthrough_successor(successors, index)
                    return successors
                if sourceLine.verb in {"branchIfError", "branchIfGroupError", "branchIfChannelClosed"} and len(args) >= 2:
                    add_label_successor(successors, args[1])
                    add_fallthrough_successor(successors, index)
                    return successors
                if sourceLine.verb == "runChecked" and len(args) >= 9:
                    add_label_successor(successors, args[8])
                    add_fallthrough_successor(successors, index)
                    return successors
                if sourceLine.verb == "branchSelected" and len(args) >= 3:
                    add_label_successor(successors, args[2])
                    add_fallthrough_successor(successors, index)
                    return successors
                add_fallthrough_successor(successors, index)
                return successors

            startIndex = labelIndices.get(labelName)
            targetIndex = lineIndices.get(targetLine.number)
            if startIndex is None or targetIndex is None:
                return False
            seen: Set[int] = set()
            stack = [startIndex]
            while stack:
                currentIndex = stack.pop()
                if currentIndex in seen:
                    continue
                if currentIndex == targetIndex:
                    return True
                seen.add(currentIndex)
                stack.extend(successor_indices(currentIndex))
            return False

        def start_reentry_edge(startLine: SourceLine) -> Optional[Tuple[SourceLine, str]]:
            reachableLineNumbers = source_line_reachable_numbers(operation)
            labelsBeforeStart = {
                labelName
                for labelName, labelLine in labelLineByName.items()
                if labelLine.number <= startLine.number
            }
            for candidate in lines:
                if candidate.number <= startLine.number:
                    continue
                if candidate.number not in reachableLineNumbers:
                    continue
                for targetLabel in branch_targets_for_wait_set(candidate):
                    if (targetLabel in labelsBeforeStart
                            and label_reaches_line(targetLabel, startLine)):
                        return candidate, targetLabel
            return None

        def add_case_result_ownership_diagnostic(
            row: SourceLine,
            callName: str,
            waitSetName: str,
            targetLabel: str,
            caseLine: SourceLine,
            *,
            escapeTarget: Optional[str] = None,
        ) -> None:
            isEscape = escapeTarget is not None
            diagnostics.append(Diagnostic(
                tier=Tier.T1_SPEC,
                code="SS3509",
                kind="concurrencyDiscipline.awaitWaitSetMalformed",
                severity=Severity.ERROR,
                subjectName=callName,
                subjectKind="call",
                gapEdge=(
                    "caseResultPrivateEscape" if isEscape
                    else "caseResultPrivateEntry"
                ),
                intentSlogan=(
                    "wait-set case result escapes its handler"
                    if isEscape
                    else "wait-set case result read outside its handler"
                ),
                primary=span_of_line(row, "callResultUse"),
                related=[span_of_line(caseLine, "caseSite")],
                invariantRule=(
                    (
                        f"`case {callName} {targetLabel}` materializes its "
                        f"result only for handler `{targetLabel}`; "
                        f"`{row.verb}` cannot write it into non-private "
                        f"state `{escapeTarget}` where later code can "
                        "observe it"
                    )
                    if isEscape
                    else (
                        f"`case {callName} {targetLabel}` materializes its "
                        f"result only for handler `{targetLabel}`; "
                        f"`{row.verb}` cannot read that call from another "
                        "label"
                    )
                ),
                specAnchor="docs/reference/syntax-inventory.md#case",
                citations=operationCitations,
                fixCandidates=[
                    FixCandidate(
                        name=(
                            "keepResultHandlerLocal" if isEscape
                            else "moveResultReadIntoCaseHandler"
                        ),
                        shape=(
                            f"# keep `{callName}` in handler-local state"
                            if isEscape
                            else f"label {targetLabel}\n{row.raw}"
                        ),
                        evidence=[span_of_line(row)],
                    ),
                ],
                confidence=Confidence.HIGH,
                blocksCompile=True,
                effort=Effort.LOCAL,
                passProvenance="check_await_wait_set_shape",
                agentHint="case result SSA values only dominate their selected handler block",
            ))

        def add_case_handler_reentry_diagnostic(
            row: SourceLine,
            callName: str,
            waitSetName: str,
            targetLabel: str,
            waitEntryLabel: str,
            gapEdge: str = "caseHandlerReentry",
        ) -> None:
            diagnostics.append(Diagnostic(
                tier=Tier.T1_SPEC,
                code="SS3509",
                kind="concurrencyDiscipline.awaitWaitSetMalformed",
                severity=Severity.ERROR,
                subjectName=callName,
                subjectKind="call",
                gapEdge=gapEdge,
                intentSlogan="wait-set case handler does not re-enter wait set",
                primary=span_of_line(row, "caseHandlerControl"),
                invariantRule=(
                    f"`case {callName} {targetLabel}` must finish by jumping "
                    f"back to `{waitEntryLabel}` so remaining futures are "
                    "consumed before the operation exits"
                ),
                specAnchor="docs/reference/syntax-inventory.md#case",
                citations=operationCitations,
                fixCandidates=[
                    FixCandidate(
                        name="jumpBackToWaitSet",
                        shape=f"jump target {waitEntryLabel}",
                        evidence=[span_of_line(row)],
                    ),
                ],
                confidence=Confidence.HIGH,
                blocksCompile=True,
                effort=Effort.LOCAL,
                passProvenance="check_await_wait_set_shape",
                agentHint="wait-set handlers cannot abandon sibling futures without explicit cleanup semantics",
            ))

        def add_wait_set_arity_diagnostic(
            row: SourceLine,
            waitSetName: str,
            expectedShape: str,
            expectedCount: int,
        ) -> None:
            diagnostics.append(Diagnostic(
                tier=Tier.T1_SPEC,
                code="SS3509",
                kind="concurrencyDiscipline.awaitWaitSetMalformed",
                severity=Severity.ERROR,
                subjectName=waitSetName or row.verb,
                subjectKind="awaitWaitSetRow",
                gapEdge="argumentCount",
                intentSlogan=f"`{row.verb}` has wrong argument count",
                primary=span_of_line(row, f"{row.verb}Site"),
                invariantRule=(
                    f"`{row.verb}` rows in an await wait set must have exactly "
                    f"{expectedCount} argument(s): `{expectedShape}`"
                ),
                specAnchor=f"docs/reference/syntax-inventory.md#{row.verb}",
                citations=operationCitations,
                fixCandidates=[
                    FixCandidate(
                        name="useExactWaitSetRowShape",
                        shape=expectedShape,
                        evidence=[span_of_line(row)],
                    ),
                ],
                confidence=Confidence.HIGH,
                blocksCompile=True,
                effort=Effort.TRIVIAL,
                passProvenance="check_await_wait_set_shape",
                agentHint="wait-set structural rows do not accept trailing metadata tokens",
            ))

        consumedLineNumbers: Set[int] = set()
        waitSetAwaitLineNumbers: Set[int] = set()
        caseCompletionLines: Dict[str, SourceLine] = {}
        caseCompletionOwners: Dict[str, Tuple[str, str, SourceLine]] = {}
        index = 0
        while index < len(lines):
            sourceLine = lines[index]
            if sourceLine.verb != "await":
                index += 1
                continue
            nextIndex = index + 1
            if nextIndex >= len(lines) or lines[nextIndex].verb not in {"case", "done"}:
                index += 1
                continue
            waitSetAwaitLineNumbers.add(sourceLine.number)
            waitSetName = sourceLine.args[0] if sourceLine.args else ""
            if len(sourceLine.args) != 1:
                add_wait_set_arity_diagnostic(
                    sourceLine, waitSetName, "await <waitSetName>", 1)
            if waitSetName and waitSetName in operationCalls:
                callFact = operationCalls[waitSetName]
                diagnostics.append(Diagnostic(
                    tier=Tier.T1_SPEC,
                    code="SS3509",
                    kind="concurrencyDiscipline.awaitWaitSetMalformed",
                    severity=Severity.ERROR,
                    subjectName=waitSetName,
                    subjectKind="awaitWaitSet",
                    gapEdge="waitSetNameCallCollision",
                    intentSlogan="wait-set name collides with call name",
                    primary=span_of_line(sourceLine, "awaitSite"),
                    related=[span_of_line(callFact.line, "callDeclaration")],
                    invariantRule=(
                        f"`await {waitSetName}` followed by `case` rows is "
                        "a wait set, not a call; choose a wait-set name that "
                        "does not match any declared call"
                    ),
                    specAnchor="docs/reference/syntax-inventory.md#await",
                    citations=operationCitations,
                    fixCandidates=[
                        FixCandidate(
                            name="renameWaitSet",
                            shape="await <freshWaitSetName>",
                            evidence=[span_of_line(sourceLine)],
                        ),
                    ],
                    confidence=Confidence.HIGH,
                    blocksCompile=True,
                    effort=Effort.TRIVIAL,
                    passProvenance="check_await_wait_set_shape",
                    agentHint="wait-set names are local branch/select names, not call references",
                ))
            caseLines: List[SourceLine] = []
            seenCaseCalls: Dict[str, SourceLine] = {}
            seenCaseLabels: Dict[str, SourceLine] = {}
            cursor = nextIndex
            while cursor < len(lines) and lines[cursor].verb == "case":
                caseLine = lines[cursor]
                consumedLineNumbers.add(caseLine.number)
                if len(caseLine.args) != 2:
                    add_wait_set_arity_diagnostic(
                        caseLine, waitSetName, "case <startedCall> <handlerLabel>", 2)
                    caseLines.append(caseLine)
                    cursor += 1
                    continue
                if len(caseLine.args) >= 1:
                    callName = caseLine.args[0]
                    targetLabel = caseLine.args[1]
                    previousCase = seenCaseCalls.get(callName)
                    previousCompletion = caseCompletionLines.get(callName)
                    callFact = operationCalls.get(callName)
                    priorStartLines = (
                        [
                            startLine
                            for startLine in callFact.start_lines
                            if startLine.number < sourceLine.number
                        ]
                        if callFact is not None
                        else []
                    )
                    hasMultiplePriorStarts = len(priorStartLines) > 1
                    hasStartBeforeWaitSet = (
                        callFact is not None
                        and not hasMultiplePriorStarts
                        and start_reaches_wait_set_entry(
                            operation, callFact, sourceLine)
                    )
                    if previousCase is not None:
                        diagnostics.append(Diagnostic(
                            tier=Tier.T1_SPEC,
                            code="SS3509",
                            kind="concurrencyDiscipline.awaitWaitSetMalformed",
                            severity=Severity.ERROR,
                            subjectName=waitSetName,
                            subjectKind="awaitWaitSet",
                            gapEdge="uniqueCaseCall",
                            intentSlogan="duplicate wait-set case",
                            primary=span_of_line(caseLine, "caseSite"),
                            related=[span_of_line(previousCase, "previousCase")],
                            invariantRule=(
                                f"`await {waitSetName}` may list each started "
                                "call at most once"
                            ),
                            specAnchor="docs/reference/syntax-inventory.md#case",
                            citations=operationCitations,
                            fixCandidates=[
                                FixCandidate(
                                    name="removeDuplicateCase",
                                    shape=f"# remove duplicate `case {callName} ...`",
                                    evidence=[span_of_line(caseLine)],
                                ),
                            ],
                            confidence=Confidence.HIGH,
                            blocksCompile=True,
                            effort=Effort.TRIVIAL,
                            passProvenance="check_await_wait_set_shape",
                            agentHint="duplicate cases would make consumed-state ambiguous",
                        ))
                    elif previousCompletion is not None:
                        diagnostics.append(Diagnostic(
                            tier=Tier.T1_SPEC,
                            code="SS3509",
                            kind="concurrencyDiscipline.awaitWaitSetMalformed",
                            severity=Severity.ERROR,
                            subjectName=callName,
                            subjectKind="call",
                            gapEdge="singleCompletionEdge",
                            intentSlogan="call appears in multiple wait sets",
                            primary=span_of_line(caseLine, "caseSite"),
                            related=[span_of_line(previousCompletion, "previousCase")],
                            invariantRule=(
                                f"`case {callName} ...` awaits and consumes the "
                                "call; the same call cannot be listed in a later "
                                "wait set"
                            ),
                            specAnchor="docs/reference/syntax-inventory.md#case",
                            citations=operationCitations,
                            fixCandidates=[
                                FixCandidate(
                                    name="useFreshStartedCall",
                                    shape=f"call <newCallName> <target>\nstart <newCallName>\ncase <newCallName> <handlerLabel>",
                                    evidence=[span_of_line(caseLine)],
                                ),
                            ],
                            confidence=Confidence.HIGH,
                            blocksCompile=True,
                            effort=Effort.LOCAL,
                            passProvenance="check_await_wait_set_shape",
                            agentHint="wait-set cases are future ownership handoffs",
                        ))
                    elif callFact is not None and hasMultiplePriorStarts:
                        diagnostics.append(Diagnostic(
                            tier=Tier.T1_SPEC,
                            code="SS3509",
                            kind="concurrencyDiscipline.awaitWaitSetMalformed",
                            severity=Severity.ERROR,
                            subjectName=callName,
                            subjectKind="call",
                            gapEdge="singlePriorStart",
                            intentSlogan="wait-set case has multiple prior starts",
                            primary=span_of_line(caseLine, "caseSite"),
                            related=[
                                span_of_line(startLine, "priorStart")
                                for startLine in priorStartLines
                            ],
                            invariantRule=(
                                f"`case {callName} ...` must refer to exactly "
                                "one prior `start`; repeated starts need fresh "
                                "call names so each future has one owner"
                            ),
                            specAnchor="docs/reference/syntax-inventory.md#case",
                            citations=operationCitations,
                            fixCandidates=[
                                FixCandidate(
                                    name="splitRepeatedStarts",
                                    shape=(
                                        f"call <freshCallName> {callFact.target}\n"
                                        "start <freshCallName>\n"
                                        f"case <freshCallName> {targetLabel}"
                                    ),
                                    evidence=[span_of_line(caseLine)],
                                ),
                            ],
                            confidence=Confidence.HIGH,
                            blocksCompile=True,
                            effort=Effort.LOCAL,
                            passProvenance="check_await_wait_set_shape",
                            agentHint="the compiler stores one future slot per call name",
                        ))
                    elif callFact is not None and not hasStartBeforeWaitSet:
                        relatedSpans = [span_of_line(callFact.line, "callDeclaration")]
                        relatedSpans.extend(
                            span_of_line(startLine, "lateStart")
                            for startLine in callFact.start_lines
                        )
                        diagnostics.append(Diagnostic(
                            tier=Tier.T1_SPEC,
                            code="SS3509",
                            kind="concurrencyDiscipline.awaitWaitSetMalformed",
                            severity=Severity.ERROR,
                            subjectName=callName,
                            subjectKind="call",
                            gapEdge="startBeforeCase",
                            intentSlogan="wait-set case lacks prior start",
                            primary=span_of_line(caseLine, "caseSite"),
                            related=relatedSpans,
                            invariantRule=(
                                f"`case {callName} ...` may only appear in an "
                                f"`await {waitSetName}` block after "
                                f"`start {callName}` has created the future"
                            ),
                            specAnchor="docs/reference/syntax-inventory.md#case",
                            citations=operationCitations,
                            fixCandidates=[
                                FixCandidate(
                                    name="moveStartBeforeWaitSet",
                                    shape=f"start {callName}",
                                    evidence=[span_of_line(caseLine)],
                                ),
                            ],
                            confidence=Confidence.HIGH,
                            blocksCompile=True,
                            effort=Effort.LOCAL,
                            passProvenance="check_await_wait_set_shape",
                            agentHint="wait-set polling needs an already-created future",
                        ))
                    elif (callFact is not None and priorStartLines
                            and start_reentry_edge(priorStartLines[-1]) is not None):
                        reentryEdge = start_reentry_edge(priorStartLines[-1])
                        assert reentryEdge is not None
                        edgeLine, edgeLabel = reentryEdge
                        diagnostics.append(Diagnostic(
                            tier=Tier.T1_SPEC,
                            code="SS3509",
                            kind="concurrencyDiscipline.awaitWaitSetMalformed",
                            severity=Severity.ERROR,
                            subjectName=callName,
                            subjectKind="call",
                            gapEdge="singleStartExecution",
                            intentSlogan="started future can be re-entered",
                            primary=span_of_line(edgeLine, "reentryEdge"),
                            related=[
                                span_of_line(priorStartLines[-1], "startSite"),
                                span_of_line(caseLine, "caseSite"),
                            ],
                            invariantRule=(
                                f"`start {callName}` creates one future for "
                                f"`case {callName} ...`; a later branch to "
                                f"`{edgeLabel}` can execute the same start "
                                "again. Use a fresh call name for each future."
                            ),
                            specAnchor="docs/reference/syntax-inventory.md#start",
                            citations=operationCitations,
                            fixCandidates=[
                                FixCandidate(
                                    name="useFreshCallNameForRestart",
                                    shape=(
                                        f"call <freshCallName> {callFact.target}\n"
                                        "start <freshCallName>"
                                    ),
                                    evidence=[span_of_line(edgeLine)],
                                ),
                            ],
                            confidence=Confidence.HIGH,
                            blocksCompile=True,
                            effort=Effort.LOCAL,
                            passProvenance="check_await_wait_set_shape",
                            agentHint="future slots are one-shot ownership cells",
                        ))
                    elif (callFact is not None
                            and not call_can_start_async_future(
                                facts, operation, callFact)):
                        diagnostics.append(Diagnostic(
                            tier=Tier.T1_SPEC,
                            code="SS3509",
                            kind="concurrencyDiscipline.awaitWaitSetMalformed",
                            severity=Severity.ERROR,
                            subjectName=callName,
                            subjectKind="call",
                            gapEdge="asyncFutureCase",
                            intentSlogan="wait-set case is not an async future",
                            primary=span_of_line(caseLine, "caseSite"),
                            related=[span_of_line(callFact.line, "callDeclaration")],
                            invariantRule=(
                                f"`case {callName} ...` requires a call target "
                                "that `start` lowers to an async future"
                            ),
                            specAnchor="docs/reference/syntax-inventory.md#case",
                            citations=operationCitations,
                            fixCandidates=[
                                FixCandidate(
                                    name="useAsyncFutureCall",
                                    shape=(
                                        f"call {callName} <asyncOperationOrNetFetch>\n"
                                        f"start {callName}\n"
                                        f"case {callName} {targetLabel}"
                                    ),
                                    evidence=[span_of_line(caseLine)],
                                ),
                            ],
                            confidence=Confidence.HIGH,
                            blocksCompile=True,
                            effort=Effort.LOCAL,
                            passProvenance="check_await_wait_set_shape",
                            agentHint="started synchronous calls do not create future slots for wait-set polling",
                        ))
                    else:
                        seenCaseCalls[callName] = caseLine
                        caseCompletionLines.setdefault(callName, caseLine)
                        caseCompletionOwners.setdefault(
                            callName, (waitSetName, targetLabel, caseLine))
                    labelLine = labelLineByName.get(targetLabel)
                    if labelLine is not None and labelLine.number <= caseLine.number:
                        diagnostics.append(Diagnostic(
                            tier=Tier.T1_SPEC,
                            code="SS3509",
                            kind="concurrencyDiscipline.awaitWaitSetMalformed",
                            severity=Severity.ERROR,
                            subjectName=targetLabel,
                            subjectKind="label",
                            gapEdge="caseLabelDeclarationOrder",
                            intentSlogan="wait-set case label appears too early",
                            primary=span_of_line(caseLine, "caseSite"),
                            related=[span_of_line(labelLine, "labelDeclaration")],
                            invariantRule=(
                                f"`case {callName} {targetLabel}` must branch "
                                "to a handler label declared after the case row"
                            ),
                            specAnchor="docs/reference/syntax-inventory.md#case",
                            citations=operationCitations,
                            fixCandidates=[
                                FixCandidate(
                                    name="moveCaseHandlerAfterWaitSet",
                                    shape=f"label {targetLabel}",
                                    evidence=[span_of_line(labelLine)],
                                ),
                            ],
                            confidence=Confidence.HIGH,
                            blocksCompile=True,
                            effort=Effort.LOCAL,
                            passProvenance="check_await_wait_set_shape",
                            agentHint="case handlers are selected continuations, not ordinary entry labels",
                        ))
                    previousEffectiveLine = None
                    if labelLine is not None:
                        for candidate in lines:
                            if candidate.number >= labelLine.number:
                                break
                            if candidate.verb in {
                                "input", "output", "effect", "async",
                                "purpose", "invariant", "warning",
                            }:
                                continue
                            previousEffectiveLine = candidate
                    if (labelLine is not None
                            and previousEffectiveLine is not None
                            and previousEffectiveLine.verb != "done"
                            and not source_row_terminates_before_next_label(
                                previousEffectiveLine)):
                        diagnostics.append(Diagnostic(
                            tier=Tier.T1_SPEC,
                            code="SS3509",
                            kind="concurrencyDiscipline.awaitWaitSetMalformed",
                            severity=Severity.ERROR,
                            subjectName=targetLabel,
                            subjectKind="label",
                            gapEdge="caseLabelPrivateEntry",
                            intentSlogan="wait-set case label has fallthrough predecessor",
                            primary=span_of_line(labelLine, "caseHandlerLabel"),
                            related=[
                                span_of_line(caseLine, "caseSite"),
                                span_of_line(previousEffectiveLine, "fallthroughPredecessor"),
                            ],
                            invariantRule=(
                                f"`case {callName} {targetLabel}` owns the "
                                "entry edge into its handler; the preceding "
                                "source row must terminate or be the wait-set "
                                "`done` row"
                            ),
                            specAnchor="docs/reference/syntax-inventory.md#case",
                            citations=operationCitations,
                            fixCandidates=[
                                FixCandidate(
                                    name="terminateBeforeCaseHandler",
                                    shape="jump target <nonCaseHandlerLabel>",
                                    evidence=[span_of_line(previousEffectiveLine)],
                                ),
                            ],
                            confidence=Confidence.HIGH,
                            blocksCompile=True,
                            effort=Effort.LOCAL,
                            passProvenance="check_await_wait_set_shape",
                            agentHint="fallthrough predecessors can break dominance for materialized case results",
                        ))
                    for referenceLine in lines:
                        if (referenceLine.number == caseLine.number
                                and referenceLine.verb == "case"):
                            continue
                        if targetLabel not in branch_targets_for_wait_set(referenceLine):
                            continue
                        diagnostics.append(Diagnostic(
                            tier=Tier.T1_SPEC,
                            code="SS3509",
                            kind="concurrencyDiscipline.awaitWaitSetMalformed",
                            severity=Severity.ERROR,
                            subjectName=targetLabel,
                            subjectKind="label",
                            gapEdge="caseLabelPrivateEntry",
                            intentSlogan="wait-set case label has another predecessor",
                            primary=span_of_line(referenceLine, "labelReference"),
                            related=[span_of_line(caseLine, "caseSite")],
                            invariantRule=(
                                f"`case {callName} {targetLabel}` owns the "
                                "entry edge into its handler; other source "
                                "branches must not target that label"
                            ),
                            specAnchor="docs/reference/syntax-inventory.md#case",
                            citations=operationCitations,
                            fixCandidates=[
                                FixCandidate(
                                    name="branchToSeparateLabel",
                                    shape="jump target <nonCaseHandlerLabel>",
                                    evidence=[span_of_line(referenceLine)],
                                ),
                            ],
                            confidence=Confidence.HIGH,
                            blocksCompile=True,
                            effort=Effort.LOCAL,
                            passProvenance="check_await_wait_set_shape",
                            agentHint="extra predecessors can break dominance for materialized case results",
                        ))
                    previousLabel = seenCaseLabels.get(targetLabel)
                    if previousLabel is not None:
                        diagnostics.append(Diagnostic(
                            tier=Tier.T1_SPEC,
                            code="SS3509",
                            kind="concurrencyDiscipline.awaitWaitSetMalformed",
                            severity=Severity.ERROR,
                            subjectName=targetLabel,
                            subjectKind="label",
                            gapEdge="uniqueCaseLabel",
                            intentSlogan="wait-set case label is reused",
                            primary=span_of_line(caseLine, "caseSite"),
                            related=[span_of_line(previousLabel, "previousCase")],
                            invariantRule=(
                                f"`await {waitSetName}` must branch each case "
                                "to a distinct handler label so the selected "
                                "call result dominates that handler"
                            ),
                            specAnchor="docs/reference/syntax-inventory.md#case",
                            citations=operationCitations,
                            fixCandidates=[
                                FixCandidate(
                                    name="useDistinctCaseHandler",
                                    shape=f"case {callName} <freshHandlerLabel>",
                                    evidence=[span_of_line(caseLine)],
                                ),
                            ],
                            confidence=Confidence.HIGH,
                            blocksCompile=True,
                            effort=Effort.LOCAL,
                            passProvenance="check_await_wait_set_shape",
                            agentHint="shared wait-set handler labels can break result dominance",
                        ))
                    else:
                        seenCaseLabels[targetLabel] = caseLine
                caseLines.append(caseLine)
                cursor += 1
            doneLine = lines[cursor] if cursor < len(lines) and lines[cursor].verb == "done" else None
            if doneLine is not None:
                consumedLineNumbers.add(doneLine.number)
                if len(doneLine.args) != 1:
                    add_wait_set_arity_diagnostic(
                        doneLine, waitSetName, "done <allCasesConsumedLabel>", 1)
                nextEffectiveLine = next_effective_line_after(doneLine.number)
                if nextEffectiveLine is not None and nextEffectiveLine.verb != "label":
                    diagnostics.append(Diagnostic(
                        tier=Tier.T1_SPEC,
                        code="SS3509",
                        kind="concurrencyDiscipline.awaitWaitSetMalformed",
                        severity=Severity.ERROR,
                        subjectName=waitSetName,
                        subjectKind="awaitWaitSet",
                        gapEdge="doneStructuralGap",
                        intentSlogan="wait-set done row is followed by executable source",
                        primary=span_of_line(nextEffectiveLine, "postDoneExecutable"),
                        related=[span_of_line(doneLine, "doneSite")],
                        invariantRule=(
                            f"`await {waitSetName}` must hand control to a "
                            "`case` or `done` label after its structural rows; "
                            f"`{nextEffectiveLine.verb}` cannot appear between "
                            "the `done` row and the next label"
                        ),
                        specAnchor="docs/reference/syntax-inventory.md#done",
                        citations=operationCitations,
                        fixCandidates=[
                            FixCandidate(
                                name="moveExecutableAfterHandlerLabel",
                                shape="label <handlerOrDoneLabel>",
                                evidence=[span_of_line(nextEffectiveLine)],
                            ),
                        ],
                        confidence=Confidence.HIGH,
                        blocksCompile=True,
                        effort=Effort.LOCAL,
                        passProvenance="check_await_wait_set_shape",
                        agentHint="wait-set lowering leaves the sequential insertion point; executable rows must live under an explicit label",
                    ))
                if len(doneLine.args) == 1:
                    doneLabel = doneLine.args[0]
                    doneLabelLine = labelLineByName.get(doneLabel)
                    if doneLabelLine is not None and doneLabelLine.number <= doneLine.number:
                        diagnostics.append(Diagnostic(
                            tier=Tier.T1_SPEC,
                            code="SS3509",
                            kind="concurrencyDiscipline.awaitWaitSetMalformed",
                            severity=Severity.ERROR,
                            subjectName=doneLabel,
                            subjectKind="label",
                            gapEdge="doneLabelDeclarationOrder",
                            intentSlogan="wait-set done label appears too early",
                            primary=span_of_line(doneLine, "doneSite"),
                            related=[span_of_line(doneLabelLine, "labelDeclaration")],
                            invariantRule=(
                                f"`done {doneLabel}` must branch to a label "
                                "declared after the wait-set `done` row"
                            ),
                            specAnchor="docs/reference/syntax-inventory.md#done",
                            citations=operationCitations,
                            fixCandidates=[
                                FixCandidate(
                                    name="moveDoneLabelAfterWaitSet",
                                    shape=f"label {doneLabel}",
                                    evidence=[span_of_line(doneLabelLine)],
                                ),
                            ],
                            confidence=Confidence.HIGH,
                            blocksCompile=True,
                            effort=Effort.LOCAL,
                            passProvenance="check_await_wait_set_shape",
                            agentHint="done labels are all-consumed continuations, not ordinary entry labels",
                        ))
                    previousEffectiveLine = None
                    if doneLabelLine is not None:
                        for candidate in lines:
                            if candidate.number >= doneLabelLine.number:
                                break
                            if candidate.verb in {
                                "input", "output", "effect", "async",
                                "purpose", "invariant", "warning",
                            }:
                                continue
                            previousEffectiveLine = candidate
                    previousIsOwningDoneLine = (
                        previousEffectiveLine is not None
                        and previousEffectiveLine.verb == "done"
                        and previousEffectiveLine.args
                        and previousEffectiveLine.args[0] == doneLabel
                        and previousEffectiveLine.number == doneLine.number
                    )
                    if (doneLabelLine is not None
                            and previousEffectiveLine is not None
                            and previousEffectiveLine.verb != "case"
                            and not previousIsOwningDoneLine
                            and not source_row_terminates_before_next_label(
                                previousEffectiveLine)):
                        diagnostics.append(Diagnostic(
                            tier=Tier.T1_SPEC,
                            code="SS3509",
                            kind="concurrencyDiscipline.awaitWaitSetMalformed",
                            severity=Severity.ERROR,
                            subjectName=doneLabel,
                            subjectKind="label",
                            gapEdge="doneLabelPrivateEntry",
                            intentSlogan="wait-set done label has fallthrough predecessor",
                            primary=span_of_line(doneLabelLine, "doneLabel"),
                            related=[
                                span_of_line(doneLine, "doneSite"),
                                span_of_line(previousEffectiveLine, "fallthroughPredecessor"),
                            ],
                            invariantRule=(
                                f"`done {doneLabel}` owns the all-consumed "
                                "entry edge; the preceding source row must "
                                "terminate or be the wait-set `case` row"
                            ),
                            specAnchor="docs/reference/syntax-inventory.md#done",
                            citations=operationCitations,
                            fixCandidates=[
                                FixCandidate(
                                    name="terminateBeforeDoneLabel",
                                    shape="jump target <nonDoneLabel>",
                                    evidence=[span_of_line(previousEffectiveLine)],
                                ),
                            ],
                            confidence=Confidence.HIGH,
                            blocksCompile=True,
                            effort=Effort.LOCAL,
                            passProvenance="check_await_wait_set_shape",
                            agentHint="fallthrough into done can skip unconsumed wait-set cases",
                        ))
                    for referenceLine in lines:
                        if (referenceLine.number == doneLine.number
                                and referenceLine.verb == "done"):
                            continue
                        if doneLabel not in branch_targets_for_wait_set(referenceLine):
                            continue
                        diagnostics.append(Diagnostic(
                            tier=Tier.T1_SPEC,
                            code="SS3509",
                            kind="concurrencyDiscipline.awaitWaitSetMalformed",
                            severity=Severity.ERROR,
                            subjectName=doneLabel,
                            subjectKind="label",
                            gapEdge="doneLabelPrivateEntry",
                            intentSlogan="wait-set done label has another predecessor",
                            primary=span_of_line(referenceLine, "labelReference"),
                            related=[span_of_line(doneLine, "doneSite")],
                            invariantRule=(
                                f"`done {doneLabel}` owns the all-consumed "
                                "entry edge into its continuation; other "
                                "source branches must not target that label"
                            ),
                            specAnchor="docs/reference/syntax-inventory.md#done",
                            citations=operationCitations,
                            fixCandidates=[
                                FixCandidate(
                                    name="branchToSeparateLabel",
                                    shape="jump target <nonDoneLabel>",
                                    evidence=[span_of_line(referenceLine)],
                                ),
                            ],
                            confidence=Confidence.HIGH,
                            blocksCompile=True,
                            effort=Effort.LOCAL,
                            passProvenance="check_await_wait_set_shape",
                            agentHint="direct entry into done can skip unconsumed wait-set cases",
                        ))
                    for caseLine in caseLines:
                        if len(caseLine.args) != 2 or caseLine.args[1] != doneLabel:
                            continue
                        diagnostics.append(Diagnostic(
                            tier=Tier.T1_SPEC,
                            code="SS3509",
                            kind="concurrencyDiscipline.awaitWaitSetMalformed",
                            severity=Severity.ERROR,
                            subjectName=doneLabel,
                            subjectKind="label",
                            gapEdge="caseDoneLabelDisjoint",
                            intentSlogan="wait-set case label matches done label",
                            primary=span_of_line(caseLine, "caseSite"),
                            related=[span_of_line(doneLine, "doneSite")],
                            invariantRule=(
                                f"`await {waitSetName}` case handlers must be "
                                "disjoint from the `done` label; `done` is only "
                                "entered after every case has been consumed"
                            ),
                            specAnchor="docs/reference/syntax-inventory.md#done",
                            citations=operationCitations,
                            fixCandidates=[
                                FixCandidate(
                                    name="splitCaseAndDoneLabels",
                                    shape=(
                                        f"case {caseLine.args[0]} <freshHandlerLabel>\n"
                                        f"done {doneLabel}"
                                    ),
                                    evidence=[
                                        span_of_line(caseLine),
                                        span_of_line(doneLine),
                                    ],
                                ),
                            ],
                            confidence=Confidence.HIGH,
                            blocksCompile=True,
                            effort=Effort.LOCAL,
                            passProvenance="check_await_wait_set_shape",
                            agentHint="the all-consumed path must not enter a selected-case handler",
                        ))
            waitEntryLabel = label_before_line(sourceLine.number)
            if caseLines and waitEntryLabel is None:
                diagnostics.append(Diagnostic(
                    tier=Tier.T1_SPEC,
                    code="SS3509",
                    kind="concurrencyDiscipline.awaitWaitSetMalformed",
                    severity=Severity.ERROR,
                    subjectName=waitSetName,
                    subjectKind="awaitWaitSet",
                    gapEdge="waitSetEntryLabel",
                    intentSlogan="wait set has no re-entry label",
                    primary=span_of_line(sourceLine, "awaitSite"),
                    invariantRule=(
                        f"`await {waitSetName}` must be preceded by a label "
                        "so case handlers can jump back and consume remaining futures"
                    ),
                    specAnchor="docs/reference/syntax-inventory.md#await",
                    citations=operationCitations,
                    fixCandidates=[
                        FixCandidate(
                            name="addWaitSetEntryLabel",
                            shape=f"label wait{waitSetName}\nawait {waitSetName}",
                            evidence=[span_of_line(sourceLine)],
                        ),
                    ],
                    confidence=Confidence.HIGH,
                    blocksCompile=True,
                    effort=Effort.LOCAL,
                    passProvenance="check_await_wait_set_shape",
                    agentHint="wait-set case handlers re-enter through the await label",
                ))
            if waitEntryLabel is not None:
                for caseLine in caseLines:
                    if len(caseLine.args) != 2:
                        continue
                    callName, targetLabel = caseLine.args
                    labelLine = labelLineByName.get(targetLabel)
                    if labelLine is None:
                        continue
                    sawReentry = False
                    for handlerLine in lines:
                        if handlerLine.number <= labelLine.number:
                            continue
                        if handlerLine.verb == "label":
                            break
                        if is_wait_set_gap_ignored(handlerLine):
                            continue
                        if handlerLine.verb in {
                            "defer", "deferLog", "deferAwaitLog",
                            "deferWhenExitLog", "deferRunOn",
                        }:
                            add_case_handler_reentry_diagnostic(
                                handlerLine, callName, waitSetName,
                                targetLabel, waitEntryLabel,
                                gapEdge="caseHandlerDefer")
                            sawReentry = True
                            break
                        targets = branch_targets_for_wait_set(handlerLine)
                        if handlerLine.verb == "jump" and targets == [waitEntryLabel]:
                            sawReentry = True
                            break
                        if return_parts(handlerLine) is not None:
                            add_case_handler_reentry_diagnostic(
                                handlerLine, callName, waitSetName,
                                targetLabel, waitEntryLabel)
                            sawReentry = True
                            break
                        disallowedTargets = [
                            target for target in targets
                            if target != waitEntryLabel
                        ]
                        if disallowedTargets:
                            add_case_handler_reentry_diagnostic(
                                handlerLine, callName, waitSetName,
                                targetLabel, waitEntryLabel)
                            sawReentry = True
                            break
                    if not sawReentry:
                        add_case_handler_reentry_diagnostic(
                            caseLine, callName, waitSetName,
                            targetLabel, waitEntryLabel)
            if not caseLines:
                diagnostics.append(Diagnostic(
                    tier=Tier.T1_SPEC,
                    code="SS3509",
                    kind="concurrencyDiscipline.awaitWaitSetMalformed",
                    severity=Severity.ERROR,
                    subjectName=waitSetName,
                    subjectKind="awaitWaitSet",
                    gapEdge="case",
                    intentSlogan="wait set has no cases",
                    primary=span_of_line(sourceLine, "awaitSite"),
                    invariantRule=(
                        f"`await {waitSetName}` followed by `done` must include "
                        "at least one `case CALL LABEL` row"
                    ),
                    specAnchor="docs/reference/syntax-inventory.md#case",
                    citations=operationCitations,
                    fixCandidates=[
                        FixCandidate(
                            name="addCase",
                            shape=f"case <startedCall> <handlerLabel>\ndone <doneLabel>",
                            evidence=[span_of_line(sourceLine)],
                        ),
                    ],
                    confidence=Confidence.HIGH,
                    blocksCompile=True,
                    effort=Effort.TRIVIAL,
                    passProvenance="check_await_wait_set_shape",
                    agentHint="a wait set with no selectable futures cannot make progress",
                ))
            if doneLine is None:
                diagnostics.append(Diagnostic(
                    tier=Tier.T1_SPEC,
                    code="SS3509",
                    kind="concurrencyDiscipline.awaitWaitSetMalformed",
                    severity=Severity.ERROR,
                    subjectName=waitSetName,
                    subjectKind="awaitWaitSet",
                    gapEdge="done",
                    intentSlogan="wait set missing done",
                    primary=span_of_line(sourceLine, "awaitSite"),
                    invariantRule=(
                        f"`await {waitSetName}` with `case` rows must end with "
                        "`done LABEL` so the all-consumed path is explicit"
                    ),
                    specAnchor="docs/reference/syntax-inventory.md#done",
                    citations=operationCitations,
                    fixCandidates=[
                        FixCandidate(
                            name="addDone",
                            shape="done <allCasesConsumedLabel>",
                            evidence=[span_of_line(caseLines[-1] if caseLines else sourceLine)],
                        ),
                    ],
                    confidence=Confidence.HIGH,
                    blocksCompile=True,
                    effort=Effort.TRIVIAL,
                    passProvenance="check_await_wait_set_shape",
                    agentHint="the compiler refuses await wait sets without an all-consumed branch",
                ))
            index = (cursor + 1) if doneLine is not None else cursor

        for sourceLine in lines:
            if sourceLine.verb not in {"case", "done"}:
                continue
            if sourceLine.number in consumedLineNumbers:
                continue
            diagnostics.append(Diagnostic(
                tier=Tier.T1_SPEC,
                code="SS3509",
                kind="concurrencyDiscipline.awaitWaitSetMalformed",
                severity=Severity.ERROR,
                subjectName=sourceLine.args[0] if sourceLine.args else sourceLine.verb,
                subjectKind="awaitWaitSetRow",
                gapEdge="await",
                intentSlogan="wait-set row is orphaned",
                primary=span_of_line(sourceLine, f"{sourceLine.verb}Site"),
                invariantRule=(
                    f"`{sourceLine.verb}` rows must immediately follow an "
                    "`await WAIT_SET` block"
                ),
                specAnchor="docs/reference/syntax-inventory.md#await",
                citations=operationCitations,
                fixCandidates=[
                    FixCandidate(
                        name="moveUnderAwait",
                        shape="await <waitSetName>\ncase <startedCall> <handlerLabel>\ndone <allCasesConsumedLabel>",
                        evidence=[span_of_line(sourceLine)],
                    ),
                ],
                confidence=Confidence.HIGH,
                blocksCompile=True,
                effort=Effort.TRIVIAL,
                passProvenance="check_await_wait_set_shape",
                agentHint="case/done are structural rows, not standalone control flow",
            ))

        privateCaseSymbols: Dict[str, Tuple[str, str, SourceLine, SourceLine]] = {}
        for _callName, (waitSetName, targetLabel, caseLine) in caseCompletionOwners.items():
            labelLine = labelLineByName.get(targetLabel)
            if labelLine is None:
                continue
            for candidate in lines:
                if candidate.number <= labelLine.number:
                    continue
                if candidate.verb == "label":
                    break
                definedSymbol = symbol_definition(candidate)
                if definedSymbol is not None:
                    privateCaseSymbols[definedSymbol] = (
                        waitSetName, targetLabel, caseLine, candidate)
                definedCallResult = call_result_definition(candidate)
                if definedCallResult is not None:
                    privateCaseSymbols[definedCallResult] = (
                        waitSetName, targetLabel, caseLine, candidate)
                if candidate.verb == "runChecked" and len(candidate.args) >= 6:
                    privateCaseSymbols[candidate.args[2]] = (
                        waitSetName, targetLabel, caseLine, candidate)
                    privateCaseSymbols[candidate.args[5]] = (
                        waitSetName, targetLabel, caseLine, candidate)

        callPrivateDependencies: Dict[str, List[Tuple[str, str, str, SourceLine, SourceLine]]] = {}

        def private_owner_for_symbol(
            symbolName: str,
        ) -> Optional[Tuple[str, str, SourceLine, SourceLine]]:
            privateOwner = privateCaseSymbols.get(symbolName)
            if privateOwner is not None:
                return privateOwner
            directOwner = caseCompletionOwners.get(symbolName)
            if directOwner is not None:
                waitSetName, targetLabel, caseLine = directOwner
                return waitSetName, targetLabel, caseLine, caseLine
            return None

        for sourceLine in lines:
            parsedArgument = argument_parts(sourceLine)
            if parsedArgument is None:
                if sourceLine.verb == "workArg" and len(sourceLine.args) >= 3:
                    callName = sourceLine.args[0]
                    valueName = sourceLine.args[2]
                else:
                    continue
            else:
                callName, _parameterName, _declaredType, valueName = parsedArgument
            privateOwner = private_owner_for_symbol(valueName)
            if privateOwner is None:
                continue
            waitSetName, targetLabel, caseLine, definitionLine = privateOwner
            callPrivateDependencies.setdefault(callName, []).append((
                valueName, waitSetName, targetLabel, caseLine, definitionLine))

        for sourceLine in lines:
            if sourceLine.verb == "case":
                continue
            directCallReference = call_result_reference(sourceLine)
            if directCallReference is not None:
                owner = caseCompletionOwners.get(directCallReference)
                if owner is not None:
                    waitSetName, targetLabel, caseLine = owner
                    if label_before_line(sourceLine.number) != targetLabel:
                        add_case_result_ownership_diagnostic(
                            sourceLine, directCallReference, waitSetName,
                            targetLabel, caseLine)
            if sourceLine.verb in {
                "run", "runChecked", "start", "startInGroup", "submitWork"
            } and sourceLine.args:
                for dependency in callPrivateDependencies.get(sourceLine.args[0], []):
                    referencedSymbol, waitSetName, targetLabel, caseLine, definitionLine = dependency
                    if (sourceLine.number > definitionLine.number
                            and label_before_line(sourceLine.number) != targetLabel):
                        add_case_result_ownership_diagnostic(
                            sourceLine, referencedSymbol, waitSetName,
                            targetLabel, caseLine)
            mutationEscape: Optional[Tuple[str, str]] = None
            if (sourceLine.verb == "set" and len(sourceLine.args) >= 3
                    and sourceLine.args[0] in {"memory", "storage"}):
                mutationEscape = (sourceLine.args[2], sourceLine.args[1])
            elif sourceLine.verb == "fieldSet" and len(sourceLine.args) >= 3:
                mutationEscape = (sourceLine.args[2], sourceLine.args[0])
            elif sourceLine.verb == "send" and len(sourceLine.args) >= 2:
                mutationEscape = (sourceLine.args[1], sourceLine.args[0])
            if mutationEscape is not None:
                valueName, targetName = mutationEscape
                privateOwner = private_owner_for_symbol(valueName)
                if privateOwner is not None:
                    waitSetName, targetLabel, caseLine, definitionLine = privateOwner
                    targetOwner = private_owner_for_symbol(targetName)
                    targetIsPrivateToSameHandler = (
                        targetOwner is not None
                        and targetOwner[1] == targetLabel
                    )
                    if (sourceLine.number > definitionLine.number
                            and label_before_line(sourceLine.number) == targetLabel
                            and not targetIsPrivateToSameHandler):
                        add_case_result_ownership_diagnostic(
                            sourceLine, valueName, waitSetName,
                            targetLabel, caseLine, escapeTarget=targetName)
            for referencedSymbol in symbol_references(sourceLine):
                privateOwner = private_owner_for_symbol(referencedSymbol)
                if privateOwner is None:
                    continue
                waitSetName, targetLabel, caseLine, _definitionLine = privateOwner
                if label_before_line(sourceLine.number) != targetLabel:
                    add_case_result_ownership_diagnostic(
                        sourceLine, referencedSymbol, waitSetName,
                        targetLabel, caseLine)

        for sourceLine in lines:
            if sourceLine.verb != "await" or not sourceLine.args:
                continue
            if sourceLine.number in waitSetAwaitLineNumbers:
                continue
            caseLine = caseCompletionLines.get(sourceLine.args[0])
            if caseLine is None:
                continue
            diagnostics.append(Diagnostic(
                tier=Tier.T1_SPEC,
                code="SS3509",
                kind="concurrencyDiscipline.awaitWaitSetMalformed",
                severity=Severity.ERROR,
                subjectName=sourceLine.args[0],
                subjectKind="call",
                gapEdge="singleCompletionEdge",
                intentSlogan="call completed by both case and await",
                primary=span_of_line(sourceLine, "awaitSite"),
                related=[span_of_line(caseLine, "caseSite")],
                invariantRule=(
                    f"`case {sourceLine.args[0]} ...` inside an await wait set "
                    "already awaits and materializes that call before branching; "
                    f"do not also write `await {sourceLine.args[0]}`"
                ),
                specAnchor="docs/reference/syntax-inventory.md#await",
                citations=operationCitations,
                fixCandidates=[
                    FixCandidate(
                        name="removeDuplicateAwait",
                        shape=f"# remove `await {sourceLine.args[0]}`",
                        evidence=[span_of_line(sourceLine)],
                    ),
                ],
                confidence=Confidence.HIGH,
                blocksCompile=True,
                effort=Effort.TRIVIAL,
                passProvenance="check_await_wait_set_shape",
                agentHint="await wait-set case rows own the future consumption",
            ))
        for callName, caseLine in caseCompletionLines.items():
            callFact = operationCalls.get(callName)
            if callFact is None:
                continue
            for startLine in callFact.start_lines:
                if startLine.number <= caseLine.number:
                    continue
                diagnostics.append(Diagnostic(
                    tier=Tier.T1_SPEC,
                    code="SS3509",
                    kind="concurrencyDiscipline.awaitWaitSetMalformed",
                    severity=Severity.ERROR,
                    subjectName=callName,
                    subjectKind="call",
                    gapEdge="startAfterCaseCompletion",
                    intentSlogan="call restarted after wait-set case",
                    primary=span_of_line(startLine, "startSite"),
                    related=[span_of_line(caseLine, "caseSite")],
                    invariantRule=(
                        f"`case {callName} ...` consumes that call future; "
                        f"do not later write `start {callName}`. Use a fresh "
                        "call name for a new future."
                    ),
                    specAnchor="docs/reference/syntax-inventory.md#case",
                    citations=operationCitations,
                    fixCandidates=[
                        FixCandidate(
                            name="useFreshCallName",
                            shape=(
                                f"call <freshCallName> {callFact.target}\n"
                                "start <freshCallName>"
                            ),
                            evidence=[span_of_line(startLine)],
                        ),
                    ],
                    confidence=Confidence.HIGH,
                    blocksCompile=True,
                    effort=Effort.LOCAL,
                    passProvenance="check_await_wait_set_shape",
                    agentHint="wait-set cases are one-shot future ownership transfers",
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
                specAnchor="docs/reference/syntax-inventory.md#timeout",
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


def check_await_without_start(facts: ExtendedFacts) -> List[Diagnostic]:
    """`await CALL` only has scheduler meaning when the same operation starts
    the call first. The 1.0 synchronous fallback can still execute in order, but
    the libuv continuation backend needs this edge to allocate/register the
    future before suspension."""
    diagnostics: List[Diagnostic] = []
    for operation in facts.base.operations.values():
        operationCitations = narrative_citations_for_operation(facts, operation.name)
        for callFact in collect_operation_calls(operation).values():
            if not callFact.await_lines or callFact.start_lines:
                continue
            diagnostics.append(Diagnostic(
                tier=Tier.T3_REFINEMENT,
                code="SS3511",
                kind="concurrencyDiscipline.awaitWithoutStart",
                severity=Severity.WARNING,
                subjectName=callFact.name,
                subjectKind="call",
                gapEdge="start",
                intentSlogan="await without matching start",
                primary=span_of_line(callFact.await_lines[0], "awaitSite"),
                related=[
                    span_of_line(callFact.line, "callDeclaration"),
                    span_of_line(operation.line, "enclosingOperation"),
                ],
                invariantRule=(
                    f"`await {callFact.name}` must be paired with "
                    f"`start {callFact.name}` in the same operation"
                ),
                specAnchor="docs/reference/syntax-inventory.md#await",
                citations=operationCitations,
                fixCandidates=[
                    FixCandidate(
                        name="addStartBeforeAwait",
                        shape=f"start {callFact.name}",
                        evidence=[span_of_line(callFact.line)],
                    ),
                ],
                confidence=Confidence.HIGH,
                effort=Effort.LOCAL,
                passProvenance="check_await_without_start",
                agentHint=(
                    "the future libuv backend needs the start edge to create "
                    "the future that await will suspend on"
                ),
            ))
    return diagnostics


def check_started_call_without_await(facts: ExtendedFacts) -> List[Diagnostic]:
    """A started call should be awaited until SemanticScript grows an explicit
    detach/cancel completion verb. `cancelOn` declares the cancellation token
    for an await, but it is not itself a completion edge."""
    diagnostics: List[Diagnostic] = []
    for operation in facts.base.operations.values():
        operationCitations = narrative_citations_for_operation(facts, operation.name)
        for callFact in collect_operation_calls(operation).values():
            if not callFact.start_lines or callFact.await_lines:
                continue
            diagnostics.append(Diagnostic(
                tier=Tier.T3_REFINEMENT,
                code="SS3512",
                kind="concurrencyDiscipline.startedCallWithoutAwait",
                severity=Severity.WARNING,
                subjectName=callFact.name,
                subjectKind="call",
                gapEdge="await",
                intentSlogan="started call without completion edge",
                primary=span_of_line(callFact.start_lines[0], "startSite"),
                related=[
                    span_of_line(callFact.line, "callDeclaration"),
                    span_of_line(operation.line, "enclosingOperation"),
                ],
                invariantRule=(
                    f"`start {callFact.name}` must be paired with "
                    f"`await {callFact.name}` until an explicit detach/cancel "
                    f"verb exists"
                ),
                specAnchor="docs/reference/syntax-inventory.md#start",
                citations=operationCitations,
                fixCandidates=[
                    FixCandidate(
                        name="addAwaitAfterStart",
                        shape=f"await {callFact.name}",
                        evidence=[span_of_line(callFact.line)],
                    ),
                ],
                confidence=Confidence.HIGH,
                effort=Effort.LOCAL,
                passProvenance="check_started_call_without_await",
                agentHint=(
                    "without await or a future detach/cancel edge, generated "
                    "async state would not have a defined ownership handoff"
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
            # Suppress when the op's output type IS FileHandle — caller owns lifetime
            outputLine = None
            for opLine in operation.lines:
                if opLine.verb == "output" and opLine.args and opLine.args[0] == operation.name:
                    outputLine = opLine
                    break
            if outputLine and len(outputLine.args) >= 2:
                if outputLine.args[1] in {"FileHandle", "FileHandle"}:
                    continue
                if (
                    outputLine.args[1] == "Result"
                    and len(outputLine.args) >= 3
                    and outputLine.args[2] in {"FileHandle", "FileHandle"}
                ):
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
                specAnchor="docs/reference/syntax-inventory.md#defer",
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
                    "type `FileHandle` to suppress this check"
                ),
            ))
    return diagnostics


def check_sqlite_database_failure_cleanup_missing(facts: ExtendedFacts) -> List[Diagnostic]:
    """After sqlite.openDatabase succeeds, later setup failures must close
    the fresh handle unless a close defer already owns the lifetime."""
    diagnostics: List[Diagnostic] = []
    for operation in facts.base.operations.values():
        operationCitations = narrative_citations_for_operation(facts, operation.name)
        operationCalls = collect_operation_calls(operation)
        operationDefers = facts.operationDefers.get(operation.name, [])
        for openCall in operationCalls.values():
            if openCall.target not in SQLITE_DATABASE_OPEN_TARGETS:
                continue
            databaseNames = call_success_value_names(openCall)
            if not databaseNames:
                continue
            if defer_consumes_any_value(
                operationDefers,
                set(SQLITE_DATABASE_CLOSE_TARGETS),
                databaseNames,
                afterLine=openCall.line.number,
            ):
                continue
            transferLineNumber: Optional[int] = None
            for sourceLine in operation.lines:
                if sourceLine.number <= openCall.line.number:
                    continue
                if is_comment(sourceLine) or not sourceLine.tokens:
                    continue
                args = sourceLine.args
                transfersDatabase = False
                if sourceLine.verb == "set" and args and args[-1] in databaseNames:
                    transfersDatabase = True
                elif sourceLine.verb in {"returnOk", "returnValue"} and args and args[0] in databaseNames:
                    transfersDatabase = True
                if transfersDatabase:
                    transferLineNumber = sourceLine.number
                    break
            for sourceLine in operation.lines:
                if (is_comment(sourceLine) or not sourceLine.tokens
                        or sourceLine.verb != "branchIfError"
                        or len(sourceLine.args) < 2):
                    continue
                if sourceLine.args[0] == openCall.name:
                    continue
                if sourceLine.number <= openCall.line.number:
                    continue
                if transferLineNumber is not None and sourceLine.number >= transferLineNumber:
                    continue
                failureLabel = sourceLine.args[1]
                if label_body_calls_cleanup_for_value(
                    operation,
                    failureLabel,
                    set(SQLITE_DATABASE_CLOSE_TARGETS),
                    databaseNames,
                ):
                    continue
                diagnostics.append(Diagnostic(
                    tier=Tier.T3_REFINEMENT,
                    code="SS3905",
                    kind="resourceLifecycle.sqliteDatabaseFailureCleanupMissing",
                    severity=Severity.WARNING,
                    subjectName=openCall.name,
                    subjectKind="call",
                    gapEdge="failureLabel.closeDatabase",
                    intentSlogan="sqlite open handle leaks on setup failure",
                    primary=span_of_line(sourceLine, "postOpenFailureBranch"),
                    related=[
                        span_of_line(openCall.line, "sqliteOpenCall"),
                        span_of_line(operation.line, "enclosingOperation"),
                    ],
                    invariantRule=(
                        "after sqlite.openDatabase succeeds, every later "
                        "branchIfError before ownership transfer must close "
                        "the fresh SqliteDatabase handle or install a close defer"
                    ),
                    specAnchor="docs/optimization-guide.md#sqlite-bootstrap-cleanup",
                    citations=operationCitations,
                    fixCandidates=[
                        FixCandidate(
                            name="closeFreshDatabaseInFailureLabel",
                            shape=(
                                f"label {failureLabel}\n"
                                f"call closeDatabaseAfterFailureCall sqlite.closeDatabase\n"
                                f"arg closeDatabaseAfterFailureCall database <freshDatabase>\n"
                                f"run closeDatabaseAfterFailureCall\n"
                                f"ignoreOk closeDatabaseAfterFailureCall Void\n"
                                f"returnError <setupError>"
                            ),
                            evidence=[span_of_line(sourceLine)],
                        ),
                        FixCandidate(
                            name="installCloseDeferAfterOpen",
                            shape="defer closeFreshDatabaseDefer sqlite.closeDatabase <freshDatabase>",
                        ),
                    ],
                    confidence=Confidence.HIGH,
                    effort=Effort.LOCAL,
                    passProvenance="check_sqlite_database_failure_cleanup_missing",
                    agentHint=(
                        "schema/bootstrap code often opens once then applies "
                        "DDL; every DDL failure path must release that fresh handle"
                    ),
                ))
    return diagnostics


def check_sqlite_statement_finalize_missing(facts: ExtendedFacts) -> List[Diagnostic]:
    """Prepared SQLite statements must be finalized by defer or explicit
    cleanup in the same operation unless the op returns the statement."""
    diagnostics: List[Diagnostic] = []
    for operation in facts.base.operations.values():
        operationCitations = narrative_citations_for_operation(facts, operation.name)
        operationCalls = collect_operation_calls(operation)
        operationDefers = facts.operationDefers.get(operation.name, [])
        for prepareCall in operationCalls.values():
            if prepareCall.target not in SQLITE_STATEMENT_PREPARE_TARGETS:
                continue
            statementNames = call_success_value_names(prepareCall)
            if not statementNames:
                continue
            if defer_consumes_any_value(
                operationDefers,
                set(SQLITE_STATEMENT_FINALIZE_TARGETS),
                statementNames,
                afterLine=prepareCall.line.number,
            ):
                continue
            if call_has_later_cleanup_call(
                prepareCall,
                operationCalls,
                set(SQLITE_STATEMENT_FINALIZE_TARGETS),
            ):
                continue
            outputTransfersStatement = False
            for sourceLine in operation.lines:
                if (not is_comment(sourceLine) and sourceLine.tokens
                        and sourceLine.verb == "output"
                        and len(sourceLine.args) >= 2
                        and sourceLine.args[0] == operation.name):
                    if sourceLine.args[1] == "SqliteStatement":
                        outputTransfersStatement = True
                    elif (sourceLine.args[1] == "Result" and len(sourceLine.args) >= 3
                            and sourceLine.args[2] == "SqliteStatement"):
                        outputTransfersStatement = True
            if outputTransfersStatement:
                continue
            diagnostics.append(Diagnostic(
                tier=Tier.T3_REFINEMENT,
                code="SS3906",
                kind="resourceLifecycle.sqliteStatementFinalizeMissing",
                severity=Severity.WARNING,
                subjectName=prepareCall.name,
                subjectKind="call",
                gapEdge="defer.finalizeStatement",
                intentSlogan="prepared statement lacks finalize",
                primary=span_of_line(prepareCall.line, "sqlitePrepareCall"),
                related=[span_of_line(operation.line, "enclosingOperation")],
                invariantRule=(
                    "every sqlite.prepareStatement success handle should be "
                    "paired with defer sqlite.finalizeStatement or an explicit "
                    "finalize call in the same operation"
                ),
                specAnchor="docs/optimization-guide.md#sqlite-statement-lifetime",
                citations=operationCitations,
                fixCandidates=[
                    FixCandidate(
                        name="addFinalizeDefer",
                        shape="defer finalizeStatementDefer sqlite.finalizeStatement <statement>",
                        evidence=[span_of_line(prepareCall.line)],
                    ),
                ],
                confidence=Confidence.HIGH,
                effort=Effort.TRIVIAL,
                passProvenance="check_sqlite_statement_finalize_missing",
                agentHint=(
                    "SQLite statements retain native resources until finalized; "
                    "use a defer immediately after a successful prepare"
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
            specAnchor="docs/reference/syntax-inventory.md#guardTokenRelease",
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
            specAnchor="docs/reference/syntax-inventory.md#guardTokenProtects",
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
                    specAnchor="docs/reference/syntax-inventory.md#type",
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
            specAnchor="docs/reference/syntax-inventory.md#jsonCodec",
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


_JSON_CODEC_TARGET_PREFIXES = (
    "json.encode.", "json.decode.", "json.stringify.", "json.parse.",
)


def _json_codec_target_type_name(targetName: str) -> Optional[str]:
    """The type portion of a high-level json codec target, e.g.
    `json.encode.Point` -> `Point`; None if not a codec target."""
    for prefix in _JSON_CODEC_TARGET_PREFIXES:
        if targetName.startswith(prefix):
            return targetName[len(prefix):]
    return None


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

            # A json codec target whose type is a declared `record` lowers to a
            # real structural codec (ss_json_document_* / set_object_field_*),
            # not the zero-stub external fallback. Warning that it is "runtime
            # missing" is stale and misleads authors into hand-rolling JSON; only
            # non-record (fallback) codec targets are a genuine gap. Resolve type
            # aliases first, matching the compiler's resolve_alias routing, so a
            # `type Coordinate Point` alias of a record is treated as the record.
            codecTypeName = _json_codec_target_type_name(targetName)
            if codecTypeName is not None:
                resolvedCodecType = _resolve_type_alias_head(
                    codecTypeName, facts.base.type_aliases)
                if (codecTypeName in facts.base.records
                        or resolvedCodecType in facts.base.records):
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
                            shape="# use json.encode.Int64/json.decode.Int64/json.encode.Bool/etc. when the value is scalar",
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
            specAnchor=f"docs/reference/syntax-inventory.md#{verb}",
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
                f"check docs/reference/syntax-inventory.md row for `{verb}` to see the exact argument shape"
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
        elif verb in {"storage", "sharedState"} and len(args) >= 4:
            moduleScopeValueNames.add(args[2])
        else:
            memory = memory_parts(sourceLine)
            if memory is not None and memory[1] in {"mutable", "immutable"} and len(memory[2]) >= 3:
                moduleScopeValueNames.add(memory[2][0])

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
        waitSetAwaitLines = wait_set_await_line_numbers(operation)
        for declarationLine in operation.lines:
            if not declarationLine.tokens or is_comment(declarationLine):
                continue
            declarationVerb = declarationLine.verb
            declarationArgs = declarationLine.args
            parsedInput = input_parts(declarationLine)
            parsedBind = bind_parts(declarationLine)
            parsedMemory = memory_parts(declarationLine)
            if parsedInput is not None and parsedInput[0] == operation.name:
                declaredValueNames.add(parsedInput[1])
            elif declarationVerb in {"const", "var", "let", "literal"} and declarationArgs:
                declaredValueNames.add(declarationArgs[0])
            elif declarationVerb == "storage" and len(declarationArgs) >= 4:
                declaredValueNames.add(declarationArgs[2])
            elif parsedMemory is not None and parsedMemory[1] in {"mutable", "immutable"} and len(parsedMemory[2]) >= 3:
                declaredValueNames.add(parsedMemory[2][0])
            elif parsedBind is not None:
                declaredValueNames.add(parsedBind[1])
            elif declarationVerb == "new" and len(declarationArgs) >= 2:
                declaredValueNames.add(declarationArgs[0])
            elif declarationVerb == "fieldGet" and len(declarationArgs) >= 2:
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
            parsedArgument = argument_parts(sourceLine)
            parsedBind = bind_parts(sourceLine)
            parsedIgnore = ignore_parts(sourceLine)
            parsedBranchErrorSource = branch_error_source(sourceLine)
            if parsedArgument is not None:
                referencedCallName = parsedArgument[0]
            elif parsedIgnore is not None:
                referencedCallName = parsedIgnore[1]
            elif parsedBranchErrorSource is not None:
                referencedCallName = parsedBranchErrorSource
            elif verb == "await" and sourceLine.number in waitSetAwaitLines:
                referencedCallName = None
            elif verb == "case" and sourceLine.args:
                referencedCallName = sourceLine.args[0]
            elif verb in CALL_REFERENCE_VERBS_AT_ARG_ZERO and sourceLine.args:
                referencedCallName = sourceLine.args[0]
            elif parsedBind is not None:
                referencedCallName = parsedBind[3]
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

            if parsedArgument is not None:
                callReferenceName, argumentName, _argumentType, referencedValueName = parsedArgument
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
                        declarationShape=f"memory {operation.name} immutable {referencedValueName} <type> <value>",
                    ))

            # Label references
            referencedLabelName: Optional[str] = None
            targets = branch_target_names_from_row(sourceLine)
            if targets:
                referencedLabelName = targets[0]
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
    # narrative-attachment subjects per docs/reference/syntax-inventory.md.
    for sourceLine in facts.base.lines:
        if not sourceLine.tokens or is_comment(sourceLine) or not sourceLine.args:
            continue
        if sourceLine.verb in {
            "module", "enum", "error", "domainLiteral", "policy", "errorPolicy",
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
        parsedInput = input_parts(sourceLine)
        parsedOutput = output_parts(sourceLine)
        parsedMemory = memory_parts(sourceLine)
        if parsedInput is not None:
            referencedSubjectName = parsedInput[0]
        elif parsedOutput is not None:
            referencedSubjectName = parsedOutput[0]
        elif parsedMemory is not None:
            referencedSubjectName = parsedMemory[0]
        elif len(sourceLine.args) >= 3 and ((sourceLine.verb == "purpose" and sourceLine.args[0] in PURPOSE_SUBJECT_KINDS) or (sourceLine.verb == "invariant" and sourceLine.args[0] in {"module", "operation"})):
            referencedSubjectName = sourceLine.args[1]
        else:
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
                specAnchor="docs/reference/syntax-inventory.md#operation",
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
                specAnchor="docs/reference/syntax-inventory.md#operation",
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


def _operation_value_types(facts: ExtendedFacts, operation: OperationFact) -> Dict[str, str]:
    valueTypes: Dict[str, str] = {
        name: constFact.type_name
        for name, constFact in facts.base.consts.items()
    }
    valueTypes.update({"true": "Bool", "false": "Bool"})
    for sourceLine in facts.base.lines:
        if not sourceLine.tokens or is_comment(sourceLine):
            continue
        if sourceLine.verb == "operation":
            break
        if sourceLine.verb == "storage" and len(sourceLine.args) >= 5:
            valueTypes[sourceLine.args[2]] = sourceLine.args[3]
        elif sourceLine.verb == "literal" and len(sourceLine.args) >= 2:
            valueTypes[sourceLine.args[0]] = sourceLine.args[1]
        elif sourceLine.verb == "domainLiteral" and len(sourceLine.args) >= 2:
            valueTypes[sourceLine.args[0]] = sourceLine.args[1]
        elif sourceLine.verb == "enumCase" and len(sourceLine.args) >= 2:
            valueTypes[sourceLine.args[1]] = sourceLine.args[0]

    for sourceLine in operation.lines:
        if not sourceLine.tokens or is_comment(sourceLine):
            continue
        parsedInput = input_parts(sourceLine)
        parsedBind = bind_parts(sourceLine)
        parsedMemory = memory_parts(sourceLine)
        if parsedInput is not None and parsedInput[0] == operation.name:
            valueTypes[parsedInput[1]] = parsedInput[2]
        elif parsedBind is not None:
            valueTypes[parsedBind[1]] = parsedBind[2]
        elif parsedMemory is not None and parsedMemory[1] in {"mutable", "immutable"} and len(parsedMemory[2]) >= 3:
            valueTypes[parsedMemory[2][0]] = parsedMemory[2][1]
        elif sourceLine.verb in {"const", "var", "let"} and len(sourceLine.args) >= 2:
            valueTypes[sourceLine.args[0]] = sourceLine.args[1]
        elif sourceLine.verb == "storage" and len(sourceLine.args) >= 5:
            valueTypes[sourceLine.args[2]] = sourceLine.args[3]
        elif sourceLine.verb == "new" and len(sourceLine.args) >= 2:
            valueTypes[sourceLine.args[0]] = sourceLine.args[1]
        elif sourceLine.verb == "fieldGet" and len(sourceLine.args) >= 2:
            valueTypes[sourceLine.args[0]] = sourceLine.args[1]
    return valueTypes


def _is_branch_if_or_error(sourceLine: SourceLine) -> bool:
    args = sourceLine.args
    return (
        sourceLine.verb == "branch"
        and (
            len(args) == 5 and args[0] == "if" and args[1] == "condition" and args[3] == "target"
            or len(args) == 5 and args[0] == "error" and args[1] == "source" and args[3] == "target"
        )
    )


def _is_branch_else(sourceLine: SourceLine) -> bool:
    return (
        sourceLine.verb == "branch"
        and len(sourceLine.args) == 3
        and sourceLine.args[0] == "else"
        and sourceLine.args[1] == "target"
    )


def check_branch_semantics(facts: ExtendedFacts) -> List[Diagnostic]:
    diagnostics: List[Diagnostic] = []
    physicalByLine: Dict[int, SourceLine] = {
        sourceLine.number: sourceLine for sourceLine in facts.base.lines
    }
    resultReturningUserOps = result_returning_operation_names(facts.base)
    for operation in facts.base.operations.values():
        operationCalls = collect_operation_calls(operation)
        valueTypes = _operation_value_types(facts, operation)
        operationCitations = narrative_citations_for_operation(facts, operation.name)
        for sourceLine in operation.lines:
            if not sourceLine.tokens or is_comment(sourceLine):
                continue
            args = sourceLine.args
            if sourceLine.verb == "branch" and len(args) == 5 and args[0] == "if":
                conditionName = args[2]
                conditionType = valueTypes.get(conditionName)
                if conditionType is not None and conditionType != "Bool":
                    diagnostics.append(Diagnostic(
                        tier=Tier.T1_SPEC,
                        code="SS4106",
                        kind="controlFlow.branchConditionType",
                        severity=Severity.ERROR,
                        subjectName=conditionName,
                        subjectKind="branchCondition",
                        gapEdge="Bool",
                        intentSlogan="branch if condition is not Bool",
                        primary=span_of_line(sourceLine, "branchIfCondition"),
                        related=[span_of_line(operation.line, "enclosingOperation")],
                        invariantRule=(
                            f"`branch if condition {conditionName} target {args[4]}` "
                            f"requires `{conditionName}` to be Bool, got `{conditionType}`"
                        ),
                        specAnchor="docs/reference/syntax-inventory.md#branch",
                        citations=operationCitations,
                        fixCandidates=[
                            FixCandidate(
                                name="bindBoolCondition",
                                shape=f"bind value {conditionName}IsTrue Bool <comparisonCall>",
                            ),
                        ],
                        confidence=Confidence.HIGH,
                        blocksCompile=True,
                        effort=Effort.LOCAL,
                        passProvenance="check_branch_semantics",
                        agentHint="branch conditions must be explicit Bool values; compare or validate before branching",
                    ))
            if sourceLine.verb == "branch" and len(args) == 5 and args[0] == "error":
                callName = args[2]
                callFact = operationCalls.get(callName)
                if callFact is None:
                    continue
                knownBranchTarget = (
                    callFact.target in BUILTIN_TARGET_SIGNATURES
                    or callFact.target in BUILTIN_TARGET_RETURN_TYPES
                    or callFact.target in KNOWN_FALLIBLE_CALL_TARGETS
                    or callFact.target in facts.base.operations
                    or callFact.target in resultReturningUserOps
                )
                if not knownBranchTarget:
                    continue
                if (callFact.target not in KNOWN_FALLIBLE_CALL_TARGETS
                        and callFact.target not in resultReturningUserOps):
                    diagnostics.append(Diagnostic(
                        tier=Tier.T1_SPEC,
                        code="SS4107",
                        kind="controlFlow.branchErrorSource",
                        severity=Severity.ERROR,
                        subjectName=callName,
                        subjectKind="call",
                        gapEdge="fallibleCall",
                        intentSlogan="branch error source is not fallible",
                        primary=span_of_line(sourceLine, "branchErrorSource"),
                        related=[span_of_line(callFact.line, "callDeclaration")],
                        invariantRule=(
                            f"`branch error source {callName}` requires a result or fallible call; "
                            f"`{callFact.target}` has no known error channel"
                        ),
                        specAnchor="docs/reference/syntax-inventory.md#branch",
                        citations=operationCitations,
                        fixCandidates=[
                            FixCandidate(
                                name="removeErrorBranch",
                                shape=f"# remove `branch error source {callName} target {args[4]}` or call a fallible target",
                            ),
                        ],
                        confidence=Confidence.HIGH,
                        blocksCompile=True,
                        effort=Effort.TRIVIAL,
                        passProvenance="check_branch_semantics",
                        agentHint="use `branch error` only for result/fallible calls; ordinary calls use value checks plus `branch if`",
                    ))

            if _is_branch_else(sourceLine):
                previousPhysical = physicalByLine.get(sourceLine.number - 1)
                if previousPhysical is None or not _is_branch_if_or_error(previousPhysical):
                    diagnostics.append(Diagnostic(
                        tier=Tier.T1_SPEC,
                        code="SS4108",
                        kind="controlFlow.branchElseAdjacency",
                        severity=Severity.ERROR,
                        subjectName=args[2],
                        subjectKind="label",
                        gapEdge="immediatePredecessor",
                        intentSlogan="branch else is not adjacent to branch if/error",
                        primary=span_of_line(sourceLine, "branchElse"),
                        related=[span_of_line(operation.line, "enclosingOperation")],
                        invariantRule="`branch else target LABEL` must be the very next physical row after `branch if` or `branch error`",
                        specAnchor="docs/reference/syntax-inventory.md#branch",
                        citations=operationCitations,
                        fixCandidates=[
                            FixCandidate(
                                name="moveBranchElseAdjacent",
                                shape="branch else target <alternateLabel>",
                            ),
                            FixCandidate(
                                name="useJumpForUnconditionalTransfer",
                                shape=f"jump target {args[2]}",
                            ),
                        ],
                        confidence=Confidence.HIGH,
                        blocksCompile=True,
                        effort=Effort.TRIVIAL,
                        passProvenance="check_branch_semantics",
                        agentHint="a separated `branch else` is ambiguous; use `jump target` outside an adjacent branch chain",
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
        specAnchor=f"docs/reference/syntax-inventory.md#{referencedKind}",
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


def _resolve_type_alias_head(
    typeName: Optional[str],
    typeAliases: Dict[str, str],
) -> Optional[str]:
    """Chase declared type aliases without collapsing primitive families."""
    if typeName is None:
        return None
    visited: Set[str] = set()
    currentName = typeName
    while currentName in typeAliases and currentName not in visited:
        visited.add(currentName)
        currentName = typeAliases[currentName]
    return currentName


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
    signed2 = {"Int2"}
    signed4 = {"Int4"}
    signed8 = {"Int8"}
    signed16 = {"Int16"}
    signed32 = {"Int32", "ExitCode", "Char"}
    signed64 = {
        "Int64", "ByteCount", "SignedByteCount", "AddressOffset",
        "UnixSecondsSinceEpoch", "CpuClockTicks", "FileByteOffset",
        "DurationMilliseconds", "MonotonicMilliseconds",
        "UtcMilliseconds",
    }
    unsigned2 = {"UInt2"}
    unsigned4 = {"UInt4"}
    unsigned8 = {"UInt8"}
    unsigned16 = {"UInt16"}
    unsigned32 = {"UInt32"}
    unsigned64 = {"UInt64"}
    float16 = {"Float16"}
    float32 = {"Float32"}
    float64 = {"Float64"}
    if typeName == "Bool":
        return "bool"
    if typeName in signed2:
        return "signed2"
    if typeName in signed4:
        return "signed4"
    if typeName in signed8:
        return "signed8"
    if typeName in signed16:
        return "signed16"
    if typeName in signed32:
        return "signed32"
    if typeName in signed64:
        return "signed64"
    if typeName in unsigned2:
        return "unsigned2"
    if typeName in unsigned4:
        return "unsigned4"
    if typeName in unsigned8:
        return "unsigned8"
    if typeName in unsigned16:
        return "unsigned16"
    if typeName in unsigned32:
        return "unsigned32"
    if typeName in unsigned64:
        return "unsigned64"
    if typeName in float16:
        return "float16"
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


Int64_COMPARISON_TARGETS: Dict[str, str] = {
    "math.equalInt64": "math.equalInt32",
    "math.notEqualInt64": "math.notEqualInt32",
    "math.lessThanInt64": "math.lessThanInt32",
    "math.lessThanOrEqualInt64": "math.lessThanOrEqualInt32",
    "math.greaterThanInt64": "math.greaterThanInt32",
    "math.greaterThanOrEqualInt64": "math.greaterThanOrEqualInt32",
}

Int32_COMPARISON_TARGETS: Dict[str, str] = {
    value: key for key, value in Int64_COMPARISON_TARGETS.items()
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
            reprName = "Int32"
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


def _bind_return_domain(resolved_type: str) -> Optional[str]:
    """Classify a resolved type into a coarse domain for the bind-return check:
    "opaque" for the non-interchangeable domain handles, "scalar" for primitives
    and String, or None when we can't classify it (so we skip rather than guess)."""
    if resolved_type in _OPAQUE_DOMAIN_HANDLE_TYPES:
        return "opaque"
    if resolved_type == "String" or resolved_type in PRIMITIVE_CANONICAL_BY_TYPE:
        return "scalar"
    return None


def check_bind_return_type_domain(facts: ExtendedFacts) -> List[Diagnostic]:
    """SS4302 — a `bind` declares a type whose DOMAIN contradicts the call
    target's real return type. Catches the class of bug where everything lowers
    to `i8*` so the type lie type-checks: e.g. binding a String/scalar-returning
    call as an opaque `HtmlFragment`/`HtmlDocument`/`JsonDocument` handle (or
    vice versa). Consuming that mislabeled value — feeding it to `html.hydrate`,
    say — dereferences garbage and crashes at runtime. Only the opaque<->scalar
    cross-domain case is flagged (high confidence); same-domain width/coercion
    differences are left to other checks."""
    diagnostics: List[Diagnostic] = []
    typeAliases = dict(facts.base.type_aliases)

    # Single-type return contract per user operation (skip Result/multi-type
    # outputs — those are not a plain handle/scalar to compare).
    userOpReturnType: Dict[str, str] = {}
    for operation in facts.base.operations.values():
        for sourceLine in operation.lines:
            parsed = output_parts(sourceLine)
            if parsed is not None and parsed[0] == operation.name:
                # output_parts returns (op, firstTypeToken); a Result contract
                # is `output operation OP Result OK ERR` — first token "Result".
                if parsed[1] != "Result":
                    userOpReturnType[operation.name] = parsed[1]
                break

    def return_type_of(target: str) -> Optional[str]:
        if target.startswith("html.hydrate."):
            return "HtmlDocument"  # an opaque HTML handle (doc or fragment)
        if target in BUILTIN_TARGET_RETURN_TYPES:
            return BUILTIN_TARGET_RETURN_TYPES[target]
        # The `string.*` namespace operates on and returns text/scalars (bytes,
        # counts, C-strings) — never an opaque HTML/JSON handle. Treating it as
        # the scalar domain catches binding a String op's result as an
        # HtmlFragment (the `string.concat`-as-fragment SIGSEGV class) at lint.
        if target.startswith("string."):
            return "String"
        return userOpReturnType.get(target)

    for operation in facts.base.operations.values():
        operationCitations = narrative_citations_for_operation(facts, operation.name)
        callTargetByCallName: Dict[str, str] = {}
        for sourceLine in operation.lines:
            if not sourceLine.tokens or is_comment(sourceLine):
                continue
            if sourceLine.verb == "call" and len(sourceLine.args) >= 2:
                callTargetByCallName[sourceLine.args[0]] = sourceLine.args[1]

        for sourceLine in operation.lines:
            if not sourceLine.tokens or is_comment(sourceLine):
                continue
            parsedBind = bind_parts(sourceLine)
            if parsedBind is None:
                continue
            variant, boundName, declaredType, callName = parsedBind
            if variant not in {"value", "ok"}:
                continue
            target = callTargetByCallName.get(callName)
            if not target:
                continue
            returnType = return_type_of(target)
            if returnType is None:
                continue
            declaredResolved = _resolve_type_alias_head(declaredType, typeAliases)
            returnResolved = _resolve_type_alias_head(returnType, typeAliases)
            declaredDomain = _bind_return_domain(declaredResolved)
            returnDomain = _bind_return_domain(returnResolved)
            if declaredDomain is None or returnDomain is None:
                continue
            if {declaredDomain, returnDomain} != {"opaque", "scalar"}:
                continue
            diagnostics.append(Diagnostic(
                tier=Tier.T1_SPEC,
                code="SS4302",
                kind="typeIntegrity.bindReturnDomainMismatch",
                severity=Severity.ERROR,
                subjectName=boundName,
                subjectKind="bindSlot",
                gapEdge="matchingReturnType",
                intentSlogan="bind type contradicts call return type domain",
                primary=span_of_line(sourceLine, "bindReturnDomainSite"),
                related=[span_of_line(operation.line, "enclosingOperation")],
                invariantRule=(
                    f"`{boundName}` is bound as `{declaredType}` but `{target}` "
                    f"returns `{returnType}` — an opaque domain handle and a "
                    f"String/scalar are not interchangeable even though both "
                    f"lower to a pointer. Consuming the mislabeled value (e.g. "
                    f"hydrating it) dereferences garbage at runtime."
                ),
                specAnchor="docs/reference/syntax-inventory.md#bind",
                citations=operationCitations,
                fixCandidates=[
                    FixCandidate(
                        name="useActualReturnType",
                        shape=f"bind {variant} {boundName} {returnType} {callName}",
                    ),
                ],
                confidence=Confidence.HIGH,
                blocksCompile=True,
                effort=Effort.LOCAL,
                passProvenance="check_bind_return_type_domain",
                agentHint=(
                    "Bind the call's real return type. To build an HTML fragment "
                    "from pieces, use the HTML fragment/template path "
                    "(html.hydrate + HtmlFragment holes), not a String op."
                ),
            ))
    return diagnostics


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
            if not sourceLine.tokens or is_comment(sourceLine):
                continue
            parsedInput = input_parts(sourceLine)
            if parsedInput is not None and parsedInput[0] == operation.name:
                signature[parsedInput[1]] = parsedInput[2]
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
        elif verb == "storage" and len(args) >= 4:
            # `storage SCOPE MUTABILITY NAME TYPE [INIT]`
            moduleScopeValueTypes[args[2]] = args[3]
        elif verb == "sharedState" and len(args) >= 4:
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
            parsedInput = input_parts(sourceLine)
            parsedBind = bind_parts(sourceLine)
            parsedMemory = memory_parts(sourceLine)
            if parsedInput is not None and parsedInput[0] == operation.name:
                valueTypesInScope[parsedInput[1]] = parsedInput[2]
            elif verb in {"const", "var", "let"} and len(args) >= 2:
                valueTypesInScope[args[0]] = args[1]
            elif parsedMemory is not None and parsedMemory[1] in {"mutable", "immutable"} and len(parsedMemory[2]) >= 3:
                valueTypesInScope[parsedMemory[2][0]] = parsedMemory[2][1]
            elif parsedBind is not None:
                valueTypesInScope[parsedBind[1]] = parsedBind[2]
            elif verb == "call" and len(args) >= 2:
                callTargetByCallName[args[0]] = args[1]

        # Second pass: every `argument CALL ARGNAME TYPE VALUE` against the target signature
        for sourceLine in operation.lines:
            if not sourceLine.tokens or is_comment(sourceLine):
                continue
            parsedArgument = argument_parts(sourceLine)
            if parsedArgument is None:
                continue
            callReferenceName, argumentName, declaredArgumentType, suppliedValueName = parsedArgument
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

            if declaredArgumentType is not None:
                resolvedDeclaredArgument = _resolve_type_alias_head(
                    declaredArgumentType, typeAliases)
                resolvedExpectedArgument = _resolve_type_alias_head(
                    expectedType, typeAliases)
                # Fold the width-preserving C-ABI spellings so the LLVM-style
                # name (`Int64`, `Float64`) and the C-ABI name (`Int64`,
                # `Float64`) for the same type compare equal. This is
                # intentionally narrow — it does NOT fold different widths
                # (Int32 stays distinct from Int64), so a float builtin
                # annotated with an integer type still mismatches.
                resolvedDeclaredArgument = _C_ABI_WIDTH_ALIAS.get(
                    resolvedDeclaredArgument, resolvedDeclaredArgument)
                resolvedExpectedArgument = _C_ABI_WIDTH_ALIAS.get(
                    resolvedExpectedArgument, resolvedExpectedArgument)
                if resolvedDeclaredArgument != resolvedExpectedArgument:
                    diagnostics.append(Diagnostic(
                        tier=Tier.T1_SPEC,
                        code="SS4301",
                        kind="typeIntegrity.argumentTypeMismatch",
                        severity=Severity.ERROR,
                        subjectName=declaredArgumentType,
                        subjectKind="argumentType",
                        gapEdge="matchingParameterType",
                        intentSlogan="argument row type does not match target signature",
                        primary=span_of_line(sourceLine, "argumentTypeMismatchSite"),
                        related=[span_of_line(operation.line, "enclosingOperation")],
                        invariantRule=(
                            f"`argument {callReferenceName} {argumentName} {declaredArgumentType} {suppliedValueName}` "
                            f"declares `{declaredArgumentType}`, but `{targetName}` expects `{expectedType}`"
                        ),
                        specAnchor="docs/reference/syntax-inventory.md#argument",
                        citations=operationCitations,
                        fixCandidates=[
                            FixCandidate(
                                name="useExpectedArgumentType",
                                shape=f"argument {callReferenceName} {argumentName} {expectedType} {suppliedValueName}",
                            ),
                        ],
                        confidence=Confidence.HIGH,
                        blocksCompile=True,
                        effort=Effort.TRIVIAL,
                        passProvenance="check_argument_type_mismatch",
                        agentHint="the repeated type on `argument` must match the callee signature",
                    ))
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
                subjectKind="argumentValue",
                gapEdge="matchingType",
                intentSlogan="arg value type does not match target signature",
                primary=span_of_line(sourceLine, "argTypeMismatchSite"),
                related=[span_of_line(operation.line, "enclosingOperation")],
                invariantRule=(
                    f"`argument {callReferenceName} {argumentName} {declaredArgumentType or expectedType} {suppliedValueName}` "
                    f"expects type `{expectedType}` (canonical `{resolvedExpected}`); "
                    f"`{suppliedValueName}` is declared `{actualType}` "
                    f"(canonical `{resolvedActual}`)"
                ),
                specAnchor="docs/reference/syntax-inventory.md#argument",
                citations=operationCitations,
                fixCandidates=[
                    FixCandidate(
                        name="supplyValueOfExpectedType",
                        shape=f"argument {callReferenceName} {argumentName} {expectedType} <valueOfType:{expectedType}>",
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
        elif verb == "storage" and len(args) >= 4:
            moduleScopeValueTypes[args[2]] = args[3]
        elif verb == "sharedState" and len(args) >= 4:
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
            elif verb == "storage" and len(args) >= 4:
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
            if targetName in Int64_COMPARISON_TARGETS and actualShape == "signed32":
                suggestedTarget = Int64_COMPARISON_TARGETS[targetName]
            elif targetName in Int32_COMPARISON_TARGETS and actualShape == "signed64":
                suggestedTarget = Int32_COMPARISON_TARGETS[targetName]
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


_FLOAT_LITERAL_TOKEN_RE = re.compile(
    r"^-?(?:(?:\d+\.\d*)|(?:\.\d+)|(?:\d+))(?:[eE][+-]?\d+)?$"
)
_IDENTIFIER_TOKEN_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_.]*$")


def _is_float_literal_token(token: str) -> bool:
    return bool(_FLOAT_LITERAL_TOKEN_RE.match(token))


def _is_identifier_token(token: str) -> bool:
    return bool(_IDENTIFIER_TOKEN_RE.match(token))


INTEGER_LITERAL_RANGES: Dict[str, Tuple[int, int]] = {
    "Int2": (-2, 1),
    "UInt2": (0, 3),
    "Int4": (-8, 7),
    "UInt4": (0, 15),
    "Int8": (-128, 127),
    "UInt8": (0, 255),
    "Int16": (-32768, 32767),
    "UInt16": (0, 65535),
    "Int32": (-2147483648, 2147483647),
    "UInt32": (0, 4294967295),
    "Int64": (-9223372036854775808, 9223372036854775807),
    "UInt64": (0, 18446744073709551615),
    "ByteCount": (-9223372036854775808, 9223372036854775807),
    "SignedByteCount": (-9223372036854775808, 9223372036854775807),
    "AddressOffset": (-9223372036854775808, 9223372036854775807),
    "UnixSecondsSinceEpoch": (-9223372036854775808, 9223372036854775807),
    "CpuClockTicks": (-9223372036854775808, 9223372036854775807),
    "FileByteOffset": (-9223372036854775808, 9223372036854775807),
}

FLOAT_LITERAL_PACK_FORMAT: Dict[str, str] = {
    "Float16": "e",
    "Float32": "f",
    "Float64": "d",
}


def _parse_char_literal(token: str) -> Optional[int]:
    if len(token) < 3 or not (token.startswith("'") and token.endswith("'")):
        return None
    body = token[1:-1]
    if body == "":
        return None
    if body.startswith("\\u{") and body.endswith("}"):
        hex_body = body[3:-1]
        if not hex_body:
            return None
        try:
            value = int(hex_body, 16)
        except ValueError:
            return None
    elif body.startswith("\\"):
        escapes = {
            "\\0": 0,
            "\\n": 10,
            "\\r": 13,
            "\\t": 9,
            "\\\\": 92,
            "\\'": 39,
            "\\\"": 34,
        }
        value = escapes.get(body)
        if value is None:
            return None
    elif len(body) == 1:
        value = ord(body)
    else:
        return None
    if value < 0 or value > 0x10FFFF:
        return None
    if 0xD800 <= value <= 0xDFFF:
        return None
    return value


def _validate_scalar_literal(typeName: str, token: str) -> Optional[str]:
    resolvedType = typeName
    if resolvedType == "Bool":
        if token.lower() in {"true", "false", "yes", "no", "1", "0"}:
            return None
        if _is_identifier_token(token):
            return None
        return "Bool literals must be one of true/false/yes/no/1/0"
    if resolvedType == "Char":
        charValue = _parse_char_literal(token)
        if charValue is not None:
            return None
        if _is_integer_literal(token):
            rawValue = int(token, 10)
            if rawValue < 0 or rawValue > 0x10FFFF or 0xD800 <= rawValue <= 0xDFFF:
                return "Char literals must be Unicode scalar values"
            return None
        if _is_identifier_token(token):
            return None
        return "Char literals must be a Unicode scalar integer or a single-quoted character literal"
    integerRange = INTEGER_LITERAL_RANGES.get(resolvedType)
    if integerRange is not None:
        if not _is_integer_literal(token):
            return None
        rawValue = int(token, 10)
        minimum, maximum = integerRange
        if rawValue < minimum or rawValue > maximum:
            return f"{resolvedType} literal out of range [{minimum}, {maximum}]"
        return None
    packFormat = FLOAT_LITERAL_PACK_FORMAT.get(resolvedType)
    if packFormat is not None:
        if not _is_float_literal_token(token):
            return None
        try:
            parsed = float(token)
        except ValueError:
            return f"{resolvedType} literal is not a valid floating-point token"
        try:
            struct.pack(packFormat, parsed)
        except OverflowError:
            return f"{resolvedType} literal overflows the target width"
        except struct.error:
            return f"{resolvedType} literal overflows the target width"
        return None
    return None


def _operation_success_output_type(
    facts: ExtendedFacts,
    operation: OperationFact,
) -> Tuple[Optional[str], Optional[str], Optional[SourceLine]]:
    for sourceLine in operation.lines:
        if not sourceLine.tokens or is_comment(sourceLine):
            continue
        parsedOutput = output_parts(sourceLine)
        if parsedOutput is not None and parsedOutput[0] == operation.name:
            outputType = parsedOutput[1]
            if outputType == "Result":
                if len(sourceLine.args) >= 3:
                    return sourceLine.args[2], "return ok", sourceLine
                return None, None, sourceLine
            resultType = facts.base.result_types.get(outputType)
            if resultType is not None:
                return resultType.ok_type, "return ok", sourceLine
            return outputType, "return value", sourceLine
    return None, None, None


def check_enum_return_uses_case(facts: ExtendedFacts) -> List[Diagnostic]:
    diagnostics: List[Diagnostic] = []
    typeAliases = facts.base.type_aliases
    _enumReprs, enumCasesByType, enumCaseValuesByType, enumTypeByCase = _enum_context(facts)

    for operation in facts.base.operations.values():
        outputType, expectedReturnVerb, outputLine = _operation_success_output_type(facts, operation)
        if outputType is None or expectedReturnVerb is None:
            continue
        enumType = _resolve_type_head(outputType, typeAliases, {})
        if enumType not in enumCasesByType:
            continue

        validCases = set(enumCasesByType.get(enumType, []))
        operationCitations = narrative_citations_for_operation(facts, operation.name)
        for sourceLine in operation.lines:
            if (not sourceLine.tokens or is_comment(sourceLine)
                    or return_parts(sourceLine) != (expectedReturnVerb.split()[1], sourceLine.args[1] if sourceLine.verb == "return" and len(sourceLine.args) > 1 else (sourceLine.args[0] if sourceLine.args else None))):
                continue
            parsedReturn = return_parts(sourceLine)
            if parsedReturn is None or parsedReturn[1] is None:
                continue
            returnedValue = parsedReturn[1]
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
                specAnchor="docs/reference/syntax-inventory.md#enumCase",
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


def check_removed_scalar_surface(facts: ExtendedFacts) -> List[Diagnostic]:
    diagnostics: List[Diagnostic] = []
    for sourceLine in facts.base.lines:
        if not sourceLine.tokens or is_comment(sourceLine):
            continue
        for token in sourceLine.tokens:
            if token.quoted:
                continue
            replacement = REMOVED_PRIMITIVE_SPELLINGS.get(token.text)
            if replacement is None:
                continue
            diagnostics.append(Diagnostic(
                tier=Tier.T1_SPEC,
                code="SS4303",
                kind="typeSurface.removedPrimitiveSpelling",
                severity=Severity.ERROR,
                subjectName=token.text,
                subjectKind="typeToken",
                gapEdge="primitiveName",
                intentSlogan="legacy primitive spelling removed",
                primary=Span(
                    path=sourceLine.path,
                    line=sourceLine.number,
                    column=token.start + 1,
                    role="removedPrimitiveToken",
                ),
                invariantRule=(
                    f"`{token.text}` is no longer part of the user-facing primitive surface; "
                    f"use `{replacement}` instead"
                ),
                specAnchor="docs/language/types-values.md#primitive-lowering",
                fixCandidates=[
                    FixCandidate(
                        name="replacePrimitiveSpelling",
                        shape=f"# replace `{token.text}` with `{replacement}`",
                        autoApplicable=True,
                    ),
                ],
                confidence=Confidence.HIGH,
                blocksCompile=True,
                effort=Effort.LOCAL,
                passProvenance="check_removed_scalar_surface",
                agentHint=(
                    "the primitive cutover removed legacy I*/F*/C* spellings from source; "
                    "rewrite the declaration, argument row, or binding to the semantic scalar name"
                ),
            ))
        if sourceLine.verb == "call" and len(sourceLine.args) >= 2:
            targetName = sourceLine.args[1]
            replacement = REMOVED_CALL_TARGET_SPELLINGS.get(targetName)
            if replacement is None:
                continue
            diagnostics.append(Diagnostic(
                tier=Tier.T1_SPEC,
                code="SS4304",
                kind="callTarget.removedLegacySpelling",
                severity=Severity.ERROR,
                subjectName=targetName,
                subjectKind="callTarget",
                gapEdge="targetName",
                intentSlogan="legacy call target removed",
                primary=span_of_line(sourceLine, "callTarget"),
                invariantRule=(
                    f"`{targetName}` is no longer part of the source surface; "
                    f"use `{replacement}` instead"
                ),
                specAnchor="docs/reference/call-targets.md#math-targets",
                fixCandidates=[
                    FixCandidate(
                        name="replaceCallTarget",
                        shape=f"call {sourceLine.args[0]} {replacement}",
                        autoApplicable=True,
                    ),
                ],
                confidence=Confidence.HIGH,
                blocksCompile=True,
                effort=Effort.LOCAL,
                passProvenance="check_removed_scalar_surface",
                agentHint=(
                    "the primitive cutover also renamed width-specific math/json targets; "
                    "update the call target instead of relying on an alias"
                ),
            ))
    return diagnostics


def check_scalar_literal_ranges(facts: ExtendedFacts) -> List[Diagnostic]:
    diagnostics: List[Diagnostic] = []
    rowsToCheck: List[Tuple[str, str, SourceLine, str]] = []

    for sourceLine in facts.base.lines:
        if not sourceLine.tokens or is_comment(sourceLine):
            continue
        args = sourceLine.args
        verb = sourceLine.verb
        if verb == "storage" and len(args) >= 5:
            rowsToCheck.append((args[3], args[4], sourceLine, args[2]))
        elif verb == "memory" and len(args) >= 5 and args[1] in {"mutable", "immutable"}:
            rowsToCheck.append((args[3], args[4], sourceLine, args[2]))
        elif verb in {"const", "let", "var", "domainLiteral"} and len(args) >= 3:
            rowsToCheck.append((args[1], args[2], sourceLine, args[0]))
        elif verb == "argument" and len(args) >= 4:
            rowsToCheck.append((args[2], args[3], sourceLine, args[1]))

    for typeName, valueToken, sourceLine, subjectName in rowsToCheck:
        problem = _validate_scalar_literal(typeName, valueToken)
        if problem is None:
            continue
        diagnostics.append(Diagnostic(
            tier=Tier.T1_SPEC,
            code="SS4305",
            kind="typeIntegrity.scalarLiteralRange",
            severity=Severity.ERROR,
            subjectName=subjectName,
            subjectKind="literalBinding",
            gapEdge="literalRange",
            intentSlogan="scalar literal out of range",
            primary=span_of_line(sourceLine, "literalRangeSite"),
            invariantRule=problem,
            specAnchor="docs/language/types-values.md#primitive-lowering",
            confidence=Confidence.HIGH,
            blocksCompile=True,
            effort=Effort.LOCAL,
            passProvenance="check_scalar_literal_ranges",
            agentHint=(
                "literal values must fit the declared scalar width exactly; "
                "widen the declaration or change the literal instead of relying on truncation"
            ),
        ))

    return diagnostics


# Integer divide / modulo targets (plus their short aliases). The `right`
# operand is the divisor; an `srem`/`sdiv` by zero is LLVM undefined behavior,
# not a trap, so a divisor that the linter can *prove* is the literal 0 must
# never reach codegen.
DIVISION_INT64_TARGETS: frozenset = frozenset({
    "math.divideInt64", "math.moduloInt64",
    "math.divInt64", "math.modInt64",
})

# Shift targets. The `right` operand is the shift count and must be in [0, 63];
# a constant count outside that range is LLVM poison (undefined), matching the
# `standard.bit` module's documented "bitIndex must be in [0, 63]" contract.
SHIFT_INT64_TARGETS: frozenset = frozenset({
    "math.shiftLeftInt64",
    "math.shiftRightLogicalInt64",
    "math.shiftRightArithmeticInt64",
})

# Domain-typed method names that lower to integer divide/modulo. A call like
# `QuotaCount.divide` (where `QuotaCount` aliases Int64) lowers to sdiv, so the
# divide-by-zero check must see through the domain surface — matching the
# compiler's `_strict_resolve_arith_target`. Float64 divide is defined on 0
# (inf/nan), so it is intentionally excluded.
DOMAIN_DIVISION_METHODS: frozenset = frozenset({"divide", "modulo", "moduloBy"})


def _resolve_division_or_shift_target(
    targetName: str,
    typeAliases: Dict[str, str],
) -> str:
    """Resolve a domain-typed `Type.divide`/`Type.modulo` call to its integer
    division primitive when `Type` heads to Int64, so the constant-zero check
    matches the compiler wall on idiomatic domain-typed arithmetic."""
    if targetName in DIVISION_INT64_TARGETS or targetName in SHIFT_INT64_TARGETS:
        return targetName
    if "." not in targetName:
        return targetName
    typePart, methodPart = targetName.split(".", 1)
    if methodPart not in DOMAIN_DIVISION_METHODS:
        return targetName
    if _resolve_type_alias_head(typePart, typeAliases) == "Int64":
        return "math.moduloInt64" if methodPart != "divide" else "math.divideInt64"
    return targetName


def _resolve_literal_int(
    valueName: str,
    literalMap: Dict[str, Tuple[str, str, SourceLine]],
) -> Optional[int]:
    """Resolve a divisor/shift-count operand to a concrete integer when it is a
    compile-time constant — either an inline integer literal token or a named
    `domainLiteral`/`const`/`literal`/`storage`/`memory` immutable bound to an
    integer literal. Returns None when the value is not a provable constant
    (a runtime binding, an opaque/namespaced constant, etc.), in which case
    these checks stay silent — they only fire on values they can *prove* bad,
    so they never false-positive on guarded or runtime divisors."""
    seen: Set[str] = set()
    current = valueName
    # Follow a bounded constant->constant alias chain (e.g.
    # `domainLiteral zeroB Int64 zeroA` where `zeroA` is itself 0).
    for _ in range(8):
        if _is_integer_literal(current):
            return int(current)
        if current in seen:
            return None
        seen.add(current)
        entry = literalMap.get(current)
        if entry is None:
            return None
        current = entry[1]
    return None


def _immutable_constant_row(sourceLine: SourceLine) -> Optional[Tuple[str, str, str]]:
    """Return (name, typeName, valueToken) for an *immutable* constant row, or
    None. Mutable `storage`/`memory` slots are excluded on purpose: a slot
    `memory OP mutable counter Int64 0` is initialized to 0 but reassigned via
    `set memory`, so its initializer is not its value at a later divide/shift
    site (this is why the GCD/Newton loops in the stdlib are not flagged)."""
    verb = sourceLine.verb
    args = sourceLine.args
    if verb in {"domainLiteral", "const", "literal"} and len(args) >= 3:
        return args[0], args[1], args[2]
    if verb in {"storage", "sharedState"} and len(args) >= 5 and args[1] == "immutable":
        return args[2], args[3], args[4]   # storage/sharedState SCOPE immutable NAME TYPE VALUE
    if verb == "memory" and len(args) >= 5 and args[1] == "immutable":
        return args[2], args[3], args[4]    # memory OP immutable NAME TYPE VALUE
    return None


def _rebound_name(sourceLine: SourceLine) -> Optional[str]:
    """The local name introduced/reassigned by this row, if any. Such a name is
    a runtime binding, so any same-named module constant must NOT be trusted
    inside this operation (shadowing / rebinding wins)."""
    verb = sourceLine.verb
    args = sourceLine.args
    inputParts = input_parts(sourceLine)
    if inputParts is not None:
        return inputParts[1]
    bindParts = bind_parts(sourceLine)
    if bindParts is not None:
        return bindParts[1]
    if verb == "set" and len(args) >= 2 and args[0] in {"memory", "storage", "sharedState"}:
        return args[1]
    # A mutable storage/memory/sharedState slot is a runtime binding even at its
    # declaration.
    if verb in {"storage", "sharedState"} and len(args) >= 4 and args[1] == "mutable":
        return args[2]
    if verb == "memory" and len(args) >= 4 and args[1] == "mutable":
        return args[2]
    return None


def _module_immutable_constants(facts: ExtendedFacts) -> Dict[str, Tuple[str, str, SourceLine]]:
    """Module-scope immutable constants only. Lines that belong to an operation
    body are skipped so operation-local `storage local`/`memory` declarations do
    not leak across operations (that global leak was a real false-positive
    source: a `storage local immutable cnt 64` in op A must not resolve `cnt`
    inside op B where it is a runtime input)."""
    operationLineKeys = {
        (sourceLine.path, sourceLine.number)
        for operation in facts.base.operations.values()
        for sourceLine in operation.lines
    }
    constants: Dict[str, Tuple[str, str, SourceLine]] = {}
    for sourceLine in facts.base.lines:
        if is_comment(sourceLine) or not sourceLine.tokens:
            continue
        if (sourceLine.path, sourceLine.number) in operationLineKeys:
            continue
        row = _immutable_constant_row(sourceLine)
        if row is not None:
            constants[row[0]] = (row[1], row[2], sourceLine)
    return constants


def _operation_constant_map(
    facts: ExtendedFacts,
    operation: OperationFact,
    moduleConstants: Dict[str, Tuple[str, str, SourceLine]],
) -> Dict[str, Tuple[str, str, SourceLine]]:
    """Module constants, plus this operation's own immutable constants, minus
    any name the operation rebinds (`input`/`bind`/`set`/mutable slot). Scope is
    operation-local so a constant in one op never resolves a runtime name in
    another, and a runtime binding always shadows a same-named module constant."""
    constants = dict(moduleConstants)
    rebound: Set[str] = set()
    for sourceLine in operation.lines:
        if is_comment(sourceLine) or not sourceLine.tokens:
            continue
        row = _immutable_constant_row(sourceLine)
        if row is not None:
            constants[row[0]] = (row[1], row[2], sourceLine)
            continue
        reboundName = _rebound_name(sourceLine)
        if reboundName is not None:
            rebound.add(reboundName)
    for name in rebound:
        constants.pop(name, None)
    return constants


def check_constant_division_or_shift_ub(facts: ExtendedFacts) -> List[Diagnostic]:
    """SS4308 / SS4309 — integer arithmetic whose operand the linter can prove
    triggers undefined behavior at the LLVM level:

      * SS4308 divisionByConstantZero — `math.divideInt64`/`math.moduloInt64`
        whose `right` divisor resolves to the literal 0 (sdiv/srem by 0 is UB).
      * SS4309 shiftCountOutOfRange — a shift whose `right` count resolves to a
        constant outside [0, 63] (a poison shift, not a wrap).

    Both fire only when the operand is a *provable* constant, so a runtime or
    comparison-guarded divisor/count is never flagged here — that broader,
    dataflow-sensitive case is tracked separately and needs an explicit
    range-discharge construct. This pass is the zero-false-positive floor."""
    diagnostics: List[Diagnostic] = []
    moduleConstants = _module_immutable_constants(facts)
    for operation in facts.base.operations.values():
        operationCitations = narrative_citations_for_operation(facts, operation.name)
        literalMap = _operation_constant_map(facts, operation, moduleConstants)
        callTargetByName: Dict[str, str] = {}
        rightArgLineByCall: Dict[str, SourceLine] = {}
        rightValueByCall: Dict[str, str] = {}
        for sourceLine in operation.lines:
            if is_comment(sourceLine) or not sourceLine.tokens:
                continue
            if sourceLine.verb == "call" and len(sourceLine.args) >= 2:
                callTargetByName[sourceLine.args[0]] = sourceLine.args[1]
                continue
            argParts = argument_parts(sourceLine)
            if argParts is not None and argParts[1] == "right":
                rightArgLineByCall[argParts[0]] = sourceLine
                rightValueByCall[argParts[0]] = argParts[3]

        for callName, rawTargetName in callTargetByName.items():
            divisorValue = rightValueByCall.get(callName)
            if divisorValue is None:
                continue
            targetName = _resolve_division_or_shift_target(
                rawTargetName, facts.base.type_aliases)
            argLine = rightArgLineByCall[callName]
            resolved = _resolve_literal_int(divisorValue, literalMap)

            if targetName in DIVISION_INT64_TARGETS and resolved == 0:
                diagnostics.append(Diagnostic(
                    tier=Tier.T1_SPEC,
                    code="SS4308",
                    kind="typeIntegrity.divisionByConstantZero",
                    severity=Severity.ERROR,
                    subjectName=callName,
                    subjectKind="call",
                    gapEdge="nonZeroDivisor",
                    intentSlogan="divide/modulo by constant zero",
                    primary=span_of_line(argLine, "divisorArgument"),
                    related=[span_of_line(operation.line, "enclosingOperation")],
                    invariantRule=(
                        f"`{targetName}` lowers to LLVM sdiv/srem; a divisor of 0 "
                        f"is undefined behavior. semsc emits a runtime divisor-zero "
                        f"trap by default, but it is silent UB under "
                        f"`runtimeChecks off` — and a constant-zero divisor is "
                        f"never intended. `{callName}` divides by `{divisorValue}` "
                        f"which is the constant 0."
                    ),
                    specAnchor="docs/language/types-values.md#primitive-lowering",
                    citations=operationCitations,
                    fixCandidates=[
                        FixCandidate(
                            name="guardDivisorIsNonZero",
                            shape=(
                                f"call {callName}DivisorCheck math.equalInt64\n"
                                f"argument {callName}DivisorCheck left Int64 {divisorValue}\n"
                                f"argument {callName}DivisorCheck right Int64 <zeroConstant>\n"
                                f"run {callName}DivisorCheck\n"
                                f"bind value {callName}DivisorIsZero Bool {callName}DivisorCheck\n"
                                f"branch if condition {callName}DivisorIsZero target <divideByZeroLabel>"
                            ),
                            evidence=[span_of_line(argLine)],
                        ),
                    ],
                    confidence=Confidence.HIGH,
                    blocksCompile=True,
                    effort=Effort.LOCAL,
                    passProvenance="check_constant_division_or_shift_ub",
                    agentHint=(
                        "a literal zero divisor is always undefined behavior; "
                        "change the divisor or guard the path so the divide is "
                        "unreachable when the divisor is zero"
                    ),
                ))
                continue

            if targetName in SHIFT_INT64_TARGETS and resolved is not None and not (0 <= resolved <= 63):
                diagnostics.append(Diagnostic(
                    tier=Tier.T1_SPEC,
                    code="SS4309",
                    kind="typeIntegrity.shiftCountOutOfRange",
                    severity=Severity.ERROR,
                    subjectName=callName,
                    subjectKind="call",
                    gapEdge="shiftCountInRange",
                    intentSlogan="shift count outside [0, 63]",
                    primary=span_of_line(argLine, "shiftCountArgument"),
                    related=[span_of_line(operation.line, "enclosingOperation")],
                    invariantRule=(
                        f"`{targetName}` shift count must be in [0, 63]; a count "
                        f"of {resolved} is LLVM poison (undefined), not a wrap. "
                        f"`{callName}` shifts by `{divisorValue}` = {resolved}."
                    ),
                    specAnchor="docs/language/types-values.md#primitive-lowering",
                    citations=operationCitations,
                    fixCandidates=[
                        FixCandidate(
                            name="maskShiftCountIntoRange",
                            shape=(
                                f"# shift counts must be in [0, 63]; mask the count "
                                f"with `math.bitwiseAndInt64` against 63 before "
                                f"`argument {callName} right Int64 ...`"
                            ),
                            evidence=[span_of_line(argLine)],
                        ),
                    ],
                    confidence=Confidence.HIGH,
                    blocksCompile=True,
                    effort=Effort.LOCAL,
                    passProvenance="check_constant_division_or_shift_ub",
                    agentHint=(
                        "an out-of-range constant shift count is undefined at the "
                        "LLVM level; keep the count in [0, 63] (mask with & 63)"
                    ),
                ))

    return diagnostics


# Non-cryptographic PRNG call targets (CWE-338): libc `rand`/`srand` and the
# POSIX `random`/`drand48` relatives. Dual-use: fine for simulations/sampling,
# never for security-sensitive values. Advisory in the permissive surface;
# `semsc --strict` (SS4601) blocks them outright. Kept in sync with the
# compiler's `_STRICT_INSECURE_RANDOM_TARGETS` (parity asserted by tests).
INSECURE_PSEUDORANDOM_TARGETS: frozenset = frozenset(
    "c." + symbol for symbol in (
        "rand", "srand", "random", "srandom", "rand_r", "random_r",
        "drand48", "lrand48", "mrand48", "srand48", "seed48", "lcong48",
        "initstate", "setstate",
    )
)


def check_insecure_pseudorandom(facts: ExtendedFacts) -> List[Diagnostic]:
    """SS4601 — flag non-cryptographic PRNG targets (c.rand/c.srand/c.random).
    Predictable randomness must not back tokens, keys, nonces, or salts."""
    diagnostics: List[Diagnostic] = []
    for operation in facts.base.operations.values():
        operationCitations = narrative_citations_for_operation(facts, operation.name)
        for callFact in collect_operation_calls(operation).values():
            if callFact.target not in INSECURE_PSEUDORANDOM_TARGETS:
                continue
            diagnostics.append(Diagnostic(
                tier=Tier.T3_REFINEMENT,
                code="SS4601",
                kind="security.insecurePseudoRandom",
                severity=Severity.WARNING,
                subjectName=callFact.name,
                subjectKind="call",
                gapEdge="cryptographicRandomness",
                intentSlogan="non-cryptographic PRNG",
                primary=span_of_line(callFact.line, "insecureRandomCall"),
                related=[span_of_line(operation.line, "enclosingOperation")],
                invariantRule=(
                    f"`{callFact.target}` is a deterministic LCG (CWE-338); its "
                    "output is predictable and must never back a token, key, "
                    "nonce, salt, or session id. It is acceptable only for "
                    "non-security sampling/simulation."
                ),
                specAnchor="docs/reference/syntax-inventory.md#random",
                citations=operationCitations,
                fixCandidates=[
                    FixCandidate(
                        name="useCryptographicRandomSource",
                        shape=(
                            "# fill a BcryptRandomBuffer with `bcrypt.randomBytes` "
                            "(platform CSPRNG) and derive the value from those "
                            "bytes instead of calling " + callFact.target
                        ),
                        evidence=[span_of_line(callFact.line)],
                    ),
                ],
                confidence=Confidence.HIGH,
                blocksCompile=False,
                effort=Effort.LOCAL,
                passProvenance="check_insecure_pseudorandom",
                agentHint=(
                    "if this randomness is security-sensitive, switch to "
                    "`bcrypt.randomBytes` (the platform CSPRNG in standard.bcrypt); "
                    "strict mode (SS4601) rejects the libc PRNG family outright"
                ),
            ))
    return diagnostics


# bcrypt password-hash target and the security floor for the cost factor.
# `bcrypt.hashPassword` is *by definition* password hashing, so a cost below the
# OWASP-ASVS floor (10) is a CWE-916 weak work factor — not dual-use. Cost 4-9
# is brute-forceable; the module's `bcryptRecommendedCost` is 12.
#
# Match only the qualified intrinsic spelling — NOT a bare `hashPassword`, which
# would false-positive a user operation that happens to be named `hashPassword`
# (a real risk: `hashPassword` is also the std export name). A singular-import
# alias of the intrinsic is a conservative advisory miss here; the strict wall
# still catches it via target resolution.
PASSWORD_HASH_TARGET: str = "bcrypt.hashPassword"
SECURE_BCRYPT_COST_FLOOR: int = 10


def check_weak_password_hash_cost(facts: ExtendedFacts) -> List[Diagnostic]:
    """SS4602 — `bcrypt.hashPassword` with a provable constant cost below the
    security floor (CWE-916). Advisory here (tests legitimately hash at low cost
    for speed); `semsc --strict` blocks it for production builds."""
    diagnostics: List[Diagnostic] = []
    moduleConstants = _module_immutable_constants(facts)
    for operation in facts.base.operations.values():
        operationCitations = narrative_citations_for_operation(facts, operation.name)
        literalMap = _operation_constant_map(facts, operation, moduleConstants)
        callTargetByName: Dict[str, str] = {}
        callLineByName: Dict[str, SourceLine] = {}
        costArgLineByCall: Dict[str, SourceLine] = {}
        costValueByCall: Dict[str, str] = {}
        for sourceLine in operation.lines:
            if is_comment(sourceLine) or not sourceLine.tokens:
                continue
            if sourceLine.verb == "call" and len(sourceLine.args) >= 2:
                callTargetByName[sourceLine.args[0]] = sourceLine.args[1]
                callLineByName[sourceLine.args[0]] = sourceLine
                continue
            argParts = argument_parts(sourceLine)
            if argParts is not None and argParts[1] == "cost":
                costArgLineByCall[argParts[0]] = sourceLine
                costValueByCall[argParts[0]] = argParts[3]

        for callName, targetName in callTargetByName.items():
            if targetName != PASSWORD_HASH_TARGET:
                continue
            costValue = costValueByCall.get(callName)
            if costValue is None:
                # Missing `cost` — bcrypt needs an explicit work factor; omitting
                # it otherwise slips past the check (and ValueErrors in codegen).
                diagnostics.append(Diagnostic(
                    tier=Tier.T3_REFINEMENT,
                    code="SS4602",
                    kind="security.weakPasswordHashCost",
                    severity=Severity.WARNING,
                    subjectName=callName,
                    subjectKind="call",
                    gapEdge="bcryptCostFactor",
                    intentSlogan="bcrypt missing cost factor",
                    primary=span_of_line(callLineByName[callName], "bcryptHashCall"),
                    related=[span_of_line(operation.line, "enclosingOperation")],
                    invariantRule=(
                        "`bcrypt.hashPassword` is missing the required `cost` "
                        "argument; bcrypt needs an explicit work factor (CWE-916). "
                        "Use `bcryptRecommendedCost` (12)."
                    ),
                    specAnchor="docs/reference/syntax-inventory.md#bcrypt",
                    citations=operationCitations,
                    fixCandidates=[
                        FixCandidate(
                            name="addBcryptCost",
                            shape=f"argument {callName} cost Int32 bcryptRecommendedCost",
                            evidence=[span_of_line(callLineByName[callName])],
                        ),
                    ],
                    confidence=Confidence.HIGH,
                    blocksCompile=False,
                    effort=Effort.TRIVIAL,
                    passProvenance="check_weak_password_hash_cost",
                    agentHint=(
                        "bcrypt requires an explicit cost; add "
                        "`cost Int32 bcryptRecommendedCost` (strict mode SS4602 "
                        "rejects a missing or weak cost)"
                    ),
                ))
                continue
            resolved = _resolve_literal_int(costValue, literalMap)
            if resolved is None or resolved >= SECURE_BCRYPT_COST_FLOOR:
                continue
            argLine = costArgLineByCall[callName]
            diagnostics.append(Diagnostic(
                tier=Tier.T3_REFINEMENT,
                code="SS4602",
                kind="security.weakPasswordHashCost",
                severity=Severity.WARNING,
                subjectName=callName,
                subjectKind="call",
                gapEdge="bcryptCostFactor",
                intentSlogan="bcrypt cost below security floor",
                primary=span_of_line(argLine, "bcryptCostArgument"),
                related=[span_of_line(operation.line, "enclosingOperation")],
                invariantRule=(
                    f"`bcrypt.hashPassword` cost {resolved} is below the security "
                    f"floor of {SECURE_BCRYPT_COST_FLOOR} (CWE-916). bcrypt cost is "
                    f"a work factor; a low constant cost is brute-forceable. Use "
                    f"`bcryptRecommendedCost` (12) unless application policy chooses "
                    f"otherwise. Low cost is acceptable only in tests."
                ),
                specAnchor="docs/reference/syntax-inventory.md#bcrypt",
                citations=operationCitations,
                fixCandidates=[
                    FixCandidate(
                        name="useRecommendedBcryptCost",
                        shape=f"argument {callName} cost Int32 bcryptRecommendedCost",
                        evidence=[span_of_line(argLine)],
                    ),
                ],
                confidence=Confidence.HIGH,
                blocksCompile=False,
                effort=Effort.TRIVIAL,
                passProvenance="check_weak_password_hash_cost",
                agentHint=(
                    "raise the bcrypt cost to bcryptRecommendedCost (12); strict "
                    "mode (SS4602) rejects a cost below "
                    f"{SECURE_BCRYPT_COST_FLOOR} outright"
                ),
            ))
    return diagnostics


# OS command-execution targets (CWE-78). `c.system` hands its argument to a
# shell; a non-constant command is command injection.
SHELL_COMMAND_TARGETS: frozenset = frozenset({"c.system"})


def check_shell_command_not_constant(facts: ExtendedFacts) -> List[Diagnostic]:
    """SS4603 — `c.system` must take a compile-time-constant command string; a
    runtime/untrusted command is OS command injection (CWE-78). Advisory here;
    `semsc --strict` blocks it."""
    diagnostics: List[Diagnostic] = []
    moduleConstants = _module_immutable_constants(facts)
    for operation in facts.base.operations.values():
        operationCitations = narrative_citations_for_operation(facts, operation.name)
        constants = _operation_constant_map(facts, operation, moduleConstants)
        for callFact in collect_operation_calls(operation).values():
            if callFact.target not in SHELL_COMMAND_TARGETS:
                continue
            for argLine in callFact.arg_lines:
                parts = argument_parts(argLine)
                if parts is None:
                    continue
                commandValue = parts[3]
                if commandValue in constants:
                    continue
                # An inline string literal (`c.system("ls -la")`) is a constant;
                # the value token carries the quoted flag. Only a bare-name value
                # that is not a resolvable immutable constant is the injection risk.
                if argLine.tokens and argLine.tokens[-1].quoted:
                    continue
                diagnostics.append(Diagnostic(
                    tier=Tier.T3_REFINEMENT,
                    code="SS4603",
                    kind="security.shellCommandNotConstant",
                    severity=Severity.WARNING,
                    subjectName=callFact.name,
                    subjectKind="call",
                    gapEdge="constantShellCommand",
                    intentSlogan="non-constant shell command",
                    primary=span_of_line(argLine, "shellCommandArgument"),
                    related=[span_of_line(operation.line, "enclosingOperation")],
                    invariantRule=(
                        f"`c.system` runs `{commandValue}` through a shell; the "
                        "command must be a compile-time-constant string (a "
                        "module/op-local immutable), never runtime/untrusted data "
                        "— that is OS command injection (CWE-78). There is no safe "
                        "shell-parameterization in this toolchain."
                    ),
                    specAnchor="docs/reference/syntax-inventory.md#system",
                    citations=operationCitations,
                    fixCandidates=[
                        FixCandidate(
                            name="useConstantCommand",
                            shape=('storage module immutable commandText String "<fixed command>"'),
                            evidence=[span_of_line(argLine)],
                        ),
                    ],
                    confidence=Confidence.HIGH,
                    blocksCompile=False,
                    effort=Effort.LOCAL,
                    passProvenance="check_shell_command_not_constant",
                    agentHint=(
                        "never build a shell command from input/runtime values; "
                        "pass a constant string to c.system (strict mode SS4603 "
                        "blocks a non-constant command), or avoid shelling out"
                    ),
                ))
                break
    return diagnostics


def _secret_trust_types(facts: ExtendedFacts) -> Set[str]:
    """Type names declared `typeTrust <T> secret` in THIS file.

    NOTE: single-file only — the linter has no import resolution, so a secret
    type defined in an imported module (e.g. std `JwtSecret`) is not visible
    here. The advisory floor therefore under-reports cross-module hard-coded
    secrets; the binding `semsc --strict` wall (which flattens imports before
    parse) does catch them. This is an advisory-floor limitation, not a wall
    gap."""
    secretTypes: Set[str] = set()
    for sourceLine in facts.base.lines:
        if is_comment(sourceLine) or not sourceLine.tokens:
            continue
        if (sourceLine.verb == "typeTrust" and len(sourceLine.args) >= 2
                and sourceLine.args[1] == "secret"):
            secretTypes.add(sourceLine.args[0])
    return secretTypes


def _type_chain_is_secret(
    typeName: str,
    typeAliases: Dict[str, str],
    secretTypes: Set[str],
) -> bool:
    """True if `typeName`, or any type it aliases through, is secret-trust.
    Closes the `type AppSecret JwtSecret` alias evasion."""
    seen: Set[str] = set()
    current: Optional[str] = typeName
    while current is not None and current not in seen:
        if current in secretTypes:
            return True
        seen.add(current)
        current = typeAliases.get(current)
    return False


def _resolve_string_const_chain(
    name: str,
    constMap: Dict[str, Tuple[str, str, SourceLine]],
) -> Optional[str]:
    """Follow a const-name chain to its ultimate value (mirrors the compiler's
    `_strict_resolve_const_chain`): a secret bound to another constant that
    resolves to a non-empty literal is still hard-coded."""
    seen: Set[str] = set()
    current: Optional[str] = name
    resolvedAny = False
    for _ in range(8):
        if current is None or current in seen:
            return None
        entry = constMap.get(current)
        if entry is None:
            # Reached a leaf. It's a hard-coded literal only if we actually
            # walked at least one immutable-constant hop to get here; a value
            # name that is NOT an immutable constant (a mutable/runtime-filled
            # sentinel, an undeclared name) is not a source literal.
            return current if resolvedAny else None
        seen.add(current)
        current = entry[1]
        resolvedAny = True
    return current


def check_hardcoded_secret(facts: ExtendedFacts) -> List[Diagnostic]:
    """SS4604 — a non-empty compile-time value bound to a secret-trust-typed
    storage is a hard-coded credential (CWE-798). Empty sentinels filled at
    runtime are the good pattern and are not flagged. Resolves const-name chains
    (parity with the compiler). Advisory here; `semsc --strict` blocks."""
    secretTypes = _secret_trust_types(facts)
    if not secretTypes:
        return []
    moduleConstants = _module_immutable_constants(facts)
    diagnostics: List[Diagnostic] = []
    for sourceLine in facts.base.lines:
        if is_comment(sourceLine) or not sourceLine.tokens:
            continue
        args = sourceLine.args
        # storage/sharedState SCOPE MUT NAME TYPE VALUE ; memory OP MUT NAME TYPE VALUE
        if sourceLine.verb not in {"storage", "sharedState", "memory"}:
            continue
        if len(args) < 5 or args[1] not in {"mutable", "immutable"}:
            continue
        declaredName, declaredType = args[2], args[3]
        if not _type_chain_is_secret(declaredType, facts.base.type_aliases, secretTypes):
            continue
        # A non-empty quoted literal is a hard-coded secret directly; a NAME value
        # is resolved through the constant chain (e.g. `secret <- realSecret <-
        # "literal"`). An empty "" sentinel or a name that resolves to nothing/
        # empty (a runtime-filled slot) is the good pattern and is not flagged.
        valueToken = sourceLine.tokens[-1]
        if valueToken.quoted:
            effectiveValue = valueToken.text
        else:
            effectiveValue = _resolve_string_const_chain(args[4], moduleConstants)
        if not effectiveValue:
            continue
        diagnostics.append(Diagnostic(
            tier=Tier.T3_REFINEMENT,
            code="SS4604",
            kind="security.hardCodedSecret",
            severity=Severity.WARNING,
            subjectName=declaredName,
            subjectKind="storage",
            gapEdge="runtimeSecretSource",
            intentSlogan="hard-coded secret literal",
            primary=span_of_line(sourceLine, "secretLiteral"),
            invariantRule=(
                f"`{declaredName}` is `{declaredType}` (typeTrust secret) but is "
                "bound to a source string literal — a hard-coded credential "
                "(CWE-798). Load it from the environment (`c.getenv`) or secure "
                "config at runtime; embed only an empty `\"\"` sentinel in source."
            ),
            specAnchor="docs/reference/syntax-inventory.md#typeTrust",
            fixCandidates=[
                FixCandidate(
                    name="useEmptySentinelFilledFromEnv",
                    shape=f'storage module mutable {declaredName} {declaredType} ""',
                    evidence=[span_of_line(sourceLine)],
                ),
            ],
            confidence=Confidence.HIGH,
            blocksCompile=False,
            effort=Effort.LOCAL,
            passProvenance="check_hardcoded_secret",
            agentHint=(
                "never put a real secret in source; read it from the environment "
                "into this secret-typed slot at runtime (strict mode SS4604 blocks "
                "a hard-coded secret)"
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
            specAnchor=f"docs/reference/syntax-inventory.md#{verb}",
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
# SS36xx — JSON CRUD discipline
# ==========================================================================

def check_unguarded_json_access(facts: ExtendedFacts) -> List[Diagnostic]:
    """SS3620 — a JsonCursor returned from a fallible navigator must not be
    consumed before the call's error branch is installed."""
    diagnostics: List[Diagnostic] = []
    for operation in facts.base.operations.values():
        operationCitations = narrative_citations_for_operation(facts, operation.name)
        operationCalls = collect_operation_calls(operation)
        for callFact in operationCalls.values():
            if callFact.target not in JSON_FALLIBLE_CURSOR_NAVIGATOR_TARGETS:
                continue
            runLineNumber = min(
                (runLine.number for runLine in callFact.run_lines),
                default=callFact.line.number,
            )
            for bindLine in callFact.bind_ok_lines:
                if len(bindLine.args) < 3 or bindLine.args[1] != "JsonCursor":
                    continue
                cursorName = bindLine.args[0]
                firstUseLine = _first_value_use_after_line(
                    operation, cursorName, bindLine.number,
                )
                if firstUseLine is None:
                    continue
                guardedBeforeUse = any(
                    runLineNumber < branchLine.number < firstUseLine.number
                    for branchLine in callFact.branch_error_lines
                )
                if guardedBeforeUse:
                    continue
                diagnostics.append(Diagnostic(
                    tier=Tier.T3_REFINEMENT,
                    code="SS3620",
                    kind="json.unguardedJsonAccess",
                    severity=Severity.WARNING,
                    subjectName=cursorName,
                    subjectKind="JsonCursor",
                    gapEdge="branchIfErrorBeforeCursorUse",
                    intentSlogan="JsonCursor used before error guard",
                    primary=span_of_line(firstUseLine, "firstCursorUse"),
                    related=[
                        span_of_line(callFact.line, "jsonNavigatorCall"),
                        span_of_line(bindLine, "cursorBindOk"),
                        span_of_line(operation.line, "enclosingOperation"),
                    ],
                    invariantRule=(
                        f"`{callFact.target}` returns `Result JsonCursor "
                        "JsonAccessError`; install `branchIfError` after `run` "
                        "and before the first use of the cursor"
                    ),
                    specAnchor="docs/reference/syntax-inventory.md#json-cursor-navigation",
                    citations=operationCitations,
                    fixCandidates=[
                        FixCandidate(
                            name="guardJsonNavigatorBeforeCursorUse",
                            shape=(
                                f"bindError {callFact.name}Error JsonAccessError {callFact.name}\n"
                                f"branchIfError {callFact.name} <jsonAccessFailedLabel>\n"
                                f"# use `{cursorName}` only after the branch"
                            ),
                            evidence=[
                                span_of_line(callFact.line),
                                span_of_line(firstUseLine),
                            ],
                        ),
                    ],
                    confidence=Confidence.HIGH,
                    effort=Effort.LOCAL,
                    passProvenance="check_unguarded_json_access",
                    agentHint=(
                        "json.documentRoot is total, but objectFieldAt, "
                        "arrayElementAt, cursorParent, cursorAtPath, and "
                        "cursorObjectFieldValueAt can fail before producing a "
                        "usable cursor"
                    ),
                ))
    return diagnostics


def check_stale_json_cursor(facts: ExtendedFacts) -> List[Diagnostic]:
    """SS3621 — cursors bound before a structural mutation should be
    re-found before they are read again."""
    diagnostics: List[Diagnostic] = []
    for operation in facts.base.operations.values():
        operationCitations = narrative_citations_for_operation(facts, operation.name)
        operationCalls = collect_operation_calls(operation)
        cursorDocuments: Dict[str, Tuple[str, SourceLine]] = {}
        staleCursors: Dict[str, Tuple[CallFact, SourceLine, SourceLine]] = {}

        for sourceLine in operation.lines:
            if is_comment(sourceLine) or not sourceLine.tokens:
                continue

            if (sourceLine.verb in {"bind", "bindOk"} and len(sourceLine.args) >= 3
                    and sourceLine.args[1] == "JsonCursor"):
                cursorName = sourceLine.args[0]
                sourceCall = operationCalls.get(sourceLine.args[2])
                documentName = call_arg_value(sourceCall, "document") if sourceCall else None
                if documentName:
                    cursorDocuments[cursorName] = (documentName, sourceLine)
                    staleCursors.pop(cursorName, None)
                continue

            for cursorName, (mutatorCall, mutatorRunLine, cursorBindLine) in list(staleCursors.items()):
                if not _line_uses_value(sourceLine, cursorName):
                    continue
                diagnostics.append(Diagnostic(
                    tier=Tier.T3_REFINEMENT,
                    code="SS3621",
                    kind="json.staleJsonCursor",
                    severity=Severity.WARNING,
                    subjectName=cursorName,
                    subjectKind="JsonCursor",
                    gapEdge="freshCursorAfterStructuralMutation",
                    intentSlogan="stale JsonCursor read",
                    primary=span_of_line(sourceLine, "staleCursorUse"),
                    related=[
                        span_of_line(mutatorRunLine, "structuralMutatorRun"),
                        span_of_line(mutatorCall.line, "structuralMutatorCall"),
                        span_of_line(cursorBindLine, "cursorBinding"),
                        span_of_line(operation.line, "enclosingOperation"),
                    ],
                    invariantRule=(
                        f"`{cursorName}` was bound before structural mutator "
                        f"`{mutatorCall.target}` ran on the same JsonDocument; "
                        "reacquire a cursor before reading it again"
                    ),
                    specAnchor="docs/reference/syntax-inventory.md#json-cursor-lifetime",
                    citations=operationCitations,
                    fixCandidates=[
                        FixCandidate(
                            name="refreshJsonCursorAfterMutation",
                            shape=(
                                "# reacquire the cursor after the mutator\n"
                                "call refreshJsonCursorCall json.cursorAtPath\n"
                                "arg refreshJsonCursorCall document <document>\n"
                                "arg refreshJsonCursorCall path <JsonPath>\n"
                                "run refreshJsonCursorCall\n"
                                f"bindOk {cursorName} JsonCursor refreshJsonCursorCall"
                            ),
                            evidence=[
                                span_of_line(mutatorRunLine),
                                span_of_line(sourceLine),
                            ],
                        ),
                    ],
                    confidence=Confidence.MEDIUM,
                    effort=Effort.LOCAL,
                    passProvenance="check_stale_json_cursor",
                    agentHint=(
                        "structural mutations can invalidate prior cursor "
                        "indices; use objectFieldAt, arrayElementAt, or "
                        "cursorAtPath to reacquire the position"
                    ),
                ))
                staleCursors.pop(cursorName, None)

            if sourceLine.verb != "run" or not sourceLine.args:
                continue
            mutatorCall = operationCalls.get(sourceLine.args[0])
            if mutatorCall is None:
                continue
            if mutatorCall.target not in JSON_STRUCTURAL_CURSOR_MUTATOR_TARGETS:
                continue
            documentName = call_arg_value(mutatorCall, "document")
            if not documentName:
                continue
            for cursorName, (cursorDocumentName, cursorBindLine) in cursorDocuments.items():
                if cursorDocumentName != documentName:
                    continue
                if cursorBindLine.number >= sourceLine.number:
                    continue
                staleCursors[cursorName] = (mutatorCall, sourceLine, cursorBindLine)
    return diagnostics


def check_malformed_json_path(facts: ExtendedFacts) -> List[Diagnostic]:
    """SS3622 — statically-declared JsonPath literals must follow the
    `.field` / `[index]` grammar before runtime navigation sees them."""
    diagnostics: List[Diagnostic] = []
    for sourceLine in facts.base.lines:
        assignment = _literal_assignment(sourceLine)
        if assignment is None:
            continue
        pathName, typeName, pathText = assignment
        if typeName != "JsonPath":
            continue
        malformedReason = _json_path_malformed_reason(pathText)
        if malformedReason is None:
            continue
        diagnostics.append(Diagnostic(
            tier=Tier.T1_SPEC,
            code="SS3622",
            kind="json.malformedJsonPath",
            severity=Severity.ERROR,
            subjectName=pathName,
            subjectKind="JsonPath",
            gapEdge=malformedReason,
            intentSlogan="malformed JsonPath literal",
            primary=span_of_line(sourceLine, "jsonPathLiteral"),
            invariantRule=(
                "JsonPath literals accept only `.fieldName` object steps and "
                "`[index]` array steps with non-negative decimal indices"
            ),
            specAnchor="docs/reference/syntax-inventory.md#JsonPath",
            fixCandidates=[
                FixCandidate(
                    name="rewriteJsonPathLiteral",
                    shape='storage local immutable <name> JsonPath ".field[0].child"',
                    evidence=[span_of_line(sourceLine)],
                ),
            ],
            confidence=Confidence.HIGH,
            blocksCompile=True,
            effort=Effort.TRIVIAL,
            passProvenance="check_malformed_json_path",
            agentHint=(
                "this is syntactic only: a valid path may still miss at runtime, "
                "but malformed bracket/index/segment shapes should stop earlier"
            ),
        ))
    return diagnostics


def check_unescaped_json_string_interpolation(facts: ExtendedFacts) -> List[Diagnostic]:
    """SS3623 — c.snprintf `%s` inside JSON string content bypasses JSON
    escaping and should move to the native JSON surface."""
    diagnostics: List[Diagnostic] = []
    for operation in facts.base.operations.values():
        operationCitations = narrative_citations_for_operation(facts, operation.name)
        operationCalls = collect_operation_calls(operation)
        literalValues = _operation_literal_assignments(facts, operation)
        for callFact in operationCalls.values():
            if callFact.target != "c.snprintf":
                continue
            for argLine in callFact.arg_lines:
                if len(argLine.args) < 3 or argLine.args[1] != "format":
                    continue
                formatName = argLine.args[2]
                literal = literalValues.get(formatName)
                if literal is None:
                    continue
                _typeName, formatText, literalLine = literal
                if not _format_contains_json_string_percent_s(formatText):
                    continue
                diagnostics.append(Diagnostic(
                    tier=Tier.T3_REFINEMENT,
                    code="SS3623",
                    kind="json.unescapedJsonStringInterpolation",
                    severity=Severity.WARNING,
                    subjectName=callFact.name,
                    subjectKind="call",
                    gapEdge="jsonStringEscape",
                    intentSlogan="snprintf interpolates JSON string",
                    primary=span_of_line(argLine, "snprintfFormatArgument"),
                    related=[
                        span_of_line(literalLine, "formatLiteral"),
                        span_of_line(callFact.line, "snprintfCall"),
                        span_of_line(operation.line, "enclosingOperation"),
                    ],
                    invariantRule=(
                        f"`{formatName}` contains `%s` inside JSON string "
                        "content; interpolated bytes are not JSON-escaped"
                    ),
                    specAnchor="docs/reference/syntax-inventory.md#json.stringify",
                    citations=operationCitations,
                    fixCandidates=[
                        FixCandidate(
                            name="useJsonStringifyOrDocumentApi",
                            shape=(
                                "call stringifyCall json.stringify.<TypeName>\n"
                                "# or build a JsonDocument and call json.serializeDocument"
                            ),
                            evidence=[
                                span_of_line(literalLine),
                                span_of_line(argLine),
                            ],
                        ),
                    ],
                    confidence=Confidence.HIGH,
                    effort=Effort.LOCAL,
                    passProvenance="check_unescaped_json_string_interpolation",
                    agentHint=(
                        "raw `%s` in a JSON string can break syntax or inject "
                        "fields; use json.stringify.<TypeName> or "
                        "json.serializeDocument"
                    ),
                ))
    return diagnostics


def _deprecated_json_call_diagnostic(
    facts: ExtendedFacts,
    operation: OperationFact,
    sourceLine: SourceLine,
    targetName: str,
    subjectName: str,
    subjectKind: str,
    code: str,
    kind: str,
    intentSlogan: str,
    replacementShape: str,
    agentHint: str,
) -> Diagnostic:
    return Diagnostic(
        tier=Tier.T1_SPEC,
        code=code,
        kind=kind,
        severity=Severity.ERROR,
        subjectName=subjectName,
        subjectKind=subjectKind,
        gapEdge="replacementJsonCrudApi",
        intentSlogan=intentSlogan,
        primary=span_of_line(sourceLine, "deprecatedJsonCall"),
        related=[span_of_line(operation.line, "enclosingOperation")],
        invariantRule=(
            f"`{targetName}` is the legacy JSON surface; new source should use "
            "json.stringify.<TypeName>, json.parse.<TypeName>, or the "
            "JsonDocument cursor/mutator API"
        ),
        specAnchor="docs/reference/syntax-inventory.md#json-crud-api",
        citations=narrative_citations_for_operation(facts, operation.name),
        fixCandidates=[
            FixCandidate(
                name="migrateToJsonCrudApi",
                shape=replacementShape,
                evidence=[span_of_line(sourceLine)],
            ),
        ],
        confidence=Confidence.HIGH,
        blocksCompile=True,
        effort=Effort.LOCAL,
        passProvenance="check_deprecated_json_calls",
        agentHint=agentHint,
    )


def check_deprecated_json_builder_calls(facts: ExtendedFacts) -> List[Diagnostic]:
    """SS3624 — legacy JsonBuilder calls should not remain in user source."""
    diagnostics: List[Diagnostic] = []
    for operation in facts.base.operations.values():
        for sourceLine in operation.lines:
            if is_comment(sourceLine) or not sourceLine.tokens or len(sourceLine.args) < 2:
                continue
            if sourceLine.verb not in {"call", "defer"}:
                continue
            targetName = sourceLine.args[1]
            if targetName not in DEPRECATED_JSON_BUILDER_TARGETS:
                continue
            diagnostics.append(_deprecated_json_call_diagnostic(
                facts=facts,
                operation=operation,
                sourceLine=sourceLine,
                targetName=targetName,
                subjectName=sourceLine.args[0],
                subjectKind=sourceLine.verb,
                code="SS3624",
                kind="json.deprecatedJsonBuilderCall",
                intentSlogan="legacy JsonBuilder call",
                replacementShape=(
                    "call stringifyCall json.stringify.<TypeName>\n"
                    "# or: json.createEmptyDocument + setObjectField*/appendArrayElement*"
                ),
                agentHint=(
                    "builder calls expose manual JSON assembly; migrate to typed "
                    "stringify or the document mutator API before removing the "
                    "legacy runtime surface"
                ),
            ))
    return diagnostics


def check_deprecated_json_finder_calls(facts: ExtendedFacts) -> List[Diagnostic]:
    """SS3625 — legacy one-shot JSON finder calls should move to cursors."""
    diagnostics: List[Diagnostic] = []
    for operation in facts.base.operations.values():
        for callFact in collect_operation_calls(operation).values():
            if callFact.target not in DEPRECATED_JSON_FINDER_TARGETS:
                continue
            diagnostics.append(_deprecated_json_call_diagnostic(
                facts=facts,
                operation=operation,
                sourceLine=callFact.line,
                targetName=callFact.target,
                subjectName=callFact.name,
                subjectKind="call",
                code="SS3625",
                kind="json.deprecatedJsonFinderCall",
                intentSlogan="legacy JSON finder call",
                replacementShape=(
                    "call createDocumentCall json.createDocument\n"
                    "call cursorAtPathCall json.cursorAtPath\n"
                    "call readCursorCall json.cursor<Type>"
                ),
                agentHint=(
                    "finder calls hide traversal and type errors behind one "
                    "operation; create a document, navigate to a cursor, then "
                    "read through a typed cursor accessor"
                ),
            ))
    return diagnostics


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"non-standard JSON constant `{value}`")


def _resolve_type_alias_for_json_body(facts: ExtendedFacts, type_name: str) -> str:
    name = type_name
    seen: Set[str] = set()
    aliases: Dict[str, str] = dict(BUILTIN_TYPE_ALIASES)
    aliases.update(facts.base.type_aliases)
    while name in aliases and name not in seen:
        seen.add(name)
        name = aliases[name]
    return name


def _is_json_text_type_for_json_body(facts: ExtendedFacts, type_name: str) -> bool:
    name = type_name
    seen: Set[str] = set()
    aliases: Dict[str, str] = dict(BUILTIN_TYPE_ALIASES)
    aliases.update(facts.base.type_aliases)
    while True:
        if name in {"JsonText", "String"}:
            return True
        if name in seen or name not in aliases:
            return False
        seen.add(name)
        name = aliases[name]


def _record_type_for_json_body_lint(facts: ExtendedFacts, type_name: str) -> Optional[str]:
    name = type_name
    seen: Set[str] = set()
    aliases: Dict[str, str] = dict(BUILTIN_TYPE_ALIASES)
    aliases.update(facts.base.type_aliases)
    while True:
        if name in facts.base.records:
            return name
        if name in seen or name not in aliases:
            return None
        seen.add(name)
        name = aliases[name]


def _json_body_lint_key(facts: ExtendedFacts, record_name: str, field_name: str) -> str:
    return facts.base.record_json_names.get((record_name, field_name), field_name)


def _json_body_lint_kind(value) -> str:
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


def _json_body_lint_default(
    facts: ExtendedFacts,
    field_type: str,
    policy: Optional[str],
) -> bool:
    if not policy:
        return False
    resolved = _resolve_type_alias_for_json_body(facts, field_type)
    if policy == "empty":
        return resolved in {"String", "JsonText"}
    if policy == "null":
        return resolved in {"String", "JsonText"}
    if policy == "false":
        return resolved == "Bool"
    if policy == "zero":
        return resolved not in {"String", "JsonText", "Bool"}
    return False


def _validate_json_body_record_lint(
    facts: ExtendedFacts,
    json_body: JsonBodyFact,
    record_name: str,
    value,
    path: str = "",
) -> Optional[Tuple[str, str]]:
    if not isinstance(value, dict):
        return (
            "jsonBodyWrongType",
            f"`{path or record_name}` expected object for record `{record_name}`, "
            f"got {_json_body_lint_kind(value)}",
        )
    fields = facts.base.records.get(record_name, [])
    expected_keys = {
        _json_body_lint_key(facts, record_name, field_name): (field_name, field_type)
        for field_name, field_type in fields
    }
    extension_keys = {"platforms"} if record_name == "BuildTarget" else set()
    unknown = sorted(set(value.keys()) - set(expected_keys.keys()) - extension_keys)
    if unknown:
        return (
            "jsonBodyUnknownField",
            f"`{path or record_name}` contains unknown JSON key `{unknown[0]}`",
        )
    for field_name, field_type in fields:
        json_key = _json_body_lint_key(facts, record_name, field_name)
        field_path = f"{path}.{field_name}" if path else field_name
        policy = facts.base.record_json_omit_when.get((record_name, field_name))
        if json_key not in value:
            if _json_body_lint_default(facts, field_type, policy):
                continue
            return (
                "jsonBodyMissingRequired",
                f"`{field_path}` is required for record `{record_name}`",
            )
        field_value = value[json_key]
        nested_record = _record_type_for_json_body_lint(facts, field_type)
        if nested_record is not None:
            nested = _validate_json_body_record_lint(
                facts, json_body, nested_record, field_value, field_path)
            if nested is not None:
                return nested
            continue
        resolved = _resolve_type_alias_for_json_body(facts, field_type)
        if field_value is None and policy == "null":
            continue
        if resolved in {"String", "JsonText"}:
            if not isinstance(field_value, str):
                return (
                    "jsonBodyWrongType",
                    f"`{field_path}` expected string, got {_json_body_lint_kind(field_value)}",
                )
            continue
        if resolved == "Bool":
            if not isinstance(field_value, bool):
                return (
                    "jsonBodyWrongType",
                    f"`{field_path}` expected boolean, got {_json_body_lint_kind(field_value)}",
                )
            continue
        if resolved in {"Float64", "Float64", "Float64", "Float64", "Float32", "Float32", "Float32", "Float32", "Float16"}:
            if isinstance(field_value, bool) or not isinstance(field_value, (int, float)):
                return (
                    "jsonBodyWrongType",
                    f"`{field_path}` expected number, got {_json_body_lint_kind(field_value)}",
                )
            continue
        if isinstance(field_value, bool) or not isinstance(field_value, int):
            return (
                "jsonBodyWrongType",
                f"`{field_path}` expected integer, got {_json_body_lint_kind(field_value)}",
            )
    return None


def _find_json_body_storage_line(
    facts: ExtendedFacts,
    json_body: JsonBodyFact,
) -> Optional[SourceLine]:
    for sourceLine in reversed(facts.base.lines):
        if sourceLine.number >= json_body.line.number:
            continue
        if sourceLine.verb != "storage" or len(sourceLine.args) < 4:
            continue
        if sourceLine.args[2] == json_body.name:
            return sourceLine
    return None


def _json_body_diagnostic(
    json_body: JsonBodyFact,
    kind: str,
    slogan: str,
    rule: str,
    related: Optional[List[Span]] = None,
) -> Diagnostic:
    return Diagnostic(
        tier=Tier.T0_PARSE,
        code="SS3626",
        kind=f"json.{kind}",
        severity=Severity.ERROR,
        subjectName=json_body.name,
        subjectKind="jsonBody",
        gapEdge=kind,
        intentSlogan=slogan,
        primary=span_of_line(json_body.line, "jsonBodyDeclaration"),
        related=related or [],
        invariantRule=rule,
        specAnchor="docs/reference/syntax-inventory.md#jsonBody",
        fixCandidates=[
            FixCandidate(
                name="repairJsonBodyLiteral",
                shape=(
                    f"storage module immutable {json_body.name or '<name>'} "
                    "JsonText\n"
                    f"jsonBody {json_body.name or '<name>'}\n"
                    "  {\"ok\":true}"
                ),
            ),
        ],
        confidence=Confidence.HIGH,
        blocksCompile=True,
        effort=Effort.LOCAL,
        passProvenance="check_json_body_literals",
        agentHint=(
            "jsonBody is indentation-sensitive; keep the JSON island indented "
            "and bind it to a preceding immutable JsonText storage row"
        ),
    )


def check_json_body_literals(facts: ExtendedFacts) -> List[Diagnostic]:
    """SS3626: statically validate jsonBody islands the same way semsc does."""
    diagnostics: List[Diagnostic] = []
    seen_targets: Dict[str, JsonBodyFact] = {}

    for json_body in facts.base.json_bodies:
        if not json_body.name:
            diagnostics.append(_json_body_diagnostic(
                json_body,
                "jsonBodyMissingName",
                "jsonBody missing name",
                "`jsonBody` requires exactly one storage target name",
            ))
            continue

        prior = seen_targets.get(json_body.name)
        if prior is not None:
            diagnostics.append(_json_body_diagnostic(
                json_body,
                "duplicateJsonBody",
                "duplicate jsonBody",
                "a storage declaration may be bound by at most one jsonBody island",
                [span_of_line(prior.line, "previousJsonBody")],
            ))
            continue
        seen_targets[json_body.name] = json_body

        storage_line = _find_json_body_storage_line(facts, json_body)
        if storage_line is None:
            diagnostics.append(_json_body_diagnostic(
                json_body,
                "orphanJsonBody",
                "jsonBody missing storage",
                "`jsonBody NAME` requires a preceding `storage local|module immutable NAME TYPE` row",
            ))
            continue

        storage_args = storage_line.args
        scope, mutability = storage_args[0], storage_args[1]
        storage_type = storage_args[3]
        related = [span_of_line(storage_line, "jsonBodyStorageTarget")]
        if scope not in {"local", "module"}:
            diagnostics.append(_json_body_diagnostic(
                json_body,
                "jsonBodyUnsupportedScope",
                "unsupported jsonBody scope",
                "jsonBody can only bind local or module storage",
                related,
            ))
            continue
        if mutability != "immutable":
            diagnostics.append(_json_body_diagnostic(
                json_body,
                "jsonBodyMutableTarget",
                "jsonBody target mutable",
                "jsonBody can only bind immutable storage",
                related,
            ))
            continue
        if len(storage_args) > 4:
            diagnostics.append(_json_body_diagnostic(
                json_body,
                "jsonBodyTargetAlreadyValued",
                "jsonBody target valued",
                "jsonBody target storage must not already have an inline value",
                related,
            ))
            continue

        if not json_body.body_lines or not any(text.strip() for text, _ in json_body.body_lines):
            diagnostics.append(_json_body_diagnostic(
                json_body,
                "emptyJsonBody",
                "empty jsonBody",
                "jsonBody requires at least one indented JSON line",
                related,
            ))
            continue

        body_text = "\n".join(text for text, _ in json_body.body_lines)
        parsed_json = None
        try:
            parsed_json = json.loads(body_text, parse_constant=_reject_json_constant)
        except json.JSONDecodeError as exc:
            diagnostics.append(_json_body_diagnostic(
                json_body,
                "invalidJsonBody",
                "invalid JSON body",
                (
                    "jsonBody islands must be strict RFC 8259 JSON; "
                    f"invalid token at island line {exc.lineno} column {exc.colno}: {exc.msg}"
                ),
                related,
            ))
        except ValueError as exc:
            diagnostics.append(_json_body_diagnostic(
                json_body,
                "invalidJsonBody",
                "invalid JSON body",
                f"jsonBody islands must be strict RFC 8259 JSON: {exc}",
                related,
            ))
            continue

        if _is_json_text_type_for_json_body(facts, storage_type):
            continue

        record_type = _record_type_for_json_body_lint(facts, storage_type)
        if record_type is None:
            diagnostics.append(_json_body_diagnostic(
                json_body,
                "jsonBodyUnsupportedType",
                "unsupported jsonBody type",
                "jsonBody storage must be JsonText or a declared record type",
                related,
            ))
            continue
        record_problem = _validate_json_body_record_lint(
            facts, json_body, record_type, parsed_json)
        if record_problem is not None:
            kind, rule = record_problem
            diagnostics.append(_json_body_diagnostic(
                json_body,
                kind,
                "record jsonBody mismatch",
                rule,
                related,
            ))

    return diagnostics


def _is_sql_text_type_for_sql_body(facts: ExtendedFacts, type_name: str) -> bool:
    name = type_name
    seen: Set[str] = set()
    aliases: Dict[str, str] = dict(BUILTIN_TYPE_ALIASES)
    aliases.update(facts.base.type_aliases)
    while True:
        if name == "SqlText":
            return True
        if name in seen or name not in aliases:
            return False
        seen.add(name)
        name = aliases[name]


def _find_sql_body_storage_line(
    facts: ExtendedFacts,
    sql_body: SqlBodyFact,
) -> Optional[SourceLine]:
    for sourceLine in reversed(facts.base.lines):
        if sourceLine.number >= sql_body.line.number:
            continue
        if sourceLine.verb != "storage" or len(sourceLine.args) < 4:
            continue
        if sourceLine.args[2] == sql_body.name:
            return sourceLine
    return None


def _sql_body_text(sql_body: SqlBodyFact) -> str:
    raw_lines = [text for text, _line in sql_body.body_lines]
    while raw_lines and not raw_lines[0].strip():
        raw_lines.pop(0)
    while raw_lines and not raw_lines[-1].strip():
        raw_lines.pop()
    return "\n".join(raw_lines).rstrip()


def _sql_first_verb_lint(sql_text: str) -> Optional[str]:
    index = 0
    while index < len(sql_text):
        if sql_text[index].isspace():
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
        if sql_text[index].isalpha():
            start = index
            while index < len(sql_text) and (sql_text[index].isalpha() or sql_text[index] == "_"):
                index += 1
            return sql_text[start:index].upper()
        return None
    return None


def _strip_sql_leading_comments_lint(sql_text: str) -> str:
    index = 0
    while index < len(sql_text):
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


def _scan_sql_text_lint(sql_text: str) -> Tuple[int, int, Optional[str]]:
    placeholder_count = 0
    statement_count = 0
    has_statement_content = False
    index = 0
    while index < len(sql_text):
        ch = sql_text[index]
        next_ch = sql_text[index + 1] if index + 1 < len(sql_text) else ""
        if ch.isspace():
            index += 1
            continue
        if ch == "-" and next_ch == "-":
            index += 2
            while index < len(sql_text) and sql_text[index] != "\n":
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
            while index < len(sql_text) and sql_text[index].isdigit():
                index += 1
            continue
        if ch in {"'", '"', "`"}:
            quote = ch
            has_statement_content = True
            index += 1
            while index < len(sql_text):
                if sql_text[index] == quote:
                    if quote in {"'", '"'} and index + 1 < len(sql_text) and sql_text[index + 1] == quote:
                        index += 2
                        continue
                    index += 1
                    break
                index += 1
            else:
                return placeholder_count, statement_count, "unterminated SQL quoted text"
            continue
        if ch == "[":
            has_statement_content = True
            index += 1
            while index < len(sql_text) and sql_text[index] != "]":
                index += 1
            if index >= len(sql_text):
                return placeholder_count, statement_count, "unterminated SQL bracket identifier"
            index += 1
            continue
        has_statement_content = True
        index += 1
    if has_statement_content:
        statement_count += 1
    return placeholder_count, statement_count, None


SQL_STATEMENT_START_VERBS: frozenset = frozenset({
    "ALTER", "BEGIN", "COMMIT", "CREATE", "DELETE", "DROP", "INSERT",
    "PRAGMA", "REPLACE", "ROLLBACK", "SELECT", "UPDATE", "WITH",
})

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

_SQL_WRITE_STATEMENT_VERBS: frozenset = frozenset({
    "DELETE",
    "INSERT",
    "REPLACE",
    "UPDATE",
})


def _normalize_sql_expression_lint(expression: str) -> str:
    return re.sub(r"\s+", " ", expression.strip()).lower()


def _redundant_sql_cases_lint(sql_text: str) -> List[Tuple[str, str]]:
    redundant_cases: List[Tuple[str, str]] = []
    for match in _SQL_REDUNDANT_CASE_RE.finditer(sql_text):
        then_expr = _normalize_sql_expression_lint(match.group("then"))
        else_expr = _normalize_sql_expression_lint(match.group("else"))
        if then_expr and then_expr == else_expr:
            redundant_cases.append((match.group(0), then_expr))
    return redundant_cases


def _sql_select_is_narrow_existence_probe_lint(sql_text: str) -> bool:
    return bool(_SQL_NARROW_EXISTENCE_RE.match(
        _strip_sql_leading_comments_lint(sql_text)))


def _sql_write_table_lint(sql_text: str) -> Optional[str]:
    match = _SQL_WRITE_TABLE_RE.match(_strip_sql_leading_comments_lint(sql_text))
    if match is None:
        return None
    return match.group(1).lower()


def _sql_select_table_lint(sql_text: str) -> Optional[str]:
    match = _SQL_SELECT_TABLE_RE.match(_strip_sql_leading_comments_lint(sql_text))
    if match is None:
        return None
    return match.group(1).lower()


def _sql_has_returning_lint(sql_text: str) -> bool:
    return bool(re.search(r"(?is)\bRETURNING\b", sql_text))


def _sql_uses_last_insert_rowid_lint(sql_text: str) -> bool:
    return bool(re.search(r"(?is)\blast_insert_rowid\s*\(", sql_text))


def _local_sql_body_texts(facts: ExtendedFacts) -> Dict[str, str]:
    return {sql_body.name: _sql_body_text(sql_body)
            for sql_body in facts.base.sql_bodies}


def _sql_body_text_for_name_lint(
    local_sql_bodies: Dict[str, str],
    sql_name: str,
) -> Optional[str]:
    sql_text = local_sql_bodies.get(sql_name)
    if sql_text is not None:
        return sql_text
    if "." in sql_name:
        return local_sql_bodies.get(sql_name.rsplit(".", 1)[1])
    return None


def _sql_is_write_statement_lint(sql_text: str) -> bool:
    return _sql_first_verb_lint(sql_text) in _SQL_WRITE_STATEMENT_VERBS


def _sqlite_statement_has_column_reads(
    operation_calls: Dict[str, CallFact],
    statement_names: Set[str],
) -> bool:
    if not statement_names:
        return False
    for call_fact in operation_calls.values():
        if not call_fact.target.startswith("sqlite.column"):
            continue
        if call_arg_value(call_fact, "statement") in statement_names:
            return True
    return False


def _sqlite_statement_passed_to_helper(
    operation_calls: Dict[str, CallFact],
    statement_names: Set[str],
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
    for call_fact in operation_calls.values():
        if (call_fact.target.startswith("sqlite.column")
                or call_fact.target in ignored_targets):
            continue
        for values in call_arg_values(call_fact).values():
            if any(value in statement_names for value in values):
                return True
    return False


def _sql_body_diagnostic(
    sql_body: SqlBodyFact,
    kind: str,
    slogan: str,
    rule: str,
    related: Optional[List[Span]] = None,
) -> Diagnostic:
    return Diagnostic(
        tier=Tier.T0_PARSE,
        code="SS3627",
        kind=f"sql.{kind}",
        severity=Severity.ERROR,
        subjectName=sql_body.name,
        subjectKind="sqlBody",
        gapEdge=kind,
        intentSlogan=slogan,
        primary=span_of_line(sql_body.line, "sqlBodyDeclaration"),
        related=related or [],
        invariantRule=rule,
        specAnchor="docs/reference/syntax-inventory.md#sqlBody",
        fixCandidates=[
            FixCandidate(
                name="repairSqlBodyLiteral",
                shape=(
                    f"storage module immutable {sql_body.name or '<name>'} SqlText\n"
                    f"sql body {sql_body.name or '<name>'}\n"
                    "  SELECT 1"
                ),
            ),
        ],
        confidence=Confidence.HIGH,
        blocksCompile=True,
        effort=Effort.LOCAL,
        passProvenance="check_sql_body_literals",
        agentHint=(
            "sql body is indentation-sensitive; dynamic values must use ? "
            "placeholders plus sqlite.bind* rows, never interpolation holes"
        ),
    )


def check_sql_body_literals(facts: ExtendedFacts) -> List[Diagnostic]:
    """SS3627: statically validate sql body islands the same way semsc does."""
    diagnostics: List[Diagnostic] = []
    seen_targets: Dict[str, SqlBodyFact] = {}

    for sql_body in facts.base.sql_bodies:
        if not sql_body.name:
            diagnostics.append(_sql_body_diagnostic(
                sql_body,
                "sqlBodyMissingName",
                "sql body missing name",
                "`sql body` requires exactly one storage target name",
            ))
            continue

        prior = seen_targets.get(sql_body.name)
        if prior is not None:
            diagnostics.append(_sql_body_diagnostic(
                sql_body,
                "duplicateSqlBody",
                "duplicate sql body",
                "a storage declaration may be bound by at most one sql body island",
                [span_of_line(prior.line, "previousSqlBody")],
            ))
            continue
        seen_targets[sql_body.name] = sql_body

        storage_line = _find_sql_body_storage_line(facts, sql_body)
        if storage_line is None:
            diagnostics.append(_sql_body_diagnostic(
                sql_body,
                "orphanSqlBody",
                "sql body missing storage",
                "`sql body NAME` requires a preceding `storage module immutable NAME SqlText` row",
            ))
            continue

        storage_args = storage_line.args
        scope, mutability = storage_args[0], storage_args[1]
        storage_type = storage_args[3]
        related = [span_of_line(storage_line, "sqlBodyStorageTarget")]
        if scope != "module":
            diagnostics.append(_sql_body_diagnostic(
                sql_body,
                "sqlBodyUnsupportedScope",
                "unsupported sql body scope",
                "sql body can only bind module-scope storage",
                related,
            ))
            continue
        if mutability != "immutable":
            diagnostics.append(_sql_body_diagnostic(
                sql_body,
                "sqlBodyMutableTarget",
                "sql body target mutable",
                "sql body can only bind immutable storage",
                related,
            ))
            continue
        if len(storage_args) > 4:
            diagnostics.append(_sql_body_diagnostic(
                sql_body,
                "sqlBodyTargetAlreadyValued",
                "sql body target valued",
                "sql body target storage must not already have an inline value",
                related,
            ))
            continue
        if not _is_sql_text_type_for_sql_body(facts, storage_type):
            diagnostics.append(_sql_body_diagnostic(
                sql_body,
                "sqlBodyUnsupportedType",
                "unsupported sql body type",
                "sql body storage must be SqlText",
                related,
            ))
            continue

        sql_text = _sql_body_text(sql_body)
        if not sql_text.strip():
            diagnostics.append(_sql_body_diagnostic(
                sql_body,
                "emptySqlBody",
                "empty sql body",
                "sql body requires at least one indented SQL line",
                related,
            ))
            continue
        if "\0" in sql_text:
            diagnostics.append(_sql_body_diagnostic(
                sql_body,
                "invalidSqlBody",
                "invalid SQL body",
                "sql body must not contain NUL bytes",
                related,
            ))
            continue
        dynamic_hole = re.search(r"\{[^{}\n]*\}", sql_text)
        if dynamic_hole is not None:
            diagnostics.append(_sql_body_diagnostic(
                sql_body,
                "sqlBodyDynamicHole",
                "SQL interpolation rejected",
                "sql body does not allow interpolation holes; use ? placeholders and sqlite.bind* rows",
                related,
            ))
            continue
        if _sql_first_verb_lint(sql_text) is None:
            diagnostics.append(_sql_body_diagnostic(
                sql_body,
                "invalidSqlBody",
                "invalid SQL body",
                "sql body must start with a SQL statement verb after whitespace/comments",
                related,
            ))
            continue
        _placeholder_count, _statement_count, scan_problem = _scan_sql_text_lint(sql_text)
        if scan_problem is not None:
            diagnostics.append(_sql_body_diagnostic(
                sql_body,
                "invalidSqlBody",
                "invalid SQL body",
                f"sql body contains invalid SQL text: {scan_problem}",
                related,
            ))

    return diagnostics


def _inline_sql_literal_diagnostic(
    source_line: SourceLine,
    name: str,
    type_name: str,
    sql_text: str,
) -> Diagnostic:
    return Diagnostic(
        tier=Tier.T3_REFINEMENT,
        code="SS3628",
        kind="sql.inlineLiteral",
        severity=Severity.WARNING,
        subjectName=name,
        subjectKind="storage",
        gapEdge="sqlBody",
        intentSlogan="inline SQL literal",
        primary=span_of_line(source_line, "sqlStorageLiteral"),
        invariantRule=(
            "executable SQL should use `SqlText` plus a `sql body` island "
            "so tools can validate statement shape, placeholders, and SQL text "
            "without string escaping"
        ),
        specAnchor="docs/reference/syntax-inventory.md#sqlBody",
        fixCandidates=[
            FixCandidate(
                name="moveSqlToBodyIsland",
                shape=(
                    f"storage module immutable {name} SqlText\n"
                    f"sql body {name}\n"
                    f"  {sql_text}"
                ),
            ),
        ],
        confidence=Confidence.HIGH,
        blocksCompile=False,
        effort=Effort.LOCAL,
        passProvenance="check_inline_sql_literals",
        agentHint=(
            f"`{type_name}` inline SQL still compiles in permissive code, "
            "but strict executable code expects SqlText bound by sql body or "
            "a trusted external literalSource asset"
        ),
    )


def check_inline_sql_literals(facts: ExtendedFacts) -> List[Diagnostic]:
    """SS3628 — SQL written as an escaped string literal should migrate to
    `SqlText` plus a `sql body` island. This is a tooling/perf rule: body
    islands let the compiler and linter scan SQL once instead of treating
    it as arbitrary bytes.
    """
    diagnostics: List[Diagnostic] = []
    for source_line in facts.base.lines:
        if source_line.verb != "storage" or len(source_line.args) < 5:
            continue
        scope, mutability, name, type_name, value = source_line.args[:5]
        if mutability != "immutable":
            continue
        if type_name not in {"String", "SqlText"}:
            continue
        first_verb = _sql_first_verb_lint(value)
        if first_verb not in SQL_STATEMENT_START_VERBS:
            continue
        diagnostics.append(_inline_sql_literal_diagnostic(
            source_line, name, type_name, value))
    return diagnostics


def check_redundant_sql_case_branches(facts: ExtendedFacts) -> List[Diagnostic]:
    """SS3629 — `CASE WHEN ... THEN X ELSE X END` inside SQL is dead work.
    It burns SQLite parse/VM cycles and often means obsolete bind parameters
    stayed behind after a refactor.
    """
    diagnostics: List[Diagnostic] = []
    for sql_body in facts.base.sql_bodies:
        for body_line, line_number in sql_body.body_lines:
            if "CASE" not in body_line.upper():
                continue
            redundant_cases = _redundant_sql_cases_lint(body_line)
            if not redundant_cases:
                continue
            _case_text, expression = redundant_cases[0]
            diagnostics.append(Diagnostic(
                tier=Tier.T3_REFINEMENT,
                code="SS3629",
                kind="sql.redundantCaseBranches",
                severity=Severity.WARNING,
                subjectName=sql_body.name,
                subjectKind="sqlBody",
                gapEdge="redundantCase",
                intentSlogan="redundant SQL CASE",
                primary=Span(
                    facts.base.path,
                    line_number,
                    1,
                    "sqlBodyLine",
                ),
                related=[span_of_line(sql_body.line, "sqlBodyDeclaration")],
                invariantRule=(
                    "`CASE WHEN ... THEN X ELSE X END` must be simplified to "
                    "`X`; if both branches are the same, the condition and any "
                    "bind parameters used only by it are dead work"
                ),
                specAnchor="docs/optimization-guide.md#sql-body",
                fixCandidates=[
                    FixCandidate(
                        name="simplifyRedundantSqlCase",
                        shape=f"# replace the redundant CASE expression with `{expression}`",
                    ),
                ],
                confidence=Confidence.HIGH,
                blocksCompile=False,
                effort=Effort.LOCAL,
                passProvenance="check_redundant_sql_case_branches",
                agentHint=(
                    "After simplifying the SQL, re-check sqlite.bind* "
                    "parameter indexes; numbered placeholders often need to "
                    "be compacted."
                ),
            ))
    return diagnostics


# ==========================================================================
# SS36xx — webserver discipline
# ==========================================================================

def check_sql_last_insert_rowid_function(facts: ExtendedFacts) -> List[Diagnostic]:
    """SS3639 - SQL bodies should not depend on last_insert_rowid().

    The SQL function is connection-global mutable state. In generated handler
    code it usually means a previous INSERT produced an id that should have
    been returned directly with RETURNING and then passed as an explicit bind.
    The native sqlite.lastInsertRowId call has the same hidden connection-state
    dependency, so the rule catches both forms.
    """
    diagnostics: List[Diagnostic] = []
    for sql_body in facts.base.sql_bodies:
        sql_text = _sql_body_text(sql_body)
        if not _sql_uses_last_insert_rowid_lint(sql_text):
            continue
        body_line = next((
            line for line in sql_body.body_lines
            if re.search(r"(?i)\blast_insert_rowid\s*\(", line[0])
        ), None)
        if body_line is None:
            primary = span_of_line(sql_body.line, "sqlBodyDeclaration")
        else:
            _text, line_number = body_line
            primary = Span(facts.base.path, line_number, 1, "lastInsertRowid")
        diagnostics.append(Diagnostic(
            tier=Tier.T3_REFINEMENT,
            code="SS3639",
            kind="sql.lastInsertRowidFunction",
            severity=Severity.WARNING,
            subjectName=sql_body.name,
            subjectKind="sqlBody",
            gapEdge="connectionGlobalGeneratedId",
            intentSlogan="connection-global last_insert_rowid()",
            primary=primary,
            related=[span_of_line(sql_body.line, "sqlBodyDeclaration")],
            invariantRule=(
                "SQL bodies must not call `last_insert_rowid()` to recover "
                "generated ids from a previous statement; use `RETURNING` on "
                "the INSERT and bind the returned id explicitly into later "
                "statements"
            ),
            specAnchor="docs/optimization-guide.md#sqlite-returning",
            fixCandidates=[
                FixCandidate(
                    name="returnGeneratedId",
                    shape=(
                        "INSERT INTO table_name(...) VALUES (...) RETURNING id\n"
                        "# read sqlite.column* from the INSERT statement and bind it explicitly"
                    ),
                ),
            ],
            confidence=Confidence.HIGH,
            blocksCompile=False,
            effort=Effort.LOCAL,
            passProvenance="check_sql_last_insert_rowid_function",
            agentHint=(
                "`last_insert_rowid()` hides a dependency on connection "
                "state. Return the generated identifier from the write "
                "statement and pass it through a named SemanticScript value."
            ),
        ))
    for operation in facts.base.operations.values():
        operation_calls = collect_operation_calls(operation)
        for call_fact in operation_calls.values():
            if call_fact.target != "sqlite.lastInsertRowId":
                continue
            diagnostics.append(Diagnostic(
                tier=Tier.T3_REFINEMENT,
                code="SS3639",
                kind="sqlite.lastInsertRowIdCall",
                severity=Severity.WARNING,
                subjectName=call_fact.name,
                subjectKind="call",
                gapEdge="connectionGlobalGeneratedId",
                intentSlogan="connection-global sqlite.lastInsertRowId",
                primary=span_of_line(call_fact.line, "lastInsertRowIdCall"),
                related=[],
                invariantRule=(
                    "Code must not call `sqlite.lastInsertRowId` to recover "
                    "generated ids from a previous statement; use `RETURNING` "
                    "on the INSERT and bind the returned id explicitly into "
                    "later statements"
                ),
                specAnchor="docs/optimization-guide.md#sqlite-returning",
                fixCandidates=[
                    FixCandidate(
                        name="returnGeneratedId",
                        shape=(
                            "INSERT INTO table_name(...) VALUES (...) RETURNING id\n"
                            "# read sqlite.column* from the INSERT statement and bind it explicitly"
                        ),
                    ),
                ],
                confidence=Confidence.HIGH,
                blocksCompile=False,
                effort=Effort.LOCAL,
                passProvenance="check_sql_last_insert_rowid_function",
                agentHint=(
                    "`sqlite.lastInsertRowId` hides a dependency on connection "
                    "state. Return the generated identifier from the write "
                    "statement and pass it through a named SemanticScript value."
                ),
            ))
    return diagnostics


def check_wide_sql_existence_probe(facts: ExtendedFacts) -> List[Diagnostic]:
    """SS3631 - SQLite existence probes should select only existence.

    When a statement is prepared, stepped, and never has any column read,
    the caller is using it as a boolean row-exists probe. Selecting a full
    row in that shape burns SQLite VM work and can keep obsolete column
    dependencies alive after refactors.
    """
    diagnostics: List[Diagnostic] = []
    local_sql_bodies = _local_sql_body_texts(facts)
    for operation in facts.base.operations.values():
        operation_calls = collect_operation_calls(operation)
        for call_fact in operation_calls.values():
            if call_fact.target != "sqlite.prepareStatement":
                continue
            sql_name = call_arg_value(call_fact, "sql")
            if sql_name is None:
                continue
            sql_text = local_sql_bodies.get(sql_name)
            if sql_text is None:
                continue
            if _sql_first_verb_lint(sql_text) != "SELECT":
                continue
            if _sql_select_is_narrow_existence_probe_lint(sql_text):
                continue
            statement_names = call_success_value_names(call_fact)
            if _sqlite_statement_has_column_reads(operation_calls, statement_names):
                continue
            if _sqlite_statement_passed_to_helper(operation_calls, statement_names):
                continue
            sql_arg_line = next((
                arg_line for arg_line in call_fact.arg_lines
                if argument_parts(arg_line) is not None
                and argument_parts(arg_line)[1] == "sql"
            ), call_fact.line)
            related = [span_of_line(call_fact.line, "prepareStatement")]
            matching_body = next((
                sql_body for sql_body in facts.base.sql_bodies
                if sql_body.name == sql_name
            ), None)
            if matching_body is not None:
                related.append(span_of_line(
                    matching_body.line, "sqlBodyDeclaration"))
            diagnostics.append(Diagnostic(
                tier=Tier.T3_REFINEMENT,
                code="SS3631",
                kind="sql.wideExistenceProbe",
                severity=Severity.WARNING,
                subjectName=call_fact.name,
                subjectKind="call",
                gapEdge="unusedSqlProjection",
                intentSlogan="wide SQL existence probe",
                primary=Span(
                    facts.base.path,
                    sql_arg_line.number,
                    sql_arg_line.column,
                    "sqlArgument",
                ),
                related=related,
                invariantRule=(
                    "A prepared SELECT whose statement is only stepped and "
                    "never read with sqlite.column* must use `SELECT 1` or "
                    "`SELECT EXISTS(...)` so existence checks do not project "
                    "unused row data"
                ),
                specAnchor="docs/optimization-guide.md#sql-existence-probes",
                fixCandidates=[
                    FixCandidate(
                        name="selectOnlyExistence",
                        shape=(
                            "storage module immutable NAME SqlText\n"
                            "sql body NAME\n"
                            "  SELECT 1 FROM table_name WHERE key = ? LIMIT 1"
                        ),
                    ),
                ],
                confidence=Confidence.MEDIUM,
                blocksCompile=False,
                effort=Effort.LOCAL,
                passProvenance="check_wide_sql_existence_probe",
                agentHint=(
                    "If the handler only compares sqlite.stepStatement to "
                    "the row status, replace the SQL projection with a "
                    "narrow existence query. If a helper reads the columns, "
                    "keep the full projection and make the data flow visible."
                ),
            ))
    return diagnostics


def check_sql_write_then_read_returning_opportunity(
    facts: ExtendedFacts,
) -> List[Diagnostic]:
    """SS3632 - SQLite writes followed by scalar reads should use RETURNING.

    A write statement immediately followed by a select on the same table
    usually means the handler paid for a second prepare/bind/step cycle to
    retrieve data SQLite could have returned from the write.
    """
    diagnostics: List[Diagnostic] = []
    local_sql_bodies = _local_sql_body_texts(facts)
    for operation in facts.base.operations.values():
        operation_calls = collect_operation_calls(operation)
        prior_writes: Dict[str, Tuple[CallFact, str]] = {}
        for call_fact in sorted(
            operation_calls.values(),
            key=lambda candidate: candidate.line.number,
        ):
            if call_fact.target != "sqlite.prepareStatement":
                continue
            sql_name = call_arg_value(call_fact, "sql")
            if sql_name is None:
                continue
            sql_text = local_sql_bodies.get(sql_name)
            if sql_text is None:
                continue
            write_table = _sql_write_table_lint(sql_text)
            if write_table is not None:
                if not _sql_has_returning_lint(sql_text):
                    prior_writes.setdefault(write_table, (call_fact, sql_name))
                continue
            select_table = _sql_select_table_lint(sql_text)
            if select_table is None or select_table not in prior_writes:
                continue
            write_call, write_sql_name = prior_writes[select_table]
            sql_arg_line = next((
                arg_line for arg_line in call_fact.arg_lines
                if argument_parts(arg_line) is not None
                and argument_parts(arg_line)[1] == "sql"
            ), call_fact.line)
            diagnostics.append(Diagnostic(
                tier=Tier.T3_REFINEMENT,
                code="SS3632",
                kind="sql.writeThenReadReturningOpportunity",
                severity=Severity.WARNING,
                subjectName=call_fact.name,
                subjectKind="call",
                gapEdge="avoidableSqlRoundTrip",
                intentSlogan="write followed by read",
                primary=Span(
                    facts.base.path,
                    sql_arg_line.number,
                    sql_arg_line.column,
                    "selectSqlArgument",
                ),
                related=[
                    span_of_line(write_call.line, "writePrepareStatement"),
                    span_of_line(call_fact.line, "selectPrepareStatement"),
                ],
                invariantRule=(
                    "When SQLite code writes a row and then selects from the "
                    "same table in the same operation, prefer a write SQL "
                    "with `RETURNING` so the handler avoids an extra "
                    "prepare/bind/step/finalize round trip"
                ),
                specAnchor="docs/optimization-guide.md#sqlite-returning",
                fixCandidates=[
                    FixCandidate(
                        name="foldReadIntoWriteReturning",
                        shape=(
                            f"# add RETURNING columns to `{write_sql_name}` "
                            f"and read them from `{write_call.name}`"
                        ),
                    ),
                ],
                confidence=Confidence.MEDIUM,
                blocksCompile=False,
                effort=Effort.LOCAL,
                passProvenance="check_sql_write_then_read_returning_opportunity",
                agentHint=(
                    "Keep a separate SELECT only when the read intentionally "
                    "observes state changed by triggers or other statements; "
                    "otherwise bind sqlite.column* from the write statement's "
                    "RETURNING row."
                ),
            ))
    return diagnostics


def check_sqlite_multiple_writes_have_transaction(
    facts: ExtendedFacts,
) -> List[Diagnostic]:
    """SS3635 - Multiple SQLite writes in one operation should be atomic.

    A multi-write request path without an explicit BEGIN/COMMIT burns one
    implicit transaction per write and can leave partial state committed when a
    later step fails. The rule is intentionally local: if an operation owns two
    or more prepared write steps, it must make the transaction boundary visible.
    """
    diagnostics: List[Diagnostic] = []
    local_sql_bodies = _local_sql_body_texts(facts)
    for operation in facts.base.operations.values():
        operation_calls = collect_operation_calls(operation)
        write_steps: List[Tuple[CallFact, CallFact, str]] = []
        for prepare_call in operation_calls.values():
            if prepare_call.target != "sqlite.prepareStatement":
                continue
            sql_name = call_arg_value(prepare_call, "sql")
            if sql_name is None:
                continue
            sql_text = _sql_body_text_for_name_lint(local_sql_bodies, sql_name)
            if sql_text is None or not _sql_is_write_statement_lint(sql_text):
                continue
            statement_names = call_success_value_names(prepare_call)
            if not statement_names:
                continue
            for step_call in operation_calls.values():
                if step_call.target != "sqlite.stepStatement":
                    continue
                if call_arg_value(step_call, "statement") not in statement_names:
                    continue
                write_steps.append((prepare_call, step_call, sql_name))

        if len(write_steps) < 2:
            continue

        has_begin = False
        has_commit = False
        for call_fact in operation_calls.values():
            if call_fact.target != "sqlite.exec":
                continue
            sql_name = call_arg_value(call_fact, "sql")
            if sql_name is None:
                continue
            sql_text = _sql_body_text_for_name_lint(local_sql_bodies, sql_name)
            if sql_text is None:
                continue
            verb = _sql_first_verb_lint(sql_text)
            if verb in {"BEGIN", "SAVEPOINT"}:
                has_begin = True
            elif verb in {"COMMIT", "RELEASE"}:
                has_commit = True

        if has_begin and has_commit:
            continue

        first_prepare, first_step, first_sql_name = write_steps[0]
        _second_prepare, second_step, second_sql_name = write_steps[1]
        diagnostics.append(Diagnostic(
            tier=Tier.T3_REFINEMENT,
            code="SS3635",
            kind="sqlite.multipleWritesWithoutTransaction",
            severity=Severity.WARNING,
            subjectName=operation.name,
            subjectKind="operation",
            gapEdge="transactionBoundary",
            intentSlogan="multiple SQLite writes without transaction",
            primary=span_of_line(second_step.line, "secondWriteStep"),
            related=[
                span_of_line(first_prepare.line, "firstWritePrepare"),
                span_of_line(first_step.line, "firstWriteStep"),
            ],
            invariantRule=(
                "An operation that steps two or more prepared INSERT/UPDATE/"
                "DELETE/REPLACE statements must make a SQLite BEGIN and "
                "COMMIT visible in the same operation so the writes execute "
                "atomically and avoid per-statement implicit transactions"
            ),
            specAnchor="docs/optimization-guide.md#sqlite-transactions",
            fixCandidates=[
                FixCandidate(
                    name="wrapWritesInTransaction",
                    shape=(
                        "call beginTxCall sqlite.exec\n"
                        "argument beginTxCall sql SqlText sqlBeginTransaction\n"
                        "# write statements\n"
                        "call commitTxCall sqlite.exec\n"
                        "argument commitTxCall sql SqlText sqlCommitTransaction"
                    ),
                ),
            ],
            confidence=Confidence.HIGH,
            blocksCompile=False,
            effort=Effort.LOCAL,
            passProvenance="check_sqlite_multiple_writes_have_transaction",
            agentHint=(
                f"`{first_sql_name}` and `{second_sql_name}` are both "
                "stepped as writes. Add visible BEGIN/COMMIT rows, or split "
                "the helper so a single caller-owned transaction is explicit."
            ),
        ))
    return diagnostics


_SQLITE_RETURNING_DRAIN_TARGETS: frozenset = frozenset({
    "sqlite.finalizeStatement",
    "sqlite.resetStatement",
    "sqlite.stepStatement",
})


def check_sqlite_returning_statement_drained_before_commit(
    facts: ExtendedFacts,
) -> List[Diagnostic]:
    """SS3636 - RETURNING statements must be drained before COMMIT.

    SQLite keeps a statement active while a RETURNING row is available. If a
    handler reads columns from that row and immediately commits, COMMIT can
    fail with a busy/active-statement error. A second step, reset, or explicit
    finalize before COMMIT completes the statement and keeps the transaction
    path deterministic.
    """
    diagnostics: List[Diagnostic] = []
    local_sql_bodies = _local_sql_body_texts(facts)
    for operation in facts.base.operations.values():
        operation_calls = collect_operation_calls(operation)
        returning_statements: Dict[str, Tuple[CallFact, str]] = {}
        for prepare_call in operation_calls.values():
            if prepare_call.target != "sqlite.prepareStatement":
                continue
            sql_name = call_arg_value(prepare_call, "sql")
            if sql_name is None:
                continue
            sql_text = _sql_body_text_for_name_lint(local_sql_bodies, sql_name)
            if sql_text is None or not _sql_has_returning_lint(sql_text):
                continue
            for statement_name in call_success_value_names(prepare_call):
                returning_statements[statement_name] = (prepare_call, sql_name)
        if not returning_statements:
            continue

        commit_calls: List[CallFact] = []
        for call_fact in operation_calls.values():
            if call_fact.target != "sqlite.exec":
                continue
            sql_name = call_arg_value(call_fact, "sql")
            if sql_name is None:
                continue
            sql_text = _sql_body_text_for_name_lint(local_sql_bodies, sql_name)
            if sql_text is None:
                continue
            if _sql_first_verb_lint(sql_text) in {"COMMIT", "RELEASE"}:
                commit_calls.append(call_fact)
        if not commit_calls:
            continue

        for statement_name, (prepare_call, sql_name) in returning_statements.items():
            column_reads = sorted(
                (
                    call_fact for call_fact in operation_calls.values()
                    if call_fact.target.startswith("sqlite.column")
                    and call_arg_value(call_fact, "statement") == statement_name
                ),
                key=lambda call_fact: call_fact.line.number,
            )
            if not column_reads:
                continue
            last_read = column_reads[-1]
            for commit_call in sorted(
                commit_calls,
                key=lambda call_fact: call_fact.line.number,
            ):
                if commit_call.line.number <= last_read.line.number:
                    continue
                drained = any(
                    drain_call.target in _SQLITE_RETURNING_DRAIN_TARGETS
                    and call_arg_value(drain_call, "statement") == statement_name
                    and last_read.line.number < drain_call.line.number < commit_call.line.number
                    for drain_call in operation_calls.values()
                )
                if drained:
                    continue
                diagnostics.append(Diagnostic(
                    tier=Tier.T3_REFINEMENT,
                    code="SS3636",
                    kind="sqlite.returningStatementNotDrainedBeforeCommit",
                    severity=Severity.WARNING,
                    subjectName=commit_call.name,
                    subjectKind="call",
                    gapEdge="returningStatementDrain",
                    intentSlogan="RETURNING statement not drained",
                    primary=span_of_line(commit_call.line, "commitBeforeDrain"),
                    related=[
                        span_of_line(prepare_call.line, "returningPrepare"),
                        span_of_line(last_read.line, "lastReturningColumnRead"),
                    ],
                    invariantRule=(
                        "After reading columns from a SQLite statement whose "
                        "SQL contains RETURNING, step it once more to DONE, "
                        "reset it, or explicitly finalize it before COMMIT/"
                        "RELEASE so the transaction cannot fail on an active "
                        "RETURNING row"
                    ),
                    specAnchor="docs/optimization-guide.md#sqlite-returning",
                    fixCandidates=[
                        FixCandidate(
                            name="drainReturningStatement",
                            shape=(
                                "call drainReturningCall sqlite.stepStatement\n"
                                f"argument drainReturningCall statement SqliteStatement {statement_name}"
                            ),
                        ),
                    ],
                    confidence=Confidence.HIGH,
                    blocksCompile=False,
                    effort=Effort.LOCAL,
                    passProvenance="check_sqlite_returning_statement_drained_before_commit",
                    agentHint=(
                        f"`{sql_name}` has RETURNING and `{statement_name}` "
                        "has column reads before this commit. Add a second "
                        "sqlite.stepStatement after the column reads, or "
                        "reset/finalize the statement before committing."
                    ),
                ))
                break
    return diagnostics


PROCESS_ENVIRONMENT_READ_TARGETS: frozenset = frozenset({
    "c.getenv",
    "c.getenv_s",
    "c.getenvSafe",
})


def _storage_name_looks_like_cache(name: str) -> bool:
    lowered = name.lower()
    return "cache" in lowered or "cached" in lowered


def _operation_has_environment_cache_guard(
    operation: OperationFact,
    first_getenv_line: int,
) -> bool:
    has_cache_write = any(
        line.verb == "set"
        and len(line.args) >= 3
        and line.args[0] == "storage"
        and _storage_name_looks_like_cache(line.args[1])
        for line in operation.lines
    )
    has_pre_getenv_guard = any(
        line.number < first_getenv_line
        and line.verb == "branch"
        and len(line.args) >= 5
        and line.args[0] == "if"
        for line in operation.lines
    )
    return has_cache_write and has_pre_getenv_guard


def check_process_environment_read_cached(facts: ExtendedFacts) -> List[Diagnostic]:
    """SS3633 - process environment reads in non-entry operations should be
    cached. Environment variables are deployment configuration, not request
    payload; repeatedly calling getenv on auth/config hot paths adds runtime
    work and makes behavior depend on mutable process state.
    """
    diagnostics: List[Diagnostic] = []
    for operation in facts.base.operations.values():
        if operation.name == "main":
            continue
        operation_calls = collect_operation_calls(operation)
        getenv_calls = [
            call_fact for call_fact in operation_calls.values()
            if call_fact.target in PROCESS_ENVIRONMENT_READ_TARGETS
        ]
        if not getenv_calls:
            continue
        first_getenv = min(getenv_calls, key=lambda call: call.line.number)
        if _operation_has_environment_cache_guard(
                operation, first_getenv.line.number):
            continue
        diagnostics.append(Diagnostic(
            tier=Tier.T3_REFINEMENT,
            code="SS3633",
            kind="process.getenvUncached",
            severity=Severity.WARNING,
            subjectName=first_getenv.name,
            subjectKind="call",
            gapEdge="repeatedConfigurationLookup",
            intentSlogan="uncached environment read",
            primary=span_of_line(first_getenv.line, "getenvCall"),
            related=[],
            invariantRule=(
                "Non-entry operations that read process environment should "
                "cache the resolved value behind module storage and guard "
                "the getenv path with a cached-ready branch"
            ),
            specAnchor="docs/optimization-guide.md#process-environment-cache",
            fixCandidates=[
                FixCandidate(
                    name="cacheEnvironmentValue",
                    shape=(
                        "storage module mutable cachedConfig String \"\"\n"
                        "storage module mutable cachedConfigReady Int32 0\n"
                        "# branch to cached return before c.getenv; set both storage rows after resolution"
                    ),
                ),
            ],
            confidence=Confidence.MEDIUM,
            blocksCompile=False,
            effort=Effort.LOCAL,
            passProvenance="check_process_environment_read_cached",
            agentHint=(
                "Keep direct getenv in CLI entry operations; for server "
                "helpers, resolve once and return cached module storage."
            ),
        ))
    return diagnostics


REPEATED_REQUEST_TIME_READ_TARGETS: frozenset = frozenset({
    "http.nowMillis",
})


def _operation_has_http_boundary(operation: OperationFact) -> bool:
    input_types = set(operation_input_types(operation).values())
    return bool(input_types & {"HttpRequest", "HttpResponse"})


def check_repeated_request_time_reads(facts: ExtendedFacts) -> List[Diagnostic]:
    """SS3637 - request handlers should read wall-clock time once.

    A single command or request path that asks the runtime for wall-clock time
    more than once pays repeated native-call overhead and can persist subtly
    different timestamps for rows that belong to the same logical operation.
    """
    diagnostics: List[Diagnostic] = []
    for operation in facts.base.operations.values():
        if not _operation_has_http_boundary(operation):
            continue
        operation_calls = collect_operation_calls(operation)
        time_calls = sorted(
            (
                call_fact for call_fact in operation_calls.values()
                if call_fact.target in REPEATED_REQUEST_TIME_READ_TARGETS
            ),
            key=lambda call_fact: call_fact.line.number,
        )
        if len(time_calls) < 2:
            continue
        first_time_call = time_calls[0]
        second_time_call = time_calls[1]
        diagnostics.append(Diagnostic(
            tier=Tier.T3_REFINEMENT,
            code="SS3637",
            kind="performance.repeatedRequestTimeRead",
            severity=Severity.WARNING,
            subjectName=second_time_call.name,
            subjectKind="call",
            gapEdge="repeatedWallClockRead",
            intentSlogan="repeated request timestamp read",
            primary=span_of_line(second_time_call.line, "secondTimeRead"),
            related=[span_of_line(first_time_call.line, "firstTimeRead")],
            invariantRule=(
                "An operation should call `http.nowMillis` once, bind the "
                "timestamp, and reuse that value for all rows and envelopes "
                "created by the same logical request"
            ),
            specAnchor="docs/optimization-guide.md#request-timestamps",
            fixCandidates=[
                FixCandidate(
                    name="reuseRequestTimestamp",
                    shape=(
                        "call requestNowCall http.nowMillis\n"
                        "run requestNowCall\n"
                        "bind value requestNow Int64 requestNowCall\n"
                        "# pass requestNow to later SQL/JSON/log calls"
                    ),
                ),
            ],
            confidence=Confidence.HIGH,
            blocksCompile=False,
            effort=Effort.LOCAL,
            passProvenance="check_repeated_request_time_reads",
            agentHint=(
                f"`{first_time_call.name}` already reads the request time. "
                f"Reuse its bound value instead of calling "
                f"`{second_time_call.target}` again."
            ),
        ))
    return diagnostics


IDEMPOTENCY_SELECT_NAMES: frozenset = frozenset({
    "sqlSelectIdempotency",
})

IDEMPOTENCY_RESPONSE_JSON_COLUMN_INDEXES: frozenset = frozenset({
    "1",
    "columnIndex1",
    "runtime.columnIndex1",
})


def _sql_name_or_text_is_idempotency_select_lint(
    local_sql_bodies: Dict[str, str],
    sql_name: str,
) -> bool:
    unqualified_name = sql_name.rsplit(".", 1)[-1]
    if unqualified_name in IDEMPOTENCY_SELECT_NAMES:
        return True
    sql_text = _sql_body_text_for_name_lint(local_sql_bodies, sql_name)
    if sql_text is None:
        return False
    folded = re.sub(r"\s+", " ", sql_text).lower()
    return (
        _sql_first_verb_lint(sql_text) == "SELECT"
        and " from idempotency_keys" in folded
        and "response_json" in folded
        and "response_status" in folded
    )


def _call_uses_response_json_column_lint(call_fact: CallFact) -> bool:
    column_index = call_arg_value(call_fact, "columnIndex")
    return column_index in IDEMPOTENCY_RESPONSE_JSON_COLUMN_INDEXES


def check_idempotency_replay_uses_response_status(
    facts: ExtendedFacts,
) -> List[Diagnostic]:
    """SS3638 - idempotency replay should use persisted response_status.

    The idempotency table already stores both response_json and
    response_status. Comparing replay JSON bodies with c.strcmp to recover the
    HTTP status performs avoidable full-body scans and couples status routing
    to exact envelope text.
    """
    diagnostics: List[Diagnostic] = []
    local_sql_bodies = _local_sql_body_texts(facts)
    for operation in facts.base.operations.values():
        operation_calls = collect_operation_calls(operation)
        idempotency_statements: Dict[str, CallFact] = {}
        for prepare_call in operation_calls.values():
            if prepare_call.target != "sqlite.prepareStatement":
                continue
            sql_name = call_arg_value(prepare_call, "sql")
            if sql_name is None:
                continue
            if not _sql_name_or_text_is_idempotency_select_lint(
                local_sql_bodies, sql_name
            ):
                continue
            for statement_name in call_success_value_names(prepare_call):
                idempotency_statements[statement_name] = prepare_call
        if not idempotency_statements:
            continue

        replay_body_reads: Dict[str, Tuple[CallFact, CallFact]] = {}
        for read_call in operation_calls.values():
            if read_call.target != "sqlite.columnText":
                continue
            statement_name = call_arg_value(read_call, "statement")
            if statement_name not in idempotency_statements:
                continue
            if not _call_uses_response_json_column_lint(read_call):
                continue
            prepare_call = idempotency_statements[statement_name]
            for body_name in call_success_value_names(read_call):
                replay_body_reads[body_name] = (read_call, prepare_call)
        if not replay_body_reads:
            continue

        for compare_call in sorted(
            operation_calls.values(),
            key=lambda call_fact: call_fact.line.number,
        ):
            if compare_call.target != "c.strcmp":
                continue
            compared_names = {
                name for name in (
                    call_arg_value(compare_call, "left"),
                    call_arg_value(compare_call, "right"),
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
            diagnostics.append(Diagnostic(
                tier=Tier.T3_REFINEMENT,
                code="SS3638",
                kind="performance.idempotencyReplayBodyClassification",
                severity=Severity.WARNING,
                subjectName=compare_call.name,
                subjectKind="call",
                gapEdge="replayStatusFromBody",
                intentSlogan="idempotency replay body classified by strcmp",
                primary=span_of_line(compare_call.line, "responseBodyCompare"),
                related=[
                    span_of_line(read_call.line, "responseJsonRead"),
                    span_of_line(prepare_call.line, "idempotencySelect"),
                ],
                invariantRule=(
                    "Idempotency replay code must read and branch on the "
                    "stored `response_status` column instead of comparing "
                    "stored `response_json` bodies to classify the response"
                ),
                specAnchor="docs/optimization-guide.md#idempotency-replay-status",
                fixCandidates=[
                    FixCandidate(
                        name="usePersistedResponseStatus",
                        shape=(
                            "call readReplayStatusCall sqlite.columnInt64\n"
                            "argument readReplayStatusCall columnIndex Int32 runtime.columnIndex2\n"
                            "# branch on response_status instead of c.strcmp(response_json, ...)"
                        ),
                    ),
                ],
                confidence=Confidence.HIGH,
                blocksCompile=False,
                effort=Effort.LOCAL,
                passProvenance="check_idempotency_replay_uses_response_status",
                agentHint=(
                    f"`{replay_body_name}` comes from idempotency "
                    "response_json. The same row includes response_status; "
                    "read column 2 and branch on that scalar."
                ),
            ))
    return diagnostics


# --------------------------------------------------------------------------
# SOURCE-OF-TRUTH note for native HTTP target sets
# --------------------------------------------------------------------------
# The constants below enumerate the native HTTP surface. They are one of
# three sites that must stay in lockstep:
#
#   1. semsc.py — the dispatch block (`if target == "http.responseText":`
#      and friends). That block carries the same SOURCE-OF-TRUTH banner.
#   2. semlint.py (here) — the constants below + ALL_NATIVE_HTTP_TARGETS.
#   3. docs/reference/syntax-inventory.md — the two `http.requestMethod, …` and
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
HTTP_METHOD_WHITELIST: frozenset = SHARED_SUPPORTED_HTTP_ROUTE_METHODS

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
    "http.formField",
})

HTTP_REQUEST_READER_TARGETS: frozenset = (
    NON_NULLABLE_HTTP_REQUEST_READS | NULLABLE_HTTP_REQUEST_READS
)

# Response writers that reject a null `body` argument at runtime. Passing
# a nullable bind to any of these surfaces the adapter's null-body 500
# unless the handler has guarded the pointer first OR explicitly opted
# into the failure-path contract via a warning text marker.
HTTP_RESPONSE_BODY_WRITERS: frozenset = frozenset({
    "http.responseHtml",
    "http.responseText",
    "http.responseBytes",
    "http.responseSseEvent",
})

HTTP_RESPONSE_BODY_ARG_SLOTS: Dict[str, frozenset] = {
    "http.responseHtml": frozenset({"body"}),
    "http.responseText": frozenset({"body"}),
    "http.responseBytes": frozenset({"body"}),
    "http.responseSseEvent": frozenset({"event", "data"}),
}

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
    "http.urlDecode",
    "http.urlEncode",
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
# verb (see docs/reference/syntax-inventory.md); these substrings are still honored for one
# deprecation cycle, but their use trips SS3605 `legacyNullBodyMarker`
# pointing the agent at the verb-based replacement.
LEGACY_HTTP_NULL_GUARD_OPT_OUT_MARKERS: Tuple[str, ...] = (
    "null-body failure path",
    "null-body 500",
)


def _operation_has_runtime_binding_response_write(operationFact: OperationFact) -> bool:
    hasRuntimeBindingBody = False
    hasResponseWriteEffect = False
    for sourceLine in operationFact.lines:
        if is_comment(sourceLine) or not sourceLine.tokens:
            continue
        if (sourceLine.verb == "operationBody"
                and len(sourceLine.args) >= 2
                and sourceLine.args[0] == operationFact.name
                and sourceLine.args[1] == "runtimeBinding"):
            hasRuntimeBindingBody = True
        elif (sourceLine.verb == "effect"
                and len(sourceLine.args) >= 3
                and sourceLine.args[0] == operationFact.name
                and sourceLine.args[1] == "write"
                and sourceLine.args[2].startswith("http.response")):
            hasResponseWriteEffect = True
    return hasRuntimeBindingBody and hasResponseWriteEffect


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
    writerSlotsByTarget: Dict[str, frozenset] = dict(HTTP_RESPONSE_BODY_ARG_SLOTS)
    for operationName, declaredBodyArgName in declaredForwarderArgNameByOp.items():
        operationFact = facts.base.operations.get(operationName)
        if (operationFact is not None
                and _operation_has_runtime_binding_response_write(operationFact)):
            writers.add(operationName)
            writerSlotsByTarget[operationName] = frozenset({declaredBodyArgName})
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
                        or sourceLine.verb not in {"arg", "argument"}
                        or len(sourceLine.args) < 3):
                    continue
                forwardedValue = (
                    sourceLine.args[3]
                    if sourceLine.verb == "argument" and len(sourceLine.args) >= 4
                    else sourceLine.args[2]
                )
                target = callTargetsByCallName.get(sourceLine.args[0])
                acceptedSlots = writerSlotsByTarget.get(target, frozenset({"body"}))
                if (sourceLine.args[1] in acceptedSlots
                        and forwardedValue == declaredBodyArgName
                        and target in writers):
                    forwardsDeclaredArg = True
                    break
            if forwardsDeclaredArg:
                writers.add(operationName)
                writerSlotsByTarget[operationName] = frozenset({declaredBodyArgName})
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
    writerSlotsByTarget: Dict[str, frozenset] = dict(HTTP_RESPONSE_BODY_ARG_SLOTS)
    for sourceLine in facts.base.lines:
        if (is_comment(sourceLine) or not sourceLine.tokens
                or sourceLine.verb != "responseBodyForwarder"
                or len(sourceLine.args) < 2):
            continue
        declaredForwarderRows.append(
            (sourceLine, sourceLine.args[0], sourceLine.args[1])
        )
    honoredForwarders: Set[str] = set()
    for _sourceLine, operationName, declaredBodyArgName in declaredForwarderRows:
        operationFact = facts.base.operations.get(operationName)
        if (operationFact is not None
                and _operation_has_runtime_binding_response_write(operationFact)):
            honoredForwarders.add(operationName)
            writerSlotsByTarget[operationName] = frozenset({declaredBodyArgName})
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
                        or innerLine.verb not in {"arg", "argument"}
                        or len(innerLine.args) < 3):
                    continue
                forwardedValue = (
                    innerLine.args[3]
                    if innerLine.verb == "argument" and len(innerLine.args) >= 4
                    else innerLine.args[2]
                )
                target = callTargetsByCallName.get(innerLine.args[0])
                acceptedSlots = writerSlotsByTarget.get(target, frozenset({"body"}))
                if (innerLine.args[1] in acceptedSlots
                        and forwardedValue == declaredBodyArgName
                        and target in acceptedWriters):
                    honoredForwarders.add(operationName)
                    writerSlotsByTarget[operationName] = frozenset({declaredBodyArgName})
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
            specAnchor="docs/reference/syntax-inventory.md#responseBodyForwarder",
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


def check_response_body_forwarder_missing(facts: ExtendedFacts) -> List[Diagnostic]:
    """Any user operation that forwards one of its inputs to a response body
    writer must declare responseBodyForwarder so SS3603 follows wrappers."""
    diagnostics: List[Diagnostic] = []
    responseBodyWriters = _collect_transitive_response_body_writers(facts)
    declaredForwarders: Set[Tuple[str, str]] = set()
    declaredForwarderOps: Set[str] = set()
    for sourceLine in facts.base.lines:
        if (is_comment(sourceLine) or not sourceLine.tokens
                or sourceLine.verb != "responseBodyForwarder"
                or len(sourceLine.args) < 2):
            continue
        declaredForwarders.add((sourceLine.args[0], sourceLine.args[1]))
        declaredForwarderOps.add(sourceLine.args[0])

    for operation in facts.base.operations.values():
        inputTypes = operation_input_types(operation)
        if not inputTypes:
            continue
        operationCalls = collect_operation_calls(operation)
        for callFact in operationCalls.values():
            if callFact.target not in responseBodyWriters:
                continue
            for argLine in callFact.arg_lines:
                if len(argLine.args) < 3:
                    continue
                if argLine.args[1] != "body":
                    continue
                bodyValueName = argLine.args[2]
                if bodyValueName not in inputTypes:
                    continue
                if (operation.name, bodyValueName) in declaredForwarders:
                    continue
                # If the op already declared a different forwarded input, let
                # SS3607 and SS3603 reason about that explicit contract rather
                # than double-reporting a second missing declaration here.
                if operation.name in declaredForwarderOps:
                    continue
                diagnostics.append(Diagnostic(
                    tier=Tier.T3_REFINEMENT,
                    code="SS3615",
                    kind="webserver.responseBodyForwarderMissing",
                    severity=Severity.WARNING,
                    subjectName=operation.name,
                    subjectKind="operation",
                    gapEdge="responseBodyForwarder",
                    intentSlogan="response wrapper lacks forwarder declaration",
                    primary=span_of_line(argLine, "forwardedBodyArgument"),
                    related=[
                        span_of_line(callFact.line, "responseWriterCall"),
                        span_of_line(operation.line, "enclosingOperation"),
                    ],
                    invariantRule=(
                        f"`{operation.name}` forwards input `{bodyValueName}` "
                        "to a response body writer; declare "
                        f"`responseBodyForwarder {operation.name} {bodyValueName}` "
                        "so nullable request-body/header values are checked "
                        "transitively through this wrapper"
                    ),
                    specAnchor="docs/reference/syntax-inventory.md#responseBodyForwarder",
                    citations=narrative_citations_for_operation(facts, operation.name),
                    fixCandidates=[
                        FixCandidate(
                            name="declareResponseBodyForwarder",
                            shape=f"responseBodyForwarder {operation.name} {bodyValueName}",
                            evidence=[span_of_line(argLine)],
                        ),
                    ],
                    confidence=Confidence.HIGH,
                    effort=Effort.TRIVIAL,
                    passProvenance="check_response_body_forwarder_missing",
                    agentHint=(
                        "without the forwarder verb, SS3603 cannot see nullable "
                        "request values that flow through this helper"
                    ),
                ))
    return diagnostics


def check_invalid_route_method(facts: ExtendedFacts) -> List[Diagnostic]:
    """SS3601 — `route SERVER METHOD PATH HANDLER` METHOD must be in the
    native dispatcher's whitelist. Unrecognized verbs never match at
    runtime and the handler binding becomes dead code."""
    diagnostics: List[Diagnostic] = []
    allowedList = ", ".join(sorted(HTTP_METHOD_WHITELIST))
    for routeFact in facts.base.routes:
        if is_supported_route_method(routeFact.method):
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
            specAnchor="docs/reference/syntax-inventory.md#route",
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


def check_placeholder_module_path(facts: ExtendedFacts) -> List[Diagnostic]:
    """SS2516 — advisory. `sem new` scaffolds `modulePath PROJECT
    github.com/example/<name>` as a placeholder. Left unchanged it can resolve
    imports/dependencies against a bogus origin, so nudge the author to set the
    real module path.

    Gated on the project actually declaring a `dependency` row: the harm this
    rule names (dependency resolution against a bogus origin) does not exist
    until there is a dependency to resolve, and firing on every freshly
    scaffolded project made `sem new` -> `sem check` noisy out of the box (a
    top agent-feedback friction). The nudge now appears exactly when it starts
    to matter; publishing-readiness, which is not statically detectable, stays
    the author's call."""
    diagnostics: List[Diagnostic] = []
    declares_dependency = any(
        line.tokens and not is_comment(line) and line.verb == "dependency"
        for line in facts.base.lines
    )
    if not declares_dependency:
        return diagnostics
    for sourceLine in facts.base.lines:
        if (not sourceLine.tokens or is_comment(sourceLine)
                or sourceLine.verb != "modulePath" or len(sourceLine.args) < 2):
            continue
        modulePath = sourceLine.args[1]
        if "github.com/example/" not in modulePath:
            continue
        diagnostics.append(Diagnostic(
            tier=Tier.T3_REFINEMENT,
            code="SS2516",
            kind="buildTape.placeholderModulePath",
            severity=Severity.WARNING,
            subjectName=sourceLine.args[0],
            subjectKind="project",
            gapEdge="modulePath",
            intentSlogan="placeholder modulePath from sem new",
            primary=span_of_line(sourceLine, "modulePathDeclaration"),
            invariantRule=(
                f"`modulePath {sourceLine.args[0]} {modulePath}` is the scaffold "
                f"placeholder; set the project's real module path so imports and "
                f"dependency resolution use the correct origin."
            ),
            specAnchor="docs/reference/package-management.md",
            fixCandidates=[
                FixCandidate(
                    name="setRealModulePath",
                    shape=f"modulePath {sourceLine.args[0]} github.com/<owner>/<repo>",
                ),
            ],
            confidence=Confidence.HIGH,
            blocksCompile=False,
            effort=Effort.TRIVIAL,
            passProvenance="check_placeholder_module_path",
            agentHint="replace the github.com/example/ placeholder with the real repository path",
        ))
    return diagnostics


def check_duplicate_route(facts: ExtendedFacts) -> List[Diagnostic]:
    """SS3611 — two `route` rows on the same server with the same METHOD+path.
    The native dispatcher matches the first registration, so every later
    duplicate is dead: its handler can never run, and the collision is almost
    always a copy-paste bug. Flagged on each duplicate after the first."""
    diagnostics: List[Diagnostic] = []
    seen: Dict[Tuple[str, str, str], RouteFact] = {}
    for routeFact in facts.base.routes:
        key = (routeFact.server, routeFact.method.upper(), routeFact.path)
        first = seen.get(key)
        if first is None:
            seen[key] = routeFact
            continue
        diagnostics.append(Diagnostic(
            tier=Tier.T1_SPEC,
            code="SS3611",
            kind="webserver.duplicateRoute",
            severity=Severity.ERROR,
            subjectName=routeFact.path,
            subjectKind="route",
            gapEdge="route.uniqueMethodPath",
            intentSlogan=f"duplicate route {routeFact.method} {routeFact.path}",
            primary=span_of_line(routeFact.line, "routeDeclaration"),
            related=[span_of_line(first.line, "firstRouteDeclaration")],
            invariantRule=(
                f"`route {routeFact.server} {routeFact.method} {routeFact.path} "
                f"{routeFact.handler}` collides with an earlier route for the same "
                f"METHOD+path (handler `{first.handler}`); the dispatcher matches "
                f"the first, so this binding is dead."
            ),
            specAnchor="docs/reference/syntax-inventory.md#route",
            fixCandidates=[
                FixCandidate(
                    name="removeDuplicateRoute",
                    shape=f"# remove the duplicate `route {routeFact.server} {routeFact.method} {routeFact.path} {routeFact.handler}`",
                ),
                FixCandidate(
                    name="distinguishPath",
                    shape=f"route {routeFact.server} {routeFact.method} <different-path> {routeFact.handler}",
                ),
            ],
            confidence=Confidence.HIGH,
            blocksCompile=True,
            effort=Effort.LOCAL,
            passProvenance="check_duplicate_route",
            agentHint="give the second route a distinct path/method, or delete it if it is a copy-paste leftover",
        ))
    return diagnostics


# Builtin call targets whose use implies an external, observable effect the
# operation must declare. Conservative on purpose: only the unambiguous,
# high-frequency external resources where the corpus already declares the
# effect 100% of the time, so flagging an omission is pure signal. (Maps
# call-target prefix -> (effect resource substring, human description).)
_EFFECT_REQUIRED_BY_CALL_PREFIX: Tuple[Tuple[str, str, str], ...] = (
    ("console.write", "console.stdout", "console.stdout"),
    ("http.response", "http.response", "http.response"),
)


def check_effect_under_declaration(facts: ExtendedFacts) -> List[Diagnostic]:
    """SS3640 — advisory. An operation that directly calls a builtin with a
    known external effect (writing console.stdout, writing the HTTP response)
    must declare that effect. Cross-checks the operation's direct call targets
    against its `effect` rows; a write to an observable resource with no matching
    effect declaration breaks the "effects are explicit and checkable" contract
    (§2) — a later edit could drop the call or the effect with nothing noticing."""
    diagnostics: List[Diagnostic] = []
    for operation in facts.base.operations.values():
        effectText: List[str] = []
        callTargets: List[Tuple[str, SourceLine]] = []
        for sourceLine in operation.lines:
            if not sourceLine.tokens or is_comment(sourceLine):
                continue
            if sourceLine.verb == "effect":
                effectText.append(" ".join(sourceLine.args))
            elif sourceLine.verb == "call" and len(sourceLine.args) >= 2:
                callTargets.append((sourceLine.args[1], sourceLine))
        effectBlob = " ".join(effectText)
        alreadyFlaggedResources: set = set()
        for target, callLine in callTargets:
            for prefix, resourceSubstring, humanResource in _EFFECT_REQUIRED_BY_CALL_PREFIX:
                if not target.startswith(prefix):
                    continue
                if resourceSubstring in effectBlob:
                    continue
                if humanResource in alreadyFlaggedResources:
                    continue
                alreadyFlaggedResources.add(humanResource)
                diagnostics.append(Diagnostic(
                    tier=Tier.T3_REFINEMENT,
                    code="SS3640",
                    kind="effectIntegrity.underDeclaredEffect",
                    severity=Severity.WARNING,
                    subjectName=operation.name,
                    subjectKind="operation",
                    gapEdge="effectDeclaration",
                    intentSlogan=f"undeclared effect on {humanResource}",
                    primary=span_of_line(callLine, "effectfulCallSite"),
                    related=[span_of_line(operation.line, "enclosingOperation")],
                    invariantRule=(
                        f"`{operation.name}` calls `{target}` (writes "
                        f"`{humanResource}`) but declares no matching `effect "
                        f"{operation.name} write {humanResource}` row; declared "
                        f"effects must cover the operation's observable behavior."
                    ),
                    specAnchor="docs/reference/syntax-inventory.md#effect",
                    fixCandidates=[
                        FixCandidate(
                            name="declareEffect",
                            shape=f"effect {operation.name} write {humanResource}",
                        ),
                    ],
                    confidence=Confidence.HIGH,
                    blocksCompile=False,
                    effort=Effort.TRIVIAL,
                    passProvenance="check_effect_under_declaration",
                    agentHint=(
                        "add the effect row (and back it with a matching "
                        "capability/authority); effects are the machine-readable "
                        "record of what the operation touches"
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
            specAnchor="docs/reference/syntax-inventory.md#routeMiddleware",
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
    """SS3603 - a value bound from a nullable http.request* read must not
    flow into the `body` argument of an http.response* writer (or a
    transitive wrapper) without an intervening `pointer.isNull` guard.

    Opt-out (per-operation): include the phrase `null-body failure path`
    or `null-body 500` in a `warning OP "..."` line. This matches the
    SemanticScript convention of pinning intentional negative-test surfaces
    in the source rather than the linter config - a future refactor that
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
                        specAnchor="docs/reference/syntax-inventory.md#pointer.isNull",
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


def check_untrusted_http_html_hydration(facts: ExtendedFacts) -> List[Diagnostic]:
    """SS3616 — request-derived bytes may flow into html.hydrate only through
    escaped string-like holes. Passing them as HtmlFragment / HtmlDocument
    would opt into raw insertion and bypass the compiler's HTML escaping.
    """
    diagnostics: List[Diagnostic] = []
    for operationName, operationFact in facts.base.operations.items():
        operationCalls = collect_operation_calls(operationFact)
        if not operationCalls:
            continue
        untrustedBindLines: Dict[str, SourceLine] = {}
        for callFact in operationCalls.values():
            if callFact.target not in HTTP_REQUEST_READER_TARGETS:
                continue
            for bindLine in [*callFact.bind_lines, *callFact.bind_ok_lines]:
                parsedBind = bind_parts(bindLine)
                if parsedBind is None:
                    continue
                untrustedBindLines[parsedBind[1]] = bindLine
        if not untrustedBindLines:
            continue

        valueTypes = _operation_value_types(facts, operationFact)
        for callFact in operationCalls.values():
            if not callFact.target.startswith("html.hydrate."):
                continue
            templateName = callFact.target[len("html.hydrate."):]
            for argLine in callFact.arg_lines:
                parsedArgument = argument_parts(argLine)
                if parsedArgument is None:
                    continue
                _callName, parameterName, declaredType, valueName = parsedArgument
                sourceLine = untrustedBindLines.get(valueName)
                if sourceLine is None:
                    continue
                effectiveType = declaredType or valueTypes.get(valueName)
                resolvedType = _resolve_type_alias_head(
                    effectiveType, facts.base.type_aliases)
                if resolvedType not in _HTML_RAW_HYDRATION_TYPES:
                    continue
                diagnostics.append(Diagnostic(
                    tier=Tier.T2_LOWERING,
                    code="SS3616",
                    kind="webserver.untrustedHtmlHydration",
                    severity=Severity.ERROR,
                    subjectName=valueName,
                    subjectKind="htmlHydrateArgument",
                    gapEdge="html.trustBoundary",
                    intentSlogan=(
                        f"request-derived `{valueName}` reaches raw HTML "
                        f"hydrate arg `{parameterName}`"
                    ),
                    primary=span_of_line(argLine, "htmlHydrateArgument"),
                    related=[
                        span_of_line(sourceLine, "requestReadBind"),
                        span_of_line(callFact.line, "htmlHydrateCall"),
                    ],
                    invariantRule=(
                        "values bound from http.request* readers are untrusted; "
                        "they may be passed to `html.hydrate.*` only as "
                        "string-like arguments that the compiler escapes. Raw "
                        "HTML types (`HtmlFragment`, `HtmlTrustedFragment`, "
                        "`HtmlDocument`) require a separate reviewed escape or "
                        "trust-conversion operation before hydration."
                    ),
                    specAnchor="docs/reference/syntax-inventory.md#html",
                    citations=narrative_citations_for_operation(facts, operationName),
                    fixCandidates=[
                        FixCandidate(
                            name="passAsEscapedString",
                            shape=(
                                f"argument {callFact.name} {parameterName} "
                                f"String {valueName}"
                            ),
                        ),
                        FixCandidate(
                            name="insertTrustConversion",
                            shape=(
                                f"# convert `{valueName}` through a reviewed "
                                "HTML sanitizer/trust boundary before passing a "
                                f"{resolvedType or 'raw HTML'} argument"
                            ),
                        ),
                    ],
                    confidence=Confidence.HIGH,
                    blocksCompile=True,
                    effort=Effort.LOCAL,
                    passProvenance="check_untrusted_http_html_hydration",
                    agentHint=(
                        "String hydrate holes are escaped by the compiler; raw "
                        "fragment/document holes are not. Do not type request "
                        "bytes as raw HTML without a visible sanitizer boundary."
                    ),
                ))
    return diagnostics


def check_middleware_return_type_is_middleware_control(facts: ExtendedFacts) -> List[Diagnostic]:
    """SS3610 — every operation bound via `routeMiddleware` MUST declare
    `output OP MiddlewareControl` (NOT bare `Int32`).

    The native HTTP dispatcher at sem_http_runtime.c interprets the
    middleware return value as a `MiddlewareControl` enum:

      - `continueMiddlewareControl`     (0) → call the route handler
      - `shortCircuitMiddlewareControl` (1) → skip the handler; send
        the response middleware already wrote
      - Anything else                       → send `500 middleware failed`

    A middleware op that declares bare `Int32` output silently
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
            if is_comment(sourceLine) or not sourceLine.tokens:
                continue
            parsedOutput = output_parts(sourceLine)
            if parsedOutput is None or parsedOutput[0] != operationName:
                continue
            outputLine = sourceLine
            # `output OP TYPE` or `output OP Result OK ERROR` — read
            # the OK type as the comparand. Middleware ops shouldn't
            # declare Result outputs (the dispatcher reads a raw i32),
            # but the rule still gets the right type either way.
            if parsedOutput[1] == "Result" and len(sourceLine.args) >= 3:
                declaredOutputType = sourceLine.args[2]
            else:
                declaredOutputType = parsedOutput[1]
                resultType = facts.base.result_types.get(declaredOutputType)
                if resultType is not None:
                    declaredOutputType = resultType.ok_type
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
                f"return-value site. A bare `Int32` output erases "
                f"the named-case contract: a returnValue of `1` would "
                f"silently short-circuit the route handler even when the "
                f"author intended it as a failure sentinel."
            ),
            specAnchor="docs/reference/syntax-inventory.md#MiddlewareControl",
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
    Int32]` positionally. A handler with `req`/`resp`/`r`/`rsp`
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
        if (not is_comment(sourceLine) and sourceLine.tokens
                and sourceLine.verb in {"routeNotFound", "routeMethodNotAllowed"}
                and len(sourceLine.args) >= 2):
            bindingSitesByOp.setdefault(sourceLine.args[1], []).append(sourceLine)
            continue
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
                    f"the native HTTP ABI defined at docs/reference/syntax-inventory.md#route requires "
                    f"every route-bound or middleware-bound operation to "
                    f"declare its `{inputType}` input under the exact name "
                    f"`{canonicalName}`. The dispatcher at semsc.py:2290 "
                    f"matches handlers positionally (`[HttpRequest, "
                    f"HttpResponse, Int32]`), but the linter and "
                    f"every other agent reading the source uses the "
                    f"canonical input names to resolve which slot is the "
                    f"request vs the response. A mismatch compiles and "
                    f"runs but silently breaks SS36xx's name-based lookups, "
                    f"so the rule is graded ERROR and blocks compile under "
                    f"--strict so the contract cannot drift unnoticed."
                ),
                specAnchor="docs/reference/syntax-inventory.md#route",
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
                    f"`req`/`resp`). The canonical SemanticScript names are "
                    f"`request` and `response` - match them and every "
                    f"downstream `arg <call> {canonicalName} {canonicalName}` "
                    f"resolves cleanly without positional inference."
                ),
            ))
    return diagnostics


def check_main_file_must_exist(facts: ExtendedFacts) -> List[Diagnostic]:
    """SS3614 - every `mainFile PROJECT "PATH"` row in a build tape MUST
    reference a file that exists on disk (resolved relative to
    `sourceRoot PROJECT "ROOT_PATH"`, or to the build tape's own
    directory when sourceRoot is absent).

    This catches the rename-rot scenario: when the module file gets
    renamed (e.g. `http_runtime_gauntlet.sscript` → `main.sem`) and the
    `mainFile` row in `build.sem` isn't updated, semsc would silently
    fail later in the build OR — worse — `importModule` would resolve
    via the module registry and the `mainFile` row would become a
    decorative lie. The lint surfaces the mismatch BEFORE compile.

    Resolution rules (matching semsc.py's build-tape resolver):
      1. `mainFile httpRuntimeGauntlet "main.sem"` is resolved relative to
         the directory of the build tape file.
      2. If `sourceRoot httpRuntimeGauntlet "."` is declared, the file is
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

    regular_plan = _regular_build_plan_payload(facts.base)
    if regular_plan is not None:
        payload, plan_line = regular_plan
        project = _regular_build_plan_object(payload, "project") or {}
        module = _regular_build_plan_main_module(payload) or {}
        project_name = _regular_build_plan_text(project, "id") or "BuildPlan"
        source_root = (
            _regular_build_plan_text(project, "sourceRoot")
            or _regular_build_plan_text(module, "sourceRoot")
        )
        main_file = _regular_build_plan_text(module, "mainFile")
        if source_root:
            sourceRootByProject[project_name] = (source_root, plan_line)
        if main_file:
            mainFileRows.append((project_name, main_file, plan_line))

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
            specAnchor="docs/reference/syntax-inventory.md#mainFile",
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


def _operation_output_type_and_line(
    operation: OperationFact,
) -> Tuple[Optional[str], Optional[SourceLine]]:
    for sourceLine in operation.lines:
        if is_comment(sourceLine) or not sourceLine.tokens:
            continue
        parsed = output_parts(sourceLine)
        if parsed is not None and parsed[0] == operation.name:
            return parsed[1], sourceLine
    return None, None


def check_webserver_lifecycle_hook_contract(facts: ExtendedFacts) -> List[Diagnostic]:
    """SS3617 - webServerStartup/webServerShutdown hooks must be validated
    during sem check, before codegen rejects the native HTTP entrypoint."""
    diagnostics: List[Diagnostic] = []
    declaredServers = {
        name for name, abstraction in facts.base.abstractions.items()
        if abstraction.kind == "webServer"
    }
    for sourceLine in facts.base.lines:
        if (is_comment(sourceLine) or not sourceLine.tokens
                or sourceLine.verb not in {"webServerStartup", "webServerShutdown"}
                or len(sourceLine.args) < 2):
            continue
        hookVerb = sourceLine.verb
        serverName = sourceLine.args[0]
        handlerName = sourceLine.args[1]
        if serverName not in declaredServers:
            diagnostics.append(Diagnostic(
                tier=Tier.T1_SPEC,
                code="SS3617",
                kind="webserver.lifecycleHookUnknownServer",
                severity=Severity.ERROR,
                subjectName=serverName,
                subjectKind="webServer",
                gapEdge="webServer",
                intentSlogan=f"{hookVerb} references unknown webServer `{serverName}`",
                primary=span_of_line(sourceLine, "webServerLifecycleHook"),
                invariantRule=(
                    f"`{hookVerb} SERVER HANDLER` must name a declared "
                    "`webServer SERVER` row before native HTTP codegen can "
                    "place the lifecycle hook in the server entrypoint"
                ),
                specAnchor="docs/reference/syntax-inventory.md#webServerStartup",
                fixCandidates=[
                    FixCandidate(
                        name="declareWebServer",
                        shape=f"webServer {serverName}",
                    ),
                ],
                confidence=Confidence.HIGH,
                blocksCompile=True,
                effort=Effort.TRIVIAL,
                passProvenance="check_webserver_lifecycle_hook_contract",
            ))

        operation = facts.base.operations.get(handlerName)
        if operation is None:
            diagnostics.append(Diagnostic(
                tier=Tier.T1_SPEC,
                code="SS3617",
                kind="webserver.lifecycleHookUndefinedHandler",
                severity=Severity.ERROR,
                subjectName=handlerName,
                subjectKind="operation",
                gapEdge="operation",
                intentSlogan=f"{hookVerb} handler `{handlerName}` is not defined",
                primary=span_of_line(sourceLine, "webServerLifecycleHook"),
                invariantRule=(
                    f"`{hookVerb} {serverName} {handlerName}` must name an "
                    "operation that exists in the resolved source stream"
                ),
                specAnchor="docs/reference/syntax-inventory.md#webServerStartup",
                fixCandidates=[
                    FixCandidate(
                        name="defineLifecycleOperation",
                        shape=(
                            f"operation {handlerName}\n"
                            f"output operation {handlerName} Int32\n"
                            f"memory {handlerName} heap no\n"
                            f"async {handlerName} no\n"
                            f"purpose operation {handlerName} \"Run the {hookVerb} lifecycle hook.\"\n"
                            f"storage local immutable successStatus Int32 0\n"
                            f"return value successStatus"
                        ),
                    ),
                ],
                confidence=Confidence.HIGH,
                blocksCompile=True,
                effort=Effort.TRIVIAL,
                passProvenance="check_webserver_lifecycle_hook_contract",
            ))
            continue

        inputLines = [
            opLine for opLine in operation.lines
            if input_parts(opLine) is not None
            and input_parts(opLine)[0] == operation.name
        ]
        if inputLines:
            diagnostics.append(Diagnostic(
                tier=Tier.T1_SPEC,
                code="SS3617",
                kind="webserver.lifecycleHookHasInputs",
                severity=Severity.ERROR,
                subjectName=handlerName,
                subjectKind="operation",
                gapEdge="input",
                intentSlogan=f"{hookVerb} handler `{handlerName}` declares inputs",
                primary=span_of_line(inputLines[0], "lifecycleHandlerInput"),
                related=[span_of_line(sourceLine, "webServerLifecycleHook")],
                invariantRule=(
                    f"`{hookVerb}` handlers run outside a request context and "
                    "must declare no `input operation` rows; only route and "
                    "middleware handlers receive HttpRequest/HttpResponse ABI inputs"
                ),
                specAnchor="docs/reference/syntax-inventory.md#webServerStartup",
                fixCandidates=[
                    FixCandidate(
                        name="removeLifecycleInputs",
                        shape=f"# remove input rows from operation {handlerName}",
                    ),
                ],
                confidence=Confidence.HIGH,
                blocksCompile=True,
                effort=Effort.TRIVIAL,
                passProvenance="check_webserver_lifecycle_hook_contract",
            ))

        outputType, outputLine = _operation_output_type_and_line(operation)
        if outputType != "Int32":
            primaryLine = outputLine if outputLine is not None else operation.line
            diagnostics.append(Diagnostic(
                tier=Tier.T1_SPEC,
                code="SS3617",
                kind="webserver.lifecycleHookOutputMustBeInt32",
                severity=Severity.ERROR,
                subjectName=handlerName,
                subjectKind="operation",
                gapEdge="output",
                intentSlogan=f"{hookVerb} handler `{handlerName}` must return Int32",
                primary=span_of_line(primaryLine, "lifecycleHandlerOutput"),
                related=[span_of_line(sourceLine, "webServerLifecycleHook")],
                invariantRule=(
                    f"`{hookVerb}` handlers are called directly by the native "
                    "HTTP entrypoint and must declare `output operation "
                    f"{handlerName} Int32`; Result-shaped or non-Int32 outputs "
                    "do not match the lifecycle ABI"
                ),
                specAnchor="docs/reference/syntax-inventory.md#webServerStartup",
                fixCandidates=[
                    FixCandidate(
                        name="declareLifecycleInt32Output",
                        shape=f"output operation {handlerName} Int32",
                    ),
                ],
                confidence=Confidence.HIGH,
                blocksCompile=True,
                effort=Effort.TRIVIAL,
                passProvenance="check_webserver_lifecycle_hook_contract",
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
                    specAnchor="docs/reference/syntax-inventory.md#routeTimeout",
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
                    specAnchor="docs/reference/syntax-inventory.md#routeMiddleware",
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
            specAnchor="docs/reference/syntax-inventory.md#pinsNullBodyFailurePath",
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
            specAnchor="docs/reference/syntax-inventory.md#pinsNullBodyFailurePath",
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
                specAnchor="docs/reference/syntax-inventory.md#rationale",
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
                specAnchor="docs/reference/syntax-inventory.md#rationale",
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
    Void`) should terminate with `returnVoid`, not `returnValue NAME`.

    The user-op ABI returns i32 even for Void outputs (see
    `_operation_output_contract` and the `Void → Int32` mapping), so a
    `returnValue someInt32Sentinel` form compiles — but the source is then
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
            if is_comment(sourceLine) or not sourceLine.tokens:
                continue
            parsedOutput = output_parts(sourceLine)
            if parsedOutput is not None and parsedOutput[0] == operationName:
                outputLine = sourceLine
                outputType = parsedOutput[1]
                break
        if outputType not in ("Void", "Void"):
            continue
        returnValueLine: Optional[SourceLine] = None
        returnValueName = ""
        for sourceLine in operationFact.lines:
            if is_comment(sourceLine) or not sourceLine.tokens:
                continue
            parsedReturn = return_parts(sourceLine)
            if parsedReturn is not None and parsedReturn[0] == "value" and parsedReturn[1] is not None:
                returnValueLine = sourceLine
                returnValueName = parsedReturn[1]
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
                f"`return void`, not `return value {returnValueName}`"
            ),
            primary=span_of_line(returnValueLine, "returnValueAtVoidOutput"),
            related=[span_of_line(outputLine, "voidOutputDeclaration")] if outputLine else [],
            invariantRule=(
                f"operations declared `output operation OP {outputType}` must end with "
                f"`return void` so the source matches the semantic contract. "
                f"`return value NAME` is the form for typed outputs; using it "
                f"on a Void-output op leaks the user-op ABI's i32 zero "
                f"sentinel into the source, which a future agent then has "
                f"to recognise as a Void-ABI quirk instead of as a real "
                f"value being returned."
            ),
            specAnchor="docs/reference/syntax-inventory.md#return",
            citations=narrative_citations_for_operation(facts, operationName),
            fixCandidates=[
                FixCandidate(
                    name="replaceReturnValueWithReturnVoid",
                    shape="return void",
                    autoApplicable=True,
                    evidence=[span_of_line(returnValueLine, "currentReturnValue")],
                ),
                FixCandidate(
                    name="changeOutputToTypedValue",
                    shape=(
                        f"# if `{operationName}` actually produces a "
                        f"caller-actionable value, change the output declaration:\n"
                        f"output operation {operationName} <ConcreteType>"
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
    `semsc.py:3674` and `test_http_runtime_gauntlet.py:273-279`, and both
    references would silently drift the moment those files got an
    insertion. Replacing the references with function names + rule
    IDs makes the citation stable.

    Fires WARNING — the narrative still parses, the code still
    compiles, the only loss is durability. Strict mode promotes to
    fatal for projects that want narrative durability enforced.
    """
    diagnostics: List[Diagnostic] = []
    # Track every narrative-bearing line. Per docs/reference/syntax-inventory.md, the narrative
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
                f"anchors (docs/reference/syntax-inventory.md#routeMiddleware), or grep-strings. "
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
    "targetRuntime", "buildProfile", "runtimeChecks", "asyncRuntime", "guiBackend",
    "persistLlvmIr", "nativeOutput", "keepResources", "resourcesDir",
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
    "buildConstant",
}

BUILD_TAPE_SINGLETON_VERBS: Set[str] = {
    "modulePath", "languageVersion", "projectVersion", "projectLicense",
    "sourceRoot", "mainFile", "mainOperation", "targetRuntime",
    "buildProfile", "runtimeChecks", "asyncRuntime", "guiBackend", "persistLlvmIr", "nativeOutput",
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
    # buildConstant PROJECT NAME TYPE VALUE — minimum arity 4.
    "buildConstant": 4,
}

BUILD_TAPE_ALLOWED_NON_PROJECT_VERBS: Set[str] = {
    "buildProject", "project", "target", "runtime", "entry", "import",
    "importModule",
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
GITHUB_HOST = "github.com"
GITHUB_OWNER_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?$")
GITHUB_REPO_RE = re.compile(r"^[A-Za-z0-9._-]+$")


def _is_https_url(value: str) -> bool:
    return value.startswith("https://") and " " not in value and len(value) > len("https://")


def _github_owner_repo_is_valid(value: str) -> bool:
    parts = value.split("/")
    if len(parts) >= 3 and parts[0].casefold() == GITHUB_HOST:
        parts = parts[1:]
    if len(parts) < 2:
        return False
    owner, repo = parts[:2]
    if not GITHUB_OWNER_RE.fullmatch(owner):
        return False
    if repo in {".", ".."} or not GITHUB_REPO_RE.fullmatch(repo):
        return False
    return all(part not in {"", ".", ".."} for part in parts[2:])


def _dependency_source_kind(args: Sequence[str]) -> Tuple[str, Sequence[str]]:
    if len(args) >= 4:
        return args[2], args[3:]
    if len(args) >= 3:
        sourceText = args[2]
        if sourceText.startswith(("https://", "http://")):
            return "http", args[2:3]
        sourceParts = sourceText.split("/", 1)
        if len(sourceParts) == 2 and sourceParts[0].casefold() == GITHUB_HOST:
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
                    edgeArgs: Sequence[str] = args
                    parsedInput = input_parts(opLine)
                    parsedOutput = output_parts(opLine)
                    if parsedInput is not None:
                        edgeArgs = [parsedInput[0], parsedInput[1], parsedInput[2]]
                    elif parsedOutput is not None:
                        edgeArgs = [parsedOutput[0], parsedOutput[1]]
                    add_edge(moduleName, exportVerb, symbolName,
                             f"operation.{verb}", edgeArgs, opLine)
                    resultOutputType = parsedOutput[1] if parsedOutput is not None else ""
                    resultTypeFact = facts.base.result_types.get(resultOutputType)
                    if resultTypeFact is not None:
                        failureType = resultTypeFact.error_type
                        add_edge(moduleName, exportVerb, symbolName,
                                 "operation.failureType", [failureType], opLine)
                        for (errorName, caseName), caseFact in facts.errorCases.items():
                            if errorName == failureType:
                                add_edge(moduleName, exportVerb, symbolName,
                                         "operation.failureCase",
                                         [errorName, caseName], caseFact.line)
                    elif (verb == "output" and len(args) >= 4
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
    ) or _regular_build_plan_payload(facts.base) is not None


def _json_body_storage_line_in_base(
    facts: ProgramFacts,
    json_body: JsonBodyFact,
) -> Optional[SourceLine]:
    for sourceLine in reversed(facts.lines):
        if sourceLine.number >= json_body.line.number:
            continue
        if sourceLine.verb != "storage" or len(sourceLine.args) < 4:
            continue
        if sourceLine.args[2] == json_body.name:
            return sourceLine
    return None


def _regular_build_plan_payload(
    facts: ProgramFacts,
) -> Optional[Tuple[Dict[str, object], SourceLine]]:
    if "BuildPlan" not in facts.records:
        return None
    for json_body in facts.json_bodies:
        storage_line = _json_body_storage_line_in_base(facts, json_body)
        if storage_line is None or len(storage_line.args) < 4:
            continue
        if storage_line.args[3] != "BuildPlan":
            continue
        body_text = "\n".join(text for text, _line in json_body.body_lines)
        try:
            payload = json.loads(body_text, parse_constant=_reject_json_constant)
        except (TypeError, ValueError, json.JSONDecodeError):
            return None
        if isinstance(payload, dict):
            return payload, json_body.line
    return None


def _regular_build_plan_object(
    payload: Dict[str, object],
    key: str,
) -> Optional[Dict[str, object]]:
    value = payload.get(key)
    return value if isinstance(value, dict) else None


def _regular_build_plan_text(
    section: Dict[str, object],
    key: str,
) -> Optional[str]:
    value = section.get(key)
    return value if isinstance(value, str) and value else None


def _regular_build_plan_module_entries(
    payload: Dict[str, object],
) -> List[Tuple[str, Dict[str, object]]]:
    modules = _regular_build_plan_object(payload, "modules")
    if modules is not None:
        entries: List[Tuple[str, Dict[str, object]]] = []
        for module_key, module_spec in modules.items():
            if isinstance(module_key, str) and isinstance(module_spec, dict):
                entries.append((module_key, module_spec))
        return entries
    module = _regular_build_plan_object(payload, "module")
    if module is not None:
        return [("main", module)]
    return []


def _regular_build_plan_main_module(
    payload: Dict[str, object],
) -> Optional[Dict[str, object]]:
    entries = _regular_build_plan_module_entries(payload)
    if not entries:
        return None
    main_key = _regular_build_plan_text(payload, "mainModule")
    if main_key:
        for module_key, module_spec in entries:
            if module_key == main_key:
                return module_spec
        return None
    return entries[0][1]


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

    regular_plan = _regular_build_plan_payload(facts.base)
    if regular_plan is not None:
        payload, plan_line = regular_plan
        project = _regular_build_plan_object(payload, "project")
        module_entries = _regular_build_plan_module_entries(payload)
        main_module = _regular_build_plan_main_module(payload)
        target = _regular_build_plan_object(payload, "target")
        missing_sections = [
            name for name, section in (
                ("project", project),
                ("modules", module_entries or None),
                ("target", target),
            )
            if section is None
        ]
        if missing_sections:
            diagnostics.append(_build_tape_diagnostic(
                plan_line,
                "SS2522",
                "buildTape.missingRequiredRow",
                "BuildPlan",
                "BuildPlan",
                "requiredBuildPlanSections",
                "BuildPlan is missing required sections",
                (
                    "Regular-syntax build.sem must provide project, module, "
                    "and target objects in its BuildPlan jsonBody."
                ),
                "jsonBody <plan>\n  {\"project\":{...},\"module\":{...},\"target\":{...}}",
            ))
            return diagnostics

        required_text_fields = [
            ("project", project, ("id", "name", "modulePath", "languageVersion", "projectVersion", "license")),
            ("target", target, ("runtime", "profile", "runtimeChecks")),
        ]
        for section_name, section, keys in required_text_fields:
            for key in keys:
                if _regular_build_plan_text(section, key) is not None:
                    continue
                diagnostics.append(_build_tape_diagnostic(
                    plan_line,
                    "SS2522",
                    "buildTape.missingRequiredRow",
                    "BuildPlan",
                    "BuildPlan",
                    f"{section_name}.{key}",
                    f"BuildPlan `{section_name}.{key}` is required",
                    (
                        "The regular build plan replaces the legacy build "
                        "rows, so each field that drives compiler metadata "
                        "must be present and non-empty."
                    ),
                    f"\"{key}\": \"<value>\"",
                ))

        if _regular_build_plan_object(payload, "modules") is not None:
            if _regular_build_plan_text(payload, "mainModule") is None:
                diagnostics.append(_build_tape_diagnostic(
                    plan_line,
                    "SS2522",
                    "buildTape.missingRequiredRow",
                    "BuildPlan",
                    "BuildPlan",
                    "mainModule",
                    "BuildPlan `mainModule` is required when using `modules`",
                    "A multi-module BuildPlan must name which module drives mainFile/mainOperation.",
                    "\"mainModule\": \"main\"",
                ))

        for module_key, module_spec in module_entries:
            for key in ("moduleName", "sourcePath", "mainFile"):
                if _regular_build_plan_text(module_spec, key) is not None:
                    continue
                diagnostics.append(_build_tape_diagnostic(
                    plan_line,
                    "SS2522",
                    "buildTape.missingRequiredRow",
                    "BuildPlan",
                    "BuildPlan",
                    f"modules.{module_key}.{key}",
                    f"BuildPlan `modules.{module_key}.{key}` is required",
                    "Each BuildPlan module entry must be resolvable to one source file.",
                    f"\"{key}\": \"<value>\"",
                ))
        if main_module is None:
            diagnostics.append(_build_tape_diagnostic(
                plan_line,
                "SS2522",
                "buildTape.missingRequiredRow",
                "BuildPlan",
                "BuildPlan",
                "mainModule",
                "BuildPlan mainModule does not name a declared module",
                "The mainModule field must match one key under modules.",
                "\"mainModule\": \"main\"",
            ))

        target_runtime = _regular_build_plan_text(target, "runtime") or ""
        main_operation = (
            _regular_build_plan_text(payload, "mainOperation")
            or _regular_build_plan_text(main_module or {}, "mainOperation")
        )
        if target_runtime in {"nativeExe", "windowsGui"} and main_operation is None:
            diagnostics.append(_build_tape_diagnostic(
                plan_line,
                "SS2522",
                "buildTape.missingRequiredRow",
                "BuildPlan",
                "BuildPlan",
                "mainOperation",
                "BuildPlan `mainOperation` is required for executable targets",
                "Native executable BuildPlan targets must name the entry operation.",
                "\"mainOperation\": \"main\"",
            ))
        if target_runtime and target_runtime not in BUILD_TAPE_CHOICES["targetRuntime"]:
            diagnostics.append(_build_tape_diagnostic(
                plan_line,
                "SS2525",
                "buildTape.invalidChoiceValue",
                target_runtime,
                "target.runtime",
                "closedEnumValue",
                f"`{target_runtime}` is not valid for BuildPlan target.runtime",
                (
                    "BuildPlan target.runtime lowers to targetRuntime and "
                    f"accepts only {', '.join(sorted(BUILD_TAPE_CHOICES['targetRuntime']))}."
                ),
                "\"runtime\": \"nativeExe\"",
            ))
        profile = _regular_build_plan_text(target, "profile") or ""
        if profile and profile not in BUILD_TAPE_CHOICES["buildProfile"]:
            diagnostics.append(_build_tape_diagnostic(
                plan_line,
                "SS2525",
                "buildTape.invalidChoiceValue",
                profile,
                "target.profile",
                "closedEnumValue",
                "`target.profile` must be dev or prod",
                "BuildPlan target.profile lowers to buildProfile.",
                "\"profile\": \"dev\"",
            ))
        gui_backend = _regular_build_plan_text(target, "guiBackend") or ""
        if gui_backend and gui_backend not in BUILD_TAPE_CHOICES["guiBackend"]:
            diagnostics.append(_build_tape_diagnostic(
                plan_line,
                "SS2525",
                "buildTape.invalidChoiceValue",
                gui_backend,
                "target.guiBackend",
                "closedEnumValue",
                f"`{gui_backend}` is not valid for BuildPlan target.guiBackend",
                (
                    "BuildPlan target.guiBackend lowers to guiBackend and "
                    f"accepts only {', '.join(sorted(BUILD_TAPE_CHOICES['guiBackend']))}."
                ),
                "\"guiBackend\": \"win32\"",
            ))
        runtime_checks = _regular_build_plan_text(target, "runtimeChecks") or ""
        if runtime_checks and runtime_checks not in BUILD_TAPE_CHOICES["runtimeChecks"]:
            diagnostics.append(_build_tape_diagnostic(
                plan_line,
                "SS2525",
                "buildTape.invalidChoiceValue",
                runtime_checks,
                "target.runtimeChecks",
                "closedEnumValue",
                "`target.runtimeChecks` must be off, traps, or panic",
                "BuildPlan target.runtimeChecks lowers to runtimeChecks.",
                "\"runtimeChecks\": \"panic\"",
            ))
        opt_level = target.get("optLevel")
        if isinstance(opt_level, bool) or not isinstance(opt_level, int) or opt_level < 0 or opt_level > 3:
            diagnostics.append(_build_tape_diagnostic(
                plan_line,
                "SS2525",
                "buildTape.invalidChoiceValue",
                str(opt_level),
                "target.optLevel",
                "llvmOptLevel",
                "`target.optLevel` must be an integer 0..3",
                "LLVM optimization levels exposed by BuildPlan are integers 0, 1, 2, or 3.",
                "\"optLevel\": 2",
            ))
        folder_name = _regular_build_plan_text(target, "buildFolderName")
        if folder_name:
            normalized = folder_name.replace("\\", os.sep).replace("/", os.sep)
            if (os.path.isabs(normalized)
                    or os.path.dirname(normalized)
                    or normalized in {"", ".", ".."}):
                diagnostics.append(_build_tape_diagnostic(
                    plan_line,
                    "SS2526",
                    "buildTape.invalidPathValue",
                    folder_name,
                    "target.buildFolderName",
                    "managedBuildFolderName",
                    "`target.buildFolderName` must be one folder name",
                    "BuildPlan buildFolderName renames the managed folder only.",
                    "\"buildFolderName\": \"build\"",
                ))
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
    regular_plan = _regular_build_plan_payload(buildFacts)
    if regular_plan is not None:
        payload, plan_line = regular_plan
        for _module_key, module in _regular_build_plan_module_entries(payload):
            module_name = _regular_build_plan_text(module, "moduleName")
            source_path = (
                _regular_build_plan_text(module, "sourcePath")
                or _regular_build_plan_text(module, "sourceRoot")
            )
            main_file = _regular_build_plan_text(module, "mainFile")
            if module_name and source_path:
                registered[module_name] = (plan_line, source_path)
            if main_file and main_file not in mainFiles:
                mainFiles.append(main_file)
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
        registeredModules: Dict[str, Tuple[SourceLine, str]] = {}
        mainFiles: List[str] = []
    else:
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
        elif buildFacts is not None:
            _registrationLine, rawPath = registration
            providerPath = _resolve_registered_module_source(
                importFact.module_name, rawPath, buildFacts.path, mainFiles)
        else:
            providerPath = None
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
    currentIsRegularBuildPlan = (
        currentIsBuildTape
        and _regular_build_plan_payload(buildFacts) is not None
    )

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
                specAnchor="docs/reference/syntax-inventory.md#registerModule",
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
                    specAnchor="docs/reference/syntax-inventory.md#exportOperation",
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
                        specAnchor="docs/reference/syntax-inventory.md#exportConstant",
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
                        specAnchor="docs/reference/syntax-inventory.md#exportConstant",
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
                    specAnchor="docs/reference/syntax-inventory.md#purpose",
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
                    specAnchor="docs/reference/syntax-inventory.md#naming",
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
                    specAnchor="docs/reference/syntax-inventory.md#effect",
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
                        specAnchor="docs/reference/syntax-inventory.md#exportOperation",
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
                specAnchor="docs/reference/syntax-inventory.md#exportOperation",
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

        if (verb == "module" and args and registeredNames
                and args[0] not in registeredNames
                and not currentIsRegularBuildPlan):
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
                specAnchor="docs/reference/syntax-inventory.md#registerModule",
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
                    specAnchor="docs/reference/syntax-inventory.md#importModule",
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
                    specAnchor="docs/reference/syntax-inventory.md#exportOperation",
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
                        specAnchor="docs/reference/syntax-inventory.md#exportOperation",
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
    elif verb == "input":
        parsedInput = input_parts(sourceLine)
        if parsedInput is not None:
            references.append(("type", parsedInput[2]))
    elif verb == "output":
        parsedOutput = output_parts(sourceLine)
        outputType = parsedOutput[1] if parsedOutput is not None else ""
        if outputType == "Result":
            if len(args) >= 3:
                references.append(("type", args[2]))
            if len(args) >= 4:
                references.append(("error", args[3]))
        elif outputType:
            references.append(("type", outputType))
    elif bind_parts(sourceLine) is not None:
        references.append(("type", bind_parts(sourceLine)[2]))  # type: ignore[index]
    elif ignore_parts(sourceLine) is not None:
        parsedIgnore = ignore_parts(sourceLine)
        if parsedIgnore is not None and parsedIgnore[2] is not None:
            references.append(("type", parsedIgnore[2]))
    elif verb == "useCapability" and len(args) >= 2:
        references.append(("capability", args[1]))
    elif verb == "makeError" and len(args) >= 2:
        qualified = args[1]
        parts = qualified.split(".")
        if len(parts) >= 3:
            references.append(("error", ".".join(parts[:2])))
    elif argument_parts(sourceLine) is not None:
        parsedArgument = argument_parts(sourceLine)
        if parsedArgument is not None:
            references.append(("constant", parsedArgument[3]))
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


def check_stdlib_module_no_smoke_main(facts: ExtendedFacts) -> List[Diagnostic]:
    """SS2515 - a `module standard.*` implementation file must not declare
    `operation main`.

    The standard library is always imported, never run directly, so a smoke
    `main` does not belong in the implementation module. Worse, a stray `main`
    in the imported module silently breaks the colocated `main.test.sem`: the
    test declares `entry console main`, but entry resolution only sees
    operations in the test compilation unit, not in the imported module, so
    codegen fails with `entry references unknown operation: main`. The smoke
    `main` (and its test-only MainError / capability scaffolding) belongs in
    `main.test.sem` next to the module, matching the canonical std/errno
    layout.
    """
    diagnostics: List[Diagnostic] = []
    # Test files legitimately carry the smoke main — only guard the
    # implementation module itself.
    if facts.base.path.name.endswith(".test.sem"):
        return diagnostics
    declaresStandardModule = any(
        sourceLine.verb == "module"
        and sourceLine.args
        and sourceLine.args[0].startswith("standard.")
        for sourceLine in facts.base.lines
        if sourceLine.tokens and not is_comment(sourceLine)
    )
    if not declaresStandardModule:
        return diagnostics
    for sourceLine in facts.base.lines:
        if not sourceLine.tokens or is_comment(sourceLine):
            continue
        if sourceLine.verb != "operation":
            continue
        if not sourceLine.args or sourceLine.args[0] != "main":
            continue
        diagnostics.append(Diagnostic(
            tier=Tier.T1_SPEC,
            code="SS2515",
            kind="module.standardLibraryDefinesSmokeMain",
            severity=Severity.ERROR,
            subjectName="main",
            subjectKind="operation",
            gapEdge="moduleEntryPurity",
            intentSlogan=(
                "standard-library module declares `operation main`; the smoke "
                "main belongs in the colocated main.test.sem"
            ),
            primary=span_of_line(sourceLine, "smokeMainInModule"),
            invariantRule=(
                "A `module standard.*` implementation file is imported, never "
                "run, and must not declare `operation main`. The smoke `main` "
                "(plus its test-only MainError and capability rows) lives in "
                "the colocated `main.test.sem`, which imports the module."
            ),
            specAnchor="docs/reference/syntax-inventory.md#module",
            fixCandidates=[
                FixCandidate(
                    name="moveSmokeMainToTest",
                    shape=(
                        "# move `operation main` and its MainError/capability "
                        "rows into main.test.sem (which imports this module)"
                    ),
                    evidence=[span_of_line(sourceLine)],
                ),
            ],
            confidence=Confidence.HIGH,
            blocksCompile=False,
            effort=Effort.LOCAL,
            passProvenance="check_stdlib_module_no_smoke_main",
            agentHint=(
                "a smoke main in the imported module silently fails the "
                "colocated test's `entry console main` resolution"
            ),
        ))
        break
    return diagnostics


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
                             or targetParts[1].startswith("decode.")
                             or targetParts[1].startswith("stringify.")
                             or targetParts[1].startswith("parse."))):
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
    check_syntax_cutover_rows,
    check_html_implicit_holes,
    check_unused_html_template,
    check_argument_arity,
    check_unresolved_references,
    check_branch_semantics,
    check_argument_type_mismatch,
    check_bind_return_type_domain,
    check_removed_scalar_surface,
    check_scalar_literal_ranges,
    check_enum_return_uses_case,
    check_math_operand_width_drift,
    check_constant_division_or_shift_ub,
    check_insecure_pseudorandom,
    check_weak_password_hash_cost,
    check_shell_command_not_constant,
    check_hardcoded_secret,
    check_duplicate_declarations,
    check_unknown_verbs,
    check_project_build_tape_schema,
    check_registered_module_contract,
    check_stdlib_module_no_smoke_main,
    check_module_import_contracts,
    check_unused_calls,
    check_unused_labels,
    check_unreachable_operation_rows,
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
    check_authority_effect_mismatch,
    check_column_memory_use_after_free,
    check_column_text_overwritten_before_use,
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
    check_loop_invariant_pure_call,
    check_string_accumulator_append_in_loop,
    check_snprintf_i32_offset_without_widening,
    check_gui_selection_handler_appends_list_item,
    check_row_count_mutation_unchecked,
    check_bind_then_ignore,
    check_memory_heap_contradiction,
    check_allocation_source_missing,
    check_unchecked_heap_allocation,
    check_allocate_free_unpaired,
    check_stack_limit_overrun,
    check_record_align_power_of_two,
    check_array_length_zero,
    check_inline_capacity_without_spill_allocator,
    check_literal_encoding_missing,
    # Style discipline (SS44xx) — info-severity hoist/rationale/dead-init signals
    check_duplicate_local_immutable_across_ops,
    check_large_local_static_literal,
    check_magic_ascii_byte_literal,
    check_dead_storage_initializer,
    check_fixed_offset_parser_needs_rationale,
    check_enum_repr_comparison,
    check_enum_result_discarded,
    check_paired_scalar_must_stay_equal,
    # Concurrency / type system / codec / resource (SS35xx, SS37xx, SS38xx, SS39xx)
    check_unawaited_task_group,
    check_lock_without_cleanup,
    check_invalid_submit_work,
    check_unawaited_submit_work,
    check_select_without_cases,
    check_select_case_references_unknown_select,
    check_await_wait_set_shape,
    check_async_call_missing_boundary,
    check_await_without_start,
    check_started_call_without_await,
    check_file_handle_not_closed,
    check_sqlite_database_failure_cleanup_missing,
    check_sqlite_statement_finalize_missing,
    check_guard_token_source_without_release,
    check_guard_token_protects_shared_state_access,
    check_circular_type_alias,
    check_json_codec_incomplete,
    check_runtime_backing_missing,
    # JSON CRUD / webserver discipline (SS36xx) — cursor safety, static
    # JsonPath checks, migration off legacy JSON helpers, route methods,
    # middleware contracts, nullable-input footgun detection, coverage
    # drift, and explicit-verb migrations
    check_unguarded_json_access,
    check_stale_json_cursor,
    check_malformed_json_path,
    check_unescaped_json_string_interpolation,
    check_deprecated_json_builder_calls,
    check_deprecated_json_finder_calls,
    check_json_body_literals,
    check_sql_body_literals,
    check_inline_sql_literals,
    check_redundant_sql_case_branches,
    check_sql_last_insert_rowid_function,
    check_wide_sql_existence_probe,
    check_sql_write_then_read_returning_opportunity,
    check_sqlite_multiple_writes_have_transaction,
    check_sqlite_returning_statement_drained_before_commit,
    check_process_environment_read_cached,
    check_repeated_request_time_reads,
    check_idempotency_replay_uses_response_status,
    check_invalid_route_method,
    check_duplicate_route,
    check_webserver_lifecycle_hook_contract,
    check_effect_under_declaration,
    check_placeholder_module_path,
    check_middleware_missing_response_effect,
    check_unguarded_http_input,
    check_untrusted_http_html_hydration,
    check_route_coverage_drift,
    check_legacy_null_body_marker,
    check_pins_null_body_failure_path_missing_rationale,
    check_response_body_forwarder_declaration_honored,
    check_response_body_forwarder_missing,
    check_rationale_call_references_known_call,
    check_route_handler_input_names,
    check_middleware_return_type_is_middleware_control,
    check_void_output_should_use_return_void,
    check_narrative_references_line_number,
    # Build-tape integrity (SS3614) — mainFile must reference a real file
    check_main_file_must_exist,
]


# A `# semlint-allow SSxxxx: rationale` comment on the line immediately above a
# flagged row acknowledges a single advisory at that site and removes it from
# the linter's output. The rationale is required (an annotation without one is
# ignored, so a forgotten reason never silently hides a finding). Compile-
# blocking diagnostics are NEVER suppressible — see _apply_lint_suppressions —
# so this can only quiet advisory noise (e.g. the SS3635 writes-without-
# transaction WARNING and the SS4002/SS4003 error-naming advisories on patterns
# the static check can't see through), never a real error. Scope note: this
# filters `semlint` diagnostics only; advisories raised by the compiler under
# `--strict` (semsc.py) are a separate surface and are unaffected.
_LINT_SUPPRESSION_RE = re.compile(
    r"#\s*semlint-allow\s+(SS\d{4})\b[:\s]+(\S.*?)\s*$")


def _collect_lint_suppressions(baseFacts: ProgramFacts) -> Dict[Tuple[str, int], str]:
    """Map (code, targetLine) -> rationale for every well-formed
    `# semlint-allow` annotation, where targetLine is the next source row after
    the annotation (the row the advisory is expected to point at)."""
    annotations: List[Tuple[str, int, str]] = []
    codeLineNumbers: List[int] = []
    for sourceLine in baseFacts.lines:
        if is_comment(sourceLine):
            match = _LINT_SUPPRESSION_RE.search(sourceLine.raw)
            if match:
                annotations.append(
                    (match.group(1), sourceLine.number, match.group(2).strip()))
        elif sourceLine.tokens:
            codeLineNumbers.append(sourceLine.number)
    suppressions: Dict[Tuple[str, int], str] = {}
    for code, annotationLine, rationale in annotations:
        if not rationale:
            continue
        targetLine = min(
            (number for number in codeLineNumbers if number > annotationLine),
            default=None)
        if targetLine is not None:
            suppressions[(code, targetLine)] = rationale
    return suppressions


def _apply_lint_suppressions(
    diagnostics: List[Diagnostic],
    suppressions: Dict[Tuple[str, int], str],
) -> List[Diagnostic]:
    if not suppressions:
        return diagnostics
    return [
        diagnostic for diagnostic in diagnostics
        # Compile-blocking diagnostics are never suppressible: a `semlint-allow`
        # can quiet an advisory, but it must not be able to hide a real error.
        if diagnostic.blocksCompile
        or (diagnostic.code, diagnostic.primary.line) not in suppressions
    ]


def lint_path(filePath: Path) -> List[Diagnostic]:
    baseFacts = parse_file_base(filePath)
    facts = gather_extended(baseFacts)
    diagnostics: List[Diagnostic] = []
    for checker in CHECKERS:
        diagnostics.extend(checker(facts))
    diagnostics = _apply_lint_suppressions(
        diagnostics, _collect_lint_suppressions(baseFacts))
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
# in docs/reference/syntax-inventory.md, so the output will NOT pass `semsc --lint --parse-only`. We
# emit the format here as a design demonstration; a real spec landing must
# precede production use. See refined-diagnostic design notes for the proposed grammar.
SEM_RECORD_HEADER = (
    "# DRAFT: diagnostic* verbs below are PROPOSED, not yet in docs/reference/syntax-inventory.md.\n"
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


def _strict_run_failed(diagnostics: Sequence[Diagnostic]) -> bool:
    """Whether `--strict` should fail the run. Strict gates on substance, not
    pure style: T4_STYLE naming advisories (SS4001 `Call` suffix, SS4002/SS4003
    bind/error naming, SS4004 vague names) never make a build fail — so reaching
    a clean strict build does not require mechanically renaming every call site.
    Any T0–T3 diagnostic (or a compile blocker, handled separately) still fails."""
    return any(d.tier != Tier.T4_STYLE for d in diagnostics)


def main(argv: Optional[Sequence[str]] = None) -> int:
    _force_utf8_streams()
    parser = argparse.ArgumentParser(
        prog="semlint",
        description=f"Refined SemanticScript linter — design playground. v{__version__}",
        epilog=(
            "Suppress a single advisory by placing a comment on the line "
            "directly above the row the diagnostic's `primary` points at:\n"
            "    # semlint-allow SS3635: BEGIN/COMMIT run through the runStatement helper\n"
            "A rationale is required; compile-blocking errors can never be "
            "suppressed this way; and the comment must sit on the line "
            "immediately above the flagged row (check the diagnostic's "
            "primary line) or it has no effect."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
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
        help="Exit non-zero on any diagnostic except T4 style/naming advisories "
             "(SS4001-SS4004), which never gate a build.",
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
    if args.strict and _strict_run_failed(allDiagnostics):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
