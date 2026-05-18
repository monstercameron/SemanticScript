#!/usr/bin/env python3
"""Refined AgentScript linter — design playground.

Parallel implementation of the linter that demonstrates the structured-
diagnostic architecture:

  * Tiered codes (T0 parse, T1 spec, T2 lowering, T3 refinement, T4 style)
  * Structured subject/gap fields (no prose-disguised-as-data)
  * Citations from narrative attachments (purpose/invariant/warning/
    security/timing/observability/# rationale:) — diagnostics CITE the
    author's stated intent rather than restating gaps in English
  * Fix candidates with evidence pointers and auto-applicable flags
  * Four output formats: human (block render), json (full), agent
    (priority queue), as-record (proposed AS-form, see header note)

The existing aslint.py stays as the stable surface. This file is the
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

# Reuse the existing tokenizer + facts. When the schemas need to diverge
# we'll fork; for now sharing keeps both linters honest about line shape.
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
if _THIS_DIR not in sys.path:
    sys.path.insert(0, _THIS_DIR)
from aslint import (  # type: ignore  # noqa: E402
    CallFact,
    OperationFact,
    ProgramFacts,
    SourceLine,
    comment_text,
    is_comment,
    parse_file as parse_file_base,
)

__version__ = "0.2.0"


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


# Names that are too vague for AgentScript's descriptive-identifier rule.
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


# Stack-byte estimates for primitive AS types. Used by AS3304 stack-limit
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
    # Console reads
    "c.fgets":                   ("read",  "console.stdin"),
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
    "c.fread":                   ("read",  "file"),
    "c.fwrite":                  ("write", "file"),
    "c.fseek":                   ("seek",  "file"),
    "c.ftell":                   ("read",  "file"),
    "c.open":                    ("open",  "file"),
    "c.close":                   ("close", "file"),
    "c.read":                    ("read",  "file"),
    "c.write":                   ("write", "file"),
}


# Primitive types that are interchangeable at the AS surface — `I64` and
# `CSignedInt64` are the same shape, `String` and `CNullTerminatedByteString`
# are the same wire form, etc. Used by the arg-type-mismatch check to avoid
# false-positive complaints about width-equivalent aliases.
_PRIMITIVE_TYPE_EQUIVALENCE_GROUPS: Tuple[frozenset, ...] = (
    # All signed integer widths AND Bool are treated as interchangeable
    # at the AS surface — the compiler emits the necessary sext/trunc/
    # zext automatically at call boundaries (Bool widens to integer
    # via zext), so flagging width mismatches here would only produce
    # noise that doesn't track real bugs.
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
    # so they live in the pointer family for AS arg-type purposes.
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
    "math.checkedMultiplyI64":    [("left", "I64"), ("right", "I64")],
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


# Minimum argument count per verb. AS lines are `verb arg1 arg2 …`; verbs
# with too few args can't be interpreted by any downstream pass. Ported
# from aslint.py and extended for refined-syntax surfaces.
VERB_MINIMUM_ARITY: Dict[str, int] = {
    # Project structure
    "project": 1, "target": 1, "runtime": 2, "entry": 2, "mode": 1,
    "module": 1, "section": 1, "importModule": 1,
    # Types / records / errors
    "type": 2, "typeInvariant": 2, "typeRepresentation": 2, "typeTrust": 2,
    "typeMemory": 2, "typeLayout": 2, "typeLiteralEncoding": 2,
    "typeLiteralTerminator": 2,
    "record": 1, "field": 3, "recordLayout": 2, "recordAlign": 2,
    "new": 2, "fieldSet": 3, "fieldGet": 4,
    "error": 1, "errorCase": 2, "enum": 1, "enumCase": 2,
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
# AS4101 reference-integrity checks.
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
# memory edges, etc.). Used by AS4104 unresolved-attachment-target check.
OPERATION_ATTACHMENT_VERBS: frozenset = frozenset({
    "input", "output", "effect", "async",
    "purpose", "invariant", "warning", "guarantee", "failure",
    "security", "timing", "observability",
    "memory", "memoryHeap", "memoryArena",
    "memoryAllocationSource", "memoryStackLimit",
    "operationBody", "useCapability", "authority",
})


# Comprehensive vocabulary built from SYNTAX.md. Verbs missing from this
# set are reported as AS0001 unknownVerb at T0 (parse / grammar). Additive
# refinements to AS land in SYNTAX.md first, then in this set — keeping
# both in lockstep is the linter's job over time.
KNOWN_AGENT_SCRIPT_VERBS: frozenset = frozenset({
    # Project structure
    "project", "target", "runtime", "entry", "module", "mode",
    # Imports & sections
    "importModule", "section",
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
    "async", "purpose", "invariant", "warning", "guarantee", "failure",
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
    "returnOk", "returnError", "returnValue",
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
    code: str                          # e.g. "AS0101"
    kind: str                          # e.g. "unusedDeclaration.call"
    severity: Severity

    # Primary span is required — every diagnostic must point at one place.
    primary: Span

    # Structured subject (pattern-matchable; agents read these, not English)
    subjectName: str = ""              # the AS identifier the diagnostic is about
    subjectKind: str = ""              # operation | call | label | capability | …
    gapEdge: str = ""                  # AS edge that's missing (useCapability, retryMaxAttempts, …)

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
    # `capability NAME EFFECT_PATH ACCESS` rows. Used by AS3104 to reuse an
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
    guardTokenReleaseDeclarations: Set[str] = field(default_factory=set)
    # JSON codec tracking
    jsonCodecDeclarations: Dict[str, SourceLine] = field(default_factory=dict)
    jsonCodecHasInput: Set[str] = field(default_factory=set)
    jsonCodecHasOutput: Set[str] = field(default_factory=set)
    jsonCodecHasDecodeTarget: Set[str] = field(default_factory=set)
    jsonCodecHasEncodeTarget: Set[str] = field(default_factory=set)


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
                facts.sharedStateAccesses.append(SharedStateAccessFact(
                    line=sourceLine,
                    accessKind="set",
                    slotName=args[1],
                    hasProtection="protectedBy" in args,
                ))
        elif verb == "read" and len(args) >= 4:
            # read sharedState BINDING TYPE BACKING [protectedBy GUARD]
            facts.storageReads.add(args[3])
            if args[0] == "sharedState":
                facts.sharedStateAccesses.append(SharedStateAccessFact(
                    line=sourceLine,
                    accessKind="read",
                    slotName=args[3],
                    hasProtection="protectedBy" in args,
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
            # follows in ARGS, record it for AS3503 cleanup pairing.
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
        elif verb == "guardTokenRelease" and args:
            facts.guardTokenReleaseDeclarations.add(args[0])
        # JSON codec completeness tracking
        elif verb == "jsonCodec" and args:
            facts.jsonCodecDeclarations[args[0]] = sourceLine
        elif verb == "jsonCodecInput" and args:
            facts.jsonCodecHasInput.add(args[0])
        elif verb == "jsonCodecOutput" and args:
            facts.jsonCodecHasOutput.add(args[0])
        elif verb == "jsonCodecDecodeTarget" and args:
            facts.jsonCodecHasDecodeTarget.add(args[0])
        elif verb == "jsonCodecEncodeTarget" and args:
            facts.jsonCodecHasEncodeTarget.add(args[0])

    return facts


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
# Per-op call collection (mirrors aslint.py's logic, kept local for clarity)
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


# ==========================================================================
# Checkers
#
# Code ranges:
#   AS00xx — grammar / parse                  (T0 — non-overridable error)
#            AS0001 unknownVerb, AS0002 argumentArityTooFew
#   AS01xx — unused declarations              (T3 refinement)
#            AS0101 call, AS0102 label, AS0103 capability, AS0104 errorCase,
#            AS0105 mutableStorage, AS0106 bindSlot,
#            AS0107 const, AS0108 input
#   AS12xx — partial declarations             (T3 refinement)
#            AS1201 retryPolicy, AS1202 trustBoundary, AS1203 externalLiteral
#   AS31xx — operation / coverage gaps        (T3 refinement)
#            AS3101 missing purpose, AS3102 missing invariant,
#            AS3104 capabilityCoverage, AS3105 unprotectedSharedState,
#            AS3106 hiddenFailure, AS3107 siblingMetadataDrift,
#            AS3111 undeclaredBodyEffect, AS3112 unknownErrorVariant
#   AS32xx — performance discipline           (T3 refinement)
#            AS3201 deadStore, AS3202 allocationInLoop,
#            AS3204 bindThenIgnore
#   AS33xx — memory / resource discipline     (T3 refinement)
#            AS3301 heapContradiction, AS3302 allocationSourceMissing,
#            AS3303 allocateFreeUnpaired, AS3304 stackLimitOverrun
#   AS34xx — layout / representation          (T3 refinement)
#            AS3401 recordAlignNotPowerOfTwo, AS3404 arrayLengthZero,
#            AS3405 inlineCapacityWithoutSpillAllocator,
#            AS3406 literalEncodingMissing
#   AS35xx — concurrency discipline           (T3 refinement)
#            AS3501 unawaitedTaskGroup, AS3503 lockWithoutCleanup,
#            AS3506 unawaitedSubmitWork, AS3507 selectWithoutCases,
#            AS3508 selectCaseReferencesUnknownSelect,
#            AS3510 asyncCallMissingBoundary
#   AS37xx — type system discipline           (T3 refinement)
#            AS3701 circularAlias
#   AS38xx — codec discipline                 (T3 refinement)
#            AS3801 jsonCodecIncomplete
#   AS39xx — resource lifecycle               (T3 refinement)
#            AS3901 fileHandleNotClosed,
#            AS3903 guardTokenSourceWithoutRelease
#   AS40xx — style discipline                 (T4 style)
#            AS4001 callObjectSuffix, AS4002 bindErrorSuffix,
#            AS4003 makeErrorSuffix, AS4004 vagueName
#   AS41xx — reference integrity              (T1 spec — blocks compile)
#            AS4101 unresolvedCall, AS4102 unresolvedLabel,
#            AS4103 unresolvedCapability,
#            AS4104 unresolvedOperationAttachment
#   AS42xx — duplicate declarations           (T1 spec — blocks compile)
#            AS4201 duplicateDeclaration (operation/label/call/type/record/
#                   error/capability/enum/retryPolicy/trustBoundary/jsonCodec)
#   AS43xx — type integrity                   (T1 spec — blocks compile)
#            AS4301 argumentTypeMismatch (resolves type aliases + primitive
#                   equivalences; skips unknowns to avoid false positives)
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
                code="AS0101",
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
    branched to. 213 such labels across stdlib_as. Treating these as unused
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
            code="AS0102",
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
    for capabilityName, capabilityFact in facts.capabilities.items():
        if capabilityName in facts.capabilityUses:
            continue
        diagnostics.append(Diagnostic(
            tier=Tier.T3_REFINEMENT,
            code="AS0103",
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
            code="AS0104",
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
                    # this fix doesn't subsequently trip AS4003 (makeError
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
            code="AS0105",
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
                    # so applying this fix doesn't subsequently trip AS3105
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
            # Future iteration: emit a separate AS1201a diagnostic just for the
            # maxAttempts gap and reference it here. For v0.3 we surface the
            # ordering hint through the agentHint + intentSlogan.
            pass
        diagnostics.append(Diagnostic(
            tier=Tier.T3_REFINEMENT,
            code="AS1201",
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
            code="AS1202",
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
            code="AS1203",
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
                "purpose", "AS3101",
                "draft from the body's calls, effects, and storage edges",
            ))

        touchesState = any(
            sourceLine.verb in {"set", "read"} for sourceLine in bodyLines
        )
        if touchesState and "invariant" not in existingNarrative:
            gapPlan.append((
                "invariant", "AS3102",
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
            code="AS3105",
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
                    # registered verbs so the fix doesn't trip AS0001.
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


def _build_capability_coverage_fix_candidates(
    operationName: str,
    effectAction: str,
    effectPath: str,
    effectLine: SourceLine,
    reusableCapabilityName: Optional[str],
    reusableCapabilityIsAlreadyUsed: bool,
) -> List[FixCandidate]:
    """Build AS3104 fix candidates, preferring reuse of an existing
    capability when one matches the effect path/action.

    Reconciliation with AS0103 (unused capability):
      - Unused matching capability → top fix is `useCapability` referencing
        it; clears AS3104 here AND AS0103 there in one stroke.
      - Already-used matching capability → top fix is `useCapability`
        referencing it; clears AS3104 here, AS0103 stays clear.
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
            # Reconcile with AS0103: if a declared capability covers this
            # (path, action), prefer reusing it over declaring a new one.
            # Unused matching capabilities are preferred — wiring it here
            # also clears AS0103 for that capability in one stroke.
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
                code="AS3104",
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
            code="AS0001",
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
                        code="AS4001",
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
                        code="AS4004",
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
                        code="AS4002",
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
                        code="AS4003",
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
                        code="AS4004",
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
                        code="AS4004",
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
                code="AS0106",
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
    drop failures. Matches aslint.py's hiddenFailure rule but on the new
    structured schema."""
    diagnostics: List[Diagnostic] = []
    for operation in facts.base.operations.values():
        operationCitations = narrative_citations_for_operation(facts, operation.name)
        operationCalls = collect_operation_calls(operation)
        for callFact in operationCalls.values():
            if callFact.target not in KNOWN_FALLIBLE_CALL_TARGETS:
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
                code="AS3106",
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
                        # the handler's returnError, AS0106 would fire on the
                        # newly-introduced bindError slot — a true cycle.
                        # `bindError` values end in `Error` per AS4002.
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
                code="AS3107",
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
                code="AS3111",
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
                        # The combined fix avoids the AS3111 → AS3104 cascade:
                        # adding `effect` alone would make AS3104 fire on the
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
                # Prerequisite chain: AS3111 fix (effect only) → AS3104 fires.
                # Declared here so agent walks fixes in order.
                prerequisite=[],
                passProvenance="check_undeclared_body_effect",
                agentHint=(
                    "declaring the effect ALONE will trigger AS3104 next; "
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
            code="AS3112",
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
    subsequent line of the same op. Mirrors AS0106 unusedDeclaration.bindSlot.
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
                code="AS0107",
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
                code="AS0108",
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
# These map C-tooling concerns onto AS's declared-intent vocabulary
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


def check_dead_store(facts: ExtendedFacts) -> List[Diagnostic]:
    """`set X val1` followed by `set X val2` with no read of X between is a
    dead store — the first write is overwritten before observation."""
    diagnostics: List[Diagnostic] = []
    for operation in facts.base.operations.values():
        operationCitations = narrative_citations_for_operation(facts, operation.name)
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
                        any(token.text == targetName for token in laterLine.tokens)
                        for laterLine in intervening
                        if not is_comment(laterLine) and laterLine.tokens
                        and laterLine.verb != "set"
                    )
                    if not isReadBetween:
                        diagnostics.append(Diagnostic(
                            tier=Tier.T3_REFINEMENT,
                            code="AS3201",
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
                    code="AS3202",
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
                code="AS3204",
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
                code="AS3301",
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
                        # declaration to pre-empt AS3302 cascading next.
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
                    "AS3302 next; the bundled fix avoids the cascade"
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
            code="AS3302",
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
    """Op body calls `c.malloc`/`c.calloc`/`c.realloc` but has no `defer`
    whose target is `c.free`. Likely leak."""
    diagnostics: List[Diagnostic] = []
    for operation in facts.base.operations.values():
        operationCitations = narrative_citations_for_operation(facts, operation.name)
        operationDefers = facts.operationDefers.get(operation.name, [])
        hasFreeDefer = any(
            target in HEAP_DEALLOCATION_CALL_TARGETS
            for _line, target in operationDefers
        )
        if hasFreeDefer:
            continue
        for sourceLine in operation.lines:
            if is_comment(sourceLine) or not sourceLine.tokens:
                continue
            if sourceLine.verb != "call" or len(sourceLine.args) < 2:
                continue
            if sourceLine.args[1] not in HEAP_ALLOCATION_CALL_TARGETS:
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
                code="AS3303",
                kind="resourceLifecycle.allocateFreeUnpaired",
                severity=Severity.WARNING,
                subjectName=sourceLine.args[0],
                subjectKind="call",
                gapEdge="defer",
                intentSlogan="heap allocation without paired free defer",
                primary=span_of_line(sourceLine, "allocatingCall"),
                related=[span_of_line(operation.line, "enclosingOperation")],
                invariantRule=(
                    f"every `{sourceLine.args[1]}` should be paired with a "
                    f"`defer NAME c.free <pointerArg>` in the same operation"
                ),
                specAnchor="SYNTAX.md#defer",
                citations=operationCitations,
                fixCandidates=[
                    FixCandidate(
                        name="addFreeDefer",
                        shape=f"defer release{sourceLine.args[0][:1].upper()}{sourceLine.args[0][1:]} c.free <allocatedPointer>",
                        evidence=[span_of_line(sourceLine)],
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
            code="AS3304",
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
            code="AS3401",
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
            code="AS3404",
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
            agentHint="zero-length arrays are a C-ism that AS's sliceType handles cleanly",
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
            code="AS3405",
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
        # Primitive AS types don't need typeLiteralEncoding rows — they're
        # already encoded by their representation.
        if literalFact.typeName in PRIMITIVE_TYPE_STACK_BYTES:
            continue
        diagnostics.append(Diagnostic(
            tier=Tier.T3_REFINEMENT,
            code="AS3406",
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
# Concurrency / resource / type-system / codec discipline (AS35xx async,
# AS37xx type system, AS38xx codec, AS39xx resource handles)
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
                code="AS3501",
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
                code="AS3503",
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
                        # error returns. Same pattern as AS3303 allocate/free.
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
                code="AS3506",
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
            code="AS3507",
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
                code="AS3508",
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
                        # this fix doesn't subsequently trip AS3507.
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
                    "declaring the select alone trips AS3507 next; the bundled "
                    "fix preserves at least one case"
                ),
            ))
    return diagnostics


def check_async_call_missing_boundary(facts: ExtendedFacts) -> List[Diagnostic]:
    """An awaited call should declare BOTH a `timeout CALL DURATION` and
    a `cancelOn CALL TOKEN` — without them the await is unbounded and
    uncancellable. Consolidates aslint.py's unboundedAsyncCall +
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
                code="AS3510",
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
    `c.close` defer in the same op. Same shape as AS3303 but for file
    handles."""
    diagnostics: List[Diagnostic] = []
    fileOpenTargets: Set[str] = {"c.fopen", "c.open"}
    fileCloseTargets: Set[str] = {"c.fclose", "c.close"}
    for operation in facts.base.operations.values():
        operationCitations = narrative_citations_for_operation(facts, operation.name)
        operationDefers = facts.operationDefers.get(operation.name, [])
        hasCloseDefer = any(
            deferTarget in fileCloseTargets
            for _deferLine, deferTarget in operationDefers
        )
        if hasCloseDefer:
            continue
        for sourceLine in operation.lines:
            if is_comment(sourceLine) or not sourceLine.tokens:
                continue
            if sourceLine.verb != "call" or len(sourceLine.args) < 2:
                continue
            callTarget = sourceLine.args[1]
            if callTarget not in fileOpenTargets:
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
                code="AS3901",
                kind="resourceLifecycle.fileHandleNotClosed",
                severity=Severity.WARNING,
                subjectName=sourceLine.args[0],
                subjectKind="call",
                gapEdge="defer",
                intentSlogan="file handle opened without paired close defer",
                primary=span_of_line(sourceLine, "openCall"),
                related=[span_of_line(operation.line, "enclosingOperation")],
                invariantRule=(
                    f"every `{callTarget}` should be paired with a "
                    f"`defer NAME {closeTargetSuggestion} <handle>` in the same operation"
                ),
                specAnchor="SYNTAX.md#defer",
                citations=operationCitations,
                fixCandidates=[
                    FixCandidate(
                        name="addCloseDefer",
                        shape=(
                            f"defer release{sourceLine.args[0][:1].upper()}{sourceLine.args[0][1:]} "
                            f"{closeTargetSuggestion} <openedHandle>"
                        ),
                        evidence=[span_of_line(sourceLine)],
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
            code="AS3903",
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
                    code="AS3701",
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
            code="AS3801",
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
            code="AS0002",
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

    # Build per-op sets of declared call objects + labels.
    operationCallsByOperationName: Dict[str, Set[str]] = {}
    operationLabelsByOperationName: Dict[str, Set[str]] = {}
    for operation in facts.base.operations.values():
        operationCallsByOperationName[operation.name] = set(
            collect_operation_calls(operation).keys()
        )
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
        declaredLabelNames = operationLabelsByOperationName.get(operation.name, set())

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
                    code="AS4101",
                    declarationShape=f"call {referencedCallName} <target>",
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
                        code="AS4102",
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
                    code="AS4102",
                    declarationShape=f"label {referencedLabelName}",
                ))

            # useCapability references — args[1] is the capability name
            if verb == "useCapability" and len(sourceLine.args) >= 2:
                referencedCapabilityName = sourceLine.args[1]
                if referencedCapabilityName not in facts.capabilities:
                    diagnostics.append(_unresolved_reference_diagnostic(
                        sourceLine=sourceLine,
                        operation=operation,
                        operationCitations=operationCitations,
                        referencedName=referencedCapabilityName,
                        referencedKind="capability",
                        verbThatReferenced=verb,
                        code="AS4103",
                        declarationShape=f"capability {referencedCapabilityName} <effectPath> <action>",
                    ))

    # Module-scope: attachment verbs reference operations at args[0]
    for sourceLine in facts.base.lines:
        if not sourceLine.tokens or is_comment(sourceLine) or not sourceLine.args:
            continue
        if sourceLine.verb not in OPERATION_ATTACHMENT_VERBS:
            continue
        referencedOperationName = sourceLine.args[0]
        if referencedOperationName in facts.base.operations:
            continue
        # Don't double-emit for ops that simply don't exist — emit one AS4104
        diagnostics.append(Diagnostic(
            tier=Tier.T1_SPEC,
            code="AS4104",
            kind="referenceIntegrity.unresolvedOperationAttachment",
            severity=Severity.ERROR,
            subjectName=referencedOperationName,
            subjectKind="operation",
            gapEdge="operationDeclaration",
            intentSlogan=f"`{sourceLine.verb}` attaches to undeclared operation",
            primary=span_of_line(sourceLine, "attachmentSite"),
            invariantRule=(
                f"`{sourceLine.verb} {referencedOperationName} …` requires a prior "
                f"`operation {referencedOperationName}` declaration"
            ),
            specAnchor="SYNTAX.md#operation",
            fixCandidates=[
                FixCandidate(
                    name="declareOperation",
                    shape=f"operation {referencedOperationName}",
                ),
                FixCandidate(
                    name="correctOperationName",
                    shape=f"# verify `{referencedOperationName}` spelling against your operation declarations",
                ),
            ],
            confidence=Confidence.HIGH,
            blocksCompile=True,
            effort=Effort.LOCAL,
            passProvenance="check_unresolved_references",
            agentHint="attachment-verb typos are the #1 source of silent narrative drift",
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


def _resolve_type_to_canonical(typeName: Optional[str], typeAliases: Dict[str, str]) -> Optional[str]:
    """Chase a name through `type X Y` aliases, then collapse to a canonical
    primitive when the alias terminus is one of the equivalence groups."""
    if typeName is None:
        return None
    visited: Set[str] = set()
    currentName = typeName
    while currentName in typeAliases and currentName not in visited:
        visited.add(currentName)
        currentName = typeAliases[currentName]
    return PRIMITIVE_CANONICAL_BY_TYPE.get(currentName, currentName)


def check_argument_type_mismatch(facts: ExtendedFacts) -> List[Diagnostic]:
    """`arg CALL ARGNAME VALUE` where VALUE's declared type doesn't match
    the call target's expected type for ARGNAME. Looks up target signature
    from BUILTIN_TARGET_SIGNATURES (for built-ins) or from `input OP NAME
    TYPE` rows (for user ops). Skipped when either type is unknown — we
    err on the side of false negatives rather than false positives."""
    diagnostics: List[Diagnostic] = []
    typeAliases = facts.base.type_aliases

    # Build per-user-op signature: argName → declared type
    userOperationSignatures: Dict[str, Dict[str, str]] = {}
    for operation in facts.base.operations.values():
        signature: Dict[str, str] = {}
        for sourceLine in operation.lines:
            if (sourceLine.tokens and not is_comment(sourceLine)
                    and sourceLine.verb == "input" and len(sourceLine.args) >= 3
                    and sourceLine.args[0] == operation.name):
                signature[sourceLine.args[1]] = sourceLine.args[2]
        userOperationSignatures[operation.name] = signature

    # Build module-scope value-name → type map from forms that survive
    # outside any operation body (domain literals, module storage, etc.).
    moduleScopeValueTypes: Dict[str, str] = {}
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
                # Unresolved call — AS4101 already handles that.
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

            resolvedExpected = _resolve_type_to_canonical(expectedType, typeAliases)
            resolvedActual = _resolve_type_to_canonical(actualType, typeAliases)
            if resolvedExpected == resolvedActual:
                continue

            diagnostics.append(Diagnostic(
                tier=Tier.T1_SPEC,
                code="AS4301",
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
            code="AS4201",
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


CHECKERS = [
    # Foundational basics — run first so reference / arity / duplicate
    # errors surface before any refinement-level diagnostic.
    check_argument_arity,
    check_unresolved_references,
    check_argument_type_mismatch,
    check_duplicate_declarations,
    check_unknown_verbs,
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
    check_effect_without_capability,
    check_hidden_failure,
    check_sibling_metadata_drift,
    check_undeclared_body_effect,
    check_make_error_unknown_variant,
    check_unused_const,
    check_unused_input,
    check_vague_names,
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
    # Concurrency / type system / codec / resource (AS35xx, AS37xx, AS38xx, AS39xx)
    check_unawaited_task_group,
    check_lock_without_cleanup,
    check_unawaited_submit_work,
    check_select_without_cases,
    check_select_case_references_unknown_select,
    check_async_call_missing_boundary,
    check_file_handle_not_closed,
    check_guard_token_source_without_release,
    check_circular_type_alias,
    check_json_codec_incomplete,
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


# Note for the as-record format: the `diagnostic*` verbs emitted below are
# DRAFT PROPOSALS for the diagnostic syntax surface — they are not yet rows
# in SYNTAX.md, so the output will NOT pass `ascc --lint --parse-only`. We
# emit the format here as a design demonstration; a real spec landing must
# precede production use. See aslint2 design notes for the proposed grammar.
AS_RECORD_HEADER = (
    "# DRAFT: diagnostic* verbs below are PROPOSED, not yet in SYNTAX.md.\n"
    "# Output will not pass `ascc --lint --parse-only` until the diagnostic\n"
    "# syntax surface is landed. See aslint2 design notes.\n"
)


def render_as_record(diagnostics: Sequence[Diagnostic]) -> str:
    """Proposed AS-form rendering: diagnostics as parseable declaration blocks.
    Header explicitly marks the verbs as draft."""
    chunks: List[str] = [AS_RECORD_HEADER]
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
            collected.extend(sorted(candidatePath.rglob("*.as")))
        elif candidatePath.is_file():
            collected.append(candidatePath)
        else:
            collected.extend(sorted(Path().glob(rawPath)))
    return collected


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="aslint2",
        description=f"Refined AgentScript linter — design playground. v{__version__}",
    )
    parser.add_argument("paths", nargs="+")
    parser.add_argument(
        "--format",
        choices=["human", "json", "agent", "as-record"],
        default="human",
        help="Output format. as-record emits proposed AS-form (see header).",
    )
    parser.add_argument(
        "--tier", action="append",
        help="Filter to tiers (T0..T4). May be repeated.",
    )
    parser.add_argument(
        "--code", action="append",
        help="Filter to codes (e.g. AS0101). May be repeated.",
    )
    parser.add_argument(
        "--strict", action="store_true",
        help="Exit non-zero on any diagnostic.",
    )
    parser.add_argument(
        "--summary", action="store_true",
        help="Print a tier/severity summary after diagnostics (human format only).",
    )
    args = parser.parse_args(argv)

    resolvedPaths = collect_paths(args.paths)
    if not resolvedPaths:
        print("aslint2: no .as files matched", file=sys.stderr)
        return 2

    allDiagnostics: List[Diagnostic] = []
    for resolvedPath in resolvedPaths:
        try:
            allDiagnostics.extend(lint_path(resolvedPath))
        except OSError as readError:
            print(f"aslint2: failed to read {resolvedPath}: {readError}", file=sys.stderr)
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
        "as-record": render_as_record,
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
